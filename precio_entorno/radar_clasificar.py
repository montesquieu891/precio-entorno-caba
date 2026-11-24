"""Clasificación editorial del radar de tendencias barriales.

Reglas deterministas y auditables, sin servicios pagos. Leen el titular, la bajada y, cuando el
medio lo sirve en acceso libre, el texto de la nota. El texto se usa solo en memoria: no se guarda.

Qué produce para cada nota:
- barrios oficiales con mención principal (cuentan en el indicador) e incidentales (no cuentan);
- menciones ambiguas o de otra ciudad, que quedan sin asignar;
- un tema, un resumen breve con frases propias y, si la nota reporta un hecho fechado, su fecha;
- aperturas de locales: reportadas o anunciadas, con local, dirección y fecha verificable si las hay.
"""

import re
import unicodedata
from datetime import date, timedelta

from .importing import BARRIOS

VERSION = 1
OFICIALES = sorted(set(BARRIOS.values()))


def plano(texto):
    """Quita tildes y diéresis, conserva mayúsculas. «Núñez» pasa a «Nunez»."""
    descompuesto = unicodedata.normalize('NFKD', str(texto or ''))
    return ''.join(c for c in descompuesto if not unicodedata.combining(c))


def _patron(nombre):
    return r'\s+'.join(re.escape(p) for p in plano(nombre).split())


# ------------------------------------------------------------------ barrios

# Variantes de escritura de un mismo barrio oficial.
VARIANTES = {
    'Montserrat': ['Monserrat'],
    'La Paternal': ['Paternal'],
    'Nueva Pompeya': ['Pompeya'],
    'Villa General Mitre': [r'Villa\s+Gral\.?\s+Mitre'],
}
# Alias con un único barrio oficial. Coinciden con las subzonas que ya usa el catálogo de avisos.
ALIAS = {
    'Chacagiales': ('Chacarita', 'Colegiales'),
    'Palermo Soho': ('Palermo',), 'Palermo Hollywood': ('Palermo',), 'Palermo Chico': ('Palermo',),
    'Palermo Viejo': ('Palermo',), 'Las Cañitas': ('Palermo',), 'Villa Freud': ('Palermo',),
    'Belgrano R': ('Belgrano',), 'Belgrano C': ('Belgrano',), 'Barrio Chino': ('Belgrano',),
    'Barrio Norte': ('Recoleta',), 'Abasto': ('Balvanera',), 'Microcentro': ('San Nicolás',),
    'Tribunales': ('San Nicolás',), 'Caballito Norte': ('Caballito',), 'Caballito Sur': ('Caballito',),
    'Distrito Tecnológico': ('Parque Patricios',), 'Distrito del Diseño': ('Barracas',),
}
# Zonas que cruzan varios barrios oficiales: se informan, pero no se asignan.
AMBIGUAS = {
    'Parque Centenario': 'la zona cruza Caballito, Almagro y Villa Crespo',
    'Distrito Audiovisual': 'el distrito abarca varios barrios',
    'Distrito de las Artes': 'el distrito abarca La Boca, San Telmo y Barracas',
    'Distrito Arcos': 'la zona cruza Palermo y Colegiales',
}
# Palabras que pueden preceder a un barrio sin volverlo parte de un nombre propio.
CONECTORES = {
    'En', 'De', 'Del', 'Y', 'E', 'O', 'A', 'La', 'El', 'Los', 'Las', 'Barrio', 'Barrios', 'Zona', 'Desde',
    'Hasta', 'Entre', 'Como', 'Sobre', 'Hacia', 'Para', 'Por', 'Con', 'Sin', 'Comuna', 'CABA', 'Plaza',
    'Estacion', 'Mientras', 'Tambien', 'Segun', 'Ademas', 'Pero', 'Hoy', 'Ahora', 'Aunque',
}
for _nombre in OFICIALES + list(ALIAS) + list(AMBIGUAS):
    CONECTORES.update(w for w in plano(_nombre).split() if w[:1].isupper())

CALLE_ANTES = re.compile(
    r'(?:\b(?:Av|Avda|Avenida|avenida|calle|Calle|pasaje|Pasaje|Boulevard|Bv|Gral|General|Ruta|ruta|Diagonal|'
    r'Autopista|autopista|Santiago de|Manuel|Cornelio|Puente|puente)\.?\s+)$')
DESPUES_EXCLUYE = re.compile(r'\s+(?:Cargas|Juniors|Nacional|de la Nacion|de los Arroyos|Argentina|provincial)\b')

CABA = re.compile(r'\b(?:CABA|Ciudad de Buenos Aires|Capital Federal|Ciudad Autonoma|porten[oa]s?)\b')
OTROS_LUGARES = re.compile(
    r'\b(?:Montevideo|Uruguay|Punta del Este|Cordoba|Rosario|Mendoza|Mar del Plata|Bariloche|Nordelta|Pilar|'
    r'Tigre|Lujan|San Isidro|Vicente Lopez|La Plata|Canning|Escobar|[Cc]onurbano|[Zz]ona [Nn]orte|[Zz]ona [Ss]ur|'
    r'[Zz]ona [Oo]este|Gran Buenos Aires|GBA|Miami|Madrid|Espana|Paraguay|Chile|Brasil|Nueva York|Pocitos|'
    r'Punta Carretas|Neuquen|Salta|Tucuman|Costa Atlantica|Pinamar|Carilo|Portugal|Italia|Francia|Europa|'
    r'Estados Unidos|Finlandia|Mexico|Peru|Colombia|Londres|Paris|Lisboa)\b')


def _compilar():
    patrones = []
    for nombre in OFICIALES:
        formas = [_patron(nombre)] + VARIANTES.get(nombre, [])
        if nombre == 'La Boca':
            formas = [r'[Ll]a\s+Boca(?!\s+Juniors)']
        patrones += [(forma, (nombre,), None) for forma in formas]
    for alias, barrios in ALIAS.items():
        patrones.append((_patron(alias), barrios, None))
    for alias, motivo in AMBIGUAS.items():
        patrones.append((_patron(alias), (), motivo))
    # «Once» también es un número: solo cuenta después de «en», «de» o «y».
    patrones.append((r'(?:(?<=\ben )|(?<=\bde )|(?<=\by ))Once\b(?!\s+(?:mil|millones|anos|meses|dias|de)\b)',
                     ('Balvanera',), None))
    patrones.sort(key=lambda p: -len(p[0]))
    return [(re.compile(r'(?<![\w])' + forma + r'(?![\w])'), barrios, motivo) for forma, barrios, motivo in patrones]


PATRONES = _compilar()


def _descartada(texto, inicio, fin):
    antes, despues = texto[max(0, inicio - 40):inicio], texto[fin:fin + 30]
    if CALLE_ANTES.search(antes) or DESPUES_EXCLUYE.match(despues):
        return 'calle, institución o nombre propio'
    previa = re.search(r'([A-Za-z]+)\s+$', antes)
    if previa and previa.group(1)[0].isupper() and previa.group(1) not in CONECTORES:
        return 'parte de un nombre propio'
    if previa and previa.group(1) in ('Villa', 'Parque', 'Nueva', 'Barrio'):
        return 'otro lugar con nombre parecido'  # «Villa Belgrano» (Córdoba) no es Belgrano.
    if previa and previa.group(1) == 'la' and texto[inicio:fin].startswith('Constitucion'):
        return 'la Constitución, no el barrio'
    return None


def menciones(texto):
    """Lista de (posición, texto, barrios, motivo_sin_asignar). Sin motivo, la mención es de un barrio."""
    texto = plano(texto)
    usado = bytearray(len(texto))
    out = []
    for regex, barrios, motivo in PATRONES:
        out += [(m.start(), m.group(0), barrios, motivo) for m in _coincidencias_libres(regex, texto, usado)]
    return sorted(out)


def _coincidencias_libres(regex, texto, usado):
    """Coincidencias que no se superponen con otra ya tomada ni se descartan; marca su tramo como usado."""
    out = []
    for m in regex.finditer(texto):
        if any(usado[m.start():m.end()]):
            continue
        usado[m.start():m.end()] = b'\x01' * (m.end() - m.start())
        descarte = _descartada(texto, m.start(), m.end())
        if descarte:
            continue  # No es una mención de barrio.
        out.append(m)
    return out


def alcance(titular, bajada, texto):
    """'caba' u 'otro': una nota sobre otra ciudad no asigna barrios aunque compare con alguno."""
    cabeza = plano(f'{titular} {bajada}')
    en_cabeza = [m for m in menciones(cabeza) if m[2]]
    if OTROS_LUGARES.search(cabeza) and not CABA.search(cabeza) and not en_cabeza:
        return 'otro'
    cuerpo = plano(texto)
    otros, propios = len(OTROS_LUGARES.findall(cuerpo)), len(CABA.findall(cuerpo))
    if not en_cabeza and not CABA.search(cabeza) and otros >= 3 and otros > 2 * (propios + len(menciones(cuerpo))):
        return 'otro'
    return 'caba'


# Un barrio nombrado como referencia («cerca de Palermo», «más barato que en Belgrano») es incidental.
COMPARACION = re.compile(
    r'(?:\bcercan\w*\s+(?:con|a|de)|\bcerca\s+de|\bvecin\w*\s+(?:de|a)|\blindante\s+con|\blimita\s+con|\bjunto\s+a|'
    r'\bque\s+en|\bque|\bcomo\s+en|\bcomo|\ba\s+diferencia\s+de|\bdetras\s+de|\befecto|\bencarecimiento\s+de|'
    r'\balrededor\s+de|\bmas\s+alla\s+de|\bigual\s+que|\bcomparad\w+\s+con|\bcomparacion\s+con|\brespecto\s+de|\ben\s+lugar\s+de|'
    r'\bfrente\s+a|\botro|\botra|\bderrame["”]?\s+de|\bexpansion\s+de|\bdesborde\s+de|\bal\s+lado\s+de)'
    r'\s+(?:(?:el|la|los|las)\s+)?(?:barrios?\s+(?:de\s+)?)?$')
CONTINUA_LISTA = re.compile(r'^(?:\s*,\s*|\s+y\s+|\s+o\s+|\s*,\s+y\s+)$')
SUBTITULO = re.compile(r'^\s*:')


def _menciones_de_oracion(oracion):
    """Menciones con marca de comparación y de subtítulo («Saavedra: calidad de vida...»)."""
    lista = menciones(oracion)
    # Subtítulo: la oración empieza con uno o más barrios unidos por «,» o «y», seguidos de «:».
    cadena = 0
    if lista and not oracion[:lista[0][0]].strip():
        cadena = 1
        while cadena < len(lista) and CONTINUA_LISTA.match(
                oracion[lista[cadena - 1][0] + len(lista[cadena - 1][1]):lista[cadena][0]]):
            cadena += 1
        ultimo = lista[cadena - 1]
        if not SUBTITULO.match(oracion[ultimo[0] + len(ultimo[1]):]):
            cadena = 0
    out, anterior = [], None
    for i, (inicio, encontrado, barrios, motivo) in enumerate(lista):
        compara = bool(COMPARACION.search(oracion[max(0, inicio - 45):inicio]))
        if anterior and anterior[1] and CONTINUA_LISTA.match(oracion[anterior[0]:inicio]):
            compara = True
        out.append((encontrado, barrios, motivo, compara, i < cadena))
        anterior = (inicio + len(encontrado), compara)
    return out


def _contar_oracion(estado, items, es_cabeza, zona):
    """Anota las menciones de una oración: ambiguas aparte y, si no, barrios en foco o contados."""
    subtitulos = {b for _, bs, m, _, s in items if s and not m for b in bs}
    if subtitulos and not es_cabeza:
        estado['seccion'] = subtitulos
    for encontrado, barrios, motivo, compara, subtitulo in items:
        if motivo or zona == 'otro':
            motivo = motivo or 'la nota trata sobre otra ciudad o región'
            if (encontrado, motivo) not in estado['ambiguas']:
                estado['ambiguas'].append((encontrado, motivo))
            continue
        _contar_barrios(estado, barrios, es_cabeza or subtitulo, compara)


def _contar_barrios(estado, barrios, destacado, compara):
    """Un barrio destacado queda en foco; si no, suma una mención propia salvo que sea comparación o de otra sección."""
    for b in barrios:
        estado['nombrados'].add(b)
        if destacado:
            estado['foco'].add(b)
        elif not compara and (estado['seccion'] is None or b in estado['seccion']):
            estado['cuenta'][b] = estado['cuenta'].get(b, 0) + 1


def barrios_de(titular, bajada, texto):
    """Barrios principales, incidentales y menciones ambiguas.

    Principal: aparece en el titular, la bajada o un subtítulo, o se lo nombra al menos dos veces sin
    usarlo como comparación ni dentro de la sección de otro barrio. El resto es incidental y no suma.
    """
    zona = alcance(titular, bajada, texto)
    estado = {'cuenta': {}, 'foco': set(), 'nombrados': set(), 'ambiguas': [], 'seccion': None}
    partes = ((titular, True), (bajada, True), (texto, False))
    for oracion, es_cabeza in [(oracion, es_cabeza) for parte, es_cabeza in partes for oracion in oraciones(parte)]:
        _contar_oracion(estado, _menciones_de_oracion(oracion), es_cabeza, zona)
    cuenta, foco, nombrados, ambiguas = estado['cuenta'], estado['foco'], estado['nombrados'], estado['ambiguas']
    # Si el titular ya nombra un barrio, otro barrio necesita más menciones propias para ser foco.
    minimo = 3 if any(m[2] and not m[3] for m in menciones(titular)) else 2
    principales = sorted(b for b in nombrados if b in foco or cuenta.get(b, 0) >= minimo)
    incidentales = sorted(b for b in nombrados if b not in principales)
    return {'alcance': zona, 'barrios': principales, 'incidentales': incidentales,
            'ambiguas': [{'texto': t, 'motivo': m} for t, m in ambiguas]}


# ------------------------------------------------------------------ tema

TEMAS = [
    ('aperturas', 'aperturas de locales y comercios',
     r'\babri(?:o|eron|ra|ran)\b|\binaugur|\babre sus puertas|\bapertura|\bnuevo local|\bdesembarc'),
    ('transformacion', 'la transformación y el perfil de los barrios',
     r'barrio(?:s)? revelacion|\bcool\b|\btendencia|\bpolo gastronomico|reconvirt|reconversion|\btransformacion|'
     r'\bidentidad|gentrific|\bcorredor|\bde moda'),
    ('precios', 'precios publicados y valores del metro cuadrado',
     r'\bprecio|\bm2\b|metro cuadrado|\bcuesta|\bcuestan|\bvalor(?:es)?\b|\bus\$|\bdolares|\bcotiza|\brentab'),
    ('alquileres', 'alquileres', r'\balquil|\binquilin|\blocador|\bcontrato'),
    ('credito', 'crédito hipotecario', r'\bhipotecari|\bcredito|\bprestamo|\bcuota'),
    ('desarrollos', 'obras y desarrollos inmobiliarios',
     r'\bemprendimiento|\bdesarrollador|\bconstruc|\btorre|\ben pozo|\bpermisos de obra|metros cuadrados proyectados|\bobra nueva'),
    ('infraestructura', 'infraestructura y espacio público',
     r'\bsubte|\btren\b|\bviaducto|\bplaza|\bparque lineal|\bobra publica|\bmetrobus|\bespacio publico'),
    ('normativa', 'normas e impuestos',
     r'codigo urbanistico|\bley\b|\bdecreto|\babl\b|\bimpuesto|\bnormativa|\blegislatura|\bsucesion|\bdonacion|\bescritura'),
    ('vivienda', 'diseño y vida en la vivienda',
     r'\bamenities|\bdecora|\barquitect|\bdiseno|\bremodel|\breforma|\bcocina|\bjardin'),
]
TEMA_NOMBRE = {clave: nombre for clave, nombre, _ in TEMAS} | {'otros': 'otros temas inmobiliarios'}
_TEMAS = [(clave, re.compile(regex)) for clave, _, regex in TEMAS]


def tema_de(titular, bajada, texto, hay_apertura=False):
    if hay_apertura:
        return 'aperturas'
    partes = [(plano(titular).lower(), 4), (plano(bajada).lower(), 2), (plano(texto).lower(), 1)]
    puntos = {clave: sum(min(len(r.findall(t)), 5) * peso for t, peso in partes) for clave, r in _TEMAS
              if clave != 'aperturas'}
    mejor = max(puntos, key=lambda k: puntos[k]) if puntos else None
    return mejor if mejor and puntos[mejor] > 0 else 'otros'


# ------------------------------------------------------------------ fechas y aperturas

MESES = {m: i for i, m in enumerate(
    'enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split(), 1)}
MESES['setiembre'] = 9
DIAS = {d: i for i, d in enumerate('lunes martes miercoles jueves viernes sabado domingo'.split())}
FECHA = re.compile(r'\b(\d{1,2})(?:º|°|ro)?\s+de\s+(' + '|'.join(MESES) + r')(?:\s+(?:de|del)\s+(\d{4}))?\b')
DIA_RELATIVO = re.compile(r'\b(?:el|este|ese|el pasado|el ultimo|este ultimo|el proximo)\s+('
                          + '|'.join(DIAS) + r')\b(?!\s+\d)(?:\s+(pasado|ultimo|proximo|que viene))?')
AYER_HOY = re.compile(r'\b(anteayer|ayer|hoy)\b')

PASADO = re.compile(r'\b(?:abrio|abrieron|reabrio|reabrieron|inauguro|inauguraron|desembarco|desembarcaron|'
                    r'estreno|estrenaron|abrio sus puertas)\b')
FUTURO = re.compile(r'\b(?:abrira|abriran|reabrira|inaugurara|inauguraran|desembarcara|desembarcaran|'
                    r'va a abrir|van a abrir|planea abrir|planean abrir|preve abrir|prevén abrir|preven abrir|'
                    r'proxima apertura|abrir(?:a|an) sus puertas|se inaugurara)\b')
PRESENTE = re.compile(r'\b(?:abre|abren|inaugura|inauguran|reabre|desembarca)\b')
# «mercado», «club» y «local» como adjetivo son demasiado comunes en notas inmobiliarias.
LOCAL = re.compile(r'\b(?:(?:un|el|nuevo|su|primer|segundo|otro) local|locales gastronomicos|restaurante|restaurant|'
                   r'resto|bar|bares|cafe|cafeteria|panaderia|heladeria|pasteleria|tienda|sucursal|vermuteria|'
                   r'cerveceria|parrilla|bodegon|pizzeria|libreria|mercado gastronomico|supermercado|hotel|gimnasio|'
                   r'centro cultural|food hall|showroom|bistro|almacen|rotiseria|cantina|vinoteca)\b')
NOMBRE_ENTRE_COMILLAS = re.compile(r'[«“"]([^»”"]{2,60})[»”"]')
NOMBRE_TRAS_LOCAL = re.compile(
    r'\b(?:local|restaurante|restaurant|resto|bar|cafe|cafeteria|panaderia|heladeria|pasteleria|tienda|sucursal|'
    r'vermuteria|cerveceria|parrilla|bodegon|pizzeria|libreria|hotel|gimnasio|centro cultural|'
    r'food hall|showroom|bistro|almacen|rotiseria|cantina|vinoteca)\s+(?:de\s+)?'
    r'([A-Z][\w\'&]*(?:\s+(?:de|del|la|las|los|y|[A-Z0-9][\w\'&]*)){0,4})')
NOMBRE_ANTES_VERBO = re.compile(r'([A-Z][\w\'&]+(?:\s+(?:de|del|[A-Z][\w\'&]+)){0,3})\s+(?:abrio|inauguro|abre|'
                                r'inaugura|abrira|inaugurara|desembarco|desembarca|desembarcara|reabrio|reabre)\b')
NO_NOMBRE = {'El', 'La', 'Los', 'Las', 'Este', 'Esta', 'Ese', 'Esa', 'Ahora', 'Hoy', 'Ayer', 'Tambien', 'Ademas',
             'Se', 'Que', 'Quien', 'Donde', 'Alli', 'En', 'Un', 'Una', 'Ya', 'Recien', 'CABA', 'Ciudad'}
DIRECCION = re.compile(
    r'\b(?:en|sobre|ubicad[oa] en|en la esquina de|frente a)\s+((?:(?:Av|Avda|Avenida)\.?\s+)?[A-Z][A-Za-z\.]+'
    r'(?:\s+(?:de|del|la|[A-Z][A-Za-z\.]+)){0,3})\s+(?:al\s+)?(\d{2,5})\b'
    r'(?!\s*(?:m2|metros|%|personas|cubiertos|dolares|pesos|mil|millones|ambientes|anos|unidades|departamentos))')
ESQUINA = re.compile(r'\b(?:en la esquina de|esquina)\s+((?:Av\.?\s+)?[A-Z][A-Za-z\.]+(?:\s+[A-Z][A-Za-z\.]+){0,2})'
                     r'\s+y\s+((?:Av\.?\s+)?[A-Z][A-Za-z\.]+(?:\s+[A-Z][A-Za-z\.]+){0,2})')
NO_CALLE = {'El', 'La', 'Los', 'Las', 'En', 'Hay', 'Desde', 'Hasta', 'Con', 'Entre', 'Unos', 'Mas', 'Cerca', 'Ley',
            'Decreto', 'Comuna', 'Linea', 'Puesto', 'Top', 'Hace', 'US', 'USD', 'CABA', 'Time', 'Argentina',
            'Buenos', 'Capital', 'Ciudad', 'Total', 'Solo', 'Apenas'} | {m.capitalize() for m in MESES}


ABREVIATURA = re.compile(r'(?:\b(?:Av|Avda|Gral|Dr|Dra|Sr|Sra|Pte|Sto|Sta|Ing|Lic|Prof|Arq|Cnel|Tte|N|Nro|aprox)'
                         r'|\b[A-Z])\.$')


def oraciones(texto):
    texto = re.sub(r'\s+', ' ', plano(texto)).strip()
    # El texto de JSON-LD a veces pega los párrafos: «...en marcha.La selección...».
    partes = [p.strip() for p in re.split(r'(?<=[.!?])\s+|(?<=[a-z0-9%)][.!?])(?=[A-Z¿¡"“«])', texto) if p.strip()]
    out = []
    for parte in partes:  # «Av. Corrientes» no termina una oración.
        if out and ABREVIATURA.search(out[-1]):
            out[-1] = f'{out[-1]} {parte}'
        else:
            out.append(parte)
    return out


def _fecha_explicita(oracion, publicado, futuro):
    m = FECHA.search(oracion.lower())
    if not m:
        return None
    dia, mes = int(m.group(1)), MESES[m.group(2)]
    anio = int(m.group(3)) if m.group(3) else publicado.year
    try:
        fecha = date(anio, mes, dia)
    except ValueError:
        return None
    if not m.group(3):
        if not futuro and fecha > publicado + timedelta(days=1):
            fecha = fecha.replace(year=anio - 1)
        elif futuro and fecha < publicado - timedelta(days=1):
            fecha = fecha.replace(year=anio + 1)
    return fecha


def fecha_de(oracion, publicado, futuro=False):
    """Fecha del hecho en la oración: explícita («5 de noviembre») o relativa a la publicación."""
    explicita = _fecha_explicita(oracion, publicado, futuro)
    if explicita:
        return explicita
    baja = oracion.lower()
    relativo = AYER_HOY.search(baja)
    if relativo:
        return publicado - timedelta(days={'anteayer': 2, 'ayer': 1, 'hoy': 0}[relativo.group(1)])
    m = DIA_RELATIVO.search(baja)
    if m:
        dia = DIAS[m.group(1)]
        if futuro or m.group(2) in ('proximo', 'que viene') or 'el proximo' in m.group(0):
            return publicado + timedelta(days=(dia - publicado.weekday()) % 7 or 7)
        return publicado - timedelta(days=(publicado.weekday() - dia) % 7)
    return None


def _limpiar_nombre(nombre, entre_comillas=False):
    palabras = nombre.split()
    while palabras and palabras[-1].lower() in ('de', 'del', 'la', 'las', 'los', 'y'):
        palabras.pop()
    nombre = ' '.join(palabras).strip(' .,;:')
    if not nombre or nombre in NO_NOMBRE or (not entre_comillas and nombre.split()[0] in NO_NOMBRE) or any(
            nombre == b or plano(nombre) == plano(b) for b in OFICIALES):
        return None
    return nombre


def _nombre_local(oracion):
    regexes = (NOMBRE_ENTRE_COMILLAS, NOMBRE_TRAS_LOCAL, NOMBRE_ANTES_VERBO)
    for regex, m in ((regex, m) for regex in regexes for m in regex.finditer(oracion)):
        nombre = _limpiar_nombre(m.group(1), regex is NOMBRE_ENTRE_COMILLAS)
        if nombre:
            return nombre
    return None


def _direccion(oracion):
    esquina = ESQUINA.search(oracion)
    if esquina:
        return f'{esquina.group(1)} y {esquina.group(2)}'
    for m in DIRECCION.finditer(oracion):
        calle = m.group(1)
        if calle.split()[0].rstrip('.') in NO_CALLE or menciones(calle):
            continue
        return f'{calle} {m.group(2)}'
    return None


def aperturas(titular, bajada, texto, publicado):
    """Aperturas de locales en la nota. Cada una: tipo, local, dirección, barrio y fecha del hecho."""
    todas = oraciones(titular) + oraciones(bajada) + oraciones(texto)
    out = []
    for i, oracion in enumerate(todas):
        baja = oracion.lower()
        if not LOCAL.search(baja) and not NOMBRE_ENTRE_COMILLAS.search(oracion):
            continue
        futuro, pasado, presente = FUTURO.search(baja), PASADO.search(baja), PRESENTE.search(baja)
        if not (futuro or pasado or presente):
            continue
        fecha = fecha_de(oracion, publicado, futuro=bool(futuro))
        if futuro:
            tipo = 'anuncio'
        elif pasado:
            tipo = 'reportada'
        else:  # Presente: lo decide la fecha, si la hay.
            tipo = 'anuncio' if fecha and fecha > publicado else 'reportada'
        verificable = fecha is not None and (tipo == 'anuncio' or fecha <= publicado)
        cercanas = [b for _, _, bs, motivo in menciones(oracion) if not motivo for b in bs]
        if not cercanas and i:
            cercanas = [b for _, _, bs, motivo in menciones(todas[i - 1]) if not motivo for b in bs]
        hecho = {'tipo': tipo, 'local': _nombre_local(oracion), 'direccion': _direccion(oracion),
                 'barrio': cercanas[0] if len(set(cercanas)) == 1 else None,
                 'fecha_hecho': fecha.isoformat() if verificable else None}
        clave = (hecho['tipo'], clave_texto(hecho['local']), clave_texto(hecho['direccion']))
        if not any((h['tipo'], clave_texto(h['local']), clave_texto(h['direccion'])) == clave for h in out):
            out.append(hecho)
    # Una mención genérica («abrió una heladería») sobra si la nota identifica una apertura del mismo tipo.
    identificadas = {h['tipo'] for h in out if h['local'] or h['direccion']}
    return [h for h in out if h['local'] or h['direccion'] or h['tipo'] not in identificadas]


def clave_texto(valor):
    return re.sub(r'[^a-z0-9]+', ' ', plano(valor or '').lower()).strip()


HECHO_VERBO = re.compile(r'\b(?:se aprobo|aprobo|se publico|publico|se lanzo|lanzo|se vendio|vendio|vendieron|'
                         r'anuncio|presento|se inauguro|inauguro|abrio|comenzo|se habilito|habilito|se licito|'
                         r'licito|subasto|se subasto|remato|se remato|ubico|eligio|distinguio)\b')


def fecha_hecho(titular, bajada, texto, publicado, hechos):
    """Fecha del hecho principal: la de una apertura o la de un verbo de hecho en el arranque de la nota."""
    for h in hechos:
        if h['fecha_hecho']:
            return h['fecha_hecho']
    for oracion in (oraciones(titular) + oraciones(bajada) + oraciones(texto)[:4]):
        if HECHO_VERBO.search(oracion.lower()):
            fecha = fecha_de(oracion, publicado)
            if fecha and fecha <= publicado:
                return fecha.isoformat()
    return None


# ------------------------------------------------------------------ resumen y clasificación

def enumerar(items):
    items = list(items)
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} y {items[-1]}"


def _fecha_corta(iso):
    return date.fromisoformat(iso).strftime('%d/%m/%Y') if iso else None


def resumen(medio, tema, zona, barrios, incidentales, hechos, acceso):
    if zona == 'otro':
        lugar = ' fuera de la Ciudad de Buenos Aires'
    elif barrios:
        lugar = f' con foco en {enumerar(barrios)}'
    else:
        lugar = ' sin un barrio porteño puntual'
    partes = [f'Nota de {medio} sobre {TEMA_NOMBRE[tema]}{lugar}.']
    if incidentales and zona != 'otro':
        partes.append(f'Nombra al pasar {enumerar(incidentales)}.')
    for h in hechos[:2]:
        local = f'«{h["local"]}»' if h['local'] else 'un local sin nombre identificado'
        donde = f' en {h["direccion"]}' if h['direccion'] else ''
        cuando = f', con fecha {_fecha_corta(h["fecha_hecho"])}' if h['fecha_hecho'] else ', sin fecha verificable'
        verbo = 'Informa la apertura de' if h['tipo'] == 'reportada' else 'Anuncia la futura apertura de'
        partes.append(f'{verbo} {local}{donde}{cuando}.')
    if acceso == 'restringido':
        partes.append('Se clasificó solo con el titular y la bajada porque el texto es de acceso restringido.')
    elif acceso == 'sin_detalle':
        partes.append('Se clasificó solo con el titular: la página de la nota no respondió.')
    return ' '.join(partes)


def clasificar(medio, titular, bajada, texto, publicado, acceso='libre'):
    """Clasifica una nota. `texto` se usa en memoria; el resultado no lo incluye."""
    zona = barrios_de(titular, bajada, texto)
    hechos = aperturas(titular, bajada, texto, publicado) if zona['alcance'] == 'caba' else []
    tema = tema_de(titular, bajada, texto, hay_apertura=any(h['local'] or h['direccion'] for h in hechos))
    return {
        **zona, 'tema': tema, 'tema_nombre': TEMA_NOMBRE[tema], 'aperturas': hechos,
        'fecha_hecho': fecha_hecho(titular, bajada, texto, publicado, hechos),
        'resumen': resumen(medio, tema, zona['alcance'], zona['barrios'], zona['incidentales'], hechos, acceso),
        'clasificacion_version': VERSION,
    }
