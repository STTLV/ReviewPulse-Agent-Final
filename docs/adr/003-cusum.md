# ADR 003: Calibración de CUSUM y medición M1–M4

**Estado:** calibración fijada; evaluación M1–M4 ejecutada, con metas parcialmente incumplidas.

## Decisión y fuentes

Se mantiene la detección CUSUM diaria con `cusum_delta`, `cusum_h` y `cusum_min_negativas`, sin modificar las metas M1–M4 históricas. Se ejecuta la rejilla `delta={0.15,0.20,0.25,0.30}`, `h={2,3,4,5,6}` y `min_negativas={3,4,6}` exclusivamente con E01–E08 y semillas 101–105. Se elige la mayor detección a 24 h con falsos positivos estrictamente por debajo del 8 %; si nadie cumple se reporta y se escoge la menor tasa de FP.

Para acelerar, el calibrador reproduce los eventos de ingesta, cierres, alertas y exclusión del historial con las predicciones del modelo congelado. Las pruebas contrastan sus resultados con el ciclo SQLite real. No se examinan resultados de semillas 11,22,33,44,55 durante la calibración.

## Bloqueo para evitar fuga de prueba

Primero se ejecuta `experiments/calibrar_cusum.py`, que escribe `config/config.json`, `experiments/calibracion_fijada.json` y la rejilla. **Estos archivos deben quedar en un commit anterior** a cualquier medición. `medir_m1_m4.py` rechaza la ejecución si la calibración no está fijada en Git o la configuración cambia respecto de ese registro.

## Métricas y límites

- **M1:** el diseño define la evaluación oficial sobre C03 (40 registros), con cinco reentrenamientos y meta de exactitud >=85 % en polaridad y tema. La evaluación con el Gold humano de T7 es complementaria y no sustituye C03. La comparación contra un LLM sin ajuste sigue pendiente.
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

## Aclaraciones de revision solicitadas por David (24/11/2026)

### M1: resultado oficial frente a evaluacion complementaria

El indicador **M1 oficial** esta definido sobre el conjunto historico **C03**, de 40 registros. La evaluacion sobre el **Gold humano de Tarea 7**, de 120 reseñas unicas, es una medicion adicional; **no reemplaza** el indicador oficial. En ambos casos se hicieron cinco reentrenamientos y la meta exige exactitud **>= 85 % en polaridad y en tema simultaneamente**.

| Evaluacion | Polaridad | Tematica | Resultado frente a M1 |
|:--|--:|--:|:--|
| **M1 C03 (oficial)** | **81 %** | **87,5 %** | **No cumple**, porque polaridad < 85 % |
| **M1 Gold T7 (complementaria)** | **91 %** | **89,83 %** | **Cumple ambas metas** |

Fuentes: `experiments/resultados/resumen_m1_m4.json` (C03) y `experiments/resultados/m1_gold.json` (Gold). Se mantienen los resultados historicos y las limitaciones del origen sintetico del Gold.

### M2: por que CUSUM obtuvo 38 % frente al 52 % de la regla semanal

Se usaron **60 combinaciones de calibracion**: `delta` en {0.15, 0.20, 0.25, 0.30}, `h` en {2, 3, 4, 5, 6} y `min_negativas` en {3, 4, 6}. La calibracion se limito a E01-E08 y semillas 101-105; busco maximizar la deteccion a 24 horas **sujeta a una tasa de falsas alertas estrictamente < 8 %**. Se fijaron `delta=0.30`, `h=5` y `min_negativas=6`; en calibracion se detectaron 15 de 30 incidentes (50 %) con 1 falsa alerta entre 16 alertas (6,25 %).

La evaluacion posterior fue **independiente de la calibracion**: escenarios E01-E12 con semillas 11, 22, 33, 44 y 55, esto es, 60 corridas por metodo. En ese conjunto, V1 detecto **26/50 = 52 %** de los incidentes dentro de 24 h y CUSUM **19/50 = 38 %**. Ambos quedaron por debajo de la meta M2 **>= 90 %**. La diferencia es de **7 detecciones** o **14 puntos porcentuales**.

| Escenario | Detecciones V1 en 24 h | Detecciones CUSUM en 24 h | Diferencia |
|:--|--:|--:|--:|
| E02 | 3 | 1 | 2 |
| E03 | 7 | 4 | 3 |
| E05 | 2 | 1 | 1 |
| E09 | 4 | 3 | 1 |
| **Total de estos escenarios** | **16** | **9** | **7** |

La rejilla refleja una compensacion entre sensibilidad y control de falsas alertas. Es **plausible** que el umbral de acumulacion y el minimo de seis negativas hayan reducido detecciones tempranas en ciertos escenarios; los resultados agregados **no prueban por si solos una causa unica**. Lo que si se observa es una menor deteccion oportuna de CUSUM con los parametros previamente fijados.

**Caso E11 (caida de todas las plataformas):** el escenario define un incidente relevante de servicio durante la semana 9, mientras todas las plataformas dejan de responder desde el inicio de esa semana hasta **36 horas despues del cierre**. En las cinco semillas evaluadas, **ninguna regla detecto el incidente en las primeras 24 h (0/5 tanto V1 como CUSUM)**. E11 muestra la dependencia de los mecanismos frente a la disponibilidad de reseñas, **pero no explica la diferencia de siete detecciones entre ambos metodos**, que se concentra en E02, E03, E05 y E09.

### M3 y M4: cumplimiento e interpretacion

- **M3:** CUSUM genero 840/840 reportes dentro del plazo considerado (**100 %**); esto no significa que se comprobara la entrega de correos reales.
- **M4:** CUSUM produjo 1 falsa alerta de 23 alertas totales (**4,35 %**). **Cumple la meta estricta `< 10 %`**, no `<= 10 %`.
- En la evaluacion final, V1 tambien registro una falsa alerta (1/32 = 3,125 %). Ni la deteccion M2 de V1 ni la de CUSUM alcanzo el 90 %.

**Limitaciones:** los escenarios y reseñas son sinteticos; las corridas M2-M4 emplean `LLMFalso`, no un modelo LLM comercial real. No se ajustaron parametros usando semillas de prueba ni se alteraron metricas para cambiar los incumplimientos observados.
