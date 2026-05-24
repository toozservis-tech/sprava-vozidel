"""Pravdivost e-mail notifikací: servisní zákazníci + žádosti o přístup (bez reálného SMTP)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import (
    Customer,
    GlobalAuditLog,
    ServiceAccessRequest,
    ServiceCustomerLink,
    Tenant,
    UserOnboardingToken,
    Vehicle,
    VehicleOwnership,
)
from src.modules.vehicle_hub.routers_v1 import service_workspace as workspace_router
from src.modules.vehicle_hub.routers_v1 import service_workspace_customer_centre as cc_router_mod
from src.modules.vehicle_hub.routers_v1.auth import get_current_user


@pytest.fixture()
def centre_db(tmp_path: Path):
    db_path = tmp_path / "email_cc.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    tenant = Tenant(name="T-em", license_key="lic-em-1")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    svc = Customer(
        tenant_id=tenant.id,
        email="svc.em@example.com",
        password_hash="x",
        name="Servis EM",
        role="service",
    )
    db.add(svc)
    db.commit()
    db.refresh(svc)
    try:
        yield db, svc, tenant
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def centre_api(centre_db, monkeypatch: pytest.MonkeyPatch):
    db, svc, _tenant = centre_db
    monkeypatch.setattr(cc_router_mod, "assert_module_ready", lambda *a, **k: None)

    app = FastAPI()
    app.include_router(cc_router_mod.router, prefix="/api/v1/services/workspace")

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[cc_router_mod.get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: svc
    yield TestClient(app), db, svc


class _OkEmail:
    def is_configured(self) -> bool:
        return True

    def send_simple_email(self, **kwargs):  # noqa: ANN003
        return True


class _NoSmtpEmail:
    def is_configured(self) -> bool:
        return False

    def send_simple_email(self, **kwargs):  # noqa: ANN003
        raise AssertionError("send_simple_email should not run when not configured")


def test_service_create_customer_email_success(centre_api, monkeypatch: pytest.MonkeyPatch):
    client, db, svc = centre_api
    monkeypatch.setattr(cc_router_mod, "EmailService", _OkEmail)
    resp = client.post(
        "/api/v1/services/workspace/customers/create",
        json={
            "first_name": "Nov",
            "last_name": "Zákazník",
            "email": "new.ok.email@example.com",
            "phone": "+420606111222",
            "consent_basis": "test",
            "consent_note": "test souhlas",
            "create_vehicle": False,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["email_sent"] is True
    assert data["notification"]["sent"] is True
    assert "zákazník byl přidán" in data["message"].lower()
    assert data.get("notification", {}).get("message")
    assert "token" not in resp.text
    uid = int(data["customer_user_id"])
    tok = db.query(UserOnboardingToken).filter(UserOnboardingToken.user_id == uid).first()
    assert tok is not None and tok.token_hash and len(tok.token_hash) > 20
    aud = (
        db.query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.action == "SERVICE_CUSTOMER_INVITE_EMAIL_SENT",
            GlobalAuditLog.entity_id == uid,
        )
        .order_by(GlobalAuditLog.id.desc())
        .first()
    )
    assert aud is not None
    meta = json.loads(aud.metadata_json or "{}")
    assert meta.get("sent") is True


def test_service_create_customer_smtp_not_configured(centre_api, monkeypatch: pytest.MonkeyPatch):
    client, db, _svc = centre_api
    monkeypatch.setattr(cc_router_mod, "EmailService", _NoSmtpEmail)
    resp = client.post(
        "/api/v1/services/workspace/customers/create",
        json={
            "first_name": "Bez",
            "last_name": "SMTP",
            "email": "nosmtp.customer@example.com",
            "phone": "+420606333444",
            "consent_basis": "test",
            "consent_note": "test souhlas",
            "create_vehicle": False,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["email_sent"] is False
    assert data["notification"]["reason"] == "smtp_not_configured"
    assert "zákazník byl přidán" in data["message"].lower()
    assert "nepodařilo" in data["message"].lower()
    uid = int(data["customer_user_id"])
    assert db.query(UserOnboardingToken).filter(UserOnboardingToken.user_id == uid).count() == 1
    aud = (
        db.query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.action == "SERVICE_CUSTOMER_INVITE_EMAIL_FAILED",
            GlobalAuditLog.entity_id == uid,
        )
        .order_by(GlobalAuditLog.id.desc())
        .first()
    )
    assert aud is not None


def test_link_from_lookup_confirm_email_failed(centre_api, monkeypatch: pytest.MonkeyPatch):
    client, db, svc = centre_api
    monkeypatch.setattr(cc_router_mod, "EmailService", _NoSmtpEmail)

    tenant_id = svc.tenant_id
    owner = Customer(
        tenant_id=tenant_id,
        email="lookup.owner@example.com",
        password_hash="x",
        name="Owner L",
        role="user",
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    r_search = client.post(
        "/api/v1/services/workspace/customers/search",
        json={"email": owner.email},
    )
    assert r_search.status_code == 200, r_search.text
    lookup_id = r_search.json()["customer_preview"]["lookup_id"]

    r_link = client.post(
        "/api/v1/services/workspace/customers/link-from-lookup",
        json={
            "lookup_id": lookup_id,
            "consent_basis": "test",
            "consent_note": "test note for link",
        },
    )
    assert r_link.status_code == 200, r_link.text
    out = r_link.json()
    assert out.get("email_sent") is False
    assert out["notification"]["reason"] == "smtp_not_configured"
    row = (
        db.query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.action == "SERVICE_CUSTOMER_LINK_CONFIRM_EMAIL_FAILED",
            GlobalAuditLog.entity_id == int(owner.id),
        )
        .order_by(GlobalAuditLog.id.desc())
        .first()
    )
    assert row is not None


def test_customer_link_from_lookup_already_active_has_notification_shape(centre_api, monkeypatch: pytest.MonkeyPatch):
    client, db, svc = centre_api
    monkeypatch.setattr(cc_router_mod, "EmailService", _OkEmail)

    tenant_id = svc.tenant_id
    owner = Customer(
        tenant_id=tenant_id,
        email="active.lookup.owner@example.com",
        password_hash="x",
        name="Owner Active",
        role="user",
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    db.add(
        ServiceCustomerLink(
            service_tenant_id=tenant_id,
            service_customer_id=int(svc.id),
            customer_tenant_id=tenant_id,
            customer_id=int(owner.id),
            status="active",
            link_source="test_seed",
            consent_basis="test",
            consent_note="test",
            created_by_service_user_id=int(svc.id),
        )
    )
    db.commit()

    r_search = client.post(
        "/api/v1/services/workspace/customers/search",
        json={"email": owner.email},
    )
    assert r_search.status_code == 200, r_search.text
    lookup_id = r_search.json()["customer_preview"]["lookup_id"]

    r_link = client.post(
        "/api/v1/services/workspace/customers/link-from-lookup",
        json={
            "lookup_id": lookup_id,
            "consent_basis": "test",
            "consent_note": "note",
        },
    )
    assert r_link.status_code == 200, r_link.text
    out = r_link.json()
    assert out["linked"] is True
    assert out["pending_customer_confirm"] is False
    assert out["email_sent"] is False
    assert out["notification"]["sent"] is False
    assert out["notification"]["reason"] == "already_active"
    assert out["customer_user_id"] == int(owner.id)


def test_access_request_notifications_keys(access_stack, monkeypatch: pytest.MonkeyPatch):
    """created + email_sent + notification struktura (regrese pro service shell)."""
    client, _db, _owner, _service, vehicle = access_stack

    def fake_send(*, to_email: str, subject: str, plain_body: str) -> bool:
        return True

    monkeypatch.setattr(
        "src.modules.vehicle_hub.service_access_messaging.send_service_access_request_email",
        fake_send,
    )
    r = client.post(
        "/api/v1/services/workspace/access-requests",
        json={"vehicle_id": vehicle.id, "lookup_query": vehicle.plate, "note": "x"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "created" in data
    assert "email_sent" in data
    assert data["notification"]["channel"] == "email"
    assert "message" in data["notification"]
    assert int(data["vehicle_id"]) == int(vehicle.id)
    assert data["message"] == "Žádost o přístup k vozidlu byla odeslána. Čeká se na vyjádření uživatele."
    assert data["notification"]["sent"] is True
    assert data["notification"]["message"] == "Uživatel byl upozorněn e-mailem."


@pytest.fixture()
def access_stack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "email_ar.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    monkeypatch.setattr(workspace_router, "_ensure_service_workspace_schema", lambda _db: None)

    tenant = Tenant(name="T-ar", license_key="lic-ar")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(
        tenant_id=tenant.id,
        email="owner.ar@example.com",
        password_hash="x",
        name="Owner AR",
        role="user",
    )
    service = Customer(
        tenant_id=tenant.id,
        email="svc.ar@example.com",
        password_hash="x",
        name="Servis AR",
        role="service",
    )
    db.add_all([owner, service])
    db.commit()
    db.refresh(owner)
    db.refresh(service)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="V",
        plate="EMAR1",
        vin="TMBEMAR123456789",
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    db.add(
        VehicleOwnership(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            ownership_type="owner",
            ownership_origin="manual",
            is_primary=True,
            is_active=True,
        )
    )
    db.commit()

    app = FastAPI()
    app.include_router(workspace_router.router, prefix="/api/v1")

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: service

    client = TestClient(app)
    try:
        yield client, db, owner, service, vehicle
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def test_access_request_email_success(access_stack, monkeypatch: pytest.MonkeyPatch):
    client, db, owner, service, vehicle = access_stack
    sent: list[bool] = []

    def fake_send(*, to_email: str, subject: str, plain_body: str) -> bool:
        sent.append(True)
        assert "Servis žádá o přístup k vozidlu" in subject
        assert "servis" in plain_body.lower()
        assert "EM" in plain_body or "SPZ" in plain_body or "vozidlu" in plain_body.lower()
        return True

    monkeypatch.setattr(
        "src.modules.vehicle_hub.service_access_messaging.send_service_access_request_email",
        fake_send,
    )
    r = client.post(
        "/api/v1/services/workspace/access-requests",
        json={"vehicle_id": vehicle.id, "lookup_query": vehicle.plate, "note": "x"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["created"] is True
    assert data["email_sent"] is True
    assert int(data["vehicle_id"]) == int(vehicle.id)
    assert data["message"] == "Žádost o přístup k vozidlu byla odeslána. Čeká se na vyjádření uživatele."
    assert data["notification"]["sent"] is True
    assert data["notification"]["reason"] is None
    assert data["notification"]["message"] == "Uživatel byl upozorněn e-mailem."
    assert sent == [True]
    rid = int(data["request_id"])
    aud = (
        db.query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.action == "service_access_request_email_sent",
            GlobalAuditLog.entity_id == rid,
        )
        .first()
    )
    assert aud is not None
    meta = json.loads(aud.metadata_json or "{}")
    assert meta.get("service_id") == int(service.id)
    assert meta.get("vehicle_id") == int(vehicle.id)


def test_access_request_smtp_unavailable(access_stack, monkeypatch: pytest.MonkeyPatch):
    client, db, owner, _service, vehicle = access_stack
    monkeypatch.setattr(
        "src.modules.vehicle_hub.service_access_messaging.send_service_access_request_email",
        None,
    )

    class NoSmtp:
        def is_configured(self) -> bool:
            return False

        def send_email(self, _msg):  # noqa: ANN001
            raise AssertionError("should not send")

    monkeypatch.setattr("src.modules.vehicle_hub.service_access_messaging.EmailService", NoSmtp)

    r = client.post(
        "/api/v1/services/workspace/access-requests",
        json={"vehicle_id": vehicle.id, "lookup_query": vehicle.plate},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["created"] is True
    assert data["email_sent"] is False
    assert data["notification"]["reason"] == "smtp_not_configured"
    assert data["notification"]["message"] == "Žádost byla uložena, ale e-mail se nepodařilo odeslat."
    assert int(data["vehicle_id"]) == int(vehicle.id)
    rid = int(data["request_id"])
    row = (
        db.query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.action == "service_access_request_email_smtp_unavailable",
            GlobalAuditLog.entity_id == rid,
        )
        .first()
    )
    assert row is not None


def test_access_request_send_returns_false_counts_as_failed(access_stack, monkeypatch: pytest.MonkeyPatch):
    client, db, owner, service, vehicle = access_stack

    def fake_send(*, to_email: str, subject: str, plain_body: str) -> bool:
        return False

    monkeypatch.setattr(
        "src.modules.vehicle_hub.service_access_messaging.send_service_access_request_email",
        fake_send,
    )
    r = client.post(
        "/api/v1/services/workspace/access-requests",
        json={"vehicle_id": vehicle.id, "lookup_query": vehicle.plate},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["created"] is True
    assert data["email_sent"] is False
    assert data["notification"]["reason"] == "send_failed"
    assert data["notification"]["message"] == "Žádost byla uložena, ale e-mail se nepodařilo odeslat."
    rid = int(data["request_id"])
    row = (
        db.query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.action == "service_access_request_email_failed",
            GlobalAuditLog.entity_id == rid,
        )
        .first()
    )
    assert row is not None


def test_access_request_send_raises_no_500(access_stack, monkeypatch: pytest.MonkeyPatch):
    client, db, owner, service, vehicle = access_stack

    def boom(**_kwargs):
        raise RuntimeError("smtp transport error")

    monkeypatch.setattr(
        "src.modules.vehicle_hub.service_access_messaging.send_service_access_request_email",
        boom,
    )
    r = client.post(
        "/api/v1/services/workspace/access-requests",
        json={"vehicle_id": vehicle.id, "lookup_query": vehicle.plate},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["created"] is True
    assert data["email_sent"] is False
    assert data["notification"]["reason"] == "send_failed"
    rid = int(data["request_id"])
    row = (
        db.query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.action == "service_access_request_email_failed",
            GlobalAuditLog.entity_id == rid,
        )
        .first()
    )
    assert row is not None


def test_workspace_access_request_forbidden_for_non_service(access_stack):
    client, db, owner, service, vehicle = access_stack
    client.app.dependency_overrides[get_current_user] = lambda: owner
    try:
        r = client.post(
            "/api/v1/services/workspace/access-requests",
            json={"vehicle_id": vehicle.id, "lookup_query": vehicle.plate},
        )
        assert r.status_code == 403, r.text
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: service


def test_access_request_existing_pending_no_duplicate_email(access_stack, monkeypatch: pytest.MonkeyPatch):
    client, db, owner, service, vehicle = access_stack
    calls: list[int] = []

    def fake_send(*, to_email: str, subject: str, plain_body: str) -> bool:
        calls.append(1)
        return True

    monkeypatch.setattr(
        "src.modules.vehicle_hub.service_access_messaging.send_service_access_request_email",
        fake_send,
    )

    r1 = client.post(
        "/api/v1/services/workspace/access-requests",
        json={"vehicle_id": vehicle.id, "lookup_query": vehicle.plate},
    )
    assert r1.status_code == 200, r1.json()
    assert r1.json()["created"] is True
    assert r1.json()["email_sent"] is True

    r2 = client.post(
        "/api/v1/services/workspace/access-requests",
        json={"vehicle_id": vehicle.id, "lookup_query": vehicle.plate},
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["created"] is False
    assert data["email_sent"] is False
    assert data["notification"]["reason"] == "existing_pending"
    assert int(data["vehicle_id"]) == int(vehicle.id)
    assert data["message"] == "Žádost už čeká na potvrzení."
    assert data["notification"]["message"] == "Žádost už čeká na potvrzení. Nový e-mail nebyl odeslán."
    assert calls == [1]
    assert db.query(ServiceAccessRequest).filter(ServiceAccessRequest.vehicle_id == vehicle.id).count() == 1


@pytest.fixture()
def link_existing_direct_api(centre_db, monkeypatch: pytest.MonkeyPatch):
    """POST /customers/link-existing je na workspace routeru, ne na customer_centre."""
    db, svc, tenant = centre_db
    monkeypatch.setattr(workspace_router, "_ensure_service_workspace_schema", lambda _db: None)

    owner = Customer(
        tenant_id=tenant.id,
        email="direct.link.owner@example.com",
        password_hash="x",
        name="Owner DirectLink",
        role="user",
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    app = FastAPI()
    app.include_router(workspace_router.router, prefix="/api/v1")

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: svc
    client = TestClient(app)
    try:
        yield client, db, svc, owner
    finally:
        app.dependency_overrides.clear()


def test_link_existing_by_email_sends_notice_when_smtp_configured(
    link_existing_direct_api, monkeypatch: pytest.MonkeyPatch
):
    client, db, _svc, owner = link_existing_direct_api
    monkeypatch.setattr(cc_router_mod, "EmailService", _OkEmail)

    resp = client.post(
        "/api/v1/services/workspace/customers/link-existing",
        json={"customer_email": owner.email, "note": "n1"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["linked"] is True
    assert data["pending_customer_confirm"] is False
    assert data["email_sent"] is True
    assert data["notification"]["sent"] is True
    assert data["notification"]["reason"] is None
    assert "informační e-mail byl odeslán" in data["message"].lower()

    row_link = (
        db.query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.action == "link_existing_customer_by_email",
            GlobalAuditLog.entity_id == int(owner.id),
        )
        .order_by(GlobalAuditLog.id.desc())
        .first()
    )
    assert row_link is not None

    row_em = (
        db.query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.action == "SERVICE_CUSTOMER_DIRECT_LINK_EMAIL_SENT",
            GlobalAuditLog.entity_id == int(owner.id),
        )
        .order_by(GlobalAuditLog.id.desc())
        .first()
    )
    assert row_em is not None
    meta = json.loads(row_em.metadata_json or "{}")
    assert meta.get("kind") == "direct_link_existing_customer"
    assert meta.get("sent") is True
    assert meta.get("customer_id") == int(owner.id)


def test_link_existing_by_email_keeps_link_when_smtp_unavailable(
    link_existing_direct_api, monkeypatch: pytest.MonkeyPatch
):
    client, db, svc, owner = link_existing_direct_api
    monkeypatch.setattr(cc_router_mod, "EmailService", _NoSmtpEmail)

    resp = client.post(
        "/api/v1/services/workspace/customers/link-existing",
        json={"customer_email": owner.email},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["linked"] is True
    assert data["email_sent"] is False
    assert data["notification"]["reason"] == "smtp_not_configured"

    link_row = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == int(svc.id),
            ServiceCustomerLink.customer_id == int(owner.id),
        )
        .first()
    )
    assert link_row is not None
    assert link_row.status == "active"

    row_em = (
        db.query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.action == "SERVICE_CUSTOMER_DIRECT_LINK_EMAIL_FAILED",
            GlobalAuditLog.entity_id == int(owner.id),
        )
        .order_by(GlobalAuditLog.id.desc())
        .first()
    )
    assert row_em is not None


def test_link_existing_by_email_send_failure_no_500(link_existing_direct_api, monkeypatch: pytest.MonkeyPatch):
    client, db, _svc, owner = link_existing_direct_api

    class _BoomEmail:
        def is_configured(self) -> bool:
            return True

        def send_simple_email(self, **kwargs):  # noqa: ANN003
            raise RuntimeError("smtp transport down")

    monkeypatch.setattr(cc_router_mod, "EmailService", _BoomEmail)

    resp = client.post(
        "/api/v1/services/workspace/customers/link-existing",
        json={"customer_email": owner.email},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["linked"] is True
    assert data["email_sent"] is False
    assert data["notification"]["reason"] == "send_failed"

    row_em = (
        db.query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.action == "SERVICE_CUSTOMER_DIRECT_LINK_EMAIL_FAILED",
            GlobalAuditLog.entity_id == int(owner.id),
        )
        .order_by(GlobalAuditLog.id.desc())
        .first()
    )
    assert row_em is not None
