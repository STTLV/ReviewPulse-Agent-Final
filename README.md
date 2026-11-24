# ReviewPulse-Agent 2.0

Proyecto de Inteligencia Artificial de la Universidad Tecnológica de Bolívar. ReviewPulse procesa reseñas **sintéticas** de un hotel piloto, las clasifica por tema y polaridad, calcula alertas CUSUM y genera resúmenes semanales. El nuevo agente con LLM se integra por tareas y por PR separados.

**Integrantes:** Ellen Nicole Ordoñez Chavez y Sara Bastidas Triana.

- **Repositorio:** https://github.com/STTLV/ReviewPulse-Agent-Final
- **Plan de implementación:** `docs/superpowers/plans/2026-11-17-reviewpulse-agente-2.md`
- **Diseño:** `docs/superpowers/specs/2026-11-17-reviewpulse-agente-llm-design.md`
- **Bitácora de IA:** `docs/bitacora_ia.md`

## Estado de la arquitectura

La **Tarea 3** separa el ciclo determinista del razonamiento del futuro agente:

- `src/reviewpulse/ciclo/ingesta.py`: consulta plataformas cada seis horas simuladas, valida, clasifica y persiste reseñas en SQLite; gestiona retrasos y alertas CUSUM
- `src/reviewpulse/ciclo/cierre.py`: cierra semanas cuando corresponde, registra eventos JSONL y garantiza el reporte aun si el manejador falla
- `src/reviewpulse/herramientas/analisis.py`: compara temas, registra alertas y prepara reportes a partir de SQLite
- `src/reviewpulse/herramientas/estadistica.py`: cálculo matemático de CUSUM diario (Tarea 2)
- `src/reviewpulse/entorno.py`, `escenarios.py`, `evaluacion.py`: simulador y evaluación, sin acceso del agente a las etiquetas reales
- `src/reviewpulse/modelo.py`: clasificador TF-IDF + léxico + regresión logística; el archivo entrenado está en `data/modelo.joblib`

El código anterior de `agente.py`, `planificador.py` y `ejecutar_agente.py` se retira en esta refactorización. El bucle ReAct con LLM y la API FastAPI se integraron en tareas posteriores; la interfaz web se mantiene como una tarea separada. Los resultados históricos M1–M4 no se reescriben.

## Instalación y pruebas

Se utiliza **Python 3.13** y las versiones fijadas en `requirements.txt`.

En PowerShell, desde la carpeta raíz:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

En macOS o Linux, exportar `PYTHONPATH=src`, activar el entorno y ejecutar `python -m unittest discover -s tests -v`.

### Paridad de la Tarea 3

Las pruebas `tests/test_paridad.py` ejecutan el ciclo nuevo en directorios temporales, con el modelo guardado y semilla 11. También se comprueba el cierre de conexiones y los reportes de respaldo en `tests/test_ciclo.py`.

| Escenario | Reseñas clasificadas | Descartadas | Reportes a tiempo | Reportes incompletos |
|---|---:|---:|---:|---:|
| E02 | 486 | 21 | 14 | 0 |
| E11 | 487 | 20 | 14 | 2 |

Para ejecutar manualmente una simulación E02 sin el ejecutable anterior:

```powershell
$env:PYTHONPATH = "src"
@'
from pathlib import Path
from reviewpulse.ciclo.cierre import ejecutar_simulacion
from reviewpulse.entorno import EntornoHotel
from reviewpulse.escenarios import ESCENARIOS
from reviewpulse.evaluacion import evaluar_corrida
entorno = EntornoHotel(ESCENARIOS["E02"], 11)
resultado = ejecutar_simulacion(entorno, Path("salidas/demo_tarea3"))
print(evaluar_corrida(entorno, resultado))
'@ | .\.venv\Scripts\python.exe -
```

Los registros se escriben en `salidas/demo_tarea3/` e incluyen `memoria.db`, `log_ejecucion.jsonl`, `reportes/` y, si hay alertas, `bandeja_salida.jsonl`. **La bandeja local simula el aviso; no acredita envío real de correo.**

## Evidencias del Hito 2 conservadas

El historial del prototipo anterior y sus métricas permanecen en `experiments/v1/` y en Git. Los umbrales históricos se copian **sin modificaciones** a `experiments/v1/umbrales_hito2.json` antes de retirar los scripts antiguos. La comparación de línea base se mantiene en `experiments/linea_base_hito2.py`.

Resultados históricos de la comparación sobre 40 reseñas de control:

| Objetivo | Línea base mayoritaria | ReviewPulse guardado |
|---|---:|---:|
| Polaridad | 16/40 (40 %) | 32/40 (80 %) |
| Tema | 10/40 (25 %) | 34/40 (85 %) |

Estos valores no sustituyen la evaluación histórica M1–M4. Los archivos y evidencias originales del Hito 2 están disponibles en la [carpeta compartida histórica](https://drive.google.com/drive/folders/1CnpElJThx8Cf-WtnUxzvz43CeNVsFXdq?usp=drive_link). La [aplicación anterior en Streamlit](https://reviewpulse-agent-sttlv.streamlit.app/) corresponde al prototipo histórico y no forma parte de la arquitectura 2.0.

## Seguridad y límites

- No subir `.env`, claves de API ni registros con secretos
- No utilizar datos de reseñas sintéticas para presentar un despliegue real
- Los umbrales CUSUM y M1–M4 históricos no se alteran durante esta tarea
- La interfaz web y la evaluación con juez se revisan en tareas y PR separados

## Datos de demostración de la API

La API inicializa su base demo a partir de una corrida del simulador `E03`, semilla `11`, mediante `ejecutar_simulacion` y el clasificador guardado en `data/modelo.joblib`. La corrida se genera en una carpeta temporal; la API utiliza su SQLite y sus reportes. Son datos sintéticos producidos por el simulador, no reseñas reales de clientes. El reinicio vuelve a generar esta base; no hay un repositorio histórico paralelo en la API.

Las tres trazas de `data/trazas_demo/` son conversaciones reales del agente: guardan la pregunta, las herramientas y los resultados cuantitativos filtrados, y la respuesta final. Al agotarse el presupuesto, el modo demo reproduce la conversación que coincide con la pregunta por SSE. Se pueden volver a grabar con `PYTHONPATH=src python scripts/capturar_trazas_demo.py`; el capturador requiere `.env`, permite hasta dos solicitudes al proveedor por conversación y desactiva los reintentos. Reemplaza las tres trazas solo cuando todas se capturan correctamente. La solicitud de chat reserva el candado cuando comienza a ejecutarse la respuesta; si ya está ocupado, conserva la respuesta `429` sin dejar bloqueado un flujo SSE que no se inició.
