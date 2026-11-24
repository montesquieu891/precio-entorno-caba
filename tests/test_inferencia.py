"""Contratos de persistencia e inferencia con avisos exclusivamente ficticios."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from precio_entorno.inferencia import load, predict, save, train
from precio_entorno.analytics.inference import predict_clean
from test_comparar_modelos import synthetic


class InferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = synthetic(20)
        cls.bundle, cls.report, cls.errors = train(cls.df, folds=2)

    def test_groups_and_holdout_predictions(self):
        self.assertEqual(self.report['grupos_compartidos'], 0)
        self.assertEqual(len(self.errors), self.report['prueba'])
        self.assertGreater(self.report['baseline_prueba']['mae'], 0)
        self.assertEqual(len(self.report['candidatos']), 3)

    def test_roundtrip_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            save(self.bundle, self.report, self.errors, out)
            restored = load(out)
            np.testing.assert_allclose(predict(self.bundle, self.df)['referencia_publicacion_usd_m2'],
                                       predict(restored, self.df)['referencia_publicacion_usd_m2'])
            with (out / 'modelo.joblib').open('ab') as stream:
                stream.write(b'alterado')
            with self.assertRaisesRegex(ValueError, 'huella'):
                load(out)

    def test_unseen_category_and_missing_optional_features(self):
        df = self.df.iloc[:2].drop(columns=['latitude', 'longitude', 'agency']).copy()
        df['neighborhood'] = 'Barrio ficticio nuevo'
        out = predict(self.bundle, df)
        self.assertTrue(out['barrio_no_visto'].all())
        self.assertTrue((out['variables_numericas_faltantes'] >= 2).all())
        self.assertTrue(np.isfinite(out['referencia_publicacion_usd_m2']).all())

    def test_rejects_invalid_schema_currency_and_operation(self):
        for field, value in [('covered_area', 0), ('rooms', np.inf), ('currency', 'ARS'),
                             ('operation', 'alquiler'), ('neighborhood', None)]:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    predict(self.bundle, self.df.iloc[:1].assign(**{field: value}))
        with self.assertRaises(ValueError):
            predict(self.bundle, self.df.drop(columns='rooms'))

    def test_category_codes_do_not_depend_on_inference_batch(self):
        one = predict(self.bundle, self.df.iloc[:1])['referencia_publicacion_usd_m2'].iloc[0]
        all_rows = predict(self.bundle, self.df)['referencia_publicacion_usd_m2'].iloc[0]
        self.assertAlmostEqual(one, all_rows)

    def test_clean_pipeline_uses_saved_model_and_preserves_ids(self):
        clean = self.df.rename(columns={'neighborhood': 'barrio', 'rooms': 'ambientes',
                                       'covered_area': 'superficie_cubierta_m2', 'agency': 'fuente'})
        with tempfile.TemporaryDirectory() as tmp:
            save(self.bundle, self.report, self.errors, Path(tmp))
            result, skipped = predict_clean(clean, load(Path(tmp)))
        self.assertEqual(skipped, 0)
        self.assertEqual(result['id'].tolist(), self.df['id'].tolist())
        self.assertTrue(result['modelo_version'].eq(self.bundle['version']).all())
