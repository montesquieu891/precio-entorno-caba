"""Figuras de diagnóstico a partir de predicciones externas ya calculadas."""

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'reports/benchmark-auditado'
OUTPUT = ROOT / 'docs/img/auditoria-estadistica'


def main():
    manifest = json.loads((EVIDENCE / 'manifiesto.json').read_text(encoding='utf-8'))
    predictions = ROOT / 'data/processed/auditoria-estadistica/predicciones_oof.csv'
    if hashlib.sha256(predictions.read_bytes()).hexdigest() != manifest['predicciones_oof_sha256']:
        raise ValueError('Las predicciones no coinciden con la corrida auditada.')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    oof = pd.read_csv(predictions)
    table = pd.read_csv(EVIDENCE / 'resumen.csv')
    families = manifest['familias']
    chosen = manifest['mejor_observado']
    rows = oof[oof['model'].eq(chosen['model']) & oof['scope'].eq(chosen['scope'])]
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.7), constrained_layout=True)
    ax = axes[0]
    ax.scatter(rows['precio_m2'], rows['estimate'], s=9, alpha=.16, color='#255c99', rasterized=True)
    lo = min(rows['precio_m2'].min(), rows['estimate'].min())
    hi = max(rows['precio_m2'].max(), rows['estimate'].max())
    ax.plot([lo, hi], [lo, hi], color='#a34a28', linestyle='--', label='Referencia perfecta')
    ax.set(xscale='log', yscale='log', xlabel='Publicado (USD/m²; eje log)',
           ylabel='Predicción externa (USD/m²; eje log)', title='Observado y predicho · todas las filas')
    ax.legend(frameon=False)
    ax = axes[1]
    ax.scatter(rows['estimate'], rows['error'], s=9, alpha=.16, color='#255c99', rasterized=True)
    ax.axhline(0, color='#a34a28', linestyle='--')
    ax.set(xscale='log', xlabel='Predicción externa (USD/m²; eje log)', ylabel='Predicho − publicado (USD/m²)',
           title='Residuos externos · todas las filas')
    fig.suptitle(f"{chosen['model']} · {chosen['scope']} · {len(rows):,} predicciones OOF", fontsize=13)
    fig.savefig(OUTPUT / 'diagnostico_oof.png', dpi=170)
    plt.close(fig)

    selected = table[(table['model'].isin(families) & table['scope'].eq('edificio'))
                     | table['scope'].eq('referencia')].sort_values('mae', ascending=False)
    fig, ax = plt.subplots(figsize=(9, 4.8), constrained_layout=True)
    colors = ['#718096' if s == 'referencia' else '#255c99' for s in selected['scope']]
    ax.barh(selected['model'], selected['mae'], color=colors)
    for i, value in enumerate(selected['mae']):
        ax.text(value + 7, i, f'{value:.1f}', va='center')
    ax.set(xlim=(0, selected['mae'].max() * 1.14), xlabel='MAE externo por aviso (USD/m²)',
           title='Cinco modelos con edificio y dos referencias simples')
    fig.savefig(OUTPUT / 'comparacion_mae.png', dpi=170)
    plt.close(fig)
    print('Figuras guardadas en', OUTPUT)


if __name__ == '__main__':
    main()
