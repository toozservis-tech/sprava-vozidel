from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    License,
    LicensePaymentTransaction,
    LicenseSubscription,
    ServiceRecord,
    Tenant,
    Vehicle,
    VehicleOwnership,
)
from src.server import admin_api


@pytest.fixture(autouse=True)
def _force_live_only_paid_counting(monkeypatch):
    # Regression target: in production, test transactions must not mark user as paid.
    monkeypatch.setattr(admin_api, "COUNT_TEST_PAYMENTS_AS_PAID", False)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_user_with_license(db, *, tenant_id: int, user_id: int, email: str) -> Customer:
    tenant = Tenant(id=tenant_id, name=f"Tenant {tenant_id}", license_key=f"T-{tenant_id}")
    user = Customer(
        id=user_id,
        tenant_id=tenant_id,
        email=email,
        password_hash="hash",
        role="user",
        name=email.split("@")[0],
        created_at=datetime.utcnow() - timedelta(minutes=tenant_id),
    )
    license_row = License(
        tenant_id=tenant_id,
        plan="basic",
        status="active",
        vehicles_limit=5,
        valid_from=datetime.utcnow() - timedelta(days=10),
        valid_to=datetime.utcnow() + timedelta(days=20),
        created_at=datetime.utcnow() - timedelta(days=10),
    )
    subscription = LicenseSubscription(
        tenant_id=tenant_id,
        provider="comgate",
        status="legacy_manual",
        plan_current="basic",
        billing_period="monthly",
        auto_renew_enabled=False,
        current_period_start=datetime.utcnow() - timedelta(days=2),
        current_period_end=datetime.utcnow() + timedelta(days=28),
    )
    db.add_all([tenant, user, license_row, subscription])
    db.flush()
    return user


def _add_payment_tx(
    db,
    *,
    tenant_id: int,
    trans_id: str,
    provider_status: str,
    event_type: str,
    amount_halers: int,
    is_test: bool,
    created_at: datetime | None = None,
) -> None:
    tx = LicensePaymentTransaction(
        tenant_id=tenant_id,
        provider="comgate",
        trans_id=trans_id,
        ref_id=f"REF-{trans_id}",
        plan="basic",
        billing_period="monthly",
        amount_halers=amount_halers,
        currency="CZK",
        event_type=event_type,
        provider_status=provider_status,
        payload_json=json.dumps({"test": is_test}),
        created_at=created_at or datetime.utcnow(),
    )
    db.add(tx)


def _seed_owned_vehicle(
    db,
    *,
    tenant_id: int,
    owner: Customer,
    vehicle_id: int,
    legacy_user_email: str,
    nickname: str,
) -> Vehicle:
    vehicle = Vehicle(
        id=vehicle_id,
        tenant_id=tenant_id,
        user_email=legacy_user_email,
        nickname=nickname,
        brand="Skoda",
        model="Octavia",
        plate=f"{vehicle_id}ABC",
        vin=f"VIN{vehicle_id:014d}"[-17:],
        created_at=datetime.utcnow(),
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
    db.flush()
    db.add(
        ServiceRecord(
            tenant_id=tenant_id,
            vehicle_id=vehicle.id,
            user_id=owner.id,
            performed_at=datetime.utcnow(),
            mileage=123456,
            description=f"Service for {nickname}",
            price=1500.0,
        )
    )
    db.commit()
    db.refresh(vehicle)
    return vehicle


def test_control_center_payments_separates_live_and_test(db_session):
    live_user = _seed_user_with_license(db_session, tenant_id=10, user_id=100, email="live@example.com")
    test_user = _seed_user_with_license(db_session, tenant_id=20, user_id=200, email="test@example.com")

    _add_payment_tx(
        db_session,
        tenant_id=live_user.tenant_id,
        trans_id="LIVE-SUCCESS-1",
        provider_status="PAID",
        event_type="paid_confirmed",
        amount_halers=9900,
        is_test=False,
    )
    _add_payment_tx(
        db_session,
        tenant_id=live_user.tenant_id,
        trans_id="LIVE-FAILED-1",
        provider_status="FAILED",
        event_type="payment_failed",
        amount_halers=9900,
        is_test=False,
    )
    _add_payment_tx(
        db_session,
        tenant_id=test_user.tenant_id,
        trans_id="TEST-SUCCESS-1",
        provider_status="PAID",
        event_type="paid_confirmed",
        amount_halers=9900,
        is_test=True,
    )
    db_session.commit()

    payload = admin_api.get_control_center_payments(
        limit=50,
        offset=0,
        status=None,
        user_email=None,
        email="developer@example.com",
        db=db_session,
    )

    by_trans = {item["trans_id"]: item for item in payload["items"]}
    assert by_trans["LIVE-SUCCESS-1"]["payment_environment"] == "LIVE"
    assert by_trans["TEST-SUCCESS-1"]["payment_environment"] == "TEST"
    assert by_trans["LIVE-SUCCESS-1"]["is_successful"] is True
    assert by_trans["LIVE-FAILED-1"]["is_failed"] is True

    summary = payload["summary"]
    assert summary["live"]["count"] == 2
    assert summary["test"]["count"] == 1
    assert summary["live"]["paid_count"] == 1
    assert summary["test"]["paid_count"] == 1
    assert summary["live"]["failed_count"] == 1
    assert summary["all"]["count"] == 3
    assert payload["source"]["table"] == "license_payment_transactions"


def test_users_has_paid_uses_live_payments_only(db_session):
    live_user = _seed_user_with_license(db_session, tenant_id=11, user_id=101, email="paid-live@example.com")
    test_user = _seed_user_with_license(db_session, tenant_id=21, user_id=201, email="paid-test-only@example.com")

    _add_payment_tx(
        db_session,
        tenant_id=live_user.tenant_id,
        trans_id="LIVE-SUCCESS-2",
        provider_status="PAID",
        event_type="paid_confirmed",
        amount_halers=9900,
        is_test=False,
    )
    _add_payment_tx(
        db_session,
        tenant_id=test_user.tenant_id,
        trans_id="TEST-SUCCESS-2",
        provider_status="PAID",
        event_type="paid_confirmed",
        amount_halers=9900,
        is_test=True,
    )
    db_session.commit()

    users = admin_api.get_all_users(
        limit=200,
        offset=0,
        email="developer@example.com",
        db=db_session,
    )
    by_email = {item.email: item for item in users}

    assert by_email["paid-live@example.com"].has_paid is True
    assert by_email["paid-live@example.com"].last_paid_at is not None
    assert by_email["paid-test-only@example.com"].has_paid is False
    assert by_email["paid-test-only@example.com"].last_paid_at is None


def test_user_insight_reports_live_and_test_consistently(db_session):
    live_user = _seed_user_with_license(db_session, tenant_id=12, user_id=102, email="insight-live@example.com")
    test_user = _seed_user_with_license(db_session, tenant_id=22, user_id=202, email="insight-test@example.com")

    _add_payment_tx(
        db_session,
        tenant_id=live_user.tenant_id,
        trans_id="LIVE-SUCCESS-3",
        provider_status="PAID",
        event_type="paid_confirmed",
        amount_halers=19900,
        is_test=False,
    )
    _add_payment_tx(
        db_session,
        tenant_id=test_user.tenant_id,
        trans_id="TEST-SUCCESS-3",
        provider_status="PAID",
        event_type="paid_confirmed",
        amount_halers=19900,
        is_test=True,
    )
    db_session.commit()

    cc_live = admin_api.get_user_license_payment_insight(
        user_id=live_user.id,
        email="developer@example.com",
        db=db_session,
    )
    cc_test = admin_api.get_user_license_payment_insight(
        user_id=test_user.id,
        email="developer@example.com",
        db=db_session,
    )
    user_detail_live = admin_api.get_user_detail(
        user_id=live_user.id,
        email="developer@example.com",
        db=db_session,
    )

    assert cc_live["payments_summary"]["has_paid"] is True
    assert cc_live["payments_summary"]["has_live_paid"] is True
    assert cc_live["payments_summary"]["live_paid_count"] == 1
    assert cc_live["payments_summary"]["count_live"] == 1
    assert cc_live["payments"][0]["payment_environment"] == "LIVE"

    assert cc_test["payments_summary"]["has_paid"] is False
    assert cc_test["payments_summary"]["has_test_paid"] is True
    assert cc_test["payments_summary"]["test_paid_count"] == 1
    assert cc_test["payments_summary"]["count_test"] == 1
    assert cc_test["payments"][0]["payment_environment"] == "TEST"

    # User detail endpoint must match control-center insight semantics.
    detail_summary = user_detail_live["insight"]["payments_summary"]
    assert detail_summary["has_paid"] is True
    assert detail_summary["has_live_paid"] is True
    assert detail_summary["live_paid_count"] == 1


def test_admin_vehicle_views_use_vehicle_ownership_source_of_truth(db_session):
    owner = _seed_user_with_license(db_session, tenant_id=30, user_id=300, email="owner-admin@example.com")
    vehicle = _seed_owned_vehicle(
        db_session,
        tenant_id=owner.tenant_id,
        owner=owner,
        vehicle_id=3000,
        legacy_user_email="stale-legacy@example.com",
        nickname="Ownership Admin Vehicle",
    )

    user_vehicles = admin_api.get_user_vehicles(
        user_id=owner.id,
        email="developer@example.com",
        db=db_session,
    )
    assert len(user_vehicles) == 1
    assert user_vehicles[0].id == vehicle.id
    assert user_vehicles[0].user_email == owner.email

    all_vehicles = admin_api.get_all_vehicles(
        limit=50,
        offset=0,
        email="developer@example.com",
        db=db_session,
    )
    by_id = {item["id"]: item for item in all_vehicles}
    assert by_id[vehicle.id]["owner_id"] == owner.id
    assert by_id[vehicle.id]["owner_name"] == owner.name
    assert by_id[vehicle.id]["user_email"] == owner.email


def test_admin_update_vehicle_reassigns_primary_owner_via_ownership(db_session):
    old_owner = _seed_user_with_license(db_session, tenant_id=31, user_id=310, email="old-owner@example.com")
    new_owner = Customer(
        id=311,
        tenant_id=31,
        email="new-owner@example.com",
        password_hash="hash",
        role="user",
        name="new-owner",
        created_at=datetime.utcnow(),
    )
    db_session.add(new_owner)
    db_session.commit()
    db_session.refresh(new_owner)
    vehicle = _seed_owned_vehicle(
        db_session,
        tenant_id=old_owner.tenant_id,
        owner=old_owner,
        vehicle_id=3100,
        legacy_user_email="legacy-owner@example.com",
        nickname="Transfer Vehicle",
    )

    response = admin_api.update_vehicle(
        vehicle_id=vehicle.id,
        vehicle_data=admin_api.VehicleUpdate(user_email=new_owner.email),
        request=None,
        email="developer@example.com",
        db=db_session,
    )

    assert response["message"] == "Vozidlo bylo upraveno"
    db_session.refresh(vehicle)
    assert vehicle.user_email == new_owner.email
    assert vehicle.tenant_id == new_owner.tenant_id

    active_owner = (
        db_session.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == vehicle.id,
            VehicleOwnership.is_primary.is_(True),
            VehicleOwnership.is_active.is_(True),
        )
        .one()
    )
    assert active_owner.customer_id == new_owner.id


def _init_sqlite_schema(path: Path) -> None:
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=engine)
    engine.dispose()


def test_restore_user_scope_uses_legacy_email_bridge_when_backup_ownership_rows_are_missing(tmp_path: Path):
    target_db = tmp_path / "target.sqlite"
    backup_db = tmp_path / "backup.sqlite"
    _init_sqlite_schema(target_db)
    _init_sqlite_schema(backup_db)

    with sqlite3.connect(str(backup_db)) as conn:
        conn.execute(
            """
            INSERT INTO customers (
                id, tenant_id, email, password_hash, role, name,
                is_disabled, is_deleted, session_version, created_at,
                partner_catalog_approved, account_status, force_password_change
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                1,
                "restore@example.com",
                "hash",
                "user",
                "Restore User",
                0,
                0,
                0,
                datetime.utcnow().isoformat(),
                0,
                "pending_email_verification",
                0,
            ),
        )
        conn.execute(
            """
            INSERT INTO vehicles (
                id, tenant_id, user_email, nickname, brand, model, vin, plate, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                10,
                1,
                "restore@example.com",
                "Legacy Car",
                "Skoda",
                "Fabia",
                "TMBARESTORE123456",
                "1AB2345",
                "active",
                datetime.utcnow().isoformat(),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.execute(
            """
            INSERT INTO service_records (
                id, tenant_id, vehicle_id, user_id, performed_at, description, price,
                created_by_ai, is_deleted, record_status, origin, visibility_scope, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                100,
                1,
                10,
                1,
                datetime.utcnow().isoformat(),
                "Legacy restore record",
                1500.0,
                0,
                0,
                "draft",
                "user_manual",
                "full_current_owner",
                datetime.utcnow().isoformat(),
            ),
        )
        conn.execute("DELETE FROM vehicle_ownerships")
        conn.commit()

    restored = admin_api._restore_user_scope_from_backup(
        backup_db_file=backup_db,
        target_db_file=target_db,
        user_id=1,
    )

    assert restored["vehicle_ownerships"] == 0
    assert restored["vehicles"] == 1
    assert restored["service_records"] == 1


def test_restore_vehicle_scope_uses_legacy_email_bridge_when_backup_ownership_rows_are_missing(tmp_path: Path):
    target_db = tmp_path / "target_vehicle.sqlite"
    backup_db = tmp_path / "backup_vehicle.sqlite"
    _init_sqlite_schema(target_db)
    _init_sqlite_schema(backup_db)

    with sqlite3.connect(str(backup_db)) as conn:
        conn.execute(
            """
            INSERT INTO customers (
                id, tenant_id, email, password_hash, role, name,
                is_disabled, is_deleted, session_version, created_at,
                partner_catalog_approved, account_status, force_password_change
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                7,
                1,
                "vehicle-owner@example.com",
                "hash",
                "user",
                "Vehicle Owner",
                0,
                0,
                0,
                datetime.utcnow().isoformat(),
                0,
                "pending_email_verification",
                0,
            ),
        )
        conn.execute(
            """
            INSERT INTO vehicles (
                id, tenant_id, user_email, nickname, brand, model, vin, plate, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                11,
                1,
                "vehicle-owner@example.com",
                "Legacy Vehicle",
                "VW",
                "Golf",
                "WVWRESTORE1234567",
                "2BC3456",
                "active",
                datetime.utcnow().isoformat(),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.execute("DELETE FROM vehicle_ownerships")
        conn.commit()

    restored = admin_api._restore_vehicle_scope_from_backup(
        backup_db_file=backup_db,
        target_db_file=target_db,
        vehicle_id=11,
    )

    assert restored["vehicle_ownerships"] == 0
    assert restored["customers"] == 1
    assert restored["vehicles"] == 1
