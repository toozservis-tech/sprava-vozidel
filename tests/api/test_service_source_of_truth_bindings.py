"""
Binding / audit tests: servisní customer centre, VehicleServiceLink vs legacy, GDPR vozidla,
faktury vázané na vozidlo, admin audit, ochrana servisních záznamů při mazání vozidla.
"""
import json
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import (
    Customer,
    GlobalAuditLog,
    ServiceCustomerLink,
    ServiceInvoiceCounter,
    ServiceRecord,
    ServiceVehicleAccess,
    Tenant,
    UserOnboardingToken,
    Vehicle,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub import service_workspace_customer_centre as cc
from src.modules.vehicle_hub.routers_v1 import service_workspace_customer_centre as cc_router_mod
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.modules.vehicle_hub.routers_v1 import service_records as service_records_router
from src.modules.vehicle_hub.routers_v1 import service_invoices as service_invoices_router
from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router
from src.modules.vehicle_hub.routers_v1.schemas import ServiceRecordCreateV1
from src.modules.vehicle_hub.database import get_db as vehicle_hub_get_db
from src.server import admin_api
from src.server.admin_api import require_developer_admin


@pytest.fixture()
def centre_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """SQLite + workspace customer router (search / create)."""
    db_path = tmp_path / "svc_sot_cc.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    tenant = Tenant(name="T-cc", license_key="lic-svc-sot-cc")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    svc = Customer(
        tenant_id=tenant.id,
        email="svc.sot@example.com",
        password_hash="x",
        name="Servis SOT",
        role="service",
    )
    db.add(svc)
    db.commit()
    db.refresh(svc)

    monkeypatch.setattr(
        cc_router_mod,
        "_send_service_customer_invite_email",
        lambda **kwargs: {"attempted": True, "sent": True, "reason": None, "error": None},
    )

    app = FastAPI()
    app.include_router(cc.router, prefix="/api/v1/services/workspace")

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[cc.get_db] = override_db

    def set_user(user: Customer):
        app.dependency_overrides[get_current_user] = lambda: user

    client = TestClient(app)
    try:
        yield {"client": client, "db": db, "svc": svc, "tenant": tenant, "set_user": set_user, "app": app}
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def test_service_customer_search_email_exact_match_masked(centre_client):
    ctx = centre_client
    db = ctx["db"]
    svc = ctx["svc"]
    usr = Customer(
        tenant_id=ctx["tenant"].id,
        email="masked.user@example.com",
        password_hash="x",
        name="Full Legal Name",
        role="user",
    )
    db.add(usr)
    db.commit()
    ctx["set_user"](svc)
    resp = ctx["client"].post(
        "/api/v1/services/workspace/customers/search",
        json={"email": usr.email},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("found") is True
    prev = data.get("customer_preview") or {}
    assert usr.email not in resp.text
    em = prev.get("email_masked") or ""
    assert "*" in em
    assert "masked.user" not in em.lower()
    assert "customer_user_id" not in prev and "user_id" not in prev


def test_service_customer_search_phone_exact_match(centre_client):
    ctx = centre_client
    db = ctx["db"]
    svc = ctx["svc"]
    usr = Customer(
        tenant_id=ctx["tenant"].id,
        email="phone.user@example.com",
        password_hash="x",
        name="Tel User",
        role="user",
        phone_e164="+420701234567",
        phone_normalized="420701234567",
    )
    db.add(usr)
    db.commit()
    ctx["set_user"](svc)
    resp = ctx["client"].post(
        "/api/v1/services/workspace/customers/search",
        json={"phone": "+420 701 234 567"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("found") is True


def test_service_customer_search_conflict(centre_client):
    ctx = centre_client
    db = ctx["db"]
    svc = ctx["svc"]
    a = Customer(
        tenant_id=ctx["tenant"].id,
        email="usera@example.com",
        password_hash="x",
        name="User A",
        role="user",
        phone_e164="+420731552211",
        phone_normalized="420731552211",
    )
    b = Customer(
        tenant_id=ctx["tenant"].id,
        email="userb@example.com",
        password_hash="x",
        name="User B",
        role="user",
        phone_e164="+420731552322",
        phone_normalized="420731552322",
    )
    db.add_all([a, b])
    db.commit()
    ctx["set_user"](svc)
    resp = ctx["client"].post(
        "/api/v1/services/workspace/customers/search",
        json={"email": "usera@example.com", "phone": "+420731552322"},
    )
    assert resp.status_code == 409


def test_service_create_customer_invite(centre_client):
    ctx = centre_client
    db = ctx["db"]
    svc = ctx["svc"]
    ctx["set_user"](svc)
    resp = ctx["client"].post(
        "/api/v1/services/workspace/customers/create",
        json={
            "first_name": "Nov",
            "last_name": "Zákazník",
            "email": "new.customer.invite@example.com",
            "phone": "+420606123456",
            "consent_basis": "service_intake_test",
            "consent_note": "Test souhlas pro vytvoření účtu ze servisu.",
            "create_vehicle": False,
        },
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert "token" not in out
    assert "password" not in resp.text.lower()
    uid = int(out["customer_user_id"])
    cust = db.query(Customer).filter(Customer.id == uid).first()
    assert cust is not None
    assert str(cust.role).lower() == "user"
    assert cust.password_hash is None
    assert cust.tenant_id != svc.tenant_id
    tok = db.query(UserOnboardingToken).filter(UserOnboardingToken.user_id == uid).first()
    assert tok is not None
    assert tok.token_hash
    assert len(tok.token_hash) > 20
    audit = (
        db.query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.entity_type == "service_customer_security",
            GlobalAuditLog.action == "SERVICE_CUSTOMER_CREATED_USER_ACCOUNT",
        )
        .order_by(GlobalAuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert int(audit.actor_user_id or 0) == int(svc.id)


@pytest.fixture()
def vehicle_access_stack(tmp_path: Path):
    db_path = tmp_path / "svc_sot_veh.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="T-veh", license_key="lic-svc-sot-veh")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    service = Customer(
        tenant_id=tenant.id,
        email="service.veh@example.com",
        name="Servis VEH",
        role="service",
    )
    owner = Customer(
        tenant_id=tenant.id,
        email="owner.veh@example.com",
        name="Majitel",
        role="user",
    )
    db.add_all([service, owner])
    db.commit()
    db.refresh(service)
    db.refresh(owner)

    vin = "1HGBH41JXMN109186"
    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Test",
        vin=vin,
        plate="3AB1234",
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
    app.include_router(vehicles_router.router, prefix="/api/v1")

    def _db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _db
    client = TestClient(app)

    def set_user(user: Customer):
        app.dependency_overrides[get_current_user] = lambda: user

    try:
        yield {
            "db": db,
            "app": app,
            "client": client,
            "set_user": set_user,
            "tenant": tenant,
            "service": service,
            "owner": owner,
            "vehicle": vehicle,
        }
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def test_service_cannot_read_unlinked_vehicle(vehicle_access_stack):
    ctx = vehicle_access_stack
    ctx["set_user"](ctx["service"])
    r = ctx["client"].get(f"/api/v1/vehicles/{ctx['vehicle'].id}")
    assert r.status_code == 403


def test_service_vehicle_payload_hides_owner_email_with_approved_link(vehicle_access_stack):
    ctx = vehicle_access_stack
    db = ctx["db"]
    db.add(
        VehicleServiceLink(
            tenant_id=ctx["tenant"].id,
            service_customer_id=ctx["service"].id,
            owner_customer_id=ctx["owner"].id,
            vehicle_id=ctx["vehicle"].id,
            status="approved",
        )
    )
    db.commit()
    ctx["set_user"](ctx["service"])
    r = ctx["client"].get(f"/api/v1/vehicles/{ctx['vehicle'].id}")
    assert r.status_code == 200, r.text
    assert r.json().get("user_email") == "hidden"
    assert r.json().get("tenant_id") is None
    assert owner_email_not_in_payload(r.json(), ctx["owner"].email)


def owner_email_not_in_payload(payload: dict, email: str) -> bool:
    raw = str(email or "").strip().lower()
    blob = str(payload).lower()
    return raw not in blob


@pytest.fixture()
def records_stack(tmp_path: Path):
    db_path = tmp_path / "svc_sot_rec.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="T-rec", license_key="lic-svc-sot-rec")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    service = Customer(
        tenant_id=tenant.id,
        email="service.rec@example.com",
        name="Servis REC",
        role="service",
    )
    owner = Customer(
        tenant_id=tenant.id,
        email="owner.rec@example.com",
        name="Majitel REC",
        role="user",
    )
    db.add_all([service, owner])
    db.commit()
    db.refresh(service)
    db.refresh(owner)

    vin = "2HGBH41JXMN109187"
    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="RecCar",
        vin=vin,
        plate="4AB1234",
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
    db.add(
        ServiceVehicleAccess(
            service_tenant_id=tenant.id,
            service_customer_id=service.id,
            customer_id=owner.id,
            vehicle_id=vehicle.id,
            status="approved",
        )
    )
    db.commit()

    app = FastAPI()
    app.include_router(service_records_router.router, prefix="/api/v1")

    def _db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[service_records_router.get_db] = _db

    def set_user(user: Customer):
        app.dependency_overrides[service_records_router.get_current_user] = lambda: user

    client = TestClient(app)
    try:
        yield {
            "db": db,
            "app": app,
            "client": client,
            "set_user": set_user,
            "service": service,
            "owner": owner,
            "vehicle": vehicle,
        }
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def test_legacy_service_vehicle_access_does_not_allow_record_without_vehicle_service_link(records_stack):
    """Zápis servisního záznamu musí projít přes VehicleServiceLink, ne jen ServiceVehicleAccess."""
    ctx = records_stack
    ctx["set_user"](ctx["service"])
    payload = ServiceRecordCreateV1(
        performed_at=datetime.utcnow(),
        mileage=1000,
        description="Test servisní záznam",
        price=100.0,
        category="OLEJ",
    )
    r = ctx["client"].post(
        f"/api/v1/vehicles/{ctx['vehicle'].id}/records",
        json=payload.model_dump(mode="json"),
    )
    assert r.status_code == 403


def test_service_can_create_record_only_with_active_link(records_stack):
    ctx = records_stack
    db = ctx["db"]
    db.add(
        VehicleServiceLink(
            tenant_id=int(ctx["vehicle"].tenant_id),
            service_customer_id=ctx["service"].id,
            owner_customer_id=ctx["owner"].id,
            vehicle_id=ctx["vehicle"].id,
            status="approved",
            scope_create_service_record=True,
        )
    )
    db.commit()

    ctx["set_user"](ctx["service"])
    payload = ServiceRecordCreateV1(
        performed_at=datetime.utcnow(),
        mileage=1000,
        description="Záznam přes schválený link",
        price=200.0,
        category="OLEJ",
    )
    r = ctx["client"].post(
        f"/api/v1/vehicles/{ctx['vehicle'].id}/records",
        json=payload.model_dump(mode="json"),
    )
    assert r.status_code == 200, r.text
    rid = r.json().get("id")
    row = db.query(ServiceRecord).filter(ServiceRecord.id == int(rid)).first()
    assert row is not None
    assert row.service_access_link_id is not None


def test_user_can_see_service_record_after_service_work(records_stack):
    ctx = records_stack
    db = ctx["db"]
    link = VehicleServiceLink(
        tenant_id=int(ctx["vehicle"].tenant_id),
        service_customer_id=ctx["service"].id,
        owner_customer_id=ctx["owner"].id,
        vehicle_id=ctx["vehicle"].id,
        status="approved",
    )
    db.add(link)
    db.flush()
    rec = ServiceRecord(
        tenant_id=int(ctx["vehicle"].tenant_id),
        vehicle_id=ctx["vehicle"].id,
        user_id=ctx["service"].id,
        performed_at=datetime.utcnow(),
        description="Práce servisu",
        category="OLEJ",
        service_id=ctx["service"].id,
        created_by_service_customer_id=ctx["service"].id,
        service_access_link_id=link.id,
    )
    db.add(rec)
    db.commit()

    ctx["set_user"](ctx["owner"])
    r = ctx["client"].get(f"/api/v1/vehicles/{ctx['vehicle'].id}/records")
    assert r.status_code == 200, r.text
    ids = [x.get("id") for x in r.json()]
    assert rec.id in ids


@pytest.fixture()
def admin_stack(tmp_path: Path):
    db_path = tmp_path / "svc_sot_admin.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="T-adm", license_key="lic-svc-sot-adm")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    admin = Customer(
        tenant_id=tenant.id,
        email="dev.admin@example.com",
        role="developer_admin",
        name="Admin",
    )
    target = Customer(
        tenant_id=tenant.id,
        email="target.user@example.com",
        role="user",
        name="Target",
    )
    db.add_all([admin, target])
    db.commit()
    db.refresh(admin)
    db.refresh(target)

    app = FastAPI()
    app.include_router(admin_api.router)

    def _db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[vehicle_hub_get_db] = _db
    app.dependency_overrides[require_developer_admin] = lambda: admin.email

    client = TestClient(app)
    try:
        yield {"client": client, "db": db, "admin": admin, "target": target}
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def test_admin_action_audit_exists(admin_stack):
    ctx = admin_stack
    before = ctx["db"].query(GlobalAuditLog).count()
    r = ctx["client"].patch(
        f"/admin-api/users/{ctx['target'].id}",
        json={"name": "Target Updated"},
    )
    assert r.status_code == 200, r.text
    after = ctx["db"].query(GlobalAuditLog).count()
    assert after > before
    last = (
        ctx["db"]
        .query(GlobalAuditLog)
        .filter(GlobalAuditLog.action == "admin_user_patch")
        .order_by(GlobalAuditLog.id.desc())
        .first()
    )
    assert last is not None
    meta_raw = last.metadata_json or "{}"
    meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
    assert int(meta.get("target_user_id", 0)) == int(ctx["target"].id)


def test_vehicle_delete_does_not_delete_records(tmp_path: Path):
    db_path = tmp_path / "del_veh.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    tenant = Tenant(name="T-del", license_key="lic-del")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    v = Vehicle(tenant_id=tenant.id, user_email="o@x.cz", nickname="N")
    db.add(v)
    db.commit()
    db.refresh(v)
    rec = ServiceRecord(
        tenant_id=tenant.id,
        vehicle_id=v.id,
        user_id=None,
        performed_at=datetime.utcnow(),
        description="Historie",
        category="X",
    )
    db.add(rec)
    db.commit()
    vid = v.id
    rid = rec.id
    db.delete(v)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.expire_all()
    row = db.query(ServiceRecord).filter(ServiceRecord.id == rid).first()
    assert row is not None
    assert int(row.vehicle_id) == int(vid)


@pytest.fixture()
def invoice_stack(tmp_path: Path):
    db_path = tmp_path / "svc_sot_inv.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="T-inv", license_key="lic-svc-sot-inv")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    service_a = Customer(
        tenant_id=tenant.id,
        email="svc.inv.a@example.com",
        name="Servis A",
        role="service",
    )
    service_b = Customer(
        tenant_id=tenant.id,
        email="svc.inv.b@example.com",
        name="Servis B",
        role="service",
    )
    owner = Customer(
        tenant_id=tenant.id,
        email="owner.inv@example.com",
        name="Majitel",
        role="user",
    )
    db.add_all([service_a, service_b, owner])
    db.commit()
    db.refresh(service_a)
    db.refresh(service_b)
    db.refresh(owner)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        brand="Skoda",
        model="Octavia",
        vin="3VW12345TEST12345",
        plate="1AB2345",
        stk_valid_until=date(2030, 1, 1),
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    for vid in (vehicle.id,):
        db.add(
            VehicleOwnership(
                tenant_id=tenant.id,
                vehicle_id=vid,
                customer_id=owner.id,
                ownership_type="owner",
                ownership_origin="manual",
                is_primary=True,
                is_active=True,
            )
        )
    for svc in (service_a, service_b):
        db.add(
            ServiceCustomerLink(
                service_tenant_id=tenant.id,
                service_customer_id=svc.id,
                customer_tenant_id=tenant.id,
                customer_id=owner.id,
                status="active",
            )
        )
    db.add(
        VehicleServiceLink(
            tenant_id=tenant.id,
            service_customer_id=service_a.id,
            owner_customer_id=owner.id,
            vehicle_id=vehicle.id,
            status="approved",
        )
    )
    db.add(ServiceInvoiceCounter(tenant_id=tenant.id, next_seq=1))
    db.commit()

    app = FastAPI()
    app.include_router(service_invoices_router.router)

    def _db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[service_invoices_router.get_db] = _db

    def set_user(user: Customer):
        app.dependency_overrides[service_invoices_router.get_current_user] = lambda: user

    client = TestClient(app)
    try:
        yield {
            "client": client,
            "db": db,
            "set_user": set_user,
            "service_a": service_a,
            "service_b": service_b,
            "owner": owner,
            "vehicle": vehicle,
        }
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


LINE = {
    "description": "Olej",
    "quantity": 1,
    "unit": "ks",
    "unit_price": 1000,
    "tax_rate": 21,
}


def test_invoice_vehicle_link_rule_requires_vehicle_id(invoice_stack):
    ctx = invoice_stack
    ctx["set_user"](ctx["service_a"])
    r = ctx["client"].post(
        "/api/service/invoices",
        json={
            "customer_id": ctx["owner"].id,
            "lines": [LINE],
            "non_vehicle_invoice": False,
        },
    )
    assert r.status_code == 422


def test_invoice_vehicle_link_rule_denies_foreign_vehicle(invoice_stack):
    ctx = invoice_stack
    ctx["set_user"](ctx["service_b"])
    r = ctx["client"].post(
        "/api/service/invoices",
        json={
            "customer_id": ctx["owner"].id,
            "vehicle_id": ctx["vehicle"].id,
            "lines": [LINE],
        },
    )
    assert r.status_code == 403
