"""Líneas de colectivo por barrio, clubes y gimnasios, con datos sintéticos."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from precio_entorno import colectivos, entorno
from precio_entorno.api import create_app

try:
    from test_entorno import ALMAGRO, CABALLITO, build_sources, collection, point, polygon
except ImportError:  # Ejecutado como tests.test_colectivos
    from tests.test_entorno import ALMAGRO, CABALLITO, build_sources, collection, point, polygon


def gtfs(path, shapes, routes):
    """Arma un GTFS mínimo. `shapes`: {id: [(lon, lat), ...]}; `routes`: [(route_id, short, desc, [shape_ids])]."""
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('routes.txt', 'route_id,agency_id,route_short_name,route_long_name,route_desc,route_type\n'
                         + ''.join(f'{r},1,{s},X,{d},3\n' for r, s, d, _ in routes))
        archive.writestr('trips.txt', 'route_id,service_id,trip_id,shape_id\n'
                         + ''.join(f'{r},1,{r}-{i},{sh}\n' for r, _, _, ids in routes for i, sh in enumerate(ids)))
        archive.writestr('shapes.txt', 'shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n'
                         + ''.join(f'{sid},{lat},{lon},{n}\n' for sid, pts in shapes.items()
                                   for n, (lon, lat) in enumerate(pts)))


class ColectivosTests(unittest.TestCase):
    def setUp(self):
        self.barrios = entorno.Barrios(collection(
            ({'nombre': 'Caballito', 'comuna': 6}, polygon(CABALLITO)),
            ({'nombre': 'Almagro', 'comuna': 5}, polygon(ALMAGRO))))

    def test_line_names_and_order(self):
        self.assertEqual([colectivos.line_name(n) for n in ('60C', '505R3', '010A', 'AZUL1')], ['60', '505', '10', 'AZUL1'])
        self.assertEqual(sorted(['100', '15', 'AZUL1', '2'], key=colectivos.line_order), ['2', '15', '100', 'AZUL1'])

    def test_densify_catches_barrio_between_distant_points(self):
        # Dos puntos fuera de los barrios: solo el tramo intermedio cruza Caballito y Almagro.
        dense = colectivos.densify([(-58.46, -34.615), (-58.42, -34.615)])
        self.assertGreater(len(dense), 50)
        self.assertEqual({b for b in self.barrios.of(dense) if b}, {'Caballito', 'Almagro'})

    def test_simplify_keeps_ends_and_corners(self):
        line = [(0, 0), (0.5, 0.00001), (1, 0), (1, 1)]
        self.assertEqual(colectivos.simplify(line, 0.001), [[0, 0], [1, 0], [1, 1]])

    def test_build_groups_branches_and_skips_lines_outside_caba(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / colectivos.ARCHIVO
            gtfs(path, {
                'a': [(-58.46, -34.615), (-58.42, -34.615)],          # cruza ambos barrios
                'b': [(-58.445, -34.611), (-58.445, -34.619)],        # solo Caballito
                'lejos': [(-58.30, -34.80), (-58.29, -34.81)],        # fuera de CABA
            }, [('r1', '60A', 'A - Ramal uno', ['a']), ('r2', '60B', 'B - Ramal dos', ['b']),
                ('r3', '7A', 'A - Corto', ['b']), ('r4', '999A', 'Provincia', ['lejos'])])
            lines = colectivos.build(path, self.barrios)
        self.assertEqual(list(lines), ['7', '60'])
        self.assertEqual(lines['60']['barrios'], ['Almagro', 'Caballito'])
        self.assertEqual(lines['60']['ramales'], ['A - Ramal uno', 'B - Ramal dos'])
        self.assertEqual(len(lines['60']['recorrido']), 2)
        self.assertEqual(colectivos.by_barrio(lines), {'Almagro': ['60'], 'Caballito': ['7', '60']})


    def test_clip_keeps_segments_touching_bbox(self):
        path = [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0], [5, 0], [6, 0]]
        bbox = (0.5, -1, 2.5, 1)
        self.assertEqual(colectivos.clip([path], bbox), [[[0, 0], [1, 0], [2, 0], [3, 0]]])
        # Sale y vuelve a entrar: dos tramos.
        self.assertEqual(len(colectivos.clip([path + [[2, 0]]], bbox)), 2)
        # Un segmento recto que cruza el rectángulo sin vértices adentro también cuenta.
        self.assertEqual(colectivos.clip([[[-5, 0], [5, 0]]], bbox), [[[-5, 0], [5, 0]]])
        self.assertEqual(colectivos.clip([path], (10, 10, 11, 11)), [])

    def test_line_color_is_stable(self):
        self.assertEqual(colectivos.color('60'), colectivos.color('60'))
        self.assertIn(colectivos.color('152'), colectivos.COLORS)


class ClubesGimnasiosTests(unittest.TestCase):
    def test_clubs_skip_admin_sites_and_contacts(self):
        rows = [{'nombre': 'Club Uno', 'tipo': 'Club de Barrio', 'tipo_sede': 'Sede', 'direccion': 'Calle 1',
                 'telefono': '4444-4444', 'email': 'a@b.c', 'geometry': 'POINT (-58.445 -34.615)'},
                {'nombre': 'Oficina', 'tipo': 'Club', 'tipo_sede': 'Sede Administrativa',
                 'geometry': 'POINT (-58.446 -34.615)'},
                {'nombre': 'Sin punto', 'geometry': ''}]
        poli = collection(({'nombre': 'Poli', 'dirreccion': 'Av. 2'}, point(-58.435, -34.615)))
        clubs = entorno.sports_clubs(rows, poli)
        self.assertEqual([c['tooltip'] for c in clubs],
                         ['Club Uno · Club de Barrio · Calle 1', 'Poli · Polideportivo de la Ciudad · Av. 2'])
        self.assertNotIn('4444', json.dumps(clubs))

    def test_gyms_from_overpass_nodes_and_ways(self):
        data = {'elements': [
            {'type': 'node', 'lat': -34.615, 'lon': -58.445, 'tags': {'name': 'Gym A', 'addr:street': 'Rivadavia',
                                                                      'addr:housenumber': '5000'}},
            {'type': 'way', 'center': {'lat': -34.616, 'lon': -58.436}, 'tags': {}},
            {'type': 'relation', 'tags': {'name': 'Sin centro'}}]}
        self.assertEqual([g['tooltip'] for g in entorno.gyms(data)], ['Gym A · Rivadavia 5000', 'Gimnasio'])


class ApiTests(unittest.TestCase):
    def test_layers_lines_and_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            poi, raw = build_sources(root)
            (raw / entorno.CLUBES_ARCHIVO).write_text(
                'nombre,tipo,tipo_sede,direccion,geometry\nClub Uno,Club de Barrio,Sede,Calle 1,POINT (-58.445 -34.615)\n',
                encoding='utf-8')
            gyms_path = root / 'osm-gimnasios-20261117' / 'gimnasios.json'
            gyms_path.parent.mkdir()
            gyms_path.write_text(json.dumps({'elements': [{'type': 'node', 'lat': -34.615, 'lon': -58.435,
                                                           'tags': {'name': 'Gym'}}]}), encoding='utf-8')
            zip_path = root / colectivos.ARCHIVO
            gtfs(zip_path, {'a': [(-58.46, -34.615), (-58.42, -34.615)]}, [('r1', '60A', 'A - Ramal', ['a'])])
            target = root / 'processed'
            summary = entorno.convert(poi, raw, target, gyms_path=gyms_path, gtfs_zip=zip_path)
            self.assertEqual((summary['Caballito']['clubes'], summary['Almagro']['gimnasios']), (1, 1))
            self.assertEqual(summary['Caballito']['colectivos'], ['60'])
            with TestClient(create_app(entorno_dir=target)) as client:
                layers = client.get('/api/mapa/capas', params={'barrio': 'Caballito', 'capas': ['clubes', 'gimnasios']}).json()
                self.assertEqual([len(layers[k]['features']) for k in ('clubes', 'gimnasios')], [1, 1])
                lines = client.get('/api/colectivos', params={'barrio': 'Almagro'}).json()
                self.assertTrue(lines['disponible'])
                self.assertEqual(lines['lineas'], [{'linea': '60', 'ramales': 1}])
                layer = client.get('/api/mapa/capas', params={'barrio': 'Caballito', 'capas': 'colectivos'}).json()
                feature, = layer['colectivos']['features']
                self.assertEqual(feature['properties']['linea'], '60')
                route = client.get('/api/colectivos/60').json()
                self.assertEqual(route['geometry']['type'], 'MultiLineString')
                self.assertEqual(client.get('/api/colectivos/7').status_code, 404)
                sources = {s['capa'] for s in client.get('/api/fuentes').json()['fuentes']}
                self.assertTrue({'clubes', 'gimnasios', 'colectivos'} <= sources)

    def test_without_optional_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            poi, raw = build_sources(Path(tmp))
            target = Path(tmp) / 'processed'
            summary = entorno.convert(poi, raw, target)
            self.assertNotIn('colectivos', summary['Caballito'])
            with TestClient(create_app(entorno_dir=target)) as client:
                self.assertFalse(client.get('/api/colectivos', params={'barrio': 'Caballito'}).json()['disponible'])
                layer = client.get('/api/mapa/capas', params={'barrio': 'Caballito', 'capas': 'clubes'}).json()['clubes']
                self.assertFalse(layer['disponible'])


if __name__ == '__main__':
    unittest.main()
