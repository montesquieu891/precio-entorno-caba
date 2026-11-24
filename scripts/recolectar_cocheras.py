"""Recopila candidatos de cocheras con los clientes autorizados del proyecto."""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from precio_entorno.inmobiliarias import (
    PoliteClient, C21_SEARCH, rsc_text, barrio, coordinate, number,
    MIG_SEARCH, MIG_BASE, parse_migliorisi_list, parse_migliorisi_detail,
)


def century21_page(client, decoder, page, captured, rows):
    """Lee una página del listado de cocheras en alquiler de Century 21 y devuelve los IDs que trae."""
    html = client.get(C21_SEARCH, {'loc': 'r|CABA||', 'op': 'rent', 'type': 'cochera', 'page': page})
    links = {path.rsplit('-', 1)[-1]: 'https://century21.com.ar' + path for path in re.findall(r'href="(/propiedades/[^\"]+)"', html)}
    text = rsc_text(html)
    current = set()
    for match in re.finditer(r'\{"property_id":', text):
        try:
            item, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        pid = str(item.get('property_id'))
        current.add(pid)
        if item.get('prop_type') != 'cochera' or item.get('operation_type') != 'rent' or item.get('status') != 'active':
            continue
        name = barrio(item.get('addr_neighborhood')) or barrio(item.get('addr_district'))
        price = None if item.get('price_hidden') else number(item.get('price'))
        if not name or not price:
            continue
        rows['century21:' + pid] = dict(id=pid, fuente='Century 21', barrio=name, precio=price,
            moneda=item.get('currency_id'), url=links.get(pid) or item.get('property_url'), capturado=captured,
            direccion='' if item.get('addr_hidden') else str(item.get('addr_street') or '') + ' ' + str(item.get('addr_number') or ''),
            lat=coordinate(item.get('geo_lat')), lon=coordinate(item.get('geo_lon')),
            periodicidad=None, expensas=None, pendiente='Verificar periodicidad y expensas')
    return current


def collect_century21(client, decoder, captured, rows):
    """Recorre hasta 30 páginas y se detiene cuando una página no trae IDs nuevos."""
    seen = set()
    stopped_without_new = False
    for page in range(1, 31):
        current = century21_page(client, decoder, page, captured, rows)
        if not current - seen:
            stopped_without_new = True
            break
        seen.update(current)
    return dict(fuente='Century 21', paginas=page,
                estado='sin nuevos identificadores' if stopped_without_new else 'límite de páginas alcanzado',
                limite_paginas=30)


def migliorisi_cards(client, cards, seen, captured, rows):
    """Lee la ficha de cada tarjeta que parece una cochera y guarda las de alquiler con barrio y precio."""
    for path, code, title in cards:
        if code in seen or not re.search(r'cochera|garage|garaje', title + ' ' + path, re.I):
            continue
        seen.add(code)
        detail = client.get(MIG_BASE + path)
        item, rental, _ = parse_migliorisi_detail(detail, path, code, title, captured, 'alquiler')
        if rental and item.get('neighborhood') and item.get('price'):
            rows['migliorisi:' + code] = dict(id=code, fuente='Migliorisi', barrio=item['neighborhood'],
                precio=item['price'], moneda=item['currency'], url=MIG_BASE + path, capturado=captured,
                periodicidad=None, expensas=item.get('expenses'), moneda_expensas='ARS' if item.get('expenses') is not None else None,
                lat=None, lon=None, pendiente='Verificar periodicidad y ubicación')


def collect_migliorisi(client, captured, rows):
    """Recorre los listados de alquiler de Migliorisi, hasta 30 páginas."""
    last, page, seen = 1, 1, set()
    while page <= min(last, 30):
        cards, last = parse_migliorisi_list(client.get(MIG_SEARCH.format(op='2/0', page=page)))
        migliorisi_cards(client, cards, seen, captured, rows)
        page += 1
    return dict(fuente='Migliorisi', paginas=page - 1, paginas_publicadas=last,
                estado='recorrido terminado' if last <= 30 else 'límite de páginas alcanzado', limite_paginas=30)


def main():
    captured = datetime.now(timezone.utc).isoformat()
    folder = Path(__file__).resolve().parents[1] / 'data/raw' / ('cocheras-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    folder.mkdir(parents=True)
    rows, runs = {}, []
    client = PoliteClient()
    try:
        runs.append(collect_century21(client, json.JSONDecoder(), captured, rows))
    except Exception as error:
        runs.append(dict(fuente='Century 21', estado='parcial', error=str(error)[:300]))
    try:
        runs.append(collect_migliorisi(client, captured, rows))
    except Exception as error:
        runs.append(dict(fuente='Migliorisi', estado='parcial', error=str(error)[:300]))
    for filename, content in [('candidatos.json', list(rows.values())), ('registro.json', runs)]:
        (folder / filename).write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(candidatos=len(rows), carpeta=str(folder), fuentes=runs), ensure_ascii=True))


if __name__ == '__main__':
    main()
