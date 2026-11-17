# ReviewPulse-Agent

Agente inteligente **basado en modelos y orientado a metas** (Russell y Norvig) que clasifica las reseñas de un hotel piloto por polaridad (positiva, negativa, neutra) y tema (limpieza, servicio, ubicación, precio), compara cada semana contra su historial y alerta al gerente cuando el tono negativo de un tema se sale de lo normal.

Proyecto del curso Inteligencia Artificial, Universidad Tecnológica de Bolívar (Tarea 3: implementación y pruebas). Este repositorio conserva el trabajo de Ellen y documenta el avance del Hito 2 del proyecto final.

**Integrantes:** Ellen Nicole Ordoñez Chavez y Sara Bastidas Triana.
**Repositorio de entrega:** https://github.com/STTLV/ReviewPulse-Agent-Final
**Aplicación web:** https://reviewpulse-agent-sttlv.streamlit.app/
**Evidencias históricas completas:** https://drive.google.com/drive/folders/1CnpElJThx8Cf-WtnUxzvz43CeNVsFXdq?usp=drive_link
**PDF Hito 2:** [`reviewpulse_agent_hito2.pdf`](reviewpulse_agent_hito2.pdf)
**Bitácora exigida para el proyecto final:** [`docs/bitacora_ia.md`](docs/bitacora_ia.md)

> El simulador utiliza reseñas sintéticas y las alertas se generan o registran localmente. No se ha comprobado el envío real de correos a gerentes. La batería histórica M1–M4 y la comparación puntual del Hito 2 son evaluaciones diferentes.

## Requisitos

- Python 3.11 o superior (probado con 3.12 y 3.13)
- Las dependencias de `requirements.txt` (scikit-learn, numpy, pandas, joblib, streamlit)

No necesita GPU, claves de API ni conexión a internet una vez instaladas las dependencias.

## Instalación

```bash
git clone https://github.com/STTLV/ReviewPulse-Agent-Final.git
cd ReviewPulse-Agent-Final
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

**1. Ejecutar el agente desde cero en un escenario** (deja log, memoria SQLite, reportes y alertas en `salidas/demo/`):

```bash
python ejecutar_agente.py --escenario E02 --semilla 11
```

Escenarios: `E01` a `E12` (ver `reviewpulse/escenarios.py`). E02 es el caso típico; E10 y E11 son fallas esperadas de plataforma.

**2. Ejecutar todas las pruebas de desempeño** (11 casos de clasificación y 12 escenarios, 5 repeticiones cada uno):

```bash
python pruebas/ejecutar_pruebas.py           # completo, unos 10 minutos
python pruebas/ejecutar_pruebas.py --rapido  # 1 repetición, para la demo en vivo; escribe en salidas/pruebas_rapido/
```

Resultados **resumidos** en `salidas/pruebas/` (el modo `--rapido` no los toca): `tabla_resultados.md`, `resumen.json`, `m1_clasificacion.csv` y `escenarios.csv`. Los logs detallados históricos de las 60 corridas se conservan en la carpeta de Google Drive enlazada arriba; la carpeta `salidas/pruebas/corridas/` no se publica en GitHub.

**Resultados de la versión entregada:** M1 no se cumple (polaridad 81 % en el conjunto de control), M2 no se cumple (52 % de incidentes detectados en 24 h), M3 y M4 sí en simulación (100 % de reportes generados a tiempo, 3,1 % de falsos positivos). El análisis está en la sección 9.7 del documento.

**2A. Línea base comparativa del Hito 2**

Para cumplir la nueva guía, añadimos una referencia que siempre predice la clase más frecuente del corpus sintético de entrenamiento (semilla 7). Tanto esa referencia como el modelo guardado se evalúan sobre **las mismas 40 reseñas de control** (`datos/evaluacion_manual_holdout.csv`), sin reentrenamiento:

```bash
python pruebas/linea_base_hito2.py
python -m unittest discover -s tests -v
```

| Tarea | Línea base mayoritaria | ReviewPulse (modelo guardado) |
|---|---:|---:|
| Polaridad | 16/40 = **40 %** | 32/40 = **80 %** |
| Tema | 10/40 = **25 %** | 34/40 = **85 %** |

**Evidencias:** `salidas/pruebas/linea_base_hito2.json` y `experiments/hito2/comparacion_holdout.csv`, con resultados fila por fila. Estas cifras NO reemplazan M1 histórica (81 % y 90 %, medias de cinco reentrenamientos).

**3. Interfaz web**

```bash
streamlit run app/streamlit_app.py
```

El menú lateral tiene dos partes. Para el gerente del hotel: *Resumen* (cifras y alertas), *Reseñas del hotel* (historial clasificado, con filtros), *Resumen por semana* y *Probar una reseña* (escribir una reseña en español y ver cómo la clasifica el agente). Para la evaluación: *Demostración técnica* (ejecutar un escenario del simulador, ver el registro percepción → decisión → acción, los resultados de las pruebas y los casos sugeridos). Los datos del panel son el escenario E02 con semilla 11, procesado por el agente al abrir la página.

**4. Reentrenar el modelo** (el agente lo carga ya entrenado desde `datos/modelo.joblib`; si no existe, lo entrena al arrancar):

```bash
python -c "from reviewpulse.modelo import entrenar_modelo_base; entrenar_modelo_base()"
```

## Despliegue en Streamlit Community Cloud

1. Suba el repositorio a GitHub (público).
2. En https://share.streamlit.io elija *Create app*, seleccione el repositorio, la rama `main` y el archivo `app/streamlit_app.py`.
3. Python 3.11 o superior. No requiere secretos.

## Estructura

```
reviewpulse/
  agente.py            ciclo percibir() → decidir() → actuar(); estado interno y metas
  planificador.py      planificación STRIPS con búsqueda en anchura (orientación a metas)
  entorno.py           simulador del hotel y conectores de plataformas (estocástico, dinámico)
  escenarios.py        12 escenarios de prueba (normales, límite, falla esperada)
  preprocesamiento.py  limpieza y validación: idioma, HTML, vacíos, fecha
  modelo.py            clasificador TF-IDF + léxico + regresión logística (herramienta externa)
  lexico.py            léxico de sentimiento y temas con manejo de negación
  memoria.py           memoria de trabajo y repositorio histórico SQLite
  actuadores.py        notificador de alertas y generador del resumen semanal
  evaluacion.py        cálculo de las medidas de desempeño contra la verdad del simulador
  corpus.py            generador de reseñas sintéticas en español
pruebas/
  umbrales.json        umbrales de aceptación, fijados antes de ejecutar las pruebas
  ejecutar_pruebas.py  pruebas M1–M4
  recolectar_estadisticas.py, calibrar_umbrales.py   calibración con semillas 101–105
  techo_deteccion.py   análisis de causa de M2 (regla aplicada a etiquetas reales)
datos/                 conjuntos de evaluación manual y modelo entrenado
config/config.json     umbrales de decisión que fija el gerente
app/streamlit_app.py   interfaz
docs/                  diagramas UML, matriz de decisión, guion del video, bitácora de IA
```

## Dónde está el ciclo percepción → decisión → acción

En `reviewpulse/agente.py`, método `paso()`:

```python
per  = self.percibir(ahora)   # sensores: plataformas, historial, configuración
plan = self.decidir(per)      # estado interno → meta → plan (BFS) → reglas de alerta
self.actuar(plan, per)        # actuadores: etiquetas, alerta, reporte, registro histórico
```

## Qué hace el código y qué hace cada herramienta

| Parte | Quién la hace |
|---|---|
| Percepción, validación, planificación, comparación estadística, decisión de alertar, redacción de la alerta, reporte, memoria | Código propio (Python) |
| Probabilidad de polaridad y de tema de cada reseña | Modelo scikit-learn entrenado antes del despliegue |
| Persistencia | SQLite (biblioteca estándar) |
| Interfaz | Streamlit |

No se usa ningún modelo de lenguaje grande (LLM) ni API paga.

## Modelo BERT

El diseño proponía un modelo tipo BERT para español. El punto de reemplazo está en `reviewpulse/modelo.py` (`ClasificadorBERT`): basta con devolver objetos `Prediccion` con la misma forma. El resto del agente no cambia.

## Reproducibilidad

Todas las fuentes de aleatoriedad usan semillas explícitas. Las semillas de prueba (11, 22, 33, 44, 55) están en `pruebas/umbrales.json`; la calibración usa semillas distintas (101 a 105).

## Documentación histórica y continuidad

Se conservan **sin eliminar** los archivos originales de Ellen en `docs/`, incluidos el informe Word/PDF y la bitácora de la Tarea 3, junto con sus diagramas, scripts de generación y guion de trabajo. Son documentación histórica. **La entrega actual del avance es `reviewpulse_agent_hito2.pdf`**, y la bitácora según la nueva guía está en `docs/bitacora_ia.md`. El desarrollo final IEEE se preparará en hitos posteriores.

El flujo de GitHub Actions (`.github/workflows/comprobacion.yml`) permite comprobar el cierre de SQLite, la nueva línea base y los escenarios E02/E11 sin alterar las métricas históricas.
