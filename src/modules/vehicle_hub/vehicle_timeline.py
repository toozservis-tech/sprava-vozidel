"""Unified vehicle timeline — server-side filtered projection (not a new event store)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from sqlalchemy.orm import Session

from .audit_log import write_global_audit_log
from .central_vehicle_identity import active_owner_assignment, vehicle_state
from .models import (
    Customer,
    Reminder,
    ServiceIntake,
    ServiceInvoice,
    ServiceQuote,
    ServiceRecord,
    ServiceWorkOrder,
    Vehicle,
    VehicleInspectionHistory,
    VehicleMileage,
    VehiclePhotoAsset,
    VehicleReportDocument,
    VehicleTachometerHistoryEntry,
)

ViewerRole = Literal["owner", "service", "admin"]

OWNER_SAFE_RECORD_SCOPES = frozenset(
    {"safe_history_after_claim", "owner_visible_no_prices", "full_current_owner"}
)
OWNER_SAFE_PHOTO_SCOPES = frozenset({"owner_visible", "safe_after_claim"})
SERVICE_ONLY_EVENT_TYPES = frozenset({"quote_created", "invoice_created"})

WORK_ORDER_STATUS_LABELS = {
    "awaiting_client_approval": "Čeká na schválení",
    "approved": "Schváleno",
    "in_progress": "Rozpracováno",
    "issue": "Problém",
    "completed": "Dokončeno",
}

INTAKE_STATUS_LABELS = {
    "draft": "Koncept",
    "checked_in": "Přijato",
    "in_progress": "Probíhá",
    "completed": "Dokončeno",
    "cancelled": "Zrušeno",
}


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _sort_key(event: dict[str, Any]) -> tuple[str, int, str]:
    ts = str(event.get("timestamp") or "")
    sid = int(event.get("source_id") or 0)
    et = str(event.get("event_type") or "")
    return (ts, sid, et)


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, int]] = set()
    unique: list[dict[str, Any]] = []
    for event in events:
        key = (
            str(event.get("event_type") or ""),
            str(event.get("source_type") or ""),
            int(event.get("source_id") or 0),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    unique.sort(key=_sort_key, reverse=True)
    return unique


def service_can_view_vehicle_timeline(
    db: Session,
    *,
    current_user: Customer,
    vehicle: Vehicle,
) -> bool:
    from .service_access import get_active_vehicle_service_link, service_can_read_vehicle

    if service_can_read_vehicle(db, current_user, int(vehicle.id)):
        return True
    if active_owner_assignment(db, int(vehicle.id)) is not None:
        return False
    if vehicle_state(db, vehicle) != "service_provisioned_unowned":
        return False
    if int(getattr(vehicle, "provisioned_by_service_customer_id", 0) or 0) != int(current_user.id):
        return False
    provisioned_tenant = int(getattr(vehicle, "provisioned_by_service_tenant_id", 0) or 0)
    user_tenant = int(getattr(current_user, "tenant_id", 0) or 0)
    if provisioned_tenant and user_tenant and provisioned_tenant != user_tenant:
        return False
    vehicle_tenant = int(getattr(vehicle, "tenant_id", 0) or 0)
    if user_tenant and vehicle_tenant and vehicle_tenant != user_tenant:
        return False
    return True


def _base_event(
    *,
    event_type: str,
    timestamp: Optional[datetime],
    vehicle_id: int,
    source_type: str,
    source_id: int,
    title: str,
    summary: str,
    visibility_scope: str,
    actor_role: str,
    mileage: Optional[int] = None,
    photo_preview: Optional[dict[str, Any]] = None,
    work_order_status: Optional[str] = None,
    service_only: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event_type": event_type,
        "timestamp": _iso(timestamp),
        "vehicle_id": int(vehicle_id),
        "source_type": source_type,
        "source_id": int(source_id),
        "title": title,
        "summary": summary,
        "visibility_scope": visibility_scope,
        "actor_role": actor_role,
    }
    if mileage is not None:
        payload["mileage"] = int(mileage)
    if photo_preview:
        payload["photo_preview"] = photo_preview
    if work_order_status:
        payload["work_order_status"] = work_order_status
    if service_only:
        payload["service_only"] = service_only
    return payload


def _collect_service_records(
    db: Session,
    *,
    vehicle_id: int,
    viewer: ViewerRole,
) -> list[dict[str, Any]]:
    rows = (
        db.query(ServiceRecord)
        .filter(
            ServiceRecord.vehicle_id == int(vehicle_id),
            ServiceRecord.is_deleted.is_(False),
        )
        .order_by(ServiceRecord.performed_at.desc(), ServiceRecord.id.desc())
        .all()
    )
    events: list[dict[str, Any]] = []
    for row in rows:
        scope = str(getattr(row, "visibility_scope", "") or "full_current_owner")
        if viewer == "owner" and scope not in OWNER_SAFE_RECORD_SCOPES:
            continue
        ts = row.performed_at or row.updated_at or row.created_at if hasattr(row, "created_at") else row.performed_at
        summary = str(row.notes_customer_visible or row.description or "Servisní záznam").strip()
        if viewer != "owner" and row.note:
            pass  # internal notes never in summary for any view per spec
        events.append(
            _base_event(
                event_type="service_record_created",
                timestamp=ts,
                vehicle_id=vehicle_id,
                source_type="service_record",
                source_id=int(row.id),
                title="Servisní záznam",
                summary=summary[:500],
                visibility_scope=scope if viewer != "owner" else "owner_safe",
                actor_role="service",
                mileage=int(row.mileage) if row.mileage is not None else None,
            )
        )
    return events


def _collect_photos(
    db: Session,
    *,
    vehicle_id: int,
    viewer: ViewerRole,
    service_customer_id: Optional[int],
) -> list[dict[str, Any]]:
    query = db.query(VehiclePhotoAsset).filter(
        VehiclePhotoAsset.vehicle_id == int(vehicle_id),
        VehiclePhotoAsset.deleted_at.is_(None),
    )
    if viewer == "service" and service_customer_id:
        query = query.filter(
            (VehiclePhotoAsset.service_customer_id.is_(None))
            | (VehiclePhotoAsset.service_customer_id == int(service_customer_id))
        )
    rows = query.order_by(VehiclePhotoAsset.created_at.desc(), VehiclePhotoAsset.id.desc()).all()
    events: list[dict[str, Any]] = []
    for row in rows:
        scope = str(getattr(row, "visibility_scope", "") or "service_private")
        if scope == "internal_only":
            continue
        if viewer == "owner" and scope not in OWNER_SAFE_PHOTO_SCOPES:
            continue
        if viewer == "service" and scope == "service_private" and service_customer_id:
            if int(getattr(row, "service_customer_id", 0) or 0) not in {0, int(service_customer_id)}:
                continue
        photo_type = str(row.photo_kind or row.role or "photo")
        events.append(
            _base_event(
                event_type="photo_uploaded",
                timestamp=row.created_at,
                vehicle_id=vehicle_id,
                source_type="vehicle_photo",
                source_id=int(row.id),
                title="Fotodokumentace",
                summary=f"Nahrána fotka ({photo_type})",
                visibility_scope=scope,
                actor_role="service" if getattr(row, "service_customer_id", None) else "owner",
                photo_preview={
                    "photo_id": int(row.id),
                    "photo_type": photo_type,
                    "preview_url": f"/api/v1/vehicles/{int(vehicle_id)}/photos/{int(row.id)}/file",
                },
            )
        )
    return events


def _collect_work_orders(
    db: Session,
    *,
    vehicle_id: int,
    service_customer_id: int,
) -> list[dict[str, Any]]:
    rows = (
        db.query(ServiceWorkOrder)
        .filter(
            ServiceWorkOrder.vehicle_id == int(vehicle_id),
            ServiceWorkOrder.service_customer_id == int(service_customer_id),
        )
        .order_by(ServiceWorkOrder.created_at.desc(), ServiceWorkOrder.id.desc())
        .all()
    )
    events: list[dict[str, Any]] = []
    for row in rows:
        status = str(row.status or "awaiting_client_approval")
        events.append(
            _base_event(
                event_type="work_order_created",
                timestamp=row.created_at,
                vehicle_id=vehicle_id,
                source_type="work_order",
                source_id=int(row.id),
                title="Servisní zakázka",
                summary=str(row.title or "Zakázka založena")[:500],
                visibility_scope="service_private",
                actor_role="service",
                work_order_status=status,
                service_only={"work_order_status_label": WORK_ORDER_STATUS_LABELS.get(status, status)},
            )
        )
        if status == "completed" and row.completed_at:
            events.append(
                _base_event(
                    event_type="work_order_completed",
                    timestamp=row.completed_at,
                    vehicle_id=vehicle_id,
                    source_type="work_order",
                    source_id=int(row.id),
                    title="Zakázka dokončena",
                    summary=str(row.title or "Servisní zakázka dokončena")[:500],
                    visibility_scope="service_private",
                    actor_role="service",
                    work_order_status=status,
                    service_only={"work_order_status_label": WORK_ORDER_STATUS_LABELS.get(status, status)},
                )
            )
    return events


def _collect_intakes(
    db: Session,
    *,
    vehicle_id: int,
    service_customer_id: int,
) -> list[dict[str, Any]]:
    rows = (
        db.query(ServiceIntake)
        .filter(
            ServiceIntake.vehicle_id == int(vehicle_id),
            ServiceIntake.service_id == int(service_customer_id),
        )
        .order_by(ServiceIntake.created_at.desc(), ServiceIntake.id.desc())
        .all()
    )
    events: list[dict[str, Any]] = []
    for row in rows:
        status = str(row.intake_status or "draft")
        summary = str(row.visible_to_owner_note or row.customer_request or "Příjem vozidla")[:500]
        events.append(
            _base_event(
                event_type="intake_created",
                timestamp=row.check_in_at or row.created_at,
                vehicle_id=vehicle_id,
                source_type="service_intake",
                source_id=int(row.id),
                title="Příjem vozidla",
                summary=summary,
                visibility_scope="service_private",
                actor_role="service",
                mileage=int(row.odometer_km) if row.odometer_km is not None else None,
                service_only={"intake_status_label": INTAKE_STATUS_LABELS.get(status, status)},
            )
        )
    return events


def _collect_quotes(
    db: Session,
    *,
    vehicle_id: int,
    service_customer_id: int,
) -> list[dict[str, Any]]:
    rows = (
        db.query(ServiceQuote)
        .filter(
            ServiceQuote.vehicle_id == int(vehicle_id),
            ServiceQuote.service_id == int(service_customer_id),
        )
        .order_by(ServiceQuote.created_at.desc(), ServiceQuote.id.desc())
        .all()
    )
    return [
        _base_event(
            event_type="quote_created",
            timestamp=row.created_at,
            vehicle_id=vehicle_id,
            source_type="service_quote",
            source_id=int(row.id),
            title="Nabídka vytvořena",
            summary=f"Stav nabídky: {str(row.status or 'draft')}",
            visibility_scope="service_private",
            actor_role="service",
            service_only={"quote_status": str(row.status or "draft")},
        )
        for row in rows
    ]


def _collect_invoices(
    db: Session,
    *,
    vehicle_id: int,
    service_customer_id: int,
) -> list[dict[str, Any]]:
    rows = (
        db.query(ServiceInvoice)
        .filter(
            ServiceInvoice.vehicle_id == int(vehicle_id),
            ServiceInvoice.service_id == int(service_customer_id),
        )
        .order_by(ServiceInvoice.created_at.desc(), ServiceInvoice.id.desc())
        .all()
    )
    return [
        _base_event(
            event_type="invoice_created",
            timestamp=row.issued_at or row.created_at,
            vehicle_id=vehicle_id,
            source_type="service_invoice",
            source_id=int(row.id),
            title="Faktura vytvořena",
            summary=f"Stav faktury: {str(row.status or 'draft')}",
            visibility_scope="service_private",
            actor_role="service",
            service_only={
                "invoice_status": str(row.status or "draft"),
                "invoice_number": row.invoice_number,
            },
        )
        for row in rows
    ]


def _collect_reminders(
    db: Session,
    *,
    vehicle_id: int,
    owner_customer_id: Optional[int],
) -> list[dict[str, Any]]:
    query = db.query(Reminder).filter(Reminder.vehicle_id == int(vehicle_id))
    if owner_customer_id:
        query = query.filter(Reminder.customer_id == int(owner_customer_id))
    rows = query.order_by(Reminder.created_at.desc(), Reminder.id.desc()).all()
    events: list[dict[str, Any]] = []
    for row in rows:
        events.append(
            _base_event(
                event_type="reminder_created",
                timestamp=row.created_at,
                vehicle_id=vehicle_id,
                source_type="reminder",
                source_id=int(row.id),
                title="Připomínka",
                summary=str(row.text or row.type or "Připomínka")[:500],
                visibility_scope="owner_visible_no_prices",
                actor_role="owner",
            )
        )
        if row.is_completed:
            events.append(
                _base_event(
                    event_type="reminder_completed",
                    timestamp=row.created_at,
                    vehicle_id=vehicle_id,
                    source_type="reminder",
                    source_id=int(row.id),
                    title="Připomínka splněna",
                    summary=str(row.text or row.type or "Připomínka")[:500],
                    visibility_scope="owner_visible_no_prices",
                    actor_role="owner",
                )
            )
    return events


def _collect_mileage(
    db: Session,
    *,
    vehicle_id: int,
) -> list[dict[str, Any]]:
    rows = (
        db.query(VehicleMileage)
        .filter(VehicleMileage.vehicle_id == int(vehicle_id))
        .order_by(VehicleMileage.created_at.desc(), VehicleMileage.id.desc())
        .all()
    )
    return [
        _base_event(
            event_type="mileage_recorded",
            timestamp=row.created_at,
            vehicle_id=vehicle_id,
            source_type="vehicle_mileage",
            source_id=int(row.id),
            title="Záznam tachometru",
            summary=f"Stav km: {int(row.mileage_km)}",
            visibility_scope="owner_visible_no_prices",
            actor_role="owner",
            mileage=int(row.mileage_km),
        )
        for row in rows
    ]


def _collect_stk(
    db: Session,
    *,
    vehicle_id: int,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    inspections = (
        db.query(VehicleInspectionHistory)
        .filter(VehicleInspectionHistory.vehicle_id == int(vehicle_id))
        .order_by(VehicleInspectionHistory.inspection_date.desc(), VehicleInspectionHistory.id.desc())
        .all()
    )
    for row in inspections:
        events.append(
            _base_event(
                event_type="stk_recorded",
                timestamp=row.inspection_date or row.imported_at,
                vehicle_id=vehicle_id,
                source_type="vehicle_inspection",
                source_id=int(row.id),
                title="STK / kontrola",
                summary=str(row.result_label or row.inspection_type or "Kontrola vozidla")[:500],
                visibility_scope="owner_visible_no_prices",
                actor_role="system",
                mileage=int(row.odometer_km) if row.odometer_km is not None else None,
            )
        )
    tach_rows = (
        db.query(VehicleTachometerHistoryEntry)
        .filter(VehicleTachometerHistoryEntry.vehicle_id == int(vehicle_id))
        .order_by(VehicleTachometerHistoryEntry.check_date.desc(), VehicleTachometerHistoryEntry.id.desc())
        .all()
    )
    for row in tach_rows:
        events.append(
            _base_event(
                event_type="stk_recorded",
                timestamp=row.check_date or row.imported_at,
                vehicle_id=vehicle_id,
                source_type="tachometer_history",
                source_id=int(row.id),
                title="Import STK / tachometr",
                summary=str(row.summary or row.inspection_type or "Kontrola tachometru")[:500],
                visibility_scope="owner_visible_no_prices",
                actor_role="system",
                mileage=int(row.mileage_km) if row.mileage_km is not None else None,
            )
        )
    return events


def _collect_documents(
    db: Session,
    *,
    vehicle_id: int,
    viewer: ViewerRole,
) -> list[dict[str, Any]]:
    if viewer == "owner":
        return []
    rows = (
        db.query(VehicleReportDocument)
        .filter(
            VehicleReportDocument.vehicle_id == int(vehicle_id),
            VehicleReportDocument.status == "valid",
        )
        .order_by(VehicleReportDocument.finalized_at.desc(), VehicleReportDocument.id.desc())
        .all()
    )
    return [
        _base_event(
            event_type="document_added",
            timestamp=row.finalized_at or row.created_at,
            vehicle_id=vehicle_id,
            source_type="vehicle_report_document",
            source_id=int(row.id),
            title="Servisní dokument",
            summary=str(row.document_type or "PDF výpis")[:500],
            visibility_scope="service_private",
            actor_role="service",
            service_only={"document_type": str(row.document_type or "")},
        )
        for row in rows
    ]


def _strip_service_only_for_owner(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for event in events:
        if str(event.get("event_type") or "") in SERVICE_ONLY_EVENT_TYPES:
            continue
        copy = dict(event)
        copy.pop("service_only", None)
        cleaned.append(copy)
    return cleaned


def build_vehicle_timeline(
    db: Session,
    *,
    vehicle: Vehicle,
    viewer: ViewerRole,
    current_user: Customer,
    limit: int = 200,
) -> dict[str, Any]:
    vehicle_id = int(vehicle.id)
    service_customer_id = int(current_user.id) if viewer in {"service", "admin"} else None
    owner_customer_id = int(current_user.id) if viewer == "owner" else None

    events: list[dict[str, Any]] = []
    events.extend(_collect_service_records(db, vehicle_id=vehicle_id, viewer=viewer))
    events.extend(_collect_photos(db, vehicle_id=vehicle_id, viewer=viewer, service_customer_id=service_customer_id))
    events.extend(_collect_mileage(db, vehicle_id=vehicle_id))
    events.extend(_collect_stk(db, vehicle_id=vehicle_id))

    if owner_customer_id:
        events.extend(_collect_reminders(db, vehicle_id=vehicle_id, owner_customer_id=owner_customer_id))
    elif viewer in {"service", "admin"} and service_customer_id:
        events.extend(_collect_reminders(db, vehicle_id=vehicle_id, owner_customer_id=None))

    if viewer in {"service", "admin"} and service_customer_id:
        events.extend(_collect_work_orders(db, vehicle_id=vehicle_id, service_customer_id=service_customer_id))
        events.extend(_collect_intakes(db, vehicle_id=vehicle_id, service_customer_id=service_customer_id))
        events.extend(_collect_quotes(db, vehicle_id=vehicle_id, service_customer_id=service_customer_id))
        events.extend(_collect_invoices(db, vehicle_id=vehicle_id, service_customer_id=service_customer_id))
        events.extend(_collect_documents(db, vehicle_id=vehicle_id, viewer=viewer))

    events = _dedupe_events(events)
    if viewer == "owner":
        events = _strip_service_only_for_owner(events)

    events = events[: max(1, min(int(limit), 500))]

    audit_action = "owner_timeline_viewed" if viewer == "owner" else "service_timeline_viewed"
    write_global_audit_log(
        db,
        entity_type="vehicle_timeline",
        entity_id=vehicle_id,
        action=audit_action,
        actor_user_id=int(current_user.id),
        actor_role=str(getattr(current_user, "role", None) or viewer),
        tenant_id=int(getattr(current_user, "tenant_id", 0) or 0) or None,
        vehicle_id=vehicle_id,
        metadata={"viewer": viewer, "event_count": len(events)},
    )
    db.flush()

    return {
        "vehicle_id": vehicle_id,
        "viewer": viewer,
        "count": len(events),
        "items": events,
    }
