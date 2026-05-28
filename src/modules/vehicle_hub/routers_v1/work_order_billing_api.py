"""Work order → quote / invoice workflow (service billing layer)."""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit_log import write_global_audit_log
from ..database import get_db
from ..models import (
    Customer,
    ServiceInvoice,
    ServiceInvoiceLine,
    ServiceQuote,
    ServiceWorkOrder,
    ServiceWorkOrderItem,
    Vehicle as VehicleModel,
)
from .auth import get_current_user
from .service_invoices import (
    ServiceInvoiceLineIn,
    _audit as _invoice_audit,
    _build_lines_from_payload,
    _ensure_invoice_customer,
    _ensure_service_invoices_schema,
    _invoice_extra_json,
    _require_service_invoice_role,
    _resolve_invoice_labels,
    _serialize_invoice,
    _validate_service_invoice_links,
)
from .service_workspace import _require_service_workspace_role

WORK_ORDER_ITEM_LABOR = "labor"
WORK_ORDER_ITEM_PART = "part"
WORK_ORDER_ITEM_TIME = "time"


class WorkOrderInvoiceCreateRequest(BaseModel):
    """Optional billing customer for unowned work orders (must be linked service customer)."""

    billing_customer_id: Optional[int] = Field(default=None, gt=0)
    tax_rate: float = Field(default=21, ge=0, le=100)
    currency: str = Field(default="CZK", max_length=8)
    notes: Optional[str] = Field(default=None, max_length=8000)


def _active_work_order_items(db: Session, *, work_order_id: int) -> list[ServiceWorkOrderItem]:
    return (
        db.query(ServiceWorkOrderItem)
        .filter(
            ServiceWorkOrderItem.work_order_id == int(work_order_id),
            ServiceWorkOrderItem.deleted_at.is_(None),
        )
        .order_by(ServiceWorkOrderItem.id.asc())
        .all()
    )


def work_order_items_to_quote_items(rows: list[ServiceWorkOrderItem]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for row in rows:
        item_type = str(row.item_type or "").lower()
        if item_type == WORK_ORDER_ITEM_TIME:
            continue
        quantity = float(row.quantity or 0)
        if item_type == WORK_ORDER_ITEM_LABOR and quantity <= 0:
            quantity = 1.0
        unit_price = float(row.sale_price_without_vat or 0)
        total_price = round(quantity * unit_price, 2)
        unit_label = str(row.unit or "").strip() or ("h" if item_type == WORK_ORDER_ITEM_LABOR else "ks")
        name = str(row.name or "Položka").strip()
        if item_type == WORK_ORDER_ITEM_LABOR:
            name = f"{name} ({quantity:g} {unit_label})"
        items.append(
            {
                "name": name[:255],
                "quantity": round(quantity, 2),
                "unit_price": round(unit_price, 2),
                "total_price": total_price,
            }
        )
    return items


def work_order_items_to_invoice_lines(
    rows: list[ServiceWorkOrderItem],
    *,
    default_tax_rate: float,
) -> list[ServiceInvoiceLineIn]:
    lines: list[ServiceInvoiceLineIn] = []
    for row in rows:
        item_type = str(row.item_type or "").lower()
        if item_type == WORK_ORDER_ITEM_TIME:
            continue
        quantity = float(row.quantity or 0)
        if item_type == WORK_ORDER_ITEM_LABOR and quantity <= 0:
            quantity = 1.0
        if quantity <= 0:
            quantity = 1.0
        unit_price = float(row.sale_price_without_vat or 0)
        tax_rate = float(row.vat_rate if row.vat_rate is not None else default_tax_rate)
        unit = str(row.unit or "").strip() or ("h" if item_type == WORK_ORDER_ITEM_LABOR else "ks")
        lines.append(
            ServiceInvoiceLineIn(
                description=str(row.name or "Položka")[:512],
                quantity=quantity,
                unit=unit[:32],
                unit_price=unit_price,
                tax_rate=tax_rate,
            )
        )
    return lines


def _sum_labor_from_items(rows: list[ServiceWorkOrderItem]) -> tuple[Optional[float], Optional[float]]:
    hours = 0.0
    rate_weighted = 0.0
    for row in rows:
        if str(row.item_type or "").lower() != WORK_ORDER_ITEM_LABOR:
            continue
        qty = float(row.quantity or 0)
        hours += qty
        rate_weighted += qty * float(row.sale_price_without_vat or 0)
    if hours <= 0:
        return None, None
    return round(hours, 2), round(rate_weighted / hours, 2) if hours else None


def _linked_quote(db: Session, *, work_order_id: int, service_customer_id: int) -> Optional[ServiceQuote]:
    return (
        db.query(ServiceQuote)
        .filter(
            ServiceQuote.work_order_id == int(work_order_id),
            ServiceQuote.service_id == int(service_customer_id),
        )
        .order_by(ServiceQuote.updated_at.desc(), ServiceQuote.id.desc())
        .first()
    )


def quote_items_to_invoice_lines(
    items: list[dict[str, object]],
    *,
    default_tax_rate: float = 21,
) -> list[ServiceInvoiceLineIn]:
    lines: list[ServiceInvoiceLineIn] = []
    for item in items:
        quantity = float(item.get("quantity") or 0)
        if quantity <= 0:
            quantity = 1.0
        unit_price = float(item.get("unit_price") or 0)
        lines.append(
            ServiceInvoiceLineIn(
                description=str(item.get("name") or "Položka")[:512],
                quantity=quantity,
                unit="ks",
                unit_price=unit_price,
                tax_rate=float(default_tax_rate),
            )
        )
    return lines


def _invoice_for_work_order(
    db: Session,
    *,
    work_order_id: int,
    service_customer_id: int,
) -> Optional[ServiceInvoice]:
    return _linked_invoice(db, work_order_id=work_order_id, service_customer_id=service_customer_id)


def _linked_invoice(db: Session, *, work_order_id: int, service_customer_id: int) -> Optional[ServiceInvoice]:
    return (
        db.query(ServiceInvoice)
        .filter(
            ServiceInvoice.work_order_id == int(work_order_id),
            ServiceInvoice.service_id == int(service_customer_id),
        )
        .order_by(ServiceInvoice.updated_at.desc(), ServiceInvoice.id.desc())
        .first()
    )


def _serialize_invoice_summary(inv: ServiceInvoice) -> dict[str, object]:
    return {
        "invoice_id": int(inv.id),
        "status": str(inv.status or "draft"),
        "status_label": {"draft": "Koncept", "issued": "Vystaveno", "cancelled": "Zrušeno"}.get(
            str(inv.status or "").lower(),
            str(inv.status or "draft"),
        ),
        "total": float(inv.total or 0),
        "currency": str(inv.currency or "CZK"),
        "invoice_number": inv.invoice_number,
        "work_order_id": int(inv.work_order_id) if inv.work_order_id else None,
        "pdf_url": f"/api/service/invoices/{int(inv.id)}/pdf",
        "pdf_available": True,
        "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
    }


def _resolve_billing_customer_id(
    db: Session,
    *,
    current_user: Customer,
    order: ServiceWorkOrder,
    billing_customer_id: Optional[int],
) -> int:
    if order.owner_customer_id is not None:
        _ensure_invoice_customer(db, current_user=current_user, customer_id=int(order.owner_customer_id))
        if billing_customer_id is not None and int(billing_customer_id) != int(order.owner_customer_id):
            raise HTTPException(
                status_code=422,
                detail="billing_customer_id musí odpovídat majiteli zakázky.",
            )
        return int(order.owner_customer_id)
    if billing_customer_id is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unowned_requires_billing_customer",
                "message": "Pro vystavení faktury k nepřiřazenému vozidlu doplňte fakturační kontakt.",
            },
        )
    _ensure_invoice_customer(db, current_user=current_user, customer_id=int(billing_customer_id))
    return int(billing_customer_id)


def get_work_order_quote(
    work_order_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from . import service_dashboard as sd

    _require_service_workspace_role(current_user)
    sd._ensure_service_dashboard_schema(db)
    order = sd._get_work_order_or_404(db, current_user=current_user, work_order_id=work_order_id)
    quote = _linked_quote(db, work_order_id=int(order.id), service_customer_id=int(current_user.id))
    if not quote:
        return {"quote": None}
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(order.vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo zakázky nebylo nalezeno.")
    public_token = sd.get_active_quote_access_token(db, quote_id=int(quote.id))
    return {
        "quote": sd._serialize_quote_summary(
            quote,
            vehicle=vehicle,
            service_customer=current_user,
            public_token=public_token,
            work_order=order,
        )
    }


def create_work_order_quote(
    work_order_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from . import service_dashboard as sd

    _require_service_workspace_role(current_user)
    sd._ensure_service_dashboard_schema(db)
    order = sd._get_work_order_or_404(db, current_user=current_user, work_order_id=work_order_id)
    existing = _linked_quote(db, work_order_id=int(order.id), service_customer_id=int(current_user.id))
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "work_order_quote_exists",
                "message": "K této zakázce už existuje nabídka.",
                "quote_id": int(existing.id),
            },
        )

    owner, vehicle, _technician = sd._load_work_order_parties(db, order)
    rows = _active_work_order_items(db, work_order_id=int(order.id))
    if not rows:
        raise HTTPException(status_code=422, detail="Zakázka nemá žádné položky pro nabídku.")

    items = work_order_items_to_quote_items(rows)
    labor_hours, labor_rate = _sum_labor_from_items(rows)
    total_price = round(sum(float(item["total_price"]) for item in items), 2)

    quote = ServiceQuote(
        tenant_id=int(order.tenant_id),
        vehicle_id=int(order.vehicle_id),
        customer_id=int(owner.id) if owner else None,
        service_id=int(current_user.id),
        work_order_id=int(order.id),
        service_record_id=None,
        items_json=json.dumps(items, ensure_ascii=False),
        labor_hours=labor_hours,
        labor_rate=labor_rate,
        total_price=total_price,
        status=sd._normalize_quote_status("draft"),
    )
    db.add(quote)
    db.flush()
    sd._write_quote_audit(
        db,
        quote=quote,
        action="quote_created",
        actor=current_user,
        previous_snapshot={},
        new_snapshot=sd._quote_snapshot(quote),
    )
    write_global_audit_log(
        db,
        entity_type="service_quote",
        entity_id=int(quote.id),
        action="quote_created_from_work_order",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(order.tenant_id),
        vehicle_id=int(order.vehicle_id),
        metadata={"work_order_id": int(order.id), "total_price": total_price},
    )
    sd._sync_work_order_status_from_quote(db, quote=quote, actor=current_user, action="quote_status_change")
    sd._sync_work_order_on_quote_rejected(
        db,
        quote=quote,
        actor=current_user,
        audit_action="quote_rejected_work_order_sync",
    )
    access_token = sd.ensure_quote_access_token(db, quote=quote, created_by_user_id=getattr(current_user, "id", None))
    db.commit()
    db.refresh(quote)
    return sd._serialize_quote(quote, owner=owner, vehicle=vehicle, service_customer=current_user, public_token=access_token)


def get_work_order_invoice(
    work_order_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)
    from . import service_dashboard as sd

    order = sd._get_work_order_or_404(db, current_user=current_user, work_order_id=work_order_id)
    inv = _linked_invoice(db, work_order_id=int(order.id), service_customer_id=int(current_user.id))
    if not inv:
        return {"invoice": None}
    return {"invoice": _serialize_invoice_summary(inv)}


def create_work_order_invoice(
    work_order_id: int,
    payload: WorkOrderInvoiceCreateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)
    from . import service_dashboard as sd

    order = sd._get_work_order_or_404(db, current_user=current_user, work_order_id=work_order_id)
    existing = _linked_invoice(db, work_order_id=int(order.id), service_customer_id=int(current_user.id))
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "work_order_invoice_exists",
                "message": "K této zakázce už existuje faktura.",
                "invoice_id": int(existing.id),
            },
        )

    customer_id = _resolve_billing_customer_id(
        db,
        current_user=current_user,
        order=order,
        billing_customer_id=payload.billing_customer_id,
    )
    rows = _active_work_order_items(db, work_order_id=int(order.id))
    if not rows:
        raise HTTPException(status_code=422, detail="Zakázka nemá žádné položky pro fakturu.")

    line_payloads = work_order_items_to_invoice_lines(rows, default_tax_rate=float(payload.tax_rate))
    _validate_service_invoice_links(
        db,
        tenant_id=int(current_user.tenant_id),
        vehicle_id=int(order.vehicle_id),
        service_record_id=None,
        work_order_id=int(order.id),
    )

    inv = ServiceInvoice(
        tenant_id=int(current_user.tenant_id),
        service_id=int(current_user.id),
        customer_id=int(customer_id),
        vehicle_id=int(order.vehicle_id),
        service_record_id=None,
        work_order_id=int(order.id),
        status="draft",
        subtotal=0,
        tax_total=0,
        total=0,
        currency=str(payload.currency or "CZK").strip()[:8] or "CZK",
        notes=(str(payload.notes).strip() if payload.notes else None),
        extra_json=_invoice_extra_json({"work_order_billing": True}),
    )
    db.add(inv)
    db.flush()

    line_rows, sub, tax, tot = _build_lines_from_payload(
        db,
        tenant_id=int(current_user.tenant_id),
        invoice_id=int(inv.id),
        items=line_payloads,
    )
    for lr in line_rows:
        db.add(lr)
    inv.subtotal = sub
    inv.tax_total = tax
    inv.total = tot
    db.flush()

    _invoice_audit(
        db,
        invoice=inv,
        action="invoice_created",
        actor=current_user,
        metadata={
            "work_order_id": int(order.id),
            "vehicle_id": int(order.vehicle_id),
            "customer_id": int(customer_id),
            "source": "work_order",
        },
    )
    write_global_audit_log(
        db,
        entity_type="service_invoice",
        entity_id=int(inv.id),
        action="invoice_created_from_work_order",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(inv.tenant_id),
        vehicle_id=int(order.vehicle_id),
        metadata={"work_order_id": int(order.id), "total": float(inv.total or 0)},
    )
    db.commit()
    db.refresh(inv)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
    return _serialize_invoice(inv, lines, customer_label=customer_label, vehicle_label=vehicle_label)


def list_service_billing_quotes(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from . import service_dashboard as sd

    _require_service_workspace_role(current_user)
    sd._ensure_service_dashboard_schema(db)
    rows = (
        db.query(ServiceQuote)
        .filter(
            ServiceQuote.service_id == int(current_user.id),
            ServiceQuote.tenant_id == int(current_user.tenant_id),
        )
        .order_by(ServiceQuote.updated_at.desc(), ServiceQuote.id.desc())
        .limit(250)
        .all()
    )
    items: list[dict[str, Any]] = []
    for quote in rows:
        vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(quote.vehicle_id)).first()
        if not vehicle:
            continue
        work_order = None
        if quote.work_order_id:
            work_order = db.query(ServiceWorkOrder).filter(ServiceWorkOrder.id == int(quote.work_order_id)).first()
        public_token = sd.get_active_quote_access_token(db, quote_id=int(quote.id))
        items.append(
            sd._serialize_quote_summary(
                quote,
                vehicle=vehicle,
                service_customer=current_user,
                public_token=public_token,
                work_order=work_order,
            )
        )
    return {"items": items, "count": len(items)}


def register_work_order_billing_routes(router: APIRouter) -> None:
    router.get("/quotes")(list_service_billing_quotes)
    router.get("/work-orders/{work_order_id}/quote")(get_work_order_quote)
    router.post("/work-orders/{work_order_id}/quote")(create_work_order_quote)
    router.get("/work-orders/{work_order_id}/invoice")(get_work_order_invoice)
    router.post("/work-orders/{work_order_id}/invoice")(create_work_order_invoice)
