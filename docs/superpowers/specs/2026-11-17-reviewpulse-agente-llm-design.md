# ReviewPulse-Agent 2.0: agente LLM con herramientas (diseño)

Fecha: 2026-11-17 · Equipo: Sara Bastidas Triana, Ellen Nicole Ordoñez Chavez · Asesoría técnica externa: David (Ing. Software)
Estado: **corregido tras la revisión de arquitectura y con OmniRoute probado; pendiente de aprobación**. Nada se construye hasta que se apruebe.

---

## 1. Intención: el porqué

El profesor rechazó la versión actual como proyecto final. Pidió una **arquitectura agéntica**. Hoy el "agente" es un planificador STRIPS cuyas precondiciones forman una cadena lineal (`limpiar → clasificar → contar → comparar → decidir → reportar → registrar`). La búsqueda en anchura siempre devuelve la misma secuencia, así que funciona como un pipeline fijo. Además, la línea base es trivial.

El objetivo de la versión 2.0 es **que el proyecto se apruebe como Ruta E (agente con herramientas)** y que **cada integrante pueda explicar y modificar en vivo cualquier parte** en la sustentación, que vale 15 puntos con nota individual.

Usuario del sistema: el gerente de un hotel piloto. Le pregunta en lenguaje natural ("¿qué pasó con la limpieza esta semana?", "¿debo preocuparme por algo?", "arma el reporte de la semana 9"). El agente decide qué herramientas usar, las usa, verifica y responde con cifras y evidencia. Además, con cada cierre semanal corre una tarea autónoma: revisar y alertar si corresponde.

## 2. Metas, no-metas y anti-metas

**Metas**
1. Bucle agéntico propio (ReAct: razonar → usar herramienta → observar) sobre un LLM vía OmniRoute, con memoria, herramientas tipadas y registro de cada paso.
2. Se conserva el entorno actual: Hotel piloto ficticio y reseñas **100 % sintéticas**, declaradas como tales, con un conjunto de prueba etiquetado a mano por el equipo.
3. Comparación exigida por la Ruta E: **agente con herramientas vs. prompt único sin herramientas** en 26 tareas, 5 repeticiones, con métricas fijadas antes de correr.
4. Prototipo desplegado por completo en Railway (interfaz, API y agente), con chat del gerente, traza visible del agente y diseño responsive. Streamlit se retira.
5. Repositorio con la estructura de la guía (`src/ data/ notebooks/ experiments/ docs/`), README de ≤ 5 comandos, commits de las dos integrantes repartidos en las 3 semanas.

**No-metas**
- Multi-hotel, multi-agente, cuentas de usuario. La app pública se protege con un solo código de acceso (sección 11).
- Hotel real, reseñas reales o conexión a las API de TripAdvisor o Google. *(Decisión del equipo, 2026-11-17.)*
- Reentrenar el clasificador en línea.
- Envío real de correos. Se usa una bandeja de salida JSONL, como hoy.

**Anti-metas (si pasa algo de esto, fracasamos aunque "funcione")**
- Usar un framework (LangChain, LangGraph, CrewAI) que las integrantes no puedan explicar línea por línea.
- Que el LLM invente cifras: todo número de la respuesta tiene que salir de una herramienta.
- Que la llave de OmniRoute quede en el repositorio o en los logs.
- Cambiar métricas o umbrales después de ver resultados sin justificarlo por escrito.

## 3. Restricciones

- Python 3.13, la misma versión del CI y del modelo guardado. Corre en recursos gratuitos. El costo del LLM se mide en tokens y se reporta.
- LLM a través de **OmniRoute** (compatible con OpenAI): `https://omniroute-production-9e65.up.railway.app/v1`. La dirección, la llave y el modelo se leen del entorno, así que el profesor puede apuntar a otro proveedor compatible (p. ej. la API gratuita de Gemini) cambiando 3 variables.
- Modelo **fijo** para los experimentos, declarado en el informe junto con el prompt de sistema: agente y línea base con `cx/gpt-6-luna-medium`; juez con `gpt-5.6-luna-medium`. Ambos completaron 5 de 5 pruebas de llamada a herramientas el 2026-11-17. Las tres variantes de Gemini 3.8 Flash probadas no llamaron la herramienta, una prueba por variante, y se descartan.
- OmniRoute reporta unos 2.566 tokens de entrada en una petición mínima, porque el proveedor agrega contexto propio. Afecta por igual al agente y a la línea base, y el informe lo declara al reportar el costo.
- Despliegue en Railway. La sesión de la CLI está vencida y la renueva el usuario con `railway login`.
- Versiones fijadas en `requirements.txt` (consultadas el 2026-11-17): `scikit-learn==1.9.1`, `numpy==2.5.5`, `pandas==2.3.3`, `joblib==1.6.0`, `openai==3.54.0`, `fastapi==0.163.2`, `uvicorn==0.54.0`, `pydantic==2.14.3`, `python-dotenv==1.2.4`, `pyyaml==6.0.3`.
- Plazo: 3 semanas. Hito 3 = informe IEEE + repositorio + prototipo + bitácora (criterios 1 a 8, 85 pts).

## 4. Enfoques considerados

| Enfoque | Qué gana | Qué cuesta | Decisión |
|---|---|---|---|
| **1. Bucle propio con llamadas a herramientas (cliente `openai`)** | Todo el razonamiento queda a la vista y se puede modificar en vivo; sin dependencias pesadas; funciona con cualquier endpoint compatible | Reintentos y límites se escriben a mano (pocas líneas) | **Elegido por el equipo** |
| 2. LangGraph | "Suena" a arquitectura agéntica y dibuja el grafo solo | Dependencia pesada y cambiante; difícil de explicar en la sustentación | Descartado |
| 3. OpenAI Agents SDK | Liviano, trae trazas | Asume la API de OpenAI; con Gemini por el router puede fallar | Descartado |

## 5. Arquitectura

### 5.1 Vista general

```
                ┌───────── Interfaz web propia (web/, Railway) ─────────┐
 Gerente ─────▶ │ chat · panel semanal · traza paso a paso · resultados │
                └──────────────────────────┬────────────────────────────┘
                                           │ HTTP + eventos en vivo (SSE)
                ┌──────────────────────────▼────────────────────────────┐
                │        API FastAPI (src/reviewpulse/api, Railway)     │
                └──────────────────────────┬────────────────────────────┘
                                           │ tarea (texto) o evento de alarma / cierre
                                           │ (eventos: ciclo/ingesta.py y ciclo/cierre.py, cada 6 h, sin LLM)
                                           ▼
 ┌──────────────────────────────── AGENTE (src/reviewpulse/agente) ────────────────────────────────┐
 │  percibir()  ──▶  decidir()  ───────────────────────────▶  actuar()  ──▶  observar  ──┐        │
 │  (tarea +        (LLM elige: herramienta + argumentos,     (dispatcher valida y        │        │
 │   memoria)        o respuesta final)                         ejecuta la herramienta)   │        │
 │       ▲                                                                                │        │
 │       └──────────────────────────── hasta respuesta final o límite de pasos ◀─────────┘        │
 │  memoria: corto plazo (mensajes de la sesión) · largo plazo (SQLite) · registro JSONL          │
 └───────────┬─────────────────────────────────────────────┬───────────────────────────────────────┘
             │ ÚNICA frontera con el proveedor              │ llamadas tipadas
             ▼                                              ▼
   llm/cliente.py ──▶ OmniRoute (/v1)            herramientas/ (funciones Python puras o con E/S)
   llm/falso.py (pruebas y modo demo)            buscar · clasificar · comparar · reportar · alertar
                                                            │
                                                            ▼
                                             datos/ (SQLite + simulador del Hotel piloto)
```

### 5.2 Ciclo del agente (lo que se explica en la sustentación)

```python
def resolver(tarea: str) -> Resultado:
    mensajes = memoria.contexto(tarea)                 # PERCEPCIÓN
    for paso in range(cfg.max_pasos):
        r = llm.chat(mensajes, herramientas=catalogo)  # DECISIÓN (el LLM razona)
        if r.respuesta_final:
            return verificar_y_cerrar(r, mensajes)     # ACCIÓN final: revisa cifras y responde
        for llamada in r.llamadas:
            obs = herramientas.ejecutar(llamada)       # ACCIÓN: usar herramienta
            mensajes.append(obs)                       # OBSERVACIÓN → nueva percepción
            registro.paso(paso, llamada, obs, r.uso)   # log con tokens y tiempo
    return Resultado.fallo("limite_de_pasos")
```

`verificar_y_cerrar` extrae los números de la respuesta y comprueba que aparezcan en las observaciones de la sesión. Si alguno no aparece, le pide al modelo una sola corrección; si persiste, la respuesta sale marcada como «cifra sin respaldo» y se cuenta en la métrica de trazabilidad.

Cada vuelta del bucle es una iteración de percepción → decisión → acción, como pide la guía. A diferencia del STRIPS actual, **la secuencia de herramientas depende de la pregunta y de lo que devuelve cada herramienta**.

### 5.3 Mapeo a los 7 componentes IBM y a Russell & Norvig

| Componente IBM | Dónde vive | Nota |
|---|---|---|
| Percepción | `ciclo/ingesta.py`, `agente/bucle.py`, `entorno.py` | Reseñas de las plataformas, tarea del gerente, eventos de alarma y cierre, observaciones de herramientas |
| Planificación y descomposición | El LLM con `agente/prompts.py` (ReAct) | El plan surge en cada paso; se registra el razonamiento corto que el modelo declara |
| Memoria | `agente/contexto.py` + `memoria.py` | Corto plazo: mensajes. Largo plazo: SQLite con reseñas, semanas, alertas y reportes |
| Razonamiento y decisión | LLM + herramienta `comparar_semana` | El LLM decide *qué* revisar; el CUSUM diario decide *si* hay anomalía (sección 8.1) |
| Llamada a herramientas | `herramientas/registro.py` | Catálogo tipado, validación de argumentos, errores devueltos como datos |
| Comunicación | Respuesta final + `herramientas/reportes.py` + UI | Toda cifra lleva su fuente (herramienta y argumentos) |
| Aprendizaje y adaptación | Fuera de alcance en línea | Se documenta como trabajo futuro: correcciones del gerente → nuevo set de entrenamiento |

Tipo de agente (R&N): **basado en metas con modelo interno**. Mantiene estado en la memoria y elige acciones según la meta de la tarea. Se documenta por qué no es de utilidad ni de aprendizaje.

## 6. Estructura de carpetas

Se evoluciona el **mismo repositorio** (`STTLV/ReviewPulse-Agent-Final`) para conservar el historial; la guía permite continuidad si el alcance crece. La versión 1 queda en la rama `v1-streamlit` y en la etiqueta `v1-hito2`. No hay carpeta `legacy/`: dos paquetes llamados `reviewpulse` chocarían al importarse.

```
ReviewPulse-Agent-Final/
├── README.md                    # qué es, ≤5 comandos, variables de entorno
├── requirements.txt             # versiones fijadas
├── .env.example                 # LLM_*, APP_CODIGO_ACCESO, LLM_TOPE_TOKENS_DIA
├── Dockerfile · railway.toml    # despliegue
├── src/reviewpulse/
│   ├── config.py                # lee el entorno; nunca imprime la llave
│   ├── modelo.py · lexico.py    # se mueven sin renombrar: modelo.joblib depende de estas rutas
│   ├── preprocesamiento.py      # validación actual + enmascarar_nombres()
│   ├── corpus.py · entorno.py · escenarios.py   # simulador actual
│   ├── memoria.py               # SQLite actual
│   ├── actuadores.py            # Notificador y GeneradorReporte actuales
│   ├── evaluacion.py            # medidas M1–M4 actuales
│   ├── ciclo/
│   │   ├── ingesta.py           # cada 6 h: consulta, limpia, clasifica, guarda, evalúa CUSUM
│   │   └── cierre.py            # cierra la semana, avisa al agente y garantiza el reporte
│   ├── llm/
│   │   ├── cliente.py           # ÚNICA frontera con el proveedor: reintentos, timeout, uso de tokens
│   │   └── falso.py             # LLM de guion: pruebas, CI, M2–M4 y modo demo sin red
│   ├── agente/                  # reemplaza a agente.py y planificador.py de la versión 1
│   │   ├── bucle.py             # resolver(tarea): el ciclo ReAct
│   │   ├── prompts.py           # prompt de sistema versionado (v1, v2…)
│   │   ├── contexto.py          # memoria de corto plazo de la sesión
│   │   └── traza.py             # log JSONL: percepción/decisión/acción + tokens + costo
│   ├── herramientas/
│   │   ├── registro.py          # @herramienta: nombre, descripción, esquema Pydantic, dispatcher
│   │   ├── resenas.py           # contar_resenas, buscar_resenas, clasificar_resena
│   │   ├── estadistica.py       # cusum_diario y regla semanal v1 (funciones puras)
│   │   ├── analisis.py          # comparar_semana
│   │   ├── reportes.py          # generar_reporte
│   │   ├── alertas.py           # emitir_alerta
│   │   └── plataformas.py       # estado_plataformas
│   └── api/
│       ├── main.py              # FastAPI: sirve web/ y monta las rutas
│       └── rutas.py             # chat (SSE), semanas, cierre, resultados, salud
├── web/                         # interfaz sin paso de compilación
│   └── index.html · estilos.css · app.js
├── data/
│   ├── README.md                # cómo se generan los datos sintéticos y sus límites
│   ├── modelo.joblib            # modelo actual, movido desde datos/
│   ├── evaluacion_manual*.csv   # conjuntos C02 y C03 actuales
│   └── gold/                    # etiquetas manuales del equipo
├── experiments/
│   ├── preparar.py              # crea la base fija de evaluación (E03, semilla 11)
│   ├── tareas.yaml              # 26 tareas con respuesta esperada y forma de verificar
│   ├── verdad.py                # calcula las respuestas esperadas
│   ├── umbrales.json            # métricas y umbrales, fechados ANTES de correr
│   ├── correr.py                # agente vs línea base, 5 repeticiones
│   ├── medir_m1_m4.py           # 60 corridas: regla semanal v1 vs CUSUM
│   ├── calibrar_cusum.py        # calibración solo con semillas 101–105
│   ├── juez.py                  # LLM-juez para respuestas en texto libre
│   ├── v1/                      # resultados históricos de salidas/pruebas
│   └── resultados/              # CSV + JSONL por corrida, con semilla y modelo
├── notebooks/exploracion.ipynb  # estadísticas descriptivas del corpus sintético
├── tests/                       # unittest con LLM falso: sin red, sin costo
└── docs/
    ├── arquitectura.md · adr/   # decisiones (ADR-001 bucle propio, ADR-002 OmniRoute, ADR-003 CUSUM)
    ├── bitacora_ia.md
    └── superpowers/specs/       # este documento
```

### 6.1 Migración, convivencia y reversa

La versión 1 sigue funcionando hasta que la 2.0 esté verificada en Railway.

| Paso | Acción | Listo cuando | Reversa |
|---|---|---|---|
| 1 | Crear la rama `v2` desde `main` y mover código con `git mv` | CI de `v2` en verde | Borrar la rama |
| 2 | Construir por tareas, con un PR por tarea hacia `v2` | Paridad P1–P3 en verde | Revertir el PR |
| 3 | Desplegar `v2` en Railway | `GET /api/salud` responde 200 y el chat resuelve una tarea | Volver al despliegue anterior en Railway |
| 4 | Crear `v1-streamlit` y la etiqueta `v1-hito2` desde `main`; apuntar Streamlit Cloud a esa rama | El enlace del Hito 2 sigue abriendo | Apuntar de nuevo a `main` |
| 5 | Unir `v2` en `main` | CI de `main` en verde | `git revert -m 1` del merge |
| 6 | Apagar Streamlit Cloud | Hito 3 calificado | Reactivar la app desde `v1-streamlit` |

**Paridad que debe mantenerse:**
- **P1:** en el conjunto de control, línea base 16/40 y 10/40; modelo 32/40 y 34/40.
- **P2:** E02 con semilla 11 clasifica 486 reseñas, descarta 21 y entrega 14 reportes a tiempo.
- **P3:** E11 con semilla 11 clasifica 487, descarta 20 y entrega 14 reportes, 2 de ellos incompletos.

Las alertas cambian a propósito, porque cambia la regla de detección.

## 7. Patrones de diseño (con su porqué)

Varios se toman de `vocero-crm` (`src/lib/ai/index.ts`, `provider.ts`, `server/dev/ai-mock.ts`, `server/ai/prompts.ts`) y se traducen a Python.

| Patrón | Dónde | Porqué | En vocero-crm |
|---|---|---|---|
| **Frontera única con el proveedor** (adaptador) | `llm/cliente.py` | Un solo lugar habla con el LLM: cambiar de modelo o proveedor no toca el agente | `lib/ai/index.ts`: "ÚNICA frontera con el proveedor" |
| **Configuración por entorno** | `config.py` | Reproducible en otra máquina; la llave nunca va en el código | `provider.ts`: `OPENROUTER_BASE_URL/MODEL/TOKEN` |
| **Resultado tipado en vez de excepción** | cliente y herramientas | Un fallo del proveedor o de una herramienta no tumba al agente: el LLM recibe el error como observación y puede recuperarse. Así se cuentan los errores de herramienta (métrica de la Ruta E) | `ChatJsonResult` con `ok:false, error` |
| **Validación de salida + reintento** | dispatcher de herramientas | Los argumentos del LLM se validan con Pydantic; si no cumplen, se devuelve el error al modelo | `extractJson` + Zod + `MAX_ATTEMPTS` |
| **Registro de herramientas** (comando) | `herramientas/registro.py` | Cada herramienta = nombre + descripción + esquema + función. El catálogo para el LLM se genera solo | contrato del despacho |
| **Doble de prueba (LLM falso)** (estrategia) | `llm/falso.py` | Pruebas y CI sin red ni costo; modo demo si Railway u OmniRoute fallan en la sustentación | `server/dev/ai-mock.ts` |
| **LLM como juez** | `experiments/juez.py` | Evaluar respuestas en texto libre con rúbrica y salida JSON; el modelo juez es distinto del agente | `buildJudgePrompt` del Laboratorio |
| **Prompts en módulo propio y versionados** | `agente/prompts.py` | La modificación en vivo de la sustentación es cambiar una línea aquí y predecir el efecto | `server/ai/prompts.ts` |
| **Funciones puras para las decisiones** | `herramientas/estadistica.py` | Se prueban sin LLM ni base de datos | `interpretarCredencial`, `resolver` |
| **Límites de seguridad** | `bucle.py` | `max_pasos`, `max_tokens` por tarea, timeout: el agente no gira sin fin ni gasta sin tope | — |

## 8. Catálogo de herramientas (primera versión)

| Herramienta | Entrada (Pydantic) | Salida | Reutiliza |
|---|---|---|---|
| `contar_resenas` | semana?, tema?, polaridad?, plataforma? | `{total, por_tema, por_polaridad}` | `RepositorioHistorico` |
| `buscar_resenas` | filtros + `texto_contiene?` + `limite≤10` | lista `{id, fecha, texto, polaridad, tema, confianza}`, con nombres de personas enmascarados | `RepositorioHistorico` |
| `clasificar_resena` | `texto` | `{polaridad, tema, confianza, revision_manual}` | `ClasificadorSentimiento` + `validar()` |
| `comparar_semana` | `semana`, `tema?` | por tema: proporción, promedio de 6 semanas, `S_max`, `h`, día de alarma, `alarma: bool` | `estadistica.cusum_diario` |
| `generar_reporte` | `semana` | ruta + resumen JSON | `GeneradorReporte` |
| `emitir_alerta` | `semana`, `tema`, `justificacion` | registro en bandeja JSONL | `Notificador` |
| `estado_plataformas` | — | disponibilidad y último dato recibido | `entorno.py` |

Regla del prompt de sistema: **ninguna cifra sin herramienta**, y antes de `emitir_alerta` es obligatorio un `comparar_semana` con `alarma: true` para ese tema. El código lo hace cumplir: `emitir_alerta` rechaza la llamada si no hay comparación positiva en la sesión. Es una barrera programada, no una confianza en el prompt.

El texto de las reseñas llega al modelo delimitado y marcado como dato. Una instrucción escrita dentro de una reseña no se obedece, y las barreras del código aplican aunque el modelo se confunda.

### 8.1 Detección de cambios: CUSUM diario

Reemplaza a la regla semanal, que no pasa de 66,7 % de detección ni con clasificador perfecto. Es lo que el Hito 2 anunció como siguiente paso.

Para cada tema y cada día `d`, con `n_d` reseñas y `neg_d` negativas (las de baja confianza pesan 0,5, como hoy):

```
p0 = (negativas + 1) / (total + 4)     # últimas 6 semanas cerradas, sin alertas
p1 = min(0.95, p0 + delta)
W_d = neg_d · ln(p1 / p0) + (n_d − neg_d) · ln((1 − p1) / (1 − p0))
S_d = max(0, S_(d−1) + W_d)            # alarma si S_d ≥ h y hay ≥ min_negativas en la semana
```

- `S` se reinicia cada lunes y después de cada alarma. Se exigen al menos 3 semanas de historial.
- `delta`, `h` y `min_negativas` se calibran **solo con las semillas 101 a 105**, y se fijan antes de usar las semillas de prueba.
- La alarma puede ocurrir a mitad de semana, y `ciclo/ingesta.py` le avisa al agente en ese momento.

### 8.2 Ingesta y cierre (sin LLM)

El trabajo repetitivo no depende del modelo:

- **`ciclo/ingesta.py`**, cada 6 horas simuladas: consulta plataformas, limpia, clasifica, guarda en SQLite, atiende reseñas tardías y evalúa el CUSUM.
- **`ciclo/cierre.py`**: aplica las reglas actuales (margen de 12 h y plazo de 24 h), cierra la semana y lanza la tarea autónoma del agente. Si el LLM falla, genera el reporte determinista y lo marca «sin análisis del agente», de modo que un fallo del proveedor no incumple M3.

## 9. Datos

**Decisión del equipo (2026-11-17): las reseñas siguen siendo 100 % sintéticas y el hotel sigue siendo ficticio.**

1. **Fuente:** `corpus.py` y el simulador `EntornoHotel` actuales, con sus 12 escenarios y semillas fijas. Son datos propios, sin datos personales y sin problemas de licencia. `data/README.md` documenta cómo se generan, su tamaño y sus límites.
2. **Etiquetado propio.** Sara y Ellen etiquetan a mano, sin ver la etiqueta del simulador, polaridad y tema de ~300 reseñas de prueba. Un 10 % lo etiquetan ambas para medir el acuerdo (kappa de Cohen).
3. **Partición fija con semilla:** entrenamiento, validación y prueba, sin compartir frases entre ellas. La prueba solo se usa al final.
4. **Limitación declarada.** El informe dice de forma explícita que ningún resultado demuestra desempeño con reseñas reales, y que el lenguaje simulado es más ordenado que el real. El Hito 2 anunció reseñas reales como siguiente paso, así que el informe justifica por escrito este cambio de alcance.

**Riesgo aceptado:** el criterio 2 de la rúbrica (Datos, 10 pts) pide fuente, licencia y partición justificadas. Con datos sintéticos, la nota depende de qué tan bien se documenten y justifiquen.

## 10. Evaluación: se fija ANTES de correr

### 10.1 Agente vs. línea base (Ruta E)

**Base fija:** `experiments/preparar.py` crea una sola base con el escenario E03 y la semilla 11 (incidentes declarados: servicio en la semana 8 y precio en la semana 11), más reseñas añadidas para las tareas trampa.

**Línea base:** mismo modelo y una sola llamada, sin herramientas. Recibe **todas** las reseñas de la base con id, fecha, plataforma, texto, polaridad y tema (unos 32.000 tokens, caben completas). No se debilita a propósito. En las tareas de acción, tiene éxito si su texto indica la decisión correcta; como no tiene actuadores, la ejecución real se reporta aparte.

**Tareas (`experiments/tareas.yaml`, 26):**

| Tipo | Ejemplo | Verificación |
|---|---|---|
| Conteo (6) | "¿Cuántas reseñas negativas de servicio hubo en la semana 8?" | Automática: número exacto contra SQL |
| Comparación (4) | "¿El servicio empeoró en la semana 8 frente a las 6 anteriores?" | Automática: cifras contra SQL y conclusión contra el incidente declarado |
| Evidencia (4) | "Dame 2 quejas sobre ruido" | Automática: los IDs existen y cumplen el filtro |
| Clasificación (4) | "Clasifica: 'el cuarto bien pero cobran todo aparte'" | Automática contra la etiqueta manual del equipo |
| Decisión de alerta (3) | Evento "cierre semana 8", "semana 11" y "semana 5" | Automática: decisión y tema contra el incidente declarado |
| Reporte (1) | "Arma el reporte de la semana 11" | Juez LLM + revisión humana |
| Trampa (4) | Semana 40 inexistente · plataforma caída · 2 reseñas con instrucciones inyectadas | Automática: reconoce la falta de datos o no obedece la inyección |

**Métricas y umbrales** (se guardan en `experiments/umbrales.json` con fecha, antes de la primera corrida completa):

| Métrica | Fórmula | Umbral |
|---|---|---|
| Tasa de éxito | tareas resueltas / tareas | Agente ≥ 80 % |
| Superioridad | diferencia de éxito agente − línea base, con IC 95 % por bootstrap pareado por tarea (10.000 remuestreos, semilla fija) | El intervalo no incluye 0 |
| Cifras incorrectas | respuestas con al menos una cifra distinta de la verdad en SQL / respuestas con cifras | Agente ≤ 5 %; se reporta para ambos |
| Trazabilidad | cifras presentes en observaciones de herramientas / cifras de la respuesta | Agente ≥ 95 % |
| Errores de herramienta | llamadas inválidas o fallidas / llamadas | ≤ 10 % |
| Pasos y costo | herramientas por tarea; tokens → USD según tarifa pública | Se reportan; ≤ US$1 por corrida completa |

5 repeticiones por tarea y sistema (260 ejecuciones). Se reporta media ± desviación estándar y se guarda cada traza JSONL. Si el agente no supera a la línea base, se reporta así y se analiza la causa.

### 10.2 Medidas M1–M4: no cambian

Las fórmulas y umbrales fijados el 15/10/2026 se conservan. Cambia la técnica, no la vara de medir.

| Medida | Umbral | Cómo se mide en 2.0 |
|---|---|---|
| M1 Exactitud | ≥ 85 % en polaridad y tema | Conjunto C03, 5 reentrenamientos, más macro-F1 sobre la prueba manual: TF-IDF+LR vs. LLM sin ajuste |
| M2 Detección ≤ 24 h | ≥ 90 % | 12 escenarios × 5 semillas: regla semanal v1 vs. CUSUM |
| M3 Reportes a tiempo | 100 % | Las mismas 60 corridas |
| M4 Falsos positivos | < 10 % | Las mismas 60 corridas |

M2–M4 corren con `llm/falso.py` (guion fijo sobre las herramientas reales), así que no consumen tokens. Si M1 o M2 siguen sin cumplirse, se reportan como incumplidas, con su análisis.

### 10.3 Análisis de errores e IA responsable

**Análisis de errores:** ≥ 10 fallos tomados de las trazas, clasificados (herramienta equivocada, argumentos inválidos, cifra inventada, se rindió antes de tiempo, error del clasificador, ambigüedad de la tarea), cada uno con una hipótesis de causa.

**IA responsable, medida:** métricas por subgrupo (plataforma, longitud, tema, con o sin errores de tipeo); enmascarado de nombres para evitar culpar a empleados; resistencia a inyección de instrucciones; privacidad (sin datos personales en logs); costo y dependencia del proveedor.

## 11. Interfaz y despliegue

**Todo corre en Railway, en un solo servicio.** Streamlit se retira. FastAPI (Python, como exige la guía) sirve la API y la interfaz web. Un solo `Dockerfile`, un solo despliegue y sin Node.

- **Vistas:** *Chat del gerente* (respuesta + "ver cómo lo resolvió" con la traza paso a paso, en vivo por SSE), *Panel semanal*, *Ejecutar cierre de semana* (tarea autónoma) y *Resultados de la evaluación* (tablas de `experiments/resultados`).
- **API:** `POST /api/chat` (SSE), `GET /api/semanas`, `POST /api/cierre`, `GET /api/resultados`, `GET /api/salud`.
- **Railway:** `Dockerfile` + `railway.toml`, variables `LLM_*` como secretos del servicio, health check en `/api/salud`, puerto desde `$PORT`.
- **Protección de la llave:** `APP_CODIGO_ACCESO` para usar el chat y `LLM_TOPE_TOKENS_DIA` como límite diario. Al llegar al tope, la app pasa a modo demo y lo dice.
- **Estado:** al arrancar, el servicio regenera la base del Hotel piloto con escenario y semilla fijos, así que no necesita volumen persistente. Un botón reinicia la demo.
- **Sin llave:** con el LLM falso, la app y las pruebas corren en otro equipo sin credenciales, para que el profesor pueda ejecutar el repositorio.
- **Modo demo:** si el LLM no responde, la app lo dice y ofrece reproducir una traza grabada. Nunca falla en silencio.

**Criterio de UX/UI (permanente):** toda pantalla se diseña y revisa con Impeccable, en modo *Operate* (escaneable, consistente, precisa), y es **responsive** desde el teléfono hasta el escritorio.

**Identidad visual: se conserva la de Sara** (`app/streamlit_app.py` de la versión 1):

| Token | Valor | Uso |
|---|---|---|
| `--crema` / `--papel` | `#FBF6EE` / `#FFFDF9` | Fondo / superficies |
| `--tinta` / `--tinta2` | `#2A2230` / `#75697B` | Texto / texto secundario |
| `--linea` | `#E8DCCF` | Bordes |
| `--rosa` / `--rosa2` | `#F7CFD8` / `#FCE9ED` | Acento suave |
| `--amarillo` / `--amarillo2` | `#FBE6A2` / `#FDF3CE` | Marca y avisos |
| `--coral` | `#DB6B5E` | Alertas y negativas (solo rellenos: sobre blanco da 3,3:1; el texto de alerta usa `#8A382F`) |
| Polaridad | `#4F9A72` · `#B79F7A` · `#DB6B5E` | Positiva · neutra · negativa |
| Temas | `#3F8FAE` · `#D4577F` · `#5FA67F` · `#D9A21B` | Limpieza · servicio · ubicación · precio |
| Tipografía | Bricolage Grotesque + Plus Jakarta Sans | Títulos + texto |

## 12. Cronograma y reparto (18 nov – 8 dic de 2026)

| Semana | Sara | Ellen | Las dos |
|---|---|---|---|
| **1** (18–24 nov) | Mover código a `src/`, paridad P1–P3, `data/README.md`, partición fija, `ciclo/ingesta.py` y `ciclo/cierre.py` | `config.py`, `llm/cliente.py`, `llm/falso.py`, registro de herramientas y 7 herramientas | Etiquetado manual; `agente/bucle.py` en pareja |
| **2** (25 nov – 1 dic) | CUSUM y calibración, `tareas.yaml`, `verdad.py`, `umbrales.json` fechado, `correr.py`, `juez.py` | API FastAPI, interfaz web responsive, Dockerfile y despliegue en Railway | Primera corrida completa y revisión de trazas |
| **3** (2–8 dic) | Análisis de errores, resultados y métodos del informe | IA responsable, trabajo relacionado, fuente de relevancia del problema, README | Informe IEEE 6–8 págs., bitácora, contribuciones, reflexión sobre IA, `hito3.pdf`, `hito4` (PPT), 2 ensayos cruzados con modificación en vivo |

### 12.1 Cómo se trabaja en el repositorio

1. Sara da acceso de escritura a Ellen en GitHub. Cada una trabaja con su cuenta y en su equipo.
2. Cada tarea va en su propia rama (`sara/ingesta`, `ellen/cliente-llm`) y entra a `v2` por un PR que la otra revisa.
3. **Cada commit lo hace quien realizó ese trabajo, el día en que lo realizó.** No se alteran fechas ni autores.
4. Antes de cada commit, la autora ejecuta la verificación de la tarea y debe poder explicar el cambio sin ayuda.
5. Cada tarea deja una fila en `docs/bitacora_ia.md`: fecha, integrante, herramienta, uso, qué se aceptó o cambió y cómo se verificó. El apoyo de David como asesor y el de Claude se declaran en la bitácora y en las contribuciones del informe.

## 13. Decisiones técnicas (revisables)

- **Respuesta esperada de las tareas:** conteos y cifras se calculan sobre la misma base que ve el agente, para medir el uso de herramientas sin mezclar los errores del clasificador. Las conclusiones y alertas se verifican contra el incidente declarado por el simulador, y las clasificaciones contra la etiqueta manual del equipo.
- **Línea base:** recibe todas las reseñas de la base, sin truncar.
- **Costo:** se reportan tokens reales por corrida; el valor en USD se calcula con la tarifa pública del modelo elegido, citando la fuente y la fecha.
- **Mismo repositorio**, con la versión 1 conservada en `v1-streamlit` y `v1-hito2`.
- **Juez:** modelo distinto al del agente; un 20 % de sus veredictos se revisa a mano y se reporta el acuerdo.
- **CUSUM diario:** técnica estadística propuesta para detectar cambios en la proporción de reseñas negativas. Su implementación y parámetros se evaluarán experimentalmente y se compararán con la regla semanal de la versión anterior.


## 14. Lo que queda a criterio del constructor

- Nombres finales de funciones y campos, siempre que respeten las responsabilidades de la sección 6.
- Formato exacto de `tareas.yaml` y del log JSONL.
- Si `config.py` usa `os.environ` + `python-dotenv` o `pydantic-settings` (preferible lo más simple).
- Diseño visual de la app.

## 15. Preguntas abiertas

Ninguna. El modelo y el soporte de llamadas a herramientas quedaron confirmados el 2026-11-17.

## 16. Referencias para el informe (≥ 5, ≥ 3 artículos)

- Russell, S., & Norvig, P. (2021). *Artificial Intelligence: A Modern Approach* (4.ª ed.), caps. 2, 11 y 18.
- Yao, S. et al. (2023). *ReAct: Synergizing Reasoning and Acting in Language Models*. ICLR. (bucle del agente)
- Schick, T. et al. (2023). *Toolformer: Language Models Can Teach Themselves to Use Tools*. NeurIPS. (uso de herramientas)
- Zheng, L. et al. (2023). *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*. NeurIPS. (juez)
- Reynolds, M. R., & Stoumbos, Z. G. (1999). *A CUSUM Chart for Monitoring a Proportion When Inspecting Continuously*. Journal of Quality Technology. (detección)
- Vásquez, J. et al. (2021). *BERT-based approach for sentiment analysis of Spanish reviews from TripAdvisor*. IberLEF. (dominio)
- IBM. *Components of AI agents*. (marco de 7 componentes)

*(Hay que verificar cada cita contra la fuente antes de ponerla en el informe.)*
