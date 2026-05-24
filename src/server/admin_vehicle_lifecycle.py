"""
Admin API — přehled převodů / archivovaných vozidel.
Mount: `/admin-api/vehicle-lifecycle` a `/api/admin/vehicle-lifecycle`.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request as FastAPIRequest
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.modules.vehicle_hub.audit_log import write_global_audit_log
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, GlobalAuditLog, Vehicle, VehicleRemovalEvent, VehicleReportDocument, VehicleTransferToken
from src.modules.vehicle_hub.ownership import get_customer_by_email
from src.modules.vehicle_hub.routers_v1.vehicle_lifecycle import REPORT_ROOT, _create_transfer_token, _send_vehicle_sale_buyer_email_background
from src.modules.vehicle_hub.service_access import vehicle_label
from src.modules.email_client.templates import build_app_url
from src.server.admin_api import require_developer_admin

router = APIRouter(prefix="/vehicle-lifecycle", tags=["admin-vehicle-lifecycle"])

REPORT_ROOT.mkdir(parents=True, exist_ok=True)


def _parse_followup(raw: str | None) -> dict[str, Any]:
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {}


def _token_summary(tok: VehicleTransferToken | None, *, now: datetime) -> dict[str, Any]:
    if tok is None:
        return {"status": None, "expires_at": None, "claimed_at": None}
    effective = tok.status
    if effective == "active" and tok.expires_at < now:
        effective = "expired"
    return {
        "id": int(tok.id),
        "status": effective,
        "expires_at": tok.expires_at.isoformat() if tok.expires_at else None,
        "claimed_at": tok.claimed_at.isoformat() if tok.claimed_at else None,
        "claimed_by_user_id": int(tok.claimed_by_user_id) if tok.claimed_by_user_id else None,
    }


def _lifecycle_phase(*, vehicle: Vehicle, tok: VehicleTransferToken | None, now: datetime) -> str:
    if getattr(vehicle, "status", None) != "archived":
        return str(getattr(vehicle, "status", None) or "active")
    if tok is None:
        return "archived"
    if tok.status == "claimed":
        return "transferred"
    if tok.status == "active":
        return "transfer_pending" if tok.expires_at >= now else "transfer_expired"
    if tok.status == "expired":
        return "transfer_expired"
    if tok.status == "revoked":
        return "transfer_revoked"
    return "archived"


def _digital_report_url(doc: VehicleReportDocument | None, vehicle_id: int) -> str | None:
    if doc is None:
        return None
    return f"/api/v1/vehicles/{int(vehicle_id)}/digital-report?document_id={doc.document_id}"


@router.get("")
def admin_list_vehicle_lifecycle(
    request: FastAPIRequest,
    _: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
    lifecycle_phase: Optional[str] = Query(None),
    reason_code: Optional[str] = Query(None),
    vin_contains: Optional[str] = Query(None),
    plate_contains: Optional[str] = Query(None),
    recipient_email_contains: Optional[str] = Query(None),
    initiator_email_contains: Optional[str] = Query(None),
    token_status: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    q = db.query(VehicleRemovalEvent, Vehicle).join(Vehicle, Vehicle.id == VehicleRemovalEvent.vehicle_id)
    if reason_code:
        q = q.filter(VehicleRemovalEvent.reason_code == reason_code.strip().lower())
    if vin_contains:
        q = q.filter(Vehicle.vin.ilike(f"%{vin_contains.strip()}%"))
    if plate_contains:
        q = q.filter(Vehicle.plate.ilike(f"%{plate_contains.strip()}%"))
    if date_from:
        q = q.filter(VehicleRemovalEvent.executed_at >= date_from)
    if date_to:
        q = q.filter(VehicleRemovalEvent.executed_at <= date_to)
    rows = (
        q.order_by(desc(VehicleRemovalEvent.executed_at), desc(VehicleRemovalEvent.id))
        .offset(offset)
        .limit(limit)
        .all()
    )
    now = datetime.utcnow()
    items: list[dict[str, Any]] = []
    for ev, veh in rows:
        fu = _parse_followup(ev.required_followup_answer_json)
        recipient_email = str(fu.get("buyer_email") or "").strip().lower() or None
        initiator = db.query(Customer).filter(Customer.id == int(ev.initiated_by_user_id)).first()
        tok = (
            db.query(VehicleTransferToken).filter(VehicleTransferToken.id == int(ev.transfer_token_id)).first()
            if ev.transfer_token_id
            else None
        )
        if recipient_email_contains and recipient_email_contains.lower() not in (recipient_email or ""):
            continue
        if initiator_email_contains and initiator_email_contains.lower() not in (
            str(initiator.email or "").lower() if initiator else ""
        ):
            continue
        tsumm = _token_summary(tok, now=now)
        if token_status and tsumm.get("status") != token_status:
            continue
        phase = _lifecycle_phase(vehicle=veh, tok=tok, now=now)
        if lifecycle_phase and phase != lifecycle_phase:
            continue
        doc = (
            db.query(VehicleReportDocument).filter(VehicleReportDocument.id == int(ev.digital_report_document_id)).first()
            if ev.digital_report_document_id
            else None
        )
        items.append(
            {
                "vehicle_id": int(veh.id),
                "vin": veh.vin,
                "plate": veh.plate,
                "brand": veh.brand,
                "model": veh.model,
                "year": veh.year,
                "vehicle_status": veh.status,
                "lifecycle_phase": phase,
                "reason_code": ev.reason_code,
                "executed_at": ev.executed_at.isoformat() if ev.executed_at else None,
                "initiator_customer_id": int(ev.initiated_by_user_id),
                "initiator_email": initiator.email if initiator else None,
                "recipient_email": recipient_email,
                "digital_report_document_uid": doc.document_id if doc else None,
                "digital_report_url": _digital_report_url(doc, veh.id),
                "transfer_token": tsumm,
                "removal_event_id": int(ev.id),
            }
        )

    write_global_audit_log(
        db,
        entity_type="admin_vehicle_lifecycle",
        entity_id=None,
        action="ADMIN_LIFECYCLE_LIST_VIEWED",
        actor_type="admin",
        tenant_id=None,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"limit": limit, "offset": offset},
    )
    db.commit()
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/{vehicle_id}")
def admin_vehicle_lifecycle_detail(
    vehicle_id: int,
    request: FastAPIRequest,
    _: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    veh = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id)).first()
    if not veh:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno.")
    events = (
        db.query(VehicleRemovalEvent)
        .filter(VehicleRemovalEvent.vehicle_id == int(vehicle_id))
        .order_by(desc(VehicleRemovalEvent.executed_at), desc(VehicleRemovalEvent.id))
        .all()
    )
    now = datetime.utcnow()
    payload_events = []
    for ev in events:
        fu = _parse_followup(ev.required_followup_answer_json)
        tok = (
            db.query(VehicleTransferToken).filter(VehicleTransferToken.id == int(ev.transfer_token_id)).first()
            if ev.transfer_token_id
            else None
        )
        doc = (
            db.query(VehicleReportDocument).filter(VehicleReportDocument.id == int(ev.digital_report_document_id)).first()
            if ev.digital_report_document_id
            else None
        )
        initiator = db.query(Customer).filter(Customer.id == int(ev.initiated_by_user_id)).first()
        payload_events.append(
            {
                "removal_event_id": int(ev.id),
                "reason_code": ev.reason_code,
                "executed_at": ev.executed_at.isoformat() if ev.executed_at else None,
                "followup": fu,
                "initiator_email": initiator.email if initiator else None,
                "digital_report_url": _digital_report_url(doc, veh.id),
                "transfer_token": _token_summary(tok, now=now),
            }
        )

    audits = (
        db.query(GlobalAuditLog)
        .filter(GlobalAuditLog.vehicle_id == int(vehicle_id))
        .filter(GlobalAuditLog.action.in_(["transfer_token_claimed", "transfer_token_opened", "vehicle_removed_archived"]))
        .order_by(desc(GlobalAuditLog.occurred_at))
        .limit(80)
        .all()
    )
    audit_rows = []
    for row in audits:
        audit_rows.append(
            {
                "action": row.action,
                "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                "metadata_json": row.metadata_json,
                "actor_user_id": row.actor_user_id,
            }
        )

    write_global_audit_log(
        db,
        entity_type="admin_vehicle_lifecycle",
        entity_id=int(vehicle_id),
        action="ADMIN_LIFECYCLE_VEHICLE_VIEWED",
        actor_type="admin",
        tenant_id=getattr(veh, "tenant_id", None),
        vehicle_id=int(vehicle_id),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={},
    )
    db.commit()

    return {
        "vehicle_id": int(veh.id),
        "vin": veh.vin,
        "plate": veh.plate,
        "brand": veh.brand,
        "model": veh.model,
        "year": veh.year,
        "vehicle_status": veh.status,
        "removal_events": payload_events,
        "audit_snippet": audit_rows,
    }


class ResendTransferEmailBody(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


@router.post("/{vehicle_id}/resend-transfer-email")
def admin_resend_transfer_email(
    vehicle_id: int,
    payload: ResendTransferEmailBody | None,
    request: FastAPIRequest,
    admin_email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    veh = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id)).first()
    if not veh:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno.")
    ev = (
        db.query(VehicleRemovalEvent)
        .filter(VehicleRemovalEvent.vehicle_id == int(vehicle_id))
        .order_by(desc(VehicleRemovalEvent.executed_at), desc(VehicleRemovalEvent.id))
        .first()
    )
    if not ev:
        raise HTTPException(status_code=404, detail="Žádný záznam odebrání.")
    fu = _parse_followup(ev.required_followup_answer_json)
    recipient = str(fu.get("buyer_email") or "").strip().lower()
    phone = str(fu.get("buyer_phone") or "").strip()
    if not recipient:
        raise HTTPException(status_code=422, detail="U události chybí e-mail příjemce.")
    tok = (
        db.query(VehicleTransferToken).filter(VehicleTransferToken.id == int(ev.transfer_token_id)).first()
        if ev.transfer_token_id
        else None
    )
    if tok is None or tok.status != "active":
        raise HTTPException(status_code=409, detail="Nelze znovu odeslat — token není aktivní.")
    doc = db.query(VehicleReportDocument).filter(VehicleReportDocument.id == int(ev.digital_report_document_id)).first()
    if not doc:
        raise HTTPException(status_code=409, detail="Chybí digitální výpis.")
    issuer = db.query(Customer).filter(Customer.id == int(tok.issued_by_user_id)).first()
    transfer_url = str(tok.qr_payload or "").strip()
    if not transfer_url:
        raise HTTPException(status_code=409, detail="Nelze znovu odeslat — chybí uložený odkaz tokenu.")
    buyer_customer = get_customer_by_email(db, recipient)
    buyer_already_registered = bool(buyer_customer)
    reg_url = build_app_url("/web/index.html")
    _send_vehicle_sale_buyer_email_background(
        recipient,
        phone or "",
        (issuer.name or issuer.email or "").strip() if issuer else "",
        vehicle_label(veh),
        transfer_url,
        pdf_path_str,
        reg_url,
        buyer_already_registered,
    )
    write_global_audit_log(
        db,
        entity_type="vehicle_transfer_token",
        entity_id=int(tok.id),
        action="ADMIN_TRANSFER_EMAIL_RESENT",
        actor_type="admin",
        actor_user_id=None,
        tenant_id=getattr(veh, "tenant_id", None),
        vehicle_id=int(vehicle_id),
        metadata={"admin_email": admin_email, "recipient_email": recipient, "note": (payload.note if payload else None)},
    )
    db.commit()
    return {"resent": True}


@router.post("/{vehicle_id}/revoke-transfer-token")
def admin_revoke_transfer_token(
    vehicle_id: int,
    request: FastAPIRequest,
    admin_email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    veh = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id)).first()
    if not veh:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno.")
    ev = (
        db.query(VehicleRemovalEvent)
        .filter(VehicleRemovalEvent.vehicle_id == int(vehicle_id))
        .order_by(desc(VehicleRemovalEvent.executed_at), desc(VehicleRemovalEvent.id))
        .first()
    )
    if not ev or not ev.transfer_token_id:
        raise HTTPException(status_code=404, detail="Token k odebrání nebyl nalezen.")
    tok = db.query(VehicleTransferToken).filter(VehicleTransferToken.id == int(ev.transfer_token_id)).first()
    if not tok:
        raise HTTPException(status_code=404, detail="Token neexistuje.")
    if tok.status != "active":
        raise HTTPException(status_code=409, detail="Token už nelze zrušit.")
    tok.status = "revoked"
    write_global_audit_log(
        db,
        entity_type="vehicle_transfer_token",
        entity_id=int(tok.id),
        action="ADMIN_TRANSFER_TOKEN_REVOKED",
        actor_type="admin",
        tenant_id=getattr(veh, "tenant_id", None),
        vehicle_id=int(vehicle_id),
        metadata={"admin_email": admin_email},
    )
    db.commit()
    return {"revoked": True}


class RegenerateBody(BaseModel):
    expires_in_days: int = Field(default=30, ge=1, le=180)


@router.post("/{vehicle_id}/regenerate-transfer-token")
def admin_regenerate_transfer_token(
    vehicle_id: int,
    payload: RegenerateBody,
    request: FastAPIRequest,
    admin_email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    veh = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id)).first()
    if not veh:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno.")
    ev = (
        db.query(VehicleRemovalEvent)
        .filter(VehicleRemovalEvent.vehicle_id == int(vehicle_id))
        .order_by(desc(VehicleRemovalEvent.executed_at), desc(VehicleRemovalEvent.id))
        .first()
    )
    if not ev:
        raise HTTPException(status_code=404, detail="Žádný záznam odebrání.")
    prev_tid = int(ev.transfer_token_id) if ev.transfer_token_id else None
    if ev.transfer_token_id:
        old = db.query(VehicleTransferToken).filter(VehicleTransferToken.id == int(ev.transfer_token_id)).first()
        if old and old.status == "active":
            old.status = "revoked"
    issuer = db.query(Customer).filter(Customer.id == int(ev.initiated_by_user_id)).first()
    if not issuer:
        raise HTTPException(status_code=409, detail="Nelze najít vystavitele tokenu.")
    new_row, _raw, _url = _create_transfer_token(
        db,
        vehicle=veh,
        current_user=issuer,
        transfer_reason="admin_regenerated",
        expires_in_days=int(payload.expires_in_days),
    )
    ev.transfer_token_id = int(new_row.id)
    write_global_audit_log(
        db,
        entity_type="vehicle_transfer_token",
        entity_id=int(new_row.id),
        action="ADMIN_TRANSFER_TOKEN_REGENERATED",
        actor_type="admin",
        tenant_id=getattr(veh, "tenant_id", None),
        vehicle_id=int(vehicle_id),
        metadata={"admin_email": admin_email, "previous_token_id": prev_tid},
    )
    db.commit()
    return {"regenerated": True, "transfer_token_id": int(new_row.id), "expires_at": new_row.expires_at.isoformat()}
