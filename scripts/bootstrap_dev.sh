#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
    if command -v python3.12 >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v python3.12)"
    elif command -v /opt/homebrew/bin/python3.12 >/dev/null 2>&1; then
        PYTHON_BIN="/opt/homebrew/bin/python3.12"
    else
        echo "Chyba: Python 3.12 nebyl nalezen."
        echo "Na macOS použijte: brew install python@3.12"
        exit 1
    fi
fi

if [[ -d .venv ]]; then
    if ! .venv/bin/python - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)
PY
    then
        stamp="$(date +%Y%m%d-%H%M%S)"
        mv .venv ".venv.invalid.${stamp}"
    fi
fi

if [[ ! -d .venv ]]; then
    "${PYTHON_BIN}" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements-dev.txt

echo
echo "Hotovo."
echo "Aktivace: source .venv/bin/activate"
echo "Python: $(.venv/bin/python --version)"
