# ReviewPulse-Agent 2.0 · Tarea 9

## Alcance

Comparación predefinida entre **agente con herramientas** y **línea base sin herramientas**, con **mismo modelo**, 20 tareas y 3 repeticiones por sistema (120 ejecuciones reales previstas). La Tarea 9 prepara el experimento; la ejecución completa, el análisis de errores y las tablas finales pertenecen a la **Tarea 13** según el plan del proyecto.

## Archivos

- `experiments/preparar.py`: escenario E03 con semilla 11 y tres ejemplos adicionales sintéticos para seguridad.
- `experiments/tareas.yaml`: catálogo versionado de 20 tareas (3 conteos, 3 comparaciones, 3 evidencias, 3 clasificaciones, 3 alertas, 1 reporte y 4 trampas).
- `experiments/verdad.py`: referencia SQL, comprobación automática y bootstrap pareado.
- `experiments/umbrales.json`: valores fijados ANTES de correr con modelos reales.
- `experiments/juez.py`: rúbrica de reporte, modelo juez distinto.
- `experiments/correr.py`: ejecución reanudable, CSV por ejecución, trazas reducidas/redactadas, sin llamadas por defecto.
- `tests/test_evaluacion.py`: pruebas sin red.

## Orden de validación (desde la raíz y sobre una COPIA aislada)

1. `git status --short` (verificar únicamente los archivos de esta tarea).
2. `$env:PYTHONPATH="src"; python -m unittest discover -s tests -p "test_evaluacion.py" -v`
3. `python -m compileall -q experiments src tests`
4. `python experiments/correr.py` (salida: MODO SEGURO, sin consumir tokens).
5. Commit separado de `experiments/umbrales.json` **antes** de ejecutar el modelo real. No alterar umbrales después.
6. Con autorización explícita de David, endpoint y modelos confirmados, variables reales solamente en `.env` privado (NUNCA en Git): `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_JUEZ_MODEL`, `LLM_TOPE_TOKENS_DIA`.
7. Prueba breve con dos tareas y una repetición: `python experiments/correr.py --ejecutar-real --sistema ambos --repeticiones 1 --tareas C01 T01 --limite-ejecuciones 4`. El ID del segundo caso se debe revisar: actualmente **T01** es el caso de semana 40; el total esperado es 4 ejecuciones.
8. Revisar el costo y la traza antes de la evaluación completa. La corrida completa de 120 registros corresponde a Tarea 13.

**Advertencias honestas:** las tres tareas de clasificación usan Gold manual, pero los datos SQL de los otros tipos provienen de las predicciones almacenadas y no deben presentarse como verdad manual. Los verificadores de comparación y alerta usan la verdad declarada de incidentes, y sus reglas lingüísticas admiten ambigüedad. El juez de texto libre puede discrepar: dos de sus seis dictámenes se revisan manualmente en T13. Los parámetros M1–M4 de T8 permanecen intactos. No se han ejecutado 120 peticiones reales ni hay un resultado de superioridad todavía.

**Costos:** `ClienteOpenAI` devuelve conteos de tokens. Para reportar USD se requiere la tarifa vigente del proveedor y los modelos efectivamente configurados, sin inventarla. La línea base incluye todas las reseñas, por lo cual una llamada puede ser mucho más costosa que una consulta del agente.

**Control de secretos:** no se copian `.env`, tokens ni prompt/respuestas completos a los CSV. Las trazas JSONL contienen los eventos filtrados por el agente. Incluso con filtros, conviene inspeccionar los archivos antes de difundirlos públicamente.
