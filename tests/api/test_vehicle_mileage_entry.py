from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    Tenant,
    Vehicle as VehicleModel,
    VehicleMileage,
    VehicleOwnership,
)
from src.modules.vehicle_hub.mileage_reports import collect_vehicle_mileage_timeline_points
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "vehicle_mileage_entry.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_owned_vehicle(db_session):
    tenant = Tenant(name="Mileage Tenant", license_key="mileage-tenant-key")
    db_session.add(tenant)
    db_session.flush()

    owner = Customer(
        tenant_id=tenant.id,
        email="driver@example.com",
        password_hash="hash",
        role="user",
    )
    db_session.add(owner)
    db_session.flush()

    vehicle = VehicleModel(
        tenant_id=tenant.id,
        user_email="legacy@example.com",
        nickname="Kilometrové auto",
        stk_valid_until=date(2030, 1, 1),
        current_mileage_km=120_000,
        last_stk_mileage_km=118_500,
    )
    db_session.add(vehicle)
    db_session.flush()

    ensure_vehicle_owner_assignment(
        db_session,
        vehicle=vehicle,
        owner=owner,
        assigned_by_customer_id=owner.id,
    )
    db_session.commit()
    db_session.refresh(owner)
    db_session.refresh(vehicle)
    return owner, vehicle


def test_record_vehicle_mileage_updates_summary_and_creates_history(db_session) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)

    result = vehicles_router.record_vehicle_mileage(
        vehicle_id=vehicle.id,
        payload=vehicles_router.VehicleMileageRecordV1(
            mileage_km=123_456,
            note="Zapsáno při tankování",
            confirm_lower_than_current=False,
            source="manual",
        ),
        current_user=owner,
        db=db_session,
    )

    db_session.refresh(vehicle)
    assert vehicle.current_mileage_km == 123_456
    assert result.vehicle.id == vehicle.id
    assert result.vehicle.current_mileage_km == 123_456

    assert result.created_vehicle_mileage_id is not None
    vm_row = (
        db_session.query(VehicleMileage)
        .filter(VehicleMileage.id == result.created_vehicle_mileage_id)
        .first()
    )
    assert vm_row is not None
    assert vm_row.vehicle_id == vehicle.id
    assert vm_row.mileage_km == 123_456
    assert vm_row.source == "manual"
    assert vm_row.note == "Zapsáno při tankování"


def test_record_vehicle_mileage_requires_confirmation_for_lower_value(db_session) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)

    with pytest.raises(HTTPException) as exc_info:
        vehicles_router.record_vehicle_mileage(
            vehicle_id=vehicle.id,
            payload=vehicles_router.VehicleMileageRecordV1(
                mileage_km=119_000,
                note="Oprava po chybně zadaném stavu",
                confirm_lower_than_current=False,
                source="manual",
            ),
            current_user=owner,
            db=db_session,
        )

    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    msg = detail.get("message", "") if isinstance(detail, dict) else str(detail)
    assert "nižší" in msg.lower() and "maximum" in msg.lower()

    confirmed = vehicles_router.record_vehicle_mileage(
        vehicle_id=vehicle.id,
        payload=vehicles_router.VehicleMileageRecordV1(
            mileage_km=119_000,
            note="Oprava po chybně zadaném stavu",
            confirm_lower_than_current=True,
            source="manual",
        ),
        current_user=owner,
        db=db_session,
    )

    db_session.refresh(vehicle)
    assert confirmed.vehicle.current_mileage_km == 119_000
    assert vehicle.current_mileage_km == 119_000
    ownership_count = (
        db_session.query(VehicleOwnership)
        .filter(VehicleOwnership.vehicle_id == vehicle.id, VehicleOwnership.customer_id == owner.id)
        .count()
    )
    assert ownership_count == 1


def test_mileage_timeline_includes_vehicle_mileage_rows(db_session) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    vehicles_router.record_vehicle_mileage(
        vehicle_id=vehicle.id,
        payload=vehicles_router.VehicleMileageRecordV1(
            mileage_km=125_000,
            note=None,
            confirm_lower_than_current=False,
            source="stk",
        ),
        current_user=owner,
        db=db_session,
    )
    points = collect_vehicle_mileage_timeline_points(db_session, vehicle.id)
    assert any(str(p.record_id).startswith("vehicle_mileage:") for p in points)
