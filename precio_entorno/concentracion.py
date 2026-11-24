"""Contexto espacial de robos y hurtos; nunca estima riesgo individual.

Radios geodésicos acumulativos sobre el pin publicado y grilla fija de 200 m.
La persistencia es una regla exploratoria reproducible, no un test estadístico.
"""

import math
import os
import pickle
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from . import importing
from .importing import BARRIOS, crime_date, csv_rows, key, number, usable_pin, value

RADIOS = (250, 500, 1000)
CELL_M = 200
DLAT = CELL_M / 111_320
DLON = CELL_M / (111_320 * math.cos(math.radians(-34.62)))
SOURCE_URL = 'https://data.buenosaires.gob.ar/dataset/delitos'
REVISION_URL = ('https://data.buenosaires.gob.ar/ar/dataset/6976d312-54e9-4398-b721-1504aedcce89/'
                'resource/66c0f0f6-e682-403d-abbe-47227d1966fe')
LIMITACIONES = [
    'La cantidad de delitos registrados no equivale a la probabilidad individual de victimización. '
    'Más peatones y actividad pueden concentrar más eventos; no hay un denominador de exposición.',
    'Existe subregistro y diferencias de denuncia y registro entre zonas y años.',
    'Los pines de hechos pueden ser puntos de referencia compartidos. Los radios de 250 m son '
    'especialmente sensibles a esa imprecisión y al pin aproximado del aviso.',
    'Robo incluye fuerza o violencia según la categoría de la fuente; estos datos no permiten '
    'aislar todos los robos con violencia contra personas. Hurto se informa por separado. '
    'Ambos incluyen los subtipos automotor.',
    'Día (06–19:59 h) y noche (20–05:59 h) duran 14 y 10 horas. Los conteos no se normalizan '
    'por duración ni por circulación; sin horario no se asigna a ninguna de esas franjas.',
    'Los radios son distancias en línea recta y se superponen: no se suman. Un círculo en el '
    'borde de CABA solo cuenta registros publicados de CABA.',
]
REVISION = ('La ficha oficial advierte que el informe ejecutivo de 2025 está en revisión por '
            'errores detectados (consulta: 09/11/2026). La advertencia se refiere al informe; '
            'las comparaciones del CSV se presentan como descriptivas y sujetas a revisión.')
PERSISTENCIA = ('Celda de 200 m con al menos 5 hechos y en el quintil superior de las celdas '
                'con registros de CABA para el mismo tipo y franja, en al menos 2 años con '
                'registros observados en los 12 meses. Umbral exploratorio, no significancia '
                'estadística ni evidencia de riesgo individual. Observar 12 meses no certifica integridad.')


@dataclass(frozen=True)
class Event:
    year: int
    month: int
    kind: str
    band: str
    count: int
    lon: float
    lat: float

    @property
    def cell(self):
        return math.floor(self.lon / DLON), math.floor(self.lat / DLAT)


def load_index(paths, cache_file=None):
    """CrimeIndex de los CSV, guardado en `cache_file` para no volver a leerlos en cada arranque.

    Leer los dos CSV anuales (37 MB) lleva unos 8 s; el índice guardado se carga en medio segundo. Se vuelve a
    armar si cambia un CSV (nombre, fecha o tamaño) o el código que los interpreta. El archivo es local y lo escribe
    esta misma función: no se comparte ni se versiona (data/local/ está fuera de Git).
    """
    paths = tuple(Path(p) for p in paths)
    signature = index_signature(paths)
    if cache_file is not None:
        try:
            with open(cache_file, 'rb') as stream:
                if pickle.load(stream) == signature:  # la firma va primero: no se lee el índice si no sirve
                    return pickle.load(stream)
        except (OSError, EOFError, pickle.UnpicklingError, AttributeError, ImportError, TypeError, ValueError):
            pass
    index = CrimeIndex(paths)
    if cache_file is not None:
        cache_file = Path(cache_file)
        partial = cache_file.with_name(cache_file.name + '.parcial')
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(partial, 'wb') as stream:
                pickle.dump(signature, stream, protocol=pickle.HIGHEST_PROTOCOL)
                pickle.dump(index, stream, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(partial, cache_file)
        except OSError:
            # Sin disco escribible (Vercel monta el paquete como solo lectura) el índice sirve igual desde memoria.
            # Borrar el parcial también puede fallar ahí: no tiene que tirar abajo el pedido.
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass
    return index


def index_signature(paths):
    """Firma del índice: el código que interpreta los CSV y el contenido de cada CSV.

    No usa la fecha de los archivos: al copiarlos al paquete de Vercel cambia, y el índice ya armado no se usaría
    nunca. El código se compara sin los finales de línea de Windows, que Git normaliza al armar el paquete.
    """
    code = sha256(b''.join(Path(m.__file__).read_bytes().replace(b'\r\n', b'\n')
                           for m in (sys.modules[__name__], importing))).hexdigest()
    return (code, tuple((Path(p).name, Path(p).stat().st_size, sha256(Path(p).read_bytes()).hexdigest()) for p in paths))


def source_paths(folder):
    """Solo CSV anuales oficiales locales; nunca incluye fixtures ni ejecuta descargas."""
    return tuple(sorted(Path(folder).glob('delitos_20[0-9][0-9].csv')))


def distance_m(lon, lat, other_lon, other_lat):
    a, b = math.radians(lat), math.radians(other_lat)
    h = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(
        math.radians(other_lon - lon) / 2) ** 2
    return 6_371_008.8 * 2 * math.asin(math.sqrt(min(1, h)))


def circle(lon, lat, radius):
    """Anillo geodésico WGS84 con cierre exacto."""
    a, b, d = math.radians(lat), math.radians(lon), radius / 6_371_008.8
    ring = []
    for step in range(72):
        bearing = math.radians(step * 5)
        y = math.asin(math.sin(a) * math.cos(d) + math.cos(a) * math.sin(d) * math.cos(bearing))
        x = b + math.atan2(math.sin(bearing) * math.sin(d) * math.cos(a),
                          math.cos(d) - math.sin(a) * math.sin(y))
        ring.append([math.degrees(x), math.degrees(y)])
    return {'type': 'Polygon', 'coordinates': [ring + [ring[0]]]}


def radius_summary(totals, year, radius, kind):
    """Hechos de un año, radio y tipo, separados por franja horaria."""
    values = {b: totals[year, radius, kind, b] for b in ('diurno', 'nocturno', 'sin_dato')}
    return {'anio': year, 'radio_m': radius, 'tipo': kind, **values, 'total': sum(values.values())}


class CrimeIndex:
    def __init__(self, paths):
        self.events, self.sources = [], []
        self.months = defaultdict(set)
        self.quality = Counter()
        seen = set()
        for path in paths:
            self._load(Path(path), seen)
        self.years = sorted(self.months)
        if not self.years:
            raise ValueError('No hay registros válidos con fecha y barrio en las fuentes locales.')
        self._grids = {}

    def _load(self, path, seen):
        """Agrega los robos y hurtos de un archivo del Mapa del Delito y anota la calidad de sus filas."""
        content = path.read_bytes()
        headers, rows = csv_rows(content)
        required = ({'id_mapa'}, {'fecha'}, {'barrio'}, {'tipo', 'tipo_delito'},
                    {'cantidad', 'cantidad_registrada'}, {'franja', 'franja_horaria'},
                    {'latitud', 'lat'}, {'longitud', 'long', 'lon'})
        if any(not names.intersection(headers) for names in required):
            raise ValueError(f'{path.name}: faltan columnas del Mapa del Delito.')
        self.sources.append({'archivo': path.name, 'sha256': sha256(content).hexdigest(),
                             'url': SOURCE_URL})
        names = {name: key(name) for name in rows[0]} if rows else {}
        for raw in rows:
            self.quality['filas_leidas'] += 1
            if None in raw:
                self.quality['descartadas'] += 1
                continue
            row = {names[k]: v for k, v in raw.items()}
            try:
                day = crime_date(value(row, 'fecha'))
                year, month = int(day[:4]), int(day[5:7])
                identifier = value(row, 'id_mapa')
                kind = value(row, 'tipo', 'tipo_delito')
                count = number(value(row, 'cantidad', 'cantidad_registrada'), whole=True)
                if not identifier or not kind or key(value(row, 'barrio')) not in BARRIOS:
                    raise ValueError
            except (ValueError, TypeError):
                self.quality['descartadas'] += 1
                continue
            identity = year, identifier.strip()
            if identity in seen:
                self.quality['duplicadas'] += 1
                continue
            seen.add(identity)
            self.months[year].add(month)
            if key(kind) not in ('robo', 'hurto'):
                continue
            try:
                lon = number(value(row, 'longitud', 'long', 'lon'), minimum=-58.54, maximum=-58.32)
                lat = number(value(row, 'latitud', 'lat'), minimum=-34.73, maximum=-34.52)
            except (ValueError, TypeError):
                self.quality['robos_hurtos_sin_pin'] += count
                continue
            try:
                hour = number(value(row, 'franja', 'franja_horaria'), maximum=23, whole=True)
                band = 'nocturno' if hour >= 20 or hour < 6 else 'diurno'
            except (ValueError, TypeError):
                band = 'sin_dato'
                self.quality['robos_hurtos_sin_horario'] += count
            self.events.append(Event(year, month, key(kind), band, count, lon, lat))

    def grids(self, kind='todos', band='todas'):
        signature = kind, band
        if signature not in self._grids:
            grids = {year: Counter() for year in self.years}
            for event in self.events:
                if (kind == 'todos' or event.kind == kind) and (band == 'todas' or event.band == band):
                    grids[event.year][event.cell] += event.count
            thresholds = {}
            for year, grid in grids.items():
                positive = sorted(n for n in grid.values() if n > 0)
                thresholds[year] = max(5, positive[max(0, math.ceil(len(positive) * .8) - 1)]) if positive else 5
            self._grids[signature] = grids, thresholds
        return self._grids[signature]

    def analyze(self, bbox, listing=None, radius=500, kind='todos', band='todas', year=None):
        if radius not in RADIOS or kind not in ('todos', 'robo', 'hurto') or band not in (
                'todas', 'diurno', 'nocturno', 'sin_dato'):
            raise ValueError('Radio, tipo o franja inválidos.')
        if year is not None and year not in self.years:
            raise ValueError('El año no está disponible en las fuentes locales.')
        pin = listing is not None and usable_pin(listing)
        if listing is not None and not pin:
            return {'disponible': False, 'motivo': 'Este aviso no tiene un pin con precisión informada de hasta 100 m.'}
        grids, thresholds = self.grids(kind, band)
        complete = [y for y in self.years if len(self.months[y]) == 12]
        universe = set().union(*(grid.keys() for grid in grids.values()))
        cells = []
        for cell in sorted(universe):
            lon, lat = (cell[0] + .5) * DLON, (cell[1] + .5) * DLAT
            if pin:
                # Mantiene celdas que tocan el círculo; los conteos exactos se calculan abajo.
                if distance_m(listing['longitude'], listing['latitude'], lon, lat) > radius + CELL_M / math.sqrt(2):
                    continue
            elif not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
                continue
            counts = {y: grids[y].get(cell, 0) for y in self.years}
            high_years = [y for y in complete if counts[y] >= thresholds[y]]
            cells.append({'lon': lon, 'lat': lat, 'hechos': counts.get(year, 0) if year else sum(counts.values()),
                          'por_anio': counts, 'anios_altos': high_years,
                          'persistente': len(high_years) >= 2})
        summaries = []
        if pin:
            totals = Counter()
            for event in self.events:
                distance = distance_m(listing['longitude'], listing['latitude'], event.lon, event.lat)
                totals.update({(event.year, r, event.kind, event.band): event.count for r in RADIOS if distance <= r})
            combinations = [(y, r, k) for y in self.years for r in RADIOS for k in ('robo', 'hurto')]
            summaries = [radius_summary(totals, y, r, k) for y, r, k in combinations]
        return {'disponible': True, 'anios': self.years, 'anio': year, 'radio_m': radius,
                'tipo': kind, 'franja': band, 'celda_m': CELL_M, 'fuentes': self.sources,
                'unidad': 'Hechos registrados; celdas de 200 m y radios acumulativos en línea recta.',
                'cobertura': [{'anio': y, 'meses_observados': sorted(self.months[y]),
                               'doce_meses_observados': y in complete} for y in self.years],
                'calidad': dict(self.quality), 'limitaciones': LIMITACIONES,
                'revision_2025': REVISION if 2025 in self.years else None, 'revision_url': REVISION_URL,
                'persistencia': {'definicion': PERSISTENCIA, 'anios_comparables': complete,
                                 'umbrales': thresholds, 'disponible': len(complete) >= 2},
                'inmueble': {'id': listing['id'], 'lon': listing['longitude'], 'lat': listing['latitude'],
                             'precision_m': listing['location_accuracy_m']} if pin else None,
                'resumen_radios': summaries, 'celdas': cells}
