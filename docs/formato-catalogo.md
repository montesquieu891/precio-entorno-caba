# Formato del catálogo de avisos

El CSV lleva encabezados y admite coma, punto y coma o tabulación. Para decimales, usá punto o coma sin separador de miles. En un CSV separado por comas, entrecomillá los decimales escritos con coma. El JSON en UTF-8 admite una lista de objetos o un objeto con una lista `listings`.

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

Además, el precio por m² cubierto debe quedar entre USD 200 y 20.000. Un importe escrito con separador de miles, como `105.000`, se lee como 105 y se descarta por inválido. Los campos opcionales son `total_area_m2` (`superficie_total`, entre 10 y 10.000 m²), `latitude` (`latitud`, `lat`), `longitude` (`longitud`, `lon`) y `location_accuracy_m` (`precision_m`). Si incluís `source` o `fuente`, debe coincidir con el catálogo indicado. Prepará el archivo solo con departamentos residenciales en venta. La app cuenta un pin como utilizable si ambas coordenadas caen en el rectángulo aproximado de CABA y el catálogo declara una precisión de hasta 100 m. En esta etapa el cruce se hace por barrio.

El cargador de delitos admite encabezados como `id-mapa`, `fecha`, `barrio`, `tipo_delito`, `franja_horaria` y `cantidad`, y sus variantes `id_mapa`, `tipo`, `franja` y `cantidad_registrada`. Conserva la fecha del hecho y muestra las franjas faltantes como «Sin dato». El resumen corresponde a las filas válidas del archivo cargado.

Los archivos `data/fixtures/avisos_prueba.csv` y `data/fixtures/delitos_prueba.csv` son ficticios. Las pruebas los cargan en bases temporales. Si querés probar el formulario con esos archivos, usá una copia de la carpeta del proyecto para mantener la base real reservada al catálogo autorizado.

Se importa desde **Datos reales** en la app de Streamlit (ver el README, «Importar archivos autorizados»).
