"""Work order line items (labor, parts, time) and service record creation from completed orders."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit_log import write_global_audit_log
from ..central_vehicle_identity import active_owner_assignment, vehicle_state
from ..database import get_db
from ..models import (
    Customer,
    ServiceRecord as ServiceRecordModel,
    ServiceWorkOrder,
    ServiceWorkOrderItem,
)
from ..ownership import get_primary_vehicle_owner
from ..schema_management import assert_module_ready
from ..service_record_snapshot import service_record_audit_snapshot as _service_record_snapshot
from .auth import get_current_user
from ..service_access import require_service_vehicle_link
from .service_workspace import _require_service_workspace_role

WORK_ORDER_ITEM_LABOR = "labor"
WORK_ORDER_ITEM_PART = "part"
WORK_ORDER_ITEM_TIME = "time"

_DATE_NOTE_RE = re.compile(r"^\[date:(\d{4}-\d{2}-\d{2})\]\s*", re.IGNORECASE)


class ServiceWorkOrderLaborCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=512)
    description: Optional[str] = Field(default=None, max_length=4000)
    hours: float = Field(default=1, gt=0, le=999)
    unit_price_without_vat: Optional[float] = Field(default=None, ge=0)


class ServiceWorkOrderPartCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=512)
    quantity: float = Field(default=1, gt=0, le=99999)
    unit: str = Field(default="ks", min_length=1, max_length=32)
    note: Optional[str] = Field(default=None, max_length=2000)
    unit_price_without_vat: Optional[float] = Field(default=None, ge=0)


class ServiceWorkOrderTimeCreateRequest(BaseModel):
    technician_id: Optional[int] = Field(default=None, gt=0)
    minutes: int = Field(..., gt=0, le=24 * 60 * 30)
    note: Optional[str] = Field(default=None, max_length=2000)
    worked_date: Optional[date] = None


class ServiceWorkOrderCreateRecordRequest(BaseModel):
    mileage: Optional[int] = Field(default=None, ge=0)
    performed_at: Optional[datetime] = None


def add_work_order_labor(
    work_order_id: int,
    payload: ServiceWorkOrderLaborCreateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from . import service_dashboard as sd

    sd._require_service_workspace_role(current_user)
    sd._ensure_service_dashboard_schema(db)
    order = sd._get_work_order_or_404(db, current_user=current_user, work_order_id=work_order_id)
    item = _create_work_order_item(
        db,
        order=order,
        actor=current_user,
        item_type=WORK_ORDER_ITEM_LABOR,
        name=str(payload.name).strip(),
        quantity=float(payload.hours),
        unit="h",
        note=(str(payload.description or "").strip() or None),
        sale_price_without_vat=float(payload.unit_price_without_vat or 0),
    )
    sd._write_work_order_audit(
        db,
        work_order=order,
        action="item_labor_added",
        actor=current_user,
        previous_snapshot=sd._work_order_snapshot(order),
        new_snapshot=sd._work_order_snapshot(order),
    )
    db.commit()
    db.refresh(item)
    return _serialize_item_for_service(item)


def add_work_order_part(
    work_order_id: int,
    payload: ServiceWorkOrderPartCreateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from . import service_dashboard as sd

    sd._require_service_workspace_role(current_user)
    sd._ensure_service_dashboard_schema(db)
    order = sd._get_work_order_or_404(db, current_user=current_user, work_order_id=work_order_id)
    item = _create_work_order_item(
        db,
        order=order,
        actor=current_user,
        item_type=WORK_ORDER_ITEM_PART,
        name=str(payload.name).strip(),
        quantity=float(payload.quantity),
        unit=str(payload.unit or "ks").strip() or "ks",
        note=(str(payload.note or "").strip() or None),
        sale_price_without_vat=float(payload.unit_price_without_vat or 0),
    )
    sd._write_work_order_audit(
        db,
        work_order=order,
        action="item_part_added",
        actor=current_user,
        previous_snapshot=sd._work_order_snapshot(order),
        new_snapshot=sd._work_order_snapshot(order),
    )
    db.commit()
    db.refresh(item)
    return _serialize_item_for_service(item)


def add_work_order_time(
    work_order_id: int,
    payload: ServiceWorkOrderTimeCreateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from . import service_dashboard as sd

    sd._require_service_workspace_role(current_user)
    sd._ensure_service_dashboard_schema(db)
    order = sd._get_work_order_or_404(db, current_user=current_user, work_order_id=work_order_id)
    mechanic_id = sd._resolve_technician_id(db, current_user=current_user, technician_id=payload.technician_id)
    note_parts: list[str] = []
    if payload.worked_date:
        note_parts.append(f"[date:{payload.worked_date.isoformat()}]")
    if payload.note and str(payload.note).strip():
        note_parts.append(str(payload.note).strip())
    note = " ".join(note_parts).strip() or None
    technician = db.query(Customer).filter(Customer.id == mechanic_id).first()
    tech_label = (
        getattr(technician, "name", None) or getattr(technician, "email", None) or f"Technik #{mechanic_id}"
    ).strip()
    item = _create_work_order_item(
        db,
        order=order,
        actor=current_user,
        item_type=WORK_ORDER_ITEM_TIME,
        name=f"Čas — {tech_label}",
        quantity=float(payload.minutes),
        unit="min",
        note=note,
        mechanic_id=mechanic_id,
        sale_price_without_vat=0,
    )
    sd._write_work_order_audit(
        db,
        work_order=order,
        action="item_time_added",
        actor=current_user,
        previous_snapshot=sd._work_order_snapshot(order),
        new_snapshot=sd._work_order_snapshot(order),
    )
    db.commit()
    db.refresh(item)
    return _serialize_item_for_service(item)


def complete_work_order(
    work_order_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from . import service_dashboard as sd

    sd._require_service_workspace_role(current_user)
    sd._ensure_service_dashboard_schema(db)
    order = sd._get_work_order_or_404(db, current_user=current_user, work_order_id=work_order_id)
    previous_snapshot = sd._work_order_snapshot(order)
    order.status = "completed"
    order.completed_at = datetime.utcnow()
    db.flush()
    sd._write_work_order_audit(
        db,
        work_order=order,
        action="completed",
        actor=current_user,
        previous_snapshot=previous_snapshot,
        new_snapshot=sd._work_order_snapshot(order),
    )
    db.commit()
    db.refresh(order)
    owner, vehicle, technician = sd._load_work_order_parties(db, order)
    return sd._serialize_work_order(order, owner=owner, vehicle=vehicle, technician=technician)


def create_service_record_from_work_order(
    work_order_id: int,
    payload: ServiceWorkOrderCreateRecordRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from . import service_dashboard as sd

    sd._require_service_workspace_role(current_user)
    sd._ensure_service_dashboard_schema(db)
    assert_module_ready(db, "service_records", detail_prefix="Servisní historie není připravena")
    order = sd._get_work_order_or_404(db, current_user=current_user, work_order_id=work_order_id)
    if str(order.status or "").lower() != "completed":
        raise HTTPException(status_code=422, detail="Servisní záznam lze vytvořit jen z dokončené zakázky.")

    existing = (
        db.query(ServiceRecordModel.id)
        .filter(
            ServiceRecordModel.work_order_id == int(order.id),
            ServiceRecordModel.is_deleted.is_(False),
            ServiceRecordModel.service_id == int(current_user.id),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Z této zakázky už existuje servisní záznam.")

    record = _build_service_record_from_work_order(
        db,
        order=order,
        actor=current_user,
        mileage=payload.mileage,
        performed_at=payload.performed_at,
    )
    sd._write_work_order_audit(
        db,
        work_order=order,
        action="service_record_created",
        actor=current_user,
        previous_snapshot=sd._work_order_snapshot(order),
        new_snapshot=sd._work_order_snapshot(order),
    )
    db.commit()
    db.refresh(record)
    return {
        "service_record_id": int(record.id),
        "vehicle_id": int(record.vehicle_id),
        "work_order_id": int(order.id),
        "visibility_scope": str(record.visibility_scope or ""),
        "record_status": str(record.record_status or ""),
    }


def register_work_order_item_routes(router: APIRouter) -> None:
    """Attach work-order item routes to the service dashboard router."""
    router.add_api_route("/work-orders/{work_order_id}/labor", add_work_order_labor, methods=["POST"])
    router.add_api_route("/work-orders/{work_order_id}/parts", add_work_order_part, methods=["POST"])
    router.add_api_route("/work-orders/{work_order_id}/time", add_work_order_time, methods=["POST"])
    router.add_api_route("/work-orders/{work_order_id}/complete", complete_work_order, methods=["POST"])
    router.add_api_route(
        "/work-orders/{work_order_id}/service-record",
        create_service_record_from_work_order,
        methods=["POST"],
    )


def _active_items_query(db: Session, *, work_order_id: int):
    return (
        db.query(ServiceWorkOrderItem)
        .filter(
            ServiceWorkOrderItem.work_order_id == int(work_order_id),
            ServiceWorkOrderItem.deleted_at.is_(None),
        )
        .order_by(ServiceWorkOrderItem.id.asc())
    )


_ITEM_TYPE_GROUP_KEYS = {
    WORK_ORDER_ITEM_LABOR: "labor",
    WORK_ORDER_ITEM_PART: "parts",
    WORK_ORDER_ITEM_TIME: "time",
}


def list_work_order_items_grouped(db: Session, *, work_order_id: int) -> dict[str, list[dict[str, object]]]:
    rows = _active_items_query(db, work_order_id=work_order_id).all()
    grouped: dict[str, list[dict[str, object]]] = {
        "labor": [],
        "parts": [],
        "time": [],
    }
    for row in rows:
        item_type = str(row.item_type or "").lower()
        group_key = _ITEM_TYPE_GROUP_KEYS.get(item_type)
        if not group_key:
            continue
        grouped[group_key].append(_serialize_item_for_service(row))
    return grouped


def work_order_capabilities(*, order: ServiceWorkOrder) -> dict[str, bool]:
    return {
        "labor": True,
        "parts": True,
        "time": True,
        "photos": True,
        "quotes": True,
        "invoices": True,
        "invoice_pdf": True,
        "complete": str(order.status or "").lower() != "completed",
        "create_service_record": str(order.status or "").lower() == "completed",
    }


def work_order_limited_notices() -> dict[str, str]:
    return {
        "photos": "Interní fotky a doklady nejsou viditelné pro majitele.",
        "billing": "Ceny a faktury jsou pouze pro servis — majitel je v historii nevidí.",
    }


def _create_work_order_item(
    db: Session,
    *,
    order: ServiceWorkOrder,
    actor: Customer,
    item_type: str,
    name: str,
    quantity: float,
    unit: str,
    note: Optional[str],
    sale_price_without_vat: float = 0,
    mechanic_id: Optional[int] = None,
) -> ServiceWorkOrderItem:
    item = ServiceWorkOrderItem(
        tenant_id=int(order.tenant_id),
        work_order_id=int(order.id),
        service_customer_id=int(order.service_customer_id),
        vehicle_id=int(order.vehicle_id),
        item_type=str(item_type),
        name=name,
        quantity=float(quantity),
        unit=unit,
        note=note,
        sale_price_without_vat=float(sale_price_without_vat or 0),
        mechanic_id=mechanic_id,
        created_by=int(actor.id),
        source="manual",
    )
    db.add(item)
    db.flush()
    write_global_audit_log(
        db,
        entity_type="service_work_order_item",
        entity_id=int(item.id),
        action="create",
        actor_user_id=int(actor.id),
        actor_role=getattr(actor, "role", None),
        tenant_id=int(order.tenant_id),
        vehicle_id=int(order.vehicle_id),
        metadata={
            "work_order_id": int(order.id),
            "item_type": item_type,
            "name": name,
        },
    )
    return item


def _serialize_item_for_service(item: ServiceWorkOrderItem) -> dict[str, object]:
    worked_date = _extract_worked_date(item.note)
    return {
        "id": int(item.id),
        "item_type": str(item.item_type),
        "name": str(item.name),
        "quantity": float(item.quantity or 0),
        "unit": str(item.unit or ""),
        "note": _strip_date_prefix(item.note),
        "mechanic_id": int(item.mechanic_id) if item.mechanic_id else None,
        "worked_date": worked_date,
        "unit_price_without_vat": float(item.sale_price_without_vat or 0),
        "line_total_without_vat": round(float(item.quantity or 0) * float(item.sale_price_without_vat or 0), 2),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def serialize_item_owner_safe(item: ServiceWorkOrderItem) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": str(item.name),
        "quantity": float(item.quantity or 0),
        "unit": str(item.unit or ""),
    }
    note = _strip_date_prefix(item.note)
    if note:
        payload["note"] = note
    return payload


def _extract_worked_date(note: Optional[str]) -> Optional[str]:
    if not note:
        return None
    match = _DATE_NOTE_RE.match(str(note))
    if match:
        return match.group(1)
    return None


def _strip_date_prefix(note: Optional[str]) -> Optional[str]:
    if not note:
        return None
    stripped = _DATE_NOTE_RE.sub("", str(note)).strip()
    return stripped or None


def _build_owner_visible_text(items: dict[str, list[ServiceWorkOrderItem]]) -> str:
    lines: list[str] = []
    labor_rows = items.get("labor") or []
    if labor_rows:
        lines.append("Úkony:")
        for row in labor_rows:
            qty = float(row.quantity or 0)
            unit = str(row.unit or "h")
            suffix = f" ({qty:g} {unit})" if qty else ""
            note = _strip_date_prefix(row.note)
            detail = f" — {note}" if note else ""
            lines.append(f"- {row.name}{suffix}{detail}")
    part_rows = items.get("parts") or []
    if part_rows:
        lines.append("Díly:")
        for row in part_rows:
            lines.append(
                f"- {row.name}: {float(row.quantity or 0):g} {str(row.unit or 'ks')}"
            )
    time_rows = items.get("time") or []
    if time_rows:
        total_min = sum(int(float(row.quantity or 0)) for row in time_rows)
        lines.append(f"Evidovaný čas práce: {total_min} min")
    return "\n".join(lines).strip()


def _build_service_record_from_work_order(
    db: Session,
    *,
    order: ServiceWorkOrder,
    actor: Customer,
    mileage: Optional[int],
    performed_at: Optional[datetime],
) -> ServiceRecordModel:
    from ..models import Vehicle as VehicleModel

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(order.vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo zakázky nebylo nalezeno.")

    rows = _active_items_query(db, work_order_id=int(order.id)).all()
    grouped_rows: dict[str, list[ServiceWorkOrderItem]] = {
        "labor": [],
        "parts": [],
        "time": [],
    }
    for row in rows:
        key = _ITEM_TYPE_GROUP_KEYS.get(str(row.item_type or "").lower())
        if key:
            grouped_rows[key].append(row)

    owner_customer = None
    if order.owner_customer_id is not None:
        owner_customer = db.query(Customer).filter(Customer.id == int(order.owner_customer_id)).first()
    service_owns_unassigned = (
        order.owner_customer_id is None
        and active_owner_assignment(db, int(vehicle.id)) is None
        and vehicle_state(db, vehicle) == "service_provisioned_unowned"
        and int(getattr(vehicle, "provisioned_by_service_customer_id", 0) or 0) == int(actor.id)
    )
    if order.owner_customer_id is not None and owner_customer:
        require_service_vehicle_link(
            db,
            current_user=actor,
            vehicle_id=int(vehicle.id),
            require_create_record=True,
        )
    elif not service_owns_unassigned and order.owner_customer_id is None:
        raise HTTPException(status_code=403, detail="Servis nemá oprávnění vytvořit záznam pro tuto zakázku.")

    owner_safe_parts = [serialize_item_owner_safe(row) for row in grouped_rows["parts"]]
    notes_customer_visible = _build_owner_visible_text(
        {
            WORK_ORDER_ITEM_LABOR: grouped_rows["labor"],
            WORK_ORDER_ITEM_PART: grouped_rows["parts"],
            WORK_ORDER_ITEM_TIME: grouped_rows["time"],
        }
    )
    if not notes_customer_visible:
        notes_customer_visible = (str(order.description or "").strip() or str(order.title or "").strip() or "Servisní úkon")

    internal_lines: list[str] = [str(order.title or "Zakázka")]
    if order.description:
        internal_lines.append(str(order.description))
    for row in rows:
        price = float(row.sale_price_without_vat or 0) * float(row.quantity or 0)
        if price > 0:
            internal_lines.append(f"{row.name}: {price:.2f} Kč (interní)")

    total_internal = sum(
        float(row.sale_price_without_vat or 0) * float(row.quantity or 0) for row in rows
    )
    labor_seconds = sum(int(float(row.quantity or 0) * 60) for row in grouped_rows["time"])

    visibility_scope = (
        "safe_history_after_claim" if service_owns_unassigned else "owner_visible_no_prices"
    )

    record = ServiceRecordModel(
        tenant_id=int(order.tenant_id),
        vehicle_id=int(order.vehicle_id),
        user_id=int(actor.id),
        customer_id=int(owner_customer.id) if owner_customer else None,
        service_id=int(actor.id),
        work_order_id=int(order.id),
        performed_at=performed_at or order.completed_at or datetime.utcnow(),
        mileage=mileage,
        description="\n".join(internal_lines).strip(),
        notes_customer_visible=notes_customer_visible,
        note=None,
        category="Servisní zakázka",
        service_type="work_order",
        record_status="published",
        visibility_scope=visibility_scope,
        total_price=total_internal if total_internal > 0 else None,
        price=total_internal if total_internal > 0 else None,
        labor_seconds=labor_seconds or None,
        origin="service_work_order",
        created_by_service_customer_id=int(actor.id),
        attachments=json.dumps(
            {"owner_safe_parts": owner_safe_parts, "work_order_id": int(order.id)},
            ensure_ascii=False,
        ),
    )
    if service_owns_unassigned:
        record.created_by_service_customer_id = int(actor.id)

    db.add(record)
    db.flush()
    snapshot = _service_record_snapshot(record)
    from ..service_record_snapshot import snapshot_json_and_hash

    _, snapshot_hash = snapshot_json_and_hash(snapshot)
    record.snapshot_hash = snapshot_hash

    write_global_audit_log(
        db,
        entity_type="service_record",
        entity_id=int(record.id),
        action="service_record_create_from_work_order",
        actor_user_id=int(actor.id),
        actor_role=getattr(actor, "role", None),
        tenant_id=int(order.tenant_id),
        vehicle_id=int(vehicle.id),
        metadata={
            "work_order_id": int(order.id),
            "visibility_scope": visibility_scope,
            "owner_safe_parts_count": len(owner_safe_parts),
        },
    )
    return record


def owner_safe_parts_from_record_attachments(raw: Optional[str]) -> list[dict[str, object]]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    parts = payload.get("owner_safe_parts")
    if not isinstance(parts, list):
        return []
    safe: list[dict[str, object]] = []
    for entry in parts:
        if not isinstance(entry, dict):
            continue
        safe.append(
            {
                "name": str(entry.get("name") or "").strip(),
                "quantity": entry.get("quantity"),
                "unit": str(entry.get("unit") or "").strip() or None,
            }
        )
    return [p for p in safe if p.get("name")]
