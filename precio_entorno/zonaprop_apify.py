"""Avisos de Zonaprop con el actor de Apify igolaizola/zonaprop-scraper.

Zonaprop autorizó por escrito la consulta automatizada. Cada corrida lleva un tope de
gasto (maxTotalChargeUsd) y se verifica antes la tarifa vigente del actor. El actor
devuelve datos del anunciante (nombre, correos, teléfonos), la descripción y las fotos:
nunca se guardan. De la descripción solo quedan indicadores (a estrenar, apto crédito,
balcón...; ver `descripcion.py`). Solo se escriben los campos del contrato de datos, en
el mismo catálogo consolidado que las inmobiliarias, con el prefijo `zonaprop:`.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from precio_entorno.actualizar import BASES
from precio_entorno.apify_client import ApifyClient
from precio_entorno.descripcion import DESCRIPTION_FIELDS, traits
from precio_entorno.importing import BARRIOS, key, parse_listings
from precio_entorno.inmobiliarias import CATALOGS, coordinate, local_number, mob_barrio, number, record
from precio_entorno.run_pilot import apify_tokens
from precio_entorno.store import Store

ACTOR = 'igolaizola/zonaprop-scraper'
ACTOR_PATH = 'acts/' + ACTOR.replace('/', '~')
ROOT = Path(__file__).resolve().parents[1]
MAX_EVENT_USD = 0.002          # Tarifa verificada el 8/11/2026: USD 0,001 por evento.
MAX_RUN_USD = 5.0              # Tope de cada cuenta de Apify.
PILOT_BARRIOS = ('Caballito', 'Almagro')
CABA_BARRIOS = tuple(sorted(set(BARRIOS.values())))
ACCOUNT_LIMIT_USD = 5.0
OPERATIONS = {'venta': ('sale', 'Venta'), 'alquiler': ('rent', 'Alquiler')}
# Códigos de características de Zonaprop.
AMBIENTES, SUP_TOTAL, SUP_CUBIERTA, EXPENSAS = 'CFT1', 'CFT100', 'CFT101', 'CFT6'
ANTIGUEDAD, COCHERAS = 'CFT5', 'CFT7'   # Zonaprop no publica estado ni piso como característica.
# Subbarrios de Zonaprop que caen en un único barrio oficial.
ZONAPROP_SUBZONES = {'almagro_sur': 'Almagro', 'parque_rivadavia': 'Caballito', 'parque_centenario': None,
                     'pompeya': 'Nueva Pompeya'}
# Nombres de barrio que el buscador de Zonaprop reconoce cuando el oficial no devuelve resultados.
SEARCH_NAMES = {'Montserrat': 'Monserrat', 'Núñez': 'Nuñez', 'Nueva Pompeya': 'Pompeya'}


def check_pricing(client):
    """Detiene la corrida si la tarifa del actor subió desde que se verificó."""
    price = client.request(ACTOR_PATH)['data']['pricingInfos'][-1]
    if price.get('pricingModel') != 'PAY_PER_EVENT':
        raise RuntimeError('Cambió el modelo de cobro del actor. Revisá la tarifa.')
    for name, event in price['pricingPerEvent']['actorChargeEvents'].items():
        unit = event.get('eventPriceUsd')
        if unit is None:
            unit = (event.get('eventTieredPricingUsd') or {}).get('FREE', {}).get('tieredEventPriceUsd')
        if type(unit) not in (int, float) or unit > MAX_EVENT_USD:
            raise RuntimeError(f'La tarifa del evento {name} cambió ({unit}). Revisá los topes.')


def payload(barrio, operation, max_items):
    return {'maxItems': max_items, 'fetchDetails': True, 'operation': OPERATIONS[operation][0],
            'location': barrio, 'locationType': 'neighborhood', 'propertyType': 'apartment',
            'sortBy': 'newest'}


def features(item):
    """{código: valor} de las características del aviso.

    El listado omite algunos códigos cuando valen 0 (por ejemplo, cocheras); la ficha
    (`_details`) los trae, así que completa con ella lo que falta.
    """
    out = {}
    entries = (item.get('features') or []) + ((item.get('_details') or {}).get('features') or [])
    for entry in entries:
        feature = (entry or {}).get('feature') or {}
        if feature.get('feature_id') is not None and 'value' in entry:
            out.setdefault(str(feature['feature_id']), entry.get('value'))
    return out


def zonaprop_barrio(location):
    """Recorre la jerarquía de ubicación de Zonaprop hasta encontrar un barrio oficial."""
    node = location
    while isinstance(node, dict):
        name = node.get('name')
        sub = key(name or '')
        if sub in ZONAPROP_SUBZONES:
            return ZONAPROP_SUBZONES[sub]
        found = mob_barrio(name)
        if found:
            return found
        node = node.get('parent')
    return None


def in_caba(location):
    node = location
    while isinstance(node, dict):
        if node.get('acronym') == 'CABA' or key(node.get('name') or '') == 'capital_federal':
            return True
        node = node.get('parent')
    return False


def listing_url(value):
    parts = urlsplit(str(value or ''))
    if parts.scheme == 'https' and parts.netloc in ('www.zonaprop.com.ar', 'zonaprop.com.ar'):
        return parts._replace(query='', fragment='').geturl()
    return None


def whole(value):
    """Entero no negativo escrito sin decimales ('0', '15'). Lo demás queda sin dato."""
    text = str(value if value is not None else '').strip()
    return int(text) if re.fullmatch(r'\d{1,3}', text) else None


def ars_amount(text):
    """'$ 200.000' -> 200000. Las expensas en otra moneda se descartan."""
    text = str(text or '').strip()
    if not text.startswith('$'):
        return None
    return local_number(text.lstrip('$').strip())


def adapt(item, captured_at, operation):
    """Convierte un resultado del actor al contrato. Devuelve (aviso o None, motivo)."""
    details = item.get('_details') or {}
    location = ((details.get('location') or {}).get('location')) or {}
    pricing = item.get('pricing') or {}
    url = listing_url(item.get('url') or details.get('url'))
    pid = str(item.get('posting_id') or item.get('id') or '')
    if not url or not re.fullmatch(r'\d+', pid):
        return None, 'sin_id_o_enlace'
    if key(pricing.get('operation') or '') != key(OPERATIONS[operation][1]):
        return None, 'fuera_de_alcance'
    if key((item.get('propertyDetails') or {}).get('type') or '') != 'departamento':
        return None, 'fuera_de_alcance'
    if not in_caba(location):
        return None, 'fuera_de_caba'
    feats = features(item)
    covered, total = number(feats.get(SUP_CUBIERTA)), number(feats.get(SUP_TOTAL))
    geo = ((item.get('location') or {}).get('posting_geolocation') or {}).get('geolocation') or {}
    rooms = number(feats.get(AMBIENTES))
    # La ficha trae la descripción completa; el listado, solo un resumen.
    text = traits(details.get('title') or item.get('title'), details.get('description') or item.get('description'))
    listing = record(
        'zonaprop', pid, url, captured_at, operation,
        price=number(pricing.get('amount')), currency=pricing.get('currency'),
        covered_area_m2=covered, total_area_m2=total if total and covered and total >= covered else None,
        rooms=int(rooms) if rooms else None, neighborhood=zonaprop_barrio(location),
        latitude=coordinate(geo.get('latitude')), longitude=coordinate(geo.get('longitude')),
        expenses=ars_amount(feats.get(EXPENSAS)),
        age_years=whole(feats.get(ANTIGUEDAD)), garages=whole(feats.get(COCHERAS)), **text)
    return listing, None if listing['neighborhood'] else 'barrio_ambiguo'


def adapt_all(items, captured_at, operation):
    listings, skipped, seen = [], {}, set()
    for item in items:
        listing, why = adapt(item, captured_at, operation)
        if why:
            skipped[why] = skipped.get(why, 0) + 1
        if listing and listing['listing_id'] not in seen:
            seen.add(listing['listing_id'])
            listings.append(listing)
    return listings, skipped


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def account_usage(client):
    return float(client.request('users/me/limits')['data'].get('current', {}).get('monthlyUsageUsd') or 0)


def pick_account(accounts, cap_usd, margin_usd):
    """Primera cuenta cuyo gasto del mes, más una corrida completa y un margen, sigue bajo USD 5."""
    for number_, client in accounts:
        if account_usage(client) + cap_usd + margin_usd <= ACCOUNT_LIMIT_USD:
            return number_, client
    return None, None


def run(accounts, out, barrios, operation, max_items, cap_usd, margin_usd=0.25):
    """Una corrida por barrio, rotando de cuenta cuando una se acerca a su tope.

    `accounts` es una lista de (número de cuenta, ApifyClient). Guarda solo avisos
    adaptados y el registro de costos.
    """
    out.mkdir(parents=True, exist_ok=False)
    check_pricing(accounts[0][1])
    captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    listings, log = [], {'actor': ACTOR, 'catalogo': CATALOGS[operation], 'operacion': operation,
                         'captura': captured_at, 'cuentas': [n for n, _ in accounts],
                         'tope_por_corrida_usd': cap_usd, 'margen_por_cuenta_usd': margin_usd, 'corridas': []}
    for barrio in barrios:
        account, client = pick_account(accounts, cap_usd, margin_usd)
        if client is None:
            log['detenido'] = f'Sin saldo en las cuentas antes de {barrio}.'
            write_json(out / 'registro.json', log)
            print(log['detenido'], flush=True)
            break
        run_ = client.request(f'{ACTOR_PATH}/runs', params={'maxTotalChargeUsd': cap_usd, 'timeout': 900,
                                                           'memory': 1024},
                              payload=payload(barrio, operation, max_items))['data']
        run_ = client.wait(run_['id'], max_seconds=1000)
        items = client.request(f"datasets/{run_['defaultDatasetId']}/items", params={'format': 'json', 'clean': 'true'})
        batch, skipped = adapt_all(items, captured_at, operation)
        known = {x['listing_id'] for x in listings}
        listings += [x for x in batch if x['listing_id'] not in known]
        log['corridas'].append({'barrio': barrio, 'cuenta': account, 'estado': run_['status'], 'recibidos': len(items),
                                'avisos': len(batch), 'omitidos': skipped, 'eventos': run_.get('chargedEventCounts'),
                                'uso_usd': run_.get('usageTotalUsd'), 'run_id': run_['id']})
        write_json(out / 'avisos.json', listings)
        write_json(out / 'registro.json', log)
        print(f"{barrio}: {run_['status']} · {len(batch)} avisos", flush=True)
    return listings, log


def reread_runs(source, clients, by_id, log):
    """Relee el dataset de cada corrida de un registro y suma sus avisos a `by_id`."""
    for entry in source['corridas']:
        # Una corrida que ya no se puede leer (cuenta sin acceso, resultados vencidos) se anota y se saltea.
        try:
            client = clients[entry.get('cuenta') or 1]
            run_ = client.request(f"actor-runs/{entry['run_id']}")['data']
            items = client.request(f"datasets/{run_['defaultDatasetId']}/items",
                                   params={'format': 'json', 'clean': 'true'})
        except (RuntimeError, KeyError) as error:
            log['corridas'].append({'barrio': entry['barrio'], 'run_id': entry['run_id'], 'error': str(error)})
            print(f"{entry['barrio']}: sin leer ({error})", flush=True)
            continue
        batch, skipped = adapt_all(items, source['captura'], source['operacion'])
        by_id.update((x['listing_id'], x) for x in batch)
        log['corridas'].append({'barrio': entry['barrio'], 'run_id': entry['run_id'], 'avisos': len(batch),
                                'omitidos': skipped})
        print(f"{entry['barrio']}: {len(batch)} avisos", flush=True)


def reread(registros, clients, out):
    """Vuelve a adaptar los resultados de corridas ya hechas, sin correr el actor.

    Lee el dataset de cada corrida registrada (no genera eventos cobrables) y conserva la
    fecha de captura original. `clients` es {número de cuenta: ApifyClient}. Si un aviso
    aparece en más de un registro, gana el último.
    """
    out.mkdir(parents=True, exist_ok=False)
    by_id, log = {}, {'actor': ACTOR, 'releido_de': [], 'corridas': [],
                      'nota': 'Relectura de datasets existentes, sin corridas nuevas del actor.'}
    for path in registros:
        source = json.loads(Path(path).read_text(encoding='utf-8'))
        log['releido_de'].append(Path(path).parent.name)
        reread_runs(source, clients, by_id, log)
    listings = list(by_id.values())
    log['avisos'] = len(listings)
    log['corridas_sin_leer'] = sum('error' in entry for entry in log['corridas'])
    log['con_antiguedad'] = sum(x['age_years'] is not None for x in listings)
    log['con_descripcion'] = sum(x[DESCRIPTION_FIELDS[0]] is not None for x in listings)
    log['rasgos'] = {c: sum(x[c] or 0 for x in listings) for c in DESCRIPTION_FIELDS}
    write_json(out / 'avisos.json', listings)
    write_json(out / 'registro.json', log)
    return listings, log


def complete_base(avisos, operation, base=None):
    """Suma a la base los datos opcionales de una relectura, solo donde la base no los tiene.

    Valida el archivo como cualquier importación. Devuelve (avisos válidos, avisos completados).
    """
    path = Path(avisos)
    listings, _ = parse_listings(path.read_bytes(), path.name, CATALOGS[operation], operation)
    return len(listings), Store(Path(base or BASES[operation])).complete_details(listings)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--barrios', nargs='+', default=list(PILOT_BARRIOS),
                        help='Barrios a buscar, o "todos" para los 48 barrios oficiales')
    parser.add_argument('--operacion', choices=sorted(OPERATIONS), default='venta')
    parser.add_argument('--max-avisos', type=int, default=25, help='Avisos por barrio')
    parser.add_argument('--tope-usd', type=float, default=0.5, help='Tope de gasto de cada corrida')
    parser.add_argument('--cuentas', type=int, nargs='+', default=[1],
                        help='Cuentas de Apify según el orden del .env, en orden de uso')
    parser.add_argument('--margen-usd', type=float, default=0.25, help='Saldo que se deja libre en cada cuenta')
    parser.add_argument('--salida', type=Path)
    parser.add_argument('--ejecutar', action='store_true', help='Sin esta opción solo muestra el plan')
    parser.add_argument('--autorizacion-confirmada', action='store_true',
                        help='Confirma que Zonaprop autorizó por escrito la consulta automatizada')
    parser.add_argument('--releer', type=Path, nargs='+', metavar='REGISTRO',
                        help='Vuelve a adaptar corridas ya hechas a partir de sus registro.json, sin costo de actor')
    parser.add_argument('--completar-base', type=Path, metavar='AVISOS',
                        help='Completa la base de la operación con un avisos.json releído, sin pisar datos')
    args = parser.parse_args()
    if args.completar_base:
        valid, done = complete_base(args.completar_base, args.operacion)
        print(f'Avisos válidos: {valid} · completados en la base de {args.operacion}: {done}')
        return
    if args.releer:
        if not args.salida:
            parser.exit(1, 'Error: --releer necesita --salida.\n')
        try:
            tokens = apify_tokens()
            listings, log = reread(args.releer, {n: ApifyClient(t) for n, t in enumerate(tokens, 1)}, args.salida)
        except (ValueError, RuntimeError, OSError, KeyError) as error:
            parser.exit(1, f'Error: {error}\n')
        print(f"Avisos: {len(listings)} · con antigüedad: {log['con_antiguedad']}"
              f" · con descripción: {log['con_descripcion']}")
        return
    if args.barrios == ['todos']:
        args.barrios = [SEARCH_NAMES.get(name, name) for name in CABA_BARRIOS]
    estimate = len(args.barrios) * (0.001 + args.max_avisos * 2 * 0.001)
    plan = {'actor': ACTOR, 'operacion': args.operacion, 'barrios': args.barrios, 'avisos_por_barrio': args.max_avisos,
            'tope_por_corrida_usd': args.tope_usd, 'estimado_usd': round(estimate, 3),
            'entrada': payload(args.barrios[0], args.operacion, args.max_avisos)}
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if not args.ejecutar:
        return
    if not args.autorizacion_confirmada:
        parser.exit(1, 'Error: falta --autorizacion-confirmada.\n')
    if not 0 < args.tope_usd <= 1:
        parser.exit(1, 'Error: el tope de cada corrida debe estar entre 0 y USD 1.\n')
    try:
        tokens = apify_tokens()
        if not tokens or any(not 1 <= n <= len(tokens) for n in args.cuentas):
            raise ValueError(f'Las cuentas deben estar entre 1 y {len(tokens)}.')
        accounts = [(n, ApifyClient(tokens[n - 1])) for n in args.cuentas]
        out = args.salida or ROOT / f"data/raw/zonaprop-{args.operacion}-{datetime.now():%Y%m%d-%H%M}"
        listings, log = run(accounts, out, args.barrios, args.operacion, args.max_avisos,
                            args.tope_usd, args.margen_usd)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f'Error: {error}\n')
    print(f'Avisos: {len(listings)} · Archivo: {out / "avisos.json"}')


if __name__ == '__main__':
    main()
