#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
NODEJS_PY_PACKAGE="nodejs-bin==18.4.0a4"

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

ensure_node_runtime() {
  if resolve_nodejs_pkg_dir >/dev/null 2>&1; then
    resolve_nodejs_pkg_dir
    return
  fi

  echo "[E2E bootstrap] Installing local Node runtime via Python package ${NODEJS_PY_PACKAGE}..."
  "$PYTHON_BIN" -m pip install --user "${NODEJS_PY_PACKAGE}"
  resolve_nodejs_pkg_dir
}

NODEJS_DIR="$(ensure_node_runtime)"
export PATH="${NODEJS_DIR}/bin:${NODEJS_DIR}/lib/node_modules/corepack/shims:${PATH}"

cd "${SCRIPT_DIR}"

echo "[E2E bootstrap] Installing npm dependencies..."
npm install

echo "[E2E bootstrap] Installing Playwright browsers..."
npx playwright install

DEPS_DIR="${SCRIPT_DIR}/.deps"
DEBS_DIR="${DEPS_DIR}/debs"
SYSROOT_DIR="${DEPS_DIR}/sysroot"
mkdir -p "${DEBS_DIR}" "${SYSROOT_DIR}"

APT_PACKAGES=(
  libnspr4
  libnss3
  libatk1.0-0
  libatk-bridge2.0-0
  libatspi2.0-0
  libxcomposite1
  libxdamage1
  libxext6
  libxfixes3
  libxrandr2
  libgbm1
  libxkbcommon0
  libasound2
  libgtk-3-0
  libpangocairo-1.0-0
  libpango-1.0-0
  libcairo-gobject2
  libcairo2
  libgdk-pixbuf-2.0-0
  libxrender1
  libx11-xcb1
  libxcb-shm0
  libxcursor1
  libxi6
  libwayland-server0
  libxcb-randr0
  libepoxy0
  libpangoft2-1.0-0
  libharfbuzz0b
  libxinerama1
  libwayland-cursor0
  libwayland-egl1
  libwayland-client0
  libthai0
  libpixman-1-0
  libxcb-render0
  libgraphite2-3
  libdatrie1
)

echo "[E2E bootstrap] Downloading shared libraries for browsers (no sudo)..."
(
  cd "${DEBS_DIR}"
  apt-get download "${APT_PACKAGES[@]}"
)

echo "[E2E bootstrap] Extracting downloaded libraries..."
for deb in "${DEBS_DIR}"/*.deb; do
  dpkg-deb -x "${deb}" "${SYSROOT_DIR}"
done

# Playwright VS Code / Cursor resolves symlinked workspaces under releases/ incorrectly
# (…/releases/releases/<release>/tests/e2e). A sibling symlink fixes IDE test-server lookup.
ensure_playwright_ide_path() {
  local e2e_real releases_root release_name doubled_dir
  e2e_real="$(cd "${SCRIPT_DIR}" && pwd -P)"
  if [[ "${e2e_real}" =~ ^(.*/releases)/([^/]+)/tests/e2e$ ]]; then
    releases_root="${BASH_REMATCH[1]}"
    release_name="${BASH_REMATCH[2]}"
    doubled_dir="${releases_root}/releases/${release_name}"
    if [[ ! -e "${doubled_dir}" ]]; then
      mkdir -p "${releases_root}/releases"
      ln -s "../${release_name}" "${doubled_dir}"
      echo "[E2E bootstrap] IDE Playwright path workaround: ${doubled_dir} -> ../${release_name}"
    fi
  fi
}
ensure_playwright_ide_path

echo "[E2E bootstrap] Complete."
echo "[E2E bootstrap] Use: npm test"
