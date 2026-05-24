from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, ServiceRecord, Tenant, Vehicle, VehicleOwnership
from src.modules.vehicle_hub.routers_v1 import analytics as analytics_router
from src.modules.vehicle_hub.routers_v1 import autopilot as autopilot_router
from src.modules.vehicle_hub.routers_v1 import bot as bot_router
from src.modules.vehicle_hub.routers_v1 import customer_commands as customer_commands_router


@pytest.fixture()
def db_context(tmp_path: Path):
    db_path = tmp_path / "ownership_compat_edges.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        tenant = Tenant(name="Edge Tenant", license_key="edge-tenant-key")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        user = Customer(
            tenant_id=tenant.id,
            email="edge-user@example.com",
            password_hash="hash-user",
            role="user",
            name="Edge User",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        vehicle = Vehicle(
            tenant_id=tenant.id,
            user_email="legacy-edge@example.com",
            nickname="Edge Car",
            brand="Skoda",
            model="Superb",
            vin="TMBEDGE1234567890"[:17],
            plate="3EF4567",
        )
        db.add(vehicle)
        db.flush()
        db.add(
            VehicleOwnership(
                tenant_id=tenant.id,
                vehicle_id=vehicle.id,
                customer_id=user.id,
                ownership_type="owner",
                is_primary=True,
                is_active=True,
                assigned_by_customer_id=user.id,
            )
        )
        db.flush()
        db.add(
            ServiceRecord(
                tenant_id=tenant.id,
                vehicle_id=vehicle.id,
                user_id=user.id,
                performed_at=datetime.utcnow(),
                description="Ownership edge record",
                price=1200.0,
            )
        )
        db.commit()
        db.refresh(vehicle)

        yield {"db": db, "tenant": tenant, "user": user, "vehicle": vehicle}
    finally:
        db.close()
        engine.dispose()


def test_analytics_summary_uses_ownership_source_of_truth(db_context):
    payload = analytics_router.get_analytics_summary(
        vehicle_id=None,
        date_from=None,
        date_to=None,
        current_user=db_context["user"],
        db=db_context["db"],
    )
    assert payload.total_records == 1
    assert payload.total_cost_czk == 1200.0


def test_customer_commands_vehicle_lookup_uses_ownership_source_of_truth(db_context):
    matches = customer_commands_router.find_vehicles_by_text(
        "eviduj výměnu oleje na Edge Car",
        db_context["user"].email,
        db_context["db"],
    )
    assert len(matches) == 1
    assert matches[0]["id"] == db_context["vehicle"].id


def test_bot_vehicle_extraction_uses_ownership_source_of_truth(db_context):
    vehicle = bot_router.extract_vehicle_info(
        "prosím vytvoř poznámku pro Edge Car",
        db_context["db"],
        db_context["user"].email,
    )
    assert vehicle is not None
    assert vehicle.id == db_context["vehicle"].id


def test_autopilot_vehicle_lookup_and_quick_record_use_ownership_source_of_truth(db_context):
    vehicles_payload = autopilot_router.get_user_vehicles(
        user_id=db_context["user"].id,
        _=True,
        db=db_context["db"],
    )
    assert len(vehicles_payload["vehicles"]) == 1
    assert vehicles_payload["vehicles"][0]["id"] == db_context["vehicle"].id

    created = autopilot_router.create_quick_record(
        vehicle_id=db_context["vehicle"].id,
        description="Quick autopilot service",
        mileage=123456,
        price=890.0,
        category="GENERAL",
        _=True,
        db=db_context["db"],
    )
    assert created["status"] == "ok"
