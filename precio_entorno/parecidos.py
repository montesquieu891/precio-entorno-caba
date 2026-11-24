"""Barrios parecidos a uno elegido, según su entorno, para sugerir barrios que la persona no tenía en cuenta.

La comparación usa solo las capas del entorno de `resumen.json`, nunca los precios ni los delitos:
estaciones de subte, espacio verde, escuelas del nivel elegido, salud pública, ruido de día, riesgo
hídrico y, si está, gastronomía de OpenStreetMap. Las cantidades se pasan a densidad por superficie del
barrio y cada capa se lleva a una escala de 0 a 1 entre el mínimo y el máximo de CABA (logarítmica para
las densidades), así ninguna pesa más por su unidad. Lo que la persona marcó en «Me importa» cuenta doble.

No se devuelve ningún puntaje: cada barrio sugerido explica en qué se parece y en qué difiere. El precio
se muestra aparte, como información, con la mediana de los avisos que encajan con la búsqueda.
"""

import math

# clave: (etiqueta, palabra cuando el sugerido tiene más, cuando tiene menos)
CAPAS = {
    'subte': ('Subte', 'más estaciones de subte', 'menos estaciones de subte'),
    'verdes': ('Espacio verde', 'más espacio verde', 'menos espacio verde'),
    'escuelas': ('Escuelas', 'más escuelas', 'menos escuelas'),
    'salud': ('Salud pública', 'más centros de salud', 'menos centros de salud'),
    'ruido': ('Ruido de día', 'más ruido', 'menos ruido'),
    'riesgo': ('Riesgo hídrico', 'más superficie en riesgo hídrico', 'menos superficie en riesgo hídrico'),
    'gastronomia': ('Gastronomía', 'más cafés, bares y restaurantes', 'menos cafés, bares y restaurantes'),
    'recreacion': ('Recreación', 'más cines, teatros y museos', 'menos cines, teatros y museos'),
}
PESO_ELEGIDO = 2
CERCA = 0.15       # Diferencia en la escala 0–1 que se considera «parecido».
LEJOS = 0.35       # Diferencia en la escala 0–1 que se informa como diferencia.
SUGERIDOS = 3


def numero(valor, decimales=0):
    texto = f'{valor:,.{decimales}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return texto.removesuffix(',0') if decimales else texto


def valores(entorno, nivel='primario'):
    """Valor por capa de un barrio; None donde no hay dato."""
    if not entorno or not entorno.get('area_ha'):
        return {}
    km2 = entorno['area_ha'] / 100
    escuelas = entorno.get('escuelas', {}).get(nivel, {})
    gastronomia = entorno.get('gastronomia')
    recreacion = entorno.get('recreacion')
    return {
        'subte': entorno['subte_estaciones'] / km2,
        'verdes': entorno['verdes_ha'] / entorno['area_ha'] * 100,
        'escuelas': sum(escuelas.values()) / km2,
        'salud': (entorno['cesac'] + entorno['hospitales']) / km2,
        'ruido': entorno['ruido']['diurno']['alto'],
        'riesgo': entorno['riesgo_hidrico'],
        'gastronomia': (sum(gastronomia[k] for k in ('restaurantes', 'cafes', 'bares')) / entorno['area_ha'] * 100
                        if gastronomia else None),
        'recreacion': sum(recreacion.values()) / entorno['area_ha'] * 100 if recreacion else None,
    }


def unidad(clave, nivel):
    return {'subte': 'estaciones por km²', 'verdes': 'ha cada 100 ha', 'escuelas': f'escuelas de nivel {nivel} por km²',
            'salud': 'centros de salud públicos por km²', 'ruido': 'de las celdas con 70 dBA o más',
            'riesgo': 'de la superficie', 'gastronomia': 'cafés, bares y restaurantes cada 100 ha',
            'recreacion': 'cines, teatros, museos y centros culturales cada 100 ha'}[clave]


def mostrar(clave, valor):
    """Valor de `valores()` como texto: porcentajes enteros, densidades con un decimal o enteras."""
    if clave in ('ruido', 'riesgo'):
        return f'{round(valor * 100)} %'
    if clave == 'gastronomia':
        return numero(valor)
    return numero(valor, 1)


def parecido_de_verdad(clave, a, b):
    """Además de estar cerca en percentil, los valores tienen que ser comparables a simple vista."""
    if clave in ('ruido', 'riesgo'):
        return abs(a - b) <= 0.10
    if a == b == 0:
        return True
    return min(a, b) / max(a, b) >= 0.67


def frase(clave, inicio, propio, ajeno, origen, nivel, nexo):
    if clave == 'subte' and propio == ajeno == 0:
        return f'{inicio}: ninguno de los dos tiene estaciones'
    return f'{inicio}: {mostrar(clave, ajeno)} {nexo} {mostrar(clave, propio)} en {origen} ({unidad(clave, nivel)})'


def escalas(tabla):
    """Cada capa llevada a 0–1 entre el mínimo y el máximo de los barrios con dato.

    Las densidades usan escala logarítmica, porque unos pocos barrios céntricos concentran valores muy
    altos y, en escala lineal, aplastarían las diferencias entre los demás.
    """
    salida = {nombre: {} for nombre in tabla}
    for clave in CAPAS:
        transformar = (lambda v: v) if clave in ('ruido', 'riesgo') else math.log1p
        con_dato = {n: transformar(v[clave]) for n, v in tabla.items() if v.get(clave) is not None}
        if not con_dato:
            continue
        poner_escala(salida, clave, con_dato)
    return salida


def poner_escala(salida, clave, con_dato):
    """Lleva los valores de una capa a 0–1 entre el mínimo y el máximo; 0 si todos son iguales."""
    bajo, alto = min(con_dato.values()), max(con_dato.values())
    for nombre, valor in con_dato.items():
        salida[nombre][clave] = (valor - bajo) / (alto - bajo) if alto > bajo else 0.0


def parecidos(barrio, filas, prefs=(), nivel='primario', cantidad=SUGERIDOS):
    """Barrios más parecidos a `barrio` por su entorno.

    `filas` son las de /api/barrios: barrio, entorno, coincidencias, avisos y mediana. Primero se sugieren
    los barrios con avisos que encajan con la búsqueda. Si no alcanzan, se completan con los demás.
    """
    por_nombre = {f['barrio']: f for f in filas}
    origen = por_nombre.get(barrio)
    if not origen or not origen.get('entorno'):
        return []
    tabla = {f['barrio']: valores(f['entorno'], nivel) for f in filas if f.get('entorno')}
    rango = escalas(tabla)
    pesos = {clave: PESO_ELEGIDO if clave in prefs else 1 for clave in CAPAS}
    candidatos = []
    for nombre, mios in rango.items():
        if nombre == barrio:
            continue
        comunes = [c for c in CAPAS if c in mios and c in rango[barrio]]
        if not comunes:
            continue
        diferencias = {c: mios[c] - rango[barrio][c] for c in comunes}
        distancia = sum(pesos[c] * abs(d) for c, d in diferencias.items()) / sum(pesos[c] for c in comunes)
        candidatos.append((distancia, nombre, diferencias))
    candidatos.sort(key=lambda x: (x[0], x[1]))
    con_avisos = [c for c in candidatos if por_nombre[c[1]].get('coincidencias')]
    elegidos = (con_avisos + [c for c in candidatos if c not in con_avisos])[:cantidad]

    salida = []
    for _, nombre, diferencias in elegidos:
        fila = por_nombre[nombre]
        ajeno, propio = tabla[nombre], tabla[barrio]
        cerca = sorted((c for c, d in diferencias.items()
                        if abs(d) <= CERCA and parecido_de_verdad(c, ajeno[c], propio[c])),
                       key=lambda c: (-pesos[c], abs(diferencias[c])))[:3]
        lejos = sorted((c for c, d in diferencias.items() if abs(d) >= LEJOS),
                       key=lambda c: (-pesos[c], -abs(diferencias[c])))[:2]
        mediana = fila.get('mediana')
        base = origen.get('mediana')
        salida.append({
            'barrio': nombre,
            'coincidencias': fila.get('coincidencias', 0),
            'avisos': fila.get('avisos', 0),
            'mediana': mediana,
            'diferencia_mediana': mediana - base if mediana is not None and base is not None else None,
            'parecido_en': [{'capa': c, 'texto': frase(c, CAPAS[c][0], propio[c], ajeno[c], barrio, nivel, 'y')}
                            for c in cerca],
            'diferencias': [{'capa': c, 'texto': frase(c, (CAPAS[c][1] if diferencias[c] > 0 else CAPAS[c][2]).capitalize(),
                                                       propio[c], ajeno[c], barrio, nivel, 'contra')}
                            for c in lejos],
        })
    return salida
