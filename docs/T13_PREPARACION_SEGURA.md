# ReviewPulse-Agent 2.0 | Tarea 13: preparación previa a corridas reales

**Fecha:** 2026-11-24. **Esta entrega NO contiene datos de corridas reales ni veredictos del juez.**

## Qué se implementó sin depender de aprobaciones

- `experiments/analizar.py`: `resumir`, validación estricta de la matriz 20 × 3 × 2, bootstrap pareado **por tarea** (20 clusters, cada uno con promedio de las 3 repeticiones), tiempos, pasos, tokens, errores de herramientas, tasas por tipo, `resumen.json`, `subgrupos.csv`, borrador de `errores.csv`.
- `tests/test_analisis.py`: pruebas sintéticas sin modelos, sin credenciales ni peticiones de red.
- `experiments/protocolo_revision_juez.csv`: se preseleccionan de forma reproducible dos de los seis dictámenes: **agente/R01/repetición 1** y **base/R01/repetición 2**, antes de ver las salidas.
- El programa **se niega a generar resultados finales** si falta `corridas.csv`, hay duplicados, alguna corrida está pendiente o no existen exactamente las 120 combinaciones planificadas.

## Dependencias para finalizar la Tarea 13

1. **Tarea 9**: revisión de David, PR #26 y sus posibles cambios; ejecución corta autorizada del runner antes de las 120 corridas. La 13 depende del *runner*, el catálogo y el CSV de T9. No necesita la API FastAPI de T10 para comparar agente y baseline.
2. **Proveedor**: confirmar endpoint, ID exacto de modelos, credenciales nuevas/seguras, presupuesto y precio oficial. Con las 60 llamadas baseline de ~32k tokens de contexto, no asumir que el total cuesta menos de US$1. Revisar presupuesto **antes** de autorizar la corrida completa.
3. **Auditoría de evaluación**: `corridas.csv` no incluye los metadatos de plataforma, longitud, tema y errores de tipeo de cada ejemplo, por lo que no permite calcular honestamente esos 4 subgrupos. `cifras_no_respaldadas` solo se alimenta para tareas de conteo y no da el denominador de respuestas numéricas del diseño; tampoco hay datos suficientes para la trazabilidad global. Hay que coordinar instrumentación con T9 **antes de ejecutar 120 veces** para no perder métricas.
4. **Revisión humana del juez**: el runner actual exporta trazas redactadas, no el texto de la respuesta completa. Para evaluar manualmente dos veredictos es necesario un procedimiento privado de captura de respuestas, con revisión y descarte seguro, sin claves ni datos personales. Registrar acuerdo/desacuerdo en el protocolo preseleccionado.
5. **Errores**: como mínimo 10 fallos deben analizarse con `tarea`, `tipo_error`, evidencia de la traza e hipótesis causal. Si hubiera menos de 10 fallos, reportarlo verazmente; nunca fabricar ejemplos.
6. **Calibración**: umbrales de `experiments/umbrales.json` inmutables desde el commit de T9; `m1_m4.csv` de T8 es independiente y no debe confundirse con las 120 corridas de T13.
7. **Entrega**: luego de corridas y revisión humana, ejecutar `analizar.py`, auditar los archivos y subir en un PR T13 separado hacia `v2` cuando corresponda. No fusionar la preparación basada en T9 antes de que T9 se estabilice.

## Uso (después de integrar y autorizar las corridas)

Desde la raíz del repositorio:

```powershell
$env:PYTHONPATH = ".;src"
python -m unittest discover -s tests -p test_analisis.py -v
python experiments/analizar.py
```

La segunda instrucción **no ejecuta ningún LLM**. Si todavía no existen las 120 ejecuciones reales, se detiene sin escribir resultados inventados. El interruptor `--sobrescribir` solo sirve para actualizar archivos derivados después de una auditoría; no modifica nunca `corridas.csv`, los umbrales ni resultados de T8.

**Control de seguridad:** no registrar claves, `.env`, prompts completos ni respuestas sensibles en el repositorio. No subir el `corridas.csv` ni las trazas hasta inspeccionarlos. No copiar los 120 resultados de pruebas automatizadas como si fueran las ejecuciones reales de los LLM.
