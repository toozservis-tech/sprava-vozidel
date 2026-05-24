"""Rychlé inline testy (TestClient + SQLite) — centrální zákazníci servisu, bez běžícího API serveru."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.modules.vehicle_hub import service_workspace_customer_centre as cc


@pytest.fixture()
def svc_client(tmp_path: Path):
    db_path = tmp_path / "svc_cc.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    tenant = Tenant(name="T", license_key="lic-svc-cc-test")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    svc = Customer(
        tenant_id=tenant.id,
        email="svc.centre@example.com",
        password_hash="x",
        name="Servis XY",
        role="service",
    )
    usr = Customer(
        tenant_id=tenant.id,
        email="cust.centre@example.com",
        password_hash="x",
        name="Jan Novák",
        role="user",
        phone_e164="+420700123456",
        phone_normalized="420700123456",
    )
    db.add_all([svc, usr])
    db.commit()
    db.refresh(svc)
    db.refresh(usr)

    app = FastAPI()
    app.include_router(cc.router, prefix="/api/v1/services/workspace")

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[cc.get_db] = override_db

    yield TestClient(app), db, svc, usr
    db.close()
    engine.dispose()


def test_post_search_masked_no_user_id_in_preview(svc_client):
    client, _, svc, usr = svc_client
    app = client.app

    def override_user():
        return svc

    app.dependency_overrides[get_current_user] = override_user

    resp = client.post(
        "/api/v1/services/workspace/customers/search",
        json={"email": usr.email},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("found") is True
    prev = data.get("customer_preview") or {}
    assert prev.get("lookup_id")
    assert "customer_user_id" not in prev and "user_id" not in prev


def test_non_service_gets_403_on_search():
    db_path = Path("/tmp") / "svc_cc_user.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    tenant = Tenant(name="T", license_key="lic-svc-cc-user-test")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    usr = Customer(
        tenant_id=tenant.id,
        email="regular@example.com",
        password_hash="x",
        name="Regular",
        role="user",
    )
    db.add(usr)
    db.commit()

    app = FastAPI()
    app.include_router(cc.router, prefix="/api/v1/services/workspace")

    def override_db():
        yield db

    app.dependency_overrides[cc.get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: usr

    client = TestClient(app)
    r = client.post("/api/v1/services/workspace/customers/search", json={"email": "a@b.cz"})
    assert r.status_code == 403

    db.close()
    engine.dispose()
