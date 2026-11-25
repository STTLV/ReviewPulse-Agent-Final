# T13: comprobación previa sin conexión

**Estado: preparación, NO autorización para realizar llamadas reales.**

El programa `experiments/preflight_t13.py` es un comprobador de solo lectura. Valida:

- 20 tareas y su distribución original, sin modificar `tareas.yaml`.
- 3 repeticiones de agente y línea base: 120 combinaciones únicas, 60 por sistema.
- 6 dictámenes previstos del juez (la tarea tipo reporte, repetida tres veces para cada sistema).
- Coherencia del diseño con `experiments/umbrales.json`. No modifica los umbrales.
- Si se pasa `--csv`, su esquema actual, la ausencia de claves duplicadas y la cobertura del plan. No da por válidas las 120 corridas solo por contar 120 filas; el análisis principal debe validar sus métricas y estados.

Para reducir el riesgo de llamadas accidentales, el programa **no importa ni ejecuta** `experiments/correr.py`. Lee el esquema del CSV desde el código fuente con AST, sin ejecutar ninguna instrucción del runner. Tampoco importa el cliente LLM, no acepta credenciales y no tiene ninguna opción para habilitar la evaluación real.

## Comandos (sin red)

Desde la raíz del proyecto:

```powershell
python experiments/preflight_t13.py
python -m unittest discover -s tests -p "test_preflight_t13.py" -v
```

Si posteriormente existe un CSV parcial (sin modificarlo):

```powershell
python experiments/preflight_t13.py --csv experiments/resultados/corridas.csv
```

No se debe usar el segundo comando si el archivo todavía no existe.

## Diferencia entre presupuesto de referencia y control real

- `LLM_TOPE_TOKENS_DIA = 0` evita llamadas en la implementación actual, pero un número positivo **no controla un gasto máximo**.
- `--limite-ejecuciones` del runner controla **número de casos, no número de solicitudes HTTP ni tokens**. Un caso del agente puede generar varias llamadas y el cliente puede reintentar fallos.
- La instrumentación guarda consumo del agente y del juez por separado cuando obtiene respuestas, pero ciertos fallos remotos podrían haberse facturado sin regresar un conteo de tokens.
- El archivo de tarifas de referencia **solo estima costos**. La tarifa real depende del proveedor y los alias efectivos de OmniRoute.
- El umbral histórico `costo_usd_max_evaluacion=1.00` debe conservarse, pero **no equivale a una autorización** ni a un techo implementado.

Antes de ejecutar el modo real se necesita confirmación de los modelos efectivos, **autorización específica de presupuesto**, **límite efectivo a nivel de la cuenta del proveedor** y pruebas con mocks de detención y reintentos. Si no existe un límite efectivo verificable, el proyecto debe documentarlo y consultar alternativas con David en lugar de asumir que el programa puede garantizarlo.

Para el informe debe primar el consumo medido de tokens, con una estimación separada en USD de referencia (fuente y fecha), tal como explicó David. **No usar el cálculo ilustrativo como factura ni afirmar que las 120 corridas ya se ejecutaron.**
