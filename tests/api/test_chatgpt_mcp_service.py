from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    GlobalAuditLog,
    ServiceIntake,
    ServiceLaborSession,
    ServiceRecord,
    ServiceVehicleLookupAudit,
    Tenant,
    Vehicle,
    VehicleMileage,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.plugins.chatgpt_mcp import service


@pytest.fixture()
def mcp_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="MCP test", license_key="MCP-TEST-LICENSE")
    db.add(tenant)
    db.flush()

    operator = Customer(
        tenant_id=tenant.id,
        email="service-mcp@example.test",
        name="MCP Service",
        role="service",
        account_status="active",
        email_verified_at=None,
        is_disabled=False,
        is_deleted=False,
    )
    owner = Customer(
        tenant_id=tenant.id,
        email="owner-mcp@example.test",
        name="Private Owner Name",
        phone="+420777111222",
        street="Private Street",
        city="Private City",
        role="user",
        account_status="active",
        is_disabled=False,
        is_deleted=False,
    )
    db.add_all([operator, owner])
    db.flush()

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Dilenske auto",
        brand="Skoda",
        model="Superb",
        year=2019,
        fuel="diesel",
        engine="2.0 TDI",
        vin="TMBJJ7NP0K7000001",
        plate="1AB2345",
        current_mileage_km=184200,
        status="active",
    )
    private_vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Bez pristupu",
        brand="Volkswagen",
        model="Passat",
        year=2018,
        fuel="diesel",
        engine="2.0 TDI",
        vin="WVWZZZ3CZJE000002",
        plate="2CD6789",
        current_mileage_km=210000,
        status="active",
    )
    db.add_all([vehicle, private_vehicle])
    db.flush()

    ensure_vehicle_owner_assignment(
        db,
        vehicle=vehicle,
        owner=owner,
        assigned_by_customer_id=owner.id,
        ownership_origin="test",
    )
    ensure_vehicle_owner_assignment(
        db,
        vehicle=private_vehicle,
        owner=owner,
        assigned_by_customer_id=owner.id,
        ownership_origin="test",
    )

    link = VehicleServiceLink(
        tenant_id=tenant.id,
        service_customer_id=operator.id,
        owner_customer_id=owner.id,
        vehicle_id=vehicle.id,
        source_type="test_approved",
        status="approved",
        scope_vehicle_history_read=True,
        scope_create_service_record=True,
        scope_edit_existing_records=False,
        scope_delete_existing_records=False,
        owner_data_access_level="none",
        approved_by_customer_id=owner.id,
    )
    db.add(link)
    db.commit()

    monkeypatch.setenv("CHATGPT_MCP_SERVICE_USER_ID", str(operator.id))
    try:
        yield db, operator, owner, vehicle, private_vehicle, link
    finally:
        db.close()
        engine.dispose()


def test_plugin_status_does_not_expose_owner_pii(mcp_db):
    db, operator, owner, vehicle, private_vehicle, link = mcp_db
    result = service.plugin_status(db)

    assert result["ok"] is True
    assert result["actor_id"] == operator.id
    assert result["owner_personal_data_exposed"] is False
    serialized = json.dumps(result, ensure_ascii=False)
    assert owner.email not in serialized
    assert owner.phone not in serialized
    assert owner.name not in serialized


def test_lookup_masks_vehicle_without_approved_access_and_audits(mcp_db):
    db, operator, owner, vehicle, private_vehicle, link = mcp_db
    result = service.lookup_vehicle(db, query=private_vehicle.vin)

    assert result["status"] == "matched"
    item = result["items"][0]
    assert item["can_open_detail"] is False
    assert item["vin_masked"] != private_vehicle.vin
    assert "vin" not in item
    assert "plate" not in item
    assert owner.email not in json.dumps(result, ensure_ascii=False)

    assert db.query(ServiceVehicleLookupAudit).count() == 1
    assert db.query(GlobalAuditLog).filter(GlobalAuditLog.action == "mcp_vehicle_lookup").count() == 1


def test_service_case_creation_is_idempotent(mcp_db):
    db, operator, owner, vehicle, private_vehicle, link = mcp_db
    first = service.create_service_case(
        db,
        vehicle_id=vehicle.id,
        customer_request="Motor pri akceleraci cuka",
        mileage_km=184350,
        intake_note="Kontrola za tepla",
    )
    second = service.create_service_case(
        db,
        vehicle_id=vehicle.id,
        customer_request="Druhy klik nesmi vytvorit novy pripad",
        mileage_km=184350,
    )

    assert first["created"] is True
    assert second["created"] is False
    assert second["reason"] == "open_case_exists"
    assert second["case"]["case_id"] == first["case"]["case_id"]
    assert db.query(ServiceIntake).filter(ServiceIntake.vehicle_id == vehicle.id).count() == 1


def test_full_workshop_flow_is_audited_and_duplicate_safe(mcp_db):
    db, operator, owner, vehicle, private_vehicle, link = mcp_db
    created = service.create_service_case(
        db,
        vehicle_id=vehicle.id,
        customer_request="P0408, cuka od 1200 rpm",
        mileage_km=184420,
    )
    case_id = created["case"]["case_id"]

    diagnosis = service.record_diagnosis(
        db,
        case_id=case_id,
        symptoms=["cukani od 1200 rpm", "po odpojeni EGR chod plynuly"],
        dtcs=["P0408"],
        measurements=[
            {"name": "EGR commanded", "value": 90, "unit": "%", "condition": "open"},
            {"name": "EGR commanded", "value": 14, "unit": "%", "condition": "closed"},
        ],
        conclusion="Nutno overit snimac polohy EGR a kabelaz; zaver neni potvrzena vymena dilu.",
        visible_to_owner_note="Provedena diagnostika EGR okruhu.",
    )
    assert diagnosis["saved"] is True
    assert diagnosis["diagnosis"]["dtcs"] == ["P0408"]

    start1 = service.start_work(db, case_id=case_id)
    start2 = service.start_work(db, case_id=case_id)
    assert start1["started"] is True
    assert start2["started"] is False
    assert start2["reason"] == "already_running"
    assert start2["session_id"] == start1["session_id"]
    assert db.query(ServiceLaborSession).filter(ServiceLaborSession.service_case_id == case_id).count() == 1

    stop1 = service.stop_work(db, case_id=case_id)
    stop2 = service.stop_work(db, case_id=case_id)
    assert stop1["stopped"] is True
    assert stop2["stopped"] is False
    assert stop2["reason"] == "not_running"

    final1 = service.finalize_service_record(
        db,
        case_id=case_id,
        description="Diagnostika EGR okruhu a kontrola namerenych hodnot",
        category="diagnostics",
        mileage_km=184420,
        price=650,
        repair_summary="Diagnostika dokoncena, dalsi oprava podle vysledku kontroly kabelaze.",
    )
    final2 = service.finalize_service_record(
        db,
        case_id=case_id,
        description="Druhy klik nesmi vytvorit duplicitni historii",
        category="diagnostics",
        mileage_km=184420,
        price=650,
    )

    assert final1["created"] is True
    assert final2["created"] is False
    assert final2["reason"] == "already_finalized"
    assert final2["record_id"] == final1["record_id"]

    records = db.query(ServiceRecord).filter(ServiceRecord.service_case_id == case_id).all()
    assert len(records) == 1
    assert records[0].origin == "service_verified"
    assert records[0].created_by_ai is True
    assert records[0].service_access_link_id == link.id

    mileage_rows = db.query(VehicleMileage).filter(VehicleMileage.service_record_id == records[0].id).all()
    assert len(mileage_rows) == 1
    assert mileage_rows[0].mileage_km == 184420

    case = db.query(ServiceIntake).filter(ServiceIntake.id == case_id).first()
    assert case.intake_status == "completed"

    actions = {
        row.action
        for row in db.query(GlobalAuditLog).filter(GlobalAuditLog.vehicle_id == vehicle.id).all()
    }
    assert "mcp_service_case_created" in actions
    assert "mcp_diagnosis_recorded" in actions
    assert "mcp_labor_started" in actions
    assert "mcp_labor_stopped" in actions
    assert "mcp_service_record_finalized" in actions


def test_revoked_access_blocks_new_case(mcp_db):
    db, operator, owner, vehicle, private_vehicle, link = mcp_db
    link.status = "revoked"
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        service.create_service_case(
            db,
            vehicle_id=vehicle.id,
            customer_request="Toto se po odvolani pristupu nesmi zapsat",
        )

    assert exc_info.value.status_code == 403
    assert db.query(ServiceIntake).filter(ServiceIntake.vehicle_id == vehicle.id).count() == 0
