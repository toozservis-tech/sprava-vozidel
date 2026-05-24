#!/bin/bash
# Ověří, že persistentní Hetzner volume je připojený a data cesty jsou správně.

set -euo pipefail

QUIET="${1:-}"
VOLUME_MOUNT="/mnt/HC_Volume_105053116"
ROOT_LINK="/opt/toozhub2/data"
APP_LINK="/opt/toozhub2/app/data"
EXPECTED_ROOT_TARGET="/mnt/HC_Volume_105053116/toozhub2/root_data"
EXPECTED_APP_TARGET="/mnt/HC_Volume_105053116/toozhub2/app_data"
MIN_FREE_MB="${MIN_FREE_MB:-1024}"

timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

info() {
    if [[ "$QUIET" != "--quiet" ]]; then
        echo "[VOLUME_CHECK] $(timestamp) $*"
    fi
}

fail() {
    echo "[VOLUME_CHECK] $(timestamp) ERROR: $*" >&2
    exit 1
}

if ! findmnt -rn --target "$VOLUME_MOUNT" >/dev/null 2>&1; then
    fail "Mountpoint $VOLUME_MOUNT není připojen."
fi

source_dev="$(findmnt -rn -o SOURCE --target "$VOLUME_MOUNT" || true)"
fs_type="$(findmnt -rn -o FSTYPE --target "$VOLUME_MOUNT" || true)"
if [[ -z "$source_dev" ]]; then
    fail "Nelze zjistit source zařízení pro $VOLUME_MOUNT."
fi
if [[ "$fs_type" != "ext4" ]]; then
    fail "Neočekávaný filesystem na $VOLUME_MOUNT: '$fs_type' (očekáván ext4)."
fi

if [[ ! -L "$ROOT_LINK" ]]; then
    fail "$ROOT_LINK není symlink."
fi
if [[ ! -L "$APP_LINK" ]]; then
    fail "$APP_LINK není symlink."
fi

resolved_root="$(readlink -f "$ROOT_LINK" || true)"
resolved_app="$(readlink -f "$APP_LINK" || true)"

if [[ "$resolved_root" != "$EXPECTED_ROOT_TARGET" ]]; then
    fail "$ROOT_LINK míří na '$resolved_root', očekáváno '$EXPECTED_ROOT_TARGET'."
fi
if [[ "$resolved_app" != "$EXPECTED_APP_TARGET" ]]; then
    fail "$APP_LINK míří na '$resolved_app', očekáváno '$EXPECTED_APP_TARGET'."
fi

if [[ ! -d "$EXPECTED_ROOT_TARGET" ]]; then
    fail "Cílová cesta neexistuje: $EXPECTED_ROOT_TARGET"
fi
if [[ ! -d "$EXPECTED_APP_TARGET" ]]; then
    fail "Cílová cesta neexistuje: $EXPECTED_APP_TARGET"
fi

rw_test="$VOLUME_MOUNT/.volume_rw_test_$$"
if ! ( : > "$rw_test" ); then
    fail "Nelze zapisovat do $VOLUME_MOUNT."
fi
unlink "$rw_test"

avail_mb="$(df -Pm "$VOLUME_MOUNT" | awk 'NR==2 {print $4}')"
if [[ -n "$avail_mb" ]] && [[ "$avail_mb" -lt "$MIN_FREE_MB" ]]; then
    echo "[VOLUME_CHECK] $(timestamp) WARNING: Volné místo ${avail_mb}MB je pod limitem ${MIN_FREE_MB}MB." >&2
fi

info "OK mount=$VOLUME_MOUNT source=$source_dev fs=$fs_type free_mb=$avail_mb"
exit 0
