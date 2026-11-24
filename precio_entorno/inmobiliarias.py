"""Captura autorizada de avisos de inmobiliarias con Scrapling.

Cada inmobiliaria dio permiso para leer su sitio. El cliente es deliberadamente
educado: se identifica, respeta robots.txt, espera entre pedidos, no usa proxies ni
técnicas de sigilo y se detiene ante cualquier bloqueo o desafío. Solo se copian los
campos del contrato de datos; nunca datos de agentes, anunciantes ni propietarios.

Todas las inmobiliarias forman un único catálogo consolidado. El ID de cada aviso
lleva el prefijo de su inmobiliaria.
"""

import argparse
import gzip
import html as html_lib
import inspect
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from precio_entorno.descripcion import DESCRIPTION_FIELDS, traits
from precio_entorno.importing import BARRIOS, key
from precio_entorno.robots import Robots, disallow_all

ROOT = Path(__file__).resolve().parents[1]
CATALOG = 'inmobiliarias-autorizadas'
# Venta y alquiler son catálogos separados, con su propia base y sus propias alertas.
CATALOGS = {'venta': CATALOG, 'alquiler': 'inmobiliarias-alquiler'}
OPERATION_SETTINGS = {
    'venta': {'remax_landing': 'departamentos-en-venta-en-ciudad-de-buenos-aires', 'remax_op': 'sale',
              'c21_op': 'sell', 'mig_path': '1/2', 'word': 'VENTA'},
    'alquiler': {'remax_landing': 'departamentos-en-alquiler-en-ciudad-de-buenos-aires', 'remax_op': 'rent',
                 'c21_op': 'rent', 'mig_path': '2/0', 'word': 'ALQUILER'},
}
USER_AGENT = 'precio-entorno-caba/0.1 (proyecto academico; captura autorizada)'
DEFAULT_PAUSE_S = 3.0
BLOCK_STATUS = {401, 403, 407, 429, 503}
CHALLENGE_MARKERS = ('cf-chl', 'just a moment...', 'challenge-platform', 'captcha-delivery')
# Subzonas comerciales con un único barrio oficial. Las ambiguas (Congreso, Centro,
# Parque Centenario) no se asignan: el aviso se descarta y se informa.
SUBZONES = {
    'palermo_hollywood': 'Palermo', 'palermo_soho': 'Palermo', 'palermo_chico': 'Palermo',
    'palermo_viejo': 'Palermo', 'palermo_nuevo': 'Palermo', 'las_canitas': 'Palermo', 'botanico': 'Palermo',
    'belgrano_r': 'Belgrano', 'belgrano_c': 'Belgrano', 'belgrano_chico': 'Belgrano',
    'barrio_norte': 'Recoleta', 'abasto': 'Balvanera', 'once': 'Balvanera',
    'microcentro': 'San Nicolás', 'tribunales': 'San Nicolás', 'barrio_santa_rita': 'Villa Santa Rita',
    'caballito_norte': 'Caballito', 'caballito_sur': 'Caballito',
}


class Blocked(RuntimeError):
    """El sitio rechazó o desafió el acceso: la captura se detiene."""


def barrio(name):
    if not name:
        return None
    k = key(html_lib.unescape(str(name)))
    return BARRIOS.get(k) or SUBZONES.get(k)


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(str(value).replace(',', '.'))
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def local_number(text):
    """Número escrito a la argentina: '1.100.540' son miles; '37.49' o '52,5' son decimales."""
    text = text.strip()
    if re.fullmatch(r'\d{1,3}(\.\d{3})+', text):
        text = text.replace('.', '')
    return number(text)


def placeholder_price(value):
    """Precios de relleno como 888.888 o 999.999, usados en lugar de 'consultar'."""
    digits = str(int(value)) if value else ''
    return len(digits) >= 5 and len(set(digits)) == 1


def coordinate(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed != 0 else None


def record(agency, local_id, url, captured_at, operation='venta', **fields):
    """Arma un aviso con los campos permitidos del contrato y nada más."""
    if fields.get('price') is not None and placeholder_price(fields['price']):
        fields['price'] = None
    return {'listing_id': f'{agency}:{local_id}', 'source': CATALOGS[operation], 'agency': agency,
            'url': url, 'captured_at': captured_at, **{k: fields.get(k) for k in (
                'price', 'currency', 'covered_area_m2', 'total_area_m2', 'rooms',
                'neighborhood', 'latitude', 'longitude', 'expenses') + OPTIONAL_FIELDS}}


# Campos opcionales del edificio y la unidad, y rasgos leídos de la descripción. Solo los traen algunas fuentes.
OPTIONAL_FIELDS = ('age_years', 'condition', 'garages', 'floor') + DESCRIPTION_FIELDS


def age_from_year(year, captured_at):
    """Antigüedad en años al momento de la captura. Un año futuro (en construcción) es 0."""
    year = number(year)
    if not year or year < 1850:
        return None
    return max(0, int(captured_at[:4]) - int(year))


def floor_number(text):
    """Piso de la unidad: '9', '9°F' → 9; 'PB' o 'Planta baja' → 0. Lo demás queda sin dato."""
    text = str(text or '').strip()
    if re.match(r'(pb|planta\s*baja)\b', text, re.I):
        return 0
    m = re.match(r'(\d{1,2})(?!\d)', text)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- Cliente educado

class PoliteClient:
    def __init__(self, fetch=None, pause_s=DEFAULT_PAUSE_S, max_requests=2000, sleep=time.sleep):
        self._fetch = fetch or self._scrapling_fetch
        self.pause_s, self.max_requests, self._sleep = pause_s, max_requests, sleep
        self._last, self._robots = {}, {}
        self.log = Counter()

    @staticmethod
    def _scrapling_fetch(url, params=None):
        from scrapling.fetchers import Fetcher
        # Sin cabeceras de sigilo, sin suplantar la huella del navegador y sin proxies.
        response = Fetcher.get(url, params=params, stealthy_headers=False, impersonate=None,
                               headers={'User-Agent': USER_AGENT}, retries=1, timeout=30)
        body = response.body
        if isinstance(body, bytes) and body[:2] == b'\x1f\x8b':
            body = gzip.decompress(body)  # Sitemaps publicados como .xml.gz.
        return response.status, body.decode('utf-8', 'replace') if isinstance(body, bytes) else str(body)

    def _wait(self, host):
        elapsed = time.monotonic() - self._last.get(host, -1e9)
        if elapsed < self.pause_s:
            self._sleep(self.pause_s - elapsed)
        self._last[host] = time.monotonic()

    def allowed(self, url):
        parts = urlsplit(url)
        host = parts.netloc
        if host not in self._robots:
            self._wait(host)
            try:
                status, text = self._fetch(f'{parts.scheme}://{host}/robots.txt')
            except Exception:  # noqa: BLE001 - p. ej., bucle de redirecciones.
                # Como un 404: no hay robots.txt utilizable en ese host.
                status, text = 404, ''
                self.log[f'robots_no_disponible:{host}'] += 1
            self.log['pedidos'] += 1
            if status == 200 and not text.lstrip().lower().startswith('<'):
                parser = Robots(text, USER_AGENT)
            elif status in (401, 403):
                parser = disallow_all()
            else:
                parser = Robots()  # Sin robots.txt utilizable: se permite el acceso.
            self._robots[host] = parser
        return self._robots[host].allowed(url)

    def get(self, url, params=None):
        if self.log['pedidos'] >= self.max_requests:
            raise Blocked(f'Se alcanzó el tope de {self.max_requests} pedidos.')
        if not self.allowed(url):
            raise Blocked(f'robots.txt no permite {url}')
        self._wait(urlsplit(url).netloc)
        try:
            status, text = self._fetch(url, params)
        except Exception as error:  # noqa: BLE001 - errores de red de la librería HTTP.
            self.log['pedidos'] += 1
            raise RuntimeError(f'{url}: {type(error).__name__}') from None
        self.log['pedidos'] += 1
        self.log[f'http_{status}'] += 1
        lowered = text[:5000].lower()
        if status in BLOCK_STATUS or any(m in lowered for m in CHALLENGE_MARKERS):
            raise Blocked(f'{url} respondió HTTP {status} o un desafío. La captura se detiene.')
        if status != 200:
            raise RuntimeError(f'{url} respondió HTTP {status}.')
        return text


# ---------------------------------------------------------------- RE/MAX

REMAX_API = 'https://api-ar.redremax.com/remaxweb-ar/api/listings/findAllWithEntrepreneurships'
REMAX_DETAIL = 'https://api-ar.redremax.com/remaxweb-ar/api/listings/findBySlug/'
REMAX_LANDING = OPERATION_SETTINGS['venta']['remax_landing']


def remax_traits(client, url):
    """Rasgos de la descripción de un aviso de RE/MAX. El listado no la trae: se pide la ficha."""
    data = json.loads(client.get(REMAX_DETAIL + url.rstrip('/').rsplit('/', 1)[-1]))['data']
    if not isinstance(data, dict):
        raise KeyError('aviso sin ficha')  # Un aviso dado de baja devuelve `data: null`.
    return traits(data.get('title'), data.get('description'))


def parse_remax(payload, captured_at, operation='venta'):
    data = payload['data']
    out, skipped = [], Counter()
    for item in data['data']:
        if item.get('entrepreneurship') or (item.get('listingStatus') or {}).get('value') != 'active':
            skipped['no_activo_o_emprendimiento'] += 1
            continue
        if (item.get('operation') or {}).get('value') != OPERATION_SETTINGS[operation]['remax_op']:
            skipped['otra_operacion'] += 1
            continue
        expenses = number(item.get('expensesPrice'))
        if (item.get('expensesCurrency') or {}).get('value') != 'ARS':
            expenses = None  # Las expensas se informan solo en pesos.
        label = str(item.get('geoLabel') or '')
        parts = [p.strip() for p in label.split(',')]
        if 'Capital Federal' not in parts:
            skipped['fuera_de_caba'] += 1
            continue
        name = barrio(parts[0])
        if not name:
            skipped['barrio_ambiguo'] += 1
        coords = (item.get('location') or {}).get('coordinates') or [None, None]
        out.append(record(
            'remax', item.get('internalId') or item['id'], f"https://www.remax.com.ar/listings/{item['slug']}",
            captured_at, operation, price=item.get('price') if item.get('priceExposure') else None,
            currency=(item.get('currency') or {}).get('value'), covered_area_m2=number(item.get('dimensionCovered')),
            total_area_m2=number(item.get('dimensionTotalBuilt')), rooms=item.get('totalRooms'),
            neighborhood=name, latitude=coordinate(coords[1]), longitude=coordinate(coords[0]),
            expenses=expenses if operation == 'alquiler' else None))
    return out, skipped, data.get('totalPages', 0)


def scrape_remax(client, captured_at, max_listings, page_size=100, known=frozenset(), operation='venta',
                 sweep=None):
    listings, skipped, page = [], Counter(), 0
    landing = OPERATION_SETTINGS[operation]['remax_landing']
    while len(listings) < max_listings:
        params = {'page': page, 'pageSize': page_size, 'sort': '-createdAt', 'landingPath': landing}
        batch, why, pages = parse_remax(json.loads(client.get(REMAX_API, params)), captured_at, operation)
        listings += batch
        skipped.update(why)
        page += 1
        if page >= pages or not batch and not why:
            break
    if sweep is not None:
        # Completo si se leyeron todas las páginas sin cortar por el tope. Los avisos que Remax marca como no
        # activos se omiten, así que cuentan como no vistos.
        sweep['completo'] = bool(pages) and page >= pages and len(listings) <= max_listings
    listings = listings[:max_listings]
    for listing in listings:
        # Solo los avisos nuevos: pedir la ficha de todos sumaría un pedido por aviso en cada corrida.
        if listing['listing_id'] in known:
            continue
        try:
            listing.update(remax_traits(client, listing['url']))
        except Blocked:
            raise
        except (RuntimeError, ValueError, KeyError):
            skipped['sin_descripcion'] += 1
    return listings, skipped


# ---------------------------------------------------------------- Century 21

C21_SEARCH = 'https://century21.com.ar/search'
C21_PARAMS = {'loc': 'r|CABA||', 'op': 'sell', 'type': 'departamento'}
CABA_REGIONS = {'ciudad_autonoma_de_buenos_aires', 'capital_federal', 'caba'}


def rsc_text(page):
    """Une el payload de React Server Components embebido en el HTML."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', page, re.S)
    return ''.join(json.loads(f'"{c}"') for c in chunks)


def parse_century21(page, captured_at, operation='venta'):
    text = rsc_text(page)
    decoder, seen, out, skipped = json.JSONDecoder(), set(), [], Counter()
    for match in re.finditer(r'\{"property_id":', text):
        try:
            item, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        pid = str(item.get('property_id'))
        if pid in seen or 'covered_square_meters' not in item:
            continue  # Se omiten las tarjetas resumidas, como las de recomendados.
        seen.add(pid)
        if item.get('operation_type') != OPERATION_SETTINGS[operation]['c21_op'] \
                or item.get('prop_type') != 'departamento' \
                or item.get('status') != 'active':
            skipped['fuera_de_alcance'] += 1
            continue
        if key(item.get('addr_region')) not in CABA_REGIONS:
            skipped['fuera_de_caba'] += 1
            continue
        name = barrio(item.get('addr_neighborhood')) or barrio(item.get('addr_district'))
        if not name:
            skipped['barrio_ambiguo'] += 1
        covered = number(item.get('covered_square_meters'))
        total = number(item.get('land_square_meters'))
        out.append(record(
            'century21', pid, item.get('property_url') or f'https://century21.com.ar/propiedades/{pid}',
            captured_at, operation, price=None if item.get('price_hidden') else number(item.get('price')),
            currency=item.get('currency_id'), covered_area_m2=covered,
            total_area_m2=total if total and covered and total >= covered else None,
            rooms=item.get('rooms'), neighborhood=name,
            latitude=coordinate(item.get('geo_lat')), longitude=coordinate(item.get('geo_lon')),
            age_years=age_from_year(item.get('construction_year'), captured_at),
            condition=item.get('property_condition') or None,
            garages=item.get('garage') if isinstance(item.get('garage'), int) else None,
            floor=floor_number(item.get('addr_floor'))))
    count = re.search(r'"count":\s*(\d+)', text)
    return out, skipped, int(count.group(1)) if count else 0


def scrape_century21(client, captured_at, max_listings, known=frozenset(), operation='venta', sweep=None):
    listings, skipped, page, total = [], Counter(), 1, None
    params = dict(C21_PARAMS, op=OPERATION_SETTINGS[operation]['c21_op'])
    while len(listings) < max_listings:
        batch, why, count = parse_century21(client.get(C21_SEARCH, dict(params, page=page)), captured_at, operation)
        total = total or count
        listings += batch
        skipped.update(why)
        if not batch and not why or (page * 16 >= total):
            break
        page += 1
    if sweep is not None:
        sweep['completo'] = bool(total) and page * 16 >= total and len(listings) <= max_listings
    return listings[:max_listings], skipped


# ---------------------------------------------------------------- Migliorisi

MIG_BASE = 'https://www.migliorisi.com.ar'
# Segmentos de operación y moneda: 1/2 = venta en dólares, 2/0 = alquiler en cualquier moneda.
MIG_DESCRIPTION = re.compile(r'<div id="div-descripcion">(.*?)</div>', re.S)
MIG_SEARCH = MIG_BASE + '/busqueda-propiedades/a/0/0/0/0/0/{op}/99999999/0/0/0/0/0/{page}'


def clean(text):
    return re.sub(r'\s+', ' ', html_lib.unescape(re.sub(r'<[^>]+>', ' ', text))).strip()


def parse_migliorisi_list(page):
    """Devuelve (ruta, código, título) de cada tarjeta y la última página enlazada."""
    cards = {}
    for path, code in re.findall(r'href="(/propiedad/ver/([a-z]\d+)/[^"]+)"', page):
        cards.setdefault(code, path)
    titles = dict(re.findall(r'href="/propiedad/ver/([a-z]\d+)/[^"]+">\s*<div[^>]*>\s*<img[^>]*title="([^"]+)"', page))
    pages = [int(p) for p in re.findall(r'busqueda-propiedades/[^"]*/(\d+)"', page)]
    return [(path, code, html_lib.unescape(titles.get(code, ''))) for code, path in cards.items()], max(pages or [1])


MIG_ELEVATORS = re.compile(r'\bAscensores\s*:?\s*(\d+)', re.I)


def migliorisi_traits(page, title=''):
    """Rasgos del bloque de descripción de la ficha. Sin ese bloque quedan sin dato.

    La tabla de características de la ficha informa «Ascensores N»: con uno o más, gana sobre el texto. Un 0 no
    se toma como «sin ascensor», porque puede ser un campo que la inmobiliaria no completó.
    """
    description = MIG_DESCRIPTION.search(page)
    if not description:
        return {}
    found = traits(title, description.group(1))
    elevators = MIG_ELEVATORS.search(clean(MIG_DESCRIPTION.sub(' ', page)))
    if elevators and int(elevators.group(1)) > 0:
        found.update(elevator=1, stairs_only=0)
    return found


def parse_migliorisi_detail(page, path, code, title, captured_at, operation='venta'):
    text = clean(page)
    if not title:
        head = re.search(r'<title>([^<]+)</title>', page)
        title = html_lib.unescape(head.group(1)).split('|', 1)[-1].strip() if head else ''

    def field(label):
        m = re.search(label + r'\s*:?\s*([\d.,]+)\s*m2', text, re.I)
        return local_number(m.group(1)) if m else None

    parts = [p.strip() for p in title.split('.')]
    rooms = re.search(r'(\d+)\s*ambiente', title, re.I)
    price = re.search(r'Precio\s*(U\$S|USD|\$)\s*([\d.]+)', text)
    covered = field('Superficie Cubierta')
    extra = [v for v in (field('Superficie Descubierta'), field('Superficie semi cubierta')) if v]
    word = OPERATION_SETTINGS[operation]['word']
    upper = [p.upper() for p in parts]
    is_operation = word in upper
    name = barrio(parts[upper.index(word) + 1]) if is_operation and upper.index(word) + 1 < len(parts) else None
    expenses = re.search(r'Expensas\s*\$\s*([\d.]+)', text)
    age = re.search(r'Antig(?:u|ü)edad\s*:?\s*(?:(\d{1,3})\s*a(?:ñ|n)os?|(a\s*estrenar))', text, re.I)
    listing = record(
        'migliorisi', code, MIG_BASE + path, captured_at, operation,
        price=local_number(price.group(2)) if price else None,
        currency='USD' if price and price.group(1) in ('U$S', 'USD') else ('ARS' if price else None),
        covered_area_m2=covered, total_area_m2=covered + sum(extra) if covered and extra else covered,
        rooms=int(rooms.group(1)) if rooms else None, neighborhood=name,
        expenses=local_number(expenses.group(1)) if expenses and operation == 'alquiler' else None,
        age_years=(0 if age.group(2) else int(age.group(1))) if age else None,
        **migliorisi_traits(page, title))
    return listing, is_operation, title.upper().startswith('DEPARTAMENTO')


def scrape_migliorisi(client, captured_at, max_listings, known=frozenset(), operation='venta', sweep=None):
    """Recorre las `max_listings` fichas más recientes del listado. Solo pide el detalle de las que no están
    en `known`. Las conocidas cuentan dentro de la ventana: si no, cada corrida bajaría a avisos más viejos.
    Las conocidas no se devuelven, pero se anotan como vistas en `sweep`."""
    listings, skipped, page, last, examined, cut = [], Counter(), 1, 1, 0, False
    op_path = OPERATION_SETTINGS[operation]['mig_path']
    while page <= last and examined < max_listings:
        cards, last = parse_migliorisi_list(client.get(MIG_SEARCH.format(op=op_path, page=page)))
        for path, code, title in cards:
            if examined >= max_listings:
                cut = True
                break
            examined += 1
            if f'migliorisi:{code}' in known:
                skipped['ya_conocido'] += 1
                if sweep is not None:
                    sweep['vistos'].add(f'migliorisi:{code}')
                continue
            listing, is_operation, is_flat = parse_migliorisi_detail(
                client.get(MIG_BASE + path), path, code, title, captured_at, operation)
            if not (is_operation and is_flat):
                skipped['fuera_de_alcance'] += 1
                continue
            if not listing['neighborhood']:
                skipped['barrio_ambiguo'] += 1
            listings.append(listing)
        page += 1
    if sweep is not None:
        sweep['completo'] = page > last and not cut
    return listings, skipped


# ---------------------------------------------------------------- Mob

MOB_BASE = 'https://www.mob.ar'
MOB_ROOT = '/alquileres/capital-federal'
MOB_SITEMAPS = (MOB_BASE + '/sitemap/2.xml', MOB_BASE + '/sitemap/3.xml')
MOB_SUBZONES = {
    'caballito_norte': 'Caballito', 'caballito_sur': 'Caballito', 'almagro_norte': 'Almagro',
    'belgrano_barrancas': 'Belgrano', 'urquiza_r': 'Villa Urquiza', 'l_de_nunez': 'Núñez',
    'barrio_parque': 'Palermo',
}


def mob_barrio(name):
    """'Las Cañitas, Palermo' -> Palermo. Las partes se prueban de la más general a la más específica."""
    for part in reversed(str(name or '').split(',')):
        found = barrio(part) or MOB_SUBZONES.get(key(part))
        if found:
            return found
    return None


def parse_mob(page, captured_at):
    """Lee los avisos completos que la página de listado trae en `initialProperties`.

    Devuelve los avisos y un diccionario {ID: motivo} con los omitidos o sin barrio.
    """
    text = rsc_text(page)
    start = re.search(r'"initialProperties":\s*', text)
    if not start:
        return [], {}
    items, _ = json.JSONDecoder().raw_decode(text, start.end())
    out, skipped = [], {}
    for item in items:
        if item.get('propertyType') != 'Departamento':
            skipped[f"mob:{item.get('id')}"] = 'fuera_de_alcance'
            continue
        name = mob_barrio(item.get('neighborhood'))
        if not name:
            skipped[f"mob:{item.get('id')}"] = 'barrio_ambiguo'
        # `price` suma alquiler y expensas en pesos; `rentPrice` es el alquiler en su moneda.
        # Las expensas se publican siempre en pesos; 0 significa que no se informan.
        out.append(record(
            'mob', item.get('id'), f"{MOB_BASE}/propiedad/{item.get('slug')}", captured_at, 'alquiler',
            price=number(item.get('rentPrice')), currency=item.get('currency'),
            covered_area_m2=number(item.get('surface')), rooms=item.get('rooms'), neighborhood=name,
            expenses=number(item.get('expensas')),
            latitude=coordinate(item.get('geoLat')), longitude=coordinate(item.get('geoLong'))))
    return out, skipped


def mob_pages(client):
    """Páginas de listado de Capital Federal del sitemap: primero las de departamentos.

    El servidor siempre devuelve los primeros 20 avisos de cada listado (la paginación
    ocurre en el navegador contra /api/, que robots.txt excluye), así que se recorren los
    listados por barrio, ambientes y filtros, y se deduplica por ID.
    """
    paths = []
    urls = [url for sitemap in MOB_SITEMAPS for url in re.findall(r'<loc>([^<]+)</loc>', client.get(sitemap))]
    for url in urls:
        path = urlsplit(url).path
        if '/capital-federal' in path and path.startswith('/alquileres') and path != MOB_ROOT:
            paths.append(path)
    paths = sorted(set(paths), key=lambda p: ('/departamentos' not in p, p.count('/'), p))
    return [MOB_ROOT] + paths


def scrape_mob(client, captured_at, max_listings, known=frozenset(), operation='venta'):
    if operation != 'alquiler':
        return [], Counter({'mob_solo_publica_alquileres': 1})
    listings, skipped, seen = [], {}, set()
    for path in mob_pages(client):
        if len(listings) >= max_listings:
            break
        batch, why = parse_mob(client.get(MOB_BASE + path), captured_at)
        skipped.update(why)
        for item in batch:
            if item['listing_id'] not in seen:
                seen.add(item['listing_id'])
                listings.append(item)
    return listings[:max_listings], Counter(skipped.values())


# ---------------------------------------------------------------- Clarín Inmuebles

CLARIN_BASE = 'https://www.inmuebles.clarin.com'
CLARIN_SITEMAPS = {'venta': '/sitemaps/sitemap-listing-venta-caba.xml.gz',
                   'alquiler': '/sitemaps/sitemap-listing-alquiler-caba.xml.gz'}
# robots.txt solo permite las páginas 1 a 3 de cada listado.
CLARIN_PAGES = 3
CLARIN_PAGE_SIZE = 20
CLARIN_CURRENCY = {'USD': 'USD', 'U$S': 'USD', '$': 'ARS'}


def clarin_slug(name):
    return key(name).replace('_', '-').replace('.', '')


def clarin_listing_paths(client, operation):
    """Listados de departamentos por barrio de CABA, tomados del sitemap del portal.

    Si el sitemap no responde o no trae listados por barrio, se arman con los barrios
    oficiales. Un listado inexistente responde 404 y se saltea.
    """
    word = 'venta' if operation == 'venta' else 'alquiler'
    pattern = re.compile(rf'^/departamentos/{word}/([a-z0-9-]+)$')
    paths = []
    try:
        for url in re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', client.get(CLARIN_BASE + CLARIN_SITEMAPS[word])):
            match = pattern.match(urlsplit(url).path)
            if match and match.group(1) != 'capital-federal':
                paths.append(match.group(0))
    except RuntimeError:
        paths = []
    if not paths:
        paths = [f'/departamentos/{word}/{clarin_slug(n)}' for n in sorted(set(BARRIOS.values()))]
    return sorted(set(paths))


def clarin_features(card):
    block = re.search(r'card__main-features">(.*?)</ul>', card, re.S)
    return [clean(f) for f in re.findall(r'<span>(.*?)</span>', block.group(1), re.S)] if block else []


def clarin_sizes(card):
    """Superficie cubierta, superficie total y ambientes de una tarjeta de Clarín."""
    covered = total = rooms = None
    for feature in clarin_features(card):
        low = feature.lower()
        if (found := re.match(r'([\d.,]+)\s*m²\s*cub', low)):
            covered = local_number(found.group(1))
        elif (found := re.match(r'([\d.,]+)\s*m²\s*tot', low)):
            total = local_number(found.group(1))
        elif (found := re.match(r'(\d+)\s*amb', low)):
            rooms = int(found.group(1))
        elif low.startswith('monoam'):
            rooms = 1
    return covered, total, rooms


def parse_clarin(page, captured_at, operation='venta', fallback=None):
    """Lee las tarjetas de un listado. Solo toma campos del contrato, nunca datos del anunciante.

    Devuelve los avisos y un diccionario {ID: motivo} con los omitidos o sin barrio.
    """
    out, skipped = [], {}
    for card in re.split(r'<div class="listing__item\b', page)[1:]:
        attrs = dict(re.findall(r'\b(idaviso|idtipopropiedad|esavisosugerido)="([^"]*)"', card))
        local_id = attrs.get('idaviso')
        href = re.search(r'<a href="(/[^"]+)"', card)
        if not local_id or not href:
            continue
        if attrs.get('esavisosugerido') == 'True':
            skipped[f'clarin:{local_id}'] = 'sugerido_de_otra_zona'
            continue
        if attrs.get('idtipopropiedad') != '1':
            skipped[f'clarin:{local_id}'] = 'fuera_de_alcance'
            continue
        price_match = re.search(r'card__price">\s*<span class="card__currency">([^<]+)</span>\s*([\d.,]+)', card)
        currency = CLARIN_CURRENCY.get(clean(price_match.group(1))) if price_match else None
        expenses = re.search(r'card__expenses"[^>]*title="\$\s*([\d.,]+)', card)
        address = re.search(r'card__address"[^>]*>(.*?)</p>', card, re.S)
        zone = clean(address.group(1)).split(',')[-1] if address else ''
        name = barrio(zone) or fallback
        if not name:
            skipped[f'clarin:{local_id}'] = 'barrio_ambiguo'
        covered, total, rooms = clarin_sizes(card)
        out.append(record(
            'clarin', local_id, CLARIN_BASE + href.group(1), captured_at, operation,
            price=local_number(price_match.group(2)) if price_match else None, currency=currency,
            covered_area_m2=covered, total_area_m2=total, rooms=rooms, neighborhood=name,
            expenses=local_number(expenses.group(1)) if expenses else None))
    return out, skipped


def scrape_clarin(client, captured_at, max_listings, known=frozenset(), operation='venta'):
    """Recorre la página 1 de cada barrio, después la 2 y después la 3, sin abrir fichas."""
    listings, skipped, seen = [], {}, set()
    paths = clarin_listing_paths(client, operation)
    active = {path: True for path in paths}
    for page_number in range(1, CLARIN_PAGES + 1):
        for path in paths:
            if len(listings) >= max_listings:
                return listings[:max_listings], Counter(skipped.values())
            if not active[path]:
                continue
            url = CLARIN_BASE + path + ('' if page_number == 1 else f'?pagina-{page_number}')
            try:
                page = client.get(url)
            except RuntimeError as error:
                if 'HTTP 404' not in str(error):
                    raise
                active[path] = False
                continue
            fallback = barrio(path.rsplit('/', 1)[-1].replace('-', ' '))
            batch, why = parse_clarin(page, captured_at, operation, fallback)
            skipped.update(why)
            new = [item for item in batch if item['listing_id'] not in seen]
            seen.update(item['listing_id'] for item in new)
            listings += new
            if len(batch) + len(why) < CLARIN_PAGE_SIZE or not new:
                active[path] = False
    return listings[:max_listings], Counter(skipped.values())


SITES = {'remax': scrape_remax, 'century21': scrape_century21, 'migliorisi': scrape_migliorisi, 'mob': scrape_mob,
         'clarin': scrape_clarin}
# La actualización programada usa estos sitios. Clarín se pide explícitamente con --sitios clarin.
DEFAULT_SITES = ('century21', 'migliorisi', 'mob', 'remax')


# ---------------------------------------------------------------- Consolidación

def possible_duplicates(listings):
    """Avisos de distintas inmobiliarias con mismo barrio, ambientes, m² y precio."""
    groups = {}
    for item in listings:
        if None in (item['neighborhood'], item['rooms'], item['covered_area_m2'], item['price']):
            continue
        k = (item['neighborhood'], item['rooms'], round(item['covered_area_m2']), round(item['price'], -3))
        groups.setdefault(k, []).append(item)
    return [[i['listing_id'] for i in g] for g in groups.values() if len({i['agency'] for i in g}) > 1]


def run_capture(sites, max_listings, out, client=None, known=frozenset(), echo=print, operation='venta'):
    """Captura cada sitio en una carpeta nueva y devuelve los avisos y el registro.

    Además escribe `vistos.json`: por sitio, si el barrido fue completo (se recorrió toda la fuente, no solo
    los más recientes) y los IDs vistos. Solo un barrido completo permite dar de baja los avisos que faltan.
    """
    out.mkdir(parents=True, exist_ok=False)
    captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    client = client or PoliteClient()
    listings, log = [], {'catalogo': CATALOGS[operation], 'operacion': operation, 'captura': captured_at,
                         'user_agent': USER_AGENT, 'sitios': {}}
    seen = {}
    for site in sites:
        before, start = dict(client.log), time.monotonic()
        sweep = {'completo': False, 'vistos': set()}
        try:
            kwargs = {'known': known, 'operation': operation} if operation != 'venta' else {'known': known}
            if 'sweep' in inspect.signature(SITES[site]).parameters:
                kwargs['sweep'] = sweep
            batch, skipped = SITES[site](client, captured_at, max_listings, **kwargs)
            status = 'completo'
        except Blocked as error:
            batch, skipped, status = [], Counter(), f'detenido: {error}'
        except (RuntimeError, ValueError, KeyError) as error:
            batch, skipped, status = [], Counter(), f'error: {error}'
        listings += batch
        complete = status == 'completo' and sweep['completo']
        seen[site] = {'barrido_completo': complete,
                      'ids': sorted(sweep['vistos'] | {item['listing_id'] for item in batch})}
        log['sitios'][site] = {'estado': status, 'avisos': len(batch), 'omitidos': dict(skipped),
                               'barrido_completo': complete,
                               'pedidos': client.log['pedidos'] - before.get('pedidos', 0),
                               'segundos': round(time.monotonic() - start)}
        (out / 'avisos.json').write_text(json.dumps(listings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (out / 'vistos.json').write_text(json.dumps(seen, ensure_ascii=False) + '\n', encoding='utf-8')
        echo(f"{site}: {status} · {len(batch)} avisos" + (' · barrido completo' if complete else ''))
    log['posibles_duplicados_entre_inmobiliarias'] = possible_duplicates(listings)
    log['respuestas_http'] = {k: v for k, v in client.log.items() if k.startswith('http_')}
    log['robots_no_disponible'] = [k.split(':', 1)[1] for k in client.log if k.startswith('robots_no_disponible:')]
    (out / 'registro.json').write_text(json.dumps(log, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return listings, log


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--sitios', nargs='+', choices=sorted(SITES), default=list(DEFAULT_SITES))
    parser.add_argument('--max-avisos', type=int, default=600, help='Tope de avisos por inmobiliaria')
    parser.add_argument('--pausa-s', type=float, default=DEFAULT_PAUSE_S)
    parser.add_argument('--operacion', choices=sorted(CATALOGS), default='venta')
    parser.add_argument('--salida', type=Path)
    parser.add_argument('--autorizacion-confirmada', action='store_true',
                        help='Confirma que cada inmobiliaria autorizó por escrito la lectura de su sitio')
    args = parser.parse_args()
    if not args.autorizacion_confirmada:
        parser.exit(1, 'Error: falta --autorizacion-confirmada.\n')
    if args.pausa_s < 2:
        parser.exit(1, 'Error: la pausa mínima entre pedidos es de 2 segundos.\n')
    suffix = '' if args.operacion == 'venta' else f'-{args.operacion}'
    args.salida = args.salida or ROOT / f"data/raw/inmobiliarias{suffix}-{datetime.now():%Y%m%d}"
    listings, log = run_capture(args.sitios, args.max_avisos, args.salida, PoliteClient(pause_s=args.pausa_s),
                                echo=lambda line: print(line, flush=True), operation=args.operacion)
    print(json.dumps(log['sitios'], ensure_ascii=False, indent=2))
    print(f'Avisos: {len(listings)} · Archivo: {args.salida / "avisos.json"}')


if __name__ == '__main__':
    main()
