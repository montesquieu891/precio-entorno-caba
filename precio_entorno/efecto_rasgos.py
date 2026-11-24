"""Cuánto se asocia cada rasgo de la descripción con el USD/m² publicado, dentro del barrio.

Regresión lineal de log(USD/m²) sobre los nueve rasgos, la superficie cubierta (en log),
los ambientes, el barrio y la inmobiliaria, con errores robustos (HC1). Se estima con y sin antigüedad,
porque «a estrenar» y «amenities» se superponen con los edificios nuevos. Es una
asociación sobre precios de publicación, no un efecto causal ni una tasación, y solo
usa los avisos que tienen descripción leída.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from precio_entorno.comparar_modelos import DEFAULT_DATASET, load_dataset
from precio_entorno.descripcion import PRICE_FIELDS, TRAITS

ROOT = Path(__file__).resolve().parents[1]
EXTRA = ['data/raw/zonaprop-venta-20261108-edificio/avisos.json', 'data/raw/inmobiliarias-20261109-edificio/avisos.json',
         'data/raw/zonaprop-venta-20261108-descripcion-completa/avisos.json',
         'data/raw/rasgos-inmobiliarias-20261115/avisos.json']


def ols_hc1(X, y):
    """Coeficientes y errores estándar robustos a heterocedasticidad (HC1)."""
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    inv = np.linalg.pinv(X.T @ X)
    cov = inv @ (X.T * resid ** 2) @ X @ inv * n / (n - k)
    return beta, np.sqrt(np.diag(cov)), 1 - (resid ** 2).sum() / ((y - y.mean()) ** 2).sum()


def effects(df, with_age):
    data = df[df[PRICE_FIELDS[0]].notna()]
    if with_age:
        data = data.dropna(subset=['age_years'])
    parts = [data[list(PRICE_FIELDS)], np.log(data['covered_area']).rename('log_m2'),
             pd.get_dummies(data['rooms'].astype(int), prefix='amb', drop_first=True),
             pd.get_dummies(data['neighborhood'], drop_first=True),
             # Cada inmobiliaria redacta y publica distinto: se compara dentro de la misma fuente.
             pd.get_dummies(data['agency'], prefix='inm', drop_first=True)]
    if with_age:
        parts.append(pd.DataFrame({'edad': data['age_years'], 'edad2': data['age_years'] ** 2}))
    X = pd.concat(parts, axis=1).astype(float)
    X.insert(0, 'const', 1.0)
    beta, se, r2 = ols_hc1(X.to_numpy(), np.log(data['precio_m2'].to_numpy()))
    coef, err = dict(zip(X.columns, beta)), dict(zip(X.columns, se))
    rows = []
    for column in PRICE_FIELDS:
        low, high = coef[column] - 1.96 * err[column], coef[column] + 1.96 * err[column]
        rows.append({'rasgo': TRAITS[column][0], 'columna': column, 'avisos_con_rasgo': int(data[column].sum()),
                     'diferencia_pct': round(float(np.expm1(coef[column]) * 100), 1),
                     'ic95_pct': [round(float(np.expm1(low) * 100), 1), round(float(np.expm1(high) * 100), 1)],
                     'distinto_de_cero': bool(low > 0 or high < 0)})
    return {'avisos': len(data), 'por_inmobiliaria': data['agency'].value_counts().to_dict(), 'r2': round(float(r2), 3), 'rasgos': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--extra', type=Path, nargs='*', default=[ROOT / p for p in EXTRA])
    parser.add_argument('--salida', type=Path, default=ROOT / 'data/processed/efecto-rasgos/resultados.json')
    args = parser.parse_args()
    df = load_dataset(args.dataset, args.extra)
    result = {'nota': __doc__.split('\n\n', 1)[1].strip().replace('\n', ' '),
              'sin_antiguedad': effects(df, False), 'con_antiguedad': effects(df, True)}
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for name in ('sin_antiguedad', 'con_antiguedad'):
        print_effects(name, result[name])


def print_effects(name, part):
    """Muestra en consola la diferencia de cada rasgo; el asterisco marca los distintos de cero."""
    print(f"\n{name} (n={part['avisos']}, R²={part['r2']})")
    for row in part['rasgos']:
        mark = '*' if row['distinto_de_cero'] else ' '
        print(f"  {row['rasgo']:13} {row['diferencia_pct']:+6.1f} % {row['ic95_pct']} {mark}")


if __name__ == '__main__':
    main()
