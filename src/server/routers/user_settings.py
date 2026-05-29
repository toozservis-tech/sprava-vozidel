"""
User settings facade API — /api/v1/user/settings/*
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func

from src.core.auth import get_current_user_email
from src.core.security import hash_password, verify_password
from src.modules.licensing.service import get_license_status
from src.modules.vehicle_hub.account_state import increment_customer_session_version
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import (
    Customer,
    LicensePaymentTransaction,
    LicenseSubscription,
    ServiceCustomerLink,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.ownership import get_owned_vehicle_ids
from src.server.main_helpers import (
    ChangePasswordRequest,
    SupportContactRequest,
    UserUpdate,
    export_current_customer_bundle,
    get_customer_by_email,
)
from src.server.security_helpers import get_or_create_security_settings
from src.server.security_tracking import log_security_event, log_user_activity
from src.server.user_settings_helpers import (
    account_type_label,
    count_active_reminders,
    deep_merge,
    enforce_notification_rules,
    format_address,
    get_user_preferences,
    list_login_devices,
    list_login_history,
    mask_email,
    mask_phone,
    password_strength_label,
    set_user_preferences,
)


router = APIRouter(prefix="/user/settings", tags=["user-settings"])


class SettingsProfilePatch(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    street: Optional[str] = None
    street_number: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    preferred_language: Optional[str] = Field(default=None, max_length=16)
    preferred_contact: Optional[str] = Field(default=None, max_length=16)


class SettingsNotificationsPatch(BaseModel):
    master: Optional[bool] = None
    quiet_mode: Optional[str] = Field(default=None, max_length=32)
    channels: Optional[Dict[str, bool]] = None
    types: Optional[Dict[str, Dict[str, bool]]] = None
    notify_email: Optional[bool] = None
    notify_sms: Optional[bool] = None
    notify_stk: Optional[bool] = None
    notify_oil: Optional[bool] = None
    notify_general: Optional[bool] = None


class SettingsPrivacyPatch(BaseModel):
    third_party: Optional[bool] = None
    personalization: Optional[bool] = None
    marketing: Optional[bool] = None


class SettingsGaragePatch(BaseModel):
    default_units: Optional[str] = Field(default=None, max_length=32)
    default_currency: Optional[str] = Field(default=None, max_length=16)
    mdcr_auto_update: Optional[bool] = None


class SettingsDocumentsPatch(BaseModel):
    auto_sort: Optional[bool] = None
    default_category: Optional[str] = Field(default=None, max_length=64)
    smart_naming: Optional[bool] = None


class SettingsServicesPatch(BaseModel):
    allow_vehicle_access: Optional[bool] = None
    allow_communication: Optional[bool] = None


class SettingsSecurityEmailsPatch(BaseModel):
    login: Optional[bool] = None
    account_changes: Optional[bool] = None


class SettingsSupportFeedbackRequest(BaseModel):
    category: str = Field(default="zpětná vazba", max_length=64)
    subject: str = Field(min_length=3, max_length=180)
    message: str = Field(min_length=10, max_length=4000)
    feedback_type: Optional[str] = Field(default=None, max_length=64)


def _require_customer(db, email: str) -> Customer:
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    return customer


def _license_summary(db, customer: Customer) -> Dict[str, Any]:
    status = get_license_status(db, customer.tenant_id, user_email=customer.email)
    sub = (
        db.query(LicenseSubscription)
        .filter(LicenseSubscription.tenant_id == customer.tenant_id)
        .first()
    )
    subscription = None
    if sub:
        subscription = {
            "status": sub.status,
            "plan_current": sub.plan_current,
            "auto_renew_enabled": bool(sub.auto_renew_enabled),
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "cancel_requested_at": sub.cancel_requested_at.isoformat() if sub.cancel_requested_at else None,
        }
    safe = {k: v for k, v in status.items() if k != "tenant_id"}
    safe["subscription"] = subscription
    return safe


def _documents_counts(db, customer: Customer) -> Dict[str, Any]:
    try:
        from src.modules.vehicle_hub.routers_v1.service_records import get_documents_hub_summary

        hub = get_documents_hub_summary(
            attachments_limit=30,
            reports_limit=20,
            tachometer_limit=20,
            current_user=customer,
            db=db,
        )
        if hasattr(hub, "model_dump"):
            data = hub.model_dump()
        elif isinstance(hub, dict):
            data = hub
        else:
            data = {}
        total = (
            int(data.get("attachments_total") or 0)
            + int(data.get("reports_total") or 0)
            + int(data.get("tachometer_documents_total") or 0)
            + int(data.get("technical_certificates_total") or 0)
        )
        return {"total": total, "hub": data}
    except Exception:
        return {"total": 0, "hub": {}}


@router.get("")
def get_settings_snapshot(
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = _require_customer(db, email)
    prefs = get_user_preferences(customer)
    security = get_or_create_security_settings(db, customer)
    license_data = _license_summary(db, customer)
    docs = _documents_counts(db, customer)
    reminders_count = count_active_reminders(db, customer)
    vehicle_ids = list(get_owned_vehicle_ids(db, customer, tenant_id=customer.tenant_id))
    vehicles_count = len(vehicle_ids)

    return {
        "profile": {
            "name": customer.name,
            "email_masked": mask_email(customer.email),
            "phone_masked": mask_phone(customer.phone or customer.phone_e164),
            "phone_verified": customer.phone_verified_at is not None,
            "email_verified": customer.email_verified_at is not None,
            "address": format_address(customer),
            "preferred_language": prefs.get("preferred_language", "cs"),
            "preferred_contact": prefs.get("preferred_contact", "email"),
            "account_type": account_type_label(customer),
            "role_label": "Uživatel" if str(customer.role or "user") == "user" else str(customer.role),
            "account_status": "Aktivní" if not customer.is_disabled else "Deaktivovaný",
            "registered_at": customer.created_at.isoformat() if customer.created_at else None,
            "last_login_at": customer.last_login_at.isoformat() if customer.last_login_at else None,
        },
        "preferences": prefs,
        "license": license_data,
        "usage": {
            "vehicles_count": vehicles_count,
            "vehicles_limit": license_data.get("vehicles_limit"),
            "vehicles_remaining": license_data.get("vehicles_remaining"),
            "documents_count": docs.get("total", 0),
            "reminders_active": reminders_count,
        },
        "security": {
            "two_factor_enabled": bool(security.two_factor_enabled),
            "password_strength": password_strength_label(customer),
            "password_last_changed_at": None,
        },
        "app_version": None,
    }


@router.patch("/profile")
def patch_profile(
    payload: SettingsProfilePatch,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = _require_customer(db, email)
    prefs = get_user_preferences(customer)
    data = payload.model_dump(exclude_unset=True)
    pref_fields = {}
    if "preferred_language" in data:
        pref_fields["preferred_language"] = data.pop("preferred_language")
    if "preferred_contact" in data:
        pref_fields["preferred_contact"] = data.pop("preferred_contact")
    if pref_fields:
        prefs = deep_merge(prefs, pref_fields)
        set_user_preferences(customer, prefs)

    if data:
        user_update = UserUpdate(**data)
        update_data = user_update.model_dump(exclude_unset=True)
        if "phone" in update_data:
            from src.modules.vehicle_hub.registration_security import normalize_validate_phone_e164

            raw_phone = update_data.pop("phone")
            if raw_phone is None or str(raw_phone).strip() == "":
                customer.phone = None
                customer.phone_e164 = None
                customer.phone_verified_at = None
            else:
                try:
                    new_e164 = normalize_validate_phone_e164(str(raw_phone))
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                if new_e164 != (customer.phone_e164 or None):
                    customer.phone_verified_at = None
                customer.phone_e164 = new_e164
                customer.phone = str(raw_phone).strip()
        for field, value in update_data.items():
            if hasattr(customer, field):
                setattr(customer, field, value)

    db.commit()
    db.refresh(customer)
    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_settings_profile_patch"},
    )
    return {"ok": True, "profile": {"name": customer.name}}


@router.patch("/notifications")
def patch_notifications(
    payload: SettingsNotificationsPatch,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = _require_customer(db, email)
    prefs = get_user_preferences(customer)
    patch: Dict[str, Any] = {"notifications": {}}
    data = payload.model_dump(exclude_unset=True)
    legacy_map = {
        "notify_email": "notify_email",
        "notify_sms": "notify_sms",
        "notify_stk": "notify_stk",
        "notify_oil": "notify_oil",
        "notify_general": "notify_general",
    }
    for key, attr in legacy_map.items():
        if key in data:
            setattr(customer, attr, data.pop(key))
    for key in ("master", "quiet_mode", "channels", "types"):
        if key in data:
            patch["notifications"][key] = data[key]
    prefs = deep_merge(prefs, patch)
    prefs = enforce_notification_rules(prefs)
    set_user_preferences(customer, prefs)
    db.commit()
    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_settings_notifications_patch"},
    )
    return {"ok": True, "preferences": prefs.get("notifications")}


@router.patch("/privacy")
def patch_privacy(
    payload: SettingsPrivacyPatch,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = _require_customer(db, email)
    prefs = get_user_preferences(customer)
    patch = {"privacy": payload.model_dump(exclude_unset=True)}
    prefs = deep_merge(prefs, patch)
    prefs = enforce_notification_rules(prefs)
    set_user_preferences(customer, prefs)
    db.commit()
    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_settings_privacy_patch"},
    )
    return {"ok": True, "privacy": prefs.get("privacy")}


@router.patch("/garage")
def patch_garage(
    payload: SettingsGaragePatch,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = _require_customer(db, email)
    prefs = get_user_preferences(customer)
    prefs = deep_merge(prefs, {"garage": payload.model_dump(exclude_unset=True)})
    set_user_preferences(customer, prefs)
    db.commit()
    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_settings_garage_patch"},
    )
    return {"ok": True, "garage": prefs.get("garage")}


@router.patch("/documents")
def patch_documents_settings(
    payload: SettingsDocumentsPatch,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = _require_customer(db, email)
    prefs = get_user_preferences(customer)
    prefs = deep_merge(prefs, {"documents": payload.model_dump(exclude_unset=True)})
    set_user_preferences(customer, prefs)
    db.commit()
    return {"ok": True, "documents": prefs.get("documents")}


@router.patch("/services")
def patch_services_settings(
    payload: SettingsServicesPatch,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = _require_customer(db, email)
    prefs = get_user_preferences(customer)
    prefs = deep_merge(prefs, {"services": payload.model_dump(exclude_unset=True)})
    set_user_preferences(customer, prefs)
    db.commit()
    return {"ok": True, "services": prefs.get("services")}


@router.get("/security")
def get_security_settings_bundle(
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = _require_customer(db, email)
    security = get_or_create_security_settings(db, customer)
    prefs = get_user_preferences(customer)
    devices = list_login_devices(db, customer)
    return {
        "password_strength": password_strength_label(customer),
        "password_last_changed_at": None,
        "two_factor_enabled": bool(security.two_factor_enabled),
        "totp_configured": bool(security.totp_secret),
        "devices": devices,
        "devices_total": len(devices),
        "security_emails": prefs.get("security_emails", {}),
    }


@router.get("/security/login-history")
def get_login_history(
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = _require_customer(db, email)
    return {"items": list_login_history(db, customer)}


@router.post("/security/change-password")
def settings_change_password(
    payload: ChangePasswordRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = _require_customer(db, email)
    if not customer.password_hash:
        raise HTTPException(status_code=400, detail="Uživatel nemá nastavené heslo")
    if not verify_password(payload.current_password, customer.password_hash):
        raise HTTPException(status_code=400, detail="Neplatné současné heslo")
    if not payload.new_password or len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Nové heslo musí mít alespoň 6 znaků")
    customer.password_hash = hash_password(payload.new_password)
    if hasattr(customer, "force_password_change"):
        customer.force_password_change = False
    db.commit()
    log_security_event(
        event_type="password_changed",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_settings_change_password"},
    )
    return {"ok": True, "message": "Heslo bylo změněno."}


@router.post("/security/logout-all")
def settings_logout_all_devices(
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = _require_customer(db, email)
    new_sv = increment_customer_session_version(customer)
    db.commit()
    log_security_event(
        event_type="logout_all_devices",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_settings_logout_all", "session_version": new_sv},
    )
    return {
        "ok": True,
        "message": "Všechna ostatní přihlášení byla ukončena. Pro jistotu se přihlaste znovu.",
        "session_version": new_sv,
        "requires_relogin": True,
    }


@router.get("/license")
def get_license_settings(
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = _require_customer(db, email)
    license_data = _license_summary(db, customer)
    try:
        from src.modules.vehicle_hub.routers_v1.license_status import _load_comgate_config

        cfg = _load_comgate_config()
        comgate = {
            "enabled": bool(cfg.get("enabled") and cfg.get("configured")),
            "configured": bool(cfg.get("configured")),
            "plans": cfg.get("plans") or {},
        }
    except Exception:
        comgate = {"enabled": False, "configured": False, "plans": {}}
    docs = _documents_counts(db, customer)
    reminders_count = count_active_reminders(db, customer)
    return {
        "license": license_data,
        "comgate": comgate,
        "usage": {
            "vehicles_count": len(list(get_owned_vehicle_ids(db, customer, tenant_id=customer.tenant_id))),
            "documents_count": docs.get("total", 0),
            "reminders_active": reminders_count,
        },
    }


@router.get("/billing")
def get_billing_settings(
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = _require_customer(db, email)
    license_data = _license_summary(db, customer)
    sub = (
        db.query(LicenseSubscription)
        .filter(LicenseSubscription.tenant_id == customer.tenant_id)
        .first()
    )
    invoices = (
        db.query(LicensePaymentTransaction)
        .filter(
            LicensePaymentTransaction.tenant_id == customer.tenant_id,
            LicensePaymentTransaction.amount_halers.isnot(None),
        )
        .order_by(LicensePaymentTransaction.created_at.desc())
        .limit(20)
        .all()
    )
    invoice_rows = []
    for idx, row in enumerate(invoices, start=1):
        amount = (row.amount_halers or 0) / 100.0
        invoice_rows.append(
            {
                "invoice_number": f"LIC-{customer.tenant_id}-{row.id}",
                "issued_at": row.created_at.isoformat() if row.created_at else None,
                "period_start": row.period_start.isoformat() if row.period_start else None,
                "period_end": row.period_end.isoformat() if row.period_end else None,
                "amount_czk": amount,
                "status": row.provider_status or row.event_type or "unknown",
                "download_available": False,
            }
        )
    return {
        "license": license_data,
        "billing_profile": {
            "name": customer.name,
            "email": mask_email(customer.email),
            "address": format_address(customer),
            "ico": customer.ico,
            "dic": customer.dic,
        },
        "payment_method": {
            "configured": bool(sub and sub.recurring_ready),
            "label": "Platební karta" if sub and sub.recurring_ready else None,
            "masked": "****" if sub and sub.recurring_ready else None,
            "expires_at": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
            "is_default": bool(sub and sub.auto_renew_enabled),
        },
        "subscription": license_data.get("subscription"),
        "invoices": invoice_rows,
    }


@router.get("/billing/invoices")
def get_billing_invoices(
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    data = get_billing_settings(email=email, db=db)
    return {"invoices": data.get("invoices", [])}


@router.get("/documents/summary")
def get_documents_settings_summary(
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = _require_customer(db, email)
    prefs = get_user_preferences(customer)
    docs = _documents_counts(db, customer)
    hub = docs.get("hub") or {}
    return {
        "total": docs.get("total", 0),
        "attachments_total": hub.get("attachments_total", 0),
        "reports_total": hub.get("reports_total", 0),
        "preferences": prefs.get("documents", {}),
        "storage_limit_gb": None,
        "storage_used_bytes": None,
    }


@router.get("/services-sharing")
def get_services_sharing_settings(
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = _require_customer(db, email)
    prefs = get_user_preferences(customer)
    from src.modules.vehicle_hub.models import ServiceAccessRequest, Vehicle
    from src.modules.vehicle_hub.service_access import masked_plate, masked_vin

    favorites = (
        db.query(ServiceCustomerLink, Customer)
        .join(Customer, ServiceCustomerLink.service_customer_id == Customer.id)
        .filter(
            ServiceCustomerLink.customer_id == customer.id,
            ServiceCustomerLink.status == "active",
            Customer.role.in_(["service", "developer_admin"]),
        )
        .limit(20)
        .all()
    )
    fav_rows = []
    for _, service in favorites:
        profile = {}
        try:
            if service.partner_public_profile:
                profile = json.loads(service.partner_public_profile)
        except Exception:
            profile = {}
        fav_rows.append(
            {
                "service_id": int(service.id),
                "name": service.name or service.email,
                "city": profile.get("city") or service.city or "—",
                "country": profile.get("country") or "Česká republika",
            }
        )

    owned_vehicle_ids = list(get_owned_vehicle_ids(db, customer, tenant_id=customer.tenant_id))
    sharing_rows = []
    pending_count = 0

    pending_requests = (
        db.query(ServiceAccessRequest, Customer, Vehicle)
        .join(Customer, ServiceAccessRequest.service_customer_id == Customer.id)
        .join(Vehicle, ServiceAccessRequest.vehicle_id == Vehicle.id)
        .filter(
            ServiceAccessRequest.owner_customer_id == customer.id,
            ServiceAccessRequest.status == "pending",
        )
        .limit(20)
        .all()
    )
    pending_count = len(pending_requests)
    for req_row, service, vehicle in pending_requests:
        sharing_rows.append(
            {
                "request_id": int(req_row.id),
                "service_id": int(service.id),
                "service_name": service.name or service.email,
                "vehicle_name": vehicle.nickname or vehicle.plate or f"Vozidlo #{vehicle.id}",
                "vehicle_plate_masked": masked_plate(vehicle.plate),
                "vehicle_vin_masked": masked_vin(vehicle.vin),
                "access_level": "view",
                "status": "pending",
                "vehicle_id": int(vehicle.id),
                "reason": req_row.request_message,
                "requested_scope": req_row.requested_scope,
                "requested_at": req_row.requested_at.isoformat() if req_row.requested_at else None,
            }
        )

    if owned_vehicle_ids:
        access_rows = (
            db.query(VehicleServiceLink, Customer, Vehicle)
            .join(Customer, VehicleServiceLink.service_customer_id == Customer.id)
            .join(Vehicle, VehicleServiceLink.vehicle_id == Vehicle.id)
            .filter(
                VehicleServiceLink.owner_customer_id == customer.id,
                VehicleServiceLink.vehicle_id.in_(owned_vehicle_ids),
            )
            .order_by(VehicleServiceLink.updated_at.desc())
            .limit(50)
            .all()
        )
        for access_row, service, vehicle in access_rows:
            status = str(access_row.status or "approved")
            level = "full"
            if access_row.scope_edit_existing_records:
                level = "edit"
            elif access_row.scope_create_service_record and not access_row.scope_edit_existing_records:
                level = "edit"
            elif not access_row.scope_create_service_record:
                level = "view"
            sharing_rows.append(
                {
                    "service_id": int(service.id),
                    "service_name": service.name or service.email,
                    "vehicle_name": vehicle.nickname or vehicle.plate or f"Vozidlo #{vehicle.id}",
                    "access_level": level,
                    "status": status,
                    "vehicle_id": int(vehicle.id),
                }
            )

    active_shares = sum(1 for r in sharing_rows if r.get("status") == "approved")
    return {
        "favorites": fav_rows,
        "sharing": sharing_rows,
        "communication": prefs.get("services", {}),
        "summary": {
            "favorites_count": len(fav_rows),
            "active_shares": active_shares,
            "pending_requests": pending_count,
            "communication_active": bool(prefs.get("services", {}).get("allow_communication", True)),
        },
    }


@router.post("/export-data")
def settings_export_data(
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    from src.server.main_helpers import APP_VERSION, cleanup_export_dir

    customer = _require_customer(db, email)
    tmp_dir_path, zip_path, export_file_name, vehicle_count = export_current_customer_bundle(
        customer,
        email=email,
        db=db,
        app_version=APP_VERSION,
    )
    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_settings_export_data", "vehicles": vehicle_count},
    )
    return FileResponse(
        path=str(zip_path),
        filename=export_file_name,
        media_type="application/zip",
        background=BackgroundTask(cleanup_export_dir, tmp_dir_path),
    )


@router.post("/support-feedback")
def settings_support_feedback(
    payload: SettingsSupportFeedbackRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    from src.server.routers.user_security import contact_support

    support_payload = SupportContactRequest(
        category=payload.category,
        subject=payload.subject,
        message=payload.message,
        include_diagnostics=True,
        page_url=str(request.url.path),
    )
    return contact_support(support_payload, request=request, email=email, db=db)
