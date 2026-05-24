"""
Admin support view vozidla: read-only snapshot + řízené opravy s auditem a e-mailem.

HTTP prefix: výhradně `/admin-api/vehicles/...` (bez aliasu `/api/admin` kvůli zmenšení povrchu útoku).

Pozn.: Router `vehicle-lifecycle` má stále dual mount `/admin-api` + `/api/admin`; tyto cesty jsou chráněny
stejným `Cloudflare Access` / síťovým guardem díky položce `/api/admin` v `_ADMIN_PATH_PREFIXES`.
"""
from __future__ import annotations

import json
import mimetypes
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request as FastAPIRequest
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from src.core.config import DATA_DIR
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import (
    AdminCustomerChangeEvent,
    DeveloperActionAuditLog,
    GlobalAuditLog,
    Reminder,
    ServiceRecord,
    Vehicle,
    VehicleInspectionHistory,
    VehiclePhotoAsset,
    VehicleReportDocument,
    VehicleServiceLink,
    VehicleTachometerHistoryEntry,
)
from src.modules.vehicle_hub.ownership import get_customer_by_email, get_primary_vehicle_owner
from src.modules.vehicle_hub.services.vehicle_technical_overview import technical_overview_for_api
from src.modules.vehicle_hub.vehicle_photo_assets import resolve_storage_file

from src.server.admin_api import require_developer_admin
from src.server.admin_customer_change_notify import (
    admin_change_table_exists,
    mark_events_notified,
    record_admin_customer_change,
    send_customer_change_notification_email,
)

router = APIRouter(tags=["admin-vehicle-support"])

VEHICLE_PHOTOS_ROOT = DATA_DIR / "vehicle_photos"


def _json_for_audit(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return "{}"


def _append_developer_audit(
    db: Session,
    *,
    admin_email: str,
    request: Optional[FastAPIRequest],
    action_type: str,
    target_resource: str,
    parameters: Dict[str, Any],
    result: str = "success",
) -> None:
    try:
        actor = get_customer_by_email(db, admin_email.strip().lower())
        if not actor:
            return
        entry = DeveloperActionAuditLog(
            developer_id=actor.id,
            developer_email=(admin_email or "").strip().lower() or None,
            action_type=action_type,
            target_resource=target_resource,
            parameters_json=_json_for_audit(parameters),
            result=result,
            status_code=None,
            request_ip=(request.client.host if request and request.client else None),
            created_at=datetime.utcnow(),
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[ADMIN_AUDIT] admin_vehicle_support: failed to persist '{action_type}': {exc}")


def _mask_email_for_owner_context(email: Optional[str]) -> Optional[str]:
    raw = (email or "").strip()
    if not raw or "@" not in raw:
        return raw or None
    local, _, domain = raw.partition("@")
    if len(local) <= 2:
        return f"{local[0]}***@{domain}"
    return f"{local[0]}{local[1]}***@{domain}"


def _dt_iso(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _serialize_vehicle_basics(vehicle: Vehicle) -> Dict[str, Any]:
    return {
        "id": int(vehicle.id),
        "tenant_id": int(vehicle.tenant_id) if vehicle.tenant_id is not None else None,
        "nickname": vehicle.nickname,
        "brand": vehicle.brand,
        "model": vehicle.model,
        "year": vehicle.year,
        "plate": vehicle.plate,
        "vin": vehicle.vin,
        "engine": vehicle.engine,
        "fuel": vehicle.fuel,
        "body_type": vehicle.body_type,
        "notes": vehicle.notes,
        "status": vehicle.status,
        "stk_valid_until": _dt_iso(vehicle.stk_valid_until),
        "insurance_provider": vehicle.insurance_provider,
        "insurance_valid_until": _dt_iso(vehicle.insurance_valid_until),
        "orv_number": vehicle.orv_number,
        "data_trust_state": vehicle.data_trust_state,
        "created_at": _dt_iso(vehicle.created_at),
        "updated_at": _dt_iso(vehicle.updated_at),
    }


def _serialize_technical_block(vehicle: Vehicle) -> Dict[str, Any]:
    sto = getattr(vehicle, "vehicle_technical_overview", None)
    return {
        "vehicle_technical_overview": technical_overview_for_api(sto) if sto else None,
        "tyres_info": vehicle.tyres_info,
        "current_mileage_km": vehicle.current_mileage_km,
        "last_stk_mileage_km": vehicle.last_stk_mileage_km,
        "mileage_checked_at": _dt_iso(vehicle.mileage_checked_at),
        "latest_stk_odometer_km": vehicle.latest_stk_odometer_km,
        "latest_stk_odometer_date": _dt_iso(vehicle.latest_stk_odometer_date),
        "latest_stk_sync_at": _dt_iso(vehicle.latest_stk_sync_at),
        "latest_stk_source": vehicle.latest_stk_source,
        "latest_stk_import_status": vehicle.latest_stk_import_status,
    }


def _service_record_dict(r: ServiceRecord) -> Dict[str, Any]:
    return {
        "id": int(r.id),
        "vehicle_id": int(r.vehicle_id),
        "performed_at": _dt_iso(r.performed_at),
        "mileage": r.mileage,
        "description": r.description,
        "price": r.price,
        "note": r.note,
        "category": r.category,
        "service_type": r.service_type,
        "record_status": r.record_status,
        "is_deleted": bool(r.is_deleted),
        "tenant_id": int(r.tenant_id) if r.tenant_id else None,
    }


def _document_dict(d: VehicleReportDocument) -> Dict[str, Any]:
    return {
        "id": int(d.id),
        "document_type": d.document_type,
        "document_id": d.document_id,
        "status": d.status,
        "issued_service_name": d.issued_service_name,
        "vehicle_brand": d.vehicle_brand,
        "vehicle_model": d.vehicle_model,
        "vehicle_vin_masked": d.vehicle_vin_masked,
        "finalized_at": _dt_iso(d.finalized_at),
    }


def _photo_dict(vehicle: Vehicle, row: VehiclePhotoAsset) -> Dict[str, Any]:
    return {
        "id": int(row.id),
        "vehicle_id": int(row.vehicle_id),
        "role": row.role,
        "photo_kind": row.photo_kind,
        "mime_type": row.mime_type,
        "created_at": _dt_iso(row.created_at),
        "sort_order": row.sort_order,
        "preview_url_admin": (
            f"/admin-api/vehicles/{int(vehicle.id)}/support-photo/{int(row.id)}/file"
        ),
    }


def _tacho_merge_rows(db: Session, vehicle_id: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in (
        db.query(VehicleTachometerHistoryEntry)
        .filter(VehicleTachometerHistoryEntry.vehicle_id == vehicle_id)
        .order_by(VehicleTachometerHistoryEntry.imported_at.desc())
        .all()
    ):
        out.append(
            {
                "entry_kind": "tachometer_import",
                "id": int(row.id),
                "check_date": _dt_iso(row.check_date),
                "mileage_km": row.mileage_km,
                "protocol_number": row.protocol_number,
                "inspection_type": row.inspection_type,
                "source": row.source,
                "status": row.status,
                "summary": row.summary,
                "imported_at": _dt_iso(row.imported_at),
            }
        )
    for row in (
        db.query(VehicleInspectionHistory)
        .filter(VehicleInspectionHistory.vehicle_id == vehicle_id)
        .order_by(VehicleInspectionHistory.imported_at.desc())
        .all()
    ):
        out.append(
            {
                "entry_kind": "inspection_history",
                "id": int(row.id),
                "inspection_date": _dt_iso(row.inspection_date),
                "inspection_type": row.inspection_type,
                "inspection_kind": row.inspection_kind,
                "odometer_km": row.odometer_km,
                "protocol_number": row.protocol_number,
                "result_label": row.result_label,
                "source": row.source,
                "imported_at": _dt_iso(row.imported_at),
            }
        )
    return out


def _reminder_dict(r: Reminder) -> Dict[str, Any]:
    return {
        "id": int(r.id),
        "vehicle_id": int(r.vehicle_id) if r.vehicle_id else None,
        "type": r.type,
        "text": r.text,
        "due_date": _dt_iso(r.due_date),
        "is_manual": r.is_manual,
        "is_completed": r.is_completed,
        "created_at": _dt_iso(r.created_at),
    }


def _service_access_dict(link: VehicleServiceLink) -> Dict[str, Any]:
    return {
        "id": int(link.id),
        "service_customer_id": int(link.service_customer_id),
        "status": link.status,
        "created_at": _dt_iso(link.created_at),
        "updated_at": _dt_iso(link.updated_at),
    }


def _audit_rows_for_vehicle(db: Session, vehicle_id: int, limit: int = 150) -> List[Dict[str, Any]]:
    rows = (
        db.query(GlobalAuditLog)
        .filter(GlobalAuditLog.vehicle_id == int(vehicle_id))
        .order_by(GlobalAuditLog.occurred_at.desc(), GlobalAuditLog.id.desc())
        .limit(limit)
        .all()
    )
    payload: List[Dict[str, Any]] = []
    for a in rows:
        payload.append(
            {
                "id": int(a.id),
                "action": a.action,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "actor_user_id": a.actor_user_id,
                "actor_role": a.actor_role,
                "occurred_at": _dt_iso(a.occurred_at),
                "has_before": bool(a.before_json),
                "has_after": bool(a.after_json),
            }
        )
    return payload


class AdminVehicleCorrectionRequest(BaseModel):
    target_entity: str = Field(..., description="vehicle|service_record|reminder")
    target_id: Optional[str] = None
    field: str = Field(..., min_length=1)
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    reason: str = Field(..., max_length=6000)
    notify_user: bool = Field(default=True)

    @field_validator("reason")
    @classmethod
    def _reason_nonempty_trim(cls, value: str) -> str:
        text = (value or "").strip()
        if len(text) < 10:
            raise ValueError("Důvod změny musí mít po ořezání mezer alespoň 10 znaků.")
        return text


def _norm_client_value(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _vehicle_field_current_raw(vehicle: Vehicle, field: str) -> Any:
    if not hasattr(vehicle, field):
        raise HTTPException(status_code=400, detail="Neplatné pole vozidla")
    return getattr(vehicle, field)


def _coerce_vehicle_value(field: str, raw: str) -> Any:
    v = raw.strip() if isinstance(raw, str) else raw
    if field in {"year", "current_mileage_km", "last_stk_mileage_km", "latest_stk_odometer_km"}:
        if v == "" or v is None:
            return None
        return int(v)
    if field in {"stk_valid_until", "insurance_valid_until"}:
        if v == "" or v is None:
            return None
        try:
            return date.fromisoformat(str(v)[:10])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Neplatné datum") from exc
    if v == "":
        return None
    return str(v)


VEHICLE_CORRECTABLE_FIELDS = {
    "nickname",
    "brand",
    "model",
    "year",
    "plate",
    "vin",
    "engine",
    "fuel",
    "body_type",
    "notes",
    "stk_valid_until",
    "insurance_provider",
    "insurance_valid_until",
    "tyres_info",
    "current_mileage_km",
    "last_stk_mileage_km",
    "orv_number",
}


def _serialize_value_for_compare(entity: str, field: str, value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


SERVICE_RECORD_CORRECTABLE = {"description", "mileage", "note", "performed_at"}


def _coerce_service_record_value(field: str, raw: str) -> Any:
    if field == "mileage":
        if raw.strip() == "":
            return None
        return int(raw)
    if field == "performed_at":
        if raw.strip() == "":
            raise HTTPException(status_code=400, detail="performed_at nemůže být prázdné")
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Neplatné performed_at (ISO)") from exc
    return raw


REMINDER_CORRECTABLE = {"text", "due_date"}


def _coerce_reminder_value(field: str, raw: str) -> Any:
    if field == "due_date":
        if raw.strip() == "":
            return None
        return date.fromisoformat(raw[:10])
    return raw


@router.get("/vehicles/{vehicle_id}/detail-snapshot")
def admin_vehicle_detail_snapshot(
    vehicle_id: int,
    request: FastAPIRequest,
    admin_email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    owner = get_primary_vehicle_owner(db, vehicle)
    owner_id = int(owner.id) if owner else None
    viewer = get_customer_by_email(db, admin_email.strip().lower())
    viewer_id = int(viewer.id) if viewer else None

    _append_developer_audit(
        db,
        admin_email=admin_email,
        request=request,
        action_type="admin_vehicle_detail_viewed",
        target_resource=f"vehicle:{vehicle_id}",
        parameters={
            "admin_id": viewer_id,
            "vehicle_id": int(vehicle_id),
            "vin": vehicle.vin,
            "tenant_id": int(vehicle.tenant_id) if vehicle.tenant_id is not None else None,
            "owner_user_id": owner_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": "admin_support_view",
        },
    )

    records = (
        db.query(ServiceRecord)
        .filter(
            ServiceRecord.vehicle_id == int(vehicle_id),
            ServiceRecord.is_deleted.is_(False),
        )
        .order_by(ServiceRecord.performed_at.desc())
        .limit(500)
        .all()
    )
    documents = (
        db.query(VehicleReportDocument)
        .filter(VehicleReportDocument.vehicle_id == int(vehicle_id))
        .order_by(VehicleReportDocument.finalized_at.desc())
        .limit(200)
        .all()
    )
    photos = (
        db.query(VehiclePhotoAsset)
        .filter(
            VehiclePhotoAsset.vehicle_id == int(vehicle_id),
            VehiclePhotoAsset.deleted_at.is_(None),
        )
        .order_by(VehiclePhotoAsset.sort_order.asc(), VehiclePhotoAsset.id.asc())
        .all()
    )
    reminders = (
        db.query(Reminder)
        .filter(Reminder.vehicle_id == int(vehicle_id))
        .order_by(Reminder.due_date.asc(), Reminder.id.desc())
        .limit(300)
        .all()
    )
    access = (
        db.query(VehicleServiceLink)
        .filter(VehicleServiceLink.vehicle_id == int(vehicle_id))
        .order_by(VehicleServiceLink.id.desc())
        .limit(200)
        .all()
    )

    owner_ctx: Dict[str, Any] = {
        "owner_user_id": owner_id,
        "tenant_id": int(vehicle.tenant_id) if vehicle.tenant_id is not None else None,
        "account_email_masked": _mask_email_for_owner_context(owner.email) if owner else None,
        "support_note": "Pro plný kontakt použijte běžné admin rozhraní uživatele — zde jen minimalizované údaje o vazbě vlastníka.",
    }

    snapshot = {
        "mode": "admin_support_view",
        "vehicle": _serialize_vehicle_basics(vehicle),
        "owner_context": owner_ctx,
        "technical_data": _serialize_technical_block(vehicle),
        "service_records": [_service_record_dict(r) for r in records],
        "documents": [_document_dict(d) for d in documents],
        "photos": [_photo_dict(vehicle, p) for p in photos],
        "tachometer_history": _tacho_merge_rows(db, int(vehicle_id)),
        "reminders": [_reminder_dict(r) for r in reminders],
        "service_access": [_service_access_dict(a) for a in access],
        "audit_log": _audit_rows_for_vehicle(db, int(vehicle_id)),
        "permissions": {
            "admin_can_view": True,
            "admin_can_correct": True,
            "default_read_only": True,
            "requires_reason_for_change": True,
            "requires_user_notification": True,
            "min_reason_length": 10,
        },
    }
    return snapshot


@router.get("/vehicles/{vehicle_id}/support-photo/{photo_id}/file")
def admin_support_vehicle_photo_file(
    vehicle_id: int,
    photo_id: int,
    request: FastAPIRequest,
    admin_email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    viewer = get_customer_by_email(db, admin_email.strip().lower())
    viewer_id = int(viewer.id) if viewer else None
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    owner = get_primary_vehicle_owner(db, vehicle)
    owner_id = int(owner.id) if owner else None

    row = (
        db.query(VehiclePhotoAsset)
        .filter(
            VehiclePhotoAsset.id == int(photo_id),
            VehiclePhotoAsset.vehicle_id == int(vehicle_id),
            VehiclePhotoAsset.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Fotka nebyla nalezena")
    key = row.storage_path_preview or row.storage_key
    photo_file = resolve_storage_file(VEHICLE_PHOTOS_ROOT, key)
    if not photo_file:
        raise HTTPException(status_code=404, detail="Soubor náhledu neexistuje")
    media_type, _ = mimetypes.guess_type(str(photo_file))

    _append_developer_audit(
        db,
        admin_email=admin_email,
        request=request,
        action_type="admin_vehicle_support_photo_viewed",
        target_resource=f"vehicle:{vehicle_id}:photo:{photo_id}",
        parameters={
            "admin_id": viewer_id,
            "vehicle_id": int(vehicle_id),
            "photo_id": int(photo_id),
            "vin": vehicle.vin,
            "tenant_id": int(vehicle.tenant_id) if vehicle.tenant_id is not None else None,
            "owner_user_id": owner_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": "admin_support_view",
        },
    )

    return FileResponse(
        path=str(photo_file),
        media_type=media_type or row.mime_type or "application/octet-stream",
        filename=photo_file.name,
    )


@router.post("/vehicles/{vehicle_id}/corrections")
def admin_vehicle_correction(
    vehicle_id: int,
    payload: AdminVehicleCorrectionRequest,
    request: FastAPIRequest,
    admin_email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    reason = payload.reason

    vehicle = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    owner = get_primary_vehicle_owner(db, vehicle)
    owner_id = int(owner.id) if owner else None

    admin_customer = get_customer_by_email(db, admin_email.strip().lower())
    admin_id = int(admin_customer.id) if admin_customer else None

    if owner and not admin_change_table_exists(db):
        raise HTTPException(
            status_code=503,
            detail="Historie změn z administrátora není k dispozici — spusťte migrace.",
        )

    tgt = payload.target_entity.strip().lower()
    field = payload.field.strip()

    prev_raw: Any = None
    new_raw: Any = None

    if tgt == "vehicle":
        if field not in VEHICLE_CORRECTABLE_FIELDS:
            raise HTTPException(status_code=400, detail="Pole není povoleno pro úpravu")
        prev_raw = _vehicle_field_current_raw(vehicle, field)
        expected = _norm_client_value(payload.old_value)
        actual = _serialize_value_for_compare("vehicle", field, prev_raw)
        if expected != actual:
            raise HTTPException(
                status_code=409,
                detail="Hodnota v databázi se neshoduje s očekáváním — obnovte náhled a zkuste znovu.",
            )
        coerced = _coerce_vehicle_value(field, _norm_client_value(payload.new_value))
        setattr(vehicle, field, coerced)
        new_raw = coerced
        db.flush()

    elif tgt == "service_record":
        if field not in SERVICE_RECORD_CORRECTABLE:
            raise HTTPException(status_code=400, detail="Pole servisního záznamu není povoleno")
        rid = int(payload.target_id or 0)
        if rid <= 0:
            raise HTTPException(status_code=400, detail="target_id je povinné pro service_record")
        rec = (
            db.query(ServiceRecord)
            .filter(
                ServiceRecord.id == rid,
                ServiceRecord.vehicle_id == int(vehicle_id),
                ServiceRecord.is_deleted.is_(False),
            )
            .first()
        )
        if not rec:
            raise HTTPException(status_code=404, detail="Servisní záznam nenalezen")
        prev_raw = getattr(rec, field)
        expected = _norm_client_value(payload.old_value)
        actual = _serialize_value_for_compare("service_record", field, prev_raw)
        if expected != actual:
            raise HTTPException(status_code=409, detail="Hodnota v DB se neshoduje s očekáváním")
        coerced = _coerce_service_record_value(field, _norm_client_value(payload.new_value))
        setattr(rec, field, coerced)
        new_raw = coerced
        db.flush()

    elif tgt == "reminder":
        if owner_id is None:
            raise HTTPException(
                status_code=400,
                detail="Nelze měnit připomínku — vozidlo nemá určeného primárního vlastníka.",
            )
        if field not in REMINDER_CORRECTABLE:
            raise HTTPException(status_code=400, detail="Pole připomínky není povoleno")
        rid = int(payload.target_id or 0)
        if rid <= 0:
            raise HTTPException(status_code=400, detail="target_id je povinné pro reminder")
        rem = (
            db.query(Reminder)
            .filter(
                Reminder.id == rid,
                Reminder.vehicle_id == int(vehicle_id),
            )
            .first()
        )
        if not rem:
            raise HTTPException(status_code=404, detail="Připomínka nenalezena")
        if owner_id is not None and int(rem.customer_id) != int(owner_id):
            # Omezíme úpravu na připomínky primárního vlastníka vozidla (GDPR / scope).
            raise HTTPException(status_code=403, detail="Připomínka nepatří primárnímu vlastníku vozidla")
        prev_raw = getattr(rem, field)
        expected = _norm_client_value(payload.old_value)
        actual = _serialize_value_for_compare("reminder", field, prev_raw)
        if expected != actual:
            raise HTTPException(status_code=409, detail="Hodnota v DB se neshoduje s očekáváním")
        coerced = _coerce_reminder_value(field, _norm_client_value(payload.new_value))
        setattr(rem, field, coerced)
        new_raw = coerced
        db.flush()
    else:
        raise HTTPException(
            status_code=400,
            detail="Nepodporovaný target_entity (aktuálně: vehicle, service_record, reminder)",
        )

    summary_line = f"Administrátorská oprava: {tgt}.{field} (vozidlo #{vehicle_id})"
    detail_text = (
        f"Důvod: {reason}\n"
        f"Dříve: {_serialize_value_for_compare(tgt, field, prev_raw) or '—'}\n"
        f"Nově: {_serialize_value_for_compare(tgt, field, new_raw) or '—'}"
    )

    notify_event_rows: List[AdminCustomerChangeEvent] = []
    if owner:
        event_id = record_admin_customer_change(
            db,
            customer_id=int(owner.id),
            admin_email=admin_email,
            change_key=f"vehicle.support.{tgt}.{field}",
            summary_line=summary_line[:4000],
            detail_text=detail_text,
            payload={
                "vehicle_id": int(vehicle_id),
                "target_entity": tgt,
                "target_id": payload.target_id,
                "field": field,
                "notify_user_requested": bool(payload.notify_user),
            },
        )
        if event_id:
            row_ev = db.get(AdminCustomerChangeEvent, int(event_id))
            if row_ev:
                notify_event_rows = [row_ev]

    notification_status = "skipped"
    if payload.notify_user:
        if not owner or not (owner.email or "").strip():
            notification_status = "failed"
        elif not notify_event_rows:
            notification_status = "failed"
        else:
            try:
                send_customer_change_notification_email(
                    to_email=str(owner.email).strip().lower(),
                    user_name=owner.name,
                    admin_email=admin_email,
                    lines=[
                        summary_line,
                        f"Důvod administrátora: {reason}",
                        f"Původní hodnota: {_serialize_value_for_compare(tgt, field, prev_raw) or '—'}",
                        f"Nová hodnota: {_serialize_value_for_compare(tgt, field, new_raw) or '—'}",
                    ],
                )
                mark_events_notified(
                    db,
                    rows=notify_event_rows,
                    to_email=str(owner.email).strip().lower(),
                )
                notification_status = "sent"
            except Exception:
                notification_status = "failed"

    _append_developer_audit(
        db,
        admin_email=admin_email,
        request=request,
        action_type="admin_vehicle_correction_applied",
        target_resource=f"vehicle:{vehicle_id}",
        parameters={
            "admin_id": admin_id,
            "vehicle_id": int(vehicle_id),
            "vin": vehicle.vin,
            "tenant_id": int(vehicle.tenant_id) if vehicle.tenant_id is not None else None,
            "owner_user_id": owner_id,
            "target_entity": tgt,
            "target_id": payload.target_id,
            "field": field,
            "previous_value": _serialize_value_for_compare(tgt, field, prev_raw),
            "new_value": _serialize_value_for_compare(tgt, field, new_raw),
            "reason": reason,
            "notification_status": notification_status,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    )

    warnings: List[Dict[str, str]] = []
    if notification_status == "failed":
        warnings.append(
            {
                "code": "email_failed",
                "message": "Změna byla uložena, ale e-mailové oznámení se nepodařilo odeslat (viz audit).",
            }
        )

    return {
        "ok": True,
        "notification_status": notification_status,
        "previous_value": _serialize_value_for_compare(tgt, field, prev_raw),
        "new_value": _serialize_value_for_compare(tgt, field, new_raw),
        "warnings": warnings,
    }
