| Medida de desempeño | Fórmula | Umbral | Casos ejecutados | Resultado obtenido | ¿Cumple? | Evidencia |
|---|---|---|---|---|---|---|
| M1 Exactitud de clasificación | aciertos / reseñas evaluadas (polaridad y tema por separado) | ≥ 85% en ambas | 11 casos × 5 reentrenamientos | Control C03: polaridad 81.0% ± 2.9%, tema 90.0% ± 0.0% | No | m1_clasificacion.csv |
| M2 Detección de cambios en 24 h | incidentes relevantes alertados ≤ 24 h tras el cierre / incidentes relevantes | ≥ 90% | 12 escenarios × 5 semillas (60 corridas, 50 incidentes) | 52.0% (26/50) | No | escenarios.csv, corridas/*/log_ejecucion.jsonl |
| M3 Reporte semanal a tiempo | reportes entregados ≤ 24 h tras el cierre / semanas cerradas | = 100% | 12 escenarios × 5 semillas (840 semanas) | 100.0% (840/840); máx. 24 h | Sí | corridas/*/reportes/ |
| M4 Falsos positivos de alerta | alertas sin incidente relevante / alertas enviadas | < 10% | 12 escenarios × 5 semillas (32 alertas) | 3.1% (1/32) | Sí | corridas/*/bandeja_salida.jsonl |

## M1 por caso (media ± desviación estándar en 5 reentrenamientos)

| Caso | Descripción | Tipo | n | Polaridad | Tema | Rechazo | ¿Cumple? |
|---|---|---|---|---|---|---|---|
| C01 | Sintético con frases no vistas | normal | 500 | 88.7% ± 1.5% | 89.2% ± 1.0% | — | Sí |
| C02 | Manual de desarrollo (40) | normal | 40 | 87.5% ± 1.8% | 97.0% ± 2.7% | — | Sí |
| C03 | Manual de control, nunca usado al ajustar (40) | normal | 40 | 81.0% ± 2.9% | 90.0% ± 0.0% | — | No |
| C04 | Control en minúsculas y sin tildes | limite | 40 | 81.0% ± 2.9% | 90.0% ± 0.0% | — | No |
| C05 | Control con errores de tipeo | limite | 40 | 70.0% ± 5.0% | 84.0% ± 2.9% | — | No |
| C06 | Solo ironía y sarcasmo (12) | limite | 12 | 100.0% ± 0.0% | 100.0% ± 0.0% | — | Sí |
| C07 | Reseñas largas (>60 palabras) | limite | 300 | 81.5% ± 0.9% | 100.0% ± 0.0% | — | No |
| C08 | Reseñas de una sola frase | limite | 300 | 59.7% ± 3.3% | 89.3% ± 1.5% | — | No |
| C09 | Sintético con 30 % de ironía | limite | 500 | 88.1% ± 1.4% | 90.2% ± 1.1% | — | Sí |
| C10 | Otro idioma: debe descartarse | falla | 7 | — | — | 100.0% ± 0.0% | Sí |
| C11 | Entradas inválidas: vacías, emojis, HTML, sin fecha | falla | 8 | — | — | 100.0% ± 0.0% | Sí |

## Escenarios del agente (5 semillas cada uno)

| Escenario | Tipo | Detección ≤ 24 h | Detectadas tarde | Reportes a tiempo | Alertas | Falsos positivos | Latencia media alerta |
|---|---|---|---|---|---|---|---|
| E01 Operación estable | normal | — | 0 | 100.0% ± 0.0% | 0 | 0 (0.0 ± 0.0 por corrida) | — |
| E02 Incidente de limpieza | normal | 60.0% ± 54.8% | 0 | 100.0% ± 0.0% | 3 | 0 (0.0 ± 0.0 por corrida) | 12 h |
| E03 Dos incidentes | normal | 70.0% ± 27.4% | 0 | 100.0% ± 0.0% | 7 | 0 (0.0 ± 0.0 por corrida) | 12 h |
| E04 Temporada alta | limite | — | 0 | 100.0% ± 0.0% | 1 | 1 (0.2 ± 0.4 por corrida) | — |
| E05 Incidente moderado | limite | 40.0% ± 54.8% | 0 | 100.0% ± 0.0% | 2 | 0 (0.0 ± 0.0 por corrida) | 12 h |
| E06 Variación leve | limite | — | 0 | 100.0% ± 0.0% | 0 | 0 (0.0 ± 0.0 por corrida) | — |
| E07 Volumen bajo | limite | 0.0% ± 0.0% | 0 | 100.0% ± 0.0% | 0 | 0 (0.0 ± 0.0 por corrida) | — |
| E08 Ironía alta | limite | 100.0% ± 0.0% | 0 | 100.0% ± 0.0% | 5 | 0 (0.0 ± 0.0 por corrida) | 12 h |
| E09 Entradas inválidas | falla | 80.0% ± 44.7% | 0 | 100.0% ± 0.0% | 4 | 0 (0.0 ± 0.0 por corrida) | 12 h |
| E10 TripAdvisor caído | falla | 100.0% ± 0.0% | 0 | 100.0% ± 0.0% | 5 | 0 (0.0 ± 0.0 por corrida) | 24 h |
| E11 Todas las plataformas caídas | falla | 0.0% ± 0.0% | 5 | 100.0% ± 0.0% | 5 | 0 (0.0 ± 0.0 por corrida) | — |
| E12 Arranque en frío | falla | 0.0% ± 0.0% | 0 | 100.0% ± 0.0% | 0 | 0 (0.0 ± 0.0 por corrida) | — |

Sin los escenarios de falla esperada: detección 56.7% (17/30), falsos positivos 5.6% (1/18).