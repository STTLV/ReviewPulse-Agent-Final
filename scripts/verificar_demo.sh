#!/usr/bin/env sh
# Verifica localmente el contenedor de demo de ReviewPulse. No usa proveedor LLM.
set -eu

PORT=${PORT:-8000}
IMAGE="reviewpulse-demo-verify:local-$$"
CONTAINER="reviewpulse-demo-verify-$$"
ACCESS_CODE="demo-local-$$-$(date +%s)"
BASE_URL="http://127.0.0.1:${PORT}"
TMP_DIR=$(mktemp -d)

cleanup() {
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    docker image rm "$IMAGE" >/dev/null 2>&1 || true
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT HUP INT TERM

fail() {
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

command -v docker >/dev/null 2>&1 || fail "docker no está instalado"
command -v curl >/dev/null 2>&1 || fail "curl no está instalado"

# Revisa las exclusiones relevantes antes de construir el contexto.
grep -Fxq '.env' .dockerignore || fail ".dockerignore no excluye .env"
grep -Fxq '.env.*' .dockerignore || fail ".dockerignore no excluye .env.*"
grep -Fxq 'secrets/' .dockerignore || fail ".dockerignore no excluye secrets/"

printf 'Construyendo imagen desde el directorio actual...\n'
docker build -t "$IMAGE" .

# El código es efímero, solo para esta ejecución; no se pasa durante el build.
docker run -d --name "$CONTAINER" \
    -e "PORT=$PORT" \
    -e 'LLM_TOPE_TOKENS_DIA=0' \
    -e "APP_CODIGO_ACCESO=$ACCESS_CODE" \
    -p "$PORT:$PORT" \
    "$IMAGE" >/dev/null

wait_for_health() {
    attempt=0
    while [ "$attempt" -lt 60 ]; do
        status=$(curl --silent --output "$TMP_DIR/salud.json" \
            --write-out '%{http_code}' "$BASE_URL/api/salud" || true)
        if [ "$status" = 200 ]; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    return 1
}

wait_for_health || fail "GET /api/salud no devolvió 200 en 60 s"
printf 'OK GET /api/salud: 200\n'

curl --fail --silent --show-error "$BASE_URL/" >"$TMP_DIR/index.html" \
    || fail "GET / no devolvió una respuesta exitosa"
grep -q '<title>ReviewPulse | Agente de reseñas</title>' "$TMP_DIR/index.html" \
    || fail "GET / no sirvió la interfaz T11 esperada"
printf 'OK GET /: interfaz T11 servida\n'

curl --fail --silent --show-error --no-buffer --max-time 45 \
    -H 'Accept: text/event-stream' \
    -H "X-Codigo-Acceso: $ACCESS_CODE" \
    -H 'Content-Type: application/json' \
    --data '{"mensaje":"¿Cuántas reseñas hubo en la semana 8?"}' \
    "$BASE_URL/api/chat" >"$TMP_DIR/chat.sse" \
    || fail "POST /api/chat no completó el stream SSE"
grep -q '^event: final$' "$TMP_DIR/chat.sse" \
    || fail "el stream SSE no incluyó el evento final"
grep -q '"modo_demo": true' "$TMP_DIR/chat.sse" \
    || fail "el evento final no declaró modo_demo=true"
printf 'OK POST /api/chat: evento final SSE en modo demo\n'

curl --fail --silent --show-error "$BASE_URL/api/semanas" \
    >"$TMP_DIR/semanas-antes.json" \
    || fail "GET /api/semanas falló antes del reinicio"
test -s "$TMP_DIR/semanas-antes.json" \
    || fail "GET /api/semanas devolvió una respuesta vacía"
docker restart "$CONTAINER" >/dev/null \
    || fail "no se pudo reiniciar el contenedor"
wait_for_health || fail "el contenedor no recuperó salud tras reiniciar"
curl --fail --silent --show-error "$BASE_URL/api/semanas" \
    >"$TMP_DIR/semanas-despues.json" \
    || fail "GET /api/semanas falló después del reinicio"
cmp -s "$TMP_DIR/semanas-antes.json" "$TMP_DIR/semanas-despues.json" \
    || fail "los datos de semanas cambiaron tras reiniciar el mismo contenedor"
printf 'OK persistencia: /api/semanas sin cambios tras docker restart\n'

# Verifica que la imagen no contiene archivos .env y que el historial de build
# no registró patrones comunes de credenciales. El código efímero es runtime-only.
docker run --rm --entrypoint sh "$IMAGE" -c \
    'test ! -e /app/.env && test ! -e /app/.env.local && test ! -d /app/secrets' \
    || fail "la imagen contiene un archivo .env o directorio secrets"
docker history --no-trunc "$IMAGE" >"$TMP_DIR/history.txt"
if grep -Eiq 'sk-[A-Za-z0-9_-]{20,}|omni_[A-Za-z0-9_-]{20,}|LLM_API_KEY=' \
    "$TMP_DIR/history.txt"; then
    fail "docker history contiene un patrón de credencial"
fi
printf 'OK imagen: sin .env/secrets y sin patrones de credenciales en docker history\n'
printf 'Todas las verificaciones locales finalizaron correctamente.\n'
