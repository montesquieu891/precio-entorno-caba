# Manual de operación

Comandos y procedimientos para capturar, importar, actualizar y publicar los datos de Precio y Entorno CABA. La descripción general del proyecto está en el [README](../README.md); el contrato de cada fuente, en [datos.md](datos.md); la arquitectura, en [arquitectura.md](arquitectura.md).

Todas las capturas requieren una fuente con acceso autorizado. Ante un bloqueo (HTTP 403, desafío o 429), la captura se detiene: no se esquiva. Las extracciones pagas respetan un tope de USD 5 por cuenta de Apify y USD 25 en total.

## 1. Importar archivos autorizados

La app de Streamlit (`python -m streamlit run app.py`) importa catálogos y prueba la actualización.

1. Abrí **Datos reales**. Usa `data/local/real.sqlite3` (venta) o `data/local/real-alquiler.sqlite3` (alquiler). La demo usa `data/local/demo.sqlite3`, con sus propias búsquedas y alertas.
2. En **Importá datos locales**, indicá el nombre de un único catálogo autorizado, seleccioná el CSV o JSON y confirmá el acceso. Revisá las filas incorporadas, duplicadas y descartadas, y los faltantes e inválidos por campo.
3. Guardá una búsqueda e importá un lote posterior del mismo catálogo. Cada ID nuevo compatible genera una alerta por búsqueda. Reimportar un ID conserva la primera observación y la alerta existente. La importación no actualiza precios ni da de baja avisos ausentes.
4. Cargá el CSV oficial del [Mapa del Delito de CABA](https://data.buenosaires.gob.ar/dataset/delitos). Cada archivo válido reemplaza el contexto anterior y queda identificado por nombre y SHA-256. Un barrio y mes sin filas válidas figura sin cobertura observada, no en cero.

### Formato del catálogo

El CSV lleva encabezados y admite coma, punto y coma o tabulación. Para decimales, usá punto o coma sin separador de miles; en un CSV separado por comas, entrecomillá los decimales con coma. El JSON en UTF-8 admite una lista de objetos o un objeto con una lista `listings`.

| Campo requerido | Alias admitidos | Validación |
| --- | --- | --- |
| `listing_id` | `id` | Identificador estable dentro del catálogo |
| `url` | `enlace` | Enlace HTTP o HTTPS sin credenciales |
| `captured_at` | `fecha_captura` | Fecha o fecha y hora ISO 8601 |
| `price` | `precio` | Importe publicado entre USD 10.000 y 10.000.000 |
| `currency` | `moneda` | USD, U$S o US$ |
| `covered_area_m2` | `covered_area`, `superficie_cubierta` | Superficie cubierta entre 10 y 2.000 m² |
| `rooms` | `ambientes` | Entero entre 1 y 20 |
| `neighborhood` | `barrio` | Barrio de CABA |

- El precio por m² cubierto debe quedar entre USD 200 y 20.000. Un importe con separador de miles, como `105.000`, se lee como 105 y se descarta.
- Opcionales: `total_area_m2` (`superficie_total`, 10 a 10.000 m²), `latitude` (`latitud`, `lat`), `longitude` (`longitud`, `lon`) y `location_accuracy_m` (`precision_m`). Los campos del edificio y los rasgos de la descripción están en [datos.md](datos.md).
- Si el archivo trae `source` o `fuente`, debe coincidir con el catálogo indicado.
- Un pin es utilizable para el cruce con delitos si cae en CABA y el catálogo declara una precisión de hasta 100 m.
- El cargador de delitos admite `id-mapa`, `fecha`, `barrio`, `tipo_delito`, `franja_horaria` y `cantidad`, y las variantes `id_mapa`, `tipo`, `franja` y `cantidad_registrada`.

`data/fixtures/avisos_prueba.csv` y `data/fixtures/delitos_prueba.csv` son ficticios. Para probar el formulario con ellos, usá una copia de la carpeta del proyecto, así la base real queda reservada al catálogo autorizado.

## 2. Capturas

Cada captura escribe `avisos.json` y `registro.json` en una carpeta nueva de `data/raw/`. Las autorizaciones escritas se guardan fuera de Git.

### Inmobiliarias (RE/MAX, Century 21, Migliorisi) y Mob

```powershell
python -m precio_entorno.inmobiliarias --max-avisos 600 --autorizacion-confirmada
python -m precio_entorno.inmobiliarias --operacion alquiler --autorizacion-confirmada
python -m precio_entorno.inmobiliarias --sitios mob --operacion alquiler --max-avisos 1300 --autorizacion-confirmada
```

- **Acceso educado:** Scrapling sin cabeceras de sigilo, sin suplantar la huella del navegador y sin proxies. Se identifica como proyecto académico, respeta robots.txt, espera 3 segundos entre pedidos y se detiene ante un bloqueo.
- **Solo campos del contrato:** nunca copia datos de agentes ni de contacto. El ID lleva el prefijo de la fuente (`remax:…`).
- **Mob** solo publica alquileres. Su servidor entrega 20 avisos por listado, así que el adaptador recorre los listados del sitemap; una captura completa tarda unos 21 minutos.
- **RE/MAX:** desde el 17/11/2026 su API responde HTTP 403 a la máquina local. La captura sigue con las demás fuentes.

### Zonaprop con Apify

Zonaprop autorizó por escrito la consulta automatizada. Se usa el actor [igolaizola/zonaprop-scraper](https://apify.com/igolaizola/zonaprop-scraper). Sin `--ejecutar`, el comando solo muestra el plan y el costo estimado:

```powershell
python -m precio_entorno.zonaprop_apify --barrios Caballito Almagro --max-avisos 25
python -m precio_entorno.zonaprop_apify --barrios Caballito Almagro --max-avisos 25 --cuenta 1 --tope-usd 0.5 --ejecutar --autorizacion-confirmada
```

- **Costo:** USD 0,001 por aviso y por ficha. El comando verifica que la tarifa no haya subido y envía `maxTotalChargeUsd` en cada corrida.
- **Cuentas:** el `.env` admite varias líneas `APIFY_TOKEN`; cada corrida usa una sola, elegida con `--cuenta`.
- **Privacidad:** el actor devuelve nombre, correo y teléfono del anunciante. El adaptador nunca los escribe.
- **Barrios:** Zonaprop reconoce Montserrat, Núñez y Nueva Pompeya como «Monserrat», «Nuñez» y «Pompeya». Con `--barrios todos` ya se usan esos nombres.
- `--releer` vuelve a leer los resultados de corridas anteriores sin eventos del actor; ver [datos.md](datos.md#zonaprop-con-apify).

| Captura del 8/11/2026 | Leídos | Nuevos en la base | Barrios | Costo aproximado |
| --- | ---: | ---: | ---: | ---: |
| Piloto (Caballito y Almagro) | 50 | 49 | 2 | USD 0,05 |
| Venta | 2.359 | 2.223 | 48 | USD 4,75 |
| Alquiler | 2.142 | 2.042 | 48 | USD 3,90 |

### Puntos de interés

```powershell
python -m precio_entorno.osm_apify             # plan; agregá --ejecutar para correrlo
python -m precio_entorno.badata_poi            # parques, escuelas y hospitales de BA Data
```

La extracción de OpenStreetMap del 7/11/2026 costó USD 9,09 y está en `data/raw/osm-20261107/`.

### Pilotos anteriores

`python -m precio_entorno.run_pilot --dry-run` y `python -m precio_entorno.ecomscrape_export` corresponden a los primeros pilotos de Zonaprop, que recibieron HTTP 403 antes de la autorización. Se conservan para reproducir esos registros; el detalle está en [arquitectura.md](arquitectura.md#7-apify).

## 3. Capas del entorno

```powershell
python -m precio_entorno.entorno
```

Genera `data/processed/entorno/` a partir de `data/raw/badata-entorno/`, `data/raw/badata-poi/` y la captura de OpenStreetMap más reciente. Tarda alrededor de un minuto. Con `--sin-osm` se omite la gastronomía.

- **Garajes comerciales:** descargá el GeoJSON de [Buenos Aires Data](https://data.buenosaires.gob.ar/dataset/garajes-comerciales) en `data/raw/badata-entorno/garajes-comerciales.geojson`.
- **Colectivos:** GTFS en `data/raw/colectivos-gtfs-AAAAMMDD/colectivos-gtfs.zip`. El calendario del feed es de 2019 y el portal suspendió sus datasets GTFS y API.
- **Gimnasios:** `data/raw/osm-gimnasios-AAAAMMDD/gimnasios.json`.
- **Cocheras en alquiler mensual:** catálogo autorizado en `data/local/cocheras.json`; ver [cocheras.md](cocheras.md).

Buenos Aires Data rechaza clientes automáticos con una página de error que responde HTTP 200. Un código 200 no prueba que la descarga sea válida; los archivos del CDN sí se bajan directo.

## 4. Actualización automática

La tarea de Windows **PrecioEntornoCABA\Actualizar avisos** corre cada 2 días a las 9:00 con [scripts/actualizar.cmd](../scripts/actualizar.cmd), que llama a `python -m precio_entorno.actualizar` para venta y para alquiler.

- **Captura:** los 200 avisos más recientes de cada sitio.
- **Importación:** a las bases reales, donde se generan las alertas.
- **Historial:** una línea por corrida en `data/local/actualizaciones.jsonl`; la salida completa en `data/local/actualizar.log`.

```powershell
schtasks /Query /TN "PrecioEntornoCABA\Actualizar avisos"
schtasks /Change /TN "PrecioEntornoCABA\Actualizar avisos" /DISABLE
schtasks /Delete /TN "PrecioEntornoCABA\Actualizar avisos" /F
```

La tarea corre solo con la sesión de Windows iniciada. Si una fuente retira el permiso o bloquea, quitá su sitio con `--sitios` en `scripts/actualizar.cmd`.

## 5. Alertas por correo con Make y Apify

Desde el 9/11/2026, Make orquesta las alertas con dos escenarios activos (el plan Free admite dos):

- **«Precio y Entorno CABA - Búsquedas»:** recibe por webhook las altas y bajas de búsquedas desde la web (`MAKE_BUSQUEDAS_WEBHOOK_URL`). El correo de la persona queda solo en Google Sheets, no en la base local.
- **«Precio y Entorno CABA - Alertas con Apify»:** cada 2 días lee las búsquedas activas, corre el Actor `precio-entorno-alertas` y envía un correo por persona.

Los escenarios se crean con `python -m precio_entorno.make_escenarios crear` y están descritos en [arquitectura.md](arquitectura.md#81-actor-de-alertas). La conexión de Gmail vence el 6/5/2027.

**Webhook de resumen (heredado).** Si `MAKE_WEBHOOK_URL` está definido, `actualizar.py` envía el resumen de cada corrida (`ok`, `parcial` o `error`) con conteos y alertas, sin datos personales. El escenario que lo recibía está inactivo desde el 9/11/2026. Para probar cada ruta sin capturar:

```powershell
python -m precio_entorno.actualizar --probar-make alertas
python -m precio_entorno.actualizar --probar-make sin-novedades
python -m precio_entorno.actualizar --probar-make error
```

## 6. Pipeline Analytics

Make baja los avisos crudos de Google Drive, el Actor `precio-entorno-analytics` hace el ETL y el EDA, y las tablas resultantes alimentan el dashboard de Looker Studio. Recorrido, costos y guion de demo: [pipeline-analytics.md](pipeline-analytics.md).

```powershell
python -m precio_entorno.pipeline_analytics etl data/raw/venta-consolidada-20261108/avisos.json
python -m precio_entorno.pipeline_analytics eda data/processed/pipeline/dataset_limpio.csv
```

## 7. Radar de tendencias barriales

```powershell
python -m precio_entorno.radar
```

Cuenta notas de Clarín, LA NACION y TN por barrio en los siete días anteriores. La tarea **PrecioEntornoCABA\Radar de noticias** lo corre los lunes a las 9:00 con [scripts/radar.cmd](../scripts/radar.cmd). Es una capa editorial: no se mezcla con avisos, delitos ni datos ficticios, y no guarda el texto de las notas. Ver [radar.md](radar.md).

## 8. Publicación en Vercel

```powershell
python scripts/preparar_vercel.py --desplegar
```

Arma la carpeta desde `HEAD`, no desde el árbol de trabajo, y la publica en `https://precio-entorno-caba.vercel.app`. Mergear un PR no despliega. Desplegar desde una rama que no tenga lo que ya está en producción lo borra. Detalle en [despliegue-vercel.md](despliegue-vercel.md).

## 9. Funciones desactivadas

**Dónde comer (Google Places).** Está implementada (`precio_entorno/lugares.py`, `/api/barrios/{barrio}/lugares`) pero no se muestra: requiere `GOOGLE_MAPS_API_KEY` y una cuenta de Google Cloud con facturación, que el proyecto decidió no activar. La gastronomía de la ficha sale de OpenStreetMap. Si se habilitara, las reglas de uso están en [ui.md](ui.md#dónde-comer-google-places-en-vivo): consulta solo a pedido, sin guardar ni cachear calificaciones, con tope mensual (`PRECIO_ENTORNO_LUGARES_TOPE_MES`, 900 por defecto) contado en `data/local/lugares-consumo.sqlite3`.
