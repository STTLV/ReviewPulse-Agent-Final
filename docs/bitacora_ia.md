# Bitácora humano-IA | Hito 2 | ReviewPulse-Agent

**Integrantes:** Ellen Nicole Ordoñez Chavez y Sara Bastidas Triana. **Curso:** Inteligencia Artificial, Universidad Tecnológica de Bolívar. **Fecha del corte:** 16 de noviembre de 2026.

Se listan usos relevantes respaldados por la bitácora original y las verificaciones actuales, no transcripciones literales. **Claude** apoyó la construcción del sistema; **ChatGPT** se utilizó para auditoría y preparación de la comparación de referencia. Ninguna de estas herramientas se consulta durante la ejecución del agente.

| Fecha | Integrante | Herramienta | Para qué se utilizó | Qué aceptamos, cambiamos o descartamos | Cómo lo verificamos |
|---|---|---|---|---|---|
| 15/10/2026 | Ellen, con revisión del equipo | Claude | Comparar dos ideas de agente; preparar la matriz de selección y el diseño inicial. | Conservamos ReviewPulse como proyecto elegido; revisamos los pesos y la sensibilidad. | `docs/matriz_decision.py`: 4,05 frente a 3,60; selección estable en doce cambios de peso. |
| 15/10/2026 | Ellen, con revisión del equipo | Claude | Apoyar el código del simulador, clasificador, planificación, memoria y pruebas. | Se conservó el prototipo en Python; se sustituyó la propuesta inicial de BERT por TF-IDF + léxico + regresión logística por recursos disponibles. | Ejecución E02 desde cero; reportes, alerta y logs comparados con CSV. |
| 15–18/10/2026 | Ellen, con revisión del equipo | Claude | Corregir manejo de negaciones y calibrar alertas. | Se ajustó el léxico y se conservaron las pruebas con semillas de calibración distintas de las de evaluación. | `salidas/calibracion/calibracion.csv`; pruebas M1–M4 del repositorio. |
| 12/11/2026 (registro de revisión) | Ellen | Claude | Revisar la preparación de datos, la documentación y la evidencia de las pruebas. | Se conservaron los umbrales documentados como fijados el **15/10/2026**; no se atribuye su creación al 12/11. | Fecha declarada en `pruebas/umbrales.json` y tablas históricas de `salidas/pruebas/`. |
| 16/11/2026 | Sara | ChatGPT | Auditar el ZIP, revisar el Hito 2 y contrastar el PDF con la nueva rúbrica. | Corregimos el comando de consola; separamos ejecución del agente de una línea base comparativa. | Ejecución E02, lectura de la guía y comparación de los resultados guardados. |
| 16/11/2026 | Sara, con revisión del equipo | ChatGPT | Preparar una línea base mayoritaria reproducible y documentarla. | Incorporamos la comparación en las mismas 40 reseñas de control, sin ajustar el modelo ni reescribir los resultados históricos. | `python pruebas/linea_base_hito2.py`: base 40 %/25 % frente al modelo guardado 80 %/85 %. |
| 18/11/2026 | Sara | ChatGPT | Apoyo para reorganizar el codigo en src, data y experiments, corregir rutas y preparar las pruebas de paridad P1. | Revise y aplique los cambios, conserve el modelo anterior y sus resultados, actualice las rutas y adapte las pruebas automaticas. | Compilacion correcta, 4 pruebas locales aprobadas, GitHub Actions exitoso y revision de David de P1, E02 y E11. |
| 19/11/2026 | Ellen | Copilot en VS Code | Revisar e implementar la frontera con el proveedor LLM y corregir los flujos simulados de alarma y cierre. | Se restauraron las dependencias de `v2`, se movieron errores de prueba fuera del cliente y se ajustó el falso para decidir según el resultado de la comparación. | Pruebas unitarias de reintentos, errores, alarma y cierre; llamada real pendiente de ejecutar con credenciales locales. |

## Alcance y decisiones del equipo

Los datos son **sintéticos**. La evaluación M1 histórica representa cinco reentrenamientos, mientras que el Hito 2 compara **una sola carga del modelo guardado** contra un método mayoritario en el mismo conjunto de control. M1 (polaridad) y M2 no alcanzaron sus metas históricas, y se registran así. M3 prueba generación y registro local de reportes, no recepción efectiva de mensajes de correo. Las sugerencias de IA se aceptaron solo después de cotejarlas con el código y las pruebas; la decisión académica sigue siendo de las integrantes.

**Caso de error detectado con apoyo de IA:** al auditar el Hito 2 se identificó que ejecutar el agente completo E02 no era una verdadera *línea base comparativa*. Se corrigió introduciendo un clasificador mayoritario y usando el mismo conjunto de control para ambos sistemas. También se corrigió la sintaxis de `--escenario` y `--semilla` en la documentación.

**Pendientes del proyecto final:** comparación adicional de modelos y ajuste de hiperparámetros, análisis de al menos diez errores, evaluación ética, informe IEEE y defensa oral. Esta bitácora continúa en los próximos hitos.
