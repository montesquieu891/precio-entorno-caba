"""Completa los rasgos de la descripción de los avisos de RE/MAX y Migliorisi que ya están en la base.

Las capturas nuevas ya los leen. Este comando pide la ficha de cada aviso guardado que todavía no los
tiene, con el mismo cliente educado de la captura, y guarda solo los rasgos, nunca el texto. El resultado
queda en una carpeta de `data/raw/` y se suma a la base sin pisar datos que ya estén.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from precio_entorno.actualizar import BASES
from precio_entorno.descripcion import ACCESS_FIELDS, DESCRIPTION_FIELDS
from precio_entorno.importing import parse_listings
from precio_entorno.inmobiliarias import (
    CATALOGS, DEFAULT_PAUSE_S, Blocked, PoliteClient, migliorisi_traits, remax_traits)
from precio_entorno.store import Store

ROOT = Path(__file__).resolve().parents[1]
SITES = ('remax', 'migliorisi')


def raw_folders(operation, raw=None):
    suffix = '' if operation == 'venta' else f'-{operation}'
    return sorted(Path(raw or ROOT / 'data/raw').glob(f'inmobiliarias{suffix}-2*/avisos.json'))


def pending(store, operation, raw=None, sites=SITES, fields=None):
    """Último registro crudo de cada aviso de la base que todavía no tiene rasgos.

    Con `fields`, solo los avisos vigentes a los que les falta alguno de esos rasgos: sirve para completar
    rasgos sumados después (los de accesibilidad) sin pedir fichas de avisos dados de baja.
    """
    if fields:
        missing = {row['id'] for row in store.listings()
                   if row['id'].split(':', 1)[0] in sites and any(row[c] is None for c in fields)}
    else:
        missing = {row['id'] for row in store.listings(include_inactive=True)
                   if row['id'].split(':', 1)[0] in sites and row[DESCRIPTION_FIELDS[0]] is None}
    latest = {}
    items = [item for path in raw_folders(operation, raw) for item in json.loads(path.read_text(encoding='utf-8'))]
    for item in items:
        if item.get('listing_id') in missing:
            latest[item['listing_id']] = item
    return [latest[i] for i in sorted(latest)]


def read_traits(client, item):
    if item['agency'] == 'remax':
        return remax_traits(client, item['url'])
    return migliorisi_traits(client.get(item['url']))


def complete(operation, out, client=None, base=None, raw=None, echo=print, limit=None, fields=None, sites=SITES):
    """Devuelve el registro de la corrida: avisos leídos, sin descripción, con error y completados.

    Una corrida anterior en la misma carpeta se conserva y se suma a la base antes de seguir, así que
    una corrida cortada se puede retomar sin volver a pedir lo ya leído.
    """
    store = Store(Path(base or BASES[operation]))
    client = client or PoliteClient()
    out.mkdir(parents=True, exist_ok=True)
    path = out / 'avisos.json'
    done = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    log = {'operacion': operation, 'pendientes': 0, 'con_rasgos': 0, 'sin_descripcion': 0, 'errores': 0,
           'estado': 'completo', 'completados_en_base': 0}

    def save():
        path.write_text(json.dumps(done, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        listings, _ = parse_listings(json.dumps(done).encode(), path.name, CATALOGS[operation], operation)
        log['completados_en_base'] += store.complete_details(listings) if listings else 0

    if done:
        save()
    items = pending(store, operation, raw, sites, fields)[:limit]
    log['pendientes'] = len(items)
    for n, item in enumerate(items, 1):
        try:
            found = read_traits(client, item)
        except Blocked as error:
            log['estado'] = f'detenido: {error}'
            break
        except (RuntimeError, ValueError, KeyError):
            log['errores'] += 1
            continue
        if not found or found[DESCRIPTION_FIELDS[0]] is None:
            log['sin_descripcion'] += 1
            continue
        done.append({**item, **found})
        log['con_rasgos'] += 1
        if n % 50 == 0:
            echo(f'{n}/{len(items)} · {log["con_rasgos"]} con rasgos')
            save()  # Se guarda a medida que avanza, por si la corrida se corta.
    save()
    (out / 'registro.json').write_text(json.dumps(log, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return log


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--operacion', choices=sorted(CATALOGS), default='venta')
    parser.add_argument('--pausa-s', type=float, default=DEFAULT_PAUSE_S)
    parser.add_argument('--max-avisos', type=int, help='Tope de fichas a pedir')
    parser.add_argument('--salida', type=Path)
    parser.add_argument('--sitios', nargs='+', choices=SITES, default=list(SITES))
    parser.add_argument('--solo-accesibilidad', action='store_true',
                        help='Completa solo los rasgos de accesibilidad (ascensor, sin ascensor, sin escalones) '
                             'de los avisos vigentes')
    parser.add_argument('--autorizacion-confirmada', action='store_true',
                        help='Confirma que cada inmobiliaria autorizó por escrito la lectura de su sitio')
    args = parser.parse_args()
    if not args.autorizacion_confirmada:
        parser.exit(1, 'Error: falta --autorizacion-confirmada.\n')
    if args.pausa_s < 2:
        parser.exit(1, 'Error: la pausa mínima entre pedidos es de 2 segundos.\n')
    suffix = '' if args.operacion == 'venta' else f'-{args.operacion}'
    kind = 'accesibilidad' if args.solo_accesibilidad else 'inmobiliarias'
    out = args.salida or ROOT / f'data/raw/rasgos-{kind}{suffix}-{datetime.now():%Y%m%d}'
    log = complete(args.operacion, out, PoliteClient(pause_s=args.pausa_s), limit=args.max_avisos,
                   echo=lambda line: print(line, flush=True),
                   fields=ACCESS_FIELDS if args.solo_accesibilidad else None, sites=tuple(args.sitios))
    print(json.dumps(log, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
