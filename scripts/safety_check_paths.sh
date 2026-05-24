#!/usr/bin/env bash
# Read-only safety audit for paths that may point at production runtime data.
# This script NEVER deletes, moves, or modifies anything.
set -euo pipefail

PROTECTED_VOLUME_PREFIX="/mnt/HC_Volume_105053116/toozhub2"

usage() {
  cat <<'EOF'
Usage: bash scripts/safety_check_paths.sh <path> [<path> ...]

Inspects each path and reports whether it resolves into protected production data.
Exit codes:
  0  — path is not protected (still inspect output before destructive ops)
  20 — path resolves into protected production volume
  21 — path is a symlink whose target is protected production data
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

is_under_protected_volume() {
  local resolved="$1"
  [[ -n "$resolved" && "$resolved" == "${PROTECTED_VOLUME_PREFIX}"* ]]
}

highest_exit=0

for input_path in "$@"; do
  echo "============================================================"
  echo "INPUT PATH: ${input_path}"

  if [[ ! -e "$input_path" && ! -L "$input_path" ]]; then
    echo "STATUS: path does not exist"
    echo
    continue
  fi

  absolute_path="$(realpath -m "$input_path" 2>/dev/null || readlink -f "$input_path" 2>/dev/null || echo "$input_path")"
  resolved_path="$(readlink -f "$input_path" 2>/dev/null || echo "$absolute_path")"

  echo "ABSOLUTE PATH: ${absolute_path}"
  echo "READLINK -F:   ${resolved_path}"

  if [[ -L "$input_path" ]]; then
    echo "SYMLINK: yes -> $(readlink "$input_path")"
  else
    echo "SYMLINK: no"
  fi

  if command -v mountpoint >/dev/null 2>&1; then
    if mountpoint -q "$resolved_path" 2>/dev/null; then
      echo "MOUNTPOINT: yes (path itself is a mount point)"
    else
      echo "MOUNTPOINT: no (path itself is not a mount point)"
    fi
  else
    echo "MOUNTPOINT: mountpoint command unavailable"
  fi

  if command -v findmnt >/dev/null 2>&1; then
    echo "FINDMNT -T:"
    findmnt -T "$resolved_path" 2>/dev/null || echo "  (no mount info)"
  else
    echo "FINDMNT -T: findmnt command unavailable"
  fi

  if command -v namei >/dev/null 2>&1; then
    echo "NAMEI -L:"
    namei -l "$resolved_path" 2>/dev/null || true
  fi

  if command -v stat >/dev/null 2>&1; then
    echo "STAT:"
    stat -c '  owner=%U:%G mode=%a' "$input_path" 2>/dev/null || stat "$input_path" 2>/dev/null || true
  fi

  if is_under_protected_volume "$resolved_path"; then
    if [[ -L "$input_path" ]]; then
      echo "RESULT: SYMLINK TO PROTECTED PRODUCTION DATA — DO NOT DELETE TARGET"
      highest_exit=21
    else
      echo "RESULT: PROTECTED PRODUCTION DATA PATH — DO NOT DELETE"
      highest_exit=20
    fi
  else
    echo "RESULT: not under ${PROTECTED_VOLUME_PREFIX} (still verify before rm/rsync --delete)"
  fi

  echo
done

exit "$highest_exit"
