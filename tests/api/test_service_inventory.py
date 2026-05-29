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
    ServiceRecord,
    ServiceWorkOrderItem,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.routers_v1 import service_dashboard as dashboard_router
from src.modules.vehicle_hub.routers_v1 import service_inventory_api as inventory_router
from src.modules.vehicle_hub.routers_v1.work_order_billing_api import work_order_items_to_quote_items
from src.modules.vehicle_hub.routers_v1.work_order_items_api import (
    ServiceWorkOrderPartCreateRequest,
    add_work_order_part,
    complete_work_order,
    create_service_record_from_work_order,
    ServiceWorkOrderCreateRecordRequest,
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
    db_path = tmp_path / "service_inventory.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    tenant = Tenant(name="Inventory Tenant", license_key="inventory-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(tenant_id=tenant.id, email="owner@example.com", password_hash="x", role="user", name="Owner")
    service = Customer(tenant_id=tenant.id, email="service@example.com", password_hash="x", role="service", name="Service")
    foreign_service = Customer(
        tenant_id=tenant.id,
        email="foreign@example.com",
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
        model="Octavia",
        vin="TMBINV1234567890",
        plate="1IN1234",
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
            title="Inventory WO",
            status="approved",
        ),
        current_user=_service_user(service),
        db=db,
    )


def test_service_inventory_create_item(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        created = inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(
                internal_code="FIL-001",
                name="Filtr oleje",
                quantity_on_hand=5,
                min_quantity=2,
                purchase_price=120,
                sale_price=250,
                supplier_name="Dodavatel X",
            ),
            current_user=service,
            db=db,
        )
        assert created["name"] == "Filtr oleje"
        assert created["quantity_on_hand"] == 5
        assert db.query(ServiceInventoryMovement).count() == 1
    finally:
        db.close()
        engine.dispose()


def test_service_inventory_update_item(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        created = inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(name="Brzdovka", min_quantity=1),
            current_user=service,
            db=db,
        )
        updated = inventory_router.update_inventory_item(
            int(created["id"]),
            inventory_router.ServiceInventoryItemUpdateRequest(name="Brzdové destičky", min_quantity=3),
            current_user=service,
            db=db,
        )
        assert updated["name"] == "Brzdové destičky"
        assert updated["min_quantity"] == 3
    finally:
        db.close()
        engine.dispose()


def test_service_inventory_adjust_stock(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        created = inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(name="Kapacitor", quantity_on_hand=4),
            current_user=service,
            db=db,
        )
        adjusted = inventory_router.adjust_inventory_item(
            int(created["id"]),
            inventory_router.ServiceInventoryAdjustRequest(quantity_delta=-1, reason="Test"),
            current_user=service,
            db=db,
        )
        assert adjusted["quantity_on_hand"] == 3
    finally:
        db.close()
        engine.dispose()


def test_service_inventory_list_scoped_to_service(tmp_path: Path) -> None:
    engine, db, _owner, service, foreign_service, _vehicle = _seed_ctx(tmp_path)
    try:
        inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(name="Own part"),
            current_user=service,
            db=db,
        )
        inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(name="Foreign part"),
            current_user=foreign_service,
            db=db,
        )
        own = inventory_router.list_inventory_items(q=None, low_stock=False, limit=200, current_user=service, db=db)
        assert own["count"] == 1
        assert own["items"][0]["name"] == "Own part"
    finally:
        db.close()
        engine.dispose()


def test_service_inventory_cross_service_forbidden(tmp_path: Path) -> None:
    engine, db, _owner, service, foreign_service, _vehicle = _seed_ctx(tmp_path)
    try:
        created = inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(name="Secret part"),
            current_user=service,
            db=db,
        )
        with pytest.raises(HTTPException) as err:
            inventory_router.get_inventory_item(int(created["id"]), current_user=foreign_service, db=db)
        assert err.value.status_code == 404
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_add_inventory_part(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        inv = inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(name="Olej 5W30", quantity_on_hand=10, sale_price=300),
            current_user=service,
            db=db,
        )
        wo = _create_work_order(db, owner, service, vehicle)
        add_work_order_part(
            int(wo["id"]),
            ServiceWorkOrderPartCreateRequest(inventory_item_id=int(inv["id"]), quantity=2),
            current_user=_service_user(service),
            db=db,
        )
        detail = dashboard_router.get_service_work_order_detail(
            work_order_id=int(wo["id"]),
            current_user=_service_user(service),
            db=db,
        )
        assert len(detail["items"]["parts"]) == 1
        assert detail["items"]["parts"][0]["from_inventory"] is True
        row = db.query(ServiceInventoryItem).filter(ServiceInventoryItem.id == int(inv["id"])).one()
        assert row.quantity_on_hand == 8
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_add_manual_part_still_works(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        wo = _create_work_order(db, owner, service, vehicle)
        add_work_order_part(
            int(wo["id"]),
            ServiceWorkOrderPartCreateRequest(name="Ruční díl", quantity=1, unit="ks"),
            current_user=_service_user(service),
            db=db,
        )
        detail = dashboard_router.get_service_work_order_detail(
            work_order_id=int(wo["id"]),
            current_user=_service_user(service),
            db=db,
        )
        assert detail["items"]["parts"][0]["name"] == "Ruční díl"
        assert detail["items"]["parts"][0]["from_inventory"] is False
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_inventory_decrements_stock(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        inv = inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(name="Svíčka", quantity_on_hand=3),
            current_user=service,
            db=db,
        )
        wo = _create_work_order(db, owner, service, vehicle)
        add_work_order_part(
            int(wo["id"]),
            ServiceWorkOrderPartCreateRequest(inventory_item_id=int(inv["id"]), quantity=1),
            current_user=_service_user(service),
            db=db,
        )
        assert db.query(ServiceInventoryMovement).filter(ServiceInventoryMovement.movement_type == "out").count() == 1
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_inventory_insufficient_stock_422(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        inv = inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(name="Disk", quantity_on_hand=1),
            current_user=service,
            db=db,
        )
        wo = _create_work_order(db, owner, service, vehicle)
        with pytest.raises(HTTPException) as err:
            add_work_order_part(
                int(wo["id"]),
                ServiceWorkOrderPartCreateRequest(inventory_item_id=int(inv["id"]), quantity=5),
                current_user=_service_user(service),
                db=db,
            )
        assert err.value.status_code == 422
        row = db.query(ServiceInventoryItem).filter(ServiceInventoryItem.id == int(inv["id"])).one()
        assert row.quantity_on_hand == 1
        assert db.query(ServiceWorkOrderItem).filter(ServiceWorkOrderItem.work_order_id == int(wo["id"])).count() == 0
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_inventory_no_partial_write(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        inv = inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(name="Těsnění", quantity_on_hand=2),
            current_user=service,
            db=db,
        )
        wo = _create_work_order(db, owner, service, vehicle)
        before_movements = db.query(ServiceInventoryMovement).count()
        with pytest.raises(HTTPException):
            add_work_order_part(
                int(wo["id"]),
                ServiceWorkOrderPartCreateRequest(inventory_item_id=int(inv["id"]), quantity=3),
                current_user=_service_user(service),
                db=db,
            )
        row = db.query(ServiceInventoryItem).filter(ServiceInventoryItem.id == int(inv["id"])).one()
        assert row.quantity_on_hand == 2
        assert db.query(ServiceWorkOrderItem).filter(ServiceWorkOrderItem.work_order_id == int(wo["id"])).count() == 0
        assert db.query(ServiceInventoryMovement).count() == before_movements
    finally:
        db.close()
        engine.dispose()


def test_owner_safe_history_no_inventory_prices_supplier(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        inv = inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(
                name="Tajný díl",
                quantity_on_hand=5,
                purchase_price=999,
                supplier_name="Tajný dodavatel",
            ),
            current_user=service,
            db=db,
        )
        wo = _create_work_order(db, owner, service, vehicle)
        add_work_order_part(
            int(wo["id"]),
            ServiceWorkOrderPartCreateRequest(inventory_item_id=int(inv["id"]), quantity=1, unit_price_without_vat=400),
            current_user=_service_user(service),
            db=db,
        )
        complete_work_order(int(wo["id"]), current_user=_service_user(service), db=db)
        create_service_record_from_work_order(
            int(wo["id"]),
            ServiceWorkOrderCreateRecordRequest(mileage=100000),
            current_user=_service_user(service),
            db=db,
        )
        record = db.query(ServiceRecord).filter(ServiceRecord.vehicle_id == vehicle.id).order_by(ServiceRecord.id.desc()).first()
        history = build_owner_safe_service_history(db, vehicle_id=int(vehicle.id), owner_customer_id=int(owner.id))
        blob = json.dumps(history, ensure_ascii=False).lower()
        assert "999" not in blob
        assert "tajný dodavatel" not in blob
        assert "inventory_item_id" not in blob
        assert "purchase_price" not in blob
        assert record is not None
    finally:
        db.close()
        engine.dispose()


def test_billing_from_work_order_uses_part_lines_without_leaking_purchase_price(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        inv = inventory_router.create_inventory_item(
            inventory_router.ServiceInventoryItemCreateRequest(
                name="Baterie",
                quantity_on_hand=2,
                purchase_price=1500,
                sale_price=2200,
            ),
            current_user=service,
            db=db,
        )
        wo = _create_work_order(db, owner, service, vehicle)
        add_work_order_part(
            int(wo["id"]),
            ServiceWorkOrderPartCreateRequest(inventory_item_id=int(inv["id"]), quantity=1),
            current_user=_service_user(service),
            db=db,
        )
        items = db.query(ServiceWorkOrderItem).filter(ServiceWorkOrderItem.work_order_id == int(wo["id"])).all()
        quote_items = work_order_items_to_quote_items(items)
        blob = json.dumps(quote_items, ensure_ascii=False).lower()
        assert "1500" not in blob
        assert quote_items[0]["unit_price"] == 2200
    finally:
        db.close()
        engine.dispose()
