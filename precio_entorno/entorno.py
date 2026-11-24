"""Prepara las capas del mapa de entorno y un resumen por barrio oficial de CABA.

Fuentes (licencia CC-BY 2.5 AR, data.buenosaires.gob.ar), en `data/raw/badata-entorno/`
y `data/raw/badata-poi/`:
- Barrios oficiales: polígonos que definen la unidad geográfica de todo el resumen.
- Estaciones de subte y estaciones accesibles (ascensores y escaleras mecánicas).
- CeSAC, hospitales y establecimientos educativos: puntos.
- Espacios verdes públicos: plazas, parques, jardines y paseos. Se excluyen canteros
  centrales, plazoletas y patios.
- Mapa de Ruido: bandas de nivel exterior diurno y nocturno. Se resumen en una grilla
  de celdas de 100 m con 9 muestras por celda. El nivel típico de la celda es la banda
  mediana de las muestras relevadas; el mapa cubre sobre todo calles y veredas.
- Riesgo hídrico: áreas de prevención, en la proyección Gauss-Krüger Buenos Aires.

Cada punto se asigna al barrio cuyo polígono lo contiene. El porcentaje de ruido se calcula
sobre las celdas relevadas del barrio y el de riesgo hídrico, sobre las muestras de la grilla
que caen dentro del barrio.

Gastronomía (opcional): restaurantes, cafés y bares de OpenStreetMap (licencia ODbL, «© colaboradores
de OpenStreetMap»), de la captura más reciente en `data/raw/osm-AAAAMMDD/`. Solo se cuentan por barrio.
Si alguna categoría llegó al tope de puntos de su corrida, la captura está incompleta y no se usa.

Recreación (opcional): cines, teatros, museos, centros culturales y galerías de OpenStreetMap (ODbL), de la captura
más reciente en `data/raw/osm-recreacion-AAAAMMDD/recreacion.json`. Se cuentan por barrio y se dibujan en el mapa.
Se descartan los lugares sin nombre y los salones de eventos (en CABA, casi todos salones de fiestas).

Movilidad en bici y bibliotecas (opcionales, CC-BY 2.5 AR, en `data/raw/badata-entorno/`): tramos de ciclovía,
estaciones de Ecobici (listado del nuevo sistema; no informa si cada una está operativa) y bibliotecas de la Red de
la Ciudad. Se cuentan por barrio y se dibujan en el mapa. De las bibliotecas no se guardan teléfonos ni correos.

Universidades y trenes (opcionales, CC-BY 2.5 AR, en `data/raw/badata-entorno/`): sedes universitarias del Ministerio
de Educación (sin teléfonos, fax ni web) y estaciones de ferrocarril con su línea. Como el resto de los puntos, solo
quedan las que caen dentro de un barrio de CABA: las estaciones del conurbano no se usan.
"""

import argparse
import csv
import json
import math
import re
import warnings
from collections import Counter, defaultdict
from datetime import date
from hashlib import sha256
from pathlib import Path

import numpy as np
from matplotlib.path import Path as Shape

from . import colectivos as colectivos_gtfs
from .badata_poi import PARK_CLASSES
from .importing import BARRIOS, key

ROOT = Path(__file__).resolve().parents[1]
CELL_M = 100
SUB = 3
# Cortes descriptivos sobre el nivel típico de cada celda; no son límites normativos.
LOUD_DBA = {'diurno': 70, 'nocturno': 65}
# Con menos celdas relevadas el porcentaje no representa al barrio y se informa sin dato.
MIN_NOISE_CELLS = 30
DECIMALS = 5
# Gauss-Krüger Buenos Aires (Campo Inchauspe), usado por la capa de riesgo hídrico.
GKBA = ('+proj=tmerc +lat_0=-34.629269 +lon_0=-58.4633 +k=0.9999980 +x_0=100000 +y_0=100000 '
        '+ellps=intl +towgs84=-148,136,90,0,0,0,0 +units=m +no_defs')
LEVELS = {
    'inicial': 'Nivel inicial común',
    'primario': 'Nivel primario común',
    'secundario': 'Nivel secundario común',
}
CDN = 'https://cdn.buenosaires.gob.ar/datosabiertos/datasets/'
SOURCES = {
    'barrios': ('entorno', 'barrios.geojson', 'innovacion-transformacion-digital/barrios/barrios.geojson',
                'Barrios oficiales', 'Límites vigentes según el portal'),
    'subte': ('entorno', 'estaciones_de_subte.geojson', 'sbase/subte-estaciones/estaciones_de_subte.geojson',
              'Estaciones de subte', 'Red publicada por SBASE'),
    'subte_accesible': ('entorno', 'estaciones-accesibles.csv', 'sbase/subte-estaciones/estaciones-accesibles.csv',
                        'Estaciones accesibles', 'Ascensores y escaleras mecánicas informados'),
    'cesac': ('entorno', 'centros_salud_nivel_1_cesac.geojson',
              'ministerio-de-salud/centros-salud-accion-comunitaria-cesac/centros_salud_nivel_1_cesac.geojson',
              'Centros de Salud y Acción Comunitaria', 'Listado del Ministerio de Salud'),
    'ruido_diurno': ('entorno', 'medicion_de_ruido_diurno.geojson',
                     'agencia-de-proteccion-ambiental/mapa-ruido/medicion_de_ruido_diurno.geojson',
                     'Mapa de Ruido diurno', 'Edición 2025'),
    'ruido_nocturno': ('entorno', 'medicion_de_ruido_nocturno.geojson',
                       'agencia-de-proteccion-ambiental/mapa-ruido/medicion_de_ruido_nocturno.geojson',
                       'Mapa de Ruido nocturno', 'Edición 2025'),
    'riesgo_hidrico': ('entorno', 'riesgo-hidrico.geojson',
                       'secretaria-de-desarrollo-urbano/riesgo-hidrico/riesgo-hidrico.geojson',
                       'Riesgo hídrico', 'Capa publicada en diciembre de 2020'),
    'verdes': ('poi', 'espacio_verde_publico.geojson', None, 'Espacios verdes públicos', 'Inventario oficial'),
    'escuelas': ('poi', 'establecimientos_educativos.geojson', None, 'Establecimientos educativos',
                 'Mapa Escolar del Ministerio de Educación'),
    'hospitales': ('poi', 'hospitales.geojson', None, 'Hospitales', 'Ministerio de Salud'),
}
SUBTE_COLORS = {'A': '#18CCCC', 'B': '#EB0909', 'C': '#233AA8', 'D': '#02A17A', 'E': '#AE3D97', 'H': '#FFD600'}
GASTRONOMIA = ('restaurantes', 'cafes', 'bares')
# Recreación: tipo de la app → nombre para el mapa. El orden es el de la ficha y la leyenda.
RECREACION = {'cine': 'Cine', 'teatro': 'Teatro', 'museo': 'Museo', 'cultural': 'Centro cultural o galería'}
DUPLICADO_M = 150
GARAJES_ARCHIVO = 'garajes-comerciales.geojson'
GARAJES_FUENTE = 'https://data.buenosaires.gob.ar/dataset/garajes-comerciales'
# El portal muestra la publicación (10/05/2021) pero no la fecha del relevamiento.
CLUBES_ARCHIVO = 'clubes.csv'
CLUBES_FUENTE = 'https://data.buenosaires.gob.ar/dataset/clubes'
POLIDEPORTIVOS_ARCHIVO = 'polideportivos.geojson'
POLIDEPORTIVOS_FUENTE = 'https://data.buenosaires.gob.ar/dataset/polideportivos'
# Sedes sin actividad deportiva: no se muestran en la capa de clubes.
SEDES_ADMINISTRATIVAS = {'sede administrativa', 'anexo administrativo'}
GARAJES_PERIODO = 'Publicado en 2021 · fecha de relevamiento no informada'
# Rampas de accesibilidad: registros de obras por relevamiento, no un inventario de la ciudad. Que una esquina no
# figure no significa que no tenga rampa. Por eso no se cuentan por barrio ni se miden distancias.
RAMPAS_CDN = 'ministerio-de-espacio-publico-e-higiene-urbana/rampas-accesibilidad/'
RAMPAS = {
    '2011': 'rampas-de-accesibilidad-relevamiento-2011.csv',
    '2012-2014': 'rampas-de-accesibilidad-relevamiento-2012-2014.csv',
    '2016': 'rampas-de-accesibilidad-relevamiento-2016.csv',
}
# Capas opcionales del explorador de necesidades (etapa B): archivo, ruta en el CDN, título y período.
MOVILIDAD = {
    'ciclovias': ('ciclovias.geojson', 'transporte-y-obras-publicas/ciclovias/ciclovias.geojson',
                  'Ciclovías', 'Recurso del 17/03/2025 · actualización semestral declarada'),
    'ecobici': ('badata_ecobici_estaciones_bicicletas_nuevo_sistema.csv',
                'transporte-y-obras-publicas/estaciones-bicicletas-publicas/'
                'badata_ecobici_estaciones_bicicletas_nuevo_sistema.csv',
                'Estaciones de Ecobici', 'Listado del 04/04/2025 · no informa si cada estación está operativa'),
    'bibliotecas': ('bibliotecas.geojson', 'ministerio-de-cultura/bibliotecas/bibliotecas.geojson',
                    'Bibliotecas de la Ciudad', 'Listado del 20/03/2025'),
    'universidades': ('universidades.geojson', 'ministerio-de-educacion/universidades/universidades.geojson',
                      'Universidades y facultades', 'Recurso del 16/09/2025 · sedes, sin oferta académica ni horarios'),
    'trenes': ('estaciones_ferroviarias.geojson',
               'transporte-y-obras-publicas/estaciones-ferrocarril/estaciones_ferroviarias.geojson',
               'Estaciones de tren', 'Listado de 2019 · no informa frecuencias ni estaciones nuevas'),
}
# Nombre corto de cada línea de tren tal como la publica el listado («Mitre , F.C.G.B.M.»).
LINEAS_TREN = {'mitre': 'Mitre', 'sarmiento': 'Sarmiento', 'roca': 'Roca', 'urquiza': 'Urquiza',
               'san_martin': 'San Martín', 'belgrano_norte': 'Belgrano Norte', 'belgrano_sur': 'Belgrano Sur',
               'tren_de_la_costa': 'Tren de la Costa'}


def polygons(geometry):
    """Lista de polígonos; cada uno es una lista de anillos y el primero es el exterior."""
    if not geometry:
        return []
    if geometry['type'] == 'Polygon':
        return [geometry['coordinates']]
    if geometry['type'] == 'MultiPolygon':
        return geometry['coordinates']
    return []


def inside(points, polygon):
    if not len(points):
        return np.zeros(0, bool)
    ok = Shape(np.asarray(polygon[0])[:, :2]).contains_points(points)
    for hole in polygon[1:]:
        ok &= ~Shape(np.asarray(hole)[:, :2]).contains_points(points)
    return ok


def inside_shape(points, shape):
    """Puntos que caen en alguno de los polígonos de una forma."""
    hit = np.zeros(len(points), bool)
    for polygon in shape:
        hit |= inside(points, polygon)
    return hit


class Grid:
    """Muestras regulares sobre CABA: SUB × SUB muestras por celda de CELL_M metros."""

    def __init__(self, west, south, east, north, cell_m=CELL_M, sub=SUB):
        self.sub = sub
        self.dlat = cell_m / 111_320 / sub
        self.dlon = cell_m / (111_320 * math.cos(math.radians((south + north) / 2))) / sub
        self.west, self.south = west, south
        self.nx = math.ceil((east - west) / self.dlon / sub) * sub
        self.ny = math.ceil((north - south) / self.dlat / sub) * sub

    def lon(self, ix):
        return self.west + (np.asarray(ix) + 0.5) * self.dlon

    def lat(self, iy):
        return self.south + (np.asarray(iy) + 0.5) * self.dlat

    def cover(self, polygon):
        ring = np.asarray(polygon[0])[:, :2]
        x0 = max(0, math.floor((ring[:, 0].min() - self.west) / self.dlon))
        x1 = min(self.nx, math.ceil((ring[:, 0].max() - self.west) / self.dlon) + 1)
        y0 = max(0, math.floor((ring[:, 1].min() - self.south) / self.dlat))
        y1 = min(self.ny, math.ceil((ring[:, 1].max() - self.south) / self.dlat) + 1)
        if x0 >= x1 or y0 >= y1:
            return np.zeros(0, int), np.zeros(0, int)
        iy, ix = (a.ravel() for a in np.mgrid[y0:y1, x0:x1])
        ok = inside(np.column_stack([self.lon(ix), self.lat(iy)]), polygon)
        return iy[ok], ix[ok]

    def blocks(self, values):
        ny, nx, s = self.ny // self.sub, self.nx // self.sub, self.sub
        return values.reshape(ny, s, nx, s).transpose(0, 2, 1, 3).reshape(ny, nx, s * s)

    def cell_center(self, cy, cx):
        return (round(float(self.lon(cx * self.sub + (self.sub - 1) / 2)), DECIMALS),
                round(float(self.lat(cy * self.sub + (self.sub - 1) / 2)), DECIMALS))


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def rounded(geometry, transform=None):
    """Redondea a 5 decimales (≈1 m) y descarta vértices repetidos tras redondear."""
    out = []
    for polygon in polygons(geometry):
        new = [points for points in (rounded_ring(ring, transform) for ring in polygon) if len(points) >= 4]
        if new:
            out.append(new)
    return {'type': 'MultiPolygon', 'coordinates': out}


def rounded_ring(ring, transform=None):
    """Vértices de un anillo redondeados, sin repetir el anterior."""
    points = []
    for x, y, *_ in ring:
        if transform:
            x, y = transform(x, y)
        point = [round(x, DECIMALS), round(y, DECIMALS)]
        if not points or point != points[-1]:
            points.append(point)
    return points


def barrio_name(value):
    return BARRIOS[key(value)]


class Barrios:
    def __init__(self, collection):
        self.names, self.shapes, self.comunas, self.area_ha = [], [], {}, {}
        for feature in collection['features']:
            props = feature['properties']
            name = barrio_name(props['nombre'])
            self.names.append(name)
            self.shapes.append(polygons(feature['geometry']))
            self.comunas[name] = props.get('comuna')
            self.area_ha[name] = round((props.get('area_metro') or 0) / 10_000, 1)
        rings = np.concatenate([np.asarray(p[0])[:, :2] for shape in self.shapes for p in shape])
        self.bbox = (*rings.min(axis=0), *rings.max(axis=0))

    def of(self, points):
        points = np.asarray(points, float).reshape(-1, 2)
        out = [None] * len(points)
        for name, shape in zip(self.names, self.shapes):
            hit = inside_shape(points, shape)
            out = [name if h and not o else o for o, h in zip(out, hit)]
        return out

    def raster(self, grid):
        values = np.full((grid.ny, grid.nx), -1, int)
        for index, polygon in [(i, polygon) for i, shape in enumerate(self.shapes) for polygon in shape]:
            iy, ix = grid.cover(polygon)
            values[iy, ix] = index
        return values


def projected(transformer):
    def point(geometry):
        x, y = geometry['coordinates'][:2]
        lon, lat = transformer.transform(x, y)
        return round(lon, DECIMALS), round(lat, DECIMALS)
    return point


def subte(collection, accessible_csv):
    elevators = {}
    with accessible_csv.open(encoding='utf-8-sig', newline='') as file:
        for row in csv.DictReader(file, delimiter=';'):
            try:
                elevators[(row['linea'].strip().upper(), key(row['estacion']))] = int(row['ascensores'])
            except (KeyError, ValueError):
                continue
    out = []
    for feature in collection['features']:
        props, geometry = feature['properties'], feature.get('geometry')
        if not geometry or geometry['type'] != 'Point':
            continue
        line = (props.get('linea') or '').strip().upper()
        name = (props.get('estacion') or '').strip()
        lift = elevators.get((line, key(name)))
        detail = f'Estación {name} · Línea {line}'
        if lift is not None:
            detail += f' · Ascensores informados: {lift}'
        out.append({'name': name, 'line': line, 'elevators': lift, 'lon': round(geometry['coordinates'][0], DECIMALS),
                    'lat': round(geometry['coordinates'][1], DECIMALS), 'tooltip': detail})
    return out


def school_levels(text):
    return [level for level, label in LEVELS.items() if label in (text or '')]


def schools(collection, point):
    out = []
    for feature in collection['features']:
        geometry = feature.get('geometry')
        if not geometry or geometry['type'] != 'Point':
            continue
        props = feature['properties']
        levels = school_levels(props.get('nen_mde'))
        if not levels:
            continue
        lon, lat = point(geometry)
        management = props.get('ges') or 'Sin dato'
        out.append({'name': props.get('nam'), 'levels': levels, 'management': management, 'lon': lon, 'lat': lat,
                    'tooltip': f"{props.get('nam')} · {', '.join(levels).capitalize()} · Gestión {management.lower()}"})
    return out


def hospitals(collection, point):
    out = []
    for feature in collection['features']:
        geometry = feature.get('geometry')
        if not geometry or geometry['type'] != 'Point':
            continue
        props = feature['properties']
        lon, lat = point(geometry)
        detail = f"{props.get('fna') or props.get('nam')} · {props.get('esp') or 'Sin especialidad informada'}"
        out.append({'name': props.get('fna') or props.get('nam'), 'lon': lon, 'lat': lat,
                    'web': props.get('web'), 'tooltip': detail})
    return out


def cesac(collection):
    out = []
    for feature in collection['features']:
        geometry = feature.get('geometry')
        if not geometry or geometry['type'] != 'Point':
            continue
        props = feature['properties']
        lon, lat = geometry['coordinates'][:2]
        out.append({'name': props.get('nombre'), 'lon': round(lon, DECIMALS), 'lat': round(lat, DECIMALS),
                    'web': props.get('web'), 'tooltip': f"{props.get('nombre')} · {props.get('direccion') or ''}".strip(' ·')})
    return out


def commercial_garages(collection):
    if collection.get('type') != 'FeatureCollection' or not isinstance(collection.get('features'), list):
        raise ValueError('El archivo de garajes debe ser una colección GeoJSON de puntos.')
    garages = {}
    for feature in collection['features']:
        geometry = feature.get('geometry') or {}
        coordinates = geometry.get('coordinates')
        if geometry.get('type') != 'Point' or not isinstance(coordinates, list) or len(coordinates) < 2:
            continue
        lon, lat = coordinates[:2]
        if not (isinstance(lon, (int, float)) and isinstance(lat, (int, float))
                and -180 <= lon <= 180 and -90 <= lat <= 90):
            continue
        props = {key(name): value for name, value in (feature.get('properties') or {}).items()}
        name = props.get('nombre') or props.get('fna') or props.get('nam') or 'Garaje comercial'
        address = props.get('direccion') or props.get('domicilio')
        if not address and props.get('calle'):
            address = f"{props['calle']} {props.get('num') or ''}".strip()
        if not address and props.get('calle_nombre'):
            address = f"{props['calle_nombre']} {props.get('calle_altura') or ''}".strip()
        tooltip = f'{name} · {address}' if address else str(name)
        lon, lat = round(lon, DECIMALS), round(lat, DECIMALS)
        garages[lon, lat, tooltip] = {'name': str(name), 'lon': lon, 'lat': lat, 'tooltip': tooltip}
    return list(garages.values())


def line(coordinates):
    out = []
    for x, y, *_ in coordinates:
        point = [round(x, DECIMALS), round(y, DECIMALS)]
        if not out or point != out[-1]:
            out.append(point)
    return out


def bike_lanes(collection):
    """Tramos de ciclovía. «Mano única» es lo único que informa la fuente: no dice si el tramo es protegido."""
    out = []
    for feature in collection.get('features', []):
        geometry = feature.get('geometry') or {}
        parts = ([geometry.get('coordinates')] if geometry.get('type') == 'LineString'
                 else geometry.get('coordinates') if geometry.get('type') == 'MultiLineString' else [])
        props = feature.get('properties') or {}
        name = ' '.join(str(props.get('nombre') or '').split()) or 'Ciclovía'
        kind = 'Mano única' if 'nica' in str(props.get('tipo') or '').lower() else 'Doble mano'
        out += [lane_feature(coords, name, kind) for coords in (line(part or []) for part in parts) if len(coords) >= 2]
    return out


def lane_feature(coords, name, kind):
    """Tramo de ciclovía con su largo en metros."""
    length = sum(math.hypot((b[0] - a[0]) * 111_320 * math.cos(math.radians(a[1])), (b[1] - a[1]) * 111_320) for a, b in zip(coords, coords[1:]))
    return {'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': coords},
            'properties': {'name': name, 'kind': kind, 'length_m': round(length),
                           'tooltip': f'Ciclovía · {name} · {kind}'}}


def ecobici_stations(rows):
    """Estaciones de Ecobici del nuevo sistema. El listado no dice si cada una está operativa."""
    out = {}
    for row in rows:
        row = {key(k): v for k, v in row.items()}
        try:
            lon, lat = float(row.get('longitud')), float(row.get('latitud'))
        except (TypeError, ValueError):
            continue
        name = ' '.join((row.get('nombre') or 'Estación').split()).title()
        address = ' '.join((row.get('direccion') or '').split())
        lon, lat = round(lon, DECIMALS), round(lat, DECIMALS)
        out[lon, lat] = {'name': name, 'lon': lon, 'lat': lat,
                         'tooltip': ' · '.join(p for p in (f'Ecobici {name}', address) if p)}
    return list(out.values())


def universities(collection):
    """Sedes universitarias: universidad, unidad académica, sede y dirección. Se descartan teléfonos, fax y web."""
    out = []
    for feature in collection.get('features', []):
        geometry = feature.get('geometry') or {}
        if geometry.get('type') != 'Point':
            continue
        props = feature.get('properties') or {}
        clean = lambda key: ' '.join(str(props.get(key) or '').split())
        name, unit, campus = clean('nombre') or 'Universidad', clean('unidad_aca'), clean('sede')
        address = clean('dirreccion') or clean('direccion')
        lon, lat = (round(v, DECIMALS) for v in geometry['coordinates'][:2])
        out.append({'name': name, 'unit': unit or None, 'lon': lon, 'lat': lat,
                    'tooltip': ' · '.join(p for p in (name, unit, campus, address) if p)})
    return out


def train_stations(collection):
    """Estaciones de tren con su línea. Una estación que el listado repite por ramal queda una vez por línea."""
    out = {}
    for feature in collection.get('features', []):
        geometry = feature.get('geometry') or {}
        if geometry.get('type') != 'Point':
            continue
        props = feature.get('properties') or {}
        name = ' '.join(str(props.get('nombre') or '').split())
        raw = str(props.get('linea') or '').split(',')[0]
        line = LINEAS_TREN.get(key(raw), ' '.join(raw.split()).title())
        if not name or not line:
            continue
        lon, lat = (round(v, DECIMALS) for v in geometry['coordinates'][:2])
        out.setdefault((key(name), line), {'name': name, 'line': line, 'lon': lon, 'lat': lat,
                                            'tooltip': f'Estación {name} · Línea {line}'})
    return list(out.values())


def libraries(collection):
    """Bibliotecas de la Red de la Ciudad. Se descartan teléfonos, correos y redes."""
    out = []
    for feature in collection.get('features', []):
        geometry = feature.get('geometry') or {}
        if geometry.get('type') != 'Point':
            continue
        props = feature.get('properties') or {}
        name = ' '.join(str(props.get('nombre') or 'Biblioteca').split())
        kind = ' '.join(str(props.get('tipo') or '').split())
        address = ' '.join(str(props.get('dirreccion') or props.get('direccion') or '').split())
        lon, lat = (round(v, DECIMALS) for v in geometry['coordinates'][:2])
        out.append({'name': name, 'lon': lon, 'lat': lat, 'tooltip': ' · '.join(p for p in (name, kind, address) if p)})
    return out


def add_ramps(out, rows, survey):
    """Agrega a `out` las rampas de un relevamiento, agrupadas por punto."""
    for row in rows:
        row = {key(k): (v or '').strip() for k, v in row.items() if k}
        try:
            lon, lat = round(float(row['x']), DECIMALS), round(float(row['y']), DECIMALS)
        except (KeyError, ValueError):
            continue
        if not (-58.6 < lon < -58.2 and -34.75 < lat < -34.5):
            continue
        address = row.get('dom_norma') or ' '.join(p for p in (row.get('calle'), row.get('altura')) if p)
        when = f"obra de {row['anio']}" if row.get('anio') else f'relevamiento {survey}'
        previous = out.get((lon, lat))
        # Un mismo punto puede reunir varias rampas (las esquinas se ubicaron por dirección).
        same = previous is not None and previous['survey'] == survey
        out[lon, lat] = {'name': 'Rampa', 'lon': lon, 'lat': lat, 'survey': survey,
                         'count': previous['count'] + 1 if same else 1, 'address': address.title(), 'when': when,
                         'building': (same and previous['building']) or row.get('estado', '').lower().startswith('en ejec')}


def ramps(files):
    """Rampas de los relevamientos de obras (`{relevamiento: ruta}`), agrupadas por punto (ubicadas por dirección).
    Un punto repetido entre relevamientos queda con el más reciente. No se guardan empresas ni números de nota."""
    out = {}
    for survey in sorted(files):
        raw = files[survey].read_bytes()
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('latin-1')
        add_ramps(out, csv.DictReader(text.splitlines(), delimiter=';'), survey)
    for ramp in out.values():
        label = 'Rampa registrada' if ramp['count'] == 1 else f"{ramp['count']} rampas registradas"
        when = ramp.pop('when') + (('' if ramp['count'] == 1 else ', alguna') + ' en ejecución al relevar'
                                   if ramp.pop('building') else '')
        ramp['tooltip'] = ' · '.join(p for p in (label, ramp.pop('address'), when) if p)
    return list(out.values())


def wkt_point(text):
    """`POINT (lon lat)` → (lon, lat), o None."""
    match = re.fullmatch(r'\s*POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)\s*', text or '', re.I)
    return (float(match[1]), float(match[2])) if match else None


def sports_clubs(club_rows, polideportivos=None):
    """Clubes de barrio y polideportivos de la Ciudad. No se guardan teléfonos, correos ni redes."""
    out = {}
    for row in club_rows:
        point = wkt_point(row.get('geometry'))
        if not point or (row.get('tipo_sede') or '').strip().lower() in SEDES_ADMINISTRATIVAS:
            continue
        name = (row.get('nombre') or 'Club').strip()
        parts = [name, (row.get('tipo') or 'Club').strip(), (row.get('direccion') or '').strip()]
        lon, lat = round(point[0], DECIMALS), round(point[1], DECIMALS)
        out[lon, lat, name] = {'name': name, 'lon': lon, 'lat': lat, 'tooltip': ' · '.join(p for p in parts if p)}
    for feature in (polideportivos or {}).get('features', []):
        geometry = feature.get('geometry') or {}
        if geometry.get('type') != 'Point':
            continue
        props = feature.get('properties') or {}
        name = (props.get('nombre') or 'Polideportivo').strip()
        address = (props.get('dirreccion') or props.get('direccion') or '').strip()
        lon, lat = (round(v, DECIMALS) for v in geometry['coordinates'][:2])
        out[lon, lat, name] = {'name': name, 'lon': lon, 'lat': lat,
                               'tooltip': ' · '.join(p for p in (name, 'Polideportivo de la Ciudad', address) if p)}
    return list(out.values())


def gyms(overpass):
    """Gimnasios de OpenStreetMap (`leisure=fitness_centre` y centros deportivos de fitness)."""
    out = {}
    for element in overpass.get('elements', []):
        tags = element.get('tags') or {}
        center = element.get('center') or element
        lon, lat = center.get('lon'), center.get('lat')
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            continue
        name = (tags.get('name') or 'Gimnasio').strip()
        street = ' '.join(v for v in (tags.get('addr:street'), tags.get('addr:housenumber')) if v)
        lon, lat = round(lon, DECIMALS), round(lat, DECIMALS)
        out[lon, lat, name] = {'name': name, 'lon': lon, 'lat': lat,
                               'tooltip': f'{name} · {street}' if street else name}
    return list(out.values())


def recreation_kind(tags):
    """Tipo de recreación de un elemento de OSM, o None si no corresponde."""
    amenity, tourism = tags.get('amenity'), tags.get('tourism')
    if amenity == 'cinema':
        return 'cine'
    if amenity == 'theatre':
        return 'teatro'
    if tourism == 'museum' or amenity == 'planetarium':
        return 'museo'
    if amenity in ('arts_centre', 'music_venue') or tourism == 'gallery':
        return 'cultural'
    return None


def near_twin(lon, lat, twins):
    """Si algún lugar ya visto con el mismo nombre y tipo está a menos de DUPLICADO_M metros."""
    return any(math.hypot((lon - x) * 111_320 * math.cos(math.radians(lat)), (lat - y) * 111_320) < DUPLICADO_M for x, y in twins)


def recreation(overpass):
    """Cines, teatros, museos, centros culturales y galerías de OSM. Sin nombre no se pueden identificar: se descartan."""
    out, seen = [], defaultdict(list)
    for element in overpass.get('elements', []):
        tags = element.get('tags') or {}
        kind = recreation_kind(tags)
        name = ' '.join(str(tags.get('name') or '').split())
        center = element.get('center') or element
        lon, lat = center.get('lon'), center.get('lat')
        if not kind or not name or not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            continue
        # Un mismo lugar a veces está como punto y como edificio: con el mismo nombre y tipo a menos de
        # DUPLICADO_M metros se queda el primero.
        twins = seen[name.casefold(), kind]
        if near_twin(lon, lat, twins):
            continue
        twins.append((lon, lat))
        street = ' '.join(v for v in (tags.get('addr:street'), tags.get('addr:housenumber')) if v)
        lon, lat = round(lon, DECIMALS), round(lat, DECIMALS)
        out.append({'name': name, 'kind': kind, 'lon': lon, 'lat': lat,
                    'tooltip': ' · '.join(p for p in (name, RECREACION[kind], street) if p)})
    return out


def latest_recreation(raw_dir):
    """`osm-recreacion-AAAAMMDD/recreacion.json` más reciente, o None."""
    found = sorted(Path(raw_dir).glob('osm-recreacion-*/recreacion.json'))
    return found[-1] if found else None


def latest_gyms(raw_dir):
    """`osm-gimnasios-AAAAMMDD/gimnasios.json` más reciente, o None."""
    found = sorted(Path(raw_dir).glob('osm-gimnasios-*/gimnasios.json'))
    return found[-1] if found else None


# Tolerancia para simplificar los polígonos de plazas: imperceptible a escala de barrio y aligera el mapa.
SIMPLIFICAR_VERDES_M = 1.5


def simplify_ring(ring, tolerance_m=SIMPLIFICAR_VERDES_M):
    """Douglas-Peucker sobre un anillo cerrado, en metros planos. Devuelve el anillo original si quedaría degenerado."""
    points = np.asarray(ring, float)
    n = len(points)
    if n <= 5:
        return ring
    scale = 111_320 * math.cos(math.radians(points[:, 1].mean()))
    xy = np.column_stack([points[:, 0] * scale, points[:, 1] * 111_320])
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    # El anillo empieza y termina en el mismo punto: se parte en el vértice más lejano a ese punto.
    far = int(np.argmax(np.hypot(*(xy - xy[0]).T)))
    keep[far] = True
    stack = [(0, far), (far, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = xy[i], xy[j]
        segment = b - a
        length = math.hypot(*segment)
        inner = xy[i + 1:j] - a
        dist = (np.abs(segment[0] * inner[:, 1] - segment[1] * inner[:, 0]) / length if length
                else np.hypot(*inner.T))
        k = int(np.argmax(dist))
        if dist[k] > tolerance_m:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    out = [ring[m] for m in np.flatnonzero(keep)]
    return out if len(out) >= 4 else ring


def simplify_polygons(geometry):
    coords = [[simplify_ring(ring) for ring in polygon] for polygon in geometry['coordinates']]
    return {'type': geometry['type'], 'coordinates': coords}


def green_spaces(collection):
    features = []
    for feature in collection['features']:
        props = feature['properties']
        kind = (props.get('clasificac') or '').upper()
        if kind not in PARK_CLASSES or not feature.get('geometry'):
            continue
        full = rounded(feature['geometry'])
        if not full['coordinates']:
            continue
        geometry = simplify_polygons(full)
        area = props.get('area') or 0
        name = props.get('nombre') or kind.capitalize()
        features.append({'type': 'Feature', 'geometry': geometry, 'properties': {
            'name': name, 'kind': kind.capitalize(), 'area_m2': round(area),
            'tooltip': f'{name} · {kind.capitalize()} · {area / 10_000:.2f} ha'},
            # Centro del polígono sin simplificar: el barrio no depende de cuántos vértices se dibujan.
            '_centro': np.asarray(full['coordinates'][0][0]).mean(axis=0)})
    return features


def noise_grid(collection, grid):
    values = np.full((grid.ny, grid.nx), np.nan)
    colors = {}
    for feature in collection['features']:
        props = feature['properties']
        try:
            low = float(props['dba_low'])
        except (KeyError, TypeError, ValueError):
            continue
        if props.get('color'):
            colors[int(low)] = [int(c) for c in str(props['color']).split()[:3]]
        raise_to(values, grid, feature['geometry'], low)
    return values, colors


def raise_to(values, grid, geometry, low):
    """Lleva a `low` las celdas que cubre la geometría y tenían un valor menor o ninguno."""
    for polygon in polygons(geometry):
        iy, ix = grid.cover(polygon)
        values[iy, ix] = np.fmax(values[iy, ix], low)


def noise_cells(values, grid, inside_city):
    blocks = grid.blocks(values)
    counts = (~np.isnan(blocks)).sum(axis=-1)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        medians = np.floor(np.nanmedian(blocks, axis=-1) / 5) * 5
        highest = np.nanmax(blocks, axis=-1)
    cells = []
    for cy, cx in zip(*np.nonzero((counts > 0) & inside_city)):
        lon, lat = grid.cell_center(cy, cx)
        cells.append([lon, lat, int(medians[cy, cx]), int(highest[cy, cx])])
    return cells


def share(mask, within):
    total = int(within.sum())
    return round(float((mask & within).sum()) / total, 3) if total else None


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def latest_osm(raw_dir):
    """Carpeta `osm-AAAAMMDD` más reciente que tenga las tres categorías de gastronomía, o None."""
    found = sorted(p for p in Path(raw_dir).glob('osm-[0-9]*')
                   if p.is_dir() and all((p / f'{name}.json').exists() for name in GASTRONOMIA))
    return found[-1] if found else None


def osm_capture_date(folder):
    stamp = folder.name.removeprefix('osm-')
    return f'{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}' if len(stamp) == 8 and stamp.isdigit() else None


def gastronomy(osm_dir, barrios):
    """Conteos por barrio de restaurantes, cafés y bares de OSM; None si la captura está incompleta."""
    runs_path = osm_dir / 'corridas.json'
    runs = {r['nombre']: r for r in read(runs_path)} if runs_path.exists() else {}
    truncated = [name for name in GASTRONOMIA
                 if name in runs and runs[name].get('puntos', 0) >= runs[name].get('max_items', math.inf)]
    if truncated:
        warnings.warn(f"OSM incompleto en {', '.join(truncated)}: no se usa la gastronomía.")
        return None
    counts, found = defaultdict(Counter), []
    for name in GASTRONOMIA:
        items = read(osm_dir / f'{name}.json')
        coords = [(i.get('lon', i.get('longitude')), i.get('lat', i.get('latitude'))) for i in items]
        coords = [c for c in coords if isinstance(c[0], (int, float)) and isinstance(c[1], (int, float))]
        found += [(barrio, name) for barrio in (barrios.of(coords) if coords else []) if barrio]
    for barrio, name in found:
        counts[barrio][name] += 1
    return counts


def with_barrio(items, barrios):
    """Anota el barrio de cada punto y deja solo los que caen en alguno."""
    for item, name in zip(items, barrios.of([(i['lon'], i['lat']) for i in items])):
        item['barrio'] = name
    return [item for item in items if item['barrio']]


def mark_cells(mask, grid, geometry):
    """Marca las celdas de la grilla que cubre la geometría."""
    for polygon in polygons(geometry):
        iy, ix = grid.cover(polygon)
        mask[iy, ix] = True


def tag_barrio(cells, grid, cell_barrio, names):
    """Agrega a cada celda de ruido el barrio que le corresponde en la grilla gruesa."""
    for cell in cells:
        cy = int((cell[1] - grid.south) / grid.dlat) // grid.sub
        cx = int((cell[0] - grid.west) / grid.dlon) // grid.sub
        cell.append(names[cell_barrio[cy, cx]])


def noise_share(cells, name, period):
    """Celdas relevadas del barrio y proporción con ruido alto; None si hay pocas celdas."""
    typical = [cell[2] for cell in cells if cell[4] == name]
    return {
        'celdas': len(typical),
        'alto': (round(sum(v >= LOUD_DBA[period] for v in typical) / len(typical), 3)
                 if len(typical) >= MIN_NOISE_CELLS else None),
    }


def convert(poi_dir, entorno_dir, target, downloaded=None, osm_dir=None, gyms_path=None, gtfs_zip=None,
            recreation_path=None):
    from pyproj import Transformer

    target.mkdir(parents=True, exist_ok=True)
    source_dirs = {'poi': poi_dir, 'entorno': entorno_dir}
    path = {name: source_dirs[folder] / file for name, (folder, file, *_) in SOURCES.items()}

    barrios = Barrios(read(path['barrios']))
    grid = Grid(*barrios.bbox)
    city = barrios.raster(grid)
    cell_barrio = np.full((grid.ny // grid.sub, grid.nx // grid.sub), -1, int)
    blocks = grid.blocks(city)
    for cy, cx in zip(*np.nonzero((blocks >= 0).any(axis=-1))):
        votes = Counter(int(v) for v in blocks[cy, cx] if v >= 0)
        cell_barrio[cy, cx] = votes.most_common(1)[0][0]
    names = barrios.names
    local = projected(Transformer.from_crs('EPSG:9498', 'EPSG:4326', always_xy=True))
    gkba = Transformer.from_crs(GKBA, 'EPSG:4326', always_xy=True)

    points = {
        'subte': subte(read(path['subte']), path['subte_accesible']),
        'cesac': cesac(read(path['cesac'])),
        'hospitales': hospitals(read(path['hospitales']), local),
        'escuelas': schools(read(path['escuelas']), local),
    }
    garage_path = entorno_dir / GARAJES_ARCHIVO
    if garage_path.is_file():
        points['estacionamiento'] = commercial_garages(read(garage_path))
    clubs_path, poli_path = entorno_dir / CLUBES_ARCHIVO, entorno_dir / POLIDEPORTIVOS_ARCHIVO
    if clubs_path.is_file():
        with clubs_path.open(encoding='utf-8-sig', newline='') as handle:
            points['clubes'] = sports_clubs(csv.DictReader(handle), read(poli_path) if poli_path.is_file() else None)
    gyms_path = Path(gyms_path) if gyms_path else None
    if gyms_path and gyms_path.is_file():
        points['gimnasios'] = gyms(read(gyms_path))
    recreation_path = Path(recreation_path) if recreation_path else None
    if recreation_path and recreation_path.is_file():
        points['recreacion'] = recreation(read(recreation_path))
    ramp_files = {survey: entorno_dir / file for survey, file in RAMPAS.items() if (entorno_dir / file).is_file()}
    if ramp_files:
        points['rampas'] = ramps(ramp_files)
    mobility = {name: entorno_dir / file for name, (file, *_) in MOVILIDAD.items()}
    mobility = {name: path_ for name, path_ in mobility.items() if path_.is_file()}
    if 'ecobici' in mobility:
        with mobility['ecobici'].open(encoding='utf-8-sig', newline='') as handle:
            points['ecobici'] = ecobici_stations(csv.DictReader(handle))
    if 'bibliotecas' in mobility:
        points['bibliotecas'] = libraries(read(mobility['bibliotecas']))
    if 'universidades' in mobility:
        points['universidades'] = universities(read(mobility['universidades']))
    if 'trenes' in mobility:
        points['trenes'] = train_stations(read(mobility['trenes']))
    lanes = bike_lanes(read(mobility['ciclovias'])) if 'ciclovias' in mobility else None
    if lanes is not None:
        middles = [f['geometry']['coordinates'][len(f['geometry']['coordinates']) // 2] for f in lanes]
        for feature, name in zip(lanes, barrios.of(middles)):
            feature['properties']['barrio'] = name
        lanes = [f for f in lanes if f['properties']['barrio']]
    for items in points.values():
        items[:] = with_barrio(items, barrios)

    greens = green_spaces(read(path['verdes']))
    centers = [f.pop('_centro') for f in greens]
    for feature, name in zip(greens, barrios.of(centers)):
        feature['properties']['barrio'] = name
    greens = [f for f in greens if f['properties']['barrio']]

    risk_features, risk = [], np.zeros((grid.ny, grid.nx), bool)
    for feature in read(path['riesgo_hidrico'])['features']:
        geometry = rounded(feature['geometry'], gkba.transform)
        mark_cells(risk, grid, geometry)
        if geometry['coordinates']:
            risk_features.append({'type': 'Feature', 'geometry': geometry, 'properties': {
                'tooltip': 'Área de prevención por riesgo hídrico · Capa 2020 · Dato para investigar en la visita'}})

    noise, noise_colors = {}, {}
    for period in ('diurno', 'nocturno'):
        values, colors = noise_grid(read(path[f'ruido_{period}']), grid)
        noise_colors.update(colors)
        noise[period] = noise_cells(values, grid, cell_barrio >= 0)
    for cells in noise.values():
        tag_barrio(cells, grid, cell_barrio, names)

    gtfs_zip = Path(gtfs_zip) if gtfs_zip else None
    lines = colectivos_gtfs.build(gtfs_zip, barrios) if gtfs_zip and gtfs_zip.is_file() else None
    lines_of = colectivos_gtfs.by_barrio(lines) if lines is not None else {}

    osm_dir = Path(osm_dir) if osm_dir else None
    food = gastronomy(osm_dir, barrios) if osm_dir else None
    capture = osm_capture_date(osm_dir) if osm_dir else None

    summary = {}
    for index, name in enumerate(names):
        within = city == index
        mine = {layer: [i for i in items if i['barrio'] == name] for layer, items in points.items()}
        school_counts = {level: Counter(s['management'] for s in mine['escuelas'] if level in s['levels']) for level in LEVELS}
        own_greens = [f['properties'] for f in greens if f['properties']['barrio'] == name]
        noise_summary = {period: noise_share(cells, name, period) for period, cells in noise.items()}
        summary[name] = {
            'comuna': barrios.comunas[name],
            'area_ha': barrios.area_ha[name],
            'subte_lineas': sorted({s['line'] for s in mine['subte']}),
            'subte_estaciones': len(mine['subte']),
            'verdes_cantidad': len(own_greens),
            'verdes_ha': round(sum(g['area_m2'] for g in own_greens) / 10_000, 1),
            'escuelas': {level: dict(counts) for level, counts in school_counts.items()},
            'cesac': len(mine['cesac']),
            'hospitales': len(mine['hospitales']),
            'ruido': noise_summary,
            'riesgo_hidrico': share(risk, within),
        }
        layers = ('clubes', 'gimnasios', 'ecobici', 'bibliotecas', 'universidades')
        summary[name].update({layer: len(mine[layer]) for layer in layers if layer in points})
        if 'trenes' in points:
            summary[name]['trenes'] = len({s['name'] for s in mine['trenes']})
            summary[name]['trenes_lineas'] = sorted({s['line'] for s in mine['trenes']})
        if 'recreacion' in points:
            kinds = Counter(item['kind'] for item in mine['recreacion'])
            summary[name]['recreacion'] = {kind: kinds[kind] for kind in RECREACION}
        if lanes is not None:
            summary[name]['ciclovias_km'] = round(
                sum(f['properties']['length_m'] for f in lanes if f['properties']['barrio'] == name) / 1000, 1)
        if lines is not None:
            summary[name]['colectivos'] = lines_of.get(name, [])
        if food is not None:
            summary[name]['gastronomia'] = {**{k: food[name][k] for k in GASTRONOMIA}, 'captura': capture}

    barrio_features = []
    for feature in read(path['barrios'])['features']:
        name = barrio_name(feature['properties']['nombre'])
        barrio_features.append({'type': 'Feature', 'geometry': rounded(feature['geometry']), 'properties': {
            'barrio': name, 'comuna': barrios.comunas[name], 'tooltip': f"{name} · Comuna {barrios.comunas[name]}"}})

    sources = []
    for name, (folder, file, url, title, period) in SOURCES.items():
        sources.append({'capa': name, 'titulo': title, 'archivo': file, 'periodo': period,
                        'url': CDN + url if url else None, 'sha256': digest(path[name]),
                        'licencia': 'CC-BY 2.5 AR · Buenos Aires Data'})
    if 'estacionamiento' in points:
        sources.append({'capa': 'estacionamiento', 'titulo': 'Garajes comerciales habilitados',
                        'archivo': garage_path.name, 'periodo': GARAJES_PERIODO + '; vigencia a confirmar',
                        'url': GARAJES_FUENTE, 'sha256': digest(garage_path),
                        'licencia': 'CC-BY 2.5 AR · Buenos Aires Data'})
    if 'clubes' in points:
        sources.append({'capa': 'clubes', 'titulo': 'Clubes de barrio', 'archivo': clubs_path.name,
                        'periodo': 'Listado que la Ciudad actualiza cada trimestre', 'url': CLUBES_FUENTE,
                        'sha256': digest(clubs_path), 'licencia': 'CC-BY 2.5 AR · Buenos Aires Data'})
        if poli_path.is_file():
            sources.append({'capa': 'clubes', 'titulo': 'Polideportivos de la Ciudad', 'archivo': poli_path.name,
                            'periodo': 'Listado que la Ciudad actualiza cada trimestre', 'url': POLIDEPORTIVOS_FUENTE,
                            'sha256': digest(poli_path), 'licencia': 'CC-BY 2.5 AR · Buenos Aires Data'})
    if 'gimnasios' in points:
        stamp = osm_capture_date(gyms_path.parent.with_name(gyms_path.parent.name.replace('osm-gimnasios-', 'osm-')))
        sources.append({'capa': 'gimnasios', 'titulo': 'Gimnasios', 'archivo': gyms_path.name,
                        'periodo': f'Captura del {stamp}' if stamp else 'Captura de OpenStreetMap',
                        'url': 'https://www.openstreetmap.org/copyright', 'sha256': digest(gyms_path),
                        'licencia': 'ODbL · © colaboradores de OpenStreetMap'})
    if 'recreacion' in points:
        stamp = osm_capture_date(recreation_path.parent.with_name(
            recreation_path.parent.name.replace('osm-recreacion-', 'osm-')))
        sources.append({'capa': 'recreacion', 'titulo': 'Cines, teatros, museos y centros culturales',
                        'archivo': recreation_path.name,
                        'periodo': f'Captura del {stamp}' if stamp else 'Captura de OpenStreetMap',
                        'url': 'https://www.openstreetmap.org/copyright', 'sha256': digest(recreation_path),
                        'licencia': 'ODbL · © colaboradores de OpenStreetMap'})
    if lines is not None:
        sources.append({'capa': 'colectivos', 'titulo': 'Recorridos de colectivos (GTFS)', 'archivo': gtfs_zip.name,
                        'periodo': colectivos_gtfs.PERIODO, 'url': colectivos_gtfs.FUENTE,
                        'sha256': digest(gtfs_zip), 'licencia': 'CC-BY 2.5 AR · Buenos Aires Data'})
    for survey, path_ in ramp_files.items():
        sources.append({'capa': 'rampas', 'titulo': f'Rampas de accesibilidad · relevamiento {survey}',
                        'archivo': path_.name, 'url': CDN + RAMPAS_CDN + path_.name,
                        'periodo': f'Registro de obras {survey}; no es un inventario de la ciudad',
                        'sha256': digest(path_), 'licencia': 'CC-BY 2.5 AR · Buenos Aires Data'})
    for layer, path_ in mobility.items():
        file, url, title, period = MOVILIDAD[layer]
        sources.append({'capa': layer, 'titulo': title, 'archivo': file, 'periodo': period, 'url': CDN + url,
                        'sha256': digest(path_), 'licencia': 'CC-BY 2.5 AR · Buenos Aires Data'})
    if food is not None:
        combined = sha256(b''.join((osm_dir / f'{n}.json').read_bytes() for n in GASTRONOMIA)).hexdigest()
        sources.append({'capa': 'gastronomia', 'titulo': 'Restaurantes, cafés y bares',
                        'archivo': ', '.join(f'{n}.json' for n in GASTRONOMIA),
                        'periodo': f'Captura del {capture}' if capture else 'Captura de OpenStreetMap',
                        'url': 'https://www.openstreetmap.org/copyright', 'sha256': combined,
                        'licencia': 'ODbL · © colaboradores de OpenStreetMap'})
    write = lambda name, data: (target / name).write_text(json.dumps(data, ensure_ascii=False) + '\n', encoding='utf-8')
    write('barrios.geojson', {'type': 'FeatureCollection', 'features': barrio_features})
    write('verdes.geojson', {'type': 'FeatureCollection', 'features': greens})
    write('riesgo_hidrico.geojson', {'type': 'FeatureCollection', 'features': risk_features})
    write('puntos.json', points)
    write('ruido.json', {'celda_m': CELL_M, 'umbral_dba': LOUD_DBA, 'colores': noise_colors, **noise})
    write('resumen.json', summary)
    if lanes is not None:
        write('ciclovias.geojson', {'type': 'FeatureCollection', 'features': lanes})
    elif (target / 'ciclovias.geojson').exists():
        (target / 'ciclovias.geojson').unlink()
    if lines is not None:
        write('colectivos.json', lines)
    elif (target / 'colectivos.json').exists():
        (target / 'colectivos.json').unlink()
    write('fuentes.json', {'generado': (downloaded or date.today()).isoformat(), 'fuentes': sources})
    return summary


def load(folder):
    """Carga las capas procesadas; devuelve None si todavía no se generaron."""
    folder = Path(folder)
    files = ('barrios.geojson', 'verdes.geojson', 'riesgo_hidrico.geojson', 'puntos.json', 'ruido.json',
             'resumen.json', 'fuentes.json')
    if not all((folder / name).exists() for name in files):
        return None
    data = {name.split('.')[0]: read(folder / name) for name in files}
    if (folder / 'colectivos.json').exists():
        data['colectivos'] = read(folder / 'colectivos.json')
    if (folder / 'ciclovias.geojson').exists():
        data['ciclovias'] = read(folder / 'ciclovias.geojson')
    return data


def percent(value):
    return None if value is None else round(value * 100)


def comparison_columns(summary, preferences, level='primario'):
    """Columnas descriptivas para la tabla de barrios. No combina capas en un puntaje."""
    if summary is None:
        return {}
    row = {}
    if 'Subte' in preferences:
        row['Líneas de subte'] = ' · '.join(summary['subte_lineas']) or '—'
        row['Estaciones de subte'] = summary['subte_estaciones']
    if 'Plazas y parques' in preferences:
        row['Plazas y parques'] = summary['verdes_cantidad']
        row['Superficie verde (ha)'] = summary['verdes_ha']
    if 'Escuelas' in preferences:
        counts = summary['escuelas'].get(level, {})
        row[f'Escuelas de nivel {level}'] = sum(counts.values())
        row[f'De gestión estatal ({level})'] = counts.get('Estatal', 0)
    if 'Salud' in preferences:
        row['CeSAC'] = summary['cesac']
        row['Hospitales'] = summary['hospitales']
    if 'Ruido' in preferences:
        for period, label in (('diurno', 'de día'), ('nocturno', 'de noche')):
            row[f"Ruido ≥{LOUD_DBA[period]} dBA {label} (% de celdas relevadas)"] = percent(
                summary['ruido'][period]['alto'])
    if 'Riesgo hídrico' in preferences:
        row['Superficie en área de riesgo hídrico (%)'] = percent(summary['riesgo_hidrico'])
    return row


def bbox_of(feature_collection, name, margin_m=800):
    """Rectángulo del barrio con un margen, para centrar el mapa y recortar capas pesadas."""
    coords = [point for f in feature_collection['features'] if f['properties']['barrio'] == name
              for polygon in f['geometry']['coordinates'] for point in polygon[0]]
    if not coords:
        return None
    lons, lats = [c[0] for c in coords], [c[1] for c in coords]
    dlat = margin_m / 111_320
    dlon = margin_m / (111_320 * math.cos(math.radians(sum(lats) / len(lats))))
    return min(lons) - dlon, min(lats) - dlat, max(lons) + dlon, max(lats) + dlat


def in_bbox(lon, lat, bbox):
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


def features_in(collection, bbox):
    """Polígonos (por su anillo exterior) o líneas con algún vértice dentro del rectángulo."""
    def touches(feature):
        geometry = feature['geometry']
        vertices = (geometry['coordinates'] if geometry['type'] == 'LineString'
                    else (v for polygon in geometry['coordinates'] for v in polygon[0]))
        return any(in_bbox(x, y, bbox) for x, y, *_ in vertices)
    return {'type': 'FeatureCollection', 'features': [f for f in collection['features'] if touches(f)]}


def crime_cells(csv_path, period, kind=None, bbox=None, cell_m=200):
    """Hechos registrados del Mapa del Delito por celda, para un mes (AAAA-MM) y un tipo opcional."""
    totals, kinds = defaultdict(int), Counter()
    dlat = cell_m / 111_320
    dlon = cell_m / (111_320 * math.cos(math.radians(-34.62)))
    with Path(csv_path).open(encoding='utf-8-sig', newline='') as file:
        for row in csv.DictReader(file):
            row = {key(k): v for k, v in row.items() if k}
            if not (row.get('fecha') or '').startswith(period):
                continue
            try:
                lat, lon = float(row['latitud']), float(row['longitud'])
                count = int(float(row.get('cantidad') or row.get('cantidad_registrada') or 1))
            except (KeyError, TypeError, ValueError):
                continue
            if not (-34.75 < lat < -34.5 and -58.56 < lon < -58.32):
                continue
            if bbox and not in_bbox(lon, lat, bbox):
                continue
            row_kind = row.get('tipo') or row.get('tipo_delito') or 'Sin dato'
            kinds[row_kind] += count
            if kind and row_kind != kind:
                continue
            cell = (math.floor(lon / dlon), math.floor(lat / dlat))
            totals[cell] += count
    cells = [{'lon': round((cx + 0.5) * dlon, DECIMALS), 'lat': round((cy + 0.5) * dlat, DECIMALS), 'hechos': n}
             for (cx, cy), n in totals.items()]
    return cells, dict(kinds)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--poi', type=Path, default=ROOT / 'data/raw/badata-poi')
    parser.add_argument('--entorno', type=Path, default=ROOT / 'data/raw/badata-entorno')
    parser.add_argument('--destino', type=Path, default=ROOT / 'data/processed/entorno')
    parser.add_argument('--osm', type=Path, default=None,
                        help='Captura de OpenStreetMap para gastronomía (por defecto, la osm-AAAAMMDD más reciente).')
    parser.add_argument('--sin-osm', action='store_true', help='No sumar la gastronomía de OpenStreetMap.')
    args = parser.parse_args()
    raw = ROOT / 'data/raw'
    osm_dir = None if args.sin_osm else (args.osm or latest_osm(raw))
    gtfs_dir = colectivos_gtfs.latest(raw)
    summary = convert(args.poi, args.entorno, args.destino, osm_dir=osm_dir, gyms_path=latest_gyms(raw),
                      gtfs_zip=gtfs_dir / colectivos_gtfs.ARCHIVO if gtfs_dir else None,
                      recreation_path=latest_recreation(raw))
    with_food = any('gastronomia' in s for s in summary.values())
    print(json.dumps({'barrios': len(summary), 'destino': str(args.destino),
                      'gastronomia': str(osm_dir) if with_food else None}, ensure_ascii=False))


if __name__ == '__main__':
    main()
