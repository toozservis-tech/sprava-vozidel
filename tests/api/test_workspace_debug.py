from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.auth import get_current_customer_optional
from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import Customer, Tenant
from src.server.routers import workspace_debug


@pytest.fixture()
def debug_client(tmp_path: Path):
    db_path = tmp_path / "workspace_debug.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="Dbg", license_key="lic-dbg-1", workspace_slug="dbgco", workspace_route_kind="user")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(
        tenant_id=tenant.id,
        email="dbg@example.com",
        password_hash="x",
        role="user",
        name="Dbg",
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    app = FastAPI()
    app.include_router(workspace_debug.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client, app, db, owner, tenant
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def test_debug_workspace_requires_auth(debug_client):
    client, app, _db, _owner, _tenant = debug_client
    with mock.patch.object(workspace_debug, "ENVIRONMENT", "development"):
        r = client.get("/api/_debug/workspace")
    assert r.status_code == 401


def test_debug_workspace_shape_when_authenticated(debug_client):
    client, app, _db, owner, tenant = debug_client
    app.dependency_overrides[get_current_customer_optional] = lambda: owner
    with mock.patch.object(workspace_debug, "ENVIRONMENT", "development"):
        r = client.get("/api/_debug/workspace")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tenant_id"] == tenant.id
    assert data["account_id"] == owner.id
    assert data["slug"]
    assert data["route_kind"] in {"user", "service"}
    assert data["default_app_path"].startswith("/app/")
    assert "/dashboard" in data["default_app_path"]


def test_debug_workspace_hidden_in_production(debug_client):
    client, app, _db, owner, _tenant = debug_client
    app.dependency_overrides[get_current_customer_optional] = lambda: owner
    with mock.patch.object(workspace_debug, "ENVIRONMENT", "production"):
        with mock.patch.dict("os.environ", {"ENABLE_WORKSPACE_DEBUG_ENDPOINT": ""}, clear=False):
            r = client.get("/api/_debug/workspace")
    assert r.status_code == 404
