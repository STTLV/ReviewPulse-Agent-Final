# Datos del proyecto ReviewPulse 2.0

## Origen y límites

Las reseñas del proyecto son **sintéticas**, generadas a partir de plantillas de `reviewpulse.corpus`. No se recolectaron reseñas reales ni se dispone de evidencia para extrapolar los resultados a hoteles reales. Hay cuatro temas (`limpieza`, `servicio`, `ubicacion`, `precio`) y tres polaridades (`positiva`, `negativa`, `neutra`). El generador puede introducir ironía, errores tipográficos y referencias secundarias a otros temas. Esto permite experimentar de forma reproducible, pero no equivale a medir desempeño sobre conversaciones humanas auténticas.

## Partición y prevención de fuga

- **Entrenamiento:** corpus sintético del clasificador, semilla `7`, con `conjunto="entrenamiento"`.
- **Validación:** escenario `C02`, utilizado para controlar el comportamiento sin usar el conjunto final de prueba.
- **Prueba:** escenario `C03` y el conjunto **gold** de 120 reseñas generado con `construir_corpus(120, semilla=2026, conjunto="evaluacion", prob_ironia=0.10)`.
- Las frases de evaluación proceden del subconjunto reservado por `corpus._particion`; no se incorporan al entrenamiento ni se optimizan parámetros contra gold. Algunos cierres y las estructuras del generador son compartidos, por lo que la independencia no es absoluta.

## Muestra ciega y etiquetado humano

`data/gold/muestra.csv` contiene exclusivamente las columnas `id,texto`. Los primeros 30 IDs son comunes a ambas personas. Sara etiquetó los IDs 1–75 (30+45); Ellen etiquetó los IDs 1–30 y 76–120 (30+45). Las plantillas usan las columnas `id,texto,polaridad,tema`. Las etiquetas deben rellenarlas las integrantes **manualmente, sin IA y sin consultar la verdad del simulador**. Las plantillas se entregaron inicialmente vacías. Las etiquetas fueron aportadas manualmente por Sara y Ellen; no se asignaron etiquetas del simulador a ninguna evaluadora.

Categorías permitidas: polaridad `positiva`, `negativa`, `neutra`; tema `limpieza`, `servicio`, `ubicacion`, `precio`. Al editar los CSV se deben conservar las columnas, los IDs y los textos originales (incluidos tildes y signos).

`experiments/preparar_gold.py` prepara los archivos de manera determinista y deja la verdad del simulador en una carpeta privada **fuera del repositorio** (`~/.reviewpulse/verdad_simulador_2026.csv`). No debe abrirse hasta concluir el etiquetado. Nunca añadir este archivo privado a Git.

`experiments/acuerdo.py` calcula **kappa de Cohen de polaridad y tema sobre los 30 comunes**. Si hay discrepancias crea `data/gold/acuerdos_resueltos.csv`: las integrantes deben acordar las respuestas y justificar cada diferencia. Solo entonces construye `data/gold/gold.csv` (`id,texto,polaridad,tema`), sin usar las etiquetas del simulador.

Comandos desde la raíz del repositorio:

```powershell
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe experiments/preparar_gold.py
.\.venv\Scripts\python.exe -m unittest tests.test_datos -v
# Después de completar las 2 plantillas a mano:
.\.venv\Scripts\python.exe experiments/acuerdo.py
```

**Estado actual:** 75 reseñas etiquetadas por Sara y 75 por Ellen, de las cuales 30 son comunes; la unión contiene 120 reseñas únicas. El acuerdo humano fue del 100 % en las 30 comunes (kappa de Cohen 1,0000 para polaridad y tema). `gold.csv` se construyó exclusivamente desde estas etiquetas humanas y la muestra ciega, sin consultar la verdad del simulador.

**Trazabilidad:** fuentes `ReviewPulse_Sara_Etiquetado_Gris.xlsx` y `ReviewPulse_Ellen_Etiquetado_Gris (1).xlsx`. La consolidación verificó IDs, texto íntegro, categorías válidas y acuerdos comunes. El desempeño en un corpus sintético no permite inferir el rendimiento en reseñas auténticas.

## Criterios manuales de anotacion y limitaciones de concordancia

**Procedimiento declarado por las integrantes.** Las 120 resenas sinteticas distintas se distribuyeron en dos plantillas: cada integrante etiqueto 75 textos (30 comunes y 45 exclusivos). Las asignaciones humanas suman 150 porque las 30 resenas compartidas fueron anotadas dos veces. Las categorias validas del esquema son `positiva`, `negativa`, `neutra` para polaridad y `limpieza`, `servicio`, `ubicacion`, `precio` para tema.

- **Sara:** leyo individualmente las resenas y asigno la polaridad segun el comentario. Si aparecian varios temas, eligio el primero mencionado en el texto, por ejemplo, `precio` antes que `ubicacion`.
- **Ellen:** indico que leyo individualmente cada resena, determino la polaridad por el sentimiento general predominante y selecciono la tematica principal segun la relevancia o el enfasis del comentario. Ante varios temas, priorizo el mas destacado, no necesariamente el primero mencionado.

**Concordancia:** en las 30 resenas compartidas se registraron cero desacuerdos tanto para polaridad como para tema, con kappa de Cohen = 1,0000 en ambas variables. Esta medida compara las **dos anotaciones humanas** sobre las 30 compartidas; no debe confundirse con la comparacion externa frente al generador.

**Revision de la procedencia:** en la revision del 22/11/2026, David informo que las 150 asignaciones humanas coinciden con las categorias asociadas a las resenas del simulador. Esta coincidencia es distinta del kappa entre anotadoras. Segun la descripcion del proceso, las etiquetas se asignaron leyendo el texto, no copiando la verdad del generador. La claridad y repetitividad de las plantillas sinteticas y la proximidad entre los criterios humanos y la estructura del generador pueden explicar la concordancia perfecta, pero tambien limitan el valor de esta evidencia para estimar desempeno en resenas reales.

**Limitaciones:** los datos son sinteticos, con patrones y vocabulario estructurados. Los criterios de seleccion de un solo tema en resenas multitematicas no fueron identicos entre las dos anotadoras. La ausencia de desacuerdos en esta muestra no demuestra que la tarea carezca de ambiguedad en datos autenticos; tampoco implica generalizacion a hoteles reales. El conjunto Gold se conserva tal como fue consolidado; no se modifican las etiquetas para alterar las tasas de coincidencia.

**Plantillas de trabajo:** Sara informo que ChatGPT ayudo a preparar dos archivos Excel con `id` y `texto` precargados y las columnas para `polaridad` y `tema` sin completar, para el posterior etiquetado manual. El 24/11/2026 se revisaron los dos Excel originales aportados: cada uno incluye 75 textos con identificador unico, las 30 resenas compartidas tienen el mismo texto, y las columnas `polaridad_manual` y `tema_manual` estaban vacias en ambos archivos (150 filas en conjunto). Sara y Ellen confirmaron que etiquetaron individualmente, sin usar IA y sin consultar etiquetas de la otra integrante ni respuestas del simulador. Las dos plantillas vacias quedan como evidencia para la revision de David.

## Exploración

`notebooks/exploracion.ipynb` visualiza conteos, longitud de reseñas y, cuando exista el conjunto gold, distribuciones de tema y polaridad. El generador no guarda una plataforma de origen por reseña; esa distribución se marca como *no disponible* y no se inventan plataformas.
