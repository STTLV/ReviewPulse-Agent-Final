// Arma el documento completo: node docs/armar_documento.js
const fs = require("fs");
const path = require("path");
const D = require("./construir_documento.js");
const { tabla, P, H1, H2, H3, B, CODIGO, figura, ESPACIO, SALTO, pct, pm, num, R, TX } = D;
const { Document, Packer, Paragraph, TextRun, AlignmentType, HeadingLevel, LevelFormat, Footer, PageNumber } = D;

const DOCS = __dirname;
const ENLACES = TX.enlaces;
if (!ENLACES.despliegue || !/^https:\/\/.+\.streamlit\.app\/?$/i.test(ENLACES.despliegue)) {
  throw new Error("Antes de generar el documento final, define REVIEWPULSE_STREAMLIT_URL con la URL real de la aplicación publicada en Streamlit, por ejemplo: REVIEWPULSE_STREAMLIT_URL='https://tu-app.streamlit.app' node docs/armar_documento.js");
}

// ---------------------------------------------------------------- 9.1 arquitectura
const s91 = [
  H1("9. Desarrollo del agente"),
  H2("9.1 Arquitectura"),
  P("El agente es un paquete de Python (reviewpulse) con un núcleo, ReviewPulseAgent, que ejecuta cada seis horas de tiempo simulado el ciclo percepción → decisión → acción. El entorno, que en producción serían las API de las plataformas, es un simulador con la misma interfaz que tendría un conector real. La figura 1 muestra los componentes y sus conexiones."),
  ...figura(path.join(DOCS, "arquitectura.png"), 2662, 1733, "Figura 1. Diagrama de componentes de ReviewPulse-Agent. Entre corchetes, el componente IBM que implementa."),
  P("El ciclo está en el método paso() de reviewpulse/agente.py:"),
  ...CODIGO([
    "def paso(self, ahora):",
    "    per  = self.percibir(ahora)   # PERCEPCIÓN: conectores, historial, config",
    "    plan = self.decidir(per)      # DECISIÓN: hechos -> meta -> plan (BFS)",
    "    self.actuar(plan, per)        # ACCIÓN: etiquetas, alerta, reporte, registro",
  ]),
  tabla(["Componente IBM", "Módulo y función", "Estado"], [
    ["1. Percepción y manejo de entradas", "agente.percibir(); preprocesamiento.validar(), limpiar(), detectar_idioma(); entorno.consultar()", "Implementado"],
    ["2. Planificación y descomposición", "planificador.planificar() (STRIPS + BFS); agente.decidir() y agente._hechos()", "Implementado"],
    ["3. Memoria", "memoria.MemoriaTrabajo (corto plazo); memoria.RepositorioHistorico (SQLite, largo plazo)", "Implementado"],
    ["4. Razonamiento y toma de decisiones", "agente._evaluar_semana(): prueba binomial con Bonferroni, aumento mínimo, mínimo de negativas; umbral de confianza", "Implementado"],
    ["5. Llamada de herramientas y acción", "agente.actuar() y métodos _a_*; modelo.ClasificadorSentimiento.predecir(); actuadores.Notificador, GeneradorReporte", "Implementado"],
    ["6. Comunicación", "actuadores.Notificador.redactar() (alerta en lenguaje natural); GeneradorReporte.generar(); app/streamlit_app.py", "Implementado"],
    ["7. Aprendizaje y adaptación", "modelo.entrenar_modelo_base() se ejecuta antes del despliegue", "No implementado en línea: el diseño lo deja como trabajo futuro (sección 8) y reentrenar sin etiquetas del gerente propagaría los errores del propio modelo"],
  ], [2600, 4560, 2200], { tam: 16 }),
  ESPACIO(),
];

// ---------------------------------------------------------------- 9.2 tecnologías
const s92 = [
  H2("9.2 Tecnologías"),
  tabla(["Tecnología", "Versión", "Para qué se usó", "Por qué frente a una alternativa"], [
    ["Python", "3.13", "Lenguaje de todo el agente, el simulador y las pruebas", "Frente a Java: el equipo lo maneja y tiene el ecosistema de aprendizaje automático"],
    ["scikit-learn", "1.9.1", "TF-IDF de palabras y caracteres, regresión logística multinomial", "Frente a un BERT (transformers): corre sin GPU ni descarga de modelos, entrena en 4 s y da probabilidades calibradas"],
    ["Léxico propio (lexico.py)", "1.0", "Rasgos de polaridad y tema con manejo de negación", "Frente a un léxico genérico en inglés (VADER): está escrito para español de reseñas de hospedaje"],
    ["NumPy", "2.5.3", "Matriz de rasgos del léxico", "Dependencia de scikit-learn"],
    ["SQLite (sqlite3)", "3.45", "Repositorio histórico: reseñas, semanas, alertas, reportes", "Frente a PostgreSQL: no requiere servidor y el archivo queda como evidencia de cada corrida"],
    ["joblib", "1.6", "Guardar y cargar el modelo entrenado", "Formato estándar de scikit-learn"],
    ["pandas", "2.3", "Tablas y gráficos de la interfaz", "Integración directa con Streamlit"],
    ["Streamlit", "1.66", "Interfaz web y despliegue (opción A)", "Frente a Flask: interfaz en un solo archivo y hosting gratuito en Streamlit Community Cloud"],
    ["Mermaid CLI", "11.16", "Diagramas de secuencia UML", "Frente a draw.io: el diagrama es texto versionado junto al código"],
    ["Graphviz", "2.43", "Diagrama de componentes", "Distribución automática de nodos"],
    ["docx (Node.js)", "9.7", "Generar este documento con los resultados leídos de los logs", "Las cifras del documento salen del mismo archivo que las pruebas"],
    ["Claude (Anthropic)", "Opus 5.5", "Asistente de programación y redacción durante el desarrollo (ver bitácora de IA)", "No interviene en tiempo de ejecución"],
  ], [1900, 900, 3200, 3360], { tam: 16 }),
  ESPACIO(),
  P("**Qué hace el código propio y qué hace cada herramienta.** El código propio hace la percepción, la validación, la planificación, la comparación estadística, la decisión de alertar, la redacción de la alerta, el reporte y la gestión de la memoria. scikit-learn solo entrega la probabilidad de cada polaridad y cada tema para un texto. SQLite solo guarda y devuelve datos. No se usa ningún modelo de lenguaje grande: ninguna decisión del agente depende de un LLM."),
];

// ---------------------------------------------------------------- 9.3 entradas
const s93 = [
  H2("9.3 Entradas (inputs)"),
  P("Ejemplos tomados del log de la corrida E02, semilla 11 (salidas/pruebas/corridas/E02_s11)."),
  tabla(["Percepción", "Tipo de dato", "Rango o formato", "Origen", "Ejemplo real"], [
    ["id", "Texto", "R00001–R99999", "API del conector", "R00344"],
    ["texto", "Texto UTF-8", "0 a ~1.000 caracteres; puede traer HTML, emojis o venir vacío", "API del conector", "«Había cucarachas en el cuarto, un asco. Pedimos aseo varias veces y nadie apareció. Qué decepción.»"],
    ["plataforma", "Categórico", "{TripAdvisor, Google}", "API del conector", "TripAdvisor"],
    ["fecha", "Fecha y hora ISO 8601", "Dentro de las 14 semanas simuladas; puede ser nula", "API del conector", "2026-03-10T02:05:37"],
    ["calificacion", "Entero o nulo", "1 a 5; nulo en ~15 % de TripAdvisor", "API del conector", "1"],
    ["disponibilidad", "Booleano por plataforma", "true / false", "Resultado de la consulta", "{TripAdvisor: true, Google: true}"],
    ["historial", "Registros JSON por semana", "Hasta 6 semanas previas; conteos por tema y polaridad", "Repositorio SQLite", "semana 8: limpieza {negativa: 2, neutra: 3, positiva: 6}"],
    ["configuracion", "Números reales y enteros", "alfa 0,001–0,2; delta 0–0,5; mínimo de negativas 1–10; confianza 0,3–0,9", "config.json o interfaz", "alfa 0,08; delta 0,25; mínimo 6; confianza 0,55"],
    ["reloj", "Fecha y hora", "Cada 6 h", "Bucle de ejecución", "2026-03-16T12:00:00"],
  ], [1350, 1450, 2350, 1500, 2710], { tam: 15 }),
  ESPACIO(),
];

// ---------------------------------------------------------------- 9.4 salidas
const s94 = [
  H2("9.4 Salidas y acciones"),
  tabla(["Acción (método)", "Efecto en el entorno", "Ejemplo real (E02, semilla 11)"], [
    ["_a_clasificar_lote()", "Fila en la tabla resenas con polaridad, tema y confianza", "R00344 → negativa, limpieza, confianza 0,998"],
    ["_a_limpiar_lote()", "Fila en la tabla descartadas con el motivo", "R00002 → idioma_pt"],
    ["_a_decidir_alerta()", "Mensaje en bandeja_salida.jsonl (o correo SMTP)", "«las reseñas negativas sobre limpieza subieron a 70 % (8 de 12), frente a un promedio de 26 % en las últimas 6 semanas…»"],
    ["_a_generar_reporte()", "reportes/semana_NN.md y .json", "semana_09.md generado el lunes 16/03 a las 12:00, 12 h después del cierre"],
    ["_a_registrar_historial()", "Fila en la tabla semanas; la semana pasa a ser línea base", "semana 9 marcada con alerta (se excluye de la línea base siguiente)"],
    ["_a_reevaluar_semanas_tardias()", "Alerta de tipo «tardía» si las reseñas atrasadas cambian la decisión", "Ver escenario E11"],
    ["esperar (decisión)", "Ningún cambio; queda registrado el motivo", "«esperar margen de reseñas tardías (6 h de 12 h)»"],
  ], [2500, 3300, 3560], { tam: 16 }),
  ESPACIO(),
  P("Cada percepción, decisión y acción queda en log_ejecucion.jsonl con la marca de tiempo real y la simulada. Ejemplo de la decisión que cierra la semana 9:"),
  ...CODIGO([
    '{"ts_simulado": "2026-03-16T12:00:00", "fase": "DECISION",',
    ' "evento": "plan", "semana": 9, "motivo": "plan completo",',
    ' "meta": "mantener_conteos_al_dia+entregar_resumen_semanal",',
    ' "acciones": ["limpiar_lote", "clasificar_lote",',
    '   "actualizar_conteos", "comparar_historial", "decidir_alerta",',
    '   "generar_reporte", "registrar_historial"],',
    ' "hechos": ["lote_nuevo", "puede_cerrar", "semana_cerrada"]}',
  ]),
];

// ---------------------------------------------------------------- 9.5 secuencia
const s95 = [
  H2("9.5 Diagramas de secuencia UML"),
  P("La figura 2 muestra el escenario típico: el ciclo de cada seis horas (loop), la clasificación del lote y, al cierre de la semana, la decisión de alertar o no (alt). La figura 3 muestra el escenario de excepción: TripAdvisor no responde al cierre y el agente espera, reintenta y, si se acaba el plazo, entrega el reporte marcado como incompleto. Las fuentes están en docs/secuencia_tipico.mmd y docs/secuencia_excepcion.mmd; los nombres de los mensajes son los de los métodos del código."),
  ...figura(path.join(DOCS, "secuencia_tipico.png"), TX.dim.tipico[0], TX.dim.tipico[1], "Figura 2. Diagrama de secuencia, escenario típico.", 820),
  ...figura(path.join(DOCS, "secuencia_excepcion.png"), TX.dim.excepcion[0], TX.dim.excepcion[1], "Figura 3. Diagrama de secuencia, escenario de excepción (plataforma caída al cierre).", 860, true),
];

// ---------------------------------------------------------------- 9.6 diferencias
const s96 = [
  H2("9.6 Diferencias entre diseño e implementación"),
  tabla(["Aspecto", "Diseño", "Implementación", "Por qué"], [
    ["Fuente de reseñas", "TripAdvisor y Google reales", "Simulador con conectores de la misma forma", "Sin acceso legal a las API para el curso; el simulador además conoce la verdad, lo que permite medir M2 y M4"],
    ["Modelo de sentimiento", "BERT ajustado para español (IberLEF 2021)", "TF-IDF + léxico + regresión logística; clase ClasificadorBERT como punto de reemplazo", "El entorno donde se construyó y probó el agente (el entorno de trabajo del asistente de IA) no tenía GPU ni acceso a Hugging Face; se conserva la interfaz para cambiarlo"],
    ["Datos de entrenamiento", "Reseñas reales etiquetadas", "Corpus sintético de 4.000 reseñas generado con plantillas y ruido", "El corpus de IberLEF se entrega bajo solicitud y no se usó en esta entrega"],
    ["Regla de alerta", "«comparación estadística frente al historial»", "Prueba binomial con Bonferroni (α = 0,08 global), aumento ≥ 25 puntos y ≥ 6 negativas; parámetros calibrados con semillas 101–105", "Concretar la regla; calibrar sin tocar las semillas de prueba"],
    ["Reseñas ambiguas", "«tratamiento distinto»", "Confianza < 0,55: cuentan 0,5 y se marcan para revisión manual", "Concretar el tratamiento"],
    ["Reseñas tardías", "No contemplado", "Reevaluación de semanas cerradas y alerta tardía", "El ambiente es dinámico"],
    ["Notificación", "Correo o mensajería", "Bandeja JSONL; SMTP opcional", "Evitar enviar correos reales en las pruebas"],
  ], [1600, 2100, 2860, 2800], { tam: 15 }),
  ESPACIO(),
];

// ---------------------------------------------------------------- 9.7 pruebas
const a = R.agregado_todos, b = R.agregado_sin_fallas_esperadas, U = R.umbrales, c3 = R.m1.C03, V = R.veredicto;
const si = (x) => (x ? "Sí" : "No");
const filasResultado = [
  ["M1 Exactitud de clasificación", "aciertos / reseñas evaluadas, por separado para polaridad y tema", "≥ 85 % en ambas",
   "11 casos (3 normales, 6 límite, 2 de falla) × 5 reentrenamientos",
   `Control C03 (n = 40): polaridad ${pm(c3.polaridad_media, c3.polaridad_de)}; tema ${pm(c3.tema_media, c3.tema_de)}`, si(V.M1), "m1_clasificacion.csv; minuto 14:00"],
  ["M2 Detección de cambios en 24 h", "incidentes relevantes alertados ≤ 24 h tras el cierre / incidentes relevantes", "≥ 90 %",
   `12 escenarios × 5 semillas = ${a.corridas} corridas; ${a.incidentes} incidentes`,
   `${pct(a.tasa_deteccion)} (${a.detectados_24h}/${a.incidentes}); por corrida ± ${pct(a.deteccion_de_por_corrida)}`, si(V.M2), "escenarios.csv; corridas/*/log_ejecucion.jsonl; minuto 16:30"],
  ["M3 Reporte semanal a tiempo", "reportes ≤ 24 h tras el cierre / semanas cerradas", "100 %",
   `${a.corridas} corridas; ${a.semanas} semanas`, `${pct(a.tasa_reportes)} (${a.reportes_a_tiempo}/${a.semanas}); latencia máxima ${num(a.latencia_reporte_max_h, 0)} h`, si(V.M3), "corridas/*/reportes/; minuto 10:30"],
  ["M4 Falsos positivos de alerta", "alertas sin incidente relevante / alertas enviadas", "< 10 %",
   `${a.corridas} corridas; ${a.alertas} alertas`, `${pct(a.tasa_fp)} (${a.fp}/${a.alertas}); por corrida ± ${pct(a.fp_de_por_corrida)}`, si(V.M4), "corridas/*/bandeja_salida.jsonl; minuto 16:30"],
];
const filasM1 = Object.entries(R.m1).map(([k, c]) => [k, c.descripcion, c.tipo, String(c.n),
  c.polaridad_media !== null ? pm(c.polaridad_media, c.polaridad_de) : "—",
  c.tema_media !== null ? pm(c.tema_media, c.tema_de) : "—",
  c.rechazo_media !== null ? pm(c.rechazo_media, c.rechazo_de) : "—", si(c.cumple)]);
const filasEsc = Object.entries(R.escenarios).map(([k, e]) => [e.nombre, e.tipo,
  e.deteccion_media !== null ? pm(e.deteccion_media, e.deteccion_de) : "sin incidente",
  String(e.detectados_tarde_total), pm(e.reportes_media, e.reportes_de), String(e.alertas_total),
  `${e.fp_total} (${num(e.fp_media_por_corrida, 1)} ± ${num(e.fp_de, 1)})`]);

const s97 = [
  H2("9.7 Pruebas"),
  P(`Los umbrales se fijaron el 15 de octubre de 2026 en pruebas/umbrales.json antes de la primera ejecución completa. Cada medida se probó con al menos 10 casos, incluyendo casos límite y al menos dos de falla esperada. Como el entorno y el entrenamiento tienen aleatoriedad, cada caso se repitió 5 veces con las semillas ${U.semillas.join(", ")} y se reportan media y desviación estándar. En M1, la repetición consiste en reentrenar el modelo con otra semilla; en M2–M4, en generar otro flujo de reseñas. Para ser transparentes: una corrida preliminar con la semilla 11 mostró falsos positivos por la negación mal manejada, y eso motivó la corrección del léxico; desde entonces, los parámetros de decisión se calibraron solo con las semillas 101 a 105 (pruebas/calibrar_umbrales.py). El conjunto de control C03 se evaluó una vez durante el desarrollo y no se ajustó nada a partir de él. Los conjuntos que las tablas llaman «manuales» (C02 y C03, 40 reseñas cada uno) se redactaron aparte del corpus de entrenamiento con asistencia de IA; no son reseñas reales. Comando: python pruebas/ejecutar_pruebas.py. El modo --rapido (una sola semilla) escribe en salidas/pruebas_rapido/ y no sustituye estos resultados: con una semilla, la polaridad de C03 puede quedar justo en 85,0 %.`),
  H3("Tabla de resultados"),
  tabla(["Medida", "Fórmula", "Umbral", "Casos ejecutados", "Resultado obtenido", "¿Cumple?", "Evidencia"], filasResultado,
        [1200, 1650, 850, 1450, 1850, 850, 1510], { tam: 14, resaltar: (f) => f[5] === "No" }),
  ESPACIO(),
  H3("Detalle de M1 por caso"),
  tabla(["Caso", "Descripción", "Tipo", "n", "Polaridad", "Tema", "Rechazo", "¿Cumple?"], filasM1,
        [600, 2600, 700, 550, 1400, 1400, 1260, 850], { tam: 14, resaltar: (f) => f[7] === "No" }),
  ESPACIO(),
  H3("Detalle de M2, M3 y M4 por escenario"),
  tabla(["Escenario", "Tipo", "Detección ≤ 24 h", "Alertas tardías", "Reportes a tiempo", "Alertas", "FP (media ± d. e. por corrida)"], filasEsc,
        [2350, 750, 1500, 900, 1400, 800, 1660], { tam: 14 }),
  ESPACIO(),
  P(`Sin los cuatro escenarios de falla esperada, la detección es ${pct(b.tasa_deteccion)} (${b.detectados_24h}/${b.incidentes}) y los falsos positivos ${pct(b.tasa_fp)} (${b.fp}/${b.alertas}).`),
  H3("Análisis de resultados"),
  ...TX.analisis.map((t) => P(t)),
];

// ---------------------------------------------------------------- 9.8, 9.9, 10
const s98 = [H2("9.8 Limitaciones y trabajo futuro"), ...TX.limitaciones.map((t) => B(t))];
const s99 = [
  H2("9.9 Enlaces"),
  B(`Repositorio de código (GitHub): ${ENLACES.repositorio}`),
  B(`Aplicación ejecutable (Streamlit Community Cloud): ${ENLACES.despliegue}`),
  B("Modalidad de evidencia: opción A, plataforma de despliegue público; no aplica video."),
  B("Logs de las pruebas: salidas/pruebas/ en el repositorio (m1_clasificacion.csv, escenarios.csv, resumen.json, corridas/*/log_ejecucion.jsonl)"),
  B("Bitácora de uso de IA: docs/bitacora_uso_ia.docx"),
];
const s10 = [H1("10. Conclusiones"), ...TX.conclusiones.map((t) => P(t))];
const refs = [
  H1("Referencias"),
  ...[
    "IBM. (s. f.). Components of AI agents. IBM Think. https://www.ibm.com/mx-es/think/topics/components-of-ai-agents",
    "Pedregosa, F., Varoquaux, G., Gramfort, A., Michel, V., Thirion, B., Grisel, O., … Duchesnay, É. (2011). Scikit-learn: Machine learning in Python. Journal of Machine Learning Research, 12, 2825–2830.",
    "Russell, S. J., & Norvig, P. (2021). Artificial Intelligence: A Modern Approach (4.ª ed., Global Edition). Pearson.",
    "Streamlit Inc. (2026). Streamlit documentation. https://docs.streamlit.io",
    "Vásquez, J., Gómez-Adorno, H., & Bel-Enguix, G. (2021). BERT-based approach for sentiment analysis of Spanish reviews from TripAdvisor. En Proceedings of the Iberian Languages Evaluation Forum (IberLEF 2021), CEUR Workshop Proceedings, 2943, 165–170. https://ceur-ws.org/Vol-2943/",
    "Wasserman, L. (2004). All of Statistics: A Concise Course in Statistical Inference. Springer. (Pruebas de hipótesis y corrección de Bonferroni, cap. 10).",
  ].map((t) => new Paragraph({ children: [new TextRun(t)], indent: { left: 720, hanging: 720 }, spacing: { after: 120 } })),
];

const VERTICAL = { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } };
const pie = () => new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
  children: [new TextRun({ children: [PageNumber.CURRENT], size: 18 })] })] });
const doc = new Document({
  creator: "Ellen Nicole Ordoñez Chavez y Sara Bastidas Triana",
  title: "ReviewPulse-Agent — Diseño, implementación y pruebas",
  styles: {
    default: { document: { run: { font: D.FUENTE, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: D.FUENTE, color: D.AZUL }, paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: D.FUENTE, color: D.AZUL }, paragraph: { spacing: { before: 220, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 21, bold: true, font: D.FUENTE }, paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 } },
    ],
  },
  numbering: { config: [
    { reference: "vinetas", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
    { reference: "numeros", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] },
  ] },
  sections: [
    { properties: { page: VERTICAL }, footers: { default: pie() },
      children: [...D.portada, ...D.seccionCambios, ...D.seccionMatriz, ...D.diseno, ...s91, ...s92, ...s93, ...s94] },
    { properties: { page: { ...VERTICAL, size: { ...VERTICAL.size, orientation: D.PageOrientation.LANDSCAPE } } },
      footers: { default: pie() }, children: s95 },
    { properties: { page: VERTICAL }, footers: { default: pie() },
      children: [...s96, ...s97, ...s98, ...s99, ...s10, ...refs] },
  ],
});

const salida = path.join(DOCS, "ReviewPulse-Agent_Documento_Ajustado.docx");
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(salida, buf); console.log("Documento:", salida); });
