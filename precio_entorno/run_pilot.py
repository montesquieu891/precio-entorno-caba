"""Piloto Zonaprop con el actor de Expandí tu Marca."""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from precio_entorno.apify_client import ApifyClient
from precio_entorno.importing import BARRIOS, import_listings, key, usable_pin
from precio_entorno.store import Store

ACTOR = 'expanditumarca/real-estate-lead-generator-market-analysis-zonaprop'
ACTOR_PATH = 'acts/' + ACTOR.replace('/', '~')
BUILD = '9.5.3'
SOURCE = 'zonaprop'
ROOT = Path(__file__).resolve().parents[1]
RAW_FIELDS = ('url', 'id', 'scraped_at', 'precio', 'moneda', 'm2_cub', 'm2_tot',
              'ambientes', 'barrio', 'operacion', 'latitud', 'longitud',
              'latitude', 'longitude', 'status', 'type')
# Campos del esquema público de 9.5.3 usados por el piloto.
SCHEMA = {
    'operationMode': {'type': 'string', 'enum': ['scrape-urls', 'property-scrape']},
    'ubicacion': {'type': 'string'},
    'operacion': {'type': 'string', 'enum': ['venta']},
    'tipo': {'type': 'string'},
    'maxPages': {'type': 'integer', 'minimum': 1, 'maximum': 10},
    'mode': {'type': 'string', 'enum': ['scrape-single']},
    'url': {'type': 'string'},
    'enableProxies': {'type': 'boolean'},
    'proxyType': {'type': 'string', 'enum': ['none']},
}


def validate_input(payload, schema):
    types = {'string': str, 'integer': int, 'boolean': bool}
    for name, value in payload.items():
        rule = schema.get(name, {})
        if type(value) is not types.get(rule.get('type')) or value not in rule.get('enum', [value]):
            raise ValueError(f'{name} no coincide con el esquema del actor.')
        if type(value) is int and not rule.get('minimum', value) <= value <= rule.get('maximum', value):
            raise ValueError(f'{name} está fuera del rango del actor.')


def pilot_plan(schema=SCHEMA):
    spec = json.loads((ROOT / 'docs/apify-piloto-input.json').read_text(encoding='utf-8'))
    searches = spec['searchInputs']
    detail = spec['detailInputTemplate']
    for payload in [*searches, detail]:
        validate_input(payload, schema)
        if payload.get('enableProxies') is not False or payload.get('proxyType') != 'none':
            raise ValueError('El piloto requiere acceso directo.')
    if (spec['actor'] != ACTOR or [p.get('ubicacion') for p in searches] != ['caballito', 'almagro']
            or any(p.get('operationMode') != 'scrape-urls' or p.get('operacion') != 'venta'
                   or p.get('tipo') != 'departamentos' or p.get('maxPages') != 1 for p in searches)
            or detail.get('operationMode') != 'property-scrape' or detail.get('mode') != 'scrape-single'
            or spec['limits'] != {'maxListingDetails': 50, 'maxTotalUsd': 1}):
        raise ValueError('La configuración se sale del alcance del piloto.')
    return {'actor': ACTOR, 'fuente': SOURCE, 'build': BUILD,
            'filtros': 'Departamentos en venta de dos ambientes en CABA',
            'filtro_ambientes': 'Se aplica a los detalles; el actor no lo admite en la búsqueda.',
            'candidatos_por_barrio': 25, 'max_total_usd': 1,
            'tope_busqueda_usd': 0.05, 'tope_detalle_usd': 0.018,
            'estimado_usd': None, 'referencia_tarifa_anterior_50_detalles_usd': 2.50,
            'busquedas': searches, 'detalle': detail}


def listing_link(value):
    try:
        url = urlsplit(str(value or ''))
    except ValueError:
        return None
    match = re.search(r'-(\d+)\.html$', url.path)
    if (url.scheme == 'https' and url.netloc in ('www.zonaprop.com.ar', 'zonaprop.com.ar')
            and url.path.startswith('/propiedades/') and match):
        return f'zonaprop.com.ar:{match[1]}', url._replace(query='', fragment='').geturl()
    return None


def adapt_row(row, expected_barrio, link, captured_at=None):
    item = listing_link(row.get('url')) if row.get('url') else link
    barrio = BARRIOS.get(key(row.get('barrio')))
    if (not item or item[0] != link[0] or barrio != expected_barrio
            or key(row.get('operacion')) != 'venta' or str(row.get('ambientes')) not in ('2', '2.0')):
        return None
    return {
        'listing_id': item[0], 'source': SOURCE, 'url': item[1],
        'captured_at': row.get('scraped_at') or captured_at,
        'price': row.get('precio'), 'currency': row.get('moneda'),
        'covered_area_m2': row.get('m2_cub'), 'total_area_m2': row.get('m2_tot'),
        'rooms': 2, 'neighborhood': barrio,
        'latitude': row.get('latitud', row.get('latitude')),
        'longitude': row.get('longitud', row.get('longitude')),
    }


def write_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def batch_stats(listings, received):
    with TemporaryDirectory() as temp:
        store = Store(Path(temp) / 'preview.sqlite3')
        report = import_listings(store, json.dumps(listings).encode(), 'piloto.json', SOURCE)
        return {
            'detalles_recibidos': received, 'fuera_de_alcance': received - len(listings),
            'comparables_con_barrio': report.added,
            'pines_utilizables': sum(map(usable_pin, store.listings())),
            'duplicados': report.duplicates, 'descartes_validacion': report.discarded,
            'faltantes': dict(report.missing), 'invalidos': dict(report.invalid),
        }


def collect(client, output, log, barrio, payload, cap):
    record = {'actor': ACTOR, 'barrio': barrio, 'modo': payload['operationMode'],
              'max_usd': cap, 'status': 'START_REQUESTED'}
    log.append(record)
    write_json(output / 'corridas.json', log)
    run = client.request(f'{ACTOR_PATH}/runs', params={
        'build': BUILD, 'maxTotalChargeUsd': cap, 'timeout': 300, 'restartOnError': 'false',
    }, payload=payload)['data']
    record.update(run_id=run['id'], status=run['status'])
    write_json(output / 'corridas.json', log)
    final = client.wait(run['id'])
    dataset = final.get('defaultDatasetId')
    cost = final.get('usageTotalUsd')
    record.update(status=final['status'], dataset_id=dataset, costo_informado_usd=cost)
    write_json(output / 'corridas.json', log)
    if final['status'] != 'SUCCEEDED' or not isinstance(dataset, str) or not re.fullmatch(r'[A-Za-z0-9]+', dataset):
        raise RuntimeError(f'Corrida {run["id"]}: {final["status"]}. Revisá Apify Console.')
    rows = client.request(f'datasets/{dataset}/items', params={'fields': ','.join(RAW_FIELDS)})
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError('El dataset de Apify tiene un formato inesperado.')
    raw = [{field: row[field] for field in RAW_FIELDS if field in row} for row in rows]
    write_json(output / f'{run["id"]}-crudo.json', raw)
    record['filas'] = len(raw)
    write_json(output / 'corridas.json', log)
    if type(cost) not in (int, float) or not 0 <= cost <= cap:
        raise RuntimeError('El costo informado falta o supera el tope de la corrida.')
    return raw, final.get('startedAt')


def pilot_search(client, plan, output, log, search, seen, listings):
    """Corre la búsqueda de un barrio y una corrida de detalle por candidato; devuelve las filas recibidas."""
    barrio = BARRIOS[search['ubicacion']]
    rows, _ = collect(client, output, log, barrio, search, plan['tope_busqueda_usd'])
    candidates = {}
    for row in rows:
        link = listing_link(row.get('url'))
        if link and link[0] not in seen:
            candidates.setdefault(*link)
    if not candidates:
        raise RuntimeError(f'La búsqueda de {barrio} no devolvió enlaces válidos. Revisá el log en Apify Console.')
    received = 0
    for listing_id, url in list(candidates.items())[:plan['candidatos_por_barrio']]:
        seen.add(listing_id)
        payload = dict(plan['detalle'], url=url)
        rows, captured_at = collect(client, output, log, barrio, payload, plan['tope_detalle_usd'])
        if len(rows) > 1:
            raise RuntimeError('La corrida individual devolvió más de una fila.')
        received += len(rows)
        if rows:
            listing = adapt_row(rows[0], barrio, (listing_id, url), captured_at)
            if listing:
                listings.append(listing)
        write_json(output / 'avisos.json', listings)
    return received


def run_pilot(client, plan, output):
    output.mkdir(exist_ok=False)
    log, listings = [], []
    seen = set()
    received = 0
    for search in plan['busquedas']:
        received += pilot_search(client, plan, output, log, search, seen, listings)
    stats = batch_stats(listings, received)
    write_json(output / 'resumen.json', stats)
    return stats


def live_plan(client, budget=1):
    actor = client.request(ACTOR_PATH)['data']
    build = client.request(f'{ACTOR_PATH}/builds/default')['data']
    if build.get('buildNumber') != BUILD:
        raise RuntimeError('Cambió el build. Revisá el esquema del actor.')
    schema = build['inputSchema']
    plan = pilot_plan((json.loads(schema) if isinstance(schema, str) else schema)['properties'])
    now = datetime.now(timezone.utc).isoformat()
    prices = [p for p in actor.get('pricingInfos', ()) if p.get('startedAt', '') <= now]
    price = max(prices, key=lambda p: p.get('startedAt', ''), default={})
    if price.get('pricingModel') == 'FREE':
        account = client.request('users/me/limits')['data']
        limit = account['limits'].get('maxMonthlyUsageUsd')
        if type(limit) not in (int, float) or not 0 < limit <= budget:
            raise RuntimeError('El tope mensual de Apify supera el presupuesto autorizado.')
        plan.update(max_total_usd=budget, tope_detalle_usd=round((budget - 0.10) / 50, 3))
        return plan
    if (price.get('pricingModel') != 'PAY_PER_EVENT' or price.get('isPPEPlatformUsagePaidByUser')
            or (price.get('minimalMaxTotalChargeUsd') or 0) > plan['tope_detalle_usd']):
        raise RuntimeError('No está verificado un tope efectivo de USD 1 con la tarifa vigente.')
    events = price.get('pricingPerEvent', {}).get('actorChargeEvents', {})
    for name, cap in [('scrape-urls', plan['tope_busqueda_usd']), ('scrape-single', plan['tope_detalle_usd'])]:
        event = events.get(name, {})
        unit = event.get('eventPriceUsd')
        if unit is None:
            unit = event.get('eventTieredPricingUsd', {}).get('FREE', {}).get('tieredEventPriceUsd')
        if type(unit) not in (int, float) or not 0 <= unit <= cap:
            raise RuntimeError(f'La tarifa vigente de {name} no está verificada dentro del tope.')
    return plan


TOKEN_LINE = re.compile(r'(?:export\s+)?APIFY_TOKEN(?:_\w+)?\s*=(.*)')


def apify_tokens(env=ROOT / '.env'):
    """Tokens en el orden del .env: líneas APIFY_TOKEN, APIFY_TOKEN_<n> o apify_api_ sueltas."""
    if os.environ.get('APIFY_TOKEN'):
        return [os.environ['APIFY_TOKEN'].strip()]
    if not env.is_file():
        return []
    tokens = []
    for line in env.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        match = TOKEN_LINE.fullmatch(line)
        token = (match[1] if match else line).strip().strip('"\'')
        if (match or token.startswith('apify_api_')) and token and token not in tokens:
            tokens.append(token)
    return tokens


def apify_token(account=None, env=ROOT / '.env'):
    """Devuelve el token de una sola cuenta. Cada cuenta tiene su propio tope de USD 5."""
    tokens = apify_tokens(env)
    if account is None:
        if len(tokens) > 1:
            raise ValueError(f'Hay {len(tokens)} cuentas de Apify en .env. Elegí una con --account 1 a {len(tokens)}.')
        return tokens[0] if tokens else None
    if not 1 <= account <= len(tokens):
        raise ValueError(f'--account debe estar entre 1 y {len(tokens)}.')
    return tokens[account - 1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--execute', action='store_true')
    parser.add_argument('--authorized-direct-access', action='store_true')
    parser.add_argument('--budget-usd', type=int, choices=(1, 5), default=1)
    parser.add_argument('--account', type=int, help='Número de cuenta de Apify según el orden del .env')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/raw/piloto-zonaprop',
                        help='Carpeta nueva para esta corrida')
    args = parser.parse_args()
    try:
        preview = pilot_plan()
        preview.update(max_total_usd=args.budget_usd,
                       tope_detalle_usd=round((args.budget_usd - 0.10) / 50, 3))
        print(json.dumps(preview, ensure_ascii=False, indent=2), flush=True)
        if not args.execute:
            return
        if not args.authorized_direct_access:
            raise ValueError('Falta confirmar el acceso directo autorizado por Zonaprop.')
        token = apify_token(args.account)
        if not token:
            raise ValueError('Falta APIFY_TOKEN en el entorno o en .env.')
        client = ApifyClient(token)
        stats = run_pilot(client, live_plan(client, args.budget_usd), args.output)
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    except (ValueError, OSError, RuntimeError, KeyError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()

