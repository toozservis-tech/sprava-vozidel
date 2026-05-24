#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import secrets
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright
from sqlalchemy import func

sys.path.insert(0, "/opt/toozhub2/app")

from src.modules.vehicle_hub.database import SessionLocal
from src.modules.vehicle_hub.models import Customer, ServiceCustomerInvite


BASE_URL = "http://127.0.0.1:8010"
PASSWORD = "RcVerify123!"
REPORT_PATH = Path("/opt/toozhub2/app/artifacts/qa/service-shell-rc-verify.json")


@dataclass
class StepResult:
    step: str
    ok: bool
    info: str = ""


class Recorder:
    def __init__(self) -> None:
        self.steps: list[StepResult] = []

    def add(self, step: str, ok: bool, info: str = "") -> None:
        self.steps.append(StepResult(step=step, ok=ok, info=info))
        status = "OK" if ok else "FAIL"
        suffix = f" - {info}" if info else ""
        print(f"[{status}] {step}{suffix}")

    def write(self, extra: dict[str, Any]) -> None:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(
                {
                    "generated_at": datetime.utcnow().isoformat(),
                    "base_url": BASE_URL,
                    "extra": extra,
                    "steps": [asdict(step) for step in self.steps],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def register_user(prefix: str, name: str, password: str = PASSWORD) -> tuple[str, str, int]:
    suffix = str(int(time.time() * 1000))
    email = f"{prefix}_{suffix}@example.com"
    response = requests.post(
        f"{BASE_URL}/user/register",
        json={"email": email, "password": password, "name": name, "phone": "+420123456789"},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    return email, payload["access_token"], int(payload["user"]["id"])


def create_vehicle(token: str, nickname: str, plate: str, vin: str) -> int:
    response = requests.post(
        f"{BASE_URL}/api/v1/vehicles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "nickname": nickname,
            "brand": "Skoda",
            "model": "Octavia",
            "year": 2022,
            "plate": plate,
            "vin": vin,
            "stk_valid_until": (date.today() + timedelta(days=365)).isoformat(),
        },
        timeout=15,
    )
    response.raise_for_status()
    return int(response.json()["id"])


def api_post(path: str, token: str, payload: dict[str, Any], *, timeout: int = 15) -> requests.Response:
    return requests.post(
        f"{BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=timeout,
    )


def seed_service_fixture(rec: Recorder) -> dict[str, Any]:
    suffix = str(int(time.time()))
    service_email, service_token, service_id = register_user("svc_rc", "RC Service")
    regular_email, regular_token, _ = register_user("user_rc", "RC Regular User")

    db = SessionLocal()
    try:
        service_customer = db.query(Customer).filter(func.lower(Customer.email) == service_email.lower()).first()
        if not service_customer:
            raise RuntimeError("Seeded service customer not found in DB.")
        service_customer.role = "service"
        db.commit()
        db.refresh(service_customer)
    finally:
        db.close()
    rec.add("seed_promote_service", True, service_email)

    linked_name = f"RC Linked {suffix[-4:]}"
    found_name = f"RC Found {suffix[-4:]}"
    multi_name = f"RC Multi {suffix[-4:]}"
    pending_name = f"RC Pending {suffix[-4:]}"
    approved_name = f"RC Approved Vehicle {suffix[-4:]}"
    pending_access_name = f"RC Pending Access {suffix[-4:]}"
    request_name = f"RC Request Access {suffix[-4:]}"
    conflict_one_name = f"RC Conflict One {suffix[-4:]}"
    conflict_two_name = f"RC Conflict Two {suffix[-4:]}"

    linked_email, linked_token, linked_id = register_user("linked_rc", linked_name)
    found_email, _, found_id = register_user("found_rc", found_name)
    multi1_email, _, _ = register_user("multi1_rc", multi_name)
    multi2_email, _, _ = register_user("multi2_rc", multi_name)
    pending_email, _, _ = register_user("pending_rc", pending_name)
    approved_email, approved_token, approved_id = register_user("approved_rc", approved_name)
    pending_owner_email, pending_owner_token, _ = register_user("pendingaccess_rc", pending_access_name)
    request_email, request_token, _ = register_user("request_rc", request_name)
    conflict1_email, conflict1_token, _ = register_user("conflict1_rc", conflict_one_name)
    conflict2_email, conflict2_token, _ = register_user("conflict2_rc", conflict_two_name)

    db = SessionLocal()
    try:
        pending_invite = ServiceCustomerInvite(
            service_tenant_id=service_customer.tenant_id,
            service_customer_id=service_customer.id,
            invite_email=pending_email,
            invite_name=pending_name,
            token=secrets.token_urlsafe(24),
            status="pending",
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        db.add(pending_invite)
        db.commit()
    finally:
        db.close()
    rec.add("seed_pending_invite", True, pending_email)

    api_post(
        "/api/v1/services/workspace/customers/link-existing",
        service_token,
        {"customer_email": linked_email, "note": "RC linked customer"},
    ).raise_for_status()
    api_post(
        "/api/v1/services/workspace/customers/link-existing",
        service_token,
        {"customer_email": approved_email, "note": "RC approved owner"},
    ).raise_for_status()
    rec.add("seed_customer_links", True)

    linked_plate = f"RC{suffix[-4:]}A"
    approved_plate = f"RC{suffix[-4:]}B"
    pending_plate = f"RC{suffix[-4:]}C"
    request_plate = f"RC{suffix[-4:]}F"
    conflict_plate = f"RC{suffix[-4:]}D"
    conflict_vin = ("TMF" + suffix.zfill(14))[:17]

    linked_vehicle_id = create_vehicle(linked_token, "RC Linked Car", linked_plate, ("TMB" + suffix.zfill(14))[:17])
    approved_vehicle_id = create_vehicle(approved_token, "RC Approved Car", approved_plate, ("TMC" + suffix.zfill(14))[:17])
    pending_vehicle_id = create_vehicle(pending_owner_token, "RC Pending Car", pending_plate, ("TMD" + suffix.zfill(14))[:17])
    request_vehicle_id = create_vehicle(request_token, "RC Request Car", request_plate, ("TMG" + suffix.zfill(14))[:17])
    create_vehicle(conflict1_token, "RC Conflict Plate", conflict_plate, ("TME" + suffix.zfill(14))[:17])
    create_vehicle(conflict2_token, "RC Conflict Vin", f"RC{suffix[-4:]}E", conflict_vin)
    rec.add("seed_vehicles", True)

    api_post(
        "/api/v1/services/vehicle-access",
        approved_token,
        {"vehicle_id": approved_vehicle_id, "service_id": service_id, "note": "approved access"},
    ).raise_for_status()
    api_post(
        "/api/v1/services/vehicle-access",
        linked_token,
        {"vehicle_id": linked_vehicle_id, "service_id": service_id, "note": "linked access"},
    ).raise_for_status()
    rec.add("seed_approved_access", True)

    pending_req = api_post(
        "/api/v1/services/access-requests",
        service_token,
        {"vehicle_id": pending_vehicle_id, "lookup_query": pending_plate, "note": "pending access"},
    )
    pending_req.raise_for_status()
    rec.add("seed_pending_access", True)

    reminder = api_post(
        "/api/v1/services/workspace/reminders",
        service_token,
        {
            "customer_id": linked_id,
            "vehicle_id": linked_vehicle_id,
            "type": "SERVIS",
            "text": "RC Reminder",
            "due_date": (date.today() + timedelta(days=5)).isoformat(),
        },
    )
    reminder.raise_for_status()

    document = api_post(
        "/api/v1/services/workspace/documents/ingest",
        service_token,
        {
            "customer_id": linked_id,
            "vehicle_id": linked_vehicle_id,
            "source_type": "invoice",
            "manual_text": "Faktura RC-001\nPolozka 1 ks 1000 Kč\nCelkem 1000 Kč",
            "auto_create_service_record": True,
        },
        timeout=25,
    )
    document.raise_for_status()

    start = (datetime.utcnow() + timedelta(days=1)).replace(microsecond=0)
    reservation = api_post(
        "/api/v1/reservations",
        service_token,
        {
            "service_id": service_id,
            "vehicle_id": linked_vehicle_id,
            "service_type": "RC Reservation",
            "note": "rc verify reservation",
            "start_datetime": start.isoformat(),
            "end_datetime": (start + timedelta(hours=1)).isoformat(),
        },
    )
    reservation.raise_for_status()
    rec.add("seed_detail_entities", True)

    work_order_awaiting = api_post(
        "/api/service/work-orders",
        service_token,
        {
            "owner_id": linked_id,
            "vehicle_id": linked_vehicle_id,
            "technician_id": service_id,
            "title": "RC Work Order Awaiting",
            "description": "awaiting desc",
            "due_date": (date.today() + timedelta(days=2)).isoformat(),
            "status": "awaiting_client_approval",
            "source_type": "manual",
        },
    )
    work_order_awaiting.raise_for_status()
    work_order_active = api_post(
        "/api/service/work-orders",
        service_token,
        {
            "owner_id": approved_id,
            "vehicle_id": approved_vehicle_id,
            "technician_id": service_id,
            "title": "RC Active Order",
            "description": "active desc",
            "due_date": (date.today() + timedelta(days=1)).isoformat(),
            "status": "in_progress",
            "source_type": "manual",
        },
    )
    work_order_active.raise_for_status()
    rec.add("seed_work_orders", True)

    return {
        "service_email": service_email,
        "service_password": PASSWORD,
        "regular_email": regular_email,
        "regular_password": PASSWORD,
        "found_customer_name": found_name,
        "linked_customer_name": linked_name,
        "multi_customer_name": multi_name,
        "pending_customer_name": pending_name,
        "not_found_customer_query": f"rc-none-{suffix}",
        "approved_vehicle_plate": approved_plate,
        "pending_vehicle_plate": pending_plate,
        "request_vehicle_plate": request_plate,
        "linked_vehicle_plate": linked_plate,
        "not_found_vehicle_query": "RC-NOT-FOUND",
        "conflict_query": f"{conflict_plate} {conflict_vin}",
        "approved_customer_name": approved_name,
        "awaiting_work_order_title": "RC Work Order Awaiting",
        "active_work_order_title": "RC Active Order",
        "new_work_order_title": f"RC UI Order {suffix}",
    }


def safe_click(page: Page, selector: str, rec: Recorder, step: str, timeout: int = 10000) -> bool:
    try:
        page.locator(selector).click(timeout=timeout)
        rec.add(step, True)
        return True
    except Exception as exc:
        rec.add(step, False, repr(exc))
        return False


def close_modal(page: Page, rec: Recorder, step: str) -> None:
    try:
        page.locator(".service-shell-modal-close").click(timeout=5000)
        page.locator(".service-shell-modal").wait_for(state="hidden", timeout=5000)
        rec.add(step, True)
    except Exception as exc:
        rec.add(step, False, f"close button failed: {exc!r}")
        page.evaluate("window.serviceShell?.closeModal?.()")
        page.wait_for_timeout(300)


def run_service_browser_flow(fixture: dict[str, Any], rec: Recorder) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        try:
            page.goto(f"{BASE_URL}/web/index.html", wait_until="domcontentloaded", timeout=30000)
            page.click("#loginModeServiceBtn")
            page.fill("#loginEmail", fixture["service_email"])
            page.fill("#loginPassword", fixture["service_password"])
            page.click("#loginSubmitBtn")
            page.wait_for_selector('[data-service-shell="root"]', timeout=20000)
            rec.add("browser_service_login", True)

            original_class = page.locator("body").get_attribute("class") or ""
            page.locator('button[aria-label="Přepnout motiv"]').click()
            page.wait_for_timeout(400)
            rec.add("browser_dark_light_toggle", original_class != (page.locator("body").get_attribute("class") or ""))

            page.locator('button[aria-label="Účet servisu"]').click()
            page.locator(".service-shell-account-menu").wait_for(state="visible", timeout=5000)
            rec.add("browser_account_menu_open", True)

            page.locator('button:has-text("Otevřít nastavení účtu")').click()
            page.locator(".service-shell-modal-title").filter(has_text="Nastavení účtu").wait_for(timeout=5000)
            rec.add("browser_account_settings_open", True)
            close_modal(page, rec, "browser_account_settings_close")

            page.locator('button[aria-label="Účet servisu"]').click()
            page.locator('button:has-text("Otevřít profil")').click()
            page.locator('[data-service-shell="root"]').filter(has_text="Aktivní technici").wait_for(timeout=10000)
            rec.add("browser_profile_open", True)

            page.locator('button[aria-label="Účet servisu"]').click()
            page.locator('button:has-text("Odhlásit se")').click()
            page.locator('[data-testid="login-form"]').wait_for(timeout=10000)
            rec.add("browser_logout_to_login", True)

            page.click("#loginModeServiceBtn")
            page.fill("#loginEmail", fixture["service_email"])
            page.fill("#loginPassword", fixture["service_password"])
            page.click("#loginSubmitBtn")
            page.wait_for_selector('[data-service-shell="root"]', timeout=20000)
            rec.add("browser_service_relogin", True)

            page.locator('button[aria-label="Servisní nástroje"]').click()
            page.locator(".service-shell-modal-title").filter(has_text="Najít nebo vytvořit").wait_for(timeout=5000)
            rec.add("browser_service_tools_open", True)

            customer_input = page.locator('input[placeholder="email, telefon nebo jméno"]')
            customer_input.fill(fixture["found_customer_name"])
            page.locator('button:has-text("Hledat klienta")').click()
            page.locator(".service-shell-modal").filter(has_text=fixture["found_customer_name"]).wait_for(timeout=8000)
            rec.add("browser_customer_search_found", True)

            customer_input.fill(fixture["not_found_customer_query"])
            page.locator('button:has-text("Hledat klienta")').click()
            page.locator(".service-shell-modal").filter(has_text="Zatím žádné výsledky.").wait_for(timeout=8000)
            rec.add("browser_customer_search_not_found", True)

            customer_input.fill(fixture["multi_customer_name"])
            page.locator('button:has-text("Hledat klienta")').click()
            page.locator(".service-shell-modal").filter(has_text="Nalezeno více podobných klientů").wait_for(timeout=8000)
            rec.add("browser_customer_search_multiple", True)

            customer_input.fill(fixture["pending_customer_name"])
            page.locator('button:has-text("Hledat klienta")').click()
            page.locator(".service-shell-modal").filter(has_text="Pozvánka").wait_for(timeout=8000)
            rec.add("browser_customer_search_pending_invitation", True)

            customer_input.fill(fixture["linked_customer_name"])
            page.locator('button:has-text("Hledat klienta")').click()
            page.locator(".service-shell-modal").filter(has_text="Otevřít").wait_for(timeout=8000)
            rec.add("browser_customer_search_already_linked", True)

            customer_input.fill(fixture["found_customer_name"])
            page.locator('button:has-text("Hledat klienta")').click()
            page.locator(".service-shell-list-row").filter(has_text=fixture["found_customer_name"]).locator('button:has-text("Propojit")').click()
            page.locator(".service-shell-modal").filter(has_text="Otevřít").wait_for(timeout=10000)
            rec.add("browser_customer_link_action", True)
            close_modal(page, rec, "browser_service_tools_close_after_link")

            page.get_by_role("button", name="Klienti").click()
            page.locator("tr").filter(has_text=fixture["found_customer_name"]).first.wait_for(timeout=10000)
            rec.add("browser_parent_refresh_after_link", True)

            page.locator('button[aria-label="Servisní nástroje"]').click()
            vehicle_input = page.locator('input[placeholder="VIN nebo SPZ"]')

            vehicle_input.fill(fixture["approved_vehicle_plate"])
            page.locator('button:has-text("Hledat vozidlo")').click()
            page.locator(".service-shell-modal").filter(has_text="Nová zakázka").wait_for(timeout=8000)
            rec.add("browser_vehicle_lookup_approved", True)

            vehicle_input.fill(fixture["pending_vehicle_plate"])
            page.locator('button:has-text("Hledat vozidlo")').click()
            page.locator(".service-shell-modal").filter(has_text="Čeká").wait_for(timeout=8000)
            rec.add("browser_vehicle_lookup_pending_access", True)

            vehicle_input.fill(fixture["request_vehicle_plate"])
            page.locator('button:has-text("Hledat vozidlo")').click()
            page.locator('button:has-text("Požádat o přístup")').click()
            page.locator(".service-shell-modal").filter(has_text="Čeká").wait_for(timeout=10000)
            rec.add("browser_vehicle_request_access", True)

            vehicle_input.fill(fixture["conflict_query"])
            page.locator('button:has-text("Hledat vozidlo")').click()
            page.wait_for_timeout(800)
            conflict_text = page.locator(".service-shell-modal").text_content() or ""
            rec.add(
                "browser_vehicle_lookup_conflict",
                ("Konfliktní identifikace" in conflict_text) or ("VIN a SPZ ukazují" in conflict_text),
                conflict_text[:200],
            )

            vehicle_input.fill(fixture["not_found_vehicle_query"])
            page.locator('button:has-text("Hledat vozidlo")').click()
            page.locator(".service-shell-modal").filter(has_text="Zatím žádné výsledky.").wait_for(timeout=8000)
            rec.add("browser_vehicle_lookup_not_found", True)
            close_modal(page, rec, "browser_service_tools_close_after_vehicle_checks")

            page.get_by_role("button", name="Klienti").click()
            page.locator("tr").filter(has_text=fixture["linked_customer_name"]).first.click()
            page.locator(".service-shell-modal-title").filter(has_text="Detail klienta").wait_for(timeout=8000)
            rec.add("browser_customer_detail_open", True)
            close_modal(page, rec, "browser_customer_detail_close")

            page.get_by_role("button", name="Vozidla").click()
            page.locator("tr").filter(has_text=fixture["approved_vehicle_plate"]).first.click()
            page.locator(".service-shell-modal-title").filter(has_text="Detail vozidla").wait_for(timeout=8000)
            rec.add("browser_vehicle_detail_open", True)
            close_modal(page, rec, "browser_vehicle_detail_close")

            page.get_by_role("button", name="Dokumenty").click()
            page.locator("table tbody tr").first.click()
            page.locator(".service-shell-modal-title").filter(has_text="Detail dokumentu").wait_for(timeout=8000)
            rec.add("browser_document_detail_open", True)
            close_modal(page, rec, "browser_document_detail_close")

            page.get_by_role("button", name="Rezervace").click()
            page.locator("table tbody tr").first.click()
            page.locator(".service-shell-modal-title").filter(has_text="Detail rezervace").wait_for(timeout=8000)
            rec.add("browser_reservation_detail_open", True)
            close_modal(page, rec, "browser_reservation_detail_close")

            page.get_by_role("button", name="Připomínky").click()
            page.locator("table tbody tr").first.click()
            page.locator(".service-shell-modal-title").filter(has_text="Detail připomínky").wait_for(timeout=8000)
            rec.add("browser_reminder_detail_open", True)
            close_modal(page, rec, "browser_reminder_detail_close")

            page.locator('button:has-text("+ Nová zakázka")').click()
            page.locator(".service-shell-modal-title").filter(has_text="Nová zakázka").wait_for(timeout=5000)
            page.select_option("#serviceShellWorkOrderOwner", label=fixture["approved_customer_name"])
            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('#serviceShellWorkOrderVehicle option')).some((option) => option.value)",
                timeout=8000,
            )
            page.select_option("#serviceShellWorkOrderVehicle", index=0)
            page.fill("#serviceShellWorkOrderTitle", fixture["new_work_order_title"])
            page.fill("#serviceShellWorkOrderDueDate", (date.today() + timedelta(days=4)).isoformat())
            page.locator('button:has-text("Uložit zakázku")').click()
            page.wait_for_timeout(1500)
            if page.locator(".service-shell-modal").count():
                modal_text = page.locator(".service-shell-modal").text_content() or ""
                rec.add("browser_work_order_create", False, modal_text[:240])
                page.evaluate("window.serviceShell?.closeModal?.()")
                page.wait_for_timeout(300)
            else:
                page.get_by_role("button", name="Zakázky").click()
                page.locator("tr").filter(has_text=fixture["new_work_order_title"]).first.wait_for(timeout=12000)
                rec.add("browser_work_order_create", True)

            page.locator('button:has-text("+ Nová zakázka")').click()
            page.locator(".service-shell-modal-title").filter(has_text="Nová zakázka").wait_for(timeout=5000)
            page.select_option("#serviceShellWorkOrderOwner", label=fixture["linked_customer_name"])
            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('#serviceShellWorkOrderVehicle option')).some((option) => option.value)",
                timeout=8000,
            )
            page.select_option("#serviceShellWorkOrderVehicle", index=0)
            page.fill("#serviceShellWorkOrderTitle", "RC Browser Duplicate Attempt")
            page.fill("#serviceShellWorkOrderDueDate", (date.today() + timedelta(days=5)).isoformat())
            page.locator('button:has-text("Uložit zakázku")').click()
            page.wait_for_timeout(1500)
            duplicate_modal_text = page.locator(".service-shell-modal").text_content() if page.locator(".service-shell-modal").count() else ""
            if not page.locator(".service-shell-modal").count():
                page.get_by_role("button", name="Zakázky").click()
                page.wait_for_timeout(500)
            duplicate_visible = page.locator('[data-service-shell="root"]').filter(has_text="RC Browser Duplicate Attempt").count()
            duplicate_lower = duplicate_modal_text.lower() if duplicate_modal_text else ""
            duplicate_rejected = any(
                token in duplicate_lower
                for token in ("duplicit", "už existuje", "otevřená zakázka", "nelze založit duplicitní")
            )
            rec.add(
                "browser_duplicate_work_order_reject",
                duplicate_rejected and duplicate_visible == 0,
                duplicate_modal_text[:240] if duplicate_modal_text else "duplicate order unexpectedly created",
            )
            page.evaluate("window.serviceShell?.closeModal?.()")
            page.wait_for_timeout(300)

            page.get_by_role("button", name="Dashboard").click()
            awaiting_card = page.locator(".service-shell-kpi").nth(1)
            awaiting_before = awaiting_card.text_content() or ""
            page.locator("tr").filter(has_text=fixture["awaiting_work_order_title"]).first.click()
            page.locator(".service-shell-modal-title").filter(has_text="Detail zakázky").wait_for(timeout=8000)
            page.select_option("#serviceShellDetailStatus", "completed")
            page.locator('button:has-text("Uložit změny")').click()
            page.locator("tr").filter(has_text=fixture["awaiting_work_order_title"]).first.wait_for(timeout=10000)
            rec.add("browser_work_order_update", True)
            awaiting_after = awaiting_card.text_content() or ""
            rec.add("browser_parent_refresh_after_work_order_update", "Dokončeno" in (page.locator("tr").filter(has_text=fixture["awaiting_work_order_title"]).first.text_content() or ""))
            rec.add("browser_kpi_refresh_after_work_order_update", awaiting_before != awaiting_after, f"{awaiting_before} -> {awaiting_after}")

            page.locator(".service-shell-kpi").nth(0).click()
            page.wait_for_timeout(500)
            rec.add("browser_kpi_click_active", True)
            page.locator(".service-shell-kpi").nth(1).click()
            page.wait_for_timeout(500)
            rec.add("browser_kpi_click_awaiting", True)
            page.locator(".service-shell-kpi").nth(3).click()
            page.wait_for_timeout(500)
            rec.add("browser_kpi_click_overdue", True)

            page.locator(".service-shell-side-card").filter(has_text="Fronta práce").locator(".service-shell-list-row").nth(0).click()
            page.wait_for_timeout(500)
            rec.add("browser_queue_click_new_jobs", True)
            page.locator(".service-shell-side-card").filter(has_text="Fronta práce").locator(".service-shell-list-row").nth(1).click()
            page.wait_for_timeout(500)
            rec.add("browser_queue_click_awaiting", True)

            modal_count = page.locator(".service-shell-modal-overlay").count()
            rec.add("browser_modal_root_lifecycle_clean", modal_count == 0, f"overlays={modal_count}")
        except PWTimeout as exc:
            rec.add("browser_timeout", False, str(exc))
            page.screenshot(path="/tmp/service_shell_rc_verify_timeout.png", full_page=True)
        except Exception as exc:
            rec.add("browser_exception", False, repr(exc))
            page.screenshot(path="/tmp/service_shell_rc_verify_exception.png", full_page=True)
        finally:
            browser.close()


def run_regular_user_regression(fixture: dict[str, Any], rec: Recorder) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        try:
            page.goto(f"{BASE_URL}/web/index.html", wait_until="domcontentloaded", timeout=30000)
            page.fill("#loginEmail", fixture["regular_email"])
            page.fill("#loginPassword", fixture["regular_password"])
            page.click("#loginSubmitBtn")
            page.locator('[data-testid="dashboard"]').wait_for(timeout=15000)
            rec.add("regression_user_login", True)
            for tab_id, step in [
                ("[data-testid='tab-vehicles']", "regression_user_vehicles"),
                ("[data-testid='tab-reminders']", "regression_user_reminders"),
                ("[data-testid='tab-reservations']", "regression_user_reservations"),
                ("[data-testid='tab-documents']", "regression_user_documents"),
                ("[data-testid='tab-account']", "regression_user_account"),
            ]:
                page.locator(tab_id).click()
                page.wait_for_timeout(600)
                rec.add(step, True)
            page.locator("[data-testid='btn-logout']").click()
            page.locator("[data-testid='login-form']").wait_for(timeout=10000)
            rec.add("regression_user_logout", True)
        except Exception as exc:
            rec.add("regression_user_browser", False, repr(exc))
        finally:
            browser.close()


def main() -> int:
    rec = Recorder()
    fixture = seed_service_fixture(rec)
    run_service_browser_flow(fixture, rec)
    run_regular_user_regression(fixture, rec)
    rec.write(fixture)
    print(f"report: {REPORT_PATH}")
    failed = [step for step in rec.steps if not step.ok]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
