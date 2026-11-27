# ReviewPulse-Agent 2.0

Proyecto de Inteligencia Artificial de la Universidad Tecnológica de Bolívar. ReviewPulse procesa reseñas **sintéticas** de un hotel piloto, las clasifica por tema y polaridad, calcula alertas CUSUM y genera resúmenes semanales. La versión V2 integra un agente LLM ReAct con herramientas, una API FastAPI, una interfaz web y evaluación experimental contra una línea base sin herramientas.

**Integrantes:** Ellen Nicole Ordoñez Chavez y Sara Bastidas Triana.

- **Repositorio:** https://github.com/STTLV/ReviewPulse-Agent-Final
- **Plan de implementación:** `docs/superpowers/plans/2026-11-17-reviewpulse-agente-2.md`
- **Diseño:** `docs/superpowers/specs/2026-11-17-reviewpulse-agente-llm-design.md`
- **Bitácora de IA:** `docs/bitacora_ia.md`

## Estado de la arquitectura

La **Tarea 3** separó el ciclo determinista del razonamiento del agente ReAct:

- `src/reviewpulse/ciclo/ingesta.py`: consulta plataformas cada seis horas simuladas, valida, clasifica y persiste reseñas en SQLite; gestiona retrasos y alertas CUSUM
- `src/reviewpulse/ciclo/cierre.py`: cierra semanas cuando corresponde, registra eventos JSONL y garantiza el reporte aun si el manejador falla
- `src/reviewpulse/herramientas/analisis.py`: compara temas, registra alertas y prepara reportes a partir de SQLite
- `src/reviewpulse/herramientas/estadistica.py`: cálculo matemático de CUSUM diario (Tarea 2)
- `src/reviewpulse/entorno.py`, `escenarios.py`, `evaluacion.py`: simulador y evaluación, sin acceso del agente a las etiquetas reales
- `src/reviewpulse/modelo.py`: clasificador TF-IDF + léxico + regresión logística; el archivo entrenado está en `data/modelo.joblib`

El código anterior de `agente.py`, `planificador.py` y `ejecutar_agente.py` se retira en esta refactorización. El bucle ReAct con LLM, la API FastAPI y la interfaz web T11 se encuentran integrados en la rama `v2`. Los resultados históricos M1–M4 no se reescriben.

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
- La interfaz web T11 y el juez de R01 ya forman parte de V2; la evaluacion experimental T13 y sus limitaciones se documentan por separado

## Datos de demostración de la API

La API inicializa su base demo a partir de una corrida del simulador `E03`, semilla `11`, mediante `ejecutar_simulacion` y el clasificador guardado en `data/modelo.joblib`. La corrida se genera al inicializar una base ausente; son datos sintéticos, no reseñas reales. En la prueba local del contenedor, `docker restart` conservó SQLite (489 reseñas antes y después). Al retirar ese contenedor y crear otro sin volumen, la base se inicializó de nuevo con 489 reseñas.

Las tres trazas de `data/trazas_demo/` son conversaciones reales del agente: guardan la pregunta, las herramientas, resultados cuantitativos filtrados y la respuesta final. Al agotarse el presupuesto, el modo demo reproduce por SSE la conversación coincidente. La solicitud de chat reserva el candado al empezar la respuesta y devuelve `429` si el agente está ocupado.

## Preparación local y contenedor (Tarea 12)

La CI y la imagen usan Python 3.13. Arranque local con proveedor, desde la raíz y en cinco comandos:

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export PYTHONPATH=src
uvicorn --factory reviewpulse.api.main:crear_app_desde_entorno --host 127.0.0.1 --port "${PORT:-8000}" --workers 1
```

El operador configura `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_JUEZ_MODEL`, `APP_CODIGO_ACCESO` y `LLM_TOPE_TOKENS_DIA` en el entorno o en el gestor de secretos. `API_CHAT_TIMEOUT_S` es opcional y su valor por defecto es 120 segundos. No se guardan valores de estas variables en el repositorio.

Para ejecutar el modo demo sin proveedor y sin llamadas LLM, usa un código de acceso desechable solo en tu terminal:

```sh
read -s APP_CODIGO_ACCESO
export APP_CODIGO_ACCESO
LLM_TOPE_TOKENS_DIA=0 LLM_BASE_URL= LLM_API_KEY= LLM_MODEL= LLM_JUEZ_MODEL= PYTHONPATH=src uvicorn --factory reviewpulse.api.main:crear_app_desde_entorno --host 127.0.0.1 --port "${PORT:-8000}" --workers 1
```

La API reproduce las trazas incluidas y no inicia llamadas al proveedor con el tope de tokens en cero.

Construcción y prueba local del contenedor:

```sh
docker build -t reviewpulse-agent .
docker run --rm -p "${PORT:-8000}:${PORT:-8000}" -e PORT="${PORT:-8000}" -e LLM_TOPE_TOKENS_DIA=0 -e APP_CODIGO_ACCESO="$APP_CODIGO_ACCESO" reviewpulse-agent
```

El Dockerfile incluye `config/config.json`, `data/modelo.joblib` y los JSON de `data/trazas_demo/`; excluye `.env`, los CSV de evaluación y resultados locales. La API carga la configuración CUSUM al importar `src/reviewpulse/ciclo/ingesta.py`. La interfaz de T11 ya está integrada en `v2`: FastAPI sirve `src/reviewpulse/web/index.html` en `/` y los archivos estáticos bajo `/assets`. `COPY src ./src` incluye esos archivos en la imagen.

`railway.toml` selecciona el builder Dockerfile y configura `/api/salud` como health check con timeout de 120 segundos. La prueba local de contenedor documentada anteriormente corresponde a una revisión previa: su resultado 404 en `/` ya no describe `v2`, donde la ruta sirve la interfaz T11. En esta revisión no se pudo repetir el build ni las comprobaciones HTTP/SSE/persistencia porque el entorno no permitió acceder al socket del daemon Docker; por tanto, no se certifican aquí para el commit actual.

La API debe operar con **un worker y una réplica**, porque el candado es local al proceso. **En la revisión local de T12 del 25/11** todavía no se había confirmado Railway; esta frase describe ese hito histórico y no el estado actual. El despliegue público se validó posteriormente el 26/11, según el apartado siguiente. Sin un volumen persistente, un contenedor nuevo puede regenerar la base demo; la permanencia de datos después de recrear la instancia **sigue sin verificarse**.

## Aclaraciones experimentales posteriores a T13 (26/11/2026)

La evidencia de 120 corridas sigue INTACTA. Las correcciones de análisis, la revisión documental de diez fallos y el costo de referencia constan en `docs/T13_CORRECCIONES_Y_LIMITACIONES.md`. Los subgrupos de errores tipográficos, longitud y tema calculados sobre el Gold con el clasificador guardado se encuentran en `experiments/resultados/gold_subgrupos_responsable/`; NO son subgrupos de éxito ReAct/base. La auditoría documental T13 precedió a las pruebas públicas de Railway; ver el estado posterior indicado abajo.


## Despliegue público y verificación funcional (26/11/2026)

**Prototipo V2 (Railway):** https://reviewpulse-agent-production.up.railway.app/

La comprobación pública de Sara se realizó desde PowerShell el **26/11/2026**, con el registro `ReviewPulse_Railway_Pruebas_20261126_220942.txt` conservado como evidencia de entrega. Los endpoints `/`, `/assets/styles.css`, `/assets/app.js`, `/api/salud`, `/api/semanas`, `/api/resultados` y `/api/demo` devolvieron HTTP 200. Una solicitud al chat sin código de acceso recibió HTTP 401, como se esperaba.

Se enviaron tres consultas autorizadas al chat y se registraron `modo_demo=False`, seis pasos y una herramienta invocada en cada una:

| Consulta de prueba | Respuesta registrada |
|---|---|
| ¿Cuántas reseñas hubo en la semana 8? | 40 reseñas |
| ¿El servicio empeoró en la semana 8? | Alarma CUSUM; 19 reseñas de servicio y 15 negativas (78,9 %) |
| ¿Cuántas reseñas hubo en la semana 40? | No hay datos disponibles para esa semana |

Este resultado prueba una **verificación funcional básica del despliegue**, no una auditoría integral de exactitud semántica, seguridad, disponibilidad del proveedor, facturación o persistencia entre despliegues. Las cifras son respuestas del agente en esas tres consultas; no se verificaron de forma independiente contra toda la base de producción. No se ejecutaron los endpoints de reinicio o cierre durante las comprobaciones.

**Acceso del docente:** el chat requiere un código de acceso, que debe entregarse por un canal privado autorizado, nunca en GitHub, el video, capturas ni un PDF público. Se recomienda verificar el enlace en una ventana privada y comprobar previamente que el docente tenga los permisos necesarios.

**Persistencia:** queda por confirmar con la configuración efectiva de Railway si `REVIEWPULSE_DB_PATH` apunta a un volumen persistente y si la base se conserva al recrear o redesplegar el servicio. El `docker restart` local de T12 no comprueba esa propiedad en producción.

**Reproducibilidad:** las pruebas del proyecto se ejecutan con las versiones fijadas en `requirements.txt`. No se afirma que estas comprobaciones HTTP sustituyan la batería automática ni los 120 registros experimentales de T13.
