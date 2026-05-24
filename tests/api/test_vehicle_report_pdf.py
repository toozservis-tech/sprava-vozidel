from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from PyPDF2 import PdfReader
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceRecord,
    ServiceVehicleAccess,
    Tenant,
    Vehicle,
    VehicleInspectionHistory,
    VehicleOwnership,
    VehicleReportDocument,
)
from src.modules.vehicle_hub.reports.vehicle_report_builder import build_vehicle_service_report_payload
from src.modules.vehicle_hub.reports.vehicle_report_models import VehicleReportMode
from src.modules.vehicle_hub.reports.vehicle_report_pdf import _generate_mileage_chart_png
from src.modules.licensing.service import upgrade_license_plan
from src.modules.vehicle_hub.routers_v1 import api_router
from src.modules.vehicle_hub.routers_v1 import service_records as service_records_router
from src.server.routers import system as system_router
from src.server.routers import public_documents as public_documents_router


@pytest.fixture()
def report_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "vehicle_report_pdf.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="Report Tenant", license_key="report-tenant-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(
        tenant_id=tenant.id,
        email="owner@example.com",
        name="Jan Černý",
        phone="+420777111222",
        city="Praha",
        role="user",
    )
    service_user = Customer(
        tenant_id=tenant.id,
        email="service@example.com",
        name="Český Servis s.r.o.",
        role="service",
    )
    admin = Customer(
        tenant_id=tenant.id,
        email="admin@example.com",
        name="Admin Audit",
        role="admin",
    )
    db.add_all([owner, service_user, admin])
    db.commit()
    for row in (owner, service_user, admin):
        db.refresh(row)

    vehicle_main = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Rodinný vůz",
        brand="ŠKODA",
        model="Superb",
        year=2020,
        engine="2.0 TDI 110 kW diesel DSG",
        vin="TMBJF73T2B9044629",
        plate="1AB2345",
        stk_valid_until=date(2027, 5, 10),
        current_mileage_km=154320,
    )
    vehicle_empty = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Druhé auto",
        brand="Toyota",
        model="Yaris",
        year=2018,
        vin="JTDKB20U907123456",
        plate="2BC3456",
        stk_valid_until=date(2026, 11, 4),
    )
    vehicle_long = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Firemní flotila",
        brand="Volkswagen",
        model="Passat",
        year=2019,
        engine="2.0 TDI 110 kW diesel",
        vin="WVWZZZ3CZKE123456",
        plate="3CD4567",
        stk_valid_until=date(2027, 3, 1),
        current_mileage_km=201000,
    )
    db.add_all([vehicle_main, vehicle_empty, vehicle_long])
    db.commit()
    for row in (vehicle_main, vehicle_empty, vehicle_long):
        db.refresh(row)

    db.add_all(
        [
            VehicleOwnership(
                tenant_id=tenant.id,
                vehicle_id=vehicle_main.id,
                customer_id=owner.id,
                ownership_type="owner",
                is_primary=True,
                is_active=True,
                assigned_by_customer_id=owner.id,
            ),
            VehicleOwnership(
                tenant_id=tenant.id,
                vehicle_id=vehicle_empty.id,
                customer_id=owner.id,
                ownership_type="owner",
                is_primary=True,
                is_active=True,
                assigned_by_customer_id=owner.id,
            ),
            VehicleOwnership(
                tenant_id=tenant.id,
                vehicle_id=vehicle_long.id,
                customer_id=owner.id,
                ownership_type="owner",
                is_primary=True,
                is_active=True,
                assigned_by_customer_id=owner.id,
            ),
            ServiceVehicleAccess(
                service_customer_id=service_user.id,
                customer_id=owner.id,
                vehicle_id=vehicle_main.id,
                status="active",
                granted_by_customer_id=owner.id,
            ),
        ]
    )

    attachment_payload = json.dumps(
        [
            {
                "file_name": "faktura-cz.pdf",
                "source_type": "invoice",
                "parsed_summary": {
                    "source_type": "invoice",
                    "supplier_name": "Český Servis s.r.o.",
                    "service_summary": "Výměna oleje a kontrola brzd",
                    "technician_name": "Petr Říha",
                    "document_number": "FV-2026-001",
                    "currency": "CZK",
                    "total_with_vat": 4290,
                    "labor_total": 1900,
                    "materials_total": 2390,
                    "items": [
                        {"name": "Motorový olej 5W-30"},
                        {"name": "Olejový filtr"},
                        {"name": "Brzdová kapalina"},
                    ],
                },
            }
        ],
        ensure_ascii=False,
    )

    records = [
        ServiceRecord(
            tenant_id=tenant.id,
            vehicle_id=vehicle_main.id,
            user_id=service_user.id,
            performed_at=datetime(2025, 2, 12, 9, 30),
            mileage=142000,
            description="Pravidelná servisní prohlídka po zimě",
            price=4290.0,
            note="Zákazník požadoval kontrolu brzd a klimatizace.",
            category="OLEJ",
            attachments=attachment_payload,
            next_service_due_date=date.today() + timedelta(days=25),
        ),
        ServiceRecord(
            tenant_id=tenant.id,
            vehicle_id=vehicle_main.id,
            user_id=owner.id,
            performed_at=datetime(2025, 9, 4, 8, 45),
            mileage=151800,
            description="Výměna předních brzdových destiček",
            price=3850.0,
            note="Použity originální díly.",
            category="BRZDY",
        ),
    ]

    for idx in range(34):
        records.append(
            ServiceRecord(
                tenant_id=tenant.id,
                vehicle_id=vehicle_long.id,
                user_id=service_user.id,
                performed_at=datetime(2024, 1, 1, 8, 0) + timedelta(days=idx * 21),
                mileage=120000 + (idx * 2200),
                description=f"Dlouhý servisní záznam {idx + 1} s rozšířenou poznámkou pro test vícestránkového layoutu.",
                note="Kontrola podvozku, kapalin, brzd a elektroniky. " * 4,
                category="OPRAVA" if idx % 2 else "OLEJ",
            )
        )

    db.add_all(records)
    db.add_all(
        [
            VehicleInspectionHistory(
                tenant_id=tenant.id,
                vehicle_id=vehicle_main.id,
                vin=vehicle_main.vin,
                inspection_date=datetime(2025, 5, 1, 9, 0),
                inspection_type="STK",
                inspection_kind="Pravidelna kontrola",
                odometer_km=145000,
                protocol_number="STK-2025-05-01-A",
                source="kontrolatachometru.cz",
                source_hash="hist-a",
                raw_payload_json=json.dumps({"detail_available": True}),
            ),
            VehicleInspectionHistory(
                tenant_id=tenant.id,
                vehicle_id=vehicle_main.id,
                vin=vehicle_main.vin,
                inspection_date=datetime(2025, 5, 1, 15, 0),
                inspection_type="STK",
                inspection_kind="Pravidelna kontrola",
                odometer_km=145050,
                protocol_number="STK-2025-05-01-B",
                source="kontrolatachometru.cz",
                source_hash="hist-b",
                raw_payload_json=json.dumps({"detail_available": True}),
            ),
            VehicleInspectionHistory(
                tenant_id=tenant.id,
                vehicle_id=vehicle_main.id,
                vin=vehicle_main.vin,
                inspection_date=datetime(2025, 5, 20, 8, 30),
                inspection_type="SME",
                inspection_kind="Evidencni kontrola",
                odometer_km=168500,
                protocol_number="SME-2025-05-20-C",
                source="kontrolatachometru.cz",
                source_hash="hist-c",
                raw_payload_json=json.dumps({"detail_available": True}),
            ),
            VehicleInspectionHistory(
                tenant_id=tenant.id,
                vehicle_id=vehicle_main.id,
                vin=vehicle_main.vin,
                inspection_date=datetime(2025, 8, 1, 8, 0),
                inspection_type="STK",
                inspection_kind="Opakovana kontrola",
                odometer_km=150200,
                protocol_number="STK-2025-08-01-D",
                source="kontrolatachometru.cz",
                source_hash="hist-d",
                raw_payload_json=json.dumps({"detail_available": True}),
            ),
        ]
    )
    db.commit()
    upgrade_license_plan(db, tenant.id, "basic")

    app = FastAPI()
    app.include_router(api_router)
    app.include_router(public_documents_router.router)
    app.include_router(system_router.router)
    users_by_token = {
        "owner": owner,
        "service": service_user,
        "admin": admin,
    }

    def override_get_db():
        yield db

    def override_get_current_user(request: Request):
        token = str(request.headers.get("authorization") or "").replace("Bearer", "").strip().lower()
        return users_by_token[token]

    app.dependency_overrides[service_records_router.get_db] = override_get_db
    app.dependency_overrides[service_records_router.get_current_user] = override_get_current_user
    app.dependency_overrides[public_documents_router.get_db] = override_get_db
    monkeypatch.setattr(service_records_router, "log_security_event", lambda **_: None)
    monkeypatch.setattr(public_documents_router, "log_security_event", lambda **_: None)

    client = TestClient(app)
    try:
        yield {
            "client": client,
            "db": db,
            "owner": owner,
            "vehicle_main": vehicle_main,
            "vehicle_empty": vehicle_empty,
            "vehicle_long": vehicle_long,
        }
    finally:
        client.close()
        db.close()
        engine.dispose()


def _pdf_text(payload: bytes) -> str:
    reader = PdfReader(BytesIO(payload))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _build_payload(report_client, vehicle_key: str = "vehicle_main"):
    db = report_client["db"]
    owner = report_client["owner"]
    vehicle = report_client[vehicle_key]
    return build_vehicle_service_report_payload(
        db=db,
        vehicle=vehicle,
        current_user=owner,
        mode=VehicleReportMode.OWNER,
    )


def test_vehicle_report_builds_mileage_timeline_from_multiple_sources(report_client) -> None:
    payload = _build_payload(report_client)

    assert len(payload.mileage_timeline.points) >= 5
    source_types = {point.source_type for point in payload.mileage_timeline.points}
    assert {"service_record", "stk_history"}.issubset(source_types)
    ordered_dates = [point.date for point in payload.mileage_timeline.points]
    assert ordered_dates == sorted(ordered_dates)


def test_vehicle_report_timeline_flags_duplicate_rollback_and_suspicious_jump(report_client) -> None:
    payload = _build_payload(report_client)

    anomaly_flags = [flag for point in payload.mileage_timeline.points for flag in point.anomaly_flags]
    assert "duplicate" in anomaly_flags
    assert "rollback" in anomaly_flags
    assert "suspicious_jump" in anomaly_flags
    assert payload.mileage_timeline.anomalies_count >= 3


def test_vehicle_report_timeline_does_not_flag_same_day_sme_then_stk_as_duplicate() -> None:
    from datetime import datetime

    from src.modules.vehicle_hub.reports.vehicle_report_mileage_timeline import build_vehicle_report_mileage_timeline
    from src.modules.vehicle_hub.reports.vehicle_report_models import VehicleReportServiceRecord

    class InspectionRow:
        def __init__(self, inspection_date, inspection_type, inspection_kind, odometer_km, row_id):
            self.inspection_date = inspection_date
            self.inspection_type = inspection_type
            self.inspection_kind = inspection_kind
            self.odometer_km = odometer_km
            self.id = row_id
            self.source = "kontrolatachometru.cz"

    timeline = build_vehicle_report_mileage_timeline(
        service_records=[],
        inspections=[
            InspectionRow(datetime(2024, 4, 22, 8, 0), "SME", "Pravidelna", 402410, 1),
            InspectionRow(datetime(2024, 4, 22, 11, 0), "STK", "Pravidelna", 402411, 2),
        ],
    )

    assert len(timeline.points) == 2
    assert all("duplicate" not in point.anomaly_flags for point in timeline.points)


def test_vehicle_report_chart_generation_returns_png(report_client) -> None:
    payload = _build_payload(report_client)

    chart_png = _generate_mileage_chart_png(payload)

    assert chart_png is not None
    assert chart_png.startswith(b"\x89PNG\r\n\x1a\n")


def test_vehicle_report_endpoint_returns_pdf_and_filename(report_client) -> None:
    client = report_client["client"]
    db = report_client["db"]
    vehicle = report_client["vehicle_main"]

    response = client.get(
        f"/api/v1/vehicles/{vehicle.id}/report.pdf?mode=public",
        headers={"Authorization": "Bearer owner"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    disposition = response.headers.get("content-disposition") or ""
    assert "toozservis-vypis-vozidla-SKODA-SUPERB-TMBJF73T2B9044629.pdf" in disposition
    assert "filename*=" in disposition

    text = _pdf_text(response.content)
    assert "Digitální servisní výpis" in text
    assert "vozidla" in text
    assert "ŠKODA Superb" in text
    assert "Vyvoj stavu km" in text
    assert "Ověření" in text
    assert "dokumentu" in text
    assert "hub.toozservis.cz/verify" in text
    assert "Důvěryhodnost a původ dat" in text
    assert "Auditovatelnost a rozsah zdrojů" in text

    document = db.query(VehicleReportDocument).filter(VehicleReportDocument.vehicle_id == vehicle.id).first()
    assert document is not None
    assert document.public_token
    assert document.status == "valid"

    reader = PdfReader(BytesIO(response.content))
    assert len(reader.pages) >= 2

    legacy_response = client.get(
        f"/api/v1/vehicles/{vehicle.id}/pdf?mode=public",
        headers={"Authorization": "Bearer owner"},
    )
    assert legacy_response.status_code == 200


def test_vehicle_report_renders_vehicle_without_records(report_client) -> None:
    client = report_client["client"]
    vehicle = report_client["vehicle_empty"]

    response = client.get(
        f"/api/v1/vehicles/{vehicle.id}/report.pdf?mode=public",
        headers={"Authorization": "Bearer owner"},
    )

    assert response.status_code == 200
    text = _pdf_text(response.content)
    assert "zatím nejsou evidovány žádné servisní záznamy" in text.lower()
    assert "Toyota Yaris" in text


def test_vehicle_report_includes_multiple_records_and_czech_diacritics(report_client) -> None:
    client = report_client["client"]
    vehicle = report_client["vehicle_main"]

    response = client.get(
        f"/api/v1/vehicles/{vehicle.id}/report.pdf?mode=owner",
        headers={"Authorization": "Bearer owner"},
    )

    assert response.status_code == 200
    text = _pdf_text(response.content)
    assert "Český Servis s.r.o." in text
    assert "Jan Černý" in text
    assert "Praha" in text


def test_vehicle_report_includes_stk_import_rows_in_history(report_client) -> None:
    client = report_client["client"]
    vehicle = report_client["vehicle_main"]

    response = client.get(
        f"/api/v1/vehicles/{vehicle.id}/report.pdf?mode=owner",
        headers={"Authorization": "Bearer owner"},
    )

    assert response.status_code == 200
    text = _pdf_text(response.content)
    assert "Načteno z kontroly tachometru (MDČR)" in text
    assert "Import STK / tachometr" in text
    assert "kontrolatachometru.cz" in text


def test_vehicle_report_forbids_unauthorized_modes(report_client) -> None:
    client = report_client["client"]
    vehicle = report_client["vehicle_main"]

    forbidden_owner = client.get(
        f"/api/v1/vehicles/{vehicle.id}/report.pdf?mode=owner",
        headers={"Authorization": "Bearer service"},
    )
    forbidden_audit = client.get(
        f"/api/v1/vehicles/{vehicle.id}/report.pdf?mode=internal_audit",
        headers={"Authorization": "Bearer owner"},
    )
    workshop_ok = client.get(
        f"/api/v1/vehicles/{vehicle.id}/report.pdf?mode=workshop",
        headers={"Authorization": "Bearer service"},
    )

    assert forbidden_owner.status_code == 403
    assert forbidden_audit.status_code == 403
    assert workshop_ok.status_code == 200


def test_vehicle_report_long_history_spans_multiple_pages(report_client) -> None:
    client = report_client["client"]
    vehicle = report_client["vehicle_long"]

    response = client.get(
        f"/api/v1/vehicles/{vehicle.id}/report.pdf?mode=public",
        headers={"Authorization": "Bearer owner"},
    )

    assert response.status_code == 200
    reader = PdfReader(BytesIO(response.content))
    assert len(reader.pages) >= 2
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Dlouhý servisní záznam 34" in text


def test_vehicle_report_pdf_contains_chart_image_object(report_client) -> None:
    client = report_client["client"]
    vehicle = report_client["vehicle_main"]

    response = client.get(
        f"/api/v1/vehicles/{vehicle.id}/report.pdf?mode=public",
        headers={"Authorization": "Bearer owner"},
    )

    assert response.status_code == 200
    reader = PdfReader(BytesIO(response.content))
    assert any(
        bool((page.get("/Resources") or {}).get("/XObject"))
        for page in reader.pages
    )


def test_public_verify_token_returns_valid_and_hides_owner_data(report_client) -> None:
    client = report_client["client"]
    db = report_client["db"]
    vehicle = report_client["vehicle_main"]

    response = client.get(
        f"/api/v1/vehicles/{vehicle.id}/report.pdf?mode=public",
        headers={"Authorization": "Bearer owner"},
    )
    assert response.status_code == 200

    document = db.query(VehicleReportDocument).filter(VehicleReportDocument.vehicle_id == vehicle.id).first()
    assert document is not None

    verify_response = client.get(f"/api/public/documents/verify/{document.public_token}")
    assert verify_response.status_code == 200
    payload = verify_response.json()
    assert payload["status"] == "valid"
    assert payload["document_id"] == document.document_id
    assert payload["issued_service_name"] == "Report Tenant"
    assert payload["vehicle_brand"] == "ŠKODA"
    assert payload["vehicle_model"] == "Superb"
    assert payload["vehicle_vin_masked"].startswith("TMB")
    assert payload["verification_code"] == document.verification_code
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "Jan Černý" not in serialized
    assert "+420777111222" not in serialized
    assert "owner@example.com" not in serialized


def test_public_verify_by_code_returns_valid(report_client) -> None:
    client = report_client["client"]
    db = report_client["db"]
    vehicle = report_client["vehicle_main"]

    response = client.get(
        f"/api/v1/vehicles/{vehicle.id}/report.pdf?mode=public",
        headers={"Authorization": "Bearer owner"},
    )
    assert response.status_code == 200
    document = db.query(VehicleReportDocument).filter(VehicleReportDocument.vehicle_id == vehicle.id).first()

    verify_response = client.post(
        "/api/public/documents/verify-by-code",
        json={"verification_code": document.verification_code.replace("-", "")},
    )
    assert verify_response.status_code == 200
    payload = verify_response.json()
    assert payload["status"] == "valid"
    assert payload["verification_code"] == document.verification_code


def test_public_verify_superseded_status(report_client) -> None:
    client = report_client["client"]
    db = report_client["db"]
    vehicle = report_client["vehicle_main"]

    first = client.get(
        f"/api/v1/vehicles/{vehicle.id}/report.pdf?mode=public",
        headers={"Authorization": "Bearer owner"},
    )
    assert first.status_code == 200
    first_document = (
        db.query(VehicleReportDocument)
        .filter(VehicleReportDocument.vehicle_id == vehicle.id)
        .order_by(VehicleReportDocument.id.asc())
        .first()
    )
    record = db.query(ServiceRecord).filter(ServiceRecord.vehicle_id == vehicle.id).first()
    record.note = "Změněná poznámka pro novou revizi dokumentu."
    db.commit()

    second = client.get(
        f"/api/v1/vehicles/{vehicle.id}/report.pdf?mode=public",
        headers={"Authorization": "Bearer owner"},
    )
    assert second.status_code == 200

    db.refresh(first_document)
    assert first_document.status == "superseded"
    assert first_document.replaced_by_document_id

    verify_response = client.get(f"/api/public/documents/verify/{first_document.public_token}")
    assert verify_response.status_code == 200
    payload = verify_response.json()
    assert payload["status"] == "superseded"
    assert payload["is_current_version"] is False


def test_public_verify_revoked_status(report_client) -> None:
    client = report_client["client"]
    db = report_client["db"]
    vehicle = report_client["vehicle_main"]

    response = client.get(
        f"/api/v1/vehicles/{vehicle.id}/report.pdf?mode=public",
        headers={"Authorization": "Bearer owner"},
    )
    assert response.status_code == 200
    document = db.query(VehicleReportDocument).filter(VehicleReportDocument.vehicle_id == vehicle.id).first()
    document.status = "revoked"
    db.commit()

    verify_response = client.get(f"/api/public/documents/verify/{document.public_token}")
    assert verify_response.status_code == 200
    payload = verify_response.json()
    assert payload["status"] == "revoked"
    assert payload["is_current_version"] is False


def test_public_verify_not_found_and_verify_page_exist(report_client) -> None:
    client = report_client["client"]

    verify_response = client.get("/api/public/documents/verify/non-existent-token")
    assert verify_response.status_code == 200
    payload = verify_response.json()
    assert payload["status"] == "not_found"

    page_response = client.get("/verify/test-token")
    assert page_response.status_code == 200
    assert "Ověření dokumentu" in page_response.text
