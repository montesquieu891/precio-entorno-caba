"""Convierte datasets oficiales de Buenos Aires Data en puntos para el modelo.

Fuentes (licencia CC-BY 2.5 AR, data.buenosaires.gob.ar):
- Espacios Verdes Públicos: polígonos en WGS84. Para la distancia al parque se usan
  los vértices de plazas, parques, jardines y paseos; se excluyen canteros
  centrales, plazoletas y patios.
- Establecimientos Educativos y Hospitales: puntos en la proyección local
  EPSG:9498, que se convierten a latitud y longitud.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARK_CLASSES = {'PLAZA', 'PARQUE', 'PARQUE SEMIPÚBLICO', 'JARDÍN', 'JARDÍN BOTÁNICO', 'PASEO'}
SOURCES = {
    'parques': 'espacio_verde_publico.geojson',
    'escuelas': 'establecimientos_educativos.geojson',
    'hospitales': 'hospitales.geojson',
}


def rings(geometry):
    if geometry['type'] == 'Polygon':
        return geometry['coordinates']
    if geometry['type'] == 'MultiPolygon':
        return [ring for polygon in geometry['coordinates'] for ring in polygon]
    return []


def parks(collection):
    points, kept = [], 0
    for feature in collection['features']:
        if (feature['properties'].get('clasificac') or '').upper() not in PARK_CLASSES or not feature.get('geometry'):
            continue
        kept += 1
        name = feature['properties'].get('nombre')
        points += [{'name': name, 'lat': lat, 'lon': lon} for ring in rings(feature['geometry']) for lon, lat in ring]
    return points, kept


def projected_points(collection, transformer):
    out = []
    for feature in collection['features']:
        geometry = feature.get('geometry')
        if not geometry or geometry['type'] != 'Point':
            continue
        x, y = geometry['coordinates'][:2]
        lon, lat = transformer.transform(x, y)
        out.append({'name': feature['properties'].get('nam'), 'lat': round(lat, 7), 'lon': round(lon, 7)})
    return out


def convert(source, target):
    from pyproj import Transformer
    transformer = Transformer.from_crs('EPSG:9498', 'EPSG:4326', always_xy=True)
    target.mkdir(parents=True, exist_ok=True)
    log = []
    for name, file in SOURCES.items():
        collection = json.loads((source / file).read_text(encoding='utf-8'))
        if name == 'parques':
            points, features = parks(collection)
        else:
            points = projected_points(collection, transformer)
            features = len(points)
        (target / f'{name}.json').write_text(json.dumps(points, ensure_ascii=False) + '\n', encoding='utf-8')
        log.append({'nombre': name, 'fuente': file, 'elementos': features, 'puntos': len(points),
                    'max_items': None, 'licencia': 'CC-BY 2.5 AR · Buenos Aires Data'})
    (target / 'corridas.json').write_text(json.dumps(log, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return log


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--origen', type=Path, default=ROOT / 'data/raw/badata-poi')
    parser.add_argument('--destino', type=Path, default=ROOT / 'data/processed/poi-badata')
    args = parser.parse_args()
    print(json.dumps(convert(args.origen, args.destino), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
