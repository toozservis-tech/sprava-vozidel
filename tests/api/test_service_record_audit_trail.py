"""
AUD-HIGH-007: service record updates must preserve prior state.
"""
from datetime import datetime, date
from pathlib import Path
from types import SimpleNamespace
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import ServiceRecord as ServiceRecordModel, Tenant, Vehicle as VehicleModel
from src.modules.vehicle_hub.routers_v1 import service_records as service_records_router
from src.modules.vehicle_hub.routers_v1.schemas import ServiceRecordUpdateV1
from src.modules.vehicle_hub.routers_v1.service_records import (
    _split_service_record_description_annotation,
)


@pytest.fixture()
def db_context(tmp_path: Path):
    db_path = tmp_path / "service_record_audit_trail.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        tenant = Tenant(name="Audit Tenant", license_key="audit-tenant-key")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        vehicle = VehicleModel(
            tenant_id=tenant.id,
            user_email="audit-owner@example.com",
            nickname="Audit Vehicle",
            stk_valid_until=date(2030, 1, 1),
        )
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)

        record = ServiceRecordModel(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            user_id=None,
            performed_at=datetime(2025, 1, 10, 12, 0, 0),
            mileage=120000,
            description="Original description",
            price=1990.0,
            note="Original note",
            category="OLEJ",
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        yield {"db": db, "tenant": tenant, "vehicle": vehicle, "record": record}
    finally:
        db.close()
        engine.dispose()


def test_service_record_update_preserves_previous_state(
    db_context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = db_context["db"]
    vehicle = db_context["vehicle"]
    record = db_context["record"]

    current_user = SimpleNamespace(
        id=999,
        email=vehicle.user_email,
        role="admin",
        tenant_id=vehicle.tenant_id,
    )

    monkeypatch.setattr(service_records_router, "can_access_vehicle", lambda *_: True)

    updated = service_records_router.update_service_record(
        vehicle_id=vehicle.id,
        record_id=record.id,
        record_data=ServiceRecordUpdateV1(
            description="Updated description",
            note="Updated note",
            mileage=120500,
        ),
        current_user=current_user,
        db=db,
    )

    main_description, previous_description = _split_service_record_description_annotation(
        updated.description
    )
    assert main_description == "Updated description"
    assert previous_description == "Original description"
    assert updated.note == "Updated note"
    assert updated.mileage == 120000

    inspector = inspect(db.bind)
    assert inspector.has_table("service_record_audit_logs"), "Missing service_record_audit_logs table"

    rows = db.execute(
        text(
            "SELECT previous_snapshot_json FROM service_record_audit_logs WHERE service_record_id = :record_id"
        ),
        {"record_id": record.id},
    ).fetchall()
    assert len(rows) == 1, "Expected one audit snapshot row for updated record"

    snapshot = json.loads(rows[0][0])
    assert snapshot["description"] == "Original description"
    assert snapshot["note"] == "Original note"
    assert snapshot["mileage"] == 120000

    full_rows = db.execute(
        text(
            """
            SELECT previous_snapshot_json, new_snapshot_json, snapshot_hash, action
            FROM service_record_audit_logs
            WHERE service_record_id = :record_id
            """
        ),
        {"record_id": record.id},
    ).fetchall()
    assert full_rows[0][1] is not None
    assert full_rows[0][2]
    assert full_rows[0][3] == "update"


def test_service_record_delete_via_public_api_forbidden(
    db_context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = db_context["db"]
    vehicle = db_context["vehicle"]
    record = db_context["record"]

    current_user = SimpleNamespace(
        id=999,
        email=vehicle.user_email,
        role="admin",
        tenant_id=vehicle.tenant_id,
    )

    monkeypatch.setattr(service_records_router, "can_access_vehicle", lambda *_: True)

    with pytest.raises(HTTPException) as exc_info:
        service_records_router.delete_service_record(
            vehicle_id=vehicle.id,
            record_id=record.id,
            current_user=current_user,
            db=db,
        )

    assert exc_info.value.status_code == 403
    assert "nelze odstranit" in (exc_info.value.detail or "").lower()

    db.refresh(record)
    assert record.is_deleted is False


def test_service_record_approved_or_locked_cannot_be_updated(
    db_context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = db_context["db"]
    vehicle = db_context["vehicle"]
    record = db_context["record"]
    record.record_status = "approved"
    db.add(record)
    db.commit()

    current_user = SimpleNamespace(
        id=999,
        email=vehicle.user_email,
        role="user",
        tenant_id=vehicle.tenant_id,
    )

    monkeypatch.setattr(service_records_router, "can_access_vehicle", lambda *_: True)

    with pytest.raises(Exception) as exc_info:
        service_records_router.update_service_record(
            vehicle_id=vehicle.id,
            record_id=record.id,
            record_data=ServiceRecordUpdateV1(description="Should fail"),
            current_user=current_user,
            db=db,
        )

    assert "nelze upravovat" in str(exc_info.value) or "nelze upravit" in str(exc_info.value)
