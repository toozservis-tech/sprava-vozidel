"""Admin vehicle support snapshot, corrections a RBAC nad izolovanou FastAPI + slabé integrace na TEST_API_URL."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.security import create_access_token
from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import (
    Customer,
    DeveloperActionAuditLog,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehiclePhotoAsset,
)
from src.server import admin_vehicle_support as avs
from src.server.admin_api import require_developer_admin

FORBIDDEN_SNAPSHOT_KEYS = frozenset(
    {
        "password_hash",
        "password",
        "reset_token",
        "password_reset_token",
        "otp_secret",
        "two_factor_secret",
        "mfa_secret",
        "billing_token",
        "stripe_customer_secret",
        "api_secret",
        "jwt_secret",
    }
)


def _assert_no_forbidden_keys(obj: object) -> None:
    if isinstance(obj, dict):
        for key, val in obj.items():
            lk = str(key).lower()
            assert lk not in FORBIDDEN_SNAPSHOT_KEYS, f"name={key}"
            _assert_no_forbidden_keys(val)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_forbidden_keys(item)


@pytest.fixture()
def support_stack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "admin_support.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="Tn", license_key="admin-support-test-tenant-key")
    db.add(tenant)
    db.flush()

    admin = Customer(tenant_id=tenant.id, email="admin-sup@x.cz", role="developer_admin", name="Admin")
    owner = Customer(tenant_id=tenant.id, email="owner-sup@x.cz", role="user", name="Owner")
    db.add(admin)
    db.add(owner)
    db.flush()

    vehicle = Vehicle(tenant_id=tenant.id, user_email=owner.email, nickname="Pre", plate="AA1234")
    db.add(vehicle)
    db.flush()

    ownership = VehicleOwnership(
        tenant_id=tenant.id,
        vehicle_id=vehicle.id,
        customer_id=owner.id,
        is_primary=True,
        is_active=True,
    )
    db.add(ownership)
    db.commit()

    app = FastAPI()
    app.include_router(avs.router, prefix="/admin-api")

    def _db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[require_developer_admin] = lambda: admin.email

    monkeypatch.setattr(avs, "send_customer_change_notification_email", lambda **kwargs: None)

    client = TestClient(app)
    try:
        yield client, db, vehicle.id, admin.email
    finally:
        db.close()


@pytest.fixture()
def rbac_stack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Skutečné `require_developer_admin` — autorizace přes JWT Bearer (sub → customers.role)."""
    db_path = tmp_path / "admin_support_rbac.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="Tn2", license_key="admin-support-rbac-tenant-key")
    db.add(tenant)
    db.flush()

    admin = Customer(tenant_id=tenant.id, email="adm-rbac@x.cz", role="developer_admin", name="Admin")
    owner = Customer(tenant_id=tenant.id, email="owner-rbac@x.cz", role="user", name="Owner")
    service = Customer(tenant_id=tenant.id, email="svc-rbac@x.cz", role="service", name="Srv")
    db.add(admin)
    db.add(owner)
    db.add(service)
    db.flush()

    vehicle = Vehicle(tenant_id=tenant.id, user_email=owner.email, nickname="Rb", plate="RB1111")
    db.add(vehicle)
    db.flush()

    ownership = VehicleOwnership(
        tenant_id=tenant.id,
        vehicle_id=vehicle.id,
        customer_id=owner.id,
        is_primary=True,
        is_active=True,
    )
    db.add(ownership)
    db.commit()

    jpg_path = tmp_path / "stub.jpg"
    jpg_path.write_bytes(b"x")

    monkeypatch.setattr(avs, "resolve_storage_file", lambda _root, _key: jpg_path)

    photo_key = f"tenants/{tenant.id}/vehicles/{vehicle.id}/stub.jpg"
    asset = VehiclePhotoAsset(
        tenant_id=tenant.id,
        vehicle_id=vehicle.id,
        role="gallery",
        photo_kind="other",
        storage_key=photo_key,
        storage_path_preview=None,
        original_filename="stub.jpg",
        mime_type="image/jpeg",
        file_size_bytes=1,
        sha256_hex="0" * 64,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    app = FastAPI()
    app.include_router(avs.router, prefix="/admin-api")

    def _db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _db

    tc = TestClient(app)

    def _tok(email: str) -> str:
        return create_access_token(data={"sub": email, "sv": 0})

    try:
        yield tc, db, vehicle.id, asset.id, _tok
    finally:
        db.close()


def test_detail_snapshot_shape_view_audit_safe(support_stack: tuple) -> None:
    client, db, vid, _admin_email = support_stack
    before = (
        db.query(DeveloperActionAuditLog)
        .filter(DeveloperActionAuditLog.action_type == "admin_vehicle_detail_viewed")
        .count()
    )
    r = client.get(f"/admin-api/vehicles/{vid}/detail-snapshot")
    assert r.status_code == 200, r.text
    data = r.json()
    _assert_no_forbidden_keys(data)
    assert "account_name_hint" not in data.get("owner_context", {})
    assert data["permissions"].get("min_reason_length") == 10

    assert data["mode"] == "admin_support_view"
    assert data["permissions"]["default_read_only"] is True
    assert data["owner_context"].get("owner_user_id") is not None
    after = (
        db.query(DeveloperActionAuditLog)
        .filter(DeveloperActionAuditLog.action_type == "admin_vehicle_detail_viewed")
        .count()
    )
    assert after == before + 1


def test_correction_reason_empty_validation(support_stack: tuple) -> None:
    client, _db, vid, _ = support_stack
    r = client.post(
        f"/admin-api/vehicles/{vid}/corrections",
        json={
            "target_entity": "vehicle",
            "field": "nickname",
            "old_value": "Pre",
            "new_value": "X",
            "reason": "",
            "notify_user": False,
        },
    )
    assert r.status_code == 422


def test_correction_reason_too_short(support_stack: tuple) -> None:
    client, _db, vid, _ = support_stack
    r = client.post(
        f"/admin-api/vehicles/{vid}/corrections",
        json={
            "target_entity": "vehicle",
            "field": "nickname",
            "old_value": "Pre",
            "new_value": "X",
            "reason": "krátký",
            "notify_user": False,
        },
    )
    assert r.status_code == 422


def test_correction_disallowed_vehicle_field(support_stack: tuple) -> None:
    client, _db, vid, _ = support_stack
    r = client.post(
        f"/admin-api/vehicles/{vid}/corrections",
        json={
            "target_entity": "vehicle",
            "field": "tenant_id",
            "old_value": "1",
            "new_value": "2",
            "reason": "Nelegální pole test záměrně dlouhé",
            "notify_user": False,
        },
    )
    assert r.status_code == 400


def test_correction_rejects_wrong_old_value(support_stack: tuple) -> None:
    client, _db, vid, _ = support_stack
    r = client.post(
        f"/admin-api/vehicles/{vid}/corrections",
        json={
            "target_entity": "vehicle",
            "field": "nickname",
            "old_value": "not-in-db",
            "new_value": "X",
            "reason": "Chybná očekávaná hodnota kvůli testu",
            "notify_user": False,
        },
    )
    assert r.status_code == 409


def test_correction_applies_audit_email_hook(support_stack: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    client, db, vid, _ = support_stack
    mock_send = MagicMock()
    monkeypatch.setattr(avs, "send_customer_change_notification_email", mock_send)

    before = (
        db.query(DeveloperActionAuditLog)
        .filter(DeveloperActionAuditLog.action_type == "admin_vehicle_correction_applied")
        .count()
    )
    r = client.post(
        f"/admin-api/vehicles/{vid}/corrections",
        json={
            "target_entity": "vehicle",
            "field": "nickname",
            "old_value": "Pre",
            "new_value": "Post",
            "reason": "Oprava nickname v rámci testu suite",
            "notify_user": True,
        },
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["notification_status"] == "sent"
    assert mock_send.called
    row = db.query(Vehicle).filter(Vehicle.id == vid).first()
    assert row is not None
    assert row.nickname == "Post"
    after = (
        db.query(DeveloperActionAuditLog)
        .filter(DeveloperActionAuditLog.action_type == "admin_vehicle_correction_applied")
        .count()
    )
    assert after == before + 1


def test_correction_email_failure_marks_notification_failed(
    support_stack: tuple,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, db, vid, _ = support_stack

    def _boom(**kwargs):
        raise ValueError("smtp simulated failure")

    monkeypatch.setattr(avs, "send_customer_change_notification_email", _boom)

    vehicle = db.query(Vehicle).filter(Vehicle.id == vid).first()
    vehicle.nickname = "NickA"
    db.commit()

    r = client.post(
        f"/admin-api/vehicles/{vid}/corrections",
        json={
            "target_entity": "vehicle",
            "field": "nickname",
            "old_value": "NickA",
            "new_value": "NickB",
            "reason": "Simulace selhání SMTP v pytest kontrole delší",
            "notify_user": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["notification_status"] == "failed"
    assert any(w.get("code") == "email_failed" for w in body.get("warnings") or [])
    db.refresh(vehicle)
    assert vehicle.nickname == "NickB"


def test_admin_change_table_required_when_owner_exists(support_stack: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _db, vid, _ = support_stack
    monkeypatch.setattr(avs, "admin_change_table_exists", lambda _db: False)
    r = client.post(
        f"/admin-api/vehicles/{vid}/corrections",
        json={
            "target_entity": "vehicle",
            "field": "plate",
            "old_value": "AA1234",
            "new_value": "BB9999",
            "reason": "Změna SPZ jen kvůli testu dostatečný text zde.",
            "notify_user": False,
        },
    )
    assert r.status_code == 503


def test_rbac_anonymous_snapshot_rejected(rbac_stack: tuple) -> None:
    tc, *_rest = rbac_stack
    r = tc.get("/admin-api/vehicles/999/detail-snapshot")
    assert r.status_code in {401, 403}


def test_rbac_regular_user_snapshot_403(rbac_stack: tuple) -> None:
    tc, _db, vid, _pid, tok = rbac_stack
    r = tc.get(
        f"/admin-api/vehicles/{vid}/detail-snapshot",
        headers={"Authorization": f"Bearer {tok('owner-rbac@x.cz')}"},
    )
    assert r.status_code == 403


def test_rbac_service_snapshot_403(rbac_stack: tuple) -> None:
    tc, _db, vid, _pid, tok = rbac_stack
    r = tc.get(
        f"/admin-api/vehicles/{vid}/detail-snapshot",
        headers={"Authorization": f"Bearer {tok('svc-rbac@x.cz')}"},
    )
    assert r.status_code == 403


def test_rbac_admin_snapshot_200_and_photo_audited(rbac_stack: tuple) -> None:
    tc, db, vid, pid, tok = rbac_stack
    hdr = {"Authorization": f"Bearer {tok('adm-rbac@x.cz')}"}
    before_view = db.query(DeveloperActionAuditLog).filter_by(action_type="admin_vehicle_detail_viewed").count()
    r = tc.get(f"/admin-api/vehicles/{vid}/detail-snapshot", headers=hdr)
    assert r.status_code == 200, r.text
    assert db.query(DeveloperActionAuditLog).filter_by(action_type="admin_vehicle_detail_viewed").count() == before_view + 1

    before_ph = db.query(DeveloperActionAuditLog).filter_by(action_type="admin_vehicle_support_photo_viewed").count()
    pr = tc.get(f"/admin-api/vehicles/{vid}/support-photo/{pid}/file", headers=hdr)
    assert pr.status_code == 200, pr.text
    assert db.query(DeveloperActionAuditLog).filter_by(action_type="admin_vehicle_support_photo_viewed").count() == before_ph + 1


def test_rbac_user_photo_stream_403(rbac_stack: tuple) -> None:
    tc, _db, vid, pid, tok = rbac_stack
    r = tc.get(
        f"/admin-api/vehicles/{vid}/support-photo/{pid}/file",
        headers={"Authorization": f"Bearer {tok('owner-rbac@x.cz')}"},
    )
    assert r.status_code == 403


def test_integration_snapshot_unauthenticated_admin_api_only(api_url: str) -> None:
    try:
        r = requests.get(f"{api_url}/admin-api/vehicles/1/detail-snapshot", timeout=3)
    except requests.RequestException:
        pytest.skip("TEST_API_URL nedostupné")
    if r.status_code == 404:
        pytest.skip("snapshot endpoint není nasazen — restart backendu")
    assert r.status_code in (401, 403)


def test_integration_snapshot_regular_user_admin_api(api_url: str, auth_token) -> None:
    if not auth_token:
        pytest.skip("bez auth tokenu")
    try:
        r = requests.get(
            f"{api_url}/admin-api/vehicles/1/detail-snapshot",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=3,
        )
    except requests.RequestException:
        pytest.skip("TEST_API_URL nedostupné")
    if r.status_code == 404:
        pytest.skip("snapshot endpoint není nasazen — restart backendu")
    assert r.status_code == 403


def test_vehicle_support_removed_from_api_admin_mount(api_url: str) -> None:
    try:
        r = requests.get(f"{api_url}/api/admin/vehicles/1/detail-snapshot", timeout=3)
    except requests.RequestException:
        pytest.skip("TEST_API_URL nedostupné")
    assert r.status_code in (403, 404), (
        "vehicle support nesmí být dostupný pod /api/admin (mount odstraněn nebo jen zakázán)"
    )
