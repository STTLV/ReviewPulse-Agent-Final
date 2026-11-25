# Tarea 13: recuperación segura y control de reintentos

**Estado:** validación local sin red. **NO constituye autorización para las 120 corridas reales ni un límite monetario de gasto.**

## Cambios limitados al runner experimental

- El runner `experiments/correr.py` instancia el cliente LLM con `max_intentos=1`. En `ClienteOpenAI`, esa configuración deshabilita también los reintentos internos del SDK cuando lo crea. No afecta a la API web de la Tarea 11.
- Antes de cada caso aún no registrado, escribe de forma durable `corridas.csv.pendiente.json`, junto al CSV seleccionado, con el sistema, tarea y repetición. Si hay un corte de luz, excepción o interrupción tras comenzar la solicitud y antes de registrar la fila, el archivo pendiente permanece.
- Al reanudar, **si existe ese marcador, el runner se niega a comenzar nuevas llamadas**. Esto evita que automáticamente repita una solicitud que pudo haber sido facturada, aunque el CSV no tenga su resultado.
- Solo después de escribir y sincronizar la fila CSV con disco se elimina el marcador. Las filas ya completadas se omiten al reanudar.
- Se rechazan CSV con claves duplicadas o identificadores de ejecución incompatibles.

## Si aparece un archivo `.pendiente.json`

**No lo borres ni vuelvas a ejecutar el lote automáticamente.** Conserva una copia del CSV, de las trazas y del marcador, verifica cuál solicitud quedó pendiente, contrasta el registro local con los registros del proveedor cuando estén disponibles y deja asentada la decisión de recuperación. El marcador puede indicar una llamada cobrada sin fila, una llamada fallida o un corte después de escribir la fila. No puede distinguirlos por sí solo.

## Límites de esta protección

- No limita el número de pasos internos que el agente necesita para un solo caso.
- No impide que una solicitud HTTP única consuma muchos tokens.
- No equivale a un límite real de USD en el proveedor ni confirma tarifas o modelo efectivo.
- No demuestra que los fallos de red no se facturen.
- No debe ejecutarse el mismo CSV desde dos procesos concurrentes; el protocolo requiere ejecución secuencial.
- `--limite-ejecuciones` limita casos y **no** consumo.
- Todavía hace falta autorización expresa del gasto, validar IDs efectivos, verificar el límite de la cuenta del proveedor y acordar el protocolo de conciliación antes de `--ejecutar-real`.

## Pruebas sintéticas

`tests/test_resiliencia_t13.py` utiliza únicamente dobles en memoria y rutas temporales. Cubre reanudación de claves completadas, interrupción con marcador, bloqueos, duplicados, un intento sin reintento y modo desactivado sin llamadas. No ejecuta OmniRoute. La suite completa de Windows deberá repetirse después de instalar el paquete.

**Alcance del PR:** esta modificación pertenece a T13. La bitácora histórica OmniRoute, Railway y la interfaz T11 se mantienen separados.
