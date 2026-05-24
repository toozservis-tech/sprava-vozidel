#!/bin/bash
# Spuštění TooZ Hub 2 API serveru (localhost:8000)
# Použití: ./start_server.sh nebo bash start_server.sh

set -euo pipefail

cd "$(dirname "$0")" || exit 1

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

LOG_DIR="logs"
LOG_FILE="$LOG_DIR/server.log"
PID_FILE="$LOG_DIR/server.pid"
VOLUME_CHECK_SCRIPT="scripts/check_volume_health.sh"

mkdir -p "$LOG_DIR"

# Ochrana proti startu bez připojeného persistentního volume.
if [[ -x "$VOLUME_CHECK_SCRIPT" ]]; then
    if ! "$VOLUME_CHECK_SCRIPT" --quiet; then
        echo "Chyba: Persistentní volume není ve zdravém stavu. Server nebude spuštěn."
        echo "Spusťte: $VOLUME_CHECK_SCRIPT"
        exit 1
    fi
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Chyba: Python interpreter '$PYTHON_BIN' neexistuje."
    echo "Spusťte nejdřív: scripts/bootstrap_dev.sh"
    exit 1
fi

# Pokud je API zdravé, není potřeba ho znovu startovat.
if curl -fsS --max-time 5 "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
    echo "Server už běží na http://${HOST}:${PORT}"
    pgrep -af "${PYTHON_BIN} -m uvicorn src.server.main:app" | head -n 1 || true
    exit 0
fi

# Uvolnit port, pokud na něm visí starý proces.
if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" 2>/dev/null || true
fi
sleep 1

CMD=("$PYTHON_BIN" -m uvicorn src.server.main:app --host "$HOST" --port "$PORT")

# setsid zajistí plné oddělení procesu od shellu.
setsid "${CMD[@]}" >> "$LOG_FILE" 2>&1 < /dev/null &
PID=$!
echo "$PID" > "$PID_FILE"

echo "Server spuštěn, PID: $PID"
echo "Health check za 4 s..."
sleep 4

if curl -fsS --max-time 5 "http://${HOST}:${PORT}/health" >/dev/null; then
    echo "OK - server odpovídá na http://${HOST}:${PORT}/health"
else
    echo "Chyba: health endpoint nevrátil 200. Zkontrolujte $LOG_FILE"
    exit 1
fi
