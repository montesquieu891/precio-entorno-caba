"""Importa un catálogo autorizado de alquileres mensuales de cocheras en JSON."""

import argparse
import json
import math
import os
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .importing import BARRIOS, key

DEFAULT = Path(__file__).resolve().parents[1] / 'data/local/cocheras.json'


def validate(rows):
    if not isinstance(rows, list):
        raise ValueError('El catálogo debe ser una lista de avisos.')
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Cada aviso debe ser un objeto JSON.')
        item = {name: row[name] for name in ('id', 'fuente', 'barrio', 'precio', 'moneda', 'url', 'capturado')}
        item['barrio'] = BARRIOS[key(item['barrio'])]
        if not all(isinstance(item[k], str) and item[k].strip() for k in ('id', 'fuente', 'url')):
            raise ValueError('ID, fuente y enlace son obligatorios.')
        if item['moneda'] not in ('ARS', 'USD') or row.get('periodicidad') != 'mensual':
            raise ValueError('Se requiere precio mensual en ARS o USD.')
        price = item['precio']
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            raise ValueError('Precio inválido.')
        url = urlparse(item['url'])
        if url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password:
            raise ValueError('Enlace inválido.')
        datetime.fromisoformat(item['capturado'].replace('Z', '+00:00'))
        item['periodicidad'] = 'mensual'
        item['expensas'] = row.get('expensas')
        item['moneda_expensas'] = row.get('moneda_expensas')
        expenses = item['expensas']
        if expenses is not None:
            if (type(expenses) not in (int, float) or not math.isfinite(expenses) or expenses < 0
                    or item['moneda_expensas'] not in ('ARS', 'USD')):
                raise ValueError('Expensas inválidas o moneda faltante.')
        elif item['moneda_expensas'] is not None:
            raise ValueError('La moneda de expensas requiere un importe.')
        item['direccion'] = str(row.get('direccion') or '')
        item['lat'], item['lon'] = row.get('lat'), row.get('lon')
        lat, lon = item['lat'], item['lon']
        if lat is not None or lon is not None:
            if not (type(lat) in (int, float) and type(lon) in (int, float)
                    and -34.73 <= lat <= -34.52 and -58.54 <= lon <= -58.32):
                raise ValueError('Coordenadas incompletas o fuera de CABA.')
        identity = (item['fuente'], item['id'])
        if identity in result and result[identity] != item:
            raise ValueError('Dos filas contradictorias para el mismo aviso.')
        result[identity] = item
    return list(result.values())


def load(path=DEFAULT):
    return validate(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archivo', type=Path)
    parser.add_argument('--destino', type=Path, default=DEFAULT)
    args = parser.parse_args()
    rows = validate(json.loads(args.archivo.read_text(encoding='utf-8-sig')))
    args.destino.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.destino.parent,
                                         delete=False) as output:
            temporary = Path(output.name)
            json.dump(rows, output, ensure_ascii=False, allow_nan=False)
        os.replace(temporary, args.destino)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    print(f'{len(rows)} cocheras importadas.')


if __name__ == '__main__':
    main()
