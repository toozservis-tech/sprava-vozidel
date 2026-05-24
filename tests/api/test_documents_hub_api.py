from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceRecord,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehicleReportDocument,
    VehicleTachometerHistoryEntry,
)
from src.modules.licensing.service import upgrade_license_plan
from src.modules.vehicle_hub.routers_v1 import service_records as service_records_router


@pytest.fixture()
def documents_client(tmp_path: Path):
    db_path = tmp_path / "documents_hub.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="Documents Tenant", license_key="documents-tenant-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(
        tenant_id=tenant.id,
        email="documents@example.com",
        password_hash="hash",
        role="user",
        name="Documents User",
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Documents Auto",
        vin="TMBDOCUMENTSHUB001",
        plate="2AB3456",
        stk_valid_until=date(2030, 1, 1),
    )
    vehicle_second = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Classic PDF Auto",
        vin="TMBDOCUMENTSHUB002",
        plate="3CD4567",
        stk_valid_until=date(2031, 1, 1),
    )
    db.add(vehicle)
    db.add(vehicle_second)
    db.commit()
    db.refresh(vehicle)
    db.refresh(vehicle_second)

    db.add(
        VehicleOwnership(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            is_active=True,
            is_primary=True,
        )
    )
    db.add(
        VehicleOwnership(
            tenant_id=tenant.id,
            vehicle_id=vehicle_second.id,
            customer_id=owner.id,
            is_active=True,
            is_primary=False,
        )
    )
    db.add(
        ServiceRecord(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            user_id=owner.id,
            performed_at=datetime.utcnow().replace(microsecond=0),
            mileage=145000,
            description="Servis s přílohou",
            category="OLEJ",
            attachments=json.dumps(
                [
                    {
                        "file_name": "faktura.pdf",
                        "mime_type": "application/pdf",
                        "storage_key": "tenant_1/vehicle_1/test.pdf",
                        "download_url": f"/api/v1/vehicles/{vehicle.id}/records/attachments/download?key=tenant_1%2Fvehicle_1%2Ftest.pdf",
                        "source_type": "invoice",
                    }
                ],
                ensure_ascii=False,
            ),
        )
    )
    db.add(
        VehicleReportDocument(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            generated_by_user_id=owner.id,
            document_type="vehicle_service_report",
            export_mode="owner",
            document_id="DOC-HUB-001",
            public_token="public-doc-token",
            verification_code="ABCD-1234",
            hash_sha256="hash",
            payload_hash_sha256="payload-hash",
            verification_enabled=True,
            status="valid",
        )
    )
    db.add(
        VehicleTachometerHistoryEntry(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            check_date=datetime.utcnow().replace(microsecond=0),
            mileage_km=144321,
            protocol_number="PT-001",
            source="stk",
            documents_json=json.dumps(
                [
                    {
                        "document_id": "doc-1",
                        "title": "Protokol STK",
                        "available": True,
                    }
                ],
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    upgrade_license_plan(db, tenant.id, "basic")

    app = FastAPI()
    app.include_router(service_records_router.router, prefix="/api/v1")

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[service_records_router.get_db] = override_get_db
    app.dependency_overrides[service_records_router.get_current_user] = lambda: owner

    client = TestClient(app)
    try:
        yield client, vehicle, vehicle_second
    finally:
        db.close()
        engine.dispose()


def test_documents_hub_endpoint_aggregates_reports_attachments_and_tachometer(documents_client) -> None:
    client, vehicle, vehicle_second = documents_client

    response = client.get("/api/v1/vehicles/documents/hub")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "user"
    assert int(payload["vehicles_total"]) == 2
    assert int(payload["attachments_total"]) == 1
    assert int(payload["reports_total"]) == 2
    assert int(payload["tachometer_documents_total"]) == 1
    assert int(payload["technical_certificates_total"]) == 2
    assert len(payload["technical_certificates"]) == 2
    tc_by_vid = {int(item["vehicle_id"]): item for item in payload["technical_certificates"]}
    assert tc_by_vid[vehicle.id]["document_title"] == "Velký technický průkaz"
    assert tc_by_vid[vehicle.id]["download_url"].endswith(
        f"/api/v1/vehicles/{vehicle.id}/documents/large-technical-certificate.pdf"
    )
    assert payload["attachments"][0]["vehicle_id"] == vehicle.id
    reports_by_vehicle = {int(item["vehicle_id"]): item for item in payload["reports"]}
    assert reports_by_vehicle[vehicle.id]["verify_url"] == "/verify/public-doc-token"
    assert reports_by_vehicle[vehicle.id]["classic_pdf_url"] == f"/api/v1/vehicles/{vehicle.id}/export/pdf"
    assert reports_by_vehicle[vehicle.id]["verified_pdf_url"] == f"/api/v1/vehicles/{vehicle.id}/report.pdf"
    assert reports_by_vehicle[vehicle.id]["has_verified_report"] is True
    assert reports_by_vehicle[vehicle_second.id]["classic_pdf_url"] == f"/api/v1/vehicles/{vehicle_second.id}/export/pdf"
    assert reports_by_vehicle[vehicle_second.id]["verified_pdf_url"] is None
    assert reports_by_vehicle[vehicle_second.id]["has_verified_report"] is False
    assert payload["tachometer_documents"][0]["protocol_number"] == "PT-001"


def test_large_technical_certificate_pdf_returns_pdf_bytes(documents_client) -> None:
    client, vehicle, _vehicle_second = documents_client
    response = client.get(f"/api/v1/vehicles/{vehicle.id}/documents/large-technical-certificate.pdf")
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/pdf")
    assert response.content[:4] == b"%PDF"


def test_free_plan_blocks_documents_hub_and_pdf_endpoints(tmp_path: Path) -> None:
    """FREE tarif (documents_enabled false) musí vracet 403 na dokumentové endpointy."""
    db_path = tmp_path / "free_docs.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="Free Tenant", license_key="free-docs-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(
        tenant_id=tenant.id,
        email="free@example.com",
        password_hash="hash",
        role="user",
        name="Free User",
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Auto",
        vin="TMBFREEPLAN00001",
        plate="1AA1111",
        stk_valid_until=date(2030, 1, 1),
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    db.add(
        VehicleOwnership(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            is_active=True,
            is_primary=True,
        )
    )
    db.commit()

    app = FastAPI()
    app.include_router(service_records_router.router, prefix="/api/v1")

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[service_records_router.get_db] = override_get_db
    app.dependency_overrides[service_records_router.get_current_user] = lambda: owner

    client = TestClient(app)
    try:
        assert client.get("/api/v1/vehicles/documents/hub").status_code == 403
        assert client.get(f"/api/v1/vehicles/{vehicle.id}/report.pdf?mode=public").status_code == 403
        assert client.get(f"/api/v1/vehicles/{vehicle.id}/export/pdf").status_code == 403
        assert (
            client.get(f"/api/v1/vehicles/{vehicle.id}/documents/large-technical-certificate.pdf").status_code
            == 403
        )
    finally:
        client.close()
        db.close()
        engine.dispose()
