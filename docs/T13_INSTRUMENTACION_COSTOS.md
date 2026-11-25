# T13: Instrumentación de consumo y análisis (sin LLM)

## Alcance
Este ajuste conserva el catálogo fijo de 20 tareas, el experimento de 3 repeticiones
por sistema, los umbrales ya versionados y los verificadores T9. No toca datos de
reseñas, Gold, CUSUM, los archivos de T11 ni el PR #28.

1. `experiments/correr.py`: conserva `tokens_entrada` y `tokens_salida` **exclusivamente
   para el modelo principal**. Añade `tokens_juez_entrada`, `tokens_juez_salida`,
   `tokens_total_entrada` y `tokens_total_salida`, y registra los identificadores
   `modelo_principal` y `modelo_juez`. Detecta CSV con cabecera antigua
   antes de agregar filas para evitar mezclar esquemas o atribuir tokens al modelo equivocado.
2. `experiments/juez.py`: preserva los tokens reportados incluso si el JSON del juez
   es inválido o el veredicto queda pendiente. Si el proveedor no reporta consumo
   ante un error de red, no es posible inferirlo; ver la consola/facturación.
3. `experiments/analizar.py`: valida aritméticamente las nuevas columnas, informa
   consumo principal y juez por separado, y calcula la trazabilidad del agente
   como suma de cifras respaldadas / suma de cifras evaluadas únicamente cuando
   **todas las filas del agente tienen datos finales** y hay un denominador positivo.
   Se dejan indeterminadas la exactitud numérica global y el costo USD facturado:
   el CSV no demuestra esas métricas.
4. `tests/test_analisis.py`: agrega pruebas sintéticas sin red sobre el uso del juez,
   el esquema CSV, la trazabilidad agregada y los casos indeterminados.

## Precauciones antes de las 120 corridas
- **No ejecutar `experiments/correr.py --ejecutar-real`** sin presupuesto autorizado
  por David y un límite efectivo del proveedor. `LLM_TOPE_TOKENS_DIA` en el cliente
  actual solo actúa como habilitación (valor > 0); NO impone techo de gasto real
  durante el lote. Los reintentos y llamadas internas tampoco equivalen a
  `--limite-ejecuciones`.
- El nuevo formato CSV no es compatible con anexar filas a uno antiguo.
  Conservar cualquier CSV anterior intacto y seleccionar una ruta nueva para
  la evaluación oficial. Evitar mezclar corridas previas con corridas nuevas.
- Antes de ejecutar, verificar con David proveedor, nombres reales de modelos,
  tarifas oficiales o efectivas, cuenta con límites, fechas y autorización.
- El bootstrap es pareado por tarea (20 unidades de remuestreo); no representa
  120 observaciones independientes.
- La columna `cifras_no_respaldadas` sólo observa conteos en su línea final;
  NO es la tasa global de cifras incorrectas de todos los tipos de tarea.
- Trazabilidad frente a observaciones de herramientas no equivale a
  exactitud factual ni a facturación.
- Revisar los 2 dictámenes humanos de reporte con evidencias originales
  protegidas y no aceptar resultados del juez pendientes como éxitos.
- Los subgrupos plataforma, longitud, tema y tipeo siguen SIN metadata
  por ejecución; no deben inventarse resultados.
- Hasta que exista `corridas.csv` con 120 ejecuciones reales válidas, no
  publicar métricas experimentales como observadas.

## Validación
En la reconstrucción local, `python -m unittest discover -s tests -p test_analisis.py -v`
completó 17/17. La prueba de regresión total debe repetirse en el repositorio
completo de Windows, antes de commit o push.
