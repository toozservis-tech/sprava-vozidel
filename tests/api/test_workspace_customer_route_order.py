"""Regrese: statická cesta /customers/search nesmí být přepsána dynamickou /customers/{id}/detail."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant
from src.modules.vehicle_hub.routers_v1 import service_workspace as sw
from src.modules.vehicle_hub.routers_v1.auth import get_current_user


@pytest.fixture()
def client_workspace(tmp_path: Path):
    db_path = tmp_path / "route_order.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    tenant = Tenant(name="T", license_key="k")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    svc = Customer(tenant_id=tenant.id, email="svc@x.cz", role="service", name="S")
    db.add(svc)
    db.commit()
    db.refresh(svc)

    app = FastAPI()
    app.include_router(sw.router, prefix="/api/v1")

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[sw.get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: svc
    tc = TestClient(app)
    try:
        yield tc
    finally:
        db.close()
        engine.dispose()


def test_customers_search_path_not_shadowed_by_detail_route(client_workspace: TestClient) -> None:
    """Musí vrátit validační chybu na chybějící query, ne 404 'Klient'."""
    r = client_workspace.get("/api/v1/services/workspace/customers/search")
    assert r.status_code == 422
