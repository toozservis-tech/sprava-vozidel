"""Intake flow: owner requests, one-time work, draft work orders, owner safe."""
from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.central_vehicle_identity import build_owner_safe_service_history
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    GlobalAuditLog,
    ServiceAccessRequest,
    ServiceWorkAccess,
    ServiceWorkOrder,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.routers_v1 import service_dashboard as dashboard_router
from src.modules.vehicle_hub.routers_v1 import service_workspace
from src.modules.vehicle_hub.routers_v1 import service_workspace_cases as cases_router
from src.modules.vehicle_hub.routers_v1 import services as services_router
from src.modules.vehicle_hub.routers_v1.work_order_items_api import accept_work_order


def _service_user(service: Customer) -> SimpleNamespace:
    return SimpleNamespace(
        id=service.id,
        email=service.email,
        role="service",
        name=service.name,
        tenant_id=service.tenant_id,
    )


def _owner_user(owner: Customer) -> SimpleNamespace:
    return SimpleNamespace(
        id=owner.id,
        email=owner.email,
        role="user",
        name=owner.name,
        tenant_id=owner.tenant_id,
    )


@pytest.fixture()
def flow_ctx(tmp_path):
    db_path = tmp_path / "intake_flow.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    tenant = Tenant(name="Intake Flow", license_key="intake-flow-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(tenant_id=tenant.id, email="owner-flow@example.com", password_hash="x", role="user", name="Owner")
    service = Customer(tenant_id=tenant.id, email="service-flow@example.com", password_hash="x", role="service", name="Service")
    foreign = Customer(tenant_id=tenant.id, email="foreign-flow@example.com", password_hash="x", role="service", name="Foreign")
    db.add_all([owner, service, foreign])
    db.commit()
    db.refresh(owner)
    db.refresh(service)
    db.refresh(foreign)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        brand="Skoda",
        model="Octavia",
        vin="TMBFLOW12345678901",
        plate="1FL1234",
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
    yield engine, db, owner, service, foreign, vehicle
    db.close()
    engine.dispose()


def test_service_request_owner_link_creates_pending_request(flow_ctx):
    _engine, db, owner, service, _foreign, vehicle = flow_ctx
    body = service_workspace.create_service_access_request(
        service_workspace.ServiceAccessRequestCreateV1(
            vehicle_id=int(vehicle.id),
            lookup_query=vehicle.plate,
            note="Propojení pro servis",
        ),
        current_user=service,
        db=db,
    )
    assert body["created"] is True
    row = db.query(ServiceAccessRequest).filter(ServiceAccessRequest.vehicle_id == int(vehicle.id)).one()
    assert row.status == "pending"


def test_owner_sees_service_access_request(flow_ctx):
    _engine, db, owner, service, _foreign, vehicle = flow_ctx
    service_workspace.create_service_access_request(
        service_workspace.ServiceAccessRequestCreateV1(
            vehicle_id=int(vehicle.id),
            lookup_query=vehicle.plate,
        ),
        current_user=service,
        db=db,
    )
    listed = services_router.get_service_access_requests(current_user=owner, db=db)
    assert len(listed["requests"]) == 1
    assert listed["requests"][0]["service_name"]


def test_owner_can_approve_service_request(flow_ctx):
    _engine, db, owner, service, _foreign, vehicle = flow_ctx
    created = service_workspace.create_service_access_request(
        service_workspace.ServiceAccessRequestCreateV1(
            vehicle_id=int(vehicle.id),
            lookup_query=vehicle.plate,
        ),
        current_user=service,
        db=db,
    )
    services_router.resolve_service_access_request(
        int(created["request_id"]),
        services_router.ServiceAccessRequestDecisionV1(decision="approved"),
        current_user=owner,
        db=db,
    )
    link = db.query(VehicleServiceLink).filter(
        VehicleServiceLink.service_customer_id == service.id,
        VehicleServiceLink.vehicle_id == vehicle.id,
    ).one()
    assert link.status == "approved"
    audit = db.query(GlobalAuditLog).filter(GlobalAuditLog.action == "owner_approved_service_link").all()
    assert audit


def test_owner_can_reject_service_request(flow_ctx):
    _engine, db, owner, service, _foreign, vehicle = flow_ctx
    created = service_workspace.create_service_access_request(
        service_workspace.ServiceAccessRequestCreateV1(
            vehicle_id=int(vehicle.id),
            lookup_query=vehicle.plate,
        ),
        current_user=service,
        db=db,
    )
    services_router.resolve_service_access_request(
        int(created["request_id"]),
        services_router.ServiceAccessRequestDecisionV1(decision="rejected"),
        current_user=owner,
        db=db,
    )
    row = db.query(ServiceAccessRequest).filter(ServiceAccessRequest.id == int(created["request_id"])).one()
    assert row.status == "rejected"
    audit = db.query(GlobalAuditLog).filter(GlobalAuditLog.action == "owner_rejected_service_link").all()
    assert audit


def test_service_can_create_one_time_work_without_owner_approval(flow_ctx):
    _engine, db, _owner, service, _foreign, vehicle = flow_ctx
    service_workspace.create_service_vehicle_work_access(
        int(vehicle.id),
        service_workspace.ServiceWorkAccessRequestV1(reason="Jednorázový zásah", source="intake"),
        current_user=service,
        db=db,
    )
    case = cases_router.create_service_case(
        cases_router.ServiceCaseCreateV1(vehicle_id=int(vehicle.id), customer_request="Diagnostika"),
        current_user=service,
        db=db,
    )
    assert case["id"] > 0
    assert db.query(VehicleServiceLink).count() == 0


def test_rejected_service_can_keep_own_work_order(flow_ctx):
    _engine, db, owner, service, _foreign, vehicle = flow_ctx
    created = service_workspace.create_service_access_request(
        service_workspace.ServiceAccessRequestCreateV1(
            vehicle_id=int(vehicle.id),
            lookup_query=vehicle.plate,
        ),
        current_user=service,
        db=db,
    )
    services_router.resolve_service_access_request(
        int(created["request_id"]),
        services_router.ServiceAccessRequestDecisionV1(decision="rejected"),
        current_user=owner,
        db=db,
    )
    service_workspace.create_service_vehicle_work_access(
        int(vehicle.id),
        service_workspace.ServiceWorkAccessRequestV1(reason="Vlastní zásah", source="intake"),
        current_user=service,
        db=db,
    )
    wo = dashboard_router.create_service_work_order(
        payload=dashboard_router.ServiceWorkOrderCreateRequest(
            vehicle_id=int(vehicle.id),
            title="Zásah po zamítnutí",
            status="intake_pending",
            source_type="intake",
        ),
        current_user=_service_user(service),
        db=db,
    )
    assert wo["id"] > 0
    assert db.query(ServiceWorkAccess).filter(ServiceWorkAccess.vehicle_id == int(vehicle.id)).count() == 1


def test_approved_service_gets_owner_approved_scope(flow_ctx):
    _engine, db, owner, service, _foreign, vehicle = flow_ctx
    created = service_workspace.create_service_access_request(
        service_workspace.ServiceAccessRequestCreateV1(
            vehicle_id=int(vehicle.id),
            lookup_query=vehicle.plate,
        ),
        current_user=service,
        db=db,
    )
    services_router.resolve_service_access_request(
        int(created["request_id"]),
        services_router.ServiceAccessRequestDecisionV1(decision="approved"),
        current_user=owner,
        db=db,
    )
    lookup = service_workspace.central_service_vehicle_lookup(
        service_workspace.CentralVehicleLookupRequestV1(vin=vehicle.vin, source="service_intake", context="intake_route"),
        request=None,
        current_user=service,
        db=db,
    )
    assert lookup["access"]["status"] == "approved"
    assert lookup.get("owner_customer_id") == int(owner.id)


def test_one_time_work_does_not_create_vehicle_ownership(flow_ctx):
    _engine, db, _owner, service, _foreign, vehicle = flow_ctx
    before = db.query(VehicleOwnership).filter(VehicleOwnership.vehicle_id == int(vehicle.id)).count()
    service_workspace.create_service_vehicle_work_access(
        int(vehicle.id),
        service_workspace.ServiceWorkAccessRequestV1(reason="Bez propojení", source="intake"),
        current_user=service,
        db=db,
    )
    wo = dashboard_router.create_service_work_order(
        payload=dashboard_router.ServiceWorkOrderCreateRequest(
            vehicle_id=int(vehicle.id),
            title="Jednorázový příjem",
            status="intake_pending",
            source_type="intake",
        ),
        current_user=_service_user(service),
        db=db,
    )
    after = db.query(VehicleOwnership).filter(VehicleOwnership.vehicle_id == int(vehicle.id)).count()
    assert after == before
    assert wo["status"] == "intake_pending"


def test_intake_draft_work_order_accept_to_in_progress(flow_ctx):
    _engine, db, _owner, service, _foreign, vehicle = flow_ctx
    service_workspace.create_service_vehicle_work_access(
        int(vehicle.id),
        service_workspace.ServiceWorkAccessRequestV1(reason="Příjem", source="intake"),
        current_user=service,
        db=db,
    )
    wo = dashboard_router.create_service_work_order(
        payload=dashboard_router.ServiceWorkOrderCreateRequest(
            vehicle_id=int(vehicle.id),
            title="Příjem",
            status="intake_pending",
            source_type="intake",
        ),
        current_user=_service_user(service),
        db=db,
    )
    accepted = accept_work_order(int(wo["id"]), current_user=_service_user(service), db=db)
    assert accepted["status"] == "in_progress"


def test_owner_safe_history_no_invoice_prices_after_one_time_work(flow_ctx):
    _engine, db, owner, service, _foreign, vehicle = flow_ctx
    service_workspace.create_service_vehicle_work_access(
        int(vehicle.id),
        service_workspace.ServiceWorkAccessRequestV1(reason="Safe history", source="intake"),
        current_user=service,
        db=db,
    )
    wo = dashboard_router.create_service_work_order(
        payload=dashboard_router.ServiceWorkOrderCreateRequest(
            vehicle_id=int(vehicle.id),
            title="Servisní zásah",
            status="intake_pending",
            source_type="intake",
        ),
        current_user=_service_user(service),
        db=db,
    )
    order = db.query(ServiceWorkOrder).filter(ServiceWorkOrder.id == int(wo["id"])).one()
    order.status = "completed"
    db.commit()
    history = build_owner_safe_service_history(db, vehicle_id=int(vehicle.id), owner_customer_id=int(owner.id))
    blob = json.dumps(history, ensure_ascii=False).lower()
    assert "invoice" not in blob or "invoice_id" not in blob
    assert "purchase_price" not in blob
