# Datos del proyecto ReviewPulse 2.0

## Origen y límites

Las reseñas del proyecto son **sintéticas**, generadas a partir de plantillas de `reviewpulse.corpus`. No se recolectaron reseñas reales ni se dispone de evidencia para extrapolar los resultados a hoteles reales. Hay cuatro temas (`limpieza`, `servicio`, `ubicacion`, `precio`) y tres polaridades (`positiva`, `negativa`, `neutra`). El generador puede introducir ironía, errores tipográficos y referencias secundarias a otros temas. Esto permite experimentar de forma reproducible, pero no equivale a medir desempeño sobre conversaciones humanas auténticas.

## Partición y prevención de fuga

- **Entrenamiento:** corpus sintético del clasificador, semilla `7`, con `conjunto="entrenamiento"`.
- **Validación:** escenario `C02`, utilizado para controlar el comportamiento sin usar el conjunto final de prueba.
- **Prueba:** escenario `C03` y el conjunto **gold** de 120 reseñas generado con `construir_corpus(120, semilla=2026, conjunto="evaluacion", prob_ironia=0.10)`.
- Las frases de evaluación proceden del subconjunto reservado por `corpus._particion`; no se incorporan al entrenamiento ni se optimizan parámetros contra gold. Algunos cierres y las estructuras del generador son compartidos, por lo que la independencia no es absoluta.

## Muestra ciega y etiquetado humano

`data/gold/muestra.csv` contiene exclusivamente las columnas `id,texto`. Los primeros 12 IDs son comunes a ambas personas. Sara etiqueta los IDs 1–66 (12+54); Ellen los IDs 1–12 y 67–120 (12+54). Las plantillas usan las columnas `id,texto,polaridad,tema`. Las etiquetas deben rellenarlas las integrantes **manualmente, sin IA y sin consultar la verdad del simulador**. Los archivos se entregan vacíos; no se atribuyen etiquetas inventadas a ninguna persona.

Categorías permitidas: polaridad `positiva`, `negativa`, `neutra`; tema `limpieza`, `servicio`, `ubicacion`, `precio`. Al editar los CSV se deben conservar las columnas, los IDs y los textos originales (incluidos tildes y signos).

`experiments/preparar_gold.py` prepara los archivos de manera determinista y deja la verdad del simulador en una carpeta privada **fuera del repositorio** (`~/.reviewpulse/verdad_simulador_2026.csv`). No debe abrirse hasta concluir el etiquetado. Nunca añadir este archivo privado a Git.

`experiments/acuerdo.py` calcula **kappa de Cohen de polaridad y tema sobre los 12 comunes**. Si hay discrepancias crea `data/gold/acuerdos_resueltos.csv`: las integrantes deben acordar las respuestas y justificar cada diferencia. Solo entonces construye `data/gold/gold.csv` (`id,texto,polaridad,tema`), sin usar las etiquetas del simulador.

Comandos desde la raíz del repositorio:

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe experiments/preparar_gold.py
.\.venv\Scripts\python.exe -m unittest tests.test_datos -v
# Después de completar las 2 plantillas a mano:
.\.venv\Scripts\python.exe experiments/acuerdo.py
```

**Estado inicial:** los CSV de Sara/Ellen están vacíos, por lo que `gold.csv` aún no existe. La creación de la muestra y la aprobación de pruebas automáticas no equivalen al etiquetado manual terminado.

## Exploración

`notebooks/exploracion.ipynb` visualiza conteos, longitud de reseñas y, cuando exista el conjunto gold, distribuciones de tema y polaridad. El generador no guarda una plataforma de origen por reseña; esa distribución se marca como *no disponible* y no se inventan plataformas.
