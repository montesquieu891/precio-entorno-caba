# Validación con una inmobiliaria · Protocolo

Este protocolo cubre el eje "Valor para el usuario" y el entregable de validación de la consigna. Mide si la app ayuda a quien gestiona búsquedas de compradores a encontrar opciones compatibles más rápido y si sus alertas resultan útiles, antes de proyectar costos o retorno.

## 1. Preguntas

1. ¿Cuánto tarda una persona del equipo en encontrar opciones compatibles con la app, comparado con su método habitual?
2. ¿Qué proporción de las alertas resulta útil?
3. ¿Cuánto cuesta mantener el seguimiento, en tiempo y dinero?
4. ¿La inmobiliaria pagaría por la herramienta, y en qué condiciones?

## 2. Participantes y duración

- **Participantes:** una inmobiliaria con búsquedas activas de compradores en CABA, y una o dos personas que gestionen esas búsquedas.
- **Búsquedas:** entre 5 y 10 búsquedas reales de departamentos en venta, cargadas sin datos personales del comprador (solo presupuesto, ambientes, superficie y barrios de interés).
- **Duración:** dos semanas, con una captura del catálogo al inicio y luego cada dos o tres días.

## 3. Preparación

1. Confirmar por escrito el permiso de la inmobiliaria y el uso de los datos: solo agregados y sin datos de clientes.
2. Correr la captura (`python -m precio_entorno.inmobiliarias --autorizacion-confirmada`) e importar `avisos.json` en **Datos reales**.
3. Cargar en la app cada búsqueda del participante y anotar su ID en la planilla.
4. Copiar la planilla [registro-validacion.csv](plantillas/registro-validacion.csv) para registrar las tareas y las alertas. Además de tiempos y opciones, tiene estas columnas:
   - `orden`: 1 o 2, según qué método se usó primero en la búsqueda;
   - `terminada`: `si` o `no`, si se llegó al tope de tiempo;
   - `fecha_captura_app`: fecha de la captura que usó la app;
   - `brecha_pct`: brecha de precio del aviso alertado frente a la referencia.
5. Antes de la primera tarea, acordar con la inmobiliaria y dejar por escrito:
   - los criterios de compatibilidad de cada búsqueda;
   - cuándo una tarea está terminada: la persona tiene la lista de avisos que enviaría al comprador;
   - el tope de tiempo por tarea (propuesta: 30 minutos);
   - los segmentos de análisis: barrios, rango de presupuesto, ambientes y cantidad de coincidencias;
   - los umbrales de la sección 5.

   Estos criterios no se cambian después de ver los resultados.

## 4. Tareas

**Tarea A · Encontrar opciones.** Para cada búsqueda, la persona encuentra los avisos compatibles de dos maneras:
- **Método habitual:** portales, CRM o planillas propias.
- **App:** comparación de barrios y lista de coincidencias.

La mitad de las búsquedas empieza con el método habitual y la otra mitad con la app, en orden asignado al azar antes de empezar. Así el aprendizaje de la segunda pasada se reparte entre los dos métodos.

Se registran el orden, el tiempo hasta tener la lista, la cantidad de opciones encontradas, cuántas considera relevantes y la fecha de la última captura de la app. Si se llega al tope sin terminar, se registra el tope y la tarea se marca como no terminada.

**Tarea B · Revisar alertas.** Después de cada captura nueva se importan los avisos y se revisan las alertas. Para cada una se registran la fecha de captura y la brecha de precio que muestra la app, y la persona marca:
- `util`: la enviaría al comprador;
- `no_util`: coincide con los filtros pero no sirve, e indica el motivo;
- `ya_conocida`: ya la tenía por otra vía.

**Tarea C · Costo operativo.** Se registra:
- el tiempo de cada captura y de cada importación;
- el tiempo dedicado a revisar las alertas;
- cualquier incidente: un sitio caído, un bloqueo o un dato erróneo.

## 5. Métricas

La definición completa y su justificación están en [Métrica de negocio](entrega-metrica-negocio.md). Los umbrales son una propuesta a confirmar con la inmobiliaria en la preparación.

| Métrica | Cálculo | Fuente | Umbral propuesto |
| --- | --- | --- | --- |
| **Tiempo ahorrado por búsqueda (principal)** | Mediana de (método habitual − app) por búsqueda, en minutos | Tarea A | Positiva, con ahorro en la mayoría de las búsquedas |
| Cobertura | Opciones relevantes de la app / opciones relevantes del método habitual | Tarea A | ≥ 80 % |
| Precisión de alertas | Alertas `util` / alertas revisadas | Tarea B | ≥ 50 % |
| Novedad | Alertas `util` no `ya_conocida` / alertas `util` | Tarea B | > 0, con casos documentados |
| Búsquedas con oferta compatible | Búsquedas con al menos un aviso compatible / búsquedas evaluadas | Tarea A | Se reporta, sin umbral |
| Costo operativo semanal | Minutos de captura, importación y revisión por semana, y USD de servicios (Apify, Make) | Tarea C | Menor que el tiempo ahorrado en la semana |

- **Reporte del tiempo ahorrado:** cada diferencia, mediana, rango intercuartílico, búsquedas con ahorro positivo, tareas no terminadas y búsquedas sin coincidencias. Se informa también según qué método se usó primero.
- **Brecha de precio:** se compara la precisión de las alertas con brecha negativa frente a la del resto, cada una con su n. Si no difieren, la brecha no se usa para ordenar.
- **Denominador cero:** el indicador queda sin dato y se muestran los conteos.

Con 5 a 10 búsquedas, los resultados son orientativos. Se reportan con su cantidad de casos, sin p-valores como evidencia y sin extrapolar a todo el mercado.

## 6. Entrevista final (20 minutos)

1. ¿En qué momento de su trabajo usaría la app? ¿Qué reemplazaría?
2. ¿Qué alertas no le sirvieron y por qué? ¿Qué filtro faltó?
3. ¿El contexto de delitos registrados le resultó útil, indiferente o contraproducente con los compradores?
4. ¿Confía en los precios y en los barrios que muestra la app? ¿Qué error vio?
5. Disposición a pagar, por usuario y por mes:
   - ¿A qué precio le parecería tan barata que dudaría de la calidad?
   - ¿A qué precio le parecería una buena compra?
   - ¿A qué precio le parecería cara, pero la pagaría igual?
   - ¿A qué precio no la pagaría?
6. ¿Qué necesitaría para usarla todos los días? Por ejemplo, correo, integración con su CRM o más fuentes.

## 7. Retorno estimado

Solo después de medir, el beneficio mensual puede estimarse así:

> beneficio = búsquedas activas por mes × minutos ahorrados por búsqueda × costo por minuto del personal − costo operativo mensual

Las cifras se reportan como un escenario con sus supuestos, no como una proyección de ingresos. Se calcula con el cuartil inferior, la mediana y el cuartil superior del ahorro medido. Las búsquedas por mes y el costo por minuto salen de la ficha o de la entrevista y se citan como supuestos.

## 8. Cuidado de los datos

- No se cargan nombres, teléfonos ni correos de compradores ni de propietarios.
- La planilla usa identificadores de búsqueda, no datos personales.
- Los avisos capturados se usan solo para la prueba y el informe, y se eliminan al terminar si la inmobiliaria lo pide.
- En el informe aparecen solo resultados agregados y, si lo prefiere, sin el nombre de la inmobiliaria.
