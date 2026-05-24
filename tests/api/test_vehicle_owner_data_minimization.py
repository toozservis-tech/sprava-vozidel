"""
PRIV-MED-006: vehicle detail responses should minimize owner-linked data exposure.
"""
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Vehicle as VehicleModel
from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "vehicle_priv_med_006.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_vehicle(db_session) -> VehicleModel:
    vehicle = VehicleModel(
        tenant_id=777,
        user_email="owner.privacy@example.com",
        nickname="Privacy Vehicle",
        stk_valid_until=date(2030, 1, 1),
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)
    return vehicle


def test_vehicle_detail_redacts_owner_data_for_non_owner_service(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vehicle = _seed_vehicle(db_session)
    service_user = SimpleNamespace(email="service@example.com", role="service", tenant_id=777)

    monkeypatch.setattr(vehicles_router, "can_access_vehicle", lambda *_: True)

    payload = vehicles_router.get_vehicle(vehicle.id, current_user=service_user, db=db_session)

    assert payload["id"] == vehicle.id
    assert payload["user_email"] == "hidden"
    assert payload["tenant_id"] is None


def test_vehicle_detail_keeps_owner_data_for_owner(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vehicle = _seed_vehicle(db_session)
    owner_user = SimpleNamespace(email=vehicle.user_email, role="user", tenant_id=777)

    monkeypatch.setattr(vehicles_router, "can_access_vehicle", lambda *_: True)

    payload = vehicles_router.get_vehicle(vehicle.id, current_user=owner_user, db=db_session)

    assert payload["user_email"] == vehicle.user_email
    assert payload["tenant_id"] == vehicle.tenant_id
