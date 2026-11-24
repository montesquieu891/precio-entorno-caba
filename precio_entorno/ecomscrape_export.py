"""Adapta localmente un JSON autorizado de EcomScrape para Zonaprop."""

import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

from precio_entorno.importing import BARRIOS, key
from precio_entorno.run_pilot import SOURCE, batch_stats, listing_link


def sale_prices(operations):
    """Precios de las operaciones de venta de un aviso."""
    return [price for operation in operations if key(operation['operation_type']['name']) == 'venta' for price in operation['prices']]


def barrio_of(node):
    """Barrio del primer nivel de la jerarquía de ubicación marcado como «barrio»."""
    while isinstance(node, dict):
        if key(node.get('label')) == 'barrio':
            return BARRIOS.get(key(node.get('name')))
        node = node.get('parent')
    return None


def adapt_export(rows, captured_at):
    if not isinstance(rows, list) or len(rows) > 50:
        raise ValueError('Se espera un JSON con hasta 50 filas del piloto.')
    capture = datetime.fromisoformat(captured_at).isoformat()
    listings = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            if key(row['real_estate_type']['name']) != 'departamentos' or row.get('units'):
                continue
            feature = row['main_features']
            if str(feature['c_f_t1']['value']) not in ('2', '2.0'):
                continue
            link = listing_link(urljoin('https://www.zonaprop.com.ar/', row['url']))
            if not link or link[0] != f"zonaprop.com.ar:{row['posting_id']}":
                continue
            prices = sale_prices(row['price_operation_types'])
            if not prices:
                continue
            price = next((p for p in prices if key(p.get('currency')) == 'usd'), prices[0])
            location = row['posting_location']
            barrio = barrio_of(location['location'])
            if barrio not in ('Caballito', 'Almagro'):
                continue
            geo = ((location.get('posting_geolocation') or {}).get('geolocation') or {})
            listings.append({
                'source': SOURCE, 'listing_id': link[0], 'url': link[1], 'captured_at': capture,
                'price': price.get('amount'), 'currency': price.get('currency'),
                'covered_area_m2': (feature.get('c_f_t101') or {}).get('value'),
                'total_area_m2': (feature.get('c_f_t100') or {}).get('value'),
                'rooms': 2, 'neighborhood': barrio, 'latitude': geo.get('latitude'),
                'longitude': geo.get('longitude'),
            })
        except (KeyError, TypeError, AttributeError, ValueError):
            continue
    return listings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--captured-at', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        rows = json.loads(args.input.read_text(encoding='utf-8-sig'))
        listings = adapt_export(rows, args.captured_at)
        stats = batch_stats(listings, len(rows))
        stats['filas_recibidas'] = stats.pop('detalles_recibidos')
        if args.output and stats['comparables_con_barrio']:
            with args.output.open('x', encoding='utf-8') as stream:
                json.dump(listings, stream, ensure_ascii=False, indent=2)
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0 if stats['comparables_con_barrio'] else 1
    except (OSError, ValueError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())

