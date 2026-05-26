"""
Servisní workspace API v1.0

Funkce:
- propojení servisního účtu s existujícím zákazníkem
- pozvánky e-mailem pro registraci/propojení zákazníka
- výpis zákazníků a jejich vozidel
- ingest dokladů (PDF/foto/text) + heuristický parser položek a cen
- volitelné automatické založení servisního záznamu
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import secrets
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from src.modules.licensing.service import LicenseError, assert_service_customer_link_quota, assert_vehicle_quota
from src.core.branding import APP_DISPLAY_NAME
from src.core.config import DATA_DIR, FRONTEND_BASE_URL
from src.core.datetime_cz import naive_utc_to_iso_z, prague_today
from src.modules.email_client.service import EmailService
from src.modules.email_client.templates import render_email_layout, render_panel
from ..audit_log import write_global_audit_log
from ..central_vehicle_identity import (
    active_owner_assignment,
    find_vehicle_by_identifiers,
    normalize_plate,
    normalize_vin,
    query_hash,
    sync_vehicle_identity_fields,
    validate_normalized_vin,
    vehicle_state,
)
from ..database import get_db
from ..models import (
    Customer,
    Reminder as ReminderModel,
    Reservation as ReservationModel,
    ServiceAccessRequest,
    ServiceCustomerInvite,
    ServiceCustomerLink,
    ServiceVehicleAccess,
    ServiceVehicleLookupAudit,
    ServiceDocumentIngestion,
    ServiceIntake,
    ServiceRecord as ServiceRecordModel,
    VehicleOwnership,
    Vehicle as VehicleModel,
    VehicleQrAccessLog,
    VehicleQrToken,
    VehicleServiceLink,
)
from ..orv_scans import apply_orv_scan_to_vehicle
from ..ownership import ensure_vehicle_owner_assignment, get_owned_vehicle, get_owned_vehicle_rows, get_primary_vehicle_owner
from ..schema_management import assert_module_ready
from ..partner_public_profile import (
    partner_public_profile_from_db,
    partner_public_profile_to_stored_json,
)
from ..service_access import (
    create_or_update_vehicle_service_link,
    get_active_vehicle_service_link,
    log_vehicle_lookup,
    masked_plate,
    masked_vin,
    normalize_lookup_query,
    require_service_vehicle_link,
    resolve_vehicle_for_lookup,
    vehicle_label,
)
from ..service_access_messaging import try_email_owner_about_service_access_request
from ..user_in_app_notifications import notify_owner_service_access_requested
from src.modules.vehicle_hub.routers_v1.service_workspace_customer_centre import (
    CustomerLinkFromLookupRequestV1,
    _send_direct_customer_link_notice_email,
    execute_customer_link_from_lookup,
)
from ..vehicle_public_history import (
    build_public_history_page_url,
    build_vehicle_qr_signature,
    is_vehicle_qr_signature_valid,
    normalize_public_mode,
    render_vehicle_qr_svg,
)
from .auth import get_current_user
from .reminders import (
    apply_reminder_completion_update,
    check_and_send_reminder_notifications,
    is_recurring_reminder,
    _to_naive_utc,
)
from .schemas import (
    ServiceAccessRequestCreateV1,
    ServiceApprovedVehicleListOutV1,
    ServiceVehicleLookupRequestV1,
    ServiceVehicleLookupResponseV1,
    VehicleQrTokenCreateV1,
    VehicleQrTokenOutV1,
)


"""
PRODUCTION CRITICAL LOGIC:
- service access enforcement
- lifecycle remove/transfer
- audit log
Jakákoliv změna musí projít production auditem.
"""

logger = logging.getLogger(__name__)


class CentralVehicleLookupRequestV1(BaseModel):
    query: str = Field(..., min_length=2, max_length=128)
    query_type: Optional[str] = Field(default="auto", pattern="^(vin|plate|auto)$")


class ServiceProvisionUnownedVehicleRequestV1(BaseModel):
    vin: Optional[str] = Field(default=None, max_length=32)
    plate: Optional[str] = Field(default=None, max_length=32)
    brand: str = Field(..., min_length=1, max_length=80)
    model: str = Field(..., min_length=1, max_length=120)
    year: Optional[int] = Field(default=None, ge=1886, le=2100)
    mileage: Optional[int] = Field(default=None, ge=0)
    intake_note: Optional[str] = Field(default=None, max_length=2000)


def _service_access_email_notification_message(email_result: dict[str, Any]) -> str:
    if email_result.get("sent"):
        return "Uživatel byl upozorněn e-mailem."
    return "Žádost byla uložena, ale e-mail se nepodařilo odeslat."


router = APIRouter(prefix="/services/workspace", tags=["service-workspace-v1"])

ALLOWED_SOURCE_TYPES = {"invoice", "delivery_note", "work_order", "receipt", "manual"}


class PartnerPublicProfileOutV1(BaseModel):
    tagline: str = ""
    about: str = ""
    services_offered: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    opening_hours: str = ""
    brands: list[str] = Field(default_factory=list)


class PartnerPublicProfileUpdateV1(BaseModel):
    tagline: str = Field("", max_length=280)
    about: str = Field("", max_length=4000)
    services_offered: list[str] = Field(default_factory=list, max_length=40)
    equipment: list[str] = Field(default_factory=list, max_length=40)
    opening_hours: str = Field("", max_length=500)
    brands: list[str] = Field(default_factory=list, max_length=30)


SERVICE_DOCS_DIR = DATA_DIR / "service_workspace_docs"
SERVICE_DOCS_DIR.mkdir(parents=True, exist_ok=True)
SERVICE_RECORD_ATTACHMENTS_DIR = DATA_DIR / "service_record_attachments"
SERVICE_RECORD_ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)

MONEY_RE = re.compile(
    r"(?<!\d)(-?\d{1,3}(?:[ .]\d{3})*(?:[.,]\d{1,2})|-?\d+(?:[.,]\d{1,2})?)(?:\s?(?:Kč|CZK|EUR|€))?",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})")
CURRENCY_MARKER_RE = re.compile(r"(kč|czk|eur|€)", re.IGNORECASE)
ITEM_QTY_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(ks|x|hod|h|l|m|km|sada|set|bal|par|pár)\b", re.IGNORECASE)
ITEM_TABLE_HEADER_RE = re.compile(
    r"popis\s+polo(?:ž|z)ky.*(?:mno(?:ž|z)stv[ií]|mj|cena)",
    re.IGNORECASE,
)
ITEM_STRICT_TABLE_ROW_RE = re.compile(
    r"^(?P<name>.+?)\s+"
    r"(?P<qty>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>ks|x|hod|h|l|m|km|sada|set|bal|par|pár)\s+"
    r"(?P<unit_price>\d{1,3}(?:[ .]\d{3})*(?:[.,]\d{1,2})|\d+(?:[.,]\d{1,2}))\s+"
    r"(?P<total>\d{1,3}(?:[ .]\d{3})*(?:[.,]\d{1,2})|\d+(?:[.,]\d{1,2}))(?:\s?(?:Kč|CZK|EUR|€))?$",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
WEBSITE_RE = re.compile(r"((?:https?://)?(?:www\.)?[a-z0-9][a-z0-9.\-]+\.[a-z]{2,}(?:/[^\s]*)?)", re.IGNORECASE)
POSTCODE_RE = re.compile(r"\b\d{5}\b")


class LinkExistingCustomerRequest(BaseModel):
    """Propojení podle e-mailu (legacy) nebo podle lookup tokenu z POST /customers/search."""

    customer_email: Optional[EmailStr] = None
    note: Optional[str] = Field(default=None, max_length=500)
    lookup_id: Optional[str] = Field(default=None, max_length=4096)
    consent_basis: Optional[str] = Field(default=None, max_length=120)
    consent_note: Optional[str] = Field(default=None, max_length=2000)
    internal_service_note: Optional[str] = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _validate_channel(self) -> LinkExistingCustomerRequest:
        lk = (self.lookup_id or "").strip()
        if lk:
            if self.customer_email is not None:
                raise ValueError("Nelze kombinovat lookup_id s customer_email.")
            cb = (self.consent_basis or "").strip()
            cn = (self.consent_note or "").strip()
            if len(cb) < 3 or len(cn) < 3:
                raise ValueError("lookup_id vyžaduje consent_basis a consent_note (min. 3 znaky).")
            return self
        if self.customer_email is None:
            raise ValueError("Zadejte customer_email nebo lookup_id.")
        return self


class ServiceCustomerLinkNotePatchRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class SendServiceInviteRequest(BaseModel):
    invite_email: EmailStr
    invite_name: Optional[str] = Field(default=None, max_length=120)
    invite_message: Optional[str] = Field(default=None, max_length=2000)


class PendingVehicleRegistrationRequest(BaseModel):
    invite_email: EmailStr
    invite_name: Optional[str] = Field(default=None, max_length=120)
    invite_message: Optional[str] = Field(default=None, max_length=2000)
    vehicle: "ServiceWorkspaceVehicleCreateRequest"


class AcceptServiceInviteRequest(BaseModel):
    token: str = Field(min_length=12, max_length=512)


class IngestDocumentRequest(BaseModel):
    customer_id: int = Field(gt=0)
    vehicle_id: Optional[int] = Field(default=None, gt=0)
    source_type: str = Field(default="invoice", max_length=32)
    manual_note: Optional[str] = Field(default=None, max_length=2000)
    manual_text: Optional[str] = Field(default=None, max_length=300_000)
    file_name: Optional[str] = Field(default=None, max_length=255)
    file_mime_type: Optional[str] = Field(default=None, max_length=255)
    file_content_base64: Optional[str] = Field(default=None, max_length=25_000_000)
    auto_create_service_record: bool = True


class ServiceWorkspaceVehicleCreateRequest(BaseModel):
    nickname: str = Field(..., min_length=2, max_length=120)
    plate: Optional[str] = Field(default=None, max_length=32)
    vin: Optional[str] = Field(default=None, max_length=64)
    brand: Optional[str] = Field(default=None, max_length=64)
    model: Optional[str] = Field(default=None, max_length=120)
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    engine: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=8000)
    stk_valid_until: Optional[date] = None
    current_mileage_km: Optional[int] = Field(default=None, ge=0)
    last_stk_mileage_km: Optional[int] = Field(default=None, ge=0)
    tyres_info: Optional[str] = Field(default=None, max_length=8000)
    orv_scan_id: Optional[int] = Field(default=None, gt=0)
    orv_number: Optional[str] = Field(default=None, max_length=128)
    orv_use_owner_data: bool = False
    data_trust_state: Optional[str] = Field(default=None, max_length=64)


class ServiceWorkspaceReminderCreateRequest(BaseModel):
    customer_id: int = Field(gt=0)
    vehicle_id: Optional[int] = Field(default=None, gt=0)
    type: str = Field(default="SERVIS", min_length=2, max_length=32)
    text: str = Field(..., min_length=3, max_length=2000)
    due_date: Optional[date] = None
    notify_at: Optional[datetime] = None
    notification_method: Optional[str] = Field(default=None, max_length=16)


class ServiceWorkspaceReminderUpdateRequest(BaseModel):
    type: Optional[str] = Field(default=None, min_length=2, max_length=32)
    text: Optional[str] = Field(default=None, min_length=3, max_length=2000)
    due_date: Optional[date] = None
    notify_at: Optional[datetime] = None
    notification_method: Optional[str] = Field(default=None, max_length=16)
    is_completed: Optional[bool] = None


def _normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def _require_service_workspace_role(current_user: Customer) -> None:
    from src.modules.vehicle_hub.workspace_entitlements import customer_has_service_workspace_access

    if not customer_has_service_workspace_access(current_user):
        raise HTTPException(status_code=403, detail="Servisní centrum je dostupné pouze pro servisní účty.")


def _ensure_service_workspace_schema(db: Session) -> None:
    assert_module_ready(db, "service_workspace", detail_prefix="Servisní workspace není připraven")


def _find_customer_by_email(db: Session, email: str) -> Optional[Customer]:
    normalized = _normalize_email(email)
    if not normalized:
        return None
    return (
        db.query(Customer)
        .filter(func.lower(Customer.email) == normalized)
        .first()
    )


def _get_active_link(
    db: Session,
    *,
    service_customer_id: int,
    customer_id: int,
) -> Optional[ServiceCustomerLink]:
    return (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == service_customer_id,
            ServiceCustomerLink.customer_id == customer_id,
            ServiceCustomerLink.status == "active",
        )
        .first()
    )


def _query_value(raw_value):
    if hasattr(raw_value, "default"):
        return raw_value.default
    return raw_value


def _mask_email_value(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    if not text or "@" not in text:
        return None
    local, domain = text.split("@", 1)
    if len(local) <= 2:
        local_masked = local[0] + "*"
    else:
        local_masked = f"{local[:2]}***"
    return f"{local_masked}@{domain}"


def _mask_phone_value(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    digits = re.sub(r"\D+", "", text)
    if len(digits) < 4:
        return "***"
    return f"***{digits[-3:]}"


def _get_linked_customer_or_404(db: Session, current_user: Customer, customer_id: int) -> Customer:
    customer = (
        db.query(Customer)
        .filter(
            Customer.id == customer_id,
            func.lower(Customer.role).notin_(["service", "admin", "developer_admin"]),
        )
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Zákazník nebyl nalezen.")

    link = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == current_user.id,
            ServiceCustomerLink.customer_id == customer.id,
            ServiceCustomerLink.status.in_(("active", "invited", "pending_customer_confirm")),
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=403, detail="Tento zákazník není propojen se servisním účtem.")
    return customer


def _get_active_linked_customer_or_404(db: Session, current_user: Customer, customer_id: int) -> Customer:
    customer = (
        db.query(Customer)
        .filter(
            Customer.id == customer_id,
            func.lower(Customer.role).notin_(["service", "admin", "developer_admin"]),
        )
        .first()
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Zákazník nebyl nalezen.")

    link = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == current_user.id,
            ServiceCustomerLink.customer_id == customer.id,
            ServiceCustomerLink.status.in_(["active", "invited"]),
        )
        .first()
    )
    if not link:
        raise HTTPException(
            status_code=403,
            detail="Ke klientovi je potřeba aktivní nebo pozvaná servisní vazba.",
        )
    return customer


def _get_shared_vehicle_ids_for_pair(db: Session, *, service_customer_id: int, customer_id: int) -> set[int]:
    """
    Vrátí ID vozidel, která mají pro daný pár servis<->klient explicitně schválený přístup.
    """
    shared_ids: set[int] = set()

    access_rows = (
        db.query(VehicleServiceLink.vehicle_id)
        .filter(
            VehicleServiceLink.service_customer_id == service_customer_id,
            VehicleServiceLink.owner_customer_id == customer_id,
            VehicleServiceLink.vehicle_id.isnot(None),
            VehicleServiceLink.status == "approved",
        )
        .distinct()
        .all()
    )
    for (vehicle_id,) in access_rows:
        if vehicle_id:
            shared_ids.add(int(vehicle_id))

    return shared_ids


def _get_customer_vehicle_rows(db: Session, customer: Customer) -> list[VehicleModel]:
    return get_owned_vehicle_rows(db, customer, tenant_id=getattr(customer, "tenant_id", None))


def _upsert_service_vehicle_access(
    db: Session,
    *,
    service_customer_id: int,
    customer_id: int,
    vehicle_id: int,
    note: Optional[str] = None,
) -> None:
    existing = (
        db.query(ServiceVehicleAccess)
        .filter(
            ServiceVehicleAccess.service_customer_id == service_customer_id,
            ServiceVehicleAccess.customer_id == customer_id,
            ServiceVehicleAccess.vehicle_id == vehicle_id,
        )
        .first()
    )
    if existing:
        existing.status = "active"
        existing.granted_by_customer_id = customer_id
        existing.note = note
        existing.revoked_at = None
        existing.updated_at = datetime.utcnow()
        db.flush()
        return

    db.add(
        ServiceVehicleAccess(
            service_customer_id=service_customer_id,
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            status="active",
            granted_by_customer_id=customer_id,
            note=note,
            revoked_at=None,
        )
    )
    db.flush()


def _service_access_scope_summary() -> str:
    return "Čtení historie vozidla a možnost vytvářet nové servisní záznamy bez úprav starší cizí historie."


def _lookup_candidate_payload(
    *,
    vehicle: VehicleModel,
    owner_customer: Optional[Customer],
    status: str,
    can_request_access: bool,
    can_open_detail: bool = True,
    can_create_work_order: bool = False,
    blocking_reason: Optional[str] = None,
    match_score: Optional[float] = None,
    match_type: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "id": f"vehicle-{int(vehicle.id)}",
        "vehicle_id": int(vehicle.id),
        "owner_customer_id": int(owner_customer.id) if owner_customer else None,
        "nickname": vehicle.nickname,
        "brand": vehicle.brand,
        "model": vehicle.model,
        "plate_masked": masked_plate(vehicle.plate),
        "vin_masked": masked_vin(vehicle.vin),
        "city": owner_customer.city if owner_customer else None,
        "owner_label": None,
        "status": status,
        "can_request_access": bool(can_request_access),
        "can_open_detail": bool(can_open_detail),
        "can_create_work_order": bool(can_create_work_order),
        "blocking_reason": blocking_reason,
        "match_score": match_score,
        "match_type": match_type,
    }


def _detail_state_payload(
    *,
    entity_type: str,
    entity_id: int,
    status: str,
    can_open_detail: bool,
    can_edit: bool,
    can_request_access: bool,
    can_create_work_order: bool,
    blocking_reason: Optional[str],
    disclosure: str,
) -> dict[str, Any]:
    return {
        "entity_type": entity_type,
        "entity_id": int(entity_id),
        "status": status,
        "access_status": "full_access" if disclosure == "full" else "limited_access",
        "can_open_detail": bool(can_open_detail),
        "can_edit": bool(can_edit),
        "can_request_access": bool(can_request_access),
        "can_create_work_order": bool(can_create_work_order),
        "blocking_reason": blocking_reason,
        "disclosure": disclosure,
    }


def _get_latest_invitation_for_email(
    db: Session,
    *,
    service_customer_id: int,
    invite_email: Optional[str],
) -> Optional[ServiceCustomerInvite]:
    normalized_email = _normalize_email(invite_email or "")
    if not normalized_email:
        return None
    return (
        db.query(ServiceCustomerInvite)
        .filter(
            ServiceCustomerInvite.service_customer_id == int(service_customer_id),
            func.lower(ServiceCustomerInvite.invite_email) == normalized_email,
        )
        .order_by(ServiceCustomerInvite.sent_at.desc(), ServiceCustomerInvite.id.desc())
        .first()
    )


def _vehicle_access_state(
    db: Session,
    *,
    current_user: Customer,
    vehicle: VehicleModel,
    owner_customer: Optional[Customer],
) -> tuple[str, Optional[VehicleServiceLink], Optional[ServiceAccessRequest]]:
    approved_link = get_active_vehicle_service_link(
        db,
        service_customer_id=int(current_user.id),
        vehicle_id=int(vehicle.id),
    )
    if approved_link:
        return "already_approved", approved_link, None
    if not owner_customer:
        return "owner_missing", None, None
    pending_request = (
        db.query(ServiceAccessRequest)
        .filter(
            ServiceAccessRequest.service_customer_id == int(current_user.id),
            ServiceAccessRequest.vehicle_id == int(vehicle.id),
            ServiceAccessRequest.status == "pending",
        )
        .order_by(ServiceAccessRequest.id.desc())
        .first()
    )
    if pending_request:
        return "pending_request", None, pending_request
    return "matched", None, None


def _vehicle_blocking_reason(
    *,
    status: str,
    linked_customer: bool,
) -> Optional[str]:
    if status == "already_approved" and not linked_customer:
        return "Vozidlo má schválený přístup, ale klient zatím není aktivně propojen se servisním účtem."
    if status == "pending_request":
        return "Pro toto vozidlo už čeká žádost o přístup."
    if status == "owner_missing":
        return "K vozidlu se nepodařilo určit schvalovatele přístupu."
    if status == "matched":
        return "Servis zatím nemá k vozidlu schválený přístup."
    return None


def _serialize_workspace_vehicle_summary(
    *,
    vehicle: VehicleModel,
    is_shared: bool,
) -> dict[str, Any]:
    base_label = (
        vehicle.nickname
        or " ".join(part for part in [vehicle.brand, vehicle.model] if part).strip()
        or vehicle.plate
        or f"Vozidlo #{int(vehicle.id)}"
    )
    return {
        "vehicle_id": int(vehicle.id),
        "label": (
            f"{base_label} • {vehicle.plate}"
            if is_shared and vehicle.plate and base_label != vehicle.plate
            else base_label
        ),
        "status": "already_approved" if is_shared else "matched",
        "can_open_detail": True,
        "can_request_access": not bool(is_shared),
        "can_create_work_order": bool(is_shared),
        "disclosure": "full" if is_shared else "limited",
    }


def _build_customer_detail_payload(
    db: Session,
    *,
    current_user: Customer,
    customer: Customer,
) -> dict[str, Any]:
    active_link = _get_active_link(db, service_customer_id=current_user.id, customer_id=int(customer.id))
    disclosure = "full" if active_link else "limited"
    shared_vehicle_ids = (
        _get_shared_vehicle_ids_for_pair(db, service_customer_id=current_user.id, customer_id=int(customer.id))
        if active_link
        else set()
    )
    customer_vehicles = _get_customer_vehicle_rows(db, customer) if active_link else []
    last_invite = _get_latest_invitation_for_email(
        db,
        service_customer_id=int(current_user.id),
        invite_email=getattr(customer, "email", None),
    )
    invite_status = None
    invite_status_label = None
    invite_completed = None
    if last_invite:
        invite_status, invite_status_label, invite_completed = _invitation_status_meta(
            str(last_invite.status or ""),
            accepted_at=last_invite.accepted_at,
        )
    last_service_date = None
    if active_link:
        last_service_date = (
            db.query(func.max(ServiceRecordModel.performed_at))
            .join(VehicleOwnership, VehicleOwnership.vehicle_id == ServiceRecordModel.vehicle_id)
            .filter(
                VehicleOwnership.customer_id == customer.id,
                VehicleOwnership.is_active.is_(True),
                ServiceRecordModel.user_id == current_user.id,
            )
            .scalar()
        )
    can_create_work_order = bool(active_link and shared_vehicle_ids)
    payload = _detail_state_payload(
        entity_type="customer",
        entity_id=int(customer.id),
        status="linked" if active_link else "not_linked",
        can_open_detail=True,
        can_edit=False,
        can_request_access=False,
        can_create_work_order=can_create_work_order,
        blocking_reason=(
            None
            if can_create_work_order or not active_link
            else "Zákazník je propojen, ale servis zatím nemá schválený přístup k žádnému jeho vozidlu."
        ),
        disclosure=disclosure,
    )
    payload.update(
        {
            "customer_id": int(customer.id),
            "name": customer.name or customer.email or f"Zákazník #{int(customer.id)}",
            "role": customer.role,
            "email": customer.email if disclosure == "full" else None,
            "email_masked": _mask_email_value(customer.email),
            "phone": customer.phone if disclosure == "full" else None,
            "phone_masked": _mask_phone_value(customer.phone),
            "vehicles_count": len(customer_vehicles) if active_link else None,
            "shared_vehicles_count": len(shared_vehicle_ids) if active_link else 0,
            "last_service_date": last_service_date.isoformat() if last_service_date else None,
            "note": active_link.note if active_link else None,
            "linked_at": active_link.created_at.isoformat() if active_link and active_link.created_at else None,
            "can_link": not bool(active_link),
            "invite_id": int(last_invite.id) if last_invite else None,
            "invite_status": invite_status,
            "invite_status_label": invite_status_label,
            "invite_completed": bool(invite_completed) if invite_completed is not None else None,
            "can_send_invite": not bool(active_link) and bool(getattr(customer, "email", None)),
            "vehicles": [
                _serialize_workspace_vehicle_summary(vehicle=vehicle, is_shared=int(vehicle.id) in shared_vehicle_ids)
                for vehicle in customer_vehicles
            ],
        }
    )
    return payload


def _build_vehicle_detail_payload(
    db: Session,
    *,
    current_user: Customer,
    vehicle: VehicleModel,
) -> dict[str, Any]:
    owner_customer = get_primary_vehicle_owner(db, vehicle)
    active_qr_token = _get_vehicle_qr_token(db, vehicle_id=int(vehicle.id))
    visible_records_count = (
        db.query(ServiceRecordModel.id)
        .filter(
            ServiceRecordModel.vehicle_id == int(vehicle.id),
            ServiceRecordModel.is_deleted.is_(False),
        )
        .count()
    )
    linked_customer = bool(
        owner_customer
        and _get_active_link(
            db,
            service_customer_id=int(current_user.id),
            customer_id=int(owner_customer.id),
        )
    )
    status, approved_link, pending_request = _vehicle_access_state(
        db,
        current_user=current_user,
        vehicle=vehicle,
        owner_customer=owner_customer,
    )
    disclosure = "full" if approved_link else "limited"
    can_create_work_order = bool(approved_link and linked_customer and owner_customer)
    can_request_access = bool(
        owner_customer
        and owner_customer.id != current_user.id
        and status not in {"already_approved", "pending_request", "owner_missing"}
    )
    payload = _detail_state_payload(
        entity_type="vehicle",
        entity_id=int(vehicle.id),
        status=status,
        can_open_detail=True,
        can_edit=False,
        can_request_access=can_request_access,
        can_create_work_order=can_create_work_order,
        blocking_reason=_vehicle_blocking_reason(status=status, linked_customer=linked_customer),
        disclosure=disclosure,
    )
    payload.update(
        {
            "vehicle_id": int(vehicle.id),
            "owner_customer_id": int(owner_customer.id) if owner_customer and linked_customer else None,
            "owner_name": (
                (owner_customer.name or owner_customer.email)
                if owner_customer and linked_customer and disclosure == "full"
                else None
            ),
            "nickname": vehicle.nickname,
            "brand": vehicle.brand,
            "model": vehicle.model,
            "year": vehicle.year,
            "engine": vehicle.engine,
            "plate": vehicle.plate if disclosure == "full" else None,
            "plate_masked": masked_plate(vehicle.plate),
            "vin": vehicle.vin if disclosure == "full" else None,
            "vin_masked": masked_vin(vehicle.vin),
            "stk_valid_until": vehicle.stk_valid_until.isoformat() if vehicle.stk_valid_until else None,
            "current_mileage_km": vehicle.current_mileage_km if disclosure == "full" else None,
            "last_stk_mileage_km": vehicle.last_stk_mileage_km if disclosure == "full" else None,
            "mileage_checked_at": vehicle.mileage_checked_at.isoformat() if vehicle.mileage_checked_at else None,
            "data_trust_state": vehicle.data_trust_state,
            "created_at": vehicle.created_at.isoformat() if vehicle.created_at else None,
            "linked_customer": linked_customer,
            "request_id": int(pending_request.id) if pending_request else None,
            "request_status": pending_request.status if pending_request else None,
            "service_link_id": int(approved_link.id) if approved_link else None,
            "records_count": int(visible_records_count),
            "has_qr_token": bool(active_qr_token),
            "qr_public_mode": getattr(active_qr_token, "public_mode", None) if active_qr_token else None,
            "qr_last_access_at": active_qr_token.last_access_at.isoformat() if active_qr_token and active_qr_token.last_access_at else None,
        }
    )
    return payload


def _document_disclosure_state(
    db: Session,
    *,
    current_user: Customer,
    entity: ServiceDocumentIngestion,
) -> tuple[str, bool, bool, Optional[str]]:
    linked_customer = bool(
        entity.customer_id
        and _get_active_link(
            db,
            service_customer_id=int(current_user.id),
            customer_id=int(entity.customer_id),
        )
    )
    approved_vehicle = bool(
        entity.vehicle_id
        and get_active_vehicle_service_link(
            db,
            service_customer_id=int(current_user.id),
            vehicle_id=int(entity.vehicle_id),
        )
    )
    disclosure = "full" if linked_customer and (not entity.vehicle_id or approved_vehicle) else "limited"
    can_request_access = bool(entity.vehicle_id and not approved_vehicle)
    can_create_work_order = bool(entity.customer_id and entity.vehicle_id and linked_customer and approved_vehicle)
    blocking_reason = None
    if entity.customer_id and not linked_customer:
        blocking_reason = "Doklad je navázaný na klienta, který už není aktivně propojen se servisním účtem."
    elif entity.vehicle_id and not approved_vehicle:
        blocking_reason = "K vozidlu z dokladu není schválený servisní přístup."
    return disclosure, can_request_access, can_create_work_order, blocking_reason

def _normalize_service_reminder_type(raw_type: Optional[str]) -> str:
    value = str(raw_type or "").strip().upper()
    if not value:
        return "SERVIS"
    aliases = {
        "STK": "STK",
        "OIL": "OLEJ",
        "OLEJ": "OLEJ",
        "SERVIS": "SERVIS",
        "SERVICE": "SERVIS",
        "INTERVAL": "SERVIS",
        "PNEU": "PNEU",
        "TIRES": "PNEU",
        "PNEUMATIKY": "PNEU",
        "VLASTNI": "VLASTNI",
        "CUSTOM": "VLASTNI",
        "GENERAL": "GENERAL",
    }
    return aliases.get(value, value[:32])


def _normalize_service_reminder_notification_method(raw_method: Optional[str]) -> Optional[str]:
    value = str(raw_method or "").strip().lower()
    if not value:
        return None
    if value in {"app", "email", "both"}:
        return value
    if value in {"inherit", "default", "none"}:
        return None
    return None


def _email_domain_for_audit(addr: Optional[str]) -> str:
    s = str(addr or "").strip().lower()
    if "@" not in s:
        return ""
    return s.split("@", 1)[1]


def _upsert_service_customer_link(
    db: Session,
    *,
    service_customer_id: int,
    service_tenant_id: Optional[int],
    target_customer: Customer,
    note: Optional[str] = None,
) -> tuple[ServiceCustomerLink, bool]:
    existing = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == service_customer_id,
            ServiceCustomerLink.customer_id == target_customer.id,
        )
        .first()
    )
    if existing:
        existing.status = "active"
        existing.service_tenant_id = service_tenant_id
        existing.customer_tenant_id = target_customer.tenant_id
        if note is not None:
            existing.note = note
        existing.updated_at = datetime.utcnow()
        db.flush()
        return existing, False

    assert_service_customer_link_quota(db, service_customer_id=service_customer_id)
    link = ServiceCustomerLink(
        service_tenant_id=service_tenant_id,
        service_customer_id=service_customer_id,
        customer_tenant_id=target_customer.tenant_id,
        customer_id=target_customer.id,
        status="active",
        note=note,
    )
    db.add(link)
    db.flush()
    return link, True


def _build_invitation_url(token: str) -> str:
    base = str(FRONTEND_BASE_URL or "").strip().rstrip("/")
    if not base:
        base = "http://127.0.0.1:8000"

    if base.endswith("/web/index.html"):
        return f"{base}?invite_token={token}"
    if base.endswith("/index.html"):
        return f"{base}?invite_token={token}"
    if base.endswith("/web"):
        return f"{base}/index.html?invite_token={token}"
    return f"{base}/web/index.html?invite_token={token}"


def _build_vehicle_qr_payload(qr_token: VehicleQrToken) -> dict[str, Any]:
    public_url = build_public_history_page_url(str(qr_token.token))
    return {
        "id": int(qr_token.id),
        "vehicle_id": int(qr_token.vehicle_id),
        "token": str(qr_token.token),
        "public_mode": normalize_public_mode(getattr(qr_token, "public_mode", None), default="basic"),
        "explicit_full_consent": bool(getattr(qr_token, "explicit_full_consent", False)),
        "issued_at": qr_token.issued_at,
        "revoked_at": qr_token.revoked_at,
        "last_access_at": qr_token.last_access_at,
        "signature_hash": str(qr_token.signature_hash or ""),
        "active": bool(getattr(qr_token, "active", False)) and not bool(getattr(qr_token, "revoked_at", None)),
        "public_history_url": public_url,
        "qr_svg": render_vehicle_qr_svg(public_url),
    }


def _get_vehicle_qr_token(db: Session, *, vehicle_id: int) -> Optional[VehicleQrToken]:
    return (
        db.query(VehicleQrToken)
        .filter(
            VehicleQrToken.vehicle_id == int(vehicle_id),
            VehicleQrToken.active.is_(True),
            VehicleQrToken.revoked_at.is_(None),
        )
        .order_by(VehicleQrToken.issued_at.desc(), VehicleQrToken.id.desc())
        .first()
    )


def _issue_vehicle_qr_token(
    db: Session,
    *,
    current_user: Customer,
    vehicle: VehicleModel,
    public_mode: str,
    explicit_full_consent: bool,
) -> VehicleQrToken:
    issued_at = datetime.utcnow()
    token_value = secrets.token_urlsafe(24)
    qr_token = VehicleQrToken(
        tenant_id=int(vehicle.tenant_id or getattr(current_user, "tenant_id", None) or 1),
        vehicle_id=int(vehicle.id),
        created_by_user_id=getattr(current_user, "id", None),
        token=token_value,
        public_mode=normalize_public_mode(public_mode, default="basic"),
        explicit_full_consent=bool(explicit_full_consent),
        active=True,
        issued_at=issued_at,
        revoked_at=None,
        last_access_at=None,
        signature_hash="pending",
    )
    qr_token.signature_hash = build_vehicle_qr_signature(
        token=token_value,
        vehicle_id=int(vehicle.id),
        issued_at=issued_at,
    )
    db.add(qr_token)
    db.flush()
    return qr_token


def _lookup_match_meta(*, identifier_type: str, query: str, vehicle: Optional[VehicleModel]) -> tuple[float, str]:
    normalized_identifier = str(identifier_type or "unknown").strip().lower()
    normalized_query = str(query or "").strip().upper()
    if vehicle is None:
        return 0.0, "fuzzy"
    vehicle_vin = str(getattr(vehicle, "vin", "") or "").strip().upper()
    vehicle_plate = str(getattr(vehicle, "plate", "") or "").strip().upper()
    if normalized_identifier == "vin":
        if normalized_query and vehicle_vin == normalized_query:
            return 1.0, "vin_exact"
        if normalized_query and vehicle_vin.startswith(normalized_query):
            return max(0.55, min(0.94, len(normalized_query) / 17.0)), "vin_partial"
        return 0.62, "fuzzy"
    if normalized_identifier == "plate":
        if normalized_query and vehicle_plate == normalized_query:
            return 1.0, "spz"
        return 0.68, "fuzzy"
    return 0.6, "fuzzy"


def _send_invitation_email(
    *,
    service_user: Customer,
    invite_email: str,
    invite_name: Optional[str],
    invite_message: Optional[str],
    invitation_url: str,
) -> bool:
    email_service = EmailService()
    if not email_service.is_configured():
        return False

    service_name = (service_user.name or service_user.email or f"{APP_DISPLAY_NAME} servis").strip()
    recipient_name = (invite_name or "zákazníku").strip()
    custom_message = (invite_message or "").strip()

    body = f"""Dobrý den {recipient_name},

servis {service_name} Vám poslal pozvánku do aplikace {APP_DISPLAY_NAME}.

Po registraci nebo přihlášení potvrďte propojení účtu kliknutím na odkaz:
{invitation_url}

{f"Zpráva od servisu: {custom_message}" if custom_message else ""}

Díky tomuto propojení uvidíte servisní historii a plánované úkony pro vaše vozidla.
"""

    panels = [
        render_panel(
            title="Detaily pozvánky",
            rows=[("Servis", service_name), ("Příjemce", invite_email)],
            accent="#3b82f6",
            tone="#eff6ff",
        )
    ]
    if custom_message:
        panels.append(
            render_panel(
                title="Zpráva od servisu",
                message=custom_message,
                accent="#64748b",
                tone="#f8fafc",
            )
        )

    html_body = render_email_layout(
        title="Pozvánka od servisu",
        subtitle="Propojení účtu se servisním workspace.",
        intro=f"Dobrý den {recipient_name},",
        paragraphs=[
            f"servis {service_name} Vám poslal pozvánku do aplikace {APP_DISPLAY_NAME}.",
            "Po potvrzení propojení získáte přístup k evidenci servisních úkonů a plánovaným úkolům pro Vaše vozidla.",
        ],
        panels=panels,
        cta_label="Otevřít pozvánku",
        cta_url=invitation_url,
        accent="#f59e0b",
        footer_note=f"Pokud účet ještě nemáte, po otevření odkazu se můžete zaregistrovat do aplikace {APP_DISPLAY_NAME}.",
    )

    try:
        email_service.send_simple_email(
            to=invite_email,
            subject=f"Pozvánka od servisu do aplikace {APP_DISPLAY_NAME}",
            body=body,
            html_body=html_body,
        )
        return True
    except Exception as exc:
        print(f"[SERVICE_WORKSPACE] Odeslání pozvánky selhalo: {exc}")
        return False


def _invitation_status_meta(status_raw: str, *, accepted_at: Optional[datetime]) -> tuple[str, str, bool]:
    status = str(status_raw or "").strip().lower()
    if accepted_at and status != "accepted":
        status = "accepted"

    if status == "accepted":
        return "accepted", "Vyřízená (přijato)", True
    if status == "pending":
        return "pending", "Čeká na přijetí", False
    if status == "expired":
        return "expired", "Vypršela", False
    if status == "cancelled":
        return "cancelled", "Zrušená", False
    return status or "unknown", "Neznámý stav", False


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _parse_decimal(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    cleaned = re.sub(r"[^0-9,.\- ]", "", text).replace("\u00a0", " ")
    cleaned = "".join(cleaned.split())
    if not cleaned or cleaned in {"-", ".", ","}:
        return None

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")

    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _parse_date(raw: str) -> Optional[date]:
    if not raw:
        return None
    text = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y"):
        try:
            parsed = datetime.strptime(text, fmt).date()
            if parsed.year < 100:
                parsed = parsed.replace(year=parsed.year + 2000)
            return parsed
        except ValueError:
            continue
    return None


def _extract_amount_from_line(line: str) -> Optional[float]:
    if not line:
        return None
    amounts: list[float] = []
    for match in MONEY_RE.finditer(line):
        parsed = _parse_decimal(match.group(1))
        if parsed is None:
            continue
        amounts.append(parsed)
    if not amounts:
        return None
    return amounts[-1]


def _extract_amount_by_labels(lines: list[str], labels: list[str]) -> Optional[float]:
    for line in lines:
        lower = line.lower()
        if any(label in lower for label in labels):
            amount = _extract_amount_from_line(line)
            if amount is None:
                continue
            if "dph" in lower and "%" in lower and amount <= 30:
                # Pravděpodobně sazba DPH, ne částka.
                continue
            return round(float(amount), 2)
    return None


def _extract_date_by_labels(lines: list[str], labels: list[str]) -> Optional[date]:
    for line in lines:
        lower = line.lower()
        if any(label in lower for label in labels):
            for match in DATE_RE.finditer(line):
                parsed = _parse_date(match.group(1))
                if parsed:
                    return parsed
    return None


def _is_summary_line(lower_line: str) -> bool:
    summary_keywords = (
        "celkem",
        "celková částka",
        "celkova castka",
        "k úhradě",
        "k uhrade",
        "zbývá uhradit",
        "zbyva uhradit",
        "uhrazeno",
        "vyhotovil",
        "převzal",
        "prevzal",
        "k úhradě:",
        "k uhrade:",
    )
    return any(keyword in lower_line for keyword in summary_keywords)


def _has_multiple_dates(line: str) -> bool:
    return len(DATE_RE.findall(line)) >= 2


def _is_header_or_meta_line(lower_line: str) -> bool:
    meta_keywords = (
        "faktura",
        "invoice",
        "zakázkový list",
        "zakazkovy list",
        "dodavatel",
        "odběratel",
        "odberatel",
        "datum vystavení",
        "datum zdanitelného plnění",
        "datum splatnosti",
        "forma úhrady",
        "forma uhrady",
        "variabilní symbol",
        "variabilni symbol",
        "konstantní symbol",
        "konstantni symbol",
        "specifický symbol",
        "specificky symbol",
        "iban",
        "swift",
        "ičo",
        "ico",
        "dič",
        "dic",
        "powered by",
    )
    return any(keyword in lower_line for keyword in meta_keywords)


def _is_address_like_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    lower = stripped.lower()
    if re.search(r"\b\d{1,5}\s*/\s*\d{1,5}[A-Za-z]?\b", stripped):
        return True
    if POSTCODE_RE.search(stripped) and any(char.isalpha() for char in stripped):
        return True
    if any(token in lower for token in ("ulice", "třída", "trida", "nám", "nam", "č.p", "cp", "česká republika", "ceska republika")):
        return True
    if ("," in stripped and POSTCODE_RE.search(stripped)) or ("č." in lower and any(ch.isdigit() for ch in stripped)):
        return True
    return False


def _extract_line_amount_entries(
    line: str,
    *,
    has_currency_marker: bool,
    has_quantity_hint: bool = False,
) -> list[tuple[float, int, int]]:
    entries: list[tuple[float, int, int]] = []
    for match in MONEY_RE.finditer(line):
        raw_amount_token = str(match.group(1) or "")
        value = _parse_decimal(raw_amount_token)
        if value is None:
            continue
        start_idx = match.start(1)
        end_idx = match.end(1)
        before_char = line[start_idx - 1] if start_idx > 0 else ""
        after_char = line[end_idx] if end_idx < len(line) else ""
        if before_char == "/" or before_char.isalpha():
            continue
        if after_char == "/":
            # Např. "2351/19a" – adresa, ne cena.
            continue
        if after_char.isalpha():
            # Např. "19a" v adrese "2351/19a" – nejde o cenu.
            continue
        digits_only = re.sub(r"[^0-9]", "", raw_amount_token)
        if (
            len(digits_only) >= 8
            and "." not in raw_amount_token
            and "," not in raw_amount_token
            and not has_currency_marker
        ):
            # Čísla typu IČO/DIČ bez měnové značky bývají 8+ číslic.
            continue
        if (
            not has_currency_marker
            and not has_quantity_hint
            and len(digits_only) >= 5
            and "." not in raw_amount_token
            and "," not in raw_amount_token
        ):
            # Bez měny i bez množství bývají 5+ číslic často adresa/PSČ/číslo dokladu.
            continue
        if abs(value) > 5_000_000:
            continue
        entries.append((float(value), start_idx, end_idx))
    return entries


def _looks_like_invalid_item_name(name: str) -> bool:
    cleaned = " ".join(str(name or "").split()).strip()
    if len(cleaned) < 3 or len(cleaned) > 180:
        return True
    lower = cleaned.lower()
    if _is_summary_line(lower) or _is_header_or_meta_line(lower) or _is_address_like_line(cleaned):
        return True
    if _has_multiple_dates(cleaned) or DATE_RE.search(cleaned):
        return True
    if EMAIL_RE.search(cleaned):
        return True
    blocked_keywords = (
        "faktura",
        "invoice",
        "zakázkový list",
        "zakazkovy list",
        "daňový doklad",
        "danovy doklad",
        "dodavatel",
        "odběratel",
        "odberatel",
        "telefon",
        "email",
        "e-mail",
        "web",
        "iban",
        "swift",
        "účet",
        "ucet",
        "variabilní symbol",
        "variabilni symbol",
        "forma úhrady",
        "forma uhrady",
        "datum vystavení",
        "datum zdanitelného",
        "datum splatnosti",
    )
    if any(token in lower for token in blocked_keywords):
        return True
    if re.search(r"\b[a-zA-ZÀ-ž]{2,}\s+\d{3,}(?:/\d+)?\b", cleaned):
        return True
    if any(token in lower for token in ("ičo", "ico", "dič", "dic", "variabilní symbol", "variabilni symbol", "vyhotovil")):
        return True
    if POSTCODE_RE.search(cleaned):
        return True
    letters_count = sum(1 for ch in cleaned if ch.isalpha())
    digits_count = sum(1 for ch in cleaned if ch.isdigit())
    if letters_count == 0:
        return True
    if digits_count > 0 and (digits_count / max(len(cleaned), 1)) > 0.5:
        return True
    return False


def _parse_strict_table_row(raw_line: str, *, currency: str) -> Optional[dict[str, Any]]:
    line = " ".join(str(raw_line or "").split())
    if not line:
        return None
    match = ITEM_STRICT_TABLE_ROW_RE.match(line)
    if not match:
        return None

    name = str(match.group("name") or "").strip(" -;:")
    if _looks_like_invalid_item_name(name):
        return None

    quantity = _parse_decimal(match.group("qty"))
    unit = str(match.group("unit") or "").strip().lower() or None
    unit_price = _parse_decimal(match.group("unit_price"))
    total_price = _parse_decimal(match.group("total"))
    if total_price is None or abs(float(total_price)) < 0.01:
        return None

    item: dict[str, Any] = {
        "name": name,
        "quantity": quantity,
        "unit": unit,
        "total_price": round(float(total_price), 2),
        "currency": currency,
    }
    if unit_price is not None and abs(float(unit_price)) >= 0.01:
        item["unit_price"] = round(float(unit_price), 2)
    return item


def _parse_item_line(
    *,
    raw_line: str,
    currency: str,
    strict_table: bool,
) -> Optional[dict[str, Any]]:
    line = " ".join(str(raw_line or "").split())
    if len(line) < 5:
        return None
    lower = line.lower()

    if _is_summary_line(lower):
        return None
    if _has_multiple_dates(line):
        return None
    if _is_header_or_meta_line(lower):
        return None
    if _is_address_like_line(line):
        return None

    has_currency_marker = bool(CURRENCY_MARKER_RE.search(line))
    qty_match = ITEM_QTY_RE.search(line)
    amount_entries = _extract_line_amount_entries(
        line,
        has_currency_marker=has_currency_marker,
        has_quantity_hint=qty_match is not None,
    )
    if not amount_entries:
        return None

    if strict_table:
        if qty_match is None and len(amount_entries) < 2:
            return None
    elif qty_match is None:
        # Mimo striktní tabulku bereme jen výrazně cenové řádky.
        if not (len(amount_entries) >= 2 or (has_currency_marker and len(amount_entries) >= 1)):
            return None

    total_price = amount_entries[-1][0]
    if abs(total_price) < 0.01:
        return None

    name_end = qty_match.start() if qty_match else amount_entries[0][1]
    name = line[:name_end].strip(" -;:")
    name = re.sub(r"^(?:položka|polozka|item)\s*[:\-]\s*", "", name, flags=re.IGNORECASE).strip(" -;:")
    if _looks_like_invalid_item_name(name):
        return None

    quantity = _parse_decimal(qty_match.group(1)) if qty_match else None
    unit = qty_match.group(2).lower() if qty_match else None

    item: dict[str, Any] = {
        "name": name,
        "quantity": quantity,
        "unit": unit,
        "total_price": round(float(total_price), 2),
        "currency": currency,
    }

    if len(amount_entries) >= 2:
        unit_price = amount_entries[-2][0]
        if abs(unit_price) > 0.01:
            item["unit_price"] = round(float(unit_price), 2)

    return item


def _extract_items_from_table(lines: list[str], currency: str) -> list[dict[str, Any]]:
    table_start_idx: Optional[int] = None
    for idx, raw_line in enumerate(lines):
        line = " ".join(str(raw_line or "").split())
        if ITEM_TABLE_HEADER_RE.search(line):
            table_start_idx = idx
            break

    if table_start_idx is None:
        return []

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_line in lines[table_start_idx + 1:]:
        line = " ".join(str(raw_line or "").split())
        lower = line.lower()
        if not line:
            if items:
                break
            continue
        if _is_summary_line(lower):
            if items:
                break
            continue

        parsed = _parse_strict_table_row(line, currency=currency)
        if not parsed:
            parsed = _parse_item_line(raw_line=line, currency=currency, strict_table=True)
        if not parsed:
            continue
        dedupe_key = f"{str(parsed.get('name') or '').lower()}|{parsed.get('total_price')}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(parsed)
        if len(items) >= 25:
            break
    return items


def _extract_items(lines: list[str], currency: str, source_type: str = "invoice") -> list[dict[str, Any]]:
    table_items = _extract_items_from_table(lines, currency=currency)
    if table_items:
        return table_items

    conservative_mode = str(source_type or "").strip().lower() in {"invoice", "delivery_note", "work_order", "receipt"}
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_line in lines:
        parsed = _parse_item_line(raw_line=raw_line, currency=currency, strict_table=conservative_mode)
        if not parsed:
            continue

        dedupe_key = f"{str(parsed.get('name') or '').lower()}|{parsed.get('total_price')}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(parsed)
        if len(items) >= 25:
            break

    return items


def _sanitize_document_items(
    raw_items: Any,
    *,
    total_with_vat: Optional[float],
    currency: str,
) -> tuple[list[dict[str, Any]], int]:
    source_items = raw_items if isinstance(raw_items, list) else []
    parsed_total = _parse_decimal(total_with_vat)
    max_allowed = max(float(parsed_total) * 1.5, 100_000.0) if parsed_total and parsed_total > 0 else 500_000.0

    sanitized: list[dict[str, Any]] = []
    seen: set[str] = set()
    invalid_count = 0

    for raw in source_items:
        if not isinstance(raw, dict):
            invalid_count += 1
            continue

        name = " ".join(str(raw.get("name") or "").split()).strip()
        if not name or _looks_like_invalid_item_name(name):
            invalid_count += 1
            continue

        total_price = _parse_decimal(raw.get("total_price"))
        if total_price is None or float(total_price) <= 0:
            invalid_count += 1
            continue
        if float(total_price) > max_allowed:
            invalid_count += 1
            continue

        quantity = _parse_decimal(raw.get("quantity"))
        unit_price = _parse_decimal(raw.get("unit_price"))
        unit = str(raw.get("unit") or "").strip().lower() or None
        item_currency = str(raw.get("currency") or currency or "CZK").strip().upper() or "CZK"

        dedupe_key = f"{name.lower()}|{round(float(total_price), 2):.2f}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        normalized_item: dict[str, Any] = {
            "name": name,
            "quantity": round(float(quantity), 3) if quantity is not None else None,
            "unit": unit,
            "total_price": round(float(total_price), 2),
            "currency": item_currency,
        }
        if unit_price is not None and float(unit_price) > 0:
            normalized_item["unit_price"] = round(float(unit_price), 2)
        sanitized.append(normalized_item)

    return sanitized[:25], invalid_count


def _parsed_payload_needs_reparse(parsed_data: dict[str, Any]) -> bool:
    if not isinstance(parsed_data, dict):
        return False
    raw_items = parsed_data.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return False

    currency = str(parsed_data.get("currency") or "CZK").upper()
    total_with_vat = _parse_decimal(parsed_data.get("total_with_vat"))
    sanitized_items, invalid_count = _sanitize_document_items(
        raw_items,
        total_with_vat=total_with_vat,
        currency=currency,
    )

    if invalid_count <= 0:
        return False
    if not sanitized_items:
        return True
    if invalid_count >= max(2, len(raw_items) // 2):
        return True
    return False


def _safe_load_parsed_payload(raw_payload: Optional[str]) -> dict[str, Any]:
    if not raw_payload:
        return {}
    try:
        payload = json.loads(raw_payload)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _try_reparse_ingestion_entity(entity: ServiceDocumentIngestion) -> bool:
    parsed_data = _safe_load_parsed_payload(entity.parsed_payload_json)
    if not _parsed_payload_needs_reparse(parsed_data):
        return False

    source_text = str(entity.extracted_text or "").strip()
    extraction_warning: Optional[str] = None
    extraction_engine: Optional[str] = parsed_data.get("extraction_engine")

    stored_path_raw = str(entity.stored_file_path or "").strip()
    if stored_path_raw:
        try:
            source_path = Path(stored_path_raw)
            if not source_path.is_absolute():
                source_path = SERVICE_DOCS_DIR / source_path
            source_path = source_path.resolve()
            docs_root = SERVICE_DOCS_DIR.resolve()

            if docs_root in source_path.parents and source_path.is_file():
                raw_content = source_path.read_bytes()
                extracted_text, warning, engine = _extract_text_from_file(
                    content=raw_content,
                    file_name=entity.original_filename,
                    mime_type=entity.original_mime_type,
                )
                if extracted_text.strip():
                    source_text = extracted_text.strip()
                extraction_warning = warning
                extraction_engine = engine
        except Exception as exc:
            extraction_warning = f"Re-parse souboru selhal: {exc}"

    if not source_text:
        return False

    reparsed = _parse_document_payload(
        source_type=str(entity.source_type or "invoice"),
        extracted_text=source_text,
        manual_text=None,
        manual_note=None,
        extraction_engine=extraction_engine or parsed_data.get("extraction_engine"),
        extraction_warning=extraction_warning or parsed_data.get("extraction_warning"),
    )
    reparsed_currency = str(reparsed.get("currency") or entity.currency or "CZK").upper()
    reparsed_total = _parse_decimal(reparsed.get("total_with_vat"))
    reparsed_items, reparsed_invalid = _sanitize_document_items(
        reparsed.get("items"),
        total_with_vat=reparsed_total,
        currency=reparsed_currency,
    )
    old_items, old_invalid = _sanitize_document_items(
        parsed_data.get("items"),
        total_with_vat=_parse_decimal(parsed_data.get("total_with_vat")),
        currency=str(parsed_data.get("currency") or entity.currency or "CZK").upper(),
    )
    reparsed["items"] = reparsed_items

    still_noisy = _parsed_payload_needs_reparse(reparsed)
    if still_noisy and len(reparsed_items) <= len(old_items):
        return False
    if len(reparsed_items) == 0 and len(old_items) == 0 and reparsed_invalid >= old_invalid:
        return False

    parse_confidence = float(reparsed.get("confidence") or 0.0)
    processing_status = "processed"
    if not source_text.strip():
        processing_status = "failed"
    elif parse_confidence < 0.35:
        processing_status = "needs_review"

    issue_date_obj = _parse_date(str(reparsed.get("issue_date") or "")) if reparsed.get("issue_date") else None
    due_date_obj = _parse_date(str(reparsed.get("due_date") or "")) if reparsed.get("due_date") else None

    entity.extracted_text = source_text
    entity.parsed_payload_json = json.dumps(_json_safe(reparsed), ensure_ascii=False)
    entity.parse_confidence = parse_confidence
    entity.processing_status = processing_status
    entity.document_number = reparsed.get("document_number")
    entity.supplier_name = reparsed.get("supplier_name")
    entity.issue_date = issue_date_obj
    entity.due_date = due_date_obj
    entity.currency = reparsed.get("currency") or "CZK"
    entity.subtotal_without_vat = reparsed.get("subtotal_without_vat")
    entity.vat_amount = reparsed.get("vat_amount")
    entity.total_with_vat = reparsed.get("total_with_vat")
    entity.labor_total = reparsed.get("labor_total")
    entity.materials_total = reparsed.get("materials_total")
    entity.updated_at = datetime.utcnow()
    return True


def _extract_document_number(text: str) -> Optional[str]:
    patterns = [
        r"(?:číslo\s*(?:faktury|dokladu)|faktura\s*č\.?|doklad\s*č\.?|invoice\s*(?:no\.?|#))\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9\-\/]{2,40})",
        r"\b(FV[-/ ]?\d{3,}|VS[-/ ]?\d{3,}|[0-9]{4,}[A-Za-z0-9\-\/]*)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_customer_name(lines: list[str]) -> Optional[str]:
    customer_keywords = (
        "odběratel",
        "odberatel",
        "customer",
        "bill to",
        "fakturováno",
        "fakturovano",
    )
    for idx, line in enumerate(lines[:30]):
        lower = line.lower()
        if any(key in lower for key in customer_keywords):
            if ":" in line:
                candidate = line.split(":", 1)[1].strip()
                if len(candidate) >= 3:
                    return candidate[:160]
            if idx + 1 < len(lines):
                candidate = lines[idx + 1].strip()
                if len(candidate) >= 3:
                    candidate_lower = candidate.lower()
                    if not any(
                        bad in candidate_lower
                        for bad in ("ič", "ico", "dič", "dic", "datum", "faktura", "invoice")
                    ):
                        return candidate[:160]
    return None


def _is_contact_or_meta_line(lower_line: str) -> bool:
    return any(
        token in lower_line
        for token in (
            "telefon",
            "phone",
            "email",
            "e-mail",
            "web",
            "www.",
            "http://",
            "https://",
            "účet",
            "ucet",
            "banka",
            "iban",
            "swift",
            "ičo",
            "ico",
            "dič",
            "dic",
            "variabilní symbol",
            "variabilni symbol",
            "forma úhrady",
            "forma uhrady",
            "datum",
            "splatnost",
            "faktura",
            "invoice",
            "dodací list",
            "dodaci list",
            "daňový doklad",
            "danovy doklad",
        )
    )


def _looks_like_company_candidate(candidate: str) -> bool:
    text = str(candidate or "").strip()
    if len(text) < 3 or len(text) > 180:
        return False
    lower = text.lower()
    if _is_contact_or_meta_line(lower):
        return False
    if EMAIL_RE.search(text):
        return False
    if DATE_RE.search(text):
        return False
    if re.fullmatch(r"[0-9\s/.,:;\-]+", text):
        return False
    if not any(char.isalpha() for char in text):
        return False
    return True


def _extract_supplier_name(lines: list[str]) -> Optional[str]:
    supplier_markers = ("dodavatel", "supplier")
    customer_markers = ("odběratel", "odberatel", "customer", "bill to")

    supplier_idx: Optional[int] = None
    for idx, line in enumerate(lines[:60]):
        lower = line.lower()
        if any(marker in lower for marker in supplier_markers):
            supplier_idx = idx
            break

    # 1) Preferovat explicitní blok "Dodavatel".
    if supplier_idx is not None:
        supplier_line = lines[supplier_idx]
        if ":" in supplier_line:
            inline = supplier_line.split(":", 1)[1].strip()
            if _looks_like_company_candidate(inline):
                return inline[:160]
        for candidate in lines[supplier_idx + 1:supplier_idx + 8]:
            if _looks_like_company_candidate(candidate):
                return candidate[:160]

    # 2) Fallback: hlavička dokumentu před blokem odběratele.
    customer_idx = None
    for idx, line in enumerate(lines[:80]):
        lower = line.lower()
        if any(marker in lower for marker in customer_markers):
            customer_idx = idx
            break
    header_limit = customer_idx if customer_idx is not None else min(len(lines), 28)
    header_lines = lines[:max(min(header_limit, 28), 8)]

    ranked_candidates: list[tuple[int, str]] = []
    for candidate in header_lines:
        stripped = candidate.strip()
        if not _looks_like_company_candidate(stripped):
            continue
        lower = stripped.lower()
        score = 0
        if any(token in lower for token in ("s.r.o", "a.s", "v.o.s", "spol.", "servis", "auto", "pneu", "motors", "garage", "firma")):
            score += 3
        if "/" in stripped:
            score += 1
        if len(stripped) <= 80:
            score += 1
        ranked_candidates.append((score, stripped))

    if ranked_candidates:
        ranked_candidates.sort(key=lambda item: item[0], reverse=True)
        return ranked_candidates[0][1][:160]

    # 3) Poslední fallback: první čitelný text bez metadat.
    for line in lines[:15]:
        stripped = line.strip()
        if _looks_like_company_candidate(stripped):
            return stripped[:120]
    return None


def _extract_supplier_email(lines: list[str], full_text: str) -> Optional[str]:
    for line in lines[:80]:
        lower = line.lower()
        if "email" in lower or "e-mail" in lower:
            match = EMAIL_RE.search(line)
            if match:
                return match.group(0).strip().lower()
    match = EMAIL_RE.search(full_text or "")
    if match:
        return match.group(0).strip().lower()
    return None


def _extract_supplier_website(lines: list[str], full_text: str) -> Optional[str]:
    for line in lines[:100]:
        lower = line.lower()
        if "web" in lower or "www." in lower or "http://" in lower or "https://" in lower:
            match = WEBSITE_RE.search(line)
            if not match:
                continue
            candidate = match.group(1).strip()
            if "@" in candidate:
                continue
            if not candidate.lower().startswith(("http://", "https://")):
                candidate = f"https://{candidate}"
            return candidate
    for match in WEBSITE_RE.finditer(full_text or ""):
        candidate = match.group(1).strip()
        if "@" in candidate:
            continue
        if not candidate.lower().startswith(("http://", "https://")):
            candidate = f"https://{candidate}"
        return candidate
    return None


def _extract_service_summary(lines: list[str]) -> Optional[str]:
    table_idx: Optional[int] = None
    for idx, line in enumerate(lines):
        if ITEM_TABLE_HEADER_RE.search(line):
            table_idx = idx
            break
    if table_idx is None:
        return None

    for candidate in reversed(lines[max(0, table_idx - 8):table_idx]):
        stripped = str(candidate or "").strip()
        if len(stripped) < 5:
            continue
        lower = stripped.lower()
        if _is_contact_or_meta_line(lower):
            continue
        if DATE_RE.search(stripped):
            continue
        if any(token in lower for token in ("vozidlo", "spz", "odběratel", "odberatel", "dodavatel")):
            continue
        return stripped[:240]
    return None


def _extract_technician_name(lines: list[str], full_text: str) -> Optional[str]:
    patterns = [
        r"(?:vyhotovil|provedl|technik|mechanik)\s*:\s*([A-Za-zÀ-ž][A-Za-zÀ-ž .\-]{1,80})",
        r"(?:zpracoval|pracoval)\s*:\s*([A-Za-zÀ-ž][A-Za-zÀ-ž .\-]{1,80})",
    ]
    text = str(full_text or "")
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        name = match.group(1).strip()
        name = re.split(
            r"(?:převzal|prevzal|k\s*úhradě|k\s*uhrade)\s*:?",
            name,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" -,:;")
        if len(name) >= 3 and any(char.isalpha() for char in name):
            return name[:120]

    for idx, line in enumerate(lines[:120]):
        lower = line.lower()
        if "vyhotovil" in lower or "technik" in lower or "mechanik" in lower:
            if ":" in line:
                inline = line.split(":", 1)[1].strip()
                if len(inline) >= 3 and any(char.isalpha() for char in inline):
                    return inline[:120]
            if idx + 1 < len(lines):
                candidate = lines[idx + 1].strip()
                if len(candidate) >= 3 and any(char.isalpha() for char in candidate):
                    return candidate[:120]
    return None


def _extract_technician_initials(name: Optional[str]) -> Optional[str]:
    raw = str(name or "").strip()
    if not raw:
        return None
    parts = [part for part in re.split(r"[\s\-]+", raw) if part]
    if not parts:
        return None
    initials = "".join(part[0].upper() for part in parts[:3] if part and part[0].isalpha())
    return initials or None


def _detect_currency(text: str) -> str:
    lower = text.lower()
    if "eur" in lower or "€" in text:
        return "EUR"
    if "czk" in lower or "kč" in lower or "kc" in lower:
        return "CZK"
    return "CZK"


def _calculate_confidence(parsed: dict[str, Any], full_text: str) -> float:
    score = 0.0
    if len((full_text or "").strip()) > 50:
        score += 0.15
    if parsed.get("document_number"):
        score += 0.1
    if parsed.get("supplier_name"):
        score += 0.1
    if parsed.get("customer_name"):
        score += 0.05
    if parsed.get("issue_date"):
        score += 0.1
    if parsed.get("due_date"):
        score += 0.05
    if parsed.get("total_with_vat") is not None:
        score += 0.2
    if parsed.get("subtotal_without_vat") is not None:
        score += 0.1
    if parsed.get("vat_amount") is not None:
        score += 0.1
    if parsed.get("labor_total") is not None or parsed.get("materials_total") is not None:
        score += 0.1
    if parsed.get("items"):
        score += 0.1

    if score <= 0 and (full_text or "").strip():
        score = 0.15
    return round(min(score, 0.98), 2)


def _try_extract_text_from_pdf(content: bytes) -> tuple[str, Optional[str]]:
    try:
        from PyPDF2 import PdfReader
    except Exception:
        return "", "PyPDF2 není dostupné"

    try:
        reader = PdfReader(BytesIO(content))
        pages: list[str] = []
        for page in reader.pages[:20]:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(page_text)
        return "\n".join(pages).strip(), None
    except Exception as exc:
        return "", f"PDF extrakce selhala: {exc}"


def _try_extract_text_from_image(content: bytes) -> tuple[str, Optional[str]]:
    try:
        from PIL import Image
    except Exception:
        return "", "Pillow není dostupné"
    try:
        import pytesseract
    except Exception:
        return "", "pytesseract není dostupné"

    try:
        image = Image.open(BytesIO(content))
        text = pytesseract.image_to_string(image, lang="ces+eng")
        return (text or "").strip(), None
    except Exception as exc:
        return "", f"OCR extrakce selhala: {exc}"


def _decode_text_bytes(content: bytes) -> str:
    for encoding in ("utf-8", "cp1250", "latin-1"):
        try:
            return content.decode(encoding)
        except Exception:
            continue
    return content.decode("utf-8", errors="ignore")


def _extract_text_from_file(
    *,
    content: bytes,
    file_name: Optional[str],
    mime_type: Optional[str],
) -> tuple[str, Optional[str], str]:
    name = (file_name or "").lower()
    mime = (mime_type or "").lower()

    if mime == "application/pdf" or name.endswith(".pdf"):
        text, warning = _try_extract_text_from_pdf(content)
        return text, warning, "pdf"

    if mime.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")):
        text, warning = _try_extract_text_from_image(content)
        return text, warning, "image-ocr"

    if (
        mime.startswith("text/")
        or name.endswith(".txt")
        or name.endswith(".csv")
        or name.endswith(".json")
        or name.endswith(".xml")
    ):
        return _decode_text_bytes(content), None, "text"

    return _decode_text_bytes(content), None, "binary-text-fallback"


def _decode_base64_payload(payload: str) -> bytes:
    raw = str(payload or "").strip()
    if not raw:
        return b""
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Soubor není validní base64 payload: {exc}") from exc


def _store_uploaded_file(file_name: Optional[str], content: bytes) -> str:
    suffix = Path(file_name or "").suffix.lower()
    if len(suffix) > 10:
        suffix = ""
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_name = f"doc_{stamp}_{secrets.token_hex(6)}{suffix}"
    target = SERVICE_DOCS_DIR / safe_name
    target.write_bytes(content)
    return str(target)


def _sanitize_file_stem(filename: Optional[str]) -> str:
    stem = Path(str(filename or "doklad")).stem
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return cleaned[:64] or "doklad"


def _store_service_record_attachment(
    *,
    vehicle: VehicleModel,
    current_user: Customer,
    file_name: Optional[str],
    file_mime_type: Optional[str],
    content: bytes,
) -> dict[str, Any]:
    if not content:
        raise HTTPException(status_code=422, detail="Nahraný soubor je prázdný.")

    filename = str(file_name or "doklad")
    extension = Path(filename).suffix.lower().strip()
    mime_type = str(file_mime_type or "").lower().strip() or "application/octet-stream"
    if not extension:
        if mime_type == "application/pdf":
            extension = ".pdf"
        elif mime_type.startswith("image/"):
            extension = ".jpg"
        elif mime_type.startswith("text/"):
            extension = ".txt"
        else:
            extension = ".bin"

    tenant_id = int(getattr(vehicle, "tenant_id", None) or getattr(current_user, "tenant_id", None) or 0)
    target_dir = SERVICE_RECORD_ATTACHMENTS_DIR / f"tenant_{tenant_id}" / f"vehicle_{int(vehicle.id)}"
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_stem = _sanitize_file_stem(filename)
    unique_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{safe_stem}_{secrets.token_hex(4)}{extension}"
    target_file = target_dir / unique_name
    target_file.write_bytes(content)

    storage_key = target_file.relative_to(SERVICE_RECORD_ATTACHMENTS_DIR).as_posix()
    return {
        "file_name": filename,
        "mime_type": mime_type,
        "file_size": len(content),
        "storage_key": storage_key,
        "download_url": f"/api/v1/vehicles/{int(vehicle.id)}/records/attachments/download?key={storage_key}",
    }


def _to_iso_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()  # type: ignore[no-any-return]
        except Exception:
            return None
    return None


def _normalize_parsed_items(items_raw: Any, currency: str) -> list[dict[str, Any]]:
    if not isinstance(items_raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in items_raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or _looks_like_invalid_item_name(name):
            continue
        quantity = _parse_decimal(item.get("quantity"))
        unit = str(item.get("unit") or "").strip() or None
        unit_price = _parse_decimal(item.get("unit_price"))
        total_price = _parse_decimal(item.get("total_price"))
        if total_price is None and quantity is not None and unit_price is not None:
            total_price = round(float(quantity) * float(unit_price), 2)
        if total_price is None:
            continue
        payload = {
            "name": name,
            "quantity": quantity,
            "unit": unit,
            "total_price": round(float(total_price), 2),
            "currency": str(item.get("currency") or currency).upper(),
        }
        if unit_price is not None:
            payload["unit_price"] = round(float(unit_price), 2)
        normalized.append(payload)
        if len(normalized) >= 30:
            break
    return normalized


def _is_labor_item_name_or_unit(name: Any, unit: Any) -> bool:
    unit_value = str(unit or "").strip().lower()
    if unit_value in {"h", "hod", "hod.", "hodina", "hodiny", "hr", "nh"}:
        return True

    lower_name = str(name or "").strip().lower()
    if not lower_name:
        return False

    labor_keywords = (
        "práce",
        "prace",
        "servisní práce",
        "servisni prace",
        "hodinová sazba",
        "hodinova sazba",
        "diagnost",
        "montáž",
        "montaz",
        "demontáž",
        "demontaz",
        "oprava",
        "seřízení",
        "serizeni",
    )
    return any(keyword in lower_name for keyword in labor_keywords)


def _infer_labor_material_breakdown(items: list[dict[str, Any]]) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    labor_total = 0.0
    materials_total = 0.0
    labor_hours = 0.0
    labor_hour_rate: Optional[float] = None
    labor_found = False
    material_found = False

    for item in items:
        if not isinstance(item, dict):
            continue
        total_price = _parse_decimal(item.get("total_price"))
        if total_price is None or float(total_price) <= 0:
            continue

        name = item.get("name")
        unit = item.get("unit")
        quantity = _parse_decimal(item.get("quantity"))
        unit_price = _parse_decimal(item.get("unit_price"))
        is_labor = _is_labor_item_name_or_unit(name, unit)

        if is_labor:
            labor_found = True
            labor_total += float(total_price)

            unit_value = str(unit or "").strip().lower()
            if quantity is not None and quantity > 0 and unit_value in {"h", "hod", "hod.", "hodina", "hodiny", "hr", "nh"}:
                labor_hours += float(quantity)
                if labor_hour_rate is None and unit_price is not None and unit_price > 0:
                    labor_hour_rate = float(unit_price)
                elif labor_hour_rate is None:
                    labor_hour_rate = float(total_price) / float(quantity)
            elif labor_hour_rate is None and unit_price is not None and unit_price > 0:
                labor_hour_rate = float(unit_price)
        else:
            material_found = True
            materials_total += float(total_price)

    return (
        round(labor_total, 2) if labor_found else None,
        round(materials_total, 2) if material_found else None,
        round(labor_hours, 2) if labor_hours > 0 else None,
        round(float(labor_hour_rate), 2) if labor_hour_rate is not None and labor_hour_rate > 0 else None,
    )


def _build_service_report_payload(parsed_data: dict[str, Any], source_type: str) -> dict[str, Any]:
    supplier_email = parsed_data.get("supplier_email")
    supplier_website = parsed_data.get("supplier_website")
    service_link = parsed_data.get("service_link") or supplier_website or (f"mailto:{supplier_email}" if supplier_email else None)
    currency = str(parsed_data.get("currency") or "CZK").upper()
    items = _normalize_parsed_items(parsed_data.get("items"), currency)

    inferred_labor_total, inferred_materials_total, inferred_labor_hours, inferred_labor_hour_rate = _infer_labor_material_breakdown(items)
    labor_total = _parse_decimal(parsed_data.get("labor_total"))
    materials_total = _parse_decimal(parsed_data.get("materials_total"))
    labor_hours = _parse_decimal(parsed_data.get("labor_hours"))
    labor_hour_rate = _parse_decimal(parsed_data.get("labor_hour_rate"))

    if labor_total is None:
        labor_total = inferred_labor_total
    if materials_total is None:
        materials_total = inferred_materials_total
    if labor_hours is None:
        labor_hours = inferred_labor_hours
    if labor_hour_rate is None:
        labor_hour_rate = inferred_labor_hour_rate

    issue_description = str(parsed_data.get("issue_description") or "").strip() or None
    if not issue_description:
        issue_description = str(parsed_data.get("service_summary") or "").strip() or None

    return {
        "source_type": source_type,
        "document_number": parsed_data.get("document_number"),
        "supplier_name": parsed_data.get("supplier_name"),
        "supplier_email": supplier_email,
        "supplier_website": supplier_website,
        "service_link": service_link,
        "customer_name": parsed_data.get("customer_name"),
        "service_summary": parsed_data.get("service_summary"),
        "issue_description": issue_description,
        "technician_name": parsed_data.get("technician_name"),
        "technician_initials": parsed_data.get("technician_initials"),
        "issue_date": _to_iso_date(parsed_data.get("issue_date")),
        "due_date": _to_iso_date(parsed_data.get("due_date")),
        "currency": currency,
        "labor_hours": labor_hours,
        "labor_hour_rate": labor_hour_rate,
        "subtotal_without_vat": parsed_data.get("subtotal_without_vat"),
        "vat_amount": parsed_data.get("vat_amount"),
        "total_with_vat": parsed_data.get("total_with_vat"),
        "labor_total": labor_total,
        "materials_total": materials_total,
        "items": items,
    }


def _parse_document_payload(
    *,
    source_type: str,
    extracted_text: str,
    manual_text: Optional[str],
    manual_note: Optional[str],
    extraction_engine: Optional[str] = None,
    extraction_warning: Optional[str] = None,
) -> dict[str, Any]:
    manual = (manual_text or "").strip()
    combined_text = "\n".join(part for part in [extracted_text.strip(), manual] if part).strip()
    lines = [line.strip() for line in combined_text.splitlines() if line.strip()]
    currency = _detect_currency(combined_text)

    document_number = _extract_document_number(combined_text)
    supplier_name = _extract_supplier_name(lines)
    supplier_email = _extract_supplier_email(lines, combined_text)
    supplier_website = _extract_supplier_website(lines, combined_text)
    if supplier_name and (EMAIL_RE.search(str(supplier_name)) or _is_address_like_line(str(supplier_name))):
        supplier_name = None
    service_link = supplier_website or (f"mailto:{supplier_email}" if supplier_email else None)
    customer_name = _extract_customer_name(lines)
    service_summary = _extract_service_summary(lines)
    issue_description = (manual_note or "").strip() or None
    if not issue_description and service_summary:
        issue_description = service_summary
    technician_name = _extract_technician_name(lines, combined_text)
    technician_initials = _extract_technician_initials(technician_name)

    issue_date = _extract_date_by_labels(lines, ["datum vystavení", "vystaveno", "datum", "issue date"])
    due_date = _extract_date_by_labels(lines, ["splatnost", "due date"])
    if not issue_date:
        for match in DATE_RE.finditer(combined_text):
            parsed = _parse_date(match.group(1))
            if parsed:
                issue_date = parsed
                break

    subtotal_without_vat = _extract_amount_by_labels(
        lines,
        [
            "bez dph",
            "zaklad dane",
            "základ daně",
            "mezisoučet",
            "mezisoucet",
            "subtotal",
        ],
    )
    vat_amount = _extract_amount_by_labels(lines, ["dph", "vat"])
    total_with_vat = _extract_amount_by_labels(lines, ["celkem", "k úhradě", "k uhrade", "s dph", "total"])
    labor_total = _extract_amount_by_labels(lines, ["práce", "prace", "labor", "servisní práce", "servisni prace"])
    materials_total = _extract_amount_by_labels(
        lines,
        ["materiál", "material", "náhradní díly", "nahradni dily", "díly", "dily", "zboží", "zbozi", "parts"],
    )

    items = _extract_items(lines, currency=currency, source_type=source_type)

    if total_with_vat is not None and items:
        try:
            total_value = float(total_with_vat)
        except Exception:
            total_value = 0.0
        if total_value > 0:
            max_reasonable_item_total = max(total_value * 1.5, 100_000.0)
            sanitized_items: list[dict[str, Any]] = []
            for item in items:
                item_total = _parse_decimal(item.get("total_price"))
                if item_total is None:
                    continue
                if float(item_total) > max_reasonable_item_total:
                    continue
                sanitized_items.append(item)
            items = sanitized_items

    if total_with_vat is None and items:
        items_sum = sum(float(item.get("total_price") or 0) for item in items)
        if items_sum > 0:
            total_with_vat = round(items_sum, 2)

    if subtotal_without_vat is None and total_with_vat is not None and vat_amount is not None:
        subtotal_without_vat = round(max(total_with_vat - vat_amount, 0), 2)

    inferred_labor_total, inferred_materials_total, _inferred_labor_hours, _inferred_labor_hour_rate = _infer_labor_material_breakdown(items)
    if labor_total is None and inferred_labor_total is not None:
        labor_total = inferred_labor_total
    if materials_total is None and inferred_materials_total is not None:
        materials_total = inferred_materials_total

    if materials_total is None and labor_total is None and items:
        materials_total = round(sum(float(item.get("total_price") or 0) for item in items), 2)

    if subtotal_without_vat is None and (labor_total is not None or materials_total is not None):
        subtotal_without_vat = round(float(labor_total or 0.0) + float(materials_total or 0.0), 2)

    parsed = {
        "source_type": source_type,
        "document_number": document_number,
        "supplier_name": supplier_name,
        "supplier_email": supplier_email,
        "supplier_website": supplier_website,
        "service_link": service_link,
        "customer_name": customer_name,
        "service_summary": service_summary,
        "issue_description": issue_description,
        "technician_name": technician_name,
        "technician_initials": technician_initials,
        "issue_date": issue_date,
        "due_date": due_date,
        "currency": currency,
        "subtotal_without_vat": subtotal_without_vat,
        "vat_amount": vat_amount,
        "total_with_vat": total_with_vat,
        "labor_total": labor_total,
        "materials_total": materials_total,
        "items": items,
        "manual_note": (manual_note or "").strip() or None,
        "extraction_engine": extraction_engine,
        "extraction_warning": extraction_warning,
    }
    parsed["confidence"] = _calculate_confidence(parsed, combined_text)
    return parsed


def _build_service_record_description(parsed_data: dict[str, Any]) -> str:
    source_type = str(parsed_data.get("source_type") or "doklad")
    document_number = str(parsed_data.get("document_number") or "").strip()
    service_summary = str(parsed_data.get("service_summary") or "").strip()
    items = parsed_data.get("items") or []

    source_label_map = {
        "invoice": "Import faktury",
        "delivery_note": "Import dodacího listu",
        "work_order": "Import zakázkového listu",
        "receipt": "Import účtenky",
        "manual": "Import ručního zápisu",
    }
    prefix = source_label_map.get(source_type, "Import dokladu")
    suffix = f" {document_number}" if document_number else ""

    if service_summary:
        cleaned_summary = " ".join(service_summary.split())
        if len(cleaned_summary) > 140:
            cleaned_summary = cleaned_summary[:137].rstrip() + "..."
        return f"{prefix}{suffix}: {cleaned_summary}"

    if items:
        first_names = [str(item.get("name") or "").strip() for item in items[:3]]
        first_names = [item for item in first_names if item]
        if first_names:
            return f"{prefix}{suffix}: {', '.join(first_names)}"
    return f"{prefix}{suffix}".strip()


def _build_ingestion_response(
    entity: ServiceDocumentIngestion,
    *,
    customer_name: Optional[str] = None,
    customer_email: Optional[str] = None,
    vehicle_label: Optional[str] = None,
) -> dict[str, Any]:
    parsed_data: dict[str, Any] = _safe_load_parsed_payload(entity.parsed_payload_json)
    parsed_currency = str(parsed_data.get("currency") or entity.currency or "CZK").upper()
    parsed_total = _parse_decimal(parsed_data.get("total_with_vat"))
    if parsed_total is None:
        parsed_total = _parse_decimal(entity.total_with_vat)
    sanitized_items, _invalid_items = _sanitize_document_items(
        parsed_data.get("items"),
        total_with_vat=parsed_total,
        currency=parsed_currency,
    )
    if isinstance(parsed_data.get("items"), list):
        parsed_data["items"] = sanitized_items
    if not parsed_data.get("currency"):
        parsed_data["currency"] = parsed_currency

    extracted_text_value = str(entity.extracted_text or "")
    has_file_input = bool(entity.original_filename or entity.stored_file_path)
    extraction_engine = parsed_data.get("extraction_engine")
    extraction_warning = parsed_data.get("extraction_warning")

    if has_file_input and extraction_engine == "manual":
        input_method = "file"
    elif has_file_input and extracted_text_value.strip():
        input_method = "file+manual"
    elif has_file_input:
        input_method = "file"
    elif extracted_text_value.strip():
        input_method = "manual"
    else:
        input_method = "unknown"

    return {
        "id": entity.id,
        "customer_id": entity.customer_id,
        "vehicle_id": entity.vehicle_id,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "vehicle_label": vehicle_label,
        "source_type": entity.source_type,
        "original_filename": entity.original_filename,
        "original_mime_type": entity.original_mime_type,
        "document_number": entity.document_number,
        "supplier_name": entity.supplier_name,
        "issue_date": entity.issue_date.isoformat() if entity.issue_date else None,
        "due_date": entity.due_date.isoformat() if entity.due_date else None,
        "currency": entity.currency,
        "subtotal_without_vat": entity.subtotal_without_vat,
        "vat_amount": entity.vat_amount,
        "total_with_vat": entity.total_with_vat,
        "labor_total": entity.labor_total,
        "materials_total": entity.materials_total,
        "parse_confidence": entity.parse_confidence,
        "processing_status": entity.processing_status,
        "auto_created_service_record_id": entity.auto_created_service_record_id,
        "input_method": input_method,
        "extraction_engine": extraction_engine,
        "extraction_warning": extraction_warning,
        "extracted_text_preview": extracted_text_value[:260] if extracted_text_value else None,
        "created_at": entity.created_at.isoformat() if entity.created_at else None,
        "parsed_data": parsed_data,
    }


@router.get("/partner-public-profile", response_model=PartnerPublicProfileOutV1)
def get_partner_public_profile(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Texty a seznamy, které servis zobrazuje majitelům vozidel v katalogu partnerů."""
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)
    raw = getattr(current_user, "partner_public_profile", None)
    return PartnerPublicProfileOutV1(**partner_public_profile_from_db(raw))


@router.put("/partner-public-profile", response_model=PartnerPublicProfileOutV1)
def put_partner_public_profile(
    payload: PartnerPublicProfileUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)
    try:
        blob = partner_public_profile_to_stored_json(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    current_user.partner_public_profile = blob
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return PartnerPublicProfileOutV1(**partner_public_profile_from_db(current_user.partner_public_profile))


@router.get("/customers")
def list_service_customers(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    links = (
        db.query(ServiceCustomerLink, Customer)
        .join(Customer, ServiceCustomerLink.customer_id == Customer.id)
        .filter(
            ServiceCustomerLink.service_customer_id == current_user.id,
            ServiceCustomerLink.status.in_(("active", "invited", "pending_customer_confirm")),
        )
        .order_by(ServiceCustomerLink.updated_at.desc(), Customer.name.asc(), Customer.email.asc())
        .all()
    )

    result = []
    for link, customer in links:
        shared_vehicle_ids = _get_shared_vehicle_ids_for_pair(
            db,
            service_customer_id=current_user.id,
            customer_id=customer.id,
        )
        customer_vehicles = _get_customer_vehicle_rows(db, customer)
        last_service_date = (
            db.query(func.max(ServiceRecordModel.performed_at))
            .join(VehicleOwnership, VehicleOwnership.vehicle_id == ServiceRecordModel.vehicle_id)
            .filter(
                VehicleOwnership.customer_id == customer.id,
                VehicleOwnership.is_active.is_(True),
                or_(
                    ServiceRecordModel.user_id == current_user.id,
                    ServiceRecordModel.created_by_service_customer_id == current_user.id,
                ),
            )
            .scalar()
        )
        result.append(
            {
                "customer_link_id": link.id,
                "customer_id": customer.id,
                "email": customer.email,
                "name": customer.name,
                "phone": customer.phone,
                "vehicles_count": len(customer_vehicles),
                "shared_vehicles_count": len(shared_vehicle_ids),
                "last_service_date": last_service_date.isoformat() if last_service_date else None,
                "note": link.note,
                "internal_service_note": getattr(link, "internal_service_note", None),
                "link_status": link.status,
                "link_source": getattr(link, "link_source", None),
                "created_at": link.created_at.isoformat() if link.created_at else None,
            }
        )
    return result


@router.get("/customers/search")
def search_service_customers_deprecated(
    query: str = Query(..., min_length=2, max_length=160),
    limit: int = Query(default=10, ge=1, le=25),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(
        status_code=410,
        detail="Vyhledávání podle volného textu již není podporováno. Použijte POST /api/v1/services/workspace/customers/search s přesným e-mailem nebo telefonem.",
    )


@router.get("/customers/{customer_id}/detail")
def get_service_customer_detail(
    customer_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    customer = _get_linked_customer_or_404(db, current_user, int(customer_id))
    return _build_customer_detail_payload(db, current_user=current_user, customer=customer)


def _central_lookup_identifier(payload: CentralVehicleLookupRequestV1) -> tuple[str, str, str]:
    query = str(payload.query or "").strip()
    qtype = str(payload.query_type or "auto").lower()
    vin_norm = normalize_vin(query)
    plate_norm = normalize_plate(query)
    if qtype == "vin" or (qtype == "auto" and len(vin_norm) == 17):
        validate_normalized_vin(vin_norm, required=True)
        return query, vin_norm, "vin"
    if qtype == "plate" or qtype == "auto":
        if not plate_norm:
            raise HTTPException(status_code=422, detail="Zadejte SPZ nebo VIN vozidla.")
        return query, plate_norm, "plate"
    raise HTTPException(status_code=422, detail="Neplatný typ lookupu.")


def _safe_vehicle_preview(vehicle: VehicleModel) -> dict[str, Any]:
    return {
        "vehicle_id": int(vehicle.id),
        "brand": getattr(vehicle, "brand", None),
        "model": getattr(vehicle, "model", None),
        "year": getattr(vehicle, "year", None),
        "vin_masked": masked_vin(getattr(vehicle, "vin", None) or getattr(vehicle, "normalized_vin", None)),
        "plate_masked": masked_plate(getattr(vehicle, "plate", None) or getattr(vehicle, "normalized_plate", None)),
        "in_system": True,
    }


def _service_access_status_for_vehicle(db: Session, *, current_user: Customer, vehicle: VehicleModel) -> tuple[str, bool]:
    if (
        active_owner_assignment(db, int(vehicle.id)) is None
        and getattr(vehicle, "provisioned_by_service_customer_id", None) == getattr(current_user, "id", None)
        and vehicle_state(db, vehicle) == "service_provisioned_unowned"
    ):
        return "approved", False
    link = get_active_vehicle_service_link(db, service_customer_id=int(current_user.id), vehicle_id=int(vehicle.id))
    if link:
        return "approved", False
    request_row = (
        db.query(ServiceAccessRequest)
        .filter(
            ServiceAccessRequest.service_customer_id == int(current_user.id),
            ServiceAccessRequest.vehicle_id == int(vehicle.id),
        )
        .order_by(ServiceAccessRequest.id.desc())
        .first()
    )
    if request_row:
        status = str(request_row.status or "pending")
        return status, status in {"rejected", "revoked"}
    return "not_requested", True


def _audit_central_lookup(
    db: Session,
    *,
    current_user: Customer,
    raw_query: str,
    normalized_query: str,
    identifier_type: str,
    vehicle: Optional[VehicleModel],
    owner_id: Optional[int],
    result_status: str,
) -> ServiceVehicleLookupAudit:
    audit = ServiceVehicleLookupAudit(
        tenant_id=int(getattr(current_user, "tenant_id", None) or 1),
        service_customer_id=int(current_user.id),
        lookup_query_raw=raw_query or None,
        lookup_query_normalized=normalized_query or None,
        lookup_query_hash=query_hash(normalized_query),
        lookup_identifier_type=identifier_type,
        matched_vehicle_id=int(vehicle.id) if vehicle else None,
        matched_owner_customer_id=owner_id,
        result_status=result_status,
        returned_candidate_count=1 if vehicle else 0,
        created_at=datetime.utcnow(),
    )
    db.add(audit)
    db.flush()
    write_global_audit_log(
        db,
        entity_type="service_vehicle_lookup",
        entity_id=int(audit.id),
        action="service_vehicle_lookup",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(getattr(current_user, "tenant_id", None) or 1),
        vehicle_id=int(vehicle.id) if vehicle else None,
        metadata={
            "identifier_type": identifier_type,
            "result_status": result_status,
            "query_hash": query_hash(normalized_query),
        },
    )
    db.flush()
    return audit


@router.post("/vehicles/lookup")
def central_service_vehicle_lookup(
    payload: CentralVehicleLookupRequestV1,
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    raw_query, normalized_query, identifier_type = _central_lookup_identifier(payload)
    vehicle, matched_by = find_vehicle_by_identifiers(
        db,
        vin=normalized_query if identifier_type == "vin" else None,
        plate=normalized_query if identifier_type == "plate" else None,
    )
    if not vehicle:
        _audit_central_lookup(
            db,
            current_user=current_user,
            raw_query=raw_query,
            normalized_query=normalized_query,
            identifier_type=identifier_type,
            vehicle=None,
            owner_id=None,
            result_status="not_found",
        )
        db.commit()
        return {
            "found": False,
            "status": "not_found",
            "can_create_unowned_vehicle": True,
            "message": "Vozidlo není v systému.",
        }

    owner_assignment = active_owner_assignment(db, int(vehicle.id))
    owner_id = int(owner_assignment.customer_id) if owner_assignment else None
    access_status, can_request_access = _service_access_status_for_vehicle(db, current_user=current_user, vehicle=vehicle)
    if access_status == "approved":
        status = "found_access_approved"
        result_status = "already_approved"
    elif access_status == "pending":
        status = "found_access_required"
        result_status = "pending_request"
    elif owner_id is None:
        status = "found_service_unowned"
        result_status = "service_unowned"
    else:
        status = "found_access_required"
        result_status = "matched"

    _audit_central_lookup(
        db,
        current_user=current_user,
        raw_query=raw_query,
        normalized_query=normalized_query,
        identifier_type=matched_by if matched_by != "none" else identifier_type,
        vehicle=vehicle,
        owner_id=owner_id,
        result_status=result_status,
    )
    db.commit()
    body: dict[str, Any] = {
        "found": True,
        "status": status,
        "vehicle_preview": _safe_vehicle_preview(vehicle),
        "access": {
            "status": access_status,
            "can_request_access": bool(can_request_access and owner_id is not None),
        },
        "owner_data": None,
        "service_history": None,
        "documents": None,
        "photos": None,
        "prices": None,
        "invoices": None,
    }
    if access_status == "approved":
        body["access"]["scope"] = ["vehicle_history_read", "create_service_record"]
        body["can_open_detail"] = True
    return body


@router.post("/vehicles/provision-unowned")
def provision_unowned_service_vehicle(
    payload: ServiceProvisionUnownedVehicleRequestV1,
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    vin_norm = normalize_vin(payload.vin)
    plate_norm = normalize_plate(payload.plate)
    validate_normalized_vin(vin_norm, required=False)
    if not vin_norm and not plate_norm:
        raise HTTPException(status_code=422, detail="Zadejte VIN nebo SPZ.")

    existing_by_vin, _ = find_vehicle_by_identifiers(db, vin=vin_norm or None)
    if existing_by_vin:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "vehicle_exists",
                "message": "Vozidlo s tímto VIN už v centrální databázi existuje.",
                "vehicle_id": int(existing_by_vin.id),
                "status": vehicle_state(db, existing_by_vin),
            },
        )

    if not vin_norm and plate_norm:
        plate_candidate, matched_by = find_vehicle_by_identifiers(db, plate=plate_norm)
        if plate_candidate:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "plate_candidate_requires_review",
                    "message": "SPZ už má kandidáta. Bez VIN nelze automaticky založit nebo sloučit vozidlo.",
                    "vehicle_id": int(plate_candidate.id),
                    "matched_by": matched_by,
                },
            )

    vehicle = VehicleModel(
        tenant_id=int(getattr(current_user, "tenant_id", None) or 1),
        user_email=f"_service_unowned_{int(current_user.id)}_{int(datetime.utcnow().timestamp())}@unassigned.vehicle.internal",
        nickname=f"{payload.brand} {payload.model}".strip(),
        brand=payload.brand.strip(),
        model=payload.model.strip(),
        year=payload.year,
        vin=vin_norm or None,
        plate=payload.plate.strip().upper() if payload.plate else None,
        current_mileage_km=payload.mileage,
        notes=(payload.intake_note or "").strip() or None,
        provisioned_by_service_customer_id=int(current_user.id),
        provisioned_by_service_tenant_id=int(getattr(current_user, "tenant_id", None) or 0) or None,
        global_vehicle_status="service_provisioned_unowned",
        source_origin="service_created",
        claim_status="unclaimed",
        status="active",
    )
    sync_vehicle_identity_fields(vehicle)
    db.add(vehicle)
    db.flush()
    write_global_audit_log(
        db,
        entity_type="vehicle",
        entity_id=int(vehicle.id),
        action="service_unowned_vehicle_created",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(getattr(current_user, "tenant_id", None) or 1),
        vehicle_id=int(vehicle.id),
        metadata={
            "normalized_vin": vin_norm or None,
            "normalized_plate": plate_norm or None,
            "source_origin": "service_created",
        },
    )
    db.commit()
    db.refresh(vehicle)
    return {
        "created": True,
        "vehicle_id": int(vehicle.id),
        "status": "service_provisioned_unowned",
        "message": "Vozidlo evidováno bez majitele.",
        "vehicle_preview": _safe_vehicle_preview(vehicle),
    }


@router.post("/vehicle-lookup", response_model=ServiceVehicleLookupResponseV1)
def lookup_vehicle_for_service(
    payload: ServiceVehicleLookupRequestV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Servisní lookup vozidla podle SPZ/VIN. Před schválením vrací jen omezenou identifikaci.
    """
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    raw_query = str(payload.query or "").strip()
    raw_parts = [part for part in re.split(r"[\s,;/]+", raw_query.upper()) if part]
    query_parts: list[str] = []
    for part in raw_parts:
        if part not in query_parts:
            query_parts.append(part)

    resolved_hits: list[dict[str, Any]] = []
    for query_part in (query_parts[:2] or [raw_query]):
        vehicle, owner_customer, normalized_query, identifier_type, result_status = resolve_vehicle_for_lookup(
            db,
            current_user=current_user,
            query=query_part,
        )
        resolved_hits.append(
            {
                "query_part": query_part,
                "vehicle": vehicle,
                "owner_customer": owner_customer,
                "normalized_query": normalized_query,
                "identifier_type": identifier_type,
                "result_status": result_status,
            }
        )

    conflict_hits = [
        item for item in resolved_hits
        if item["vehicle"] is not None
    ]
    if len(conflict_hits) >= 2 and len({int(item["vehicle"].id) for item in conflict_hits}) > 1:
        log_vehicle_lookup(
            db,
            current_user=current_user,
            raw_query=raw_query,
            normalized_query=" / ".join(str(item["normalized_query"]) for item in resolved_hits if item["normalized_query"]),
            identifier_type="mixed",
            vehicle=None,
            owner_customer=None,
            result_status="conflict",
            returned_candidate_count=len(conflict_hits),
        )
        db.commit()
        return {
            "query": raw_query,
            "result_count": len(conflict_hits),
            "has_multiple_matches": True,
            "has_conflict": True,
            "identifier_type": "mixed",
            "candidates": [
                {
                    "id": "vehicle-lookup-conflict",
                    "status": "conflict",
                    "can_request_access": False,
                    "can_open_detail": False,
                    "can_create_work_order": False,
                    "blocking_reason": "VIN a SPZ ukazují na různé záznamy. Zkontrolujte vstup a otevřete správný detail zvlášť.",
                    "conflicting_candidates": [
                        _lookup_candidate_payload(
                            vehicle=item["vehicle"],
                            owner_customer=item["owner_customer"],
                            status=item["result_status"],
                            can_request_access=item["result_status"] not in {"already_approved", "pending_request", "owner_missing"},
                            can_open_detail=True,
                            can_create_work_order=item["result_status"] == "already_approved",
                            blocking_reason=_vehicle_blocking_reason(
                                status=item["result_status"],
                                linked_customer=bool(
                                    item["owner_customer"]
                                    and _get_active_link(
                                        db,
                                        service_customer_id=int(current_user.id),
                                        customer_id=int(item["owner_customer"].id),
                                    )
                                ),
                            ),
                            match_score=_lookup_match_meta(
                                identifier_type=str(item["identifier_type"] or "unknown"),
                                query=str(item["normalized_query"] or ""),
                                vehicle=item["vehicle"],
                            )[0],
                            match_type=_lookup_match_meta(
                                identifier_type=str(item["identifier_type"] or "unknown"),
                                query=str(item["normalized_query"] or ""),
                                vehicle=item["vehicle"],
                            )[1],
                        )
                        for item in conflict_hits
                    ],
                }
            ],
        }

    primary_hit = next(
        (
            item for item in resolved_hits
            if item["vehicle"] is not None or item["result_status"] in {"owner_missing"}
        ),
        resolved_hits[0],
    )
    vehicle = primary_hit["vehicle"]
    owner_customer = primary_hit["owner_customer"]
    normalized_query = str(primary_hit["normalized_query"] or "")
    identifier_type = str(primary_hit["identifier_type"] or "unknown")
    result_status = str(primary_hit["result_status"] or "not_found")
    match_score, match_type = _lookup_match_meta(
        identifier_type=identifier_type,
        query=normalized_query,
        vehicle=vehicle,
    )

    candidates: list[dict[str, Any]] = []
    if vehicle:
        linked_customer = bool(
            owner_customer
            and _get_active_link(
                db,
                service_customer_id=int(current_user.id),
                customer_id=int(owner_customer.id),
            )
        )
        candidates.append(
            _lookup_candidate_payload(
                vehicle=vehicle,
                owner_customer=owner_customer,
                status=result_status,
                can_request_access=result_status not in {"already_approved", "pending_request", "owner_missing"},
                can_open_detail=True,
                can_create_work_order=result_status == "already_approved" and linked_customer,
                blocking_reason=_vehicle_blocking_reason(
                    status=result_status,
                    linked_customer=linked_customer,
                ),
                match_score=match_score,
                match_type=match_type,
            )
        )

    log_vehicle_lookup(
        db,
        current_user=current_user,
        raw_query=raw_query,
        normalized_query=normalized_query,
        identifier_type=identifier_type,
        vehicle=vehicle,
        owner_customer=owner_customer,
        result_status=result_status,
        returned_candidate_count=len(candidates),
    )
    db.commit()
    return {
        "query": raw_query,
        "result_count": len(candidates),
        "has_multiple_matches": len(candidates) > 1,
        "has_conflict": False,
        "identifier_type": identifier_type,
        "candidates": candidates,
    }


@router.post("/customers/{customer_id}/link")
def link_existing_customer_by_id(
    customer_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    customer = db.query(Customer).filter(Customer.id == int(customer_id)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Účet zákazníka nebyl nalezen.")
    if customer.id == current_user.id:
        raise HTTPException(status_code=400, detail="Nelze propojit servisní účet se sebou samým.")

    try:
        _, created = _upsert_service_customer_link(
            db,
            service_customer_id=current_user.id,
            service_tenant_id=current_user.tenant_id,
            target_customer=customer,
            note="Propojeno z vyhledání zákazníka",
        )
        write_global_audit_log(
            db,
            entity_type="service_customer_link",
            entity_id=int(customer.id),
            action="link_existing_customer",
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
            tenant_id=getattr(current_user, "tenant_id", None),
            metadata={
                "customer_id": int(customer.id),
                "created": bool(created),
            },
        )
        db.commit()
        return {
            "linked": True,
            "created": created,
            "message": "Zákazník byl úspěšně propojen." if created else "Zákazník už byl propojen, vazba byla potvrzena.",
            "customer_id": int(customer.id),
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Nepodařilo se propojit zákazníka: {exc}") from exc


@router.patch("/customers/{customer_id}/link")
def patch_service_customer_link_note(
    customer_id: int,
    payload: ServiceCustomerLinkNotePatchRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    link = _get_active_link(db, service_customer_id=current_user.id, customer_id=int(customer_id))
    if not link:
        raise HTTPException(status_code=404, detail="Aktivní vazba se zákazníkem neexistuje.")

    note_clean = (payload.note or "").strip() or None
    link.note = note_clean
    link.updated_at = datetime.utcnow()
    write_global_audit_log(
        db,
        entity_type="service_customer_link",
        entity_id=int(customer_id),
        action="patch_link_note",
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=getattr(current_user, "tenant_id", None),
        metadata={"customer_id": int(customer_id)},
    )
    db.commit()
    return {"customer_id": int(customer_id), "note": note_clean}


@router.delete("/customers/{customer_id}/link")
def delete_service_customer_link(
    customer_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    link = _get_active_link(db, service_customer_id=current_user.id, customer_id=int(customer_id))
    if not link:
        raise HTTPException(status_code=404, detail="Aktivní vazba se zákazníkem neexistuje.")

    link.status = "archived"
    link.updated_at = datetime.utcnow()
    write_global_audit_log(
        db,
        entity_type="service_customer_link",
        entity_id=int(customer_id),
        action="unlink_customer",
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=getattr(current_user, "tenant_id", None),
        metadata={"customer_id": int(customer_id)},
    )
    db.commit()
    return {"unlinked": True, "customer_id": int(customer_id)}


@router.post("/access-requests")
def create_service_access_request(
    payload: ServiceAccessRequestCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Servis vytvoří žádost o přístup k vozidlu nalezenému přes SPZ/VIN.
    """
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    raw_query = str(payload.lookup_query or "").strip()
    vehicle: Optional[VehicleModel] = None
    owner_customer: Optional[Customer] = None
    normalized_query = ""
    identifier_type = "unknown"
    result_status = "not_found"

    if payload.vehicle_id:
        vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(payload.vehicle_id)).first()
        if vehicle:
            owner_customer = get_primary_vehicle_owner(db, vehicle)
            normalized_query, identifier_type = normalize_lookup_query(raw_query)
            result_status = "matched" if owner_customer else "owner_missing"
    else:
        vehicle, owner_customer, normalized_query, identifier_type, result_status = resolve_vehicle_for_lookup(
            db,
            current_user=current_user,
            query=raw_query,
        )

    audit = log_vehicle_lookup(
        db,
        current_user=current_user,
        raw_query=raw_query,
        normalized_query=normalized_query,
        identifier_type=identifier_type,
        vehicle=vehicle,
        owner_customer=owner_customer,
        result_status=result_status,
        returned_candidate_count=1 if vehicle and owner_customer else 0,
    )

    if not vehicle or not owner_customer:
        db.commit()
        raise HTTPException(status_code=404, detail="Pro zadanou SPZ nebo VIN nebylo nalezeno schvalovatelné vozidlo.")
    if owner_customer.id == current_user.id:
        db.commit()
        raise HTTPException(status_code=400, detail="Servis nemůže žádat o přístup ke svému vlastnímu vozidlu.")

    active_link = (
        db.query(VehicleServiceLink.id)
        .filter(
            VehicleServiceLink.service_customer_id == current_user.id,
            VehicleServiceLink.vehicle_id == vehicle.id,
            VehicleServiceLink.status == "approved",
        )
        .first()
    )
    if active_link:
        db.commit()
        raise HTTPException(status_code=409, detail="Servis už má k tomuto vozidlu schválený přístup.")

    existing_pending = (
        db.query(ServiceAccessRequest)
        .filter(
            ServiceAccessRequest.service_customer_id == current_user.id,
            ServiceAccessRequest.vehicle_id == vehicle.id,
            ServiceAccessRequest.status == "pending",
        )
        .order_by(ServiceAccessRequest.id.desc())
        .first()
    )
    if existing_pending:
        db.commit()
        return {
            "created": False,
            "request_id": int(existing_pending.id),
            "vehicle_id": int(vehicle.id),
            "status": "pending",
            "message": "Žádost už čeká na potvrzení.",
            "email_sent": False,
            "notification": {
                "channel": "email",
                "sent": False,
                "reason": "existing_pending",
                "message": "Žádost už čeká na potvrzení. Nový e-mail nebyl odeslán.",
            },
        }

    request_row = ServiceAccessRequest(
        tenant_id=vehicle.tenant_id or current_user.tenant_id or owner_customer.tenant_id or 1,
        service_customer_id=current_user.id,
        owner_customer_id=owner_customer.id,
        vehicle_id=vehicle.id,
        lookup_audit_id=audit.id,
        requested_scope="history_read_create_record",
        status="pending",
        request_message=(payload.note or "").strip() or None,
        requested_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(request_row)
    db.flush()
    try:
        notify_owner_service_access_requested(
            db,
            owner_customer_id=int(owner_customer.id),
            service=current_user,
            vehicle=vehicle,
            request_message=request_row.request_message,
        )
    except Exception as exc:
        logger.warning("[SERVICE_WORKSPACE] In-app oznámení majiteli o žádosti o přístup selhalo: %s", exc)
    try:
        email_result = try_email_owner_about_service_access_request(
            db,
            owner=owner_customer,
            service=current_user,
            vehicle=vehicle,
            request_id=int(request_row.id),
            tenant_id=getattr(request_row, "tenant_id", None),
        )
    except Exception as exc:
        logger.warning("[SERVICE_WORKSPACE] E-mail majiteli (žádost o přístup) selhalo neočekávaně: %s", exc)
        email_result = {
            "attempted": True,
            "sent": False,
            "reason": "send_failed",
            "error": None,
        }
    db.commit()
    db.refresh(request_row)
    notif_msg = _service_access_email_notification_message(email_result)
    return {
        "created": True,
        "request_id": int(request_row.id),
        "vehicle_id": int(vehicle.id),
        "status": "pending",
        "message": "Žádost o přístup k vozidlu byla odeslána. Čeká se na vyjádření uživatele.",
        "email_sent": bool(email_result.get("sent")),
        "notification": {
            "channel": "email",
            "sent": bool(email_result.get("sent")),
            "reason": email_result.get("reason") if not email_result.get("sent") else None,
            "message": notif_msg,
        },
    }


@router.get("/approved-vehicles", response_model=ServiceApprovedVehicleListOutV1)
def list_approved_service_vehicles(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Vrátí vozidla, ke kterým má servis schválený přístup.
    """
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    rows = (
        db.query(VehicleServiceLink, VehicleModel, Customer)
        .join(VehicleModel, VehicleServiceLink.vehicle_id == VehicleModel.id)
        .outerjoin(Customer, VehicleServiceLink.owner_customer_id == Customer.id)
        .filter(
            VehicleServiceLink.service_customer_id == current_user.id,
            VehicleServiceLink.status == "approved",
            VehicleModel.status != "archived",
        )
        .order_by(VehicleServiceLink.updated_at.desc(), VehicleServiceLink.id.desc())
        .all()
    )
    return {
        "items": [
            {
                "id": int(vehicle.id),
                "customer_id": int(owner.id) if owner else None,
                "customer_name": (
                    owner.name or owner.email
                    if owner and owner.id != current_user.id
                    else (
                        f"Čeká na registraci: {vehicle.user_email}"
                        if getattr(vehicle, "user_email", None) and str(vehicle.user_email).lower() != str(current_user.email).lower()
                        else (owner.name or owner.email if owner else "Čeká na registraci")
                    )
                ),
                "vehicle_name": vehicle_label(vehicle),
                "vehicle_plate": vehicle.plate,
                "last_shared_at": link.updated_at.isoformat() if link.updated_at else None,
            }
            for link, vehicle, owner in rows
        ]
    }


@router.get("/vehicles/{vehicle_id}/detail")
def get_service_vehicle_detail(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno.")
    return _build_vehicle_detail_payload(db, current_user=current_user, vehicle=vehicle)


@router.get("/vehicles/{vehicle_id}/qr", response_model=VehicleQrTokenOutV1)
def get_vehicle_qr_token(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    require_service_vehicle_link(
        db,
        current_user=current_user,
        vehicle_id=vehicle_id,
        require_create_record=False,
    )
    qr_token = _get_vehicle_qr_token(db, vehicle_id=vehicle_id)
    if not qr_token:
        raise HTTPException(status_code=404, detail="QR token pro vozidlo zatím neexistuje.")
    if not is_vehicle_qr_signature_valid(qr_token):
        raise HTTPException(status_code=409, detail="QR token neprošel integritní kontrolou.")
    return _build_vehicle_qr_payload(qr_token)


@router.post("/vehicles/{vehicle_id}/qr", response_model=VehicleQrTokenOutV1)
def create_vehicle_qr_token(
    vehicle_id: int,
    payload: VehicleQrTokenCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    require_service_vehicle_link(
        db,
        current_user=current_user,
        vehicle_id=vehicle_id,
        require_create_record=False,
    )
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno.")

    existing = _get_vehicle_qr_token(db, vehicle_id=vehicle_id)
    if existing:
        if not is_vehicle_qr_signature_valid(existing):
            raise HTTPException(status_code=409, detail="Existující QR token neprošel integritní kontrolou.")
        return _build_vehicle_qr_payload(existing)

    qr_token = _issue_vehicle_qr_token(
        db,
        current_user=current_user,
        vehicle=vehicle,
        public_mode=payload.public_mode,
        explicit_full_consent=payload.explicit_full_consent,
    )
    write_global_audit_log(
        db,
        entity_type="vehicle_qr_token",
        entity_id=int(qr_token.id),
        action="vehicle_qr_create",
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=getattr(vehicle, "tenant_id", None),
        metadata={
            "vehicle_id": int(vehicle.id),
            "public_mode": qr_token.public_mode,
            "explicit_full_consent": bool(qr_token.explicit_full_consent),
        },
    )
    db.commit()
    db.refresh(qr_token)
    return _build_vehicle_qr_payload(qr_token)


@router.delete("/vehicles/{vehicle_id}/qr")
def revoke_vehicle_qr_token(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    require_service_vehicle_link(
        db,
        current_user=current_user,
        vehicle_id=vehicle_id,
        require_create_record=False,
    )
    qr_token = _get_vehicle_qr_token(db, vehicle_id=vehicle_id)
    if not qr_token:
        raise HTTPException(status_code=404, detail="QR token pro vozidlo nebyl nalezen.")

    qr_token.active = False
    qr_token.revoked_at = datetime.utcnow()
    write_global_audit_log(
        db,
        entity_type="vehicle_qr_token",
        entity_id=int(qr_token.id),
        action="vehicle_qr_revoke",
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=getattr(qr_token, "tenant_id", None),
        metadata={"vehicle_id": int(vehicle_id)},
    )
    db.commit()
    return {"revoked": True, "vehicle_id": int(vehicle_id)}


@router.post("/vehicles/{vehicle_id}/qr/regenerate", response_model=VehicleQrTokenOutV1)
def regenerate_vehicle_qr_token(
    vehicle_id: int,
    payload: VehicleQrTokenCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    require_service_vehicle_link(
        db,
        current_user=current_user,
        vehicle_id=vehicle_id,
        require_create_record=False,
    )
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno.")

    existing = _get_vehicle_qr_token(db, vehicle_id=vehicle_id)
    if existing:
        existing.active = False
        existing.revoked_at = datetime.utcnow()

    qr_token = _issue_vehicle_qr_token(
        db,
        current_user=current_user,
        vehicle=vehicle,
        public_mode=payload.public_mode,
        explicit_full_consent=payload.explicit_full_consent,
    )
    write_global_audit_log(
        db,
        entity_type="vehicle_qr_token",
        entity_id=int(qr_token.id),
        action="vehicle_qr_regenerate",
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=getattr(vehicle, "tenant_id", None),
        metadata={
            "vehicle_id": int(vehicle.id),
            "public_mode": qr_token.public_mode,
            "previous_token_id": int(existing.id) if existing else None,
        },
    )
    db.commit()
    db.refresh(qr_token)
    return _build_vehicle_qr_payload(qr_token)


@router.post("/customers/link-existing")
def link_existing_customer(
    payload: LinkExistingCustomerRequest,
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    if str(payload.lookup_id or "").strip():
        cen_payload = CustomerLinkFromLookupRequestV1(
            lookup_id=str(payload.lookup_id).strip(),
            consent_basis=(payload.consent_basis or "").strip(),
            consent_note=(payload.consent_note or "").strip(),
            internal_service_note=payload.internal_service_note,
        )
        return execute_customer_link_from_lookup(
            payload=cen_payload,
            request=request,
            current_user=current_user,
            db=db,
        )

    customer_email_req = payload.customer_email
    if customer_email_req is None:
        raise HTTPException(status_code=422, detail="Chybí customer_email nebo lookup_id.")
    customer = _find_customer_by_email(db, customer_email_req)
    if not customer:
        raise HTTPException(status_code=404, detail="Účet s tímto emailem nebyl nalezen.")

    if customer.id == current_user.id:
        raise HTTPException(status_code=400, detail="Nelze propojit servisní účet se sebou samým.")

    try:
        link_row, created = _upsert_service_customer_link(
            db,
            service_customer_id=current_user.id,
            service_tenant_id=current_user.tenant_id,
            target_customer=customer,
            note=(payload.note or "").strip() or None,
        )
        write_global_audit_log(
            db,
            entity_type="service_customer_link",
            entity_id=int(customer.id),
            action="link_existing_customer_by_email",
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
            tenant_id=getattr(current_user, "tenant_id", None),
            metadata={
                "customer_id": int(customer.id),
                "created": bool(created),
                "channel": "email",
            },
        )

        service_name = (current_user.name or current_user.email or "Servis").strip()
        owner_disp = (customer.name or "uživateli").strip()
        email_result = _send_direct_customer_link_notice_email(
            to_email=str(customer.email),
            owner_name=owner_disp,
            service_name=service_name,
        )
        sent_ok = bool(email_result.get("sent"))
        reason_out = None if sent_ok else email_result.get("reason")
        msg = (
            "Zákazník byl propojen a informační e-mail byl odeslán."
            if sent_ok
            else "Zákazník byl propojen, ale informační e-mail se nepodařilo odeslat."
        )

        direct_link_audit_action = (
            "SERVICE_CUSTOMER_DIRECT_LINK_EMAIL_SENT" if sent_ok else "SERVICE_CUSTOMER_DIRECT_LINK_EMAIL_FAILED"
        )
        write_global_audit_log(
            db,
            entity_type="service_customer_security",
            entity_id=int(customer.id),
            action=direct_link_audit_action,
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
            tenant_id=getattr(current_user, "tenant_id", None),
            metadata={
                "kind": "direct_link_existing_customer",
                "sent": sent_ok,
                "reason": reason_out,
                "customer_id": int(customer.id),
                "service_customer_link_id": int(link_row.id),
                "email_domain": _email_domain_for_audit(customer.email),
                "created": bool(created),
            },
            ip=(request.client.host if request.client else "")[:128],
            user_agent=(request.headers.get("user-agent") or "")[:2000],
        )
        db.commit()
        return {
            "linked": True,
            "pending_customer_confirm": False,
            "created": created,
            "customer_id": customer.id,
            "customer_user_id": int(customer.id),
            "email_sent": sent_ok,
            "notification": {
                "channel": "email",
                "sent": sent_ok,
                "reason": reason_out,
                "message": msg,
            },
            "message": msg,
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Nepodařilo se propojit zákazníka: {exc}") from exc


@router.get("/invitations")
def list_service_invitations(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    rows = (
        db.query(ServiceCustomerInvite)
        .filter(ServiceCustomerInvite.service_customer_id == current_user.id)
        .order_by(ServiceCustomerInvite.sent_at.desc())
        .limit(limit)
        .all()
    )
    now = datetime.utcnow()
    changed = False
    for row in rows:
        if row.status == "pending" and row.expires_at and row.expires_at < now:
            row.status = "expired"
            row.updated_at = now
            changed = True
    if changed:
        db.commit()

    result = []
    for row in rows:
        normalized_status, status_label, is_completed = _invitation_status_meta(
            str(row.status or ""),
            accepted_at=row.accepted_at,
        )
        can_resend = normalized_status in {"pending", "expired", "cancelled"}
        result.append(
            {
                "id": row.id,
                "invite_email": row.invite_email,
                "invite_name": row.invite_name,
                "status": normalized_status,
                "status_label": status_label,
                "is_completed": bool(is_completed),
                "can_resend": bool(can_resend),
                "can_delete": True,
                "sent_at": row.sent_at.isoformat() if row.sent_at else None,
                "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                "linked_customer_id": row.linked_customer_id,
            }
        )
    return result


@router.post("/invitations/send")
def send_service_invitation(
    payload: SendServiceInviteRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    invite_email = _normalize_email(payload.invite_email)
    if not invite_email:
        raise HTTPException(status_code=422, detail="Email pozvánky je povinný.")

    existing_customer = _find_customer_by_email(db, invite_email)
    if existing_customer and existing_customer.id == current_user.id:
        raise HTTPException(status_code=400, detail="Nelze poslat pozvánku na servisní účet.")

    try:
        # U existujícího účtu provedeme okamžité propojení bez čekání.
        if existing_customer:
            _, created = _upsert_service_customer_link(
                db,
                service_customer_id=current_user.id,
                service_tenant_id=current_user.tenant_id,
                target_customer=existing_customer,
                note="Propojeno přes pozvánku servisu",
            )
            audit_invite = ServiceCustomerInvite(
                service_tenant_id=current_user.tenant_id,
                service_customer_id=current_user.id,
                invite_email=invite_email,
                invite_name=(payload.invite_name or "").strip() or None,
                invite_message=(payload.invite_message or "").strip() or None,
                token=secrets.token_urlsafe(24),
                status="accepted",
                linked_customer_id=existing_customer.id,
                linked_customer_tenant_id=existing_customer.tenant_id,
                sent_at=datetime.utcnow(),
                accepted_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=30),
            )
            db.add(audit_invite)
            db.commit()
            return {
                "already_linked": not created,
                "linked_now": True,
                "email_sent": False,
                "message": (
                    "Účet už byl propojen." if not created else "Existující účet byl automaticky propojen se servisem."
                ),
                "customer_id": existing_customer.id,
            }

        existing_pending_invite = (
            db.query(ServiceCustomerInvite)
            .filter(
                ServiceCustomerInvite.service_customer_id == current_user.id,
                func.lower(ServiceCustomerInvite.invite_email) == invite_email,
                ServiceCustomerInvite.status == "pending",
            )
            .order_by(ServiceCustomerInvite.sent_at.desc(), ServiceCustomerInvite.id.desc())
            .first()
        )
        if existing_pending_invite and (
            not existing_pending_invite.expires_at or existing_pending_invite.expires_at >= datetime.utcnow()
        ):
            return {
                "already_linked": False,
                "already_pending": True,
                "invite_id": int(existing_pending_invite.id),
                "email_sent": True,
                "registration_url": _build_invitation_url(existing_pending_invite.token),
                "message": "Pozvánka už byla dříve odeslána a stále čeká na přijetí.",
            }

        # Zneplatnit staré čekající pozvánky pro stejný e-mail od stejného servisu.
        (
            db.query(ServiceCustomerInvite)
            .filter(
                ServiceCustomerInvite.service_customer_id == current_user.id,
                func.lower(ServiceCustomerInvite.invite_email) == invite_email,
                ServiceCustomerInvite.status == "pending",
            )
            .update(
                {
                    ServiceCustomerInvite.status: "cancelled",
                    ServiceCustomerInvite.updated_at: datetime.utcnow(),
                },
                synchronize_session=False,
            )
        )

        token = secrets.token_urlsafe(32)
        invitation_url = _build_invitation_url(token)
        invite = ServiceCustomerInvite(
            service_tenant_id=current_user.tenant_id,
            service_customer_id=current_user.id,
            invite_email=invite_email,
            invite_name=(payload.invite_name or "").strip() or None,
            invite_message=(payload.invite_message or "").strip() or None,
            token=token,
            status="pending",
            sent_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
        db.add(invite)
        db.commit()

        email_sent = _send_invitation_email(
            service_user=current_user,
            invite_email=invite_email,
            invite_name=payload.invite_name,
            invite_message=payload.invite_message,
            invitation_url=invitation_url,
        )
        return {
            "already_linked": False,
            "email_sent": bool(email_sent),
            "registration_url": invitation_url,
            "message": (
                "Pozvánka byla odeslána na email zákazníka."
                if email_sent
                else "Pozvánka je vytvořena, ale SMTP není dostupné. Pošlete zákazníkovi registrační odkaz ručně."
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Nepodařilo se vytvořit pozvánku: {exc}") from exc


@router.post("/invitations/{invite_id}/resend")
def resend_service_invitation(
    invite_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    invite = (
        db.query(ServiceCustomerInvite)
        .filter(
            ServiceCustomerInvite.id == invite_id,
            ServiceCustomerInvite.service_customer_id == current_user.id,
        )
        .first()
    )
    if not invite:
        raise HTTPException(status_code=404, detail="Pozvánka nebyla nalezena.")

    now = datetime.utcnow()
    normalized_status, _, is_completed = _invitation_status_meta(str(invite.status or ""), accepted_at=invite.accepted_at)
    if is_completed or normalized_status == "accepted":
        raise HTTPException(status_code=400, detail="Pozvánka je už vyřízená, nelze ji znovu odeslat.")

    invite_email = _normalize_email(invite.invite_email)
    if not invite_email:
        raise HTTPException(status_code=422, detail="Pozvánka nemá validní email.")

    try:
        existing_customer = _find_customer_by_email(db, invite_email)
        if existing_customer and existing_customer.id != current_user.id:
            _upsert_service_customer_link(
                db,
                service_customer_id=current_user.id,
                service_tenant_id=current_user.tenant_id,
                target_customer=existing_customer,
                note="Propojeno přes opětovné odeslání pozvánky",
            )
            invite.status = "accepted"
            invite.accepted_at = now
            invite.linked_customer_id = existing_customer.id
            invite.linked_customer_tenant_id = existing_customer.tenant_id
            invite.updated_at = now
            db.commit()
            return {
                "resent": False,
                "linked_now": True,
                "status": "accepted",
                "message": "Účet zákazníka už existuje, pozvánka byla rovnou označena jako vyřízená.",
                "customer_id": existing_customer.id,
            }

        invite.token = secrets.token_urlsafe(32)
        invite.status = "pending"
        invite.sent_at = now
        invite.accepted_at = None
        invite.linked_customer_id = None
        invite.linked_customer_tenant_id = None
        invite.expires_at = now + timedelta(days=30)
        invite.updated_at = now
        invitation_url = _build_invitation_url(invite.token)
        db.commit()

        email_sent = _send_invitation_email(
            service_user=current_user,
            invite_email=invite_email,
            invite_name=invite.invite_name,
            invite_message=invite.invite_message,
            invitation_url=invitation_url,
        )

        return {
            "resent": True,
            "email_sent": bool(email_sent),
            "status": "pending",
            "registration_url": invitation_url,
            "message": (
                "Pozvánka byla znovu odeslána."
                if email_sent
                else "Pozvánka byla obnovena, ale SMTP není dostupné. Odkaz pošlete zákazníkovi ručně."
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Opětovné odeslání pozvánky selhalo: {exc}") from exc


@router.delete("/invitations/{invite_id}")
def delete_service_invitation(
    invite_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    invite = (
        db.query(ServiceCustomerInvite)
        .filter(
            ServiceCustomerInvite.id == invite_id,
            ServiceCustomerInvite.service_customer_id == current_user.id,
        )
        .first()
    )
    if not invite:
        raise HTTPException(status_code=404, detail="Pozvánka nebyla nalezena.")

    try:
        db.delete(invite)
        db.commit()
        return {"deleted": True, "invite_id": invite_id}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Smazání pozvánky selhalo: {exc}") from exc


@router.post("/invitations/accept")
def accept_service_invitation(
    payload: AcceptServiceInviteRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_service_workspace_schema(db)

    token = str(payload.token or "").strip()
    invite = db.query(ServiceCustomerInvite).filter(ServiceCustomerInvite.token == token).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Pozvánka nebyla nalezena.")

    now = datetime.utcnow()
    if invite.status == "accepted":
        if invite.linked_customer_id == current_user.id:
            return {"accepted": True, "message": "Pozvánka už byla dříve přijata."}
        raise HTTPException(status_code=409, detail="Pozvánka už byla použita jiným účtem.")

    if invite.status != "pending":
        raise HTTPException(status_code=400, detail="Pozvánka není aktivní.")

    if invite.expires_at and invite.expires_at < now:
        invite.status = "expired"
        invite.updated_at = now
        db.commit()
        raise HTTPException(status_code=400, detail="Pozvánka vypršela.")

    if _normalize_email(current_user.email) != _normalize_email(invite.invite_email):
        raise HTTPException(status_code=403, detail="Pozvánka patří jinému e-mailu.")

    try:
        _upsert_service_customer_link(
            db,
            service_customer_id=invite.service_customer_id,
            service_tenant_id=invite.service_tenant_id,
            target_customer=current_user,
            note="Propojeno přes přijatou pozvánku",
        )
        invite.status = "accepted"
        invite.accepted_at = now
        invite.linked_customer_id = current_user.id
        invite.linked_customer_tenant_id = current_user.tenant_id
        invite.updated_at = now
        db.commit()
        return {
            "accepted": True,
            "message": "Pozvánka byla přijata a účet je propojen se servisem.",
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Přijetí pozvánky selhalo: {exc}") from exc


@router.get("/customers/{customer_id}/vehicles")
def list_customer_vehicles(
    customer_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    customer = _get_linked_customer_or_404(db, current_user, customer_id)
    shared_vehicle_ids = _get_shared_vehicle_ids_for_pair(
        db,
        service_customer_id=current_user.id,
        customer_id=customer.id,
    )
    vehicles = _get_customer_vehicle_rows(db, customer)
    return [
        {
            "id": vehicle.id,
            "nickname": vehicle.nickname,
            "brand": vehicle.brand,
            "model": vehicle.model,
            "year": vehicle.year,
            "plate": vehicle.plate,
            "vin": vehicle.vin,
            "stk_valid_until": vehicle.stk_valid_until.isoformat() if vehicle.stk_valid_until else None,
            "current_mileage_km": vehicle.current_mileage_km,
            "last_stk_mileage_km": vehicle.last_stk_mileage_km,
            "mileage_checked_at": vehicle.mileage_checked_at.isoformat() if vehicle.mileage_checked_at else None,
            "created_at": vehicle.created_at.isoformat() if vehicle.created_at else None,
            "is_shared": int(vehicle.id) in shared_vehicle_ids,
        }
        for vehicle in vehicles
    ]


@router.get("/reservations/{reservation_id}/detail")
def get_service_workspace_reservation_detail(
    reservation_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    reservation = (
        db.query(ReservationModel)
        .filter(ReservationModel.id == int(reservation_id))
        .first()
    )
    if not reservation:
        raise HTTPException(status_code=404, detail="Rezervace nebyla nalezena.")
    if int(reservation.service_id or 0) != int(current_user.id) and str(current_user.role or "").lower() not in {"admin", "developer_admin"}:
        raise HTTPException(status_code=403, detail="Nemáte přístup k této rezervaci.")

    customer = db.query(Customer).filter(Customer.id == reservation.customer_id).first()
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == reservation.vehicle_id).first()
    linked_customer = bool(
        customer
        and _get_active_link(db, service_customer_id=int(current_user.id), customer_id=int(customer.id))
    )
    approved_vehicle = bool(
        vehicle
        and get_active_vehicle_service_link(
            db,
            service_customer_id=int(current_user.id),
            vehicle_id=int(vehicle.id),
        )
    )
    disclosure = "full" if linked_customer and approved_vehicle else "limited"
    can_create_work_order = bool(linked_customer and approved_vehicle and customer and vehicle)
    payload = _detail_state_payload(
        entity_type="reservation",
        entity_id=int(reservation.id),
        status=str(reservation.status or "PENDING"),
        can_open_detail=True,
        can_edit=str(reservation.status or "").upper() not in {"CANCELLED", "COMPLETED"},
        can_request_access=bool(vehicle and not approved_vehicle),
        can_create_work_order=can_create_work_order,
        blocking_reason=(
            "Rezervace je navázaná na klienta bez aktivní servisní vazby."
            if customer and not linked_customer
            else "K vozidlu z rezervace není schválený servisní přístup."
            if vehicle and not approved_vehicle
            else None
        ),
        disclosure=disclosure,
    )
    payload.update(
        {
            "reservation_id": int(reservation.id),
            "service_id": int(reservation.service_id),
            "customer_id": int(reservation.customer_id),
            "vehicle_id": int(reservation.vehicle_id),
            "service_type": reservation.service_type,
            "note": reservation.note if disclosure == "full" else None,
            "start_datetime": reservation.start_datetime.isoformat() if reservation.start_datetime else None,
            "end_datetime": reservation.end_datetime.isoformat() if reservation.end_datetime else None,
            "created_at": reservation.created_at.isoformat() if reservation.created_at else None,
            "source_platform": reservation.source_platform,
            "customer_name": (
                (customer.name or customer.email)
                if customer and disclosure == "full"
                else customer.name
                if customer
                else None
            ),
            "customer_email": customer.email if customer and disclosure == "full" else None,
            "customer_email_masked": _mask_email_value(customer.email if customer else None),
            "vehicle_name": (
                (
                    vehicle.nickname
                    or " ".join(part for part in [vehicle.brand, vehicle.model] if part).strip()
                    or vehicle.plate
                    or f"Vozidlo #{int(vehicle.id)}"
                )
                if vehicle
                else None
            ),
            "vehicle_plate": vehicle.plate if vehicle and disclosure == "full" else None,
            "vehicle_plate_masked": masked_plate(vehicle.plate) if vehicle else None,
            "vehicle_vin_masked": masked_vin(vehicle.vin) if vehicle else None,
            "customer_linked": linked_customer,
            "vehicle_access_approved": approved_vehicle,
        }
    )
    return payload


def _build_workspace_vehicle_row(
    *,
    tenant_id: int,
    owner_email: str,
    payload: ServiceWorkspaceVehicleCreateRequest,
) -> VehicleModel:
    normalized_plate = str(payload.plate or "").strip() or None
    normalized_vin = str(payload.vin or "").strip().upper() or None
    return VehicleModel(
        tenant_id=tenant_id,
        user_email=owner_email,
        nickname=str(payload.nickname or "").strip(),
        plate=normalized_plate,
        vin=normalized_vin,
        brand=str(payload.brand or "").strip() or None,
        model=str(payload.model or "").strip() or None,
        year=payload.year,
        engine=str(payload.engine or "").strip() or None,
        notes=str(payload.notes or "").strip() or None,
        stk_valid_until=payload.stk_valid_until,
        current_mileage_km=payload.current_mileage_km,
        last_stk_mileage_km=payload.last_stk_mileage_km,
        mileage_checked_at=datetime.utcnow() if payload.last_stk_mileage_km is not None else None,
        tyres_info=str(payload.tyres_info or "").strip() or None,
    )


@router.post("/customers/{customer_id}/vehicles")
def create_customer_vehicle(
    customer_id: int,
    payload: ServiceWorkspaceVehicleCreateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    customer = _get_active_linked_customer_or_404(db, current_user, customer_id)
    customer_email_key = _normalize_email(customer.email)
    if not customer_email_key:
        raise HTTPException(status_code=400, detail="Klient nemá platný email pro přiřazení vozidla.")

    tenant_id = getattr(customer, "tenant_id", None) or getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Nelze určit tenant pro nové vozidlo.")

    normalized_plate = str(payload.plate or "").strip() or None
    normalized_vin = str(payload.vin or "").strip().upper() or None
    if payload.orv_scan_id and not normalized_vin:
        raise HTTPException(status_code=422, detail="ORV scan vyžaduje doplněný VIN před uložením vozidla.")
    normalized_stk = payload.stk_valid_until
    if not normalized_stk:
        raise HTTPException(status_code=422, detail="Vyplňte platnost STK.")
    if (
        payload.current_mileage_km is not None
        and payload.last_stk_mileage_km is not None
        and payload.current_mileage_km < payload.last_stk_mileage_km
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Aktuální stav km nesmí být menší než poslední známý stav km ze STK/emisí "
                f"({payload.last_stk_mileage_km:,} km)."
            ).replace(",", " "),
        )

    # Deduplikace v rámci tenantu pro SPZ/VIN.
    if normalized_plate:
        duplicate_plate = (
            db.query(VehicleModel.id)
            .filter(
                VehicleModel.tenant_id == tenant_id,
                VehicleModel.plate == normalized_plate,
            )
            .first()
        )
        if duplicate_plate:
            raise HTTPException(status_code=409, detail="Vozidlo s touto SPZ už v tenantu existuje.")
    if normalized_vin:
        duplicate_vin = (
            db.query(VehicleModel.id)
            .filter(
                VehicleModel.tenant_id == tenant_id,
                VehicleModel.vin == normalized_vin,
            )
            .first()
        )
        if duplicate_vin:
            raise HTTPException(status_code=409, detail="Vozidlo s tímto VIN už v tenantu existuje.")

    try:
        assert_vehicle_quota(db, int(tenant_id))
    except LicenseError as exc:
        write_global_audit_log(
            db,
            entity_type="license",
            entity_id=int(tenant_id),
            action="vehicle_quota_denied_service_add_vehicle",
            actor_user_id=int(current_user.id),
            actor_role=getattr(current_user, "role", None),
            tenant_id=int(getattr(current_user, "tenant_id", None) or 0) or None,
            vehicle_id=None,
            metadata={
                "target_customer_id": int(customer.id),
                "target_customer_tenant_id": int(tenant_id),
                "code": getattr(exc, "code", None),
            },
        )
        raise exc

    build_payload = payload.model_copy(update={"stk_valid_until": normalized_stk})
    vehicle = _build_workspace_vehicle_row(
        tenant_id=tenant_id,
        owner_email=customer_email_key,
        payload=build_payload,
    )
    setattr(vehicle, "provisioned_by_service_customer_id", int(current_user.id))
    db.add(vehicle)
    db.flush()
    apply_orv_scan_to_vehicle(
        db=db,
        vehicle=vehicle,
        current_user=current_user,
        scan_id=payload.orv_scan_id,
        orv_number=payload.orv_number,
        use_owner_data=payload.orv_use_owner_data,
        data_trust_state=payload.data_trust_state or "verified_by_user",
        create_payload=payload.dict(),
    )
    ensure_vehicle_owner_assignment(
        db,
        vehicle=vehicle,
        owner=customer,
        assigned_by_customer_id=current_user.id,
        ownership_origin="service_workspace",
    )
    create_or_update_vehicle_service_link(
        db,
        tenant_id=int(tenant_id),
        service_customer_id=int(current_user.id),
        owner_customer_id=int(customer.id),
        vehicle_id=int(vehicle.id),
        approved_by_customer_id=int(customer.id),
        source_type="service_workspace_vehicle_create",
        note="Servis založil vozidlo pro klienta",
    )

    db.commit()
    db.refresh(vehicle)

    return {
        "id": vehicle.id,
        "customer_id": customer.id,
        "customer_email": customer.email,
        "nickname": vehicle.nickname,
        "plate": vehicle.plate,
        "vin": vehicle.vin,
        "orv_number": vehicle.orv_number,
        "orv_scan_source": vehicle.orv_scan_source,
        "data_trust_state": vehicle.data_trust_state,
        "brand": vehicle.brand,
        "model": vehicle.model,
        "year": vehicle.year,
        "engine": vehicle.engine,
        "stk_valid_until": vehicle.stk_valid_until.isoformat() if vehicle.stk_valid_until else None,
        "current_mileage_km": vehicle.current_mileage_km,
        "last_stk_mileage_km": vehicle.last_stk_mileage_km,
        "mileage_checked_at": vehicle.mileage_checked_at.isoformat() if vehicle.mileage_checked_at else None,
        "created_at": vehicle.created_at.isoformat() if vehicle.created_at else None,
        "is_shared": True,
        "message": "Vozidlo bylo přidáno ke klientovi a zpřístupněno servisu.",
    }


@router.post("/pending-vehicles")
def create_pending_vehicle_registration(
    payload: PendingVehicleRegistrationRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    invite_email = _normalize_email(payload.invite_email)
    if not invite_email:
        raise HTTPException(status_code=422, detail="Email budoucího vlastníka je povinný.")

    vehicle_payload = payload.vehicle
    normalized_vin = str(vehicle_payload.vin or "").strip().upper() or None
    if not normalized_vin:
        raise HTTPException(status_code=422, detail="Pro předregistraci vozidla je povinný VIN.")

    existing_vehicle = (
        db.query(VehicleModel)
        .filter(VehicleModel.vin == normalized_vin)
        .order_by(VehicleModel.created_at.asc(), VehicleModel.id.asc())
        .first()
    )
    if existing_vehicle:
        raise HTTPException(
            status_code=409,
            detail="Vozidlo s tímto VIN už v databázi existuje. Použijte lookup a navazující žádost o přístup.",
        )

    existing_customer = _find_customer_by_email(db, invite_email)
    if existing_customer and existing_customer.id == current_user.id:
        raise HTTPException(status_code=400, detail="Nelze předregistrovat vozidlo na servisní účet.")

    try:
        if existing_customer:
            _, created_link = _upsert_service_customer_link(
                db,
                service_customer_id=current_user.id,
                service_tenant_id=current_user.tenant_id,
                target_customer=existing_customer,
                note="Propojeno při předregistraci vozidla servisem",
            )
            vehicle = _build_workspace_vehicle_row(
                tenant_id=int(existing_customer.tenant_id or current_user.tenant_id or 1),
                owner_email=invite_email,
                payload=vehicle_payload,
            )
            db.add(vehicle)
            db.flush()
            apply_orv_scan_to_vehicle(
                db=db,
                vehicle=vehicle,
                current_user=current_user,
                scan_id=vehicle_payload.orv_scan_id,
                orv_number=vehicle_payload.orv_number,
                use_owner_data=vehicle_payload.orv_use_owner_data,
                data_trust_state=vehicle_payload.data_trust_state or "verified_by_service",
                create_payload=vehicle_payload.dict(),
            )
            ensure_vehicle_owner_assignment(
                db,
                vehicle=vehicle,
                owner=existing_customer,
                assigned_by_customer_id=current_user.id,
                ownership_origin="service_pre_registration",
            )
            create_or_update_vehicle_service_link(
                db,
                tenant_id=vehicle.tenant_id,
                service_customer_id=current_user.id,
                owner_customer_id=existing_customer.id,
                vehicle_id=vehicle.id,
                approved_by_customer_id=current_user.id,
                source_type="service_pre_registration",
                note="Vozidlo bylo založeno servisem pro existující zákaznický účet.",
            )
            db.commit()
            return {
                "vehicle_id": vehicle.id,
                "customer_id": existing_customer.id,
                "linked_now": True,
                "already_linked": not created_link,
                "email_sent": False,
                "registration_state": "linked_existing_customer",
                "message": "Existující účet byl propojen a vozidlo bylo založeno přímo do profilu zákazníka.",
            }

        (
            db.query(ServiceCustomerInvite)
            .filter(
                ServiceCustomerInvite.service_customer_id == current_user.id,
                func.lower(ServiceCustomerInvite.invite_email) == invite_email,
                ServiceCustomerInvite.status == "pending",
            )
            .update(
                {
                    ServiceCustomerInvite.status: "cancelled",
                    ServiceCustomerInvite.updated_at: datetime.utcnow(),
                },
                synchronize_session=False,
            )
        )

        token = secrets.token_urlsafe(32)
        invitation_url = _build_invitation_url(token)
        invite = ServiceCustomerInvite(
            service_tenant_id=current_user.tenant_id,
            service_customer_id=current_user.id,
            invite_email=invite_email,
            invite_name=(payload.invite_name or "").strip() or None,
            invite_message=(payload.invite_message or "").strip() or None,
            token=token,
            status="pending",
            sent_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
        db.add(invite)
        db.flush()

        vehicle = _build_workspace_vehicle_row(
            tenant_id=int(current_user.tenant_id or 1),
            owner_email=invite_email,
            payload=vehicle_payload,
        )
        db.add(vehicle)
        db.flush()
        apply_orv_scan_to_vehicle(
            db=db,
            vehicle=vehicle,
            current_user=current_user,
            scan_id=vehicle_payload.orv_scan_id,
            orv_number=vehicle_payload.orv_number,
            use_owner_data=vehicle_payload.orv_use_owner_data,
            data_trust_state=vehicle_payload.data_trust_state or "verified_by_service",
            create_payload=vehicle_payload.dict(),
        )
        create_or_update_vehicle_service_link(
            db,
            tenant_id=vehicle.tenant_id,
            service_customer_id=current_user.id,
            owner_customer_id=current_user.id,
            vehicle_id=vehicle.id,
            approved_by_customer_id=current_user.id,
            source_type="pending_owner_registration",
            note="Vozidlo bylo předregistrováno servisem a čeká na převzetí budoucím vlastníkem.",
        )
        db.commit()

        email_sent = _send_invitation_email(
            service_user=current_user,
            invite_email=invite_email,
            invite_name=payload.invite_name,
            invite_message=payload.invite_message,
            invitation_url=invitation_url,
        )
        return {
            "vehicle_id": vehicle.id,
            "linked_now": False,
            "email_sent": bool(email_sent),
            "registration_state": "pending_registration",
            "registration_url": invitation_url,
            "message": (
                "Vozidlo bylo zaevidováno a pozvánka odeslána."
                if email_sent
                else "Vozidlo bylo zaevidováno. SMTP není dostupné, registrační odkaz pošlete zákazníkovi ručně."
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Předregistrace vozidla selhala: {exc}") from exc


@router.get("/reminders")
def list_service_workspace_reminders(
    customer_id: Optional[int] = Query(default=None, ge=1),
    vehicle_id: Optional[int] = Query(default=None, ge=1),
    include_completed: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=500),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    linked_customer_ids = [
        int(item[0])
        for item in (
            db.query(ServiceCustomerLink.customer_id)
            .filter(
                ServiceCustomerLink.service_customer_id == current_user.id,
                ServiceCustomerLink.status == "active",
            )
            .all()
        )
        if item and item[0]
    ]
    if not linked_customer_ids:
        return []

    if customer_id and int(customer_id) not in linked_customer_ids:
        raise HTTPException(status_code=403, detail="Zadaný klient není propojen s tímto servisním účtem.")

    query = (
        db.query(ReminderModel, Customer, VehicleModel)
        .join(Customer, Customer.id == ReminderModel.customer_id)
        .outerjoin(VehicleModel, VehicleModel.id == ReminderModel.vehicle_id)
        .filter(ReminderModel.customer_id.in_(linked_customer_ids))
    )

    if customer_id:
        query = query.filter(ReminderModel.customer_id == int(customer_id))
    if vehicle_id:
        query = query.filter(ReminderModel.vehicle_id == int(vehicle_id))
    if not include_completed:
        query = query.filter(ReminderModel.is_completed.is_(False))

    rows = (
        query
        .order_by(ReminderModel.is_completed.asc(), ReminderModel.due_date.asc(), ReminderModel.created_at.desc())
        .limit(limit)
        .all()
    )

    output = []
    for reminder, customer, vehicle in rows:
        vehicle_label = (
            (getattr(vehicle, "nickname", None) or None)
            or " ".join([part for part in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None)] if part]).strip()
            or getattr(vehicle, "plate", None)
            or (f"Vozidlo #{getattr(vehicle, 'id', '')}" if vehicle else "Bez vozidla")
        )
        output.append(
            {
                "id": reminder.id,
                "customer_id": reminder.customer_id,
                "customer_name": customer.name or customer.email,
                "customer_email": customer.email,
                "vehicle_id": reminder.vehicle_id,
                "vehicle_label": vehicle_label,
                "type": reminder.type,
                "text": reminder.text,
                "due_date": reminder.due_date.isoformat() if reminder.due_date else None,
                "notify_at": naive_utc_to_iso_z(reminder.notify_at),
                "notification_method": reminder.notification_method,
                "is_completed": bool(reminder.is_completed),
                "is_manual": bool(reminder.is_manual),
                "is_recurring": bool(is_recurring_reminder(reminder)),
                "recurrence_group_id": getattr(reminder, "recurrence_group_id", None),
                "recurrence_index": getattr(reminder, "recurrence_index", None),
                "created_at": naive_utc_to_iso_z(reminder.created_at),
                "service_account_id": current_user.id,
            }
        )
    return output


@router.post("/reminders")
def create_service_workspace_reminder(
    payload: ServiceWorkspaceReminderCreateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    customer = _get_active_linked_customer_or_404(db, current_user, int(payload.customer_id))
    vehicle = None
    if payload.vehicle_id:
        vehicle = get_owned_vehicle(
            db,
            customer,
            int(payload.vehicle_id),
            tenant_id=getattr(customer, "tenant_id", None),
        )
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vybrané vozidlo klienta nebylo nalezeno.")

    reminder = ReminderModel(
        tenant_id=getattr(customer, "tenant_id", None) or getattr(current_user, "tenant_id", None) or 1,
        customer_id=customer.id,
        vehicle_id=int(payload.vehicle_id) if payload.vehicle_id else None,
        type=_normalize_service_reminder_type(payload.type),
        text=str(payload.text or "").strip(),
        due_date=payload.due_date,
        notify_at=_to_naive_utc(payload.notify_at),
        notification_method=_normalize_service_reminder_notification_method(payload.notification_method),
        last_notified_at=None,
        is_manual=True,
        is_completed=False,
    )
    db.add(reminder)
    db.flush()

    db.commit()
    db.refresh(reminder)

    try:
        now_utc = datetime.utcnow()
        today = prague_today()
        should_sweep = False
        if reminder.notify_at and now_utc >= _to_naive_utc(reminder.notify_at):
            should_sweep = True
        elif reminder.due_date is not None and reminder.due_date <= today:
            should_sweep = True
        if should_sweep:
            check_and_send_reminder_notifications(db)
    except Exception as sweep_exc:
        print(f"[REMINDERS] Service workspace create reminder sweep failed (non-fatal): {sweep_exc}")

    return {
        "id": reminder.id,
        "customer_id": customer.id,
        "customer_name": customer.name or customer.email,
        "customer_email": customer.email,
        "vehicle_id": reminder.vehicle_id,
        "vehicle_label": (
            vehicle.nickname if vehicle and vehicle.nickname
            else (vehicle.plate if vehicle else "Bez vozidla")
        ),
        "type": reminder.type,
        "text": reminder.text,
        "due_date": reminder.due_date.isoformat() if reminder.due_date else None,
        "notify_at": naive_utc_to_iso_z(reminder.notify_at),
        "notification_method": reminder.notification_method,
        "is_completed": bool(reminder.is_completed),
        "is_manual": bool(reminder.is_manual),
        "is_recurring": bool(is_recurring_reminder(reminder)),
        "recurrence_group_id": getattr(reminder, "recurrence_group_id", None),
        "recurrence_index": getattr(reminder, "recurrence_index", None),
        "created_at": naive_utc_to_iso_z(reminder.created_at),
        "service_account_id": current_user.id,
    }


@router.get("/reminders/{reminder_id}/detail")
def get_service_workspace_reminder_detail(
    reminder_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    reminder = db.query(ReminderModel).filter(ReminderModel.id == int(reminder_id)).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Připomínka nebyla nalezena.")

    customer = db.query(Customer).filter(Customer.id == reminder.customer_id).first()
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == reminder.vehicle_id).first() if reminder.vehicle_id else None
    linked_customer = bool(
        customer
        and _get_active_link(db, service_customer_id=int(current_user.id), customer_id=int(customer.id))
    )
    approved_vehicle = bool(
        vehicle
        and get_active_vehicle_service_link(
            db,
            service_customer_id=int(current_user.id),
            vehicle_id=int(vehicle.id),
        )
    )
    disclosure = "full" if linked_customer and (not vehicle or approved_vehicle) else "limited"
    can_create_work_order = bool(linked_customer and vehicle and approved_vehicle)
    payload = _detail_state_payload(
        entity_type="reminder",
        entity_id=int(reminder.id),
        status="completed" if bool(reminder.is_completed) else "open",
        can_open_detail=True,
        can_edit=linked_customer,
        can_request_access=bool(vehicle and not approved_vehicle),
        can_create_work_order=can_create_work_order,
        blocking_reason=(
            "Připomínka patří klientovi bez aktivní servisní vazby."
            if customer and not linked_customer
            else "K vozidlu z připomínky není schválený servisní přístup."
            if vehicle and not approved_vehicle
            else None
        ),
        disclosure=disclosure,
    )
    payload.update(
        {
            "reminder_id": int(reminder.id),
            "customer_id": int(reminder.customer_id),
            "customer_name": (
                (customer.name or customer.email)
                if customer and disclosure == "full"
                else customer.name
                if customer
                else None
            ),
            "customer_email": customer.email if customer and disclosure == "full" else None,
            "customer_email_masked": _mask_email_value(customer.email if customer else None),
            "vehicle_id": int(reminder.vehicle_id) if reminder.vehicle_id else None,
            "vehicle_label": (
                (vehicle.nickname if vehicle and vehicle.nickname else None)
                or (" ".join(part for part in [vehicle.brand, vehicle.model] if part).strip() if vehicle else None)
                or (vehicle.plate if vehicle and disclosure == "full" else None)
                or ("Vozidlo bez schváleného přístupu" if vehicle else "Bez vozidla")
            ),
            "vehicle_plate_masked": masked_plate(vehicle.plate) if vehicle else None,
            "vehicle_vin_masked": masked_vin(vehicle.vin) if vehicle else None,
            "type": reminder.type,
            "text": reminder.text if disclosure == "full" else None,
            "due_date": reminder.due_date.isoformat() if reminder.due_date else None,
            "notify_at": naive_utc_to_iso_z(reminder.notify_at),
            "notification_method": reminder.notification_method,
            "is_completed": bool(reminder.is_completed),
            "is_manual": bool(reminder.is_manual),
            "is_recurring": bool(is_recurring_reminder(reminder)),
            "recurrence_group_id": getattr(reminder, "recurrence_group_id", None),
            "recurrence_index": getattr(reminder, "recurrence_index", None),
            "created_at": naive_utc_to_iso_z(reminder.created_at),
            "customer_linked": linked_customer,
            "vehicle_access_approved": approved_vehicle if vehicle else None,
        }
    )
    return payload


@router.put("/reminders/{reminder_id}")
def update_service_workspace_reminder(
    reminder_id: int,
    payload: ServiceWorkspaceReminderUpdateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    linked_customer_ids = [
        int(item[0])
        for item in (
            db.query(ServiceCustomerLink.customer_id)
            .filter(
                ServiceCustomerLink.service_customer_id == current_user.id,
                ServiceCustomerLink.status == "active",
            )
            .all()
        )
        if item and item[0]
    ]
    if not linked_customer_ids:
        raise HTTPException(status_code=403, detail="Servis nemá propojené klienty.")

    reminder = (
        db.query(ReminderModel)
        .filter(
            ReminderModel.id == reminder_id,
            ReminderModel.customer_id.in_(linked_customer_ids),
        )
        .first()
    )
    if not reminder:
        raise HTTPException(status_code=404, detail="Připomínka nebyla nalezena.")

    fields_set = set(getattr(payload, "model_fields_set", set()) or set())
    schedule_reset = False

    if payload.type is not None:
        reminder.type = _normalize_service_reminder_type(payload.type)
    if payload.text is not None:
        reminder.text = str(payload.text or "").strip()
    if "due_date" in fields_set:
        reminder.due_date = payload.due_date
        schedule_reset = True
    if "notify_at" in fields_set:
        reminder.notify_at = _to_naive_utc(payload.notify_at)
        schedule_reset = True
    if "notification_method" in fields_set:
        reminder.notification_method = _normalize_service_reminder_notification_method(payload.notification_method)
    if "is_completed" in fields_set and payload.is_completed is not None:
        apply_reminder_completion_update(reminder, bool(payload.is_completed))

    if schedule_reset:
        reminder.last_notified_at = None

    db.commit()
    db.refresh(reminder)

    if schedule_reset:
        try:
            now_utc = datetime.utcnow()
            today = prague_today()
            should_sweep = False
            if reminder.notify_at and now_utc >= _to_naive_utc(reminder.notify_at):
                should_sweep = True
            elif reminder.due_date is not None and reminder.due_date <= today:
                should_sweep = True
            if should_sweep:
                check_and_send_reminder_notifications(db)
        except Exception as sweep_exc:
            print(f"[REMINDERS] Service workspace update reminder sweep failed (non-fatal): {sweep_exc}")

    customer = db.query(Customer).filter(Customer.id == reminder.customer_id).first()
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == reminder.vehicle_id).first() if reminder.vehicle_id else None
    vehicle_label = (
        (vehicle.nickname if vehicle and vehicle.nickname else None)
        or (vehicle.plate if vehicle else None)
        or ("Bez vozidla" if not reminder.vehicle_id else f"Vozidlo #{reminder.vehicle_id}")
    )

    return {
        "id": reminder.id,
        "customer_id": reminder.customer_id,
        "customer_name": (customer.name if customer else None) or (customer.email if customer else f"Klient #{reminder.customer_id}"),
        "customer_email": customer.email if customer else None,
        "vehicle_id": reminder.vehicle_id,
        "vehicle_label": vehicle_label,
        "type": reminder.type,
        "text": reminder.text,
        "due_date": reminder.due_date.isoformat() if reminder.due_date else None,
        "notify_at": naive_utc_to_iso_z(reminder.notify_at),
        "notification_method": reminder.notification_method,
        "is_completed": bool(reminder.is_completed),
        "is_manual": bool(reminder.is_manual),
        "is_recurring": bool(is_recurring_reminder(reminder)),
        "recurrence_group_id": getattr(reminder, "recurrence_group_id", None),
        "recurrence_index": getattr(reminder, "recurrence_index", None),
        "created_at": naive_utc_to_iso_z(reminder.created_at),
        "service_account_id": current_user.id,
    }


@router.delete("/reminders/{reminder_id}")
def delete_service_workspace_reminder(
    reminder_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    linked_customer_ids = [
        int(item[0])
        for item in (
            db.query(ServiceCustomerLink.customer_id)
            .filter(
                ServiceCustomerLink.service_customer_id == current_user.id,
                ServiceCustomerLink.status == "active",
            )
            .all()
        )
        if item and item[0]
    ]
    if not linked_customer_ids:
        raise HTTPException(status_code=403, detail="Servis nemá propojené klienty.")

    reminder = (
        db.query(ReminderModel)
        .filter(
            ReminderModel.id == reminder_id,
            ReminderModel.customer_id.in_(linked_customer_ids),
        )
        .first()
    )
    if not reminder:
        raise HTTPException(status_code=404, detail="Připomínka nebyla nalezena.")

    db.delete(reminder)
    db.commit()
    return {"deleted": True, "id": reminder_id}


@router.get("/documents")
def list_ingested_documents(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    rows = (
        db.query(ServiceDocumentIngestion)
        .filter(ServiceDocumentIngestion.service_customer_id == current_user.id)
        .order_by(ServiceDocumentIngestion.created_at.desc())
        .limit(limit)
        .all()
    )
    reparsed_any = False
    for row in rows:
        try:
            if _try_reparse_ingestion_entity(row):
                reparsed_any = True
        except Exception as exc:
            print(f"[SERVICE_WORKSPACE] Re-parse ingestu #{row.id} selhal: {exc}")
    if reparsed_any:
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            print(f"[SERVICE_WORKSPACE] Uložení re-parse změn selhalo: {exc}")

    customer_ids = sorted({int(row.customer_id) for row in rows if row.customer_id})
    vehicle_ids = sorted({int(row.vehicle_id) for row in rows if row.vehicle_id})

    customers_map: dict[int, Customer] = {}
    if customer_ids:
        customer_rows = (
            db.query(Customer)
            .filter(Customer.id.in_(customer_ids))
            .all()
        )
        customers_map = {int(item.id): item for item in customer_rows}

    vehicles_map: dict[int, VehicleModel] = {}
    if vehicle_ids:
        vehicle_rows = (
            db.query(VehicleModel)
            .filter(VehicleModel.id.in_(vehicle_ids))
            .all()
        )
        vehicles_map = {int(item.id): item for item in vehicle_rows}

    result: list[dict[str, Any]] = []
    for row in rows:
        customer_obj = customers_map.get(int(row.customer_id)) if row.customer_id else None
        vehicle_obj = vehicles_map.get(int(row.vehicle_id)) if row.vehicle_id else None
        vehicle_label = None
        if vehicle_obj:
            vehicle_label = (
                vehicle_obj.nickname
                or " ".join(part for part in [vehicle_obj.brand, vehicle_obj.model] if part).strip()
                or vehicle_obj.plate
                or f"Vozidlo #{vehicle_obj.id}"
            )
            if vehicle_obj.plate and vehicle_label != vehicle_obj.plate:
                vehicle_label = f"{vehicle_label} • {vehicle_obj.plate}"

        result.append(
            _build_ingestion_response(
                row,
                customer_name=(customer_obj.name if customer_obj else None),
                customer_email=(customer_obj.email if customer_obj else None),
                vehicle_label=vehicle_label,
            )
        )
    return result


@router.get("/documents/{document_id}/detail")
def get_service_workspace_document_detail(
    document_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    row = (
        db.query(ServiceDocumentIngestion)
        .filter(
            ServiceDocumentIngestion.id == int(document_id),
            ServiceDocumentIngestion.service_customer_id == int(current_user.id),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Doklad nebyl nalezen.")
    try:
        _try_reparse_ingestion_entity(row)
        db.flush()
    except Exception as exc:
        print(f"[SERVICE_WORKSPACE] Re-parse detailu dokladu #{row.id} selhal: {exc}")

    customer_obj = db.query(Customer).filter(Customer.id == row.customer_id).first() if row.customer_id else None
    vehicle_obj = db.query(VehicleModel).filter(VehicleModel.id == row.vehicle_id).first() if row.vehicle_id else None
    vehicle_label = None
    if vehicle_obj:
        vehicle_label = (
            vehicle_obj.nickname
            or " ".join(part for part in [vehicle_obj.brand, vehicle_obj.model] if part).strip()
            or vehicle_obj.plate
            or f"Vozidlo #{vehicle_obj.id}"
        )
        if vehicle_obj.plate and vehicle_label != vehicle_obj.plate:
            vehicle_label = f"{vehicle_label} • {vehicle_obj.plate}"
    detail = _build_ingestion_response(
        row,
        customer_name=(customer_obj.name if customer_obj else None),
        customer_email=(customer_obj.email if customer_obj else None),
        vehicle_label=vehicle_label,
    )
    disclosure, can_request_access, can_create_work_order, blocking_reason = _document_disclosure_state(
        db,
        current_user=current_user,
        entity=row,
    )
    payload = _detail_state_payload(
        entity_type="document",
        entity_id=int(row.id),
        status=str(row.processing_status or "processed"),
        can_open_detail=True,
        can_edit=False,
        can_request_access=can_request_access,
        can_create_work_order=can_create_work_order,
        blocking_reason=blocking_reason,
        disclosure=disclosure,
    )
    payload.update(detail)
    payload["customer_email"] = detail.get("customer_email") if disclosure == "full" else None
    payload["customer_email_masked"] = _mask_email_value(detail.get("customer_email"))
    payload["parsed_data"] = detail.get("parsed_data") if disclosure == "full" else None
    payload["extracted_text_preview"] = detail.get("extracted_text_preview") if disclosure == "full" else None
    payload["vehicle_access_approved"] = not can_request_access if row.vehicle_id else None
    payload["customer_linked"] = bool(
        row.customer_id
        and _get_active_link(
            db,
            service_customer_id=int(current_user.id),
            customer_id=int(row.customer_id),
        )
    )
    return payload


@router.post("/documents/ingest")
def ingest_service_document(
    payload: IngestDocumentRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_workspace_schema(db)

    source_type = str(payload.source_type or "invoice").strip().lower()
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="Neplatný typ dokladu.")

    customer = _get_active_linked_customer_or_404(db, current_user, payload.customer_id)
    vehicle: Optional[VehicleModel] = None
    approved_vehicle_link: Optional[VehicleServiceLink] = None
    if payload.vehicle_id:
        vehicle = get_owned_vehicle(
            db,
            customer,
            int(payload.vehicle_id),
            tenant_id=getattr(customer, "tenant_id", None),
        )
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vybrané vozidlo nebylo nalezeno.")
        approved_vehicle_link = require_service_vehicle_link(
            db,
            current_user=current_user,
            vehicle_id=int(vehicle.id),
            require_create_record=bool(payload.auto_create_service_record),
        )

    raw_file_content = b""
    if payload.file_content_base64:
        raw_file_content = _decode_base64_payload(payload.file_content_base64)
        if len(raw_file_content) > (15 * 1024 * 1024):
            raise HTTPException(status_code=413, detail="Soubor je příliš velký (max 15 MB).")

    manual_text = (payload.manual_text or "").strip()
    if not raw_file_content and not manual_text:
        raise HTTPException(status_code=422, detail="Nahrajte soubor nebo vložte ruční text dokladu.")

    stored_file_path = None
    extracted_text = ""
    extraction_engine = "manual"
    extraction_warning = None
    if raw_file_content:
        stored_file_path = _store_uploaded_file(payload.file_name, raw_file_content)
        extracted_text, extraction_warning, extraction_engine = _extract_text_from_file(
            content=raw_file_content,
            file_name=payload.file_name,
            mime_type=payload.file_mime_type,
        )

    parsed_data = _parse_document_payload(
        source_type=source_type,
        extracted_text=extracted_text,
        manual_text=manual_text,
        manual_note=payload.manual_note,
        extraction_engine=extraction_engine,
        extraction_warning=extraction_warning,
    )
    parse_confidence = float(parsed_data.get("confidence") or 0.0)
    processing_status = "processed"
    if not (extracted_text.strip() or manual_text):
        processing_status = "failed"
    elif parse_confidence < 0.35:
        processing_status = "needs_review"

    auto_record_id: Optional[int] = None

    try:
        if payload.auto_create_service_record and vehicle and processing_status != "failed":
            issue_date = _parse_date(str(parsed_data.get("issue_date") or "")) if parsed_data.get("issue_date") else None
            performed_at = (
                datetime.combine(issue_date, datetime.min.time()) if issue_date else datetime.utcnow()
            )
            total_price = parsed_data.get("total_with_vat")
            if total_price is None:
                subtotal = parsed_data.get("subtotal_without_vat")
                vat = parsed_data.get("vat_amount")
                if subtotal is not None and vat is not None:
                    total_price = round(float(subtotal) + float(vat), 2)

            note_parts = [
                f"Zdroj: {source_type}",
                f"Dodavatel: {parsed_data.get('supplier_name')}" if parsed_data.get("supplier_name") else None,
                f"Číslo dokladu: {parsed_data.get('document_number')}" if parsed_data.get("document_number") else None,
                (payload.manual_note or "").strip() or None,
            ]
            note_text = " | ".join(part for part in note_parts if part)

            service_report_payload = _build_service_report_payload(parsed_data, source_type)
            attachments_payload_items: list[dict[str, Any]] = [
                {
                    "kind": "service_report_meta",
                    "source_type": source_type,
                    "parsed_summary": service_report_payload,
                }
            ]
            if raw_file_content:
                attachment_meta = _store_service_record_attachment(
                    vehicle=vehicle,
                    current_user=current_user,
                    file_name=payload.file_name,
                    file_mime_type=payload.file_mime_type,
                    content=raw_file_content,
                )
                attachments_payload_items.append(
                    {
                        "kind": "service_document",
                        "file_name": attachment_meta.get("file_name"),
                        "mime_type": attachment_meta.get("mime_type"),
                        "file_size": attachment_meta.get("file_size"),
                        "storage_key": attachment_meta.get("storage_key"),
                        "download_url": attachment_meta.get("download_url"),
                        "source_type": source_type,
                        "parsed_summary": service_report_payload,
                    }
                )
            attachments_payload = json.dumps(attachments_payload_items, ensure_ascii=False)

            record = ServiceRecordModel(
                tenant_id=vehicle.tenant_id or current_user.tenant_id or 1,
                vehicle_id=vehicle.id,
                user_id=current_user.id,
                created_by_service_customer_id=current_user.id,
                service_access_link_id=approved_vehicle_link.id if approved_vehicle_link else None,
                performed_at=performed_at,
                mileage=None,
                description=_build_service_record_description(parsed_data),
                price=float(total_price) if total_price is not None else None,
                note=note_text or None,
                category="SERVIS",
                attachments=attachments_payload,
            )
            db.add(record)
            db.flush()
            auto_record_id = record.id

        issue_date_obj = _parse_date(str(parsed_data.get("issue_date") or "")) if parsed_data.get("issue_date") else None
        due_date_obj = _parse_date(str(parsed_data.get("due_date") or "")) if parsed_data.get("due_date") else None

        ingestion = ServiceDocumentIngestion(
            service_tenant_id=current_user.tenant_id,
            service_customer_id=current_user.id,
            customer_id=customer.id,
            vehicle_id=vehicle.id if vehicle else None,
            source_type=source_type,
            original_filename=payload.file_name,
            original_mime_type=payload.file_mime_type,
            stored_file_path=stored_file_path,
            extracted_text=(extracted_text or "").strip() or manual_text or None,
            parsed_payload_json=json.dumps(_json_safe(parsed_data), ensure_ascii=False),
            parse_confidence=parse_confidence,
            processing_status=processing_status,
            document_number=parsed_data.get("document_number"),
            supplier_name=parsed_data.get("supplier_name"),
            issue_date=issue_date_obj,
            due_date=due_date_obj,
            currency=parsed_data.get("currency") or "CZK",
            subtotal_without_vat=parsed_data.get("subtotal_without_vat"),
            vat_amount=parsed_data.get("vat_amount"),
            total_with_vat=parsed_data.get("total_with_vat"),
            labor_total=parsed_data.get("labor_total"),
            materials_total=parsed_data.get("materials_total"),
            auto_created_service_record_id=auto_record_id,
        )
        db.add(ingestion)
        db.commit()
        db.refresh(ingestion)
        vehicle_label = None
        if vehicle:
            vehicle_label = (
                vehicle.nickname
                or " ".join(part for part in [vehicle.brand, vehicle.model] if part).strip()
                or vehicle.plate
                or f"Vozidlo #{vehicle.id}"
            )
            if vehicle.plate and vehicle_label != vehicle.plate:
                vehicle_label = f"{vehicle_label} • {vehicle.plate}"
        return _build_ingestion_response(
            ingestion,
            customer_name=customer.name,
            customer_email=customer.email,
            vehicle_label=vehicle_label,
        )
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Zpracování dokladu selhalo: {exc}") from exc
