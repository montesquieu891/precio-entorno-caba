"""Distancias en línea recta desde el punto que publica cada aviso hasta el entorno más cercano.

Lo usa el explorador de necesidades (docs/plan-explorador-necesidades.md). El origen es el punto que publica la
fuente, sin precisión declarada; la API solo lo usa si `ubicacion.quality` lo considera coherente con el barrio.

- Distancia plana local (equirectangular, a la latitud media de CABA), válida a escala de barrio. No es un
  recorrido por calles.
- Se redondea a decenas de metros para no sugerir más exactitud de la que tiene el punto.
- Plazas y parques: distancia al borde del polígono, muestreado cada PASO_M metros (error de pocos metros).
- Ruido: el nivel típico diurno de la celda de 100 m que contiene el punto, o None si no hay celda relevada.
- Ciclovías: distancia al tramo más cercano, muestreado como los bordes de las plazas. No dice si el recorrido
  sigue ni si el tramo es protegido.
- Subte con ascensor: la estación más cercana con al menos un ascensor informado por SBASE. No dice si funciona.
- Recreación: el cine, teatro, museo o centro cultural más cercano de OpenStreetMap, con su nombre y tipo.
"""

import math

import numpy as np

CAPAS = ('subte', 'escuelas', 'salud', 'verdes', 'ruido', 'ciclovias', 'ecobici', 'bibliotecas', 'recreacion',
         'universidades', 'trenes')
NIVELES = ('inicial', 'primario', 'secundario')
M_LAT = 111_320
KX = M_LAT * math.cos(math.radians(-34.62))
PASO_M = 20
BLOQUE = 2_000  # Puntos de capa por bloque: acota la memoria de la matriz avisos × puntos.
CELDA_M = 250
BUSQUEDA_MAX_M = 8_000


def metros(lons, lats):
    """Coordenadas planas en metros (x, y) para arrays de longitud y latitud."""
    return np.column_stack([np.asarray(lons, float) * KX, np.asarray(lats, float) * M_LAT])


def redondear(distancia):
    return None if distancia is None or not math.isfinite(distancia) else int(round(distancia / 10) * 10)


def _todos_contra_todos(origenes, puntos):
    mejor = np.full(len(origenes), np.inf)
    indice = np.full(len(origenes), -1)
    for inicio in range(0, len(puntos), BLOQUE):
        bloque = puntos[inicio:inicio + BLOQUE]
        d = np.hypot(origenes[:, None, 0] - bloque[None, :, 0], origenes[:, None, 1] - bloque[None, :, 1])
        cerca = d.argmin(axis=1)
        valor = d[np.arange(len(origenes)), cerca]
        mejora = valor < mejor
        mejor[mejora], indice[mejora] = valor[mejora], cerca[mejora] + inicio
    return mejor, indice


class Puntos:
    """Puntos de una capa en metros planos, agrupados en una grilla de CELDA_M para buscar solo cerca."""

    def __init__(self, xy):
        self.xy = np.asarray(xy, float).reshape(-1, 2)
        self.grilla = {}
        if len(self.xy):
            celdas = np.floor(self.xy / CELDA_M).astype(np.int64)
            orden = np.lexsort((celdas[:, 1], celdas[:, 0]))
            claves, inicios = np.unique(celdas[orden], axis=0, return_index=True)
            for (cx, cy), a, b in zip(claves, inicios, [*inicios[1:], len(orden)]):
                self.grilla[int(cx), int(cy)] = orden[a:b]

    def __len__(self):
        return len(self.xy)

    def alrededor(self, cx, cy, k):
        partes = [self.grilla[x, y] for x in range(cx - k, cx + k + 1) for y in range(cy - k, cy + k + 1)
                  if (x, y) in self.grilla]
        return np.concatenate(partes) if partes else np.zeros(0, int)


def cercanos(origenes, capa):
    """Distancia mínima y su índice para cada origen; (inf, -1) si la capa está vacía.

    Los orígenes se agrupan por celda de la grilla. Cada grupo se compara con las celdas a k celdas o menos de la
    suya: un punto más allá está a más de k × CELDA_M en algún eje, así que un mínimo ≤ k × CELDA_M es exacto. Si
    algún origen del grupo no lo alcanza, se duplica k; pasado BUSQUEDA_MAX_M se compara con la capa entera.
    """
    if not isinstance(capa, Puntos):
        capa = Puntos(capa)
    mejor, indice = np.full(len(origenes), np.inf), np.full(len(origenes), -1)
    if not len(origenes) or not len(capa):
        return mejor, indice
    celdas = np.floor(origenes / CELDA_M).astype(np.int64)
    claves, grupo = np.unique(celdas, axis=0, return_inverse=True)
    for g, (cx, cy) in enumerate(claves):
        miembros = np.flatnonzero(grupo.ravel() == g)
        mejor[miembros], indice[miembros] = _cercanos_de_celda(origenes[miembros], capa, int(cx), int(cy))
    return mejor, indice


def _cercanos_de_celda(origenes, capa, cx, cy):
    """Distancia mínima e índice para los orígenes de una celda, ampliando la búsqueda de a k = 1, 2, 4…"""
    k = 1
    while k * CELDA_M <= BUSQUEDA_MAX_M:
        candidatos = capa.alrededor(cx, cy, k)
        d, i = _todos_contra_todos(origenes, capa.xy[candidatos])
        if len(candidatos) and np.all(d <= k * CELDA_M):
            return d, np.where(i >= 0, candidatos[np.maximum(i, 0)], -1)
        k *= 2
    candidatos = np.arange(len(capa))
    d, i = _todos_contra_todos(origenes, capa.xy[candidatos])
    return d, np.where(i >= 0, candidatos[np.maximum(i, 0)], -1)


def anillos(geometria):
    """Líneas de un polígono (sus anillos) o de una línea; `bordes` las muestrea igual."""
    if geometria['type'] == 'Polygon':
        return geometria['coordinates']
    if geometria['type'] == 'MultiPolygon':
        return [ring for poligono in geometria['coordinates'] for ring in poligono]
    if geometria['type'] == 'LineString':
        return [geometria['coordinates']]
    if geometria['type'] == 'MultiLineString':
        return geometria['coordinates']
    return []


def bordes(coleccion, paso=PASO_M):
    """Puntos del borde de cada polígono, cada `paso` metros como máximo, en metros planos."""
    rings = [ring for feature in coleccion.get('features', []) for ring in anillos(feature.get('geometry') or {'type': None})]
    salida = [parte for ring in rings for parte in _muestrear(ring, paso)]
    return np.vstack(salida) if salida else np.zeros((0, 2))


def _muestrear(ring, paso):
    """Puntos de una línea cada `paso` metros como máximo, en metros planos."""
    xy = metros(*np.asarray(ring, float)[:, :2].T)
    if len(xy) < 2:
        return [xy]
    a, delta = xy[:-1], np.diff(xy, axis=0)
    partes = np.maximum(1, np.ceil(np.hypot(delta[:, 0], delta[:, 1]) / paso)).astype(int)
    tramo = np.repeat(np.arange(len(a)), partes)
    t = (np.arange(partes.sum()) - np.repeat(np.cumsum(partes) - partes, partes)) / partes[tramo]
    return [a[tramo] + t[:, None] * delta[tramo], xy[-1:]]


class Cercania:
    """Índice de las capas del entorno; se arma una vez por versión de las capas."""

    def __init__(self, capas):
        puntos = capas['puntos']

        def de(items):
            items = list(items)
            return items, Puntos(metros([i['lon'] for i in items], [i['lat'] for i in items]) if items else [])

        self.subte, self.subte_xy = de(puntos.get('subte', []))
        self.ascensor, self.ascensor_xy = de(s for s in puntos.get('subte', []) if (s.get('elevators') or 0) > 0)
        self.escuelas = {nivel: de(e for e in puntos.get('escuelas', []) if nivel in e.get('levels', ()))[1]
                         for nivel in NIVELES}
        self.cesac = de(puntos.get('cesac', []))[1]
        self.hospitales = de(puntos.get('hospitales', []))[1]
        self.verdes = Puntos(bordes(capas.get('verdes') or {}))
        self.ciclovias = Puntos(bordes(capas.get('ciclovias') or {}))
        self.ecobici = de(puntos.get('ecobici', []))[1]
        self.bibliotecas = de(puntos.get('bibliotecas', []))[1]
        self.recreacion, self.recreacion_xy = de(puntos.get('recreacion', []))
        self.universidades, self.universidades_xy = de(puntos.get('universidades', []))
        self.trenes, self.trenes_xy = de(puntos.get('trenes', []))
        # Sin la capa cargada no se informa distancia (None), en lugar de «ninguna cerca».
        self.disponibles = {'ciclovias': bool(capas.get('ciclovias')), 'ecobici': 'ecobici' in puntos,
                            'bibliotecas': 'bibliotecas' in puntos, 'recreacion': 'recreacion' in puntos,
                            'universidades': 'universidades' in puntos, 'trenes': 'trenes' in puntos}
        ruido = capas.get('ruido') or {}
        self.celda_m = ruido.get('celda_m', 100)
        # Una grilla por período: las celdas relevadas de día y de noche no son exactamente las mismas.
        self.ruido = {}
        for periodo in ('diurno', 'nocturno'):
            celdas = ruido.get(periodo, [])
            self.ruido[periodo] = (Puntos(metros([c[0] for c in celdas], [c[1] for c in celdas]) if celdas else []),
                                   [c[2] for c in celdas])

    def calcular(self, lons, lats, capas, nivel='primario'):
        """Una entrada por origen, con las claves de las capas pedidas."""
        if not len(lons):
            return []
        origen = metros(lons, lats)
        salida = [{} for _ in range(len(origen))]

        def poner(clave, distancias, extra=None):
            for i, d in enumerate(distancias):
                valor = {'m': redondear(float(d))}
                if extra and valor['m'] is not None:
                    valor.update(extra(i))
                salida[i][clave] = valor

        if 'subte' in capas:
            d, idx = cercanos(origen, self.subte_xy)
            poner('subte', d, lambda i: {'estacion': self.subte[idx[i]]['name'],
                                         'linea': self.subte[idx[i]].get('line')})
            d, idx_a = cercanos(origen, self.ascensor_xy)
            poner('subte_ascensor', d, lambda i: {'estacion': self.ascensor[idx_a[i]]['name'],
                                                  'linea': self.ascensor[idx_a[i]].get('line')})
        if 'escuelas' in capas:
            poner('escuela', cercanos(origen, self.escuelas[nivel])[0], lambda i: {'nivel': nivel})
        if 'salud' in capas:
            poner('cesac', cercanos(origen, self.cesac)[0])
            poner('hospital', cercanos(origen, self.hospitales)[0])
        if 'verdes' in capas:
            poner('plaza', cercanos(origen, self.verdes)[0])
        for capa, clave, indice in (('ciclovias', 'ciclovia', self.ciclovias), ('ecobici', 'ecobici', self.ecobici),
                                    ('bibliotecas', 'biblioteca', self.bibliotecas)):
            if capa in capas:
                poner(clave, cercanos(origen, indice)[0] if self.disponibles[capa] else [math.inf] * len(origen))
        if 'recreacion' in capas:
            if self.disponibles['recreacion']:
                d, idx = cercanos(origen, self.recreacion_xy)
                poner('recreacion', d, lambda i: {'nombre': self.recreacion[idx[i]]['name'],
                                                  'tipo': self.recreacion[idx[i]]['kind']})
            else:
                poner('recreacion', [math.inf] * len(origen))
        if 'universidades' in capas:
            if self.disponibles['universidades']:
                d, idx = cercanos(origen, self.universidades_xy)
                poner('universidad', d, lambda i: {'nombre': self.universidades[idx[i]]['name'],
                                                   'unidad': self.universidades[idx[i]].get('unit')})
            else:
                poner('universidad', [math.inf] * len(origen))
        if 'trenes' in capas:
            if self.disponibles['trenes']:
                d, idx = cercanos(origen, self.trenes_xy)
                poner('tren', d, lambda i: {'estacion': self.trenes[idx[i]]['name'], 'linea': self.trenes[idx[i]]['line']})
            else:
                poner('tren', [math.inf] * len(origen))
        if 'ruido' in capas:
            # La celda que contiene el punto: el centro más cercano a no más de media celda en cada eje.
            for periodo, (grilla, valores) in self.ruido.items():
                self._poner_ruido(salida, origen, f'ruido_{periodo}', grilla, valores)
        return salida

    def _poner_ruido(self, salida, origen, clave, grilla, valores):
        """Nivel de ruido de la celda que contiene cada origen, o None si cae fuera de la grilla."""
        _, idx = cercanos(origen, grilla)
        for i, j in enumerate(idx):
            dentro = j >= 0 and np.all(np.abs(grilla.xy[j] - origen[i]) <= self.celda_m / 2 + 1)
            salida[i][clave] = {'dba': valores[j] if dentro else None}
