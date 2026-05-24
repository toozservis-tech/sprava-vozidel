#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.." || exit 1

if [[ ! -x .venv/bin/python ]]; then
    echo "Chyba: .venv není připravená. Spusťte scripts/bootstrap_dev.sh"
    exit 1
fi

MODE="${1:-local}"
shift || true

case "${MODE}" in
    local)
        exec .venv/bin/python -m pytest \
            tests/api/test_backend_sanity_ci_smoke.py \
            tests/api/test_schema_migration_smoke.py \
            tests/api/test_vehicle_ownership_source_of_truth.py \
            tests/api/test_service_record_audit_trail.py \
            tests/api/test_vehicle_owner_data_minimization.py \
            tests/api/test_vehicles_tenant_fallback_guard.py \
            tests/api/test_admin_user_archive_purge.py \
            "$@"
        ;;
    integration)
        exec .venv/bin/python -m pytest \
            tests/api/test_health.py \
            tests/api/test_auth.py \
            tests/api/test_vehicles.py \
            "$@"
        ;;
    *)
        echo "Použití: scripts/run_tests.sh [local|integration] [další pytest argumenty]"
        exit 1
        ;;
esac
