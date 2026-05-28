from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceAccessRequest,
    Tenant,
    Vehicle,
    VehicleOwnership,
)
from src.modules.vehicle_hub.routers_v1 import service_workspace


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'service_intake.sqlite'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _tenant(db, suffix: str) -> Tenant:
    row = Tenant(name=f"tenant-{suffix}", license_key=f"lic-{suffix}")
    db.add(row)
    db.flush()
    return row


def _customer(db, tenant: Tenant, email: str, role: str = "user") -> Customer:
    row = Customer(
        tenant_id=tenant.id,
        email=email,
        password_hash="hash",
        role=role,
        name=email.split("@")[0],
    )
    db.add(row)
    db.flush()
    return row


def _vehicle(db, tenant: Tenant, owner: Customer | None, vin: str | None, plate: str | None) -> Vehicle:
    row = Vehicle(
        tenant_id=tenant.id,
        user_email=(owner.email if owner else "nobody@example.test"),
        nickname="Intake test",
        brand="Skoda",
        model="Octavia",
        vin=vin,
        plate=plate,
    )
    db.add(row)
    db.flush()
    if owner:
        db.add(
            VehicleOwnership(
                tenant_id=tenant.id,
                vehicle_id=row.id,
                customer_id=owner.id,
                ownership_type="owner",
                is_primary=True,
                is_active=True,
                assigned_by_customer_id=owner.id,
                assigned_at=datetime.utcnow(),
            )
        )
        db.flush()
    return row


def test_service_intake_lookup_not_found(db):
    tenant = _tenant(db, "lookup-not-found")
    service = _customer(db, tenant, "service-intake-not-found@example.test", role="service")
    payload = service_workspace.CentralVehicleLookupRequestV1(vin="TMBJH7NP9N7041234", source="service_intake", context="intake_route")
    body = service_workspace.central_service_vehicle_lookup(payload, request=None, current_user=service, db=db)
    assert body["status"] == "not_found"
    assert body["can_create_unowned_vehicle"] is True


def test_service_intake_lookup_found_safe_preview(db):
    tenant = _tenant(db, "lookup-safe-preview")
    owner = _customer(db, tenant, "owner-safe-preview@example.test")
    service = _customer(db, tenant, "service-safe-preview@example.test", role="service")
    vehicle = _vehicle(db, tenant, owner, vin="TMBJH7NP9N7041111", plate="1AB1234")
    body = service_workspace.central_service_vehicle_lookup(
        service_workspace.CentralVehicleLookupRequestV1(vin=vehicle.vin, source="service_intake", context="intake_route"),
        request=None,
        current_user=service,
        db=db,
    )
    assert body["status"] == "found_access_required"
    assert body["vehicle_preview"]["vehicle_id"] == vehicle.id
    assert body["vehicle_preview"]["vin_masked"] != vehicle.vin


def test_service_intake_lookup_no_owner_data(db):
    tenant = _tenant(db, "lookup-no-owner-data")
    owner = _customer(db, tenant, "owner-no-owner-data@example.test")
    service = _customer(db, tenant, "service-no-owner-data@example.test", role="service")
    vehicle = _vehicle(db, tenant, owner, vin="TMBJH7NP9N7042222", plate="2AB1234")
    body = service_workspace.central_service_vehicle_lookup(
        service_workspace.CentralVehicleLookupRequestV1(plate=vehicle.plate, source="service_intake", context="intake_route"),
        request=None,
        current_user=service,
        db=db,
    )
    assert body["owner_data"] is None


def test_service_intake_lookup_no_prices_invoices_docs_photos(db):
    tenant = _tenant(db, "lookup-no-sensitive")
    owner = _customer(db, tenant, "owner-no-sensitive@example.test")
    service = _customer(db, tenant, "service-no-sensitive@example.test", role="service")
    vehicle = _vehicle(db, tenant, owner, vin="TMBJH7NP9N7043333", plate="3AB1234")
    body = service_workspace.central_service_vehicle_lookup(
        service_workspace.CentralVehicleLookupRequestV1(vin=vehicle.vin, source="service_intake", context="intake_route"),
        request=None,
        current_user=service,
        db=db,
    )
    assert body["prices"] is None
    assert body["invoices"] is None
    assert body["documents"] is None
    assert body["photos"] is None
    assert body["service_history"] is None


def test_service_intake_create_unowned_vehicle(db):
    tenant = _tenant(db, "create-unowned")
    service = _customer(db, tenant, "service-create-unowned@example.test", role="service")
    created = service_workspace.provision_unowned_service_vehicle(
        service_workspace.ServiceProvisionUnownedVehicleRequestV1(
            vin="TMBJH7NP9N7044444",
            plate="4AB1234",
            brand="Skoda",
            model="Fabia",
            source="service_intake",
            context="intake_route",
        ),
        request=None,
        current_user=service,
        db=db,
    )
    assert created["created"] is True
    assert created["status"] == "service_provisioned_unowned"


def test_service_intake_unowned_lookup_can_create_work_order(db):
    tenant = _tenant(db, "unowned-wo-lookup")
    service = _customer(db, tenant, "service-unowned-wo@example.test", role="service")
    created = service_workspace.provision_unowned_service_vehicle(
        service_workspace.ServiceProvisionUnownedVehicleRequestV1(
            vin="TMBJH7NP9N7088882",
            brand="Skoda",
            model="Fabia",
            source="service_intake",
            context="intake_route",
        ),
        request=None,
        current_user=service,
        db=db,
    )
    body = service_workspace.central_service_vehicle_lookup(
        service_workspace.CentralVehicleLookupRequestV1(
            vin="TMBJH7NP9N7088882",
            source="service_intake",
            context="intake_route",
        ),
        request=None,
        current_user=service,
        db=db,
    )
    assert body["status"] == "found_service_unowned"
    assert body.get("can_create_work_order") is True
    assert int(created["vehicle_id"]) == body["vehicle_preview"]["vehicle_id"]


def test_service_intake_create_unowned_no_ownership_created(db):
    tenant = _tenant(db, "create-unowned-no-ownership")
    service = _customer(db, tenant, "service-create-unowned-no-own@example.test", role="service")
    created = service_workspace.provision_unowned_service_vehicle(
        service_workspace.ServiceProvisionUnownedVehicleRequestV1(
            vin="TMBJH7NP9N7045555",
            brand="Skoda",
            model="Fabia",
            source="service_intake",
            context="intake_route",
        ),
        request=None,
        current_user=service,
        db=db,
    )
    vehicle_id = int(created["vehicle_id"])
    assert db.query(VehicleOwnership).filter(VehicleOwnership.vehicle_id == vehicle_id).count() == 0


def test_service_intake_duplicate_vin_blocked(db):
    tenant = _tenant(db, "duplicate-vin")
    service = _customer(db, tenant, "service-duplicate-vin@example.test", role="service")
    _vehicle(db, tenant, None, vin="TMBJH7NP9N7046666", plate="6AB1234")
    with pytest.raises(HTTPException) as err:
        service_workspace.provision_unowned_service_vehicle(
            service_workspace.ServiceProvisionUnownedVehicleRequestV1(
                vin="TMBJH7NP9N7046666",
                plate="7AB1234",
                brand="Skoda",
                model="Fabia",
                source="service_intake",
                context="intake_route",
            ),
            request=None,
            current_user=service,
            db=db,
        )
    assert err.value.status_code == 409


def test_service_intake_access_request_created(db):
    tenant = _tenant(db, "access-request-created")
    owner = _customer(db, tenant, "owner-access-request-created@example.test")
    service = _customer(db, tenant, "service-access-request-created@example.test", role="service")
    vehicle = _vehicle(db, tenant, owner, vin="TMBJH7NP9N7047777", plate="7AB1234")
    body = service_workspace.create_service_access_request(
        payload=service_workspace.ServiceAccessRequestCreateV1(vehicle_id=vehicle.id, lookup_query=vehicle.plate, note="Příjem vozidla do servisu"),
        current_user=service,
        db=db,
    )
    assert body["created"] is True
    assert body["status"] == "pending"


def test_service_intake_access_request_duplicate_not_created(db):
    tenant = _tenant(db, "access-request-duplicate")
    owner = _customer(db, tenant, "owner-access-request-duplicate@example.test")
    service = _customer(db, tenant, "service-access-request-duplicate@example.test", role="service")
    vehicle = _vehicle(db, tenant, owner, vin="TMBJH7NP9N7048888", plate="8AB1234")
    db.add(
        ServiceAccessRequest(
            tenant_id=tenant.id,
            service_customer_id=service.id,
            owner_customer_id=owner.id,
            vehicle_id=vehicle.id,
            requested_scope="history_read_create_record",
            status="pending",
            request_message="already pending",
        )
    )
    db.flush()
    body = service_workspace.create_service_access_request(
        payload=service_workspace.ServiceAccessRequestCreateV1(vehicle_id=vehicle.id, lookup_query=vehicle.plate, note="dup"),
        current_user=service,
        db=db,
    )
    assert body["created"] is False
    assert body["status"] == "pending"


def test_service_intake_plate_only_candidate_no_auto_merge(db):
    tenant = _tenant(db, "plate-only-candidate")
    service = _customer(db, tenant, "service-plate-only-candidate@example.test", role="service")
    _vehicle(db, tenant, None, vin=None, plate="9AB1234")
    with pytest.raises(HTTPException) as err:
        service_workspace.provision_unowned_service_vehicle(
            service_workspace.ServiceProvisionUnownedVehicleRequestV1(
                plate="9AB-1234",
                brand="VW",
                model="Golf",
                source="service_intake",
                context="intake_route",
            ),
            request=None,
            current_user=service,
            db=db,
        )
    assert err.value.status_code == 409
    assert err.value.detail["code"] == "plate_candidate_requires_review"
