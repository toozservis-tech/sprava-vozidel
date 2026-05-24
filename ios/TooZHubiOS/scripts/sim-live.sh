#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCHEME="${SCHEME:-TooZHubiOS}"
BUNDLE_ID="${BUNDLE_ID:-cz.toozservis.spravavozidel.ios}"
DEVICE_NAME="${DEVICE_NAME:-iPhone 16}"
DERIVED_DATA="${DERIVED_DATA:-$ROOT_DIR/.build/DerivedData}"

COMMAND="${1:-run}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing command: $1"
    exit 1
  fi
}

require_cmd xcodebuild
require_cmd xcrun
require_cmd open

find_or_boot_simulator() {
  local booted
  booted="$(xcrun simctl list devices | awk '
    /\(Booted\)/ {
      if (match($0, /[0-9A-Fa-f-]{36}/)) {
        print substr($0, RSTART, RLENGTH)
        exit
      }
    }')"
  if [[ -n "$booted" ]]; then
    echo "$booted"
    return 0
  fi

  local udid
  udid="$(xcrun simctl list devices available | awk -v dev="$DEVICE_NAME" '
    $0 ~ ("^[[:space:]]*" dev " \\(") {
      if (match($0, /[0-9A-Fa-f-]{36}/)) {
        print substr($0, RSTART, RLENGTH)
        exit
      }
    }')"

  if [[ -z "$udid" ]]; then
    udid="$(xcrun simctl list devices available | awk -v dev="$DEVICE_NAME" '
      index($0, dev) {
        if (match($0, /[0-9A-Fa-f-]{36}/)) {
          print substr($0, RSTART, RLENGTH)
          exit
        }
      }')"
  fi

  if [[ -z "$udid" ]]; then
    echo "Cannot find simulator device: $DEVICE_NAME"
    echo "Tip: export DEVICE_NAME='iPhone 15 Pro'"
    exit 1
  fi

  open -a Simulator >/dev/null 2>&1 || true
  xcrun simctl boot "$udid" >/dev/null 2>&1 || true
  xcrun simctl bootstatus "$udid" -b >/dev/null 2>&1
  echo "$udid"
}

build_install_launch() {
  local udid="$1"
  echo "Building for simulator $udid ..."
  xcodebuild \
    -project "$ROOT_DIR/TooZHubiOS.xcodeproj" \
    -scheme "$SCHEME" \
    -destination "id=$udid" \
    -derivedDataPath "$DERIVED_DATA" \
    CODE_SIGNING_ALLOWED=NO \
    build

  local app_path="$DERIVED_DATA/Build/Products/Debug-iphonesimulator/TooZHubiOS.app"
  if [[ ! -d "$app_path" ]]; then
    echo "App not found at: $app_path"
    exit 1
  fi

  echo "Installing app ..."
  xcrun simctl install "$udid" "$app_path"

  echo "Launching app ..."
  xcrun simctl terminate "$udid" "$BUNDLE_ID" >/dev/null 2>&1 || true
  xcrun simctl launch "$udid" "$BUNDLE_ID"
}

stream_logs() {
  local udid="$1"
  echo
  echo "Streaming logs for $BUNDLE_ID (Ctrl+C to stop)"
  xcrun simctl spawn "$udid" log stream --style compact --level debug \
    --predicate "process == \"TooZHubiOS\" OR processImagePath CONTAINS \"TooZHubiOS\""
}

usage() {
  cat <<EOF
Usage:
  ./scripts/sim-live.sh run      # build + install + launch + logs
  ./scripts/sim-live.sh reload   # build + install + launch
  ./scripts/sim-live.sh logs     # only log stream

Optional env:
  DEVICE_NAME='iPhone 16'
  SCHEME='TooZHubiOS'
  BUNDLE_ID='cz.toozservis.spravavozidel.ios'
  DERIVED_DATA='/custom/path'
EOF
}

main() {
  local udid
  udid="$(find_or_boot_simulator)"

  case "$COMMAND" in
    run)
      build_install_launch "$udid"
      stream_logs "$udid"
      ;;
    reload)
      build_install_launch "$udid"
      ;;
    logs)
      stream_logs "$udid"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
