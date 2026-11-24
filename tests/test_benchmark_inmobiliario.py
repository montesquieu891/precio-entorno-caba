import unittest

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold
from threadpoolctl import threadpool_limits

from precio_entorno.benchmark_inmobiliario import (
    CATEGORICAL, EXTRA, NUMERIC, bootstrap_mae_delta, model_specs, scores, simple_baselines, training_comparables,
)


class BenchmarkIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.data = pd.DataFrame({
            'grupo': np.repeat([f'grupo-{i}' for i in range(60)], 2),
            'neighborhood': 'Almagro', 'agency': 'fuente', 'rooms': 2,
            'precio_m2': np.repeat(1_000 + np.arange(60) * 20, 2),
            'price': 100_000, 'covered_area': 50, 'total_area_m2': 60, 'age_years': 10,
        })

    def test_nested_folds_separate_duplicate_properties(self):
        data = self.data
        seen = []
        for train_index, test_index in GroupKFold(5).split(data, groups=data.grupo):
            train, test = data.iloc[train_index], data.iloc[test_index]
            self.assertTrue(set(train.grupo).isdisjoint(test.grupo))
            seen.extend(test_index)
            self.assert_inner_folds_separate(train, test)
        self.assertEqual(sorted(seen), list(range(len(data))))

    def assert_inner_folds_separate(self, train, test):
        for a, b in GroupKFold(3).split(train, groups=train.grupo):
            self.assertTrue(set(train.iloc[a].grupo).isdisjoint(train.iloc[b].grupo))
            self.assertTrue(set(train.iloc[b].grupo).isdisjoint(test.grupo))

    def test_comparables_use_training_prices_and_count_properties(self):
        train, test = self.data.iloc[:100], self.data.iloc[100:].copy()
        initial = training_comparables(train, test)
        test['precio_m2'] = 100
        mutated = training_comparables(train, test)
        self.assertTrue(initial.n_ref.eq(50).all())
        self.assertTrue(initial.n_ref.equals(mutated.n_ref))
        train_prices = train.groupby('grupo').precio_m2.median()
        median = train_prices.median()
        scale = 1.4826 * (train_prices - median).abs().median()
        np.testing.assert_allclose(initial.z_ref, (initial.precio_m2 - median) / scale)
        np.testing.assert_allclose(mutated.z_ref, (test.precio_m2 - median) / scale)

    def test_missing_or_constant_reference_is_not_a_positive(self):
        train = self.data.iloc[:100].assign(precio_m2=2_000)
        for neighborhood in ['Almagro', 'Caballito']:
            with self.subTest(neighborhood=neighborhood):
                test = self.data.iloc[100:].assign(neighborhood=neighborhood)
                refs = training_comparables(train, test)
                self.assertFalse(refs.supported.any())
                self.assertFalse(refs.proxy.any())

    def test_all_families_handle_unknown_categories(self):
        train = self.data.copy()
        for name in NUMERIC:
            if name not in train:
                train[name] = np.linspace(1, 10, len(train))
        train['cond_code'] = np.nan
        features = NUMERIC + CATEGORICAL + EXTRA
        test = train.iloc[:2].assign(agency='otra fuente', neighborhood='Caballito')
        specs = model_specs(True)
        self.assertEqual(set(specs), {'Ridge', 'KNN', 'Random Forest', 'HistGradientBoosting', 'MLP'})
        with threadpool_limits(limits=1):
            for name, (model, _) in specs.items():
                with self.subTest(model=name):
                    model.fit(train[features], np.log(train.precio_m2))
                    self.assertTrue(np.isfinite(model.predict(test[features])).all())

    def test_mdape_and_paired_interval(self):
        base = pd.DataFrame({
            'row': [0, 1], 'grupo': ['a', 'b'], 'precio_m2': [1_000, 2_000], 'error': [100, -200],
        })
        self.assertEqual(scores(base).mdape_pct, 10)
        improved = base.assign(error=[0, -100])
        np.testing.assert_allclose(bootstrap_mae_delta(improved, base), [-100, -100])

    def test_simple_baselines_ignore_test_price_and_duplicate_copies(self):
        train, test = self.data.iloc[:100], self.data.iloc[100:].copy()
        original = simple_baselines(train, test)
        mutated = simple_baselines(pd.concat([train, train]), test.assign(precio_m2=1))
        for name in original:
            np.testing.assert_allclose(original[name], mutated[name])
        self.assertTrue(np.all(original['Mediana comparables'] == train.groupby('grupo').precio_m2.median().median()))

    def test_bootstrap_rejects_unpaired_predictions(self):
        base = pd.DataFrame({'row': [0, 1], 'grupo': ['a', 'b'], 'precio_m2': [100, 200], 'error': [10, 20]})
        for bad in [base.iloc[:1], base.assign(grupo=['a', 'otra']), base.assign(precio_m2=[100, 201]),
                    pd.concat([base, base])]:
            with self.assertRaises(ValueError):
                bootstrap_mae_delta(bad, base)


if __name__ == '__main__':
    unittest.main()
