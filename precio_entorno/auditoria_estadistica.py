"""Reproduce el benchmark de cinco familias y conserva evidencia auditable."""

import argparse
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.metrics import r2_score
from sklearn.model_selection import GroupKFold

from precio_entorno import benchmark_inmobiliario as bm

ROOT = Path(__file__).resolve().parents[1]


def shared_groups(a, b):
    """Cantidad de grupos que aparecen en las dos particiones."""
    return len(set(a['grupo']) & set(b['grupo']))


def verify_splits(data):
    checks = []
    seen = []
    for fold, (a, b) in enumerate(GroupKFold(5).split(data, groups=data['grupo']), 1):
        train, test = data.iloc[a], data.iloc[b]
        overlaps = shared_groups(train, test)
        inner = GroupKFold(3).split(train, groups=train['grupo'])
        inner_overlaps = [shared_groups(train.iloc[i], train.iloc[j]) for i, j in inner]
        if overlaps or any(inner_overlaps):
            raise ValueError('Se detectaron grupos compartidos entre particiones.')
        checks.append({'fold': fold, 'n_train': len(train), 'n_test': len(test),
                       'grupos_compartidos_externos': overlaps, 'grupos_compartidos_internos': inner_overlaps})
        seen.extend(b.tolist())
    if sorted(seen) != list(range(len(data))):
        raise ValueError('Las particiones externas no cubren cada fila exactamente una vez.')
    return checks


def summarize(oof, fits):
    reference = oof[oof['model'].eq('Mediana comparables')]
    rows = []
    for (model, scope), block in oof.groupby(['model', 'scope']):
        score = bm.scores(block).to_dict()
        fit = fits[fits['model'].eq(model) & fits['scope'].eq(scope)]
        low, high = bm.bootstrap_mae_delta(block, reference)
        train_mae = fit['mae_train'].mean() if 'mae_train' in fit and fit['mae_train'].notna().any() else None
        rows.append({'model': model, 'scope': scope, **score,
                     'r2': r2_score(block['precio_m2'], block['estimate']),
                     'mae_propiedad_igual_peso': block.groupby('grupo')['error'].apply(lambda x: x.abs().mean()).mean(),
                     'mae_train_media_folds': train_mae,
                     'brecha_mae': score['mae'] - train_mae if train_mae is not None else None,
                     'mae_fold_sd': block['error'].abs().groupby(block['fold']).mean().std(),
                     'delta_mae_vs_comparables': score['mae'] - bm.scores(reference)['mae'],
                     'delta_ic95_low': low, 'delta_ic95_high': high})
    return pd.DataFrame(rows).sort_values(['scope', 'mae']).reset_index(drop=True)


def run(bundle_path, output, evidence):
    started = time.perf_counter()
    data = bm.load_sales(bundle_path)
    checks = verify_splits(data)
    oof, fits, _ = bm.benchmark(data, include_references=True, explain=False,
                               progress=lambda s: print(s, flush=True))
    if oof.duplicated(['model', 'scope', 'row']).any():
        raise ValueError('Hay predicciones externas repetidas.')
    if not oof.groupby(['model', 'scope'])['row'].nunique().eq(len(data)).all():
        raise ValueError('Los modelos no cubren las mismas observaciones.')
    if not np.isfinite(oof['estimate']).all() or not oof['estimate'].gt(0).all():
        raise ValueError('Hay predicciones no positivas o no finitas.')
    summary = summarize(oof, fits)
    output.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    oof.to_csv(output / 'predicciones_oof.csv', index=False)
    fits.to_csv(output / 'ajustes.csv', index=False)
    fits.to_csv(evidence / 'ajustes.csv', index=False)
    summary.to_csv(evidence / 'resumen.csv', index=False)
    for col in ['agency', 'neighborhood']:
        blocks = oof.groupby(['model', 'scope', col])
        table = pd.DataFrame([{'model': m, 'scope': s, col: value, **bm.scores(block).to_dict()} for (m, s, value), block in blocks])
        table.to_csv(evidence / f'por_{col}.csv', index=False)
    families = list(bm.model_specs(False))
    best = summary[summary['model'].isin(families)].sort_values('mae').iloc[0]
    manifest = {
        'fecha_utc': datetime.now(timezone.utc).isoformat(),
        'versiones': {'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__,
                     'scipy': scipy.__version__, 'sklearn': sklearn.__version__},
        'datos': {'avisos': len(data), 'grupos': int(data['grupo'].nunique()),
                  'barrios': int(data['neighborhood'].nunique()),
                  'sha256_bundle': hashlib.sha256(bundle_path.read_bytes()).hexdigest()},
        'codigo_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [Path(bm.__file__), Path(__file__)]},
        'familias': families, 'objetivo_ajuste': 'log(precio_publicado_usd_por_m2_cubierto)',
        'criterio_seleccion': 'MAE en USD/m² en validación interna agrupada de tres folds',
        'particiones': checks, 'semilla_estimadores': bm.SEED, 'bootstrap_grupos_repeticiones': 600,
        'configuraciones': {scope: {name: {'parametros': {k: repr(v) for k, v in model.get_params().items()},
                                          'busqueda': grid}
                                     for name, (model, grid) in bm.model_specs(extended).items()}
                            for scope, extended in [('base', False), ('edificio', True)]},
        'mejor_observado': {'model': best['model'], 'scope': best['scope'], 'mae': float(best['mae'])},
        'segundos_totales': time.perf_counter() - started,
        'alcance': 'Validación anidada dentro de una captura. La elección de familia sobre OOF requiere confirmación futura.',
        'predicciones_oof_sha256': hashlib.sha256((output / 'predicciones_oof.csv').read_bytes()).hexdigest(),
    }
    (evidence / 'manifiesto.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    display = summary[['model', 'scope', 'mae', 'rmse', 'r2', 'mdape_pct', 'mae_fold_sd']].copy()
    columns = list(display.columns)
    lines = ['# Benchmark auditado de cinco modelos', '',
             'Resultados externos por aviso; pérdidas en USD/m² de publicación. Dos escenarios y tres referencias.', '',
             '| ' + ' | '.join(columns) + ' |', '| ' + ' | '.join(['---'] * len(columns)) + ' |']
    for row in display.itertuples(index=False, name=None):
        lines.append('| ' + ' | '.join(f'{v:.3f}' if isinstance(v, (float, np.floating)) else str(v) for v in row) + ' |')
    lines += ['', 'El desvío entre folds no es un intervalo de confianza. Los intervalos emparejados condicionales '
              'a errores OOF están en resumen.csv. Los ajustes y advertencias se conservan en ajustes.csv.',
              '', 'No mezclar estas métricas con la evaluación 80/20 del prototipo operativo: usan otra especificación.']
    (evidence / 'resultados.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(display.to_string(index=False), flush=True)
    return summary, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=bm.BUNDLE)
    parser.add_argument('--salida', type=Path, default=ROOT / 'data/processed/auditoria-estadistica')
    parser.add_argument('--evidencia', type=Path, default=ROOT / 'reports/benchmark-auditado')
    args = parser.parse_args()
    run(args.bundle, args.salida, args.evidencia)


if __name__ == '__main__':
    main()
