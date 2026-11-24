"""Evalúa si los delitos registrados mejoran la predicción del precio publicado por m².

Compara tres referencias sobre la misma partición de prueba:
1. la mediana de comparables del mismo barrio y ambientes;
2. un modelo inmobiliario con superficie, ambientes, barrio y ubicación;
3. el mismo modelo con delitos registrados en la ventana previa a la captura.

Las capturas repetidas de un aviso quedan en la misma partición. El resultado mide
capacidad predictiva sobre precios publicados, no efectos causales.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from precio_entorno.eda_delitos import load_many
from precio_entorno.importing import parse_listings

ROOT = Path(__file__).resolve().parents[1]
WINDOW_MONTHS = 12
RADIUS_M = 500
MIN_COMPARABLES = 5
MIN_LISTINGS = 30
TARGET_LISTINGS = (700, 2000)
BASE_FEATURES = ['covered_area', 'total_area_m2', 'rooms', 'barrio_code', 'latitude', 'longitude']
BARRIO_FEATURES = ['barrio_delitos', 'barrio_robos_hurtos', 'barrio_pct_arma']
RADIUS_FEATURES = ['radio_delitos', 'radio_robos_hurtos']
ENV_FEATURES = BARRIO_FEATURES + RADIUS_FEATURES


def load_listings(paths, source, approximate_pins=False):
    """Une los archivos del catálogo y conserva cada captura distinta de un aviso."""
    frames, reports = [], []
    for path in map(Path, paths):
        listings, report = parse_listings(path.read_bytes(), path.name, source)
        reports.append({'archivo': path.name, 'leidas': report.read, 'validas': len(listings),
                        'descartadas': report.discarded, 'faltantes': dict(report.missing),
                        'invalidos': dict(report.invalid)})
        frames.append(pd.DataFrame(listings))
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if df.empty:
        raise ValueError('No hay avisos válidos en los archivos indicados.')
    df['captured_at'] = pd.to_datetime(df['captured_at'], format='ISO8601', utc=True).dt.tz_convert(None)
    total = len(df)
    df = df.drop_duplicates(['id', 'captured_at']).reset_index(drop=True)
    for col in ('total_area_m2', 'latitude', 'longitude', 'location_accuracy_m'):
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['precio_m2'] = df['price'] / df['covered_area']
    has_pin = df['latitude'].notna() & df['longitude'].notna()
    accurate = has_pin & (df['location_accuracy_m'] <= 100)
    df['pin_para_radio'] = accurate | (has_pin & approximate_pins)
    # El modelo usa coordenadas solo cuando el pin admite el cruce por radio.
    df.loc[~df['pin_para_radio'], ['latitude', 'longitude']] = np.nan
    # En un catálogo consolidado, el prefijo del ID identifica a la inmobiliaria.
    df['agency'] = df['id'].map(lambda i: i.split(':', 1)[0] if ':' in i else source.strip().casefold())
    df['grupo'] = duplicate_groups(df)
    captures = df.groupby('id').size()
    summary = {'archivos': reports, 'observaciones_validas': total,
               'capturas_identicas_descartadas': total - len(df), 'observaciones': len(df),
               'avisos_distintos': int(len(captures)), 'avisos_con_capturas_repetidas': int((captures > 1).sum()),
               'pines_con_precision_declarada': int(accurate.sum()),
               'pines_usados_para_radio': int(df['pin_para_radio'].sum()),
               'avisos_en_grupos_de_posibles_duplicados': int((df['grupo'] != df['id']).sum()),
               'grupos_de_posibles_duplicados': int(df.loc[df['grupo'] != df['id'], 'grupo'].nunique())}
    return df, summary


def duplicate_groups(df):
    """Grupo de partición de cada aviso.

    Una misma propiedad puede estar publicada por una inmobiliaria y por un portal. Los
    avisos de fuentes distintas con mismo barrio, ambientes, m² cubiertos redondeados y
    precio redondeado a miles comparten grupo, para que la partición no ponga una copia
    en entrenamiento y otra en prueba. El resto usa su propio ID.
    """
    key = (df['neighborhood'].astype(str) + '|' + df['rooms'].astype(str) + '|'
           + df['covered_area'].round().astype(int).astype(str) + '|' + df['price'].round(-3).astype(int).astype(str))
    sources = df.groupby(key)['agency'].transform('nunique')
    return np.where(sources > 1, 'dup:' + key, df['id'])


OSM_GROUPS = {
    'dist_transporte_m': ('nearest', ['transporte']),
    'dist_parque_m': ('nearest', ['parques']),
    'dist_hospital_m': ('nearest', ['hospitales']),
    'gastronomia_500m': ('count', ['restaurantes', 'cafes', 'bares']),
    'servicios_500m': ('count', ['supermercados', 'farmacias']),
    'escuelas_500m': ('count', ['escuelas']),
}


def load_osm_folder(folder, capped, points, truncated, sources):
    """Suma las categorías completas de una carpeta; las que llegaron al tope quedan como truncadas."""
    for path in folder.glob('*.json'):
        if path.name == 'corridas.json':
            continue
        if path.stem in capped:
            if path.stem not in points:
                truncated.add(path.stem)
            continue
        rows = json.loads(path.read_text(encoding='utf-8'))
        coords = [(r.get('lat', r.get('latitude')), r.get('lon', r.get('longitude'))) for r in rows]
        points[path.stem] = np.array([c for c in coords if None not in c], dtype=float).reshape(-1, 2)
        sources[path.stem] = folder.name
        truncated.discard(path.stem)


def load_osm(*folders):
    """Lee puntos de interés por archivo de categoría: {nombre: array [lat, lon]}.

    Acepta varias carpetas; una categoría completa de una carpeta posterior reemplaza
    a la de una anterior. Omite las categorías que llegaron a su tope de puntos:
    están incompletas y sus conteos o distancias quedarían sesgados. Las que siguen
    incompletas se informan en `load_osm.truncated` y su origen en `load_osm.sources`.
    """
    points, truncated, sources = {}, set(), {}
    for folder in map(Path, folders):
        log_path = folder / 'corridas.json'
        log = json.loads(log_path.read_text(encoding='utf-8')) if log_path.exists() else []
        capped = {r['nombre'] for r in log
                  if r.get('puntos') is not None and r.get('max_items') is not None and r['puntos'] >= r['max_items']}
        load_osm_folder(folder, capped, points, truncated, sources)
    load_osm.truncated, load_osm.sources = sorted(truncated), sources
    return points


def amenities(listings, points, radius_m=RADIUS_M):
    """Agrega distancias y conteos de puntos de interés, solo para avisos con pin apto."""
    out = listings.copy()
    for name, (kind, files) in OSM_GROUPS.items():
        out[name] = np.nan
        found = [points[f] for f in files if f in points and len(points[f])]
        if len(found) < len(files):
            continue  # Falta alguna categoría del grupo, o está incompleta: sin dato.
        fill_amenity(out, name, kind, np.vstack(found), radius_m)
    return out


def fill_amenity(out, name, kind, pts, radius_m):
    """Distancia al punto más cercano o cantidad de puntos en el radio, para cada aviso con pin apto."""
    for i in out.index[out['pin_para_radio'].to_numpy(dtype=bool)]:
        lat0, lon0 = out.at[i, 'latitude'], out.at[i, 'longitude']
        dx = (pts[:, 1] - lon0) * np.cos(np.radians(lat0)) * 111_320
        dy = (pts[:, 0] - lat0) * 110_574
        d2 = dx * dx + dy * dy
        out.at[i, name] = float(np.sqrt(d2.min())) if kind == 'nearest' else int((d2 <= radius_m ** 2).sum())


def crime_window(capture, months):
    """Últimos 12 meses publicados y consecutivos, todos anteriores al mes de captura."""
    cutoff = pd.Period(capture, freq='M')
    prior = [m for m in months if pd.Period(m, freq='M') < cutoff]
    if len(prior) < WINDOW_MONTHS:
        return None
    window = prior[-WINDOW_MONTHS:]
    expected = pd.period_range(end=window[-1], periods=WINDOW_MONTHS, freq='M').strftime('%Y-%m').tolist()
    return tuple(window) if window == expected else None


def environment(listings, crimes, radius_m=RADIUS_M):
    """Agrega a cada captura los delitos de su barrio y, si el pin lo permite, de su entorno.

    Un barrio sin filas válidas en la ventana queda sin dato, no en cero.
    """
    out = listings.copy()
    for col in ENV_FEATURES + ['desfase_meses']:
        out[col] = np.nan
    out['ventana'] = None
    months = sorted(crimes['mes'].unique())
    windows = out['captured_at'].map(lambda c: crime_window(c, months))
    for window in set(windows.dropna()):
        idx = windows.index[windows.map(lambda w: w == window)]
        sub = crimes[crimes['mes'].isin(window) & crimes['delito']]
        rh = sub['tipo'].isin(['Robo', 'Hurto'])
        by_barrio = pd.DataFrame({
            'barrio_delitos': sub.groupby('barrio')['cantidad'].sum(),
            'barrio_robos_hurtos': sub[rh].groupby('barrio')['cantidad'].sum(),
            'barrio_pct_arma': sub[sub['uso_arma']].groupby('barrio')['cantidad'].sum(),
        })
        by_barrio = by_barrio.fillna({'barrio_robos_hurtos': 0, 'barrio_pct_arma': 0})
        by_barrio['barrio_pct_arma'] = by_barrio['barrio_pct_arma'] / by_barrio['barrio_delitos'] * 100
        out.loc[idx, BARRIO_FEATURES] = by_barrio.reindex(out.loc[idx, 'neighborhood']).to_numpy()
        out.loc[idx, 'ventana'] = f'{window[0]} a {window[-1]}'
        last = pd.Period(window[-1], freq='M')
        out.loc[idx, 'desfase_meses'] = [(pd.Period(c, freq='M') - last).n - 1 for c in out.loc[idx, 'captured_at']]

        pinned = idx[out.loc[idx, 'pin_para_radio'].to_numpy(dtype=bool)]
        fill_radius_crimes(out, pinned, sub['latitud'].to_numpy(), sub['longitud'].to_numpy(), rh.to_numpy(), radius_m)
    return out


def fill_radius_crimes(out, pinned, lat, lon, is_rh, radius_m):
    """Delitos y robos o hurtos a menos de `radius_m` metros de cada aviso con pin apto."""
    for i in pinned:
        lat0, lon0 = out.at[i, 'latitude'], out.at[i, 'longitude']
        dx = (lon - lon0) * np.cos(np.radians(lat0)) * 111_320
        dy = (lat - lat0) * 110_574
        near = dx * dx + dy * dy <= radius_m * radius_m
        out.at[i, 'radio_delitos'] = int(near.sum())
        out.at[i, 'radio_robos_hurtos'] = int((near & is_rh).sum())


def group_split(df, seed, test_size=0.2):
    from sklearn.model_selection import GroupShuffleSplit
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    return next(splitter.split(df, groups=df['grupo']))


def comparables(train, test):
    """Mediana del barrio y ambientes, con respaldo en el barrio y luego en toda la muestra."""
    by_rooms = train.groupby(['neighborhood', 'rooms'])['precio_m2'].agg(['median', 'size'])
    by_barrio = train.groupby('neighborhood')['precio_m2'].agg(['median', 'size'])
    fallback = train['precio_m2'].median()
    preds, levels = [], Counter()
    for barrio, rooms in zip(test['neighborhood'], test['rooms']):
        if (barrio, rooms) in by_rooms.index and by_rooms.at[(barrio, rooms), 'size'] >= MIN_COMPARABLES:
            preds.append(by_rooms.at[(barrio, rooms), 'median'])
            levels['barrio_y_ambientes'] += 1
        elif barrio in by_barrio.index and by_barrio.at[barrio, 'size'] >= MIN_COMPARABLES:
            preds.append(by_barrio.at[barrio, 'median'])
            levels['barrio'] += 1
        else:
            preds.append(fallback)
            levels['toda_la_muestra'] += 1
    return np.array(preds), dict(levels)


def boosting_model(features, seed):
    from sklearn.ensemble import HistGradientBoostingRegressor
    return HistGradientBoostingRegressor(
        loss='absolute_error', learning_rate=0.05, max_iter=300, min_samples_leaf=10,
        categorical_features=[f in ('barrio_code', 'agency_code') for f in features], random_state=seed)


def boosting(train, test, features, seed):
    model = boosting_model(features, seed)
    model.fit(train[features], train['precio_m2'])
    return model.predict(test[features])


def placebo(df, seed):
    """Reemplaza el entorno por valores sin información sobre delitos.

    Por barrio: un número al azar constante dentro de cada barrio, que conserva el
    efecto de codificar el barrio como número. Por radio: los mismos conteos,
    reasignados al azar entre los avisos que tienen pin.
    """
    rng = np.random.default_rng(seed)
    out = df.copy()
    for f in BARRIO_FEATURES:
        if out[f].notna().any():
            out[f] = out['neighborhood'].map({n: rng.uniform(0, 1000) for n in out['neighborhood'].unique()})
    has = out['radio_delitos'].notna().to_numpy()
    if has.any():
        rows = np.flatnonzero(has)
        out.loc[out.index[rows], RADIUS_FEATURES] = out.loc[out.index[rng.permutation(rows)], RADIUS_FEATURES].to_numpy()
    return out


def evaluate(df, seed=42, folds=5, control_agency=False):
    """MAE en USD/m² de las tres referencias, en la misma partición de prueba.

    Con control_agency, los dos modelos incluyen la inmobiliaria como variable, para
    descontar diferencias de composición o de criterio de publicación entre fuentes.
    """
    df = df.reset_index(drop=True).copy()
    if df['id'].nunique() < MIN_LISTINGS:
        raise ValueError(f'Hacen falta al menos {MIN_LISTINGS} avisos distintos para evaluar.')
    df['barrio_code'] = df['neighborhood'].astype('category').cat.codes
    base = list(BASE_FEATURES) + [f for f in OSM_GROUPS if f in df and df[f].notna().any()]
    if control_agency:
        df['agency_code'] = df['agency'].astype('category').cat.codes
        base.append('agency_code')
    env = base + [f for f in ENV_FEATURES if df[f].notna().any()]

    def score(train, test):
        reference, levels = comparables(train, test)
        y = test['precio_m2'].to_numpy()
        return {
            'comparables': float(np.mean(np.abs(y - reference))),
            'inmobiliario': float(np.mean(np.abs(y - boosting(train, test, base, seed)))),
            'inmobiliario_con_entorno': float(np.mean(np.abs(y - boosting(train, test, env, seed)))),
        }, levels

    train_idx, test_idx = group_split(df, seed)
    train, test = df.iloc[train_idx], df.iloc[test_idx]
    assert not set(train['id']) & set(test['id'])
    mae, levels = score(train, test)

    from sklearn.model_selection import GroupKFold
    n_folds = min(folds, df['grupo'].nunique())
    fake = placebo(df, seed)
    cv = []
    for a, b in GroupKFold(n_splits=n_folds).split(df, groups=df['grupo']):
        fold = score(df.iloc[a], df.iloc[b])[0]
        y = fake.iloc[b]['precio_m2'].to_numpy()
        fold['placebo_entorno'] = float(np.mean(np.abs(y - boosting(fake.iloc[a], fake.iloc[b], env, seed))))
        cv.append(fold)
    cv_table = pd.DataFrame(cv)
    gain = cv_table['inmobiliario'] - cv_table['inmobiliario_con_entorno']
    beats_placebo = bool((cv_table['inmobiliario_con_entorno'] < cv_table['placebo_entorno']).all())

    barrio_constant = all(df.groupby('neighborhood')[f].nunique(dropna=True).max() <= 1
                          for f in BARRIO_FEATURES if df[f].notna().any())
    return {
        'mae_usd_m2': {k: round(v, 1) for k, v in mae.items()},
        'particion': {'semilla': seed, 'observaciones_entrenamiento': len(train),
                      'observaciones_prueba': len(test), 'avisos_prueba': int(test['id'].nunique())},
        'comparables_por_nivel': levels,
        'variables_inmobiliarias': base,
        'variables_entorno': [f for f in env if f in ENV_FEATURES],
        'prueba_con_radio': int(test['radio_delitos'].notna().sum()),
        'validacion_cruzada': {
            'pliegues': n_folds,
            'mae_medio_usd_m2': cv_table.mean().round(1).to_dict(),
            'mae_desvio_usd_m2': cv_table.std(ddof=1).round(1).to_dict() if n_folds > 1 else {},
            'mejora_entorno_por_pliegue_usd_m2': gain.round(1).tolist(),
            'entorno_supera_al_placebo_en_todos_los_pliegues': beats_placebo,
            'entorno_mejora_en_todos_los_pliegues': bool((gain > 0).all()),
        },
        'notas': [
            nota for nota, aplica in [
                ('Las variables de delitos por barrio son constantes dentro de cada barrio: '
                 'repiten la información de la variable barrio.', barrio_constant),
                ('Ningún aviso de prueba tiene pin apto para el cruce por radio.',
                 test['radio_delitos'].isna().all()),
                (f'Hay menos de {TARGET_LISTINGS[0]} avisos distintos: el resultado es exploratorio.',
                 df['id'].nunique() < TARGET_LISTINGS[0]),
                ('El entorno no supera al placebo en todos los pliegues: la mejora no puede '
                 'atribuirse a los delitos registrados.', not beats_placebo),
                ('El entorno no mejora al modelo inmobiliario en todos los pliegues: su aporte no es robusto.',
                 not (gain > 0).all()),
            ] if aplica
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('avisos', type=Path, nargs='+', help='CSV o JSON del catálogo autorizado')
    parser.add_argument('--catalogo', required=True, help='Nombre del catálogo autorizado')
    parser.add_argument('--delitos', type=Path, nargs='*',
                        help='CSV del Mapa del Delito. Por defecto, data/raw/delitos_20*.csv')
    parser.add_argument('--radio-m', type=int, default=RADIUS_M)
    parser.add_argument('--pines-aproximados', action='store_true',
                        help='Usa pines sin precisión declarada para el cruce por radio (análisis de sensibilidad)')
    parser.add_argument('--control-inmobiliaria', action='store_true',
                        help='Incluye la inmobiliaria como variable en ambos modelos (prueba de robustez)')
    parser.add_argument('--osm', type=Path, nargs='+',
                        help='Carpetas con puntos de interés (OpenStreetMap, BA Data); la última tiene prioridad')
    parser.add_argument('--semilla', type=int, default=42)
    parser.add_argument('--salida', type=Path, default=ROOT / 'data/processed/modelo')
    args = parser.parse_args()
    crimes_paths = args.delitos or sorted((ROOT / 'data/raw').glob('delitos_20*.csv'))
    try:
        if not crimes_paths:
            raise ValueError('No hay CSV del Mapa del Delito en data/raw.')
        listings, summary = load_listings(args.avisos, args.catalogo, args.pines_aproximados)
        crimes, _, _ = load_many(crimes_paths)
        data = environment(listings, crimes, args.radio_m)
        if args.osm:
            data = amenities(data, load_osm(*args.osm), args.radio_m)
        without_window = int(data['ventana'].isna().sum())
        result = evaluate(data, args.semilla, control_agency=args.control_inmobiliaria)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Error: {error}\n')
    result = {'catalogo': args.catalogo.strip().casefold(), 'datos': summary,
              'delitos': [p.name for p in crimes_paths], 'radio_m': args.radio_m,
              'pines_aproximados': args.pines_aproximados,
              'control_inmobiliaria': args.control_inmobiliaria,
              'osm': [str(p) for p in args.osm] if args.osm else None,
              'puntos_de_interes_por_fuente': getattr(load_osm, 'sources', {}) if args.osm else {},
              'osm_categorias_incompletas': getattr(load_osm, 'truncated', []) if args.osm else [],
              'ventanas': data['ventana'].value_counts().to_dict(),
              'capturas_sin_ventana_completa': without_window,
              'desfase_meses': data['desfase_meses'].describe()[['min', 'max']].to_dict(), **result}
    args.salida.mkdir(parents=True, exist_ok=True)
    data.drop(columns=['url'], errors='ignore').to_csv(args.salida / 'dataset_modelo.csv', index=False)
    (args.salida / 'resultados.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
