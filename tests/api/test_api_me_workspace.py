from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.auth import get_current_customer_optional
from src.core.branding import APP_DISPLAY_NAME
from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import Customer, Tenant
from src.modules.vehicle_hub.workspace_routing import ensure_tenant_workspace_slug
from src.server.routers.session_me import router as session_me_router


@pytest.fixture()
def workspace_api_client(tmp_path: Path):
    db_path = tmp_path / "api_me_workspace.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="Workspace Tenant", license_key="workspace-tenant-key-unique")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(
        tenant_id=tenant.id,
        email="workspace_owner@example.com",
        password_hash="hash",
        role="user",
        name="Tomas Zachurcok",
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    app = FastAPI()
    app.include_router(session_me_router)

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


@pytest.fixture()
def workspace_api_service(tmp_path: Path):
    db_path = tmp_path / "api_me_service.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="Servis Alpha", license_key="workspace-service-tenant-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    svc = Customer(
        tenant_id=tenant.id,
        email="service_owner@example.com",
        password_hash="hash",
        role="service",
        name="TooZ Servis",
    )
    db.add(svc)
    db.commit()
    db.refresh(svc)

    app = FastAPI()
    app.include_router(session_me_router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client, app, db, svc, tenant
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def test_api_me_anonymous(workspace_api_client):
    client, app, _db, _owner, _tenant = workspace_api_client
    app.dependency_overrides[get_current_customer_optional] = lambda: None
    r = client.get("/api/me")
    assert r.status_code == 200, r.text
    assert r.json().get("authenticated") is False
    assert r.json().get("app_name") == APP_DISPLAY_NAME


def test_api_me_authenticated_user_shape(workspace_api_client):
    client, app, db, owner, tenant = workspace_api_client
    app.dependency_overrides[get_current_customer_optional] = lambda: owner

    r = client.get("/api/me")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("authenticated") is True
    assert data.get("app_name") == APP_DISPLAY_NAME
    assert data.get("account_type") == "user"
    assert data.get("account_id") == owner.id
    assert data.get("email") == owner.email
    assert "permissions" in data
    assert isinstance(data.get("permissions"), dict)
    slug = data.get("account_slug")
    assert slug
    assert data.get("default_app_path") == f"/app/u/{slug}/dashboard"
    assert data.get("workspace_route_kind") == "user"
    assert re.match(r"^/app/u/[a-z0-9-]+/dashboard$", data.get("default_app_path") or "")

    db.refresh(tenant)
    assert tenant.workspace_slug == slug

    ok = client.get("/api/me", params={"assert_route": "u", "assert_slug": slug})
    assert ok.status_code == 200, ok.text

    bad = client.get("/api/me", params={"assert_route": "u", "assert_slug": "foreign-workspace-slug"})
    assert bad.status_code == 403, bad.text
    detail = bad.json().get("detail")
    assert isinstance(detail, dict)
    assert "default_app_path" in detail


def test_api_me_authenticated_service_shape(workspace_api_service):
    client, app, db, svc, tenant = workspace_api_service
    app.dependency_overrides[get_current_customer_optional] = lambda: svc

    r = client.get("/api/me")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("authenticated") is True
    assert data.get("app_name") == APP_DISPLAY_NAME
    assert data.get("account_type") == "service"
    assert data.get("workspace_route_kind") == "service"
    slug = data.get("account_slug")
    assert slug
    assert data.get("default_app_path") == f"/app/s/{slug}/dashboard"
    assert re.match(r"^/app/s/[a-z0-9-]+/dashboard$", data.get("default_app_path") or "")

    ok = client.get("/api/me", params={"assert_route": "s", "assert_slug": slug})
    assert ok.status_code == 200, ok.text


def test_api_me_assert_route_mismatch_user(workspace_api_client):
    client, app, _db, owner, _tenant = workspace_api_client
    app.dependency_overrides[get_current_customer_optional] = lambda: owner
    r = client.get("/api/me", params={"assert_route": "s", "assert_slug": "any"})
    assert r.status_code == 403, r.text
    d = r.json().get("detail")
    assert isinstance(d, dict) and d.get("default_app_path")


def test_api_me_assert_route_mismatch_service(workspace_api_service):
    client, app, _db, svc, _tenant = workspace_api_service
    app.dependency_overrides[get_current_customer_optional] = lambda: svc
    r = client.get("/api/me", params={"assert_route": "u", "assert_slug": "x"})
    assert r.status_code == 403, r.text


def test_api_me_partial_assert_params_ignored(workspace_api_client):
    """Jen assert_route nebo jen assert_slug bez páru — assert se neaplikuje."""
    client, app, _db, owner, tenant = workspace_api_client
    app.dependency_overrides[get_current_customer_optional] = lambda: owner
    r1 = client.get("/api/me", params={"assert_route": "u"})
    assert r1.status_code == 200
    slug = r1.json().get("account_slug")
    r2 = client.get("/api/me", params={"assert_slug": slug})
    assert r2.status_code == 200


def test_workspace_slug_collision_same_kind(tmp_path: Path):
    db_path = tmp_path / "slug_collision.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        t1 = Tenant(name="SameCo", license_key="col-a-unique-key-1")
        t2 = Tenant(name="SameCo", license_key="col-a-unique-key-2")
        db.add_all([t1, t2])
        db.commit()
        db.refresh(t1)
        db.refresh(t2)
        ensure_tenant_workspace_slug(db, t1, seed_label="SameCo", route_kind="user")
        ensure_tenant_workspace_slug(db, t2, seed_label="SameCo", route_kind="user")
        db.commit()
        db.refresh(t1)
        db.refresh(t2)
        assert t1.workspace_slug == "sameco"
        assert t2.workspace_slug == "sameco-2"
        assert t1.workspace_route_kind == "user"
        assert t2.workspace_route_kind == "user"
    finally:
        db.close()
        engine.dispose()
