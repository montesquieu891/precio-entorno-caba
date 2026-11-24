"""Núcleo del Actor de alertas: captura, descarta lo ya visto y cruza con las búsquedas.

Make lanza el Actor con las búsquedas activas, sin datos personales: solo número,
operación, barrio, presupuesto, moneda, superficie y ambientes. El Actor captura los
sitios autorizados con el cliente educado de siempre, valida los avisos con las reglas
de `importing`, descarta los IDs ya vistos en corridas anteriores y devuelve un ítem por
búsqueda con avisos nuevos, con el resumen listo para el correo.

Este módulo no depende del SDK de Apify: recibe el estado y devuelve el estado nuevo,
para poder probarlo sin red. `actor_main` hace la entrada y salida en Apify.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from precio_entorno.importing import BARRIOS, CURRENCIES, OPERATIONS, key, parse_listings
from precio_entorno.inmobiliarias import CATALOGS, DEFAULT_SITES, run_capture
from precio_entorno.make_webhook import ALERT_FIELDS, group
from precio_entorno.matching import matches

OFFICIAL = frozenset(BARRIOS.values())
MAX_SEARCHES = 200
MAX_LISTINGS_PER_SITE = 200


def _int(value, name, minimum=1, maximum=10**9):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value):
        raise ValueError(f'«{name}» debe ser un número entero.')
    if not minimum <= value <= maximum:
        raise ValueError(f'«{name}» debe estar entre {minimum} y {maximum}.')
    return int(value)


def parse_searches(raw):
    """Valida las búsquedas de la entrada. Una búsqueda inválida detiene la corrida con un mensaje claro."""
    if not isinstance(raw, list) or not raw:
        raise ValueError('La entrada necesita al menos una búsqueda en «busquedas».')
    if len(raw) > MAX_SEARCHES:
        raise ValueError(f'Como máximo {MAX_SEARCHES} búsquedas por corrida.')
    searches, ids = [], set()
    for n, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f'La búsqueda {n} no es un objeto.')
        operation = item.get('operacion', 'venta')
        if operation not in OPERATIONS:
            raise ValueError(f'Búsqueda {n}: operación desconocida «{operation}».')
        neighborhood = BARRIOS.get(key(item.get('barrio', '')))
        if neighborhood is None:
            raise ValueError(f'Búsqueda {n}: «{item.get("barrio")}» no es un barrio oficial de CABA.')
        currency = CURRENCIES[operation].get(str(item.get('moneda', 'USD')).strip().upper())
        if currency is None:
            raise ValueError(f'Búsqueda {n}: moneda no válida para {operation}.')
        search_id = item.get('id')
        if type(search_id) not in (int, str) or not str(search_id).strip() or search_id in ids:
            raise ValueError(f'Búsqueda {n}: falta un «id» único.')
        ids.add(search_id)
        searches.append({
            'id': search_id, 'operation': operation, 'neighborhood': neighborhood, 'currency': currency,
            'budget': _int(item.get('presupuesto'), 'presupuesto'),
            'min_area': _int(item.get('superficie', 1), 'superficie', maximum=2000),
            'rooms': _int(item.get('ambientes', 1), 'ambientes', maximum=20),
            'or_more': bool(item.get('ambientesOMas', False)),
        })
    return searches


def parse_input(raw):
    """Entrada completa del Actor, con valores por defecto prudentes."""
    if not isinstance(raw, dict):
        raise ValueError('La entrada debe ser un objeto JSON.')
    if raw.get('autorizacionConfirmada') is not True:
        raise ValueError('Falta «autorizacionConfirmada»: solo se capturan sitios con permiso de lectura.')
    sites = raw.get('sitios') or list(DEFAULT_SITES)
    unknown = [s for s in sites if s not in DEFAULT_SITES]
    if unknown:
        raise ValueError(f'Sitios no habilitados para el Actor: {", ".join(map(str, unknown))}.')
    return {
        'searches': parse_searches(raw.get('busquedas')),
        'sites': list(dict.fromkeys(sites)),
        'max_listings': _int(raw.get('maxAvisosPorSitio', 50), 'maxAvisosPorSitio', maximum=MAX_LISTINGS_PER_SITE),
        'alert_first': bool(raw.get('alertarPrimeraCorrida', False)),
    }


def _alert(listing, search):
    alert = {'operacion': search['operation'], 'busqueda': search['id'], 'aviso': listing['id'],
             'barrio': listing['neighborhood'], 'precio': listing['price'], 'moneda': listing['currency'],
             'precio_usd': listing['price'], 'expensas_ars': listing.get('expenses'),
             'superficie_m2': listing['covered_area'], 'ambientes': listing['rooms'], 'url': listing['url']}
    return {k: alert[k] for k in ALERT_FIELDS}


def run(config, seen, client=None, echo=print, workdir=None, now=None):
    """Corre una vez. `seen` es {operación: lista de IDs ya vistos o None si nunca corrió}.

    Devuelve los ítems del dataset (uno por búsqueda con avisos nuevos), el estado nuevo
    de IDs vistos por operación y un resumen de la corrida. Un sitio bloqueado no frena la
    corrida: queda `parcial`. Un fallo inesperado de una operación se informa como `error`
    y su estado de IDs vistos no se toca, para no perder avisos.
    """
    now = now or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    searches = config['searches']
    summary = {'fecha': now, 'estado': 'ok', 'error': None, 'busquedas': len(searches),
               'busquedas_con_avisos': 0, 'alertas': 0, 'operaciones': {}}
    items, new_seen = [], {}
    with tempfile.TemporaryDirectory() as temp:
        base = Path(workdir or temp)
        for operation in sorted({s['operation'] for s in searches}):
            previous = seen.get(operation)
            known = frozenset(previous or ())
            op = summary['operaciones'][operation] = {'linea_base': previous is None and not config['alert_first']}
            try:
                raw, log = run_capture(config['sites'], config['max_listings'], base / operation, client=client,
                                       known=known, echo=echo, operation=operation)
                listings, report = parse_listings(json.dumps(raw).encode(), 'avisos.json', CATALOGS[operation],
                                                  operation)
            except Exception as error:  # noqa: BLE001 - se informa en el resumen y en el estado de la corrida
                op['error'] = f'{type(error).__name__}: {error}'[:300]
                summary['estado'], summary['error'] = 'error', op['error']
                echo(f'{operation}: error · {op["error"]}')
                continue
            sites_status = {s: v['estado'] for s, v in log['sitios'].items()}
            if any(v != 'completo' for v in sites_status.values()) and summary['estado'] == 'ok':
                summary['estado'] = 'parcial'
            fresh = _fresh(listings, known)
            # Se guardan también los IDs descartados, para no volver a pedir su ficha en cada corrida.
            new_seen[operation] = sorted(known | {r['listing_id'] for r in raw})
            op.update(sitios=sites_status, leidos=report.read, validos=len(listings), descartados=report.discarded,
                      nuevos=len(fresh))
            if op['linea_base']:
                echo(f'{operation}: primera corrida, {len(new_seen[operation])} IDs quedan como línea de base')
                continue
            found_items = _search_items(operation, searches, fresh)
            items += found_items
            summary['busquedas_con_avisos'] += len(found_items)
            summary['alertas'] += sum(len(item['alertas']) for item in found_items)
    return items, new_seen, summary


def _fresh(listings, known):
    """Avisos que no estaban entre los vistos, sin repetir ID."""
    fresh, ids = [], set()
    for listing in listings:
        if listing['id'] not in known and listing['id'] not in ids:
            ids.add(listing['id'])
            fresh.append(listing)
    return fresh


def _search_items(operation, searches, fresh):
    """Un ítem por cada búsqueda de la operación que tiene avisos nuevos que la cumplen."""
    items = []
    for search in (s for s in searches if s['operation'] == operation):
        found = [_alert(l, search) for l in fresh if l['neighborhood'] == search['neighborhood']
                 and matches(l, search['budget'], search['min_area'], search['rooms'], search['currency'],
                             search['or_more'])]
        if found:
            summary_item, = group(found, [search])
            items.append({'operacion': operation, **summary_item, 'alertas': found})
    return items
