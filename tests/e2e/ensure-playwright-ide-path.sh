#!/usr/bin/env bash
# Playwright VS Code / Cursor test server can resolve symlinked workspaces under
# releases/ to a doubled path (…/releases/releases/<release>/tests/e2e). Create the
# sibling symlink so node_modules/@playwright/test/cli.js is found by the IDE.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
e2e_real="$(cd "${SCRIPT_DIR}" && pwd -P)"

if [[ "${e2e_real}" =~ ^(.*/releases)/([^/]+)/tests/e2e$ ]]; then
  releases_root="${BASH_REMATCH[1]}"
  release_name="${BASH_REMATCH[2]}"
  doubled_dir="${releases_root}/releases/${release_name}"
  if [[ ! -e "${doubled_dir}" ]]; then
    mkdir -p "${releases_root}/releases"
    ln -s "../${release_name}" "${doubled_dir}"
    echo "Created ${doubled_dir} -> ../${release_name}"
  else
    echo "Already present: ${doubled_dir}"
  fi
else
  echo "No releases/ layout detected (${e2e_real}); skipping IDE path workaround."
fi
