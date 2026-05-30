"""User-facing service access requests API and dashboard indicator."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceAccessRequest,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.routers_v1 import service_workspace
from src.modules.vehicle_hub.routers_v1 import services as services_router
from src.modules.vehicle_hub.routers_v1.analytics import get_dashboard_summary
from src.server.routers import user_service_requests as user_requests_router


def _owner_user(owner: Customer) -> SimpleNamespace:
    return SimpleNamespace(
        id=owner.id,
        email=owner.email,
        role="user",
        name=owner.name,
        tenant_id=owner.tenant_id,
    )


@pytest.fixture()
def user_requests_ctx(tmp_path):
    db_path = tmp_path / "user_service_requests.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    tenant = Tenant(name="User Requests", license_key="user-requests-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(tenant_id=tenant.id, email="owner-requests@example.com", password_hash="x", role="user", name="Owner")
    service = Customer(tenant_id=tenant.id, email="service-requests@example.com", password_hash="x", role="service", name="Service")
    db.add_all([owner, service])
    db.commit()
    db.refresh(owner)
    db.refresh(service)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        brand="Skoda",
        model="Fabia",
        vin="TMBREQ12345678901",
        plate="9RQ1234",
        nickname="Test Fabia",
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

    service_workspace.create_service_access_request(
        service_workspace.ServiceAccessRequestCreateV1(
            vehicle_id=int(vehicle.id),
            lookup_query=vehicle.plate,
            note="Prosím o schválení propojení",
        ),
        current_user=service,
        db=db,
    )
    db.commit()
    request_row = db.query(ServiceAccessRequest).filter(ServiceAccessRequest.vehicle_id == int(vehicle.id)).one()

    yield db, owner, service, vehicle, request_row
    db.close()
    engine.dispose()


def test_user_service_requests_list_pending(user_requests_ctx):
    db, owner, service, vehicle, request_row = user_requests_ctx
    payload = user_requests_router.list_user_service_requests(status="pending", email=owner.email, db=db)
    assert payload["meta"]["pending"] == 1
    assert len(payload["requests"]) == 1
    item = payload["requests"][0]
    assert item["request_id"] == int(request_row.id)
    assert item["vehicle_id"] == int(vehicle.id)
    assert item["service_name"] == service.name
    assert item["reason"] == "Prosím o schválení propojení"
    assert item["status"] == "pending"
    assert item["vehicle_plate_masked"]
    assert item["vehicle_vin_masked"]
    assert "invoice" not in str(item).lower()
    assert "billing" not in str(item).lower()


def test_user_approve_service_request(user_requests_ctx):
    db, owner, _service, vehicle, request_row = user_requests_ctx
    services_router.resolve_service_access_request(
        int(request_row.id),
        services_router.ServiceAccessRequestDecisionV1(decision="approved"),
        current_user=owner,
        db=db,
    )
    db.commit()
    db.refresh(request_row)
    assert request_row.status == "approved"
    link = (
        db.query(VehicleServiceLink)
        .filter(
            VehicleServiceLink.vehicle_id == int(vehicle.id),
            VehicleServiceLink.status == "approved",
        )
        .one()
    )
    assert link is not None


def test_user_reject_service_request(user_requests_ctx):
    db, owner, _service, vehicle, request_row = user_requests_ctx
    services_router.resolve_service_access_request(
        int(request_row.id),
        services_router.ServiceAccessRequestDecisionV1(decision="rejected"),
        current_user=owner,
        db=db,
    )
    db.commit()
    db.refresh(request_row)
    assert request_row.status == "rejected"
    assert (
        db.query(VehicleServiceLink)
        .filter(VehicleServiceLink.vehicle_id == int(vehicle.id))
        .count()
        == 0
    )


def test_user_dashboard_has_pending_service_request_indicator(user_requests_ctx):
    db, owner, _service, _vehicle, _request_row = user_requests_ctx
    summary = get_dashboard_summary(
        recent_limit=8,
        attention_limit=14,
        current_user=_owner_user(owner),
        db=db,
    )
    assert summary.pending_service_requests == 1


def test_approved_request_creates_vehicle_service_link(user_requests_ctx):
    db, owner, _service, vehicle, request_row = user_requests_ctx
    services_router.resolve_service_access_request(
        int(request_row.id),
        services_router.ServiceAccessRequestDecisionV1(decision="approved"),
        current_user=owner,
        db=db,
    )
    db.commit()
    link = db.query(VehicleServiceLink).filter(VehicleServiceLink.vehicle_id == int(vehicle.id)).one()
    assert link.status == "approved"


def test_rejected_request_does_not_create_owner_access(user_requests_ctx):
    db, owner, _service, vehicle, request_row = user_requests_ctx
    services_router.resolve_service_access_request(
        int(request_row.id),
        services_router.ServiceAccessRequestDecisionV1(decision="rejected"),
        current_user=owner,
        db=db,
    )
    db.commit()
    assert db.query(VehicleServiceLink).filter(VehicleServiceLink.vehicle_id == int(vehicle.id)).count() == 0


def test_service_without_approval_does_not_see_owner_pii(user_requests_ctx):
    db, owner, service, vehicle, request_row = user_requests_ctx
    services_router.resolve_service_access_request(
        int(request_row.id),
        services_router.ServiceAccessRequestDecisionV1(decision="rejected"),
        current_user=owner,
        db=db,
    )
    db.commit()
    lookup = service_workspace.lookup_vehicle_for_service(
        payload=service_workspace.ServiceVehicleLookupRequestV1(query=vehicle.plate),
        current_user=service,
        db=db,
    )
    assert lookup.get("owner_customer_id") is None
    assert lookup.get("owner_data") is None
    preview = lookup.get("vehicle_preview") or {}
    candidates = lookup.get("candidates") or []
    if preview:
        assert preview.get("plate_masked") or preview.get("vin_masked")
    elif candidates:
        first = candidates[0] or {}
        assert first.get("plate_masked") or first.get("vin_masked")
    else:
        assert lookup.get("found") is not False
