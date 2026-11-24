"""Une varias capturas de un mismo catálogo en una sola carpeta para el análisis.

Cada carpeta de entrada tiene un `avisos.json` y, si existe, un `registro.json`. La
salida tiene los avisos sin IDs repetidos (se conserva la primera aparición), un
registro con los sitios de cada captura y los posibles duplicados entre fuentes:
la misma propiedad publicada por una inmobiliaria y por un portal.
"""

import argparse
import json
from pathlib import Path

from precio_entorno.inmobiliarias import possible_duplicates


def add_counts(target, counts):
    """Suma cada conteo al acumulado del mismo motivo."""
    for reason, count in counts.items():
        target[reason] = target.get(reason, 0) + count


def add_unseen(listings, seen, items):
    """Agrega los avisos cuyo ID todavía no apareció, en el orden en que llegan."""
    for item in items:
        if item['listing_id'] not in seen:
            seen.add(item['listing_id'])
            listings.append(item)


def site_entries(log):
    """Sitios de un registro. Las capturas de Apify se resumen por corridas."""
    if 'sitios' in log:
        return log['sitios']
    if 'corridas' in log:
        omitted = {}
        for run in log['corridas']:
            add_counts(omitted, run.get('omitidos') or {})
        return {'zonaprop': {'estado': 'completo', 'avisos': sum(r.get('avisos', 0) for r in log['corridas']),
                             'omitidos': omitted, 'pedidos': len(log['corridas'])}}
    return {}


def merge_sites(target, entries):
    for site, entry in entries.items():
        if site not in target:
            target[site] = dict(entry, omitidos=dict(entry.get('omitidos') or {}))
            continue
        merged = target[site]
        merged['avisos'] = merged.get('avisos', 0) + entry.get('avisos', 0)
        merged['pedidos'] = (merged.get('pedidos') or 0) + (entry.get('pedidos') or 0)
        add_counts(merged['omitidos'], entry.get('omitidos') or {})
        if 'segundos' in merged or 'segundos' in entry:
            merged['segundos'] = (merged.get('segundos') or 0) + (entry.get('segundos') or 0)


def consolidate(folders, out):
    listings, seen, sites, captures = [], set(), {}, []
    for folder in map(Path, folders):
        add_unseen(listings, seen, json.loads((folder / 'avisos.json').read_text(encoding='utf-8')))
        log_path = folder / 'registro.json'
        log = json.loads(log_path.read_text(encoding='utf-8')) if log_path.exists() else {}
        merge_sites(sites, site_entries(log))
        captures.append({'carpeta': folder.name, 'catalogo': log.get('catalogo'), 'captura': log.get('captura')})
    catalogs = {c['catalogo'] for c in captures if c['catalogo']}
    if len(catalogs) > 1:
        raise ValueError(f'Las capturas son de catálogos distintos: {sorted(catalogs)}.')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    log = {'catalogo': catalogs.pop() if catalogs else None, 'capturas': captures, 'sitios': sites,
           'avisos': len(listings),
           'posibles_duplicados_entre_inmobiliarias': possible_duplicates(
               [dict(x, agency=x.get('agency') or x['listing_id'].split(':')[0]) for x in listings])}
    (out / 'avisos.json').write_text(json.dumps(listings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'registro.json').write_text(json.dumps(log, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return listings, log


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('capturas', type=Path, nargs='+', help='Carpetas con avisos.json')
    parser.add_argument('--salida', type=Path, required=True)
    args = parser.parse_args()
    try:
        listings, log = consolidate(args.capturas, args.salida)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'Error: {error}\n')
    print(json.dumps({'avisos': len(listings), 'sitios': {k: v.get('avisos') for k, v in log['sitios'].items()},
                      'posibles_duplicados': len(log['posibles_duplicados_entre_inmobiliarias'])},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
