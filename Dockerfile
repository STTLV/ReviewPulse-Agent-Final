# Python 3.13 es la versión indicada por CI y por el proyecto.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    REVIEWPULSE_DB_PATH=/var/lib/reviewpulse/demo.sqlite3 \
    REVIEWPULSE_HISTORICO_DB_PATH=/var/lib/reviewpulse/historico.sqlite3

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

RUN groupadd --system reviewpulse \
    && useradd --system --gid reviewpulse --home-dir /nonexistent \
        --shell /usr/sbin/nologin reviewpulse \
    && mkdir -p /var/lib/reviewpulse \
    && chown reviewpulse:reviewpulse /var/lib/reviewpulse \
    && chmod 700 /var/lib/reviewpulse

COPY src ./src
COPY config/config.json ./config/config.json
COPY data/ ./data/

USER reviewpulse

EXPOSE 8000

# La factoría es necesaria: main.py no exporta una variable global `app`.
# Un único worker protege el candado que coordina las solicitudes del proceso.
CMD ["/bin/sh", "-c", "exec uvicorn --factory reviewpulse.api.main:crear_app_desde_entorno --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1"]
