// Genera el documento ajustado (DOCX). Los resultados se leen de salidas/pruebas/resumen.json.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun, AlignmentType,
  HeadingLevel, WidthType, BorderStyle, ShadingType, LevelFormat, PageBreak, Footer, PageNumber,
  TableOfContents, PageOrientation,
} = require("docx");

const RAIZ = path.resolve(__dirname, "..");
const R = JSON.parse(fs.readFileSync(path.join(RAIZ, "salidas/pruebas/resumen.json"), "utf8"));
const MZ = JSON.parse(fs.readFileSync(path.join(__dirname, "matriz_decision.json"), "utf8"));
const TX = require("./textos_resultados.js");

const ANCHO = 9360;
const FUENTE = "Arial";
const AZUL = "1F3B6E";
const GRIS = "E8EDF5";

// ---------------------------------------------------------------- utilidades
function runs(texto, base = {}) {
  // **negrita** y ~~cursiva~~ simples
  const partes = texto.split(/(\*\*[^*]+\*\*|~~[^~]+~~)/g).filter(Boolean);
  return partes.map((p) => {
    if (p.startsWith("**")) return new TextRun({ text: p.slice(2, -2), bold: true, ...base });
    if (p.startsWith("~~")) return new TextRun({ text: p.slice(2, -2), italics: true, ...base });
    return new TextRun({ text: p, ...base });
  });
}
const P = (t, o = {}) => new Paragraph({ children: runs(t, o.run || {}), spacing: { after: 140, line: 300 },
  alignment: o.align || AlignmentType.JUSTIFIED, ...(o.p || {}) });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)], pageBreakBefore: false });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const B = (t, nivel = 0) => new Paragraph({ numbering: { reference: "vinetas", level: nivel }, children: runs(t),
  spacing: { after: 80, line: 290 }, alignment: AlignmentType.LEFT });
const N = (t) => new Paragraph({ numbering: { reference: "numeros", level: 0 }, children: runs(t), spacing: { after: 80 } });
const SALTO = () => new Paragraph({ children: [new PageBreak()] });
const CODIGO = (lineas) => lineas.map((l, i) => new Paragraph({
  children: [new TextRun({ text: l || " ", font: "Consolas", size: 18 })],
  shading: { type: ShadingType.CLEAR, fill: "F4F4F4", color: "auto" },
  spacing: { after: i === lineas.length - 1 ? 160 : 0, line: 240 }, indent: { left: 200 } }));

const borde = { style: BorderStyle.SINGLE, size: 4, color: "B7C0CE" };
const bordes = { top: borde, bottom: borde, left: borde, right: borde };

function tabla(encabezados, filas, anchos, opciones = {}) {
  const total = anchos.reduce((a, b) => a + b, 0);
  const tam = opciones.tam || 17;
  const celda = (txt, esEnc, ancho, fill) => new TableCell({
    borders: bordes, width: { size: ancho, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: esEnc ? AZUL : (fill || "FFFFFF"), color: "auto" },
    margins: { top: 50, bottom: 50, left: 80, right: 80 },
    children: String(txt).split("\n").map((linea) => new Paragraph({ spacing: { after: 0, line: 250 },
      children: runs(linea, { size: tam, color: esEnc ? "FFFFFF" : "000000", bold: esEnc || undefined }) })),
  });
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: anchos,
    rows: [
      new TableRow({ tableHeader: true, children: encabezados.map((e, i) => celda(e, true, anchos[i])) }),
      ...filas.map((f, k) => new TableRow({ children: f.map((c, i) => celda(c, false, anchos[i],
        opciones.resaltar && opciones.resaltar(f, k) ? "FFF4D6" : (k % 2 ? "F7F9FC" : "FFFFFF"))) })),
    ],
  });
}
const ESPACIO = () => new Paragraph({ children: [], spacing: { after: 80 } });
function figura(ruta, anchoPx, altoPx, pie, anchoMax = 620, saltoAntes = false) {
  const esc = Math.min(1, anchoMax / anchoPx);
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 }, pageBreakBefore: saltoAntes, children: [new ImageRun({
      type: "png", data: fs.readFileSync(ruta), transformation: { width: Math.round(anchoPx * esc), height: Math.round(altoPx * esc) },
      altText: { title: pie, description: pie, name: path.basename(ruta) } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
      children: [new TextRun({ text: pie, italics: true, size: 18 })] }),
  ];
}
const pct = (x, d = 1) => (x === null || x === undefined) ? "—" : (100 * x).toFixed(d).replace(".", ",") + " %";
const pm = (m, s) => (m === null || m === undefined) ? "—" : `${pct(m)} ± ${pct(s)}`;
const num = (x, d = 2) => x.toFixed(d).replace(".", ",");

// ---------------------------------------------------------------- portada
const portada = [
  new Paragraph({ spacing: { before: 1800, after: 120 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: "Universidad Tecnológica de Bolívar", bold: true, size: 30 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 900 },
    children: [new TextRun({ text: "Ingeniería de Sistemas y Computación", size: 24 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 },
    children: [new TextRun({ text: "Diseño, implementación y pruebas de un agente inteligente", bold: true, size: 32, color: AZUL })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 1200 },
    children: [new TextRun({ text: "ReviewPulse-Agent — Agente de análisis de sentimientos en reseñas de hotel", italics: true, size: 26 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [new TextRun({ text: "Presentado por:", bold: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 }, children: [new TextRun("Ellen Nicole Ordoñez Chavez — T00079685")] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 700 }, children: [new TextRun("Sara Bastidas Triana — T00081674")] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 40 }, children: [new TextRun("Curso: Inteligencia Artificial")] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 1200 }, children: [new TextRun("Docente: Edwin Alexander Puertas del Castillo")] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun("Cartagena, octubre de 2026")] }),
  SALTO(),
];

// ---------------------------------------------------------------- tabla de cambios
const cambios = [
  ["Portada", "Un autor; título «Diseño inicial»; 24 de agosto de 2026.", "Pareja Ordoñez–Bastidas; título «Diseño, implementación y pruebas»; octubre de 2026.", "La Tarea 3 se entrega en parejas y el documento ahora incluye la implementación."],
  ["0 (nueva)", "—", "Matriz de decisión ponderada, sensibilidad y justificación.", "Requisito de la Fase 1."],
  ["1. Introducción", "Errores de ortografía y puntuación («problematica», enumeración sin dos puntos).", "Texto corregido; se aclara que el piloto se valida en un entorno simulado.", "Redacción y alcance real de esta entrega."],
  ["2. Tipo de agente", "Basado en modelos y orientado a objetivos, sin indicar cómo se realiza cada rasgo.", "Mismo tipo. El estado interno es la memoria de trabajo y el repositorio SQLite; las metas se alcanzan con un planificador STRIPS con búsqueda en anchura.", "Coherencia entre tipo de agente e implementación."],
  ["3. Tipos de ambiente", "Clasificación en texto corrido.", "Tabla resumen y, para cada propiedad, cómo la reproduce el simulador. El tiempo se discretiza en ciclos de 6 horas.", "Trazabilidad con el simulador (Fase 2)."],
  ["4. Entorno", "Plataformas reales TripAdvisor y Google.", "Siguen siendo las fuentes del diseño; en esta entrega se simulan con conectores que imitan su API, sus caídas y sus retrasos de publicación.", "No hay acceso a las API dentro de sus términos de uso para un proyecto de curso."],
  ["5. Entradas", "Cuatro entradas sin tipo de dato ni rango.", "Tabla con tipo, rango y origen; se agregan el reloj del ciclo y la disponibilidad de cada plataforma.", "La implementación necesita esa especificación."],
  ["6. Salidas", "Cuatro salidas sin condición de disparo.", "Tabla con actuador, condición y efecto; se agregan la marca de datos incompletos y la alerta tardía.", "Coherencia con el código."],
  ["7. Medidas de desempeño", "Metas sin fórmula; la detección decía «cualquier variación que supere el umbral», lo cual se cumple por definición.", "Cada medida con fórmula, umbral y conjunto de prueba. M1 se mide por separado para polaridad y tema en un conjunto de control. M2 pasa a ser el porcentaje de incidentes reales alertados en 24 h (≥ 90 %).", "Medibilidad: una medida que se cumple por definición no se puede probar."],
  ["8. Componentes IBM", "«una simple regla de aplicada»; modelo tipo BERT.", "Redacción corregida; el razonamiento es una prueba binomial con corrección de Bonferroni, aumento mínimo y mínimo de reseñas; el modelo es TF-IDF + léxico (BERT queda como reemplazo).", "Coherencia con la implementación (ver 9.6)."],
  ["9 (nueva)", "—", "Desarrollo del agente: arquitectura, tecnologías, entradas, salidas, diagramas de secuencia, diferencias, pruebas, limitaciones y enlaces.", "Requisito de la Fase 2."],
  ["10. Conclusiones", "Sección 9, sin resultados.", "Renumerada y basada en los resultados de las pruebas.", "Requisito de la Tarea 3."],
  ["Referencias", "Tres referencias.", "Se agregan scikit-learn, Streamlit y la referencia de prueba binomial.", "Nuevas herramientas y métodos."],
];

const seccionCambios = [
  H1("Tabla de cambios frente a la entrega anterior"),
  P("La tabla resume qué cambió en cada sección del documento de la Tarea 2 y por qué. El texto original se conserva salvo donde se indica."),
  tabla(["Sección", "Qué decía", "Qué dice ahora", "Por qué cambió"], cambios, [1500, 2400, 3060, 2400], { tam: 16 }),
  ESPACIO(),
];

// ---------------------------------------------------------------- 0. matriz de decisión
const evid = {
  "Viabilidad técnica": ["4: sabemos implementar 6 de los 7 componentes IBM (todos salvo aprendizaje en línea); clasificación de texto con scikit-learn ya vista en clase.",
                         "3: sabemos implementar 5 de 7; la función de utilidad y la recalibración supervisada con revisión de equidad son nuevas para el equipo."],
  "Disponibilidad de datos o entorno": ["4: existe un corpus de reseñas de TripAdvisor en español (IberLEF 2021) y el flujo semanal se puede simular con incidentes conocidos.",
                                        "3: el dataset IBM HR de Kaggle (1.470 empleados) es de un solo corte; no trae trayectoria mensual ni fecha de renuncia, que habría que inventar."],
  "Medibilidad del desempeño": ["5: 4 de 4 medidas se pueden escribir con fórmula y umbral, y el simulador conoce la verdad (incidentes y etiquetas).",
                                "3: 1 medida (precisión ≥ 75 %); requiere saber quién renunció en los 3 meses siguientes, dato que el dataset no tiene."],
  "Complejidad de IA": ["3: basado en modelos y orientado a metas (estado interno + planificación).",
                        "5: basado en utilidad con aprendizaje supervisado periódico."],
  "Costo y recursos": ["5: 0 COP; Python y bibliotecas libres, sin API pagas ni GPU.", "5: 0 COP; mismas condiciones."],
  "Valor del problema": ["3: gerente de un hotel piloto; detecta quejas en 24 h en lugar de leerlas a mano cada semana.",
                         "4: área de RR. HH.; anticipar renuncias evita costos de reemplazo, que suelen ser altos."],
};
const filasMatriz = MZ.sensibilidad.length && [
  ["Viabilidad técnica", 0.25, 4, 3], ["Disponibilidad de datos o entorno", 0.20, 4, 3], ["Medibilidad del desempeño", 0.20, 5, 3],
  ["Complejidad de IA", 0.15, 3, 5], ["Costo y recursos", 0.10, 5, 5], ["Valor del problema", 0.10, 3, 4],
].map(([c, w, a, b]) => [c, pct(w, 0), String(a), evid[c][0], String(b), evid[c][1]]);
filasMatriz.push(["**Puntaje ponderado S**", "100 %", `**${num(MZ.puntajes.ReviewPulse)}**`, "S = Σ wᵢ × pᵢ", `**${num(MZ.puntajes.RetainIQ)}**`, "S = Σ wᵢ × pᵢ"]);

const sensMed = MZ.sensibilidad.filter((s) => s.criterio === MZ.criterio_mas_influyente);
const seccionMatriz = [
  H1("0. Selección justificada del agente"),
  P("La pareja tenía asignados dos diseños: **ReviewPulse-Agent** (análisis de sentimiento en reseñas de hotel, agente A) y **RetainIQ-Agent** (predicción de rotación de empleados, agente B). Los pesos se fijaron antes de puntuar, con los valores sugeridos por la guía, porque reflejan bien la restricción principal del equipo: construir y probar el agente en el tiempo del curso. El cálculo completo está en el repositorio (docs/matriz_decision.py), de modo que cualquier persona puede reproducirlo."),
  tabla(["Criterio", "Peso (w)", "A (1–5)", "A: evidencia", "B (1–5)", "B: evidencia"], filasMatriz,
        [1500, 700, 700, 2880, 700, 2880], { tam: 15 }),
  ESPACIO(),
  P(`Cálculo para A: 0,25×4 + 0,20×4 + 0,20×5 + 0,15×3 + 0,10×5 + 0,10×3 = **${num(MZ.puntajes.ReviewPulse)}**. Para B: 0,25×3 + 0,20×3 + 0,20×3 + 0,15×5 + 0,10×5 + 0,10×4 = **${num(MZ.puntajes.RetainIQ)}**.`),
  H2("Análisis de sensibilidad"),
  P(`El criterio más influyente es el que más pesa en la diferencia entre los dos agentes, |wᵢ × (pᵢᴬ − pᵢᴮ)|: **${MZ.criterio_mas_influyente.toLowerCase()}** (0,20 × 2 = 0,40), seguido de complejidad de IA (0,30, a favor de B). Al subir o bajar su peso 10 puntos y repartir la diferencia entre los demás criterios en proporción a su peso, el resultado es:`),
  tabla(["Cambio en medibilidad", "Peso nuevo", "S (A) ReviewPulse", "S (B) RetainIQ", "Elegido"],
        sensMed.map((s) => [s.cambio.replace("%", " puntos"), pct(s.peso_nuevo, 0), num(s.ReviewPulse, 3), num(s.RetainIQ, 3), s.ganador]),
        [2200, 1400, 2000, 2000, 1760]),
  ESPACIO(),
  P("Se repitió la prueba con los seis criterios (±10 puntos cada uno, 12 combinaciones): ReviewPulse gana en todas. El caso más estrecho es subir complejidad de IA a 25 %, donde la ventaja baja a 0,16 puntos. La decisión no depende de un peso en particular."),
  H2("Justificación"),
  P(`Se elige **ReviewPulse-Agent** con ${num(MZ.puntajes.ReviewPulse)} frente a ${num(MZ.puntajes.RetainIQ)}. Gana porque sus cuatro medidas de desempeño se pueden probar de forma objetiva contra una verdad conocida y porque su entorno se puede simular respetando cada propiedad declarada en la sección 3. RetainIQ depende de datos laborales mensuales y de renuncias futuras que no tenemos, y su única medida no se podría verificar sin inventar esos datos.`),
  P("**Qué se pierde al descartar RetainIQ-Agent:** la parte de utilidad y de aprendizaje supervisado, que es la de mayor complejidad de IA, y un problema con impacto económico directo para Recursos Humanos. Para compensar en parte, ReviewPulse incorpora planificación por metas con búsqueda y una regla de decisión estadística, no solo condicionales."),
];

// ---------------------------------------------------------------- 1 a 8 (diseño corregido)
const diseno = [
  H1("1. Introducción y planteamiento del problema"),
  P("Antes de reservar una habitación, gran parte de los huéspedes revisa lo que otras personas han escrito en plataformas como TripAdvisor o Google. Ese hábito deja un volumen de comentarios que crece de forma constante y que rara vez tiene una estructura ordenada: son textos libres, escritos con distinto nivel de detalle, que mezclan opiniones sobre la limpieza, el servicio, la ubicación o el precio sin seguir ningún criterio fijo. Revisar ese material a mano, reseña por reseña, se vuelve insostenible a medida que el hotel gana visibilidad, y además llega tarde: para cuando alguien del equipo nota un patrón de quejas, es posible que varias semanas de huéspedes ya hayan tenido una experiencia deficiente sin que nadie interviniera."),
  P("De esa problemática surge ReviewPulse-Agent, un agente inteligente que clasifica automáticamente cada reseña de un hotel piloto según su polaridad (positiva, negativa o neutra) y su tema principal, y que detecta cuándo el tono de esas reseñas se aparta de lo habitual. No es un problema que se resuelva con una búsqueda de palabras clave. Exige tres cosas: interpretar lenguaje natural con sus ambigüedades, mantener memoria de las semanas anteriores para poder comparar y decidir a tiempo cuándo una variación merece la atención del gerente. Interpretación, memoria y oportunidad son las que justifican un agente inteligente en lugar de un mecanismo de reglas fijas."),
  P("En esta entrega el agente se implementa y se prueba sobre un entorno simulado del hotel piloto (sección 9), porque no hay acceso a las API de las plataformas dentro de sus términos de uso para un proyecto de curso."),
  H1("2. Tipo de agente inteligente"),
  P("Siguiendo la clasificación de Russell y Norvig en ~~Artificial Intelligence: A Modern Approach~~, ReviewPulse-Agent es un **agente basado en modelos con orientación a objetivos**. Es basado en modelos porque una sola reseña no dice casi nada sobre si algo está cambiando: para saber si un aumento de comentarios negativos es una anomalía, el agente compara lo que ve ahora contra lo que vio en semanas pasadas, y esa comparación solo es posible si conserva y actualiza una representación interna del comportamiento habitual del hotel. En la implementación, ese estado interno es la memoria de trabajo (conteos de la semana abierta) y el repositorio histórico (agregados semanales, alertas y reportes)."),
  P("Es orientado a objetivos porque persigue metas explícitas: mantener los conteos al día, entregar el resumen semanal dentro de 24 horas y revisar semanas cerradas cuando llegan reseñas tardías. En cada ciclo el agente describe su situación con hechos (hay lote nuevo, la semana cerró, la plataforma responde) y un planificador busca la secuencia de acciones que alcanza la meta. Si la meta no es alcanzable todavía, por ejemplo porque una plataforma está caída y aún hay plazo, el plan cambia a esperar. Eso descarta tanto al agente reflejo simple como a uno basado en modelos sin metas."),
  P("No es un agente basado en utilidad, porque no pondera de forma continua distintos estados del entorno con una función de utilidad, ni un agente de aprendizaje en sentido estricto, porque el modelo de sentimiento se entrena antes del despliegue y el agente no ajusta sus parámetros mientras opera."),
  H1("3. Tipos de ambiente"),
  tabla(["Dimensión", "Clasificación", "Justificación", "Cómo lo reproduce el simulador"], [
    ["Observabilidad", "Parcialmente observable", "El agente solo ve el texto, la fecha, la plataforma y la calificación; no ve qué pasó en la estadía ni qué opinan quienes no escriben.", "El estado operativo del hotel (incidentes por tema) existe en el simulador, pero el agente nunca lo lee."],
    ["Determinismo", "Estocástico", "Reseñas parecidas pueden clasificarse distinto por ironía o expresiones regionales; el volumen semanal es incierto.", "Volumen Poisson, polaridad y tema aleatorios, ironía, errores de tipeo y caídas de plataforma."],
    ["Episodicidad", "Secuencial", "Notar un cambio solo tiene sentido frente a las semanas anteriores.", "14 semanas encadenadas; cada semana se compara con las 6 anteriores."],
    ["Dinamismo", "Dinámico", "Las reseñas siguen publicándose mientras el agente procesa.", "Cada reseña se vuelve visible con un retraso aleatorio de hasta 30 h; una reseña del domingo puede llegar el lunes, después del cierre."],
    ["Discretización", "Discreto", "Reseñas contables, categorías cerradas y cortes semanales.", "El agente actúa en ciclos fijos de 6 horas."],
    ["Número de agentes", "Agente único", "Las plataformas y el canal de notificación son herramientas, no agentes con objetivos propios.", "Un solo agente; las plataformas son conectores."],
  ], [1450, 1500, 3300, 3110], { tam: 16 }),
  ESPACIO(),
  H1("4. Descripción del entorno"),
  P("ReviewPulse-Agent opera en un espacio deliberadamente acotado: un único hotel piloto y las reseñas públicas que acumula en TripAdvisor y Google. Conviven tres actores: los huéspedes, que generan la materia prima del sistema cada vez que escriben un comentario; el gerente del hotel, que recibe los resúmenes semanales y las alertas y decide qué hacer con esa información; y las plataformas de reseñas, que son una fuente externa de datos que el agente no controla."),
  P("El entorno tiene límites claros. El agente solo puede recolectar información respetando los términos de uso de cada plataforma, depende de un modelo de sentimiento para el español de reseñas de hospedaje y su alcance no va más allá del hotel piloto. En un día cualquiera llega un flujo moderado de reseñas (unas 36 por semana en el simulador) con una distribución de opiniones estable. Pero también puede pasar que un problema de servicio dispare los comentarios negativos, que una plataforma quede inaccesible, que aparezcan reseñas en otro idioma o cargadas de ironía, o que la temporada alta traiga más huéspedes y más información para procesar. Los doce escenarios de prueba de la sección 9.7 cubren cada uno de estos casos."),
  H1("5. Entradas y sensores"),
  P("Todas las entradas se capturan por mecanismos digitales; no hay sensores físicos. La sección 9.3 detalla tipo, rango y un ejemplo real de cada una."),
  tabla(["Entrada", "Sensor (mecanismo)", "Uso en la decisión"], [
    ["Texto de la reseña", "Conector de cada plataforma: consulta de reseñas visibles desde el último cursor", "Insumo del clasificador de polaridad y tema"],
    ["Metadatos: identificador, fecha, plataforma, calificación de 1 a 5", "Mismo conector, en la misma consulta", "La fecha asigna la semana; la calificación se guarda en el reporte"],
    ["Disponibilidad de cada plataforma", "Resultado de la consulta (éxito o PlataformaNoDisponible)", "Decide si esperar reintento o cerrar con datos incompletos"],
    ["Historial del hotel", "Consulta al repositorio SQLite", "Línea base de comparación de las últimas 6 semanas"],
    ["Parámetros de configuración", "config.json o ajustes de las alertas de la interfaz", "Umbrales de la regla de alerta"],
    ["Reloj del ciclo", "Planificador de ejecución cada 6 horas", "Determina qué semanas cerraron y cuántas horas han pasado"],
  ], [2800, 3300, 3260], { tam: 17 }),
  ESPACIO(),
  H1("6. Salidas y actuadores"),
  tabla(["Acción", "Actuador", "Condición que la dispara", "Efecto en el entorno"], [
    ["Etiqueta de clasificación", "Escritura en la tabla resenas (SQLite)", "Cada reseña válida del lote", "La reseña queda con polaridad, tema, confianza y marca de revisión manual si la confianza es menor de 0,55"],
    ["Alerta al gerente", "Notificador: correo SMTP o bandeja de salida JSONL", "Al cierre semanal, si un tema supera la regla de alerta", "El gerente recibe un mensaje en lenguaje natural con la proporción, el promedio y dos ejemplos"],
    ["Alerta tardía", "Notificador", "Llegan reseñas atrasadas de una semana ya cerrada y la reevaluación supera la regla", "Aviso marcado como tardío"],
    ["Resumen semanal por tema", "Generador de reportes (Markdown y JSON)", "Semana cerrada, con margen de 12 h o en el último ciclo antes de 24 h", "Reporte con conteos por tema y marca de datos incompletos si alguna plataforma falló"],
    ["Registro histórico", "Escritura en tablas semanas, alertas y reportes", "Después de cada reporte", "Línea base para las semanas siguientes y trazabilidad"],
    ["Descarte de entrada", "Escritura en la tabla descartadas", "Texto vacío, otro idioma, HTML sin contenido o sin fecha", "La reseña no entra a los conteos"],
  ], [1900, 2300, 2500, 2660], { tam: 16 }),
  ESPACIO(),
  H1("7. Medidas de desempeño"),
  P("Las medidas se reescribieron con fórmula, umbral y conjunto de prueba para que se puedan verificar de forma objetiva. Los umbrales se fijaron antes de ejecutar las pruebas (pruebas/umbrales.json) y no se modificaron después."),
  tabla(["Medida", "Fórmula", "Umbral", "Conjunto y plazo"], [
    ["M1 Exactitud de clasificación", "Reseñas con polaridad correcta / reseñas evaluadas; igual para el tema", "≥ 85 % en polaridad y ≥ 85 % en tema", "Conjunto de control de 40 reseñas redactadas aparte del corpus de entrenamiento, con asistencia de IA (ver bitácora), nunca usado para ajustar el modelo; 5 reentrenamientos"],
    ["M2 Detección de cambios en el sentimiento", "Incidentes relevantes alertados ≤ 24 h tras el cierre / incidentes relevantes", "≥ 90 %", "12 escenarios × 5 semillas; el simulador sabe qué semanas tuvieron un incidente real"],
    ["M3 Generación oportuna de reportes", "Reportes entregados ≤ 24 h tras el cierre / semanas cerradas", "100 %", "Las mismas 60 corridas"],
    ["M4 Errores de notificación", "Alertas sin incidente relevante / alertas enviadas", "< 10 %", "Las mismas 60 corridas"],
  ], [2100, 2900, 1600, 2760], { tam: 16 }),
  ESPACIO(),
  P("M2 se reformuló porque la versión anterior («reconocer cualquier variación que supere el umbral») se cumple por definición: el agente siempre reconoce lo que su propio umbral marca. La versión nueva compara las alertas contra incidentes reales conocidos por el simulador, que es lo que le importa al gerente."),
  H1("8. Componentes de la arquitectura de IA agéntica (marco IBM)"),
  P("De acuerdo con la arquitectura de IA agéntica descrita por IBM, los componentes de un agente se agrupan en siete áreas funcionales. Así las implementa ReviewPulse-Agent; la sección 9.1 indica el módulo de código de cada una."),
  H3("Percepción y manejo de entradas"),
  P("El método percibir() consulta cada seis horas las plataformas del hotel en busca de reseñas nuevas y recoge, junto con el texto, sus metadatos. Antes de que el contenido llegue al clasificador pasa por una limpieza: se quitan etiquetas HTML y entidades, se verifica el idioma, se descartan textos vacíos o sin fecha y se normaliza el formato."),
  H3("Planificación y descomposición de tareas"),
  P("La meta de fondo (tener al gerente informado sobre cómo perciben los huéspedes al hotel) se divide en metas concretas y en acciones con precondiciones y efectos: limpiar el lote, clasificarlo, actualizar los conteos, comparar con el historial, decidir la alerta, generar el reporte y registrar el historial. Un planificador tipo STRIPS con búsqueda en anchura encuentra en cada ciclo la secuencia que lleva a la meta activa."),
  H3("Memoria"),
  P("En el corto plazo, mientras la semana sigue abierta, el agente mantiene en memoria de trabajo el conteo de reseñas por tema y polaridad. En el largo plazo guarda en un repositorio SQLite las reseñas etiquetadas, los agregados de semanas anteriores, los resúmenes entregados y las alertas enviadas. Esa memoria le da contra qué comparar y deja trazabilidad de lo que hizo y por qué."),
  H3("Razonamiento y toma de decisiones"),
  P("Decidir si algo amerita una alerta no es una regla aplicada a ciegas. Para cada tema, el agente compara la proporción de reseñas negativas de la semana con la de las seis semanas anteriores mediante una prueba binomial con corrección de Bonferroni (porque se evalúan cuatro temas a la vez), y exige además un aumento mínimo de la proporción y un mínimo de reseñas negativas. La confianza de cada clasificación también entra al razonamiento: las reseñas con confianza menor de 0,55 cuentan la mitad y se marcan para revisión manual."),
  H3("Llamada de herramientas y acción (tool calling)"),
  P("El agente se apoya en herramientas externas para cada parte del proceso: el modelo de sentimiento para clasificar polaridad y tema, los conectores hacia las plataformas, la base de datos SQLite para leer y escribir el historial, el generador de reportes y el notificador que envía la alerta al gerente."),
  H3("Comunicación"),
  P("Los resultados se presentan para un usuario no técnico: el resumen semanal por tema, como reporte y como panel en la interfaz, y alertas en lenguaje natural que dicen qué se detectó, cuánto subió frente al promedio y dan dos ejemplos de reseñas."),
  H3("Aprendizaje y adaptación"),
  P("En esta versión el modelo de sentimiento se entrena antes de ponerse en marcha y el agente no lo ajusta mientras opera. Queda como paso a futuro usar las reseñas que el gerente revise manualmente para reentrenar el modelo cada cierto tiempo."),
  SALTO(),
];

module.exports = { portada, seccionCambios, seccionMatriz, diseno, tabla, P, H1, H2, H3, B, N, CODIGO, figura, ESPACIO, SALTO,
  pct, pm, num, R, TX, AZUL, FUENTE, Document, Packer, Paragraph, TextRun, AlignmentType, HeadingLevel, LevelFormat, Footer,
  PageNumber, TableOfContents, PageOrientation };
