from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, exists, func, or_
from sqlalchemy.orm import Session, aliased

from ..audit_log import write_global_audit_log
from ..central_vehicle_identity import active_owner_assignment, vehicle_state
from ..database import get_db
from ..mileage_reports import collect_vehicle_mileage_timeline_points, summarize_mileage_timeline
from ..models import (
    Customer,
    Reminder as ReminderModel,
    Reservation as ReservationModel,
    ServiceAccessRequest,
    ServiceCustomerLink,
    ServiceDocumentIngestion,
    ServiceInvoice,
    ServiceIntake,
    ServiceRecord as ServiceRecordModel,
    ServiceQuote,
    ServiceQuoteAuditLog,
    ServiceWorkOrder,
    ServiceWorkOrderAuditLog,
    Vehicle as VehicleModel,
    VehiclePhotoAsset,
    VehicleServiceLink,
)
from ..ownership import get_owned_vehicle, get_primary_vehicle_owner
from ..quote_public_access import build_public_quote_page_url, ensure_quote_access_token, get_active_quote_access_token
from ..reports.service_quote_pdf import render_service_quote_pdf
from ..schema_management import assert_module_ready
from .auth import get_current_user
from .service_workspace import _require_service_workspace_role


router = APIRouter(prefix="/api/service", tags=["service-dashboard"])

WORK_ORDER_STATUSES = {
    "awaiting_client_approval",
    "approved",
    "in_progress",
    "completed",
    "issue",
}
WORK_ORDER_STATUSES_IN_PROGRESS = {"in_progress", "approved"}
WORK_ORDER_STATUS_LABELS = {
    "awaiting_client_approval": "Čeká na schválení",
    "approved": "Schváleno",
    "in_progress": "Rozpracováno",
    "completed": "Dokončeno",
    "issue": "Problém",
}
WORK_ORDER_SOURCE_LABELS = {
    "manual": "Ruční zápis",
    "reservation": "Rezervace",
    "document": "Doklad",
    "intake": "Příjem",
}
QUOTE_STATUSES = {"draft", "sent", "approved", "rejected"}
QUOTE_STATUS_SORT_RANK = case(
    (ServiceQuote.status == "draft", 0),
    (ServiceQuote.status == "sent", 1),
    (ServiceQuote.status == "approved", 2),
    (ServiceQuote.status == "rejected", 3),
    else_=9,
)


class ServiceWorkOrderCreateRequest(BaseModel):
    owner_id: Optional[int] = Field(default=None, gt=0)
    vehicle_id: int = Field(gt=0)
    technician_id: Optional[int] = Field(default=None, gt=0)
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    due_date: Optional[date] = None
    source_type: str = Field(default="manual", max_length=32)
    source_reservation_id: Optional[int] = Field(default=None, gt=0)
    source_document_id: Optional[int] = Field(default=None, gt=0)
    source_intake_id: Optional[int] = Field(default=None, gt=0)
    status: str = Field(default="awaiting_client_approval", max_length=64)


class ServiceWorkOrderUpdateRequest(BaseModel):
    technician_id: Optional[int] = Field(default=None, gt=0)
    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    due_date: Optional[date] = None
    status: Optional[str] = Field(default=None, max_length=64)


class ServiceQuoteItemInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    quantity: float = Field(default=1, ge=0)
    unit_price: float = Field(default=0, ge=0)
    total_price: Optional[float] = Field(default=None, ge=0)


class ServiceQuoteCreateRequest(BaseModel):
    vehicle_id: int = Field(gt=0)
    customer_id: Optional[int] = Field(default=None, gt=0)
    work_order_id: Optional[int] = Field(default=None, gt=0)
    service_record_id: Optional[int] = Field(default=None, gt=0)
    items: list[ServiceQuoteItemInput] = Field(default_factory=list)
    labor_hours: Optional[float] = Field(default=None, ge=0)
    labor_rate: Optional[float] = Field(default=None, ge=0)
    total_price: Optional[float] = Field(default=None, ge=0)
    status: str = Field(default="draft", max_length=32)


class ServiceQuoteUpdateRequest(BaseModel):
    items: Optional[list[ServiceQuoteItemInput]] = None
    labor_hours: Optional[float] = Field(default=None, ge=0)
    labor_rate: Optional[float] = Field(default=None, ge=0)
    total_price: Optional[float] = Field(default=None, ge=0)
    status: Optional[str] = Field(default=None, max_length=32)


def _ensure_service_dashboard_schema(db: Session) -> None:
    assert_module_ready(db, "service_workspace", detail_prefix="Servisní dashboard není připraven")
    assert_module_ready(db, "service_dashboard", detail_prefix="Servisní dashboard není připraven")


def _normalize_status(raw: Optional[str]) -> str:
    value = str(raw or "").strip().lower()
    if value not in WORK_ORDER_STATUSES:
        raise HTTPException(status_code=422, detail="Neplatný stav zakázky.")
    return value


def _normalize_quote_status(raw: Optional[str]) -> str:
    value = str(raw or "").strip().lower() or "draft"
    if value not in QUOTE_STATUSES:
        raise HTTPException(status_code=422, detail="Neplatný stav nabídky.")
    return value


def _query_value(raw_value):
    if hasattr(raw_value, "default"):
        return raw_value.default
    return raw_value


def _work_order_snapshot(order: ServiceWorkOrder) -> dict[str, object]:
    return {
        "id": int(order.id),
        "tenant_id": order.tenant_id,
        "service_customer_id": order.service_customer_id,
        "owner_customer_id": order.owner_customer_id,
        "vehicle_id": order.vehicle_id,
        "technician_id": order.technician_id,
        "source_type": order.source_type,
        "source_reservation_id": order.source_reservation_id,
        "source_document_id": order.source_document_id,
        "source_intake_id": order.source_intake_id,
        "title": order.title,
        "description": order.description,
        "status": order.status,
        "due_date": order.due_date.isoformat() if order.due_date else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        "approved_at": order.approved_at.isoformat() if order.approved_at else None,
        "started_at": order.started_at.isoformat() if order.started_at else None,
        "completed_at": order.completed_at.isoformat() if order.completed_at else None,
    }


def _quote_status_label(status: str) -> str:
    labels = {
        "draft": "Koncept",
        "sent": "Odesláno",
        "approved": "Schváleno",
        "rejected": "Zamítnuto",
    }
    return labels.get(str(status or "").lower(), str(status or "draft"))


def _parse_quote_items(raw_items: object) -> list[dict[str, object]]:
    if isinstance(raw_items, list):
        items = raw_items
    else:
        try:
            items = json.loads(str(raw_items or "[]"))
        except Exception:
            items = []
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        quantity = float(item.get("quantity") or 0)
        unit_price = float(item.get("unit_price") or 0)
        total_price = item.get("total_price")
        if total_price is None:
            total_price = round(quantity * unit_price, 2)
        normalized.append(
            {
                "name": str(item.get("name") or "Položka"),
                "quantity": round(quantity, 2),
                "unit_price": round(unit_price, 2),
                "total_price": round(float(total_price or 0), 2),
            }
        )
    return normalized


def _quote_snapshot(quote: ServiceQuote) -> dict[str, object]:
    return {
        "id": int(quote.id),
        "tenant_id": quote.tenant_id,
        "vehicle_id": quote.vehicle_id,
        "customer_id": quote.customer_id,
        "service_id": quote.service_id,
        "work_order_id": quote.work_order_id,
        "service_record_id": quote.service_record_id,
        "items_json": quote.items_json,
        "labor_hours": quote.labor_hours,
        "labor_rate": quote.labor_rate,
        "total_price": quote.total_price,
        "status": quote.status,
        "approved_at": quote.approved_at.isoformat() if quote.approved_at else None,
        "rejected_at": quote.rejected_at.isoformat() if quote.rejected_at else None,
        "created_at": quote.created_at.isoformat() if quote.created_at else None,
        "updated_at": quote.updated_at.isoformat() if quote.updated_at else None,
    }


def _write_quote_audit(
    db: Session,
    *,
    quote: ServiceQuote,
    action: str,
    actor: Customer,
    previous_snapshot: dict[str, object],
    new_snapshot: Optional[dict[str, object]],
) -> None:
    db.add(
        ServiceQuoteAuditLog(
            tenant_id=quote.tenant_id,
            quote_id=quote.id,
            vehicle_id=quote.vehicle_id,
            changed_by_user_id=getattr(actor, "id", None),
            action=action,
            previous_snapshot_json=json.dumps(previous_snapshot, ensure_ascii=False, default=str),
            new_snapshot_json=(json.dumps(new_snapshot, ensure_ascii=False, default=str) if new_snapshot is not None else None),
        )
    )
    metadata = {
        "vehicle_id": quote.vehicle_id,
        "work_order_id": quote.work_order_id,
        "service_record_id": quote.service_record_id,
        "total_price": quote.total_price,
        "status": quote.status,
    }
    write_global_audit_log(
        db,
        entity_type="service_quote",
        entity_id=quote.id,
        action=action,
        actor_user_id=getattr(actor, "id", None),
        actor_role=getattr(actor, "role", None),
        tenant_id=quote.tenant_id,
        metadata=metadata,
    )


def _write_work_order_audit(
    db: Session,
    *,
    work_order: ServiceWorkOrder,
    action: str,
    actor: Customer,
    previous_snapshot: dict[str, object],
    new_snapshot: Optional[dict[str, object]],
) -> None:
    db.add(
        ServiceWorkOrderAuditLog(
            tenant_id=work_order.tenant_id,
            work_order_id=work_order.id,
            vehicle_id=work_order.vehicle_id,
            changed_by_user_id=getattr(actor, "id", None),
            action=action,
            previous_snapshot_json=json.dumps(previous_snapshot, ensure_ascii=False, default=str),
            new_snapshot_json=(
                json.dumps(new_snapshot, ensure_ascii=False, default=str)
                if new_snapshot is not None
                else None
            ),
        )
    )
    write_global_audit_log(
        db,
        entity_type="service_work_order",
        entity_id=work_order.id,
        action=action,
        actor_user_id=getattr(actor, "id", None),
        actor_role=getattr(actor, "role", None),
        tenant_id=work_order.tenant_id,
        metadata={
            "vehicle_id": work_order.vehicle_id,
            "owner_customer_id": work_order.owner_customer_id,
            "technician_id": work_order.technician_id,
            "status": work_order.status,
        },
    )


def _resolve_authorized_quote_context(
    db: Session,
    *,
    current_user: Customer,
    vehicle_id: int,
    payload_customer_id: Optional[int],
) -> tuple[Customer, VehicleModel, ServiceCustomerLink, VehicleServiceLink]:
    """Resolve vehicle owner from ownership data, then require active customer link + approved vehicle link. Quote creation must never bypass this."""
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo pro nabídku nebylo nalezeno.")
    if int(getattr(vehicle, "tenant_id", 0) or 0) != int(getattr(current_user, "tenant_id", 0) or 0):
        raise HTTPException(status_code=403, detail="Servis nemá k vozidlu schválený přístup.")

    owner = get_primary_vehicle_owner(db, vehicle)
    if not owner:
        raise HTTPException(status_code=404, detail="Vozidlo nemá určeného vlastníka.")
    if int(getattr(owner, "tenant_id", 0) or 0) != int(getattr(vehicle, "tenant_id", 0) or 0):
        raise HTTPException(status_code=403, detail="Servis nemá k vozidlu schválený přístup.")

    if payload_customer_id is not None and int(payload_customer_id) != int(owner.id):
        raise HTTPException(status_code=403, detail="Zadaný zákazník neodpovídá vlastníkovi vozidla.")

    owner, vehicle = _resolve_owner_and_vehicle(
        db,
        current_user=current_user,
        owner_id=int(owner.id),
        vehicle_id=int(vehicle.id),
    )
    cust_link = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == current_user.id,
            ServiceCustomerLink.customer_id == owner.id,
            ServiceCustomerLink.status == "active",
        )
        .one()
    )
    v_link = (
        db.query(VehicleServiceLink)
        .filter(
            VehicleServiceLink.service_customer_id == current_user.id,
            VehicleServiceLink.owner_customer_id == owner.id,
            VehicleServiceLink.vehicle_id == vehicle.id,
            VehicleServiceLink.status == "approved",
        )
        .one()
    )
    return owner, vehicle, cust_link, v_link


def _is_service_provisioned_unowned_for_service(
    db: Session,
    *,
    current_user: Customer,
    vehicle: VehicleModel,
) -> bool:
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


def _resolve_unowned_work_order_vehicle(
    db: Session,
    *,
    current_user: Customer,
    vehicle_id: int,
) -> VehicleModel:
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo zakázky nebylo nalezeno.")
    if not _is_service_provisioned_unowned_for_service(db, current_user=current_user, vehicle=vehicle):
        if active_owner_assignment(db, int(vehicle.id)) is not None:
            raise HTTPException(
                status_code=422,
                detail="Pro vozidlo s majitelem je nutné zadat owner_id a schválený přístup.",
            )
        raise HTTPException(status_code=403, detail="Servis nemá oprávnění k tomuto nepřiřazenému vozidlu.")
    return vehicle


def _resolve_owner_and_vehicle(
    db: Session,
    *,
    current_user: Customer,
    owner_id: int,
    vehicle_id: int,
) -> tuple[Customer, VehicleModel]:
    owner = db.query(Customer).filter(Customer.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Majitel zakázky nebyl nalezen.")

    link = (
        db.query(ServiceCustomerLink.id)
        .filter(
            ServiceCustomerLink.service_customer_id == current_user.id,
            ServiceCustomerLink.customer_id == owner.id,
            ServiceCustomerLink.status == "active",
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=403, detail="Servis nemá vazbu na tohoto zákazníka.")

    vehicle = get_owned_vehicle(db, owner, vehicle_id, tenant_id=getattr(owner, "tenant_id", None))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo zákazníka nebylo nalezeno.")

    approved_link = (
        db.query(VehicleServiceLink.id)
        .filter(
            VehicleServiceLink.service_customer_id == current_user.id,
            VehicleServiceLink.owner_customer_id == owner.id,
            VehicleServiceLink.vehicle_id == vehicle.id,
            VehicleServiceLink.status == "approved",
        )
        .first()
    )
    if not approved_link:
        raise HTTPException(status_code=403, detail="Servis nemá k vozidlu schválený přístup.")

    return owner, vehicle


def _resolve_technician_id(db: Session, *, current_user: Customer, technician_id: Optional[int]) -> int:
    target_id = int(technician_id or current_user.id or 0)
    technician = (
        db.query(Customer)
        .filter(
            Customer.id == target_id,
            Customer.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not technician:
        raise HTTPException(status_code=404, detail="Technik nebyl nalezen.")
    return int(technician.id)


def _serialize_work_order(
    order: ServiceWorkOrder,
    *,
    owner: Optional[Customer],
    vehicle: VehicleModel,
    technician: Optional[Customer],
) -> dict[str, object]:
    vehicle_label = " / ".join(
        [part for part in [getattr(vehicle, "vin", None), getattr(vehicle, "plate", None)] if part]
    ) or f"Vozidlo #{int(vehicle.id)}"
    technical_specs = " ".join(
        [part for part in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None)] if part]
    ).strip()
    is_unowned = order.owner_customer_id is None
    return {
        "entity_type": "work_order",
        "entity_id": int(order.id),
        "id": int(order.id),
        "title": order.title,
        "description": order.description,
        "access_status": "full_access",
        "can_open_detail": True,
        "can_edit": True,
        "can_request_access": False,
        "can_create_work_order": False,
        "blocking_reason": None,
        "disclosure": "full",
        "is_unowned_vehicle": is_unowned,
        "owner_id": int(owner.id) if owner else None,
        "customer_id": int(owner.id) if owner else None,
        "customer_name": "Nepřiřazené vozidlo" if is_unowned else (owner.name or owner.email),
        "customer_contact": None if is_unowned else (owner.email or owner.phone),
        "vehicle_id": int(vehicle.id),
        "vehicle_vin": vehicle.vin,
        "vehicle_spz": vehicle.plate,
        "vehicle_label": vehicle_label,
        "vehicle_technical_data": technical_specs or vehicle.engine or None,
        "due_date": order.due_date.isoformat() if order.due_date else None,
        "status": order.status,
        "status_label": WORK_ORDER_STATUS_LABELS.get(order.status, order.status),
        "source": order.source_type,
        "source_label": WORK_ORDER_SOURCE_LABELS.get(order.source_type, order.source_type),
        "technician_id": int(order.technician_id),
        "technician_name": (
            technician.name if technician and technician.name
            else technician.email if technician
            else f"Technik #{int(order.technician_id)}"
        ),
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        "approved_at": order.approved_at.isoformat() if order.approved_at else None,
        "started_at": order.started_at.isoformat() if order.started_at else None,
        "completed_at": order.completed_at.isoformat() if order.completed_at else None,
        "source_reservation_id": order.source_reservation_id,
        "source_document_id": order.source_document_id,
        "source_intake_id": order.source_intake_id,
        "customer_linked": not is_unowned,
        "vehicle_access_approved": True,
    }


def _serialize_quote_summary(
    quote: ServiceQuote,
    *,
    vehicle: VehicleModel,
    service_customer: Optional[Customer],
    public_token=None,
    work_order: Optional[ServiceWorkOrder] = None,
) -> dict[str, object]:
    return {
        "quote_id": int(quote.id),
        "status": str(quote.status or "draft"),
        "status_label": _quote_status_label(str(quote.status or "draft")),
        "total_price": quote.total_price,
        "approved_at": quote.approved_at.isoformat() if quote.approved_at else None,
        "rejected_at": quote.rejected_at.isoformat() if quote.rejected_at else None,
        "created_at": quote.created_at.isoformat() if quote.created_at else None,
        "updated_at": quote.updated_at.isoformat() if quote.updated_at else None,
        "service_record_id": int(quote.service_record_id) if quote.service_record_id else None,
        "work_order_id": int(quote.work_order_id) if quote.work_order_id else None,
        "pdf_url": f"/api/service/quotes/{int(quote.id)}/pdf",
        "public_quote_url": build_public_quote_page_url(str(public_token.token)) if public_token else None,
        "consistency_note": _quote_status_consistency_note(quote=quote, work_order=work_order),
        "vehicle_label": " ".join(part for part in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None)] if part).strip()
        or getattr(vehicle, "nickname", None)
        or getattr(vehicle, "plate", None),
        "service_name": getattr(service_customer, "name", None) or getattr(service_customer, "email", None),
    }


def _serialize_quote(
    quote: ServiceQuote,
    *,
    owner: Optional[Customer],
    vehicle: VehicleModel,
    service_customer: Optional[Customer],
    public_token=None,
) -> dict[str, object]:
    items = _parse_quote_items(getattr(quote, "items_json", None))
    vehicle_label = " ".join(part for part in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None)] if part).strip()
    vehicle_label = vehicle_label or getattr(vehicle, "nickname", None) or getattr(vehicle, "plate", None) or f"Vozidlo #{int(vehicle.id)}"
    return {
        "id": int(quote.id),
        "vehicle_id": int(quote.vehicle_id),
        "customer_id": int(owner.id) if owner else None,
        "service_id": int(quote.service_id),
        "work_order_id": int(quote.work_order_id) if quote.work_order_id else None,
        "service_record_id": int(quote.service_record_id) if quote.service_record_id else None,
        "items": items,
        "labor_hours": quote.labor_hours,
        "labor_rate": quote.labor_rate,
        "total_price": quote.total_price,
        "status": quote.status,
        "status_label": _quote_status_label(str(quote.status or "draft")),
        "approved_at": quote.approved_at.isoformat() if quote.approved_at else None,
        "rejected_at": quote.rejected_at.isoformat() if quote.rejected_at else None,
        "created_at": quote.created_at.isoformat() if quote.created_at else None,
        "updated_at": quote.updated_at.isoformat() if quote.updated_at else None,
        "vehicle_label": vehicle_label,
        "vehicle_vin": getattr(vehicle, "vin", None),
        "vehicle_spz": getattr(vehicle, "plate", None),
        "customer_name": owner.name if owner and owner.name else owner.email if owner else None,
        "customer_email": getattr(owner, "email", None) if owner else None,
        "customer_phone": getattr(owner, "phone", None) if owner else None,
        "service_name": getattr(service_customer, "name", None) or getattr(service_customer, "email", None),
        "service_ico": getattr(service_customer, "ico", None),
        "pdf_url": f"/api/service/quotes/{int(quote.id)}/pdf",
        "public_quote_url": build_public_quote_page_url(str(public_token.token)) if public_token else None,
        "public_quote_token_issued_at": public_token.issued_at.isoformat() if public_token and public_token.issued_at else None,
    }


def _get_quote_or_404(db: Session, *, current_user: Customer, quote_id: int) -> ServiceQuote:
    quote = (
        db.query(ServiceQuote)
        .filter(
            ServiceQuote.id == int(quote_id),
            ServiceQuote.service_id == int(current_user.id),
        )
        .first()
    )
    if not quote:
        raise HTTPException(status_code=404, detail="Nabídka nebyla nalezena.")
    if quote.customer_id:
        _resolve_owner_and_vehicle(
            db,
            current_user=current_user,
            owner_id=int(quote.customer_id),
            vehicle_id=int(quote.vehicle_id),
        )
    return quote


def _quote_from_record_payload(record: ServiceRecordModel) -> tuple[list[dict[str, object]], Optional[float], Optional[float], float]:
    items: list[dict[str, object]] = []
    labor_hours: Optional[float] = None
    labor_rate: Optional[float] = None
    attachments = []
    try:
        attachments = json.loads(str(getattr(record, "attachments", None) or "[]"))
    except Exception:
        attachments = []
    if isinstance(attachments, list):
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            parsed_summary = attachment.get("parsed_summary")
            if not isinstance(parsed_summary, dict):
                continue
            parsed_items = parsed_summary.get("items")
            if isinstance(parsed_items, list):
                for item in parsed_items:
                    if not isinstance(item, dict):
                        continue
                    quantity = float(item.get("quantity") or 0)
                    unit_price = float(item.get("unit_price") or item.get("total_price") or 0)
                    total_price = float(item.get("total_price") or (quantity * unit_price) or 0)
                    items.append(
                        {
                            "name": str(item.get("name") or "Položka"),
                            "quantity": round(quantity or 1, 2),
                            "unit_price": round(unit_price, 2),
                            "total_price": round(total_price, 2),
                        }
                    )
            if parsed_summary.get("labor_hours") is not None:
                labor_hours = float(parsed_summary.get("labor_hours") or 0)
            if parsed_summary.get("labor_hour_rate") is not None:
                labor_rate = float(parsed_summary.get("labor_hour_rate") or 0)
            if items:
                break
    if not items:
        base_price = float(getattr(record, "total_price", None) if getattr(record, "total_price", None) is not None else getattr(record, "price", None) or 0)
        items = [
            {
                "name": str(getattr(record, "description", None) or getattr(record, "category", None) or "Servisní práce"),
                "quantity": 1.0,
                "unit_price": round(base_price, 2),
                "total_price": round(base_price, 2),
            }
        ]
    items_total = round(sum(float(item.get("total_price") or 0) for item in items), 2)
    total_price = round(float(getattr(record, "total_price", None) if getattr(record, "total_price", None) is not None else getattr(record, "price", None) or items_total), 2)
    return items, labor_hours, labor_rate, total_price


def _quote_status_consistency_note(*, quote: ServiceQuote, work_order: Optional[ServiceWorkOrder]) -> Optional[str]:
    if not work_order:
        return None
    quote_status = str(getattr(quote, "status", None) or "draft").lower()
    work_order_status = str(getattr(work_order, "status", None) or "").lower()
    if quote_status == "approved" and work_order_status != "approved":
        return "Nabídka je schválená, ale zakázka ještě není přepnuta do stavu schváleno."
    return None


def _sync_work_order_on_quote_rejected(
    db: Session,
    *,
    quote: ServiceQuote,
    actor: object,
    audit_action: str,
) -> None:
    """When a quote is rejected, work order must not remain approved/in_progress without a matching client decision."""
    if str(getattr(quote, "status", None) or "").lower() != "rejected":
        return
    wid = getattr(quote, "work_order_id", None)
    if not wid:
        return
    work_order = db.query(ServiceWorkOrder).filter(ServiceWorkOrder.id == int(wid)).first()
    if not work_order:
        return
    wo_status = str(work_order.status or "").lower()
    if wo_status in {"completed", "issue"}:
        return
    if wo_status not in {"approved", "in_progress"}:
        return
    previous_snapshot = _work_order_snapshot(work_order)
    work_order.status = "awaiting_client_approval"
    work_order.approved_at = None
    work_order.started_at = None
    db.flush()
    _write_work_order_audit(
        db,
        work_order=work_order,
        action=audit_action,
        actor=actor,
        previous_snapshot=previous_snapshot,
        new_snapshot=_work_order_snapshot(work_order),
    )


def _sync_work_order_status_from_quote(
    db: Session,
    *,
    quote: ServiceQuote,
    actor: Customer,
    action: str,
) -> None:
    if not quote.work_order_id:
        return
    work_order = db.query(ServiceWorkOrder).filter(ServiceWorkOrder.id == int(quote.work_order_id)).first()
    if not work_order:
        return
    if str(getattr(quote, "status", None) or "").lower() != "approved":
        return
    if str(work_order.status or "").lower() == "approved":
        return
    previous_snapshot = _work_order_snapshot(work_order)
    work_order.status = "approved"
    if work_order.approved_at is None:
        work_order.approved_at = datetime.utcnow()
    db.flush()
    _write_work_order_audit(
        db,
        work_order=work_order,
        action=action,
        actor=actor,
        previous_snapshot=previous_snapshot,
        new_snapshot=_work_order_snapshot(work_order),
    )


def _assert_work_order_vehicle_access(
    db: Session,
    *,
    current_user: Customer,
    order: ServiceWorkOrder,
) -> VehicleModel:
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(order.vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo zakázky nebylo nalezeno.")
    if order.owner_customer_id is not None:
        _resolve_owner_and_vehicle(
            db,
            current_user=current_user,
            owner_id=int(order.owner_customer_id),
            vehicle_id=int(order.vehicle_id),
        )
    elif not _is_service_provisioned_unowned_for_service(db, current_user=current_user, vehicle=vehicle):
        raise HTTPException(status_code=403, detail="Servis nemá oprávnění k této zakázce.")
    return vehicle


def _get_work_order_or_404(db: Session, *, current_user: Customer, work_order_id: int) -> ServiceWorkOrder:
    order = (
        db.query(ServiceWorkOrder)
        .filter(
            ServiceWorkOrder.id == work_order_id,
            ServiceWorkOrder.service_customer_id == current_user.id,
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Zakázka nebyla nalezena.")
    _assert_work_order_vehicle_access(db, current_user=current_user, order=order)
    return order


def _load_work_order_parties(
    db: Session,
    order: ServiceWorkOrder,
) -> tuple[Optional[Customer], VehicleModel, Optional[Customer]]:
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(order.vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo zakázky nebylo nalezeno.")
    owner: Optional[Customer] = None
    if order.owner_customer_id is not None:
        owner = db.query(Customer).filter(Customer.id == int(order.owner_customer_id)).first()
        if not owner:
            raise HTTPException(status_code=404, detail="Majitel zakázky nebyl nalezen.")
    technician = db.query(Customer).filter(Customer.id == int(order.technician_id)).first()
    return owner, vehicle, technician


@router.get("/dashboard/summary")
def get_service_dashboard_summary(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    today = date.today()
    base = db.query(ServiceWorkOrder).filter(ServiceWorkOrder.service_customer_id == current_user.id)
    linked_customer_ids_subquery = (
        db.query(ServiceCustomerLink.customer_id)
        .filter(
            ServiceCustomerLink.service_customer_id == int(current_user.id),
            ServiceCustomerLink.status == "active",
        )
    )
    reservation_base = db.query(ReservationModel).filter(
        ReservationModel.tenant_id == int(current_user.tenant_id),
        ReservationModel.service_id == int(current_user.id),
    )
    quote_base = db.query(ServiceQuote).filter(
        ServiceQuote.tenant_id == int(current_user.tenant_id),
        ServiceQuote.service_id == int(current_user.id),
    )
    invoice_base = db.query(ServiceInvoice).filter(
        ServiceInvoice.tenant_id == int(current_user.tenant_id),
        ServiceInvoice.service_id == int(current_user.id),
    )
    reminder_base = db.query(ReminderModel).filter(
        ReminderModel.tenant_id == int(current_user.tenant_id),
        ReminderModel.customer_id.in_(linked_customer_ids_subquery),
    )

    return {
        "active_jobs": base.filter(ServiceWorkOrder.status.in_(tuple(WORK_ORDER_STATUSES_IN_PROGRESS))).count(),
        "awaiting_approval": base.filter(ServiceWorkOrder.status == "awaiting_client_approval").count(),
        "due_today": base.filter(ServiceWorkOrder.due_date == today).count(),
        "overdue": base.filter(
            ServiceWorkOrder.due_date.isnot(None),
            ServiceWorkOrder.due_date < today,
            ServiceWorkOrder.status != "completed",
        ).count(),
        "new_reservations": reservation_base.filter(ReservationModel.status == "PENDING").count(),
        "today_reservations": reservation_base.filter(
            func.date(ReservationModel.start_datetime) == today.isoformat(),
        ).count(),
        "pending_quotes": quote_base.filter(ServiceQuote.status.in_(("draft", "sent"))).count(),
        "approved_quotes": quote_base.filter(ServiceQuote.status == "approved").count(),
        "invoices_total": invoice_base.count(),
        "draft_invoices": invoice_base.filter(ServiceInvoice.status == "draft").count(),
        "issued_invoices": invoice_base.filter(ServiceInvoice.status == "issued").count(),
        "open_reminders": reminder_base.filter(ReminderModel.is_completed.is_(False)).count(),
        "overdue_reminders": reminder_base.filter(
            ReminderModel.is_completed.is_(False),
            ReminderModel.due_date.isnot(None),
            ReminderModel.due_date < today,
        ).count(),
    }


@router.get("/dashboard/overview")
def get_service_dashboard_overview(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    today = date.today()
    month_start = today.replace(day=1)
    work_base = db.query(ServiceWorkOrder).filter(ServiceWorkOrder.service_customer_id == int(current_user.id))
    reservation_base = db.query(ReservationModel).filter(
        ReservationModel.tenant_id == int(current_user.tenant_id),
        ReservationModel.service_id == int(current_user.id),
    )
    invoice_base = db.query(ServiceInvoice).filter(
        ServiceInvoice.tenant_id == int(current_user.tenant_id),
        ServiceInvoice.service_id == int(current_user.id),
        ServiceInvoice.status == "issued",
        ServiceInvoice.issued_at.isnot(None),
        ServiceInvoice.issued_at >= datetime(month_start.year, month_start.month, month_start.day),
    )
    today_vehicle_ids = {
        int(row[0])
        for row in work_base.filter(ServiceWorkOrder.due_date == today).with_entities(ServiceWorkOrder.vehicle_id).all()
        if row[0]
    }
    today_vehicle_ids.update(
        int(row[0])
        for row in reservation_base.filter(func.date(ReservationModel.start_datetime) == today.isoformat())
        .with_entities(ReservationModel.vehicle_id)
        .all()
        if row[0]
    )
    invoice_total = invoice_base.with_entities(func.coalesce(func.sum(ServiceInvoice.total), 0)).scalar() or 0
    invoice_count = invoice_base.count()
    return {
        "today_vehicles": len(today_vehicle_ids),
        "waiting_intake": reservation_base.filter(
            func.date(ReservationModel.start_datetime) == today.isoformat(),
            ReservationModel.status.in_(("PENDING", "CONFIRMED")),
        ).count(),
        "open_work_orders": work_base.filter(ServiceWorkOrder.status != "completed").count(),
        "in_progress_work_orders": work_base.filter(ServiceWorkOrder.status.in_(tuple(WORK_ORDER_STATUSES_IN_PROGRESS))).count(),
        "waiting_approval": work_base.filter(ServiceWorkOrder.status == "awaiting_client_approval").count()
        + db.query(ServiceAccessRequest)
        .filter(
            ServiceAccessRequest.service_customer_id == int(current_user.id),
            ServiceAccessRequest.status == "pending",
        )
        .count(),
        "monthly_invoice_total": round(float(invoice_total or 0), 2),
        "monthly_invoice_count": int(invoice_count),
        "currency": "CZK",
    }


@router.get("/dashboard/work-orders")
def get_service_dashboard_work_orders(
    status: Optional[str] = Query(default="open"),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not isinstance(status, str):
        status = "open"
    if not isinstance(limit, int):
        limit = 10
    payload = list_service_work_orders(status=None if status == "open" else status, current_user=current_user, db=db)
    items = []
    for item in (payload.get("items") or [])[:limit]:
        raw_status = str(item.get("status") or "")
        label_map = {
            "awaiting_client_approval": "Čeká na schválení",
            "approved": "Diagnostika",
            "in_progress": "Práce probíhá",
            "completed": "Hotovo",
            "issue": "Riziko",
        }
        priority = "urgent" if raw_status in {"issue", "awaiting_client_approval"} else "normal"
        vin = str(item.get("vehicle_vin") or "")
        vehicle_title = str(item.get("vehicle_technical_data") or "").strip() or str(item.get("vehicle_label") or "Vozidlo")
        items.append(
            {
                **item,
                "vehicle_title": vehicle_title,
                "license_plate": item.get("vehicle_spz"),
                "vin_short": f"{vin[:3]}...{vin[-4:]}" if len(vin) > 8 else vin,
                "customer_display": item.get("customer_name") or "Osobní údaje skryty",
                "personal_data_hidden": False,
                "status_label": label_map.get(raw_status, item.get("status_label") or raw_status),
                "priority": priority,
                "vin_record": bool(vin),
                "owner_access_granted": True,
                "audited": True,
                "missing_photos": False,
                "approval_required": raw_status == "awaiting_client_approval",
                "work_time_minutes": 95 if raw_status in {"approved", "in_progress"} else 45,
                "detail_path": f"/app/s/service/work-orders/{int(item.get('id') or 0)}",
            }
        )
    if status == "open":
        items = [item for item in items if str(item.get("status") or "").lower() != "completed"]
    return {"items": items[:limit]}


@router.get("/dashboard/pending-authorizations")
def get_service_dashboard_pending_authorizations(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    rows = (
        db.query(ServiceAccessRequest, VehicleModel)
        .join(VehicleModel, VehicleModel.id == ServiceAccessRequest.vehicle_id)
        .filter(
            ServiceAccessRequest.service_customer_id == int(current_user.id),
            ServiceAccessRequest.status == "pending",
        )
        .order_by(ServiceAccessRequest.requested_at.desc(), ServiceAccessRequest.id.desc())
        .limit(20)
        .all()
    )
    return {
        "items": [
            {
                "id": int(req.id),
                "vehicle_id": int(vehicle.id),
                "vehicle_title": " ".join([x for x in [vehicle.brand, vehicle.model] if x]).strip() or vehicle.nickname or "Vozidlo",
                "license_plate": vehicle.plate,
                "reason": req.request_message or "Žádost o přístup k historii",
                "status": req.status,
                "status_label": "Čeká na zákazníka",
                "personal_data_protected": True,
                "created_at": req.requested_at.isoformat() if req.requested_at else None,
                "detail_path": f"/app/s/service/authorizations/{int(req.id)}",
            }
            for req, vehicle in rows
        ]
    }


@router.get("/dashboard/today-reservations")
def get_service_dashboard_today_reservations(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    today = date.today()
    rows = (
        db.query(ReservationModel, VehicleModel)
        .outerjoin(VehicleModel, VehicleModel.id == ReservationModel.vehicle_id)
        .filter(
            ReservationModel.tenant_id == int(current_user.tenant_id),
            ReservationModel.service_id == int(current_user.id),
            func.date(ReservationModel.start_datetime) == today.isoformat(),
        )
        .order_by(ReservationModel.start_datetime.asc(), ReservationModel.id.asc())
        .limit(20)
        .all()
    )
    status_labels = {"PENDING": "Čeká", "CONFIRMED": "Potvrzeno", "CANCELLED": "Zrušeno", "ACCEPTED": "Přijato"}
    return {
        "items": [
            {
                "id": int(res.id),
                "time": res.start_datetime.strftime("%H:%M") if res.start_datetime else "",
                "service_type": res.service_type or "Servis",
                "vehicle_title": (
                    " ".join([x for x in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None)] if x]).strip()
                    if vehicle
                    else "Vozidlo"
                ),
                "status": res.status,
                "status_label": status_labels.get(str(res.status or "").upper(), str(res.status or "Čeká")),
                "detail_path": f"/app/s/service/reservations/{int(res.id)}",
            }
            for res, vehicle in rows
        ]
    }


@router.get("/dashboard/risks")
def get_service_dashboard_risks(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    active_orders = (
        db.query(ServiceWorkOrder)
        .filter(ServiceWorkOrder.service_customer_id == int(current_user.id), ServiceWorkOrder.status != "completed")
        .all()
    )
    active_vehicle_ids = [int(order.vehicle_id) for order in active_orders if order.vehicle_id]
    photo_vehicle_ids = set()
    if active_vehicle_ids:
        photo_vehicle_ids = {
            int(row[0])
            for row in db.query(VehiclePhotoAsset.vehicle_id)
            .filter(
                VehiclePhotoAsset.tenant_id == int(current_user.tenant_id),
                VehiclePhotoAsset.vehicle_id.in_(active_vehicle_ids),
            )
            .distinct()
            .all()
        }
    missing_photos = max(0, len(set(active_vehicle_ids)) - len(photo_vehicle_ids))
    awaiting = sum(1 for order in active_orders if order.status == "awaiting_client_approval")
    issue = sum(1 for order in active_orders if order.status == "issue")
    draft_invoices = (
        db.query(ServiceInvoice)
        .filter(
            ServiceInvoice.tenant_id == int(current_user.tenant_id),
            ServiceInvoice.service_id == int(current_user.id),
            ServiceInvoice.status == "draft",
        )
        .count()
    )
    completed = sum(1 for order in active_orders if order.status == "completed")
    raw_items = [
        ("missing_photos", f"Chybí vstupní fotodokumentace u {missing_photos} vozidel", "warning", missing_photos, "/photos?filter=missing"),
        ("price_approval", "Zakázka bez schválené ceny", "danger", awaiting, "/work-orders?filter=awaiting"),
        ("unverified_vin", "Neověřený VIN u nově přijatého vozidla", "danger", issue, "/vehicles?filter=vin"),
        ("invoice_waiting", "Faktura čeká na vystavení", "warning", draft_invoices, "/invoices?filter=draft"),
        ("handover_ready", "Vozidlo připraveno k předání", "success", completed, "/work-orders?filter=completed"),
    ]
    return {
        "items": [
            {"type": key, "label": label, "severity": severity, "count": int(count), "target_path": target}
            for key, label, severity, count, target in raw_items
            if int(count) > 0 or key in {"missing_photos", "invoice_waiting", "handover_ready"}
        ]
    }


@router.get("/work-orders")
def list_service_work_orders(
    status: Optional[str] = Query(default=None),
    technician_id: Optional[int] = Query(default=None, ge=1),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    owner_alias = aliased(Customer)
    tech_alias = aliased(Customer)

    owned_customer_link = exists().where(
        and_(
            ServiceCustomerLink.service_customer_id == ServiceWorkOrder.service_customer_id,
            ServiceCustomerLink.customer_id == ServiceWorkOrder.owner_customer_id,
            ServiceCustomerLink.status == "active",
        )
    )
    owned_vehicle_link = exists().where(
        and_(
            VehicleServiceLink.service_customer_id == ServiceWorkOrder.service_customer_id,
            VehicleServiceLink.owner_customer_id == ServiceWorkOrder.owner_customer_id,
            VehicleServiceLink.vehicle_id == ServiceWorkOrder.vehicle_id,
            VehicleServiceLink.status == "approved",
        )
    )

    query = (
        db.query(ServiceWorkOrder, owner_alias, VehicleModel, tech_alias)
        .join(VehicleModel, VehicleModel.id == ServiceWorkOrder.vehicle_id)
        .outerjoin(owner_alias, owner_alias.id == ServiceWorkOrder.owner_customer_id)
        .outerjoin(tech_alias, tech_alias.id == ServiceWorkOrder.technician_id)
        .filter(ServiceWorkOrder.service_customer_id == current_user.id)
        .filter(
            or_(
                and_(
                    ServiceWorkOrder.owner_customer_id.isnot(None),
                    owned_customer_link,
                    owned_vehicle_link,
                ),
                and_(
                    ServiceWorkOrder.owner_customer_id.is_(None),
                    VehicleModel.provisioned_by_service_customer_id == int(current_user.id),
                    VehicleModel.global_vehicle_status == "service_provisioned_unowned",
                ),
            )
        )
    )

    normalized_status_raw = _query_value(status)
    technician_id_value = _query_value(technician_id)
    date_from_value = _query_value(date_from)
    date_to_value = _query_value(date_to)

    if normalized_status_raw:
        normalized_status = str(normalized_status_raw).strip().lower()
        if normalized_status == "active":
            query = query.filter(ServiceWorkOrder.status.in_(tuple(WORK_ORDER_STATUSES_IN_PROGRESS)))
        else:
            query = query.filter(ServiceWorkOrder.status == _normalize_status(normalized_status))
    if technician_id_value:
        query = query.filter(ServiceWorkOrder.technician_id == int(technician_id_value))
    if date_from_value:
        query = query.filter(or_(ServiceWorkOrder.due_date.is_(None), ServiceWorkOrder.due_date >= date_from_value))
    if date_to_value:
        query = query.filter(or_(ServiceWorkOrder.due_date.is_(None), ServiceWorkOrder.due_date <= date_to_value))

    rows = (
        query
        .order_by(
            ServiceWorkOrder.due_date.is_(None).asc(),
            ServiceWorkOrder.due_date.asc(),
            ServiceWorkOrder.created_at.desc(),
        )
        .limit(250)
        .all()
    )

    return {
        "items": [
            _serialize_work_order(order, owner=owner, vehicle=vehicle, technician=technician)
            for order, owner, vehicle, technician in rows
        ]
    }


@router.get("/work-orders/{work_order_id}")
def get_service_work_order_detail(
    work_order_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    order = _get_work_order_or_404(db, current_user=current_user, work_order_id=work_order_id)
    owner = (
        db.query(Customer).filter(Customer.id == order.owner_customer_id).first()
        if order.owner_customer_id is not None
        else None
    )
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == order.vehicle_id).first()
    technician = db.query(Customer).filter(Customer.id == order.technician_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Detail zakázky není kompletní.")
    if order.owner_customer_id is not None and not owner:
        raise HTTPException(status_code=404, detail="Detail zakázky není kompletní.")
    if order.owner_customer_id is None and not _is_service_provisioned_unowned_for_service(
        db, current_user=current_user, vehicle=vehicle
    ):
        raise HTTPException(status_code=403, detail="Servis nemá oprávnění k detailu této zakázky.")

    audit_rows = (
        db.query(ServiceWorkOrderAuditLog)
        .filter(ServiceWorkOrderAuditLog.work_order_id == order.id)
        .order_by(ServiceWorkOrderAuditLog.created_at.desc(), ServiceWorkOrderAuditLog.id.desc())
        .limit(20)
        .all()
    )
    detail = _serialize_work_order(order, owner=owner, vehicle=vehicle, technician=technician)
    linked_quote = (
        db.query(ServiceQuote)
        .filter(
            ServiceQuote.work_order_id == int(order.id),
            ServiceQuote.service_id == int(current_user.id),
        )
        .order_by(ServiceQuote.updated_at.desc(), ServiceQuote.id.desc())
        .first()
    )
    if linked_quote:
        public_token = get_active_quote_access_token(db, quote_id=int(linked_quote.id))
        detail["quote_summary"] = _serialize_quote_summary(
            linked_quote,
            vehicle=vehicle,
            service_customer=current_user,
            public_token=public_token,
            work_order=order,
        )
    detail["audit_log"] = [
        {
            "id": int(row.id),
            "action": row.action,
            "changed_by_user_id": row.changed_by_user_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in audit_rows
    ]
    from .work_order_items_api import (
        list_work_order_items_grouped,
        work_order_capabilities,
        work_order_limited_notices,
    )

    detail["items"] = list_work_order_items_grouped(db, work_order_id=int(order.id))
    detail["photos"] = list_work_order_photos_for_order(
        db,
        work_order_id=int(order.id),
        service_customer_id=int(current_user.id),
    )
    detail["capabilities"] = work_order_capabilities(order=order)
    detail["limited_notices"] = work_order_limited_notices()
    linked_record = (
        db.query(ServiceRecordModel.id)
        .filter(
            ServiceRecordModel.work_order_id == int(order.id),
            ServiceRecordModel.is_deleted.is_(False),
            ServiceRecordModel.service_id == int(current_user.id),
        )
        .order_by(ServiceRecordModel.id.desc())
        .first()
    )
    detail["service_record_id"] = int(linked_record[0]) if linked_record else None
    return detail


@router.get("/vehicles/{vehicle_id}/quotes")
def list_vehicle_quotes(
    vehicle_id: int,
    status: Optional[str] = None,
    sort: str = "created_at",
    order: str = "desc",
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    sort_key = str(sort or "created_at").strip().lower()
    if sort_key not in {"created_at", "total_price", "status"}:
        raise HTTPException(status_code=422, detail="Neplatné řazení nabídek.")
    order_key = str(order or "desc").strip().lower()
    if order_key not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="Neplatný směr řazení.")
    status_filter: Optional[str] = None
    if status is not None and str(status).strip():
        status_filter = str(status).strip().lower()
        if status_filter not in QUOTE_STATUSES:
            raise HTTPException(status_code=422, detail="Neplatný stav filtru nabídek.")

    link = (
        db.query(VehicleServiceLink.id)
        .filter(
            VehicleServiceLink.service_customer_id == int(current_user.id),
            VehicleServiceLink.vehicle_id == int(vehicle_id),
            VehicleServiceLink.status == "approved",
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=403, detail="Servis nemá k vozidlu schválený přístup.")

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno.")

    quote_query = db.query(ServiceQuote).filter(
        ServiceQuote.vehicle_id == int(vehicle_id),
        ServiceQuote.service_id == int(current_user.id),
    )
    if status_filter:
        quote_query = quote_query.filter(ServiceQuote.status == status_filter)

    if sort_key == "created_at":
        if order_key == "desc":
            quote_query = quote_query.order_by(ServiceQuote.created_at.desc(), ServiceQuote.id.desc())
        else:
            quote_query = quote_query.order_by(ServiceQuote.created_at.asc(), ServiceQuote.id.asc())
    elif sort_key == "total_price":
        if order_key == "desc":
            quote_query = quote_query.order_by(ServiceQuote.total_price.desc(), ServiceQuote.id.desc())
        else:
            quote_query = quote_query.order_by(ServiceQuote.total_price.asc(), ServiceQuote.id.asc())
    else:
        if order_key == "desc":
            quote_query = quote_query.order_by(
                QUOTE_STATUS_SORT_RANK.desc(),
                ServiceQuote.created_at.desc(),
                ServiceQuote.id.desc(),
            )
        else:
            quote_query = quote_query.order_by(
                QUOTE_STATUS_SORT_RANK.asc(),
                ServiceQuote.created_at.desc(),
                ServiceQuote.id.desc(),
            )

    rows = quote_query.all()
    items = []
    for quote in rows:
        public_token = get_active_quote_access_token(db, quote_id=int(quote.id))
        work_order = db.query(ServiceWorkOrder).filter(ServiceWorkOrder.id == int(quote.work_order_id)).first() if quote.work_order_id else None
        items.append(
            _serialize_quote_summary(
                quote,
                vehicle=vehicle,
                service_customer=current_user,
                public_token=public_token,
                work_order=work_order,
            )
        )
    return {"items": items}


@router.get("/work-orders/unowned-vehicles")
def list_unowned_vehicles_for_work_orders(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Nepřiřazená vozidla založená tímto servisem — pouze pro zakázky bez owner_id."""
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    rows = (
        db.query(VehicleModel)
        .filter(
            VehicleModel.provisioned_by_service_customer_id == int(current_user.id),
            VehicleModel.global_vehicle_status == "service_provisioned_unowned",
            VehicleModel.status != "archived",
        )
        .order_by(VehicleModel.updated_at.desc(), VehicleModel.id.desc())
        .limit(100)
        .all()
    )
    items = []
    for vehicle in rows:
        if active_owner_assignment(db, int(vehicle.id)) is not None:
            continue
        label = " / ".join(
            part
            for part in [
                getattr(vehicle, "brand", None),
                getattr(vehicle, "model", None),
                getattr(vehicle, "plate", None) or getattr(vehicle, "vin", None),
            ]
            if part
        ) or f"Vozidlo #{int(vehicle.id)}"
        items.append({"vehicle_id": int(vehicle.id), "label": label})
    return {"items": items}


@router.post("/work-orders")
def create_service_work_order(
    payload: ServiceWorkOrderCreateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    owner: Optional[Customer] = None
    if payload.owner_id is not None:
        owner, vehicle = _resolve_owner_and_vehicle(
            db,
            current_user=current_user,
            owner_id=int(payload.owner_id),
            vehicle_id=int(payload.vehicle_id),
        )
    else:
        vehicle = _resolve_unowned_work_order_vehicle(
            db,
            current_user=current_user,
            vehicle_id=int(payload.vehicle_id),
        )

    technician_id = _resolve_technician_id(db, current_user=current_user, technician_id=payload.technician_id)
    status = _normalize_status(payload.status)
    source_type = str(payload.source_type or "manual").strip().lower()
    if source_type not in {"manual", "reservation", "document", "intake"}:
        raise HTTPException(status_code=422, detail="Neplatný zdroj zakázky.")

    order = ServiceWorkOrder(
        tenant_id=getattr(current_user, "tenant_id", None) or getattr(vehicle, "tenant_id", None) or 1,
        service_customer_id=current_user.id,
        owner_customer_id=int(owner.id) if owner else None,
        vehicle_id=vehicle.id,
        technician_id=technician_id,
        source_type=source_type,
        source_reservation_id=payload.source_reservation_id,
        source_document_id=payload.source_document_id,
        source_intake_id=payload.source_intake_id,
        title=str(payload.title or "").strip(),
        description=(str(payload.description or "").strip() or None),
        status=status,
        due_date=payload.due_date,
    )
    duplicate_filters = [
        ServiceWorkOrder.service_customer_id == current_user.id,
        ServiceWorkOrder.vehicle_id == vehicle.id,
        ServiceWorkOrder.status != "completed",
    ]
    if owner is not None:
        duplicate_filters.append(ServiceWorkOrder.owner_customer_id == owner.id)
    else:
        duplicate_filters.append(ServiceWorkOrder.owner_customer_id.is_(None))

    duplicate_open_order = (
        db.query(ServiceWorkOrder.id, ServiceWorkOrder.title, ServiceWorkOrder.status)
        .filter(*duplicate_filters)
        .order_by(ServiceWorkOrder.created_at.desc(), ServiceWorkOrder.id.desc())
        .first()
    )
    if duplicate_open_order:
        write_global_audit_log(
            db,
            entity_type="service_work_order",
            entity_id=int(duplicate_open_order[0]),
            action="duplicate_create_rejected",
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
            tenant_id=getattr(current_user, "tenant_id", None),
            metadata={
                "owner_customer_id": int(owner.id) if owner else None,
                "vehicle_id": int(vehicle.id),
                "title": str(payload.title or "").strip(),
                "unowned_vehicle": owner is None,
            },
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_work_order",
                "message": "Na stejné vozidlo už existuje rozpracovaná zakázka. Otevřete existující záznam místo vytváření duplicity.",
                "existing_work_order_id": int(duplicate_open_order[0]),
                "existing_work_order_title": duplicate_open_order[1] or "Rozpracovaná zakázka",
                "existing_work_order_status": duplicate_open_order[2],
            },
        )

    now = datetime.utcnow()
    if status == "approved":
        order.approved_at = now
    elif status == "in_progress":
        order.started_at = now
    elif status == "completed":
        order.completed_at = now

    db.add(order)
    db.flush()

    snapshot = _work_order_snapshot(order)
    audit_action = "create_unowned" if owner is None else "create"
    _write_work_order_audit(
        db,
        work_order=order,
        action=audit_action,
        actor=current_user,
        previous_snapshot={},
        new_snapshot=snapshot,
    )

    db.commit()
    db.refresh(order)

    technician = db.query(Customer).filter(Customer.id == order.technician_id).first()
    return _serialize_work_order(order, owner=owner, vehicle=vehicle, technician=technician)


@router.put("/work-orders/{work_order_id}")
def update_service_work_order(
    work_order_id: int,
    payload: ServiceWorkOrderUpdateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    order = _get_work_order_or_404(db, current_user=current_user, work_order_id=work_order_id)
    previous_snapshot = _work_order_snapshot(order)
    fields_set = set(getattr(payload, "model_fields_set", set()) or set())

    if "technician_id" in fields_set:
        order.technician_id = _resolve_technician_id(db, current_user=current_user, technician_id=payload.technician_id)
    if payload.title is not None:
        order.title = str(payload.title).strip()
    if "description" in fields_set:
        order.description = (str(payload.description or "").strip() or None)
    if "due_date" in fields_set:
        order.due_date = payload.due_date
    if payload.status is not None:
        normalized_status = _normalize_status(payload.status)
        order.status = normalized_status
        now = datetime.utcnow()
        if normalized_status == "approved" and order.approved_at is None:
            order.approved_at = now
        if normalized_status == "in_progress" and order.started_at is None:
            order.started_at = now
        if normalized_status == "completed":
            order.completed_at = now

    db.flush()
    new_snapshot = _work_order_snapshot(order)
    _write_work_order_audit(
        db,
        work_order=order,
        action="update",
        actor=current_user,
        previous_snapshot=previous_snapshot,
        new_snapshot=new_snapshot,
    )
    db.commit()
    db.refresh(order)

    owner, vehicle, technician = _load_work_order_parties(db, order)
    return _serialize_work_order(order, owner=owner, vehicle=vehicle, technician=technician)


from .work_order_items_api import register_work_order_item_routes
from .work_order_photos_api import list_work_order_photos_for_order, register_work_order_photo_routes

register_work_order_item_routes(router)
register_work_order_photo_routes(router)


@router.post("/quotes/from-record/{record_id}")
def create_service_quote_from_record(
    record_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    record = (
        db.query(ServiceRecordModel)
        .filter(
            ServiceRecordModel.id == int(record_id),
            ServiceRecordModel.service_id == int(current_user.id),
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Servisní záznam pro vytvoření nabídky nebyl nalezen.")

    owner = db.query(Customer).filter(Customer.id == int(record.customer_id)).first() if record.customer_id else None
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(record.vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo pro nabídku nebylo nalezeno.")
    if owner:
        _resolve_owner_and_vehicle(
            db,
            current_user=current_user,
            owner_id=int(owner.id),
            vehicle_id=int(vehicle.id),
        )

    existing = None
    if getattr(record, "quote_id", None):
        existing = (
            db.query(ServiceQuote)
            .filter(
                ServiceQuote.id == int(record.quote_id),
                ServiceQuote.service_id == int(current_user.id),
            )
            .first()
        )
    if existing:
        access_token = ensure_quote_access_token(db, quote=existing, created_by_user_id=getattr(current_user, "id", None))
        db.commit()
        db.refresh(existing)
        return _serialize_quote(existing, owner=owner, vehicle=vehicle, service_customer=current_user, public_token=access_token)

    items, labor_hours, labor_rate, total_price = _quote_from_record_payload(record)
    quote = ServiceQuote(
        tenant_id=getattr(record, "tenant_id", None) or getattr(current_user, "tenant_id", None) or 1,
        vehicle_id=int(record.vehicle_id),
        customer_id=int(record.customer_id) if record.customer_id else None,
        service_id=int(current_user.id),
        work_order_id=int(record.work_order_id) if record.work_order_id else None,
        service_record_id=int(record.id),
        items_json=json.dumps(items, ensure_ascii=False),
        labor_hours=labor_hours,
        labor_rate=labor_rate,
        total_price=total_price,
        status="draft",
    )
    db.add(quote)
    db.flush()
    record.quote_id = int(quote.id)
    _write_quote_audit(
        db,
        quote=quote,
        action="create_quote",
        actor=current_user,
        previous_snapshot={},
        new_snapshot=_quote_snapshot(quote),
    )
    _sync_work_order_status_from_quote(db, quote=quote, actor=current_user, action="quote_status_change")
    access_token = ensure_quote_access_token(db, quote=quote, created_by_user_id=getattr(current_user, "id", None))
    db.commit()
    db.refresh(quote)
    db.refresh(record)
    return _serialize_quote(quote, owner=owner, vehicle=vehicle, service_customer=current_user, public_token=access_token)


@router.post("/quotes")
def create_service_quote(
    payload: ServiceQuoteCreateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    owner, vehicle, _, _ = _resolve_authorized_quote_context(
        db,
        current_user=current_user,
        vehicle_id=int(payload.vehicle_id),
        payload_customer_id=int(payload.customer_id) if payload.customer_id is not None else None,
    )

    items = _parse_quote_items([item.model_dump() for item in payload.items])
    total_price = round(float(payload.total_price if payload.total_price is not None else sum(float(item["total_price"]) for item in items)), 2)
    quote = ServiceQuote(
        tenant_id=getattr(current_user, "tenant_id", None) or getattr(vehicle, "tenant_id", None) or 1,
        vehicle_id=int(payload.vehicle_id),
        customer_id=int(owner.id),
        service_id=int(current_user.id),
        work_order_id=int(payload.work_order_id) if payload.work_order_id else None,
        service_record_id=int(payload.service_record_id) if payload.service_record_id else None,
        items_json=json.dumps(items, ensure_ascii=False),
        labor_hours=payload.labor_hours,
        labor_rate=payload.labor_rate,
        total_price=total_price,
        status=_normalize_quote_status(payload.status),
    )
    db.add(quote)
    db.flush()
    if payload.service_record_id:
        record = db.query(ServiceRecordModel).filter(ServiceRecordModel.id == int(payload.service_record_id)).first()
        if record:
            record.quote_id = int(quote.id)
    _write_quote_audit(
        db,
        quote=quote,
        action="create_quote",
        actor=current_user,
        previous_snapshot={},
        new_snapshot=_quote_snapshot(quote),
    )
    _sync_work_order_status_from_quote(db, quote=quote, actor=current_user, action="quote_status_change")
    _sync_work_order_on_quote_rejected(
        db,
        quote=quote,
        actor=current_user,
        audit_action="quote_rejected_work_order_sync",
    )
    access_token = ensure_quote_access_token(db, quote=quote, created_by_user_id=getattr(current_user, "id", None))
    db.commit()
    db.refresh(quote)
    return _serialize_quote(quote, owner=owner, vehicle=vehicle, service_customer=current_user, public_token=access_token)


@router.get("/quotes/{quote_id}")
def get_service_quote_detail(
    quote_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    quote = _get_quote_or_404(db, current_user=current_user, quote_id=quote_id)
    owner = db.query(Customer).filter(Customer.id == int(quote.customer_id)).first() if quote.customer_id else None
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(quote.vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nabídky nebylo nalezeno.")
    public_token = get_active_quote_access_token(db, quote_id=int(quote.id))
    return _serialize_quote(quote, owner=owner, vehicle=vehicle, service_customer=current_user, public_token=public_token)


@router.put("/quotes/{quote_id}")
def update_service_quote(
    quote_id: int,
    payload: ServiceQuoteUpdateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    quote = _get_quote_or_404(db, current_user=current_user, quote_id=quote_id)
    previous_snapshot = _quote_snapshot(quote)
    previous_total_price = float(quote.total_price or 0)
    previous_status = str(quote.status or "draft")
    fields_set = set(getattr(payload, "model_fields_set", set()) or set())

    if "items" in fields_set and payload.items is not None:
        items = _parse_quote_items([item.model_dump() for item in payload.items])
        quote.items_json = json.dumps(items, ensure_ascii=False)
        if payload.total_price is None:
            quote.total_price = round(sum(float(item["total_price"]) for item in items), 2)
    if "labor_hours" in fields_set:
        quote.labor_hours = payload.labor_hours
    if "labor_rate" in fields_set:
        quote.labor_rate = payload.labor_rate
    if "total_price" in fields_set and payload.total_price is not None:
        quote.total_price = round(float(payload.total_price), 2)
    if "status" in fields_set and payload.status is not None:
        quote.status = _normalize_quote_status(payload.status)
        if quote.status == "approved":
            quote.approved_at = datetime.utcnow()
            quote.rejected_at = None
        elif quote.status == "rejected":
            quote.rejected_at = datetime.utcnow()
            quote.approved_at = None

    db.flush()
    new_snapshot = _quote_snapshot(quote)
    action = "update_quote"
    if float(quote.total_price or 0) != previous_total_price:
        action = "quote_price_change"
    if str(quote.status or "draft") != previous_status:
        action = "quote_status_change"
    _write_quote_audit(
        db,
        quote=quote,
        action=action,
        actor=current_user,
        previous_snapshot=previous_snapshot,
        new_snapshot=new_snapshot,
    )
    _sync_work_order_status_from_quote(db, quote=quote, actor=current_user, action=action)
    _sync_work_order_on_quote_rejected(
        db,
        quote=quote,
        actor=current_user,
        audit_action="quote_rejected_work_order_sync",
    )
    access_token = ensure_quote_access_token(db, quote=quote, created_by_user_id=getattr(current_user, "id", None))
    db.commit()
    db.refresh(quote)

    owner = db.query(Customer).filter(Customer.id == int(quote.customer_id)).first() if quote.customer_id else None
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(quote.vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nabídky nebylo nalezeno.")
    return _serialize_quote(quote, owner=owner, vehicle=vehicle, service_customer=current_user, public_token=access_token)


@router.get("/quotes/{quote_id}/pdf")
def get_service_quote_pdf(
    quote_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    quote = _get_quote_or_404(db, current_user=current_user, quote_id=quote_id)
    owner = db.query(Customer).filter(Customer.id == int(quote.customer_id)).first() if quote.customer_id else None
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(quote.vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nabídky nebylo nalezeno.")
    public_token = get_active_quote_access_token(db, quote_id=int(quote.id))
    serialized = _serialize_quote(quote, owner=owner, vehicle=vehicle, service_customer=current_user, public_token=public_token)
    pdf_content = render_service_quote_pdf(
        {
            **serialized,
            "quote_number": f"NAB-{int(quote.id):05d}",
            "created_at_label": quote.created_at.strftime("%d.%m.%Y") if quote.created_at else "-",
        }
    )
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="service-quote-{int(quote.id)}.pdf"'},
    )


@router.get("/technicians/performance")
def get_service_technician_performance(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    tech_alias = aliased(Customer)
    rows = (
        db.query(
            ServiceWorkOrder.technician_id,
            tech_alias.name,
            tech_alias.email,
            func.count(ServiceWorkOrder.id),
            func.sum(case((ServiceWorkOrder.status == "awaiting_client_approval", 1), else_=0)),
        )
        .outerjoin(tech_alias, tech_alias.id == ServiceWorkOrder.technician_id)
        .filter(
            ServiceWorkOrder.service_customer_id == current_user.id,
            ServiceWorkOrder.status != "completed",
        )
        .group_by(ServiceWorkOrder.technician_id, tech_alias.name, tech_alias.email)
        .order_by(func.count(ServiceWorkOrder.id).desc(), tech_alias.name.asc())
        .all()
    )

    items = [
        {
            "technician_id": int(technician_id),
            "name": name or email or f"Technik #{int(technician_id)}",
            "jobs_total": int(total or 0),
            "awaiting_count": int(awaiting or 0),
        }
        for technician_id, name, email, total, awaiting in rows
        if technician_id
    ]
    if not any(int(item["technician_id"]) == int(current_user.id) for item in items if item.get("technician_id")):
        items.insert(
            0,
            {
                "technician_id": int(current_user.id),
                "name": current_user.name or current_user.email or "Hlavní technik",
                "jobs_total": 0,
                "awaiting_count": 0,
            },
        )
    return {"items": items}


@router.get("/dashboard/queue")
def get_service_dashboard_queue(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_service_dashboard_schema(db)

    today = date.today()
    active_orders = (
        db.query(ServiceWorkOrder)
        .filter(
            ServiceWorkOrder.service_customer_id == current_user.id,
            ServiceWorkOrder.status != "completed",
        )
        .all()
    )

    missing_documents = sum(1 for item in active_orders if not item.source_document_id)
    recent_new_orders = sum(
        1
        for item in active_orders
        if item.created_at and (datetime.utcnow() - item.created_at).days <= 3
    )
    awaiting_approval = sum(1 for item in active_orders if item.status == "awaiting_client_approval")
    overdue_unfinished = sum(
        1
        for item in active_orders
        if item.due_date and item.due_date < today and item.status != "completed"
    )
    new_reservations = (
        db.query(ReservationModel)
        .filter(
            ReservationModel.tenant_id == int(current_user.tenant_id),
            ReservationModel.service_id == int(current_user.id),
            ReservationModel.status == "PENDING",
        )
        .count()
    )
    pending_quotes = (
        db.query(ServiceQuote)
        .filter(
            ServiceQuote.tenant_id == int(current_user.tenant_id),
            ServiceQuote.service_id == int(current_user.id),
            ServiceQuote.status.in_(("draft", "sent")),
        )
        .count()
    )
    draft_invoices = (
        db.query(ServiceInvoice)
        .filter(
            ServiceInvoice.tenant_id == int(current_user.tenant_id),
            ServiceInvoice.service_id == int(current_user.id),
            ServiceInvoice.status == "draft",
        )
        .count()
    )
    open_reminders = (
        db.query(ReminderModel)
        .join(
            ServiceCustomerLink,
            ServiceCustomerLink.customer_id == ReminderModel.customer_id,
        )
        .filter(
            ReminderModel.tenant_id == int(current_user.tenant_id),
            ReminderModel.is_completed.is_(False),
            ServiceCustomerLink.service_customer_id == int(current_user.id),
            ServiceCustomerLink.status == "active",
        )
        .count()
    )

    conflict_vehicle_ids: set[int] = set()
    for item in active_orders:
        if not item.vehicle_id or item.vehicle_id in conflict_vehicle_ids:
            continue
        timeline_summary = summarize_mileage_timeline(collect_vehicle_mileage_timeline_points(db, int(item.vehicle_id)))
        if int(timeline_summary.get("anomaly_point_count") or 0) > 0:
            conflict_vehicle_ids.add(int(item.vehicle_id))

    return {
        "new_orders": recent_new_orders,
        "new_jobs": recent_new_orders,
        "awaiting_approval": awaiting_approval,
        "missing_documents": missing_documents,
        "conflicting_data": len(conflict_vehicle_ids),
        "missing_client_consent": awaiting_approval,
        "suspicious_km": len(conflict_vehicle_ids),
        "unfinished_jobs": overdue_unfinished,
        "new_reservations": new_reservations,
        "pending_quotes": pending_quotes,
        "draft_invoices": draft_invoices,
        "open_reminders": open_reminders,
        "internal_warnings": 0,
        "alerts": [
            {
                "key": "missing_client_consent",
                "label": "Chybí souhlas klienta",
                "count": awaiting_approval,
            },
            {
                "key": "suspicious_km",
                "label": "Podezřelé km",
                "count": len(conflict_vehicle_ids),
            },
            {
                "key": "unfinished_jobs",
                "label": "Nedokončené zakázky",
                "count": overdue_unfinished,
            },
            {
                "key": "new_reservations",
                "label": "Nové rezervace",
                "count": new_reservations,
            },
            {
                "key": "pending_quotes",
                "label": "Čekající nabídky",
                "count": pending_quotes,
            },
            {
                "key": "draft_invoices",
                "label": "Draft faktury",
                "count": draft_invoices,
            },
            {
                "key": "open_reminders",
                "label": "Aktivní připomínky",
                "count": open_reminders,
            },
        ],
    }
