#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PROFILE="full"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
PW_ENABLE_WEBKIT="${PW_ENABLE_WEBKIT:-0}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${ROOT_DIR}/artifacts/qa/postchange/${RUN_ID}"

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/qa/run_post_change_validation.sh [--profile <name>] [--base-url <url>]

Profiles:
  full        A+B+C+D+E (default hard gate)
  fast        A+B+C+D
  security    A+B
  responsive  A+D
  frontend    A+C+D+E
  backend     A+B+C
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      PROFILE="${2:-}"
      shift 2
      ;;
    --base-url)
      BASE_URL="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

case "${PROFILE}" in
  full|fast|security|responsive|frontend|backend) ;;
  *)
    echo "Unsupported profile: ${PROFILE}" >&2
    usage
    exit 2
    ;;
esac

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    echo "python3 not found." >&2
    exit 1
  fi
fi

mkdir -p "${RUN_DIR}"
STEPS_TSV="${RUN_DIR}/steps.tsv"
: > "${STEPS_TSV}"

SERVER_STARTED_BY_SCRIPT=0
SERVER_PID=""

OVERALL_STATUS="PASS"
FAILED_STEP=""

PLAYWRIGHT_REPORT_PATH="${ROOT_DIR}/artifacts/qa/playwright-report/index.html"
PLAYWRIGHT_TRACE_DIR="${ROOT_DIR}/tests/e2e/test-results"

sanitize_text() {
  local value="${1:-}"
  value="${value//$'\t'/ }"
  value="${value//$'\n'/ }"
  echo "${value}"
}

record_step() {
  local step_id="$1"
  local status="$2"
  local required="$3"
  local reason="$4"
  local log_file="$5"
  local duration_s="$6"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "${step_id}" \
    "${status}" \
    "${required}" \
    "$(sanitize_text "${reason}")" \
    "${log_file}" \
    "${duration_s}" >> "${STEPS_TSV}"
}

skip_step() {
  local step_id="$1"
  local required="$2"
  local reason="$3"
  local log_file="${RUN_DIR}/${step_id}.log"
  printf 'SKIPPED: %s\n' "${reason}" > "${log_file}"
  record_step "${step_id}" "SKIPPED" "${required}" "${reason}" "${log_file}" "0"
}

run_step_cmd() {
  local step_id="$1"
  local required="$2"
  local description="$3"
  local command="$4"

  local log_file="${RUN_DIR}/${step_id}.log"
  local started_at
  started_at="$(date +%s)"

  {
    echo "step=${step_id}"
    echo "description=${description}"
    echo "required=${required}"
    echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "cwd=${ROOT_DIR}"
    echo "command=${command}"
    echo ""
  } > "${log_file}"

  local exit_code=0
  set +e
  bash -lc "cd \"${ROOT_DIR}\" && ${command}" >> "${log_file}" 2>&1
  exit_code=$?
  set -e

  local finished_at duration
  finished_at="$(date +%s)"
  duration=$((finished_at - started_at))

  if [[ ${exit_code} -eq 0 ]]; then
    record_step "${step_id}" "PASS" "${required}" "" "${log_file}" "${duration}"
    return 0
  fi

  record_step "${step_id}" "FAIL" "${required}" "exit_code=${exit_code}" "${log_file}" "${duration}"
  return "${exit_code}"
}

mark_failure() {
  local step_id="$1"
  OVERALL_STATUS="FAIL"
  FAILED_STEP="${step_id}"
}

run_required_step() {
  local step_id="$1"
  local description="$2"
  local command="$3"
  if ! run_step_cmd "${step_id}" "yes" "${description}" "${command}"; then
    mark_failure "${step_id}"
    return 1
  fi
  return 0
}

run_optional_step() {
  local step_id="$1"
  local description="$2"
  local command="$3"
  if ! run_step_cmd "${step_id}" "no" "${description}" "${command}"; then
    mark_failure "${step_id}"
    return 1
  fi
  return 0
}

cleanup_server() {
  if [[ "${SERVER_STARTED_BY_SCRIPT}" -eq 1 ]] && [[ -n "${SERVER_PID}" ]]; then
    if kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
      kill "${SERVER_PID}" >/dev/null 2>&1 || true
      wait "${SERVER_PID}" >/dev/null 2>&1 || true
    fi
  fi
}
trap cleanup_server EXIT

ensure_server_running() {
  local log_file="$1"
  local health_url="${BASE_URL%/}/health"

  if curl -fsS --max-time 5 "${health_url}" >/dev/null 2>&1; then
    echo "Server already healthy at ${health_url}" >> "${log_file}"
    return 0
  fi

  if [[ ! "${BASE_URL}" =~ ^https?://(127\.0\.0\.1|localhost)(:[0-9]+)?$ ]]; then
    echo "Cannot auto-start non-local BASE_URL=${BASE_URL}" >> "${log_file}"
    return 1
  fi

  local port="8000"
  if [[ "${BASE_URL}" =~ :([0-9]+)$ ]]; then
    port="${BASH_REMATCH[1]}"
  fi

  echo "Starting local server on 127.0.0.1:${port}" >> "${log_file}"
  (
    cd "${ROOT_DIR}"
    "${PYTHON_BIN}" -m uvicorn src.server.main:app --host 127.0.0.1 --port "${port}"
  ) >> "${RUN_DIR}/server.log" 2>&1 &
  SERVER_PID=$!
  SERVER_STARTED_BY_SCRIPT=1
  echo "Started PID=${SERVER_PID}" >> "${log_file}"

  for _ in $(seq 1 90); do
    if curl -fsS --max-time 5 "${health_url}" >/dev/null 2>&1; then
      echo "Server became healthy at ${health_url}" >> "${log_file}"
      return 0
    fi
    sleep 1
  done

  echo "Server failed to reach healthy state at ${health_url}" >> "${log_file}"
  return 1
}

run_security_runtime_checks() {
  local step_id="B1_security_runtime_routes"
  local log_file="${RUN_DIR}/${step_id}.log"
  local started_at
  started_at="$(date +%s)"

  {
    echo "step=${step_id}"
    echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "base_url=${BASE_URL}"
    echo ""
  } > "${log_file}"

  local failed=0

  check_path() {
    local path="$1"
    local expected_codes="$2"
    local tmp_file
    tmp_file="$(mktemp)"
    local status_code
    status_code="$(curl -sS -o "${tmp_file}" -w '%{http_code}' "${BASE_URL%/}${path}" || true)"
    local body_snippet
    body_snippet="$(head -c 160 "${tmp_file}" | tr '\n' ' ' || true)"
    rm -f "${tmp_file}"

    echo "${path} => status=${status_code} expected=[${expected_codes}] body='${body_snippet}'" >> "${log_file}"

    local allowed=0
    for code in ${expected_codes}; do
      if [[ "${status_code}" == "${code}" ]]; then
        allowed=1
        break
      fi
    done

    if [[ ${allowed} -ne 1 ]]; then
      failed=1
    fi
  }

  check_path "/files/" "401 403 404"
  check_path "/files/api/list" "401 403 404"
  check_path "/files/view?path=README.md" "401 403 404"
  check_path "/files/download?path=README.md" "401 403 404"
  check_path "/api/v1/vehicles" "401 403"

  local finished_at duration
  finished_at="$(date +%s)"
  duration=$((finished_at - started_at))

  if [[ ${failed} -eq 0 ]]; then
    record_step "${step_id}" "PASS" "yes" "" "${log_file}" "${duration}"
    return 0
  fi

  record_step "${step_id}" "FAIL" "yes" "status_code_out_of_policy" "${log_file}" "${duration}"
  return 1
}

should_run_step_group() {
  local group="$1"
  case "${PROFILE}" in
    full)
      return 0
      ;;
    fast)
      [[ "${group}" != "cross" ]]
      return
      ;;
    security)
      [[ "${group}" == "security" ]]
      return
      ;;
    responsive)
      [[ "${group}" == "responsive" ]]
      return
      ;;
    frontend)
      [[ "${group}" == "core" || "${group}" == "responsive" || "${group}" == "cross" ]]
      return
      ;;
    backend)
      [[ "${group}" == "security" || "${group}" == "core" ]]
      return
      ;;
  esac
  return 1
}

generate_reports() {
  local summary_json="${RUN_DIR}/summary.json"
  local summary_txt="${RUN_DIR}/summary.txt"
  export SUMMARY_JSON="${summary_json}"
  export SUMMARY_TXT="${summary_txt}"
  export QA_RUN_ID="${RUN_ID}"
  export QA_RUN_DIR="${RUN_DIR}"
  export QA_STEPS_TSV="${STEPS_TSV}"
  export QA_OVERALL="${OVERALL_STATUS}"
  export QA_FAILED_STEP="${FAILED_STEP}"
  export QA_PROFILE="${PROFILE}"
  export QA_BASE_URL="${BASE_URL}"
  export QA_PLAYWRIGHT_REPORT="${PLAYWRIGHT_REPORT_PATH}"
  export QA_TRACE_DIR="${PLAYWRIGHT_TRACE_DIR}"

  "${PYTHON_BIN}" - <<'PY'
import csv
import json
import os
from pathlib import Path

steps = []
with open(os.environ["QA_STEPS_TSV"], "r", encoding="utf-8") as handle:
    reader = csv.reader(handle, delimiter="\t")
    for row in reader:
        if not row:
            continue
        step_id, status, required, reason, log_path, duration_s = row
        steps.append(
            {
                "step": step_id,
                "status": status,
                "required": required == "yes",
                "reason": reason,
                "log_path": log_path,
                "duration_seconds": int(duration_s or "0"),
            }
        )

summary = {
    "run_id": os.environ["QA_RUN_ID"],
    "profile": os.environ["QA_PROFILE"],
    "base_url": os.environ["QA_BASE_URL"],
    "overall_status": os.environ["QA_OVERALL"],
    "failed_step": os.environ["QA_FAILED_STEP"] or None,
    "artifacts_dir": os.environ["QA_RUN_DIR"],
    "playwright_report_path": os.environ["QA_PLAYWRIGHT_REPORT"],
    "playwright_trace_dir": os.environ["QA_TRACE_DIR"],
    "steps": steps,
}

summary_json = Path(os.environ["SUMMARY_JSON"])
summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")

lines = [
    f"run_id: {summary['run_id']}",
    f"profile: {summary['profile']}",
    f"base_url: {summary['base_url']}",
    f"overall_status: {summary['overall_status']}",
    f"failed_step: {summary['failed_step']}",
    f"artifacts_dir: {summary['artifacts_dir']}",
    f"playwright_report_path: {summary['playwright_report_path']}",
    f"playwright_trace_dir: {summary['playwright_trace_dir']}",
    "",
    "steps:",
]
for step in steps:
    reason = f" ({step['reason']})" if step["reason"] else ""
    lines.append(
        f"- {step['step']}: {step['status']}{reason}, required={step['required']}, "
        f"duration={step['duration_seconds']}s, log={step['log_path']}"
    )

Path(os.environ["SUMMARY_TXT"]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

run_pipeline() {
  local server_log="${RUN_DIR}/A0_server_boot_sanity.log"
  local a0_started
  a0_started="$(date +%s)"
  {
    echo "step=A0_server_boot_sanity"
    echo "description=Ensure app boots and /health is reachable"
    echo "required=yes"
    echo "started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "base_url=${BASE_URL}"
    echo ""
  } > "${server_log}"
  if ensure_server_running "${server_log}"; then
    local a0_finished a0_duration
    a0_finished="$(date +%s)"
    a0_duration=$((a0_finished - a0_started))
    record_step "A0_server_boot_sanity" "PASS" "yes" "" "${server_log}" "${a0_duration}"
  else
    local a0_finished a0_duration
    a0_finished="$(date +%s)"
    a0_duration=$((a0_finished - a0_started))
    record_step "A0_server_boot_sanity" "FAIL" "yes" "server_not_healthy" "${server_log}" "${a0_duration}"
    mark_failure "A0_server_boot_sanity"
    return 1
  fi

  if [[ -f "${ROOT_DIR}/pyproject.toml" || -f "${ROOT_DIR}/ruff.toml" || -f "${ROOT_DIR}/mypy.ini" || -f "${ROOT_DIR}/package.json" ]]; then
    skip_step "A1_lint_type_build" "no" "No stable lint/type/build gate configured for this repository."
  else
    skip_step "A1_lint_type_build" "no" "No lint/type/build configuration files detected."
  fi

  run_required_step \
    "A2_python_compile_sanity" \
    "Syntax/runtime import sanity for backend modules" \
    "\"${PYTHON_BIN}\" -m compileall -q src" || return 1

  run_required_step \
    "A3_health_route_pytest" \
    "Route/app boot sanity checks" \
    "\"${PYTHON_BIN}\" -m pytest tests/api/test_health.py -q" || return 1

  run_required_step \
    "A4_playwright_runtime_check" \
    "Playwright runtime dependency check" \
    "bash tests/e2e/run-playwright.sh --version" || return 1

  if should_run_step_group "security"; then
    if ! run_security_runtime_checks; then
      mark_failure "B1_security_runtime_routes"
      return 1
    fi

    run_required_step \
      "B2_security_pytest_regressions" \
      "Security regression unit checks" \
      "\"${PYTHON_BIN}\" -m pytest tests/api/test_file_browser_security.py tests/api/test_services_discovery_tenant_isolation.py tests/api/test_vehicles_tenant_fallback_guard.py -q" || return 1
  else
    skip_step "B1_security_runtime_routes" "no" "Skipped by selected profile '${PROFILE}'."
    skip_step "B2_security_pytest_regressions" "no" "Skipped by selected profile '${PROFILE}'."
  fi

  if should_run_step_group "core"; then
    run_required_step \
      "C1_core_e2e_smoke" \
      "Protected core flow smoke: auth + dashboard + vehicles + service records + reminders/reservations + profile/support" \
      "BASE_URL='${BASE_URL}' bash tests/e2e/run-playwright.sh test auth-smoke.spec.ts critical-smoke.spec.ts --project auth-chromium --project smoke-desktop-chromium" || return 1

    if [[ -n "${E2E_ADMIN_EMAIL:-}" && -n "${E2E_ADMIN_PASSWORD:-}" ]]; then
      run_optional_step \
        "C2_admin_e2e_smoke" \
        "Admin shell/login smoke (optional when admin credentials are present)" \
        "BASE_URL='${BASE_URL}' E2E_ADMIN_EMAIL='${E2E_ADMIN_EMAIL}' E2E_ADMIN_PASSWORD='${E2E_ADMIN_PASSWORD}' bash tests/e2e/run-playwright.sh test admin-smoke.spec.ts --project admin-chromium" || return 1
    else
      skip_step "C2_admin_e2e_smoke" "no" "E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD not set."
    fi
  else
    skip_step "C1_core_e2e_smoke" "no" "Skipped by selected profile '${PROFILE}'."
    skip_step "C2_admin_e2e_smoke" "no" "Skipped by selected profile '${PROFILE}'."
  fi

  if should_run_step_group "responsive"; then
    run_required_step \
      "D1_responsive_e2e" \
      "Responsive/mobile/tablet validation smoke" \
      "BASE_URL='${BASE_URL}' bash tests/e2e/run-playwright.sh test responsive-smoke.spec.ts --project smoke-mobile-chromium --project smoke-tablet-chromium" || return 1
  else
    skip_step "D1_responsive_e2e" "no" "Skipped by selected profile '${PROFILE}'."
  fi

  if should_run_step_group "cross"; then
    run_required_step \
      "E1_cross_browser_chromium_firefox" \
      "Cross-browser smoke on Chromium (desktop/mobile/tablet) and Firefox desktop" \
      "BASE_URL='${BASE_URL}' bash tests/e2e/run-playwright.sh test critical-smoke.spec.ts responsive-smoke.spec.ts --project smoke-desktop-chromium --project smoke-desktop-firefox --project smoke-mobile-chromium --project smoke-tablet-chromium" || return 1

    if [[ "${PW_ENABLE_WEBKIT}" == "1" ]]; then
      run_optional_step \
        "E2_cross_browser_webkit" \
        "Cross-browser smoke on WebKit desktop/mobile (optional via PW_ENABLE_WEBKIT=1)" \
        "PW_ENABLE_WEBKIT=1 BASE_URL='${BASE_URL}' bash tests/e2e/run-playwright.sh test critical-smoke.spec.ts responsive-smoke.spec.ts --project smoke-desktop-webkit --project smoke-mobile-safari" || return 1
    else
      skip_step "E2_cross_browser_webkit" "no" "PW_ENABLE_WEBKIT is not set to 1."
    fi
  else
    skip_step "E1_cross_browser_chromium_firefox" "no" "Skipped by selected profile '${PROFILE}'."
    skip_step "E2_cross_browser_webkit" "no" "Skipped by selected profile '${PROFILE}'."
  fi

  return 0
}

if ! run_pipeline; then
  OVERALL_STATUS="FAIL"
fi

generate_reports

echo "QA run profile: ${PROFILE}"
echo "QA artifacts: ${RUN_DIR}"
echo "Summary text: ${RUN_DIR}/summary.txt"
echo "Summary JSON: ${RUN_DIR}/summary.json"
echo "Playwright report: ${PLAYWRIGHT_REPORT_PATH}"
echo "Playwright traces: ${PLAYWRIGHT_TRACE_DIR}"
echo "Overall status: ${OVERALL_STATUS}"

if [[ "${OVERALL_STATUS}" == "FAIL" ]]; then
  echo "Failed step: ${FAILED_STEP}"
  exit 1
fi

exit 0
