from __future__ import annotations

import hashlib
import json
import re
import secrets
import zipfile
from datetime import datetime, timedelta
from typing import Any, Optional

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.config import DATA_DIR, FRONTEND_BASE_URL
from src.core.rbac import normalize_role

from ..audit_log import write_global_audit_log
from ..database import get_db
from ..models import (
    Customer,
    ServiceAccessRequest,
    ServiceRecord,
    SystemNotification,
    Vehicle,
    VehicleRemovalEvent,
    VehicleReportDocument,
    VehicleServiceLink,
    VehicleTransferToken,
)
from ..ownership import (
    get_customer_by_email,
    get_owned_vehicle,
    released_placeholder_user_email,
    release_vehicle_owner_assignment,
    transfer_vehicle_to_new_owner,
    user_owns_vehicle,
)
from ..reports.vehicle_report_access import resolve_report_mode
from ..reports.vehicle_report_builder import build_vehicle_service_report_payload
from ..reports.vehicle_report_pdf import render_vehicle_service_report_pdf
from ..reports.vehicle_report_verification import finalize_vehicle_report_document
from ..schema_management import assert_module_ready
from ..service_access import (
    create_or_update_vehicle_service_link,
    finalize_service_access_decision,
    revoke_vehicle_service_link,
    vehicle_label,
)
from ..user_in_app_notifications import (
    APP_AUTOMATED_NOTIFICATION_SENDER,
    notify_service_access_decided,
    notify_service_owner_granted_direct_access,
)
from ..vehicle_public_history import render_vehicle_qr_svg
from .auth import get_current_user

"""
PRODUCTION CRITICAL LOGIC:
- service access enforcement
- lifecycle remove/transfer
- audit log
Jakákoliv změna musí projít production auditem.
"""

router = APIRouter(prefix="/vehicles", tags=["vehicle-lifecycle-v1"])

ARCHIVE_ROOT = DATA_DIR / "vehicle_archives"
REPORT_ROOT = DATA_DIR / "vehicle_reports"
ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
REPORT_ROOT.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

REMOVAL_FOLLOWUP_FIELDS = {
    "ceased": "note",
    "scrap": "scrap_document_reference",
    "export": "export_country",
    "temporary_hide": "hide_until_or_reason",
    "duplicate": "duplicate_vehicle_reference",
    "other": "note",
}

REMOVAL_REASON_CODES = frozenset({"sale", "handover", *REMOVAL_FOLLOWUP_FIELDS.keys()})

# Prodej i předání novému držiteli — transfer token + e-mail příjemci (stejný kontakt jako „sale“).
REMOVAL_REASONS_WITH_TRANSFER_RECIPIENT = frozenset({"sale", "handover"})

_SALE_BUYER_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_sale_buyer_contact(answer: dict[str, Any] | None, *, seller_email: str | None) -> tuple[str, str]:
    raw = answer or {}
    email = str(raw.get("buyer_email") or "").strip().lower()
    phone_raw = str(raw.get("buyer_phone") or "").strip()
    if not email or not _SALE_BUYER_EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Zadejte platný e-mail kupce.")
    seller_norm = str(seller_email or "").strip().lower()
    if seller_norm and email == seller_norm:
        raise HTTPException(status_code=422, detail="Zadejte e-mail kupce, ne svůj účet.")
    digits = re.sub(r"\D", "", phone_raw)
    if len(digits) < 9:
        raise HTTPException(
            status_code=422,
            detail="Zadejte platné telefonní číslo kupce (alespoň 9 číslic).",
        )
    return email, phone_raw


def _send_vehicle_sale_buyer_email_background(
    buyer_email: str,
    buyer_phone: str,
    seller_name: str,
    vehicle_label_s: str,
    transfer_url: str,
    pdf_path_str: str,
    registration_url: str,
    buyer_already_registered: bool,
) -> None:
    from pathlib import Path

    from src.core.branding import APP_DISPLAY_NAME
    from src.modules.email_client.service import EmailMessage, EmailService
    from src.modules.email_client.templates import render_email_layout, render_panel

    svc = EmailService()
    if not svc.is_configured():
        print("[VEHICLE_SALE] SMTP není nakonfigurováno — e-mail kupci neodeslán")
        return
    path = Path(pdf_path_str)
    pdf_bytes = path.read_bytes() if path.is_file() else b""
    seller_bit = f" ({seller_name})" if seller_name else ""
    intro_paras = [
        f"Prodávající{seller_bit} vám předává vozidlo — {vehicle_label_s}.",
        "V příloze najdete digitální výpis vozidla (PDF). Tlačítkem níže dokončíte převod v aplikaci (ověření SPZ a VIN).",
    ]
    extra_paras: list[str] = []
    if not buyer_already_registered:
        extra_paras.append(
            f"Účet s tímto e-mailem v {APP_DISPLAY_NAME} zatím neevidujeme — založte si ho přes registraci v aplikaci, "
            "poté použijte odkaz pro převod."
        )
    plain_lines = [
        "Dobrý den,",
        "",
        intro_paras[0],
        intro_paras[1],
        "",
        f"Odkaz pro převod: {transfer_url}",
        f"Telefon uvedený při předání: {buyer_phone}",
        "",
    ]
    if not buyer_already_registered:
        plain_lines.extend(
            [
                f"Registrace v aplikaci: {registration_url}",
                "",
            ]
        )
    plain_body = "\n".join(plain_lines) + f"\n— {APP_DISPLAY_NAME}\n"

    panels = [
        render_panel(
            title="Údaje pro převod",
            rows=[("Vozidlo", vehicle_label_s), ("Váš e-mail", buyer_email), ("Telefon", buyer_phone)],
        ),
    ]
    html_body = render_email_layout(
        title="Předání vozidla — digitální výpis",
        subtitle=vehicle_label_s,
        intro="Dobrý den,",
        paragraphs=intro_paras + extra_paras,
        panels=panels,
        cta_label="Dokončit převod",
        cta_url=transfer_url,
        accent="#16a34a",
        footer_note=None if buyer_already_registered else f"Registrace: {registration_url}",
    )
    blobs: list[tuple[str, bytes, str]] = []
    if pdf_bytes:
        blobs.append(("digitalni-vypis-vozidla.pdf", pdf_bytes, "application/pdf"))
    msg = EmailMessage(
        to=[buyer_email],
        subject=f"Předání vozidla — {vehicle_label_s}",
        body=plain_body,
        html_body=html_body,
        attachment_blobs=blobs,
    )
    try:
        svc.send_email(msg)
        print(f"[VEHICLE_SALE] E-mail kupci odeslán: {buyer_email}")
    except Exception as exc:
        print(f"[VEHICLE_SALE] Odeslání e-mailu kupci selhalo: {exc}")


class ServiceAccessLinkRequest(BaseModel):
    service_id: int = Field(gt=0)
    request_reason: Optional[str] = Field(default=None, max_length=500)
    access_scope: list[str] = Field(default_factory=lambda: [
        "read_summary",
        "create_service_record",
        "manage_work_order",
        "manage_invoice",
        "manage_photos",
    ])


class ServiceAccessDecisionRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class VehicleLookupBySpzRequest(BaseModel):
    spz: str = Field(..., min_length=2, max_length=32)


class AttachExistingVehicleRequest(BaseModel):
    spz: str = Field(..., min_length=2, max_length=32)
    vin: str = Field(..., min_length=5, max_length=32)
    confirm_vehicle_id: int = Field(gt=0)
    acquisition_reason: str = Field(default="existing_vehicle_claim", max_length=64)


class RemovalInitRequest(BaseModel):
    reason_code: str = Field(..., min_length=3, max_length=64)


class RemovalConfirmRequest(BaseModel):
    reason_code: str = Field(..., min_length=3, max_length=64)
    followup_answer: dict[str, Any] = Field(default_factory=dict)


class TransferTokenRequest(BaseModel):
    transfer_reason: str = Field(default="sale", min_length=3, max_length=64)
    expires_in_days: int = Field(default=30, ge=1, le=180)


class ClaimByTransferRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=512)
    spz: str = Field(..., min_length=2, max_length=32)
    vin: str = Field(..., min_length=5, max_length=32)


def _normalize_spz(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _normalize_vin(value: str | None) -> str:
    return re.sub(r"[^A-HJ-NPR-Z0-9]", "", str(value or "").upper())


def _token_hash(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _transfer_url(raw_token: str) -> str:
    base = str(FRONTEND_BASE_URL or "").strip().rstrip("/") or "http://127.0.0.1:8000"
    if base.endswith("/web/index.html"):
        return f"{base.rsplit('/', 1)[0]}/vehicle-transfer.html?token={raw_token}"
    if base.endswith("/web"):
        return f"{base}/vehicle-transfer.html?token={raw_token}"
    return f"{base}/web/vehicle-transfer.html?token={raw_token}"


def _safe_qr_svg(public_url: str) -> str | None:
    try:
        return render_vehicle_qr_svg(public_url)
    except HTTPException:
        return None


def _require_owned_vehicle(db: Session, current_user: Customer, vehicle_id: int) -> Vehicle:
    vehicle = get_owned_vehicle(db, current_user, int(vehicle_id), tenant_id=getattr(current_user, "tenant_id", None))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno nebo k němu nemáte vlastnickou vazbu.")
    return vehicle


def _vehicle_public_summary(vehicle: Vehicle) -> dict[str, Any]:
    vin = str(vehicle.vin or "")
    return {
        "vehicle_id": int(vehicle.id),
        "label": vehicle_label(vehicle),
        "brand": vehicle.brand,
        "model": vehicle.model,
        "year": vehicle.year,
        "spz_current": vehicle.plate,
        "vin_masked": f"{vin[:3]}***{vin[-4:]}" if vin else None,
        "status": getattr(vehicle, "status", "active"),
    }


def _create_transfer_token(
    db: Session,
    *,
    vehicle: Vehicle,
    current_user: Customer,
    transfer_reason: str,
    expires_in_days: int,
) -> tuple[VehicleTransferToken, str, str]:
    raw_token = secrets.token_urlsafe(32)
    public_url = _transfer_url(raw_token)
    row = VehicleTransferToken(
        vehicle_id=int(vehicle.id),
        issued_by_user_id=int(current_user.id),
        transfer_reason=transfer_reason,
        token_hash=_token_hash(raw_token),
        qr_payload=public_url,
        expires_at=datetime.utcnow() + timedelta(days=int(expires_in_days)),
        status="active",
    )
    db.add(row)
    db.flush()
    write_global_audit_log(
        db,
        entity_type="vehicle_transfer_token",
        entity_id=int(row.id),
        action="transfer_token_issued",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=getattr(current_user, "tenant_id", None),
        vehicle_id=int(vehicle.id),
        metadata={"transfer_reason": transfer_reason, "expires_at": row.expires_at.isoformat()},
    )
    return row, raw_token, public_url


def _generate_vehicle_report(
    db: Session,
    *,
    vehicle: Vehicle,
    current_user: Customer,
    new_owner_claim_url: str | None = None,
) -> tuple[VehicleReportDocument, bytes]:
    resolved_mode = resolve_report_mode(db=db, vehicle=vehicle, current_user=current_user, requested_mode="owner")
    payload = build_vehicle_service_report_payload(db=db, vehicle=vehicle, current_user=current_user, mode=resolved_mode)
    payload, document_row = finalize_vehicle_report_document(db=db, vehicle=vehicle, current_user=current_user, payload=payload)
    claim_url = str(new_owner_claim_url or "").strip()
    if claim_url:
        payload.new_owner_claim_qr_payload = claim_url
    pdf_content = render_vehicle_service_report_pdf(payload)
    report_path = REPORT_ROOT / f"vehicle-{int(vehicle.id)}-report-{document_row.document_id}.pdf"
    report_path.write_bytes(pdf_content)
    write_global_audit_log(
        db,
        entity_type="vehicle_report_document",
        entity_id=int(document_row.id),
        action="digital_report_generated",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(vehicle.tenant_id),
        vehicle_id=int(vehicle.id),
        metadata={"document_id": document_row.document_id, "path": str(report_path)},
    )
    return document_row, pdf_content


def _archive_vehicle_bundle(db: Session, *, vehicle: Vehicle, document_row: VehicleReportDocument) -> str:
    records = (
        db.query(ServiceRecord)
        .filter(ServiceRecord.vehicle_id == int(vehicle.id), ServiceRecord.is_deleted.is_(False))
        .order_by(ServiceRecord.performed_at.asc(), ServiceRecord.id.asc())
        .all()
    )
    archive_path = ARCHIVE_ROOT / f"vehicle-{int(vehicle.id)}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.zip"
    manifest = {
        "vehicle": {
            "id": int(vehicle.id),
            "vin": vehicle.vin,
            "spz_current": vehicle.plate,
            "make": vehicle.brand,
            "model": vehicle.model,
            "year": vehicle.year,
            "status": getattr(vehicle, "status", "active"),
        },
        "digital_report_document_id": int(document_row.id),
        "records": [
            {
                "id": int(row.id),
                "performed_at": row.performed_at.isoformat() if row.performed_at else None,
                "origin": getattr(row, "origin", None),
                "category": row.category,
                "description": row.description,
                "mileage": row.mileage,
            }
            for row in records
        ],
        "archived_at": datetime.utcnow().isoformat(),
    }
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, default=str, indent=2))
        report_path = REPORT_ROOT / f"vehicle-{int(vehicle.id)}-report-{document_row.document_id}.pdf"
        if report_path.exists():
            zf.write(report_path, "digital-report.pdf")
    return str(archive_path)


@router.post("/lookup-by-spz")
def lookup_vehicle_by_spz(
    payload: VehicleLookupBySpzRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")
    spz = _normalize_spz(payload.spz)
    if not spz:
        raise HTTPException(status_code=422, detail="Zadejte platnou SPZ.")
    vehicle = db.query(Vehicle).filter(Vehicle.plate == spz).order_by(Vehicle.created_at.asc(), Vehicle.id.asc()).first()
    write_global_audit_log(
        db,
        entity_type="vehicle",
        entity_id=int(vehicle.id) if vehicle else None,
        action="vehicle_lookup_by_spz",
        actor_type=normalize_role(getattr(current_user, "role", None)),
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=getattr(current_user, "tenant_id", None),
        vehicle_id=int(vehicle.id) if vehicle else None,
        metadata={"spz_hash": hashlib.sha256(spz.encode("utf-8")).hexdigest(), "found": bool(vehicle)},
    )
    db.commit()
    return {
        "exists": bool(vehicle),
        "vehicle": _vehicle_public_summary(vehicle) if vehicle else None,
        "requires_vin_confirmation": bool(vehicle),
    }


@router.post("/attach-existing")
def attach_existing_vehicle(
    payload: AttachExistingVehicleRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(payload.confirm_vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno.")
    if _normalize_spz(payload.spz) != _normalize_spz(vehicle.plate):
        raise HTTPException(status_code=409, detail="SPZ nesouhlasí s nalezeným vozidlem.")
    if _normalize_vin(payload.vin) != _normalize_vin(vehicle.vin):
        raise HTTPException(status_code=409, detail="VIN nesouhlasí s nalezeným vozidlem.")
    transfer_vehicle_to_new_owner(
        db,
        vehicle=vehicle,
        new_owner=current_user,
        assigned_by_customer_id=int(current_user.id),
        ownership_origin=str(payload.acquisition_reason or "existing_vehicle_claim"),
    )
    vehicle.status = "active"
    write_global_audit_log(
        db,
        entity_type="vehicle",
        entity_id=int(vehicle.id),
        action="existing_vehicle_attached",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(current_user.tenant_id),
        vehicle_id=int(vehicle.id),
        metadata={"acquisition_reason": payload.acquisition_reason},
    )
    db.commit()
    return {"attached": True, "vehicle_id": int(vehicle.id), "history_preserved": True}


@router.get("/{vehicle_id}/service-access")
def list_vehicle_service_access(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = _require_owned_vehicle(db, current_user, vehicle_id)
    rows = (
        db.query(VehicleServiceLink, Customer)
        .join(Customer, VehicleServiceLink.service_customer_id == Customer.id)
        .filter(VehicleServiceLink.vehicle_id == int(vehicle.id))
        .order_by(VehicleServiceLink.updated_at.desc(), VehicleServiceLink.id.desc())
        .all()
    )
    requests = (
        db.query(ServiceAccessRequest, Customer)
        .join(Customer, ServiceAccessRequest.service_customer_id == Customer.id)
        .filter(
            ServiceAccessRequest.vehicle_id == int(vehicle.id),
            ServiceAccessRequest.owner_customer_id == int(current_user.id),
        )
        .order_by(ServiceAccessRequest.requested_at.desc(), ServiceAccessRequest.id.desc())
        .all()
    )
    return {
        "vehicle_id": int(vehicle.id),
        "access": [
            {
                "id": int(link.id),
                "service_tenant_id": getattr(service, "tenant_id", None),
                "service_id": int(service.id),
                "service_name": service.name or service.email,
                "status": link.status,
                "access_scope": {
                    "read_summary": bool(link.scope_vehicle_history_read),
                    "create_service_record": bool(link.scope_create_service_record),
                    "manage_work_order": True,
                    "manage_invoice": True,
                    "manage_photos": True,
                },
                "approved_at": link.approved_at.isoformat() if link.approved_at else None,
                "revoked_at": link.revoked_at.isoformat() if link.revoked_at else None,
                "updated_at": link.updated_at.isoformat() if link.updated_at else None,
            }
            for link, service in rows
        ],
        "requests": [
            {
                "id": int(req.id),
                "service_id": int(service.id),
                "service_name": service.name or service.email,
                "status": req.status,
                "message": req.request_message,
                "requested_at": req.requested_at.isoformat() if req.requested_at else None,
            }
            for req, service in requests
        ],
    }


@router.post("/{vehicle_id}/service-access/request-or-link")
def request_or_link_service_access(
    vehicle_id: int,
    payload: ServiceAccessLinkRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = _require_owned_vehicle(db, current_user, vehicle_id)
    service = db.query(Customer).filter(Customer.id == int(payload.service_id), Customer.role.in_(["service", "developer_admin"])).first()
    if not service:
        raise HTTPException(status_code=404, detail="Servis nebyl nalezen.")
    link = create_or_update_vehicle_service_link(
        db,
        tenant_id=int(vehicle.tenant_id),
        service_customer_id=int(service.id),
        owner_customer_id=int(current_user.id),
        vehicle_id=int(vehicle.id),
        approved_by_customer_id=int(current_user.id),
        source_type="direct_user_grant",
        note=(payload.request_reason or "").strip() or None,
    )
    write_global_audit_log(
        db,
        entity_type="vehicle_service_access",
        entity_id=int(link.id),
        action="service_access_direct_approved",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(vehicle.tenant_id),
        vehicle_id=int(vehicle.id),
        metadata={"service_id": int(service.id), "access_scope": payload.access_scope},
    )
    try:
        notify_service_owner_granted_direct_access(
            db,
            service_customer_id=int(service.id),
            vehicle=vehicle,
            owner=current_user,
        )
    except Exception as exc:
        print(f"[VEHICLE_LIFECYCLE] In-app oznámení servisu (direct grant) selhalo: {exc}")
    db.commit()
    return {"linked": True, "access_id": int(link.id), "status": "approved", "vehicle_id": int(vehicle.id), "service_id": int(service.id)}


@router.post("/{vehicle_id}/service-access/{access_id}/approve")
def approve_service_access(
    vehicle_id: int,
    access_id: int,
    payload: ServiceAccessDecisionRequest | None = None,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = _require_owned_vehicle(db, current_user, vehicle_id)
    request_row = db.query(ServiceAccessRequest).filter(
        ServiceAccessRequest.id == int(access_id),
        ServiceAccessRequest.vehicle_id == int(vehicle.id),
    ).first()
    if not request_row:
        raise HTTPException(status_code=404, detail="Žádost o přístup nebyla nalezena.")
    if int(request_row.owner_customer_id) != int(current_user.id):
        raise HTTPException(status_code=403, detail="Tuto žádost nemůžete schválit.")
    if request_row.status != "pending":
        raise HTTPException(status_code=409, detail="Žádost už byla vyřízena.")
    service_customer = (
        db.query(Customer)
        .filter(
            Customer.id == int(request_row.service_customer_id),
            Customer.role.in_(["service", "developer_admin"]),
        )
        .first()
    )
    if not service_customer:
        raise HTTPException(status_code=404, detail="Servis spojený se žádostí nebyl nalezen.")

    finalize_service_access_decision(
        db,
        request_row=request_row,
        vehicle=vehicle,
        owner_customer=current_user,
        service_customer=service_customer,
        decision="approved",
        decided_by=current_user,
        decision_note=(payload.note if payload else None) or None,
        source_route="post_vehicle_service_access_approve",
    )
    try:
        notify_service_access_decided(
            db,
            service_customer_id=int(request_row.service_customer_id),
            vehicle=vehicle,
            approved=True,
            owner=current_user,
        )
    except Exception as exc:
        print(f"[VEHICLE_LIFECYCLE] In-app oznámení servisu (schváleno) selhalo: {exc}")
    db.commit()
    return {"approved": True, "access_id": int(request_row.approved_link_id or 0), "request_id": int(request_row.id)}


@router.post("/{vehicle_id}/service-access/{access_id}/reject")
def reject_service_access(
    vehicle_id: int,
    access_id: int,
    payload: ServiceAccessDecisionRequest | None = None,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = _require_owned_vehicle(db, current_user, vehicle_id)
    request_row = db.query(ServiceAccessRequest).filter(
        ServiceAccessRequest.id == int(access_id),
        ServiceAccessRequest.vehicle_id == int(vehicle.id),
    ).first()
    if not request_row:
        raise HTTPException(status_code=404, detail="Žádost o přístup nebyla nalezena.")
    if request_row.status != "pending":
        raise HTTPException(status_code=409, detail="Žádost už byla vyřízena.")
    request_row.status = "rejected"
    request_row.decided_at = datetime.utcnow()
    request_row.decided_by_customer_id = int(current_user.id)
    request_row.decision_note = payload.note if payload else None
    write_global_audit_log(
        db,
        entity_type="vehicle_service_request",
        entity_id=int(request_row.id),
        action="service_access_rejected",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(vehicle.tenant_id),
        vehicle_id=int(vehicle.id),
        metadata={"note": payload.note if payload else None},
    )
    try:
        notify_service_access_decided(
            db,
            service_customer_id=int(request_row.service_customer_id),
            vehicle=vehicle,
            approved=False,
            owner=current_user,
        )
    except Exception as exc:
        print(f"[VEHICLE_LIFECYCLE] In-app oznámení servisu (zamítnuto) selhalo: {exc}")
    db.commit()
    return {"rejected": True, "request_id": int(request_row.id)}


@router.post("/{vehicle_id}/service-access/{access_id}/revoke")
def revoke_service_access(
    vehicle_id: int,
    access_id: int,
    payload: ServiceAccessDecisionRequest | None = None,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = _require_owned_vehicle(db, current_user, vehicle_id)
    link = db.query(VehicleServiceLink).filter(
        VehicleServiceLink.id == int(access_id),
        VehicleServiceLink.vehicle_id == int(vehicle.id),
        VehicleServiceLink.owner_customer_id == int(current_user.id),
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="Servisní přístup nebyl nalezen.")
    revoke_vehicle_service_link(
        db,
        service_customer_id=int(link.service_customer_id),
        vehicle_id=int(vehicle.id),
        revoked_by_customer_id=int(current_user.id),
        reason=(payload.note if payload else None) or "user_revoke",
    )
    write_global_audit_log(
        db,
        entity_type="vehicle_service_access",
        entity_id=int(link.id),
        action="service_access_revoked",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(vehicle.tenant_id),
        vehicle_id=int(vehicle.id),
        metadata={"reason": payload.note if payload else None},
    )
    db.commit()
    return {"revoked": True, "access_id": int(link.id)}


@router.post("/{vehicle_id}/remove/init")
def init_vehicle_removal(
    vehicle_id: int,
    payload: RemovalInitRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = _require_owned_vehicle(db, current_user, vehicle_id)
    reason = str(payload.reason_code or "").strip().lower()
    if reason not in REMOVAL_REASON_CODES:
        raise HTTPException(status_code=422, detail="Neplatný důvod odstranění vozidla z evidence.")
    if reason in REMOVAL_REASONS_WITH_TRANSFER_RECIPIENT:
        return {
            "vehicle_id": int(vehicle_id),
            "reason_code": reason,
            "required_followup_field": "buyer_email",
            "required_followup_fields": ["buyer_email", "buyer_phone"],
            "requires_transfer_token": True,
            "will_generate_digital_report": True,
            "will_archive_without_loss": True,
        }
    field = REMOVAL_FOLLOWUP_FIELDS[reason]
    return {
        "vehicle_id": int(vehicle_id),
        "reason_code": reason,
        "required_followup_field": field,
        "required_followup_fields": [field],
        "requires_transfer_token": False,
        "will_generate_digital_report": True,
        "will_archive_without_loss": True,
    }


@router.post("/{vehicle_id}/transfer-token")
def create_transfer_token(
    vehicle_id: int,
    payload: TransferTokenRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = _require_owned_vehicle(db, current_user, vehicle_id)
    token_row, raw_token, public_url = _create_transfer_token(
        db,
        vehicle=vehicle,
        current_user=current_user,
        transfer_reason=payload.transfer_reason,
        expires_in_days=payload.expires_in_days,
    )
    db.commit()
    return {
        "id": int(token_row.id),
        "vehicle_id": int(vehicle.id),
        "token": raw_token,
        "status": token_row.status,
        "expires_at": token_row.expires_at.isoformat(),
        "qr_payload": public_url,
        "qr_svg": _safe_qr_svg(public_url),
        "share": {"email": public_url, "sms": public_url, "whatsapp": public_url},
    }


@router.post("/{vehicle_id}/remove/confirm")
def confirm_vehicle_removal(
    vehicle_id: int,
    payload: RemovalConfirmRequest,
    background_tasks: BackgroundTasks,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = _require_owned_vehicle(db, current_user, vehicle_id)
    reason = str(payload.reason_code or "").strip().lower()
    if reason not in REMOVAL_REASON_CODES:
        raise HTTPException(status_code=422, detail="Neplatný důvod odstranění vozidla z evidence.")

    sale_buyer_email: str | None = None
    sale_buyer_phone: str | None = None
    followup_for_event: dict[str, Any] = dict(payload.followup_answer or {})

    if reason in REMOVAL_REASONS_WITH_TRANSFER_RECIPIENT:
        sale_buyer_email, sale_buyer_phone = _validate_sale_buyer_contact(
            payload.followup_answer,
            seller_email=getattr(current_user, "email", None),
        )
        followup_for_event = {"buyer_email": sale_buyer_email, "buyer_phone": sale_buyer_phone}
        rn = str((payload.followup_answer or {}).get("recipient_note") or "").strip()
        if rn:
            followup_for_event["recipient_note"] = rn
    else:
        required_field = REMOVAL_FOLLOWUP_FIELDS.get(reason)
        if not required_field:
            raise HTTPException(status_code=422, detail="Neplatný důvod odstranění vozidla z evidence.")
        if not str((payload.followup_answer or {}).get(required_field) or "").strip():
            raise HTTPException(
                status_code=422,
                detail=f"Pro důvod {reason} je povinné pole {required_field}.",
            )

    transfer_row = None
    transfer_payload = None
    new_owner_url: str | None = None
    if reason in REMOVAL_REASONS_WITH_TRANSFER_RECIPIENT:
        transfer_row, raw_token, public_url = _create_transfer_token(
            db,
            vehicle=vehicle,
            current_user=current_user,
            transfer_reason=str(reason),
            expires_in_days=30,
        )
        new_owner_url = public_url
        transfer_payload = {
            "token": raw_token,
            "qr_payload": public_url,
            "qr_svg": _safe_qr_svg(public_url),
            "share": {"email": public_url, "sms": public_url, "whatsapp": public_url},
        }
    document_row, _pdf_content = _generate_vehicle_report(
        db,
        vehicle=vehicle,
        current_user=current_user,
        new_owner_claim_url=new_owner_url,
    )
    archive_path = _archive_vehicle_bundle(db, vehicle=vehicle, document_row=document_row)
    released = release_vehicle_owner_assignment(db, vehicle=vehicle, owner=current_user)
    if not released:
        raise HTTPException(status_code=409, detail="Aktivní vlastnická vazba už byla ukončena.")
    vehicle.status = "archived"
    vehicle.user_email = released_placeholder_user_email(int(vehicle.id))
    event = VehicleRemovalEvent(
        vehicle_id=int(vehicle.id),
        initiated_by_user_id=int(current_user.id),
        reason_code=reason,
        required_followup_answer_json=json.dumps(followup_for_event, ensure_ascii=False, default=str),
        digital_report_document_id=int(document_row.id),
        archive_bundle_path=archive_path,
        transfer_token_id=int(transfer_row.id) if transfer_row else None,
    )
    db.add(event)
    db.flush()

    buyer_already_registered = False
    if reason in REMOVAL_REASONS_WITH_TRANSFER_RECIPIENT and sale_buyer_email:
        buyer_customer = get_customer_by_email(db, sale_buyer_email)
        buyer_already_registered = bool(buyer_customer)
        if buyer_customer:
            try:
                assert_module_ready(
                    db,
                    "system_notifications",
                    detail_prefix="Systémová oznámení nejsou připravená",
                )
                label = vehicle_label(vehicle)
                seller_disp = (current_user.name or current_user.email or "Prodávající").strip()
                db.add(
                    SystemNotification(
                        target_type="user",
                        target_value=str(buyer_customer.id),
                        title="Předání vozidla",
                        message=(
                            f"{seller_disp} vám předává vozidlo {label}. "
                            "Podrobnosti a digitální výpis najdete v e-mailu; dokončete převod přes odkaz v něm."
                        ),
                        severity="info",
                        created_by_customer_id=None,
                        created_by_email=APP_AUTOMATED_NOTIFICATION_SENDER,
                    )
                )
            except Exception as exc:
                print(f"[VEHICLE_SALE] Nepodařilo se vytvořit in-app oznámení pro kupce: {exc}")

    write_global_audit_log(
        db,
        entity_type="vehicle_removal_event",
        entity_id=int(event.id),
        action="vehicle_removed_archived",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(vehicle.tenant_id),
        vehicle_id=int(vehicle.id),
        metadata={
            "reason_code": reason,
            "archive_bundle_path": archive_path,
            "digital_report_document_id": int(document_row.id),
            "transfer_token_id": int(transfer_row.id) if transfer_row else None,
        },
    )
    db.commit()

    if reason in REMOVAL_REASONS_WITH_TRANSFER_RECIPIENT and sale_buyer_email and new_owner_url:
        pdf_path_str = str(REPORT_ROOT / f"vehicle-{int(vehicle.id)}-report-{document_row.document_id}.pdf")
        from src.modules.email_client.templates import build_app_url

        reg_url = build_app_url("/web/index.html")
        background_tasks.add_task(
            _send_vehicle_sale_buyer_email_background,
            sale_buyer_email,
            sale_buyer_phone or "",
            (current_user.name or current_user.email or "").strip(),
            vehicle_label(vehicle),
            str(new_owner_url),
            pdf_path_str,
            reg_url,
            buyer_already_registered,
        )

    return {
        "removed": True,
        "vehicle_id": int(vehicle.id),
        "reason_code": reason,
        "digital_report_document_id": int(document_row.id),
        "digital_report_document_uid": document_row.document_id,
        "digital_report_url": f"/api/v1/vehicles/{int(vehicle.id)}/digital-report?document_id={document_row.document_id}",
        "archive_bundle_path": archive_path,
        "transfer": transfer_payload,
        "history_preserved": True,
    }


@router.get("/{vehicle_id}/digital-report")
def get_vehicle_digital_report(
    vehicle_id: int,
    document_id: Optional[str] = None,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno.")
    can_access_report = user_owns_vehicle(db, current_user, vehicle)
    existing_document = None
    if document_id:
        existing_document = (
            db.query(VehicleReportDocument)
            .filter(
                VehicleReportDocument.vehicle_id == int(vehicle.id),
                VehicleReportDocument.document_id == str(document_id),
            )
            .first()
        )
        if not existing_document:
            raise HTTPException(status_code=404, detail="Digitální výpis nebyl nalezen.")
        removal_event = (
            db.query(VehicleRemovalEvent.id)
            .filter(
                VehicleRemovalEvent.vehicle_id == int(vehicle.id),
                VehicleRemovalEvent.digital_report_document_id == int(existing_document.id),
                VehicleRemovalEvent.initiated_by_user_id == int(current_user.id),
            )
            .first()
        )
        if removal_event is not None:
            can_access_report = True
    if not can_access_report:
        raise HTTPException(status_code=403, detail="Digitální výpis může stáhnout aktuální vlastník/správce vozidla.")
    if existing_document is not None:
        report_path = REPORT_ROOT / f"vehicle-{int(vehicle.id)}-report-{existing_document.document_id}.pdf"
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="PDF digitálního výpisu nebylo nalezeno v úložišti.")
        pdf_content = report_path.read_bytes()
        filename = f"vypis-vozidla-{int(vehicle.id)}-{existing_document.document_id}.pdf"
        return Response(content=pdf_content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'})
    document_row, pdf_content = _generate_vehicle_report(db, vehicle=vehicle, current_user=current_user)
    db.commit()
    filename = f"vypis-vozidla-{int(vehicle.id)}-{document_row.document_id}.pdf"
    return Response(content=pdf_content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'})


def validate_transfer_claim_identity(
    db: Session,
    payload: ClaimByTransferRequest,
    current_user: Customer,
) -> tuple[VehicleTransferToken, Vehicle]:
    """
    Ověří platný předávací token a shodu SPZ/VIN se záznamem vozidla.
    Používá se před převodem vlastnictví i před doplněním technického přehledu (bez změny vlastníka).
    """
    token_row = db.query(VehicleTransferToken).filter(VehicleTransferToken.token_hash == _token_hash(payload.token)).first()
    if not token_row:
        raise HTTPException(status_code=404, detail="Předávací token nebyl nalezen.")
    now = datetime.utcnow()
    if token_row.expires_at < now and token_row.status == "active":
        token_row.status = "expired"
        db.flush()
    if token_row.status == "claimed":
        write_global_audit_log(
            db,
            entity_type="vehicle_transfer_token",
            entity_id=int(token_row.id),
            action="transfer_token_claim_rejected",
            actor_type="user",
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
            tenant_id=getattr(current_user, "tenant_id", None),
            vehicle_id=int(token_row.vehicle_id),
            metadata={"reason": "already_claimed"},
        )
        db.commit()
        raise HTTPException(status_code=409, detail="Předávací token už byl použit.")
    if token_row.status == "revoked":
        write_global_audit_log(
            db,
            entity_type="vehicle_transfer_token",
            entity_id=int(token_row.id),
            action="transfer_token_claim_rejected",
            actor_type="user",
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
            tenant_id=getattr(current_user, "tenant_id", None),
            vehicle_id=int(token_row.vehicle_id),
            metadata={"reason": "token_revoked"},
        )
        db.commit()
        raise HTTPException(status_code=409, detail="Předávací token byl zrušen.")
    if token_row.status != "active":
        write_global_audit_log(
            db,
            entity_type="vehicle_transfer_token",
            entity_id=int(token_row.id),
            action="transfer_token_claim_rejected",
            actor_type="user",
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
            tenant_id=getattr(current_user, "tenant_id", None),
            vehicle_id=int(token_row.vehicle_id),
            metadata={"reason": "inactive_token", "token_status": token_row.status},
        )
        db.commit()
        raise HTTPException(status_code=409, detail="Předávací token už není aktivní.")
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(token_row.vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo k tokenu nebylo nalezeno.")
    if _normalize_spz(payload.spz) != _normalize_spz(vehicle.plate) or _normalize_vin(payload.vin) != _normalize_vin(vehicle.vin):
        write_global_audit_log(
            db,
            entity_type="vehicle_transfer_token",
            entity_id=int(token_row.id),
            action="transfer_token_claim_rejected",
            actor_type="user",
            actor_user_id=int(current_user.id),
            actor_role=getattr(current_user, "role", None),
            tenant_id=getattr(current_user, "tenant_id", None),
            vehicle_id=int(vehicle.id),
            metadata={"reason": "vin_or_spz_mismatch"},
        )
        db.commit()
        raise HTTPException(
            status_code=409,
            detail=(
                "SPZ nebo VIN po vyčištění mezer nesedí se záznamem vozidla v rejstříku. "
                "Zadejte SPZ přesně podle velkého technického průkazu včetně prvních znaků "
                "(často se plete začátek: číslice „1“ vs písmeno „I“, nebo „5“ vs „S“, pořadí znaků u kombinace číslic a písmen). "
                "VIN musí mít přesně 17 znaků bez mezer."
            ),
        )
    return token_row, vehicle


def _technical_overview_snapshot_for_refresh(overview: object | None) -> str | None:
    if overview is None:
        return None
    try:
        return json.dumps(overview, sort_keys=True, default=str)
    except Exception:
        return None


def perform_transfer_technical_refresh_before_claim(
    db: Session,
    payload: ClaimByTransferRequest,
    current_user: Customer,
) -> dict[str, Any]:
    """Obnoví vehicle_technical_overview před dokončením převodu (bez změny vlastníka)."""
    from src.modules.vehicle_hub.services.vehicle_technical_overview import persist_vehicle_technical_overview

    _, vehicle = validate_transfer_claim_identity(db, payload, current_user)
    before = _technical_overview_snapshot_for_refresh(getattr(vehicle, "vehicle_technical_overview", None))
    try:
        persist_vehicle_technical_overview(db, vehicle)
    except Exception as exc:
        logger.warning(
            "[VEHICLE_LIFECYCLE] refresh technical overview failed vehicle_id=%s err=%s",
            getattr(vehicle, "id", None),
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Technické údaje se nepodařilo načíst. Zkuste to za chvíli znovu.",
        )
    db.commit()
    db.refresh(vehicle)
    after = _technical_overview_snapshot_for_refresh(getattr(vehicle, "vehicle_technical_overview", None))
    changed = before != after
    write_global_audit_log(
        db,
        entity_type="vehicle",
        entity_id=int(vehicle.id),
        action="transfer_technical_overview_pre_claim_refresh",
        actor_type="user",
        actor_user_id=int(current_user.id),
        tenant_id=getattr(vehicle, "tenant_id", None),
        vehicle_id=int(vehicle.id),
        metadata={"technical_overview_changed": changed},
    )
    db.commit()
    return {"refreshed": True, "technical_overview_changed": changed}


@router.post("/transfer-technical-refresh-before-claim")
def transfer_technical_refresh_before_claim(
    payload: ClaimByTransferRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Doplnění technických údajů před převodem — kanonické URL pod /api/v1/vehicles/."""
    return perform_transfer_technical_refresh_before_claim(db, payload, current_user)


@router.post("/claim-by-transfer")
def claim_vehicle_by_transfer(
    payload: ClaimByTransferRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token_row, vehicle = validate_transfer_claim_identity(db, payload, current_user)
    transfer_vehicle_to_new_owner(
        db,
        vehicle=vehicle,
        new_owner=current_user,
        assigned_by_customer_id=int(token_row.issued_by_user_id),
        ownership_origin="transfer_token_claim",
    )
    token_row.status = "claimed"
    token_row.claimed_by_user_id = int(current_user.id)
    token_row.claimed_at = datetime.utcnow()
    vehicle.status = "active"
    write_global_audit_log(
        db,
        entity_type="vehicle_transfer_token",
        entity_id=int(token_row.id),
        action="transfer_token_claimed",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=getattr(current_user, "tenant_id", None),
        vehicle_id=int(vehicle.id),
        metadata={"issued_by_user_id": int(token_row.issued_by_user_id)},
    )
    db.commit()
    return {"claimed": True, "vehicle_id": int(vehicle.id), "history_preserved": True}


@router.post("/transfer-claim")
def transfer_claim_alias(
    payload: ClaimByTransferRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stejné chování jako POST /claim-by-transfer (alias pro novější klienty)."""
    return claim_vehicle_by_transfer(payload=payload, current_user=current_user, db=db)
