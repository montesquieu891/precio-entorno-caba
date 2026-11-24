"""Pruebas del pipeline del modelo con datos sintéticos y ficticios."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from precio_entorno.modelo import amenities, crime_window, environment, evaluate, load_listings, load_osm

CENTERS = {'Caballito': (-34.618, -58.443), 'Almagro': (-34.606, -58.420),
           'Flores': (-34.630, -58.465), 'Palermo': (-34.580, -58.425)}


def listing(i, barrio, lat, lon, accuracy=50.0, captured='2026-03-01', rooms=2, area=50.0, price=120000):
    return {'listing_id': f'ficticio-{i}', 'url': f'https://example.invalid/{i}', 'captured_at': captured,
            'price': price, 'currency': 'USD', 'covered_area_m2': area, 'rooms': rooms,
            'neighborhood': barrio, 'latitude': lat, 'longitude': lon, 'location_accuracy_m': accuracy}


def crimes(rows):
    df = pd.DataFrame(rows, columns=['mes', 'tipo', 'barrio', 'latitud', 'longitud'])
    return df.assign(cantidad=1, uso_arma=df['tipo'].eq('Robo'), delito=df['tipo'] != 'Vialidad')


def synthetic_crimes(rng, months, barrio, clat, clon):
    """Robos y hurtos concentrados en un foco del barrio, más amenazas repartidas, con coordenadas ficticias."""
    hotspot = (clat + rng.uniform(-0.006, 0.006), clon + rng.uniform(-0.006, 0.006))
    rows = []
    for _ in range(600):
        lat, lon = rng.normal(hotspot, 0.002)
        rows.append((rng.choice(months), rng.choice(['Robo', 'Hurto']), barrio, lat, lon))
    for _ in range(300):
        lat, lon = clat + rng.uniform(-0.01, 0.01), clon + rng.uniform(-0.01, 0.01)
        rows.append((rng.choice(months), 'Amenazas', barrio, lat, lon))
    return rows


class ModeloTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)

    def write(self, rows, name='avisos.json'):
        path = self.dir / name
        path.write_text(json.dumps(rows), encoding='utf-8')
        return path

    def test_window_uses_last_complete_year_before_capture(self):
        months = pd.period_range('2024-01', '2025-12', freq='M').strftime('%Y-%m').tolist()
        self.assertEqual(crime_window(pd.Timestamp('2026-03-10'), months),
                         tuple(pd.period_range('2025-01', '2025-12', freq='M').strftime('%Y-%m')))
        self.assertEqual(crime_window(pd.Timestamp('2025-07-15'), months)[::11], ('2024-07', '2025-06'))
        self.assertIsNone(crime_window(pd.Timestamp('2024-06-01'), months))
        self.assertIsNone(crime_window(pd.Timestamp('2026-03-10'), [m for m in months if m != '2025-05']))

    def test_environment_counts_radius_and_barrio_without_inventing_zeros(self):
        lat, lon = -34.618, -58.443
        path = self.write([
            listing(1, 'Caballito', lat, lon),
            listing(2, 'Caballito', lat, lon, accuracy=None),
            listing(3, 'Boedo', -34.63, -58.415),
        ])
        months = pd.period_range('2025-01', '2025-12', freq='M').strftime('%Y-%m')
        rows = [(m, 'Hurto', 'Almagro', -34.606, -58.42) for m in months]  # Cubre los 12 meses.
        rows += [
            ('2025-06', 'Robo', 'Caballito', lat + 0.002, lon),   # A unos 220 m.
            ('2025-06', 'Robo', 'Caballito', lat + 0.006, lon),   # A unos 660 m.
            ('2025-06', 'Amenazas', 'Caballito', lat, lon),
            ('2025-06', 'Vialidad', 'Caballito', lat, lon),       # No es delito.
        ]
        listings, summary = load_listings([path], 'ficticio')
        data = environment(listings, crimes(rows)).set_index('id')
        first = data.loc['ficticio-1']
        self.assertEqual((first['radio_delitos'], first['radio_robos_hurtos']), (2, 1))
        self.assertEqual((first['barrio_delitos'], first['barrio_robos_hurtos']), (3, 2))
        self.assertAlmostEqual(first['barrio_pct_arma'], 200 / 3)
        self.assertEqual((first['ventana'], first['desfase_meses']), ('2025-01 a 2025-12', 2))
        # Sin precisión declarada: se cruza por barrio y no se usan sus coordenadas.
        self.assertTrue(np.isnan(data.loc['ficticio-2', 'radio_delitos']))
        self.assertTrue(np.isnan(data.loc['ficticio-2', 'latitude']))
        self.assertEqual(data.loc['ficticio-2', 'barrio_delitos'], 3)
        # Un barrio sin filas en la ventana queda sin dato.
        self.assertTrue(np.isnan(data.loc['ficticio-3', 'barrio_delitos']))
        self.assertEqual((summary['pines_con_precision_declarada'], summary['pines_usados_para_radio']), (2, 2))
        approximate, _ = load_listings([path], 'ficticio', approximate_pins=True)
        self.assertEqual(environment(approximate, crimes(rows)).set_index('id').loc['ficticio-2', 'radio_delitos'], 2)

    def test_three_references_share_split_and_detect_environment_signal(self):
        rng = np.random.default_rng(7)
        months = pd.period_range('2025-01', '2025-12', freq='M').strftime('%Y-%m')
        rows = []
        for barrio, (clat, clon) in CENTERS.items():
            rows += synthetic_crimes(rng, months, barrio, clat, clon)
        avisos = []
        for i in range(400):
            barrio = list(CENTERS)[i % 4]
            clat, clon = CENTERS[barrio]
            rooms = int(rng.integers(1, 5))
            avisos.append(listing(i, barrio, clat + rng.uniform(-0.01, 0.01), clon + rng.uniform(-0.01, 0.01),
                                  rooms=rooms, area=round(25 + 15 * rooms + rng.uniform(0, 10), 1)))
        avisos += [dict(a, captured_at='2026-04-01') for a in avisos[:60]]
        listings, summary = load_listings([self.write(avisos)], 'ficticio')
        data = environment(listings, crimes(rows))
        # Precio sintético: base por barrio, menos un efecto del entorno inmediato.
        base = data['neighborhood'].map({'Caballito': 2600, 'Almagro': 2400, 'Flores': 2000, 'Palermo': 3200})
        noise = data['id'].map({i: rng.normal(0, 40) for i in data['id'].unique()})
        data['precio_m2'] = base - 4 * data['radio_robos_hurtos'] + noise

        result = evaluate(data, seed=3)
        mae = result['mae_usd_m2']
        self.assertEqual(summary['avisos_con_capturas_repetidas'], 60)
        self.assertEqual(result['particion']['observaciones_entrenamiento']
                         + result['particion']['observaciones_prueba'], 460)
        self.assertLess(mae['inmobiliario_con_entorno'], mae['inmobiliario'])
        self.assertLess(mae['inmobiliario'], mae['comparables'])
        self.assertIn('radio_robos_hurtos', result['variables_entorno'])
        self.assertTrue(any('constantes dentro de cada barrio' in n for n in result['notas']))
        self.assertEqual(len(result['validacion_cruzada']['mejora_entorno_por_pliegue_usd_m2']), 5)
        self.assertTrue(result['validacion_cruzada']['entorno_supera_al_placebo_en_todos_los_pliegues'])
        self.assertTrue(result['validacion_cruzada']['entorno_mejora_en_todos_los_pliegues'])

    def test_agency_control_adds_a_categorical_variable(self):
        rng = np.random.default_rng(1)
        avisos = [dict(listing(i, 'Caballito', -34.618, -58.443, area=50 + i % 7), listing_id=f'{a}:{i}')
                  for i, a in zip(range(40), ['remax', 'century21'] * 20)]
        listings, _ = load_listings([self.write(avisos)], 'ficticio')
        self.assertEqual(set(listings['agency']), {'remax', 'century21'})
        data = environment(listings, crimes([('2025-01', 'Robo', 'Caballito', -34.618, -58.443)]))
        data['precio_m2'] = 2500 + 300 * (data['agency'] == 'remax') + rng.normal(0, 20, len(data))
        result = evaluate(data, folds=2, control_agency=True)
        self.assertIn('agency_code', result['variables_inmobiliarias'])
        self.assertLess(result['mae_usd_m2']['inmobiliario'], 100)

    def test_osm_amenities_only_for_usable_pins(self):
        lat, lon = -34.618, -58.443
        (self.dir / 'osm').mkdir()
        (self.dir / 'osm' / 'transporte.json').write_text(json.dumps([{'lat': lat + 0.003, 'lon': lon}]), encoding='utf-8')
        (self.dir / 'osm' / 'cafes.json').write_text(json.dumps(
            [{'lat': lat + 0.001, 'lon': lon}, {'lat': lat + 0.02, 'lon': lon}]), encoding='utf-8')
        (self.dir / 'osm' / 'escuelas.json').write_text(json.dumps([{'lat': lat, 'lon': lon}]), encoding='utf-8')
        (self.dir / 'osm' / 'corridas.json').write_text(json.dumps(
            [{'nombre': 'escuelas', 'puntos': 1, 'max_items': 1}, {'nombre': 'cafes', 'puntos': 2, 'max_items': 10}]),
            encoding='utf-8')
        listings, _ = load_listings([self.write([listing(1, 'Caballito', lat, lon),
                                                 listing(2, 'Caballito', lat, lon, accuracy=None)])], 'ficticio')
        points = load_osm(self.dir / 'osm')
        self.assertEqual(load_osm.truncated, ['escuelas'])
        data = amenities(listings, points).set_index('id')
        self.assertAlmostEqual(data.loc['ficticio-1', 'dist_transporte_m'], 332, delta=2)
        self.assertTrue(np.isnan(data.loc['ficticio-2', 'dist_transporte_m']))
        # Gastronomía necesita restaurantes, cafés y bares; escuelas llegó al tope: ambas sin dato.
        self.assertTrue(np.isnan(data.loc['ficticio-1', 'gastronomia_500m']))
        self.assertTrue(np.isnan(data.loc['ficticio-1', 'escuelas_500m']))
        # Una carpeta posterior con la categoría completa reemplaza a la incompleta.
        (self.dir / 'oficial').mkdir()
        (self.dir / 'oficial' / 'escuelas.json').write_text(json.dumps(
            [{'lat': lat, 'lon': lon}, {'lat': lat + 0.001, 'lon': lon}]), encoding='utf-8')
        (self.dir / 'oficial' / 'corridas.json').write_text(json.dumps(
            [{'nombre': 'escuelas', 'puntos': 2, 'max_items': None}]), encoding='utf-8')
        merged = amenities(listings, load_osm(self.dir / 'osm', self.dir / 'oficial')).set_index('id')
        self.assertEqual((load_osm.truncated, load_osm.sources['escuelas']), ([], 'oficial'))
        self.assertEqual(merged.loc['ficticio-1', 'escuelas_500m'], 2)

    def test_too_few_listings_are_rejected(self):
        path = self.write([listing(i, 'Caballito', -34.618, -58.443) for i in range(10)])
        listings, _ = load_listings([path], 'ficticio')
        data = environment(listings, crimes([('2025-01', 'Robo', 'Caballito', -34.618, -58.443)]))
        with self.assertRaisesRegex(ValueError, 'al menos 30'):
            evaluate(data)
