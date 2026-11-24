"""Calidad de la ubicación publicada de un aviso, para dibujarlo en el mapa.

Las fuentes publican coordenadas sin precisión en metros. Solo se controla que el punto sea coherente con
el barrio del aviso:

- `publicada`: cae dentro del barrio o a menos de BORDE_M de su límite (un pin en la vereda de enfrente
  del límite sigue siendo plausible);
- `aproximada`: cae a entre BORDE_M y MAX_M del barrio;
- `None`: no hay coordenadas o el punto queda a más de MAX_M, lo que contradice el barrio del aviso.

Sirve para mostrar el aviso en el mapa. No habilita el cruce con delitos alrededor del aviso, que sigue
exigiendo precisión declarada (`importing.usable_pin`).
"""

import math

import numpy as np

from .entorno import inside, polygons

BORDE_M = 150
MAX_M = 500
PUBLICADA, APROXIMADA = 'publicada', 'aproximada'


def distance_to_polygons_m(lon, lat, shapes):
    """Distancia en metros del punto al borde más cercano (aproximación plana, válida a escala de barrio)."""
    scale = 111_320 * math.cos(math.radians(lat))
    rings = [ring for polygon in shapes for ring in polygon]
    return min((distance_to_ring_m(lon, lat, ring, scale) for ring in rings), default=math.inf)


def distance_to_ring_m(lon, lat, ring, scale):
    """Distancia en metros del punto al tramo más cercano de un anillo; infinito si no tiene tramos."""
    ring = np.asarray(ring, float)[:, :2]
    x, y = (ring[:, 0] - lon) * scale, (ring[:, 1] - lat) * 111_320
    x1, y1, dx, dy = x[:-1], y[:-1], np.diff(x), np.diff(y)
    t = np.clip(-(x1 * dx + y1 * dy) / np.maximum(dx * dx + dy * dy, 1e-9), 0, 1)
    return float(np.hypot(x1 + t * dx, y1 + t * dy).min()) if len(t) else math.inf


def quality(lon, lat, geometry):
    """`publicada`, `aproximada` o None para un punto y la geometría GeoJSON de su barrio."""
    if lon is None or lat is None or not geometry:
        return None
    shapes = polygons(geometry)
    point = np.array([[lon, lat]], float)
    if any(inside(point, polygon)[0] for polygon in shapes):
        return PUBLICADA
    distance = distance_to_polygons_m(lon, lat, shapes)
    if distance <= BORDE_M:
        return PUBLICADA
    return APROXIMADA if distance <= MAX_M else None
