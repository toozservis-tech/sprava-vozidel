from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Reminder, ServiceRecord, Tenant, Vehicle, VehicleOwnership
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import analytics as analytics_router


@pytest.fixture()
def dashboard_client(tmp_path: Path):
    db_path = tmp_path / "dashboard_summary.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="Dashboard Tenant", license_key="dashboard-tenant-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(
        tenant_id=tenant.id,
        email="owner@example.com",
        password_hash="hash",
        role="user",
        name="Dashboard User",
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Dashboard Auto",
        brand="Skoda",
        model="Octavia",
        vin="TMBTESTDASHBOARD01",
        plate="1AB2345",
        stk_valid_until=date.today() + timedelta(days=25),
        current_mileage_km=123456,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    ensure_vehicle_owner_assignment(db, vehicle=vehicle, owner=owner, assigned_by_customer_id=owner.id)

    db.add(
        ServiceRecord(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            user_id=owner.id,
            performed_at=datetime.utcnow().replace(microsecond=0),
            mileage=123456,
            description="Test dashboard record",
            price=1990.0,
            category="OLEJ",
        )
    )
    db.add(
        Reminder(
            tenant_id=tenant.id,
            customer_id=owner.id,
            vehicle_id=vehicle.id,
            type="SERVIS",
            text="Test dashboard reminder",
            is_manual=True,
            is_completed=False,
        )
    )
    db.commit()

    app = FastAPI()
    app.include_router(analytics_router.router, prefix="/api/v1")

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[analytics_router.get_db] = override_get_db
    app.dependency_overrides[analytics_router.get_current_user] = lambda: owner

    client = TestClient(app)
    try:
        yield client, vehicle
    finally:
        db.close()
        engine.dispose()


def test_dashboard_summary_endpoint_aggregates_user_scope(dashboard_client) -> None:
    client, vehicle = dashboard_client

    response = client.get("/api/v1/analytics/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "user"
    assert int(payload["vehicles_total"]) == 1
    assert int(payload["active_reminders"]) == 1
    assert int(payload["stk_soon"]) == 1
    assert payload["recent_activity"]
    assert int(payload["recent_activity"][0]["vehicle_id"]) == vehicle.id
    assert any(item["kind"] in {"missing_photo", "missing_primary_photo"} for item in payload["attention"])
    assert any(item.get("action_label") for item in payload["attention"])
