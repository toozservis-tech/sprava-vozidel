#!/usr/bin/env python3
"""
Interactive end-to-end browser agent for Správa vozidel.

What it does:
1) Verifies API availability and ensures an E2E user exists.
2) Runs an interactive UI flow in Playwright (login, tabs, add vehicle, detail modal, logout).
3) Validates key API flows with JWT token obtained from the UI session.
4) Writes a JSON report with per-step pass/fail status.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_LIBS_DIR = PROJECT_ROOT / ".local-libs"
DEB_CACHE_DIR = Path("/tmp/pwdeps")

DEB_PACKAGES = [
    "libnspr4",
    "libnss3",
    "libatk1.0-0",
    "libatk-bridge2.0-0",
    "libatspi2.0-0",
    "libxcomposite1",
    "libxdamage1",
    "libxext6",
    "libxfixes3",
    "libxrandr2",
    "libgbm1",
    "libxkbcommon0",
    "libasound2",
    "libxi6",
    "libxrender1",
    "libwayland-server0",
    "libxcb-randr0",
]


@dataclass
class StepResult:
    step: str
    ok: bool
    info: str = ""


class Recorder:
    def __init__(self) -> None:
        self.steps: List[StepResult] = []

    def add(self, step: str, ok: bool, info: str = "") -> None:
        self.steps.append(StepResult(step=step, ok=ok, info=info))
        status = "OK" if ok else "FAIL"
        suffix = f" - {info}" if info else ""
        print(f"[{status}] {step}{suffix}")

    def all_ok(self) -> bool:
        return all(s.ok for s in self.steps)

    def to_dict(self) -> List[Dict[str, Any]]:
        return [asdict(s) for s in self.steps]


def run_cmd(cmd: List[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def find_headless_shell() -> Optional[Path]:
    cache_root = Path.home() / ".cache" / "ms-playwright"
    if not cache_root.exists():
        return None
    candidates = sorted(cache_root.glob("chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))
    return candidates[-1] if candidates else None


def parse_missing_libs(binary: Path, env: Dict[str, str]) -> List[str]:
    result = subprocess.run(
        ["ldd", str(binary)],
        text=True,
        capture_output=True,
        env=env,
    )
    if result.returncode != 0:
        return ["ldd-failed"]
    missing = []
    for line in result.stdout.splitlines():
        if "=> not found" in line:
            missing.append(line.strip())
    return missing


def ensure_local_runtime_libs(rec: Recorder) -> None:
    shell = find_headless_shell()
    if not shell:
        rec.add("runtime_libs", True, "headless-shell-not-installed-yet")
        return

    base_env = os.environ.copy()
    missing = parse_missing_libs(shell, base_env)
    if not missing:
        rec.add("runtime_libs", True, "already-resolved")
        return

    if not shutil.which("apt-get") or not shutil.which("dpkg-deb"):
        rec.add("runtime_libs", False, "apt-get/dpkg-deb-not-available")
        return

    LOCAL_LIBS_DIR.mkdir(parents=True, exist_ok=True)
    DEB_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    for package in DEB_PACKAGES:
        run_cmd(["apt-get", "download", package], cwd=DEB_CACHE_DIR, check=True)

    for deb_file in DEB_CACHE_DIR.glob("*.deb"):
        run_cmd(["dpkg-deb", "-x", str(deb_file), str(LOCAL_LIBS_DIR)], check=True)

    lib_paths = [
        str(LOCAL_LIBS_DIR / "usr/lib/x86_64-linux-gnu"),
        str(LOCAL_LIBS_DIR / "lib/x86_64-linux-gnu"),
    ]
    current = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = ":".join([*lib_paths, current]).rstrip(":")

    missing_after = parse_missing_libs(shell, os.environ.copy())
    if missing_after:
        rec.add("runtime_libs", False, f"unresolved: {', '.join(missing_after)}")
    else:
        rec.add("runtime_libs", True, "resolved-via-local-debs")


def ensure_playwright_browser(rec: Recorder, python_bin: str) -> None:
    run_cmd([python_bin, "-m", "playwright", "install", "chromium"], check=True)
    rec.add("playwright_browser", True, "chromium-installed")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_credentials() -> Tuple[str, str]:
    suffix = f"{int(time.time())}{random.randint(1000, 9999)}"
    email = os.getenv("E2E_EMAIL", f"e2e.agent.{suffix}@example.com")
    password = os.getenv("E2E_PASSWORD", "E2eAgent123!")
    return email, password


def api_post_json(
    base_url: str,
    path: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 20,
) -> requests.Response:
    return requests.post(
        f"{base_url}{path}",
        json=payload,
        headers=headers or {},
        timeout=timeout,
    )


def api_get(
    base_url: str,
    path: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 20,
) -> requests.Response:
    return requests.get(
        f"{base_url}{path}",
        headers=headers or {},
        timeout=timeout,
    )


def api_put_json(
    base_url: str,
    path: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 20,
) -> requests.Response:
    return requests.put(
        f"{base_url}{path}",
        json=payload,
        headers=headers or {},
        timeout=timeout,
    )


def api_delete(
    base_url: str,
    path: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 20,
) -> requests.Response:
    return requests.delete(
        f"{base_url}{path}",
        headers=headers or {},
        timeout=timeout,
    )


def ensure_test_user(base_url: str, email: str, password: str, rec: Recorder) -> None:
    health = api_get(base_url, "/health", timeout=15)
    rec.add("api_health", health.status_code == 200, f"status={health.status_code}")

    register = api_post_json(
        base_url,
        "/user/register",
        {"email": email, "password": password, "name": "E2E Agent"},
    )
    rec.add(
        "api_register",
        register.status_code in (200, 400),
        f"status={register.status_code}",
    )

    login = api_post_json(
        base_url,
        "/user/login",
        {"email": email, "password": password},
    )
    rec.add("api_login_precheck", login.status_code == 200, f"status={login.status_code}")


def run_ui_flow(base_url: str, email: str, password: str, rec: Recorder) -> Tuple[Optional[str], Optional[int]]:
    token: Optional[str] = None
    first_vehicle_id: Optional[int] = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=os.getenv("E2E_HEADLESS", "1") != "0")
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()

        try:
            page.goto(f"{base_url}/web/index.html", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector('[data-testid="login-form"]', timeout=10000)
            rec.add("ui_load_login", True)

            page.fill('[data-testid="input-email"]', email)
            page.fill('[data-testid="input-password"]', password)
            page.click('[data-testid="btn-login"]')
            page.wait_for_selector('[data-testid="dashboard"]', timeout=15000)
            rec.add("ui_login", True)

            for tab, content in [
                ("tab-vehicles", "vehicles-tab"),
                ("tab-reminders", "reminders-tab"),
                ("tab-reservations", "reservations-tab"),
                ("tab-documents", "documents-tab"),
                ("tab-account", "account-tab"),
            ]:
                page.click(f'[data-testid="{tab}"]')
                page.wait_for_selector(f'[data-testid="{content}"]', timeout=10000)
                rec.add(f"ui_navigate_{tab}", True)

            page.click('[data-testid="tab-vehicles"]')
            page.wait_for_timeout(1000)
            before_cards = page.locator('[data-testid="vehicle-card"]').count()

            page.click('[data-testid="btn-toggle-add-vehicle"]')
            page.wait_for_selector('[data-testid="add-vehicle-form"]', timeout=10000)
            ts = int(time.time())
            page.fill('[data-testid="input-vehicle-name"]', f"E2E Vehicle {ts}")
            page.fill('[data-testid="input-vehicle-plate"]', f"E2E{ts % 10000:04d}")
            page.fill('[data-testid="input-vehicle-stk-date"]', str(date.today() + timedelta(days=365)))
            page.click('[data-testid="btn-add-vehicle"]')
            page.wait_for_timeout(2500)

            err_count = page.locator('[data-testid="alert-error"]').count()
            page.click('[data-testid="tab-vehicles"]')
            page.wait_for_timeout(1500)
            after_cards = page.locator('[data-testid="vehicle-card"]').count()
            add_ok = err_count == 0 and after_cards >= max(1, before_cards)
            rec.add("ui_add_vehicle", add_ok, f"errors={err_count}, cards={before_cards}->{after_cards}")

            if after_cards > 0:
                first_card = page.locator('[data-testid="vehicle-card"]').first
                raw_id = first_card.get_attribute("data-vehicle-id")
                if raw_id and raw_id.isdigit():
                    first_vehicle_id = int(raw_id)
                first_card.click()
                page.wait_for_selector('[data-testid="vehicle-detail-modal"]', timeout=5000)
                rec.add("ui_vehicle_detail_modal_open", True)
                page.click('[data-testid="btn-close-vehicle-modal"]')
                page.wait_for_timeout(400)
                rec.add("ui_vehicle_detail_modal_close", True)
            else:
                rec.add("ui_vehicle_detail_modal_open", False, "no-cards-available")

            page.click('[data-testid="tab-account"]')
            page.wait_for_selector('[data-testid="profile-container"]', timeout=10000)
            rec.add("ui_profile_load", True)

            token = page.evaluate("() => localStorage.getItem('accessToken')")
            rec.add("ui_token_present", bool(token), "missing accessToken in localStorage" if not token else "")

            page.click('[data-testid="btn-logout"]')
            page.wait_for_selector('[data-testid="login-form"]', timeout=10000)
            rec.add("ui_logout", True)

        except PWTimeout as exc:
            rec.add("ui_flow_timeout", False, str(exc))
            page.screenshot(path="/tmp/sprava_vozidel_ui_flow_timeout.png", full_page=True)
        except Exception as exc:  # pragma: no cover - runtime safety
            rec.add("ui_flow_exception", False, repr(exc))
            page.screenshot(path="/tmp/sprava_vozidel_ui_flow_exception.png", full_page=True)
        finally:
            browser.close()

    return token, first_vehicle_id


def run_api_flow(base_url: str, token: Optional[str], vehicle_id: Optional[int], rec: Recorder) -> None:
    if not token:
        rec.add("api_flow_token", False, "JWT token missing from UI session")
        return

    headers = {"Authorization": f"Bearer {token}"}

    me = api_get(base_url, "/user/me", headers=headers)
    rec.add("api_user_me", me.status_code == 200, f"status={me.status_code}")

    vehicles = api_get(base_url, "/api/v1/vehicles", headers=headers)
    rec.add("api_vehicles_list", vehicles.status_code == 200, f"status={vehicles.status_code}")

    reminders = api_get(base_url, "/api/v1/reminders", headers=headers)
    rec.add("api_reminders_list", reminders.status_code == 200, f"status={reminders.status_code}")

    reservations = api_get(base_url, "/api/v1/reservations/my", headers=headers)
    rec.add("api_reservations_list", reservations.status_code == 200, f"status={reservations.status_code}")

    license_status = api_get(base_url, "/api/v1/license/status", headers=headers)
    rec.add("api_license_status", license_status.status_code == 200, f"status={license_status.status_code}")

    vin_decode = api_post_json(
        base_url,
        "/api/vehicles/decode-vin",
        {"vin": "WVWZZZ1JZ3W386752"},
        headers=headers,
        timeout=30,
    )
    rec.add("api_decode_vin", vin_decode.status_code in (200, 400), f"status={vin_decode.status_code}")

    created_reminder_id: Optional[int] = None
    reminder_create = api_post_json(
        base_url,
        "/api/v1/reminders",
        {
            "vehicle_id": vehicle_id,
            "type": "other",
            "text": "E2E reminder",
            "due_date": str(date.today() + timedelta(days=7)),
        },
        headers=headers,
    )
    reminder_ok = reminder_create.status_code in (200, 201)
    if reminder_ok:
        try:
            created_reminder_id = reminder_create.json().get("id")
        except Exception:
            created_reminder_id = None
    rec.add("api_reminder_create", reminder_ok, f"status={reminder_create.status_code}")

    if created_reminder_id:
        reminder_update = api_put_json(
            base_url,
            f"/api/v1/reminders/{created_reminder_id}",
            {"text": "E2E reminder updated", "is_completed": False},
            headers=headers,
        )
        rec.add("api_reminder_update", reminder_update.status_code == 200, f"status={reminder_update.status_code}")

        reminder_delete = api_delete(base_url, f"/api/v1/reminders/{created_reminder_id}", headers=headers)
        rec.add("api_reminder_delete", reminder_delete.status_code in (200, 204), f"status={reminder_delete.status_code}")
    else:
        rec.add("api_reminder_update", True, "skipped-no-created-reminder")
        rec.add("api_reminder_delete", True, "skipped-no-created-reminder")

    services = api_get(base_url, "/api/v1/services", headers=headers)
    if services.status_code == 200:
        items = services.json() if isinstance(services.json(), list) else []
        if items and vehicle_id:
            service_id = items[0].get("id")
            start_dt = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0).isoformat()
            reserve = api_post_json(
                base_url,
                "/api/v1/reservations",
                {
                    "service_id": service_id,
                    "vehicle_id": vehicle_id,
                    "start_datetime": start_dt,
                    "note": "E2E reservation",
                },
                headers=headers,
            )
            ok = reserve.status_code in (200, 201)
            rec.add("api_reservation_create", ok, f"status={reserve.status_code}")
            if ok:
                reservation_id = reserve.json().get("id")
                if reservation_id:
                    delete_res = api_delete(base_url, f"/api/v1/reservations/{reservation_id}", headers=headers)
                    rec.add(
                        "api_reservation_delete",
                        delete_res.status_code in (200, 204),
                        f"status={delete_res.status_code}",
                    )
                else:
                    rec.add("api_reservation_delete", True, "skipped-no-reservation-id")
            else:
                rec.add("api_reservation_delete", True, "skipped-create-failed")
        else:
            rec.add("api_reservation_create", True, "skipped-no-services-or-vehicle")
            rec.add("api_reservation_delete", True, "skipped-no-services-or-vehicle")
    elif services.status_code in (401, 403, 404):
        rec.add("api_reservation_create", True, f"skipped-services-status={services.status_code}")
        rec.add("api_reservation_delete", True, "skipped-services-unavailable")
    else:
        rec.add("api_reservation_create", False, f"services-status={services.status_code}")
        rec.add("api_reservation_delete", True, "skipped-services-unavailable")


def save_report(base_url: str, email: str, rec: Recorder, report_path: Path) -> None:
    payload = {
        "generated_at": now_iso(),
        "base_url": base_url,
        "email": email,
        "all_ok": rec.all_ok(),
        "steps": rec.to_dict(),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    email, password = default_credentials()
    python_bin = sys.executable
    report_path = Path(os.getenv("E2E_REPORT", str(PROJECT_ROOT / "logs" / "e2e_browser_agent_report.json")))

    rec = Recorder()

    try:
        ensure_playwright_browser(rec, python_bin)
        ensure_local_runtime_libs(rec)
        ensure_test_user(base_url, email, password, rec)
        token, vehicle_id = run_ui_flow(base_url, email, password, rec)
        run_api_flow(base_url, token, vehicle_id, rec)
    except Exception as exc:  # pragma: no cover - runtime safety
        rec.add("fatal_exception", False, repr(exc))

    save_report(base_url, email, rec, report_path)
    print(f"REPORT={report_path}")
    print(f"ALL_OK={1 if rec.all_ok() else 0}")
    return 0 if rec.all_ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
