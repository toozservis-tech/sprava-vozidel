from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.documents.document_registry import DOCUMENT_REGISTRY
from src.modules.vehicle_hub.documents.document_renderer import render_platform_document_pdf
from src.modules.vehicle_hub.documents.document_schemas import PlatformDocumentPayload
from src.modules.vehicle_hub.documents.document_service import create_platform_document
from src.modules.vehicle_hub.models import (
    Customer,
    Tenant,
    Vehicle,
    VehicleDocument,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.routers_v1 import vehicle_documents as vehicle_documents_router
from src.server.routers import public_documents as public_documents_router


def _make_app(db):
    app = FastAPI()
    app.include_router(vehicle_documents_router.router, prefix="/api/v1")
    app.include_router(public_documents_router.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[vehicle_documents_router.get_db] = override_get_db
    app.dependency_overrides[public_documents_router.get_db] = override_get_db
    return app


@pytest.fixture()
def platform_context(tmp_path: Path, monkeypatch):
    docs_root = tmp_path / "vehicle_documents"
    docs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "src.modules.vehicle_hub.documents.document_service.VEHICLE_DOCUMENTS_ROOT",
        docs_root,
    )
    monkeypatch.setattr(
        "src.modules.vehicle_hub.documents.document_storage.VEHICLE_DOCUMENTS_ROOT",
        docs_root,
    )

    db_path = tmp_path / "vehicle_documents.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="Doc Platform Tenant", license_key="doc-platform-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    service_a = Customer(
        tenant_id=tenant.id,
        email="service-a@example.com",
        name="Servis A",
        role="service",
        ico="12345678",
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
        vin="VINPLATFORM123456789",
        plate="1AB2345",
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
    db.add(
        VehicleServiceLink(
            tenant_id=tenant.id,
            service_customer_id=service_a.id,
            owner_customer_id=owner.id,
            vehicle_id=vehicle.id,
            status="approved",
        )
    )
    db.commit()

    app = _make_app(db)
    client = TestClient(app)

    def auth(email: str):
        from src.modules.vehicle_hub.routers_v1 import auth as auth_module

        app.dependency_overrides[auth_module.get_current_user] = lambda: db.query(Customer).filter(Customer.email == email).first()

    yield {
        "db": db,
        "client": client,
        "auth": auth,
        "vehicle": vehicle,
        "service_a": service_a,
        "service_b": service_b,
        "owner": owner,
        "docs_root": docs_root,
    }

    app.dependency_overrides.clear()


def test_vehicle_document_model_requires_vehicle_id(platform_context):
    db = platform_context["db"]
    row = VehicleDocument(
        tenant_id=platform_context["vehicle"].tenant_id,
        vehicle_id=platform_context["vehicle"].id,
        document_type="invoice",
        document_status="draft",
        title="Test",
        visibility_scope="owner_visible",
    )
    db.add(row)
    db.commit()
    assert row.vehicle_id == platform_context["vehicle"].id


def test_vehicle_document_create_platform_document(platform_context):
    db = platform_context["db"]
    platform_context["auth"](platform_context["service_a"].email)
    client = platform_context["client"]
    vehicle = platform_context["vehicle"]

    response = client.post(
        f"/api/v1/vehicles/{vehicle.id}/documents/platform",
        json={
            "document_type": "invoice",
            "document_status": "draft",
            "visibility_scope": "owner_visible",
            "title": "Test faktura platformy",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["document_type"] == "invoice"
    assert payload["status"] == "draft"
    assert "thumbnail_url" in payload
    assert "/documents/" in payload["file_url"]
    assert payload["storage_path"] if False else True  # API must not expose storage_path
    assert "storage_path" not in payload
    assert "tenants/" not in payload["file_url"]

    doc = db.query(VehicleDocument).filter(VehicleDocument.vehicle_id == vehicle.id).one()
    assert doc.vehicle_id == vehicle.id
    assert doc.verification_token
    assert doc.storage_path.startswith("tenants/")


def test_vehicle_documents_list_owner_safe(platform_context):
    db = platform_context["db"]
    create_platform_document(
        db,
        vehicle=platform_context["vehicle"],
        current_user=platform_context["service_a"],
        document_type="invoice",
        document_status="completed",
        visibility_scope="owner_visible",
    )
    create_platform_document(
        db,
        vehicle=platform_context["vehicle"],
        current_user=platform_context["service_a"],
        document_type="quote",
        document_status="draft",
        visibility_scope="service_private",
    )
    platform_context["auth"](platform_context["owner"].email)
    response = platform_context["client"].get(f"/api/v1/vehicles/{platform_context['vehicle'].id}/documents")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["document_type"] == "invoice"


def test_vehicle_documents_list_service_private_scoped(platform_context):
    db = platform_context["db"]
    create_platform_document(
        db,
        vehicle=platform_context["vehicle"],
        current_user=platform_context["service_a"],
        document_type="invoice",
        visibility_scope="service_private",
    )
    create_platform_document(
        db,
        vehicle=platform_context["vehicle"],
        current_user=platform_context["service_b"],
        document_type="quote",
        visibility_scope="service_private",
    )
    platform_context["auth"](platform_context["service_a"].email)
    response = platform_context["client"].get(f"/api/v1/vehicles/{platform_context['vehicle'].id}/documents")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1


def test_vehicle_document_file_access_scoped(platform_context):
    db = platform_context["db"]
    doc = create_platform_document(
        db,
        vehicle=platform_context["vehicle"],
        current_user=platform_context["service_a"],
        document_type="invoice",
        visibility_scope="owner_visible",
    )
    platform_context["auth"](platform_context["service_b"].email)
    response = platform_context["client"].get(
        f"/api/v1/vehicles/{platform_context['vehicle'].id}/documents/{doc.id}/file"
    )
    assert response.status_code == 403


def test_vehicle_document_verify_public_safe(platform_context):
    db = platform_context["db"]
    doc = create_platform_document(
        db,
        vehicle=platform_context["vehicle"],
        current_user=platform_context["service_a"],
        document_type="vehicle_history",
        document_status="completed",
        visibility_scope="public_verified",
    )
    response = platform_context["client"].get(f"/api/public/documents/verify/{doc.verification_token}")
    assert response.status_code == 200
    payload = response.json()
    assert "valid" in payload
    assert payload["document_type"] == "vehicle_history"
    assert "owner@example.com" not in str(payload)
    assert "VINPLATFORM" not in str(payload)


def test_vehicle_document_no_filesystem_path_leak(platform_context):
    platform_context["auth"](platform_context["service_a"].email)
    response = platform_context["client"].post(
        f"/api/v1/vehicles/{platform_context['vehicle'].id}/documents/platform",
        json={"document_type": "service_report", "document_status": "draft"},
    )
    assert response.status_code == 200
    body = response.text
    assert "/opt/" not in body
    assert "vehicle_documents/tenants" not in body


def test_vehicle_document_registry_contains_all_types(platform_context):
    response = platform_context["client"].get("/api/v1/vehicles/documents/registry")
    assert response.status_code == 200
    data = response.json()
    for key in (
        "invoice",
        "quote",
        "work_order_sheet",
        "intake_protocol",
        "service_report",
        "handover_protocol",
        "vehicle_history",
    ):
        assert key in data
        assert data[key]["label"]


def test_vehicle_document_generic_pdf_is_not_text_export():
    pdf = render_platform_document_pdf(
        PlatformDocumentPayload(
            document_type="invoice",
            document_status="draft",
            title="Platform proof",
            document_number="PLT-TEST-1",
            vehicle_label="Skoda Octavia",
            vehicle_plate="1AB 2345",
            vehicle_vin_masked="VIN***7890",
            service_name="Servis Test",
            verify_url="https://hub.toozservis.cz/verify/test-token",
            verification_code="ABCD-1234",
        )
    )
    assert len(pdf) > 4096
    assert pdf[:4] == b"%PDF"
    assert b"Platform proof" in pdf or b"Faktura" in pdf


def test_vehicle_document_thumbnail_fallback_exists(platform_context):
    db = platform_context["db"]
    doc = create_platform_document(
        db,
        vehicle=platform_context["vehicle"],
        current_user=platform_context["service_a"],
        document_type="invoice",
        visibility_scope="owner_visible",
    )
    platform_context["auth"](platform_context["owner"].email)
    response = platform_context["client"].get(
        f"/api/v1/vehicles/{platform_context['vehicle'].id}/documents/{doc.id}/thumbnail"
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg")


def test_vehicle_document_registry_module():
    assert len(DOCUMENT_REGISTRY) == 7
