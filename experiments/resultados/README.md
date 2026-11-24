# Evidencias de evaluacion - Tarea 8

Esta carpeta contiene mediciones diferentes; no deben mezclarse ni sobrescribirse.

- calibracion_rejilla.csv: 60 combinaciones CUSUM evaluadas con las semillas 101 a 105.
- m1_m4.csv: 60 corridas historicas V1 y 60 corridas CUSUM, con semillas de prueba 11, 22, 33, 44 y 55.
- resumen_m1_m4.json: instantanea HISTORICA con M1 sobre C03 (40 reseñas) y resultados M2-M4. Sus referencias a que el Gold estaba pendiente describen el momento de generar ese archivo y no el estado actual del proyecto.
- m1_gold.json: evaluacion ADICIONAL y posterior sobre las 120 reseñas del Gold humano de Tarea 7. Cinco reentrenamientos con semillas 71-75, sin utilizar el Gold para entrenar ni calibrar.

## Resultados

- M1 sobre Gold: exactitud polaridad 91 %; exactitud tema 89.83 %. Ambas superan la meta de 85 %.
- M1 historica C03: polaridad 81 %; tema 87,5 %. La polaridad no alcanzo 85 %.
- M2 CUSUM: 38 % frente a la meta de 90 %. NO cumple; V1 historica obtuvo 52 %.
- M3 CUSUM: 100 %, cumple la meta del 100 %.
- M4 CUSUM: 4.35 %, cumple la meta estricta de menos del 10 %.

## Limitaciones

Las reseñas son sinteticas y comparten patrones con el generador; la generalizacion a reseñas reales no esta demostrada. Las corridas del agente usan LLMFalso sin red, NO un proveedor LLM real. La comparacion con LLM real pertenece a la evaluacion posterior y no puede declararse completada con estos archivos.

Los objetivos incumplidos se documentan sin ajustar parametros usando las semillas de prueba.
