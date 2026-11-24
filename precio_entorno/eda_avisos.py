"""Análisis exploratorio de una captura del catálogo de avisos.

Aplica las mismas reglas de validación que la app y describe calidad, cobertura,
oferta por barrio según los filtros de la persona y precios publicados. Son precios
de publicación, no tasaciones ni precios de cierre.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from precio_entorno.importing import parse_listings
from precio_entorno.matching import compare_neighborhoods

ROOT = Path(__file__).resolve().parents[1]
FOCUS = ('Caballito', 'Almagro', 'Villa Crespo', 'Flores')
BUDGETS = (80_000, 100_000, 120_000, 150_000, 200_000, 300_000)
MIN_N = 15


def load(folder, catalog):
    """Devuelve los avisos válidos, el reporte de validación y el registro de la captura."""
    folder = Path(folder)
    content = (folder / 'avisos.json').read_bytes()
    raw = pd.DataFrame(json.loads(content))
    valid, report = parse_listings(content, 'avisos.json', catalog)
    df = pd.DataFrame(valid)
    df['agency'] = df['id'].str.split(':').str[0]
    df['precio_m2'] = df['price'] / df['covered_area']
    df['con_coordenadas'] = df['latitude'].notna() & df['longitude'].notna()
    log_path = folder / 'registro.json'
    log = json.loads(log_path.read_text(encoding='utf-8')) if log_path.exists() else {}
    return raw, df, report, log


def quality(raw, df, report, log):
    sites = log.get('sitios', {})
    rows = []
    for agency, captured in raw.groupby('agency').size().items():
        valid = df[df['agency'] == agency]
        site = sites.get(agency, {})
        rows.append({
            'inmobiliaria': agency,
            'omitidos_por_alcance': sum(site.get('omitidos', {}).values()),
            'capturados': int(captured),
            'validos': len(valid),
            'pct_validos': round(len(valid) / captured * 100, 1),
            'con_coordenadas': int(valid['con_coordenadas'].sum()),
            'barrios': int(valid['neighborhood'].nunique()),
            'pedidos': site.get('pedidos'),
            'segundos_por_aviso_valido': round(site['segundos'] / len(valid), 2)
            if site.get('segundos') and len(valid) else None,
        })
    table = pd.DataFrame(rows).set_index('inmobiliaria')
    fields = sorted(set(report.missing) | set(report.invalid))
    missing = pd.DataFrame({'faltantes': [report.missing[f] for f in fields],
                            'invalidos': [report.invalid[f] for f in fields]}, index=pd.Index(fields, name='campo'))
    return table, missing


def by_neighborhood(df):
    g = df.groupby('neighborhood')
    table = pd.DataFrame({
        'avisos': g.size(),
        'precio_mediano_usd': g['price'].median().round(-3),
        'precio_p25_usd': g['price'].quantile(.25).round(-3),
        'precio_p75_usd': g['price'].quantile(.75).round(-3),
        'usd_m2_mediano': g['precio_m2'].median().round(0),
        'usd_m2_p25': g['precio_m2'].quantile(.25).round(0),
        'usd_m2_p75': g['precio_m2'].quantile(.75).round(0),
        'm2_cubiertos_medianos': g['covered_area'].median().round(1),
        'inmobiliarias': g['agency'].nunique(),
    })
    table.index.name = 'barrio'
    return table.sort_values('avisos', ascending=False)


def by_rooms(df):
    rooms = df['rooms'].clip(upper=5).map(lambda r: '5 o más' if r >= 5 else str(r))
    g = df.groupby(rooms)
    table = pd.DataFrame({'avisos': g.size(), 'precio_mediano_usd': g['price'].median().round(-3),
                          'm2_cubiertos_medianos': g['covered_area'].median().round(1),
                          'usd_m2_mediano': g['precio_m2'].median().round(0)})
    table.index.name = 'ambientes'
    return table


def offer_row(budget, row):
    """Fila del cuadro de oferta para un barrio y un presupuesto."""
    return {'presupuesto_usd': budget, 'barrio': row['Barrio'], 'coincidencias': row['Coincidencias'],
            'precio_mediano_coincidencias_usd': row['Precio mediano de coincidencias (USD)']}


def offer(df, rooms=2, min_area=40):
    """Coincidencias por barrio al variar el presupuesto, con la lógica de la app."""
    items = df.rename(columns={'covered_area': 'covered_area'}).to_dict('records')
    rows = []
    for budget in BUDGETS:
        rows += [offer_row(budget, row) for row in compare_neighborhoods(items, budget, min_area, rooms)]
    return pd.DataFrame(rows)


def inconsistencies(df):
    total = df['total_area_m2']
    ratio = total / df['covered_area']
    pm = df['precio_m2']
    q1, q3 = pm.quantile([.25, .75])
    low, high = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    cols = ['id', 'neighborhood', 'price', 'covered_area', 'precio_m2']
    below, above = df[pm < low].sort_values('precio_m2'), df[pm > high].sort_values('precio_m2')
    return {
        'superficie_total_informada': int(total.notna().sum()),
        'total_igual_a_cubierta': int((ratio == 1).sum()),
        'total_mas_del_doble_de_cubierta': int((ratio > 2).sum()),
        'usd_m2_limites_iqr': [round(low), round(high)],
        'usd_m2_atipicos_bajos': int(len(below)),
        'usd_m2_atipicos_altos': int(len(above)),
        'atipicos_altos_por_barrio': above['neighborhood'].value_counts().head(5).to_dict(),
        'mas_bajos': df.sort_values('precio_m2').head(3)[cols].round(1).to_dict('records'),
        'mas_altos': above.tail(3)[cols].round(1).to_dict('records'),
    }


def figures(df, barrios, oferta, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    out.mkdir(parents=True, exist_ok=True)
    ink, muted, grid, surface = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
    blue, orange, aqua, yellow = '#2a78d6', '#eb6834', '#1baf7a', '#eda100'
    thousands = FuncFormatter(lambda v, _: f'{v:,.0f}'.replace(',', '.'))
    plt.rcParams.update({
        'figure.facecolor': surface, 'axes.facecolor': surface, 'axes.edgecolor': grid,
        'axes.labelcolor': muted, 'xtick.color': muted, 'ytick.color': muted, 'text.color': ink,
        'font.size': 10, 'axes.titlesize': 12, 'axes.titleweight': 'bold', 'axes.titlelocation': 'left',
        'axes.spines.top': False, 'axes.spines.right': False, 'axes.grid': True, 'axes.grid.axis': 'y',
        'grid.color': grid, 'grid.linewidth': 0.8, 'axes.axisbelow': True, 'legend.frameon': False,
    })

    def header(ax, title, subtitle, pad=24):
        ax.set_title(title, pad=pad)
        ax.annotate(subtitle, (0, 1), xycoords='axes fraction', xytext=(0, 6),
                    textcoords='offset points', color=muted, fontsize=9, va='bottom')

    # 1. Distribución del precio por m².
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    ax.hist(df['precio_m2'].clip(upper=8000), bins=np.arange(0, 8001, 200), color=blue,
            edgecolor=surface, linewidth=1)
    median = df['precio_m2'].median()
    ax.axvline(median, color=ink, linewidth=1, linestyle='--')
    ax.annotate(f'Mediana {median:,.0f}'.replace(',', '.'), (median, ax.get_ylim()[1] * .92),
                xytext=(6, 0), textcoords='offset points', fontsize=9)
    ax.xaxis.set_major_formatter(thousands)
    ax.set_xlabel('Precio publicado por m² cubierto (USD). Valores sobre 8.000 agrupados al final')
    ax.set_ylabel('Avisos')
    header(ax, f'Precio publicado por m² · {len(df):,} departamentos en venta en CABA'.replace(',', '.'),
           'Captura del 7 de noviembre de 2026 · RE/MAX, Century 21 y Migliorisi')
    fig.tight_layout()
    fig.savefig(out / 'precio-m2-distribucion.png')
    plt.close(fig)

    # 2. Barrios con suficientes avisos: mediana e intervalo intercuartílico.
    data = barrios[barrios['avisos'] >= MIN_N].sort_values('usd_m2_mediano')
    fig, ax = plt.subplots(figsize=(8, 0.32 * len(data) + 1.6), dpi=150)
    y = range(len(data))
    ax.hlines(y, data['usd_m2_p25'], data['usd_m2_p75'], color=grid, linewidth=4, zorder=1)
    colors = [orange if b in FOCUS else blue for b in data.index]
    ax.scatter(data['usd_m2_mediano'], y, s=40, color=colors, edgecolor=surface, linewidth=1.5, zorder=2)
    ax.set_yticks(list(y), [f'{b} ({n})' for b, n in zip(data.index, data['avisos'])])
    for label in ax.get_yticklabels():
        if label.get_text().rsplit(' (', 1)[0] in FOCUS:
            label.set_fontweight('bold')
            label.set_color(ink)
    ax.grid(axis='y', visible=False)
    ax.grid(axis='x', visible=True)
    ax.tick_params(axis='y', length=0, labelsize=8.5)
    ax.xaxis.set_major_formatter(thousands)
    ax.set_xlabel('Precio publicado por m² cubierto (USD)')
    ax.margins(y=0.02)
    header(ax, 'Precio publicado por m² por barrio',
           f'Punto: mediana. Barra: percentiles 25 a 75. Entre paréntesis, avisos. Barrios con {MIN_N} avisos o más.\n'
           'En naranja, los barrios del piloto y su posible ampliación.', pad=40)
    fig.tight_layout()
    fig.savefig(out / 'precio-m2-por-barrio.png')
    plt.close(fig)

    # 3. Oferta compatible al variar el presupuesto.
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    pivot = oferta.pivot_table(index='presupuesto_usd', columns='barrio', values='coincidencias', fill_value=0)
    x = list(range(len(pivot)))
    ends = []
    for name, color in zip(FOCUS, (blue, orange, aqua, yellow)):
        if name in pivot:
            ax.plot(x, pivot[name], color=color, linewidth=2, marker='o', markersize=5,
                    markeredgecolor=surface, markeredgewidth=1.5, label=name)
            ends.append((pivot[name].iat[-1], name))
    gap = pivot[[n for n in FOCUS if n in pivot]].to_numpy().max() * 0.06
    placed = []
    for value, name in sorted(ends):
        yy = max(value, placed[-1] + gap) if placed else value
        placed.append(yy)
        ax.annotate(name, (x[-1], yy), xytext=(8, 0), textcoords='offset points', va='center', fontsize=9)
    ax.set_xticks(x, [f'{b // 1000}k' for b in pivot.index])
    ax.set_xlim(-0.3, len(x) - 0.2)
    ax.set_ylim(bottom=0)
    ax.set_xlabel('Presupuesto máximo (USD)')
    ax.set_ylabel('Avisos que coinciden')
    header(ax, 'Oferta compatible según el presupuesto',
           'Departamentos de 2 ambientes con 40 m² cubiertos o más, con la misma regla de la app.')
    ax.legend(loc='upper left', bbox_to_anchor=(0, -0.14), ncol=4)
    fig.tight_layout()
    fig.savefig(out / 'oferta-por-presupuesto.png')
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('captura', type=Path, nargs='?', default=ROOT / 'data/raw/inmobiliarias-20261107')
    parser.add_argument('--catalogo', default='inmobiliarias-autorizadas')
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'data/processed/avisos')
    parser.add_argument('--fig-dir', type=Path, default=ROOT / 'docs/img/eda-avisos')
    parser.add_argument('--no-figures', action='store_true')
    args = parser.parse_args()
    try:
        raw, df, report, log = load(args.captura, args.catalogo)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Error: {error}\n')
    calidad, faltantes = quality(raw, df, report, log)
    barrios, ambientes, oferta = by_neighborhood(df), by_rooms(df), offer(df)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, table in {'calidad': calidad, 'faltantes': faltantes, 'barrios': barrios,
                        'ambientes': ambientes}.items():
        table.to_csv(args.out_dir / f'{name}.csv', encoding='utf-8')
    oferta.to_csv(args.out_dir / 'oferta_2_ambientes_40m2.csv', index=False, encoding='utf-8')
    resumen = {
        'avisos_capturados': len(raw), 'avisos_validos': len(df), 'descartados': report.discarded,
        'posibles_duplicados': len(log.get('posibles_duplicados_entre_inmobiliarias', [])),
        'barrios': int(df['neighborhood'].nunique()), 'barrios_con_al_menos_15': int((barrios['avisos'] >= MIN_N).sum()),
        'precio_mediano_usd': float(df['price'].median()), 'usd_m2_mediano': round(float(df['precio_m2'].median())),
        'usd_m2_p25_p75': [round(float(v)) for v in df['precio_m2'].quantile([.25, .75])],
        'pct_con_coordenadas': round(float(df['con_coordenadas'].mean() * 100), 1),
        'inconsistencias': inconsistencies(df),
    }
    (args.out_dir / 'resumen.json').write_text(json.dumps(resumen, ensure_ascii=False, indent=2, default=str) + '\n',
                                               encoding='utf-8')
    if not args.no_figures:
        figures(df, barrios, oferta, args.fig_dir)
    print(json.dumps(resumen, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
