# Tarea 11: chat y traza del agente

## Alcance acordado con David (24-11-2026)

- Interfaz web responsive de una sola página, en paleta azul aguamarina.
- Chat funcional sobre `POST /api/chat` con cabecera `X-Codigo-Acceso`.
- Traza paso a paso en vivo consumiendo SSE `paso`, `final` y `error`.
- Indicador de API, cancelación del cliente, accesibilidad elemental.
- Corrección del modo demo: si la consulta no coincide con ninguna grabación, mostrar **solo un aviso** y no emitir respuesta ni traza de otra consulta. Si coincide, reproducir íntegramente los eventos y la respuesta final original, sin reescribirlos.
- Renombrar los 3 JSON de conversación con nombres congruentes con las preguntas, ajustar el capturador, conservar su contenido.

## Implementación

- `src/reviewpulse/web/index.html`, `styles.css`, `app.js`: web estática, sin CDN, sin framework adicional.
- `src/reviewpulse/api/main.py`: sirve `/` y `/assets/*` junto a la API actual. Mantiene `crear_app` y `crear_app_desde_entorno`.
- `src/reviewpulse/api/estado.py`: selector de conversación identifica coincidencias mediante `coincidencia_demo`; se conserva la selección de respaldo por compatibilidad, pero no se reproduce cuando la pregunta no coincide.
- `src/reviewpulse/api/rutas.py`: si hay coincidencia, emite `reproduccion_demo`, los pasos originales y la respuesta final. Si no la hay, emite solo un `final` informativo, sin eventos `paso` ni cifras de otra pregunta.
- `data/trazas_demo/`: las tres conversaciones fueron **renombradas sin modificar los bytes de sus contenidos**. `scripts/capturar_trazas_demo.py` escribe a los nuevos nombres en futuras capturas.

## Ejecución local sin consumo del modelo

Usar desde la raíz del proyecto y con `.venv` instalado:

```powershell
$env:PYTHONPATH = "src"
$env:LLM_TOPE_TOKENS_DIA = "0"
$env:APP_CODIGO_ACCESO = "t11-prueba-local-2026"
.\.venv\Scripts\python.exe -m uvicorn reviewpulse.api.main:crear_app_desde_entorno --factory --host 127.0.0.1 --port 8000
```

Abrir `http://127.0.0.1:8000/`. El código de prueba es `t11-prueba-local-2026`, **solo para la demostración local**. No utilizar este código en Railway ni compartir credenciales reales. Con `LLM_TOPE_TOKENS_DIA=0`, el backend fuerza el modo demo y no llama al proveedor.

## Matriz de aceptación manual

| Prueba | Resultado esperado |
|---|---|
| Cargar `/` | HTML con chat, campo de código y panel de traza |
| Consulta de semana 8 | Aparecen eventos SSE y la respuesta guardada de 40 reseñas |
| Consulta de servicio semana 8 | Traza muestra `comparar_semana` y la respuesta de CUSUM |
| Consulta de semana 40 | Traza muestra `sin_datos`, sin inventar reseñas |
| Escribir `hola` | Solo se muestra `Modo demostración: no hay una conversación grabada para «hola»...` y se sugieren preguntas; no aparece el conteo de la semana 8 ni su traza |
| Omitir código o usar código inválido | Validación del formulario o HTTP 401, sin exponer secreto |
| Enviar una segunda consulta cuando agente ocupado | Mensaje controlado HTTP 429 |
| Cancelar una respuesta en vivo | `AbortController` cancela la lectura; API administra liberación del candado |
| Pantalla estrecha | Chat y traza apilados, controles utilizables |

## Pruebas automáticas

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_tarea11.py -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -q
```

Las pruebas de T11 usan una API sintética en memoria. No hacen llamadas reales al proveedor. La suite de todo el proyecto debe ejecutarse también antes del PR. No modificar evaluaciones T8/T9 ni resultados de Hito 2.

## Seguridad y límites

- No se guarda el código de acceso en `localStorage`, URL, cookies ni archivos. El código se envía solo en `X-Codigo-Acceso`.
- La salida del agente se muestra usando `textContent`, no `innerHTML`; los eventos de herramientas se muestran como JSON escapado, sin razonamiento privado.
- La UI utiliza `fetch` de mismo origen con política CSP restrictiva. Si Railway tiene proxy con buffering SSE, Ellen deberá revisar esa configuración en T12.
- Esta tarea **no añade pruebas reales OmniRoute** ni modifica su bitácora. La evidencia histórica de `sara/mover-src` corresponde a un PR documental aparte.
- No se realizan commits, push ni merge durante la preparación de esta entrega.
