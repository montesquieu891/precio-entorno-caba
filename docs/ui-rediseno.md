# Rediseño de la interfaz

Decisiones tomadas con el usuario el 17 y 18 de noviembre de 2026, sobre la maqueta `web/_maqueta.html` (no se publica). Antes y después en `docs/img/rediseno/`. Reemplaza la distribución de `docs/ui.md`; los principios de datos de ese documento siguen vigentes: sin puntajes, precios de publicación y advertencias de cada capa a la vista.

## Por qué

La versión anterior se veía apagada y técnica: panel fijo a la izquierda, mapa gris, una ficha larga de texto y tablas, y ruido y delitos como mosaicos opacos que tapaban las calles. Se buscó una app con carácter porteño.

## Distribución

- Mapa a pantalla completa, con el estilo **Voyager** de Carto en lugar de Positron.
- Filtros en una sola línea de pastillas que flotan sobre el mapa.
- **Inicio:** hoja flotante a la izquierda con una portada armada con SB7 y revisada con *Made to Stick*: el título «Elegí el barrio antes que el departamento», un ejemplo concreto con el primer barrio de la lista (avisos, mediana y subte), la guía con la proporción de avisos que encajan («de cada 6 avisos publicados, 5 no son para vos») y la fuente de los datos, un plan de tres pasos con resultados concretos, el botón «Activar una alerta» y el enlace «Ver de dónde salen los datos». Como las alertas son por barrio, el botón pide elegir uno y abre su pestaña «Crear alerta». Debajo va la lista de barrios. Cada fila muestra el nombre, los avisos que encajan de los publicados, la mediana, las insignias de subte y las hectáreas de plazas. El orden sigue siendo por cantidad de avisos.
- **Ficha del barrio:** misma hoja, con el nombre enorme, las insignias de las líneas de subte, la mediana y pestañas «Entorno», «Avisos (n)» y «Crear alerta». El entorno se muestra en piezas con una cifra grande (hectáreas de plazas, km de ciclovías, escuelas, líneas de colectivo) y una barra para el ruido.
- Capas en una fila al pie del mapa, cada una con un punto de su color. Aparecen al elegir un barrio.
  - 2026-11-19: con varias capas de puntos encendidas, los avisos se perdían: eran círculos violetas de radio 5, más chicos que los de Subte o Recreación y casi del color de los cines. Ahora son un pin con punta (la única forma del mapa que no es un círculo), relleno o hueco si la ubicación es aproximada, más grande en un punto con varios avisos, y van encima de todas las capas. El globo se abre arriba del pin para no taparlo.
  - 2026-11-19: la fila quedaba larga y las últimas capas (Ciclovías, Ecobici, Rampas, Delitos) se perdían fuera de la vista. La fila muestra las capas de «Lo que me importa» y una pestaña fija «Más capas» a la derecha. Esa pestaña abre un cajón, desde la derecha, con el resto agrupado en Movilidad, Actividades y Registros. Una capa del cajón encendida también aparece en la fila, y la pestaña cuenta cuántas hay prendidas. El cajón se cierra con «Cerrar», Escape o un clic afuera. En el celular ocupa todo el ancho.
- **Celular:** el mapa arriba y la hoja deslizable desde abajo.

## Identidad

- Tipografía **Archivo** (Omnibus-Type, Buenos Aires) usada al extremo de ancho para nombres de barrio y títulos.
- Paleta **jacarandá**: el violeta es el color de lo que la persona elige (botones activos, barrio marcado, pestañas) y del teñido de barrios en el mapa.
- **Títulos en adoquín** (`#23272B`), no en violeta (elegido frente a jacarandá, tinta violeta y adoquín con franja).
- Se descartaron las paletas celeste, taxi y mayólica.

## Mapa

- **Ruido:** se mantiene la escala amarilla a roja, pero se dibujan solo las calles con 70 dBA o más, como un brillo suave. La barra de la ficha sigue esa misma escala.
- **Delitos:** el mismo brillo, en gris azulado, sobre el 20 % de las zonas del barrio con más hechos registrados. La leyenda dice «Zonas del barrio con más hechos registrados» y conserva las advertencias de subregistro y circulación.
- Ruido y delitos se recortan por la forma del barrio, no por un rectángulo.

## Implementación prevista

1. Estructura y estilo: distribución, Voyager, hoja con pestañas, capas al pie, lista nueva, celular y teclado. Todo lo que hoy existe (alertas, explorador de necesidades, controles de delitos, estacionamientos, cocheras, radar) tiene que tener un lugar en la hoja.
2. Mapa: brillo de ruido y delitos y recorte por barrio (requiere un cambio chico en la API).
