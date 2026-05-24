from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    Reservation,
    ServiceCustomerLink,
    Tenant,
    Vehicle,
)
from src.modules.vehicle_hub.routers_v1 import reservations as reservations_router
from src.modules.vehicle_hub.routers_v1.schemas import ReservationCreateV1


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
    db_path = tmp_path / "reservations_vehicle_options.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        tenant_a = Tenant(name="Tenant A", license_key="res-opt-a")
        tenant_b = Tenant(name="Tenant B", license_key="res-opt-b")
        db.add_all([tenant_a, tenant_b])
        db.commit()
        db.refresh(tenant_a)
        db.refresh(tenant_b)

        user = Customer(
            tenant_id=tenant_a.id,
            email="res-opt-user@example.com",
            password_hash="hash-user",
            role="user",
            name="User",
        )
        service = Customer(
            tenant_id=tenant_a.id,
            email="res-opt-service@example.com",
            password_hash="hash-service",
            role="service",
            name="Service",
        )
        db.add_all([user, service])
        db.commit()
        db.refresh(user)
        db.refresh(service)

        from src.modules.licensing.service import get_or_create_license

        for tenant in (tenant_a, tenant_b):
            lic = get_or_create_license(db, tenant.id)
            lic.plan = "basic"
            lic.status = "active"
        db.commit()

        yield {
            "db": db,
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
            "user": user,
            "service": service,
        }
    finally:
        db.close()
        engine.dispose()


def test_user_vehicle_options_fallback_to_email_without_tenant_match(db_context) -> None:
    db = db_context["db"]
    user = db_context["user"]
    tenant_b = db_context["tenant_b"]

    vehicle = Vehicle(
        tenant_id=tenant_b.id,
        user_email=user.email,
        nickname="Fallback Vehicle",
        brand="Skoda",
        model="Octavia",
        vin="TMB12345678901234",
        plate="1AB2345",
    )
    db.add(vehicle)
    db.commit()

    payload = reservations_router.get_reservation_vehicle_options(
        current_user=user,
        db=db,
    )
    vehicle_ids = {int(item["id"]) for item in payload}
    assert vehicle.id in vehicle_ids


def test_service_vehicle_options_include_linked_customer_vehicles(db_context) -> None:
    db = db_context["db"]
    tenant_a = db_context["tenant_a"]
    user = db_context["user"]
    service = db_context["service"]

    vehicle = Vehicle(
        tenant_id=tenant_a.id,
        user_email=user.email,
        nickname="Linked Vehicle",
        brand="VW",
        model="Passat",
        vin="WVW12345678901234",
        plate="2CD3456",
    )
    db.add(vehicle)
    db.flush()

    db.add(
        ServiceCustomerLink(
            service_tenant_id=tenant_a.id,
            service_customer_id=service.id,
            customer_tenant_id=tenant_a.id,
            customer_id=user.id,
            status="active",
            note="test link",
        )
    )
    db.commit()

    payload = reservations_router.get_reservation_vehicle_options(
        current_user=service,
        db=db,
    )
    matched = [item for item in payload if int(item["id"]) == vehicle.id]
    assert matched, "Linked vehicle must be available for service reservation."
    assert matched[0]["source"] in {"linked_customer", "service_access", "reservation_history"}


def test_create_reservation_persists_source_platform(db_context, monkeypatch: pytest.MonkeyPatch) -> None:
    db = db_context["db"]
    tenant_a = db_context["tenant_a"]
    user = db_context["user"]
    service = db_context["service"]

    vehicle = Vehicle(
        tenant_id=tenant_a.id,
        user_email=user.email,
        nickname="Source Platform Vehicle",
        brand="Audi",
        model="A4",
        vin="WAU12345678901234",
        plate="3EF4567",
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    monkeypatch.setattr(reservations_router, "send_reservation_created_email", lambda *_, **__: None)

    payload = ReservationCreateV1(
        service_id=service.id,
        vehicle_id=vehicle.id,
        service_type="Pravidelný servis",
        note="test",
        start_datetime=datetime.utcnow() + timedelta(days=2),
        end_datetime=None,
        created_via="ios_app",
    )

    created = reservations_router.create_reservation(
        reservation_data=payload,
        request=_request(headers=[(b"x-client-platform", b"ios_app")]),
        current_user=user,
        db=db,
    )

    saved = db.query(Reservation).filter(Reservation.id == created.id).first()
    assert saved is not None
    assert saved.source_platform == "ios_app"

