# T13 · Presupuesto de referencia y control previo (sin llamadas LLM)

**Estado:** preparación académica; NO autoriza ejecución ni sustituye el límite real del proveedor.
**Fecha de consulta de tarifas:** 25 de noviembre de 2026.
**Fuente oficial:** https://developers.openai.com/api/docs/pricing

## Instrucción económica de David

- OmniRoute es un enrutador de código abierto alojado en Railway; su costo depende de la cuenta que sirve los modelos.
- Informar **tokens medidos** como indicador principal del experimento y, separadamente, una **estimación USD de referencia** con las tarifas públicas de OpenAI y fecha de consulta.
- David estimó ~2.500.000 tokens para los dos sistemas (cerca de 2.300.000 en línea base) y ~10.000 del juez en 6 veredictos. Estos valores NO son resultados experimentales.
- El código guarda `tokens_entrada`/`tokens_salida` del modelo principal y `tokens_juez_entrada`/`tokens_juez_salida` del juez.

## Cómo leer las tarifas

El archivo `experiments/precios_referencia_t13.json` usa un **escenario condicional**, no una asignación a OmniRoute:

| Variante ilustrativa | Entrada USD/1M | Salida USD/1M | Fuente |
|---|---:|---:|---|
| `gpt-6-astra` | 10 | 50 | OpenAI API, Standard, contexto corto |
| `gpt-5.6-sol` | 4 | 20 | OpenAI API (versión publicada en español; revisar vigencia/variante) |

**Advertencia:** GPT-6 y GPT-5.6 son nombres generales. No asumir que nuestra cuenta sirve las variantes de la tabla. Tarifas, caché, contexto largo, niveles, impuestos, créditos y proveedor real pueden variar.

**Fórmula:** `(entrada × tarifa_entrada + salida × tarifa_salida) / 1.000.000` para cada modelo, y luego sumar. Nunca sumar tokens del juez bajo el precio del principal.

## Ejecución sin red (solo escenario)

Desde la raíz del repositorio con Python disponible:

```powershell
python experiments/presupuesto_t13.py
python experiments/presupuesto_t13.py --proporcion-salida-ilustrativa 20
```

La primera orden devuelve un intervalo teórico entre todo-entrada y todo-salida (no un límite de facturación). La segunda ilustra 20% de salida, **sin afirmar que el consumo real tenga ese reparto**.

Después de tener un `corridas.csv` real del nuevo esquema, se podrá usar:

```powershell
python experiments/presupuesto_t13.py --corridas experiments/resultados/corridas.csv
```

Este programa **solo lee datos y nunca contacta al proveedor**. Con un CSV parcial indica cuántas filas existen; **incluso 120 filas no prueban por sí solas cobertura correcta**. No valida éxito estadístico ni sustituye `experiments/analizar.py`.

## Cómo comparar con el umbral de US$1

`experiments/umbrales.json` contiene un umbral histórico `costo_usd_max_evaluacion = 1.00`. **No se modifica.** Un escenario con costo mínimo superior a US$1 evidencia que ese umbral no es alcanzable bajo las hipótesis de ese escenario, NO que el equipo esté autorizado a cambiarlo o a gastar más.

## Bloqueo de seguridad antes de la evaluación real

Este paquete **NO agrega un límite técnico de gasto**. Nunca iniciar el runner con `--ejecutar-real` solamente porque el presupuesto orientativo parezca aceptable. Antes deben existir:

1. Confirmación de modelo subyacente (ID exacto, no alias), modalidad y tarifa de referencia aplicable.
2. Autorización de David para la ejecución real y presupuesto específico, separado del umbral histórico.
3. Límite efectivo configurado en la **cuenta del proveedor** con margen para reintentos y concurrencia, o mecanismo transaccional auditable a nivel de llamada. `LLM_TOPE_TOKENS_DIA` no lo es.
4. Prueba con mocks del manejo de fallos, reintentos, y detención sin nuevos gastos; no ejecutar una prueba paga sin autorización.
5. Uso de CSV nuevo con esquema corregido; nunca modificar resultados ya guardados ni Gold/umbrales históricos.
6. Registro posterior de los tokens del juez y del principal, costo estimado por tarifa oficial y, si está disponible, cargo real facturado.

**Estado de T13:** 17 pruebas específicas y 175 de la suite completa aprobadas en Windows (según el registro de ejecución compartido); **120 corridas reales pendientes**.
