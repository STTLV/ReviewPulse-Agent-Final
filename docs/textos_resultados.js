// Textos de análisis, limitaciones y conclusiones. Las cifras se leen de los resultados.
const fs = require("fs");
const path = require("path");
const RAIZ = path.resolve(__dirname, "..");
const R = JSON.parse(fs.readFileSync(path.join(RAIZ, "salidas/pruebas/resumen.json"), "utf8"));
const T = JSON.parse(fs.readFileSync(path.join(RAIZ, "salidas/pruebas/techo_deteccion.json"), "utf8"));

const pct = (x, d = 1) => (100 * x).toFixed(d).replace(".", ",") + " %";
const a = R.agregado_todos, b = R.agregado_sin_fallas_esperadas, m = R.m1, e = R.escenarios;
const techo1 = T.find((t) => t.conjunto.startsWith("sin") && t.volumen === "x1");
const techo2 = T.find((t) => t.conjunto.startsWith("sin") && t.volumen === "x2");
const det = (k) => `${Math.round(e[k].deteccion_media * 5 * (k === "E03" ? 2 : 1))}/${k === "E03" ? 10 : 5}`;

module.exports = {
  dim: { tipico: [2768, 1550], excepcion: [2768, 1456] },
  enlaces: {
    repositorio: "[pegar enlace de GitHub]",
    despliegue: "[pegar enlace de Streamlit Community Cloud]",
    video: "[pegar enlace de YouTube no listado]",
  },
  analisis: [
    `**Se cumplen M3 y M4.** El agente entregó ${a.reportes_a_tiempo} de ${a.semanas} reportes dentro de 24 horas, incluidas las semanas con plataformas caídas, porque la planificación por metas cambia a «cerrar con datos incompletos» en el último ciclo antes del plazo. Solo ${a.fp} de ${a.alertas} alertas fue un falso positivo (${pct(a.tasa_fp)}), por debajo del 10 %: el gerente puede confiar en lo que recibe. El único falso positivo ocurrió en temporada alta (E04).`,
    `**No se cumple M1.** En el conjunto de control, que no se usó para ajustar nada, la polaridad llega a ${pct(m.C03.polaridad_media)} ± ${pct(m.C03.polaridad_de)} y el tema a ${pct(m.C03.tema_media)}; el tema cumple, la polaridad no. En frases sintéticas no vistas (C01) el modelo sí pasa el umbral (${pct(m.C01.polaridad_media)}), lo que muestra la causa: se entrenó con un corpus sintético de vocabulario limitado y generaliza mal a expresiones reales como «tardaron muchísimo» o «cobran todo aparte». Las reseñas de una sola frase (C08, ${pct(m.C08.polaridad_media)}) y con errores de tipeo (C05, ${pct(m.C05.polaridad_media)}) son los casos más débiles, y de los ocho errores del modelo base en ese conjunto, seis involucran la clase neutra y cinco son reseñas negativas que el modelo no reconoce como tales, lo que también le resta detección a M2. El 100 % de C06 (ironía) no es informativo: esas frases están en el corpus de entrenamiento. C04 tampoco es una prueba independiente: el preprocesamiento (normalizar) ya pasa todo a minúsculas y quita las tildes antes del modelo, por eso da exactamente lo mismo que C03. Además, con 40 reseñas cada una pesa 2,5 puntos y el margen de error de un 81 % es de unos ±12 puntos, así que este conjunto es demasiado pequeño para decidir con seguridad frente a un umbral de 85 %; el veredicto «No» se apoya en el promedio de cinco reentrenamientos y en que C05, C07 y C08 también quedan por debajo. **Corrección:** reemplazar el modelo por uno preentrenado para español (la clase ClasificadorBERT ya deja el punto de cambio) y entrenarlo con reseñas reales etiquetadas, como el corpus de TripAdvisor de IberLEF 2021.`,
    `**No se cumple M2: ${pct(a.tasa_deteccion)} (${a.detectados_24h}/${a.incidentes}) frente a 90 %.** Diez de los ${a.incidentes - a.detectados_24h} incidentes perdidos son fallas esperadas por diseño: en E11 no hay datos al cierre (las ${e.E11.detectados_tarde_total} alertas llegan tarde, después de 24 h) y en E12 no hay historial con qué comparar. Sin los escenarios de falla, la detección es ${pct(b.tasa_deteccion)}. En E07 (12 reseñas por semana) no detecta nada porque el mínimo de 6 negativas es inalcanzable con unas 5 reseñas por tema; en E02, E03 y E05 falla cuando el incidente real produce pocas reseñas negativas en la semana (en una semilla de E02, solo 11 de las 23 reseñas de limpieza de esa semana se clasificaron como negativas).`,
    `Para separar causas se aplicó la misma regla a las etiquetas reales del simulador (pruebas/techo_deteccion.py). Con un clasificador perfecto, la detección en los escenarios normales y límite sería ${pct(techo1.deteccion)}, no 90 %; con el doble de volumen semanal subiría a ${pct(techo2.deteccion)}. Es decir, el clasificador explica unos ${Math.round(100 * (techo1.deteccion - b.tasa_deteccion))} puntos de la diferencia y el resto es potencia estadística: con unas 9 reseñas por tema a la semana, una ventana semanal no alcanza para distinguir un incidente de la variación normal sin disparar falsos positivos. **Corrección:** (1) usar una prueba secuencial acumulada (por ejemplo, CUSUM diario) en lugar de cortes semanales, para acumular evidencia en varios días; (2) fusionar la calificación numérica con el texto, que reduce el ruido del clasificador; (3) escalar el mínimo de negativas con el volumen del tema; y (4) reformular M2 para hoteles de bajo volumen como detección dentro de 48 h o con ventanas de 14 días.`,
  ],
  limitaciones: [
    "Los conjuntos de evaluación manuales (C02 y C03) y el corpus de entrenamiento se redactaron con asistencia de IA; ninguno contiene reseñas reales. La exactitud medida es una estimación optimista de lo que pasaría con lenguaje real, y el siguiente paso es evaluar con reseñas reales etiquetadas por personas.",
    "El entorno es simulado. El agente no se ha probado con reseñas reales de TripAdvisor o Google; el simulador reproduce las propiedades del ambiente, pero su lenguaje es más limitado que el real.",
    "El modelo de sentimiento se entrenó con un corpus sintético. Su exactitud en lenguaje natural (conjunto de control) queda por debajo de la meta; es la primera mejora: un modelo preentrenado para español y datos reales etiquetados.",
    "La detección semanal pierde incidentes en hoteles de bajo volumen. Trabajo futuro: prueba secuencial diaria y umbrales que se ajusten al volumen.",
    "La calificación numérica se recoge, pero no se usa para decidir. Trabajo futuro: combinarla con la probabilidad del texto.",
    "No hay aprendizaje en línea. Trabajo futuro: usar las reseñas que el gerente corrija en la revisión manual para reentrenar el modelo cada mes, con validación antes de reemplazarlo.",
    "Las alertas se escriben en una bandeja de salida; el envío por correo SMTP está implementado pero no se probó con un servidor real.",
    "El agente atiende un solo hotel. Para varios hoteles habría que separar el historial por hotel y revisar la corrección por comparaciones múltiples.",
  ],
  conclusiones: [
    `ReviewPulse-Agent se construyó como un agente basado en modelos y orientado a metas, coherente con el diseño: mantiene un estado interno en dos plazos, planifica sus acciones con búsqueda en anchura sobre hechos y metas, y su ciclo percepción → decisión → acción se puede seguir en el código y en el log de cada ejecución. El agente funciona de punta a punta en los doce escenarios, incluidos los de falla, sin detenerse por entradas inválidas o plataformas caídas.`,
    `De las cuatro medidas de desempeño, se cumplen dos: el reporte semanal llega a tiempo en el 100 % de las semanas y los falsos positivos quedan en ${pct(a.tasa_fp)}. No se cumplen la exactitud de polaridad en lenguaje real (${pct(m.C03.polaridad_media)} frente a 85 %) ni la detección de incidentes en 24 horas (${pct(a.tasa_deteccion)} frente a 90 %). El análisis muestra que la detección está limitada sobre todo por el volumen de reseñas por semana: ni siquiera un clasificador perfecto llegaría al 90 % con la ventana semanal. Ese es el hallazgo más útil de las pruebas, porque indica que la siguiente versión debe cambiar la forma de acumular evidencia, no solo el modelo.`,
    "En lo ético se mantiene lo planteado en el diseño: las reseñas son públicas, pero las escribieron personas reales, y el modelo puede tener sesgos hacia ciertos estilos de escritura. Por eso el agente marca para revisión humana las clasificaciones de baja confianza, explica cada alerta con cifras y ejemplos, y deja la decisión final en manos del gerente.",
  ],
};
