"""API local de la interfaz web: barrios, avisos que encajan, capas del entorno y alertas.

Se ejecuta con `python -m precio_entorno.api` y sirve la página de `web/` en http://127.0.0.1:8000.
"""

import argparse
import json
import math
import re
import secrets
import threading
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from statistics import median
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import (cercania, colectivos, comparables, concentracion, descripcion, entorno, lugares as lugares_google,
               make_webhook, parecidos as barrios_parecidos, preferencias, radar, ubicacion, cocheras)
from .bases import REAL_BASE, ROOT, demo_base, open_store
from .importing import BARRIOS, usable_pin
from .matching import matches

Mode = Literal['demo', 'real']
Operation = Literal['venta', 'alquiler']
LAYER_KEYS = ('subte', 'verdes', 'escuelas', 'salud', 'ruido', 'riesgo', 'estacionamiento', 'clubes', 'gimnasios',
              'colectivos', 'ciclovias', 'ecobici', 'bibliotecas', 'rampas', 'recreacion')
# Capas de puntos que cubren toda la ciudad, no solo el recuadro del barrio elegido.
CITYWIDE = {'estacionamiento': 'garaje', 'clubes': 'club', 'gimnasios': 'gimnasio'}
CURRENCIES = {'venta': ('USD',), 'alquiler': ('ARS', 'USD')}
OFFICIAL = sorted(set(BARRIOS.values()))


EMAIL = re.compile(r'[^@\s<>"]+@[^@\s<>"]+\.[A-Za-z]{2,}')

# Caché HTTP. index.html pide app.js y styles.css con ?v=<hash del contenido>: con esa versión el navegador los
# guarda un año sin volver a preguntar, y un cambio en el archivo cambia la URL. El HTML y lo que depende de los
# avisos se revalida siempre (no-cache, con ETag); la geometría de los barrios y el radar semanal se guardan un rato.
# Sin Cache-Control, el navegador estimaba la vigencia por la fecha del archivo y podía usar un app.js viejo.
VERSIONED_ASSETS = ('app.js', 'styles.css')
ASSET_REF = re.compile(r'(?P<attr>href|src)="(?P<file>app\.js|styles\.css)"')
IMMUTABLE = 'public, max-age=31536000, immutable'
API_CACHE = {
    '/api/mapa/barrios': 'public, max-age=86400, stale-while-revalidate=604800',
    '/api/radar': 'public, max-age=3600, stale-while-revalidate=86400',
}


def conditional(request, body, media_type, cache_control):
    """Respuesta con ETag del contenido; devuelve 304 sin cuerpo si el navegador ya tiene esa versión."""
    etag = f'"{sha256(body).hexdigest()[:20]}"'
    headers = {'ETag': etag, 'Cache-Control': cache_control}
    if etag in (tag.strip() for tag in request.headers.get('if-none-match', '').split(',')):
        return Response(status_code=304, headers=headers)
    return Response(body, media_type=media_type, headers=headers)


class SearchIn(BaseModel):
    barrio: str
    presupuesto: int = Field(ge=1)
    superficie: int = Field(ge=1)
    ambientes: int = Field(ge=1, le=20)
    moneda: str = 'USD'
    # Opcional: aviso por correo. El mail se reenvía a Make y no se guarda en la base local.
    email: str | None = Field(default=None, max_length=254)
    consentimiento: bool = False
    ambientes_o_mas: bool = False
    # Nivel pago elegido en «Precios» para anotarse en la primera tanda. Solo viaja con el alta por mail.
    interes: Literal['buscar', 'acompanado'] | None = None


class PreferenciasIn(BaseModel):
    texto: str = Field(min_length=1, max_length=2000)


def square(lon, lat, size_m):
    half_lat = size_m / 2 / 111_320
    half_lon = size_m / 2 / (111_320 * math.cos(math.radians(lat)))
    ring = [[lon - half_lon, lat - half_lat], [lon + half_lon, lat - half_lat], [lon + half_lon, lat + half_lat],
            [lon - half_lon, lat + half_lat], [lon - half_lon, lat - half_lat]]
    return {'type': 'Polygon', 'coordinates': [[[round(x, 6), round(y, 6)] for x, y in ring]]}


def collection(features):
    return {'type': 'FeatureCollection', 'features': features}


def point_features(items, kind, bbox):
    return [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [i['lon'], i['lat']]},
             'properties': {'kind': kind or i.get('kind'), 'name': i['name'], 'tooltip': i['tooltip'],
                            'line': i.get('line'), 'web': i.get('web'), 'elevators': i.get('elevators')}}
            for i in items if bbox is None or entorno.in_bbox(i['lon'], i['lat'], bbox)]


def create_app(demo_path=None, real_path=None, entorno_dir=None, raw_dir=None, web_dir=None,
               subscriptions_url=..., post=None, radar_dir=None, interprete=None, lugares=None):
    """`subscriptions_url` es el webhook de altas de Make; por defecto se lee MAKE_BUSQUEDAS_WEBHOOK_URL.

    `lugares` consulta Google Places para «Dónde comer»; por defecto se configura con GOOGLE_MAPS_API_KEY.
    """
    entorno_dir = Path(entorno_dir or ROOT / 'data/processed/entorno')
    # El índice de delitos armado se guarda solo con los CSV de siempre; con otra carpeta (las pruebas), no.
    crime_index_file = ROOT / 'data/local/indice_delitos.pickle' if raw_dir is None else None
    raw_dir = Path(raw_dir or ROOT / 'data/raw')
    web_dir = Path(web_dir or ROOT / 'web')
    radar_dir = Path(radar_dir or radar.RADAR_DIR)
    cache = {}
    index_lock = threading.Lock()
    layer_cache = {}  # (versión, capa, barrio, variante) → GeoJSON listo para el mapa
    interprete = interprete if interprete is not None else preferencias.Interprete.from_env(ROOT / 'data/local')
    lugares = lugares if lugares is not None else lugares_google.Lugares.from_env(ROOT / 'data/local')
    app = FastAPI(title='Lüga', docs_url='/api/docs', openapi_url='/api/openapi.json')
    versions = {}  # archivo → (mtime_ns, tamaño, hash corto); se recalcula si el archivo cambia

    def asset_version(name):
        path = web_dir / name
        if not path.exists():
            return None
        stat = path.stat()
        known = versions.get(name)
        if not known or known[:2] != (stat.st_mtime_ns, stat.st_size):
            known = versions[name] = (stat.st_mtime_ns, stat.st_size, sha256(path.read_bytes()).hexdigest()[:12])
        return known[2]

    @app.middleware('http')
    async def http_cache(request: Request, call_next):
        response = await call_next(request)
        if request.method not in ('GET', 'HEAD') or 'cache-control' in response.headers:
            return response
        if response.status_code not in (200, 304):
            response.headers['Cache-Control'] = 'no-store'  # que un error no quede guardado
            return response
        path = request.url.path
        name = path.lstrip('/')
        if name in VERSIONED_ASSETS and request.query_params.get('v') == asset_version(name):
            response.headers['Cache-Control'] = IMMUTABLE
        elif path in API_CACHE and response.status_code == 200:
            body = b''.join([chunk async for chunk in response.body_iterator])
            return conditional(request, body, response.headers.get('content-type'), API_CACHE[path])
        else:
            response.headers['Cache-Control'] = 'no-cache'
        return response

    # Comprime en gzip lo que pasa de 1 KB: las capas del mapa son JSON muy repetitivo y bajan de 1,6 MB a ~200 KB.
    # Se agrega después del middleware de caché para quedar por fuera y comprimir la respuesta final. Nivel 5:
    # casi el mismo tamaño que el 9 con una fracción del tiempo de CPU.
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)

    layers_lock = threading.Lock()

    def layers():
        marker = entorno_dir / 'resumen.json'
        stamp = marker.stat().st_mtime if marker.exists() else None
        if 'layers' not in cache or cache.get('stamp') != stamp:
            with layers_lock:  # el precalentado y el primer pedido no las cargan dos veces
                if 'layers' not in cache or cache.get('stamp') != stamp:
                    cache.update(stamp=stamp, layers=entorno.load(entorno_dir) if stamp else None, cercania=None)
        return cache['layers']

    def proximity_index():
        data = layers()
        if data is not None and cache.get('cercania') is None:
            cache['cercania'] = cercania.Cercania(data)
        return cache.get('cercania')

    stores = {}  # (modo, operación, rutas) → Store ya abierto

    def store_for(mode, operation):
        # Abrir la base corre las migraciones y, en la demo, vuelve a cargar el lote ficticio: son escrituras en
        # disco (unos 100 ms por pedido). Se hace una vez por base; si el archivo desaparece, se vuelve a abrir.
        paths = (demo_path or demo_base(), real_path or REAL_BASE)
        key = (mode, operation, *map(str, paths))
        store = stores.get(key)
        if store is None or not store.path.exists():
            store = stores[key] = open_store(mode == 'demo', operation, *paths)
        return store

    def db_signature(path):
        """Fecha y tamaño de la base (y de su -wal): cambian con cada escritura, también desde Streamlit o Make."""
        out = []
        for file in (path, path.with_name(path.name + '-wal')):
            try:
                stat = file.stat()
                out.append((stat.st_mtime_ns, stat.st_size))
            except FileNotFoundError:
                out.append(None)
        return tuple(out)

    def read(store, method):
        """Lecturas de la base que se repiten en cada pedido (los 4.000 avisos: ~70 ms; los períodos de delitos:
        ~35 ms). Se guardan hasta que el archivo cambia. El resultado se comparte: los llamadores no lo modifican."""
        key = ('lectura', str(store.path), method)
        signature = db_signature(store.path)
        hit = cache.get(key)
        if hit is None or hit[0] != signature:
            hit = cache[key] = (signature, getattr(store, method)())
        return hit[1]

    def check_barrio(name):
        if name not in OFFICIAL:
            raise HTTPException(404, f'{name} no es un barrio oficial de CABA.')
        return name

    def check_currency(operation, currency):
        if currency not in CURRENCIES[operation]:
            raise HTTPException(422, f"En {operation} la moneda tiene que ser {' o '.join(CURRENCIES[operation])}.")
        return currency

    def crime_source(store):
        crime_file, periods = read(store, 'crime_periods')
        if not crime_file:
            return None, periods, 'Todavía no se cargó un archivo del Mapa del Delito.'
        path = raw_dir / crime_file['filename']
        if not path.exists():
            return None, periods, f"Falta {crime_file['filename']} en data/raw/ para ubicar los hechos."
        key = ('digest', str(path), path.stat().st_mtime)
        if key not in cache:
            cache[key] = sha256(path.read_bytes()).hexdigest()
        if cache[key] != crime_file['digest']:
            return None, periods, f"{crime_file['filename']} en data/raw/ no es el mismo archivo que se cargó."
        return path, periods, None

    @app.post('/api/preferencias/interpretar', response_model=preferencias.Propuesta)
    def interpretar_preferencias(pedido: PreferenciasIn):
        try:
            return interprete.interpretar(pedido.texto)
        except preferencias.ErrorPreferencias as error:
            raise HTTPException(error.status, str(error)) from None

    @app.get('/api/estado')
    def state(modo: Mode = 'demo', operacion: Operation = 'venta'):
        store = store_for(modo, operacion)
        listings = read(store, 'listings')
        crime_file, periods = read(store, 'crime_periods')
        return {
            'modo': modo, 'operacion': operacion, 'monedas': CURRENCIES[operacion],
            'interpretar_preferencias': interprete.enabled,
            # «Dónde comer» usa datos de Google: solo con datos reales y clave configurada.
            'lugares': modo == 'real' and lugares.enabled,
            'catalogo': listings[0].get('source') if listings and listings[0].get('source') else None,
            'avisos': len(listings),
            'avisos_por_moneda': {c: sum((i.get('currency') or 'USD') == c for i in listings)
                                  for c in CURRENCIES[operacion]},
            'capas': layers() is not None,
            'delitos': None if modo == 'demo' or not crime_file else {
                'archivo': crime_file['filename'], 'periodos': periods},
        }

    @app.get('/api/barrios')
    def neighborhoods(modo: Mode = 'demo', operacion: Operation = 'venta', presupuesto: int = Query(110_000, ge=1),
                      superficie: int = Query(40, ge=1), ambientes: int = Query(2, ge=1), moneda: str = 'USD',
                      ambientes_o_mas: bool = False):
        check_currency(operacion, moneda)
        listings = read(store_for(modo, operacion), 'listings')
        summary = (layers() or {}).get('resumen', {})
        by_barrio = {}  # una sola pasada por los avisos, no una por cada uno de los 48 barrios
        for i in listings:
            if (i.get('currency') or 'USD') == moneda:
                by_barrio.setdefault(i['neighborhood'], []).append(i)
        rows = []
        for name in OFFICIAL:
            own = by_barrio.get(name, [])
            found = [i['price'] for i in own if matches(i, presupuesto, superficie, ambientes, moneda, ambientes_o_mas)]
            rows.append({'barrio': name, 'comuna': (summary.get(name) or {}).get('comuna'),
                         'avisos': len(own), 'coincidencias': len(found),
                         'mediana': int(median(found)) if found else None, 'entorno': summary.get(name)})
        rows.sort(key=lambda r: (-r['coincidencias'], r['barrio']))
        return {'moneda': moneda, 'barrios': rows}

    @app.get('/api/barrios/{barrio}/avisos')
    def listings_for(barrio: str, modo: Mode = 'demo', operacion: Operation = 'venta',
                     presupuesto: int = Query(110_000, ge=1), superficie: int = Query(40, ge=1),
                     ambientes: int = Query(2, ge=1), moneda: str = 'USD', ambientes_o_mas: bool = False,
                     capas: list[str] = Query(default=[]),
                     nivel: Literal['inicial', 'primario', 'secundario'] = 'primario'):
        check_barrio(barrio)
        check_currency(operacion, moneda)
        for name in capas:
            if name not in cercania.CAPAS:
                raise HTTPException(422, f"Sin distancias para la capa {name}. Opciones: {', '.join(cercania.CAPAS)}.")
        own = [i for i in read(store_for(modo, operacion), 'listings') if i['neighborhood'] == barrio]
        found = [i for i in own if matches(i, presupuesto, superficie, ambientes, moneda, ambientes_o_mas)]
        found.sort(key=lambda i: (i['price'], -i['covered_area']))
        # Referencia: todos los avisos vigentes del barrio en la moneda, no solo los que encajan con el filtro.
        comparacion = comparables.comparar_todos(found, own)
        data = layers()
        shape = next((f['geometry'] for f in (data['barrios']['features'] if data else [])
                      if f['properties'].get('barrio') == barrio), None)
        avisos = []
        for i in found:
            location = ubicacion.quality(i.get('longitude'), i.get('latitude'), shape)
            avisos.append({
                'id': i['id'], 'precio': i['price'], 'moneda': i.get('currency') or 'USD',
                'superficie': i['covered_area'], 'superficie_total': i.get('total_area_m2'), 'ambientes': i['rooms'],
                'expensas': i.get('expenses'), 'capturado': i.get('captured_at'),
                'cocheras': i.get('garages'),
                'pin_utilizable': modo == 'real' and usable_pin(i),
                # Punto para el mapa: solo si es coherente con el barrio (ver precio_entorno/ubicacion.py).
                'ubicacion': location,
                'lat': i['latitude'] if location else None, 'lon': i['longitude'] if location else None,
                'enlace': i.get('url') if modo == 'real' else None,
                # Rasgos leídos del texto del aviso: 1 lo menciona, 0 el texto no lo menciona, None sin texto.
                'rasgos': {name: i.get(column) for name, column in descripcion.SPANISH_NAMES.items()},
                'antiguedad': i.get('age_years'), 'piso': i.get('floor'),
                'comparacion': comparacion[i['id']]})
        index = proximity_index() if capas else None
        if capas:
            # Distancias desde el punto publicado; un aviso sin ubicación usable queda sin distancia.
            located = [a for a in avisos if a['ubicacion']]
            values = index.calcular([a['lon'] for a in located], [a['lat'] for a in located], capas, nivel) if index else []
            for aviso in avisos:
                aviso['cercania'] = None
            for aviso, value in zip(located, values):
                aviso['cercania'] = value
        return {'avisos': avisos, **({'cercania': {
            'disponible': index is not None, 'capas': capas, 'nivel': nivel,
            'metodo': 'Línea recta desde el punto que publica la fuente, sin precisión declarada; '
                      'redondeada a decenas de metros. No es un recorrido por calles.'}} if capas else {})}

    @app.get('/api/estacionamientos')
    def parking_locations(barrio: str,
                          lat: float | None = Query(None, ge=-34.73, le=-34.52),
                          lon: float | None = Query(None, ge=-58.54, le=-58.32),
                          radio: int = Query(500, ge=100, le=2000)):
        check_barrio(barrio)
        if (lat is None) != (lon is None):
            raise HTTPException(422, 'Se requieren ambas coordenadas.')
        points = (layers() or {}).get('puntos', {})
        found = []
        for row in points.get('estacionamiento', []):
            distance = concentracion.distance_m(lon, lat, row['lon'], row['lat']) if lat is not None else None
            if (distance is None and row['barrio'] != barrio) or (distance is not None and distance > radio):
                continue
            found.append(dict(nombre=row['name'], detalle=row['tooltip'], barrio=row['barrio'],
                              lat=row['lat'], lon=row['lon'], distancia_m=distance))
        found.sort(key=lambda r: (r['distancia_m'] or 0, r['detalle']))
        for row in found:
            if row['distancia_m'] is not None:
                row['distancia_m'] = round(row['distancia_m'])
        return dict(disponible='estacionamiento' in points, estacionamientos=found,
                    periodo=entorno.GARAJES_PERIODO, fuente=entorno.GARAJES_FUENTE)

    @app.get('/api/cocheras')
    def parking_rentals(barrio: str, moneda: Literal['ARS', 'USD'] = 'ARS',
                        presupuesto: float = Query(1_000_000, gt=0, allow_inf_nan=False),
                        lat: float | None = Query(None, ge=-34.73, le=-34.52),
                        lon: float | None = Query(None, ge=-58.54, le=-58.32),
                        radio: int = Query(500, ge=100, le=2000)):
        check_barrio(barrio)
        if (lat is None) != (lon is None):
            raise HTTPException(422, 'Se requieren ambas coordenadas.')
        try:
            rows = cocheras.load()
        except (ValueError, KeyError, TypeError, OSError):
            raise HTTPException(503, 'El catálogo de cocheras requiere revisión.') from None
        candidates = [r for r in (rows or []) if r['moneda'] == moneda and r['precio'] <= presupuesto]
        if lat is None:
            candidates = [r for r in candidates if r['barrio'] == barrio]
        else:
            candidates = [dict(r, distancia_m=concentracion.distance_m(lon, lat, r['lon'], r['lat']))
                          for r in candidates if r['lat'] is not None]
            candidates = [r for r in candidates if r['distancia_m'] <= radio]
            candidates = [dict(r, distancia_m=round(r['distancia_m'])) for r in candidates]
        found = sorted(candidates,
                       key=lambda r: r['precio'])
        return {'disponible': rows is not None, 'avisos': found}

    @app.get('/api/colectivos')
    def bus_lines(barrio: str):
        check_barrio(barrio)
        lines = (layers() or {}).get('colectivos')
        found = [] if lines is None else [
            {'linea': name, 'ramales': len(line['ramales'])}
            for name, line in lines.items() if barrio in line['barrios']]
        return {'disponible': lines is not None, 'lineas': found,
                'periodo': colectivos.PERIODO, 'fuente': colectivos.FUENTE}

    @app.get('/api/colectivos/{linea}')
    def bus_route(linea: str):
        line = ((layers() or {}).get('colectivos') or {}).get(linea)
        if line is None:
            raise HTTPException(404, 'Línea sin recorrido cargado.')
        return {'type': 'Feature', 'geometry': {'type': 'MultiLineString', 'coordinates': line['recorrido']},
                'properties': {'linea': linea, 'ramales': line['ramales'], 'barrios': line['barrios'],
                               'periodo': colectivos.PERIODO}}

    @app.get('/api/mapa/barrios')
    def neighborhood_shapes():
        data = layers()
        if data is None:
            raise HTTPException(503, 'Las capas no se generaron. Ejecutá python -m precio_entorno.entorno.')
        return data['barrios']

    @app.get('/api/hospitales')
    def hospitals():
        """Hospitales de toda la ciudad para elegir un lugar fijo. Se manda la lista completa: la elección de la
        persona (que puede revelar un tratamiento) queda en su navegador y no viaja en ningún pedido."""
        data = layers()
        if data is None:
            raise HTTPException(503, 'Las capas no se generaron. Ejecutá python -m precio_entorno.entorno.')
        rows = [{'nombre': h['name'], 'barrio': h.get('barrio'), 'lon': h['lon'], 'lat': h['lat'],
                 'especialidad': (h.get('tooltip') or '').split(' · ', 1)[1] if ' · ' in (h.get('tooltip') or '') else None}
                for h in data['puntos'].get('hospitales', []) if h.get('lon') is not None and h.get('lat') is not None]
        return {'hospitales': sorted(rows, key=lambda r: r['nombre'])}

    @app.get('/api/mapa/capas')
    def map_layers(barrio: str, capas: list[str] = Query(default=[]), nivel: str = 'primario',
                   ruido: Literal['diurno', 'nocturno'] = 'diurno'):
        check_barrio(barrio)
        data = layers()
        if data is None:
            raise HTTPException(503, 'Las capas no se generaron. Ejecutá python -m precio_entorno.entorno.')
        bbox = entorno.bbox_of(data['barrios'], barrio)
        points = data['puntos']
        for name in capas:
            if name not in LAYER_KEYS:
                raise HTTPException(422, f'Capa desconocida: {name}.')

        def build(name):
            out = {}
            if name == 'subte':
                out['subte'] = collection(point_features(points['subte'], 'subte', bbox))
            if name == 'escuelas':
                out['escuelas'] = collection(point_features(
                    [s for s in points['escuelas'] if nivel in s['levels']], 'escuela', bbox))
            if name == 'salud':
                out['salud'] = collection(point_features(points['cesac'], 'cesac', bbox)
                                          + point_features(points['hospitales'], 'hospital', bbox))
            if name in CITYWIDE:
                # Toda la ciudad: el mapa los muestra fuera del barrio al desplazarse.
                features = point_features(points.get(name, []), CITYWIDE[name], None)
                out[name] = {**collection(features), 'disponible': name in points}
            if name == 'colectivos':
                lines = data.get('colectivos')
                out['colectivos'] = {**collection(colectivos.barrio_features(lines or {}, barrio, bbox)),
                                     'disponible': lines is not None}
            if name == 'verdes':
                out['verdes'] = entorno.features_in(data['verdes'], bbox)
            if name in ('ecobici', 'bibliotecas', 'rampas'):
                kind = {'ecobici': 'ecobici', 'bibliotecas': 'biblioteca', 'rampas': 'rampa'}[name]
                out[name] = {**collection(point_features(points.get(name, []), kind, bbox)), 'disponible': name in points}
            if name == 'recreacion':
                # Cada punto lleva su tipo (cine, teatro, museo, cultural) para el color y la leyenda.
                out[name] = {**collection(point_features(points.get(name, []), None, bbox)), 'disponible': name in points}
            if name == 'ciclovias':
                lanes = data.get('ciclovias')
                out['ciclovias'] = {**(entorno.features_in(lanes, bbox) if lanes else collection([])),
                                    'disponible': lanes is not None}
            if name == 'riesgo':
                out['riesgo'] = entorno.features_in(data['riesgo_hidrico'], bbox)
            if name == 'ruido':
                # Solo las celdas asignadas al barrio, como punto en su centro: el mapa dibuja un brillo por celda.
                out['ruido'] = {**collection([
                    {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
                     'properties': {'tipico': typical, 'maximo': top}}
                    for lon, lat, typical, top, cell_barrio in data['ruido'][ruido] if cell_barrio == barrio]),
                    'celda_m': data['ruido']['celda_m'], 'umbral_dba': data['ruido']['umbral_dba'][ruido]}
            return out[name]

        # Las capas no cambian entre pedidos: se guardan por versión de las capas, barrio y variante.
        out = {}
        for name in capas:
            key = ('capa', cache.get('stamp'), name, None if name in CITYWIDE else barrio,
                   nivel if name == 'escuelas' else None, ruido if name == 'ruido' else None)
            if key not in layer_cache:
                if len(layer_cache) >= 300:
                    layer_cache.pop(next(iter(layer_cache)))
                # Se guarda ya convertida a JSON: convertir cientos de KB en cada pedido era lo que más tardaba.
                layer_cache[key] = json.dumps(build(name), ensure_ascii=False, separators=(',', ':'))
            out[name] = layer_cache[key]
        body = '{' + ','.join(f'{json.dumps(name)}:{texto}' for name, texto in out.items()) + '}'
        return Response(content=body, media_type='application/json')

    @app.get('/api/delitos')
    def crimes(barrio: str, periodo: str | None = None, tipo: str | None = None,
               modo: Mode = 'real', operacion: Operation = 'venta'):
        check_barrio(barrio)
        if modo == 'demo':
            return {'disponible': False, 'motivo': 'En la demo los delitos son ficticios y no se ubican en el mapa.'}
        data = layers()
        path, periods, reason = crime_source(store_for(modo, operacion))
        if reason or data is None:
            return {'disponible': False, 'motivo': reason or 'Las capas no se generaron.', 'periodos': periods}
        period = periodo if periodo in periods else periods[0]
        bbox = entorno.bbox_of(data['barrios'], barrio)
        key = ('delitos', str(path), period, tipo, bbox)
        if key not in cache:
            cache[key] = entorno.crime_cells(path, period, tipo, bbox)
        cells, kinds = cache[key]
        if tipo and tipo not in kinds:
            cells = []
        return {'disponible': True, 'archivo': path.name, 'periodo': period, 'periodos': periods,
                'tipo': tipo, 'tipos': kinds, 'maximo': max((c['hechos'] for c in cells), default=0),
                'celdas': collection([{'type': 'Feature', 'geometry': square(c['lon'], c['lat'], 200),
                                       'properties': {'hechos': c['hechos']}} for c in cells])}

    @app.get('/api/delitos/concentracion')
    def crime_concentration(barrio: str, inmueble: str | None = None,
                            radio: int = Query(500, ge=250, le=1000),
                            tipo: Literal['todos', 'robo', 'hurto'] = 'todos',
                            franja: Literal['todas', 'diurno', 'nocturno', 'sin_dato'] = 'todas',
                            anio: int | None = None, modo: Mode = 'real', operacion: Operation = 'venta'):
        check_barrio(barrio)
        if modo == 'demo':
            return {'disponible': False, 'motivo': 'Los avisos ficticios no se cruzan con delitos reales.'}
        store = store_for(modo, operacion)
        listing = None
        if inmueble is not None:
            listing = next((i for i in read(store, 'listings') if i['id'] == inmueble and i['neighborhood'] == barrio), None)
            if listing is None:
                raise HTTPException(404, 'El inmueble no pertenece al catálogo y barrio seleccionados.')
        paths = concentracion.source_paths(raw_dir)
        if not paths:
            path, _, reason = crime_source(store)
            if reason:
                return {'disponible': False, 'motivo': reason}
            paths = (path,)
        signature = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
        try:
            # El índice tarda varios segundos en armarse: con el candado, el precalentado y un pedido no lo arman dos veces.
            with index_lock:
                if cache.get('concentracion_signature') != signature:
                    index = concentracion.load_index(paths, crime_index_file)
                    cache.update(concentracion_signature=signature, concentracion_index=index)
            data = layers()
            if data is None:
                return {'disponible': False, 'motivo': 'Las capas no se generaron.'}
            result = cache['concentracion_index'].analyze(
                entorno.bbox_of(data['barrios'], barrio), listing, radio, tipo, franja, anio)
        except (OSError, ValueError) as error:
            raise HTTPException(422, str(error)) from error
        if result['disponible']:
            result['celdas'] = collection([
                {'type': 'Feature', 'geometry': square(c['lon'], c['lat'], concentracion.CELL_M),
                 'properties': {k: v for k, v in c.items() if k not in ('lon', 'lat')}} for c in result['celdas']])
            result['radios'] = collection([
                {'type': 'Feature', 'geometry': concentracion.circle(listing['longitude'], listing['latitude'], r),
                 'properties': {'radio_m': r, 'seleccionado': r == radio}} for r in concentracion.RADIOS
            ]) if listing else collection([])
        return result

    @app.get('/api/barrios/{barrio}/parecidos')
    def similar(barrio: str, modo: Mode = 'demo', operacion: Operation = 'venta',
                presupuesto: int = Query(110_000, ge=1), superficie: int = Query(40, ge=1),
                ambientes: int = Query(2, ge=1), moneda: str = 'USD', ambientes_o_mas: bool = False,
                prefs: list[str] = Query(default=[]), nivel: Literal['inicial', 'primario', 'secundario'] = 'primario'):
        """Barrios con un entorno parecido, sin puntaje. Los precios se informan aparte, no se comparan."""
        check_barrio(barrio)
        rows = neighborhoods(modo, operacion, presupuesto, superficie, ambientes, moneda, ambientes_o_mas)['barrios']
        return {'barrio': barrio,
                'parecidos': barrios_parecidos.parecidos(barrio, rows, [p for p in prefs if p in barrios_parecidos.CAPAS],
                                                         nivel)}

    @app.get('/api/barrios/{barrio}/lugares')
    def places(barrio: str, tipo: Literal['restaurantes', 'cafes', 'bares'] = 'restaurantes', modo: Mode = 'real'):
        """Lugares más valorados en Google, consultados en vivo. La respuesta no se guarda ni se cachea."""
        check_barrio(barrio)
        if modo == 'demo':
            return {'disponible': False, 'motivo': 'demo',
                    'mensaje': 'En la demo no se consultan lugares reales.'}
        if not lugares.enabled:
            return {'disponible': False, 'motivo': 'config',
                    'mensaje': 'La consulta a Google no está configurada.'}
        data = layers()
        shape = next((f['geometry'] for f in (data['barrios']['features'] if data else [])
                      if f['properties'].get('barrio') == barrio), None)
        if shape is None:
            return {'disponible': False, 'motivo': 'capas', 'mensaje': 'Las capas no se generaron.'}
        try:
            result = lugares.buscar(barrio, shape, entorno.bbox_of(data['barrios'], barrio, margin_m=100), tipo)
        except lugares_google.ErrorLugares as error:
            return {'disponible': False, 'motivo': error.motivo, 'mensaje': str(error)}
        return {'disponible': True, 'tipo': tipo, 'fuente': 'Google Maps', **result}

    @app.get('/api/radar')
    def news_radar(periodo: str | None = None):
        """Capa editorial: cobertura de prensa por barrio. No depende del modo ni de la operación."""
        return radar.boletin(radar_dir, periodo)

    @app.get('/api/fuentes')
    def sources():
        data = layers()
        return data['fuentes'] if data else {'generado': None, 'fuentes': []}

    @app.get('/api/busquedas')
    def searches(modo: Mode = 'demo', operacion: Operation = 'venta'):
        store = store_for(modo, operacion)
        return {
            'busquedas': [{'id': s['id'], 'barrio': s['neighborhood'], 'presupuesto': s['budget'],
                           'superficie': s['min_area'], 'ambientes': s['rooms'],
                           'moneda': s.get('currency') or 'USD', 'ambientes_o_mas': bool(s['rooms_or_more'])} for s in store.searches()],
            'alertas': [{'busqueda': a['search_id'], 'id': a['id'], 'barrio': a['neighborhood'],
                         'precio': a['price'], 'moneda': a['currency'], 'superficie': a['covered_area'],
                         'ambientes': a['rooms'], 'expensas': a.get('expenses'),
                         'estado': a.get('status') or 'activo',
                         'enlace': a.get('url') if modo == 'real' else None} for a in store.alerts()],
        }

    @app.delete('/api/busquedas/{busqueda_id}')
    def delete_search(busqueda_id: int, modo: Mode = 'demo', operacion: Operation = 'venta'):
        # El alta por correo vive en Make: se da de baja con el enlace de cada correo, no desde acá.
        if not store_for(modo, operacion).delete_search(busqueda_id):
            raise HTTPException(404, 'Esa alerta ya no existe. Puede que la hayas quitado en otra pestaña.')
        return {'quitada': True}

    def subscriptions_webhook():
        if subscriptions_url is not ...:
            return subscriptions_url
        try:
            return make_webhook.webhook_url(variable='MAKE_BUSQUEDAS_WEBHOOK_URL')
        except ValueError:
            return None

    @app.post('/api/busquedas')
    def save_search(search: SearchIn, modo: Mode = 'demo', operacion: Operation = 'venta'):
        check_barrio(search.barrio)
        check_currency(operacion, search.moneda)
        email = (search.email or '').strip() or None
        if email:
            if modo != 'real':
                raise HTTPException(422, 'El aviso por correo solo funciona con datos reales.')
            if not EMAIL.fullmatch(email):
                raise HTTPException(422, 'Revisá el mail: no parece una dirección válida.')
            if not search.consentimiento:
                raise HTTPException(422, 'Para recibir correos, aceptá el aviso de uso del mail.')
        created = store_for(modo, operacion).save_search(
            search.barrio, search.presupuesto, search.superficie, search.ambientes, search.moneda, search.ambientes_o_mas)
        result = {'creada': created, 'correo': None}
        if email:
            url = subscriptions_webhook()
            if not url:
                result['correo'] = {'enviado': False, 'motivo': 'El aviso por correo no está configurado.'}
            else:
                body = make_webhook.subscription(
                    secrets.token_urlsafe(9), operacion, search.model_dump(), email,
                    datetime.now(timezone.utc).replace(microsecond=0).isoformat())
                sent = make_webhook.send(url, body, **({'post': post} if post else {}))
                result['correo'] = ({'enviado': True} if sent['enviado'] else
                                    {'enviado': False, 'motivo': 'Make no recibió el alta. Probá de nuevo más tarde.'})
        return result

    def warm_up():
        """Carga las capas y arma el índice de delitos antes del primer pedido (el índice tarda unos 8 s)."""
        try:
            if layers() is not None:
                proximity_index()
                crime_concentration(OFFICIAL[0], None, 500, 'todos', 'todas', None, 'real', 'venta')
        except Exception:  # noqa: BLE001 — precalentar es opcional; el pedido real informa el error
            pass

    app.state.warm_up = warm_up

    if (web_dir / 'index.html').exists():
        @app.get('/', include_in_schema=False)
        @app.get('/index.html', include_in_schema=False)
        def index_page(request: Request):
            html = (web_dir / 'index.html').read_text(encoding='utf-8')

            def versioned(match):
                version = asset_version(match['file'])
                return f'{match["attr"]}="{match["file"]}?v={version}"' if version else match[0]

            return conditional(request, ASSET_REF.sub(versioned, html).encode('utf-8'),
                               'text/html; charset=utf-8', 'no-cache')

    if web_dir.exists():
        app.mount('/', StaticFiles(directory=web_dir, html=True), name='web')
    return app


app = create_app()


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--puerto', type=int, default=8000)
    args = parser.parse_args()
    threading.Thread(target=app.state.warm_up, name='precalentar', daemon=True).start()
    uvicorn.run(app, host='127.0.0.1', port=args.puerto)


if __name__ == '__main__':
    main()
