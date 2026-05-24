from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from src.modules.licensing import service as licensing_service
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceCustomerLink,
    ServiceVehicleAccess,
    Tenant,
    Vehicle,
    VehicleOwnership,
)
from src.modules.vehicle_hub.routers_v1 import reminders as reminders_router
from src.modules.vehicle_hub.routers_v1 import reservations as reservations_router
from src.modules.vehicle_hub.routers_v1 import service_workspace as workspace_router
from src.modules.vehicle_hub.routers_v1 import services as services_router
from src.modules.vehicle_hub.routers_v1.schemas import ReminderCreateV1, ReservationCreateV1


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/reservations",
        "headers": headers or [],
        "query_string": b"",
    }
    return Request(scope)


@pytest.fixture()
def db_context(tmp_path: Path):
    db_path = tmp_path / "operational_ownership_modules.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        tenant = Tenant(name="Ownership Tenant", license_key="ownership-ops-key")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        user = Customer(
            tenant_id=tenant.id,
            email="ownership-user@example.com",
            password_hash="hash-user",
            role="user",
            name="Owner User",
        )
        service = Customer(
            tenant_id=tenant.id,
            email="ownership-service@example.com",
            password_hash="hash-service",
            role="service",
            name="Linked Service",
        )
        db.add_all([user, service])
        db.commit()
        db.refresh(user)
        db.refresh(service)

        license_row = licensing_service.get_or_create_license(db, tenant.id)
        license_row.plan = "premium"
        license_row.status = "active"
        license_row.vehicles_limit = 0
        license_row.vin_decode_enabled = True
        db.add(license_row)
        db.commit()

        yield {
            "db": db,
            "tenant": tenant,
            "user": user,
            "service": service,
        }
    finally:
        db.close()
        engine.dispose()


def _seed_owned_vehicle(
    db,
    *,
    tenant_id: int,
    owner: Customer,
    nickname: str,
    legacy_user_email: str = "legacy-owner@example.com",
) -> Vehicle:
    vehicle = Vehicle(
        tenant_id=tenant_id,
        user_email=legacy_user_email,
        nickname=nickname,
        brand="Skoda",
        model="Octavia",
        vin=f"VIN{nickname}".replace(" ", "").upper()[:17].ljust(17, "1"),
        plate=f"{nickname[:3].upper()}1234",
        stk_valid_until=date.today() + timedelta(days=7),
    )
    db.add(vehicle)
    db.flush()
    db.add(
        VehicleOwnership(
            tenant_id=tenant_id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            ownership_type="owner",
            is_primary=True,
            is_active=True,
            assigned_by_customer_id=owner.id,
            assigned_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()
    db.refresh(vehicle)
    return vehicle


def test_reminders_use_ownership_source_of_truth_for_owned_vehicle(db_context):
    db = db_context["db"]
    user = db_context["user"]
    vehicle = _seed_owned_vehicle(db, tenant_id=user.tenant_id, owner=user, nickname="Reminder Car")

    reminders_payload = reminders_router.get_reminders(current_user=user, db=db)
    reminder_vehicle_ids = {item.vehicle_id for item in reminders_payload}
    assert vehicle.id in reminder_vehicle_ids

    created = reminders_router.create_reminder(
        reminder_data=ReminderCreateV1(
            vehicle_id=vehicle.id,
            type="SERVIS",
            text="Ruční připomínka",
            due_date=date.today() + timedelta(days=10),
            repeat_count=0,
            repeat_interval_days=0,
        ),
        current_user=user,
        db=db,
    )
    assert created.vehicle_id == vehicle.id


def test_reservations_use_ownership_source_of_truth_for_user_and_service(db_context, monkeypatch: pytest.MonkeyPatch):
    db = db_context["db"]
    user = db_context["user"]
    service = db_context["service"]
    vehicle = _seed_owned_vehicle(db, tenant_id=user.tenant_id, owner=user, nickname="Reservation Car")

    db.add(
        ServiceCustomerLink(
            service_tenant_id=service.tenant_id,
            service_customer_id=service.id,
            customer_tenant_id=user.tenant_id,
            customer_id=user.id,
            status="active",
            note="ownership test",
        )
    )
    db.commit()

    user_options = reservations_router.get_reservation_vehicle_options(current_user=user, db=db)
    assert {int(item["id"]) for item in user_options} == {vehicle.id}

    service_options = reservations_router.get_reservation_vehicle_options(current_user=service, db=db)
    matched = [item for item in service_options if int(item["id"]) == vehicle.id]
    assert matched
    assert matched[0]["source"] in {"linked_customer", "service_access", "reservation_history"}

    monkeypatch.setattr(reservations_router, "send_reservation_created_email", lambda *_, **__: None)
    created = reservations_router.create_reservation(
        reservation_data=ReservationCreateV1(
            service_id=service.id,
            vehicle_id=vehicle.id,
            service_type="Pravidelný servis",
            note="ownership reservation",
            start_datetime=datetime.utcnow() + timedelta(days=2),
            end_datetime=None,
            created_via="web_browser",
        ),
        request=_request(),
        current_user=user,
        db=db,
    )
    assert created.vehicle_id == vehicle.id
    assert created.customer_id == user.id


def test_services_vehicle_access_uses_ownership_source_of_truth(db_context):
    db = db_context["db"]
    user = db_context["user"]
    service = db_context["service"]
    vehicle = _seed_owned_vehicle(db, tenant_id=user.tenant_id, owner=user, nickname="Access Car")

    granted = services_router.grant_vehicle_access_to_service(
        payload=services_router.VehicleAccessGrantRequest(vehicle_id=vehicle.id, service_id=service.id),
        current_user=user,
        db=db,
    )
    assert granted["granted"] is True

    grants = services_router.get_vehicle_access_grants(current_user=user, db=db)
    assert len(grants["grants"]) == 1
    assert grants["grants"][0]["vehicle_id"] == vehicle.id

    access_rows = db.query(ServiceVehicleAccess).filter(ServiceVehicleAccess.vehicle_id == vehicle.id).all()
    assert access_rows


def test_service_workspace_uses_ownership_source_of_truth(db_context):
    db = db_context["db"]
    user = db_context["user"]
    service = db_context["service"]
    vehicle = _seed_owned_vehicle(db, tenant_id=user.tenant_id, owner=user, nickname="Workspace Car")

    db.add(
        ServiceCustomerLink(
            service_tenant_id=service.tenant_id,
            service_customer_id=service.id,
            customer_tenant_id=user.tenant_id,
            customer_id=user.id,
            status="active",
            note="workspace link",
        )
    )
    db.commit()

    listed = workspace_router.list_customer_vehicles(customer_id=user.id, current_user=service, db=db)
    listed_ids = {int(item["id"]) for item in listed}
    assert vehicle.id in listed_ids

    created = workspace_router.create_customer_vehicle(
        customer_id=user.id,
        payload=workspace_router.ServiceWorkspaceVehicleCreateRequest(
            nickname="Workspace New Car",
            plate="WS12345",
            vin="WSVIN123456789012",
            brand="VW",
            model="Golf",
            year=2021,
            stk_valid_until=date.today() + timedelta(days=365),
        ),
        current_user=service,
        db=db,
    )
    ownership = (
        db.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == int(created["id"]),
            VehicleOwnership.customer_id == user.id,
            VehicleOwnership.is_active.is_(True),
        )
        .first()
    )
    assert ownership is not None


def test_licensing_counts_user_vehicles_via_ownership(db_context):
    db = db_context["db"]
    user = db_context["user"]
    _seed_owned_vehicle(db, tenant_id=user.tenant_id, owner=user, nickname="License Car")

    count = licensing_service.get_vehicle_count_for_user(db, user.tenant_id, user.email)
    assert count == 1
