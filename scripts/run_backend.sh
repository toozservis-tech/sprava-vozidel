#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

if [[ ! -x .venv/bin/python ]]; then
    echo "Chyba: .venv není připravená. Spusťte scripts/bootstrap_dev.sh"
    exit 1
fi

export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-8000}"

exec .venv/bin/python -m uvicorn src.server.main:app --host "${HOST}" --port "${PORT}"
