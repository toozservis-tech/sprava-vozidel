# Continuous Validation (Post-Change Hard Gate)

## Purpose
Automatic validation gate for the Správa vozidel codebase after relevant changes.  
It detects regressions across security checks, core E2E flows, responsive behavior, and cross-browser coverage without changing product behavior.

## Hard-Gate Command (Cursor default)

```bash
bash scripts/qa/run_post_change_validation.sh --profile full
```

If any required step fails, overall result is `FAIL` and command exits non-zero.

## Commands

```bash
# Full gate (A+B+C+D+E)
bash scripts/qa/run_full_validation.sh

# Fast gate (A+B+C+D)
bash scripts/qa/run_fast_validation.sh

# Security regression only (A+B)
bash scripts/qa/run_security_regression.sh

# Responsive validation only (A+D)
bash scripts/qa/run_responsive_validation.sh

# Optional helper profiles
bash scripts/qa/run_after_frontend_change.sh   # A+C+D+E
bash scripts/qa/run_after_backend_change.sh    # A+B+C
```

## Validation Steps

- `A` Fast safety checks:
  - app boot and `/health` readiness
  - backend syntax/import sanity (`compileall`)
  - health/root/version pytest checks
  - Playwright runtime check
- `B` Security regression checks:
  - runtime route checks:
    - `/files/`
    - `/files/api/list`
    - `/files/view?path=README.md`
    - `/files/download?path=README.md`
    - unauthenticated `/api/v1/vehicles`
  - pytest security regressions:
    - `tests/api/test_file_browser_security.py`
    - `tests/api/test_services_discovery_tenant_isolation.py`
    - `tests/api/test_vehicles_tenant_fallback_guard.py`
- `C` Core E2E smoke:
  - `auth-smoke.spec.ts`
  - `critical-smoke.spec.ts`
  - optional admin smoke (`admin-smoke.spec.ts`) if `E2E_ADMIN_EMAIL` and `E2E_ADMIN_PASSWORD` are set
- `D` Responsive validation:
  - `responsive-smoke.spec.ts`
  - includes required viewport matrix checks:
    - mobile: `360x800`, `390x844`, `412x915`
    - tablet: `768x1024`, `820x1180`
    - desktop: `1280x800`, `1366x768`, `1440x900`
- `E` Cross-browser validation:
  - Chromium desktop/mobile/tablet
  - Firefox desktop
  - WebKit desktop/mobile only when `PW_ENABLE_WEBKIT=1`

## Status Rules

- `PASS`: step completed successfully.
- `FAIL`: required check failed; overall result is `FAIL`.
- `SKIPPED`: only for environment-gated optional checks (for example missing admin credentials or `PW_ENABLE_WEBKIT` not enabled).

## Artifacts

Each run creates:

- `artifacts/qa/postchange/<UTC_RUN_ID>/summary.txt`
- `artifacts/qa/postchange/<UTC_RUN_ID>/summary.json`
- `artifacts/qa/postchange/<UTC_RUN_ID>/*.log` (per-step logs)

Playwright outputs:

- HTML report: `artifacts/qa/playwright-report/index.html`
- traces/screenshots/videos on failures/retries: `tests/e2e/test-results/`

## Environment

- `BASE_URL` (default: `http://127.0.0.1:8000`)
- `E2E_ADMIN_EMAIL` and `E2E_ADMIN_PASSWORD` (optional admin smoke)
- `PW_ENABLE_WEBKIT=1` (enable WebKit projects in step E)

If local `BASE_URL` is not healthy, the script attempts to start uvicorn automatically for local host targets.
