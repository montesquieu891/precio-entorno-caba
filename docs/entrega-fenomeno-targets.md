# Precio y Entorno CABA · Fenómeno y targets

> Ayudamos a intermediarias inmobiliarias que gestionan búsquedas de compradores a decidir en qué barrios concentrar cada búsqueda y qué avisos revisar primero.

## Versión breve para el formulario

Estudiamos la variación del precio publicado por m² cubierto de departamentos en venta en CABA y cuánto de esa variación se explica por las características del inmueble, su ubicación y su entorno. La pregunta central es si los delitos registrados del Mapa del Delito aportan información predictiva adicional a la ubicación. El target es el precio publicado dividido por la superficie cubierta, en USD/m², y se modela como regresión. La unidad de análisis es el aviso; la evaluación agrupa las publicaciones del mismo inmueble para evitar fuga entre entrenamiento y prueba. Usamos un corte de 3.806 avisos de un catálogo autorizado, capturados del 7 al 9 de noviembre de 2026. La referencia estimada se usa para priorizar avisos, no como tasación ni precio de cierre. Las asociaciones encontradas no son causales.

## 1. Problema y decisión

La oferta está repartida entre portales e inmobiliarias, con avisos duplicados y campos informados de forma desigual. Quien gestiona búsquedas de compradores debe filtrar, reconciliar y volver a revisar periódicamente para no perder opciones nuevas.

La decisión que el análisis informa es: **¿en qué barrios conviene concentrar esta búsqueda y qué avisos vale la pena revisar primero?** El producto la lleva a la práctica con el flujo preferencias → comparación de barrios → búsqueda guardada → alerta por aviso nuevo.

**Alcance analítico:** departamentos en venta publicados en USD. Alquileres, estacionamientos y las demás capas de la app son extensiones del producto, con datos y unidades propios, y no forman parte de este análisis.

## 2. Fenómeno, pregunta e hipótesis

**Fenómeno.** Dos departamentos de superficie similar pueden publicarse a precios por m² muy distintos, entre barrios y dentro de un mismo barrio. En el corte auditado la mediana es USD 2.411/m² y el 98 % central va de USD 778 a 7.273/m².

**Pregunta.** ¿Qué parte de esa variación se puede anticipar con las características publicadas del inmueble y su ubicación, y los delitos registrados en el entorno agregan información predictiva más allá de esa ubicación?

| Hipótesis | Criterio para sostenerla |
| --- | --- |
| H1. Las características y la ubicación anticipan el precio por m² mejor que la mediana de comparables del mismo barrio y ambientes | El modelo reduce el MAE frente a comparables en prueba y en los 5 pliegues de validación cruzada |
| H2. Los delitos registrados aportan información adicional a la ubicación y la proximidad a servicios | El modelo con delitos mejora en los 5 pliegues **y** supera a un placebo con valores sin información sobre delitos |

El criterio de H2 se fijó antes de evaluar. Un aporte que no supera al placebo se interpreta como codificación de barrio o de actividad urbana, no como señal de los delitos.

**Lo que el diseño no permite afirmar.** Que un equipamiento o los delitos *causen* diferencias de precio. Intervienen características no observadas del inmueble, diferencias de criterio entre fuentes y la propia distribución territorial de las denuncias.

## 3. Datos y unidades

| Fuente | Unidad | Uso | Período |
| --- | --- | --- | --- |
| Catálogo autorizado de avisos (5 fuentes) | Aviso, agrupado en inmuebles aproximados | Target y variables del inmueble | Captura del 7 al 9/11/2026 |
| Mapa del Delito de CABA | Hecho registrado, agregado por barrio; conteo a 500 m como sensibilidad | Variables de entorno | Los 12 meses publicados previos a la captura: enero–diciembre de 2025 |
| Capas de entorno (transporte, parques, salud, escuelas, gastronomía) | Punto o polígono, resumido como distancia o conteo cercano | Variables de ubicación | Según la fuente |

**Corte analítico.** 3.806 avisos de venta en USD que forman 3.582 inmuebles aproximados; 220 grupos tienen más de un aviso, todos de fuentes distintas. Zonaprop aporta el 59,7 % con un tope de 50 avisos por barrio. El corte describe ese catálogo, no el mercado total.

**Unidades a no confundir.** El análisis se hace por aviso, la partición por inmueble aproximado y los delitos por barrio y ventana anual. Los delitos por hectárea son una densidad territorial: sin un denominador de población o circulación no son una tasa de riesgo.

## 4. Target

`y = precio_publicado_USD / superficie_cubierta_m2`

- **Tipo:** regresión continua, en USD/m².
- **Filtros de validez:** precio en USD, superficie cubierta de 10 a 2.000 m² y precio por m² de USD 200 a 20.000. Los atípicos dentro de ese rango se marcan para revisión pero no se eliminan de la evaluación.
- **Transformación:** el modelo puede entrenarse sobre `log(y)` por la asimetría de la distribución; el error se reporta siempre en USD/m².
- **Por qué por m² y no precio total:** permite comparar inmuebles de distinto tamaño y es la unidad con la que el usuario contrasta avisos. Como la superficie está en el denominador, parte de su asociación con el target es mecánica y no debe leerse como efecto del tamaño.

**Fuga de información.** Se excluyen como predictoras el precio total, el propio precio por m² y cualquier estadística calculada con el precio de avisos del conjunto de prueba, incluidas las medianas de comparables sobre el catálogo completo. Imputación, escalado, vocabularios y comparables se ajustan dentro de cada partición de entrenamiento.

## 5. Salidas del producto derivadas del target

No son targets de aprendizaje; se apoyan en el target o en reglas explícitas.

| Salida | Definición | Condición de uso |
| --- | --- | --- |
| Referencia de precio publicado | Predicción del modelo para un aviso nuevo, en USD/m² | Mostrarla con el MAE de evaluación y la fecha del corte |
| Brecha para priorizar | (precio por m² publicado − referencia) / referencia | Solo con soporte suficiente de comparables y sin señales de carga dudosa. Una brecha negativa sugiere revisar primero, no indica una buena compra |
| Alerta por aviso nuevo | ID no visto antes que cumple presupuesto, superficie, ambientes y barrios de la búsqueda | Regla determinística; no requiere un modelo |

## 6. Evaluación

- **EDA:** distribuciones, faltantes por fuente y barrio, Pearson, Spearman y LOWESS, cada cruce con su n y su unidad. Se comparan precio absoluto y precio relativo a la mediana del barrio para separar diferencias entre barrios de diferencias dentro de cada barrio.
- **Predicción:** partición de prueba del 20 % por inmueble (semilla 42) y validación cruzada de 5 pliegues agrupada. Métrica principal: MAE en USD/m²; secundarias: R² y error porcentual mediano sobre el precio observado. Referencia mínima: mediana de comparables por barrio y ambientes calculada solo con entrenamiento. Se informan errores por fuente, barrio y rango de precio.
- **Atribución al entorno:** placebo por pliegue y mejora pliegue a pliegue, como define H2.
- **Utilidad:** la prueba con usuarios se especifica en la [métrica de negocio](entrega-metrica-negocio.md).

## 7. Estado de la evidencia (14–15/11)

- **H1 se sostiene.** HistGradientBoosting obtiene un MAE de validación cruzada de 469 ± 10 USD/m² con las variables base y de 400 ± 14 al sumar antigüedad, cocheras y rasgos de la descripción, frente a 584 ± 21 de la mediana de comparables. Ambos ensambles superan a los modelos lineales, al árbol y al MLP.
- **H2 no se sostiene con la especificación final.** Al incluir la proximidad a servicios, los delitos bajan el MAE de 469 a 467, la mejora cambia de signo entre pliegues y no supera al placebo. El aporte aparente en especificaciones más simples se explicaba por la ubicación y la actividad urbana.
- **Consecuencia para el producto:** la referencia de precio usa el modelo sin delitos. Los delitos registrados se muestran como contexto, con período y unidad geográfica, y no como predictor ni como puntaje de seguridad.

Detalle y tablas en [modelo.md](modelo.md).

## 8. Sesgos y límites

- **Selección:** la muestra depende de las fuentes autorizadas y de los topes de captura. No es representativa de toda la oferta de CABA.
- **Faltantes que dependen de la fuente:** la antigüedad está en el 77 % de los avisos, el estado solo en Century 21 y faltan coordenadas en el 11 %. En Zonaprop, el 27 % declara 0 años de antigüedad, posible valor por defecto. El modelo puede aprender la fuente a través de esos patrones.
- **Precio de publicación:** no equivale a tasación ni a precio de cierre; el margen de negociación no se observa.
- **Duplicados y coordenadas aproximados:** la detección de duplicados entre fuentes no es exhaustiva y varios pines coinciden.
- **Delitos registrados:** dependen de la denuncia, la circulación y el patrullaje. Describen hechos de un período y un territorio, no el riesgo de una persona.
- **Generalización:** validada dentro del corte. Falta comprobarla con capturas posteriores, barrios o fuentes nuevas.

## Evidencia del proyecto

- [Plan de entrega](plan-capstone.md)
- [Auditoría metodológica](../reports/auditoria_metodologica.md)
- [Evaluación del modelo](modelo.md)
- [Notebook EDA](../notebooks/eda_oportunidades.ipynb)
- [Benchmark de modelos](../notebooks/benchmark_modelos.ipynb)

Al compartir esta página por fuera del repositorio, reemplazar los enlaces relativos por enlaces accesibles para los evaluadores.
