from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.central_vehicle_identity import normalize_plate, normalize_vin, sync_vehicle_identity_fields
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    GlobalAuditLog,
    ServiceRecord,
    ServiceVehicleLookupAudit,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.ownership import user_owns_vehicle
from src.modules.vehicle_hub.routers_v1.auth import can_access_vehicle
from src.modules.vehicle_hub.routers_v1 import service_workspace, vehicles


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'central_vehicle_identity.sqlite'}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _tenant(db, name: str) -> Tenant:
    tenant = Tenant(name=name, license_key=f"lic-{name}", workspace_slug=name, workspace_route_kind="service")
    db.add(tenant)
    db.flush()
    return tenant


def _customer(db, tenant: Tenant, email: str, role: str = "user") -> Customer:
    customer = Customer(tenant_id=tenant.id, email=email, role=role, name=email.split("@", 1)[0], password_hash="x")
    db.add(customer)
    db.flush()
    return customer


def _vehicle(db, tenant: Tenant, *, vin: str | None, plate: str | None, owner: Customer | None = None, service: Customer | None = None) -> Vehicle:
    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email if owner else "_service_unowned@test.local",
        nickname="Test vehicle",
        brand="Skoda",
        model="Octavia",
        year=2020,
        vin=normalize_vin(vin) or None,
        plate=plate,
        global_vehicle_status="owned_vehicle" if owner else "service_provisioned_unowned",
        source_origin="user_created" if owner else "service_created",
        claim_status="none" if owner else "unclaimed",
        provisioned_by_service_customer_id=service.id if service else None,
        provisioned_by_service_tenant_id=service.tenant_id if service else None,
    )
    sync_vehicle_identity_fields(vehicle)
    db.add(vehicle)
    db.flush()
    if owner:
        db.add(
            VehicleOwnership(
                tenant_id=tenant.id,
                vehicle_id=vehicle.id,
                customer_id=owner.id,
                ownership_origin="test",
                is_primary=True,
                is_active=True,
            )
        )
        db.flush()
    return vehicle


def test_existing_owner_vehicle_visibility_preserved(db):
    tenant = _tenant(db, "owner-preserved")
    owner = _customer(db, tenant, "owner@example.test")
    stranger = _customer(db, tenant, "stranger@example.test")
    vehicle = _vehicle(db, tenant, vin="TMB123456789ABCDE", plate="1AB 2345", owner=owner)

    assert user_owns_vehicle(db, owner, vehicle) is True
    assert user_owns_vehicle(db, stranger, vehicle) is False


def test_service_lookup_existing_vehicle_without_access_returns_safe_preview_only(db):
    tenant = _tenant(db, "safe-preview")
    owner = _customer(db, tenant, "owner-safe@example.test")
    service = _customer(db, tenant, "service-safe@example.test", role="service")
    vehicle = _vehicle(db, tenant, vin="TMB123456789ABCDF", plate="4AB 1234", owner=owner)

    payload = service_workspace.CentralVehicleLookupRequestV1(query="4ab-1234", query_type="plate")
    response = service_workspace.central_service_vehicle_lookup(payload, request=None, current_user=service, db=db)

    assert response["found"] is True
    assert response["status"] == "found_access_required"
    assert response["vehicle_preview"]["vehicle_id"] == vehicle.id
    assert response["vehicle_preview"]["vin_masked"] != vehicle.vin
    assert response["vehicle_preview"]["plate_masked"] != normalize_plate(vehicle.plate)
    assert response["owner_data"] is None
    assert response["service_history"] is None
    assert response["photos"] is None
    assert response["documents"] is None
    assert response["prices"] is None
    assert response["invoices"] is None
    assert db.query(ServiceVehicleLookupAudit).count() == 1


def test_service_request_access_then_owner_approves_then_detail_visible(db):
    tenant = _tenant(db, "approved-access")
    owner = _customer(db, tenant, "owner-approved@example.test")
    service = _customer(db, tenant, "service-approved@example.test", role="service")
    vehicle = _vehicle(db, tenant, vin="TMB123456789ABCDG", plate="5AB 1234", owner=owner)
    db.add(
        VehicleServiceLink(
            tenant_id=tenant.id,
            service_customer_id=service.id,
            owner_customer_id=owner.id,
            vehicle_id=vehicle.id,
            status="approved",
            approved_at=datetime.utcnow(),
            approved_by_customer_id=owner.id,
        )
    )
    db.commit()

    payload = service_workspace.CentralVehicleLookupRequestV1(query=vehicle.vin, query_type="vin")
    response = service_workspace.central_service_vehicle_lookup(payload, request=None, current_user=service, db=db)

    assert response["status"] == "found_access_approved"
    assert response["can_open_detail"] is True
    assert can_access_vehicle(vehicle.id, service, db) is True


def test_service_lookup_not_found_can_create_unowned_vehicle_and_duplicate_vin_is_blocked(db):
    tenant = _tenant(db, "unowned")
    service = _customer(db, tenant, "service-unowned@example.test", role="service")

    not_found = service_workspace.central_service_vehicle_lookup(
        service_workspace.CentralVehicleLookupRequestV1(query="TMB123456789ABCDH", query_type="vin"),
        request=None,
        current_user=service,
        db=db,
    )
    assert not_found["found"] is False
    assert not_found["can_create_unowned_vehicle"] is True

    created = service_workspace.provision_unowned_service_vehicle(
        service_workspace.ServiceProvisionUnownedVehicleRequestV1(
            vin="TMB123456789ABCDH",
            plate="6AB 1234",
            brand="Skoda",
            model="Fabia",
            year=2019,
            mileage=123456,
        ),
        request=None,
        current_user=service,
        db=db,
    )
    vehicle = db.query(Vehicle).filter(Vehicle.id == created["vehicle_id"]).one()
    assert vehicle.global_vehicle_status == "service_provisioned_unowned"
    assert vehicle.normalized_vin == "TMB123456789ABCDH"
    assert db.query(VehicleOwnership).filter(VehicleOwnership.vehicle_id == vehicle.id).count() == 0
    assert can_access_vehicle(vehicle.id, service, db) is True

    with pytest.raises(HTTPException) as duplicate:
        service_workspace.provision_unowned_service_vehicle(
            service_workspace.ServiceProvisionUnownedVehicleRequestV1(
                vin="TMB123456789ABCDH",
                plate="7AB 1234",
                brand="Skoda",
                model="Fabia",
            ),
            request=None,
            current_user=service,
            db=db,
        )
    assert duplicate.value.status_code == 409


def test_owner_claims_service_created_vehicle_and_sees_safe_history_without_prices_or_invoice_data(db):
    tenant = _tenant(db, "claim-safe-history")
    service = _customer(db, tenant, "service-claim@example.test", role="service")
    owner = _customer(db, tenant, "owner-claim@example.test")
    vehicle = _vehicle(db, tenant, vin="TMB123456789ABCDJ", plate="8AB 1234", service=service)
    db.add(
        ServiceRecord(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            user_id=service.id,
            service_id=service.id,
            created_by_service_customer_id=service.id,
            performed_at=datetime.utcnow(),
            mileage=111222,
            category="OLEJ",
            service_type="maintenance",
            description="Výměna oleje a filtrů",
            notes_customer_visible="Výměna oleje, filtrů a kontrola brzd.",
            note="Interní poznámka servisu, nesmí k majiteli.",
            price=2500,
            total_price=3025,
            quote_id=123,
            visibility_scope="safe_history_after_claim",
            origin="service_created",
        )
    )
    db.commit()

    lookup = vehicles.owner_vehicle_claim_lookup(
        vehicles.VehicleClaimLookupRequestV1(vin="TMB123456789ABCDJ"),
        current_user=owner,
        db=db,
    )
    assert lookup["claim_available"] is True

    vehicles.owner_vehicle_claim_init(
        vehicle.id,
        vehicles.VehicleClaimInitRequestV1(vin="TMB123456789ABCDJ", verification_method="manual_confirmation"),
        current_user=owner,
        db=db,
    )
    confirmed = vehicles.owner_vehicle_claim_confirm(
        vehicle.id,
        vehicles.VehicleClaimConfirmRequestV1(vin="TMB123456789ABCDJ", confirm_ownership=True),
        current_user=owner,
        db=db,
    )
    assert confirmed["claimed"] is True
    assert user_owns_vehicle(db, owner, vehicle) is True

    history = vehicles.get_owner_safe_service_history(vehicle.id, current_user=owner, db=db)
    assert len(history["items"]) == 1
    item = history["items"][0]
    assert item["source_label"] == "Servisní záznam"
    assert "price" not in item
    assert "total_price" not in item
    assert "invoice_id" not in item
    assert "quote_id" not in item
    assert "service_id" not in item
    assert "service_name" not in item
    assert "Interní poznámka" not in str(item)


def test_plate_only_match_is_safe_candidate_not_auto_merge(db):
    tenant = _tenant(db, "plate-candidate")
    service = _customer(db, tenant, "service-plate@example.test", role="service")
    _vehicle(db, tenant, vin=None, plate="9AB 1234", service=service)

    with pytest.raises(HTTPException) as conflict:
        service_workspace.provision_unowned_service_vehicle(
            service_workspace.ServiceProvisionUnownedVehicleRequestV1(
                plate="9AB-1234",
                brand="VW",
                model="Golf",
            ),
            request=None,
            current_user=service,
            db=db,
        )
    assert conflict.value.status_code == 409
    assert conflict.value.detail["code"] == "plate_candidate_requires_review"
    assert db.query(Vehicle).filter(Vehicle.normalized_plate == normalize_plate("9AB 1234")).count() == 1


def test_audit_written_for_lookup_create_claim_access(db):
    tenant = _tenant(db, "audit")
    service = _customer(db, tenant, "service-audit@example.test", role="service")
    owner = _customer(db, tenant, "owner-audit@example.test")

    service_workspace.central_service_vehicle_lookup(
        service_workspace.CentralVehicleLookupRequestV1(query="TMB123456789ABCDK", query_type="vin"),
        request=None,
        current_user=service,
        db=db,
    )
    created = service_workspace.provision_unowned_service_vehicle(
        service_workspace.ServiceProvisionUnownedVehicleRequestV1(
            vin="TMB123456789ABCDK",
            brand="BMW",
            model="320d",
        ),
        request=None,
        current_user=service,
        db=db,
    )
    vehicles.owner_vehicle_claim_lookup(
        vehicles.VehicleClaimLookupRequestV1(vin="TMB123456789ABCDK"),
        current_user=owner,
        db=db,
    )
    vehicles.owner_vehicle_claim_confirm(
        int(created["vehicle_id"]),
        vehicles.VehicleClaimConfirmRequestV1(vin="TMB123456789ABCDK", confirm_ownership=True),
        current_user=owner,
        db=db,
    )

    actions = {row.action for row in db.query(GlobalAuditLog).all()}
    assert "service_vehicle_lookup" in actions
    assert "service_unowned_vehicle_created" in actions
    assert "owner_vehicle_claim_lookup" in actions
    assert "owner_vehicle_claim_approved" in actions
