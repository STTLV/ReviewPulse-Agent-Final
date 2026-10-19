# Guion del video — ReviewPulse-Agent (máximo 20 minutos)

Ambas integrantes con cámara y voz. Integrante A: Ellen Nicole Ordoñez Chavez. Integrante B: Sara Bastidas Triana.
Poner este índice en la descripción del video y en la primera diapositiva.

| Minuto | Sección | Quién | Qué mostrar |
|---|---|---|---|
| 00:00 | Introducción | A y B | Presentarse, problema del hotel piloto, objetivo del agente |
| 01:30 | Selección del agente | B | Matriz de decisión: 4,05 frente a 3,60; criterio más influyente (medibilidad) y sensibilidad ±10 |
| 03:30 | Arquitectura | A | Diagrama de componentes y los 7 componentes IBM con su módulo |
| 06:00 | Código: ciclo del agente | A | `agente.py`, método `paso()`: `percibir()`, `decidir()`, `actuar()`; el planificador BFS |
| 08:00 | Demo en vivo, caso típico | B | Terminal: `python ejecutar_agente.py --escenario E02 --semilla 11`; abrir el reporte de la semana 9 y la alerta |
| 10:30 | Demo en vivo, falla esperada | A | `--escenario E11`: plataformas caídas, reporte marcado incompleto, alerta tardía; mostrar el log con `plataforma_no_disponible` y `esperar` |
| 12:30 | Interfaz | B | Streamlit: mostrar el panel del hotel (resumen, reseñas clasificadas, resumen por semana); en «Probar una reseña», escribir una reseña en inglés (se descarta); en «Demostración técnica», ejecutar E04 (temporada alta) y mover un ajuste de alerta |
| 14:00 | Ejecución de pruebas | A | `python pruebas/ejecutar_pruebas.py --rapido` en vivo; abrir `tabla_resultados.md` de la corrida completa |
| 16:30 | Resultados y análisis | B | Tabla de resultados: qué se cumple, qué no y por qué |
| 18:30 | Limitaciones y cierre | A y B | Trabajo futuro y despedida |

## Notas por sección

**00:00 Introducción.** Los hoteles reciben reseñas que nadie lee a tiempo. ReviewPulse clasifica cada reseña por polaridad y tema, compara la semana contra las anteriores y avisa al gerente si algo se dispara.

**01:30 Selección.** Leer los seis criterios y sus pesos. Explicar que la mayor diferencia ponderada está en medibilidad del desempeño (0,40), y que ninguna variación de ±10 puntos en ningún criterio cambia la decisión. Lo que se pierde: utilidad y aprendizaje de RetainIQ.

**03:30 Arquitectura.** Recorrer el diagrama de izquierda a derecha: entorno simulado, percepción, planificador, acción, modelo externo, memoria SQLite, actuadores. Decir qué componente IBM no se implementó completo (aprendizaje y adaptación) y por qué.

**06:00 Código.** Mostrar `percibir()` (sensores), `_hechos()` y `planificar()` (orientación a metas), `_evaluar_semana()` (prueba binomial, puntaje z y delta), y los métodos `_a_...` (actuadores).

**08:00 Caso típico.** Ejecutar desde cero, no mostrar resultados guardados. Señalar en la salida la línea ALERTA y la latencia (12 h tras el cierre).

**10:30 Falla esperada.** Explicar que el agente no se cae: espera reintento, entrega el reporte antes de 24 h con la marca de datos incompletos y, cuando llegan las reseñas atrasadas, emite una alerta tardía. Es la falla esperada que se ve en M2.

**14:00 Pruebas.** Ejecutar la versión rápida en vivo (1 repetición, unos 2 minutos; se puede acelerar en edición) y luego abrir los resultados de la corrida completa de 5 repeticiones.

**16:30 Resultados.** Leer la tabla de resultados del documento. Explicar la medida que no se cumplió con su causa y la corrección propuesta.

**Grabación.** Zoom o Teams con pantalla compartida y las dos cámaras visibles. Subir a YouTube como "No listado" y verificar el enlace en una ventana de incógnito.
