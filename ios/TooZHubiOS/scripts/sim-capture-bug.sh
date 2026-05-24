#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_ID="${BUNDLE_ID:-cz.toozservis.spravavozidel.ios}"
NOTE="${*:-Bug report without note}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing command: $1"
    exit 1
  fi
}

require_cmd xcrun
require_cmd log

UDID="$(xcrun simctl list devices booted | awk -F '[()]' '/Booted/ {print $2; exit}')"
if [[ -z "$UDID" ]]; then
  echo "No booted simulator found. Start simulator first."
  exit 1
fi

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="$ROOT_DIR/artifacts/ios-bugs/$TIMESTAMP"
mkdir -p "$OUT_DIR"

echo "Capturing screenshot ..."
xcrun simctl io "$UDID" screenshot "$OUT_DIR/screen.png" >/dev/null

echo "Collecting recent logs ..."
log show --last 6m --style compact --predicate "process == \"TooZHubiOS\"" > "$OUT_DIR/app.log" 2>/dev/null || true

echo "Extracting error lines ..."
grep -Ei "error|fault|fatal|assert|exception|crash|swiftui" "$OUT_DIR/app.log" > "$OUT_DIR/errors.log" || true

echo "Copying crash reports ..."
cp "$HOME"/Library/Logs/DiagnosticReports/TooZHubiOS* "$OUT_DIR/" 2>/dev/null || true

cat > "$OUT_DIR/PROMPT_FOR_CODEX.md" <<EOF
# iOS bug report

## User note
$NOTE

## Collected files
- screen.png
- app.log
- errors.log
- DiagnosticReports/TooZHubiOS*.crash (if available)

## What to send to Codex
1. Přilož screenshot.
2. Přilož \`errors.log\` nebo \`app.log\`.
3. Pokud existuje crash report, přilož ho celý.
EOF

echo
echo "Saved bug bundle: $OUT_DIR"
echo "Open: $OUT_DIR/PROMPT_FOR_CODEX.md"

