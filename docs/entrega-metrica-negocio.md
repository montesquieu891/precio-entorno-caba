# Precio y Entorno CABA · Métrica de negocio

> Medimos si la herramienta permite a una intermediaria inmobiliaria armar la lista de opciones para un comprador en menos tiempo, sin perder opciones relevantes.

## Versión breve para el formulario

La métrica principal es la mediana de minutos ahorrados por búsqueda: para cada búsqueda real, el tiempo con el método habitual menos el tiempo con la app, y luego la mediana de esas diferencias. Una búsqueda termina cuando la persona tiene la lista que enviaría al comprador, con un tope de 30 minutos. La elegimos porque los datos muestran el costo manual de buscar: 5 fuentes con campos informados de forma desigual, 220 inmuebles publicados en más de una fuente y precios por m² que varían más de nueve veces dentro de la ciudad. El ahorro solo cuenta si se conservan las opciones relevantes; por eso lo acompañan la cobertura de opciones relevantes, la precisión y novedad de las alertas y el costo operativo. Se medirá en un piloto con 5 a 10 búsquedas de una inmobiliaria. Todavía no hay resultados: no presentamos ahorro ni retorno como medidos.

## 1. Decisión que informa

**¿Vale la pena que una intermediaria incorpore la herramienta a su trabajo habitual, y bajo qué costo mensual?** La respuesta alimenta el ROI y el período de recuperación de la defensa del 24/11.

El valor esperado del producto tiene dos partes: armar la primera lista de opciones más rápido y enterarse antes de los avisos nuevos compatibles. La métrica principal mide la primera; los KPI de alertas, la segunda.

## 2. Métrica principal

Para cada búsqueda *i* resuelta con ambos métodos:

`ahorro_i = minutos_método_habitual_i − minutos_app_i`

`métrica principal = mediana(ahorro_i)`, en **minutos por búsqueda**

- Se calcula la mediana de las diferencias emparejadas, no la diferencia entre dos medianas.
- Un valor positivo indica ahorro; uno negativo, que la app llevó más tiempo.
- **Fin de la tarea:** la persona entrega la lista de avisos que enviaría al comprador. Si llega al tope de 30 minutos, se registra 30 y se marca como no terminada. El tope y la definición de "terminada" se fijan antes del piloto.
- **Reporte:** cada diferencia individual, mediana, rango intercuartílico, cantidad de búsquedas con ahorro positivo, tareas no terminadas y búsquedas sin coincidencias. Con 5 a 10 casos el resultado es descriptivo; no se reportan p-valores como evidencia.

**Por qué mediana y no promedio.** Con pocas búsquedas, una tarea excepcionalmente larga por un sitio caído o un comprador con criterios raros movería el promedio. La mediana resiste esos casos sin descartarlos.

## 3. Por qué esta métrica, según los datos

El corte auditado de 3.806 avisos muestra de dónde viene el tiempo que hoy dedica una persona a buscar:

| Evidencia en los datos | Trabajo manual que implica | Qué hace la app |
| --- | --- | --- |
| 5 fuentes; Zonaprop aporta el 59,7 % | Consultar varios sitios con filtros distintos | Un catálogo con filtros únicos |
| 220 inmuebles con avisos en más de una fuente | Detectar y descartar repetidos a mano | Agrupa duplicados aproximados |
| Antigüedad en el 77 % de los avisos, estado solo en una fuente, coordenadas faltantes en el 11 % | Abrir fichas para completar datos | Muestra qué falta y en qué fuente |
| Precio por m² entre USD 778 y 7.273 en el 98 % central, con diferencias fuertes entre los 48 barrios | Comparar barrios para el presupuesto del comprador | Compara barrios por coincidencias y precio publicado |

Estos datos justifican que el tiempo de búsqueda es el costo a reducir. **No demuestran que la app lo reduzca**: eso lo mide el piloto.

La misma heterogeneidad obliga a segmentar. Una búsqueda en un barrio con mucha oferta y otra con casi ninguna coincidencia no son comparables. Los segmentos se definen antes del piloto: barrios, rango de presupuesto, ambientes y cantidad de coincidencias. Cada uno se reporta con su n.

## 4. KPI de control

El ahorro se interpreta junto con estos indicadores. Los umbrales son una **propuesta a confirmar con Diana antes del piloto**; no se ajustan después de ver los resultados.

| KPI | Definición | Umbral propuesto | Qué controla |
| --- | --- | --- | --- |
| Cobertura de opciones relevantes | Relevantes con la app / relevantes con el método habitual | ≥ 80 % | Que el ahorro no venga de mostrar menos opciones. Puede superar 100 % |
| Precisión de alertas | Alertas `util` / alertas revisadas | ≥ 50 % | Que las alertas no sean ruido |
| Novedad de alertas | Alertas `util` que no eran `ya_conocida` / alertas `util` | > 0, con casos documentados | Que la app avise algo que la persona no tenía |
| Búsquedas con oferta compatible | Búsquedas con al menos un aviso compatible / búsquedas evaluadas | Se reporta, sin umbral | Cobertura del catálogo para necesidades reales |
| Costo operativo semanal | Minutos de captura, importación y revisión; USD de Apify y Make | Menor que el tiempo ahorrado en la semana | Que el mantenimiento no se coma el beneficio |

- La relevancia la decide la persona participante. Cumplir los filtros es condición necesaria, no suficiente.
- Si un denominador es cero, el indicador queda sin dato y se muestran los conteos; no se asigna cero.
- Cada búsqueda cuenta una vez por corte de evaluación; repetir un intento no suma búsquedas.

## 5. Protocolo del piloto

1. Una inmobiliaria con búsquedas activas en CABA y una o dos personas que las gestionen. Permiso escrito para el uso de datos.
2. Entre 5 y 10 búsquedas reales de departamentos en venta, cargadas sin datos personales: presupuesto, ambientes, superficie y barrios.
3. Antes de empezar, fijar criterios de compatibilidad, tope de tiempo, definición de tarea terminada, segmentos y umbrales.
4. **Tarea A.** Resolver cada búsqueda con ambos métodos. La mitad de las búsquedas empieza con el método habitual y la otra mitad con la app, en orden asignado al azar.
5. **Tarea B.** Durante dos semanas, capturar el catálogo cada dos o tres días y calificar cada alerta como `util`, `no_util` (con motivo) o `ya_conocida`.
6. **Tarea C.** Registrar tiempos de captura, importación y revisión, costos de servicios e incidentes.
7. Cerrar con la entrevista de adopción y disposición a pagar del [protocolo](validacion-inmobiliaria.md).

Todo se registra en la [planilla de validación](plantillas/registro-validacion.csv), incluidas las tareas fallidas y sin coincidencias.

**Sesgos del diseño y cómo se tratan:**

- **Aprendizaje:** quien resuelve la búsqueda por segunda vez ya conoce parte de las opciones. El orden balanceado reparte ese efecto entre métodos y se reporta el ahorro según qué método fue primero.
- **Cobertura distinta:** el método habitual recorre los portales completos y la app usa un catálogo con topes. El KPI de cobertura evita leer como ahorro una búsqueda que encontró menos.
- **Desfase de fechas:** el catálogo de la app puede ser más viejo que los portales. Se registra la fecha de la última captura en cada tarea.
- **Pocos casos y un solo participante:** el resultado orienta la decisión de esta inmobiliaria; no se extrapola al mercado.

## 6. Relación con la métrica técnica

El **MAE en USD/m²** mide qué tan bien el modelo anticipa el precio publicado; los **minutos ahorrados** miden el beneficio operativo. Un MAE menor no implica, por sí solo, que la persona encuentre opciones antes.

El vínculo se prueba en el piloto: si la brecha entre precio publicado y referencia sirve para priorizar, las alertas con brecha negativa deberían tener una precisión mayor que el resto. Se reportan ambas precisiones con su n. Si no difieren, la brecha no se muestra como criterio de orden.

## 7. Estado y criterio de decisión

**Estado al 17/11:** la métrica, los KPI y el protocolo están definidos. El piloto no se realizó: no hay línea de base ni ahorro medido.

**Criterio propuesto para recomendar la adopción** (a acordar con Diana antes del piloto): mediana de ahorro positiva, con ahorro en la mayoría de las búsquedas, y todos los umbrales de la sección 4 cumplidos. Si el ahorro es positivo pero falla la cobertura, la recomendación es ampliar fuentes antes de cobrar.

**Escenario económico,** solo con el ahorro medido:

`valor operativo mensual = búsquedas por mes × ahorro por búsqueda × costo por minuto del personal − costo operativo mensual`

- Las búsquedas por mes y el costo por minuto salen de la ficha de Diana o de la entrevista, y se citan como supuestos.
- Se calcula con el cuartil inferior, la mediana y el cuartil superior del ahorro, no con un único valor.
- El resultado valoriza tiempo liberado. No acredita ingresos, ventas adicionales ni ahorro de caja, salvo que ese tiempo se reasigne a otras tareas.
- El ROI y la recuperación de la inversión siguen las fórmulas del [plan de entrega](plan-capstone.md#presupuesto-y-defensa-comercial).

## Evidencia del proyecto

- [Plan de entrega](plan-capstone.md): definición de la métrica y fórmulas de ROI.
- [Protocolo de validación](validacion-inmobiliaria.md) y [planilla de registro](plantillas/registro-validacion.csv).
- [Auditoría metodológica](../reports/auditoria_metodologica.md): conteos, faltantes y duplicados citados en la sección 3.
- [Fenómeno y targets](entrega-fenomeno-targets.md).

Al compartir esta página por fuera del repositorio, reemplazar los enlaces relativos por enlaces accesibles para los evaluadores.
