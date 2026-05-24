"""Unit tests for garage vehicle_order validation (in-process, no live server)."""
from __future__ import annotations

from pathlib import Path

from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle, VehicleOwnership
from src.server.user_settings_helpers import validate_vehicle_order_ids


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "vehicle_order_validation.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    tenant = Tenant(name="Settings Tenant", license_key="settings-order-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    user = Customer(
        tenant_id=tenant.id,
        email="settings-order@example.com",
        password_hash="hash",
        role="user",
        name="Settings Order User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=user.email,
        nickname="Owned Car",
        plate="1AB2345",
    )
    db.add(vehicle)
    db.flush()
    db.add(
        VehicleOwnership(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            customer_id=user.id,
            ownership_type="owner",
            is_primary=True,
            is_active=True,
            assigned_by_customer_id=user.id,
            assigned_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()
    db.refresh(vehicle)

    try:
        yield {"db": db, "user": user, "vehicle_id": vehicle.id}
    finally:
        db.close()


def test_validate_vehicle_order_empty_list(db_session):
    db = db_session["db"]
    user = db_session["user"]
    assert validate_vehicle_order_ids(db, user, []) == []


def test_validate_vehicle_order_owned_ids(db_session):
    db = db_session["db"]
    user = db_session["user"]
    vid = db_session["vehicle_id"]
    assert validate_vehicle_order_ids(db, user, [vid]) == [vid]


def test_validate_vehicle_order_duplicate_rejected(db_session):
    db = db_session["db"]
    user = db_session["user"]
    vid = db_session["vehicle_id"]
    with pytest.raises(HTTPException) as exc:
        validate_vehicle_order_ids(db, user, [vid, vid])
    assert exc.value.status_code == 400
    assert "duplicit" in str(exc.value.detail).lower()


def test_validate_vehicle_order_foreign_rejected(db_session):
    db = db_session["db"]
    user = db_session["user"]
    with pytest.raises(HTTPException) as exc:
        validate_vehicle_order_ids(db, user, [999999])
    assert exc.value.status_code == 400
    assert "nepatří" in str(exc.value.detail).lower()


def test_validate_vehicle_order_bool_rejected(db_session):
    db = db_session["db"]
    user = db_session["user"]
    with pytest.raises(HTTPException) as exc:
        validate_vehicle_order_ids(db, user, [True])  # type: ignore[list-item]
    assert exc.value.status_code == 400


def test_validate_vehicle_order_not_a_list(db_session):
    db = db_session["db"]
    user = db_session["user"]
    with pytest.raises(HTTPException) as exc:
        validate_vehicle_order_ids(db, user, "1,2,3")  # type: ignore[arg-type]
    assert exc.value.status_code == 400
