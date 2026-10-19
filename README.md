# ReviewPulse-Agent

Agente inteligente **basado en modelos y orientado a metas** (Russell y Norvig) que clasifica las reseñas de un hotel piloto por polaridad (positiva, negativa, neutra) y tema (limpieza, servicio, ubicación, precio), compara cada semana contra su historial y alerta al gerente cuando el tono negativo de un tema se sale de lo normal.

Proyecto del curso Inteligencia Artificial, Universidad Tecnológica de Bolívar (Tarea 3: implementación y pruebas).

**Aplicación pública verificada:** https://reviewpulse-agent-sttlv.streamlit.app/
**Repositorio de entrega (STTLV):** https://github.com/STTLV/ReviewPulse-Agent-Final
**Integrantes:** Ellen Nicole Ordoñez Chavez y Sara Bastidas Triana.
**Implementación inicial:** desarrollada por el grupo con apoyo de Claude. **Auditoría, pruebas y correcciones finales:** realizadas por el equipo con apoyo de ChatGPT.
**Evidencias de las 60 corridas:** https://drive.google.com/drive/folders/1CnpElJThx8Cf-WtnUxzvz43CeNVsFXdq?usp=drive_link

> **Importante:** la aplicación usa reseñas generadas por el simulador, no las API de TripAdvisor ni Google.
> El guardado en SQLite y la generación de reportes se verifican en tiempo simulado;
> el envío externo real de correos no está validado en las pruebas de la entrega.

## Requisitos

- Python 3.11 o superior (probado con 3.12 y 3.13)
- Las dependencias de `requirements.txt` (scikit-learn, numpy, pandas, joblib, streamlit)

No necesita GPU, claves de API ni conexión a internet una vez instaladas las dependencias.
Se exige **scikit-learn 1.9.1** porque `datos/modelo.joblib` se entrenó y guardó con esa versión.
Ejecutar `python -m pip install -r requirements.txt` en un entorno virtual nuevo; evitar
mezclarlo con entornos de otros proyectos.

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

Resultados **resumidos** incluidos en el repositorio: `salidas/pruebas/tabla_resultados.md`,
`resumen.json`, `m1_clasificacion.csv` y `escenarios.csv`. **Los logs detallados no se
incluyen en GitHub**: la carpeta `salidas/pruebas/corridas/` está excluida para evitar
publicar 60 bases SQLite y datos sintéticos extensos. Para generar todos los logs, ejecute la batería completa. El equipo dispone también del
paquete separado **`ReviewPulse_Ellen_Evidencias_60_Corridas.zip`**, que contiene la evidencia
histórica previa al arreglo de SQLite: 60 logs JSONL, bases SQLite, reportes y bandejas.
Las métricas, el modelo y los umbrales de dicha evidencia coinciden con esta versión.
Este paquete **no** equivale a afirmar que se repitieron las 60 corridas tras el arreglo.
El ZIP histórico se comparte mediante la carpeta pública de Google Drive enlazada arriba y
en el informe final; **la plataforma académica solo permite entregar dos archivos PDF**.
No sustituya la batería oficial con `--rapido`.

**Resultados de la batería documentada:** M1 no se cumple (polaridad 81 % en el conjunto de control), M2 no se cumple (52 % de incidentes detectados en 24 h), M3 y M4 sí en simulación (100 % de reportes locales generados a tiempo, 3,1 % de falsas alertas). El análisis está en la sección 9.7 del documento.

**3. Interfaz web**

```bash
streamlit run app/streamlit_app.py
```

El menú lateral tiene dos partes. Para el gerente del hotel: *Resumen* (cifras y alertas), *Reseñas del hotel* (historial clasificado, con filtros), *Resumen por semana* y *Probar una reseña* (escribir una reseña en español y ver cómo la clasifica el agente). Para la evaluación: *Demostración técnica* (ejecutar un escenario del simulador, ver el registro percepción → decisión → acción, los resultados de las pruebas y los casos sugeridos). Los datos del panel son el escenario E02 con semilla 11, procesado por el agente al abrir la página.

**4. Reentrenar el modelo** (el agente lo carga ya entrenado desde `datos/modelo.joblib`; si no existe, lo entrena al arrancar):

```bash
python -c "from reviewpulse.modelo import entrenar_modelo_base; entrenar_modelo_base()"
```

## Verificaciones rápidas y corrección para Windows

```bash
python -m unittest discover -s tests -v
python ejecutar_agente.py --escenario E02 --semilla 11
python -m streamlit run app/streamlit_app.py
```

El agente cierra tanto `log_ejecucion.jsonl` como la conexión `memoria.db` al terminar,
**también cuando aparece una excepción**. Esto permite eliminar carpetas temporales
en Windows sin `PermissionError [WinError 32]`. Las pruebas en `tests/` verifican el cierre.

## Documentación académica

El **informe final** y la **bitácora de uso de IA** ya se entregaron por separado en
formato PDF en el aula virtual, de acuerdo con la restricción de dos archivos. El informe
incluye la sección **9.9 Enlaces** y distingue las medidas SMART cumplidas y no cumplidas.

La carpeta `docs/` conserva los diagramas y archivos técnicos de trabajo; **no es la
versión definitiva del informe ni de la bitácora presentada al docente**. Los registros
históricos detallados se conservan en `ReviewPulse_Ellen_Evidencias_60_Corridas.zip`,
disponible en la [carpeta pública de Google Drive](https://drive.google.com/drive/folders/1CnpElJThx8Cf-WtnUxzvz43CeNVsFXdq?usp=drive_link), no en este repositorio.

## Despliegue en Streamlit Community Cloud

**Aplicación ya desplegada:** https://reviewpulse-agent-sttlv.streamlit.app/
**Repositorio de origen del despliegue:** https://github.com/STTLV/ReviewPulse-Agent-Final (rama `main`).

Se desplegó desde Streamlit Community Cloud, archivo principal `app/streamlit_app.py`,
Python 3.13, scikit-learn 1.9.1. El repositorio y la aplicación son públicos
para que el docente pueda consultar el código y ejecutar la demostración.

**Comprobación comunicada por el equipo, 19/10/2026:** acceso en incógnito sin iniciar sesión;
menús *Resumen*, *Reseñas del hotel* (incluidos filtros), *Resumen por semana* y *Probar una reseña*;
ejecuciones E02/semilla 11 y E11/semilla 11 desde *Demostración técnica*, sin WinError 32.
GitHub Actions aprobó instalación, compatibilidad del modelo, pruebas SQLite y ambos escenarios.
Estas verificaciones de despliegue fueron realizadas por la estudiante; no sustituyen la batería
estadística completa de 60 corridas que respalda los valores SMART.

**Recorrido para evaluación docente:**
1. Abrir la aplicación pública y consultar *Resumen* y *Reseñas del hotel*.
2. Probar una reseña breve en español en *Probar una reseña*.
3. Entrar a *Demostración técnica → Ejecutar un escenario*; escoger `E02`, semilla `11`,
   pulsar *Ejecutar desde cero* y revisar la alerta, el reporte y las fases del registro.
4. Repetir con `E11`, semilla `11`, para evidenciar fallos de plataformas y alerta tardía.
5. Abrir la pestaña *Resultados de las pruebas* para consultar M1–M4; descargar o revisar
   `salidas/pruebas/tabla_resultados.md` y la evidencia histórica en Google Drive.

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
docs/                  diagramas UML, matriz de decisión y archivos técnicos de trabajo
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
