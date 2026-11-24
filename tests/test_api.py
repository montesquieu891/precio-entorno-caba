"""Pruebas de la API de la interfaz web con bases temporales y capas sintéticas."""

import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from precio_entorno import entorno
from precio_entorno.api import VERSIONED_ASSETS as VERSIONED, create_app
from precio_entorno.importing import import_crimes
from precio_entorno.store import Store

try:
    from test_entorno import build_sources, collection, point, write
except ImportError:  # Ejecutado como tests.test_api
    from tests.test_entorno import build_sources, collection, point, write

CRIMES = (
    '"id-mapa","fecha","franja","tipo","barrio","latitud","longitud","cantidad"\n'
    '1,"2025-03-02",14,"Robo","CABALLITO","-34.6150","-58.4450",1\n'
    '2,"2025-03-05",9,"Hurto","CABALLITO","-34.6152","-58.4452",2\n'
    '3,"2025-04-01",20,"Robo","ALMAGRO","-34.6150","-58.4350",1\n'
).encode('utf-8')


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        poi, raw = build_sources(root)
        entorno.convert(poi, raw, root / 'entorno')
        cls.raw = root / 'raw'
        cls.raw.mkdir()
        cls.real = root / 'real.sqlite3'
        import_crimes(Store(cls.real), CRIMES, 'delitos.csv')
        (cls.raw / 'delitos.csv').write_bytes(CRIMES)
        cls.client = TestClient(create_app(demo_path=root / 'demo.sqlite3', real_path=cls.real,
                                           entorno_dir=root / 'entorno', raw_dir=cls.raw))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def get(self, path, **params):
        response = self.client.get(path, params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_demo_neighborhoods_count_matches_and_attach_environment(self):
        state = self.get('/api/estado')
        self.assertEqual((state['avisos'], state['delitos'], state['capas']), (6, None, True))
        rows = {r['barrio']: r for r in self.get('/api/barrios')['barrios']}
        self.assertEqual(len(rows), 48)
        self.assertEqual((rows['Almagro']['coincidencias'], rows['Almagro']['mediana']), (2, 100_000))
        self.assertEqual(rows['Caballito']['coincidencias'], 1)
        self.assertEqual(rows['Caballito']['entorno']['subte_lineas'], ['A'])
        self.assertIsNone(rows['Palermo']['entorno'])
        first = self.get('/api/barrios')['barrios'][0]
        self.assertEqual(first['barrio'], 'Almagro')

    def test_demo_listings_hide_links_and_follow_filters(self):
        listings = self.get('/api/barrios/Almagro/avisos')['avisos']
        self.assertEqual([a['precio'] for a in listings], [98_000, 102_000])
        self.assertTrue(all(a['enlace'] is None for a in listings))
        self.assertEqual(self.get('/api/barrios/Almagro/avisos', presupuesto=99_000)['avisos'][0]['id'], 'demo-003')

    def test_listings_carry_comparison_with_similar_listings(self):
        listings = self.get('/api/barrios/Almagro/avisos')['avisos']
        # La base de ejemplo tiene pocos avisos por barrio: hay comparación, pero sin posición.
        self.assertTrue(all(a['comparacion']['posicion'] is None for a in listings))
        self.assertTrue(all(a['comparacion']['n'] < 8 for a in listings))

    def test_rooms_or_more_widens_matches(self):
        exact = sum(r['coincidencias'] for r in self.get('/api/barrios', ambientes=1, presupuesto=10**9)['barrios'])
        rows = self.get('/api/barrios', ambientes=1, presupuesto=10**9, superficie=1, ambientes_o_mas='true')['barrios']
        self.assertEqual(sum(r['coincidencias'] for r in rows), sum(r['avisos'] for r in rows))
        self.assertGreaterEqual(sum(r['coincidencias'] for r in rows), exact)

    def test_rentals_compare_in_the_chosen_currency(self):
        self.assertEqual(self.get('/api/estado', operacion='alquiler')['monedas'], ['ARS', 'USD'])
        rows = self.get('/api/barrios', operacion='alquiler', presupuesto=800_000, moneda='ARS')['barrios']
        self.assertGreater(sum(r['coincidencias'] for r in rows), 0)
        self.assertEqual(self.client.get('/api/barrios', params={'moneda': 'ARS'}).status_code, 422)

    def test_search_can_be_removed_once(self):
        body = {'barrio': 'Flores', 'presupuesto': 95_000, 'superficie': 35, 'ambientes': 2}
        self.assertTrue(self.client.post('/api/busquedas', json=body).json()['creada'])
        flores = next(s for s in self.get('/api/busquedas')['busquedas'] if s['barrio'] == 'Flores')
        self.assertEqual(self.client.delete(f"/api/busquedas/{flores['id']}").json(), {'quitada': True})
        self.assertNotIn('Flores', [s['barrio'] for s in self.get('/api/busquedas')['busquedas']])
        again = self.client.delete(f"/api/busquedas/{flores['id']}")
        self.assertEqual(again.status_code, 404)
        self.assertIn('ya no existe', again.json()['detail'])

    def test_search_is_saved_once_and_validated(self):
        body = {'barrio': 'Villa Crespo', 'presupuesto': 120_000, 'superficie': 40, 'ambientes': 2}
        self.assertTrue(self.client.post('/api/busquedas', json=body).json()['creada'])
        self.assertFalse(self.client.post('/api/busquedas', json=body).json()['creada'])
        saved = self.get('/api/busquedas')['busquedas']
        self.assertIn('Villa Crespo', [s['barrio'] for s in saved])
        self.assertEqual(self.client.post('/api/busquedas', json=dict(body, barrio='Narnia')).status_code, 404)
        self.assertEqual(self.client.post('/api/busquedas', json=dict(body, ambientes=0)).status_code, 422)
        self.assertEqual(self.client.post('/api/busquedas', params={'operacion': 'alquiler'},
                                          json=dict(body, moneda='EUR')).status_code, 422)

    def test_alert_can_ask_for_rooms_or_more(self):
        # La interfaz ya no exige ambientes exactos para crear una alerta: la base guarda «N o más» como otra búsqueda.
        body = {'barrio': 'Boedo', 'presupuesto': 90_000, 'superficie': 30, 'ambientes': 2}
        self.assertTrue(self.client.post('/api/busquedas', json=dict(body, ambientes_o_mas=True)).json()['creada'])
        self.assertTrue(self.client.post('/api/busquedas', json=body).json()['creada'])
        boedo = [s for s in self.get('/api/busquedas')['busquedas'] if s['barrio'] == 'Boedo']
        self.assertEqual(sorted(s['ambientes_o_mas'] for s in boedo), [False, True])

    def test_email_subscription_goes_only_to_make(self):
        sent = []
        root = Path(self.temp.name)
        with tempfile.TemporaryDirectory() as temp:
            real = Path(temp) / 'real.sqlite3'
            client = TestClient(create_app(demo_path=root / 'demo.sqlite3', real_path=real,
                                           entorno_dir=root / 'entorno', raw_dir=self.raw,
                                           subscriptions_url='https://hook.us2.make.com/x',
                                           post=lambda url, body: sent.append(body) or 200))
            body = {'barrio': 'Boedo', 'presupuesto': 100_000, 'superficie': 35, 'ambientes': 2,
                    'email': 'persona@example.com', 'consentimiento': True}
            result = client.post('/api/busquedas', params={'modo': 'real'}, json=body).json()
            self.assertEqual(result, {'creada': True, 'correo': {'enviado': True}})
            alta, = sent
            self.assertEqual((alta['tipo'], alta['email']), ('alta', 'persona@example.com'))
            self.assertEqual({k: v for k, v in alta['busqueda'].items() if k != 'id'},
                             {'operacion': 'venta', 'barrio': 'Boedo', 'presupuesto': 100_000, 'moneda': 'USD',
                              'superficie': 35, 'ambientes': 2, 'ambientesOMas': False})
            self.assertGreaterEqual(len(alta['busqueda']['id']), 12)  # Aleatorio: sirve de clave para la baja.
            self.assertEqual(alta['descripcion'], 'Boedo · hasta USD 100.000 · 35 m² o más · 2 ambientes')
            self.assertNotIn('interes', alta)  # Sin nivel elegido en «Precios», el alta no cambia.
            self.assertNotIn(b'persona@example.com', real.read_bytes())  # El mail no queda en la base local.
            # Otra persona con los mismos filtros también se suscribe, con otro ID.
            again = client.post('/api/busquedas', params={'modo': 'real'}, json=dict(body, email='otra@example.com'))
            self.assertEqual(again.json(), {'creada': False, 'correo': {'enviado': True}})
            self.assertNotEqual(sent[1]['busqueda']['id'], alta['busqueda']['id'])
            bad = {'demo': ({'modo': 'demo'}, body), 'mail': ({'modo': 'real'}, dict(body, email='persona@')),
                   'consentimiento': ({'modo': 'real'}, dict(body, consentimiento=False))}
            for name, (params, payload) in bad.items():
                with self.subTest(name):
                    self.assertEqual(client.post('/api/busquedas', params=params, json=payload).status_code, 422)
            self.assertEqual(len(sent), 2)
            unset = TestClient(create_app(demo_path=root / 'demo.sqlite3', real_path=real, entorno_dir=root / 'entorno',
                                          raw_dir=self.raw, subscriptions_url=None))
            result = unset.post('/api/busquedas', params={'modo': 'real'}, json=body).json()
            self.assertFalse(result['correo']['enviado'])

    def test_first_cohort_interest_travels_with_the_email_signup(self):
        # «Anotarme en la primera tanda» manda el nivel elegido a Make junto con el alta; un nivel inventado se rechaza.
        sent = []
        root = Path(self.temp.name)
        with tempfile.TemporaryDirectory() as temp:
            client = TestClient(create_app(demo_path=root / 'demo.sqlite3', real_path=Path(temp) / 'real.sqlite3',
                                           entorno_dir=root / 'entorno', raw_dir=self.raw,
                                           subscriptions_url='https://hook.us2.make.com/x',
                                           post=lambda url, body: sent.append(body) or 200))
            body = {'barrio': 'Boedo', 'presupuesto': 100_000, 'superficie': 35, 'ambientes': 2,
                    'email': 'persona@example.com', 'consentimiento': True}
            for nivel in ('buscar', 'acompanado'):
                result = client.post('/api/busquedas', params={'modo': 'real'}, json=dict(body, interes=nivel))
                self.assertTrue(result.json()['correo']['enviado'])
            self.assertEqual([alta['interes'] for alta in sent], ['buscar', 'acompanado'])
            invalid = client.post('/api/busquedas', params={'modo': 'real'}, json=dict(body, interes='premium'))
            self.assertEqual(invalid.status_code, 422)
            self.assertEqual(len(sent), 2)

    def test_map_layers_are_cut_to_the_neighborhood(self):
        shapes = self.get('/api/mapa/barrios')
        self.assertEqual({f['properties']['barrio'] for f in shapes['features']}, {'Caballito', 'Almagro'})
        layers = self.client.get('/api/mapa/capas', params=[('barrio', 'Caballito'), ('capas', 'subte'),
                                                             ('capas', 'ruido'), ('capas', 'salud')]).json()
        self.assertEqual(set(layers), {'subte', 'ruido', 'salud'})
        self.assertIn('Primera Junta', [f['properties']['name'] for f in layers['subte']['features']])
        elevators = {f['properties']['name']: f['properties']['elevators'] for f in layers['subte']['features']}
        self.assertEqual(elevators['Primera Junta'], 2)
        cell = layers['ruido']['features'][0]
        self.assertEqual(cell['geometry']['type'], 'Point')        # el mapa dibuja un brillo por celda
        self.assertEqual(cell['properties']['tipico'], 70)
        self.assertEqual(layers['ruido']['umbral_dba'], 70)
        # Solo celdas del barrio pedido, aunque las de Almagro caigan dentro del rectángulo de Caballito.
        almagro = self.client.get('/api/mapa/capas', params={'barrio': 'Almagro', 'capas': 'ruido'}).json()['ruido']
        self.assertTrue({f['properties']['tipico'] for f in almagro['features']} <= {55})
        self.assertTrue(all(f['properties']['tipico'] == 70 for f in layers['ruido']['features']))
        kinds = {f['properties']['kind'] for f in layers['salud']['features']}
        self.assertEqual(kinds, {'cesac', 'hospital'})
        bad = self.client.get('/api/mapa/capas', params={'barrio': 'Caballito', 'capas': 'bares'})
        self.assertEqual(bad.status_code, 422)

    def test_hospitales_de_toda_la_ciudad_para_el_lugar_fijo(self):
        rows = self.get('/api/hospitales')['hospitales']
        self.assertTrue(rows)
        self.assertEqual(rows, sorted(rows, key=lambda r: r['nombre']))
        self.assertTrue(all({'nombre', 'barrio', 'lon', 'lat', 'especialidad'} <= set(r) for r in rows))

    def test_optional_commercial_garages_layer(self):
        params = {'barrio': 'Caballito', 'capas': 'estacionamiento'}
        missing = self.get('/api/mapa/capas', **params)['estacionamiento']
        self.assertFalse(missing['disponible'])
        self.assertEqual(missing['features'], [])

        with tempfile.TemporaryDirectory() as temp:
            poi, raw = build_sources(Path(temp))
            garage = ({'NOMBRE': 'Garaje de prueba', 'calle_nombre': 'Calle', 'calle_altura': 123},
                      point(-58.445, -34.615))
            # Almagro, fuera del recuadro de Caballito: la capa cubre toda la ciudad.
            lejano = ({'NOMBRE': 'Garaje lejano'}, point(-58.4305, -34.615))
            write(raw / entorno.GARAJES_ARCHIVO, collection(
                garage, garage, lejano, ({'nombre': 'Fuera de CABA'}, point(-58.30, -34.615))))
            target = Path(temp) / 'processed'
            entorno.convert(poi, raw, target)
            with TestClient(create_app(entorno_dir=target)) as client:
                result = client.get('/api/mapa/capas', params=params)
                self.assertEqual(result.status_code, 200)
                layer = result.json()['estacionamiento']
                self.assertTrue(layer['disponible'])
                tooltips = sorted(f['properties']['tooltip'] for f in layer['features'])
                self.assertEqual(tooltips, ['Garaje de prueba · Calle 123', 'Garaje lejano'])
                sources = client.get('/api/fuentes').json()['fuentes']
                self.assertTrue(any(s['url'] == entorno.GARAJES_FUENTE for s in sources))

    def test_crimes_are_mapped_only_with_real_data_and_matching_file(self):
        demo = self.get('/api/delitos', barrio='Caballito', modo='demo')
        self.assertFalse(demo['disponible'])
        real = self.get('/api/delitos', barrio='Caballito', periodo='2025-03')
        self.assertTrue(real['disponible'])
        self.assertEqual((real['periodo'], real['maximo'], real['tipos']), ('2025-03', 3, {'Robo': 1, 'Hurto': 2}))
        self.assertEqual(real['periodos'], ['2025-04', '2025-03'])
        robos = self.get('/api/delitos', barrio='Caballito', periodo='2025-03', tipo='Robo')
        self.assertEqual(robos['maximo'], 1)

    def test_crimes_refuse_a_file_that_differs_from_the_loaded_one(self):
        with tempfile.TemporaryDirectory() as temp:
            other_raw = Path(temp)
            (other_raw / 'delitos.csv').write_bytes(CRIMES + b'4,"2025-03-09",1,"Robo","CABALLITO","-34.6","-58.44",1\n')
            app = create_app(real_path=self.real, entorno_dir=Path(self.temp.name) / 'entorno', raw_dir=other_raw,
                             demo_path=Path(temp) / 'demo.sqlite3')
            data = TestClient(app).get('/api/delitos', params={'barrio': 'Caballito'}).json()
            self.assertFalse(data['disponible'])
            self.assertIn('no es el mismo archivo', data['motivo'])

    def test_sources_and_page_are_served(self):
        self.assertEqual(len(self.get('/api/fuentes')['fuentes']), len(entorno.SOURCES))
        page = self.client.get('/')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Lüga', page.text)

    def test_concentration_preserves_demo_separation_and_validates_filters(self):
        demo = self.get('/api/delitos/concentracion', barrio='Caballito', modo='demo')
        self.assertFalse(demo['disponible'])
        self.assertIn('ficticios', demo['motivo'])
        data = self.get('/api/delitos/concentracion', barrio='Caballito', radio=250, anio=2025)
        self.assertTrue(data['disponible'])
        self.assertEqual(data['anios'], [2025])
        self.assertIsNone(data['inmueble'])
        self.assertEqual(data['resumen_radios'], [])
        self.assertEqual(data['radios']['features'], [])
        # La vista anual incluye también el registro cercano al límite de Almagro.
        self.assertEqual(sum(f['properties']['hechos'] for f in data['celdas']['features']), 4)
        for params in ({'radio': 750}, {'franja': 'madrugada'}, {'tipo': 'Vialidad'}, {'anio': 2026}):
            response = self.client.get('/api/delitos/concentracion', params={'barrio': 'Caballito', **params})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get('/api/delitos/concentracion', params={
            'barrio': 'Caballito', 'inmueble': 'inexistente'}).status_code, 404)

    def test_listings_carry_traits_age_and_optional_proximity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / 'real.sqlite3')
            base = {'neighborhood': 'Caballito', 'price': 100_000, 'covered_area': 45, 'rooms': 2,
                    'url': 'https://example.invalid/x', 'captured_at': '2026-11-17', 'currency': 'USD',
                    'total_area_m2': None, 'latitude': None, 'longitude': None, 'location_accuracy_m': None}
            store.ingest([
                # Sobre Primera Junta (-58.445, -34.615), con texto que menciona balcón y no patio.
                dict(base, id='con-pin', latitude=-34.615, longitude=-58.445, age_years=12, balcony=1, patio=0),
                dict(base, id='sin-pin', price=101_000),
            ], source='prueba')
            client = TestClient(create_app(real_path=store.path, demo_path=root / 'demo.sqlite3',
                                           entorno_dir=Path(self.temp.name) / 'entorno'))
            path = '/api/barrios/Caballito/avisos'
            plain = client.get(path, params={'modo': 'real'}).json()
            self.assertNotIn('cercania', plain)
            con, sin = plain['avisos']
            self.assertEqual((con['antiguedad'], con['rasgos']['balcon'], con['rasgos']['patio']), (12, 1, 0))
            self.assertIsNone(sin['rasgos']['balcon'])   # sin texto: sin dato, no «no tiene»
            self.assertNotIn('cercania', con)

            params = [('modo', 'real'), ('capas', 'subte'), ('capas', 'escuelas'), ('capas', 'ruido'),
                      ('nivel', 'primario')]
            result = client.get(path, params=params).json()
            self.assertTrue(result['cercania']['disponible'])
            self.assertIn('Línea recta', result['cercania']['metodo'])
            con, sin = result['avisos']
            self.assertEqual(con['cercania']['subte'], {'m': 0, 'estacion': 'Primera Junta', 'linea': 'A'})
            self.assertEqual(con['cercania']['subte_ascensor'], {'m': 0, 'estacion': 'Primera Junta', 'linea': 'A'})
            self.assertEqual(con['cercania']['escuela']['nivel'], 'primario')
            self.assertGreater(con['cercania']['escuela']['m'], 0)
            self.assertEqual(con['cercania']['ruido_diurno'], {'dba': 70})
            self.assertIsNone(sin['cercania'])            # sin ubicación: sin distancia

            bad = client.get(path, params=[('modo', 'real'), ('capas', 'riesgo')])
            self.assertEqual(bad.status_code, 422)
            self.assertEqual(client.get(path, params=[('capas', 'subte'), ('nivel', 'terciario')]).status_code, 422)

    def test_demo_listings_never_invent_traits(self):
        result = self.get('/api/barrios/Almagro/avisos')
        self.assertTrue(all(set(a['rasgos'].values()) == {None} for a in result['avisos']))

    def test_concentration_uses_annual_sources_precise_listing_and_refreshes_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / 'raw'
            raw.mkdir()
            first = raw / 'delitos_2024.csv'
            first.write_bytes(CRIMES.replace(b'2025-', b'2024-'))
            store = Store(root / 'real.sqlite3')
            listing = {'id': 'pin', 'neighborhood': 'Caballito', 'price': 100_000, 'covered_area': 45,
                       'rooms': 2, 'url': 'https://example.invalid/pin', 'captured_at': '2026-11-09',
                       'currency': 'USD', 'total_area_m2': 50, 'latitude': -34.615, 'longitude': -58.445,
                       'location_accuracy_m': 50}
            store.ingest([listing, dict(listing, id='sin-precision', location_accuracy_m=None)], source='prueba')
            client = TestClient(create_app(real_path=store.path, demo_path=root / 'demo.sqlite3', raw_dir=raw,
                                          entorno_dir=Path(self.temp.name) / 'entorno'))
            params = {'barrio': 'Caballito', 'inmueble': 'pin', 'radio': 1000, 'tipo': 'robo', 'franja': 'diurno'}
            result = client.get('/api/delitos/concentracion', params=params).json()
            self.assertTrue(result['disponible'])
            self.assertEqual(result['inmueble']['precision_m'], 50)
            self.assertEqual(len(result['radios']['features']), 3)
            self.assertEqual(sum(f['properties']['seleccionado'] for f in result['radios']['features']), 1)
            self.assertEqual(sum(c['properties']['hechos'] for c in result['celdas']['features']), 1)
            self.assertEqual(len(result['resumen_radios']), 6)
            (raw / 'delitos_2025.csv').write_bytes(CRIMES)
            refreshed = client.get('/api/delitos/concentracion', params=params).json()
            self.assertEqual(refreshed['anios'], [2024, 2025])
            self.assertEqual(len(refreshed['fuentes']), 2)
            self.assertEqual(len(refreshed['resumen_radios']), 12)
            bad_pin = client.get('/api/delitos/concentracion', params=dict(params, inmueble='sin-precision')).json()
            self.assertFalse(bad_pin['disponible'])
            self.assertEqual(client.get('/api/delitos/concentracion', params=dict(params, barrio='Almagro')).status_code, 404)
            found = client.get('/api/barrios/Caballito/avisos', params={'modo': 'real'}).json()['avisos']
            self.assertEqual({i['id']: i['pin_utilizable'] for i in found}, {'pin': True, 'sin-precision': False})

    def test_concentration_refuses_changed_import_and_handles_missing_layers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'delitos.csv').write_bytes(CRIMES + b'\n')
            app = create_app(real_path=self.real, raw_dir=root, entorno_dir=root / 'missing',
                             demo_path=root / 'demo.sqlite3')
            client = TestClient(app)
            response = client.get('/api/delitos/concentracion', params={'barrio': 'Caballito'})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()['disponible'])
            self.assertIn('no es el mismo archivo', response.json()['motivo'])
            (root / 'delitos.csv').write_bytes(CRIMES)
            response = client.get('/api/delitos/concentracion', params={'barrio': 'Caballito'})
            self.assertFalse(response.json()['disponible'])
            self.assertIn('capas', response.json()['motivo'])

    def test_map_shapes_are_cached_with_etag_and_answer_304(self):
        first = self.client.get('/api/mapa/barrios')
        self.assertEqual(first.status_code, 200)
        self.assertIn('max-age=86400', first.headers['cache-control'])
        again = self.client.get('/api/mapa/barrios', headers={'If-None-Match': first.headers['etag']})
        self.assertEqual((again.status_code, again.content), (304, b''))

    def test_listing_data_revalidates_and_errors_are_not_stored(self):
        self.assertEqual(self.client.get('/api/estado').headers['cache-control'], 'no-cache')
        missing = self.client.get('/api/barrios/NoExiste/avisos')
        self.assertEqual((missing.status_code, missing.headers['cache-control']), (404, 'no-store'))


class CacheTests(unittest.TestCase):
    """index.html versiona app.js y styles.css con el hash del contenido para guardarlos como inmutables."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.web = Path(self.temp.name) / 'web'
        self.web.mkdir()
        (self.web / 'index.html').write_text(
            '<link href="styles.css" rel="stylesheet"><script src="app.js" defer></script>', encoding='utf-8')
        (self.web / 'styles.css').write_text('body{}', encoding='utf-8')
        (self.web / 'app.js').write_text('let a = 1;', encoding='utf-8')
        self.client = TestClient(create_app(entorno_dir=Path(self.temp.name) / 'sin-capas', web_dir=self.web))

    def tearDown(self):
        self.temp.cleanup()

    def version(self, html, name):
        return re.search(rf'{re.escape(name)}\?v=(\w+)"', html)[1]

    def test_index_points_to_versioned_assets_and_revalidates(self):
        page = self.client.get('/')
        self.assertEqual(page.headers['cache-control'], 'no-cache')
        for name in VERSIONED:
            self.assertRegex(page.text, rf'{re.escape(name)}\?v=\w{{12}}"')
        again = self.client.get('/', headers={'If-None-Match': page.headers['etag']})
        self.assertEqual(again.status_code, 304)

    def test_only_the_current_version_is_immutable(self):
        version = self.version(self.client.get('/').text, 'app.js')
        self.assertIn('immutable', self.client.get(f'/app.js?v={version}').headers['cache-control'])
        self.assertEqual(self.client.get('/app.js').headers['cache-control'], 'no-cache')
        self.assertEqual(self.client.get('/app.js?v=vieja').headers['cache-control'], 'no-cache')

    def test_changing_a_file_changes_its_version(self):
        before = self.version(self.client.get('/').text, 'app.js')
        (self.web / 'app.js').write_text('let a = 2; // cambio', encoding='utf-8')
        after = self.version(self.client.get('/').text, 'app.js')
        self.assertNotEqual(before, after)
        self.assertEqual(self.client.get(f'/app.js?v={before}').headers['cache-control'], 'no-cache')


if __name__ == '__main__':
    unittest.main()
