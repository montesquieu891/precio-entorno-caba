"""Prepara muestras y un paquete local de entrega, sin conexiones externas."""

import csv
import hashlib
import io
import json
import subprocess
import zipfile
from collections import Counter, defaultdict, deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/entrega-12-11'
BUNDLE = ROOT / 'data/processed/eda-colab/eda_bundle.zip'
SALE_FIELDS = ('id', 'captured_at', 'neighborhood', 'price', 'currency',
               'covered_area', 'rooms', 'precio_m2', 'agency', 'grupo')
CRIME_FIELDS = ('barrio', 'mes', 'filas_validas', 'robos', 'hurtos', 'amenazas',
                'lesiones_dolosas', 'homicidios_dolosos', 'total_delitos', 'siniestros_viales')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(name, rows, fields):
    path = OUT / name
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    return path


def take_round(queues, selected, limit):
    """Una ronda: toma el siguiente aviso de cada barrio, en orden alfabético, hasta llegar al límite."""
    for queue in queues.values():
        if queue and len(selected) < limit:
            selected.append(queue.popleft())


def main():
    with zipfile.ZipFile(BUNDLE) as bundle:
        sale = list(csv.DictReader(io.StringIO(bundle.read('venta.csv').decode('utf-8-sig'))))
        crimes = list(csv.DictReader(io.StringIO(bundle.read('delitos/barrio_mes.csv').decode('utf-8-sig'))))
    # Una observación por grupo aproximado. El ID menor elige el representante de forma estable.
    representatives = {}
    for row in sorted(sale, key=lambda item: item['id']):
        representatives.setdefault(row['grupo'] or row['id'], row)
    neighborhoods = defaultdict(list)
    for row in representatives.values():
        neighborhoods[row['neighborhood']].append(row)
    queues = {}
    for neighborhood, rows in sorted(neighborhoods.items()):
        queues[neighborhood] = deque(sorted(rows, key=lambda row: hashlib.sha256(
            ('entrega-12-11-v1|' + row['id']).encode()).hexdigest()))
    selected = []
    while len(selected) < 1800 and any(queues.values()):
        take_round(queues, selected, 1800)
    if len(selected) != 1800 or len({row['grupo'] or row['id'] for row in selected}) != 1800:
        raise ValueError('Se requieren 1.800 grupos distintos para la muestra de venta.')
    keys = {(row['barrio'], row['mes']) for row in crimes}
    if len(crimes) != 1152 or len(keys) != 1152 or len({row['barrio'] for row in crimes}) != 48:
        raise ValueError('Se requieren 48 barrios por 24 meses sin claves repetidas.')
    OUT.mkdir(parents=True, exist_ok=True)
    sale_path = write_csv('avisos_venta_1800.csv', selected, SALE_FIELDS)
    crime_path = write_csv('delitos_barrio_mes_1152.csv', crimes, CRIME_FIELDS)
    prices = sorted(float(row['precio_m2']) for row in selected)
    counts = Counter(row['neighborhood'] for row in selected)
    manifest = {
        'fecha_revision': '2026-11-10',
        'hito': '2026-11-12',
        'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'fuente_local': str(BUNDLE.relative_to(ROOT)), 'sha256_fuente': sha256(BUNDLE),
        'venta': {
            'filas_origen': len(sale), 'grupos_origen': len(representatives), 'filas': len(selected),
            'columnas': list(SALE_FIELDS), 'por_barrio': dict(sorted(counts.items())),
            'capturas': sorted({row['captured_at'] for row in selected}),
            'seleccion': 'Un representante por grupo aproximado, menor ID. Orden SHA-256 con '
                         'prefijo entrega-12-11-v1. Rondas por barrio alfabético hasta 1.800.',
            'sesgo': 'Muestra balanceada por barrio. No estima la distribución de oferta del mercado.',
            'mediana_usd_m2': (prices[899] + prices[900]) / 2,
            'faltantes_por_campo': {field: sum(not row[field] for row in selected) for field in SALE_FIELDS},
        },
        'delitos': {
            'filas': len(crimes), 'columnas': list(CRIME_FIELDS), 'barrios': 48,
            'meses': sorted({row['mes'] for row in crimes}),
            'faltantes_por_campo': {field: sum(not row[field] for row in crimes) for field in CRIME_FIELDS},
            'unidad': 'barrio oficial y mes, enero 2024 a diciembre 2025',
            'limite': 'Serie histórica de contexto. Revisar cambios entre ediciones antes de comparar años. '
                      'Para cruzar con avisos de 2026 se utiliza 2025, con desfase explícito.',
        },
        'archivos': {path.name: sha256(path) for path in (sale_path, crime_path)},
    }
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    files = [ROOT / 'README.md', ROOT / 'requirements.txt', ROOT / '.dockerignore',
             ROOT / 'notebooks/eda_oportunidades.ipynb', Path(__file__),
             *sorted(path for path in (ROOT / '.actor').glob('*') if path.is_file()),
             *sorted((ROOT / 'precio_entorno').glob('*.py')), *sorted((ROOT / 'tests').glob('*.py')),
             *sorted((ROOT / 'tests').glob('*.cjs')), *sorted((ROOT / 'web').glob('*.*')),
             *sorted((ROOT / 'data/fixtures').glob('*.*')),
             *sorted((ROOT / 'docs').rglob('*.md')), *sorted((ROOT / 'docs/img').rglob('*.png')),
             *sorted((ROOT / 'docs/plantillas').glob('*.csv')),
             sale_path, crime_path, OUT / 'manifest.json', ROOT / 'data/processed/etl/reporte.json']
    evidence = OUT / 'verificacion.json'
    if evidence.exists():
        files.append(evidence)
    archive = OUT / 'precio-entorno-entrega-12-11.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(ROOT).as_posix())
    print(json.dumps({'paquete': str(archive.relative_to(ROOT)), 'venta': len(selected),
                      'delitos': len(crimes), 'barrios': len(counts),
                      'minimo_por_barrio': min(counts.values()), 'maximo_por_barrio': max(counts.values()),
                      'mediana_usd_m2': manifest['venta']['mediana_usd_m2']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
