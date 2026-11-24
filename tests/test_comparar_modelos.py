"""Pruebas de la comparación de modelos con datos sintéticos y ficticios."""

import json
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from precio_entorno.comparar_modelos import MODELS, build_models, compare, load_dataset

BARRIOS = {'Caballito': 2600, 'Almagro': 2300, 'Flores': 1900, 'Palermo': 3400}


def synthetic(n_per_barrio=60, seed=0):
    """Precio por m² que baja con la superficie dentro de cada barrio (señal lineal)."""
    rng = np.random.default_rng(seed)
    rows = []
    cases = [(b, barrio, base, i) for b, (barrio, base) in enumerate(BARRIOS.items()) for i in range(n_per_barrio)]
    for b, barrio, base, i in cases:
        area = rng.uniform(30, 120)
        rows.append({'id': f'ficticio:{b}-{i}', 'neighborhood': barrio, 'agency': 'ficticio',
                     'rooms': int(area // 25) + 1, 'covered_area': area, 'total_area_m2': area * 1.1,
                     'latitude': -34.6 + rng.normal(0, 0.01), 'longitude': -58.43 + rng.normal(0, 0.01),
                     'precio_m2': base - 8 * area + rng.normal(0, 40)})
    df = pd.DataFrame(rows)
    df['price'] = df['precio_m2'] * df['covered_area']
    df['grupo'] = df['id']
    return df


class CompararModelosTests(unittest.TestCase):
    def setUp(self):
        warnings.simplefilter('ignore')

    def test_compares_six_models_and_reference_on_same_partition(self):
        table, info = compare(synthetic(), folds=3)
        self.assertEqual(set(table['modelo']), set(MODELS) | {'comparables'})
        self.assertTrue(np.isfinite(table[['mae_prueba', 'mae_cv_medio', 'rmse_prueba']].to_numpy()).all())
        self.assertEqual(info['particion']['pliegues'], 3)
        self.assertEqual(info['particion']['observaciones_entrenamiento']
                         + info['particion']['observaciones_prueba'], 240)
        # Los comparables ignoran la superficie; la regresión lineal la aprovecha.
        cv = table.set_index('modelo')['mae_cv_medio']
        self.assertLess(cv['regresion_lineal'], cv['comparables'])
        self.assertTrue(table['mae_cv_medio'].is_monotonic_increasing)

    def test_unseen_barrio_in_test_does_not_fail(self):
        df = synthetic(30)
        train, test = df[df['neighborhood'] != 'Palermo'], df[df['neighborhood'] == 'Palermo']
        numeric = ['covered_area', 'total_area_m2', 'rooms', 'latitude', 'longitude']
        for name, model in build_models(numeric, ['neighborhood'], seed=1).items():
            model.fit(train[numeric + ['neighborhood']], train['precio_m2'])
            self.assertEqual(len(model.predict(test[numeric + ['neighborhood']])), len(test), name)

    def test_load_dataset_adds_building_fields_by_id_without_inventing_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            pd.DataFrame({'id': ['a:1', 'a:2', 'b:3'], 'precio_m2': [1, 2, 3]}).to_csv(tmp / 'd.csv', index=False)
            (tmp / 'e1.json').write_text(json.dumps([
                {'listing_id': 'a:1', 'age_years': 30, 'garages': None},
                {'listing_id': 'a:1', 'age_years': 32, 'garages': 1},
                {'listing_id': 'b:3', 'age_years': None, 'garages': 2}]), encoding='utf-8')
            df = load_dataset(tmp / 'd.csv', [tmp / 'e1.json']).set_index('id')
        self.assertEqual(df.at['a:1', 'age_years'], 32)
        self.assertEqual(df.at['a:1', 'garages'], 1)
        self.assertTrue(np.isnan(df.at['a:2', 'age_years']))
        self.assertTrue(np.isnan(df.at['b:3', 'age_years']))
        self.assertEqual(df.at['b:3', 'agency'], 'b')
        self.assertEqual(df.at['b:3', 'grupo'], 'b:3')


if __name__ == '__main__':
    unittest.main()
