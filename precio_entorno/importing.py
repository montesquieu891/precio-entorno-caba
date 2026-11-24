import csv
import io
import json
import math
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha256
from urllib.parse import urlsplit

from precio_entorno.descripcion import TRAITS


def key(value):
    plain = unicodedata.normalize('NFKD', str(value))
    return ''.join(c for c in plain if not unicodedata.combining(c)).strip().lower().replace('-', '_').replace(' ', '_')


BARRIOS = {key(name): name for name in (
    'Agronomía|Almagro|Balvanera|Barracas|Belgrano|Boedo|Caballito|Chacarita|Coghlan|'
    'Colegiales|Constitución|Flores|Floresta|La Boca|La Paternal|Liniers|Mataderos|'
    'Monte Castro|Montserrat|Nueva Pompeya|Núñez|Palermo|Parque Avellaneda|Parque Chacabuco|'
    'Parque Chas|Parque Patricios|Puerto Madero|Recoleta|Retiro|Saavedra|San Cristóbal|'
    'San Nicolás|San Telmo|Vélez Sarsfield|Versalles|Villa Crespo|Villa del Parque|'
    'Villa Devoto|Villa General Mitre|Villa Lugano|Villa Luro|Villa Ortúzar|Villa Pueyrredón|'
    'Villa Real|Villa Riachuelo|Villa Santa Rita|Villa Soldati|Villa Urquiza'
).split('|')}
BARRIOS.update({
    'boca': 'La Boca', 'paternal': 'La Paternal', 'monserrat': 'Montserrat',
    'villa_gral._mitre': 'Villa General Mitre',
})

# Rangos plausibles para departamentos en venta en CABA. Un separador de miles
# leído como decimal ("105.000" -> 105) queda fuera de rango y se descarta.
PRICE_USD = (10_000, 10_000_000)
COVERED_AREA_M2 = (10, 2_000)
TOTAL_AREA_M2 = (10, 10_000)
ROOMS = (1, 20)
PRICE_PER_M2_USD = (200, 20_000)

# Alquileres: precio mensual publicado, en pesos o en dólares, sin conversión.
OPERATIONS = ('venta', 'alquiler')
USD_ALIASES = {'USD': 'USD', 'U$S': 'USD', 'US$': 'USD'}
CURRENCIES = {
    'venta': USD_ALIASES,
    'alquiler': {**USD_ALIASES, 'ARS': 'ARS', '$': 'ARS', 'AR$': 'ARS', 'ARS$': 'ARS', 'PESOS': 'ARS'},
}
PRICE_RANGES = {('venta', 'USD'): PRICE_USD, ('alquiler', 'ARS'): (50_000, 50_000_000),
                ('alquiler', 'USD'): (100, 30_000)}
# Datos opcionales del edificio y la unidad (hoy solo los publican algunas fuentes).
AGE_YEARS = (0, 200)
GARAGES = (0, 10)
FLOOR = (0, 80)
# Estado de la propiedad, con las etiquetas que usan las fuentes llevadas a una sola escala.
CONDITIONS = {
    'a_estrenar': 'a estrenar', 'nuevo': 'a estrenar', 'en_construccion': 'en construcción',
    'en_pozo': 'en construcción', 'de_pozo': 'en construcción',
    'excelente': 'excelente', 'muy_bueno': 'muy bueno', 'bueno': 'bueno', 'regular': 'regular',
    'reciclado': 'reciclado', 'a_reciclar': 'a reciclar', 'a_refaccionar': 'a reciclar',
}
# Rasgos leídos de la descripción: 1 lo menciona, 0 no lo menciona.
FLAGS = {'1': 1, '0': 0, 'true': 1, 'false': 0, 'si': 1, 'no': 0}


def flag(raw):
    if isinstance(raw, (bool, int, float)) and raw in (0, 1):
        return int(raw)
    return FLAGS[key(str(raw))]


PRICE_PER_M2_RANGES = {('venta', 'USD'): PRICE_PER_M2_USD, ('alquiler', 'ARS'): (1_000, 2_000_000),
                       ('alquiler', 'USD'): (1, 1_000)}


@dataclass
class Report:
    read: int = 0
    added: int = 0
    duplicates: int = 0
    alerts: int = 0
    discarded: int = 0
    price_changes: int = 0   # Avisos ya conocidos cuyo precio publicado cambió.
    reactivated: int = 0     # Avisos dados de baja que volvieron a publicarse.
    missing: Counter = field(default_factory=Counter)
    invalid: Counter = field(default_factory=Counter)


def csv_rows(content):
    try:
        data = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        data = content.decode('cp1252')
    try:
        dialect = csv.Sniffer().sniff(data.splitlines()[0], delimiters=',;\t')
        reader = csv.DictReader(io.StringIO(data, newline=''), dialect=dialect, strict=True)
        headers = [key(name) for name in reader.fieldnames]
        if len(set(headers)) != len(headers):
            raise ValueError('El CSV tiene encabezados duplicados.')
        return headers, list(reader)
    except (IndexError, csv.Error) as error:
        raise ValueError('El CSV está vacío o tiene un formato inválido.') from error


def value(row, *names):
    for name in names:
        item = row.get(name)
        if item is not None and str(item).strip().casefold() not in ('', 'null'):
            return item
    return None


def number(raw, *, minimum=0, maximum=1e12, whole=False):
    if isinstance(raw, bool):
        raise ValueError
    parsed = float(str(raw).strip().replace(',', '.'))
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise ValueError
    if whole:
        if not parsed.is_integer():
            raise ValueError
        return int(parsed)
    return parsed


def identifier(raw):
    if type(raw) not in (str, int) or not str(raw).strip():
        raise ValueError
    return str(raw).strip()


def web_url(raw):
    url = str(raw).strip()
    parts = urlsplit(url)
    if (parts.scheme not in ('https', 'http') or not parts.hostname
            or parts.username is not None or any(c.isspace() for c in url)):
        raise ValueError
    return url


def field_value(report, name, raw, parse):
    if raw is None:
        report.missing[name] += 1
        return None
    try:
        return parse(raw)
    except (ValueError, TypeError, KeyError, OverflowError):
        report.invalid[name] += 1
        return None


def import_listings(store, content, filename, source, operation='venta'):
    source = source.strip().casefold()
    listings, report = parse_listings(content, filename, source, operation)
    stats = {}
    report.added, report.alerts = store.ingest(listings, source=source, stats=stats)
    report.price_changes, report.reactivated = stats['cambios_de_precio'], stats['reactivados']
    report.duplicates = len(listings) - report.added
    return report


def parse_listings(content, filename, source, operation='venta'):
    """Valida un archivo del catálogo y devuelve todas las observaciones válidas.

    Venta: precio en USD. Alquiler: precio mensual en pesos o en dólares, con
    rangos propios y expensas opcionales. No descarta capturas repetidas del
    mismo aviso: eso lo decide quien guarda.
    """
    source = source.strip().casefold()
    if not source:
        raise ValueError('Identificá el catálogo autorizado.')
    if operation not in OPERATIONS:
        raise ValueError(f'Operación desconocida: {operation}.')
    if filename.lower().endswith('.json'):
        rows = json.loads(content.decode('utf-8-sig'))
        if isinstance(rows, dict):
            rows = rows.get('listings')
        if not isinstance(rows, list):
            raise ValueError('El JSON debe contener una lista de avisos.')
    elif filename.lower().endswith('.csv'):
        _, rows = csv_rows(content)
    else:
        raise ValueError('Elegí un archivo CSV o JSON.')

    report = Report(read=len(rows))
    listings = []
    for raw in rows:
        if not isinstance(raw, dict) or None in raw:
            report.invalid['fila'] += 1
            report.discarded += 1
            continue
        row = {key(name): item for name, item in raw.items()}

        def get(name, parse, *aliases):
            return field_value(report, name, value(row, name, *aliases), parse)

        currency = get('currency', lambda x: CURRENCIES[operation][str(x).strip().upper()], 'moneda')
        price = get('price', lambda x: number(x, minimum=0.01), 'precio')
        # Sin moneda válida, la venta se sigue controlando contra el rango en USD.
        price_range = PRICE_RANGES.get((operation, currency or ('USD' if operation == 'venta' else None)))
        if price is not None and price_range and not price_range[0] <= price <= price_range[1]:
            report.invalid['price'] += 1
            price = None
        listing = {
            'id': get('listing_id', identifier, 'id'),
            'url': get('url', web_url, 'enlace'),
            'captured_at': get('captured_at', lambda x: datetime.fromisoformat(str(x)).isoformat(), 'fecha_captura'),
            'price': price,
            'currency': currency,
            'covered_area': get('covered_area_m2', lambda x: number(
                x, minimum=COVERED_AREA_M2[0], maximum=COVERED_AREA_M2[1]), 'covered_area', 'superficie_cubierta'),
            'rooms': get('rooms', lambda x: number(x, minimum=ROOMS[0], maximum=ROOMS[1], whole=True), 'ambientes'),
            'neighborhood': get('neighborhood', lambda x: BARRIOS[key(x)], 'barrio'),
        }
        valid = all(item is not None for item in listing.values())
        per_m2 = PRICE_PER_M2_RANGES.get((operation, currency))
        if valid and not per_m2[0] <= listing['price'] / listing['covered_area'] <= per_m2[1]:
            report.invalid['precio_m2'] += 1
            valid = False
        # Expensas mensuales en pesos; el rango descarta un "95.000" leído como 95.
        listing['expenses'] = get('expenses', lambda x: number(x, minimum=1_000, maximum=10_000_000), 'expensas')
        listing['total_area_m2'] = get('total_area_m2', lambda x: number(
            x, minimum=TOTAL_AREA_M2[0], maximum=TOTAL_AREA_M2[1]), 'superficie_total')
        listing['latitude'] = get('latitude', lambda x: number(x, minimum=-34.73, maximum=-34.52), 'latitud', 'lat')
        listing['longitude'] = get('longitude', lambda x: number(x, minimum=-58.54, maximum=-58.32), 'longitud', 'lon')
        listing['location_accuracy_m'] = get('location_accuracy_m', lambda x: number(x, minimum=0.01), 'precision_m')
        listing['age_years'] = get('age_years', lambda x: number(
            x, minimum=AGE_YEARS[0], maximum=AGE_YEARS[1], whole=True), 'antiguedad')
        listing['condition'] = get('condition', lambda x: CONDITIONS[key(x)], 'estado')
        listing['garages'] = get('garages', lambda x: number(
            x, minimum=GARAGES[0], maximum=GARAGES[1], whole=True), 'cocheras')
        listing['floor'] = get('floor', lambda x: number(x, minimum=FLOOR[0], maximum=FLOOR[1], whole=True), 'piso')
        listing.update({column: get(column, flag, spanish) for column, (spanish, _) in TRAITS.items()})
        if listing['total_area_m2'] is not None and listing['covered_area'] is not None:
            if listing['total_area_m2'] < listing['covered_area']:
                report.invalid['total_area_m2'] += 1
                listing['total_area_m2'] = None
        declared_source = value(row, 'source', 'fuente')
        if declared_source is not None and str(declared_source).strip().casefold() != source:
            raise ValueError('El archivo declara un catálogo distinto del indicado.')
        if valid:
            listings.append(listing)
        else:
            report.discarded += 1
    return listings, report


def usable_pin(item):
    accuracy = item.get('location_accuracy_m')
    return (item.get('latitude') is not None and item.get('longitude') is not None
            and accuracy is not None and accuracy <= 100)


def crime_date(raw):
    text = str(raw).strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return datetime.strptime(text, '%d/%m/%Y').date().isoformat()


def import_crimes(store, content, filename):
    headers, rows = csv_rows(content)
    required = [
        {'id_mapa'}, {'fecha'}, {'barrio'}, {'tipo_delito', 'tipo'},
        {'franja_horaria', 'franja'}, {'cantidad', 'cantidad_registrada'},
    ]
    if any(not names.intersection(headers) for names in required):
        raise ValueError('El CSV no tiene las columnas requeridas del Mapa del Delito.')

    report = Report(read=len(rows))
    events = {}
    for raw in rows:
        if None in raw:
            report.invalid['fila'] += 1
            report.discarded += 1
            continue
        row = {key(name): item for name, item in raw.items()}
        day = field_value(report, 'fecha', value(row, 'fecha'), crime_date)
        event_id = field_value(report, 'id_mapa', value(row, 'id_mapa'), identifier)
        barrio = field_value(report, 'barrio', value(row, 'barrio'), lambda x: BARRIOS[key(x)])
        kind = field_value(report, 'tipo', value(row, 'tipo_delito', 'tipo'), identifier)
        hour = field_value(report, 'franja', value(row, 'franja_horaria', 'franja'),
                           lambda x: number(x, maximum=23, whole=True))
        count = field_value(report, 'cantidad', value(row, 'cantidad', 'cantidad_registrada'),
                            lambda x: number(x, whole=True))
        # Una franja faltante o inválida se muestra como desconocida.
        if None in (day, event_id, barrio, kind, count):
            report.discarded += 1
            continue
        event_key = (day[:4], event_id)
        if event_key in events:
            report.duplicates += 1
            continue
        events[event_key] = (day, barrio, kind, hour, count, event_id)

    if events:
        changed = store.replace_crimes(events.values(), filename, sha256(content).hexdigest())
        if changed:
            report.added = len(events)
        else:
            report.duplicates += len(events)
    return report

