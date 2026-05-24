#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

resolve_nodejs_pkg_dir() {
  "$PYTHON_BIN" - <<'PY'
import importlib.util
import pathlib
import sys

spec = importlib.util.find_spec("nodejs")
if not spec or not spec.origin:
    sys.exit(1)
print(pathlib.Path(spec.origin).resolve().parent)
PY
}

if ! NODEJS_DIR="$(resolve_nodejs_pkg_dir 2>/dev/null)"; then
  echo "[E2E run] Node runtime not found. Run: npm run bootstrap"
  exit 1
fi

LIB_DIR="${SCRIPT_DIR}/.deps/sysroot/usr/lib/x86_64-linux-gnu"
if [[ ! -d "${LIB_DIR}" ]]; then
  echo "[E2E run] Browser shared libraries not found in ${LIB_DIR}."
  echo "[E2E run] Run: npm run bootstrap"
  exit 1
fi

export PATH="${NODEJS_DIR}/bin:${NODEJS_DIR}/lib/node_modules/corepack/shims:${PATH}"
export LD_LIBRARY_PATH="${LIB_DIR}:${LD_LIBRARY_PATH:-}"

cd "${SCRIPT_DIR}"

if [[ $# -eq 0 ]]; then
  set -- test
fi

exec npx playwright "$@"
