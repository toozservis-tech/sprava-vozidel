"""C1.6 — platform handover protocol documents (VehicleDocument + renderer)."""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PyPDF2 import PdfReader
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceCustomerLink,
    ServiceIntake,
    Tenant,
    Vehicle,
    VehicleDocument,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.routers_v1 import service_dashboard as service_dashboard_router
from src.modules.vehicle_hub.routers_v1 import vehicle_documents as vehicle_documents_router
from src.server.routers import public_documents as public_documents_router


def _make_app(db):
    app = FastAPI()
    app.include_router(service_dashboard_router.router)
    app.include_router(vehicle_documents_router.router, prefix="/api/v1")
    app.include_router(public_documents_router.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[service_dashboard_router.get_db] = override_get_db
    app.dependency_overrides[vehicle_documents_router.get_db] = override_get_db
    app.dependency_overrides[public_documents_router.get_db] = override_get_db
    return app


@pytest.fixture()
def handover_protocol_platform_context(tmp_path: Path, monkeypatch):
    docs_root = tmp_path / "vehicle_documents"
    docs_root.mkdir(parents=True, exist_ok=True)
    for target in (
        "src.modules.vehicle_hub.documents.document_service.VEHICLE_DOCUMENTS_ROOT",
        "src.modules.vehicle_hub.documents.document_storage.VEHICLE_DOCUMENTS_ROOT",
        "src.modules.vehicle_hub.documents.invoice_sync.VEHICLE_DOCUMENTS_ROOT",
        "src.modules.vehicle_hub.documents.quote_sync.VEHICLE_DOCUMENTS_ROOT",
        "src.modules.vehicle_hub.documents.work_order_sheet_sync.VEHICLE_DOCUMENTS_ROOT",
        "src.modules.vehicle_hub.documents.intake_protocol_sync.VEHICLE_DOCUMENTS_ROOT",
        "src.modules.vehicle_hub.documents.service_report_sync.VEHICLE_DOCUMENTS_ROOT",
        "src.modules.vehicle_hub.documents.handover_protocol_sync.VEHICLE_DOCUMENTS_ROOT",
    ):
        monkeypatch.setattr(target, docs_root)

    db_path = tmp_path / "handover_protocol_platform.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="Handover Protocol Platform Tenant", license_key="handover-protocol-platform-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    service_a = Customer(
        tenant_id=tenant.id,
        email="service-a@example.com",
        name="Servis A",
        role="service",
        ico="11111111",
    )
    service_b = Customer(
        tenant_id=tenant.id,
        email="service-b@example.com",
        name="Servis B",
        role="service",
    )
    owner = Customer(
        tenant_id=tenant.id,
        email="owner@example.com",
        name="Majitel",
        role="user",
    )
    db.add_all([service_a, service_b, owner])
    db.commit()
    for row in (service_a, service_b, owner):
        db.refresh(row)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        brand="Skoda",
        model="Octavia",
        vin="VINHANDOVER123456",
        plate="1AB2345",
        stk_valid_until=date(2030, 1, 1),
        current_mileage_km=118500,
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
            is_active=True,
            is_primary=True,
        )
    )
    db.add(
        ServiceCustomerLink(
            service_tenant_id=tenant.id,
            service_customer_id=service_a.id,
            customer_tenant_id=tenant.id,
            customer_id=owner.id,
            status="active",
        )
    )
    db.add(
        VehicleServiceLink(
            tenant_id=tenant.id,
            service_customer_id=service_a.id,
            owner_customer_id=owner.id,
            vehicle_id=vehicle.id,
            status="approved",
        )
    )
    db.add(
        VehicleServiceLink(
            tenant_id=tenant.id,
            service_customer_id=service_b.id,
            owner_customer_id=owner.id,
            vehicle_id=vehicle.id,
            status="approved",
        )
    )
    db.commit()

    app = _make_app(db)

    def set_user(user: Customer):
        from src.modules.vehicle_hub.routers_v1 import auth as auth_module

        app.dependency_overrides[auth_module.get_current_user] = lambda: user
        app.dependency_overrides[service_dashboard_router.get_current_user] = lambda: user
        app.dependency_overrides[vehicle_documents_router.get_current_user] = lambda: user

    client = TestClient(app)
    try:
        yield {
            "db": db,
            "client": client,
            "set_user": set_user,
            "service_a": service_a,
            "service_b": service_b,
            "owner": owner,
            "vehicle": vehicle,
            "tenant": tenant,
            "docs_root": docs_root,
        }
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _create_completed_work_order(ctx, *, with_recommendations: bool = True) -> dict:
    db = ctx["db"]
    intake = ServiceIntake(
        tenant_id=ctx["tenant"].id,
        service_id=ctx["service_a"].id,
        vehicle_id=ctx["vehicle"].id,
        customer_id=ctx["owner"].id,
        odometer_km=125000,
        damage_description="Opotřebené brzdové destičky",
        customer_request="Výměna brzd",
        fluids_ok='{"keys": true}',
        check_in_at=datetime.utcnow(),
    )
    db.add(intake)
    db.commit()
    db.refresh(intake)

    ctx["set_user"](ctx["service_a"])
    created = ctx["client"].post(
        "/api/service/work-orders",
        json={
            "owner_id": ctx["owner"].id,
            "vehicle_id": ctx["vehicle"].id,
            "technician_id": ctx["service_a"].id,
            "title": "Servis brzd",
            "description": "Výměna brzdových destiček a kotoučů",
            "source_type": "intake",
            "source_intake_id": intake.id,
            "status": "in_progress",
        },
    )
    assert created.status_code == 200, created.text
    wo = created.json()

    labor = ctx["client"].post(
        f"/api/service/work-orders/{wo['id']}/labor",
        json={"name": "Výměna brzdových destiček", "hours": 2, "unit_price_without_vat": 500},
    )
    assert labor.status_code == 200, labor.text

    parts = ctx["client"].post(
        f"/api/service/work-orders/{wo['id']}/parts",
        json={"name": "Brzdové destičky", "quantity": 1, "unit_price_without_vat": 890},
    )
    assert parts.status_code == 200, parts.text

    complete = ctx["client"].post(f"/api/service/work-orders/{wo['id']}/complete", json={})
    assert complete.status_code == 200, complete.text

    if with_recommendations:
        record_resp = ctx["client"].post(
            f"/api/service/work-orders/{wo['id']}/service-record",
            json={"mileage": 126800},
        )
        assert record_resp.status_code == 200, record_resp.text
        from src.modules.vehicle_hub.models import ServiceRecord

        record = db.query(ServiceRecord).filter(ServiceRecord.work_order_id == int(wo["id"])).first()
        assert record is not None
        record.recommended_next_service_text = "Kontrola brzd za 12 měsíců"
        db.add(record)
        db.commit()

    return wo


def test_handover_protocol_pdf_uses_platform_renderer(handover_protocol_platform_context) -> None:
    wo = _create_completed_work_order(handover_protocol_platform_context)
    ctx = handover_protocol_platform_context
    ctx["set_user"](ctx["service_a"])
    response = ctx["client"].get(f"/api/service/work-orders/{wo['id']}/handover.pdf")
    assert response.status_code == 200
    body = response.content
    assert body.startswith(b"%PDF")
    assert len(body) > 4096
    text = _pdf_text(body)
    assert "PŘEDÁVACÍ PROTOKOL" in text
    assert "Document Platform C1.6" in text


def test_handover_protocol_creates_vehicle_document(handover_protocol_platform_context) -> None:
    wo = _create_completed_work_order(handover_protocol_platform_context)
    ctx = handover_protocol_platform_context
    ctx["set_user"](ctx["service_a"])
    ctx["client"].get(f"/api/service/work-orders/{wo['id']}/handover.pdf")
    doc = (
        ctx["db"]
        .query(VehicleDocument)
        .filter(
            VehicleDocument.source_type == "service_work_order",
            VehicleDocument.source_id == int(wo["id"]),
            VehicleDocument.document_type == "handover_protocol",
        )
        .first()
    )
    assert doc is not None
    assert int(doc.vehicle_id) == int(ctx["vehicle"].id)
    assert doc.verification_token


def test_handover_protocol_vehicle_document_no_duplicates(handover_protocol_platform_context) -> None:
    wo = _create_completed_work_order(handover_protocol_platform_context)
    ctx = handover_protocol_platform_context
    ctx["set_user"](ctx["service_a"])
    ctx["client"].get(f"/api/service/work-orders/{wo['id']}/handover.pdf")
    ctx["client"].put(
        f"/api/service/work-orders/{wo['id']}",
        json={"description": "Aktualizovaný popis předání"},
    )
    ctx["client"].get(f"/api/service/work-orders/{wo['id']}/handover.pdf")
    rows = (
        ctx["db"]
        .query(VehicleDocument)
        .filter(
            VehicleDocument.source_type == "service_work_order",
            VehicleDocument.source_id == int(wo["id"]),
            VehicleDocument.document_type == "handover_protocol",
        )
        .all()
    )
    assert len(rows) == 1


def test_handover_protocol_pdf_contains_vehicle(handover_protocol_platform_context) -> None:
    wo = _create_completed_work_order(handover_protocol_platform_context)
    ctx = handover_protocol_platform_context
    ctx["set_user"](ctx["service_a"])
    text = _pdf_text(ctx["client"].get(f"/api/service/work-orders/{wo['id']}/handover.pdf").content)
    assert "Octavia" in text or "1AB2345" in text or "Skoda" in text


def test_handover_protocol_pdf_contains_handover_date(handover_protocol_platform_context) -> None:
    wo = _create_completed_work_order(handover_protocol_platform_context)
    ctx = handover_protocol_platform_context
    ctx["set_user"](ctx["service_a"])
    text = _pdf_text(ctx["client"].get(f"/api/service/work-orders/{wo['id']}/handover.pdf").content)
    assert "Datum a čas předání" in text or "202" in text


def test_handover_protocol_pdf_contains_work_summary(handover_protocol_platform_context) -> None:
    wo = _create_completed_work_order(handover_protocol_platform_context)
    ctx = handover_protocol_platform_context
    ctx["set_user"](ctx["service_a"])
    text = _pdf_text(ctx["client"].get(f"/api/service/work-orders/{wo['id']}/handover.pdf").content)
    assert "brzd" in text.lower() or "destič" in text.lower()


def test_handover_protocol_pdf_contains_recommendations(handover_protocol_platform_context) -> None:
    wo = _create_completed_work_order(handover_protocol_platform_context)
    ctx = handover_protocol_platform_context
    ctx["set_user"](ctx["service_a"])
    text = _pdf_text(ctx["client"].get(f"/api/service/work-orders/{wo['id']}/handover.pdf").content)
    assert "12 měsíc" in text.lower() or "brzd" in text.lower()


def test_handover_protocol_pdf_contains_qr_verify(handover_protocol_platform_context) -> None:
    wo = _create_completed_work_order(handover_protocol_platform_context)
    ctx = handover_protocol_platform_context
    ctx["set_user"](ctx["service_a"])
    ctx["client"].get(f"/api/service/work-orders/{wo['id']}/handover.pdf")
    doc = (
        ctx["db"]
        .query(VehicleDocument)
        .filter(VehicleDocument.source_id == int(wo["id"]), VehicleDocument.document_type == "handover_protocol")
        .first()
    )
    assert doc
    text = _pdf_text(ctx["client"].get(f"/api/service/work-orders/{wo['id']}/handover.pdf").content)
    assert "Ověření dokumentu" in text or doc.verification_token


def test_handover_protocol_pdf_is_not_text_export(handover_protocol_platform_context) -> None:
    wo = _create_completed_work_order(handover_protocol_platform_context)
    ctx = handover_protocol_platform_context
    ctx["set_user"](ctx["service_a"])
    body = ctx["client"].get(f"/api/service/work-orders/{wo['id']}/handover.pdf").content
    assert len(body) > 4096
    text = _pdf_text(body)
    assert "Document Platform C1.6" in text
    assert "PŘEDÁVACÍ PROTOKOL" in text


def test_handover_protocol_document_scoped_to_service(handover_protocol_platform_context) -> None:
    wo = _create_completed_work_order(handover_protocol_platform_context)
    ctx = handover_protocol_platform_context
    db = ctx["db"]
    vehicle_id = ctx["vehicle"].id
    ctx["set_user"](ctx["service_a"])
    ctx["client"].get(f"/api/service/work-orders/{wo['id']}/handover.pdf")
    doc = (
        db.query(VehicleDocument)
        .filter(VehicleDocument.source_id == int(wo["id"]), VehicleDocument.document_type == "handover_protocol")
        .first()
    )
    assert doc is not None
    doc.visibility_scope = "service_private"
    db.add(doc)
    db.commit()

    items = ctx["client"].get(f"/api/v1/vehicles/{vehicle_id}/documents").json()
    assert any(item.get("document_type") == "handover_protocol" for item in items)

    ctx["set_user"](ctx["service_b"])
    foreign = ctx["client"].get(f"/api/v1/vehicles/{vehicle_id}/documents").json()
    assert not any(item.get("document_type") == "handover_protocol" for item in foreign)

    doc_id = next(item["id"] for item in items if item["document_type"] == "handover_protocol")
    ctx["set_user"](ctx["service_b"])
    assert ctx["client"].get(f"/api/v1/vehicles/{vehicle_id}/documents/{doc_id}/file").status_code == 403


def test_owner_does_not_see_service_private_handover_protocol(handover_protocol_platform_context) -> None:
    wo = _create_completed_work_order(handover_protocol_platform_context)
    ctx = handover_protocol_platform_context
    db = ctx["db"]
    vehicle_id = ctx["vehicle"].id
    ctx["set_user"](ctx["service_a"])
    ctx["client"].get(f"/api/service/work-orders/{wo['id']}/handover.pdf")
    doc = (
        db.query(VehicleDocument)
        .filter(VehicleDocument.source_id == int(wo["id"]), VehicleDocument.document_type == "handover_protocol")
        .first()
    )
    assert doc is not None
    doc.visibility_scope = "service_private"
    db.add(doc)
    db.commit()

    ctx["set_user"](ctx["owner"])
    listed = ctx["client"].get(f"/api/v1/vehicles/{vehicle_id}/documents")
    assert listed.status_code == 200
    assert not any(item.get("document_type") == "handover_protocol" for item in listed.json())

    from src.modules.vehicle_hub.documents.document_service import user_can_view_document

    assert user_can_view_document(db, current_user=ctx["owner"], doc=doc) is False


def test_owner_can_see_owner_visible_handover_protocol_without_prices(handover_protocol_platform_context) -> None:
    wo = _create_completed_work_order(handover_protocol_platform_context)
    ctx = handover_protocol_platform_context
    vehicle_id = ctx["vehicle"].id
    ctx["set_user"](ctx["service_a"])
    ctx["client"].get(f"/api/service/work-orders/{wo['id']}/handover.pdf")
    ctx["set_user"](ctx["owner"])
    listed = ctx["client"].get(f"/api/v1/vehicles/{vehicle_id}/documents")
    assert listed.status_code == 200
    reports = [item for item in listed.json() if item.get("document_type") == "handover_protocol"]
    assert len(reports) == 1

    doc = (
        ctx["db"]
        .query(VehicleDocument)
        .filter(VehicleDocument.source_id == int(wo["id"]), VehicleDocument.document_type == "handover_protocol")
        .first()
    )
    assert doc is not None
    assert doc.visibility_scope in {"owner_visible", "safe_after_claim"}

    doc_id = reports[0]["id"]
    pdf = ctx["client"].get(f"/api/v1/vehicles/{vehicle_id}/documents/{doc_id}/file")
    assert pdf.status_code == 200
    text = _pdf_text(pdf.content)
    assert "890" not in text
    assert "Kč" not in text
    assert "brzd" in text.lower() or "destič" in text.lower()


def test_public_verify_handover_protocol_safe_no_pii(handover_protocol_platform_context) -> None:
    wo = _create_completed_work_order(handover_protocol_platform_context)
    ctx = handover_protocol_platform_context
    ctx["set_user"](ctx["service_a"])
    ctx["client"].get(f"/api/service/work-orders/{wo['id']}/handover.pdf")
    doc = (
        ctx["db"]
        .query(VehicleDocument)
        .filter(VehicleDocument.source_id == int(wo["id"]), VehicleDocument.document_type == "handover_protocol")
        .first()
    )
    assert doc
    response = ctx["client"].get(f"/api/public/documents/verify/{doc.verification_token}")
    assert response.status_code == 200
    payload = response.json()
    blob = str(payload).lower()
    assert "owner@example.com" not in blob
    assert "vinhandover" not in blob
    assert payload.get("document_type") == "handover_protocol"
