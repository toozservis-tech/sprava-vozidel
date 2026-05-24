#!/bin/bash
# Denní záloha persistentních dat z Hetzner volume.
# Zálohy ukládá mimo volume do /opt/toozhub2/backups/volume_data.

set -euo pipefail

PROJECT_ROOT="/opt/toozhub2"
APP_ROOT="$PROJECT_ROOT/app"
VOLUME_ROOT="/mnt/HC_Volume_105053116/toozhub2"
ROOT_DATA_DIR="$VOLUME_ROOT/root_data"
APP_DATA_DIR="$VOLUME_ROOT/app_data"
BACKUP_BASE="$PROJECT_ROOT/backups/volume_data"
LOG_FILE="$PROJECT_ROOT/logs/volume_backup.log"
LOCK_FILE="/tmp/toozhub2_volume_backup.lock"
HEALTH_SCRIPT="$APP_ROOT/scripts/check_volume_health.sh"
PYTHON_BIN="$APP_ROOT/.venv/bin/python"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

log() {
    echo "[VOLUME_BACKUP] $(timestamp) $*" >> "$LOG_FILE"
}

mkdir -p "$BACKUP_BASE" "$PROJECT_ROOT/logs"

if [[ ! -x "$HEALTH_SCRIPT" ]]; then
    log "ERROR: Chybí health script: $HEALTH_SCRIPT"
    exit 1
fi

if ! "$HEALTH_SCRIPT" --quiet; then
    log "ERROR: Volume health check selhal, záloha přeskočena."
    exit 1
fi

if command -v flock >/dev/null 2>&1; then
    exec 200>"$LOCK_FILE"
    if ! flock -n 200; then
        log "INFO: Backup už běží v jiném procesu, končím."
        exit 0
    fi
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python3)"
    else
        log "ERROR: Není dostupný Python (venv ani system python3)."
        exit 1
    fi
fi

if [[ ! -d "$ROOT_DATA_DIR" ]] || [[ ! -d "$APP_DATA_DIR" ]]; then
    log "ERROR: Chybí data složky na volume."
    exit 1
fi

TS="$(date -u +%Y%m%d_%H%M%S)"
TMP_DIR="$BACKUP_BASE/.tmp_$TS"
TARGET_DIR="$BACKUP_BASE/$TS"
mkdir -p "$TMP_DIR"

log "START backup_id=$TS retention_days=$RETENTION_DAYS"

# Konzistentní snapshot SQLite DB přes sqlite3 backup API.
if [[ -f "$ROOT_DATA_DIR/vehicles.db" ]]; then
    "$PYTHON_BIN" - "$ROOT_DATA_DIR/vehicles.db" "$TMP_DIR/vehicles.db" <<'PY'
import sqlite3
import sys

src = sys.argv[1]
dst = sys.argv[2]

src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
dst_conn = sqlite3.connect(dst)

with dst_conn:
    src_conn.backup(dst_conn)

src_conn.close()
dst_conn.close()
PY
    gzip -f "$TMP_DIR/vehicles.db"
else
    log "WARNING: Nenalezena DB $ROOT_DATA_DIR/vehicles.db"
fi

# Soubory mimo DB.
tar -C "$VOLUME_ROOT" -czf "$TMP_DIR/root_data.tar.gz" root_data
tar -C "$VOLUME_ROOT" -czf "$TMP_DIR/app_data.tar.gz" app_data

{
    echo "backup_id=$TS"
    echo "created_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "host=$(hostname)"
    echo "user=$(whoami)"
    echo "volume_root=$VOLUME_ROOT"
    echo "retention_days=$RETENTION_DAYS"
} > "$TMP_DIR/metadata.txt"

(cd "$TMP_DIR" && sha256sum * > SHA256SUMS)
mv "$TMP_DIR" "$TARGET_DIR"

# Promazání starých záloh přes Python (bez rm -rf).
"$PYTHON_BIN" - "$BACKUP_BASE" "$RETENTION_DAYS" <<'PY'
import os
import shutil
import sys
import time

base = sys.argv[1]
retention_days = int(sys.argv[2])
cutoff = time.time() - retention_days * 86400

for name in os.listdir(base):
    path = os.path.join(base, name)
    if not os.path.isdir(path):
        continue
    if not name[:8].isdigit():
        continue
    try:
        st = os.stat(path)
    except FileNotFoundError:
        continue
    if st.st_mtime < cutoff:
        shutil.rmtree(path, ignore_errors=True)
PY

log "OK backup_id=$TS target=$TARGET_DIR"
exit 0
