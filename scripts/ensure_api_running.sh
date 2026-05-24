#!/bin/bash
# Watchdog backendu: pokud API neodpovídá, automaticky ho znovu spustí.

set -euo pipefail

PROJECT_DIR="/opt/toozhub2/app"
API_URL="http://127.0.0.1:8000/health"
SERVER_LOG="$PROJECT_DIR/logs/server.log"
WATCHDOG_LOG="$PROJECT_DIR/logs/watchdog.log"
PID_FILE="$PROJECT_DIR/logs/server.pid"
LOCK_FILE="/tmp/toozhub2_api_watchdog.lock"
VOLUME_CHECK_SCRIPT="$PROJECT_DIR/scripts/check_volume_health.sh"

cd "$PROJECT_DIR" || exit 1
mkdir -p "$PROJECT_DIR/logs"

timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

# Zabrání souběžnému spuštění watchdogu (např. cron overlap).
if command -v flock >/dev/null 2>&1; then
    exec 200>"$LOCK_FILE"
    if ! flock -n 200; then
        exit 0
    fi
fi

# Pokud API běží, není co dělat.
if curl -fsS --max-time 5 "$API_URL" >/dev/null 2>&1; then
    exit 0
fi

# Nespouštět API, pokud není persistentní volume správně připojeno.
if [[ -x "$VOLUME_CHECK_SCRIPT" ]]; then
    if ! "$VOLUME_CHECK_SCRIPT" --quiet; then
        echo "$(timestamp) restart SKIPPED (volume health check failed)" >> "$WATCHDOG_LOG"
        exit 1
    fi
fi

if command -v fuser >/dev/null 2>&1; then
    fuser -k 8000/tcp 2>/dev/null || true
fi

setsid "$PROJECT_DIR/.venv/bin/python" -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000 >> "$SERVER_LOG" 2>&1 < /dev/null &
PID=$!
echo "$PID" > "$PID_FILE"

sleep 5

if curl -fsS --max-time 5 "$API_URL" >/dev/null 2>&1; then
    echo "$(timestamp) restart OK (pid=$PID)" >> "$WATCHDOG_LOG"
    exit 0
fi

echo "$(timestamp) restart FAILED (pid=$PID), check logs/server.log" >> "$WATCHDOG_LOG"
exit 1
