'use strict';

/* Lüga: interfaz web. Habla con la API local de precio_entorno.api. */

const PREFERENCIAS = [
  { clave: 'subte', nombre: 'Subte' },
  { clave: 'verdes', nombre: 'Plazas y parques' },
  { clave: 'escuelas', nombre: 'Escuelas' },
  { clave: 'salud', nombre: 'Salud' },
  { clave: 'ruido', nombre: 'Ruido' },
  { clave: 'riesgo', nombre: 'Riesgo hídrico' },
  { clave: 'recreacion', nombre: 'Recreación' },
];
// Recreación: tipo → [nombre en plural, singular, color en el mapa]. El orden es el de la ficha y la leyenda.
const RECREACION = {
  cine: ['cines', 'cine', '#4338CA'],
  teatro: ['teatros', 'teatro', '#BE123C'],
  museo: ['museos', 'museo', '#A16207'],
  cultural: ['centros culturales y galerías', 'centro cultural o galería', '#0E7490'],
};
const CAPAS_MAPA = [...PREFERENCIAS, { clave: 'estacionamiento', nombre: 'Estacionamiento' },
  { clave: 'clubes', nombre: 'Clubes' }, { clave: 'gimnasios', nombre: 'Gimnasios' },
  { clave: 'colectivos', nombre: 'Colectivos' }, { clave: 'ciclovias', nombre: 'Ciclovías' },
  { clave: 'ecobici', nombre: 'Ecobici' }, { clave: 'bibliotecas', nombre: 'Bibliotecas' },
  { clave: 'rampas', nombre: 'Rampas' }];
// Capas de puntos de toda la ciudad: se piden una vez, sin importar el barrio.
const CAPAS_CIUDAD = new Set(['estacionamiento', 'clubes', 'gimnasios']);
const CAPAS = [...CAPAS_MAPA, { clave: 'delitos', nombre: 'Delitos registrados' }];
// Las capas de «Lo que me importa» van siempre a la vista; el resto, en «Más capas», agrupadas.
// Una capa de «Más capas» encendida también aparece en la fila, para apagarla sin abrir el cajón.
const MAS_CAPAS = [
  ['Movilidad', ['colectivos', 'ciclovias', 'ecobici', 'estacionamiento']],
  ['Actividades', ['clubes', 'gimnasios', 'bibliotecas']],
  ['Registros', ['delitos', 'rampas']],
];
const SUBTE = { A: '#18CCCC', B: '#EB0909', C: '#233AA8', D: '#02A17A', E: '#AE3D97', H: '#FFD600' };
const COLOR = { verdes: '#5E7D4F', riesgo: '#1E88E5', escuela: '#1E2A32', cesac: '#00897B', hospital: '#795548',
  aviso: '#6A4FB3', estacionamiento: '#1671A3', clubes: '#C2410C', gimnasios: '#0F766E', colectivo: '#D81B60',
  ascensor: '#1E2A32', ciclovias: '#00838F', ecobici: '#004F56', bibliotecas: '#AD1457', rampas: '#B26B00' };
const RUIDO = [[50, '#FFFFCC'], [55, '#FFEDA0'], [60, '#FED976'], [65, '#FEB24C'], [70, '#FD8D3C'], [75, '#F03B20'], [80, '#BD0026']];
const DELITOS = ['#D3DBE3', '#A9B8C8', '#7E93AB', '#55708E', '#2E4560'];
const ESCALA_BARRIOS = ['#F4F2F8', '#E2DAF3', '#7A62C4'];
const ESTILO = 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json';
const NOTA_AVISOS = 'Punto que publica la fuente, sin precisión declarada: puede marcar el edificio o una referencia cercana. '
  + 'Hueco si cae a entre 150 y 500 m del barrio del aviso. Más lejos, no se dibuja. Un punto más grande reúne varios avisos.';
const NOTAS = {
  subte: 'Indican conectividad, no tiempos de viaje. Borde oscuro: estación con ascensores informados por SBASE; '
    + 'no indica si funcionan, y hay estaciones sin dato.',
  verdes: 'Plazas, parques, jardines y paseos. No incluye canteros ni plazoletas.',
  escuelas: 'Estar cerca no asegura una vacante. Consultá cada escuela.',
  salud: 'Estar cerca no asegura turnos.',
  ruido: 'Se marcan solo las celdas de 100 m del barrio con nivel exterior típico de 70 dBA o más de día (65 de noche), medido sobre todo en calles. No describe el interior de un departamento.',
  riesgo: 'Áreas de prevención publicadas en 2020. Si una dirección cae dentro, conviene preguntarlo en la visita.',
  estacionamiento: 'Inventario oficial publicado en 2021, sin fecha de relevamiento informada. Confirmá que el garaje siga funcionando y consultá cupos y abonos mensuales.',
  clubes: 'Clubes de barrio y polideportivos del listado de la Ciudad. Consultá actividades, cuotas y horarios con cada club.',
  gimnasios: 'Gimnasios cargados en OpenStreetMap. La cobertura depende de quién mapea cada zona y puede haber cierres o aperturas recientes.',
  colectivos: 'Líneas que pasan por el barrio, según el GTFS oficial con calendario de 2019. Los recorridos pueden haber cambiado: confirmalos en la app oficial.',
  ciclovias: 'Tramos de ciclovía publicados por la Ciudad (recurso de marzo de 2025). Que haya una cerca no garantiza un recorrido continuo ni protegido.',
  ecobici: 'Estaciones del listado oficial de abril de 2025. No informa si cada estación está operativa ni cuántas bicis tiene: consultalo en la app de Ecobici.',
  bibliotecas: 'Bibliotecas de la Red de la Ciudad, incluidas las populares (listado de marzo de 2025). Confirmá horarios y servicios con cada una.',
  recreacion: 'Cines, teatros, museos, centros culturales y galerías cargados en OpenStreetMap. La cobertura depende de quién mapea cada zona: '
    + 'faltan salas independientes y puede haber cierres recientes. Confirmá la programación con cada lugar.',
  rampas: 'Rampas registradas en obras de 2011 a 2016 (BA Data), ubicadas por dirección. No es un inventario: que una esquina no tenga punto no '
    + 'significa que no tenga rampa, y una rampa registrada pudo haber cambiado. No certifica recorridos accesibles.',
  delitos: 'Se marcan las zonas del barrio con más hechos registrados: el 20 % de las celdas de 200 m con más hechos en el año elegido, o las que se repiten entre años. Hechos registrados por celda de 200 m. Más circulación puede concentrar más eventos y existe subregistro. No equivalen a la probabilidad individual de victimización.',
};
/* Explorador de necesidades (docs/plan-explorador-necesidades.md). Apagado por defecto: se prueba con
   ?explorador=1. Cada necesidad sugiere capas y columnas; no filtra avisos ni arma puntajes. */
const EXPLORADOR = (() => {
  try { return new URLSearchParams(window.location?.search || '').get('explorador') === '1'; } catch { return false; }
})();
const NECESIDADES = [
  { clave: 'sin_auto', nombre: 'Me muevo sin auto', descripcion: 'Subte cercano y líneas de colectivo del barrio.',
    capas: ['subte', 'colectivos'], columnas: ['subte', 'subte_ascensor'], advertencias: [] },
  { clave: 'sin_escaleras', nombre: 'Necesito evitar escaleras',
    descripcion: 'Ascensor, planta baja o acceso sin escalones según el aviso, subte con ascensor y salud cerca.',
    capas: ['subte', 'salud'], columnas: ['acceso', 'subte_ascensor', 'hospital', 'cesac'],
    advertencias: [
      'El acceso sale del texto del aviso: que no mencione el ascensor no significa que no tenga. Por ahora lo tienen los '
        + 'avisos de Migliorisi y los capturados desde el 23/11/2026; en los demás figura «Sin dato».',
      'Un ascensor no asegura llegar sin escalones. Antes de visitar, preguntale al anunciante: ¿hay escalones entre la '
        + 'vereda y el ascensor? ¿Cuánto miden la puerta del ascensor y la del baño? ¿Hay espacio para girar con una silla de ruedas?',
    ] },
  { clave: 'lugar_fijo', nombre: 'Tengo que ir seguido a un lugar',
    descripcion: 'Un hospital, un tratamiento, una escuela o el trabajo: distancia desde cada barrio y cada aviso.',
    capas: [], columnas: ['lugar_fijo'],
    advertencias: [
      'La distancia al lugar fijo es en línea recta: no es un recorrido por calles ni un tiempo de viaje.',
      'El lugar que elegís queda guardado solo en este navegador: Lüga no lo recibe.',
    ] },
  { clave: 'familia', nombre: 'Escuelas y salud cerca', descripcion: 'Escuelas del nivel elegido, centros de salud y plazas.',
    capas: ['escuelas', 'salud', 'verdes'],
    columnas: ['escuela', 'cesac', 'hospital', 'plaza', 'ambientes', 'superficie', 'patio', 'balcon'], advertencias: [] },
  { clave: 'teletrabajo', nombre: 'Trabajo desde casa', descripcion: 'Ruido exterior de día, bibliotecas, ambientes, luz y contrafrente.',
    capas: ['ruido', 'bibliotecas'], columnas: ['ruido_diurno', 'biblioteca', 'ambientes', 'superficie', 'luminoso', 'contrafrente'],
    advertencias: [] },
  { clave: 'bicicleta', nombre: 'Me muevo en bici', descripcion: 'Ciclovías y estaciones de Ecobici.',
    capas: ['ciclovias', 'ecobici'], columnas: ['ciclovia', 'ecobici'], advertencias: [] },
  { clave: 'salidas', nombre: 'Salir: cine, teatro y museos', descripcion: 'Cines, teatros, museos y centros culturales.',
    capas: ['recreacion'], columnas: ['recreacion'], advertencias: [] },
  { clave: 'costo_mensual', nombre: 'Quiero ver el costo mensual', descripcion: 'Precio publicado, expensas y cocheras.',
    capas: [], columnas: ['precio', 'expensas', 'cocheras'],
    advertencias: ['Los importes se suman por moneda, sin convertir. Si el aviso no informa las expensas, se indica.'] },
];
// Capas con distancia por aviso en /api/barrios/{barrio}/avisos (precio_entorno/cercania.py).
const CAPAS_CERCANIA = ['subte', 'escuelas', 'salud', 'verdes', 'ruido', 'ciclovias', 'ecobici', 'bibliotecas', 'recreacion'];

/* Combina las necesidades elegidas con las decisiones manuales. La elección manual gana: una capa apagada a mano
   no vuelve aunque una necesidad la sugiera. Devuelve capas en el orden del mapa, sin duplicados. */
function resolverNecesidades(seleccion, manual = { encendidas: new Set(), apagadas: new Set() }) {
  const elegidas = NECESIDADES.filter((n) => seleccion.has(n.clave));
  const origen = {};
  for (const n of elegidas) for (const c of n.capas) (origen[c] ||= []).push(n.clave);
  for (const c of manual.encendidas) (origen[c] ||= []).push('manual');
  const capas = CAPAS.map((c) => c.clave).filter((c) => origen[c] && !manual.apagadas.has(c));
  return {
    capas,
    columnas: [...new Set(elegidas.flatMap((n) => n.columnas))],
    cercania: capas.filter((c) => CAPAS_CERCANIA.includes(c)),
    advertencias: [...new Set([...capas.map((c) => NOTAS[c]), ...elegidas.flatMap((n) => n.advertencias)].filter(Boolean))],
    origen: Object.fromEntries(capas.map((c) => [c, origen[c]])),
  };
}

function explorador() {
  return resolverNecesidades(estado.necesidades, { encendidas: estado.prefs, apagadas: estado.apagadas });
}

const metrosTexto = (m) => (m < 1000 ? `${numero.format(m)} m` : `${decimal.format(m / 1000)} km`);
// Columnas de distancia de la tabla de avisos: la capa tiene que estar prendida para que la API la calcule.
const COLUMNAS_DISTANCIA = {
  subte: { capa: 'subte', titulo: () => 'Subte', valor: (c) => c.subte,
    texto: (v) => `<span title="Estación ${esc(v.estacion)}">${metrosTexto(v.m)} · ${esc(v.linea)}</span>` },
  subte_ascensor: { capa: 'subte', titulo: () => 'Subte con ascensor', valor: (c) => c.subte_ascensor,
    texto: (v) => `<span title="Estación ${esc(v.estacion)}">${metrosTexto(v.m)} · ${esc(v.linea)}</span>` },
  escuela: { capa: 'escuelas', titulo: () => `Escuela (${estado.nivel})`, valor: (c) => c.escuela },
  cesac: { capa: 'salud', titulo: () => 'CeSAC', valor: (c) => c.cesac },
  hospital: { capa: 'salud', titulo: () => 'Hospital', valor: (c) => c.hospital },
  plaza: { capa: 'verdes', titulo: () => 'Plaza', valor: (c) => c.plaza },
  ciclovia: { capa: 'ciclovias', titulo: () => 'Ciclovía', valor: (c) => c.ciclovia },
  ecobici: { capa: 'ecobici', titulo: () => 'Ecobici', valor: (c) => c.ecobici },
  biblioteca: { capa: 'bibliotecas', titulo: () => 'Biblioteca', valor: (c) => c.biblioteca },
  recreacion: { capa: 'recreacion', titulo: () => 'Cine, teatro o museo', valor: (c) => c.recreacion,
    texto: (v) => `<span title="${esc(v.nombre)}">${metrosTexto(v.m)} · ${esc(RECREACION[v.tipo]?.[1] || '')}</span>` },
  ruido_diurno: { capa: 'ruido', titulo: () => 'Ruido de día', valor: (c) => c.ruido_diurno,
    texto: (v) => (v.dba == null ? 'Sin celda relevada' : `${v.dba} dBA`) },
};
const RASGOS_TEXTO = { patio: 'patio', balcon: 'balcón', luminoso: 'luminoso', contrafrente: 'contrafrente' };

function celdaDistancia(def, aviso) {
  const v = aviso.cercania && def.valor(aviso.cercania);
  if (!v || (!('dba' in v) && v.m == null)) return '—';
  const texto = def.texto ? def.texto(v) : metrosTexto(v.m);
  return aviso.ubicacion === 'aproximada' ? `${texto} <span class="fuente">aprox.</span>` : texto;
}

function celdaRasgos(claves, aviso) {
  if (claves.every((k) => aviso.rasgos?.[k] == null)) return '<span class="fuente">Sin texto</span>';
  const menciona = claves.filter((k) => aviso.rasgos[k] === 1).map((k) => RASGOS_TEXTO[k]);
  return menciona.length ? esc(enumerar(menciona)) : '<span class="fuente">No los menciona</span>';
}

/* Acceso según el aviso: texto de la descripción (ascensor, sin ascensor, sin escalones) y piso informado.
   Nunca dice «no tiene» si el aviso no lo dice: «No lo menciona» y «Sin dato» son cosas distintas. */
function celdaAcceso(aviso) {
  const r = aviso.rasgos || {};
  const pb = aviso.piso === 0;
  if (r.sin_ascensor === 1) return pb ? 'Planta baja; dice que no tiene ascensor' : 'Dice que no tiene ascensor';
  const partes = [r.acceso_sin_escalones === 1 && 'acceso sin escalones', pb && 'planta baja', r.ascensor === 1 && 'ascensor']
    .filter(Boolean);
  if (partes.length) { const t = enumerar(partes); return esc(t[0].toUpperCase() + t.slice(1)); }
  return r.ascensor == null ? '<span class="fuente">Sin dato</span>' : '<span class="fuente">No lo menciona</span>';
}

/* Lugar fijo: un punto que la persona elige (hospital de la lista o marca en el mapa). Las distancias se calculan
   acá, en línea recta y en metros planos, para que el lugar no viaje en ningún pedido al servidor. */
const M_LAT = 111320;
const M_LON = M_LAT * Math.cos((-34.62 * Math.PI) / 180);

function metrosEntre(lon1, lat1, lon2, lat2) {
  return Math.hypot((lon1 - lon2) * M_LON, (lat1 - lat2) * M_LAT);
}

// 0 si el punto cae dentro del barrio; si no, la distancia al borde más cercano.
function metrosABarrio(lon, lat, geometria) {
  const poligonos = geometria?.type === 'Polygon' ? [geometria.coordinates]
    : geometria?.type === 'MultiPolygon' ? geometria.coordinates : [];
  let dentro = false;
  let minimo = Infinity;
  for (const anillos of poligonos) {
    for (const anillo of anillos) {
      for (let i = 0, j = anillo.length - 1; i < anillo.length; j = i, i += 1) {
        const [x1, y1] = anillo[i];
        const [x2, y2] = anillo[j];
        if ((y1 > lat) !== (y2 > lat) && lon < ((x2 - x1) * (lat - y1)) / (y2 - y1) + x1) dentro = !dentro;
        const ax = (x1 - lon) * M_LON; const ay = (y1 - lat) * M_LAT;
        const bx = (x2 - lon) * M_LON; const by = (y2 - lat) * M_LAT;
        const dx = bx - ax; const dy = by - ay;
        const t = dx || dy ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy))) : 0;
        minimo = Math.min(minimo, Math.hypot(ax + t * dx, ay + t * dy));
      }
    }
  }
  return poligonos.length ? (dentro ? 0 : minimo) : null;
}

const lugarActivo = () => (EXPLORADOR && estado.necesidades.has('lugar_fijo') && estado.lugarFijo) || null;

function metrosLugarBarrio(barrio) {
  const lugar = lugarActivo();
  const forma = lugar && estado.formas?.features.find((f) => f.properties.barrio === barrio);
  return forma ? metrosABarrio(lugar.lon, lugar.lat, forma.geometry) : null;
}

function textoLugarBarrio(barrio) {
  const m = metrosLugarBarrio(barrio);
  if (m == null) return '';
  return m === 0 ? 'Está en el barrio' : `A ${metrosTexto(Math.round(m / 10) * 10)} del borde`;
}

function celdaLugarFijo(aviso) {
  const lugar = lugarActivo();
  if (!lugar || !aviso.ubicacion || aviso.lat == null) return '<span class="fuente">Sin ubicación</span>';
  const texto = metrosTexto(Math.round(metrosEntre(aviso.lon, aviso.lat, lugar.lon, lugar.lat) / 10) * 10);
  return aviso.ubicacion === 'aproximada' ? `${texto} <span class="fuente">aprox.</span>` : texto;
}

function porMes(aviso) {
  if (aviso.expensas == null) return `${dinero(aviso.precio, aviso.moneda)} <span class="fuente">+ expensas sin informar</span>`;
  if (aviso.moneda === 'ARS') return dinero(aviso.precio + aviso.expensas, 'ARS');
  return `${dinero(aviso.precio, aviso.moneda)} + ${dinero(aviso.expensas, 'ARS')}`;
}

// Columnas extra de la tabla según las necesidades: [{ titulo, celda(aviso) }].
function columnasExplorador() {
  if (!EXPLORADOR || !estado.necesidades.size) return [];
  const { columnas, capas } = explorador();
  const extra = Object.entries(COLUMNAS_DISTANCIA)
    .filter(([clave, def]) => columnas.includes(clave) && capas.includes(def.capa))
    .map(([, def]) => ({ titulo: def.titulo(), celda: (a) => celdaDistancia(def, a) }));
  if (columnas.includes('acceso')) extra.unshift({ titulo: 'Acceso según el aviso', celda: celdaAcceso });
  if (columnas.includes('lugar_fijo') && lugarActivo()) extra.unshift({ titulo: 'A tu lugar fijo', celda: celdaLugarFijo });
  const rasgos = Object.keys(RASGOS_TEXTO).filter((k) => columnas.includes(k));
  if (rasgos.length) extra.push({ titulo: 'El texto menciona', celda: (a) => celdaRasgos(rasgos, a) });
  if (columnas.includes('expensas')) {
    extra.push(estado.operacion === 'alquiler'
      ? { titulo: 'Por mes', celda: porMes }
      : { titulo: 'Expensas', celda: (a) => (a.expensas == null ? '<span class="fuente">No informadas</span>' : dinero(a.expensas, 'ARS')) });
  }
  return extra;
}

function renderSegunNecesidades() {
  if (!EXPLORADOR || !estado.necesidades.size) return '';
  const r = explorador();
  const nombres = NECESIDADES.filter((n) => estado.necesidades.has(n.clave)).map((n) => n.nombre);
  const nombreCapa = (c) => CAPAS.find((x) => x.clave === c)?.nombre || c;
  const origen = (c) => (r.origen[c].includes('manual') ? 'Elegida por vos'
    : `Sugerida por «${r.origen[c].map((k) => NECESIDADES.find((n) => n.clave === k).nombre).join('» y «')}»`);
  const filas = r.capas.filter((c) => c !== 'delitos').map((c) => `<dt>${esc(nombreCapa(c))}</dt><dd>${esc(origen(c))}</dd>`);
  const conCercania = estado.avisos.filter((a) => a.cercania).length;
  const sinUbicacion = estado.avisos.filter((a) => !a.ubicacion).length;
  const distancias = r.cercania.length && estado.avisos.length && estado.cercaniaInfo
    ? `<p class="fuente">${conCercania} de ${estado.avisos.length} ${plural(estado.avisos.length, 'aviso tiene', 'avisos tienen')} distancias en la tabla.
        ${sinUbicacion ? `${sinUbicacion} sin ubicación publicada ${plural(sinUbicacion, 'queda', 'quedan')} sin distancia.` : ''}
        ${esc(estado.cercaniaInfo.metodo || '')}</p>` : '';
  return `<section class="segun" aria-labelledby="titulo-segun">
      <h2 id="titulo-segun">Según lo que elegiste</h2>
      <p class="fuente">${esc(enumerar(nombres))}. <button class="boton-texto" type="button" data-abrir-importa>Cambiar</button></p>
      ${filas.length ? `<dl class="hechos">${filas.join('')}</dl>` : ''}
      ${distancias}
      ${r.advertencias.length ? `<ul class="segun-avisos">${r.advertencias.map((a) => `<li>${esc(a)}</li>`).join('')}</ul>` : ''}
    </section>`;
}

const PRESUPUESTO = { 'venta-USD': 110000, 'alquiler-ARS': 800000, 'alquiler-USD': 900 };

// Precios de la primera tanda. Respaldo de costos y decisiones en docs/modelo-de-negocio.md. El precio principal va en
// pesos (precios a consumidores en moneda local) y el dólar es referencia. Hoy no se cobra: los niveles pagos anotan
// el interés con la alerta por mail. El orden pone primero el nivel más caro, que funciona como ancla.
const PRECIOS = {
  tipoCambio: 1450, // ARS por USD de referencia. Fijar el real antes de cobrar.
  actualizado: '20/11/2026',
  cupos: 20,
  niveles: [
    { id: 'acompanado', nombre: 'Buscar acompañado', ars: 42000, usd: 29,
      resumen: 'Además, una persona revisa los avisos que elijas.',
      incluye: ['Todo lo de Buscar', 'Una persona revisa hasta 5 avisos que elijas y te dice qué preguntar antes de visitar'],
      boton: 'Anotarme en la primera tanda' },
    { id: 'buscar', nombre: 'Buscar', ars: 13000, usd: 9, recomendado: true,
      resumen: 'Seguimos tu búsqueda 30 días y te mandamos cada aviso nuevo con su lectura.',
      incluye: ['Hasta 3 avisos nuevos por correo, cada uno con su comparación frente a parecidos y el motivo',
        'Segunda opinión sobre avisos que encuentres en otros portales',
        'Un resumen de cada aviso para reenviar a tu pareja o tu familia'],
      boton: 'Anotarme en la primera tanda' },
    { id: 'explorar', nombre: 'Explorar', ars: 0, usd: 0,
      resumen: 'Mirá dónde te rinde el presupuesto antes de buscar departamento.',
      incluye: ['Barrios donde te rinde el presupuesto y su entorno en el mapa',
        'Avisos con su comparación frente a parecidos del barrio',
        'Alerta por mail, gratis durante el lanzamiento'],
      boton: 'Empezar gratis' },
  ],
};

function precioNivel(n) {
  return n.ars ? `ARS ${numero.format(n.ars)}` : 'Gratis';
}

// Página de precios: titular de resultado, niveles con su precio en pesos y las respuestas a las dudas más probables
// donde aparecen (precio, confianza, privacidad, renovación y garantía).
function renderPrecios() {
  const tarjetas = PRECIOS.niveles.map((n) => `<article class="nivel${n.recomendado ? ' nivel-recomendado' : ''}">
      ${n.recomendado ? '<p class="nivel-marca">Recomendado</p>' : ''}
      <h3>${esc(n.nombre)}</h3>
      <p class="nivel-precio">${precioNivel(n)}</p>
      <p class="nivel-detalle">${n.ars ? `≈ USD ${n.usd} · por búsqueda, 30 días` : 'Sin registrarte'}</p>
      <p class="nivel-resumen">${esc(n.resumen)}</p>
      <ul>${n.incluye.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>
      <button class="${n.recomendado ? 'boton-primario' : 'boton-secundario'}" type="button" data-anotarme="${n.id}">${esc(n.boton)}</button>
    </article>`).join('');
  return `<p class="precios-titular">Seguí buscando donde buscás. Nosotros te decimos qué aviso vale la llamada.</p>
    <p class="nota">Primera tanda: tomamos ${PRECIOS.cupos} búsquedas, porque una persona del equipo prepara cada correo.
      Hoy no cobramos: te anotás con tu mail y te escribimos cuando abra. Recién ahí decidís si pagás.</p>
    <div class="niveles">${tarjetas}</div>
    <ul class="precios-dudas">
      <li><strong>No es una tasación.</strong> Comparamos precios publicados con avisos parecidos del mismo barrio.</li>
      <li><strong>Nadie paga para aparecer.</strong> No cobramos a inmobiliarias ni a anunciantes.</li>
      <li><strong>Tu mail se usa solo para tu búsqueda.</strong> No lo vendemos ni se lo pasamos a inmobiliarias.</li>
      <li><strong>Pago único por 30 días,</strong> sin renovación automática.</li>
      <li><strong>Garantía Tres Avisos:</strong> en la tanda paga, si en 30 días no te llegan al menos 3 avisos nuevos que cumplan lo imprescindible, te devolvemos todo.</li>
      <li><strong>De dónde salen los avisos:</strong> inmobiliarias y portales con permiso de lectura, revisados cada 2 días.</li>
    </ul>
    <p class="fuente">Precio final por búsqueda. El valor en dólares es de referencia, a ARS ${numero.format(PRECIOS.tipoCambio)} por USD (${PRECIOS.actualizado}).</p>`;
}

const VACIO ={ type: 'FeatureCollection', features: [] };
const reducido = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const celular = () => window.matchMedia('(max-width: 820px)').matches;

const numero = new Intl.NumberFormat('es-AR');
const decimal = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 1 });
const dinero = (valor, moneda) => (valor == null ? '—' : `${moneda} ${numero.format(valor)}`);
const plural = (n, uno, varios) => (n === 1 ? uno : varios);
const enumerar = (items) => (items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} y ${items.at(-1)}`);
const porcentaje = (v) => (v == null ? null : Math.round(v * 100));
const mes = (periodo) => {
  const [anio, numeroMes] = periodo.split('-').map(Number);
  return new Intl.DateTimeFormat('es-AR', { month: 'long', year: 'numeric' }).format(new Date(anio, numeroMes - 1, 1));
};
const esc = (texto) => String(texto ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const $ = (selector) => document.querySelector(selector);

/* «Dónde comer»: datos de Google consultados a pedido. No se guardan ni se dibujan en el mapa. */
const TIPOS_LUGAR = [['restaurantes', 'Restaurantes'], ['cafes', 'Cafés'], ['bares', 'Bares']];
const MIN_RESENAS = 200;
const MIN_RESENAS_BAJO = 50;
const LUGARES_VISIBLES = 5;

function lugaresIniciales(tipo) {
  return { tipo, fase: 'inicial', datos: null, minResenas: MIN_RESENAS, todos: false, pedido: 0, mensaje: '' };
}

function leerGuardado() {
  try { return JSON.parse(localStorage.getItem('precio-entorno-filtros')) || {}; } catch { return {}; }
}

function lugarValido(l) {
  const ok = l && typeof l.nombre === 'string' && Number.isFinite(l.lon) && Number.isFinite(l.lat)
    && l.lon > -58.6 && l.lon < -58.3 && l.lat > -34.75 && l.lat < -34.5;
  return ok ? { nombre: l.nombre.slice(0, 120), lon: l.lon, lat: l.lat } : null;
}

const guardado = leerGuardado();
const estado = {
  modo: guardado.modo || 'real',
  operacion: guardado.operacion || 'venta',
  moneda: guardado.moneda || 'USD',
  presupuesto: guardado.presupuesto || 110000,
  superficie: guardado.superficie || 40,
  ambientes: guardado.ambientes || 2,
  ambientesOMas: Boolean(guardado.ambientesOMas),
  verTodos: false,
  prefs: new Set(guardado.prefs || ['subte', 'verdes']),
  necesidades: new Set(EXPLORADOR ? guardado.necesidades || [] : []),
  apagadas: new Set(EXPLORADOR ? guardado.apagadas || [] : []),
  // { nombre, lon, lat } elegido por la persona. Solo en localStorage: no se manda en ningún pedido.
  lugarFijo: EXPLORADOR ? lugarValido(guardado.lugarFijo) : null,
  eligiendoLugar: false,
  hospitales: null, // lista para elegir el lugar fijo; se pide una vez, completa
  nivel: guardado.nivel || 'primario',
  ruido: 'diurno',
  delitos: { anio: '', tipo: 'todos', franja: 'todas', radio: '500', inmueble: '' },
  pedidoDelitos: 0,
  info: null,
  barrios: [],
  comparando: new Set(),
  ordenBarrios: 'avisos',
  formas: null,
  seleccionado: null,
  colectivo: null, // { linea, datos } de la línea de colectivo dibujada en el mapa
  avisos: [],
  cercaniaInfo: null,
  pestana: 'entorno',
  eligiendoAlerta: false, // tras «Activar una alerta», el próximo barrio elegido abre su pestaña de alerta
  interes: '', // nivel pago elegido en Precios ('buscar' o 'acompanado'); viaja con el alta por mail
  capas: new Set(),
  capasDatos: {},
  delitosDatos: null,
  hover: null,
  leyendaCerrada: window.matchMedia('(max-width: 820px)').matches,
  leyendaAbierta: false,
  lugares: lugaresIniciales('restaurantes'),
  parecidos: { barrio: null, datos: null, error: '' },
};

function guardar() {
  const { modo, operacion, moneda, presupuesto, superficie, ambientes, nivel } = estado;
  try {
    localStorage.setItem('precio-entorno-filtros', JSON.stringify(
      { modo, operacion, moneda, presupuesto, superficie, ambientes, ambientesOMas: estado.ambientesOMas, nivel, prefs: [...estado.prefs],
        ...(EXPLORADOR ? { necesidades: [...estado.necesidades], apagadas: [...estado.apagadas], lugarFijo: estado.lugarFijo } : {}) }));
  } catch { /* Sin almacenamiento local: los filtros vuelven a los valores iniciales. */ }
}

function consulta(extra = {}) {
  const { modo, operacion, presupuesto, superficie, ambientes, moneda } = estado;
  return new URLSearchParams({ modo, operacion, presupuesto, superficie, ambientes, moneda,
    ambientes_o_mas: estado.ambientesOMas, ...extra });
}

// Nombres de los campos que la API puede rechazar, para decir cuál revisar.
const CAMPOS_API = { presupuesto: 'el presupuesto', superficie: 'la superficie', ambientes: 'los ambientes',
  moneda: 'la moneda', email: 'el mail', barrio: 'el barrio', texto: 'la descripción' };

// Traduce un fallo a un mensaje que dice qué pasó y qué hacer. El detalle técnico queda en la consola, no en pantalla.
function mensajeDeError(status, cuerpo) {
  const detalle = cuerpo?.detail;
  if (Array.isArray(detalle)) { // validación de FastAPI, en inglés: se nombra el campo y nada más
    const campo = CAMPOS_API[detalle[0]?.loc?.at(-1)];
    return campo ? `Revisá ${campo}: el valor no es válido.` : 'Revisá los filtros: hay un valor que no es válido.';
  }
  if (typeof detalle === 'string' && detalle && !/python -m/.test(detalle)) return detalle;
  if (status === 503) return 'Una parte de los datos todavía no está lista. Probá de nuevo en un rato.';
  if (status >= 500) return 'Lüga tuvo un problema de su lado. Probá de nuevo en un momento.';
  return 'No se pudo completar el pedido. Probá de nuevo.';
}

async function api(ruta, opciones) {
  let respuesta;
  try {
    respuesta = await fetch(ruta, opciones);
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    console.error('Sin respuesta de la API', ruta, error);
    throw new Error('No hay conexión con Lüga. Revisá tu conexión y probá de nuevo.');
  }
  if (!respuesta.ok) {
    let cuerpo = null;
    try { cuerpo = await respuesta.json(); } catch { /* sin cuerpo */ }
    console.error('Error de la API', ruta, respuesta.status, cuerpo);
    throw new Error(mensajeDeError(respuesta.status, cuerpo));
  }
  return respuesta.json();
}

// Bloque de error con «Probar de nuevo». `accion` es una clave de REINTENTOS; `dato` viaja con ella.
function bloqueError(mensaje, accion, dato = '') {
  return `<div class="aviso-error" role="alert"><p>${esc(mensaje)}</p>
    <button class="boton-texto" type="button" data-reintentar="${accion}" data-dato="${esc(dato)}">Probar de nuevo</button></div>`;
}

// Aviso breve arriba del mapa, con «Deshacer» opcional. Reemplaza a las confirmaciones «¿Estás seguro?».
let avisoTimer;
function avisar(texto, deshacer) {
  let caja = $('#aviso-flotante');
  if (!caja) {
    caja = document.createElement('div');
    caja.id = 'aviso-flotante';
    caja.className = 'aviso-flotante';
    caja.setAttribute('role', 'status');
    document.body.append(caja);
  }
  caja.innerHTML = `<span>${esc(texto)}</span>${deshacer ? '<button class="boton-texto" type="button">Deshacer</button>' : ''}`;
  caja.hidden = false;
  caja.querySelector('button')?.addEventListener('click', () => { caja.hidden = true; deshacer(); }, { once: true });
  clearTimeout(avisoTimer);
  avisoTimer = setTimeout(() => { caja.hidden = true; }, deshacer ? 10000 : 6000);
}

/* Textos del entorno */

function datosEntorno(e) {
  if (!e) return {};
  const escuelas = e.escuelas[estado.nivel] || {};
  const totalEscuelas = (escuelas.Estatal || 0) + (escuelas.Privada || 0);
  const ruidoDia = porcentaje(e.ruido.diurno.alto);
  return {
    subte: e.subte_lineas.length ? `Subte ${enumerar(e.subte_lineas)}` : 'Sin estaciones de subte',
    verdes: e.verdes_cantidad
      ? `${e.verdes_cantidad} ${plural(e.verdes_cantidad, 'plaza o parque', 'plazas y parques')}, ${decimal.format(e.verdes_ha)} ha`
      : 'Sin plazas ni parques en el inventario',
    escuelas: `${totalEscuelas} ${plural(totalEscuelas, 'escuela', 'escuelas')} de nivel ${estado.nivel}`,
    salud: `${e.cesac} CeSAC y ${e.hospitales} ${plural(e.hospitales, 'hospital', 'hospitales')}`,
    ruido: ruidoDia == null ? 'Ruido sin cobertura suficiente'
      : `Ruido de día de 70 dBA o más en el ${ruidoDia} % de las celdas`,
    riesgo: `${porcentaje(e.riesgo_hidrico)} % en área de riesgo hídrico`,
    recreacion: e.recreacion ? textoRecreacion(e.recreacion) : 'Recreación sin datos cargados',
  };
}

// «3 cines, 5 teatros y 2 museos»: solo los tipos que el barrio tiene.
function textoRecreacion(r) {
  const partes = Object.entries(RECREACION).filter(([k]) => r[k])
    .map(([k, [varios, uno]]) => `${r[k]} ${plural(r[k], uno, varios)}`);
  return partes.length ? enumerar(partes) : 'Sin cines, teatros, museos ni centros culturales en OpenStreetMap';
}

const totalRecreacion = (r) => Object.keys(RECREACION).reduce((suma, k) => suma + (r[k] || 0), 0);

function lineaEntorno(e) {
  const datos = datosEntorno(e);
  const elegidas = EXPLORADOR ? new Set(explorador().capas) : estado.prefs;
  const partes = PREFERENCIAS.filter((p) => elegidas.has(p.clave)).map((p) => datos[p.clave]);
  return partes.length ? `${partes.join('. ')}.` : '';
}

/* Panel: lista de barrios */

// Insignias redondas de las líneas de subte, con sus colores oficiales.
// A, D y H llevan texto oscuro: en blanco no llegan a 4,5:1 sobre su color.
const LINEAS_CLARAS = ['A', 'D', 'H'];
function insignias(lineas, clase = 'insignia') {
  return lineas.map((l) => `<span class="${clase}${LINEAS_CLARAS.includes(l) ? ' insignia-clara' : ''}" style="background:${SUBTE[l] || '#55626B'}"
    title="Línea ${esc(l)}">${esc(l)}</span>`).join('');
}

function preferenciasComparacion() {
  const claves = EXPLORADOR ? explorador().capas : [...estado.prefs];
  return CAPAS_MAPA.filter((p) => claves.includes(p.clave));
}

function datoComparacion(clave, e) {
  if (!e) return 'Sin datos de entorno';
  const faltante = 'Sin dato';
  const valor = (v, unidad) => v == null ? faltante : `${numero.format(v)} ${unidad}`;
  switch (clave) {
    case 'subte': return e.subte_lineas == null ? faltante : e.subte_lineas.length
      ? `Líneas ${enumerar(e.subte_lineas)} · ${valor(e.subte_estaciones, plural(e.subte_estaciones, 'estación', 'estaciones'))}` : 'Sin estaciones de subte';
    case 'verdes': return e.verdes_cantidad == null || e.verdes_ha == null ? faltante
      : `${numero.format(e.verdes_cantidad)} ${plural(e.verdes_cantidad, 'espacio', 'espacios')} · ${decimal.format(e.verdes_ha)} ha`;
    case 'escuelas': {
      const nivel = e.escuelas?.[estado.nivel];
      return nivel == null ? faltante : `${numero.format((nivel.Estatal || 0) + (nivel.Privada || 0))} de nivel ${estado.nivel}`;
    }
    case 'salud': return e.cesac == null || e.hospitales == null ? faltante : `${e.cesac} CeSAC · ${e.hospitales} hospitales`;
    case 'ruido': return e.ruido?.diurno?.alto == null ? 'Sin cobertura suficiente'
      : `${porcentaje(e.ruido.diurno.alto)} % de celdas con 70 dBA o más de día`;
    case 'riesgo': return e.riesgo_hidrico == null ? faltante : `${porcentaje(e.riesgo_hidrico)} % del área en prevención`;
    case 'recreacion': return e.recreacion == null ? faltante : `${totalRecreacion(e.recreacion)} lugares en OpenStreetMap`;
    case 'colectivos': return e.colectivos == null ? faltante : `${e.colectivos.length} líneas · recorridos de 2019`;
    case 'ciclovias': return e.ciclovias_km == null ? faltante : `${decimal.format(e.ciclovias_km)} km de ciclovías`;
    case 'ecobici': return valor(e.ecobici, 'estaciones');
    case 'bibliotecas': return valor(e.bibliotecas, 'bibliotecas');
    case 'clubes': return valor(e.clubes, 'clubes y polideportivos');
    case 'gimnasios': return valor(e.gimnasios, 'gimnasios en OpenStreetMap');
    default: return faltante;
  }
}

function renderComparacion() {
  const barrios = [...estado.comparando].map((nombre) => estado.barrios.find((b) => b.barrio === nombre)).filter(Boolean);
  const prefs = preferenciasComparacion();
  const fila = (nombre, valores) => `<tr><th scope="row">${esc(nombre)}</th>${valores.map((v) => `<td>${v}</td>`).join('')}</tr>`;
  return `<p class="busqueda-resumen">${contextoAlerta()} · ${textoBusquedaAlerta()}.</p>
    <p class="nota">Los mismos criterios para cada barrio. Cada dato se muestra por separado, sin un puntaje general.</p>
    <p class="fuente">En celular, desplazá la tabla para ver los barrios; el nombre de cada criterio queda fijo.</p>
    <div class="comparacion-tabla" role="region" aria-label="Comparación de barrios según tus preferencias" tabindex="0">
      <table><caption class="solo-lectura">Avisos, precios publicados y preferencias por barrio oficial</caption>
      <thead><tr><th scope="col">Tu búsqueda</th>${barrios.map((b) => `<th scope="col">${esc(b.barrio)}</th>`).join('')}</tr></thead>
      <tbody>
      ${fila('Avisos que encajan', barrios.map((b) => `<strong>${b.coincidencias}</strong> de ${b.avisos} en ${esc(estado.moneda)}`))}
      ${fila('Mediana publicada de los que encajan', barrios.map((b) => b.mediana == null ? 'Sin avisos que encajen' : dinero(b.mediana, estado.moneda)))}
      ${prefs.map((p) => fila(p.nombre, barrios.map((b) => esc(datoComparacion(p.clave, b.entorno))))).join('')}
      ${fila('Seguir con este barrio', barrios.map((b) => `<button class="boton-comparar" type="button" data-elegir-comparado="${esc(b.barrio)}">Ver ${esc(b.barrio)}</button>`))}
      </tbody></table>
    </div>
    ${!prefs.length ? '<p class="nota">No elegiste preferencias de entorno. Podés sumarlas desde «Lo que me importa».</p>' : ''}
    <p class="fuente">Precios de publicación, no tasaciones ni precios de cierre. Las medianas corresponden a los avisos que encajan en cada barrio; pueden describir propiedades distintas.</p>
    ${estado.modo === 'demo' ? '<p class="franja-comparacion">Avisos ficticios de ejemplo. El entorno usa datos abiertos reales.</p>' : ''}
    <details class="comparacion-notas"><summary>Cómo leer los datos y consultar fuentes</summary>
      <p>Datos agregados por barrio oficial. Los conteos de lugares no miden cercanía a un departamento ni calidad del servicio.</p>
      ${prefs.map((p) => `<p><strong>${esc(p.nombre)}.</strong> ${esc(NOTAS[p.clave] || '')}</p>`).join('')}
      <button class="boton-texto" type="button" data-fuentes-comparacion>Ver fuentes y períodos</button>
    </details>`;
}

function actualizarComparador() {
  const n = estado.comparando.size;
  const pie = $('#comparacion-pie');
  if (pie) {
    pie.hidden = !n || Boolean(estado.seleccionado);
    pie.innerHTML = `<span>${n} de 3 barrios elegidos</span><button class="boton-comparar" type="button"${n < 2 ? ' disabled' : ''}>${n < 2 ? 'Elegí otro barrio' : `Comparar ${n} barrios`}</button>`;
  }
  const boton = $('#abrir-comparacion');
  if (!boton) return;
  boton.disabled = n < 2;
  boton.textContent = `Comparar (${n}/3)`;
  $('#resumen-comparacion').textContent = n ? `${n} ${plural(n, 'barrio elegido', 'barrios elegidos')}: ${[...estado.comparando].join(', ')}.` : 'Elegí 2 o 3 barrios para comparar.';
  document.querySelectorAll('[data-comparar]').forEach((input) => {
    input.checked = estado.comparando.has(input.dataset.comparar);
    input.disabled = n >= 3 && !input.checked;
  });
}

function renderLista() {
  const lugar = lugarActivo();
  const orden = estado.ordenBarrios === 'lugar' && !lugar ? 'avisos' : estado.ordenBarrios;
  const cercania = lugar ? Object.fromEntries(estado.barrios.map((b) => [b.barrio, metrosLugarBarrio(b.barrio) ?? Infinity])) : {};
  const con = estado.barrios.filter((b) => b.coincidencias > 0).sort((a, b) =>
    (orden === 'precio' ? a.mediana - b.mediana
      : orden === 'lugar' ? cercania[a.barrio] - cercania[b.barrio]
        : orden === 'nombre' ? 0 : b.coincidencias - a.coincidencias) || a.barrio.localeCompare(b.barrio, 'es'));
  const sin = estado.barrios.filter((b) => !b.coincidencias);
  const total = estado.barrios.reduce((s, b) => s + b.avisos, 0);
  const encajan = con.reduce((s, b) => s + b.coincidencias, 0);
  // Portada con SB7: quien busca es el protagonista y Lüga lo guía. Las cifras salen de los datos cargados.
  const acciones = `<div class="acciones-portada">
      <button class="boton-texto" type="button" id="activar-alerta">Crear una alerta por barrio</button>
      <button class="boton-texto" type="button" data-fuentes>Ver de dónde salen los datos</button>
    </div>`;
  // Idea central (Made to Stick): elegí el barrio antes que el departamento. Todo lo concreto sale de los datos
  // de la búsqueda actual: el ejemplo es el primer barrio de la lista y la proporción se calcula con los totales.
  const ejemplo = con[0];
  const e = ejemplo?.entorno;
  const cadaCuantos = encajan ? Math.round(total / encajan) : 0; // 4.257 / 670 → 1 de cada 6
  const proporcion = cadaCuantos >= 2
    ? `de cada ${cadaCuantos} avisos publicados, ${cadaCuantos - 1} no son para vos. Te mostramos el que sí`
    : 'te mostramos los avisos que encajan';
  const guia = estado.modo === 'demo'
    ? 'Sabemos lo que es saltar entre pestañas de portales. Por eso juntamos avisos y datos abiertos de la Ciudad, cada uno con su fuente y su período. En esta demo, los avisos son de ejemplo.'
    : `Sabemos lo que es saltar entre pestañas de portales: ${proporcion}, con datos abiertos de la Ciudad que citan su fuente y su período.`;
  const sub = ejemplo
    ? `Hasta ${dinero(estado.presupuesto, estado.moneda)}: hay avisos que encajan en ${con.length} ${plural(con.length, 'barrio', 'barrios')}.
      En ${esc(ejemplo.barrio)}, por ejemplo: ${ejemplo.coincidencias} ${plural(ejemplo.coincidencias, 'aviso', 'avisos')},
      mediana ${dinero(ejemplo.mediana, estado.moneda)}${e?.subte_lineas.length ? `, subte ${enumerar(e.subte_lineas)} en el barrio` : ''}.`
    : '';
  const ruidoDia = e ? porcentaje(e.ruido?.diurno?.alto) : null;
  const alrededor = e ? [
    e.subte_estaciones ? `${e.subte_estaciones} ${plural(e.subte_estaciones, 'estación', 'estaciones')} de subte` : '',
    e.verdes_cantidad ? `${decimal.format(e.verdes_ha)} ha de plazas` : '',
    ruidoDia != null ? `ruido fuerte en ${Math.round(ruidoDia / 10)} de cada 10 puntos medidos de día` : '',
  ].filter(Boolean) : [];
  const paso2 = alrededor.length
    ? `Mirá qué hay a la vuelta: en ${esc(ejemplo.barrio)}, ${enumerar(alrededor)}`
    : 'Mirá qué hay a la vuelta de cada barrio: subte, plazas, ruido y delitos registrados';
  const portada = con.length
    ? `<header class="portada">
      <p class="recorrido-etapa">Comparación de barrios</p>
      <h1 class="titulo-lista" id="titulo-vista" tabindex="-1">Elegí dónde buscar</h1>
      <p class="portada-sub"><strong>${con.length} ${plural(con.length, 'barrio', 'barrios')}</strong> con ${numero.format(encajan)} avisos que encajan.</p>
      <p class="busqueda-resumen">${estado.operacion === 'venta' ? 'Comprar' : 'Alquilar'} · ${textoBusquedaAlerta()}.</p>
      <p class="portada-guia">Elegí un barrio para revisar el entorno y los avisos. Después podés guardar tu búsqueda y recibir alertas.</p>
      <details class="como-seguir"><summary>Cómo funciona y qué datos usamos</summary>
        <p>${guia}</p><p>${sub}</p><p>${paso2}.</p>
        <p>${numero.format(encajan)} de ${numero.format(total)} avisos en ${estado.moneda}. Precios publicados, no tasaciones.</p>
        ${acciones}
      </details>
    </header>`
    : `<header class="portada">
      <h1 class="titulo-lista" id="titulo-vista" tabindex="-1">Ningún aviso encaja con estos filtros</h1>
      <p class="portada-sub">Probá subir el presupuesto, bajar la superficie mínima o cambiar los ambientes.
        También podés activar una alerta y te avisamos cuando aparezca algo.</p>
      <p class="busqueda-resumen">${textoBusquedaAlerta()}.</p>${acciones}
    </header>`;
  const eligiendo = estado.eligiendoAlerta
    ? `<p class="eligiendo-alerta" role="status">${estado.interes
      ? `Elegí el barrio de tu búsqueda para anotarte en «${esc(nivelInteres().nombre)}»`
      : 'Elegí el barrio de tu alerta'}
        <button class="boton-texto" type="button" id="cancelar-alerta">Cancelar</button></p>`
    : '';
  const filas = con.map((b) => `
    <li><button class="fila" type="button" data-barrio="${esc(b.barrio)}">
      <span class="fila-nombre">${esc(b.barrio)}</span>
      <span class="fila-cuenta">${b.coincidencias} ${plural(b.coincidencias, 'aviso', 'avisos')}<small>de ${b.avisos}</small></span>
      <span class="fila-mediana">Mediana ${dinero(b.mediana, estado.moneda)}</span>
      <span></span>
      <span class="fila-criterios">${lugar && textoLugarBarrio(b.barrio) ? `<span><strong>Tu lugar fijo</strong><span>${esc(textoLugarBarrio(b.barrio))}</span></span>` : ''}${preferenciasComparacion().map((p) => `<span><strong>${esc(p.nombre)}</strong><span>${esc(datoComparacion(p.clave, b.entorno))}</span></span>`).join('')}</span>
      ${prensaFila(b.barrio)}
    </button><label class="elegir-comparacion"><input type="checkbox" data-comparar="${esc(b.barrio)}" aria-label="Comparar ${esc(b.barrio)}" aria-describedby="resumen-comparacion">Comparar ${esc(b.barrio)}</label></li>`).join('');
  const compactos = sin.map((b) => `<li><button type="button" data-barrio="${esc(b.barrio)}">${esc(b.barrio)} · ${b.avisos}</button></li>`).join('');
  $('#contenido').innerHTML = `
    ${portada}
    ${con.length || estado.comparando.size ? `<section class="comparador" aria-label="Elegir barrios para comparar">
      <p class="comparador-preferencias">${preferenciasComparacion().length ? `Tus prioridades: ${esc(preferenciasComparacion().map((p) => p.nombre).join(' · '))}.` : 'Elegí qué te importa del entorno.'}
        <button class="boton-texto" type="button" data-abrir-importa>Cambiar</button></p>
      <label class="orden-barrios">Ordenar por <select id="orden-barrios">
        <option value="avisos"${orden === 'avisos' ? ' selected' : ''}>Más avisos que encajan</option>
        <option value="precio"${orden === 'precio' ? ' selected' : ''}>Menor mediana publicada</option>
        <option value="nombre"${orden === 'nombre' ? ' selected' : ''}>Nombre del barrio</option>
        ${lugar ? `<option value="lugar"${orden === 'lugar' ? ' selected' : ''}>Más cerca de tu lugar fijo</option>` : ''}
      </select></label>
      <p class="fuente" id="resumen-comparacion" role="status" aria-atomic="true"></p>
      <div class="comparador-acciones"><button class="boton-comparar" id="abrir-comparacion" type="button" disabled>Comparar (0/3)</button>
        <button class="boton-texto" id="limpiar-comparacion" type="button">Limpiar selección</button></div>
    </section>` : ''}
    ${eligiendo}
    ${con.length ? `<ul class="barrios">${filas}</ul>` : ''}
    ${sin.length ? `<details class="sin-coincidencias"${con.length && !estado.eligiendoAlerta ? '' : ' open'}>
      <summary>${sin.length} ${plural(sin.length, 'barrio', 'barrios')} sin avisos que encajen</summary>
      <ul class="lista-compacta">${compactos}</ul></details>` : ''}
    ${renderRadarLista()}`;
  actualizarComparador();
}

/* Panel: ficha del barrio */

const lugaresOsm = (g) => g.restaurantes + g.cafes + g.bares;
const densidadOsm = (e) => (e.area_ha ? (lugaresOsm(e.gastronomia) / e.area_ha) * 100 : null);

function textoGastronomia(e) {
  const g = e.gastronomia;
  const valores = estado.barrios.map((b) => (b.entorno?.gastronomia ? densidadOsm(b.entorno) : null))
    .filter((v) => v != null).sort((a, b) => a - b);
  const medio = Math.floor(valores.length / 2);
  const mediana = valores.length ? (valores.length % 2 ? valores[medio] : (valores[medio - 1] + valores[medio]) / 2) : null;
  const densidad = densidadOsm(e);
  return `${numero.format(lugaresOsm(g))} registrados en OpenStreetMap: ${g.restaurantes} ${plural(g.restaurantes, 'restaurante', 'restaurantes')}, `
    + `${g.cafes} ${plural(g.cafes, 'café', 'cafés')} y ${g.bares} ${plural(g.bares, 'bar', 'bares')}`
    + (densidad == null ? '' : `. ${numero.format(Math.round(densidad))} cada 100 ha`)
    + (mediana == null ? '' : ` (barrio mediano: ${numero.format(Math.round(mediana))})`);
}

const PESTANAS = [['entorno', 'Entorno'], ['avisos', 'Avisos'], ['alerta', 'Crear alerta']];

// Entorno del barrio en piezas: una cifra grande y una frase. Son datos por barrio, nunca un puntaje.
function renderPiezas(e) {
  if (!e) return '<p class="nota">Este barrio todavía no tiene datos de entorno.</p>';
  const pieza = (cifra, texto, clase = '') => `<div class="pieza${clase ? ` ${clase}` : ''}"><p class="cifra">${cifra}</p><p>${texto}</p></div>`;
  const escuelas = e.escuelas[estado.nivel] || {};
  const total = (escuelas.Estatal || 0) + (escuelas.Privada || 0);
  const dia = porcentaje(e.ruido.diurno.alto);
  const noche = porcentaje(e.ruido.nocturno.alto);
  const piezas = [
    e.verdes_cantidad
      ? pieza(`${decimal.format(e.verdes_ha)} ha`, `de plazas y parques, en ${e.verdes_cantidad} ${plural(e.verdes_cantidad, 'espacio', 'espacios')}`, 'pieza-verde')
      : pieza('0', 'plazas y parques en el inventario oficial', 'pieza-verde'),
    e.ciclovias_km != null
      ? pieza(`${decimal.format(e.ciclovias_km)} km`, `de ciclovías${e.ecobici != null ? ` y ${e.ecobici} ${plural(e.ecobici, 'estación', 'estaciones')} de Ecobici` : ''}`)
      : '',
    `<div class="pieza pieza-ancha"><h3>Ruido de día</h3>${dia == null ? '<p>Sin cobertura suficiente en el mapa de ruido.</p>'
      : `<div class="ruido-barra" role="img" aria-label="${dia} % de las celdas con 70 dBA o más"
          style="background:linear-gradient(90deg, #FED976 0 ${100 - dia}%, #F03B20 ${100 - dia}% 100%)"></div>
        <p><strong>${dia} %</strong> de las celdas relevadas tiene 70 dBA o más en la calle${noche == null ? '' : `; de noche, el ${noche} % supera 65 dBA`}.
          No describe el interior de un departamento.</p>`}</div>`,
    pieza(numero.format(total), `escuelas de nivel ${estado.nivel}, ${escuelas.Estatal || 0} de gestión estatal`),
    e.colectivos ? pieza(numero.format(e.colectivos.length), `${plural(e.colectivos.length, 'línea', 'líneas')} de colectivo, según recorridos de 2019`) : '',
    pieza(numero.format(e.cesac + e.hospitales), `centros de salud: ${e.cesac} CeSAC y ${e.hospitales} ${plural(e.hospitales, 'hospital', 'hospitales')}`),
    e.clubes != null ? pieza(numero.format(e.clubes), `clubes de barrio y polideportivos${e.gimnasios != null ? `, y ${e.gimnasios} gimnasios en OpenStreetMap` : ''}`) : '',
    e.bibliotecas != null ? pieza(numero.format(e.bibliotecas), `${plural(e.bibliotecas, 'biblioteca', 'bibliotecas')} de la Red de la Ciudad`) : '',
    pieza(`${porcentaje(e.riesgo_hidrico)} %`, 'de la superficie en área de prevención por riesgo hídrico, según la capa de 2020'),
    e.recreacion ? pieza(numero.format(totalRecreacion(e.recreacion)), totalRecreacion(e.recreacion)
      ? `lugares de recreación: ${esc(textoRecreacion(e.recreacion))}` : 'cines, teatros, museos o centros culturales en OpenStreetMap') : '',
    e.gastronomia ? `<div class="pieza pieza-ancha"><h3>${numero.format(lugaresOsm(e.gastronomia))} cafés, bares y restaurantes</h3>
      <p>${esc(textoGastronomia(e))}</p></div>` : '',
  ].filter(Boolean);
  return `<div class="piezas">${piezas.join('')}</div>
    <p class="fuente">Datos abiertos de Buenos Aires Data, por barrio oficial. Describen el barrio, no un departamento.
      ${e.gastronomia || e.recreacion ? `${enumerar([
    e.gastronomia ? `Cafés, bares y restaurantes${e.gastronomia.captura ? ` (captura del ${fechaCorta(e.gastronomia.captura)})` : ''}` : '',
    e.recreacion ? `${e.gastronomia ? 'c' : 'C'}ines, teatros, museos y centros culturales` : '',
  ].filter(Boolean))}: © colaboradores de OpenStreetMap. La cobertura depende de quién mapea cada zona.` : ''}
      <button class="boton-texto" type="button" data-fuentes>Ver fuentes</button></p>`;
}

function renderFicha() {
  const b = estado.barrios.find((x) => x.barrio === estado.seleccionado);
  if (!b) return;
  const contexto = `${estado.modo}|${estado.operacion}|${b.barrio}|${textoBusquedaAlerta()}`;
  const formularioAnterior = $('#form-alerta');
  const conservar = formularioAnterior?.dataset.contexto === contexto;
  if (conservar && $('#crear-alerta')?.getAttribute('aria-busy') === 'true') return;
  const borrador = conservar ? { email: $('#mail-alerta')?.value || '', consentimiento: $('#consentimiento-alerta')?.checked,
    mensaje: $('#estado-alerta')?.innerHTML || '', clase: $('#estado-alerta')?.className || 'estado',
    invalido: $('#mail-alerta')?.getAttribute('aria-invalid') } : null;
  const focoAnterior = conservar && formularioAnterior.contains(document.activeElement) ? document.activeElement.id : '';
  const e = b.entorno;
  const alquiler = estado.operacion === 'alquiler';
  const visibles = estado.verTodos ? estado.avisos : estado.avisos.slice(0, 25);
  const extra = columnasExplorador();
  const filas = visibles.map((a) => `<tr>
      <td>${dinero(a.precio, a.moneda)}</td>
      <td>${celdaComparacion(a.comparacion, a.moneda)}</td>
      <td>${a.superficie} m²</td>
      <td>${a.ambientes}</td>
      <td>${a.cocheras == null ? 'No informada' : a.cocheras === 0 ? 'Sin cochera' : a.cocheras}</td>
      ${alquiler ? `<td>${a.expensas == null ? '—' : dinero(a.expensas, 'ARS')}</td>` : ''}
      ${extra.map((c) => `<td>${c.celda(a)}</td>`).join('')}
      <td>${a.enlace ? `<a href="${esc(a.enlace)}" target="_blank" rel="noopener">Ver aviso</a>` : 'Ejemplo'}</td>
      <td>${a.pin_utilizable ? `<button class="boton-texto" type="button" data-inmueble="${esc(a.id)}">${estado.delitos.inmueble === a.id ? 'Entorno elegido' : 'Ver registros cerca'}</button>`
        : a.ubicacion ? `<button class="boton-texto" type="button" data-ubicar="${esc(a.id)}" title="Ver en el mapa">Ubicar</button>`
          : '<span class="fuente">Sin ubicación</span>'}</td>
    </tr>`).join('');
  const ubicados = estado.avisos.filter((a) => a.ubicacion).length;
  const resumen = b.coincidencias
    ? `${b.coincidencias} de ${b.avisos} ${plural(b.avisos, 'aviso', 'avisos')} en ${estado.moneda} ${plural(b.coincidencias, 'encaja', 'encajan')} con tu búsqueda. Mediana ${dinero(b.mediana, estado.moneda)}.`
    : 'Ningún aviso encaja con tu búsqueda por ahora. Podés crear la alerta igual.';
  // «N ambientes o más» también se puede guardar: la base y el envío por Make ya lo comparan como mínimo.
  // El patrón del mail es el mismo que valida la API (EMAIL en api.py), así el error aparece antes de enviar.
  const interes = estado.interes && estado.modo === 'real' ? nivelInteres() : null;
  const alerta = `${interes ? `<p class="nota interes-tanda" role="status">Te estás anotando en la primera tanda de
      «${esc(interes.nombre)}» (${precioNivel(interes)}). Dejá tu mail: te escribimos cuando abra, y recién ahí decidís si pagás.
      <button class="boton-texto" type="button" data-quitar-interes>No anotarme</button></p>` : ''}
      <h2>Guardá tu búsqueda en ${esc(b.barrio)}</h2>
      <div class="alerta-resumen"><strong>${estado.operacion === 'venta' ? 'Comprar' : 'Alquilar'} · ${esc(b.barrio)}</strong>
        <p>${textoBusquedaAlerta()}.</p>
        <span>${estado.modo === 'demo' ? 'Datos de ejemplo · avisos ficticios' : 'Datos reales · precios de publicación'}</span></div>
      <p class="nota">Los avisos nuevos que encajen aparecerán en Mis alertas. Los que ya están publicados no generan una alerta.</p>
      ${estado.modo === 'real' ? `<div class="alerta-mail">
        <label class="campo campo-mail"><span class="campo-etiqueta">Mail</span>
          <input type="email" id="mail-alerta" autocomplete="email" inputmode="email" maxlength="254"
            pattern="[^@\\s&lt;&gt;&quot;]+@[^@\\s&lt;&gt;&quot;]+\\.[A-Za-z]{2,}" title="Una dirección como nombre@dominio.com"
            aria-describedby="ayuda-mail estado-alerta" placeholder="nombre@dominio.com"></label>
        <label class="consentimiento" id="consentimiento-campo" hidden>
          <input type="checkbox" id="consentimiento-alerta">
          Acepto que usen este mail solo para mandarme los avisos nuevos de esta búsqueda.</label>
        <p class="fuente" id="ayuda-mail">El mail es opcional. Sin mail, consultá los avisos nuevos en Mis alertas. Si lo dejás, también los recibís por correo, con un enlace para darte de baja.</p>
      </div>` : '<p class="nota">Esta alerta es de ejemplo: usa avisos ficticios y no envía correos.</p>'}
      <button class="boton-primario" type="submit" id="crear-alerta">Crear alerta para ${esc(b.barrio)}</button>`;
  const panel = (clave, contenido) => `<div class="pestana-panel" role="tabpanel" id="panel-${clave}"
    aria-labelledby="pestana-${clave}"${estado.pestana === clave ? '' : ' hidden'}>${contenido}</div>`;
  const pestanas = PESTANAS.map(([clave, nombre]) => `<button type="button" role="tab" id="pestana-${clave}"
    data-pestana="${clave}" aria-controls="panel-${clave}" aria-selected="${estado.pestana === clave}"
    tabindex="${estado.pestana === clave ? 0 : -1}">${clave === 'avisos' ? `${nombre} (${b.coincidencias})` : nombre}</button>`).join('');
  $('#contenido').innerHTML = `
    <article class="ficha">
      <header class="ficha-cabeza">
        <button class="boton-texto volver" type="button" id="volver">Todos los barrios</button>
        <h1 class="titulo-barrio" id="titulo-vista" tabindex="-1">${esc(b.barrio)}</h1>
        ${e ? `<p class="ficha-sub">${e.subte_lineas.length ? `<span class="insignias">${insignias(e.subte_lineas)}</span>` : ''}
          <span>${e.subte_lineas.length ? `${e.subte_estaciones} ${plural(e.subte_estaciones, 'estación', 'estaciones')} de subte, ` : 'Sin subte, '}comuna ${e.comuna},
          ${numero.format(Math.round(e.area_ha))} ha</span></p>` : ''}
        ${b.coincidencias ? `<p class="ficha-precio"><strong>${dinero(b.mediana, estado.moneda)}</strong>
          <span>Mediana de ${b.coincidencias} ${plural(b.coincidencias, 'aviso que encaja', 'avisos que encajan')}, de ${b.avisos}
          ${plural(b.avisos, 'publicado', 'publicados')} en el barrio. Precios publicados, no tasaciones.</span></p>`
          : '<p class="ficha-resumen">Ningún aviso encaja con tu búsqueda por ahora. Podés crear la alerta igual.</p>'}
        <button class="boton-texto ir-alerta" type="button" data-ir-alerta>Crear alerta para ${esc(b.barrio)}</button>
      </header>
      <nav class="pestanas" role="tablist" aria-label="Secciones del barrio">${pestanas}</nav>
      ${panel('entorno', `${renderAnalisisDelitos()}${renderPiezas(e)}${renderColectivos(e)}${renderSegunNecesidades()}
        ${renderParecidos(b.barrio)}${renderLugares(b.barrio)}${renderRadarFicha(b.barrio)}`)}
      ${panel('avisos', `${estado.errorAvisos?.barrio === b.barrio ? bloqueError(estado.errorAvisos.mensaje, 'avisos') : b.coincidencias ? `
        ${extra.length ? `<p class="fuente">Deslizá la tabla hacia la derecha para ver ${enumerar(extra.map((c) => `«${c.titulo}»`))}.</p>` : ''}
        <div class="tabla-desplazable" role="region" aria-label="Avisos que encajan; desplazá para ver todas las columnas" tabindex="0"><table class="avisos">
          <thead><tr><th>Precio publicado</th><th>Frente a parecidos</th><th>Cubierta</th><th>Amb.</th><th>Cocheras</th>${alquiler ? '<th>Expensas</th>' : ''}${extra.map((c) => `<th>${esc(c.titulo)}</th>`).join('')}<th><span hidden>Enlace</span></th><th>Mapa</th></tr></thead>
          <tbody>${filas}</tbody>
        </table></div>
        ${estado.avisos.length > visibles.length ? `<p class="fuente">Se muestran los ${visibles.length} más baratos de ${estado.avisos.length}. <button class="boton-texto" type="button" id="ver-todos">Ver todos</button></p>` : ''}
        <p class="fuente">${estado.modo === 'demo' ? 'Avisos ficticios de ejemplo.' : 'Precios de publicación del catálogo autorizado, no tasaciones ni precios de cierre.'}
          ${estado.modo === 'real' ? `${ubicados} de ${estado.avisos.length} ${plural(estado.avisos.length, 'aviso tiene', 'avisos tienen')} un punto en el mapa, publicado por la fuente sin precisión declarada.` : ''}</p>
        <p class="fuente">${NOTA_COMPARACION}</p>`
        : '<p class="nota">Ningún aviso encaja con tu búsqueda en este barrio. Probá cambiar los filtros o creá una alerta.</p>'}
        ${estado.modo === 'real' ? `<h2>Localizar estacionamientos</h2>
        <p class="fuente">Inventario oficial publicado en 2021, sin fecha de relevamiento informada. Confirmá funcionamiento, horarios, cupos y tarifas con el lugar.</p>
        <form id="buscar-estacionamientos">
          ${camposOrigen()}
          <button type="submit" class="boton-texto">Localizar estacionamientos</button>
        </form><div id="resultado-estacionamientos" role="status"></div>
        <h2>Cocheras en alquiler mensual</h2>
        <form id="buscar-cocheras">
          <label>Moneda <select name="moneda"><option>ARS</option><option>USD</option></select></label>
          <label>Hasta <input name="presupuesto" type="number" min="1" value="250000" required></label>
          ${camposOrigen()}
          <button type="submit" class="boton-texto">Buscar cocheras</button>
        </form><div id="resultado-cocheras" role="status"></div>
        <p class="fuente">Con «Mi ubicación actual», el navegador pide permiso al buscar. La ubicación se usa solo para esa consulta y no se guarda.</p>` : ''}`)}
      ${panel('alerta', `<form id="form-alerta" data-contexto="${esc(contexto)}" novalidate>${alerta}<p class="estado" id="estado-alerta" role="status" aria-atomic="true"></p></form>`)}
    </article>`;
  if (borrador) {
    $('#estado-alerta').innerHTML = borrador.mensaje;
    $('#estado-alerta').className = borrador.clase;
    if ($('#mail-alerta')) {
      $('#mail-alerta').value = borrador.email;
      if (borrador.invalido) $('#mail-alerta').setAttribute('aria-invalid', borrador.invalido);
      $('#consentimiento-alerta').checked = Boolean(borrador.consentimiento);
      actualizarAlerta();
    }
    if (focoAnterior) document.getElementById(focoAnterior)?.focus({ preventScroll: true });
  }
}

function renderColectivos(e) {
  if (!e?.colectivos?.length) return '';
  const elegido = estado.colectivo?.linea;
  const ramales = estado.colectivo?.datos?.properties.ramales || [];
  return `<h2>Colectivos</h2>
    <p class="fuente">Tocá una línea para ver su recorrido en el mapa.</p>
    <div class="lineas-colectivo">${e.colectivos.map((l) => `<button type="button" class="chip" data-colectivo="${esc(l)}"
      aria-pressed="${l === elegido}">${esc(l)}</button>`).join('')}</div>
    ${elegido ? `<p class="estado" role="status">Línea ${esc(elegido)}${estado.colectivo.datos
      ? ` · ${ramales.length} ${plural(ramales.length, 'ramal', 'ramales')}: ${esc(ramales.join(' · '))}` : ' · cargando recorrido…'}
      <button class="boton-texto" type="button" data-quitar-colectivo>Quitar recorrido</button></p>` : ''}
    <p class="fuente">GTFS oficial de colectivos de Buenos Aires Data, con calendario de septiembre a diciembre de 2019.
      Los recorridos pueden haber cambiado: confirmalos en la app oficial o con la empresa.</p>`;
}

async function elegirColectivo(linea) {
  if (estado.colectivo?.linea === linea) { quitarColectivo(); return; }
  estado.colectivo = { linea, datos: null };
  renderPanel();
  renderControles();
  try {
    const datos = await api(`/api/colectivos/${encodeURIComponent(linea)}`);
    if (estado.colectivo?.linea !== linea) return;
    datos.properties.tooltip = `Línea ${linea} · Recorrido del GTFS de 2019 · Tocá para quitarlo`;
    estado.colectivo.datos = datos;
    ponerDatos('colectivo', { type: 'FeatureCollection', features: [datos] });
    const coords = datos.geometry.coordinates.flat();
    const lons = coords.map((c) => c[0]);
    const lats = coords.map((c) => c[1]);
    mapa?.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: 40, maxZoom: 14 });
    if (celular()) plegarPanel(false);
  } catch (error) {
    if (estado.colectivo?.linea === linea) estado.colectivo = null;
    mostrarAvisoMapa(`No se pudo cargar el recorrido de la línea ${linea}. ${error.message}`, 'recorrido', linea);
  }
  renderPanel();
  renderControles();
}

function quitarColectivo() {
  if (!estado.colectivo) return;
  estado.colectivo = null;
  ponerDatos('colectivo', VACIO);
  popup?.remove();
  renderPanel();
  renderControles();
  if (estado.seleccionado) encuadrar(estado.seleccionado);
}

// Origen compartido por las búsquedas de estacionamientos y cocheras.
function camposOrigen() {
  return `<label>Buscar desde <select name="origen"><option value="barrio">Todo el barrio</option>
      <option value="actual">Mi ubicación actual</option>
      <option value="mapa">El centro del mapa</option>
      ${estado.avisos.filter((a) => a.ubicacion).map((a) => `<option value="${esc(a.id)}">Aviso ${esc(a.id)}</option>`).join('')}
    </select></label>
    <label>Radio para búsqueda cercana <select name="radio"><option value="300">300 m</option><option value="500" selected>500 m</option><option value="1000">1 km</option></select></label>`;
}

function enCaba(lat, lon) {
  return lat >= -34.73 && lat <= -34.52 && lon >= -58.54 && lon <= -58.32;
}

function ubicacionActual() {
  if (!navigator.geolocation || !window.isSecureContext) {
    return Promise.reject(new Error('Este navegador no permite consultar la ubicación en esta página. Elegí el centro del mapa.'));
  }
  return new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(
    (p) => resolve({ lat: p.coords.latitude, lon: p.coords.longitude, precision: Math.round(p.coords.accuracy) }),
    (error) => reject(new Error(error.code === 1 ? 'No se autorizó el acceso a la ubicación. Podés usar el centro del mapa.'
      : error.code === 3 ? 'La consulta de ubicación tardó demasiado. Intentá otra vez o usá el mapa.'
        : 'No se pudo obtener tu ubicación. Podés usar el centro del mapa.')),
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }));
}

// Devuelve null para todo el barrio, o el punto de partida de una búsqueda cercana.
async function puntoDeBusqueda(origen, output) {
  if (origen === 'barrio') return null;
  let punto;
  if (origen === 'actual') {
    output.textContent = 'Esperando tu ubicación…';
    punto = await ubicacionActual();
    if (!enCaba(punto.lat, punto.lon)) {
      throw new Error('Tu ubicación está fuera del área de consulta de CABA. Mové el mapa hasta la zona que querés explorar y elegí el centro del mapa.');
    }
    marcarMiUbicacion(punto);
  } else if (origen === 'mapa') {
    if (!mapa) throw new Error('El mapa todavía se está cargando. Probá de nuevo en un momento.');
    const centro = mapa.getCenter();
    punto = { lat: centro.lat, lon: centro.lng };
  } else {
    const aviso = estado.avisos.find((a) => a.id === origen);
    punto = aviso && { lat: aviso.lat, lon: aviso.lon, aviso };
  }
  if (!punto) throw new Error('Elegí una ubicación disponible.');
  if (!enCaba(punto.lat, punto.lon)) {
    throw new Error('La ubicación está fuera del área de consulta de CABA. Mové el mapa hasta la zona que querés explorar.');
  }
  return punto;
}

function notaPrecision(punto, radio) {
  if (punto?.precision == null) return '';
  return `<p class="fuente">Precisión informada por el dispositivo: aproximadamente ${punto.precision} m.${
    punto.precision > radio ? ' Supera el radio elegido; usá el centro del mapa para precisar la búsqueda.' : ''}</p>`;
}

const NOTA_COMPARACION = '«Frente a parecidos» compara el precio publicado por m² cubierto con el de avisos vigentes '
  + 'del mismo barrio y moneda, con ±1 ambiente y superficie cubierta ±25 %. Si el aviso declara antigüedad, '
  + 'se usan los que declaran ±10 años, cuando alcanzan. «Más bajo» o «más alto que la mayoría» significa '
  + 'fuera de la mitad central de esos avisos. Compara precios de publicación: no es una tasación ni dice si conviene.';

const POSICIONES = { debajo: 'Más bajo que la mayoría', dentro: 'En línea', arriba: 'Más alto que la mayoría' };

// Versión en una línea para el pin del mapa.
function textoComparacion(c) {
  if (!c) return '';
  if (!c.posicion) return 'Pocos avisos parecidos para comparar';
  const signo = c.diferencia_pct > 0 ? '+' : c.diferencia_pct < 0 ? '−' : '';
  return `${POSICIONES[c.posicion]} · ${signo}${Math.abs(c.diferencia_pct)} % vs. mediana de ${c.n} ${plural(c.n, 'parecido', 'parecidos')}`;
}

function celdaComparacion(c, moneda) {
  if (!c) return '—';
  if (!c.posicion) return `<span class="fuente" title="${esc(c.motivo || '')}">Pocos parecidos</span>`;
  const signo = c.diferencia_pct > 0 ? '+' : c.diferencia_pct < 0 ? '−' : '';
  const detalle = `${dinero(c.precio_m2, moneda)}/m² · mediana ${dinero(c.mediana_m2, moneda)}/m² · `
    + `mitad central entre ${numero.format(c.p25_m2)} y ${numero.format(c.p75_m2)} · ${enumerar(c.criterios)}`
    + (c.sin_antiguedad ? ' · sin antigüedad: no alcanzaban los parecidos con antigüedad declarada' : '');
  return `<span class="comparacion comparacion-${c.posicion}" title="${esc(detalle)}">${POSICIONES[c.posicion]}</span>
    <span class="fuente comparacion-detalle">${signo}${Math.abs(c.diferencia_pct)} % vs. mediana de ${c.n} ${plural(c.n, 'parecido', 'parecidos')}</span>`;
}

function costoMensual(vivienda, cochera) {
  const totales = {};
  const componentes = [
    [vivienda.precio, vivienda.moneda],
    [cochera.precio, cochera.moneda],
    [vivienda.expensas, 'ARS'],
    [cochera.expensas, cochera.moneda_expensas],
  ];
  for (const [importe, moneda] of componentes) {
    if (importe != null) totales[moneda] = (totales[moneda] || 0) + importe;
  }
  const pendientes = [];
  if (vivienda.expensas == null) pendientes.push('expensas de la vivienda');
  if (cochera.expensas == null) pendientes.push('expensas de la cochera');
  const total = Object.entries(totales).map(([moneda, importe]) => dinero(importe, moneda)).join(' + ');
  return `<p>Vivienda y cochera por mes · ${pendientes.length ? 'Subtotal conocido' : 'Alquileres y expensas'} ${total}.
    ${pendientes.length ? 'Falta informar ' + pendientes.join(' y ') + '.' : ''}</p>`;
}

function textoPrecioParecido(p, barrio) {
  if (!p.coincidencias) return 'Ningún aviso encaja con tu búsqueda';
  const base = `${p.coincidencias} ${plural(p.coincidencias, 'aviso encaja', 'avisos encajan')}, mediana ${dinero(p.mediana, estado.moneda)}`;
  if (p.diferencia_mediana == null) return base;
  if (p.diferencia_mediana === 0) return `${base}, igual que en ${barrio}`;
  return `${base}, ${dinero(Math.abs(p.diferencia_mediana), estado.moneda)} ${p.diferencia_mediana < 0 ? 'menos' : 'más'} que en ${barrio}`;
}

function renderParecidos(barrio) {
  const p = estado.parecidos;
  if (p.barrio !== barrio || (!p.datos && !p.error)) return '';
  if (p.error) return `<section class="parecidos"><h2>Barrios parecidos</h2>${bloqueError(p.error, 'parecidos')}</section>`;
  if (!p.datos.length) return '';
  const elegidas = PREFERENCIAS.filter((x) => estado.prefs.has(x.clave)).map((x) => x.nombre.toLowerCase());
  const items = p.datos.map((x) => `<li class="parecido">
      <button type="button" class="parecido-boton" data-barrio="${esc(x.barrio)}">
        <span class="parecido-nombre">${esc(x.barrio)}</span>
        <span class="parecido-precio">${esc(textoPrecioParecido(x, barrio))}</span>
      </button>
      <ul class="parecido-motivos">
        ${x.parecido_en.map((m) => `<li><span class="motivo-marca" aria-hidden="true">=</span>${esc(m.texto)}</li>`).join('')}
        ${x.diferencias.map((m) => `<li class="motivo-difiere"><span class="motivo-marca" aria-hidden="true">≠</span>${esc(m.texto)}</li>`).join('')}
      </ul>
    </li>`).join('');
  return `<section class="parecidos" aria-labelledby="titulo-parecidos">
      <h2 id="titulo-parecidos">Barrios parecidos</h2>
      <p class="fuente">Por su entorno, no por su precio.${elegidas.length ? ` Pesa doble lo que marcaste: ${esc(enumerar(elegidas))}.` : ''}
        Primero, los que tienen avisos que encajan con tu búsqueda.</p>
      <ol class="lista-parecidos">${items}</ol>
    </section>`;
}

async function cargarParecidos() {
  const barrio = estado.seleccionado;
  if (!barrio) return;
  const params = consulta({ nivel: estado.nivel });
  estado.prefs.forEach((clave) => params.append('prefs', clave));
  try {
    const datos = await api(`/api/barrios/${encodeURIComponent(barrio)}/parecidos?${params}`);
    if (barrio !== estado.seleccionado) return;
    estado.parecidos = { barrio, datos: datos.parecidos, error: '' };
  } catch (error) {
    if (barrio !== estado.seleccionado) return;
    estado.parecidos = { barrio, datos: null, error: `No se pudieron calcular los barrios parecidos. ${error.message}` };
  }
  renderPanel();
}

function renderLugares(barrio) {
  if (estado.modo !== 'real' || !estado.info?.lugares) return '';
  const l = estado.lugares;
  const tipos = TIPOS_LUGAR.map(([clave, nombre]) => `<button type="button" class="chip-lugar" data-lugares-tipo="${clave}"
      aria-pressed="${l.tipo === clave}">${nombre}</button>`).join('');
  const nombreTipo = TIPOS_LUGAR.find(([clave]) => clave === l.tipo)[1].toLowerCase();
  let cuerpo;
  if (l.fase === 'inicial') {
    cuerpo = `<p class="fuente">Se consulta a Google solo cuando lo pedís.</p>
      <button class="boton-secundario" type="button" id="cargar-lugares">Ver los más valorados en Google</button>`;
  } else if (l.fase === 'cargando') {
    cuerpo = '<p class="fuente" role="status">Consultando a Google…</p>';
  } else if (l.fase === 'error') {
    cuerpo = `<p>${esc(l.mensaje)}</p>
      <p class="fuente">Mientras tanto, las capas del mapa siguen disponibles.</p>`;
  } else {
    const filtrados = l.datos.lugares.filter((x) => x.resenas >= l.minResenas);
    const visibles = l.todos ? filtrados : filtrados.slice(0, LUGARES_VISIBLES);
    const filas = visibles.map((x) => `<li class="lugar">
        <span class="lugar-nombre">${esc(x.nombre)}</span>
        <span class="lugar-datos">★ ${decimal.format(x.nota)}, ${numero.format(x.resenas)} ${plural(x.resenas, 'reseña', 'reseñas')}${x.precio ? `, ${esc(x.precio)}` : ''}</span>
        ${x.enlace ? `<a class="lugar-enlace" href="${esc(x.enlace)}" target="_blank" rel="noopener">Abrir en Maps</a>` : ''}
      </li>`).join('');
    cuerpo = filtrados.length
      ? `<ol class="lugares">${filas}</ol>
        ${filtrados.length > visibles.length ? `<button class="boton-texto" type="button" id="lugares-todos">Ver los ${filtrados.length} más valorados</button>` : ''}`
      : `<p>Google no devolvió ${nombreTipo} con al menos ${numero.format(l.minResenas)} reseñas en ${esc(barrio)}.</p>
        ${l.minResenas > MIN_RESENAS_BAJO ? `<button class="boton-texto" type="button" id="lugares-menos">Mostrar los que tienen al menos ${MIN_RESENAS_BAJO}</button>` : ''}`;
    cuerpo += `<p class="fuente">Los más valorados entre los ${l.datos.en_barrio} lugares de ${esc(barrio)} que devolvió Google,
      con al menos ${numero.format(l.minResenas)} reseñas. Calificaciones de usuarios de Google, no de Lüga.
      Se consultan al momento y no se guardan.</p>`;
  }
  return `<section class="lugares-google" aria-labelledby="titulo-lugares">
      <div class="lugares-encabezado"><h2 id="titulo-lugares">Dónde comer</h2><span class="atribucion-google">Google Maps</span></div>
      <div class="chips-lugar" role="group" aria-label="Tipo de lugar">${tipos}</div>
      ${cuerpo}
    </section>`;
}

async function cargarLugares() {
  const barrio = estado.seleccionado;
  if (!barrio) return;
  const l = estado.lugares;
  const pedido = l.pedido + 1;
  Object.assign(l, { fase: 'cargando', pedido, todos: false, minResenas: MIN_RESENAS });
  renderFicha();
  try {
    const datos = await api(`/api/barrios/${encodeURIComponent(barrio)}/lugares?${new URLSearchParams({ tipo: l.tipo, modo: estado.modo })}`);
    if (barrio !== estado.seleccionado || pedido !== estado.lugares.pedido) return;
    if (datos.disponible) Object.assign(l, { fase: 'listo', datos });
    else Object.assign(l, { fase: 'error', mensaje: datos.motivo === 'cupo' ? 'La consulta a Google no está disponible por este mes.' : datos.mensaje });
  } catch (error) {
    if (barrio !== estado.seleccionado || pedido !== estado.lugares.pedido) return;
    Object.assign(l, { fase: 'error', mensaje: `No se pudo consultar a Google: ${error.message}` });
  }
  renderFicha();
}

function renderAnalisisDelitos() {
  if (!estado.capas.has('delitos')) return '';
  const d = estado.delitosDatos;
  if (!d?.disponible) return `<section class="analisis-delitos" aria-live="polite"><h2>Registros y contexto</h2><p class="nota">${esc(d?.motivo || 'Cargando registros…')}</p></section>`;
  const filas = d.resumen_radios.map((r) => `<tr${r.radio_m === Number(estado.delitos.radio) ? ' class="radio-elegido"' : ''}>
    <th scope="row">${r.anio} · ${numero.format(r.radio_m)} m · ${r.tipo === 'robo' ? 'Robo' : 'Hurto'}</th>
    <td>${numero.format(r.diurno)}</td><td>${numero.format(r.nocturno)}</td><td>${numero.format(r.sin_dato)}</td><td>${numero.format(r.total)}</td></tr>`).join('');
  const series = d.resumen_radios.filter((r) => r.radio_m === Number(estado.delitos.radio)
    && (estado.delitos.tipo === 'todos' || r.tipo === estado.delitos.tipo));
  const valor = (r) => estado.delitos.franja === 'todas' ? r.total : r[estado.delitos.franja];
  const maximo = Math.max(1, ...series.map(valor));
  const barras = series.map((r) => `<div class="serie-registros"><span>${r.anio} · ${r.tipo === 'robo' ? 'Robo' : 'Hurto'}</span>
    <div class="barra-registros" aria-hidden="true"><i style="width:${valor(r) / maximo * 100}%"></i></div><strong>${numero.format(valor(r))}</strong></div>`).join('');
  return `<section class="analisis-delitos" aria-live="polite"><h2>Registros y contexto</h2>
    <p class="nota"><strong>Los registros no indican tu probabilidad de sufrir un delito.</strong> Más peatones y actividad pueden concentrar más eventos. Existe subregistro.</p>
    ${d.revision_2025 ? `<p class="revision-fuente">${esc(d.revision_2025)} <a href="${esc(d.revision_url)}" target="_blank" rel="noopener">Ficha oficial</a></p>` : ''}
    <p class="fuente">${esc(d.unidad)} Día: 06–19:59 h. Noche: 20–05:59 h. Sin horario se informa aparte.</p>
    ${d.inmueble ? `<h3>Alrededor del aviso ${esc(d.inmueble.id)}</h3><p class="fuente">Precisión informada del pin: ${d.inmueble.precision_m} m. Los círculos pueden cruzar límites de barrio.</p>
      <figure class="comparacion-registros"><figcaption>Hechos registrados a ${numero.format(Number(estado.delitos.radio))} m · ${esc(estado.delitos.tipo)} · horario ${esc(estado.delitos.franja)}</figcaption>${barras}</figure>
      <details><summary>Los tres radios · día y noche, por año y tipo</summary><div class="tabla-registros"><table class="avisos"><caption>Conteos acumulativos sin filtros de tipo ni franja; no sumar los radios.</caption>
      <thead><tr><th>Año · radio · tipo</th><th>Día</th><th>Noche</th><th>Sin hora</th><th>Total</th></tr></thead><tbody>${filas}</tbody></table></div></details>`
      : '<p class="nota">Elegí «Ver registros cerca» en un aviso con pin preciso para comparar radios de 250, 500 y 1.000 m. Esta vista general usa celdas, no totales por barrio.</p>'}
    <h3>Persistencia entre años</h3><p class="fuente">${esc(d.persistencia.definicion)}</p>
    ${!d.persistencia.disponible ? '<p class="nota">Faltan al menos dos años con los 12 meses observados para evaluar persistencia.</p>' : ''}
    <p class="fuente">Cobertura observada: ${d.cobertura.map((c) => `${c.anio}: ${c.meses_observados.length}/12 meses`).join(' · ')}. Los conteos de años parciales no se anualizan.</p>
    <details><summary>Fuente, calidad y límites</summary><ul class="nota">${d.limitaciones.map((s) => `<li>${esc(s)}</li>`).join('')}</ul>
      <p class="fuente">Robos y hurtos excluidos por falta de coordenadas válidas: ${numero.format(d.calidad.robos_hurtos_sin_pin || 0)}. Sin horario entre los geolocalizados: ${numero.format(d.calidad.robos_hurtos_sin_horario || 0)}. Estos valores corresponden al conjunto de fuentes.</p>
      ${d.fuentes.map((f) => `<p class="fuente">${esc(f.archivo)} · <a href="${esc(f.url)}" target="_blank" rel="noopener">Mapa del Delito CABA</a><br>SHA-256: <span class="huella-fuente">${esc(f.sha256)}</span></p>`).join('')}</details></section>`;
}

/* Radar de tendencias barriales: capa editorial, separada de avisos, delitos y datos de ejemplo. */

const ESTADO_FUENTE = { ok: 'Completa', parcial: 'Parcial', error: 'Falló', restringido: 'Acceso restringido', sin_ejecutar: 'Sin ejecutar' };
const fechaCorta = (iso) => (iso ? new Intl.DateTimeFormat('es-AR', { day: 'numeric', month: 'numeric', year: 'numeric',
  timeZone: 'America/Argentina/Buenos_Aires' }).format(new Date(iso.length === 10 ? `${iso}T12:00:00-03:00` : iso)) : '—');
const fechaHora = (iso) => (iso ? new Intl.DateTimeFormat('es-AR', { day: 'numeric', month: 'numeric', year: 'numeric',
  hour: '2-digit', minute: '2-digit', timeZone: 'America/Argentina/Buenos_Aires' }).format(new Date(iso)) : '—');
const fechaLarga = (iso) => new Intl.DateTimeFormat('es-AR', { day: 'numeric', month: 'long', year: 'numeric',
  timeZone: 'America/Argentina/Buenos_Aires' }).format(new Date(`${iso}T12:00:00-03:00`));

function periodoRadar(r) {
  return `del ${fechaLarga(r.periodo.desde)} al ${fechaLarga(r.periodo.hasta)}`;
}

function fuentesConProblemas(r) {
  return r.fuentes.filter((f) => !['ok', 'parcial'].includes(f.estado));
}

function avisoFuentes(r) {
  const malas = fuentesConProblemas(r);
  const parciales = r.fuentes.filter((f) => f.estado === 'parcial');
  const partes = [];
  if (malas.length) partes.push(`Sin datos de ${enumerar(malas.map((f) => f.medio))} para este período: la recolección ${plural(malas.length, 'falló', 'fallaron')} y eso no significa que no hubo notas.`);
  if (parciales.length) partes.push(`La recolección de ${enumerar(parciales.map((f) => f.medio))} fue parcial.`);
  return partes.length ? `<p class="nota radar-alerta">${esc(partes.join(' '))}</p>` : '';
}

function renderRadarLista() {
  const r = estado.radar;
  if (!r) return '';
  if (!r.disponible) {
    return `<p class="fuente radar-lista">Radar de tendencias barriales: ${esc(r.motivo || 'no está disponible.')}${r.reintentable
      ? ' <button class="boton-texto" type="button" data-reintentar="radar">Probar de nuevo</button>' : ''}</p>`;
  }
  const filas = r.barrios.filter((b) => b.notas || b.aperturas).map((b) => `<tr>
      <th scope="row"><button class="boton-texto" type="button" data-barrio="${esc(b.barrio)}">${esc(b.barrio)}</button></th>
      <td>${b.notas ? `<button class="radar-numero" type="button" data-radar-barrio="${esc(b.barrio)}" data-radar-tipo="notas"
        aria-label="Ver las ${b.notas} ${plural(b.notas, 'nota', 'notas')} sobre ${esc(b.barrio)}">${b.notas}</button>` : '0'}</td>
      <td>${b.aperturas ? `<button class="radar-numero" type="button" data-radar-barrio="${esc(b.barrio)}" data-radar-tipo="aperturas"
        aria-label="Ver las aperturas reportadas en ${esc(b.barrio)}">${b.aperturas}</button>` : '0'}</td></tr>`).join('');
  const sinBarrio = r.sin_barrio.length;
  const problemas = fuentesConProblemas(r).length + r.fuentes.filter((f) => f.estado === 'parcial').length;
  return `<details class="radar radar-lista"${estado.radarAbierto ? ' open' : ''}>
    <summary><span class="radar-titulo" id="titulo-radar">Radar de tendencias barriales</span>
      <span class="radar-resumen">${r.totales.notas} ${plural(r.totales.notas, 'nota', 'notas')} de prensa ·
        ${r.totales.aperturas} ${plural(r.totales.aperturas, 'apertura reportada', 'aperturas reportadas')} ·
        ${fechaCorta(r.periodo.desde)} al ${fechaCorta(r.periodo.hasta)}${problemas ? ' · revisar fuentes' : ''}</span></summary>
    <p class="nota">Notas inmobiliarias publicadas ${periodoRadar(r)} en ${enumerar(r.fuentes.map((f) => f.medio))}.
      ${esc(r.aviso)} Es una capa editorial aparte: no usa los avisos, los delitos ni los datos de ejemplo.</p>
    <p class="fuente">Última actualización: ${fechaHora(r.actualizado)} ·
      <button class="boton-texto" type="button" data-radar-fuentes>Estado de las fuentes</button></p>
    <ul class="radar-fuentes">${r.fuentes.map((f) => `<li class="radar-estado radar-${esc(f.estado)}">
      ${esc(f.medio)}: ${esc(ESTADO_FUENTE[f.estado] || f.estado)}${['ok', 'parcial'].includes(f.estado) ? ` · ${f.notas} ${plural(f.notas, 'nota', 'notas')}` : ''}</li>`).join('')}</ul>
    ${avisoFuentes(r)}
    ${filas ? `<table class="tabla radar-tabla">
      <caption>Barrios con notas centradas en ellos, en orden alfabético. Tocá un número para ver las notas que lo respaldan.</caption>
      <thead><tr><th scope="col">Barrio</th><th scope="col">Notas publicadas</th><th scope="col">Aperturas reportadas</th></tr></thead>
      <tbody>${filas}</tbody></table>`
      : '<p class="nota">Ninguna nota del período se centró en un barrio porteño.</p>'}
    <p class="fuente">Las menciones al pasar y las comparaciones no suman. Una apertura cuenta solo si la nota informa local, dirección y una fecha de apertura dentro del período.
      ${sinBarrio ? `<button class="boton-texto" type="button" data-radar-sin-barrio>${sinBarrio} ${plural(sinBarrio, 'nota', 'notas')} sin barrio asignado</button>` : ''}</p>
  </details>`;
}

function prensaFila(barrio) {
  const fila = estado.radar?.disponible && estado.radar.barrios.find((x) => x.barrio === barrio);
  if (!fila || !(fila.notas || fila.aperturas)) return '';
  const partes = [`${fila.notas} ${plural(fila.notas, 'nota', 'notas')}`];
  if (fila.aperturas) partes.push(`${fila.aperturas} ${plural(fila.aperturas, 'apertura', 'aperturas')}`);
  return `<span class="fila-prensa">En la prensa: ${partes.join(' · ')}</span>`;
}

function renderNotaRadar(n) {
  const republicada = n.republicaciones?.length
    ? `<p class="fuente">También publicada en: ${n.republicaciones.map((x) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.medio)}, ${fechaCorta(x.fecha_publicacion)}</a>`).join(' · ')}</p>` : '';
  return `<li class="radar-nota">
    <p class="radar-meta">${fechaCorta(n.fecha_publicacion)} · ${esc(n.medio)} · ${esc(n.tema_nombre)}</p>
    <a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.titular)}</a>
    <p class="fuente">${esc(n.resumen)}${n.fecha_hecho ? ` Fecha del hecho: ${fechaCorta(n.fecha_hecho)}.` : ''}</p>
    ${republicada}</li>`;
}

function renderAperturaRadar(a) {
  return `<li class="radar-nota">
    <p class="radar-meta">Apertura el ${fechaCorta(a.fecha_apertura)}${a.barrio ? ` · ${esc(a.barrio)}` : ''}</p>
    <strong>${esc(a.local)}</strong>, ${esc(a.direccion)}
    ${a.fechas_informadas.length > 1 ? `<p class="fuente">Las notas informan fechas distintas: ${a.fechas_informadas.map(fechaCorta).join(', ')}.</p>` : ''}
    <p class="fuente">${plural(a.notas.length, 'Lo respalda', 'Lo respaldan')}: ${a.notas.map((n) => `<a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.medio)}, ${fechaCorta(n.fecha_publicacion)}</a>`).join(' · ')}</p></li>`;
}

function coberturaAperturas(barrio) {
  return (estado.radar?.aperturas_sin_conteo || []).filter((a) => a.barrio === barrio);
}

function renderRadarFicha(barrio) {
  const r = estado.radar;
  if (!r?.disponible) return '';
  const d = r.detalle[barrio] || { notas: [], aperturas: [] };
  const fila = r.barrios.find((b) => b.barrio === barrio);
  const extra = coberturaAperturas(barrio);
  return `<section class="radar radar-ficha" aria-labelledby="titulo-prensa">
    <h2 id="titulo-prensa">En la prensa</h2>
    <p class="fuente">Radar de tendencias barriales, ${periodoRadar(r)}. Cobertura de los medios monitoreados, no demanda medida.</p>
    ${avisoFuentes(r)}
    <dl class="hechos"><dt>Notas publicadas</dt><dd>${d.notas.length}</dd><dt>Aperturas reportadas</dt><dd>${d.aperturas.length}</dd></dl>
    ${d.notas.length ? `<ul class="radar-notas">${d.notas.map(renderNotaRadar).join('')}</ul>`
      : '<p class="nota">Ninguna nota del período se centró en este barrio.</p>'}
    ${d.aperturas.length ? `<h3>Aperturas reportadas</h3><ul class="radar-notas">${d.aperturas.map(renderAperturaRadar).join('')}</ul>` : ''}
    ${extra.length ? `<h3>Cobertura de aperturas que no suma</h3><ul class="radar-notas">${extra.map((a) => `<li class="radar-nota">
      ${a.local ? `<strong>${esc(a.local)}</strong>` : 'Local sin nombre identificado'}: ${esc(a.motivo)}.
      <a href="${esc(a.nota.url)}" target="_blank" rel="noopener">${esc(a.nota.medio)}</a></li>`).join('')}</ul>` : ''}
    ${fila?.incidentales ? `<p class="fuente">Además, ${fila.incidentales} ${plural(fila.incidentales, 'nota lo nombra', 'notas lo nombran')} al pasar o como comparación. No suman.</p>` : ''}
  </section>`;
}

function abrirRadar(contenido) {
  $('#radar-contenido').innerHTML = contenido;
  $('#dialogo-radar').showModal();
}

function detalleRadar(barrio, tipo) {
  const r = estado.radar;
  const d = r.detalle[barrio] || { notas: [], aperturas: [] };
  if (tipo === 'aperturas') {
    abrirRadar(`<h3>Aperturas reportadas en ${esc(barrio)}</h3>
      <p class="nota">${periodoRadar(r)}. Cada apertura agrupa las notas que informan el mismo local y la misma dirección. No es un censo: solo incluye lo que publicaron los medios monitoreados.</p>
      <ul class="radar-notas">${d.aperturas.map(renderAperturaRadar).join('')}</ul>`);
    return;
  }
  abrirRadar(`<h3>Notas publicadas sobre ${esc(barrio)}</h3>
    <p class="nota">${periodoRadar(r)}. Notas centradas en el barrio: lo nombran en el titular, la bajada o un subtítulo, o varias veces sin usarlo como comparación.</p>
    <ul class="radar-notas">${d.notas.map(renderNotaRadar).join('')}</ul>`);
}

function detalleSinBarrio() {
  const r = estado.radar;
  abrirRadar(`<h3>Notas sin barrio asignado</h3>
    <p class="nota">${periodoRadar(r)}. Tratan sobre la Ciudad en general, otra ciudad o un tema sin un barrio puntual, o lo nombran de forma ambigua.</p>
    <ul class="radar-notas">${r.sin_barrio.map(renderNotaRadar).join('')}</ul>`);
}

function detalleFuentesRadar() {
  const r = estado.radar;
  abrirRadar(`<h3>Estado de las fuentes</h3>
    <p class="nota">Período ${periodoRadar(r)}. Cada medio se recolecta y se guarda por separado: si uno falla, se conservan sus datos anteriores y la falla se informa.</p>
    <table class="tabla"><thead><tr><th>Medio</th><th>Estado</th><th>Notas</th><th>Recolectado</th></tr></thead><tbody>
    ${r.fuentes.map((f) => `<tr><td><a href="${esc(f.seccion)}" target="_blank" rel="noopener">${esc(f.medio)}</a></td>
      <td>${esc(ESTADO_FUENTE[f.estado] || f.estado)}</td><td>${['ok', 'parcial'].includes(f.estado) ? f.notas : '—'}</td>
      <td>${fechaHora(f.recolectado_en)}</td></tr>`).join('')}</tbody></table>
    ${r.fuentes.map((f) => `<p class="fuente"><strong>${esc(f.medio)}.</strong> ${esc(f.metodo)}
      ${f.cobertura_desde ? ` Los listados llegaron hasta el ${fechaCorta(f.cobertura_desde)}.` : ''}
      ${f.motivo ? ` Observaciones: ${esc(f.motivo)}` : ''}
      ${f.ultimo_intento && f.ultimo_intento.fecha !== f.recolectado_en ? ` Último intento: ${fechaHora(f.ultimo_intento.fecha)}, ${esc(ESTADO_FUENTE[f.ultimo_intento.estado] || f.ultimo_intento.estado)}.` : ''}</p>`).join('')}
    <p class="fuente">Se guardan medio, titular, enlace, fechas, barrios, tema y un resumen propio. No se guarda el texto de las notas ni se leen notas de acceso restringido.</p>`);
}

async function cargarRadar() {
  try {
    estado.radar = await api('/api/radar');
  } catch (error) {
    estado.radar = { disponible: false, reintentable: true, motivo: `no se pudo cargar. ${error.message}` };
  }
}

function renderPanel() {
  const foco = $('#contenido').contains(document.activeElement) ? document.activeElement.id : '';
  if (estado.seleccionado) renderFicha();
  else renderLista();
  if (estado.seleccionado) actualizarComparador();
  if (foco) document.getElementById(foco)?.focus({ preventScroll: true });
  pintarAvisos();
  const salida = $('#estado-resultados');
  if (salida) {
    const con = estado.barrios.filter((b) => b.coincidencias > 0);
    const barrio = estado.barrios.find((b) => b.barrio === estado.seleccionado);
    const mensaje = barrio ? `${barrio.barrio}: ${barrio.coincidencias} avisos que encajan.`
      : `${con.length} barrios con ${con.reduce((s, b) => s + b.coincidencias, 0)} avisos que encajan.`;
    const resumen = `${mensaje} ${contextoAlerta()}. ${textoBusquedaAlerta()}.`;
    if (salida.textContent !== resumen) salida.textContent = resumen;
  }
}

/* Mapa */

// MapLibre pesa unos 210 KB comprimido: se descarga en paralelo con la lista (precargarMapa) y el mapa se crea
// recién después de pintarla, para que no compita con el primer pantallazo. Hasta entonces, `mapa`, `popup` y
// `popupAviso` valen null y las funciones del mapa no hacen nada; prepararMapa() pinta todo al final.
const MAPLIBRE_JS = 'https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js';
let mapa = null;
let mapaListo = null;
let popup = null;
let popupAviso = null;

function cargarMapLibre() {
  if (window.maplibregl) return Promise.resolve();
  return new Promise((resolver, rechazar) => {
    const script = document.createElement('script');
    script.src = MAPLIBRE_JS;
    script.addEventListener('load', resolver, { once: true });
    script.addEventListener('error', () => rechazar(new Error('no se pudo descargar MapLibre')), { once: true });
    document.head.append(script);
  });
}

function crearMapa() {
  mapa = new maplibregl.Map({
    container: 'mapa',
    style: ESTILO,
    center: [-58.445, -34.615],
    zoom: 11.2,
    minZoom: 10,
    maxZoom: 17.5,
    dragRotate: false,
    pitchWithRotate: false,
    attributionControl: { compact: true },
    // Sin el fundido de etiquetas: el mapa no queda redibujando 300 ms después de cada movimiento.
    fadeDuration: 0,
  });
  mapa.touchZoomRotate.disableRotation();
  mapa.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  // Centra el mapa en la ubicación del navegador; después se puede buscar desde «El centro del mapa».
  // La posición queda en el navegador y no se envía al servidor hasta que se pide una búsqueda.
  if (window.isSecureContext && navigator.geolocation) {
    mapa.addControl(new maplibregl.GeolocateControl({
      positionOptions: { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
      fitBoundsOptions: { maxZoom: 16 }, showAccuracyCircle: true, trackUserLocation: false,
    }), 'top-right');
  }
  mapaListo = new Promise((resolver) => mapa.on('load', resolver));
  new ResizeObserver(() => mapa.resize()).observe(document.querySelector('.mapa'));
  popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10, maxWidth: '18rem' });
  // Lista de avisos de un punto, con enlaces. Se cierra a mano al tocar otro lugar del mapa.
  popupAviso = new maplibregl.Popup({ closeButton: true, closeOnClick: false, offset: OFFSET_PIN, maxWidth: '20rem',
    className: 'popup-avisos' });
  popupAviso.on('close', () => { estado.pinAbierto = null; });
}

let marcadorUbicacion = null;
function marcarMiUbicacion({ lat, lon, precision }) {
  if (!mapa) return;
  if (!marcadorUbicacion) {
    const punto = document.createElement('div');
    punto.className = 'mi-ubicacion';
    marcadorUbicacion = new maplibregl.Marker({ element: punto });
  }
  marcadorUbicacion.setLngLat([lon, lat]).addTo(mapa);
  marcadorUbicacion.getElement().title = `Tu ubicación (precisión aproximada ${precision} m)`;
  mapa.flyTo({ center: [lon, lat], zoom: Math.max(mapa.getZoom(), 15) });
}
// Los pines de avisos se dibujan hacia arriba desde el punto: el globo no tiene que taparlos.
const OFFSET_PIN = { top: [0, 4], 'top-left': [0, 4], 'top-right': [0, 4], bottom: [0, -34],
  'bottom-left': [0, -34], 'bottom-right': [0, -34], left: [12, -16], right: [-12, -16] };

// Pin de aviso dibujado en un canvas al doble de resolución: gota con punta, borde y un punto en el centro.
function imagenPin(relleno, borde) {
  const r = 2, margen = 3 * r, ancho = 22 * r, alto = 30 * r;
  const lienzo = document.createElement('canvas');
  lienzo.width = ancho + 2 * margen;
  lienzo.height = alto + 2 * margen;
  const c = lienzo.getContext('2d');
  const cx = lienzo.width / 2, cy = margen + 10.5 * r, radio = 9.5 * r, punta = margen + alto;
  const abertura = Math.acos(radio / (punta - cy)); // tangentes desde la punta al círculo
  const gota = () => {
    c.beginPath();
    c.arc(cx, cy, radio, Math.PI / 2 + abertura, Math.PI * 2.5 - abertura);
    c.lineTo(cx, punta);
    c.closePath();
  };
  c.shadowColor = 'rgba(30, 42, 50, 0.35)';
  c.shadowBlur = 3 * r;
  c.shadowOffsetY = r;
  gota();
  c.fillStyle = relleno;
  c.fill();
  c.shadowColor = 'transparent';
  c.lineWidth = 2 * r;
  c.strokeStyle = borde;
  gota();
  c.stroke();
  c.beginPath();
  c.arc(cx, cy, 3.5 * r, 0, Math.PI * 2);
  c.fillStyle = borde;
  c.fill();
  return c.getImageData(0, 0, lienzo.width, lienzo.height);
}
// La descarga de MapLibre y de las formas arranca junto con la lista (iniciar): el script entra con prioridad baja
// y no demora los datos de los barrios, pero ya está en el navegador cuando la lista termina de pintarse.
let precargaMapa = null;
function precargarMapa() {
  if (!precargaMapa) {
    precargaMapa = { formas: api('/api/mapa/barrios'), libreria: cargarMapLibre() };
    // Si fallan, el error se informa en prepararMapa(); acá se evita el aviso de promesa sin atender y se
    // permite volver a pedirlas.
    const olvidar = () => { precargaMapa = null; };
    precargaMapa.formas.catch(olvidar);
    precargaMapa.libreria.catch(olvidar);
  }
  return precargaMapa;
}

async function prepararMapa() {
  const { formas: pedidoFormas, libreria } = precargarMapa();
  await libreria;
  crearMapa();
  const [formas] = await Promise.all([pedidoFormas, mapaListo]);
  estado.formas = formas;
  mapa.resize();
  if (!estado.seleccionado) encuadrar(null, true);
  // Del mapa base se ocultan edificios, números de calle y lugares: no aportan a elegir barrio y son lo que
  // más cuesta dibujar al mover el mapa (medido en docs/ui-rediseno.md).
  for (const capa of mapa.getStyle().layers) {
    if (/^(poi|building|housenumber)/.test(capa.id)) mapa.setLayoutProperty(capa.id, 'visibility', 'none');
  }
  const simbolo = mapa.getStyle().layers.find((capa) => capa.type === 'symbol')?.id;
  mapa.addSource('barrios', { type: 'geojson', data: formas, promoteId: 'barrio' });
  for (const id of ['delitos', 'radios', 'inmueble', 'colectivo', 'lugar-fijo', ...CAPAS_MAPA.map((c) => c.clave), 'avisos']) {
    // Teselas hasta zoom 16 (por defecto, 18): más cerca se agranda la última, con precisión de centímetros. Cortar
    // las capas grandes (rampas, verdes, garajes) en dos niveles menos es lo que más se nota al acercarse.
    mapa.addSource(id, { type: 'geojson', data: VACIO, maxzoom: 16 });
  }
  const sel = ['boolean', ['feature-state', 'sel'], false];
  const hover = ['boolean', ['feature-state', 'hover'], false];
  mapa.addLayer({
    id: 'barrios-relleno', type: 'fill', source: 'barrios',
    paint: {
      'fill-color': ['interpolate', ['linear'], ['coalesce', ['feature-state', 'r'], 0],
        0, ESCALA_BARRIOS[0], 0.001, ESCALA_BARRIOS[1], 1, ESCALA_BARRIOS[2]],
      'fill-opacity': 0.62,
    },
  }, simbolo);
  const escalaRuido = ['step', ['get', 'tipico'], RUIDO[0][1], ...RUIDO.slice(1).flat()];
  // Ruido: un brillo suave por celda, solo donde la calle llega al umbral (filtro en actualizarCapas).
  mapa.addLayer({ id: 'ruido', type: 'circle', source: 'ruido', filter: ['>=', ['get', 'tipico'], 70],
    paint: { 'circle-color': escalaRuido, 'circle-opacity': 0.42, 'circle-blur': 0.85,
      'circle-radius': ['interpolate', ['exponential', 2], ['zoom'], 12, 9, 15, 34, 17, 80] } }, simbolo);
  // Delitos: el mismo brillo, en gris azulado, sobre las zonas del barrio con más hechos registrados.
  mapa.addLayer({ id: 'delitos', type: 'circle', source: 'delitos',
    paint: { 'circle-color': DELITOS[4], 'circle-opacity': 0.34, 'circle-blur': 0.9,
      'circle-radius': ['interpolate', ['exponential', 2], ['zoom'], 12, 15, 15, 64, 17, 150] } }, simbolo);
  mapa.addLayer({ id: 'riesgo', type: 'fill', source: 'riesgo',
    paint: { 'fill-color': COLOR.riesgo, 'fill-opacity': 0.26 } }, simbolo);
  mapa.addLayer({ id: 'riesgo-borde', type: 'line', source: 'riesgo',
    paint: { 'line-color': COLOR.riesgo, 'line-width': 1 } }, simbolo);
  mapa.addLayer({ id: 'verdes', type: 'fill', source: 'verdes',
    paint: { 'fill-color': COLOR.verdes, 'fill-opacity': 0.5 } }, simbolo);
  mapa.addLayer({ id: 'verdes-borde', type: 'line', source: 'verdes',
    paint: { 'line-color': COLOR.verdes, 'line-width': 0.8 } }, simbolo);
  mapa.addLayer({ id: 'barrios-borde', type: 'line', source: 'barrios',
    paint: {
      'line-color': ['case', sel, '#4B3487', hover, '#6A4FB3', '#FFFFFF'],
      'line-width': ['case', sel, 3.5, hover, 2.4, 1.1],
      'line-opacity': ['case', sel, 1, hover, 0.95, 0.9],
    } });
  // Todas las líneas del barrio, recortadas a su zona; cada color es una línea.
  mapa.addLayer({ id: 'colectivos', type: 'line', source: 'colectivos',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ['get', 'color'], 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 1.5, 15, 3.5],
      'line-opacity': 0.7 } });
  // Recorrido completo de la línea elegida, por encima de las demás y debajo de los puntos.
  mapa.addLayer({ id: 'colectivo', type: 'line', source: 'colectivo',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': COLOR.colectivo, 'line-width': ['interpolate', ['linear'], ['zoom'], 11, 2.5, 15, 5], 'line-opacity': 0.85 } });
  mapa.addLayer({ id: 'escuelas', type: 'circle', source: 'escuelas',
    paint: { 'circle-radius': 4.5, 'circle-color': COLOR.escuela, 'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': 1.2 } });
  mapa.addLayer({ id: 'salud', type: 'circle', source: 'salud',
    paint: { 'circle-radius': ['match', ['get', 'kind'], 'hospital', 7.5, 5.5],
      'circle-color': ['match', ['get', 'kind'], 'hospital', COLOR.hospital, COLOR.cesac],
      'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': 1.5 } });
  mapa.addLayer({ id: 'subte', type: 'circle', source: 'subte',
    paint: { 'circle-radius': 6.5, 'circle-color': ['match', ['get', 'line'], ...Object.entries(SUBTE).flat(), '#55626B'],
      // Borde oscuro y más grueso: estación con ascensores informados.
      'circle-stroke-color': ['case', ['>', ['coalesce', ['get', 'elevators'], 0], 0], COLOR.ascensor, '#FFFFFF'],
      'circle-stroke-width': ['case', ['>', ['coalesce', ['get', 'elevators'], 0], 0], 2.5, 2] } });
  mapa.addLayer({ id: 'estacionamiento', type: 'circle', source: 'estacionamiento',
    // Toda la ciudad: puntos chicos con el mapa alejado para que se lean los 2.700 garajes.
    paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 11, 2.5, 14, 4.5, 16, 6],
      'circle-color': COLOR.estacionamiento,
      'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 11, 0.5, 14, 1.5] } });
  mapa.addLayer({ id: 'ciclovias', type: 'line', source: 'ciclovias', layout: { 'line-cap': 'round' },
    paint: { 'line-color': COLOR.ciclovias, 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 1.5, 16, 4] } },
  'escuelas'); // debajo de las capas de puntos
  for (const id of ['rampas', 'ecobici', 'bibliotecas']) {
    mapa.addLayer({ id, type: 'circle', source: id,
      paint: { 'circle-radius': { bibliotecas: 6, ecobici: 4.5, rampas: 3 }[id], 'circle-color': COLOR[id],
        'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': 1.5 } });
  }
  mapa.addLayer({ id: 'recreacion', type: 'circle', source: 'recreacion',
    paint: { 'circle-radius': 6, 'circle-color': ['match', ['get', 'kind'],
      ...Object.entries(RECREACION).flatMap(([k, [, , color]]) => [k, color]), '#55626B'],
    'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': 1.5 } });
  for (const id of ['clubes', 'gimnasios']) {
    mapa.addLayer({ id, type: 'circle', source: id,
      paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 11, 3, 14, 5, 16, 6.5], 'circle-color': COLOR[id],
        'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 11, 0.6, 14, 1.5] } });
  }
  // Avisos que encajan: un pin con punta, la única forma del mapa que no es un círculo, para que no se pierda
  // entre las capas de puntos. Relleno si la ubicación publicada es coherente con el barrio, hueco si es
  // aproximada. Un punto con varios avisos (un mismo edificio) se dibuja más grande. Va encima de todo.
  mapa.addImage('pin-aviso', imagenPin(COLOR.aviso, '#FFFFFF'), { pixelRatio: 2 });
  mapa.addImage('pin-aviso-hueco', imagenPin('#FFFFFF', COLOR.aviso), { pixelRatio: 2 });
  const porCantidad = ['interpolate', ['linear'], ['get', 'cantidad'], 1, 1, 5, 1.15, 20, 1.3];
  mapa.addLayer({ id: 'avisos', type: 'symbol', source: 'avisos',
    layout: {
      'icon-image': ['case', ['get', 'aproximada'], 'pin-aviso-hueco', 'pin-aviso'],
      'icon-size': ['interpolate', ['linear'], ['zoom'], 12, ['*', 0.7, porCantidad], 15, porCantidad],
      'icon-anchor': 'bottom', 'icon-offset': [0, 3], // la imagen tiene 3 px de margen debajo de la punta
      'icon-allow-overlap': true, 'icon-ignore-placement': true,
    } });
  mapa.addLayer({ id: 'radios', type: 'line', source: 'radios',
    paint: { 'line-color': '#6A4FB3', 'line-width': ['case', ['get', 'seleccionado'], 2.5, 1], 'line-dasharray': [3, 2] } });
  mapa.addLayer({ id: 'inmueble', type: 'circle', source: 'inmueble',
    paint: { 'circle-radius': 7, 'circle-color': '#6A4FB3', 'circle-stroke-color': '#FFFFFF', 'circle-stroke-width': 2 } });
  // El lugar fijo: un anillo oscuro con centro blanco, distinto de los pines de avisos y de los puntos de capas.
  mapa.addLayer({ id: 'lugar-fijo', type: 'circle', source: 'lugar-fijo',
    paint: { 'circle-radius': 9, 'circle-color': '#FFFFFF', 'circle-stroke-color': '#1E2A32', 'circle-stroke-width': 4 } });

  const puntos = ['subte', 'salud', 'escuelas', 'estacionamiento', 'clubes', 'gimnasios', 'ecobici', 'bibliotecas', 'rampas', 'recreacion'];
  const conTexto = [...puntos, 'colectivo', 'colectivos', 'ciclovias', 'verdes', 'riesgo', 'ruido', 'delitos'];

  let movimiento = null;
  mapa.on('mousemove', (evento) => {
    if (!movimiento) requestAnimationFrame(() => { const e = movimiento; movimiento = null; alMoverMouse(e); });
    movimiento = evento;
  });
  // Una sola consulta por cuadro con todas las capas (antes eran tres). MapLibre devuelve primero lo que está más
  // arriba, así que el pin, el elemento y el barrio salen de la misma lista.
  const capasHover = ['avisos', ...conTexto, 'barrios-relleno'];
  const conTextoSet = new Set(conTexto);
  let textoPopup = null;
  let offsetPopup = null;
  const mostrarPopup = (lngLat, texto, offset) => {
    if (offsetPopup !== offset) { popup.setOffset(offset); offsetPopup = offset; }
    popup.setLngLat(lngLat);
    if (textoPopup !== texto) { popup.setHTML(esc(texto)); textoPopup = texto; }
    if (!popup.isOpen()) popup.addTo(mapa);
  };
  const ocultarPopup = () => { if (popup.isOpen()) popup.remove(); };
  popup.on('close', () => { textoPopup = null; });
  let cursor = '';
  const ponerCursor = (valor) => { if (cursor !== valor) { cursor = valor; mapa.getCanvas().style.cursor = valor; } };
  const alMoverMouse = (evento) => {
    // Mientras se arrastra o se hace zoom, consultar el mapa en cada cuadro compite con el dibujo.
    if (!evento || mapa.isMoving()) return;
    if (estado.eligiendoLugar) { ocultarPopup(); ponerCursor('crosshair'); return; }
    const debajo = mapa.queryRenderedFeatures(evento.point, { layers: capasHover });
    const barrio = debajo.find((f) => f.layer.id === 'barrios-relleno');
    marcarHover(barrio ? barrio.id : null, 'mapa');
    const pin = debajo[0]?.layer.id === 'avisos' ? debajo[0] : null;
    if (pin) {
      ponerCursor('pointer');
      if (estado.pinAbierto === pin.properties.clave) ocultarPopup();
      else mostrarPopup(pin.geometry.coordinates, textoPin(pin.properties.clave), OFFSET_PIN);
      return;
    }
    const elemento = debajo.find((f) => conTextoSet.has(f.layer.id));
    const texto = elemento ? textoElemento(elemento) : (barrio && !estado.seleccionado ? textoBarrio(barrio.id) : null);
    ponerCursor(barrio || elemento ? 'pointer' : '');
    if (texto) mostrarPopup(evento.lngLat, texto, 10);
    else ocultarPopup();
  };
  mapa.on('mouseout', () => { popup?.remove(); marcarHover(null, 'mapa'); });
  mapa.on('click', (evento) => {
    if (estado.eligiendoLugar) {
      fijarLugar({ nombre: 'Punto marcado en el mapa', lon: evento.lngLat.lng, lat: evento.lngLat.lat });
      return;
    }
    const pin = mapa.queryRenderedFeatures(evento.point, { layers: ['avisos'] })[0];
    if (pin) {
      abrirPin(pin.properties.clave);
      return;
    }
    popupAviso?.remove();
    if (estado.colectivo && mapa.queryRenderedFeatures(evento.point, { layers: ['colectivo'] }).length) {
      quitarColectivo();
      return;
    }
    const linea = mapa.queryRenderedFeatures(evento.point, { layers: ['colectivos'] })[0];
    if (linea) {
      elegirColectivo(String(linea.properties.linea));
      return;
    }
    const elemento = mapa.queryRenderedFeatures(evento.point, { layers: conTexto })[0];
    if (elemento) {
      mostrarPopup(evento.lngLat, textoElemento(elemento), 10);
      return;
    }
    const barrio = mapa.queryRenderedFeatures(evento.point, { layers: ['barrios-relleno'] })[0];
    if (barrio && barrio.id !== estado.seleccionado) seleccionar(barrio.id);
  });
  pintarAvisos();
}

/* Pines de los avisos */

function claveUbicacion(a) {
  return `${a.lat.toFixed(6)},${a.lon.toFixed(6)}`;
}

// estado.avisos siempre se reemplaza entero (nunca se modifica en el lugar): los grupos se calculan una vez por lista.
let gruposCalculados = { avisos: null, grupos: new Map() };
function gruposAvisos() {
  if (gruposCalculados.avisos === estado.avisos) return gruposCalculados.grupos;
  const grupos = new Map();
  for (const a of estado.avisos) {
    if (!a.ubicacion) continue;
    const clave = claveUbicacion(a);
    if (!grupos.has(clave)) grupos.set(clave, []);
    grupos.get(clave).push(a);
  }
  gruposCalculados = { avisos: estado.avisos, grupos };
  return grupos;
}

// renderPanel() llama a esto en cada cambio del panel; los pines se reenvían al mapa solo si cambió la lista.
let pinesPintados;
function pintarAvisos() {
  const fuente = mapa?.getSource('avisos');
  if (!fuente) return;
  const grupos = estado.seleccionado ? gruposAvisos() : new Map();
  const firma = estado.seleccionado ? estado.avisos : null;
  if (pinesPintados !== firma) {
    pinesPintados = firma;
    fuente.setData({ type: 'FeatureCollection', features: [...grupos].map(([clave, lista]) => ({
      type: 'Feature', geometry: { type: 'Point', coordinates: [lista[0].lon, lista[0].lat] },
      properties: { clave, cantidad: lista.length, aproximada: lista.every((a) => a.ubicacion === 'aproximada') },
    })) });
  }
  if (estado.pinAbierto && !grupos.has(estado.pinAbierto)) popupAviso?.remove();
}

function textoPin(clave) {
  const lista = gruposAvisos().get(clave) || [];
  if (lista.length === 1) {
    const a = lista[0];
    return `${dinero(a.precio, a.moneda)} · ${a.superficie} m² · ${a.ambientes} amb.${a.ubicacion === 'aproximada' ? ' Ubicación aproximada.' : ''}`;
  }
  const precios = lista.map((a) => a.precio);
  return `${lista.length} avisos en este punto, de ${dinero(Math.min(...precios), lista[0].moneda)} a ${dinero(Math.max(...precios), lista[0].moneda)}. Tocá para verlos.`;
}

function abrirPin(clave) {
  const lista = gruposAvisos().get(clave);
  if (!lista || !popupAviso) return;
  popup?.remove();
  estado.pinAbierto = clave;
  const filas = lista.map((a) => `<li><strong>${esc(dinero(a.precio, a.moneda))}</strong> · ${a.superficie} m² · ${a.ambientes} amb.
    ${a.enlace ? `<a href="${esc(a.enlace)}" target="_blank" rel="noopener">Ver aviso</a>` : ''}
    <span class="pin-comparacion">${textoComparacion(a.comparacion)}</span></li>`).join('');
  const nota = (lista.every((a) => a.ubicacion === 'aproximada')
    ? 'Ubicación aproximada: el punto publicado cae a entre 150 y 500 m del barrio.'
    : 'Punto publicado por la fuente, sin precisión declarada.')
    + ' Frente a parecidos: precio por m² contra avisos del barrio de tamaño parecido; no es una tasación.';
  popupAviso.setLngLat([lista[0].lon, lista[0].lat])
    .setHTML(`<p class="pin-titulo">${lista.length === 1 ? '1 aviso' : `${lista.length} avisos`} en este punto</p>
      <ul class="pin-lista">${filas}</ul><p class="pin-nota">${nota}</p>`)
    .addTo(mapa);
  estado.pinAbierto = clave;
}

function textoBarrio(nombre) {
  const b = estado.barrios.find((x) => x.barrio === nombre);
  if (!b) return nombre;
  return `${nombre}: ${b.coincidencias} ${plural(b.coincidencias, 'aviso encaja', 'avisos encajan')}`;
}

function textoElemento(f) {
  const p = f.properties;
  if (f.layer.id === 'ruido') {
    return `Nivel exterior típico de ${p.tipico} a ${p.tipico + 5} dBA. El máximo en la celda es de ${p.maximo} a ${p.maximo + 5} dBA.`;
  }
  if (f.layer.id === 'delitos') {
    const detalle = JSON.parse(typeof p.por_anio === 'string' ? p.por_anio : JSON.stringify(p.por_anio));
    const altos = JSON.parse(typeof p.anios_altos === 'string' ? p.anios_altos : JSON.stringify(p.anios_altos));
    return `Celda de 200 m · ${Object.entries(detalle).map(([y, n]) => `${y}: ${n}`).join(' · ')} hechos. ${estado.delitos.tipo}; ${estado.delitos.franja}. Años de concentración alta: ${altos.join(', ') || 'ninguno'}. La celda puede cruzar el círculo; los conteos por radio usan cada registro.`;
  }
  return `${String(p.tooltip || p.name || '').split(' · ').join('. ')}.`.replace(/\.\.$/, '.');
}

function marcarHover(nombre, origen) {
  if (estado.hover === nombre) return;
  if (estado.hover && mapa?.getSource('barrios')) mapa.setFeatureState({ source: 'barrios', id: estado.hover }, { hover: false });
  estado.hover = nombre;
  if (nombre && mapa?.getSource('barrios')) mapa.setFeatureState({ source: 'barrios', id: nombre }, { hover: true });
  if (origen === 'mapa') {
    document.querySelectorAll('.fila.resaltada').forEach((fila) => fila.classList.remove('resaltada'));
    if (nombre) document.querySelector(`.fila[data-barrio="${CSS.escape(nombre)}"]`)?.classList.add('resaltada');
  }
}

function pintarCoropletas() {
  if (!mapa?.getSource('barrios')) return;
  const maximo = Math.max(1, ...estado.barrios.map((b) => b.coincidencias));
  for (const b of estado.barrios) {
    mapa.setFeatureState({ source: 'barrios', id: b.barrio }, { r: b.coincidencias ? b.coincidencias / maximo : 0 });
  }
  mapa.setPaintProperty('barrios-relleno', 'fill-opacity',
    estado.seleccionado ? ['case', ['boolean', ['feature-state', 'sel'], false], 0, 0.28] : 0.62);
}

function limites(nombre) {
  const feature = estado.formas.features.find((f) => f.properties.barrio === nombre);
  const puntos = feature.geometry.coordinates.flatMap((poligono) => poligono[0]);
  const lons = puntos.map((p) => p[0]);
  const lats = puntos.map((p) => p[1]);
  return [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]];
}

function limitesCiudad() {
  const puntos = estado.formas.features.flatMap((f) => f.geometry.coordinates.flatMap((poligono) => poligono[0]));
  const lons = puntos.map((p) => p[0]);
  const lats = puntos.map((p) => p[1]);
  return [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]];
}

// Lo que tapa el mapa: la barra de filtros arriba, la hoja a la izquierda (abajo en celular) y las capas abajo.
function margenesLibres() {
  const alto = mapa.getContainer().clientHeight;
  const barra = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--barra-real')) || 60;
  const hoja = document.querySelector('#panel')?.getBoundingClientRect();
  const controles = document.querySelector('.mapa-arriba')?.getBoundingClientRect().height || 44;
  const top = Math.min(barra + 30, alto * 0.35);
  if (celular()) {
    return { top, bottom: Math.max(24, Math.min(alto - top - 80, Math.round(alto - (hoja?.top ?? alto * 0.72)) + controles + 24)), left: 24, right: 24 };
  }
  return { top, bottom: Math.max(24, Math.min(alto - top - 80, controles + 32)), left: Math.round((hoja?.right ?? 460) + 24), right: 70 };
}

function encuadrar(nombre, inmediato = false) {
  if (!estado.formas || !mapa) return;
  const duracion = reducido || inmediato ? 0 : 700;
  mapa.fitBounds(nombre ? limites(nombre) : limitesCiudad(), { padding: margenesLibres(), duration: duracion });
}

function encuadrarPin(pin) {
  if (!mapa) return;
  const dlat = 1100 / 111320;
  const dlon = dlat / Math.cos(pin.lat * Math.PI / 180);
  mapa.fitBounds([[pin.lon - dlon, pin.lat - dlat], [pin.lon + dlon, pin.lat + dlat]], {
    padding: margenesLibres(), duration: reducido ? 0 : 500,
  });
}

/* Capas del barrio elegido */

/* Mandar un GeoJSON al mapa obliga a MapLibre a volver a cortarlo en teselas en su worker: con los garajes de toda la
   ciudad o las rampas son cientos de miles de vértices. Antes, prender una capa reenviaba todas las demás; ahora solo
   se manda la fuente cuyo contenido cambió (mismo objeto = mismos datos). */
const datosFuente = new Map();
let ultimoUmbralRuido = null;
function ponerDatos(id, datos) {
  const fuente = mapa?.getSource(id);
  if (!fuente || datosFuente.get(id) === datos) return;
  datosFuente.set(id, datos);
  fuente.setData(datos);
}

let inmuebleMarcado = null;
function puntoInmueble({ lon, lat }) {
  if (inmuebleMarcado?.lon !== lon || inmuebleMarcado?.lat !== lat) {
    inmuebleMarcado = { lon, lat, datos: { type: 'FeatureCollection', features: [{ type: 'Feature',
      geometry: { type: 'Point', coordinates: [lon, lat] }, properties: {} }] } };
  }
  return inmuebleMarcado.datos;
}

function claveCapa(clave) {
  // Los garajes cubren toda la ciudad: se piden una vez, sin importar el barrio.
  return [CAPAS_CIUDAD.has(clave) ? 'CABA' : estado.seleccionado, clave, clave === 'escuelas' ? estado.nivel : '', clave === 'ruido' ? estado.ruido : ''].join('|');
}

async function actualizarCapas() {
  const barrio = estado.seleccionado;
  const fijas = CAPAS_MAPA.map((c) => c.clave);
  if (!barrio) {
    fijas.concat('delitos', 'radios', 'inmueble', 'colectivo').forEach((id) => ponerDatos(id, VACIO));
    estado.colectivo = null;
    renderControles();
    renderLeyenda();
    return;
  }
  const faltan = fijas.filter((c) => estado.capas.has(c) && !estado.capasDatos[claveCapa(c)]);
  try {
    if (faltan.length) {
      const pedido = new URLSearchParams({ barrio, nivel: estado.nivel, ruido: estado.ruido });
      faltan.forEach((c) => pedido.append('capas', c));
      const respuesta = await api(`/api/mapa/capas?${pedido}`);
      if (barrio !== estado.seleccionado) return;
      faltan.forEach((c) => { estado.capasDatos[claveCapa(c)] = respuesta[c]; });
    }
    if (estado.capas.has('delitos') && !await cargarDelitos()) return;
  } catch (error) {
    mostrarAvisoMapa(`No se pudieron cargar las capas del mapa. ${error.message}`, 'capas');
  }
  if (barrio !== estado.seleccionado) return;
  for (const c of fijas) ponerDatos(c, estado.capas.has(c) ? estado.capasDatos[claveCapa(c)] || VACIO : VACIO);
  const umbralRuido = estado.ruido === 'diurno' ? 70 : 65;
  if (mapa?.getLayer('ruido') && umbralRuido !== ultimoUmbralRuido) {
    ultimoUmbralRuido = umbralRuido;
    mapa.setFilter('ruido', ['>=', ['get', 'tipico'], umbralRuido]);
  }
  const delitos = estado.capas.has('delitos') && estado.delitosDatos?.disponible ? estado.delitosDatos.celdas : VACIO;
  ponerDatos('delitos', delitos);
  const d = estado.capas.has('delitos') && estado.delitosDatos?.disponible ? estado.delitosDatos : null;
  ponerDatos('radios', d?.radios || VACIO);
  ponerDatos('inmueble', d?.inmueble ? puntoInmueble(d.inmueble) : VACIO);
  renderControles();
  renderLeyenda();
  renderPanel();
}

async function cargarDelitos() {
  const secuencia = ++estado.pedidoDelitos;
  const pedido = new URLSearchParams({ barrio: estado.seleccionado, modo: estado.modo, operacion: estado.operacion });
  for (const clave of ['tipo', 'franja', 'radio', 'inmueble']) if (estado.delitos[clave]) pedido.set(clave, estado.delitos[clave]);
  if (estado.delitos.anio && estado.delitos.anio !== 'persistencia') pedido.set('anio', estado.delitos.anio);
  const datos = await api(`/api/delitos/concentracion?${pedido}`);
  if (secuencia !== estado.pedidoDelitos) return false;
  if (datos.disponible) {
    if (!estado.delitos.anio) estado.delitos.anio = datos.persistencia.disponible ? 'persistencia' : String(datos.anios.at(-1));
    const persistencia = estado.delitos.anio === 'persistencia';
    for (const f of datos.celdas.features) {
      const p = f.properties;
      p.hechos = persistencia ? p.anios_altos.length : (p.por_anio[estado.delitos.anio] || 0);
      p.paso = persistencia ? Math.min(4, p.hechos) : [5, 10, 20, 50].filter((n) => p.hechos >= n).length;
    }
    datos.celdas.features = datos.celdas.features.filter((f) => persistencia ? f.properties.persistente : f.properties.hechos > 0);
    zonasAltas(datos.celdas, estado.seleccionado, !persistencia);
  }
  estado.delitosDatos = datos;
  return true;
}

// ¿El punto cae dentro del barrio? Ray casting sobre su polígono oficial, con agujeros.
function dentroDelBarrio(nombre) {
  const forma = estado.formas?.features.find((f) => f.properties.barrio === nombre)?.geometry;
  if (!forma) return () => true;
  const poligonos = forma.type === 'Polygon' ? [forma.coordinates] : forma.coordinates;
  const enAnillo = ([x, y], anillo) => {
    let dentro = false;
    for (let a = 0, b = anillo.length - 1; a < anillo.length; b = a++) {
      const [xa, ya] = anillo[a];
      const [xb, yb] = anillo[b];
      if ((ya > y) !== (yb > y) && x < ((xb - xa) * (y - ya)) / (yb - ya) + xa) dentro = !dentro;
    }
    return dentro;
  };
  return (punto) => poligonos.some(([exterior, ...agujeros]) => enAnillo(punto, exterior) && !agujeros.some((h) => enAnillo(punto, h)));
}

/* Celdas de delitos → punto en su centro, solo dentro del barrio. Con `soloAltas`, se queda con el 20 % de las celdas
   con más hechos; en la vista de persistencia ya vienen solo las que se repiten entre años. */
function zonasAltas(celdas, barrio, soloAltas) {
  const dentro = dentroDelBarrio(barrio);
  const puntos = celdas.features.map((f) => {
    if (f.geometry?.type !== 'Polygon') return f;
    const anillo = f.geometry.coordinates[0];
    const centro = [(anillo[0][0] + anillo[2][0]) / 2, (anillo[0][1] + anillo[2][1]) / 2];
    return { ...f, geometry: { type: 'Point', coordinates: centro } };
  }).filter((f) => !f.geometry || dentro(f.geometry.coordinates));
  if (soloAltas && puntos.length) {
    const valores = puntos.map((f) => f.properties.hechos).sort((a, b) => a - b);
    const corte = valores[Math.floor(0.8 * (valores.length - 1))];
    celdas.corte = corte;
    celdas.features = puntos.filter((f) => f.properties.hechos >= corte);
  } else {
    celdas.features = puntos;
  }
}

function mostrarAvisoMapa(texto, accion, dato = '') {
  $('#mapa-pista').hidden = false;
  $('#mapa-pista').innerHTML = esc(texto) + (accion
    ? ` <button class="boton-texto" type="button" data-reintentar="${accion}" data-dato="${esc(dato)}">Probar de nuevo</button>` : '');
}

// Capas al elegir un barrio. Sin el explorador, las de «Lo que me importa», como siempre.
function capasIniciales() {
  return new Set(EXPLORADOR ? explorador().capas : estado.prefs);
}

/* Prende o apaga una capa desde los chips del mapa. Con el explorador, la decisión se recuerda: prender la suma a
   «Lo que me importa» y apagar una capa sugerida por una necesidad la deja apagada al cambiar de barrio. Delitos
   nunca se recuerda. */
function alternarCapa(clave) {
  const prender = !estado.capas.has(clave);
  if (prender) estado.capas.add(clave); else estado.capas.delete(clave);
  if (!EXPLORADOR || !CAPAS_MAPA.some((c) => c.clave === clave)) return;
  if (prender) {
    estado.prefs.add(clave);
    estado.apagadas.delete(clave);
  } else {
    estado.prefs.delete(clave);
    if (NECESIDADES.some((n) => estado.necesidades.has(n.clave) && n.capas.includes(clave))) estado.apagadas.add(clave);
  }
  guardar();
  sincronizarControles();
}

// Punto de color de cada capa en los chips del mapa (el mismo que usa la capa).
const PUNTO_CAPA = { subte: '#02A17A', verdes: '#5E7D4F', escuelas: '#1E2A32', salud: '#00897B', ruido: '#FD8D3C',
  riesgo: '#1E88E5', estacionamiento: '#1671A3', clubes: '#C2410C', gimnasios: '#0F766E', colectivos: '#D81B60',
  ciclovias: '#00838F', ecobici: '#004F56', bibliotecas: '#AD1457', rampas: '#B26B00', recreacion: '#BE123C', delitos: '#55708E' };

function chipCapa(c) {
  return `<button class="chip" type="button" data-capa="${c.clave}" aria-pressed="${estado.capas.has(c.clave)}">`
    + `<i class="chip-punto" style="background:${PUNTO_CAPA[c.clave] || '#55626B'}"></i>${esc(c.nombre)}</button>`;
}

function filaCapas() {
  return CAPAS;
}

function renderChips() {
  const cantidad = estado.capas.size;
  const herramientas = $('#abrir-mapa');
  if (herramientas) herramientas.textContent = `Filtros y leyenda${estado.seleccionado ? ` (${cantidad})` : ''}`;
  const centrar = $('#centrar-mapa');
  if (centrar) centrar.textContent = estado.seleccionado ? 'Centrar barrio' : 'Ver CABA';
  const resumen = $('#estado-capas');
  if (resumen) resumen.textContent = estado.seleccionado
    ? `${estado.seleccionado} · ${cantidad} ${plural(cantidad, 'capa activada', 'capas activadas')}. Los puntos de los avisos se muestran por separado.`
    : 'Elegí un barrio en la lista o en el mapa para activar sus capas.';
  const resumenMapa = $('#estado-capas-mapa');
  if (resumenMapa) resumenMapa.textContent = estado.seleccionado ? `${estado.seleccionado}: ${cantidad} capas activadas.` : '';
  for (const id of ['capas-preferidas', 'apagar-capas']) {
    const boton = $(`#${id}`);
    if (boton) boton.disabled = !estado.seleccionado;
  }
  $('#capas-fila').hidden = !estado.seleccionado;
  $('#mapa-pista').hidden = Boolean(estado.seleccionado);
  if (!estado.seleccionado) {
    $('#mapa-pista').textContent = 'Elegí un barrio para ver subte, plazas, ruido y más en el mapa.';
    return;
  }
  $('#capas').innerHTML = filaCapas().map(chipCapa).join('');
}

function renderControles() {
  const controlActivo = document.activeElement?.dataset?.control;
  const ruidoActivo = document.activeElement?.dataset?.ruido;
  const partes = [];
  if (estado.seleccionado && estado.capas.has('escuelas')) {
    partes.push(`<label class="control-flotante">Escuelas de nivel
      <select data-control="nivel">${['inicial', 'primario', 'secundario'].map((n) =>
        `<option value="${n}"${n === estado.nivel ? ' selected' : ''}>${n}</option>`).join('')}</select></label>`);
  }
  if (estado.seleccionado && estado.capas.has('ruido')) {
    partes.push(`<div class="control-flotante">Ruido
      <div class="segmentado segmentado-chico" role="radiogroup" aria-label="Momento del día">
        <button type="button" role="radio" data-ruido="diurno" tabindex="${estado.ruido === 'diurno' ? 0 : -1}" aria-checked="${estado.ruido === 'diurno'}">De día</button>
        <button type="button" role="radio" data-ruido="nocturno" tabindex="${estado.ruido === 'nocturno' ? 0 : -1}" aria-checked="${estado.ruido === 'nocturno'}">De noche</button>
      </div></div>`);
  }
  if (estado.seleccionado && estado.capas.has('delitos') && estado.delitosDatos) {
    const d = estado.delitosDatos;
    if (d.disponible) {
      partes.push(`<div class="control-flotante">
        <label>Vista <select data-control="anio">${[['persistencia', 'Persistencia entre años'], ...d.anios.map((y) => [String(y), String(y)])].map(([v, t]) => `<option value="${v}"${v === estado.delitos.anio ? ' selected' : ''}>${t}</option>`).join('')}</select></label>
        <label>Tipo <select data-control="tipo">${[['todos', 'Robos y hurtos'], ['robo', 'Robos · fuerza o violencia'], ['hurto', 'Hurtos · sin violencia']].map(([v, t]) => `<option value="${v}"${v === estado.delitos.tipo ? ' selected' : ''}>${t}</option>`).join('')}</select></label>
        <label>Horario <select data-control="franja">${[['todas', 'Todos los horarios'], ['diurno', 'Día · 06–19:59'], ['nocturno', 'Noche · 20–05:59'], ['sin_dato', 'Sin horario informado']].map(([v, t]) => `<option value="${v}"${v === estado.delitos.franja ? ' selected' : ''}>${t}</option>`).join('')}</select></label>
        ${d.inmueble ? `<label>Radio <select data-control="radio">${[250, 500, 1000].map((r) => `<option value="${r}"${String(r) === estado.delitos.radio ? ' selected' : ''}>${numero.format(r)} m</option>`).join('')}</select></label><button class="boton-texto" type="button" data-quitar-inmueble>Vista general</button>` : ''}
        <p class="fuente">${d.celdas.features.length ? `${d.celdas.features.length} celdas visibles` : estado.delitos.anio === 'persistencia' ? 'Sin celdas persistentes con estos filtros; no implica ausencia de delitos.' : 'Sin registros geolocalizados con estos filtros; no implica ausencia de delitos.'}</p>
      </div>`);
    } else {
      partes.push(`<p class="control-flotante">${esc(d.motivo)}</p>`);
    }
  }
  if (estado.colectivo) {
    partes.push(`<div class="control-flotante">Línea ${esc(estado.colectivo.linea)}
      <button class="boton-texto" type="button" data-quitar-colectivo>Quitar recorrido</button></div>`);
  }
  $('#capa-controles').innerHTML = partes.join('');
  if (controlActivo) $(`[data-control="${controlActivo}"]`)?.focus({ preventScroll: true });
  if (ruidoActivo) $(`[data-ruido="${ruidoActivo}"]`)?.focus({ preventScroll: true });
}

function muestra(color, etiqueta) {
  return `<li><span class="chip-muestra" style="background:${color}"></span>${esc(etiqueta)}</li>`;
}

function renderLeyenda() {
  const leyenda = $('#leyenda');
  if (!estado.seleccionado) {
    const maximo = Math.max(0, ...estado.barrios.map((b) => b.coincidencias));
    leyenda.innerHTML = maximo ? `<h3>Avisos que encajan por barrio</h3>
      <div class="gradiente" style="background:linear-gradient(90deg,${ESCALA_BARRIOS[1]},${ESCALA_BARRIOS[2]})"></div>
      <div class="gradiente-extremos"><span>1 aviso</span><span>${maximo} ${plural(maximo, 'aviso', 'avisos')}</span></div>
      <ul class="leyenda-items">${muestra(ESCALA_BARRIOS[0], 'Sin avisos que encajen')}</ul>
      <p class="fuente">Cantidad por barrio oficial con tus filtros actuales. Un tono más oscuro indica más avisos, no un mejor barrio.</p>`
      : '<p class="nota">Ningún barrio tiene avisos que encajen con estos filtros.</p>';
    return;
  }
  const bloques = [];
  const notas = [];
  const conPunto = estado.avisos.filter((a) => a.ubicacion);
  if (conPunto.length) {
    const pin = (hueco, etiqueta) => `<li><svg class="muestra-pin" viewBox="0 0 22 30" aria-hidden="true">
      <path d="M11 29 2.85 15.4A9.5 9.5 0 1 1 19.15 15.4Z" fill="${hueco ? '#FFFFFF' : COLOR.aviso}" stroke="${hueco ? COLOR.aviso : '#FFFFFF'}" stroke-width="2"/>
      <circle cx="11" cy="10.5" r="3.5" fill="${hueco ? COLOR.aviso : '#FFFFFF'}"/></svg>${esc(etiqueta)}</li>`;
    bloques.push(`<h3>Avisos que encajan</h3><ul class="leyenda-items">${pin(false, 'Punto publicado')}${
      conPunto.some((a) => a.ubicacion === 'aproximada') ? pin(true, 'Aproximado') : ''}</ul>`);
    notas.push(`<li><strong>Avisos.</strong> ${esc(NOTA_AVISOS)}</li>`);
  }
  for (const c of CAPAS) {
    if (!estado.capas.has(c.clave)) continue;
    if (c.clave !== 'delitos') {
      const capa = estado.capasDatos[claveCapa(c.clave)];
      if (!capa || capa.disponible === false || capa.features?.length === 0) {
        bloques.push(`<h3>${esc(c.nombre)}</h3><p>${!capa ? 'Datos pendientes de carga.' : capa.disponible === false
          ? 'Capa sin datos disponibles.' : 'Sin elementos registrados en esta capa para la zona consultada.'}</p>`);
        notas.push(`<li><strong>${esc(c.nombre)}.</strong> ${esc(NOTAS[c.clave])}</li>`);
        continue;
      }
    }
    let items = [];
    if (c.clave === 'subte') {
      const lineas = [...new Set((estado.capasDatos[claveCapa('subte')]?.features || []).map((f) => f.properties.line))].sort();
      items = lineas.map((l) => muestra(SUBTE[l] || '#55626B', `Línea ${l}`));
      items.push(`<li><span class="chip-muestra chip-ascensor"></span>Con ascensor informado</li>`);
    } else if (c.clave === 'verdes') items = [muestra(COLOR.verdes, 'Plaza o parque')];
    else if (c.clave === 'escuelas') items = [muestra(COLOR.escuela, `Escuela de nivel ${estado.nivel}`)];
    else if (c.clave === 'salud') items = [muestra(COLOR.cesac, 'CeSAC'), muestra(COLOR.hospital, 'Hospital')];
    else if (c.clave === 'estacionamiento') {
      const capa = estado.capasDatos[claveCapa(c.clave)];
      if (capa?.features.length) items = [muestra(COLOR.estacionamiento, `Garaje comercial · ${numero.format(capa.features.length)} en toda la ciudad`)];
      else if (capa) items = [esc(capa.disponible ? 'Sin garajes registrados.' : 'Inventario de garajes sin cargar.')];
    }
    else if (c.clave === 'clubes' || c.clave === 'gimnasios') {
      const capa = estado.capasDatos[claveCapa(c.clave)];
      const nombre = c.clave === 'clubes' ? 'Club o polideportivo' : 'Gimnasio';
      if (capa?.features.length) items = [muestra(COLOR[c.clave], `${nombre} · ${numero.format(capa.features.length)} en toda la ciudad`)];
      else if (capa) items = [esc(capa.disponible ? 'Sin lugares registrados.' : 'Capa sin cargar.')];
    }
    else if (['ciclovias', 'ecobici', 'bibliotecas', 'rampas'].includes(c.clave)) {
      const capa = estado.capasDatos[claveCapa(c.clave)];
      const nombre = { ciclovias: 'Tramo de ciclovía', ecobici: 'Estación de Ecobici', bibliotecas: 'Biblioteca',
        rampas: 'Rampa registrada en obras 2011–2016 (no es un inventario)' }[c.clave];
      if (capa?.features.length) items = [muestra(COLOR[c.clave], nombre)];
      else if (capa) items = [esc(capa.disponible === false ? 'Capa sin cargar.' : 'Ninguna en esta zona.')];
    }
    else if (c.clave === 'recreacion') {
      const capa = estado.capasDatos[claveCapa(c.clave)];
      const tipos = new Set((capa?.features || []).map((f) => f.properties.kind));
      if (tipos.size) items = Object.entries(RECREACION).filter(([k]) => tipos.has(k)).map(([, [, uno, color]]) => muestra(color, uno[0].toUpperCase() + uno.slice(1)));
      else if (capa) items = [esc(capa.disponible === false ? 'Capa sin cargar.' : 'Ninguno en esta zona.')];
    }
    else if (c.clave === 'colectivos') {
      const capa = estado.capasDatos[claveCapa(c.clave)];
      if (capa?.features.length) items = [muestra(COLOR.colectivo, `${capa.features.length} ${plural(capa.features.length, 'línea', 'líneas')} · cada color es una línea; tocá una para ver su recorrido completo`)];
      else if (capa) items = [esc(capa.disponible ? 'Ninguna línea en el recorrido cargado.' : 'Recorridos sin cargar.')];
    }
    else if (c.clave === 'riesgo') items = [muestra(COLOR.riesgo, 'Área de prevención')];
    else if (c.clave === 'ruido') {
      const umbral = estado.ruido === 'diurno' ? 70 : 65;
      items = RUIDO.filter(([v]) => v >= umbral).map(([v, color]) => muestra(color, v === 80 ? '80 dBA o más' : `${v} a ${v + 5} dBA`));
      items.push(`<li class="leyenda-nota">Solo se marcan las calles del barrio con ${umbral} dBA o más.</li>`);
    } else if (c.clave === 'delitos') {
      const d = estado.delitosDatos;
      if (!d?.disponible) {
        bloques.push(`<h3>Delitos registrados</h3><p>${esc(d?.motivo || 'Datos pendientes de carga.')}</p>`);
        continue;
      }
      items = estado.delitos.anio === 'persistencia'
        ? [muestra(DELITOS[4], 'Zonas del barrio con concentración alta en más de un año')]
        : [muestra(DELITOS[4], `Zonas del barrio con más hechos registrados en ${estado.delitos.anio}`
          + (d.celdas.corte ? ` (${d.celdas.corte} o más por celda)` : ''))];
      if (d.inmueble) items.push(muestra('#6A4FB3', `Pin del aviso · círculos 250, 500 y 1.000 m`));
      items.push(`<li class="leyenda-nota">${estado.delitos.anio === 'persistencia' ? `Años ${esc((d.anios || []).join(', '))}` : `Año ${esc(estado.delitos.anio)}`} · registros por celda de 200 m, dentro del barrio.</li>`);
    }
    const titulo = c.clave === 'ruido' ? `Ruido ${estado.ruido === 'diurno' ? 'de día' : 'de noche'}` : c.nombre;
    bloques.push(`<h3>${esc(titulo)}</h3>${items.length ? `<ul class="leyenda-items">${items.join('')}</ul>` : ''}`);
    notas.push(`<li><strong>${esc(titulo)}.</strong> ${esc(NOTAS[c.clave])}</li>`);
  }
  leyenda.innerHTML = bloques.length
    ? `<details class="leyenda-caja"${estado.leyendaCerrada ? '' : ' open'}><summary>Leyenda · ${esc(estado.seleccionado)}</summary>
      ${bloques.join('')}<details class="leyenda-mas"${estado.leyendaAbierta ? ' open' : ''}><summary>Cómo leer el mapa</summary>
      <ul class="leyenda-notas">${notas.join('')}</ul>
      <button class="boton-texto" type="button" data-fuentes>Ver fuentes</button></details></details>`
    : '<p class="nota">No hay capas de entorno activas. Elegí una para ver sus colores y símbolos.</p>';
  leyenda.querySelector('.leyenda-mas')?.addEventListener('toggle', (e) => { estado.leyendaAbierta = e.target.open; });
  leyenda.querySelector('.leyenda-caja')?.addEventListener('toggle', (e) => {
    if (e.target.classList.contains('leyenda-caja')) estado.leyendaCerrada = !e.target.open;
  });
}

/* Carga de datos */

async function cargarEstado() {
  estado.info = await api(`/api/estado?${new URLSearchParams({ modo: estado.modo, operacion: estado.operacion })}`);
  $('#abrir-preferencias-texto').hidden = !estado.info.interpretar_preferencias;
}

async function cargarBarrios() {
  const datos = await api(`/api/barrios?${consulta()}`);
  estado.barrios = datos.barrios;
  pintarCoropletas();
}

async function cargarAvisos() {
  if (!estado.seleccionado) return;
  estado.errorAvisos = null;
  const barrio = estado.seleccionado;
  const pedido = consulta();
  if (EXPLORADOR && estado.necesidades.size) {
    const { cercania } = explorador();
    cercania.forEach((c) => pedido.append('capas', c));
    if (cercania.includes('escuelas')) pedido.set('nivel', estado.nivel);
  }
  const datos = await api(`/api/barrios/${encodeURIComponent(barrio)}/avisos?${pedido}`);
  if (barrio === estado.seleccionado) {
    estado.avisos = datos.avisos;
    estado.cercaniaInfo = datos.cercania || null;
  }
}

// Las alertas son por barrio: desde la lista, el botón pide elegir uno y lleva a su pestaña de alerta.
function elegirBarrioAlerta() {
  estado.eligiendoAlerta = true;
  renderLista();
  const aviso = $('#contenido .eligiendo-alerta');
  const quieto = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  aviso?.scrollIntoView({ block: 'start', behavior: quieto ? 'auto' : 'smooth' });
  ($('#contenido .barrios .fila') || $('#contenido .lista-compacta [data-barrio]'))?.focus({ preventScroll: true });
}

let ultimaLista = null;

function vistaActual() {
  return { barrio: estado.seleccionado, pestana: estado.pestana, scroll: $('#contenido').scrollTop,
    expandido: $('#panel').classList.contains('expandido'), foco: document.activeElement?.dataset?.barrio || '' };
}

function recordarVista(nueva = false, ajustes = {}) {
  if (!window.history) return;
  window.history[nueva ? 'pushState' : 'replaceState'](
    { ...window.history.state, lugaVista: { ...vistaActual(), ...ajustes } }, '');
}

function restaurarPosicion(vista) {
  if (!vista) return;
  if (celular()) plegarPanel(vista.expandido);
  $('#contenido').scrollTop = vista.scroll || 0;
  if (vista.foco) [...document.querySelectorAll('[data-barrio]')]
    .find((b) => b.dataset.barrio === vista.foco)?.focus({ preventScroll: true });
}

async function seleccionar(nombre, { historial = true } = {}) {
  const cambia = nombre !== estado.seleccionado;
  if (cambia && !estado.seleccionado) ultimaLista = vistaActual();
  if (cambia && historial) recordarVista();
  if (estado.seleccionado && mapa?.getSource('barrios')) {
    mapa.setFeatureState({ source: 'barrios', id: estado.seleccionado }, { sel: false });
  }
  estado.seleccionado = nombre;
  estado.pestana = nombre && estado.eligiendoAlerta ? 'alerta' : 'entorno';
  if (cambia && historial) recordarVista(true, { scroll: 0, foco: '' });
  estado.eligiendoAlerta = false;
  estado.verTodos = false;
  estado.avisos = [];
  estado.delitosDatos = null;
  estado.delitos.inmueble = '';
  estado.pedidoDelitos += 1;
  estado.lugares = { ...lugaresIniciales(estado.lugares.tipo), pedido: estado.lugares.pedido + 1 };
  popup?.remove();
  popupAviso?.remove();
  if (nombre && mapa?.getSource('barrios')) mapa.setFeatureState({ source: 'barrios', id: nombre }, { sel: true });
  estado.capas = nombre ? capasIniciales() : new Set();
  pintarCoropletas();
  renderChips();
  encuadrar(nombre);
  renderPanel();
  $('#contenido').scrollTop = 0;
  $('#titulo-vista')?.focus({ preventScroll: true });
  if (celular()) plegarPanel(estado.pestana === 'alerta');
  estado.parecidos = { barrio: null, datos: null, error: '' };
  cargarParecidos();
  try {
    await cargarAvisos();
    if (nombre === estado.seleccionado) renderPanel();
  } catch (error) {
    // Antes el mensaje se agregaba al final y el siguiente redibujo lo borraba: la tabla quedaba vacía, como si no hubiera avisos.
    if (nombre === estado.seleccionado) {
      estado.errorAvisos = { barrio: nombre, mensaje: `No se pudieron cargar los avisos de ${nombre}. ${error.message}` };
      renderPanel();
    }
  }
  await actualizarCapas();
  if (!nombre && estado.seleccionado === null) restaurarPosicion(ultimaLista);
}

// Pone el error arriba del panel y deja debajo lo que ya se estaba viendo (la lista o la ficha anteriores).
function mostrarErrorArriba(mensaje, accion) {
  const contenido = $('#contenido');
  contenido.querySelector(':scope > .aviso-error')?.remove();
  contenido.insertAdjacentHTML('afterbegin', bloqueError(mensaje, accion));
  contenido.scrollTop = 0;
}

let espera;
function recargar() {
  clearTimeout(espera);
  espera = setTimeout(async () => {
    guardar();
    try {
      await cargarBarrios();
      await cargarAvisos();
      cargarParecidos();
      if (!estado.avisos.some((a) => a.id === estado.delitos.inmueble)) estado.delitos.inmueble = '';
      if (estado.capas.has('delitos')) await actualizarCapas();
      renderPanel();
      renderLeyenda();
    } catch (error) {
      mostrarErrorArriba(`No se pudo actualizar la búsqueda. ${error.message}`, 'barrios');
    }
  }, 280);
}

/* Barra de filtros */

function sincronizarControles() {
  for (const [atributo, valor] of [['operacion', estado.operacion], ['modo', estado.modo]]) {
    document.querySelectorAll(`[data-${atributo}]`).forEach((b) => {
      const activo = b.dataset[atributo] === valor;
      b.setAttribute('aria-checked', activo);
      b.tabIndex = activo ? 0 : -1;
    });
  }
  const alquiler = estado.operacion === 'alquiler';
  $('#moneda').hidden = !alquiler;
  $('#moneda-fija').hidden = alquiler;
  $('#moneda').value = estado.moneda;
  $('#etiqueta-presupuesto').textContent = alquiler ? 'Hasta por mes' : 'Hasta';
  $('#presupuesto').setAttribute('aria-label', `Presupuesto máximo${alquiler ? ' por mes' : ''} en ${estado.moneda}`);
  $('#presupuesto').value = numero.format(estado.presupuesto);
  $('#superficie').value = estado.superficie;
  const ambientes = $('#ambientes');
  const valor = String(estado.ambientes) + (estado.ambientesOMas ? '+' : '');
  if (![...ambientes.options].some((o) => o.value === valor)) {
    ambientes.add(new Option(estado.ambientes + ' ambientes' + (estado.ambientesOMas ? ' o más' : ''), valor));
  }
  ambientes.value = valor;
  $('#nivel').value = estado.nivel;
  $('#franja-demo').hidden = estado.modo !== 'demo';
  // Capas que alguna necesidad elegida sugiere, aunque estén apagadas a mano.
  const sugeridas = new Set(EXPLORADOR ? NECESIDADES.filter((n) => estado.necesidades.has(n.clave)).flatMap((n) => n.capas) : []);
  $('#preferencias').innerHTML = `<legend ${EXPLORADOR ? 'class="importa-titulo"' : 'hidden'}>${EXPLORADOR ? 'Capas del mapa' : 'Lo que me importa'}</legend>${PREFERENCIAS.map((p) => `
    <label><input type="checkbox" value="${p.clave}"${estado.prefs.has(p.clave) ? ' checked' : ''}>${esc(p.nombre)}${
      sugeridas.has(p.clave) && !estado.prefs.has(p.clave) ? `<small class="sugerida">${estado.apagadas.has(p.clave) ? 'sugerida, apagada' : 'sugerida'}</small>` : ''}</label>`).join('')}`;
  $('#nivel-campo').hidden = !estado.prefs.has('escuelas');
  renderResumenNecesidades();
  const elegidas = estado.prefs.size + estado.necesidades.size;
  $('#abrir-importa').textContent = elegidas ? `Lo que me importa: ${elegidas}` : 'Lo que me importa';
  $('#abrir-importa').classList.toggle('con-eleccion', elegidas > 0);
}

// Casillas de necesidades. Se dibujan al iniciar y al restablecer, no en cada cambio, para no perder el foco.
function renderNecesidades() {
  // Sin el interruptor no se toca nada; con una página vieja en caché tampoco hay casillas que dibujar.
  const contenedor = $('#necesidades');
  if (!EXPLORADOR || !contenedor) return;
  contenedor.hidden = false;
  $('#necesidades-pie').hidden = false;
  contenedor.innerHTML = `<legend class="importa-titulo">Lo que necesitás</legend>${NECESIDADES.map((n) => `
    <label class="necesidad"><input type="checkbox" value="${n.clave}"${estado.necesidades.has(n.clave) ? ' checked' : ''}>
      <span>${esc(n.nombre)}<small>${esc(n.descripcion)}</small></span></label>`).join('')}`;
}

function renderResumenNecesidades() {
  if (!EXPLORADOR || !$('#necesidades-resumen')) return;
  const r = explorador();
  const nombres = r.capas.map((c) => CAPAS.find((x) => x.clave === c)?.nombre || c);
  const columnas = columnasExplorador().map((c) => c.titulo);
  $('#necesidades-resumen').textContent = estado.necesidades.size
    ? `En el mapa: ${nombres.length ? enumerar(nombres) : 'ninguna capa'}.`
      + (columnas.length ? ` En la tabla de avisos: ${enumerar(columnas)}.` : '') + ' No se oculta ningún aviso.'
    : 'Elegí una o más para ver capas y datos relacionados. No filtran avisos ni arman puntajes.';
}

// Selector del lugar fijo, debajo de las necesidades. Solo se ve con «Tengo que ir seguido a un lugar» marcada.
function renderLugarFijo() {
  const caja = $('#lugar-fijo');
  if (!caja) return;
  caja.hidden = !(EXPLORADOR && estado.necesidades.has('lugar_fijo'));
  if (caja.hidden) return;
  const l = estado.lugarFijo;
  const opciones = (estado.hospitales || []).map((h, i) => `<option value="${i}">${esc(h.nombre)}${h.barrio ? ` · ${esc(h.barrio)}` : ''}</option>`);
  caja.innerHTML = `
    <p class="lugar-fijo-actual">${l ? `Tu lugar fijo: <strong>${esc(l.nombre)}</strong>
      <button class="boton-texto" type="button" id="quitar-lugar">Quitar</button>` : 'Todavía no elegiste el lugar.'}</p>
    <label class="lugar-fijo-campo">Elegir un hospital
      <select id="lugar-hospital"><option value="">${estado.hospitales ? 'Elegí de la lista…' : 'Cargando hospitales…'}</option>${opciones.join('')}</select></label>
    <button class="boton-texto" type="button" id="marcar-lugar">${estado.eligiendoLugar ? 'Tocá el mapa…' : 'O marcalo en el mapa'}</button>
    <p class="importa-ayuda">Queda guardado solo en este navegador: Lüga no lo recibe.</p>`;
  if (!estado.hospitales) cargarHospitales();
}

async function cargarHospitales() {
  if (estado.hospitales || cargarHospitales.pendiente) return;
  cargarHospitales.pendiente = true;
  try {
    estado.hospitales = (await api('/api/hospitales')).hospitales;
  } catch {
    estado.hospitales = [];
  } finally {
    cargarHospitales.pendiente = false;
  }
  renderLugarFijo();
}

function pintarLugarFijo() {
  const l = lugarActivo();
  ponerDatos('lugar-fijo', l ? { type: 'FeatureCollection', features: [
    { type: 'Feature', geometry: { type: 'Point', coordinates: [l.lon, l.lat] }, properties: { nombre: l.nombre } }] } : VACIO);
}

function fijarLugar(lugar) {
  estado.lugarFijo = lugarValido(lugar);
  estado.eligiendoLugar = false;
  if (mapa) mapa.getCanvas().style.cursor = '';
  if (!estado.lugarFijo && lugar) avisar('Ese punto queda fuera de la Ciudad. Elegí un lugar dentro de CABA.');
  else if (estado.lugarFijo) avisar(`Lugar fijo: ${estado.lugarFijo.nombre}.`);
  if (estado.ordenBarrios === 'lugar' && !estado.lugarFijo) estado.ordenBarrios = 'avisos';
  guardar();
  renderLugarFijo();
  pintarLugarFijo();
  renderResumenNecesidades();
  renderPanel();
}

async function aplicarNecesidades() {
  guardar();
  sincronizarControles();
  renderLugarFijo();
  pintarLugarFijo();
  if (!estado.seleccionado) { renderPanel(); return; }
  const delitos = estado.capas.has('delitos');
  estado.capas = capasIniciales();
  if (delitos) estado.capas.add('delitos');
  renderChips();
  actualizarCapas();
  try { await cargarAvisos(); } catch { /* La ficha sigue con los avisos anteriores. */ }
  renderPanel();
}

function enteroDe(texto) {
  const valor = parseInt(String(texto).replace(/\D/g, ''), 10);
  return Number.isFinite(valor) && valor > 0 ? valor : null;
}

async function cambiarContexto() {
  // Invalida antes de los awaits para no mostrar un resultado de la base anterior.
  estado.pedidoDelitos += 1;
  estado.delitosDatos = null;
  estado.delitos = { anio: '', tipo: 'todos', franja: 'todas', radio: '500', inmueble: '' };
  estado.avisos = [];
  for (const id of ['delitos', 'radios', 'inmueble']) ponerDatos(id, VACIO);
  renderPanel();
  sincronizarControles();
  guardar();
  try {
    await cargarEstado();
    await cargarBarrios();
    if (estado.seleccionado) {
      await cargarAvisos();
      await actualizarCapas();
    }
    renderPanel();
    renderLeyenda();
  } catch (error) {
    mostrarErrorArriba(`No se pudieron cargar los datos. ${error.message}`, 'contexto');
  }
}

function plegarPanel(expandir) {
  const panel = $('#panel');
  panel.classList.toggle('expandido', expandir);
  $('#panel-asa').setAttribute('aria-expanded', expandir);
  $('#panel-asa').textContent = expandir ? 'Ver mapa' : 'Ver lista';
  if (!expandir && mapa && estado.formas) setTimeout(() => {
    if (!panel.classList.contains('expandido')) encuadrar(estado.seleccionado);
  }, reducido ? 0 : 230);
}

function conectarPreferencias() {
  const dialogo = $('#dialogo-preferencias');
  const interpretar = $('#interpretar-preferencias');
  const revisar = $('#revisar-preferencias');
  const salida = $('#estado-preferencias');
  let pedido;
  let capas = [];
  let requiereConfirmacion = false;
  const opciones = (items) => items.map(([id, label]) =>
    '<option value="' + esc(id) + '">' + esc(label) + '</option>').join('');

  function presentar(propuesta) {
    const valores = Object.fromEntries(propuesta.campos.map((c) => [c.clave, c.valor]));
    const barrios = [...new Set(propuesta.campos.filter((c) => c.clave === 'barrio').map((c) => c.valor))];
    capas = propuesta.campos.filter((c) => c.clave === 'capa').map((c) => c.valor);
    const barrio = barrios.length === 1 ? barrios[0] : barrios.length ? '' : estado.seleccionado || '';
    const campos = [
      ['operacion', 'Operación', valores.operacion ?? estado.operacion, [['venta', 'Comprar'], ['alquiler', 'Alquilar']]],
      ['moneda', 'Moneda', valores.moneda ?? estado.moneda, [['USD', 'USD'], ['ARS', 'ARS']]],
      ['presupuesto', 'Presupuesto máximo', valores.presupuesto ?? estado.presupuesto, 1000000000],
      ['superficie', 'Superficie cubierta mínima (m²)', valores.superficie ?? estado.superficie, 2000],
      ['ambientes', 'Ambientes', valores.ambientes ?? estado.ambientes, 20],
      ['ambientes_o_mas', 'Cantidad de ambientes', valores.ambientes_o_mas ?? String(estado.ambientesOMas),
        [['false', 'Exacta'], ['true', 'O más']]],
      ['barrio', 'Barrio', barrio, [['', 'Comparación general'], ...[...new Set([
        ...barrios, ...(barrio ? [barrio] : []), ...estado.barrios.map((b) => b.barrio)
      ])].sort((a, b) => a.localeCompare(b, 'es')).map((b) => [b, b])]],
    ];
    $('#campos-preferencias').innerHTML = campos.map(([clave, label, valor, tipo]) => {
      const origen = clave === 'barrio' && barrios.length > 1 ? 'Elegí un barrio o compará todos'
        : clave in valores ? 'De tu descripción' : 'Valor actual';
      const control = Array.isArray(tipo)
        ? '<select name="' + clave + '">' + opciones(tipo) + '</select>'
        : '<input type="number" name="' + clave + '" required min="1" step="1" max="' + tipo + '">';
      return '<label>' + label + control + '<small>' + origen + '</small></label>';
    }).join('');
    campos.forEach(([clave, , valor]) => { revisar.elements.namedItem(clave).value = valor; });
    const avisos = [
      ...propuesta.dudas.map((d) => 'Revisá «' + d.evidencia + '» (' + d.campo + ').'),
      ...propuesta.no_soportadas.map((c) => 'No se aplicará «' + c.evidencia + '»' +
        (c.obligatoria ? ' (requisito indicado).' : '.')),
      ...capas.map((c) => 'Capa del mapa: ' + PREFERENCIAS.find((p) => p.clave === c)?.nombre + '.'),
    ];
    requiereConfirmacion = propuesta.dudas.length > 0 || barrios.length > 1 ||
      propuesta.no_soportadas.some((c) => c.obligatoria);
    $('#avisos-preferencias').innerHTML = avisos.map((aviso) => '<li>' + esc(aviso) + '</li>').join('');
    revisar.hidden = false;
  }

  $('#abrir-preferencias-texto').addEventListener('click', () => dialogo.showModal());
  $('#cancelar-preferencias').addEventListener('click', () => dialogo.close());
  dialogo.addEventListener('close', () => {
    pedido?.abort();
    pedido = null;
    // No se borra lo escrito: si la persona cierra sin aplicar, lo encuentra al volver a abrir.
    interpretar.querySelector('button').disabled = false;
    revisar.hidden = true;
    $('#campos-preferencias').replaceChildren();
    $('#avisos-preferencias').replaceChildren();
    salida.textContent = '';
    capas = [];
  });
  interpretar.addEventListener('input', () => {
    pedido?.abort();
    pedido = null;
    interpretar.querySelector('button').disabled = false;
    revisar.hidden = true;
    salida.textContent = '';
  });
  interpretar.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (pedido) return;
    const actual = new AbortController();
    pedido = actual;
    const boton = interpretar.querySelector('button');
    boton.disabled = true;
    revisar.hidden = true;
    salida.textContent = 'Interpretando…';
    try {
      const propuesta = await api('/api/preferencias/interpretar', {
        method: 'POST', signal: actual.signal, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texto: $('#texto-preferencias').value }),
      });
      if (pedido === actual) {
        presentar(propuesta);
        salida.textContent = '';
      }
    } catch (error) {
      if (pedido === actual) salida.textContent = error.message;
    } finally {
      if (pedido === actual) {
        pedido = null;
        boton.disabled = false;
      }
    }
  });
  revisar.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (revisar.hidden) return;
    const f = new FormData(revisar);
    if (f.get('operacion') === 'venta' && f.get('moneda') !== 'USD') {
      salida.textContent = 'Para comprar, elegí USD.';
      return;
    }
    clearTimeout(espera);
    const antes = { operacion: estado.operacion, moneda: estado.moneda, presupuesto: estado.presupuesto,
      superficie: estado.superficie, ambientes: estado.ambientes, ambientesOMas: estado.ambientesOMas,
      prefs: [...estado.prefs], seleccionado: estado.seleccionado };
    const dudosos = requiereConfirmacion;
    estado.operacion = f.get('operacion');
    estado.moneda = f.get('moneda');
    estado.presupuesto = Number(f.get('presupuesto'));
    estado.superficie = Number(f.get('superficie'));
    estado.ambientes = Number(f.get('ambientes'));
    estado.ambientesOMas = f.get('ambientes_o_mas') === 'true';
    capas.forEach((capa) => estado.prefs.add(capa));
    $('#texto-preferencias').value = '';
    dialogo.close();
    await cambiarContexto();
    await seleccionar(f.get('barrio') || null);
    avisar(dudosos ? 'Cambiamos los filtros según tu descripción. Había datos dudosos: revisá la barra.'
      : 'Cambiamos los filtros según tu descripción.', async () => {
      const { seleccionado, prefs, ...filtros } = antes;
      Object.assign(estado, filtros, { prefs: new Set(prefs) });
      await cambiarContexto();
      await seleccionar(seleccionado);
    });
  });
}

function conectarEventos() {
  conectarPreferencias();
  const dialogoMapa = $('#dialogo-mapa');
  const ubicarLeyenda = () => {
    const destino = $(dialogoMapa.open || celular() ? '#leyenda-dialogo' : '#leyenda-mapa');
    if ($('#leyenda').parentElement !== destino) destino.append($('#leyenda'));
    // Nivel de escuelas, día/noche del ruido y filtros de delitos quedan sobre el mapa, junto a las capas que
    // filtran; con el diálogo abierto se mudan a él. Los eventos están en el contenedor y viajan con él.
    const controles = $('#capa-controles');
    const lugar = $(dialogoMapa.open ? '#controles-dialogo' : '.mapa-arriba');
    if (controles.parentElement !== lugar) lugar.prepend(controles);
  };
  ubicarLeyenda();
  window.addEventListener('resize', ubicarLeyenda);
  dialogoMapa.addEventListener('close', ubicarLeyenda);
  $('#abrir-mapa').addEventListener('click', () => {
    estado.leyendaCerrada = false;
    renderLeyenda();
    dialogoMapa.showModal();
    ubicarLeyenda();
  });
  $('#centrar-mapa').addEventListener('click', () => encuadrar(estado.seleccionado));
  $('#capas-preferidas').addEventListener('click', () => {
    estado.capas = capasIniciales();
    renderChips();
    actualizarCapas();
  });
  $('#apagar-capas').addEventListener('click', () => {
    estado.capas.clear();
    renderChips();
    actualizarCapas();
  });
  const dialogoComparacion = $('#dialogo-comparacion');
  const abrirComparacion = () => {
    $('#comparacion-contenido').innerHTML = renderComparacion();
    dialogoComparacion.showModal();
  };
  $('#comparacion-pie').addEventListener('click', (e) => {
    if (e.target.closest('button') && estado.comparando.size >= 2) abrirComparacion();
  });
  $('#contenido').addEventListener('change', (e) => {
    if (e.target.matches('[data-comparar]')) {
      const barrio = e.target.dataset.comparar;
      if (e.target.checked && estado.comparando.size < 3) estado.comparando.add(barrio);
      else estado.comparando.delete(barrio);
      actualizarComparador();
    }
    if (e.target.id === 'orden-barrios') {
      estado.ordenBarrios = e.target.value;
      renderLista();
      $('#orden-barrios').focus({ preventScroll: true });
    }
  });
  $('#contenido').addEventListener('click', (e) => {
    if (e.target.closest('#abrir-comparacion')) {
      abrirComparacion();
    }
    if (e.target.closest('#limpiar-comparacion')) {
      estado.comparando.clear();
      actualizarComparador();
    }
  });
  dialogoComparacion.addEventListener('click', (e) => {
    const elegido = e.target.closest('[data-elegir-comparado]');
    if (elegido) {
      dialogoComparacion.close();
      seleccionar(elegido.dataset.elegirComparado);
    }
    if (e.target.closest('[data-fuentes-comparacion]')) {
      dialogoComparacion.close();
      abrirFuentes();
    }
  });
  recordarVista();
  let navegacion = 0;
  window.addEventListener('popstate', async (e) => {
    const turno = ++navegacion;
    const vista = e.state?.lugaVista || { barrio: null, pestana: 'entorno', scroll: 0 };
    await seleccionar(vista.barrio, { historial: false });
    if (turno !== navegacion || estado.seleccionado !== vista.barrio) return;
    estado.pestana = PESTANAS.some(([clave]) => clave === vista.pestana) ? vista.pestana : 'entorno';
    renderPanel();
    restaurarPosicion(vista);
  });
  document.addEventListener('keydown', (e) => {
    const radio = e.target.closest('[role="radio"]');
    if (!radio || !['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return;
    const radios = [...radio.closest('[role="radiogroup"]').querySelectorAll('[role="radio"]')];
    const i = radios.indexOf(radio);
    const j = e.key === 'Home' ? 0 : e.key === 'End' ? radios.length - 1
      : (i + (['ArrowRight', 'ArrowDown'].includes(e.key) ? 1 : -1) + radios.length) % radios.length;
    e.preventDefault();
    radios[j].focus();
    radios[j].click();
  });
  const alternarFiltros = $('#alternar-filtros');
  const cerrarFiltros = () => {
    $('.barra').classList.remove('filtros-abiertos');
    alternarFiltros.setAttribute('aria-expanded', 'false');
    alternarFiltros.textContent = 'Cambiar filtros';
    $('#importa').hidden = true;
    $('#abrir-importa').setAttribute('aria-expanded', 'false');
  };
  $('#lugar-fijo')?.addEventListener('change', (e) => {
    if (e.target.id !== 'lugar-hospital' || e.target.value === '') return;
    const h = estado.hospitales?.[Number(e.target.value)];
    if (h) fijarLugar({ nombre: h.nombre, lon: h.lon, lat: h.lat });
  });
  $('#lugar-fijo')?.addEventListener('click', (e) => {
    if (e.target.id === 'quitar-lugar') fijarLugar(null);
    if (e.target.id !== 'marcar-lugar') return;
    estado.eligiendoLugar = !estado.eligiendoLugar;
    if (!estado.eligiendoLugar) { renderLugarFijo(); return; }
    cerrarFiltros();
    if (mapa) mapa.getCanvas().style.cursor = 'crosshair';
    avisar('Tocá el mapa donde está tu lugar fijo.');
  });
  alternarFiltros.addEventListener('click', () => {
    const abrir = alternarFiltros.getAttribute('aria-expanded') !== 'true';
    if (!abrir) { cerrarFiltros(); return; }
    $('.barra').classList.toggle('filtros-abiertos', abrir);
    alternarFiltros.setAttribute('aria-expanded', abrir);
    alternarFiltros.textContent = 'Listo, ver barrios';
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && celular() && alternarFiltros.getAttribute('aria-expanded') === 'true' && $('#importa').hidden) {
      cerrarFiltros();
      alternarFiltros.focus();
    }
  });
  $('#contenido').addEventListener('submit', (e) => {
    if (e.target.id !== 'form-alerta') return;
    e.preventDefault();
    crearAlerta($('#crear-alerta'));
  });
  // «Probar de nuevo» en cualquier bloque de error vuelve a pedir lo que falló.
  const REINTENTOS = {
    inicio: () => cargarInicio(),
    barrios: () => recargar(),
    contexto: () => cambiarContexto(),
    avisos: async () => {
      try {
        await cargarAvisos();
      } catch (error) {
        estado.errorAvisos = { barrio: estado.seleccionado, mensaje: `No se pudieron cargar los avisos de ${estado.seleccionado}. ${error.message}` };
      }
      renderPanel();
    },
    parecidos: () => cargarParecidos(),
    radar: async () => { await cargarRadar(); renderPanel(); },
    capas: () => { renderChips(); return actualizarCapas(); },
    recorrido: (linea) => elegirColectivo(linea),
    alertas: () => abrirAlertas(),
    fuentes: () => abrirFuentes(),
  };
  document.addEventListener('click', (e) => {
    const boton = e.target.closest('[data-reintentar]');
    if (boton) REINTENTOS[boton.dataset.reintentar]?.(boton.dataset.dato);
  });
  document.querySelectorAll('[data-operacion]').forEach((boton) => boton.addEventListener('click', () => {
    if (estado.operacion === boton.dataset.operacion) return;
    estado.operacion = boton.dataset.operacion;
    estado.moneda = estado.operacion === 'venta' ? 'USD' : 'ARS';
    estado.presupuesto = PRESUPUESTO[`${estado.operacion}-${estado.moneda}`];
    cambiarContexto();
  }));
  document.querySelectorAll('[data-modo]').forEach((boton) => boton.addEventListener('click', () => {
    if (estado.modo === boton.dataset.modo) return;
    estado.modo = boton.dataset.modo;
    cambiarContexto();
  }));
  $('#moneda').addEventListener('change', (e) => {
    estado.moneda = e.target.value;
    estado.presupuesto = PRESUPUESTO[`alquiler-${estado.moneda}`];
    sincronizarControles();
    recargar();
  });
  $('#presupuesto').addEventListener('input', (e) => {
    const valor = enteroDe(e.target.value);
    if (valor) { estado.presupuesto = valor; recargar(); }
  });
  $('#presupuesto').addEventListener('blur', (e) => {
    if (!enteroDe(e.target.value)) {
      const vigente = dinero(estado.presupuesto, estado.moneda);
      avisar(e.target.value.trim() ? `El presupuesto tiene que ser mayor que 0. Volvimos a ${vigente}.`
        : `El presupuesto quedó vacío. Volvimos a ${vigente}.`);
    }
    e.target.value = numero.format(estado.presupuesto);
  });
  $('#superficie').addEventListener('input', (e) => {
    const valor = enteroDe(e.target.value);
    if (valor) { estado.superficie = valor; recargar(); }
  });
  $('#superficie').addEventListener('blur', (e) => {
    if (!enteroDe(e.target.value)) {
      avisar(e.target.value.trim() ? `La superficie tiene que ser de al menos 1 m². Volvimos a ${estado.superficie} m².`
        : `La superficie quedó vacía. Volvimos a ${estado.superficie} m².`);
    }
    e.target.value = estado.superficie;
  });
  $('#ambientes').addEventListener('change', (e) => {
    estado.ambientes = parseInt(e.target.value, 10);
    estado.ambientesOMas = e.target.value.endsWith('+');
    recargar();
  });
  $('#filtros').addEventListener('submit', (e) => e.preventDefault());

  const importa = $('#importa');
  const abrirImporta = $('#abrir-importa');
  abrirImporta.addEventListener('click', () => {
    importa.hidden = !importa.hidden;
    abrirImporta.setAttribute('aria-expanded', !importa.hidden);
  });
  document.addEventListener('click', (e) => {
    if (!importa.hidden && !e.target.closest('.importa')) {
      importa.hidden = true;
      abrirImporta.setAttribute('aria-expanded', 'false');
    }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && estado.colectivo && importa.hidden && !document.querySelector('dialog[open]')) {
      quitarColectivo();
      return;
    }
    if (e.key === 'Escape' && !importa.hidden) {
      importa.hidden = true;
      abrirImporta.setAttribute('aria-expanded', 'false');
      abrirImporta.focus();
    }
  });
  $('#preferencias').addEventListener('change', (e) => {
    const clave = e.target.value;
    if (e.target.checked) estado.prefs.add(clave); else estado.prefs.delete(clave);
    if (e.target.checked) estado.apagadas.delete(clave);
    else if (EXPLORADOR && NECESIDADES.some((n) => estado.necesidades.has(n.clave) && n.capas.includes(clave))) {
      estado.apagadas.add(clave);
    }
    if (estado.seleccionado) {
      if (e.target.checked) estado.capas.add(clave); else estado.capas.delete(clave);
      renderChips();
      actualizarCapas();
    }
    sincronizarControles();
    guardar();
    renderPanel();
    cargarParecidos();
  });
  $('#nivel').addEventListener('change', (e) => { cambiarNivel(e.target.value); });
  // Pestañas de la ficha: se muestran y ocultan sin volver a dibujar, así no se pierde lo que se escribió.
  const elegirPestana = (clave, foco = false) => {
    estado.pestana = clave;
    if (celular()) plegarPanel(true);
    document.querySelectorAll('[data-pestana]').forEach((t) => {
      const activa = t.dataset.pestana === clave;
      t.setAttribute('aria-selected', activa);
      t.tabIndex = activa ? 0 : -1;
      if (activa && foco) t.focus();
    });
    document.querySelectorAll('.pestana-panel').forEach((panel) => { panel.hidden = panel.id !== `panel-${clave}`; });
    const contenido = $('#contenido');
    const cabeza = $('#contenido .ficha-cabeza');
    contenido.scrollTop += cabeza.getBoundingClientRect().bottom - contenido.getBoundingClientRect().top
      + parseFloat(getComputedStyle(cabeza).marginBottom);
    recordarVista();
  };
  $('#contenido').addEventListener('click', (e) => {
    const tab = e.target.closest('[data-pestana]');
    if (tab) elegirPestana(tab.dataset.pestana);
    if (e.target.closest('[data-ir-alerta]')) {
      elegirPestana('alerta');
      ($('#mail-alerta') || $('#crear-alerta'))?.focus();
    }
    if (e.target.closest('[data-ver-alertas]')) abrirAlertas();
  });
  // Con mail, la casilla de consentimiento aparece y el botón espera a que se marque.
  $('#contenido').addEventListener('input', (e) => {
    if (e.target.matches('#mail-alerta')) e.target.removeAttribute('aria-invalid');
    if (e.target.matches('#mail-alerta, #consentimiento-alerta')) actualizarAlerta();
  });
  $('#contenido').addEventListener('change', (e) => { if (e.target.matches('#consentimiento-alerta')) actualizarAlerta(); });
  $('#contenido').addEventListener('keydown', (e) => {
    const tab = e.target.closest('[data-pestana]');
    if (!tab || !['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault();
    const claves = PESTANAS.map(([c]) => c);
    const i = claves.indexOf(tab.dataset.pestana);
    const j = e.key === 'Home' ? 0 : e.key === 'End' ? claves.length - 1
      : (i + (e.key === 'ArrowRight' ? 1 : -1) + claves.length) % claves.length;
    elegirPestana(claves[j], true);
  });
  $('#necesidades')?.addEventListener('change', (e) => {
    const clave = e.target.value;
    if (e.target.checked) estado.necesidades.add(clave); else estado.necesidades.delete(clave);
    aplicarNecesidades();
  });
  $('#restablecer-necesidades')?.addEventListener('click', () => {
    const antes = { necesidades: [...estado.necesidades], apagadas: [...estado.apagadas], prefs: [...estado.prefs] };
    estado.necesidades.clear();
    estado.apagadas.clear();
    estado.prefs = new Set(['subte', 'verdes']);
    renderNecesidades();
    aplicarNecesidades();
    avisar('Se restablecieron tus elecciones de «Lo que me importa».', () => {
      estado.necesidades = new Set(antes.necesidades);
      estado.apagadas = new Set(antes.apagadas);
      estado.prefs = new Set(antes.prefs);
      renderNecesidades();
      aplicarNecesidades();
    });
  });
  $('#contenido').addEventListener('click', (e) => {
    if (!e.target.closest('[data-abrir-importa]')) return;
    e.stopPropagation();
    if (celular()) {
      $('.barra').classList.add('filtros-abiertos');
      $('#alternar-filtros').setAttribute('aria-expanded', 'true');
      $('#alternar-filtros').textContent = 'Listo, ver barrios';
    }
    $('#importa').hidden = false;
    $('#abrir-importa').setAttribute('aria-expanded', 'true');
    ($('#necesidades:not([hidden]) input') || $('#preferencias input'))?.focus();
  });

  let consultaEstacionamientos = 0;
  $('#contenido').addEventListener('submit', async (e) => {
    if (e.target.id !== 'buscar-estacionamientos') return;
    e.preventDefault();
    const output = $('#resultado-estacionamientos');
    const fields = new FormData(e.target);
    const params = new URLSearchParams({ barrio: estado.seleccionado, radio: fields.get('radio') });
    const request = ++consultaEstacionamientos;
    output.textContent = 'Buscando estacionamientos…';
    try {
      const point = await puntoDeBusqueda(fields.get('origen'), output);
      if (!output.isConnected || request !== consultaEstacionamientos) return;
      if (point) { params.set('lat', point.lat); params.set('lon', point.lon); }
      output.textContent = 'Buscando estacionamientos…';
      const data = await api('/api/estacionamientos?' + params);
      if (!output.isConnected || request !== consultaEstacionamientos) return;
      if (!data.disponible) { output.textContent = 'El inventario de estacionamientos todavía no está cargado.'; return; }
      output.innerHTML = `<p>${data.estacionamientos.length} estacionamientos en el inventario para esta búsqueda.</p>`
        + notaPrecision(point, Number(fields.get('radio')))
        + (data.estacionamientos.length ? '<ul>' + data.estacionamientos.map((r) => `<li>
          <strong>${esc(r.detalle)}</strong> · ${esc(r.barrio)}
          ${r.distancia_m == null ? '' : `· ${r.distancia_m} m en línea recta`}
          <button type="button" class="boton-texto" data-estacionamiento-lat="${r.lat}" data-estacionamiento-lon="${r.lon}" data-estacionamiento-texto="${esc(r.detalle)}">Ver en mapa</button>
          <a href="https://www.google.com/maps/dir/?api=1&amp;destination=${r.lat},${r.lon}" target="_blank" rel="noopener">Cómo llegar</a>
          </li>`).join('') + '</ul>' : '<p>La cobertura histórica puede ser incompleta.</p>')
        + `<p class="fuente">Fuente: <a href="${esc(data.fuente)}" target="_blank" rel="noopener">Buenos Aires Data</a>, ${esc(data.periodo)}. Las distancias no representan recorridos a pie.</p>`;
    } catch (error) {
      if (output.isConnected && request === consultaEstacionamientos) output.textContent = 'No se pudo completar la búsqueda. ' + error.message;
    }
  });
  let consultaCocheras = 0;
  $('#contenido').addEventListener('submit', async (e) => {
    if (e.target.id !== 'buscar-cocheras') return;
    e.preventDefault();
    const output = $('#resultado-cocheras');
    const fields = new FormData(e.target);
    const params = new URLSearchParams({ barrio: estado.seleccionado, radio: fields.get('radio'),
      moneda: fields.get('moneda'), presupuesto: fields.get('presupuesto') });
    const operacion = estado.operacion;
    const consulta = ++consultaCocheras;
    output.textContent = 'Buscando cocheras…';
    try {
      const punto = await puntoDeBusqueda(fields.get('origen'), output);
      if (!output.isConnected || consulta !== consultaCocheras) return;
      const aviso = punto?.aviso;
      if (punto) { params.set('lat', punto.lat); params.set('lon', punto.lon); }
      output.textContent = 'Buscando cocheras…';
      const data = await api('/api/cocheras?' + params);
      if (!output.isConnected || consulta !== consultaCocheras) return;
      if (!data.disponible) { output.textContent = 'El catálogo de cocheras está pendiente de incorporación.'; return; }
      output.innerHTML = data.avisos.length ? '<ul>' + data.avisos.map((r) =>
        `<li><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.direccion || r.barrio)}</a>
        · ${dinero(r.precio, r.moneda)} por mes
        · ${r.expensas == null ? 'Expensas no informadas' : `Expensas ${dinero(r.expensas, r.moneda_expensas)}`}
        ${r.distancia_m == null ? '' : `· aproximadamente ${r.distancia_m} m en línea recta`}
        · Captura ${esc(fechaCorta(r.capturado))}
        ${aviso && operacion === 'alquiler' ? costoMensual(aviso, r) : ''}</li>`).join('') + '</ul>'
        : 'Sin coincidencias en el catálogo para estos filtros.';
      output.innerHTML += notaPrecision(punto, Number(fields.get('radio')));
      if (punto) output.innerHTML += '<p class="fuente">Distancias aproximadas en línea recta desde el punto elegido hasta las ubicaciones publicadas.</p>';
    } catch (error) {
      if (output.isConnected && consulta === consultaCocheras) output.textContent = 'No se pudo consultar el catálogo. ' + error.message;
    }
  });

  $('#contenido').addEventListener('click', async (e) => {
    const colectivo = e.target.closest('[data-colectivo]');
    if (colectivo) { elegirColectivo(colectivo.dataset.colectivo); return; }
    if (e.target.closest('[data-quitar-colectivo]')) { quitarColectivo(); return; }
    const estacionamiento = e.target.closest('[data-estacionamiento-lat]');
    if (estacionamiento) {
      if (!mapa) return;
      const coords = [Number(estacionamiento.dataset.estacionamientoLon), Number(estacionamiento.dataset.estacionamientoLat)];
      mapa.flyTo({ center: coords, zoom: 17 });
      popupAviso.setLngLat(coords).setHTML(esc(estacionamiento.dataset.estacionamientoTexto) + '<p>Inventario sin fecha de relevamiento informada. Confirmá funcionamiento y cupos.</p>').addTo(mapa);
      if (celular()) plegarPanel(false);
      return;
    }
    const inmueble = e.target.closest('[data-inmueble]');
    if (inmueble) {
      estado.delitos.inmueble = inmueble.dataset.inmueble;
      estado.capas.add('delitos');
      estado.pestana = 'entorno';
      estado.delitosDatos = null;
      renderChips(); renderPanel();
      await actualizarCapas();
      const pin = estado.delitosDatos?.inmueble;
      if (pin) { if (celular()) plegarPanel(false); encuadrarPin(pin); }
      return;
    }
    const ubicar = e.target.closest('[data-ubicar]');
    if (ubicar) {
      const aviso = estado.avisos.find((a) => a.id === ubicar.dataset.ubicar);
      if (aviso?.ubicacion) {
        if (celular()) plegarPanel(false);
        encuadrarPin(aviso);
        abrirPin(claveUbicacion(aviso));
      }
      return;
    }
    const tipoLugar = e.target.closest('[data-lugares-tipo]');
    if (tipoLugar) {
      if (tipoLugar.dataset.lugaresTipo !== estado.lugares.tipo) {
        estado.lugares.tipo = tipoLugar.dataset.lugaresTipo;
        if (estado.lugares.fase === 'inicial') renderFicha(); else cargarLugares();
      }
      return;
    }
    if (e.target.closest('#cargar-lugares')) { cargarLugares(); return; }
    if (e.target.closest('#lugares-todos')) { estado.lugares.todos = true; renderFicha(); return; }
    if (e.target.closest('#lugares-menos')) { estado.lugares.minResenas = MIN_RESENAS_BAJO; renderFicha(); return; }
    const numero = e.target.closest('[data-radar-barrio]');
    if (numero) { detalleRadar(numero.dataset.radarBarrio, numero.dataset.radarTipo); return; }
    if (e.target.closest('[data-radar-fuentes]')) { detalleFuentesRadar(); return; }
    if (e.target.closest('[data-radar-sin-barrio]')) { detalleSinBarrio(); return; }
    if (e.target.closest('#activar-alerta')) { elegirBarrioAlerta(); return; }
    if (e.target.closest('#cancelar-alerta')) { estado.eligiendoAlerta = false; estado.interes = ''; renderLista(); return; }
    if (e.target.closest('[data-quitar-interes]')) { estado.interes = ''; e.target.closest('.interes-tanda')?.remove(); return; }
    const fila = e.target.closest('[data-barrio]');
    if (fila) { seleccionar(fila.dataset.barrio); return; }
    if (e.target.closest('#volver')) { seleccionar(null); return; }
    if (e.target.closest('[data-fuentes]')) { abrirFuentes(); return; }
    if (e.target.closest('#ver-todos')) { estado.verTodos = true; renderFicha(); }
  });
  $('#contenido').addEventListener('toggle', (e) => {
    if (e.target.matches('.radar-lista')) estado.radarAbierto = e.target.open;
  }, true);
  $('#contenido').addEventListener('mouseover', (e) => {
    const fila = e.target.closest('.fila');
    marcarHover(fila ? fila.dataset.barrio : null, 'lista');
  });
  $('#contenido').addEventListener('mouseleave', () => marcarHover(null, 'lista'));

  const clicCapa = (e) => {
    const chip = e.target.closest('[data-capa]');
    if (!chip) return;
    alternarCapa(chip.dataset.capa);
    renderChips();
    renderPanel();
    actualizarCapas();
    // El cajón se vuelve a dibujar: el foco sigue en la misma capa para poder seguir con el teclado.
    $(`#${e.currentTarget.id} [data-capa="${chip.dataset.capa}"]`)?.focus({ preventScroll: true });
  };
  $('#capas').addEventListener('click', clicCapa);
  $('#capa-controles').addEventListener('change', (e) => {
    const control = e.target.dataset.control;
    if (control === 'nivel') cambiarNivel(e.target.value);
    if (['anio', 'tipo', 'franja', 'radio'].includes(control)) { estado.delitos[control] = e.target.value; actualizarCapas(); }
  });
  $('#capa-controles').addEventListener('click', (e) => {
    if (e.target.closest('[data-quitar-colectivo]')) { quitarColectivo(); return; }
    if (e.target.closest('[data-quitar-inmueble]')) { estado.delitos.inmueble = ''; actualizarCapas(); encuadrar(estado.seleccionado); }
    const boton = e.target.closest('[data-ruido]');
    if (boton && boton.dataset.ruido !== estado.ruido) {
      estado.ruido = boton.dataset.ruido;
      renderControles();
      actualizarCapas();
    }
  });
  $('#leyenda').addEventListener('click', (e) => {
    if (e.target.closest('[data-fuentes]')) {
      if (dialogoMapa.open) dialogoMapa.close();
      abrirFuentes();
    }
  });

  $('#abrir-precios').addEventListener('click', abrirPrecios);
  $('#dialogo-precios').addEventListener('click', (e) => {
    const boton = e.target.closest('[data-anotarme]');
    if (boton) anotarse(boton.dataset.anotarme);
  });
  $('#abrir-alertas').addEventListener('click', abrirAlertas);
  $('#dialogo-alertas').addEventListener('click', (e) => {
    const quitar = e.target.closest('[data-quitar-busqueda]');
    if (quitar) quitarBusqueda(quitar);
    const deshacer = e.target.closest('[data-deshacer-quitar]');
    if (deshacer) deshacerQuitar(deshacer.dataset.deshacerQuitar);
  });
  $('#dialogo-alertas').addEventListener('close', () => { [...quitando.keys()].forEach((id) => confirmarQuitar(id)); });
  window.addEventListener('pagehide', () => { [...quitando.keys()].forEach((id) => confirmarQuitar(id, true)); });
  document.querySelectorAll('[data-cerrar]').forEach((b) => b.addEventListener('click', () => b.closest('dialog').close()));
  $('#panel-asa').addEventListener('click', () => plegarPanel(!$('#panel').classList.contains('expandido')));
}

function cambiarNivel(nivel) {
  estado.nivel = nivel;
  guardar();
  sincronizarControles();
  renderPanel();
  actualizarCapas();
  if (estado.prefs.has('escuelas')) cargarParecidos();
  if (EXPLORADOR && estado.seleccionado && explorador().cercania.includes('escuelas')) {
    cargarAvisos().then(renderPanel).catch(() => {});
  }
}

// Los filtros que guarda la alerta, dichos como se ven en la barra.
function textoBusquedaAlerta() {
  const ambientes = `${estado.ambientes} ${plural(estado.ambientes, 'ambiente', 'ambientes')}${estado.ambientesOMas ? ' o más' : ''}`;
  return `hasta ${dinero(estado.presupuesto, estado.moneda)}, desde ${estado.superficie} m², ${ambientes}`;
}

// La alerta queda guardada por operación y por datos de trabajo: se dice cuál, para encontrarla después en Mis alertas.
function contextoAlerta() {
  return `${estado.operacion === 'venta' ? 'compra' : 'alquiler'}, ${estado.modo === 'demo' ? 'datos de ejemplo' : 'datos reales'}`;
}

function actualizarAlerta() {
  const campoMail = $('#mail-alerta');
  const boton = $('#crear-alerta');
  if (!campoMail || !boton || boton.getAttribute('aria-busy') === 'true') return;
  const conMail = Boolean(campoMail.value.trim());
  const acepta = $('#consentimiento-alerta')?.checked;
  $('#consentimiento-campo').hidden = !conMail;
  boton.disabled = conMail && !acepta;
}

async function crearAlerta(boton) {
  if (boton.disabled || boton.getAttribute('aria-busy') === 'true') return;
  const salida = $('#estado-alerta');
  const campoMail = $('#mail-alerta');
  const email = campoMail ? campoMail.value.trim() : '';
  if (campoMail && email && !campoMail.checkValidity()) {
    salida.className = 'estado error';
    salida.textContent = 'Revisá el mail: tiene que ser una dirección como nombre@dominio.com.';
    campoMail.setAttribute('aria-invalid', 'true');
    campoMail.focus();
    return;
  }
  const consentimiento = Boolean(email && $('#consentimiento-alerta')?.checked);
  if (email && !consentimiento) return; // el botón ya está deshabilitado; por si llega un clic igual
  // Anotarse en la primera tanda necesita el mail: es la única forma de escribirle cuando abra.
  const interes = estado.interes && campoMail ? estado.interes : '';
  if (interes && !email) {
    salida.className = 'estado error';
    salida.textContent = 'Para anotarte en la primera tanda, dejá tu mail. Si no, borrá la anotación con «No anotarme».';
    campoMail.setAttribute('aria-invalid', 'true');
    campoMail.focus();
    return;
  }
  const textoBoton = boton.textContent;
  boton.disabled = true;
  boton.setAttribute('aria-busy', 'true');
  boton.textContent = 'Creando alerta…';
  salida.className = 'estado';
  salida.textContent = '';
  try {
    const { creada, correo } = await api(`/api/busquedas?${new URLSearchParams({ modo: estado.modo, operacion: estado.operacion })}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ barrio: estado.seleccionado, presupuesto: estado.presupuesto,
        superficie: estado.superficie, ambientes: estado.ambientes, moneda: estado.moneda,
        ambientes_o_mas: estado.ambientesOMas,
        ...(email ? { email, consentimiento } : {}), ...(interes ? { interes } : {}) }),
    });
    const barrio = esc(estado.seleccionado);
    const anotado = interes && correo && correo.enviado
      ? ` Quedaste anotado en la primera tanda de «${esc(nivelInteres().nombre)}»: te escribimos cuando abra.` : '';
    const local = creada
      ? `Búsqueda guardada. Alerta creada para ${barrio}: ${contextoAlerta()}. Cuando entre un aviso nuevo que encaje, aparece en Mis alertas.`
      : `Ya tenías una alerta para ${barrio} con estos mismos filtros (${contextoAlerta()}).`;
    salida.className = correo && !correo.enviado ? 'estado error' : 'estado ok';
    salida.innerHTML = `${!correo ? local
      : correo.enviado ? `${local} También te vamos a escribir a ${esc(email)}.${anotado}`
        : `${local} No se activó el aviso por correo: ${esc(correo.motivo)}`}
      <button class="boton-texto" type="button" data-ver-alertas>Ver mis alertas</button>`;
    salida.scrollIntoView({ block: 'nearest' });
    if (correo && correo.enviado) {
      campoMail.value = '';
      $('#consentimiento-alerta').checked = false;
      if (anotado) {
        estado.interes = '';
        $('.interes-tanda')?.remove();
      }
    }
  } catch (error) {
    salida.className = 'estado error';
    salida.textContent = `No se creó la alerta: ${error.message}`;
    salida.scrollIntoView({ block: 'nearest' });
  } finally {
    boton.removeAttribute('aria-busy');
    boton.textContent = textoBoton;
    boton.disabled = false;
    actualizarAlerta();
  }
}

// Quitar una alerta: la fila ofrece «Deshacer» unos segundos y recién entonces se borra en el servidor. No hace
// falta una confirmación «¿Estás seguro?», y el esquema de la base no cambia. Al cerrar el diálogo o la página,
// lo pendiente se confirma.
const QUITAR_MS = 8000;
const quitando = new Map(); // id → { timer, modo, operacion }

function filasDeBusqueda(id) {
  return document.querySelectorAll(`#alertas-contenido tr[data-busqueda="${CSS.escape(id)}"]`);
}

function quitarBusqueda(boton) {
  const id = boton.dataset.quitarBusqueda;
  if (quitando.has(id)) return;
  const fila = boton.closest('tr');
  filasDeBusqueda(id).forEach((tr) => { tr.hidden = true; });
  fila.insertAdjacentHTML('afterend', `<tr class="fila-quitada" data-quitada="${esc(id)}"><td colspan="5">
    Quitaste la alerta de ${esc(boton.dataset.nombre)}.
    <button class="boton-texto" type="button" data-deshacer-quitar="${esc(id)}">Deshacer</button></td></tr>`);
  document.querySelector(`[data-deshacer-quitar="${CSS.escape(id)}"]`).focus();
  quitando.set(id, { modo: estado.modo, operacion: estado.operacion, timer: setTimeout(() => confirmarQuitar(id), QUITAR_MS) });
}

function deshacerQuitar(id) {
  const pendiente = quitando.get(id);
  if (!pendiente) return;
  clearTimeout(pendiente.timer);
  quitando.delete(id);
  filasDeBusqueda(id).forEach((tr) => { tr.hidden = false; });
  document.querySelector(`[data-quitada="${CSS.escape(id)}"]`)?.remove();
  document.querySelector(`[data-quitar-busqueda="${CSS.escape(id)}"]`)?.focus();
}

async function confirmarQuitar(id, alSalir = false) {
  const pendiente = quitando.get(id);
  if (!pendiente) return;
  clearTimeout(pendiente.timer);
  quitando.delete(id);
  const ruta = `/api/busquedas/${encodeURIComponent(id)}?${new URLSearchParams({ modo: pendiente.modo, operacion: pendiente.operacion })}`;
  if (alSalir) { fetch(ruta, { method: 'DELETE', keepalive: true }); return; }
  const respuesta = await fetch(ruta, { method: 'DELETE' }).catch(() => null);
  const aviso = document.querySelector(`[data-quitada="${CSS.escape(id)}"] td`);
  if (respuesta?.ok || respuesta?.status === 404) { // 404: ya la habían quitado, por ejemplo en otra pestaña
    filasDeBusqueda(id).forEach((tr) => tr.remove());
    if (aviso) aviso.textContent = 'Alerta quitada.';
    return;
  }
  // No se pudo: la alerta vuelve a su lugar, con su botón «Quitar» para intentar otra vez.
  filasDeBusqueda(id).forEach((tr) => { tr.hidden = false; });
  if (aviso) {
    aviso.parentElement.classList.add('fila-error');
    aviso.textContent = respuesta ? 'No se pudo quitar la alerta: Lüga tuvo un problema de su lado. Probá de nuevo en un momento.'
      : 'No se pudo quitar la alerta: no hay conexión con Lüga. Revisá tu conexión y probá de nuevo.';
  }
}

async function abrirAlertas() {
  const dialogo = $('#dialogo-alertas');
  const contenido = $('#alertas-contenido');
  contenido.innerHTML = '<p class="nota">Cargando…</p>';
  if (!dialogo.open) dialogo.showModal();
  try {
    const { busquedas, alertas } = await api(`/api/busquedas?${new URLSearchParams({ modo: estado.modo, operacion: estado.operacion })}`);
    const contexto = `${estado.operacion === 'venta' ? 'Compra' : 'Alquiler'} con ${estado.modo === 'demo' ? 'datos de ejemplo' : 'datos reales'}.`;
    if (!busquedas.length) {
      contenido.innerHTML = `<p class="nota">${contexto} Todavía no creaste alertas. Elegí un barrio y tocá Crear alerta.</p>`;
      return;
    }
    contenido.innerHTML = `<p class="nota">${contexto}</p>
      <h3>Alertas creadas</h3>
      <table class="tabla"><thead><tr><th>Barrio</th><th>Hasta</th><th>Desde</th><th>Ambientes</th><th><span hidden>Quitar</span></th></tr></thead><tbody>
      ${busquedas.map((b) => `<tr data-busqueda="${b.id}"><td>${esc(b.barrio)}</td><td>${dinero(b.presupuesto, b.moneda)}</td>
        <td>${b.superficie} m²</td><td>${b.ambientes}${b.ambientes_o_mas ? ' o más' : ''}</td>
        <td><button class="boton-texto" type="button" data-quitar-busqueda="${b.id}" data-nombre="${esc(b.barrio)}"
          aria-label="Quitar la alerta de ${esc(b.barrio)}">Quitar</button></td></tr>`).join('')}</tbody></table>
      ${estado.modo === 'real' ? '<p class="fuente">Quitar una alerta no da de baja los correos: para eso está el enlace que trae cada correo.</p>' : ''}
      <h3>Avisos nuevos que encajan</h3>
      ${alertas.length ? `<table class="tabla"><thead><tr><th>Barrio</th><th>Precio publicado</th><th>Cubierta</th><th>Amb.</th><th></th></tr></thead><tbody>
      ${alertas.map((a) => `<tr data-busqueda="${a.busqueda}"><td>${esc(a.barrio)}</td><td>${dinero(a.precio, a.moneda)}</td><td>${a.superficie} m²</td>
        <td>${a.ambientes}</td><td>${{ baja: 'Ya no está publicado', reservado: 'Reservado' }[a.estado]
          ?? (a.enlace ? `<a href="${esc(a.enlace)}" target="_blank" rel="noopener">Ver aviso</a>` : 'Ejemplo')}</td></tr>`).join('')}
      </tbody></table>` : '<p class="nota">Todavía no entró ningún aviso nuevo que encaje. Los avisos que ya estaban cuando creaste la alerta no cuentan.</p>'}`;
  } catch (error) {
    contenido.innerHTML = bloqueError(`No se pudieron cargar tus alertas. ${error.message}`, 'alertas');
  }
}

function nivelInteres() {
  return PRECIOS.niveles.find((n) => n.id === estado.interes) || PRECIOS.niveles.find((n) => n.recomendado);
}

function abrirPrecios() {
  $('#precios-contenido').innerHTML = renderPrecios();
  const dialogo = $('#dialogo-precios');
  if (!dialogo.open) dialogo.showModal();
}

// Un nivel pago lleva al alta de la alerta con mail, con el nivel anotado. El mail solo funciona con datos reales.
async function anotarse(nivel) {
  $('#dialogo-precios').close();
  if (nivel === 'explorar') return;
  estado.interes = nivel;
  if (estado.modo !== 'real') {
    estado.modo = 'real';
    await cambiarContexto();
  }
  if (estado.seleccionado) {
    estado.pestana = 'alerta';
    renderPanel();
    ($('#mail-alerta') || $('#crear-alerta'))?.focus();
  } else {
    elegirBarrioAlerta();
  }
}

async function abrirFuentes() {
  const dialogo = $('#dialogo-fuentes');
  const contenido = $('#fuentes-contenido');
  contenido.innerHTML = '<p class="nota">Cargando…</p>';
  if (!dialogo.open) dialogo.showModal();
  try {
    const { generado, fuentes } = await api('/api/fuentes');
    const catalogo = estado.info?.catalogo;
    contenido.innerHTML = `
      <p class="nota">Las capas se prepararon el ${esc(generado)} con datos abiertos de Buenos Aires Data, bajo licencia CC-BY 2.5 AR. La unidad geográfica es el barrio oficial.</p>
      <table class="tabla"><thead><tr><th>Capa</th><th>Período</th><th>Archivo</th></tr></thead><tbody>
      ${fuentes.map((f) => `<tr><td>${esc(f.titulo)}</td><td>${esc(f.periodo)}</td>
        <td>${f.url ? `<a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.archivo)}</a>` : esc(f.archivo)}</td></tr>`).join('')}
      </tbody></table>
      <h3>Avisos y delitos</h3>
      <p class="nota">${estado.modo === 'demo' ? 'En la demo, los avisos y los delitos son ficticios.'
        : `Avisos del catálogo autorizado ${esc(catalogo || 'sin cargar')}, con precios de publicación. Delitos del Mapa del Delito de CABA${estado.info?.delitos ? `, archivo ${esc(estado.info.delitos.archivo)}` : ''}.`}</p>`;
  } catch (error) {
    contenido.innerHTML = bloqueError(`No se pudieron cargar las fuentes. ${error.message}`, 'fuentes');
  }
}

// La barra flota sobre el mapa y puede ocupar una o dos filas: la hoja y los controles se ubican debajo.
function seguirAltoBarra() {
  const barra = document.querySelector('.barra');
  if (!barra || typeof ResizeObserver === 'undefined') return;
  const fijar = () => {
    const filas = [...barra.querySelectorAll('.marca, .barra-extremo, .filtros, .filtros-movil')].map((n) => n.getBoundingClientRect());
    const alto = Math.max(0, ...filas.map((r) => r.bottom)) - barra.getBoundingClientRect().top;
    if (alto > 0) document.documentElement.style.setProperty('--barra-real', `${Math.round(alto)}px`);
  };
  new ResizeObserver(fijar).observe(barra);
  const herramientas = document.querySelector('.mapa-arriba');
  if (herramientas) new ResizeObserver(() => {
    document.documentElement.style.setProperty('--alto-herramientas', `${Math.ceil(herramientas.getBoundingClientRect().height)}px`);
  }).observe(herramientas);
  fijar();
}

async function cargarInicio() {
  $('#contenido').innerHTML = '<p class="nota">Cargando barrios…</p>';
  try {
    await Promise.all([cargarEstado(), cargarBarrios(), cargarRadar()]);
    renderPanel();
  } catch (error) {
    $('#contenido').innerHTML = bloqueError(`No se pudieron cargar los barrios. ${error.message}`, 'inicio');
  }
}

async function iniciar() {
  seguirAltoBarra();
  renderNecesidades();
  renderLugarFijo();
  sincronizarControles();
  conectarEventos();
  if (celular()) plegarPanel(true);
  renderChips();
  precargarMapa();
  await cargarInicio();
  try {
    await prepararMapa();
    // Si la persona eligió un barrio mientras el mapa cargaba, se aplica ahora.
    if (estado.seleccionado) {
      mapa.setFeatureState({ source: 'barrios', id: estado.seleccionado }, { sel: true });
      encuadrar(estado.seleccionado, true);
    }
    pintarCoropletas();
    pintarLugarFijo();
    await actualizarCapas();
  } catch (error) {
    mostrarAvisoMapa(`El mapa no se pudo preparar: ${error.message}`);
  }
}

iniciar();
