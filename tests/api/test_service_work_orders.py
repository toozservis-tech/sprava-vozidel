from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceCustomerLink,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.routers_v1 import service_dashboard as dashboard_router


def _service_user(service: Customer) -> SimpleNamespace:
    return SimpleNamespace(
        id=service.id,
        email=service.email,
        role="service",
        name=service.name,
        tenant_id=service.tenant_id,
    )


def _seed_ctx(tmp_path: Path):
    db_path = tmp_path / "service_work_orders.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    tenant = Tenant(name="Work Orders Tenant", license_key="work-orders-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(tenant_id=tenant.id, email="owner@example.com", password_hash="x", role="user", name="Owner")
    service = Customer(tenant_id=tenant.id, email="service@example.com", password_hash="x", role="service", name="Service")
    foreign_service = Customer(
        tenant_id=tenant.id,
        email="foreign-service@example.com",
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
        vin="TMB12345678901234",
        plate="1AB2345",
        stk_valid_until=date(2030, 1, 1),
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


def test_service_work_order_list_loads(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                owner_id=owner.id,
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Diagnostika",
                status="in_progress",
            ),
            current_user=_service_user(service),
            db=db,
        )
        rows = dashboard_router.list_service_work_orders(current_user=_service_user(service), db=db)
        assert len(rows["items"]) == 1
        assert rows["items"][0]["status"] == "in_progress"
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_create_for_authorized_vehicle(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                owner_id=owner.id,
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Příjem",
                status="awaiting_client_approval",
            ),
            current_user=_service_user(service),
            db=db,
        )
        assert created["vehicle_id"] == vehicle.id
        assert created["owner_id"] == owner.id
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_forbidden_without_access(tmp_path: Path) -> None:
    engine, db, owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        with pytest.raises(HTTPException) as exc:
            dashboard_router.create_service_work_order(
                payload=dashboard_router.ServiceWorkOrderCreateRequest(
                    owner_id=owner.id,
                    vehicle_id=vehicle.id,
                    technician_id=foreign_service.id,
                    title="Bez přístupu",
                    status="approved",
                ),
                current_user=_service_user(foreign_service),
                db=db,
            )
        assert exc.value.status_code == 403
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_create_from_intake_context(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                owner_id=owner.id,
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Z intake",
                source_type="intake",
                source_intake_id=77,
                status="approved",
            ),
            current_user=_service_user(service),
            db=db,
        )
        assert created["source"] == "intake"
        assert created["status"] == "approved"
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_status_update(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                owner_id=owner.id,
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Status update",
            ),
            current_user=_service_user(service),
            db=db,
        )
        updated = dashboard_router.update_service_work_order(
            work_order_id=int(created["id"]),
            payload=dashboard_router.ServiceWorkOrderUpdateRequest(status="completed"),
            current_user=_service_user(service),
            db=db,
        )
        assert updated["status"] == "completed"
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_audit_written(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                owner_id=owner.id,
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Audit trail",
            ),
            current_user=_service_user(service),
            db=db,
        )
        row = db.execute(
            text("SELECT action FROM service_work_order_audit_logs WHERE work_order_id = :id ORDER BY id DESC LIMIT 1"),
            {"id": int(created["id"])},
        ).fetchone()
        assert row is not None
        assert row[0] == "create"
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_add_labor_part_time_or_limited(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                owner_id=owner.id,
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Limited operations",
            ),
            current_user=_service_user(service),
            db=db,
        )
        detail = dashboard_router.get_service_work_order_detail(
            work_order_id=int(created["id"]),
            current_user=_service_user(service),
            db=db,
        )
        # Backend currently provides canonical detail, while labor/parts/time endpoints are intentionally not exposed yet.
        assert detail["id"] == int(created["id"])
        assert "audit_log" in detail
    finally:
        db.close()
        engine.dispose()
