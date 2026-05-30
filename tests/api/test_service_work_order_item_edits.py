from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.central_vehicle_identity import build_owner_safe_service_history
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceCustomerLink,
    ServiceInventoryItem,
    ServiceInventoryMovement,
    ServiceWorkOrderItem,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.routers_v1 import service_dashboard as dashboard_router
from src.modules.vehicle_hub.routers_v1 import service_inventory_api as inventory_router
from src.modules.vehicle_hub.routers_v1.work_order_items_api import (
    ServiceWorkOrderItemUpdateRequest,
    ServiceWorkOrderPartCreateRequest,
    add_work_order_part,
    complete_work_order,
    delete_work_order_item,
    update_work_order_item,
)


def _service_user(service: Customer) -> SimpleNamespace:
    return SimpleNamespace(
        id=service.id,
        email=service.email,
        role="service",
        name=service.name,
        tenant_id=service.tenant_id,
    )


def _seed_ctx(tmp_path: Path):
    db_path = tmp_path / "wo_item_edits.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    tenant = Tenant(name="WO Edits Tenant", license_key="wo-edits-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(tenant_id=tenant.id, email="owner-edits@example.com", password_hash="x", role="user", name="Owner")
    service = Customer(tenant_id=tenant.id, email="service-edits@example.com", password_hash="x", role="service", name="Service")
    foreign_service = Customer(
        tenant_id=tenant.id,
        email="foreign-edits@example.com",
        password_hash="x",
        role="service",
        name="Foreign Service",
    )
    db.add_all([owner, service, foreign_service])
    db.commit()
    db.refresh(owner)
    db.refresh(service)
    db.refresh(foreign_service)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        brand="Skoda",
        model="Fabia",
        vin="TMBEDIT1234567890",
        plate="1ED1234",
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    db.add(
        VehicleOwnership(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            ownership_type="owner",
            ownership_origin="manual",
            is_primary=True,
            is_active=True,
        )
    )
    db.add(
        ServiceCustomerLink(
            service_tenant_id=tenant.id,
            service_customer_id=service.id,
            customer_tenant_id=tenant.id,
            customer_id=owner.id,
            status="active",
        )
    )
    db.add(
        VehicleServiceLink(
            tenant_id=tenant.id,
            service_customer_id=service.id,
            owner_customer_id=owner.id,
            vehicle_id=vehicle.id,
            status="approved",
            approved_at=datetime.utcnow(),
            approved_by_customer_id=owner.id,
        )
    )
    db.commit()
    return engine, db, owner, service, foreign_service, vehicle


def _create_work_order(db, owner, service, vehicle):
    return dashboard_router.create_service_work_order(
        payload=dashboard_router.ServiceWorkOrderCreateRequest(
            owner_id=owner.id,
            vehicle_id=vehicle.id,
            technician_id=service.id,
            title="Edit WO",
            status="approved",
        ),
        current_user=_service_user(service),
        db=db,
    )


def _add_manual_part(db, owner, service, vehicle, *, name="Ruční díl", quantity=1.0):
    wo = _create_work_order(db, owner, service, vehicle)
    item = add_work_order_part(
        int(wo["id"]),
        ServiceWorkOrderPartCreateRequest(name=name, quantity=quantity, unit="ks"),
        current_user=_service_user(service),
        db=db,
    )
    return wo, item


def _add_inventory_part(db, service, wo_id, *, inventory_item_id, quantity=1.0):
    return add_work_order_part(
        int(wo_id),
        ServiceWorkOrderPartCreateRequest(inventory_item_id=int(inventory_item_id), quantity=quantity),
        current_user=_service_user(service),
        db=db,
    )


def test_update_manual_part(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        wo, item = _add_manual_part(db, owner, service, vehicle)
        updated = update_work_order_item(
            int(wo["id"]),
            int(item["id"]),
            ServiceWorkOrderItemUpdateRequest(name="Upravený díl", quantity=2, unit="ks"),
            current_user=_service_user(service),
            db=db,
        )
        assert updated["name"] == "Upravený díl"
        assert updated["quantity"] == 2
    finally:
        db.close()
        engine.dispose()


def test_delete_manual_part(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        wo, item = _add_manual_part(db, owner, service, vehicle)
        result = delete_work_order_item(
            int(wo["id"]),
            int(item["id"]),
            current_user=_service_user(service),
            db=db,
        )
        assert result["deleted"] is True
        row = db.query(ServiceWorkOrderItem).filter(ServiceWorkOrderItem.id == int(item["id"])).one()
        assert row.deleted_at is not None
    finally:
        db.close()
        engine.dispose()


def test_update_inventory_part_decreases_stock(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        inv = inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(name="Filtr", quantity_on_hand=10),
            current_user=service,
            db=db,
        )
        wo = _create_work_order(db, owner, service, vehicle)
        item = _add_inventory_part(db, service, wo["id"], inventory_item_id=inv["id"], quantity=4)
        update_work_order_item(
            int(wo["id"]),
            int(item["id"]),
            ServiceWorkOrderItemUpdateRequest(quantity=2),
            current_user=_service_user(service),
            db=db,
        )
        row = db.query(ServiceInventoryItem).filter(ServiceInventoryItem.id == int(inv["id"])).one()
        assert row.quantity_on_hand == 8
        assert db.query(ServiceInventoryMovement).filter(ServiceInventoryMovement.movement_type == "return").count() >= 1
    finally:
        db.close()
        engine.dispose()


def test_update_inventory_part_increases_stock(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        inv = inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(name="Olej", quantity_on_hand=10),
            current_user=service,
            db=db,
        )
        wo = _create_work_order(db, owner, service, vehicle)
        item = _add_inventory_part(db, service, wo["id"], inventory_item_id=inv["id"], quantity=2)
        update_work_order_item(
            int(wo["id"]),
            int(item["id"]),
            ServiceWorkOrderItemUpdateRequest(quantity=5),
            current_user=_service_user(service),
            db=db,
        )
        row = db.query(ServiceInventoryItem).filter(ServiceInventoryItem.id == int(inv["id"])).one()
        assert row.quantity_on_hand == 5
        assert db.query(ServiceInventoryMovement).filter(ServiceInventoryMovement.movement_type == "out").count() >= 1
    finally:
        db.close()
        engine.dispose()


def test_delete_inventory_part_restores_stock(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        inv = inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(name="Svíčka", quantity_on_hand=6),
            current_user=service,
            db=db,
        )
        wo = _create_work_order(db, owner, service, vehicle)
        item = _add_inventory_part(db, service, wo["id"], inventory_item_id=inv["id"], quantity=3)
        delete_work_order_item(
            int(wo["id"]),
            int(item["id"]),
            current_user=_service_user(service),
            db=db,
        )
        row = db.query(ServiceInventoryItem).filter(ServiceInventoryItem.id == int(inv["id"])).one()
        assert row.quantity_on_hand == 6
        assert db.query(ServiceInventoryMovement).filter(ServiceInventoryMovement.movement_type == "return").count() >= 1
    finally:
        db.close()
        engine.dispose()


def test_insufficient_stock_update_returns_422_no_partial_write(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        inv = inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(name="Disk", quantity_on_hand=2),
            current_user=service,
            db=db,
        )
        wo = _create_work_order(db, owner, service, vehicle)
        item = _add_inventory_part(db, service, wo["id"], inventory_item_id=inv["id"], quantity=1)
        stock_before = db.query(ServiceInventoryItem).filter(ServiceInventoryItem.id == int(inv["id"])).one().quantity_on_hand
        movements_before = db.query(ServiceInventoryMovement).count()
        with pytest.raises(HTTPException) as err:
            update_work_order_item(
                int(wo["id"]),
                int(item["id"]),
                ServiceWorkOrderItemUpdateRequest(quantity=10),
                current_user=_service_user(service),
                db=db,
            )
        assert err.value.status_code == 422
        row = db.query(ServiceWorkOrderItem).filter(ServiceWorkOrderItem.id == int(item["id"])).one()
        assert float(row.quantity or 0) == 1
        stock_after = db.query(ServiceInventoryItem).filter(ServiceInventoryItem.id == int(inv["id"])).one().quantity_on_hand
        assert stock_after == stock_before
        assert db.query(ServiceInventoryMovement).count() == movements_before
    finally:
        db.close()
        engine.dispose()


def test_cannot_edit_cross_service_item(tmp_path: Path) -> None:
    engine, db, owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        wo, item = _add_manual_part(db, owner, service, vehicle)
        with pytest.raises(HTTPException) as err:
            update_work_order_item(
                int(wo["id"]),
                int(item["id"]),
                ServiceWorkOrderItemUpdateRequest(name="Hack"),
                current_user=_service_user(foreign_service),
                db=db,
            )
        assert err.value.status_code == 404
        with pytest.raises(HTTPException) as err2:
            delete_work_order_item(
                int(wo["id"]),
                int(item["id"]),
                current_user=_service_user(foreign_service),
                db=db,
            )
        assert err2.value.status_code == 404
    finally:
        db.close()
        engine.dispose()


def test_cannot_edit_closed_work_order(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        wo, item = _add_manual_part(db, owner, service, vehicle)
        complete_work_order(int(wo["id"]), current_user=_service_user(service), db=db)
        with pytest.raises(HTTPException) as err:
            update_work_order_item(
                int(wo["id"]),
                int(item["id"]),
                ServiceWorkOrderItemUpdateRequest(name="Pozdě"),
                current_user=_service_user(service),
                db=db,
            )
        assert err.value.status_code == 422
        with pytest.raises(HTTPException) as err2:
            delete_work_order_item(
                int(wo["id"]),
                int(item["id"]),
                current_user=_service_user(service),
                db=db,
            )
        assert err2.value.status_code == 422
    finally:
        db.close()
        engine.dispose()


def test_owner_safe_history_no_prices_inventory_data_after_edit(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        inv = inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(
                name="Tajný díl",
                quantity_on_hand=5,
                purchase_price=888,
                supplier_name="Tajný dodavatel",
            ),
            current_user=service,
            db=db,
        )
        wo = _create_work_order(db, owner, service, vehicle)
        item = _add_inventory_part(
            db,
            service,
            wo["id"],
            inventory_item_id=inv["id"],
            quantity=1,
        )
        update_work_order_item(
            int(wo["id"]),
            int(item["id"]),
            ServiceWorkOrderItemUpdateRequest(name="Veřejný název", unit_price_without_vat=500),
            current_user=_service_user(service),
            db=db,
        )
        history = build_owner_safe_service_history(db, vehicle_id=int(vehicle.id), owner_customer_id=int(owner.id))
        blob = json.dumps(history, ensure_ascii=False).lower()
        assert "888" not in blob
        assert "tajný dodavatel" not in blob
        assert "inventory_item_id" not in blob
        assert "purchase_price" not in blob
        assert "500" not in blob
    finally:
        db.close()
        engine.dispose()
