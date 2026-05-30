"""Service parts inventory — catalog, stock levels, movements."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit_log import write_global_audit_log
from ..database import get_db
from ..models import Customer, ServiceInventoryItem, ServiceInventoryMovement
from .auth import get_current_user
from .service_workspace import _require_service_workspace_role


class ServiceInventoryItemCreateRequest(BaseModel):
    internal_code: Optional[str] = Field(default=None, max_length=128)
    name: str = Field(..., min_length=1, max_length=512)
    description: Optional[str] = Field(default=None, max_length=4000)
    brand: Optional[str] = Field(default=None, max_length=255)
    supplier_name: Optional[str] = Field(default=None, max_length=255)
    unit: str = Field(default="ks", min_length=1, max_length=32)
    quantity_on_hand: float = Field(default=0, ge=0)
    min_quantity: float = Field(default=0, ge=0)
    purchase_price: Optional[float] = Field(default=None, ge=0)
    sale_price: Optional[float] = Field(default=None, ge=0)
    vat_rate: Optional[float] = Field(default=None, ge=0, le=100)
    location: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = True


class ServiceInventoryItemUpdateRequest(BaseModel):
    internal_code: Optional[str] = Field(default=None, max_length=128)
    name: Optional[str] = Field(default=None, min_length=1, max_length=512)
    description: Optional[str] = Field(default=None, max_length=4000)
    brand: Optional[str] = Field(default=None, max_length=255)
    supplier_name: Optional[str] = Field(default=None, max_length=255)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=32)
    min_quantity: Optional[float] = Field(default=None, ge=0)
    purchase_price: Optional[float] = Field(default=None, ge=0)
    sale_price: Optional[float] = Field(default=None, ge=0)
    vat_rate: Optional[float] = Field(default=None, ge=0, le=100)
    location: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None


class ServiceInventoryAdjustRequest(BaseModel):
    quantity_delta: float = Field(..., ge=-999999, le=999999)
    reason: Optional[str] = Field(default=None, max_length=2000)


def _ensure_inventory_schema(db: Session) -> None:
    from . import service_dashboard as sd

    sd._ensure_service_dashboard_schema(db)


def _inventory_scope(db: Session, current_user: Customer):
    return db.query(ServiceInventoryItem).filter(
        ServiceInventoryItem.service_customer_id == int(current_user.id),
        ServiceInventoryItem.service_tenant_id == int(current_user.tenant_id),
    )


def get_inventory_item_for_service(
    db: Session,
    current_user: Customer,
    inventory_item_id: int,
) -> ServiceInventoryItem:
    item = (
        _inventory_scope(db, current_user)
        .filter(ServiceInventoryItem.id == int(inventory_item_id))
        .first()
    )
    if not item:
        write_global_audit_log(
            db,
            entity_type="service_inventory_item",
            entity_id=int(inventory_item_id),
            action="inventory_forbidden_access",
            actor_user_id=int(current_user.id),
            actor_role=getattr(current_user, "role", None),
            tenant_id=int(current_user.tenant_id),
            metadata={"inventory_item_id": int(inventory_item_id)},
        )
        raise HTTPException(status_code=404, detail="Skladová položka nebyla nalezena.")
    if not item.is_active:
        raise HTTPException(status_code=422, detail="Skladová položka není aktivní.")
    return item


def _serialize_inventory_item(item: ServiceInventoryItem) -> dict[str, object]:
    qty = float(item.quantity_on_hand or 0)
    min_qty = float(item.min_quantity or 0)
    return {
        "id": int(item.id),
        "internal_code": item.internal_code,
        "name": str(item.name),
        "description": item.description,
        "brand": item.brand,
        "supplier_name": item.supplier_name,
        "unit": str(item.unit or "ks"),
        "quantity_on_hand": qty,
        "min_quantity": min_qty,
        "purchase_price": float(item.purchase_price) if item.purchase_price is not None else None,
        "sale_price": float(item.sale_price) if item.sale_price is not None else None,
        "vat_rate": float(item.vat_rate) if item.vat_rate is not None else None,
        "location": item.location,
        "is_active": bool(item.is_active),
        "is_low_stock": qty <= min_qty,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _serialize_movement(row: ServiceInventoryMovement) -> dict[str, object]:
    return {
        "id": int(row.id),
        "inventory_item_id": int(row.inventory_item_id),
        "work_order_id": int(row.work_order_id) if row.work_order_id else None,
        "work_order_item_id": int(row.work_order_item_id) if row.work_order_item_id else None,
        "movement_type": str(row.movement_type),
        "quantity_delta": float(row.quantity_delta),
        "quantity_before": float(row.quantity_before),
        "quantity_after": float(row.quantity_after),
        "reason": row.reason,
        "actor_id": int(row.actor_id) if row.actor_id else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _record_movement(
    db: Session,
    *,
    item: ServiceInventoryItem,
    actor: Customer,
    movement_type: str,
    quantity_delta: float,
    quantity_before: float,
    quantity_after: float,
    reason: Optional[str],
    work_order_id: Optional[int] = None,
    work_order_item_id: Optional[int] = None,
) -> ServiceInventoryMovement:
    movement = ServiceInventoryMovement(
        service_tenant_id=int(item.service_tenant_id),
        inventory_item_id=int(item.id),
        work_order_id=work_order_id,
        work_order_item_id=work_order_item_id,
        movement_type=str(movement_type),
        quantity_delta=float(quantity_delta),
        quantity_before=float(quantity_before),
        quantity_after=float(quantity_after),
        reason=reason,
        actor_id=int(actor.id),
    )
    db.add(movement)
    db.flush()
    return movement


def decrement_inventory_for_work_order(
    db: Session,
    *,
    inventory_item: ServiceInventoryItem,
    quantity: float,
    actor: Customer,
    work_order_id: int,
    work_order_item_id: int,
    reason: Optional[str] = None,
) -> None:
    before = float(inventory_item.quantity_on_hand or 0)
    if before < float(quantity):
        write_global_audit_log(
            db,
            entity_type="service_inventory_item",
            entity_id=int(inventory_item.id),
            action="inventory_insufficient_stock",
            actor_user_id=int(actor.id),
            actor_role=getattr(actor, "role", None),
            tenant_id=int(inventory_item.service_tenant_id),
            metadata={
                "requested": float(quantity),
                "available": before,
                "work_order_id": int(work_order_id),
            },
        )
        raise HTTPException(status_code=422, detail="Nedostatečné množství na skladě.")
    after = before - float(quantity)
    inventory_item.quantity_on_hand = after
    inventory_item.updated_at = datetime.utcnow()
    _record_movement(
        db,
        item=inventory_item,
        actor=actor,
        movement_type="out",
        quantity_delta=-float(quantity),
        quantity_before=before,
        quantity_after=after,
        reason=reason or "Odpis na zakázku",
        work_order_id=int(work_order_id),
        work_order_item_id=int(work_order_item_id),
    )
    write_global_audit_log(
        db,
        entity_type="service_inventory_item",
        entity_id=int(inventory_item.id),
        action="inventory_stock_decremented",
        actor_user_id=int(actor.id),
        actor_role=getattr(actor, "role", None),
        tenant_id=int(inventory_item.service_tenant_id),
        metadata={
            "quantity": float(quantity),
            "quantity_before": before,
            "quantity_after": after,
            "work_order_id": int(work_order_id),
            "work_order_item_id": int(work_order_item_id),
        },
    )


def return_inventory_for_work_order_item(
    db: Session,
    *,
    inventory_item: ServiceInventoryItem,
    quantity: float,
    actor: Customer,
    work_order_id: int,
    work_order_item_id: int,
    reason: Optional[str] = None,
) -> None:
    qty = float(quantity)
    if qty <= 0:
        return
    before = float(inventory_item.quantity_on_hand or 0)
    after = before + qty
    inventory_item.quantity_on_hand = after
    inventory_item.updated_at = datetime.utcnow()
    _record_movement(
        db,
        item=inventory_item,
        actor=actor,
        movement_type="return",
        quantity_delta=qty,
        quantity_before=before,
        quantity_after=after,
        reason=reason or "Vrácení ze zakázky",
        work_order_id=int(work_order_id),
        work_order_item_id=int(work_order_item_id),
    )
    write_global_audit_log(
        db,
        entity_type="service_inventory_item",
        entity_id=int(inventory_item.id),
        action="inventory_stock_returned",
        actor_user_id=int(actor.id),
        actor_role=getattr(actor, "role", None),
        tenant_id=int(inventory_item.service_tenant_id),
        metadata={
            "quantity": qty,
            "quantity_before": before,
            "quantity_after": after,
            "work_order_id": int(work_order_id),
            "work_order_item_id": int(work_order_item_id),
        },
    )


def adjust_inventory_for_work_order_item(
    db: Session,
    *,
    inventory_item: ServiceInventoryItem,
    quantity_delta: float,
    actor: Customer,
    work_order_id: int,
    work_order_item_id: int,
    reason: Optional[str] = None,
) -> None:
    """Positive delta consumes stock; negative delta returns stock."""
    delta = float(quantity_delta)
    if delta == 0:
        return
    before = float(inventory_item.quantity_on_hand or 0)
    if delta > 0:
        if before < delta:
            write_global_audit_log(
                db,
                entity_type="service_inventory_item",
                entity_id=int(inventory_item.id),
                action="inventory_insufficient_stock",
                actor_user_id=int(actor.id),
                actor_role=getattr(actor, "role", None),
                tenant_id=int(inventory_item.service_tenant_id),
                metadata={
                    "requested": delta,
                    "available": before,
                    "work_order_id": int(work_order_id),
                    "work_order_item_id": int(work_order_item_id),
                },
            )
            raise HTTPException(status_code=422, detail="Nedostatečné množství na skladě.")
        after = before - delta
        movement_type = "out"
        movement_delta = -delta
        audit_action = "inventory_stock_decremented"
    else:
        after = before - delta
        movement_type = "return"
        movement_delta = -delta
        audit_action = "inventory_stock_returned"
    inventory_item.quantity_on_hand = after
    inventory_item.updated_at = datetime.utcnow()
    _record_movement(
        db,
        item=inventory_item,
        actor=actor,
        movement_type=movement_type,
        quantity_delta=movement_delta,
        quantity_before=before,
        quantity_after=after,
        reason=reason or "Úprava položky zakázky",
        work_order_id=int(work_order_id),
        work_order_item_id=int(work_order_item_id),
    )
    write_global_audit_log(
        db,
        entity_type="service_inventory_item",
        entity_id=int(inventory_item.id),
        action=audit_action,
        actor_user_id=int(actor.id),
        actor_role=getattr(actor, "role", None),
        tenant_id=int(inventory_item.service_tenant_id),
        metadata={
            "quantity_delta": delta,
            "quantity_before": before,
            "quantity_after": after,
            "work_order_id": int(work_order_id),
            "work_order_item_id": int(work_order_item_id),
        },
    )


def list_inventory_items(
    q: Optional[str] = Query(default=None, max_length=200),
    low_stock: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=500),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_inventory_schema(db)
    query = _inventory_scope(db, current_user).filter(ServiceInventoryItem.is_active.is_(True))
    if q and str(q).strip():
        term = f"%{str(q).strip().lower()}%"
        query = query.filter(
            func.lower(ServiceInventoryItem.name).like(term)
            | func.lower(func.coalesce(ServiceInventoryItem.internal_code, "")).like(term)
            | func.lower(func.coalesce(ServiceInventoryItem.brand, "")).like(term)
        )
    rows = query.order_by(ServiceInventoryItem.name.asc(), ServiceInventoryItem.id.asc()).limit(limit).all()
    items = [_serialize_inventory_item(row) for row in rows]
    if low_stock:
        items = [item for item in items if item.get("is_low_stock")]
    return {"items": items, "count": len(items)}


def create_inventory_item(
    payload: ServiceInventoryItemCreateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_inventory_schema(db)
    item = ServiceInventoryItem(
        service_tenant_id=int(current_user.tenant_id),
        service_customer_id=int(current_user.id),
        internal_code=(str(payload.internal_code).strip() if payload.internal_code else None),
        name=str(payload.name).strip(),
        description=(str(payload.description).strip() if payload.description else None),
        brand=(str(payload.brand).strip() if payload.brand else None),
        supplier_name=(str(payload.supplier_name).strip() if payload.supplier_name else None),
        unit=str(payload.unit or "ks").strip() or "ks",
        quantity_on_hand=float(payload.quantity_on_hand or 0),
        min_quantity=float(payload.min_quantity or 0),
        purchase_price=float(payload.purchase_price) if payload.purchase_price is not None else None,
        sale_price=float(payload.sale_price) if payload.sale_price is not None else None,
        vat_rate=float(payload.vat_rate) if payload.vat_rate is not None else None,
        location=(str(payload.location).strip() if payload.location else None),
        is_active=bool(payload.is_active),
    )
    db.add(item)
    db.flush()
    if float(item.quantity_on_hand or 0) > 0:
        _record_movement(
            db,
            item=item,
            actor=current_user,
            movement_type="in",
            quantity_delta=float(item.quantity_on_hand),
            quantity_before=0.0,
            quantity_after=float(item.quantity_on_hand),
            reason="Počáteční stav skladu",
        )
    write_global_audit_log(
        db,
        entity_type="service_inventory_item",
        entity_id=int(item.id),
        action="inventory_item_created",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(current_user.tenant_id),
        metadata={"name": item.name, "internal_code": item.internal_code},
    )
    db.commit()
    db.refresh(item)
    return _serialize_inventory_item(item)


def get_inventory_item(
    item_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_inventory_schema(db)
    item = get_inventory_item_for_service(db, current_user, item_id)
    return _serialize_inventory_item(item)


def update_inventory_item(
    item_id: int,
    payload: ServiceInventoryItemUpdateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_inventory_schema(db)
    item = get_inventory_item_for_service(db, current_user, item_id)
    previous = _serialize_inventory_item(item)
    if payload.internal_code is not None:
        item.internal_code = str(payload.internal_code).strip() or None
    if payload.name is not None:
        item.name = str(payload.name).strip()
    if payload.description is not None:
        item.description = str(payload.description).strip() or None
    if payload.brand is not None:
        item.brand = str(payload.brand).strip() or None
    if payload.supplier_name is not None:
        item.supplier_name = str(payload.supplier_name).strip() or None
    if payload.unit is not None:
        item.unit = str(payload.unit).strip() or "ks"
    if payload.min_quantity is not None:
        item.min_quantity = float(payload.min_quantity)
    if payload.purchase_price is not None:
        item.purchase_price = float(payload.purchase_price)
    if payload.sale_price is not None:
        item.sale_price = float(payload.sale_price)
    if payload.vat_rate is not None:
        item.vat_rate = float(payload.vat_rate)
    if payload.location is not None:
        item.location = str(payload.location).strip() or None
    if payload.is_active is not None:
        item.is_active = bool(payload.is_active)
    item.updated_at = datetime.utcnow()
    write_global_audit_log(
        db,
        entity_type="service_inventory_item",
        entity_id=int(item.id),
        action="inventory_item_updated",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(current_user.tenant_id),
        metadata={"previous": previous, "next": _serialize_inventory_item(item)},
    )
    db.commit()
    db.refresh(item)
    return _serialize_inventory_item(item)


def adjust_inventory_item(
    item_id: int,
    payload: ServiceInventoryAdjustRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_inventory_schema(db)
    item = get_inventory_item_for_service(db, current_user, item_id)
    before = float(item.quantity_on_hand or 0)
    after = before + float(payload.quantity_delta)
    if after < 0:
        raise HTTPException(status_code=422, detail="Úprava by vedla k zápornému stavu skladu.")
    item.quantity_on_hand = after
    item.updated_at = datetime.utcnow()
    movement_type = "adjustment"
    if float(payload.quantity_delta) > 0:
        movement_type = "in"
    elif float(payload.quantity_delta) < 0:
        movement_type = "out"
    _record_movement(
        db,
        item=item,
        actor=current_user,
        movement_type=movement_type,
        quantity_delta=float(payload.quantity_delta),
        quantity_before=before,
        quantity_after=after,
        reason=(str(payload.reason).strip() if payload.reason else "Ruční úprava skladu"),
    )
    write_global_audit_log(
        db,
        entity_type="service_inventory_item",
        entity_id=int(item.id),
        action="inventory_adjusted",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(current_user.tenant_id),
        metadata={
            "quantity_delta": float(payload.quantity_delta),
            "quantity_before": before,
            "quantity_after": after,
        },
    )
    db.commit()
    db.refresh(item)
    return _serialize_inventory_item(item)


def list_inventory_movements(
    item_id: Optional[int] = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_inventory_schema(db)
    query = (
        db.query(ServiceInventoryMovement)
        .filter(ServiceInventoryMovement.service_tenant_id == int(current_user.tenant_id))
        .join(ServiceInventoryItem, ServiceInventoryItem.id == ServiceInventoryMovement.inventory_item_id)
        .filter(ServiceInventoryItem.service_customer_id == int(current_user.id))
    )
    if item_id:
        query = query.filter(ServiceInventoryMovement.inventory_item_id == int(item_id))
    rows = query.order_by(ServiceInventoryMovement.created_at.desc(), ServiceInventoryMovement.id.desc()).limit(limit).all()
    return {"items": [_serialize_movement(row) for row in rows], "count": len(rows)}


def register_inventory_routes(router: APIRouter) -> None:
    router.add_api_route("/inventory/items", list_inventory_items, methods=["GET"])
    router.add_api_route("/inventory/items", create_inventory_item, methods=["POST"])
    router.add_api_route("/inventory/items/{item_id}", get_inventory_item, methods=["GET"])
    router.add_api_route("/inventory/items/{item_id}", update_inventory_item, methods=["PUT"])
    router.add_api_route("/inventory/items/{item_id}/adjust", adjust_inventory_item, methods=["POST"])
    router.add_api_route("/inventory/movements", list_inventory_movements, methods=["GET"])
