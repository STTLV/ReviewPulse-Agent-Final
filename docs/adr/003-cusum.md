# ADR 003: Calibración de CUSUM y medición M1–M4

**Estado:** calibración fijada; evaluación M1–M4 ejecutada, con metas parcialmente incumplidas.

## Decisión y fuentes

Se mantiene la detección CUSUM diaria con `cusum_delta`, `cusum_h` y `cusum_min_negativas`, sin modificar las metas M1–M4 históricas. Se ejecuta la rejilla `delta={0.15,0.20,0.25,0.30}`, `h={2,3,4,5,6}` y `min_negativas={3,4,6}` exclusivamente con E01–E08 y semillas 101–105. Se elige la mayor detección a 24 h con falsos positivos estrictamente por debajo del 8 %; si nadie cumple se reporta y se escoge la menor tasa de FP.

Para acelerar, el calibrador reproduce los eventos de ingesta, cierres, alertas y exclusión del historial con las predicciones del modelo congelado. Las pruebas contrastan sus resultados con el ciclo SQLite real. No se examinan resultados de semillas 11,22,33,44,55 durante la calibración.

## Bloqueo para evitar fuga de prueba

Primero se ejecuta `experiments/calibrar_cusum.py`, que escribe `config/config.json`, `experiments/calibracion_fijada.json` y la rejilla. **Estos archivos deben quedar en un commit anterior** a cualquier medición. `medir_m1_m4.py` rechaza la ejecución si la calibración no está fijada en Git o la configuración cambia respecto de ese registro.

## Métricas y límites

- **M1:** exactitud mínima del 85 % tanto en polaridad como en tema, sobre C03, cinco reentrenamientos sobre corpus de entrenamiento. Se comunica por separado el macro-F1; el gold humano y la comparación con LLM sin ajuste quedan pendientes hasta existir evidencia.
- **M2:** incidentes relevantes detectados en no más de 24 h / incidentes relevantes; meta ≥ 90 %.
- **M3:** reportes generados en ≤ 24 h / 840 reportes esperados de 60 corridas; meta 100 %. No equivale a entrega real de correo.
- **M4:** falsas alertas / total de alertas; meta estrictamente < 10 %. Si no hubo alertas, la tasa se reporta como 0 y se muestra explícitamente el denominador.

La evaluación final usa los **12 escenarios y las semillas 11,22,33,44,55** (60 corridas), con el bucle ReAct y `LLMFalso` sin conexión de red. El CSV combina filas históricas `semanal_v1` y filas nuevas `cusum`, etiquetadas por regla. Se preservan `experiments/v1/` y `data/modelo.joblib`.

**Limitaciones:** la salida del `LLMFalso` no representa precisión de un proveedor real. Los 40 registros C03 son históricos con etiquetado manual asistido por IA, distintos del gold humano independiente de la Tarea 7. Incumplimientos de M1 o M2 deben reportarse, no maquillarse.

## Resultados obtenidos (24/11/2026)

- Parametros CUSUM elegidos antes de las pruebas: delta=0.30, h=5, min_negativas=6.
- Calibracion (E01..E08, semillas 101..105): deteccion=50 %, tasa de falsas alertas=6.25 % (<8 %).
- Regla semanal historica (60 corridas): M2=52 %, M3=100 %, M4=3.125 %.
- CUSUM (60 corridas, semillas 11,22,33,44,55): M2=38 %, M3=100 %, M4=4.3478 %.
- Metas inalteradas: M1 >=85 % para polaridad y tema; M2 >=90 %; M3=100 %; M4 <10 %.
- M1 historica C03: polaridad=81 %, tema=87.5 %, NO cumple ambos umbrales.
- M1 adicional sobre Gold humano T7, 120 reseñas y cinco reentrenamientos: polaridad=91 %, tema=89.83 %, cumple M1=SI. Resultados por semilla en experiments/resultados/m1_gold.json.
- El Gold no se utilizo en entrenamiento ni calibracion. La medicion M1-Gold **complementa** la historica C03 y no cambia las 60 corridas M2-M4.
- Limitaciones: datos sinteticos con patrones previsibles; simulador y conjunto de prueba comparten su origen generativo; CUSUM detecto menos incidentes en 24 h que la linea base. No se evaluo un LLM comercial real.

Las metas no alcanzadas se consignan sin modificar las metricas ni recalibrar con semillas de prueba.
