"""Pruebas de los blueprints de Make, sin red."""

import json
import unittest

from precio_entorno import make_escenarios as m


def modules(flow):
    for item in flow:
        yield item
        yield from (module for route in item.get('routes', []) for module in modules(route['flow']))


class BlueprintTests(unittest.TestCase):
    def test_actor_input_carries_criteria_but_never_the_email(self):
        bp = m.alerts_blueprint('https://hook.us2.make.com/x', 'equipo@example.com')
        by_id = {item['id']: item for item in modules(bp['flow'])}
        criteria = by_id[2]['mapper']['value']
        self.assertNotIn(f"`{m.COL['email']}`", criteria)
        self.assertIn(f"`{m.COL['barrio']}`", criteria)
        actor = by_id[3]['mapper'][f'inputBody{m.ACTOR}']
        self.assertIn('"busquedas":[{{2.text}}]', actor)
        self.assertIn('"alertarPrimeraCorrida":false', actor)
        # El mail se busca recién después, en la planilla, para el módulo de Gmail.
        self.assertEqual(by_id[7]['mapper']['to'], [f"{{{{6.`{m.COL['email']}`}}}}"])
        self.assertIn('?tipo=baja&id={{5.busqueda}}', by_id[7]['mapper']['content'])
        self.assertEqual(by_id[1]['mapper']['filter'], [[{'a': 'L', 'b': 'si', 'o': 'text:equal'}]])

    def test_failures_are_logged_and_reported(self):
        bp = m.alerts_blueprint('https://hook.us2.make.com/x', 'equipo@example.com')
        by_id = {item['id']: item for item in modules(bp['flow'])}
        self.assertEqual(by_id[4]['mapper']['sheetId'], m.SHEET_RUNS)  # Toda corrida queda registrada.
        self.assertEqual(by_id[9]['filter']['conditions'][0][0]['o'], 'text:notequal')
        self.assertEqual(by_id[5]['filter']['conditions'][0][0]['b'], 'SUCCEEDED')

    def test_searches_router_separates_signup_and_unsubscribe(self):
        bp = m.searches_blueprint(123)
        router = bp['flow'][1]
        alta, baja = (route['flow'] for route in router['routes'])
        self.assertEqual(alta[0]['filter']['conditions'][0][0]['b'], 'alta')
        self.assertEqual(alta[0]['mapper']['values'][str(m.COL['activa'])], 'si')
        self.assertEqual(baja[0]['filter']['conditions'][0][0]['b'], 'baja')
        self.assertEqual(baja[1]['mapper']['values'][str(m.COL['activa'])], 'no')
        self.assertTrue(bp['metadata']['instant'])

    def test_sheet_names_are_ascii_and_blueprints_serialize(self):
        for name in (m.SHEET_SEARCHES, m.SHEET_RUNS, m.SHEET_ALERTS):
            self.assertTrue(name.isascii(), name)  # Make no lee rangos con tildes.
        for bp in (m.searches_blueprint(1), m.alerts_blueprint('https://hook.us2.make.com/x', 'e@example.com'),
                   m.headers_blueprint()):
            json.loads(json.dumps(bp, ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()
