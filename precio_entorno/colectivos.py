"""Líneas de colectivo que pasan por cada barrio y su recorrido, a partir del GTFS oficial.

Fuente: «Colectivos: GTFS» de Buenos Aires Data (licencia CC-BY 2.5 AR), guardado en
`data/raw/colectivos-gtfs-AAAAMMDD/colectivos-gtfs.zip`. El feed cubre el AMBA; se conservan las
líneas con algún tramo dentro de CABA. Su calendario corresponde a septiembre-diciembre de 2019,
así que los recorridos pueden haber cambiado: la interfaz pide confirmarlos con la empresa o la app
oficial. Una línea «pasa» por un barrio si algún punto de su trazado, densificado cada 50 m, cae
dentro del polígono oficial. No se usan horarios ni frecuencias.
"""

import csv
import io
import math
import re
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np

FUENTE = 'https://data.buenosaires.gob.ar/dataset/colectivos-gtfs'
ARCHIVO = 'colectivos-gtfs.zip'
PERIODO = 'Calendario del feed: septiembre a diciembre de 2019; confirmá el recorrido vigente'
STEP_M = 50
# Tolerancia de simplificación del trazado para el mapa (~8 m).
TOLERANCE_DEG = 0.00008
DECIMALS = 5


def latest(raw_dir):
    """Carpeta más reciente `colectivos-gtfs-*` con el feed, o None."""
    folders = sorted(p for p in Path(raw_dir).glob('colectivos-gtfs-*') if (p / ARCHIVO).is_file())
    return folders[-1] if folders else None


def line_name(short_name):
    """`60C` → `60`, `505R3` → `505`; las líneas sin número conservan su nombre (`AZUL1`)."""
    match = re.match(r'\d+', short_name)
    return str(int(match.group())) if match else short_name


def line_order(name):
    return (0, int(name), '') if name.isdigit() else (1, 0, name)


def rows(archive, name):
    with archive.open(name) as handle:
        yield from csv.DictReader(io.TextIOWrapper(handle, 'utf-8-sig'))


def densify(coords, step_m=STEP_M):
    """Agrega puntos intermedios para no saltear barrios en tramos rectos largos."""
    out = [coords[0]]
    for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
        dx = (x1 - x0) * 111_320 * math.cos(math.radians(y0))
        dy = (y1 - y0) * 111_320
        parts = max(1, int(math.hypot(dx, dy) // step_m))
        out.extend((x0 + (x1 - x0) * k / parts, y0 + (y1 - y0) * k / parts) for k in range(1, parts + 1))
    return out


def simplify(coords, tolerance=TOLERANCE_DEG):
    """Douglas-Peucker iterativo."""
    points = np.asarray(coords, float)
    if len(points) < 3:
        return points.tolist()
    keep = np.zeros(len(points), bool)
    keep[[0, -1]] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        if end - start < 2:
            continue
        a, b = points[start], points[end]
        segment = points[start + 1:end]
        ab = b - a
        norm = np.hypot(*ab)
        if norm == 0:
            distances = np.hypot(*(segment - a).T)
        else:
            distances = np.abs(ab[0] * (segment[:, 1] - a[1]) - ab[1] * (segment[:, 0] - a[0])) / norm
        index = int(np.argmax(distances))
        if distances[index] > tolerance:
            middle = start + 1 + index
            keep[middle] = True
            stack += [(start, middle), (middle, end)]
    return points[keep].tolist()


def build(zip_path, barrios):
    """Devuelve {línea: {barrios, ramales, recorrido}} para las líneas que pasan por CABA.

    `barrios` es un `entorno.Barrios`: se usa su `bbox` y `of(points)`.
    """
    archive = zipfile.ZipFile(zip_path)
    routes = {r['route_id']: r for r in rows(archive, 'routes.txt')}
    shapes_of = defaultdict(set)
    for trip in rows(archive, 'trips.txt'):
        if trip['route_id'] in routes and trip.get('shape_id'):
            shapes_of[trip['route_id']].add(trip['shape_id'])
    points = defaultdict(list)
    for row in rows(archive, 'shapes.txt'):
        points[row['shape_id']].append((int(row['shape_pt_sequence']),
                                        float(row['shape_pt_lon']), float(row['shape_pt_lat'])))
    west, south, east, north = barrios.bbox
    shape_coords, shape_cells = {}, {}
    for shape_id, sequence in points.items():
        coords = [(lon, lat) for _, lon, lat in sorted(sequence)]
        if len(coords) < 2:
            continue
        # Puntos densificados dentro del rectángulo de CABA, redondeados a ~10 m: muchas líneas
        # comparten calles, así que cada punto se ubica en un barrio una sola vez.
        cells = {(round(x, 4), round(y, 4)) for x, y in densify(coords)
                 if west <= x <= east and south <= y <= north}
        if cells:
            shape_coords[shape_id] = coords
            shape_cells[shape_id] = cells
    unique = sorted(set().union(*shape_cells.values())) if shape_cells else []
    located = dict(zip(unique, barrios.of(unique))) if unique else {}
    shape_barrios = {}
    for shape_id, cells in shape_cells.items():
        crossed = {located[cell] for cell in cells if located[cell]}
        if crossed:
            shape_barrios[shape_id] = crossed

    lines = {}
    for route_id, route in routes.items():
        mine = [s for s in shapes_of[route_id] if s in shape_barrios]
        if not mine:
            continue
        name = line_name(route['route_short_name'])
        line = lines.setdefault(name, {'barrios': set(), 'ramales': set(), 'shapes': set()})
        line['ramales'].add(route['route_desc'].strip() or route['route_short_name'])
        line['shapes'].update(mine)
        line['barrios'].update(*(shape_barrios[shape_id] for shape_id in mine))

    result = {}
    for name in sorted(lines, key=line_order):
        line = lines[name]
        paths = distinct_paths(shape_coords[shape_id] for shape_id in sorted(line['shapes']))
        result[name] = {'barrios': sorted(line['barrios']), 'ramales': sorted(line['ramales']), 'recorrido': paths}
    return result


def distinct_paths(coords_list):
    """Trazados simplificados y redondeados, sin repetir los que tienen mismos extremos y largo."""
    paths, seen = [], set()
    for coords in coords_list:
        path = [[round(x, DECIMALS), round(y, DECIMALS)] for x, y in simplify(coords)]
        signature = (tuple(path[0]), tuple(path[-1]), len(path))
        if signature not in seen:
            seen.add(signature)
            paths.append(path)
    return paths


# Paleta para distinguir líneas en el mapa; el color de cada línea es estable entre barrios.
COLORS = ('#D81B60', '#1E88E5', '#F4511E', '#3949AB', '#00897B', '#8E24AA', '#C0CA33', '#6D4C41',
          '#00ACC1', '#E53935', '#5E35B1', '#43A047')


def color(name):
    return COLORS[sum(map(ord, name)) % len(COLORS)]


def clip(paths, bbox):
    """Tramos de cada trazado que tocan el rectángulo.

    Se conservan los segmentos cuyo rectángulo se superpone con el del barrio, así que una avenida
    recta que lo cruza sin vértices adentro también aparece. Los segmentos contiguos forman un tramo.
    """
    return [piece for path in paths for piece in pieces_in(path, bbox)]


def pieces_in(path, bbox):
    """Tramos de un trazado formados por segmentos contiguos que tocan el rectángulo."""
    west, south, east, north = bbox
    out, piece = [], []
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        touches = (min(x0, x1) <= east and max(x0, x1) >= west
                   and min(y0, y1) <= north and max(y0, y1) >= south)
        if touches:
            if not piece:
                piece = [[x0, y0]]
            piece.append([x1, y1])
        elif piece:
            out.append(piece)
            piece = []
    if piece:
        out.append(piece)
    return out


def barrio_features(lines, barrio, bbox):
    """Una entidad por línea que pasa por el barrio, recortada al rectángulo del barrio."""
    features = []
    for name, line in lines.items():
        if barrio not in line['barrios']:
            continue
        pieces = clip(line['recorrido'], bbox)
        if pieces:
            features.append({'type': 'Feature', 'geometry': {'type': 'MultiLineString', 'coordinates': pieces},
                             'properties': {'linea': name, 'color': color(name),
                                            'tooltip': f'Línea {name} · Tocá para ver el recorrido completo'}})
    return features


def by_barrio(lines):
    """{barrio: [líneas ordenadas]} a partir del resultado de `build`."""
    out = defaultdict(list)
    pairs = [(barrio, name) for name, line in lines.items() for barrio in line['barrios']]
    for barrio, name in pairs:
        out[barrio].append(name)
    return {barrio: sorted(names, key=line_order) for barrio, names in out.items()}
