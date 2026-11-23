# Historial de captura de avisos

Registro de cómo se consiguieron los avisos: el plan del piloto, los actores de Apify probados, sus costos y los bloqueos. Se sacó del README el 23/11/2026 porque describe etapas ya cerradas. El estado vigente de las fuentes está en [datos.md](datos.md).

## Plan del piloto (anterior a la captura completa)

Confirmar el acceso a un único catálogo. La prioridad es Zonaprop con autorización, con la API oficial de Mercado Libre o un catálogo cedido por una inmobiliaria como alternativas. Después, probar hasta 50 avisos de Caballito y Almagro con tope de USD 5 en una sola cuenta, dentro del presupuesto total de USD 25. Medir cuántos avisos quedan aptos, los duplicados, la calidad de los pines y el costo por aviso usable. Cargar el CSV oficial y documentar su cobertura. Para el capstone, preparar entre 700 y 2.000 registros válidos y unas diez variables interpretables por dataset después de limpiar.

### Piloto Zonaprop con Apify

El piloto usa [Expandí tu Marca para Zonaprop](https://apify.com/expanditumarca/real-estate-lead-generator-market-analysis-zonaprop). Desde PowerShell, ejecutá el dry-run local sin token ni solicitudes a Apify.

```powershell
python -m precio_entorno.run_pilot --dry-run
```

El [archivo de preparación](apify-piloto-input.json) contiene dos búsquedas de departamentos en venta y la plantilla del detalle. El actor no admite filtrar por ambientes en la búsqueda. El piloto toma hasta 25 enlaces únicos por barrio y conserva los avisos de dos ambientes después de consultar el detalle con `scrape-single`. Puede quedar por debajo de 50 avisos aptos. Los proxies quedan desactivados y una corrida fallida detiene el proceso.

El presupuesto autorizado para el piloto es USD 5 en una sola cuenta. El dry-run permite reproducir esa configuración con `--budget-usd 5`. Para un actor en modalidad FREE, el cliente verifica que el tope mensual de Apify de la cuenta elegida sea igual o inferior al presupuesto. Los límites enviados por corrida y el costo informado se registran por separado.

La ejecución real requiere autorización de Zonaprop para consultar su catálogo con este actor y un token de Apify en el entorno (`APIFY_TOKEN`) o en `.env`. El `.env` puede tener varias cuentas, cada una con un tope de USD 5, en líneas `APIFY_TOKEN`, `APIFY_TOKEN_2`, etc., o como tokens sueltos. Cada corrida usa una sola cuenta. Si hay más de una, elegila con `--account`, según el orden del archivo. La suma de todas las cuentas no debe superar los USD 25. Los términos generales del portal restringen el uso de herramientas de búsqueda externas. El comando verifica el esquema, la tarifa y el límite aplicable antes de crear una corrida.

```powershell
python -m precio_entorno.run_pilot --execute --authorized-direct-access --budget-usd 5 --account 1 --output data/raw/piloto-zonaprop-cuenta1
```

Usá una carpeta `--output` nueva en cada corrida. La de la primera prueba, `data/raw/piloto-zonaprop/`, conserva el registro de los HTTP 403.

La ejecución escribe en `data/raw/piloto-zonaprop/` los resultados crudos limitados a campos inmobiliarios, el JSON adaptado, el resumen de calidad y un registro con IDs, estados y costos informados. Si la carpeta ya existe, se detiene para evitar una segunda corrida accidental. Ante una interrupción, usá `corridas.json` y Apify Console para recuperar el dataset existente.

Cargá `avisos.json` desde **Datos reales** con el catálogo `zonaprop`. Se conservan precio, moneda y coordenadas cuando están disponibles. El cruce se hace por barrio y los pines sin precisión declarada quedan como aproximados. También podés cargar el CSV o JSON de un catálogo autorizado desde el mismo formulario.

### Zonaprop con el actor de igolaizola

Zonaprop autorizó por escrito la consulta automatizada. Desde el 8 de noviembre de 2026, sus avisos se obtienen con el actor [igolaizola/zonaprop-scraper](https://apify.com/igolaizola/zonaprop-scraper) y entran al catálogo consolidado `inmobiliarias-autorizadas` con el prefijo `zonaprop:`. Sin `--ejecutar`, el comando solo muestra el plan y el costo estimado:

```powershell
python -m precio_entorno.zonaprop_apify --barrios Caballito Almagro --max-avisos 25
```

```powershell
python -m precio_entorno.zonaprop_apify --barrios Caballito Almagro --max-avisos 25 --cuenta 1 --tope-usd 0.5 --ejecutar --autorizacion-confirmada
```

- **Costo:** la tarifa es de USD 0,001 por aviso y USD 0,001 por ficha de detalle. Antes de cada corrida, el comando verifica que la tarifa no haya subido. Cada corrida lleva `maxTotalChargeUsd`, y el total de una ejecución no puede superar los USD 5 de la cuenta.
- **Privacidad:** el actor devuelve el nombre, los correos y los teléfonos del anunciante. El adaptador nunca los escribe: solo guarda los campos del contrato en `avisos.json`, junto con el registro de costos en `registro.json`.
- **Piloto del 8 de noviembre de 2026:**
  - **Captura:** 25 departamentos en venta por barrio en Caballito y Almagro, con ficha, en la cuenta 1 de Apify, por unos USD 0,05.
  - **Validación:** pasaron 49 de 50 avisos. El que falta no tenía superficie cubierta.
  - **Datos:** todos traen coordenadas con visibilidad «exacta» según Zonaprop, y 42 traen expensas. La mediana es de 2.423 USD/m².
  - **Ubicación:** `data/raw/zonaprop-venta-piloto-20261108/`. Los avisos ya están cargados en `data/local/real.sqlite3`.
- **Captura completa del 8 de noviembre de 2026:** se corrieron los 48 barrios oficiales en venta y en alquiler, con hasta 50 avisos con ficha por barrio. El comando rotó entre cuentas antes de que alguna se acercara a USD 5. Montserrat, Núñez y Nueva Pompeya se buscan como «Monserrat», «Nuñez» y «Pompeya», que son los nombres que reconoce Zonaprop; con `--barrios todos`, el comando ya los usa.

  | Operación | Leídos | Nuevos en la base | Barrios | Costo aproximado | Carpetas |
  | --- | ---: | ---: | ---: | ---: | --- |
  | Venta | 2.359 | 2.223 | 48 | USD 4,75 | `data/raw/zonaprop-venta-20261108/` y `-reintento/` |
  | Alquiler | 2.142 | 2.042 | 48 | USD 3,90 | `data/raw/zonaprop-alquiler-20261108/` y `-reintento/` |

  En venta, 49 avisos ya estaban cargados por el piloto. Los descartados no tenían superficie o tenían valores fuera de rango. En alquiler entraron 1.797 avisos en pesos y 245 en dólares. Con las cuatro cuentas, el gasto de Apify del mes quedó en USD 18,43 de USD 25.

### Exportaciones de EcomScrape

El [input de EcomScrape](apify-ecomscrape-input.json) limita la búsqueda a 25 resultados por barrio y desactiva los proxies y reintentos. El actor anterior recibió HTTP 403 en ambos barrios. La corrida de EcomScrape queda pendiente de que Zonaprop habilite el acceso directo desde Apify.

Si ya tenés una exportación autorizada de este actor, podés convertirla localmente. Usá la fecha efectiva de captura en ISO 8601. El archivo adaptado excluye datos del anunciante y se carga en **Datos reales** con el catálogo `zonaprop`.

```powershell
python -m precio_entorno.ecomscrape_export data/raw/ecomscrape.json --captured-at 2026-11-07 --output data/raw/avisos-ecomscrape.json
```

## Piloto de inmobiliarias autorizadas

El piloto del 7 de noviembre de 2026 capturó 50 avisos por inmobiliaria en `data/raw/inmobiliarias-piloto-consolidado/`: 138 de 150 pasan la validación y no hubo duplicados entre inmobiliarias. RE/MAX y Century 21 traen coordenadas sin precisión declarada; Migliorisi no trae coordenadas.
