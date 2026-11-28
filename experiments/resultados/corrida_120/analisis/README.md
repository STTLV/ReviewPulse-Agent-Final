# Análisis de la evaluación T13: evidencias y estados

Esta carpeta contiene archivos derivados de la evaluación de **120 ejecuciones** (60 ReAct y 60 línea base). No son nuevas corridas y no se han rehecho los experimentos para preparar el Hito 3.

| Archivo | Función y estado |
|---|---|
| `resumen.json` | Resumen derivado de las 120 ejecuciones originales. |
| `subgrupos.csv` | Desagregación de resultados por categoría/tarea según los campos disponibles; no reemplaza el análisis Gold independiente. |
| `errores.csv` | Listado experimental de ejecuciones fallidas, sin respuestas originales completas. |
| **`revision_documental_10.csv`** | **Análisis documental definitivo de diez casos**, separando evidencia, hipótesis y límites de verificación. |
| `revision_humana_10_borrador.csv` | **Borrador histórico preliminar**, no informe final. La columna `revision_humana=pendiente` reflejaba el estado inicial de la planificación, no una revisión completada ni una tarea realizable con los archivos preservados. |
| `consumo_documentado.json` | Consumo de tokens registrado y notas de procedencia; **no es una factura**. |

## Precauciones de interpretación

1. No utilizar `revision_humana_10_borrador.csv` para afirmar que faltaría solo completar una comparación humana pendiente. **La evaluación retrospectiva de las respuestas originales es no evaluable**, porque el runner no conservó esos textos completos. Véase `revision_documental_10.csv` y `docs/T13_CORRECCIONES_Y_LIMITACIONES.md`.
2. En `consumo_documentado.json`, el texto libre del campo `autorizacion` constituye una **nota histórica de procedencia**, no evidencia técnica o contable independiente de quién ejecutó la corrida, quién pagó, o quién desplegó la aplicación. La atribución pública de contribuciones se aclara en `docs/bitacora_ia.md` (27/11/2026). Los tokens medidos permanecen inalterados.
3. Los modelos con tarifas de referencia no son necesariamente idénticos a los alias del proveedor usado durante la ejecución. Los **US$25,58440** corresponden a un escenario tarifario ilustrativo, no a un importe facturado verificado.
4. No se modificaron `corridas.csv`, los 120 JSONL, datos Gold, umbrales, resultados ni los archivos originales de este directorio.
