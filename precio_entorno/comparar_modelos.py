"""Compara seis modelos de scikit-learn para el precio publicado por m².

Todos se evalúan en la misma partición agrupada que `precio_entorno.modelo`:
- dos clásicos: regresión lineal y árbol de decisión;
- dos ensambles: random forest e HistGradientBoosting (el modelo del pipeline principal);
- una red neuronal: MLPRegressor;
- un lineal regularizado: ElasticNet.

La mediana de comparables del mismo barrio y ambientes queda como referencia. Los
delitos registrados no entran: el pipeline principal mostró que no superan al placebo.
El resultado mide capacidad predictiva sobre precios publicados, no tasaciones.
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from precio_entorno.descripcion import PRICE_FIELDS
from precio_entorno.modelo import BASE_FEATURES, OSM_GROUPS, boosting_model, comparables, group_split

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / 'data/processed/ampliado/modelo-pines-aproximados-poi-control/dataset_modelo.csv'
BUILDING_FEATURES = ['age_years', 'garages']
# Rasgos leídos de la descripción (1 lo menciona, 0 no). Solo entran si algún archivo los trae.
EXTRA_FEATURES = BUILDING_FEATURES + list(PRICE_FIELDS)
MODELS = {
    'regresion_lineal': ('clásico', 'LinearRegression'),
    'arbol_de_decision': ('clásico', 'DecisionTreeRegressor'),
    'random_forest': ('ensamble', 'RandomForestRegressor'),
    'hist_gradient_boosting': ('ensamble', 'HistGradientBoostingRegressor'),
    'mlp': ('red neuronal', 'MLPRegressor'),
    'elastic_net': ('lineal regularizado', 'ElasticNet'),
}


def load_dataset(path, building_paths=()):
    """Lee el dataset del modelo y, si se indican, suma por ID antigüedad, cocheras y rasgos de la descripción."""
    df = pd.read_csv(path)
    if 'grupo' not in df:
        df['grupo'] = df['id']
    if 'agency' not in df:
        df['agency'] = df['id'].map(lambda i: i.split(':', 1)[0] if ':' in str(i) else 'sin_prefijo')
    if building_paths:
        rows = []
        for p in map(Path, building_paths):
            rows += json.loads(p.read_text(encoding='utf-8'))
        extra = pd.DataFrame(rows).rename(columns={'listing_id': 'id'})
        extra = extra[['id'] + [c for c in EXTRA_FEATURES if c in extra]]
        # Si un aviso aparece en varias capturas, se queda el último dato informado.
        extra = extra.groupby('id').last()
        df = df.drop(columns=[c for c in EXTRA_FEATURES if c in df]).join(extra, on='id')
        for col in EXTRA_FEATURES:
            if col in df:
                df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.reset_index(drop=True)


def feature_sets(df, control_agency):
    """Variables numéricas y categóricas presentes con al menos un dato."""
    numeric = [f for f in BASE_FEATURES if f != 'barrio_code']
    numeric += [f for f in list(OSM_GROUPS) + EXTRA_FEATURES if f in df and df[f].notna().any()]
    categorical = ['neighborhood'] + (['agency'] if control_agency else [])
    return numeric, categorical


def build_models(numeric, categorical, seed):
    """Pipelines con el mismo preprocesamiento para los modelos que lo necesitan.

    Los faltantes numéricos se completan con la mediana de entrenamiento y se agrega
    un indicador de faltante. Las variables se escalan y las categorías pasan a
    columnas binarias; una categoría que no estaba en entrenamiento queda en cero.
    HistGradientBoosting usa su propia configuración, igual a la del pipeline principal.
    """
    from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import ElasticNet, LinearRegression
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import Pipeline, make_pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from sklearn.tree import DecisionTreeRegressor

    def prep():
        return ColumnTransformer([
            ('num', make_pipeline(SimpleImputer(strategy='median', add_indicator=True), StandardScaler()), numeric),
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical),
        ])

    def pipe(estimator):
        return Pipeline([('prep', prep()), ('modelo', estimator)])

    return {
        'regresion_lineal': pipe(LinearRegression()),
        'arbol_de_decision': pipe(DecisionTreeRegressor(min_samples_leaf=10, random_state=seed)),
        'random_forest': pipe(RandomForestRegressor(n_estimators=300, min_samples_leaf=3, max_features=0.5,
                                                    n_jobs=-1, random_state=seed)),
        # La red aprende mejor con el objetivo escalado; las predicciones vuelven a USD/m².
        'mlp': TransformedTargetRegressor(
            regressor=pipe(MLPRegressor(hidden_layer_sizes=(64, 32), alpha=1e-3, learning_rate_init=1e-3,
                                        max_iter=1000, early_stopping=True, random_state=seed)),
            transformer=StandardScaler()),
        'elastic_net': pipe(ElasticNet(alpha=0.1, l1_ratio=0.5, max_iter=10_000)),
    }


def hgb_features(df, numeric, categorical):
    """Columnas y códigos que espera `modelo.boosting` (barrio e inmobiliaria como categorías)."""
    df = df.copy()
    df['barrio_code'] = df['neighborhood'].astype('category').cat.codes
    features = list(BASE_FEATURES) + [f for f in numeric if f not in BASE_FEATURES]
    if 'agency' in categorical:
        df['agency_code'] = df['agency'].astype('category').cat.codes
        features.append('agency_code')
    return df, features


def metrics(y, pred):
    err = y - pred
    return {'mae': float(np.mean(np.abs(err))), 'rmse': float(np.sqrt(np.mean(err ** 2))),
            'r2': float(1 - np.sum(err ** 2) / np.sum((y - y.mean()) ** 2))}


def fit_predict(name, train, test, numeric, categorical, features, seed):
    """Entrena un modelo y devuelve predicciones de entrenamiento y de prueba."""
    if name == 'hist_gradient_boosting':
        model = boosting_model(features, seed).fit(train[features], train['precio_m2'])
        return model.predict(train[features]), model.predict(test[features])
    model = build_models(numeric, categorical, seed)[name]
    model.fit(train[numeric + categorical], train['precio_m2'])
    return model.predict(train[numeric + categorical]), model.predict(test[numeric + categorical])


def fold_mae(name, train, test, numeric, categorical, features, seed):
    """MAE de un modelo entrenado en un pliegue y evaluado en el resto."""
    _, pred = fit_predict(name, train, test, numeric, categorical, features, seed)
    return metrics(test['precio_m2'].to_numpy(), pred)['mae']


def compare(df, seed=42, folds=5, control_agency=False):
    """MAE, RMSE y R² de los seis modelos y de los comparables en la misma partición."""
    numeric, categorical = feature_sets(df, control_agency)
    df, features = hgb_features(df, numeric, categorical)
    train_idx, test_idx = group_split(df, seed)
    train, test = df.iloc[train_idx], df.iloc[test_idx]
    assert not set(train['grupo']) & set(test['grupo'])
    y_train, y_test = train['precio_m2'].to_numpy(), test['precio_m2'].to_numpy()

    from sklearn.model_selection import GroupKFold
    n_folds = min(folds, df['grupo'].nunique())
    splits = list(GroupKFold(n_splits=n_folds).split(df, groups=df['grupo']))

    rows = []
    reference, _ = comparables(train, test)
    cv_ref = [metrics(df.iloc[b]['precio_m2'].to_numpy(), comparables(df.iloc[a], df.iloc[b])[0])['mae']
              for a, b in splits]
    rows.append({'modelo': 'comparables', 'familia': 'referencia', 'estimador': 'mediana barrio y ambientes',
                 'mae_entrenamiento': None, **{f'{k}_prueba': v for k, v in metrics(y_test, reference).items()},
                 'mae_cv_medio': float(np.mean(cv_ref)), 'mae_cv_desvio': float(np.std(cv_ref, ddof=1)),
                 'segundos': None})
    for name, (family, estimator) in MODELS.items():
        start = time.perf_counter()
        pred_train, pred_test = fit_predict(name, train, test, numeric, categorical, features, seed)
        seconds = time.perf_counter() - start
        cv = [fold_mae(name, df.iloc[a], df.iloc[b], numeric, categorical, features, seed) for a, b in splits]
        rows.append({'modelo': name, 'familia': family, 'estimador': estimator,
                     'mae_entrenamiento': metrics(y_train, pred_train)['mae'],
                     **{f'{k}_prueba': v for k, v in metrics(y_test, pred_test).items()},
                     'mae_cv_medio': float(np.mean(cv)), 'mae_cv_desvio': float(np.std(cv, ddof=1)),
                     'segundos': seconds})
    table = pd.DataFrame(rows)
    table['brecha_generalizacion'] = table['mae_prueba'] - table['mae_entrenamiento']
    table = table.sort_values('mae_cv_medio').reset_index(drop=True)
    best = table[table['modelo'] != 'comparables'].iloc[0]
    ref_mae = float(table.loc[table['modelo'] == 'comparables', 'mae_cv_medio'].iloc[0])
    return table, {
        'particion': {'semilla': seed, 'observaciones_entrenamiento': len(train), 'observaciones_prueba': len(test),
                      'grupos_prueba': int(test['grupo'].nunique()), 'pliegues': n_folds},
        'variables_numericas': numeric,
        'variables_categoricas': categorical,
        'faltantes_por_variable': {f: int(df[f].isna().sum()) for f in numeric if df[f].isna().any()},
        'mejor_modelo': best['modelo'],
        'mejor_mae_cv_usd_m2': round(float(best['mae_cv_medio']), 1),
        'mejora_sobre_comparables_pct': round((1 - best['mae_cv_medio'] / ref_mae) * 100, 1),
        'mediana_precio_m2': round(float(df['precio_m2'].median()), 1),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET,
                        help='dataset_modelo.csv generado por precio_entorno.modelo')
    parser.add_argument('--edificio', type=Path, nargs='*', default=[],
                        help='avisos.json con antigüedad, cocheras o rasgos de la descripción para sumar por ID')
    parser.add_argument('--control-inmobiliaria', action='store_true',
                        help='Incluye la inmobiliaria como variable en todos los modelos')
    parser.add_argument('--semilla', type=int, default=42)
    parser.add_argument('--salida', type=Path, default=ROOT / 'data/processed/comparacion-modelos')
    args = parser.parse_args()
    try:
        df = load_dataset(args.dataset, args.edificio)
        table, info = compare(df, args.semilla, control_agency=args.control_inmobiliaria)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'Error: {error}\n')
    result = {'dataset': str(args.dataset), 'edificio': [str(p) for p in args.edificio],
              'control_inmobiliaria': args.control_inmobiliaria, 'avisos': int(df['id'].nunique()),
              'observaciones': len(df), **info,
              'modelos': table.round(3).replace({np.nan: None}).to_dict(orient='records'),
              'notas': ['MAE en USD/m² de precio publicado; no son tasaciones ni precios de cierre.',
                        'Hiperparámetros fijos y documentados en el código, sin búsqueda: la comparación '
                        'es entre familias de modelos con la misma partición.',
                        'HistGradientBoosting optimiza error absoluto; los demás, error cuadrático.']}
    args.salida.mkdir(parents=True, exist_ok=True)
    table.round(1).to_csv(args.salida / 'tabla.csv', index=False)
    (args.salida / 'resultados.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    cols = ['modelo', 'familia', 'mae_entrenamiento', 'mae_prueba', 'r2_prueba', 'mae_cv_medio', 'mae_cv_desvio']
    print(table[cols].round(2).to_string(index=False))
    print(f"\nMejor: {info['mejor_modelo']} ({info['mejor_mae_cv_usd_m2']} USD/m² en validación cruzada, "
          f"{info['mejora_sobre_comparables_pct']} % mejor que comparables)")


if __name__ == '__main__':
    main()
