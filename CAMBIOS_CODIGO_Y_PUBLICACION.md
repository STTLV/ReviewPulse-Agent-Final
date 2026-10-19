# Correcciones de código y publicación de ReviewPulse-Agent

Base: ZIP `reviewpulse-agent-main.zip` aportado por el equipo. El proyecto se mantiene **independiente** del prototipo alternativo trabajado anteriormente.

## Archivos cambiados

| Archivo | Cambio | Razón |
|---|---|---|
| `reviewpulse/agente.py` | Cierre seguro de log + conexión SQLite en `finally` | Corregir `WinError 32` en carpetas temporales Windows y evitar fugas ante excepciones |
| `reviewpulse/memoria.py` | Método `cerrar()` que libera la conexión | Centralizar el cierre explícito |
| `requirements.txt` | Fijar `scikit-learn==1.9.1` | Evitar la carga cruzada del modelo serializado en 1.9.1 con scikit-learn 1.8.0 |
| `README.md` | URLs correctas, instrucciones y límites de los logs | Que el repositorio represente fielmente el ZIP y su despliegue |
| `tests/test_cierre_recursos.py` | Dos pruebas de regresión | Verificar liberación en éxito y error |
| `.github/workflows/comprobacion.yml` | Integración continua (GitHub Actions) | Detectar fallas de instalación, pruebas y escenarios E02/E11 en Python 3.13 |
| `.gitignore` | Excluir cachés de pruebas | Evitar archivos temporales en el repositorio |
| `CAMBIOS_CODIGO_Y_PUBLICACION.md` | Este manifiesto | Trazabilidad para el equipo y el evaluador |

## Sin cambios

- `datos/modelo.joblib` **no fue modificado** ni reentrenado.
- Reglas de detección, semillas y umbrales de `config/config.json` y `pruebas/umbrales.json` sin cambios.
- Los archivos históricos en `salidas/pruebas/` se conservan sin modificación.
- Los PDF, el Word y la bitácora existentes permanecen **sin editar**: su versión académica definitiva debe reemplazarse en una siguiente etapa.

## Cómo publicar de forma segura

El contenido de este ZIP es la **raíz** del repositorio `https://github.com/Ellen-01/reviewpulse-agent`.
Subir **los archivos y carpetas de la raíz**, no la carpeta envolvente `reviewpulse-agent-main` como subcarpeta nueva. La alternativa recomendada es actualizar el repositorio existente con Git y subir solo los archivos modificados.
No subir `.venv/`, `__pycache__/`, `.env`, secretos ni logs completos de `salidas/pruebas/corridas/` a menos que acuerden publicarlos; lo habitual es entregarlos aparte en un ZIP docente.

En GitHub web: entrar al repositorio, usar `Add file → Upload files`, cargar los archivos modificados (incluidas las rutas en subcarpetas) y confirmar el commit. Es más fiable usar Git desde una copia ya clonada para conservar la jerarquía.

Con Git, desde una **copia de trabajo de Ellen** y tras mantener una copia de seguridad: reemplazar los archivos modificados y ejecutar:

```powershell
git status --short
git add reviewpulse/agente.py reviewpulse/memoria.py requirements.txt README.md .gitignore .github/workflows/comprobacion.yml tests/test_cierre_recursos.py CAMBIOS_CODIGO_Y_PUBLICACION.md
git commit -m "Corregir cierre SQLite y fijar dependencias del modelo"
git push origin main
```

Antes del `push`, comprobar `git remote -v`: el destino debe ser `https://github.com/Ellen-01/reviewpulse-agent.git`, **no** el repositorio de nuestro prototipo previo.

## Verificación sugerida

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe ejecutar_agente.py --escenario E02 --semilla 11
.\.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py
```

**Nota:** esta actualización corrige el código y las instrucciones. No prueba recepción real de alertas por correo, no sustituye la batería de 60 escenarios ni corrige por sí sola las definiciones SMART del documento.

## Alcance de las verificaciones efectuadas antes del paquete

- Dos pruebas unitarias nuevas `tests/test_cierre_recursos.py`: **2/2 pasaron**.
- Compilación de Python: **OK**.
- Caso E02, semilla 11, ejecutado desde cero: **486 reseñas clasificadas, 21 descartadas, 14/14 reportes y una alerta a las 12 h simuladas**.
- Caso E11, semilla 11, ejecutado desde cero: **487 reseñas clasificadas, 20 descartadas, 14/14 reportes, dos reportes incompletos y una alerta tardía**.
- Estas pruebas se ejecutaron aquí con **scikit-learn 1.8.0**, que advierte incompatibilidad con el modelo guardado en 1.9.1. **No se pudo instalar 1.9.1 en este entorno desconectado**; la instalación exacta y el primer GitHub Actions deben validarse en la computadora del equipo o CI. Python del entorno de pruebas: 3.13.
- **No se repitió la batería completa de 60 corridas** y no se probó visualmente la interfaz alojada. No interpretar estas pruebas como nueva medición SMART.
