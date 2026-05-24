from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.bot.command_engine import IntentType
from src.modules.licensing import service as licensing_service
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, CustomerCommand, Tenant, Vehicle, VehicleOwnership
from src.modules.vehicle_hub.ownership import get_primary_vehicle_owner, user_owns_vehicle
from src.modules.vehicle_hub.routers_v1 import customer_commands as customer_commands_router
from src.server.main_helpers import cleanup_export_dir, delete_customer_account, export_current_customer_bundle


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "ownership_compat_cleanup.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_owner_with_vehicle(db_session):
    tenant = Tenant(name="Compat Tenant", license_key="compat-tenant-key")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)

    owner = Customer(
        tenant_id=tenant.id,
        email="owner.compat@example.com",
        password_hash="hash",
        role="user",
        name="Compat Owner",
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email="stale-legacy@example.com",
        nickname="Compat Car",
        brand="Skoda",
        model="Fabia",
        vin="TMBCOMPAT12345678"[:17],
        plate="1AB2345",
    )
    db_session.add(vehicle)
    db_session.flush()
    db_session.add(
        VehicleOwnership(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            ownership_type="owner",
            is_primary=True,
            is_active=True,
            assigned_by_customer_id=owner.id,
        )
    )
    db_session.commit()
    db_session.refresh(vehicle)
    return owner, vehicle


def test_export_bundle_uses_ownership_source_of_truth(monkeypatch: pytest.MonkeyPatch, db_session) -> None:
    owner, vehicle = _seed_owner_with_vehicle(db_session)

    monkeypatch.setattr(
        "src.server.main_helpers.build_vehicle_export_pdf",
        lambda pdf_path, **_: Path(pdf_path).write_text("pdf", encoding="utf-8"),
    )

    tmp_dir_path, zip_path, _export_file_name, vehicle_count = export_current_customer_bundle(
        owner,
        email=owner.email,
        db=db_session,
        app_version="test-version",
    )
    try:
        assert vehicle_count == 1
        with ZipFile(zip_path) as archive:
            names = set(archive.namelist())
            assert "data/kompletni_export.json" in names
            assert any(name.endswith(".pdf") for name in names)
    finally:
        cleanup_export_dir(tmp_dir_path)


def test_delete_customer_account_deletes_owned_vehicles_via_ownership(db_session) -> None:
    owner, vehicle = _seed_owner_with_vehicle(db_session)
    vehicle_id = int(vehicle.id)

    deleted = delete_customer_account(owner, email=owner.email, db=db_session)
    db_session.commit()

    assert deleted["vehicle_ownerships"] == 1
    assert deleted["vehicles"] == 1
    assert db_session.query(VehicleOwnership).filter(VehicleOwnership.vehicle_id == vehicle_id).count() == 0
    assert db_session.query(Vehicle).filter(Vehicle.id == vehicle_id).count() == 0


def test_ownership_helpers_backfill_legacy_email_without_using_it_as_authority(db_session) -> None:
    tenant = Tenant(name="Legacy Tenant", license_key="legacy-tenant-key")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)

    owner = Customer(
        tenant_id=tenant.id,
        email="legacy.owner@example.com",
        password_hash="hash",
        role="user",
        name="Legacy Owner",
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Legacy Car",
        brand="VW",
        model="Golf",
        vin="WVWLEGACY12345678"[:17],
        plate="2BC3456",
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)

    assert db_session.query(VehicleOwnership).count() == 0

    resolved_owner = get_primary_vehicle_owner(db_session, vehicle)
    assert resolved_owner is not None
    assert resolved_owner.id == owner.id
    assert user_owns_vehicle(db_session, owner, vehicle) is True
    assert db_session.query(VehicleOwnership).filter(VehicleOwnership.vehicle_id == vehicle.id).count() == 1


def test_customer_command_add_vehicle_creates_ownership_assignment(
    monkeypatch: pytest.MonkeyPatch,
    db_session,
) -> None:
    tenant = Tenant(name="Command Tenant", license_key="command-tenant-key")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)

    owner = Customer(
        tenant_id=tenant.id,
        email="command.owner@example.com",
        password_hash="hash",
        role="user",
        name="Command Owner",
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    async def _fake_mdcr_fetch(_vin: str):
        return None

    monkeypatch.setattr(
        "src.modules.vehicle_hub.decoder.mdcr_client.fetch_vehicle_by_vin_from_mdcr",
        _fake_mdcr_fetch,
    )

    command = CustomerCommand(
        tenant_id=tenant.id,
        source="web_chat",
        customer_name=owner.name,
        customer_email=owner.email,
        raw_text="SPZ: 1AB2345, název: Rodinné auto",
        normalized_text=json.dumps(
            {
                "step": "waiting_for_info",
                "vin": "TMBCOMMAND1234567",
                "brand": "Skoda",
                "model": "Octavia",
                "year": 2022,
                "plate": "1AB2345",
                "nickname": "Rodinné auto",
            }
        ),
        intent_type=IntentType.ADD_VEHICLE.value,
        status="REQUIRES_INFO",
    )
    db_session.add(command)
    db_session.commit()
    db_session.refresh(command)

    result = customer_commands_router.execute_customer_command(command, db_session)
    assert "úspěšně přidáno" in result.lower()

    vehicle = db_session.query(Vehicle).filter(Vehicle.vin == "TMBCOMMAND1234567").first()
    assert vehicle is not None
    ownership = (
        db_session.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == vehicle.id,
            VehicleOwnership.customer_id == owner.id,
            VehicleOwnership.is_active.is_(True),
        )
        .first()
    )
    assert ownership is not None


def test_licensing_fallback_uses_normalized_compat_email(db_session) -> None:
    tenant = Tenant(name="License Compat Tenant", license_key="license-compat-key")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email="Compat.Owner@Example.com",
        nickname="License Compat Car",
        brand="VW",
        model="Golf",
        vin="WVWLICENSE1234567",
        plate="3CD4567",
    )
    db_session.add(vehicle)
    db_session.commit()

    count = licensing_service.get_vehicle_count_for_user(
        db_session,
        tenant_id=tenant.id,
        user_email="compat.owner@example.com",
    )
    assert count == 1
