# T13: correcciones experimentales verificadas (26/11/2026)

**Alcance:** revisión documental de la evaluación existente, sin repetir llamadas LLM, sin editar los resultados originales. El costo es una referencia condicional, no una factura. El análisis de subgrupos corresponde al clasificador del Gold y NO a éxitos por tarea del experimento ReAct/base.

## Integridad de los datos

- Matriz conservada: 120 filas únicas; 60 agente (48 éxitos), 60 base (45 éxitos).
- Archivo protegido: `experiments/resultados/corrida_120/corridas.csv`, SHA256 `64b02edf7f851e295ea4ffdf0d98a6bf601b668d67206c16c0251426e542c1d5`.
- Trazas `.jsonl` conservadas en el ZIP: 120 (60 agente + 60 base); no se reescriben.
- Umbrales de T9 conservados sin modificación; la ventaja descriptiva de 5 pp no alcanza significancia (IC pareado [-10,20] pp).

## Diez errores: lectura específica

La matriz `experiments/resultados/corrida_120/analisis/revision_documental_10.csv` aporta una explicación separada para las diez filas. Se distinguen los hechos observables (CSV, traza, verificador, juez) de hipótesis sobre la respuesta NO conservada.

- **L02, agente:** la reseña Gold EVAL-003 es `negativa/precio`, con error tipográfico `much omás`. El clasificador guardado predice `positiva` con confianza de polaridad 0.47005 y tema `precio`. Corrigiendo a `mucho más` la predicción del clasificador pasa a `neutra` (confianza 0.49318), no a `negativa`; por tanto, el error tipográfico afecta la salida pero NO constituye explicación causal completa. La traza confirma que el agente llamó `clasificar_resena`, no qué texto exacto emitió al final.
- **P02 y A02, agente:** la herramienta `comparar_semana` para precio en semana 11 devolvió `S_max=2.5637`, `h=5`, `alarma=false`, 6 negativas de 17 reseñas. El protocolo marca `incidente=true`/`alerta_esperada=true`. Hay una **desalineación de etiqueta esperada frente a regla CUSUM**; no se demuestra que el LLM se haya equivocado al interpretar esa regla. La respuesta completa no quedó conservada, así que el verificador pudo rechazar la decisión o el formato final.
- **R01, agente:** el juez guardó criterios `[verdadero, falso, verdadero, verdadero]` y señaló en su evidencia una mención de `1,5` sobre limpieza y afirmaciones sobre CUSUM/historial/completitud que consideró sin sustento. **Es el dictamen del juez**, no una inspección directa de la respuesta original.
- **R01, base:** el juez guardó criterios `[verdadero, falso, verdadero, verdadero]` y objetó cifras o afirmaciones sin respaldo SQL. No tenemos el texto íntegro para comprobarlo independientemente.
- **C01, base, repeticiones 1 y 2:** `exito=0`, `cifras_no_respaldadas=1` en el control restringido de conteo; el texto ausente impide determinar el numeral final.
- **P03, base:** `exito=0` frente a etiqueta `incidente=false`, sin texto para distinguir decisión errónea y formato final inválido.
- **A02 y P02, base:** fallaron contra el verificador, pero no llamaron herramientas; el resultado del comparador del agente NO es evidencia de la salida emitida por la base.

## Revisión humana del juez

Se habían preseleccionado `agente/R01/r1` y `base/R01/r2` para contraste humano. **No evaluable retrospectivamente:** el runner no retuvo las respuestas originales completas, de manera que no es posible contrastar el dictamen con el texto que evaluó el juez. No llenar `veredicto_humano` ni `acuerdo`; el estado correcto es *no evaluable por ausencia de respuesta*. Repetir la evaluación produciría una salida nueva, no recuperaría la original.

## Costo de referencia (120 corridas, sin piloto)

Tarifas en `experiments/precios_referencia_t13.json`: principal (`gpt-6-astra`) US$10.00 y US$50.00 por millón de tokens de entrada/salida; juez (`gpt-5.6-sol`) US$4.00 y US$20.00.

| Componente | Tokens entrada | Tokens salida | USD estimados |
|---|---:|---:|---:|
| Principal | 2,446,892 | 21,196 | 25.52872 |
| Juez | 5,300 | 1,724 | 0.05568 |
| **Total** | **2,452,192** | **22,920** | **25.58440** |

**Meta de US$1:** incumplida bajo las tarifas de referencia, aproximadamente **US$25,58**. El archivo de precios utiliza modelos de referencia **distintos** de los alias realmente ejecutados en OmniRoute; no se afirma que sea el costo facturado, ni que los precios oficiales permanezcan vigentes. El piloto (4 ejecuciones), las comprobaciones previas y Railway quedan fuera de esta estimación. El informe anterior que indicaba US$0,26 estaba usando otra tabla tarifaria y debe corregirse para no mezclar escenarios.

## Subgrupos de IA responsable: clasificador Gold, no ReAct

Se utilizó `data/modelo.joblib` para clasificar las mismas 120 reseñas Gold; no se utilizaron tokens de proveedor. El grupo `tipeo` se obtuvo reproduciendo la semilla 2026 y registrando la permutación de caracteres de `_ruido()` (18 textos), verificando igualdad exacta de los 120 textos generados contra `gold.csv`. Longitud por caracteres: corta hasta 99, media 100-150, larga 151 o más; 40 registros por tercil. Tema tomado del Gold humano.

| Dimensión | Grupo | N | Acierto polaridad | Acierto tema |
|---|---|---:|---:|---:|
| longitud | corta | 40 | 36/40 (90.0 %) | 36/40 (90.0 %) |
| longitud | larga | 40 | 38/40 (95.0 %) | 37/40 (92.5 %) |
| longitud | media | 40 | 37/40 (92.5 %) | 37/40 (92.5 %) |
| tema | limpieza | 36 | 35/36 (97.2 %) | 33/36 (91.7 %) |
| tema | precio | 29 | 26/29 (89.7 %) | 29/29 (100.0 %) |
| tema | servicio | 21 | 21/21 (100.0 %) | 18/21 (85.7 %) |
| tema | ubicacion | 34 | 29/34 (85.3 %) | 30/34 (88.2 %) |
| tipeo | con_permutacion | 18 | 16/18 (88.9 %) | 17/18 (94.4 %) |
| tipeo | sin_permutacion | 102 | 95/102 (93.1 %) | 93/102 (91.2 %) |

La exactitud global del clasificador persistido fue polaridad 111/120 (92,5 %), tema 110/120 (91,7 %) y ambas 101/120 (84,2 %). Estas cifras NO deben sustituir los promedios de cinco reentrenamientos M1, ni las tasas de éxito por tarea ReAct/base. El diferencial de polaridad con/sin permutación (16/18 frente a 95/102) es descriptivo, no prueba estadística ni causalidad. Los subgrupos de `plataforma` y los subgrupos de **éxito del LLM por fila T13** continúan no evaluables sin metadatos unidos a cada respuesta.

**Precaución de reproducibilidad:** el modelo fue guardado con scikit-learn 1.9.1 y cargado en esta auditoría con 1.8.0, provocando advertencias de compatibilidad. Las predicciones anteriores se comprobaron numéricamente en este entorno, pero deben reproducirse también con las dependencias del proyecto antes de darlas por definitivamente certificadas.

## Cierre operativo y documentación

Las ramas/PR #32, #33 y #34 se consideran fusionados **según confirmación de Sara**, no según las trazas T13. El README ya contiene T11 y configuración de Railway, pero ningún archivo demuestra por sí solo despliegue público, conexión de producción, persistencia entre instancias ni cumplimiento de seguridad en vivo. Una vez Railway funcione, actualizar el estado y grabar evidencia de salud, interfaz y rutas permitidas; no divulgar la clave en video ni repositorio.
