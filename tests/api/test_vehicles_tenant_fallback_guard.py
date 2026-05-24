"""
SEC-HIGH-005: Vehicle listing must never fall back to tenant-unsafe query paths.
"""
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Vehicle as VehicleModel
from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "vehicles_sec_high_005.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_vehicle(db_session, *, tenant_id: int, user_email: str, nickname: str) -> VehicleModel:
    vehicle = VehicleModel(
        tenant_id=tenant_id,
        user_email=user_email,
        nickname=nickname,
        stk_valid_until=date(2030, 1, 1),
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)
    return vehicle


def test_get_vehicles_requires_tenant_context(db_session) -> None:
    _seed_vehicle(
        db_session,
        tenant_id=10,
        user_email="sec-high-005@example.com",
        nickname="Unsafe fallback candidate",
    )

    current_user = SimpleNamespace(email="sec-high-005@example.com", tenant_id=None)

    with pytest.raises(HTTPException) as exc_info:
        vehicles_router.get_vehicles(current_user=current_user, db=db_session)

    assert exc_info.value.status_code == 403


def test_get_vehicles_returns_only_same_tenant_records(db_session) -> None:
    own = _seed_vehicle(
        db_session,
        tenant_id=100,
        user_email="sec-high-005@example.com",
        nickname="Tenant 100 vehicle",
    )
    _seed_vehicle(
        db_session,
        tenant_id=200,
        user_email="sec-high-005@example.com",
        nickname="Tenant 200 vehicle",
    )

    current_user = SimpleNamespace(email="sec-high-005@example.com", tenant_id=100)
    vehicles = vehicles_router.get_vehicles(current_user=current_user, db=db_session)

    returned_ids = {item["id"] for item in vehicles}
    assert returned_ids == {own.id}
