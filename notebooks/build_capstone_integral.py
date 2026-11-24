"""Genera el Colab integral a partir de la memoria y los módulos auditados."""

import hashlib
import json
import re
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
MEMORY = (ROOT / 'docs/memoria-matematica.md').read_text(encoding='utf-8')
cells = []


def md(text, name):
    cell = nbf.v4.new_markdown_cell(text.strip())
    cell['id'] = name
    cells.append(cell)


def code(text, name):
    cell = nbf.v4.new_code_cell(text.strip())
    cell['id'] = name
    cells.append(cell)


def theory(start, end):
    text = MEMORY.split(start, 1)[1].split(end, 1)[0].strip()
    # Las referencias relativas de la memoria no se abren dentro de Colab.
    return re.sub(r'\[([^\]]+)\]\((?!https?://)[^)]+\)', r'\1', text)


md(r"""
# Lüga
## Del catálogo a una decisión fundamentada

**Capstone integral · Estadística, aprendizaje automático y operación · 18 de noviembre de 2026**

Una inmobiliaria recibe una búsqueda. Tiene un presupuesto, varios barrios posibles y demasiados avisos para revisar uno por uno. Este cuaderno recorre cómo convertir un catálogo autorizado en referencias de publicación, con evidencia estadística y límites explícitos.

**Recorrido del producto:** preferencias → comparación de barrios → búsqueda guardada → alerta por aviso nuevo.

**Tres preguntas que guían la lectura**

1. ¿Cómo se distribuyen los precios publicados y cuánto difieren entre barrios?
2. ¿Cuál de cinco modelos generaliza mejor dentro de la captura observada?
3. ¿Qué falta para convertir sus predicciones en ahorro de tiempo para el cliente?

Trabajamos con datos **reales autorizados**. Las referencias estiman precios publicados por m² cubierto; no son tasaciones, precios de cierre ni recomendaciones de inversión. Los delitos registrados se muestran como contexto, con período y unidad geográfica. El radar editorial queda fuera de los cálculos.

### Cómo usar este Colab

1. Elegir un entorno **CPU**, subir `capstone_bundle.zip` cuando lo pida la sección 1 y ejecutar las celdas en orden.
2. Mantener `REENTRENAR = False` para leer los resultados auditados y ejecutar los análisis y el reajuste final. Cambiarlo a `True` para repetir los **505 ajustes** de la comparación completa.
3. Usar los parámetros del explorador y del escenario de negocio. Al final se genera `salidas_capstone.zip`, con tablas, figuras, modelo y manifiesto.

El modo de lectura reutiliza predicciones externas verificadas por hash: **no simula un nuevo entrenamiento**. Las celdas identifican siempre el origen de la evidencia. El código necesario viaja dentro del ZIP: no hace falta clonar el repositorio, configurar claves ni llamar a servicios pagos.

### Índice

1. Entorno y trazabilidad · 2. Contrato de datos · 3. Calidad y cobertura · 4. Distribuciones y geografía · 5. Contexto y asociaciones · 6. ANOVA · 7. Cinco modelos · 8. Validación anidada · 9. Comparación y errores · 10. Interpretación · 11. Explorador de búsquedas · 12. Modelo exportable · 13. Negocio y costos · 14. Confirmación futura · 15. Exportación · Anexo A. Validación temporal del HGB operativo · Referencias.
""", 'portada')

md("""
## 1 · Entorno y trazabilidad

La configuración conserva la semilla 42 y limita los hilos de cálculo. Los modelos tabulares utilizados no aprovechan una GPU mediante scikit-learn. Los recursos de Colab son variables; el tiempo de una corrida local no garantiza el de Colab. [Condiciones de recursos de Google Colab](https://research.google.com/colaboratory/faq.html).

La instalación se realiza antes de importar bibliotecas científicas. Si se ejecutó otro código previamente en Colab y cambió una biblioteca ya cargada, reiniciar el entorno antes de continuar.
""", 'entorno-texto')

code(r"""
import os, sys, subprocess, platform, importlib.metadata
from pathlib import Path

try:
    import google.colab
    EN_COLAB = True
except ImportError:
    EN_COLAB = False

os.environ['OMP_NUM_THREADS'] = '2'
os.environ['OPENBLAS_NUM_THREADS'] = '2'
os.environ['MKL_NUM_THREADS'] = '2'

REENTRENAR = False  #@param {type:"boolean"}
INSTALAR_EN_COLAB = True  #@param {type:"boolean"}
DESCARGAR_AL_FINAL = False  #@param {type:"boolean"}

if EN_COLAB and INSTALAR_EN_COLAB:
    requisitos = ['numpy>=1.26,<3', 'pandas>=2.2,<3', 'scikit-learn==1.7.2',
                  'scipy>=1.16,<2', 'matplotlib>=3.8,<4', 'joblib>=1.3,<2', 'ipywidgets>=7,<9']
    previas = {p: importlib.metadata.version(p) for p in ['numpy', 'pandas', 'scikit-learn', 'scipy']}
    cargadas = {p for p in ['numpy', 'pandas', 'sklearn', 'scipy'] if p in sys.modules}
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', *requisitos], check=True)
    for modulo, distribucion in [('numpy','numpy'), ('pandas','pandas'), ('sklearn','scikit-learn'), ('scipy','scipy')]:
        if modulo in cargadas and importlib.metadata.version(distribucion) != previas[distribucion]:
            raise RuntimeError('Cambió una biblioteca ya cargada. Reiniciar entorno y ejecutar desde el inicio.')

import io, json, hashlib, html, time, warnings
from zipfile import ZipFile, ZIP_DEFLATED
from datetime import datetime, timezone
from pathlib import PurePosixPath
import numpy as np
import pandas as pd
import scipy, sklearn, joblib
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from matplotlib.patches import Polygon
from matplotlib.collections import PatchCollection
from IPython.display import display, HTML, Markdown
from threadpoolctl import threadpool_limits

versiones = {p: importlib.metadata.version(p) for p in ['numpy','pandas','scipy','scikit-learn','matplotlib','joblib']}
assert tuple(map(int, scipy.__version__.split('.')[:2])) >= (1,16), 'Se requiere SciPy >= 1.16.'
print('Python', platform.python_version(), '·', platform.system(), '· Colab:', EN_COLAB)
display(pd.Series(versiones, name='Versión del entorno actual').to_frame())
INICIO_CUADERNO = time.perf_counter()
""", 'configuracion')

code(r"""
display(HTML('''<style>
.capstone-note {padding:16px 20px;border-left:4px solid #6a4fb3;background:#f5f2fb;color:#24323b;margin:18px 0;line-height:1.6}
.capstone-kpis {display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}
.capstone-kpi {flex:1;min-width:160px;padding:18px;border:1px solid #dce2e7;border-radius:8px;background:#fbfcfd}
.capstone-kpi strong {display:block;font-size:26px;color:#392c60;margin-top:6px}
.dataframe {font-size:12px;border-collapse:collapse}
.dataframe th {text-align:left;background:#f4f6f8;padding:9px}
.dataframe td {padding:8px;border-bottom:1px solid #edf0f3}
</style>'''))
INK, PURPLE, BLUE, ORANGE, GRAY = '#24323b', '#6a4fb3', '#2b6699', '#b96039', '#80909d'
plt.rcParams.update({'figure.dpi':110, 'savefig.dpi':160, 'font.size':10,
                     'figure.facecolor':'white', 'axes.facecolor':'white',
                     'axes.spines.top':False, 'axes.spines.right':False,
                     'axes.titlelocation':'left', 'axes.titlesize':12, 'axes.labelcolor':INK,
                     'text.color':INK, 'legend.frameon':False})
pd.set_option('display.max_columns', 22)
pd.set_option('display.max_rows', 60)

def nota(texto):
    display(HTML('<div class="capstone-note">' + html.escape(texto) + '</div>'))

def kpis(valores):
    display(HTML('<div class="capstone-kpis">' + ''.join(
        '<div class="capstone-kpi">' + html.escape(str(k)) + '<strong>' + html.escape(str(v)) + '</strong></div>'
        for k,v in valores.items()) + '</div>'))

def figura(fig, nombre):
    fig.savefig(SALIDA / (nombre + '.png'), bbox_inches='tight')
    display(fig)
    plt.close(fig)
""", 'estilo')

md("""
### Un solo paquete de entrada

`capstone_bundle.zip` contiene el bundle de datos, los módulos auditados y las predicciones externas históricas. La siguiente celda comprueba los hashes y los límites de ruta antes de utilizarlo. Un hash comprueba integridad frente al manifiesto; no equivale a una firma de autor.

Se puede subir desde la computadora o colocarlo en `/content/drive/MyDrive/precio-entorno-caba/`. El montaje de Drive es opcional y manual. El cuaderno no comparte archivos ni modifica servicios remotos.
""", 'paquete-texto')

code(r"""
PROYECTO = next((p for p in [Path.cwd(), *Path.cwd().parents] if (p/'precio_entorno').is_dir()), Path.cwd())
CANDIDATOS = [Path('capstone_bundle.zip'), Path('/content/capstone_bundle.zip'),
              PROYECTO/'data/processed/colab-capstone/capstone_bundle.zip',
              Path('/content/drive/MyDrive/precio-entorno-caba/capstone_bundle.zip')]
PAQUETE = next((p for p in CANDIDATOS if p.is_file()), None)
if PAQUETE is None and EN_COLAB:
    from google.colab import files
    print('Seleccionar capstone_bundle.zip')
    subidos = files.upload()
    if 'capstone_bundle.zip' not in subidos:
        raise ValueError('Subir el archivo capstone_bundle.zip, sin cambiar su nombre.')
    PAQUETE = Path('capstone_bundle.zip')
if PAQUETE is None:
    raise FileNotFoundError('Falta capstone_bundle.zip. En el proyecto: python scripts/preparar_colab_capstone.py')

TRABAJO = Path('/content/capstone-caba') if EN_COLAB else PROYECTO/'data/processed/colab-capstone/workspace'
TRABAJO.mkdir(parents=True, exist_ok=True)
SALIDA = TRABAJO/'salidas'
SALIDA.mkdir(exist_ok=True)
with ZipFile(PAQUETE) as paquete:
    paquete_meta = json.loads(paquete.read('capstone_manifest.json'))
    permitidos = paquete_meta['archivos_sha256']
    if set(paquete.namelist()) != set(permitidos) | {'capstone_manifest.json'}:
        raise ValueError('El ZIP contiene entradas no declaradas o repetidas.')
    if len(paquete.infolist()) != len(set(paquete.namelist())) or sum(i.file_size for i in paquete.infolist()) > 200_000_000:
        raise ValueError('Tamaño o entradas del paquete inválidos.')
    for nombre, digest in permitidos.items():
        ruta = PurePosixPath(nombre)
        if ruta.is_absolute() or '..' in ruta.parts or '\\' in nombre or ':' in nombre:
            raise ValueError('Ruta de paquete inválida.')
        contenido = paquete.read(nombre)
        if hashlib.sha256(contenido).hexdigest() != digest:
            raise ValueError('No coincide el hash: ' + nombre)
        destino = TRABAJO.joinpath(*ruta.parts)
        if not destino.resolve().is_relative_to(TRABAJO.resolve()):
            raise ValueError('Ruta fuera del espacio de trabajo.')
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(contenido)

sys.path.insert(0, str(TRABAJO))
from precio_entorno import benchmark_inmobiliario as bm
from precio_entorno.auditoria_estadistica import run as ejecutar_auditoria, verify_splits, summarize
from precio_entorno.anova_barrios import analyze

BUNDLE = TRABAJO/'data/processed/eda-colab/eda_bundle.zip'
EVIDENCIA = TRABAJO/'reports/benchmark-auditado'
OOF_PATH = TRABAJO/'data/processed/auditoria-estadistica/predicciones_oof.csv'
print('Paquete verificado:', hashlib.sha256(PAQUETE.read_bytes()).hexdigest())
print('Archivos declarados:', len(permitidos), '· Espacio de trabajo:', TRABAJO)
""", 'paquete')

md('## 2 · Contrato de datos\n\n' + theory('## 1. Qué estimamos y sobre qué población', '## 2. Variables, preprocesamiento y escala del objetivo'), 'contrato-texto')

code(r"""
data = bm.load_sales(BUNDLE).reset_index(drop=True)
with ZipFile(BUNDLE) as z:
    meta = json.loads(z.read('meta.json'))
    geo = json.loads(z.read('entorno/barrios.geojson'))
    delitos = pd.read_csv(z.open('delitos/barrio_anio.csv'))

assert len(data) == data['id'].nunique(), 'Los ID deben ser únicos.'
assert np.allclose(data['price']/data['covered_area'], data['precio_m2'])
assert data['currency'].eq('USD').all()
assert data['grupo'].notna().all()
kpis({'Avisos de venta':f'{len(data):,}', 'Propiedades aproximadas':f'{data.grupo.nunique():,}',
      'Barrios':data.neighborhood.nunique(), 'Mediana publicada':f'USD {data.precio_m2.median():,.0f}/m²'})
display(Markdown('**Capturas:** ' + ', '.join(meta['captura']) + '. **Contexto:** ' + meta['delitos']))
nota('El paquete también contiene alquileres en una tabla separada. El modelo de este cuaderno usa únicamente venta en USD.')
""", 'contrato')

md(r"""
## 3 · Calidad, cobertura y fuentes

Antes de elegir un algoritmo revisamos qué está realmente informado. Un faltante puede representar una práctica de la fuente, no una ausencia aleatoria. Si una variable aparece solo en ciertas inmobiliarias, su mejora predictiva puede incorporar diferencias de segmento o disponibilidad.

**Qué mirar:** tamaño de cada fuente, cobertura de edificio, duplicados aproximados y rangos físicos. La regla de grupos reduce fuga entre copias detectadas; no garantiza identificar cada inmueble.
""", 'calidad-texto')

code(r"""
features = bm.NUMERIC + bm.CATEGORICAL + bm.EXTRA
diccionario = pd.DataFrame([
    ('covered_area','m²','Superficie cubierta'), ('total_area_m2','m²','Superficie total'),
    ('rooms','ambientes','Cantidad de ambientes'), ('latitude','grados','Latitud aproximada'),
    ('longitude','grados','Longitud aproximada'), ('dist_transporte_m','m','Transporte más cercano'),
    ('dist_parque_m','m','Parque más cercano'), ('dist_hospital_m','m','Hospital más cercano'),
    ('gastronomia_500m','puntos / radio 500 m','Gastronomía cercana'),
    ('escuelas_500m','puntos / radio 500 m','Escuelas cercanas'),
    ('neighborhood','categoría','Barrio oficial'), ('agency','categoría','Fuente inmobiliaria'),
    ('age_years','años','Antigüedad informada'), ('cond_code','categoría nominal','Estado de conservación')
], columns=['variable','unidad','definicion'])
diccionario['faltantes_pct'] = diccionario.variable.map(data[features].isna().mean()*100)
display(diccionario.round(1))
diccionario.to_csv(SALIDA/'diccionario.csv', index=False)
fuentes = data.groupby('agency').agg(avisos=('id','size'), grupos=('grupo','nunique'),
                                      edad_informada=('age_years','count'), estado_informado=('cond_code','count'))
display(fuentes)
fuentes.to_csv(SALIDA/'cobertura_fuentes.csv')
checks_datos = pd.Series({'cubierta_mayor_total':int(data.covered_area.gt(data.total_area_m2).sum()),
    'grupos_con_varios_avisos':int(data.groupby('grupo').size().gt(1).sum()),
    'pines_repetidos_adicionales':int(data.dropna(subset=['latitude','longitude']).duplicated(['latitude','longitude']).sum())})
display(checks_datos.to_frame('cantidad'))
fig, ax = plt.subplots(figsize=(10,4.5), constrained_layout=True)
ax.imshow(data.groupby('agency')[features].agg(lambda s:s.isna().mean()).to_numpy(),
          vmin=0,vmax=1,cmap='Purples',aspect='auto')
ax.set_xticks(range(len(features)), features, rotation=55, ha='right')
ax.set_yticks(range(len(fuentes)), fuentes.index)
ax.set_title('Proporción de faltantes por fuente · blanco = 0; violeta = 100 %')
figura(fig,'01_cobertura')
""", 'calidad')

md(r"""
## 4 · Distribuciones y geografía de publicación

Comparamos distribuciones, no solo promedios. El histograma en escala original conserva la cola; el logaritmo permite observar el cuerpo central sin eliminar casos. El mapa usa **medianas de avisos por barrio**, una medida descriptiva distinta de las medias por grupo del ANOVA.
""", 'eda-texto')

code(r"""
display(data[['price','precio_m2','covered_area','age_years']].describe(percentiles=[.01,.25,.5,.75,.99]).round(1))
fig, axes = plt.subplots(1,2,figsize=(12,4),constrained_layout=True)
axes[0].hist(data.precio_m2,bins=65,color=BLUE)
axes[0].set(xlabel='Precio publicado (USD/m²)',ylabel='Avisos',title='Distribución completa')
axes[1].hist(np.log(data.precio_m2),bins=45,color=PURPLE)
axes[1].set(xlabel='Logaritmo de USD/m²',ylabel='Avisos',title='Misma muestra · escala logarítmica')
figura(fig,'02_distribucion')

barrios = data.groupby('neighborhood').agg(avisos=('id','size'), mediana_usd_m2=('precio_m2','median'),
    media_usd_m2=('precio_m2','mean')).sort_values('mediana_usd_m2')
barrios.to_csv(SALIDA/'barrios_descriptivos.csv')
fig, axes = plt.subplots(1,2,figsize=(12,7),gridspec_kw={'width_ratios':[1,1.15]},constrained_layout=True)
extremos = pd.concat([barrios.head(8),barrios.tail(8)])
axes[0].barh(extremos.index,extremos.mediana_usd_m2,color=PURPLE)
axes[0].set(xlabel='Mediana publicada (USD/m²)',title='Ocho medianas menores y ocho mayores')
patches, colors = [], []
for feature in geo['features']:
    barrio = feature['properties']['barrio']
    geometry = feature['geometry']
    polygons = geometry['coordinates'] if geometry['type']=='MultiPolygon' else [geometry['coordinates']]
    for polygon in polygons:
        patches.append(Polygon(polygon[0],closed=True))
        colors.append(barrios.loc[barrio,'mediana_usd_m2'] if barrio in barrios.index else np.nan)
collection = PatchCollection(patches,cmap='Purples',edgecolor='white',linewidth=.55)
collection.set_array(np.array(colors))
axes[1].add_collection(collection)
axes[1].autoscale_view()
axes[1].set_aspect(1/np.cos(np.deg2rad(-34.6)))
axes[1].set(xlabel='Longitud',ylabel='Latitud',title='Mediana por barrio oficial · misma captura')
axes[1].xaxis.set_major_locator(MaxNLocator(4))
fig.colorbar(collection,ax=axes[1],label='USD/m² publicados',shrink=.7)
figura(fig,'03_geografia')
nota('La oferta fue recolectada con topes por barrio y fuente. El color no representa precio de cierre ni nivel de seguridad.')
""", 'eda')

md(r"""
## 5 · Asociaciones y contexto: tres niveles distintos

Pearson resume asociación lineal y Spearman ordenamiento monótono. Los calculamos por aviso y mostramos cómo cambia Spearman al dividir cada precio por la mediana de su barrio. Ese ajuste descriptivo atenúa niveles barriales; no controla todos los atributos ni identifica causalidad.

El contexto delictivo corresponde a **hechos registrados por barrio y año**. Los conteos no son tasas de exposición; dependen de denuncia, actividad y circulación. Su visualización no prueba que causen diferencias de publicación.
""", 'asociaciones-texto')

code(r"""
relativo = data.precio_m2 / data.groupby('neighborhood').precio_m2.transform('median')
asociaciones = []
for variable in bm.NUMERIC + ['age_years']:
    validos = data[variable].notna()
    asociaciones.append({'variable':variable,'n':int(validos.sum()),
        'Pearson':data.loc[validos,variable].corr(data.loc[validos,'precio_m2']),
        'Spearman':data.loc[validos,variable].corr(data.loc[validos,'precio_m2'],method='spearman'),
        'Spearman_relativo':data.loc[validos,variable].corr(relativo[validos],method='spearman')})
asociaciones = pd.DataFrame(asociaciones)
display(asociaciones.round(3))
asociaciones.to_csv(SALIDA/'asociaciones.csv',index=False)
contexto = delitos.groupby('anio').agg(barrios=('barrio','nunique'),delitos_registrados=('total_delitos','sum'))
display(contexto)
contexto.to_csv(SALIDA/'contexto_anual.csv')
contexto_2025 = delitos[delitos.anio.eq(2025)].set_index('barrio').join(barrios)
fig,axes=plt.subplots(1,2,figsize=(12,4.5),constrained_layout=True)
edad=data.dropna(subset=['age_years'])
axes[0].scatter(edad.age_years,edad.precio_m2,s=9,alpha=.15,color=BLUE)
axes[0].set(xlabel='Antigüedad informada (años)',ylabel='Publicado (USD/m²)',yscale='log',title=f'Por aviso · edad informada (n={len(edad)})')
axes[1].scatter(contexto_2025.total_delitos,contexto_2025.mediana_usd_m2,s=35,color=PURPLE)
axes[1].set(xlabel='Delitos registrados en 2025 por barrio',ylabel='Mediana publicada (USD/m²)',title='Agregados barriales · no efecto causal')
figura(fig,'04_asociaciones_contexto')
nota('Los delitos y el radar editorial no entran en los cinco modelos. Los alquileres permanecen separados por operación y moneda.')
""", 'asociaciones')

md('## 6 · ANOVA: ¿difieren las medias entre barrios?\n\n' + theory('## 6. ANOVA: una pregunta descriptiva sobre barrios','## 7. Conexión con operación y negocio'), 'anova-teoria')

code(r"""
anova, resumen_barrios, tabla_anova, pares = analyze(data, min_groups=5, alpha=.05)
display(pd.DataFrame([{'prueba':'Welch principal',**anova['welch']},
                     {'prueba':'ANOVA clásico',**anova['clasico']}]))
display(tabla_anova.round(2))
display(pd.DataFrame({'diagnostico': ['Brown–Forsythe','Normalidad agrupada','Kruskal sensibilidad'],
                      'p':[anova['brown_forsythe']['p'], anova['normalidad_residuos']['p'], anova['kruskal_sensibilidad']['p']]}))
ejemplo = pares[pares.barrio_a.eq('Almagro') & pares.barrio_b.eq('Caballito')]
display(ejemplo.round(5))
nota(f"Welch: F={anova['welch']['F']:.2f}, p={anova['welch']['p']:.3g}. "
     f"Pares con p de Holm < 0,05: {anova['pares_significativos_holm']} de {anova['pares']}. "
     'No rechazo en un par no demuestra equivalencia; el tamaño de efecto no establece causalidad.')
for nombre,frame in [('anova_barrios',resumen_barrios),('anova_clasico',tabla_anova),('anova_pares_holm',pares)]:
    frame.to_csv(SALIDA/(nombre+'.csv'),index=False)
(SALIDA/'anova_resultados.json').write_text(json.dumps(anova,ensure_ascii=False,indent=2),encoding='utf-8')
fig,ax=plt.subplots(figsize=(10,5),constrained_layout=True)
vista=resumen_barrios.sort_values('media').iloc[np.r_[0:8,-8:0]]
ax.errorbar(vista.media,np.arange(len(vista)),xerr=vista.desvio,fmt='o',color=PURPLE,ecolor='#bec8d0',capsize=3)
ax.set_yticks(np.arange(len(vista)),vista.neighborhood)
ax.set(xlabel='Media ± 1 desvío de precios por grupo (USD/m²)',title='Extremos de medias barriales · barras descriptivas, no intervalos de confianza')
figura(fig,'05_anova_medias')
""", 'anova-calculo')

md('## 7 · Cinco modelos, una comparación\n\n' + theory('## 2. Variables, preprocesamiento y escala del objetivo','## 3. Los cinco modelos y sus decisiones de ajuste'), 'preprocesamiento-teoria')

code(r"""
familias = list(bm.model_specs(False))
assert familias == ['Ridge','KNN','Random Forest','HistGradientBoosting','MLP']
configuraciones = []
for ampliado in [False,True]:
    for nombre,(modelo,grilla) in bm.model_specs(ampliado).items():
        configuraciones.append({'modelo':nombre,'escenario':'edificio' if ampliado else 'base',
                                'busqueda':json.dumps(grilla,ensure_ascii=False)})
display(pd.DataFrame(configuraciones))
nota('Dos escenarios comparan las mismas observaciones. No se atribuye la mejora a edad aisladamente: también cambia estado y el patrón de faltantes.')
""", 'cinco-configuraciones')

for number, (start,end) in enumerate([
    ('### 3.1 Ridge: una referencia lineal regularizada','### 3.2 KNN: una referencia local dependiente de la distancia'),
    ('### 3.2 KNN: una referencia local dependiente de la distancia','### 3.3 Random Forest: promedio de árboles aleatorizados'),
    ('### 3.3 Random Forest: promedio de árboles aleatorizados','### 3.4 HistGradientBoosting: correcciones sucesivas'),
    ('### 3.4 HistGradientBoosting: correcciones sucesivas','### 3.5 MLP: una composición no lineal regularizada'),
    ('### 3.5 MLP: una composición no lineal regularizada','## 4. Selección, evaluación y baselines'),
],1):
    md(start.replace('### 3.','### 7.') + '\n\n' + theory(start,end),f'modelo-teoria-{number}')

md('## 8 · Separar ajuste y evaluación\n\n' + theory('## 4. Selección, evaluación y baselines','## 5. Métricas e incertidumbre'), 'validacion-teoria')

code(r"""
particiones = verify_splits(data)
display(pd.DataFrame(particiones))
from sklearn.model_selection import GroupKFold
fold_por_fila=np.zeros(len(data),dtype=int)
for fold,(_,test_idx) in enumerate(GroupKFold(5).split(data,groups=data.grupo),1):
    fold_por_fila[test_idx]=fold
fig,ax=plt.subplots(figsize=(11,2.4),constrained_layout=True)
ax.imshow(np.array([np.where(fold_por_fila==i,1,0) for i in range(1,6)]),
          cmap='Purples',aspect='auto',interpolation='nearest',vmin=0,vmax=1)
ax.set_yticks(range(5),['Fold '+str(i) for i in range(1,6)])
ax.set(xlabel='Fila del catálogo (las copias detectadas comparten fold)',title='En violeta: evaluación externa; en claro: entrenamiento')
figura(fig,'06_particiones')
""", 'validacion')

md(r"""
### Ejecutar o recuperar la evidencia

Con `REENTRENAR=True` se repite la búsqueda anidada completa. Son cinco familias, dos escenarios, tres configuraciones, tres folds internos y cinco externos: **500 ajustes**, más cinco del HGB histórico. Se limita a un hilo dentro del benchmark y se informa el avance.

Con `False` se cargan predicciones externas ya calculadas, verificando bundle, código y predicciones contra su manifiesto. Las métricas y los diagnósticos se recalculan desde esas filas. Se muestran por separado las versiones de la evidencia histórica y las del entorno actual. Los tiempos del modo de lectura no son tiempos de entrenamiento.
""", 'benchmark-texto')

code(r"""
t_benchmark=time.perf_counter()
if REENTRENAR:
    resumen, manifiesto = ejecutar_auditoria(BUNDLE, OOF_PATH.parent, EVIDENCIA)
    origen_resultados='REENTRENADO EN ESTA EJECUCIÓN'
else:
    manifiesto=json.loads((EVIDENCIA/'manifiesto.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(BUNDLE.read_bytes()).hexdigest()==manifiesto['datos']['sha256_bundle']
    assert hashlib.sha256(OOF_PATH.read_bytes()).hexdigest()==manifiesto['predicciones_oof_sha256']
    for nombre,digest in manifiesto['codigo_sha256'].items():
        assert hashlib.sha256((TRABAJO/'precio_entorno'/nombre).read_bytes()).hexdigest()==digest
    origen_resultados='EVIDENCIA HISTÓRICA AUDITADA · NO REENTRENADA EN ESTA CELDA'

oof=pd.read_csv(OOF_PATH)
fits=pd.read_csv(EVIDENCIA/'ajustes.csv')
assert not oof.duplicated(['model','scope','row']).any()
assert oof.groupby(['model','scope']).row.nunique().eq(len(data)).all()
assert oof.groupby('grupo').fold.nunique().eq(1).all()
assert np.isfinite(oof.estimate).all() and oof.estimate.gt(0).all()
resumen=summarize(oof,fits)
resumen.to_csv(SALIDA/'modelos_resumen.csv',index=False)
fits.to_csv(SALIDA/'modelos_ajustes.csv',index=False)
print(origen_resultados)
print('Fecha de evidencia:',manifiesto['fecha_utc'])
print('Versiones de evidencia:',manifiesto['versiones'])
print('Segundos de esta celda:',round(time.perf_counter()-t_benchmark,1))
print('Segundos de la corrida de evidencia:',round(manifiesto['segundos_totales'],1))
""", 'benchmark')

md('## 9 · Evaluar en unidades útiles\n\n' + theory('## 5. Métricas e incertidumbre','### Resultados reproducidos y lectura de los errores'), 'metricas-teoria')

code(r"""
columnas=['model','scope','mae','rmse','r2','mdape_pct','mae_propiedad_igual_peso',
          'mae_train_media_folds','brecha_mae','mae_fold_sd']
display(resumen[columnas].round(3))
mejores=resumen[resumen.model.isin(familias)].sort_values('mae')
ganador=mejores.iloc[0]
ref=resumen[resumen.model.eq('Mediana comparables')].iloc[0]
kpis({'Mejor observado':ganador['model'], 'Escenario':ganador['scope'],
      'MAE externo':f"{ganador['mae']:.1f} USD/m²",'Mejora vs comparables':f"{100*(1-ganador['mae']/ref['mae']):.1f} %"})

fig,axes=plt.subplots(1,2,figsize=(13,5),gridspec_kw={'width_ratios':[1.1,1]},constrained_layout=True)
vista=resumen[(resumen.model.isin(familias)&resumen.scope.eq('edificio'))|resumen.scope.eq('referencia')].sort_values('mae',ascending=False)
axes[0].barh(vista.model,vista.mae,color=[GRAY if s=='referencia' else PURPLE for s in vista.scope])
axes[0].set(xlabel='MAE externo (USD/m²)',title='Cinco modelos con edificio y referencias')
for i,v in enumerate(vista.mae): axes[0].text(v+5,i,f'{v:.1f}',va='center',fontsize=9)
axes[0].set_xlim(0,vista.mae.max()*1.15)
ampliados=resumen[resumen.model.isin(familias)&resumen.scope.eq('edificio')].sort_values('delta_mae_vs_comparables')
delta=ampliados.delta_mae_vs_comparables.to_numpy()
axes[1].errorbar(delta,np.arange(len(delta)),xerr=np.vstack([delta-ampliados.delta_ic95_low,ampliados.delta_ic95_high-delta]),
                 fmt='o',color=BLUE,capsize=4)
axes[1].axvline(0,color=ORANGE,ls='--')
axes[1].set_yticks(np.arange(len(delta)),ampliados.model)
axes[1].set(xlabel='Diferencia de MAE vs comparables (USD/m²)',title='Intervalos bootstrap condicionales al 95 %')
figura(fig,'07_comparacion')
nota('Negativo favorece al modelo. Los intervalos mantienen fijas las predicciones OOF y no corrigen selección de familia ni todas las comparaciones a la vez.')
""", 'comparacion')

code(r"""
elegido=oof[oof.model.eq(ganador['model'])&oof.scope.eq(ganador['scope'])].copy()
fig,axes=plt.subplots(1,2,figsize=(12,4.8),constrained_layout=True)
axes[0].scatter(elegido.precio_m2,elegido.estimate,s=8,alpha=.15,color=BLUE)
lim=[min(elegido.precio_m2.min(),elegido.estimate.min()),max(elegido.precio_m2.max(),elegido.estimate.max())]
axes[0].plot(lim,lim,color=ORANGE,ls='--')
axes[0].set(xscale='log',yscale='log',xlabel='Publicado (USD/m²; eje log)',ylabel='Predicho (USD/m²; eje log)',title='Predicción externa · todas las filas')
axes[1].scatter(elegido.estimate,elegido.error,s=8,alpha=.15,color=BLUE)
axes[1].axhline(0,color=ORANGE,ls='--')
axes[1].set(xscale='log',xlabel='Predicción externa (USD/m²; eje log)',ylabel='Predicho − publicado (USD/m²)',title='Residuos externos · sin recortar extremos')
figura(fig,'08_residuos')
print('Sesgo medio (predicho − publicado):',round(elegido.error.mean(),2),'USD/m²')
print('MAE por aviso:',round(elegido.error.abs().mean(),2))
print('MAE con igual peso por propiedad:',round(elegido.groupby('grupo').error.apply(lambda x:x.abs().mean()).mean(),2))
""", 'residuos')

md(r"""
### ¿A quién le funciona peor?

Una media agregada puede ocultar fuentes o barrios con errores altos. Leemos cada error junto con su tamaño muestral. El conjunto externo fue usado para examinar estos subgrupos: elegir modificaciones después de verlos requiere otra prueba independiente.
""", 'subgrupos-texto')

code(r"""
por_fuente=pd.DataFrame([{'modelo':m,'escenario':s,'fuente':a,**bm.scores(b).to_dict()}
                        for (m,s,a),b in oof.groupby(['model','scope','agency'])])
por_barrio=pd.DataFrame([{'barrio':b,**bm.scores(g).to_dict()} for b,g in elegido.groupby('neighborhood')]).sort_values('mae',ascending=False)
display(por_fuente[por_fuente.modelo.eq(ganador['model'])].round(2))
display(por_barrio.round(2))
por_fuente.to_csv(SALIDA/'errores_por_fuente.csv',index=False)
por_barrio.to_csv(SALIDA/'errores_por_barrio.csv',index=False)
mlp=fits[fits.model.eq('MLP')]
display(mlp[['scope','fold','n_iter','max_iter','limite_iteraciones_alcanzado','avisos_convergencia_busqueda']])
nota('El criterio de parada de MLP es numérico. Terminar antes del límite no demuestra óptimo global. El estado solo está informado en parte del catálogo y la antigüedad depende de la fuente.')
""", 'subgrupos')

md(r"""
## 10 · Interpretar el modelo sin atribuir causalidad

El siguiente diagnóstico conserva un fold externo y reajusta solo en sus grupos de entrenamiento, con la configuración que ese fold eligió. La importancia por permutación mide cuánto aumenta su MAE cuando desordenamos una entrada externa. Variables correlacionadas pueden compartir o desplazar importancia; una importancia negativa es posible por variabilidad de la prueba.

La dependencia parcial varía superficie manteniendo otras entradas observadas. Puede formar combinaciones físicamente poco habituales, especialmente cubierta y superficie total. Se muestran su media y dispersión descriptiva, sin convertirlas en un efecto causal.
""", 'interpretacion-texto')

code(r"""
from sklearn.base import clone
from sklearn.inspection import permutation_importance
familia=ganador['model']; escenario=ganador['scope']; ampliado=escenario=='edificio'
columnas_modelo=bm.NUMERIC+bm.CATEGORICAL+(bm.EXTRA if ampliado else [])
train_idx,test_idx=next(GroupKFold(5).split(data,groups=data.grupo))
registro=fits[fits.model.eq(familia)&fits.scope.eq(escenario)&fits.fold.eq(1)].iloc[0]
import ast
params=ast.literal_eval(registro['params'])
modelo_fold=clone(bm.model_specs(ampliado)[familia][0]).set_params(**params)
with threadpool_limits(limits=1):
    modelo_fold.fit(data.iloc[train_idx][columnas_modelo],np.log(data.iloc[train_idx].precio_m2))
    importancia=permutation_importance(modelo_fold,data.iloc[test_idx][columnas_modelo],np.log(data.iloc[test_idx].precio_m2),
        scoring=bm.usd_mae,n_repeats=3,random_state=42,n_jobs=1)
importancias=pd.DataFrame({'variable':columnas_modelo,'aumento_mae':importancia.importances_mean,
                          'desvio_permutaciones':importancia.importances_std}).sort_values('aumento_mae')
importancias.to_csv(SALIDA/'importancia_fold1.csv',index=False)
fig,axes=plt.subplots(1,2,figsize=(13,5),constrained_layout=True)
etiquetas=diccionario.set_index('variable').definicion.to_dict()
axes[0].barh(importancias.variable.map(etiquetas),importancias.aumento_mae,color=PURPLE)
axes[0].set(xlabel='Aumento de MAE al permutar (USD/m²)',title='Importancia · fold externo 1')
muestra=data.iloc[test_idx][columnas_modelo].sample(n=min(120,len(test_idx)),random_state=42)
areas=data.iloc[train_idx].covered_area.quantile(np.linspace(.1,.9,9)).to_numpy()
pdp=[]
for area in areas:
    valores=np.exp(modelo_fold.predict(muestra.assign(covered_area=area)))
    pdp.append({'area':area,'media':valores.mean(),'p10':np.quantile(valores,.1),'p90':np.quantile(valores,.9)})
pdp=pd.DataFrame(pdp)
axes[1].plot(pdp.area,pdp.media,color=BLUE)
axes[1].fill_between(pdp.area,pdp.p10,pdp.p90,color=BLUE,alpha=.15,label='Percentiles 10–90 de predicciones individuales')
axes[1].set(xlabel='Superficie cubierta variada (m²)',ylabel='Predicción (USD/m²)',title='Dependencia parcial descriptiva · fold 1')
axes[1].legend(fontsize=8)
figura(fig,'09_interpretacion')
""", 'interpretacion')

md(r"""
## 11 · Del modelo a una búsqueda

El explorador filtra la captura histórica por barrio, ambientes y presupuesto. Muestra las predicciones **externas OOF**, no las del modelo final entrenado con todo el catálogo. Una brecha negativa significa publicado por debajo de la referencia calculada, sin acreditar una ganga.

El ranking ordena revisión, sin excluir automáticamente avisos compatibles. El precio publicado participa en su definición; para evaluar utilidad se necesita revisión de la inmobiliaria, vigencia de enlaces y una captura posterior.
""", 'explorador-texto')

code(r"""
explorador=data[['id','neighborhood','rooms','price','covered_area','precio_m2']].join(
    elegido.set_index('row')[['estimate','gap','review','supported']])

def explorar(barrio='Caballito',ambientes=2,presupuesto=150000):
    vista=explorador[explorador.neighborhood.eq(barrio)&explorador.rooms.eq(ambientes)&explorador.price.le(presupuesto)]
    kpis({'Barrio':barrio,'Avisos compatibles':len(vista),'Presupuesto (USD)':f'{presupuesto:,.0f}'})
    tabla=vista.sort_values('gap').head(15).rename(columns={
        'neighborhood':'Barrio','rooms':'Ambientes','price':'Publicado USD','covered_area':'Cubierta m²',
        'precio_m2':'Publicado USD/m²','estimate':'Referencia externa USD/m²','gap':'Brecha relativa',
        'review':'Señal de revisión','supported':'Comparables suficientes'})
    display(tabla.drop(columns='id').round(2))
    return vista

vista_inicial=explorar()
try:
    import ipywidgets as widgets
    control_barrio=widgets.Dropdown(options=sorted(data.neighborhood.unique()),value='Caballito',description='Barrio')
    control_amb=widgets.IntSlider(min=1,max=5,value=2,description='Ambientes')
    control_pres=widgets.IntSlider(min=50000,max=600000,step=10000,value=150000,description='USD máximo')
    panel=widgets.Output()
    def refrescar(change=None):
        with panel:
            panel.clear_output(wait=True)
            explorar(control_barrio.value,control_amb.value,control_pres.value)
    for control in [control_barrio,control_amb,control_pres]: control.observe(refrescar,names='value')
    display(widgets.VBox([widgets.HBox([control_barrio,control_amb]),control_pres,panel]))
except ImportError:
    print('Para explorar sin widgets: explorar(barrio="Almagro", ambientes=2, presupuesto=150000)')
""", 'explorador')

md(r"""
## 12 · Un modelo exportable con su transformación completa

La evaluación terminó antes de este paso. Seleccionamos la familia/escenario mejor observado y volvemos a elegir sus hiperparámetros con tres folds agrupados sobre todo el corte; después se reajusta el ganador con todos los datos. Este artefacto sirve para operar, **no genera una nueva estimación independiente de desempeño**.

La transformación `log → modelo → exp` queda guardada en `TransformedTargetRegressor`; el objeto predice directamente en USD/m². Los archivos incluyen versiones, columnas y hash. El artefacto que genera este Colab corresponde al benchmark; el prototipo local previo de Streamlit usaba otra especificación y debe migrarse explícitamente antes de atribuirle estos resultados.
""", 'modelo-final-texto')

code(r"""
from sklearn.compose import TransformedTargetRegressor
from sklearn.model_selection import GridSearchCV
estimador,grilla=bm.model_specs(ampliado)[familia]
modelo_usd=TransformedTargetRegressor(regressor=estimador,func=np.log,inverse_func=np.exp)
grilla_usd={'regressor__'+k:v for k,v in grilla.items()}
cv_final=list(GroupKFold(3).split(data,groups=data.grupo))
t_refit=time.perf_counter()
with warnings.catch_warnings(record=True) as avisos_finales, threadpool_limits(limits=1):
    warnings.simplefilter('always')
    busqueda_final=GridSearchCV(modelo_usd,grilla_usd,cv=cv_final,scoring='neg_mean_absolute_error',n_jobs=1,error_score='raise')
    busqueda_final.fit(data[columnas_modelo],data.precio_m2)
modelo_final=busqueda_final.best_estimator_
segundos_refit=time.perf_counter()-t_refit
ruta_modelo=SALIDA/'modelo_publicacion.joblib'
joblib.dump(modelo_final,ruta_modelo)
metadata_modelo={'familia':familia,'escenario':escenario,'columnas':columnas_modelo,
    'parametros_finales':busqueda_final.best_params_,'versiones':versiones,
    'fecha_utc':datetime.now(timezone.utc).isoformat(),
    'sha256':hashlib.sha256(ruta_modelo.read_bytes()).hexdigest(),
    'sha256_datos':hashlib.sha256(BUNDLE.read_bytes()).hexdigest(),
    'nota':'Reajustado con todo el corte. La métrica de búsqueda final no es evaluación externa.'}
(SALIDA/'modelo_metadata.json').write_text(json.dumps(metadata_modelo,ensure_ascii=False,indent=2),encoding='utf-8')
modelo_recargado=joblib.load(ruta_modelo)  # Archivo propio recién generado.
np.testing.assert_allclose(modelo_final.predict(data.iloc[:3][columnas_modelo]),
                           modelo_recargado.predict(data.iloc[:3][columnas_modelo]))
print('Modelo persistido y recargado:',familia,escenario)
print('Parámetros:',busqueda_final.best_params_,'· Reajuste:',round(segundos_refit,1),'s')
print('Advertencias del reajuste final:',len(avisos_finales))
""", 'modelo-final')

md(r"""
### Avisos nuevos: un contrato explícito

El lote debe declarar venta, USD, ID, barrio, ambientes y superficie cubierta. Las variables opcionales ausentes se contabilizan y conservan como faltantes. No se atribuye a un lote incompleto el error de evaluación con enriquecimiento completo.

La comprobación automática usa tres filas históricas conocidas **solo para probar el funcionamiento**. No representan una captura nueva ni una prueba de generalización. Para una captura posterior, usar `predecir_lote(pd.read_csv('avisos_nuevos.csv'))` con este contrato y conservar el resultado aparte.
""", 'inferencia-texto')

code(r"""
ESTADOS=['a estrenar','en construcción','excelente','muy bueno','bueno','regular','reciclado','a reciclar']
def predecir_lote(lote):
    requeridas={'id','neighborhood','covered_area','rooms','currency','operation'}
    if lote.empty or not requeridas.issubset(lote):
        raise ValueError('Faltan columnas obligatorias o el lote está vacío: '+str(sorted(requeridas-set(lote))))
    if not lote.currency.eq('USD').all() or not lote.operation.eq('venta').all():
        raise ValueError('El modelo admite únicamente venta en USD.')
    if lote[['id','neighborhood']].isna().any().any() or lote.id.duplicated().any():
        raise ValueError('ID y barrio obligatorios; ID sin duplicados.')
    x=lote.copy()
    for col in ['covered_area','rooms']:
        x[col]=pd.to_numeric(x[col],errors='coerce')
        if not (np.isfinite(x[col])&x[col].gt(0)).all(): raise ValueError('Entrada inválida: '+col)
    if 'cond_code' not in x and 'condition' in x:
        x['cond_code']=x.condition.map(dict(zip(ESTADOS,range(len(ESTADOS)))))
    x=x.reindex(columns=columnas_modelo)
    for col in bm.NUMERIC+(['age_years'] if ampliado else []):
        x[col]=pd.to_numeric(x[col],errors='coerce')
        if np.isinf(x[col]).any(): raise ValueError('Infinitos en '+col)
    for col in bm.CATEGORICAL: x[col]=x[col].fillna('sin_dato').astype(str)
    resultado=lote[['id','neighborhood']].copy()
    resultado['referencia_publicacion_usd_m2']=modelo_recargado.predict(x)
    resultado['referencia_publicacion_usd']=resultado.referencia_publicacion_usd_m2*pd.to_numeric(lote.covered_area)
    resultado['variables_faltantes']=x.isna().sum(axis=1)
    resultado['barrio_no_visto']=~lote.neighborhood.isin(data.neighborhood)
    resultado['fecha_utc']=datetime.now(timezone.utc).isoformat()
    return resultado

prueba_tecnica=data.head(3).assign(operation='venta')
resultado_tecnico=predecir_lote(prueba_tecnica)
display(resultado_tecnico.drop(columns='id').round(2))
try:
    predecir_lote(prueba_tecnica.assign(currency='ARS'))
    raise AssertionError('Debería rechazar la moneda.')
except ValueError:
    print('Verificación: moneda incompatible rechazada.')

# Prueba adicional, sobre el mismo fold externo: disponibilidad de campos básicos.
basicos=bm.NUMERIC[:5]+bm.CATEGORICAL
x_basico=data.iloc[test_idx][columnas_modelo].copy()
for col in columnas_modelo:
    if col not in basicos: x_basico[col]=np.nan
pred_basico=np.exp(modelo_fold.predict(x_basico))
pred_completo=np.exp(modelo_fold.predict(data.iloc[test_idx][columnas_modelo]))
print('MAE completo, fold 1:',round(np.abs(pred_completo-data.iloc[test_idx].precio_m2).mean(),1),'USD/m²')
print('MAE con campos básicos, fold 1:',round(np.abs(pred_basico-data.iloc[test_idx].precio_m2).mean(),1),'USD/m²')
nota('Esta sensibilidad usa un solo fold externo del benchmark. No equivale a la prueba 80/20 del prototipo operativo ni garantiza el desempeño de un lote futuro.')
""", 'inferencia')

md(r"""
## 13 · Métrica de negocio y costos: distinguir supuestos de observaciones

El cliente necesita ahorrar tiempo sin perder candidatos relevantes. La métrica propuesta es

$$\Delta t=t_{\mathrm{habitual}}-t_{\mathrm{app}},\qquad
B=R\,\overline{\Delta t}\,c_h/60.$$

$R$ son revisiones mensuales, $c_h$ el costo del tiempo en USD/h y $B$ el ahorro imputado. El tiempo incluye comprobar referencias y descartar errores. La concordancia top-20 con comparables es un proxy, no un ahorro medido ni una tasa de ventas.

Los siguientes parámetros son **supuestos editables**. ETL+EDA usa el consumo histórico documentado del 14/11 (USD 0,0033 por corrida), sin nueva extracción. La inferencia cloud todavía no tiene un costo observado. El entrenamiento del cuaderno no llama a APIs pagas; equipo, energía, impuestos y comisiones requieren medición aparte.
""", 'negocio-texto')

code(r"""
REVISIONES_MES = 40  #@param {type:"integer"}
MINUTOS_AHORRADOS = 10  #@param {type:"number"}
COSTO_HORA_USD = 12  #@param {type:"number"}
CUOTA_USD = 39  #@param {type:"number"}
CORRIDAS_MES = 12  #@param {type:"integer"}
MINUTOS_SOPORTE = 40  #@param {type:"number"}
MINUTOS_MANTENIMIENTO = 30  #@param {type:"number"}
RESERVA_INFRA_USD = 0  #@param {type:"number"}
CAPTURA_NUEVA_USD = 0  #@param {type:"number"}

beneficio=REVISIONES_MES*MINUTOS_AHORRADOS*COSTO_HORA_USD/60
costo_humano=(MINUTOS_SOPORTE+MINUTOS_MANTENIMIENTO)*COSTO_HORA_USD/60
costo_analytics=CORRIDAS_MES*.0033
costo_estimado=costo_humano+costo_analytics+RESERVA_INFRA_USD+CAPTURA_NUEVA_USD
negocio=pd.DataFrame([
    ['Ahorro imputado del cliente',beneficio,'Supuesto; pendiente de piloto'],
    ['Beneficio cliente después de cuota',beneficio-CUOTA_USD,'Escenario mensual'],
    ['Costo proveedor estimado',costo_estimado,'Excluye partidas no medidas'],
    ['Contribución proveedor',CUOTA_USD-costo_estimado,'Antes de impuestos/comisiones'],
    ['Créditos Make del Analytics existente',CORRIDAS_MES*7,'Estimación; no incluye alertas ni inferencia remota']
],columns=['concepto','valor','alcance'])
display(negocio.round(2))
negocio.to_csv(SALIDA/'escenario_negocio.csv',index=False)
print('Retorno cliente sobre cuota:',f'{(beneficio-CUOTA_USD)/CUOTA_USD:.1%}' if CUOTA_USD>0 else 'no definido')
print('Margen de contribución:',f'{(CUOTA_USD-costo_estimado)/CUOTA_USD:.1%}' if CUOTA_USD>0 else 'no definido')
nota('Ninguno de estos escenarios acredita ahorro real. Los topes de extracción del proyecto siguen vigentes: USD 25 totales y USD 5 por cuenta; esta ejecución no hace extracciones.')
""", 'negocio')

md(r"""
## 14 · Qué podemos defender y qué necesitamos medir

**Con evidencia en este corte:** cinco familias comparadas en las mismas particiones, preprocesamiento dentro de entrenamiento, referencias simples, errores externos, incertidumbre condicional, convergencia numérica y diferencias barriales exploratorias.

**Evidencia complementaria:** el Anexo A documenta la evaluación temporal del HGB operativo con capturas del 13 al 20/11/2026. Es otro artefacto y otro protocolo; no valida temporalmente al ganador de este benchmark.

**Pendiente de confirmación:** desempeño del ganador del benchmark en una captura futura; independencia por edificio o microzona; disponibilidad de atributos a la fecha real de predicción; utilidad de las alertas; ahorro del cliente; costo de inferencia desplegada en Apify; actualización remota de Make/Sheets/Looker.

El protocolo siguiente convierte esos pendientes en una prueba concreta. Los límites de aceptación se acuerdan antes de observar la nueva muestra; no se eligen retrospectivamente para aprobar el modelo.
""", 'cierre-texto')

code(r"""
protocolo=pd.DataFrame([
 ['Congelar','Familia, columnas, transformación, parámetros, fecha y hash','Antes de la captura futura'],
 ['Adquirir','Catálogo autorizado; separar conocidos de nuevos; guardar información disponible a su fecha','Sin extracción automática en este cuaderno'],
 ['Evaluar','MAE por aviso/grupo, RMSE, sesgo, cobertura y errores por fuente/barrio','Mismas filas y baselines'],
 ['Validar utilidad','Tiempo de revisión, candidatos relevantes, novedad y vigencia','5–10 búsquedas del cliente; alternar orden'],
 ['Decidir','Contrastar métricas contra tolerancias acordadas','No usar significación del ANOVA como criterio comercial']
],columns=['etapa','evidencia','regla'])
display(protocolo)
protocolo.to_csv(SALIDA/'protocolo_confirmacion.csv',index=False)
""", 'protocolo')

md(r"""
## 15 · Exportar una entrega trazable

Se exportan tablas, figuras, el modelo reajustado y un manifiesto de la ejecución. Las predicciones individuales OOF quedan incluidas en el ZIP de resultados para revisión privada; el notebook muestra principalmente agregados. Los archivos del entorno de Colab son temporales: descargar o guardar el ZIP antes de cerrar la sesión.

La próxima celda no publica el trabajo. Con `DESCARGAR_AL_FINAL=True` abre la descarga del archivo generado. Para guardar el notebook con sus salidas, usar **Archivo → Descargar → Descargar .ipynb**.
""", 'exportacion-texto')

code(r"""
elegido.to_csv(SALIDA/'predicciones_oof_ganador.csv',index=False)
ejecucion={'fecha_utc':datetime.now(timezone.utc).isoformat(),'origen_resultados':origen_resultados,
          'versiones_actuales':versiones,'versiones_evidencia':manifiesto['versiones'],
          'sha256_paquete':hashlib.sha256(PAQUETE.read_bytes()).hexdigest(),
          'sha256_bundle':hashlib.sha256(BUNDLE.read_bytes()).hexdigest(),
          'mejor_observado':{'modelo':familia,'escenario':escenario,'mae_oof':float(ganador['mae'])},
          'filas':len(data),'grupos':int(data.grupo.nunique()),'anova_welch':anova['welch'],
          'segundos_cuaderno':time.perf_counter()-INICIO_CUADERNO,'segundos_refit_final':segundos_refit,
          'validaciones':['IDs únicos','USD de venta','cociente precio/superficie','grupos separados',
                          'OOF únicas','hashes verificados','modelo recargado consistente','moneda incompatible rechazada'],
          'nota':'No se ejecutaron extracciones ni se validó generalización temporal o utilidad comercial.'}
ejecucion['archivos_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in SALIDA.iterdir() if p.is_file() and p.name!='ejecucion.json'}
(SALIDA/'ejecucion.json').write_text(json.dumps(ejecucion,ensure_ascii=False,indent=2),encoding='utf-8')
ZIP_SALIDA=TRABAJO/'salidas_capstone.zip'
with ZipFile(ZIP_SALIDA,'w',ZIP_DEFLATED) as z:
    for archivo in sorted(SALIDA.iterdir()):
        if archivo.is_file(): z.write(archivo,archivo.name)
display(pd.DataFrame([{'archivo':p.name,'KB':round(p.stat().st_size/1024,1)} for p in sorted(SALIDA.iterdir()) if p.is_file()]))
print('Resultados:',ZIP_SALIDA,'·',round(ZIP_SALIDA.stat().st_size/1e6,2),'MB')
if EN_COLAB and DESCARGAR_AL_FINAL:
    from google.colab import files
    files.download(str(ZIP_SALIDA))
""", 'exportacion')

# El anexo incorpora evidencia agregada ya ejecutada; no entrena ni extrae datos.
TEMPORAL_PATH = ROOT / 'reports/validacion_temporal.json'
temporal_bytes = TEMPORAL_PATH.read_bytes()
temporal = json.loads(temporal_bytes)

def temporal_number(value, decimals=1):
    return f'{value:,.{decimals}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

temporal_rows = []
for key, label in [('inmobiliarias_13a17', 'Inmobiliarias, 13–17/11 · 40 barrios'),
                   ('zonaprop_20261120', 'Zonaprop, 20/11 · Caballito y Almagro'),
                   (None, '**Total**')]:
    block = temporal['segmentos'][key] if key else temporal['todos']
    model, base = block['modelo'], block['linea_de_base']
    temporal_rows.append('| ' + ' | '.join([
        label, temporal_number(block['avisos'], 0), temporal_number(model['mae']),
        temporal_number(base['mae']), temporal_number(block['mejora_mae_pct']) + ' %',
        temporal_number(model['rmse']), temporal_number(model['r2'], 3),
        temporal_number(model['dentro_20_pct']) + ' %',
    ]) + ' |')

md("""
## Anexo A · Validación temporal del HGB operativo · 20/11/2026

### Pregunta y alcance

¿El modelo operativo conserva una ventaja sobre la mediana de comparables cuando se aplica a avisos de capturas posteriores a las del entrenamiento?

Este anexo presenta **resultados históricos ya ejecutados**, incorporados desde `reports/validacion_temporal.json`. Puede leerse sin ejecutar el cuaderno. Cambiar `REENTRENAR` no vuelve a ejecutar esta evaluación: esa opción controla únicamente el benchmark integral. No se realizaron nuevas extracciones para incorporar el anexo.

**Son dos experimentos diferentes.** El benchmark principal compara cinco familias sobre log(USD/m²), con validación anidada por grupos. Aquí se evalúa el HGB operativo, con pérdida absoluta sobre USD/m², 300 iteraciones y rasgos adicionales de edificio y descripción. Su versión es `VERSION_MODELO`. Los 402,6 USD/m² del ganador del benchmark no son su error histórico: el HGB operativo obtuvo 442,7 USD/m² en su propia prueba histórica y 528,7 en esta evaluación temporal. Tampoco es una comparación temporal de las cinco familias.

### Datos y procedimiento

- Entrenamiento: catálogo autorizado capturado del **7 al 9 de noviembre de 2026**.
- Evaluación: capturas de inmobiliarias autorizadas del **13 al 17 de noviembre**, y Zonaprop del **20 de noviembre**. Zonaprop comprende Caballito y Almagro, 2 ambientes y hasta USD 165.000; no representa todo CABA.
- Se aplicó el modelo guardado sin reentrenarlo ni ajustar sus parámetros con la muestra evaluada. Se conservaron el pipeline de variables y las capas de puntos de interés del entrenamiento.
- De 2.049 avisos válidos se excluyeron 147 por ID conocido y 139 por posible coincidencia con un inmueble del entrenamiento. Quedaron **1.763 avisos**. La regla aproximada usa barrio, ambientes, superficie y precio redondeados; no garantiza independencia por edificio ni detecta todos los duplicados.
- La referencia es la mediana de USD/m² de entrenamiento por barrio y ambientes, con respaldo barrial y global cuando faltan comparables. No usa precios de la muestra nueva para ajustar la referencia.

La fecha de entrenamiento registrada es `FECHA_MODELO`: parte de las capturas evaluadas es anterior al ajuste final, aunque posterior a la captura de entrenamiento. Es una evaluación retrospectiva entre capturas, no una prueba prospectiva completa con atributos congelados antes de publicar los nuevos avisos. La disponibilidad de los atributos a cada fecha sigue requiriendo control.

### Resultados observados

MAE y RMSE están expresados en USD por m² cubierto. La última columna mide la proporción con error absoluto relativo al precio publicado no mayor al 20 %; no es recall ni precisión de clasificación.

| Muestra | Avisos | MAE HGB | MAE comparables | Reducción del MAE | RMSE HGB | R² HGB | Dentro de ±20 % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
TABLA_TEMPORAL

### Interpretación y límites

- **El HGB operativo reduce el MAE un 9 %** frente a los comparables en esta muestra: 528,7 frente a 581,0 USD/m². Esto evalúa referencias de precios publicados; no acredita oportunidades reales ni ahorro de tiempo.
- La ventaja es menor que en su propia prueba histórica (29,4 %), y el MAE pasa de 442,7 a 528,7 USD/m². Cambian simultáneamente las fechas, la composición y la disponibilidad de atributos; no puede atribuirse toda la diferencia al paso del tiempo.
- La mediana de variables numéricas faltantes es **11 por aviso** en ambos segmentos. No se debe atribuir el desempeño de los datos enriquecidos a lotes que no tienen esos campos.
- La mediana de predicción menos precio publicado es **−122 USD/m²**; el modelo subestima el 56,7 % de los avisos. El R² total es 0,192 y depende de la dispersión y composición de esta muestra; no es directamente comparable con el R² del benchmark.
- El intervalo bootstrap del 95 % para la reducción absoluta de MAE es **[37,0; 67,7] USD/m²**, con 2.000 remuestreos por aviso sobre predicciones fijas. No incorpora reentrenamiento, selección de modelos ni dependencia entre avisos de un mismo edificio, y no es un intervalo de precio individual.
- Los siguientes pasos son evaluar también al ganador del benchmark con otra captura reservada, controlar atributos disponibles a su fecha y medir utilidad con la inmobiliaria. Estos resultados no permiten afirmar cuál de las cinco familias generaliza mejor temporalmente.

### Procedencia y reproducción

Evidencia agregada: `reports/validacion_temporal.json`. Implementación: `precio_entorno/validacion_temporal.py`. Interpretación ampliada: sección «Validación temporal · 20/11/2026» de `docs/entrega-inferencia.md`.

SHA-256 del reporte incorporado: `HASH_TEMPORAL`.

El anexo es autocontenido. Para recalcular la evaluación original se necesitan el repositorio local, el artefacto operativo correspondiente y las capturas autorizadas; no basta con el bundle del benchmark. Desde la raíz del proyecto, con esos insumos disponibles:

```powershell
python -m precio_entorno.validacion_temporal
```

El comando usa archivos locales y no inicia una extracción. Las predicciones individuales permanecen fuera de Git. Todos los importes corresponden a precios de publicación, no tasaciones ni precios de cierre.
""".replace('VERSION_MODELO', temporal['modelo_version'])
   .replace('FECHA_MODELO', temporal['entrenado_utc'])
   .replace('TABLA_TEMPORAL', '\n'.join(temporal_rows))
   .replace('HASH_TEMPORAL', hashlib.sha256(temporal_bytes).hexdigest()), 'anexo-validacion-temporal')


md(r"""
## Referencias y guía de lectura

- **Formulación y configuración efectiva:** [Ridge](https://scikit-learn.org/1.7/modules/linear_model.html#ridge-regression-and-classification), [KNN](https://scikit-learn.org/1.7/modules/neighbors.html#nearest-neighbors-regression), [Random Forest](https://scikit-learn.org/1.7/modules/generated/sklearn.ensemble.RandomForestRegressor.html), [HistGradientBoosting](https://scikit-learn.org/1.7/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html) y [MLP](https://scikit-learn.org/1.7/modules/generated/sklearn.neural_network.MLPRegressor.html).
- **Diseño de evaluación:** [validación anidada](https://scikit-learn.org/1.7/auto_examples/model_selection/plot_nested_cross_validation_iris.html) y [dependencia al comparar modelos](https://scikit-learn.org/1.7/auto_examples/model_selection/plot_grid_search_stats.html).
- **ANOVA clásico y Welch:** [SciPy 1.16](https://docs.scipy.org/doc/scipy-1.16.0/reference/generated/scipy.stats.f_oneway.html).
- **Artículo primario:** Breiman (2001), *Random Forests*, Machine Learning 45, 5–32. [Texto](https://www.ams.jhu.edu/~priebe/COURSES/FALL2003/550.730/RF/breiman-rf.pdf).
- **Lectura académica complementaria:** James, Witten, Hastie, Tibshirani y Taylor (2023), *An Introduction to Statistical Learning: with Applications in Python*. [Ficha editorial](https://link.springer.com/book/10.1007/978-3-031-38747-0) y [sitio de autores](https://www.statlearning.com/home). Se verificaron ficha e índice; no se declara revisión exhaustiva de todos sus capítulos.
- **Fuentes de contexto:** [Mapa del Delito de CABA](https://data.buenosaires.gob.ar/dataset/delitos), datos abiertos de Buenos Aires y OpenStreetMap, según la trazabilidad incluida en el paquete.
- **Uso de Colab:** [FAQ y límites de recursos](https://research.google.com/colaboratory/faq.html) y [carga/descarga de archivos](https://colab.research.google.com/notebooks/io.ipynb).

**Para la defensa:** presentar primero la decisión del cliente, después la evidencia comparativa y finalmente sus límites. Reservar las derivaciones para explicar por qué las métricas y los algoritmos responden a esa pregunta. Un resultado significativo o un modelo sofisticado no sustituyen una muestra futura ni la validación del usuario.
""", 'referencias')


def build():
    notebook = nbf.v4.new_notebook(cells=cells, metadata={
        'kernelspec': {'display_name':'Python 3','language':'python','name':'python3'},
        'language_info': {'name':'python','version':'3.13.7'},
        'colab': {'name':'Precio_y_Entorno_CABA_Capstone_Integral.ipynb','toc_visible':True},
    })
    nbf.validate(notebook)
    destination = ROOT/'notebooks/capstone_integral_colab.ipynb'
    nbf.write(notebook,destination)
    print(f'{destination}\n{len(cells)} celdas · {sum(c.cell_type=="code" for c in cells)} de código')
    return destination


if __name__=='__main__':
    build()
