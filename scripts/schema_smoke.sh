#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

if [[ ! -x .venv/bin/python ]]; then
    echo "Chyba: .venv není připravená. Spusťte scripts/bootstrap_dev.sh"
    exit 1
fi

exec .venv/bin/python -m pytest tests/api/test_schema_migration_smoke.py "$@"
