#!/usr/bin/env python3
"""
License clickthrough smoke flow for Správa vozidel.

Runs end-to-end flow:
- health/register/login prechecks
- UI login
- license modal open/close
- click upgrade buttons (BASIC + PREMIUM)
- collect license API responses from browser and direct API calls
- write JSON report and screenshot
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = PROJECT_ROOT / "logs" / "license_clickthrough_report.json"
DEFAULT_SCREENSHOT = PROJECT_ROOT / "logs" / "license_clickthrough_final.png"


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
        state = "OK" if ok else "FAIL"
        suffix = f" - {info}" if info else ""
        print(f"[{state}] {step}{suffix}")

    def all_ok(self) -> bool:
        return all(step.ok for step in self.steps)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def post_json(base_url: str, path: str, payload: Dict[str, Any], headers: Dict[str, str] | None = None) -> requests.Response:
    return requests.post(f"{base_url}{path}", json=payload, headers=headers or {}, timeout=30)


def get_json(base_url: str, path: str, headers: Dict[str, str] | None = None) -> requests.Response:
    return requests.get(f"{base_url}{path}", headers=headers or {}, timeout=30)


def run() -> int:
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    headless = os.getenv("E2E_HEADLESS", "1") != "0"
    report_path = Path(os.getenv("LICENSE_REPORT", str(DEFAULT_REPORT)))
    screenshot_path = Path(os.getenv("LICENSE_SCREENSHOT", str(DEFAULT_SCREENSHOT)))

    suffix = f"{int(time.time())}{random.randint(1000, 9999)}"
    email = os.getenv("E2E_EMAIL", f"e2e.license.{suffix}@example.com")
    password = os.getenv("E2E_PASSWORD", "E2eLicense123!")

    rec = Recorder()
    ui_api_events: List[Dict[str, Any]] = []
    ui_alerts: List[str] = []
    direct_api: Dict[str, Any] = {}

    # API precheck
    try:
        health = get_json(base_url, "/health")
        rec.add("api_health", health.status_code == 200, f"status={health.status_code}")
    except Exception as exc:
        rec.add("api_health", False, repr(exc))
        health = None

    try:
        reg = post_json(base_url, "/user/register", {"email": email, "password": password, "name": "E2E License Tester"})
        rec.add("api_register", reg.status_code in (200, 400), f"status={reg.status_code}")
    except Exception as exc:
        rec.add("api_register", False, repr(exc))

    try:
        login = post_json(base_url, "/user/login", {"email": email, "password": password})
        rec.add("api_login_precheck", login.status_code == 200, f"status={login.status_code}")
    except Exception as exc:
        rec.add("api_login_precheck", False, repr(exc))

    token = None
    license_label = ""
    plan_cards_count = 0

    # UI clickthrough
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(viewport={"width": 1440, "height": 960})
            page = context.new_page()

            def on_response(resp):
                url = resp.url
                if "/api/v1/license/status" in url or "/api/v1/license/upgrade" in url:
                    ui_api_events.append(
                        {
                            "method": resp.request.method,
                            "status": resp.status,
                            "url": url,
                        }
                    )

            page.on("response", on_response)

            page.goto(f"{base_url}/web/index.html", wait_until="domcontentloaded", timeout=40000)
            page.wait_for_selector('[data-testid="login-form"]', timeout=15000)
            rec.add("ui_load_login", True)

            page.fill('[data-testid="input-email"]', email)
            page.fill('[data-testid="input-password"]', password)
            page.click('[data-testid="btn-login"]')
            page.wait_for_selector('[data-testid="dashboard"]', timeout=20000)
            rec.add("ui_login", True)

            page.wait_for_selector("#licenseQuickToggle", timeout=10000)
            page.wait_for_timeout(1200)
            license_label = (page.locator("#licenseQuickLabel").inner_text() or "").strip()
            rec.add("ui_license_badge_loaded", "Licence:" in license_label, license_label)

            page.click("#licenseQuickToggle")
            page.wait_for_selector("#licenseModal:not(.hidden)", timeout=10000)
            rec.add("ui_license_modal_open", True)

            plan_cards_count = page.locator("#licenseModal .license-plan-card").count()
            rec.add("ui_license_plan_cards", plan_cards_count == 3, f"count={plan_cards_count}")

            # Vyčistit předchozí alerty (např. "Přihlášení úspěšné"), aby nezkreslily upgrade výsledek.
            page.evaluate(
                "() => { const c = document.getElementById('alertContainer'); if (c) c.innerHTML = ''; }"
            )

            for plan in ("basic", "premium"):
                btn = page.locator(f'#licenseModal .license-plan-card[data-plan="{plan}"] .plan-action-btn')
                if btn.count() == 0:
                    rec.add(f"ui_click_upgrade_{plan}", False, "button-not-found")
                    continue
                if not btn.first.is_enabled():
                    rec.add(f"ui_click_upgrade_{plan}", True, "button-disabled-current-plan")
                    continue

                try:
                    previous_alert = (page.locator("#alertContainer").inner_text() or "").strip()
                    btn.first.click()
                    page.wait_for_function(
                        """
                        (prevText) => {
                          const current = (document.getElementById('alertContainer')?.innerText || '').trim();
                          return current.length > 0 && current !== prevText;
                        }
                        """,
                        arg=previous_alert,
                        timeout=10000,
                    )
                    alert_text = (page.locator("#alertContainer").inner_text() or "").strip()
                    ui_alerts.append(f"{plan.upper()}: {alert_text}")
                    ok = (
                        ("Licence změněna" in alert_text)
                        or ("Nemáte oprávnění" in alert_text)
                        or ("Nepodařilo se změnit licenci" in alert_text)
                    )
                    rec.add(f"ui_click_upgrade_{plan}", ok, alert_text)
                except PWTimeout:
                    rec.add(f"ui_click_upgrade_{plan}", False, "alert-timeout")
                finally:
                    page.wait_for_timeout(500)

                # Pokud se modal zavřel po úspěchu upgradu, znovu otevřít pro další krok
                if page.locator("#licenseModal.hidden").count() > 0:
                    page.click("#licenseQuickToggle")
                    page.wait_for_selector("#licenseModal:not(.hidden)", timeout=10000)

            page.click("#licenseModal .license-modal-close")
            page.wait_for_function(
                "() => document.getElementById('licenseModal')?.classList.contains('hidden') === true",
                timeout=8000,
            )
            rec.add("ui_license_modal_close_button", True)

            page.click("#licenseQuickToggle")
            page.wait_for_selector("#licenseModal:not(.hidden)", timeout=8000)
            page.keyboard.press("Escape")
            page.wait_for_function(
                "() => document.getElementById('licenseModal')?.classList.contains('hidden') === true",
                timeout=8000,
            )
            rec.add("ui_license_modal_close_escape", True)

            token = page.evaluate("() => localStorage.getItem('accessToken')")
            rec.add("ui_token_present", bool(token), "missing-access-token" if not token else "")

            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            rec.add("ui_screenshot_saved", True, str(screenshot_path))

            browser.close()
    except PWTimeout as exc:
        rec.add("ui_timeout", False, str(exc))
    except Exception as exc:
        rec.add("ui_exception", False, repr(exc))

    # Direct API validation for license endpoints
    if token:
        headers = {"Authorization": f"Bearer {token}"}
        try:
            status_resp = get_json(base_url, "/api/v1/license/status", headers=headers)
            direct_api["status"] = {"code": status_resp.status_code, "body": status_resp.text[:1200]}
            rec.add("api_license_status_direct", status_resp.status_code == 200, f"status={status_resp.status_code}")
        except Exception as exc:
            direct_api["status_error"] = repr(exc)
            rec.add("api_license_status_direct", False, repr(exc))

        for plan in ("basic", "premium"):
            try:
                up_resp = post_json(base_url, "/api/v1/license/upgrade", {"plan": plan}, headers=headers)
                direct_api[f"upgrade_{plan}"] = {"code": up_resp.status_code, "body": up_resp.text[:1200]}
                rec.add(f"api_license_upgrade_{plan}_direct", up_resp.status_code in (200, 403), f"status={up_resp.status_code}")
            except Exception as exc:
                direct_api[f"upgrade_{plan}_error"] = repr(exc)
                rec.add(f"api_license_upgrade_{plan}_direct", False, repr(exc))
    else:
        rec.add("api_license_status_direct", False, "skipped-no-token")
        rec.add("api_license_upgrade_basic_direct", False, "skipped-no-token")
        rec.add("api_license_upgrade_premium_direct", False, "skipped-no-token")

    report = {
        "generated_at": now_iso(),
        "base_url": base_url,
        "email": email,
        "headless": headless,
        "all_ok": rec.all_ok(),
        "license_label": license_label,
        "plan_cards_count": plan_cards_count,
        "ui_alerts": ui_alerts,
        "ui_license_api_events": ui_api_events,
        "direct_api": direct_api,
        "steps": [asdict(step) for step in rec.steps],
        "screenshot": str(screenshot_path),
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"REPORT={report_path}")
    print(f"SCREENSHOT={screenshot_path}")
    print(f"ALL_OK={1 if rec.all_ok() else 0}")
    return 0 if rec.all_ok() else 1


if __name__ == "__main__":
    raise SystemExit(run())
