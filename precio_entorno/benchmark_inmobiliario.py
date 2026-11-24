"""Benchmark agrupado del catálogo de venta incluido en el bundle del EDA."""

import time
import warnings
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.neighbors import KNeighborsRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'data/processed/eda-colab/eda_bundle.zip'
SEED = 42
NUMERIC = ['covered_area', 'total_area_m2', 'rooms', 'latitude', 'longitude',
           'dist_transporte_m', 'dist_parque_m', 'dist_hospital_m', 'gastronomia_500m', 'escuelas_500m']
CATEGORICAL = ['neighborhood', 'agency']
EXTRA = ['age_years', 'cond_code']
KEYS = ['neighborhood', 'rooms']
BASELINE = 'HGB fijo EDA'
SIMPLE_BASELINES = ('Mediana global', 'Mediana comparables')


def load_sales(bundle=BUNDLE):
    with ZipFile(bundle) as archive, archive.open('venta.csv') as sales:
        data = pd.read_csv(sales, dtype={'id': str, 'grupo': str})
    required = {'id', 'grupo', 'price', 'precio_m2', 'currency', *NUMERIC, *CATEGORICAL}
    if missing := required.difference(data.columns):
        raise ValueError(f'Columnas ausentes: {sorted(missing)}')
    if data['id'].isna().any() or data['id'].duplicated().any() or data['grupo'].isna().any():
        raise ValueError('Se requieren ID únicos y grupos informados')
    if not data['currency'].eq('USD').all() or not np.isfinite(data['precio_m2']).all() or not data['precio_m2'].gt(0).all():
        raise ValueError('Se requieren precios por m² positivos, finitos y en USD')
    data['age_years'] = pd.to_numeric(data.get('age_years', np.nan), errors='coerce')
    # El código histórico identifica estados sin imponer distancias entre ellos.
    states = ['a estrenar', 'en construcción', 'excelente', 'muy bueno', 'bueno', 'regular', 'reciclado', 'a reciclar']
    data['cond_code'] = data.get('condition', pd.Series(index=data.index, dtype=object)).map(dict(zip(states, range(len(states)))))
    return data


def model_specs(extended):
    numeric = NUMERIC + (['age_years'] if extended else [])
    categorical = CATEGORICAL + (['cond_code'] if extended else [])

    def pipeline(estimator, scale=False):
        imputer = SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True)
        processing = ColumnTransformer([
            ('num', make_pipeline(imputer, StandardScaler()) if scale else imputer, numeric),
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical),
        ])
        return make_pipeline(processing, estimator)

    hgb_preprocessing = ColumnTransformer([
        ('cat', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=np.nan), categorical),
        ('num', 'passthrough', numeric),
    ])
    hgb = make_pipeline(hgb_preprocessing, HistGradientBoostingRegressor(
        max_iter=220, early_stopping=False, random_state=SEED, categorical_features=list(range(len(categorical))),
    ))
    mlp = TransformedTargetRegressor(
        regressor=pipeline(MLPRegressor(hidden_layer_sizes=(48, 24), max_iter=250, tol=0.001,
                                       early_stopping=False, random_state=SEED), scale=True),
        transformer=StandardScaler(),
    )
    return {
        'Ridge': (pipeline(Ridge(), scale=True), {'ridge__alpha': [1, 10, 100]}),
        'KNN': (pipeline(KNeighborsRegressor(weights='distance'), scale=True),
                {'kneighborsregressor__n_neighbors': [8, 20, 40]}),
        'Random Forest': (pipeline(RandomForestRegressor(n_estimators=100, max_features=0.7, n_jobs=1,
                                                       random_state=SEED)),
                          {'randomforestregressor__min_samples_leaf': [2, 5, 10]}),
        'HistGradientBoosting': (hgb, {'histgradientboostingregressor__min_samples_leaf': [10, 20, 40]}),
        'MLP': (mlp, {'regressor__mlpregressor__alpha': [0.001, 0.01, 0.1]}),
    }


def historical_baseline(train, test):
    columns = NUMERIC + CATEGORICAL
    # Misma familia, hiperparámetros y objetivo del EDA. El vocabulario se ajusta en train.
    processing = ColumnTransformer([
        ('num', 'passthrough', NUMERIC),
        ('cat', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=np.nan), CATEGORICAL),
    ])
    baseline = make_pipeline(processing, HistGradientBoostingRegressor(
        max_iter=500, learning_rate=0.05, min_samples_leaf=20, early_stopping=False,
        categorical_features=[len(NUMERIC), len(NUMERIC) + 1], random_state=SEED,
    ))
    baseline.fit(train[columns], np.log(train['precio_m2']))
    return np.exp(baseline.predict(test[columns]))


def training_comparables(train, test):
    # Una observación por grupo y segmento impide ponderar más las propiedades republicadas.
    groups = train.groupby([*KEYS, 'grupo'], dropna=False)[['precio_m2', 'covered_area']].median().reset_index()
    by_key = groups.groupby(KEYS)
    reference = by_key.agg(
        n_ref=('precio_m2', 'size'), median_ref=('precio_m2', 'median'),
        mad=('precio_m2', lambda price: np.median(np.abs(price - np.median(price)))),
        area_ref=('covered_area', 'median'),
    )
    scores = test.join(reference, on=KEYS)
    scores['n_ref'] = scores['n_ref'].fillna(0).astype(int)
    scores['z_ref'] = (scores['precio_m2'] - scores['median_ref']) / (1.4826 * scores['mad'].replace(0, np.nan))
    p01 = test['neighborhood'].map(groups.groupby('neighborhood')['precio_m2'].quantile(0.01))
    scores['review'] = (test['covered_area'].div(test['total_area_m2']).lt(0.5)
                        | test['covered_area'].div(test['rooms']).lt(12)
                        | test['precio_m2'].lt(p01) | test['price'].lt(25_000)
                        | test['covered_area'].gt(2.5 * scores['area_ref']))
    scores['supported'] = scores['n_ref'].ge(10) & scores['z_ref'].notna()
    scores['proxy'] = scores['supported'] & scores['z_ref'].le(-1.5) & ~scores['review']
    return scores[['grupo', 'agency', 'neighborhood', 'age_years', 'precio_m2', 'n_ref', 'z_ref', 'supported', 'review', 'proxy']]


def usd_mae(estimator, features, log_prices):
    return -np.mean(np.abs(np.exp(log_prices) - np.exp(estimator.predict(features))))


def simple_baselines(train, test, minimum=5):
    """Referencias sin aprendizaje: una propiedad aproximada por grupo y segmento."""
    units = train.groupby([*KEYS, 'grupo'], dropna=False)['precio_m2'].median().reset_index()
    local = units.groupby(KEYS)['precio_m2'].agg(['median', 'size'])
    neighborhoods = train.groupby(['neighborhood', 'grupo'])['precio_m2'].median().reset_index()
    neighborhood_stats = neighborhoods.groupby('neighborhood')['precio_m2'].agg(['median', 'size'])
    global_median = train.groupby('grupo')['precio_m2'].median().median()
    estimates = []
    for neighborhood, rooms in zip(test['neighborhood'], test['rooms']):
        if (neighborhood, rooms) in local.index and local.at[(neighborhood, rooms), 'size'] >= minimum:
            estimates.append(local.at[(neighborhood, rooms), 'median'])
        elif neighborhood in neighborhood_stats.index and neighborhood_stats.at[neighborhood, 'size'] >= minimum:
            estimates.append(neighborhood_stats.at[neighborhood, 'median'])
        else:
            estimates.append(global_median)
    return {SIMPLE_BASELINES[0]: np.full(len(test), global_median),
            SIMPLE_BASELINES[1]: np.asarray(estimates)}


def benchmark(data, include_references=False, explain=True, progress=None):
    predictions, fits, explanations = [], [], []
    splits = list(GroupKFold(n_splits=5).split(data, groups=data['grupo']))
    scopes = ['base', 'edificio'] if data[EXTRA].notna().any().any() else ['base']
    with threadpool_limits(limits=1):
        for fold, (train_index, test_index) in enumerate(splits, 1):
            train, test = data.iloc[train_index], data.iloc[test_index]
            if progress:
                progress(f'Fold {fold}/5: {len(train)} entrenamiento, {len(test)} prueba')
            fold_predictions, fold_fits, fold_explanations = benchmark_fold(
                train, test, fold, scopes, include_references, explain, progress)
            predictions += fold_predictions
            fits += fold_fits
            explanations += fold_explanations
    oof = pd.concat(predictions).rename_axis('row').reset_index()
    oof['error'] = oof['estimate'] - oof['precio_m2']
    oof['gap'] = oof['precio_m2'].div(oof['estimate']) - 1
    return oof, pd.DataFrame(fits), pd.DataFrame(explanations)


def benchmark_fold(train, test, fold, scopes, include_references, explain, progress):
    """Predicciones, ajustes y explicaciones de un fold externo, en el orden del informe."""
    refs = training_comparables(train, test)
    predictions, explanations = [], []
    if include_references:
        baselines = simple_baselines(train, test).items()
        predictions += [refs.assign(model=name, scope='referencia', fold=fold, estimate=prediction) for name, prediction in baselines]
    start = time.perf_counter()
    predictions.append(refs.assign(model=BASELINE, scope='base', fold=fold,
                                   estimate=historical_baseline(train, test)))
    fits = [{'fold': fold, 'scope': 'base', 'model': BASELINE, 'seconds': time.perf_counter() - start, 'params': {}}]
    inner = list(GroupKFold(n_splits=3).split(train, groups=train['grupo']))
    for scope in scopes:
        scope_predictions, scope_fits, scope_explanations = benchmark_scope(
            train, test, refs, fold, scope, inner, explain, progress)
        predictions += scope_predictions
        fits += scope_fits
        explanations += scope_explanations
    return predictions, fits, explanations


def benchmark_scope(train, test, refs, fold, scope, inner, explain, progress):
    """Ajusta las cinco familias en un escenario y, si se pide, explica los ensambles."""
    extended = scope == 'edificio'
    features = NUMERIC + CATEGORICAL + (EXTRA if extended else [])
    predictions, fits, explanations, fold_ensembles = [], [], [], {}
    for name, (estimator, grid) in model_specs(extended).items():
        search, price, fit = fit_model(name, estimator, grid, train, test, features, inner)
        predictions.append(refs.assign(model=name, scope=scope, fold=fold, estimate=price))
        fits.append({'fold': fold, 'scope': scope, 'model': name, **fit})
        if progress:
            progress(f'  {scope} / {name}: MAE {np.abs(price - test.precio_m2).mean():.2f}')
        if name == 'Ridge':
            explanations += ridge_coefficients(search.best_estimator_, extended, fold, scope, name)
        if name in {'Random Forest', 'HistGradientBoosting'}:
            fold_ensembles[name] = search.best_estimator_
    # Ambas explicaciones se calculan sobre el fold externo y permiten elegir qué mostrar después.
    for name, estimator in (fold_ensembles.items() if explain else []):
        explanations += explain_ensemble(estimator, train, test, features, fold, scope, name)
    return predictions, fits, explanations


def fit_model(name, estimator, grid, train, test, features, inner):
    """Busca hiperparámetros en el fold interno; devuelve la búsqueda, el precio estimado y el registro del ajuste."""
    start = time.perf_counter()
    search = GridSearchCV(estimator, grid, cv=inner, scoring=usd_mae, n_jobs=1, error_score='raise')
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter('always', ConvergenceWarning)
        search.fit(train[features], np.log(train['precio_m2']))
    price = np.exp(search.predict(test[features]))
    fit_seconds = time.perf_counter() - start
    train_mae = float(np.abs(np.exp(search.predict(train[features])) - train['precio_m2']).mean())
    iterations, limit = None, None
    if name == 'MLP':
        fitted_mlp = search.best_estimator_.regressor_.steps[-1][1]
        iterations, limit = int(fitted_mlp.n_iter_), int(fitted_mlp.max_iter)
    fit = {'params': search.best_params_, 'mae_train': train_mae,
           'mae_test': float(np.abs(price - test['precio_m2']).mean()),
           'seconds': fit_seconds, 'n_iter': iterations, 'max_iter': limit,
           'limite_iteraciones_alcanzado': iterations >= limit if iterations is not None else None,
           'avisos_convergencia_busqueda': sum(issubclass(w.category, ConvergenceWarning) for w in recorded)}
    return search, price, fit


def ridge_coefficients(pipe, extended, fold, scope, name):
    """Coeficientes de Ridge en log por unidad original de cada variable numérica."""
    prep, ridge = pipe.steps[0][1], pipe.steps[1][1]
    scaler = prep.named_transformers_['num'].named_steps['standardscaler']
    numeric = NUMERIC + (['age_years'] if extended else [])
    row = {'fold': fold, 'scope': scope, 'model': name}
    return [{**row, 'feature': feature, 'type': 'coef_log_por_unidad', 'value': coef / scale} for feature, coef, scale in zip(numeric, ridge.coef_, scaler.scale_)]


def explain_ensemble(estimator, train, test, features, fold, scope, name):
    """Importancia por permutación y PDP/ICE de superficie cubierta de un ensamble."""
    importance = permutation_importance(estimator, test[features], np.log(test['precio_m2']),
                                        scoring=usd_mae, n_repeats=4, random_state=SEED, n_jobs=1)
    row = {'fold': fold, 'scope': scope, 'model': name}
    explanations = [{**row, 'feature': feature, 'type': 'aumento_mae_usd_m2', 'value': value} for feature, value in zip(features, importance.importances_mean)]
    # PDP/ICE de superficie cubierta en el rango central del fold de entrenamiento.
    grid = train['covered_area'].quantile(np.linspace(0.1, 0.9, 9))
    sample = test[features].sample(n=min(120, len(test)), random_state=SEED)
    for quantile, area in grid.items():
        ice = np.exp(estimator.predict(sample.assign(covered_area=area)))
        explanations.append({**row, 'feature': 'covered_area', 'type': 'pdp_usd_m2', 'value': ice.mean(),
                             'quantile': quantile, 'area': area,
                             'ice_p10': np.quantile(ice, 0.1), 'ice_p90': np.quantile(ice, 0.9)})
    return explanations


def scores(rows):
    return pd.Series({'n': len(rows), 'groups': rows['grupo'].nunique(), 'mae': rows['error'].abs().mean(),
                      'rmse': np.sqrt(rows['error'].pow(2).mean()), 'bias': rows['error'].mean(),
                      'mdape_pct': 100 * rows['error'].abs().div(rows['precio_m2']).median()})


def bootstrap_mae_delta(rows, baseline, draws=600):
    if draws < 2 or rows.empty or baseline.empty or rows['row'].duplicated().any() or baseline['row'].duplicated().any():
        raise ValueError('Se requieren predicciones emparejadas únicas y al menos dos remuestreos.')
    if set(rows['row']) != set(baseline['row']):
        raise ValueError('Los modelos deben evaluarse sobre las mismas filas.')
    left = rows.set_index('row')
    right = baseline.set_index('row').reindex(left.index)
    if not left['grupo'].equals(right['grupo']) or not np.allclose(left['precio_m2'], right['precio_m2']):
        raise ValueError('Grupos y precios observados deben coincidir entre modelos.')
    paired = rows.set_index('row')['error'].abs().sub(baseline.set_index('row')['error'].abs())
    summary = pd.DataFrame({'delta': paired, 'grupo': rows.set_index('row')['grupo']}).groupby('grupo')['delta'].agg(['sum', 'size'])
    rng = np.random.default_rng(SEED)
    sums, sizes = summary['sum'].to_numpy(), summary['size'].to_numpy()
    samples = rng.integers(len(summary), size=(draws, len(summary)))
    return np.quantile(sums[samples].sum(axis=1) / sizes[samples].sum(axis=1), [0.025, 0.975])


def candidates_by_threshold(candidates):
    """Cantidad de candidatos con señal que quedan bajo cada umbral de brecha."""
    return [(threshold, (candidates['gap'].le(threshold) & candidates['proxy']).sum()) for threshold in [-0.15, -0.20, -0.25]]


def ranking(oof, k=20):
    rows, sets = [], {}
    for (model, scope, fold), block in oof.groupby(['model', 'scope', 'fold']):
        candidates = block[block['supported'] & ~block['review']].sort_values(['gap', 'row']).drop_duplicates('grupo')
        top = candidates.head(k)
        sets[model, scope, fold] = set(top['grupo'])
        row = {'model': model, 'scope': scope, 'fold': fold, 'top_n': len(top),
               'precision_proxy': top['proxy'].mean(), 'coverage': block['supported'].mean(),
               'flags_in_top_without_review': block.sort_values(['gap', 'row']).drop_duplicates('grupo').head(k)['review'].sum()}
        rows += [{**row, 'threshold': threshold, 'candidates': int(passing)} for threshold, passing in candidates_by_threshold(candidates)]
    table = pd.DataFrame(rows)
    for index, row in table.iterrows():
        top = sets[row['model'], row['scope'], row['fold']]
        base = sets[BASELINE, 'base', row['fold']]
        table.loc[index, 'jaccard_vs_eda'] = len(top & base) / len(top | base) if top | base else np.nan
    return table
