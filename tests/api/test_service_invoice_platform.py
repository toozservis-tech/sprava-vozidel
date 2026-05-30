"""C1.1 — platform invoice documents (VehicleDocument + renderer)."""
from __future__ import annotations

import re
from datetime import date
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
    Tenant,
    Vehicle,
    VehicleDocument,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.routers_v1 import service_invoices as service_invoices_router
from src.modules.vehicle_hub.routers_v1 import vehicle_documents as vehicle_documents_router
from src.server.routers import public_documents as public_documents_router


def _make_app(db):
    app = FastAPI()
    app.include_router(service_invoices_router.router)
    app.include_router(vehicle_documents_router.router, prefix="/api/v1")

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[service_invoices_router.get_db] = override_get_db
    app.dependency_overrides[vehicle_documents_router.get_db] = override_get_db
    app.dependency_overrides[public_documents_router.get_db] = override_get_db
    return app


@pytest.fixture()
def invoice_platform_context(tmp_path: Path, monkeypatch):
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
    monkeypatch.setattr(
        "src.modules.vehicle_hub.documents.invoice_sync.VEHICLE_DOCUMENTS_ROOT",
        docs_root,
    )

    db_path = tmp_path / "invoice_platform.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="Inv Platform Tenant", license_key="inv-platform-key")
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
        vin="VININVPLAT1234567",
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
    app.include_router(public_documents_router.router)

    def set_user(user: Customer):
        from src.modules.vehicle_hub.routers_v1 import auth as auth_module

        app.dependency_overrides[auth_module.get_current_user] = lambda: user
        app.dependency_overrides[service_invoices_router.get_current_user] = lambda: user
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
            "docs_root": docs_root,
        }
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


LINE = {
    "description": "Výměna oleje",
    "quantity": 1,
    "unit": "ks",
    "unit_price": 1000,
    "tax_rate": 21,
}


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _create_vehicle_invoice(ctx, *, issue: bool = True) -> dict:
    ctx["set_user"](ctx["service_a"])
    created = ctx["client"].post(
        "/api/service/invoices",
        json={
            "customer_id": ctx["owner"].id,
            "vehicle_id": ctx["vehicle"].id,
            "lines": [LINE],
        },
    )
    assert created.status_code == 201, created.text
    inv = created.json()
    if issue:
        issued = ctx["client"].post(f"/api/service/invoices/{inv['id']}/issue")
        assert issued.status_code == 200, issued.text
        inv = issued.json()
    return inv


def test_service_invoice_pdf_uses_platform_renderer(invoice_platform_context) -> None:
    inv = _create_vehicle_invoice(invoice_platform_context, issue=False)
    ctx = invoice_platform_context
    ctx["set_user"](ctx["service_a"])
    response = ctx["client"].get(f"/api/service/invoices/{inv['id']}/pdf")
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/pdf")
    body = response.content
    assert body.startswith(b"%PDF")
    assert len(body) > 4096
    text = _pdf_text(body)
    assert "FAKTURA" in text
    assert "Document Platform" in text
    assert "DejaVu" in body.decode("latin-1", errors="ignore") or "FAKTURA — daňový doklad" in text


def test_service_invoice_creates_vehicle_document(invoice_platform_context) -> None:
    inv = _create_vehicle_invoice(invoice_platform_context)
    db = invoice_platform_context["db"]
    doc = (
        db.query(VehicleDocument)
        .filter(
            VehicleDocument.source_type == "service_invoice",
            VehicleDocument.source_id == int(inv["id"]),
        )
        .first()
    )
    assert doc is not None
    assert doc.document_type == "invoice"
    assert int(doc.vehicle_id) == int(invoice_platform_context["vehicle"].id)
    assert doc.visibility_scope == "service_private"
    assert doc.verification_token


def test_service_invoice_vehicle_document_no_duplicates(invoice_platform_context) -> None:
    inv = _create_vehicle_invoice(invoice_platform_context, issue=False)
    ctx = invoice_platform_context
    ctx["set_user"](ctx["service_a"])
    ctx["client"].get(f"/api/service/invoices/{inv['id']}/pdf")
    ctx["client"].post(f"/api/service/invoices/{inv['id']}/issue")
    ctx["client"].get(f"/api/service/invoices/{inv['id']}/pdf")
    db = ctx["db"]
    rows = (
        db.query(VehicleDocument)
        .filter(
            VehicleDocument.source_type == "service_invoice",
            VehicleDocument.source_id == int(inv["id"]),
        )
        .all()
    )
    assert len(rows) == 1


def test_service_invoice_pdf_contains_invoice_number(invoice_platform_context) -> None:
    inv = _create_vehicle_invoice(invoice_platform_context)
    ctx = invoice_platform_context
    ctx["set_user"](ctx["service_a"])
    pdf = ctx["client"].get(f"/api/service/invoices/{inv['id']}/pdf").content
    number = str(inv.get("invoice_number") or "")
    assert number
    text = _pdf_text(pdf)
    assert number in text


def test_service_invoice_pdf_contains_vehicle(invoice_platform_context) -> None:
    inv = _create_vehicle_invoice(invoice_platform_context)
    ctx = invoice_platform_context
    ctx["set_user"](ctx["service_a"])
    pdf = ctx["client"].get(f"/api/service/invoices/{inv['id']}/pdf").content
    text = _pdf_text(pdf)
    assert "Octavia" in text or "1AB2345" in text or "Skoda" in text


def test_service_invoice_pdf_contains_qr_verify(invoice_platform_context) -> None:
    inv = _create_vehicle_invoice(invoice_platform_context)
    db = invoice_platform_context["db"]
    doc = (
        db.query(VehicleDocument)
        .filter(VehicleDocument.source_id == int(inv["id"]))
        .first()
    )
    assert doc and doc.verification_token
    ctx = invoice_platform_context
    ctx["set_user"](ctx["service_a"])
    pdf = ctx["client"].get(f"/api/service/invoices/{inv['id']}/pdf").content
    text = _pdf_text(pdf)
    assert "Ověření dokumentu" in text or doc.verification_token in text or "verify" in text


def test_service_invoice_pdf_is_not_text_export(invoice_platform_context) -> None:
    inv = _create_vehicle_invoice(invoice_platform_context)
    ctx = invoice_platform_context
    ctx["set_user"](ctx["service_a"])
    pdf = ctx["client"].get(f"/api/service/invoices/{inv['id']}/pdf").content
    text = _pdf_text(pdf)
    assert len(pdf) > 8000
    assert "FAKTURA" in text
    assert "Document Platform" in text
    assert "Položky" in text


def test_service_invoice_document_scoped_to_service(invoice_platform_context) -> None:
    inv = _create_vehicle_invoice(invoice_platform_context)
    ctx = invoice_platform_context
    vehicle_id = ctx["vehicle"].id
    ctx["set_user"](ctx["service_a"])
    listed = ctx["client"].get(f"/api/v1/vehicles/{vehicle_id}/documents")
    assert listed.status_code == 200
    items = listed.json()
    assert any(item.get("document_type") == "invoice" for item in items)

    ctx["set_user"](ctx["service_b"])
    foreign = ctx["client"].get(f"/api/v1/vehicles/{vehicle_id}/documents")
    assert foreign.status_code == 200
    assert not any(item.get("document_type") == "invoice" for item in foreign.json())

    doc_id = next(item["id"] for item in items if item["document_type"] == "invoice")
    ctx["set_user"](ctx["service_b"])
    file_resp = ctx["client"].get(f"/api/v1/vehicles/{vehicle_id}/documents/{doc_id}/file")
    assert file_resp.status_code == 403


def test_owner_does_not_see_service_private_invoice_document(invoice_platform_context) -> None:
    inv = _create_vehicle_invoice(invoice_platform_context)
    ctx = invoice_platform_context
    db = ctx["db"]
    vehicle_id = ctx["vehicle"].id
    ctx["set_user"](ctx["owner"])
    listed = ctx["client"].get(f"/api/v1/vehicles/{vehicle_id}/documents")
    assert listed.status_code == 200
    assert not any(item.get("document_type") == "invoice" for item in listed.json())

    from src.modules.vehicle_hub.documents.document_service import user_can_view_document

    doc = (
        db.query(VehicleDocument)
        .filter(VehicleDocument.source_id == int(inv["id"]))
        .first()
    )
    assert doc is not None
    assert user_can_view_document(db, current_user=ctx["owner"], doc=doc) is False


def test_public_verify_invoice_safe_no_pii(invoice_platform_context) -> None:
    inv = _create_vehicle_invoice(invoice_platform_context)
    db = invoice_platform_context["db"]
    doc = (
        db.query(VehicleDocument)
        .filter(VehicleDocument.source_id == int(inv["id"]))
        .first()
    )
    assert doc
    response = invoice_platform_context["client"].get(
        f"/api/public/documents/verify/{doc.verification_token}"
    )
    assert response.status_code == 200
    payload = response.json()
    blob = str(payload).lower()
    assert "owner@example.com" not in blob
    assert "vininvplat" not in blob
    assert payload.get("document_type") == "invoice"


def test_invoice_document_card_metadata(invoice_platform_context) -> None:
    inv = _create_vehicle_invoice(invoice_platform_context)
    ctx = invoice_platform_context
    ctx["set_user"](ctx["service_a"])
    detail = ctx["client"].get(f"/api/service/invoices/{inv['id']}")
    assert detail.status_code == 200
    body = detail.json()
    card = body.get("vehicle_document")
    assert card is not None
    assert card.get("document_type") == "invoice"
    assert card.get("label") == "Faktura"
    assert card.get("file_url")
    assert card.get("verify_url")
    assert "verify" in (card.get("actions") or [])
    assert body.get("vehicle_document_id")
    assert re.match(r"/api/v1/vehicles/\d+/documents/\d+/file", body.get("pdf_url") or "")
