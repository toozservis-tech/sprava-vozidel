from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.auth import get_current_customer_optional
from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import Customer, Tenant
from src.modules.vehicle_hub.workspace_sanity import (
    collect_workspace_sanity_report,
    repair_empty_workspace_slugs,
)
from src.server.routers.session_me import router as session_me_router


@pytest.fixture()
def sanity_client(tmp_path: Path):
    db_path = tmp_path / "workspace_sanity.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="T", license_key="lic-sanity-1", workspace_slug=None, workspace_route_kind=None)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(
        tenant_id=tenant.id,
        email="owner_sanity@example.com",
        password_hash="x",
        role="user",
        name="Owner",
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


def test_workspace_sanity_report_clean_after_slug_repair(sanity_client):
    _client, app, db, owner, tenant = sanity_client
    report = collect_workspace_sanity_report(db)
    assert report.has_empty_slugs is True
    assert report.has_duplicate_slugs is False

    repaired = repair_empty_workspace_slugs(db)
    assert repaired >= 1

    report2 = collect_workspace_sanity_report(db)
    assert report2.has_empty_slugs is False


def test_api_me_normalizes_invalid_workspace_route_kind(sanity_client):
    client, app, db, owner, tenant = sanity_client
    tenant.workspace_route_kind = "legacy"
    tenant.workspace_slug = "acme"
    db.add(tenant)
    db.commit()

    app.dependency_overrides[get_current_customer_optional] = lambda: owner
    r = client.get("/api/me")
    assert r.status_code == 200, r.text
    db.refresh(tenant)
    assert tenant.workspace_route_kind == "user"


def test_default_app_path_matches_user_workspace(sanity_client):
    client, app, db, owner, tenant = sanity_client
    tenant.workspace_slug = "myfleet"
    tenant.workspace_route_kind = "user"
    db.add(tenant)
    db.commit()

    app.dependency_overrides[get_current_customer_optional] = lambda: owner
    data = client.get("/api/me").json()
    assert data["default_app_path"] == "/app/u/myfleet/dashboard"
    assert data["workspace_route_kind"] == "user"
    assert data["account_slug"] == "myfleet"
