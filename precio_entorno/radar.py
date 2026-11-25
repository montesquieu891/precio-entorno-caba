"""Radar de tendencias barriales: recolector semanal de notas inmobiliarias de medios de CABA.

Uso:
    python -m precio_entorno.radar                     # siete días calendario anteriores a hoy
    python -m precio_entorno.radar --hasta 2026-11-09  # período 2026-11-02 a 2026-11-08
    python -m precio_entorno.radar --validar URL       # clasifica una nota sin guardarla
    python -m precio_entorno.radar --resumen           # muestra el boletín guardado

Fuentes: feeds y sitemaps oficiales cuando cubren la sección, y la página pública de la sección si
robots.txt lo permite. Respeta robots.txt, espera entre pedidos, no usa proxies ni sigilo, y no lee
textos marcados como de acceso restringido. Guarda metadatos, barrios, tema, fecha del hecho y un
resumen propio. El texto de las notas se usa en memoria para clasificar y nunca se guarda.

Cada fuente se guarda en su propio archivo. Una corrida fallida no borra lo que ya había y queda
registrada como falla, no como una semana sin noticias.
"""

import argparse
import gzip
import html as html_lib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha1
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from . import radar_clasificar as clasif
from .robots import Robots, disallow_all

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo('America/Argentina/Buenos_Aires')
except Exception:  # noqa: BLE001 - sin base de zonas horarias: Argentina no usa horario de verano.
    TZ = timezone(timedelta(hours=-3), 'ART')

ROOT = Path(__file__).resolve().parents[1]
RADAR_DIR = ROOT / 'data/local/radar'
USER_AGENT = 'precio-entorno-caba/0.1 (proyecto academico; radar semanal de noticias)'
PAUSA_S = 4.0
REINTENTOS = 3
TOPE_PEDIDOS = 80  # Por fuente y corrida.
CHALLENGE = ('cf-chl', 'just a moment...', 'challenge-platform', 'captcha-delivery')
AVISO = ('La cobertura de prensa cuenta lo que publicaron los medios monitoreados. No mide demanda '
         'inmobiliaria, no es un censo de aperturas y no ordena los barrios por popularidad.')


@dataclass(frozen=True)
class Fuente:
    clave: str
    medio: str
    seccion: str
    prefijo: str
    listados: tuple
    metodo: str


FUENTES = {
    'clarin': Fuente(
        'clarin', 'Clarín', 'https://www.clarin.com/propiedades/', 'https://www.clarin.com/propiedades/',
        (('rss', 'https://www.clarin.com/rss/propiedades/'),
         ('sitemap_noticias', 'https://www.clarin.com/sitemaps/index_news.xml')),
        'Feed RSS oficial de Propiedades y sitemap oficial de noticias, filtrado por la sección.'),
    'lanacion': Fuente(
        'lanacion', 'LA NACION', 'https://www.lanacion.com.ar/propiedades/', 'https://www.lanacion.com.ar/propiedades/',
        (('rss_paginado', 'https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/propiedades/?outputType=xml'),),
        'Feed RSS oficial de la categoría Propiedades, paginado hasta cubrir el período.'),
    'tn': Fuente(
        'tn', 'TN', 'https://tn.com.ar/economia/propiedades/', 'https://tn.com.ar/economia/propiedades/',
        (('rss', 'https://tn.com.ar/arc/outboundfeeds/rss/category/economia/?outputType=xml'),
         ('seccion', 'https://tn.com.ar/economia/propiedades/')),
        'TN no publica un feed de Propiedades: se usa el feed oficial de Economía filtrado y la página '
        'pública de la sección, que robots.txt permite leer.'),
}


class Restringido(RuntimeError):
    """El medio no permite el acceso automatizado a esa dirección."""


class NoEncontrado(RuntimeError):
    pass


# ------------------------------------------------------------------ fechas

def ahora():
    return datetime.now(TZ).replace(microsecond=0)


def periodo(hasta=None):
    """Siete días calendario anteriores a `hasta` (excluido). Por defecto, hasta hoy en Buenos Aires."""
    fin = hasta or ahora().date()
    return fin - timedelta(days=7), fin - timedelta(days=1)


def fecha_iso(valor):
    """Fecha y hora de un feed o de JSON-LD, en Buenos Aires. Acepta RFC 822 e ISO 8601."""
    if not valor:
        return None
    valor = valor.strip()
    try:
        momento = parsedate_to_datetime(valor)
    except (TypeError, ValueError, IndexError):
        texto = re.sub(r'([+-]\d\d)(\d\d)$', r'\1:\2', valor.replace('Z', '+00:00'))
        try:
            momento = datetime.fromisoformat(texto)
        except ValueError:
            return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(TZ).replace(microsecond=0).isoformat()


def dia(iso):
    return date.fromisoformat(iso[:10]) if iso else None


# ------------------------------------------------------------------ cliente HTTP educado

def _urllib_fetch(url):
    pedido = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept-Encoding': 'gzip'})
    try:
        with urllib.request.urlopen(pedido, timeout=30) as respuesta:
            cuerpo, estado = respuesta.read(), respuesta.status
            if respuesta.headers.get('Content-Encoding') == 'gzip' or cuerpo[:2] == b'\x1f\x8b':
                cuerpo = gzip.decompress(cuerpo)
    except urllib.error.HTTPError as error:
        return error.code, ''
    return estado, cuerpo.decode('utf-8', 'replace')


class Cliente:
    """Respeta robots.txt, espera entre pedidos al mismo sitio y reintenta fallas transitorias."""

    def __init__(self, fetch=None, pausa_s=PAUSA_S, reintentos=REINTENTOS, sleep=time.sleep, tope=TOPE_PEDIDOS):
        self._fetch, self.pausa_s, self.reintentos, self._sleep, self.tope = (
            fetch or _urllib_fetch, pausa_s, reintentos, sleep, tope)
        self._ultimo, self._robots = {}, {}
        self.log = Counter()

    def _esperar(self, host):
        pasado = time.monotonic() - self._ultimo.get(host, -1e9)
        if pasado < self.pausa_s:
            self._sleep(self.pausa_s - pasado)
        self._ultimo[host] = time.monotonic()

    def _pedir(self, url):
        """Un pedido con reintentos ante errores de red, 429 y 5xx."""
        host = urlsplit(url).netloc
        ultimo = None
        for intento in range(1, self.reintentos + 1):
            if self.log['pedidos'] >= self.tope:
                raise RuntimeError(f'Se alcanzó el tope de {self.tope} pedidos de la corrida.')
            self._esperar(host)
            self.log['pedidos'] += 1
            try:
                estado, texto = self._fetch(url)
            except Exception as error:  # noqa: BLE001 - errores de red de la librería HTTP.
                ultimo = f'{type(error).__name__}'
            else:
                if estado in (401, 403, 451):
                    raise Restringido(f'{url} respondió HTTP {estado}.')
                if estado == 404:
                    raise NoEncontrado(f'{url} respondió HTTP 404.')
                if estado == 200 and any(m in texto[:5000].lower() for m in CHALLENGE):
                    raise Restringido(f'{url} respondió con un desafío anti-robots.')
                if estado == 200:
                    return texto
                ultimo = f'HTTP {estado}'
            self.log['reintentos'] += intento < self.reintentos
            if intento < self.reintentos:
                self._sleep(2 ** intento)
        raise RuntimeError(f'{url}: {ultimo} tras {self.reintentos} intentos.')

    def permitido(self, url):
        partes = urlsplit(url)
        host = partes.netloc
        if host not in self._robots:
            try:
                texto = self._pedir(f'{partes.scheme}://{host}/robots.txt')
                self._robots[host] = Robots(texto, USER_AGENT)
            except NoEncontrado:
                self._robots[host] = Robots()
            except Restringido:
                self._robots[host] = disallow_all()
        return self._robots[host].allowed(url)

    def get(self, url):
        if not self.permitido(url):
            raise Restringido(f'robots.txt no permite leer {url}.')
        return self._pedir(url)


# ------------------------------------------------------------------ lectura de listados y notas

def canonica(url):
    """https, host en minúsculas y sin consulta ni fragmento (quita utm_ y similares)."""
    partes = urlsplit(url.strip())
    return urlunsplit(('https', partes.netloc.lower(), partes.path, '', ''))


def _xml(texto):
    return ET.fromstring(texto.encode('utf-8') if isinstance(texto, str) else texto)


def _local(etiqueta):
    return etiqueta.rsplit('}', 1)[-1]


def parse_rss(texto):
    """Ítems de un RSS: dirección, titular y fecha. No lee content:encoded."""
    items = []
    for item in _xml(texto).iter('item'):
        campos = {_local(h.tag): (h.text or '').strip() for h in item}
        if campos.get('link'):
            items.append({'url': canonica(campos['link']), 'titular': html_lib.unescape(campos.get('title', '')),
                          'fecha': fecha_iso(campos.get('pubDate'))})
    return items


def parse_urlset(texto):
    out = []
    for nodo in _xml(texto):
        campos = {_local(h.tag): (h.text or '').strip() for h in nodo.iter()}
        if campos.get('loc'):
            out.append((campos['loc'], fecha_iso(campos.get('lastmod') or campos.get('publication_date'))))
    return out


TN_ENLACE = re.compile(r'(?:https://tn\.com\.ar)?(/economia/propiedades/(\d{4})/(\d\d)/(\d\d)/[a-z0-9-]+/)')


def parse_seccion_tn(texto):
    out = {}
    for m in TN_ENLACE.finditer(texto):
        out['https://tn.com.ar' + m.group(1)] = f'{m.group(2)}-{m.group(3)}-{m.group(4)}T00:00:00-03:00'
    return [{'url': u, 'titular': None, 'fecha': f} for u, f in out.items()]


def _jsonld(texto):
    for bloque in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', texto, re.S | re.I):
        try:
            datos = json.loads(bloque.strip())
        except json.JSONDecodeError:
            continue
        articulo = _articulo_en(datos if isinstance(datos, list) else datos.get('@graph', [datos]))
        if articulo is not None:
            return articulo
    return {}


def _articulo_en(candidatos):
    """El primer bloque JSON-LD que declara ser una nota; None si no hay."""
    for c in candidatos:
        tipo = c.get('@type') if isinstance(c, dict) else None
        tipos = tipo if isinstance(tipo, list) else [tipo]
        if any(t in ('NewsArticle', 'Article', 'ReportageNewsArticle', 'AnalysisNewsArticle') for t in tipos):
            return c
    return None


def _meta(texto, nombre):
    m = re.search(r'<meta[^>]+(?:property|name)="' + re.escape(nombre) + r'"[^>]+content="([^"]*)"', texto, re.I)
    return html_lib.unescape(m.group(1)) if m else None


def parse_articulo(texto):
    """Metadatos de la nota. `texto` solo se completa si el medio no la marca como de acceso restringido."""
    datos = _jsonld(texto)
    canon = re.search(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', texto, re.I)
    libre = datos.get('isAccessibleForFree', True)
    libre = not (libre is False or str(libre).strip().lower() == 'false')
    cuerpo = html_lib.unescape(datos.get('articleBody') or '') if libre else ''
    return {
        'url': canonica(canon.group(1)) if canon else None,
        'titular': html_lib.unescape(datos.get('headline') or _meta(texto, 'og:title') or '').strip(),
        'bajada': html_lib.unescape(datos.get('description') or _meta(texto, 'og:description') or '').strip(),
        'publicado': fecha_iso(datos.get('datePublished') or _meta(texto, 'article:published_time')),
        'modificado': fecha_iso(datos.get('dateModified') or _meta(texto, 'article:modified_time')),
        'acceso': 'libre' if libre else 'restringido',
        'texto': re.sub(r'<[^>]+>', ' ', cuerpo),
    }


def _listar_sitemap(cliente, fuente, url, desde):
    """Notas de un índice de sitemaps de noticias y el cierre más reciente anterior al período."""
    items, cierre_anterior = [], None
    for loc, modificado in parse_urlset(cliente.get(url))[:8]:
        if modificado and dia(modificado) < desde:
            cierre_anterior = max(filter(None, (cierre_anterior, dia(modificado))))
            continue
        items += [{'url': canonica(direccion), 'titular': None, 'fecha': fecha} for direccion, fecha in parse_urlset(cliente.get(loc))]
    return [i for i in items if i['url'].startswith(fuente.prefijo)], cierre_anterior


def _listar(cliente, fuente, tipo, url, desde):
    """Devuelve (items, fecha más antigua vista en el listado)."""
    if tipo == 'rss':
        items = parse_rss(cliente.get(url))
    elif tipo == 'rss_paginado':
        items, vistas, desplazamiento = [], set(), 0
        for _ in range(6):
            pagina = parse_rss(cliente.get(f'{url}&from={desplazamiento}' if desplazamiento else url))
            # Las URL ya leídas se guardan en un set que crece con cada página, en lugar de rearmarlo por ítem.
            nuevos = [i for i in pagina if i['url'] not in vistas]
            if not nuevos:
                break
            items += nuevos
            vistas.update(i['url'] for i in nuevos)
            desplazamiento += len(pagina)
            fechas = [dia(i['fecha']) for i in pagina if i['fecha']]
            if fechas and min(fechas) < desde:
                break
    elif tipo == 'sitemap_noticias':
        # Cada archivo del índice cubre una semana que termina en su lastmod. Se leen los que terminan
        # dentro del período o después; el primero que termina antes prueba que la cobertura es completa.
        return _listar_sitemap(cliente, fuente, url, desde)
    elif tipo == 'seccion':
        items = parse_seccion_tn(cliente.get(url))
    else:
        raise ValueError(tipo)
    fechas = [dia(i['fecha']) for i in items if i['fecha']]
    return [i for i in items if i['url'].startswith(fuente.prefijo)], min(fechas, default=None)


# ------------------------------------------------------------------ almacenamiento por fuente

def archivo(directorio, clave):
    return Path(directorio) / 'fuentes' / f'{clave}.json'


def cargar(directorio, clave):
    ruta = archivo(directorio, clave)
    if ruta.exists():
        return json.loads(ruta.read_text(encoding='utf-8'))
    return {'fuente': clave, 'notas': {}, 'periodos': {}, 'ultimo_intento': None}


def guardar(directorio, clave, datos):
    """Escritura atómica: o queda el archivo nuevo completo o el anterior intacto."""
    ruta = archivo(directorio, clave)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix('.tmp')
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True), encoding='utf-8')
    os.replace(temporal, ruta)


def _registrar(directorio, linea):
    ruta = Path(directorio) / 'corridas.jsonl'
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open('a', encoding='utf-8') as salida:
        salida.write(json.dumps(linea, ensure_ascii=False) + '\n')


def nota_desde(fuente, articulo, listado, recolectado):
    """Registro guardado: metadatos, clasificación y resumen propio. Sin bajada ni texto de la nota."""
    publicado = articulo.get('publicado') or listado.get('fecha')
    titular = articulo.get('titular') or listado.get('titular') or ''
    resultado = clasif.clasificar(fuente.medio, titular, articulo.get('bajada', ''), articulo.get('texto', ''),
                                  dia(publicado), articulo.get('acceso', 'sin_detalle'))
    url = articulo.get('url') or listado['url']
    return {
        'id': sha1(url.encode()).hexdigest()[:12], 'fuente': fuente.clave, 'medio': fuente.medio,
        'titular': titular, 'url': url,
        'urls_vistas': sorted({listado['url'], url}),
        'fecha_publicacion': publicado, 'fecha_modificacion': articulo.get('modificado'),
        'fecha_en_listado': listado.get('fecha'), 'recolectado_en': recolectado,
        'acceso': articulo.get('acceso', 'sin_detalle'), **resultado,
    }


def _sumar_candidatos(candidatos, items):
    """Une los ítems de un listado con los ya vistos: conserva el titular y la fecha más antigua."""
    for item in items:
        previo_item = candidatos.get(item['url'], {})
        candidatos[item['url']] = {**item, 'titular': item['titular'] or previo_item.get('titular'),
                                   'fecha': min(filter(None, (item['fecha'], previo_item.get('fecha'))), default=None)}


def recolectar_fuente(fuente, desde, hasta, cliente, directorio, reclasificar=False, momento=None):
    """Recolecta una fuente para el período y la guarda en su archivo. Devuelve el registro del período."""
    momento = momento or ahora().isoformat()
    datos = cargar(directorio, fuente.clave)
    clave_periodo = desde.isoformat()
    previo = datos['periodos'].get(clave_periodo)
    candidatos, antiguas, problemas, restringido = {}, [], [], None
    listados_ok = 0
    for tipo, url in fuente.listados:
        try:
            items, antigua = _listar(cliente, fuente, tipo, url, desde)
        except Restringido as error:
            restringido = str(error)
            problemas.append(f'{tipo}: {error}')
            continue
        except (RuntimeError, NoEncontrado, ET.ParseError, OSError) as error:
            problemas.append(f'{tipo}: {error}')
            continue
        listados_ok += 1
        if antigua:
            antiguas.append(antigua)
        _sumar_candidatos(candidatos, items)

    nuevas, fallidas, fuera, ya_guardadas = 0, 0, 0, 0
    if listados_ok:
        conocidas = {u for n in datos['notas'].values() for u in n['urls_vistas']}
        for url, item in sorted(candidatos.items()):
            fecha_listado = dia(item['fecha'])
            # El listado puede traer la fecha de modificación: se mira un día de margen a cada lado.
            if fecha_listado and not desde - timedelta(days=1) <= fecha_listado <= hasta + timedelta(days=1):
                continue
            if url in conocidas and not reclasificar:
                ya_guardadas += 1
                continue
            try:
                articulo = parse_articulo(cliente.get(url))
            except Restringido as error:
                problemas.append(f'nota: {error}')
                articulo = {'acceso': 'restringido'}
            except (RuntimeError, NoEncontrado, OSError) as error:
                fallidas += 1
                problemas.append(f'nota: {error}')
                if not item.get('titular'):
                    continue
                articulo = {'acceso': 'sin_detalle'}
            if not (articulo.get('publicado') or item.get('fecha')):
                continue
            nota = nota_desde(fuente, articulo, item, momento)
            existente = datos['notas'].get(nota['url'])
            if existente:  # Misma URL canónica: se actualiza sin duplicar y se conserva la primera recolección.
                nota['recolectado_en'] = existente['recolectado_en']
                nota['urls_vistas'] = sorted(set(existente['urls_vistas']) | set(nota['urls_vistas']))
            else:
                nuevas += 1
            datos['notas'][nota['url']] = nota
            if not desde <= dia(nota['fecha_publicacion']) <= hasta:
                fuera += 1

    en_periodo = sorted(u for u, n in datos['notas'].items()
                        if n['fecha_publicacion'] and desde <= dia(n['fecha_publicacion']) <= hasta)
    cubre = bool(antiguas) and min(antiguas) < desde
    if not listados_ok:
        estado = 'restringido' if restringido else 'error'
    elif problemas or not cubre or listados_ok < len(fuente.listados):
        estado = 'parcial'
    else:
        estado = 'ok'
    motivo = '; '.join(problemas[:4])
    if listados_ok and not cubre:
        hasta_donde = min(antiguas).isoformat() if antiguas else 'sin fechas'
        motivo = '; '.join(filter(None, [motivo, f'Los listados solo llegaban hasta {hasta_donde}.']))
    intento = {'fecha': momento, 'estado': estado, 'motivo': motivo or None, 'pedidos': cliente.log['pedidos'],
               'reintentos': cliente.log['reintentos'], 'candidatas': len(candidatos), 'nuevas': nuevas,
               'ya_guardadas': ya_guardadas, 'fallidas': fallidas, 'fuera_de_periodo': fuera}
    registro = {'desde': desde.isoformat(), 'hasta': hasta.isoformat(), 'estado': estado, 'motivo': motivo or None,
                'recolectado_en': momento, 'notas': en_periodo,
                'cobertura_desde': min(antiguas).isoformat() if antiguas else None, 'ultimo_intento': intento}
    exito_previo = previo and previo['estado'] in ('ok', 'parcial')
    if estado in ('error', 'restringido') and exito_previo:
        # La falla no borra la recolección anterior del mismo período: solo se anota el intento.
        registro = {**previo, 'notas': sorted(set(previo['notas']) | set(en_periodo)), 'ultimo_intento': intento}
    elif estado == 'parcial' and previo and previo['estado'] == 'ok':
        registro = {**previo, 'notas': sorted(set(previo['notas']) | set(en_periodo)), 'ultimo_intento': intento}
    datos['periodos'][clave_periodo] = registro
    datos['ultimo_intento'] = intento
    guardar(directorio, fuente.clave, datos)
    _registrar(directorio, {'fuente': fuente.clave, 'periodo': clave_periodo, **intento})
    return registro


def recolectar(desde, hasta, directorio=RADAR_DIR, fuentes=None, cliente_factory=Cliente, reclasificar=False):
    """Corre cada fuente por separado: una falla no frena a las demás."""
    resultados = {}
    for clave in fuentes or FUENTES:
        try:
            resultados[clave] = recolectar_fuente(FUENTES[clave], desde, hasta, cliente_factory(), directorio,
                                                  reclasificar=reclasificar)
        except Exception as error:  # noqa: BLE001 - se registra y se sigue con la próxima fuente.
            momento = ahora().isoformat()
            datos = cargar(directorio, clave)
            intento = {'fecha': momento, 'estado': 'error', 'motivo': f'{type(error).__name__}: {error}'}
            previo = datos['periodos'].get(desde.isoformat())
            datos['periodos'][desde.isoformat()] = ({**previo, 'ultimo_intento': intento} if previo else
                                                    {'desde': desde.isoformat(), 'hasta': hasta.isoformat(),
                                                     'estado': 'error', 'motivo': intento['motivo'],
                                                     'recolectado_en': momento, 'notas': [], 'cobertura_desde': None,
                                                     'ultimo_intento': intento})
            datos['ultimo_intento'] = intento
            guardar(directorio, clave, datos)
            _registrar(directorio, {'fuente': clave, 'periodo': desde.isoformat(), **intento})
            resultados[clave] = datos['periodos'][desde.isoformat()]
    return resultados


# ------------------------------------------------------------------ boletín para la interfaz

def _tokens(titular):
    return {t for t in clasif.clave_texto(titular).split() if len(t) > 2}


def _parecidos(a, b):
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.8


def _vista(nota):
    return {k: nota.get(k) for k in ('id', 'medio', 'titular', 'url', 'fecha_publicacion', 'tema', 'tema_nombre',
                                     'resumen', 'fecha_hecho', 'acceso', 'barrios', 'incidentales', 'alcance')}


def _anotar_aperturas(nota, grupos, cobertura, inicio, fin):
    """Agrupa las aperturas reportadas de una nota por local y dirección; las demás van a cobertura."""
    for hecho in nota.get('aperturas', []):
        completo = hecho['local'] and hecho['direccion']
        if hecho['tipo'] == 'reportada' and completo and hecho['fecha_hecho']:
            k = (clasif.clave_texto(hecho['local']), clasif.clave_texto(hecho['direccion']))
            grupo = grupos.setdefault(k, {'local': hecho['local'], 'direccion': hecho['direccion'],
                                          'barrio': hecho['barrio'], 'fechas': set(), 'notas': {}})
            grupo['fechas'].add(hecho['fecha_hecho'])
            grupo['barrio'] = grupo['barrio'] or hecho['barrio']
            grupo['notas'][nota['url']] = {'medio': nota['medio'], 'titular': nota['titular'], 'url': nota['url'],
                                           'fecha_publicacion': nota['fecha_publicacion']}
        elif inicio <= dia(nota['fecha_publicacion']) <= fin:
            motivo = ('anuncio de una apertura futura' if hecho['tipo'] == 'anuncio' else
                      'sin fecha de apertura verificable' if not hecho['fecha_hecho'] else
                      'sin local y dirección identificables')
            cobertura.append({**hecho, 'motivo': motivo, 'nota': {'medio': nota['medio'], 'url': nota['url'],
                                                                  'titular': nota['titular']}})


def _fila_barrio(barrios, barrio):
    return barrios.setdefault(barrio, {'barrio': barrio, 'notas': [], 'aperturas': [], 'incidentales': 0})


def _sumar_nota(barrios, nota, vista):
    """Suma la nota a sus barrios principales y cuenta una mención en cada incidental."""
    for b in nota['barrios']:
        _fila_barrio(barrios, b)['notas'].append(vista(nota))
    for b in nota['incidentales']:
        _fila_barrio(barrios, b)['incidentales'] += 1


def boletin(directorio=RADAR_DIR, desde=None):
    """Arma el radar del período: notas por barrio, aperturas reportadas y estado de cada fuente."""
    archivos = {clave: cargar(directorio, clave) for clave in FUENTES}
    periodos = sorted({p for d in archivos.values() for p in d['periodos']}, reverse=True)
    if not periodos:
        return {'disponible': False, 'motivo': 'El radar todavía no se ejecutó. Corré python -m precio_entorno.radar.',
                'aviso': AVISO}
    clave = desde if desde in periodos else periodos[0]
    inicio = date.fromisoformat(clave)
    fin = max(date.fromisoformat(d['periodos'][clave]['hasta']) for d in archivos.values() if clave in d['periodos'])

    todas = sorted((n for d in archivos.values() for n in d['notas'].values() if n.get('fecha_publicacion')),
                   key=lambda n: (n['fecha_publicacion'], n['url']))
    # Republicaciones: titulares casi idénticos. La primera publicación es la original.
    originales, republicadas = [], {}
    for nota in todas:
        original = next((o for o in originales if _parecidos(o['titular'], nota['titular'])), None)
        if original:
            republicadas.setdefault(original['url'], []).append(nota)
        else:
            originales.append(nota)
    en_periodo = [n for n in originales if inicio <= dia(n['fecha_publicacion']) <= fin]

    def con_republicaciones(nota):
        extra = republicadas.get(nota['url'], [])
        return {**_vista(nota), 'republicaciones': [{'medio': r['medio'], 'url': r['url'],
                                                     'fecha_publicacion': r['fecha_publicacion']} for r in extra]}

    # Aperturas: se agrupan por local y dirección en todas las notas guardadas; cuentan si la fecha
    # verificable de la apertura cae en el período.
    grupos, cobertura = {}, []
    for nota in originales + [r for rs in republicadas.values() for r in rs]:
        _anotar_aperturas(nota, grupos, cobertura, inicio, fin)
    aperturas = []
    for grupo in grupos.values():
        fecha = min(grupo['fechas'])
        if inicio <= date.fromisoformat(fecha) <= fin:
            aperturas.append({'local': grupo['local'], 'direccion': grupo['direccion'], 'barrio': grupo['barrio'],
                              'fecha_apertura': fecha, 'fechas_informadas': sorted(grupo['fechas']),
                              'notas': sorted(grupo['notas'].values(), key=lambda n: n['fecha_publicacion'])})
    aperturas.sort(key=lambda a: (a['fecha_apertura'], a['local']))

    barrios = {}
    for nota in en_periodo:
        _sumar_nota(barrios, nota, con_republicaciones)
    for apertura in aperturas:
        if apertura['barrio']:
            barrios.setdefault(apertura['barrio'], {'barrio': apertura['barrio'], 'notas': [], 'aperturas': [],
                                                    'incidentales': 0})['aperturas'].append(apertura)
    filas = sorted(barrios.values(), key=lambda b: clasif.plano(b['barrio']))

    fuentes = []
    for clave_fuente, fuente in FUENTES.items():
        registro = archivos[clave_fuente]['periodos'].get(clave)
        fuentes.append({
            'fuente': clave_fuente, 'medio': fuente.medio, 'seccion': fuente.seccion, 'metodo': fuente.metodo,
            'estado': registro['estado'] if registro else 'sin_ejecutar',
            'motivo': registro.get('motivo') if registro else 'No se ejecutó para este período.',
            'recolectado_en': registro.get('recolectado_en') if registro else None,
            'ultimo_intento': registro.get('ultimo_intento') if registro else None,
            'cobertura_desde': registro.get('cobertura_desde') if registro else None,
            'notas': sum(n['fuente'] == clave_fuente for n in en_periodo),
        })
    intentos = [f['ultimo_intento']['fecha'] for f in fuentes if f.get('ultimo_intento')]
    return {
        'disponible': True, 'aviso': AVISO,
        'periodo': {'desde': clave, 'hasta': fin.isoformat()}, 'periodos': periodos,
        'actualizado': max(intentos, default=None), 'fuentes': fuentes,
        'totales': {'notas': len(en_periodo), 'con_barrio': sum(bool(n['barrios']) for n in en_periodo),
                    'aperturas': len(aperturas), 'republicaciones': sum(
                        len(republicadas.get(n['url'], [])) for n in en_periodo)},
        'barrios': [{'barrio': b['barrio'], 'notas': len(b['notas']), 'aperturas': len(b['aperturas']),
                     'incidentales': b['incidentales']} for b in filas],
        'detalle': {b['barrio']: {'notas': b['notas'], 'aperturas': b['aperturas']} for b in filas},
        'sin_barrio': [con_republicaciones(n) for n in en_periodo if not n['barrios']],
        'aperturas': aperturas, 'aperturas_sin_conteo': cobertura,
    }


# ------------------------------------------------------------------ línea de comandos

def validar(url, cliente=None, hoy=None):
    """Clasifica una nota sin guardarla y dice si entraría en el período actual."""
    cliente = cliente or Cliente()
    articulo = parse_articulo(cliente.get(url))
    host = urlsplit(url).netloc
    fuente = next((f for f in FUENTES.values() if urlsplit(f.prefijo).netloc == host), FUENTES['clarin'])
    nota = nota_desde(fuente, articulo, {'url': canonica(url)}, ahora().isoformat())
    desde, hasta = periodo(hoy)
    nota['en_periodo_actual'] = desde <= dia(nota['fecha_publicacion']) <= hasta
    nota['periodo_actual'] = {'desde': desde.isoformat(), 'hasta': hasta.isoformat()}
    return nota


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--hasta', type=date.fromisoformat,
                        help='Fecha de corte, excluida (AAAA-MM-DD). Por defecto, hoy en Buenos Aires.')
    parser.add_argument('--fuentes', nargs='+', choices=sorted(FUENTES))
    parser.add_argument('--directorio', type=Path, default=RADAR_DIR)
    parser.add_argument('--reclasificar', action='store_true', help='Vuelve a leer notas ya guardadas.')
    parser.add_argument('--validar', metavar='URL', help='Clasifica una nota sin guardarla.')
    parser.add_argument('--resumen', action='store_true', help='Muestra el boletín guardado sin recolectar.')
    args = parser.parse_args(argv)
    if args.validar:
        print(json.dumps(validar(args.validar), ensure_ascii=False, indent=2))
        return 0
    if not args.resumen:
        desde, hasta = periodo(args.hasta)
        print(f'Radar: notas publicadas del {desde} al {hasta}.')
        for clave, registro in recolectar(desde, hasta, args.directorio, args.fuentes,
                                          reclasificar=args.reclasificar).items():
            intento = registro.get('ultimo_intento') or {}
            print(f"- {FUENTES[clave].medio}: {registro['estado']} · {len(registro['notas'])} notas en el período · "
                  f"{intento.get('nuevas', 0)} nuevas · {intento.get('pedidos', 0)} pedidos"
                  + (f" · {registro['motivo']}" if registro.get('motivo') else ''))
    datos = boletin(args.directorio, (periodo(args.hasta)[0].isoformat() if not args.resumen or args.hasta else None))
    if not datos['disponible']:
        print(datos['motivo'])
        return 1
    print(f"\nPeríodo {datos['periodo']['desde']} a {datos['periodo']['hasta']}: {datos['totales']['notas']} notas, "
          f"{datos['totales']['aperturas']} aperturas reportadas con fecha verificable.")
    for fila in datos['barrios']:
        print(f"  {fila['barrio']}: {fila['notas']} notas · {fila['aperturas']} aperturas"
              + (f" · {fila['incidentales']} menciones incidentales (no suman)" if fila['incidentales'] else ''))
    return 0 if all(f['estado'] in ('ok', 'parcial') for f in datos['fuentes']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
