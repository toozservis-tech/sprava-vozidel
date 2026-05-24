"""GET /admin-api/service-invoices (read-only)."""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.auth import get_current_user_email
from src.modules.vehicle_hub.database import Base, get_db as vehicle_hub_get_db
from src.modules.vehicle_hub.models import Customer, ServiceInvoice, Tenant, Vehicle
from src.server import admin_api


@pytest.fixture()
def admin_inv_client(tmp_path):
    db_path = tmp_path / "admin_inv.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="T", license_key="lic-admin-inv", workspace_slug="adm", workspace_route_kind="user")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    admin = Customer(
        tenant_id=tenant.id,
        email="dev.admin@example.com",
        password_hash="x",
        name="Admin",
        role="developer_admin",
    )
    svc = Customer(
        tenant_id=tenant.id,
        email="svc.inv@example.com",
        password_hash="x",
        name="Servis",
        role="service",
    )
    cust = Customer(
        tenant_id=tenant.id,
        email="cust.inv@example.com",
        password_hash="x",
        name="Cust",
        role="user",
    )
    db.add_all([admin, svc, cust])
    db.commit()
    for c in (admin, svc, cust):
        db.refresh(c)

    v = Vehicle(
        tenant_id=tenant.id,
        user_email=cust.email,
        nickname="Car",
        vin="TMBADM12345678901",
    )
    db.add(v)
    db.commit()
    db.refresh(v)

    inv = ServiceInvoice(
        tenant_id=tenant.id,
        service_id=svc.id,
        customer_id=cust.id,
        vehicle_id=v.id,
        status="issued",
        subtotal=100.0,
        tax_total=21.0,
        total=121.0,
        invoice_number="FV-1",
        issued_at=datetime.utcnow(),
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)

    app = FastAPI()
    app.include_router(admin_api.router)

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[vehicle_hub_get_db] = override_db
    app.dependency_overrides[get_current_user_email] = lambda: admin.email

    client = TestClient(app)
    try:
        yield client, db, inv, v, svc
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def test_admin_service_invoices_ok_and_filter(admin_inv_client):
    client, db, inv, v, svc = admin_inv_client
    r = client.get("/admin-api/service-invoices")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] >= 1
    assert any(x.get("invoice_id") == int(inv.id) for x in data["items"])

    r2 = client.get(f"/admin-api/service-invoices?vehicle_id={v.id}")
    assert r2.status_code == 200
    assert all(x.get("vehicle_id") in (None, v.id) for x in r2.json()["items"])

    r3 = client.get("/admin-api/service-invoices?status=issued")
    assert r3.status_code == 200
    assert all(x.get("status") == "issued" for x in r3.json()["items"])


def test_non_admin_forbidden(tmp_path):
    db_path = tmp_path / "noadmin.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    t = Tenant(name="T", license_key="lic-na", workspace_slug="na", workspace_route_kind="user")
    db.add(t)
    db.commit()
    db.refresh(t)
    user = Customer(
        tenant_id=t.id,
        email="user@ex.com",
        password_hash="x",
        name="U",
        role="user",
    )
    db.add(user)
    db.commit()

    app = FastAPI()
    app.include_router(admin_api.router)

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[vehicle_hub_get_db] = override_db
    app.dependency_overrides[get_current_user_email] = lambda: user.email

    client = TestClient(app)
    r = client.get("/admin-api/service-invoices")
    assert r.status_code == 403
    db.close()
    engine.dispose()
