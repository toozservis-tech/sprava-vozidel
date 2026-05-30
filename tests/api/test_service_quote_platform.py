"""C1.2 — platform quote documents (VehicleDocument + renderer)."""
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
from src.modules.vehicle_hub.routers_v1 import service_dashboard as service_dashboard_router
from src.modules.vehicle_hub.routers_v1 import service_invoices as service_invoices_router
from src.modules.vehicle_hub.routers_v1 import vehicle_documents as vehicle_documents_router
from src.server.routers import public_documents as public_documents_router


def _make_app(db):
    app = FastAPI()
    app.include_router(service_dashboard_router.router)
    app.include_router(service_invoices_router.router)
    app.include_router(vehicle_documents_router.router, prefix="/api/v1")
    app.include_router(public_documents_router.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[service_dashboard_router.get_db] = override_get_db
    app.dependency_overrides[service_invoices_router.get_db] = override_get_db
    app.dependency_overrides[vehicle_documents_router.get_db] = override_get_db
    app.dependency_overrides[public_documents_router.get_db] = override_get_db
    return app


@pytest.fixture()
def quote_platform_context(tmp_path: Path, monkeypatch):
    docs_root = tmp_path / "vehicle_documents"
    docs_root.mkdir(parents=True, exist_ok=True)
    for target in (
        "src.modules.vehicle_hub.documents.document_service.VEHICLE_DOCUMENTS_ROOT",
        "src.modules.vehicle_hub.documents.document_storage.VEHICLE_DOCUMENTS_ROOT",
        "src.modules.vehicle_hub.documents.invoice_sync.VEHICLE_DOCUMENTS_ROOT",
        "src.modules.vehicle_hub.documents.quote_sync.VEHICLE_DOCUMENTS_ROOT",
    ):
        monkeypatch.setattr(target, docs_root)

    db_path = tmp_path / "quote_platform.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="Quote Platform Tenant", license_key="quote-platform-key")
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
        vin="VINQUOTEPLAT12345",
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

    def set_user(user: Customer):
        from src.modules.vehicle_hub.routers_v1 import auth as auth_module

        app.dependency_overrides[auth_module.get_current_user] = lambda: user
        app.dependency_overrides[service_dashboard_router.get_current_user] = lambda: user
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


QUOTE_ITEM = {"name": "Výměna oleje", "quantity": 1, "unit_price": 1000}


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _create_vehicle_quote(ctx, *, status: str = "sent") -> dict:
    ctx["set_user"](ctx["service_a"])
    created = ctx["client"].post(
        "/api/service/quotes",
        json={
            "vehicle_id": ctx["vehicle"].id,
            "customer_id": ctx["owner"].id,
            "items": [QUOTE_ITEM],
            "status": status,
        },
    )
    assert created.status_code == 200, created.text
    return created.json()


def test_service_quote_pdf_uses_platform_renderer(quote_platform_context) -> None:
    quote = _create_vehicle_quote(quote_platform_context)
    ctx = quote_platform_context
    ctx["set_user"](ctx["service_a"])
    response = ctx["client"].get(f"/api/service/quotes/{quote['id']}/pdf")
    assert response.status_code == 200
    body = response.content
    assert body.startswith(b"%PDF")
    assert len(body) > 4096
    text = _pdf_text(body)
    assert "NABÍDKA" in text
    assert "Document Platform" in text


def test_service_quote_creates_vehicle_document(quote_platform_context) -> None:
    quote = _create_vehicle_quote(quote_platform_context)
    db = quote_platform_context["db"]
    doc = (
        db.query(VehicleDocument)
        .filter(
            VehicleDocument.source_type == "service_quote",
            VehicleDocument.source_id == int(quote["id"]),
        )
        .first()
    )
    assert doc is not None
    assert doc.document_type == "quote"
    assert int(doc.vehicle_id) == int(quote_platform_context["vehicle"].id)
    assert doc.visibility_scope == "service_private"
    assert doc.verification_token


def test_service_quote_vehicle_document_no_duplicates(quote_platform_context) -> None:
    quote = _create_vehicle_quote(quote_platform_context)
    ctx = quote_platform_context
    ctx["set_user"](ctx["service_a"])
    ctx["client"].get(f"/api/service/quotes/{quote['id']}/pdf")
    ctx["client"].put(
        f"/api/service/quotes/{quote['id']}",
        json={"status": "approved", "items": [QUOTE_ITEM], "total_price": 1000},
    )
    ctx["client"].get(f"/api/service/quotes/{quote['id']}/pdf")
    rows = (
        ctx["db"]
        .query(VehicleDocument)
        .filter(
            VehicleDocument.source_type == "service_quote",
            VehicleDocument.source_id == int(quote["id"]),
        )
        .all()
    )
    assert len(rows) == 1


def test_service_quote_pdf_contains_quote_number(quote_platform_context) -> None:
    quote = _create_vehicle_quote(quote_platform_context)
    ctx = quote_platform_context
    ctx["set_user"](ctx["service_a"])
    pdf = ctx["client"].get(f"/api/service/quotes/{quote['id']}/pdf").content
    number = f"NAB-{int(quote['id']):05d}"
    assert number in _pdf_text(pdf)


def test_service_quote_pdf_contains_vehicle(quote_platform_context) -> None:
    quote = _create_vehicle_quote(quote_platform_context)
    ctx = quote_platform_context
    ctx["set_user"](ctx["service_a"])
    text = _pdf_text(ctx["client"].get(f"/api/service/quotes/{quote['id']}/pdf").content)
    assert "Octavia" in text or "1AB2345" in text or "Skoda" in text


def test_service_quote_pdf_contains_qr_verify(quote_platform_context) -> None:
    quote = _create_vehicle_quote(quote_platform_context)
    db = quote_platform_context["db"]
    doc = (
        db.query(VehicleDocument)
        .filter(VehicleDocument.source_id == int(quote["id"]))
        .first()
    )
    assert doc and doc.verification_token
    ctx = quote_platform_context
    ctx["set_user"](ctx["service_a"])
    text = _pdf_text(ctx["client"].get(f"/api/service/quotes/{quote['id']}/pdf").content)
    assert "Ověření dokumentu" in text or doc.verification_token in text


def test_service_quote_pdf_is_not_text_export(quote_platform_context) -> None:
    quote = _create_vehicle_quote(quote_platform_context)
    ctx = quote_platform_context
    ctx["set_user"](ctx["service_a"])
    pdf = ctx["client"].get(f"/api/service/quotes/{quote['id']}/pdf").content
    text = _pdf_text(pdf)
    assert len(pdf) > 8000
    assert "NABÍDKA" in text
    assert "Document Platform" in text
    assert "Položky" in text


def test_service_quote_document_scoped_to_service(quote_platform_context) -> None:
    quote = _create_vehicle_quote(quote_platform_context)
    ctx = quote_platform_context
    vehicle_id = ctx["vehicle"].id
    ctx["set_user"](ctx["service_a"])
    items = ctx["client"].get(f"/api/v1/vehicles/{vehicle_id}/documents").json()
    assert any(item.get("document_type") == "quote" for item in items)

    ctx["set_user"](ctx["service_b"])
    foreign = ctx["client"].get(f"/api/v1/vehicles/{vehicle_id}/documents").json()
    assert not any(item.get("document_type") == "quote" for item in foreign)

    doc_id = next(item["id"] for item in items if item["document_type"] == "quote")
    ctx["set_user"](ctx["service_b"])
    assert ctx["client"].get(f"/api/v1/vehicles/{vehicle_id}/documents/{doc_id}/file").status_code == 403


def test_owner_does_not_see_service_private_quote_document(quote_platform_context) -> None:
    quote = _create_vehicle_quote(quote_platform_context)
    ctx = quote_platform_context
    db = ctx["db"]
    vehicle_id = ctx["vehicle"].id
    ctx["set_user"](ctx["owner"])
    listed = ctx["client"].get(f"/api/v1/vehicles/{vehicle_id}/documents")
    assert listed.status_code == 200
    assert not any(item.get("document_type") == "quote" for item in listed.json())

    from src.modules.vehicle_hub.documents.document_service import user_can_view_document

    doc = (
        db.query(VehicleDocument)
        .filter(VehicleDocument.source_id == int(quote["id"]))
        .first()
    )
    assert doc is not None
    assert user_can_view_document(db, current_user=ctx["owner"], doc=doc) is False


def test_public_verify_quote_safe_no_pii(quote_platform_context) -> None:
    quote = _create_vehicle_quote(quote_platform_context)
    db = quote_platform_context["db"]
    doc = (
        db.query(VehicleDocument)
        .filter(VehicleDocument.source_id == int(quote["id"]))
        .first()
    )
    assert doc
    response = quote_platform_context["client"].get(
        f"/api/public/documents/verify/{doc.verification_token}"
    )
    assert response.status_code == 200
    payload = response.json()
    blob = str(payload).lower()
    assert "owner@example.com" not in blob
    assert "vinquoteplat" not in blob
    assert payload.get("document_type") == "quote"


def test_quote_document_card_metadata(quote_platform_context) -> None:
    quote = _create_vehicle_quote(quote_platform_context)
    ctx = quote_platform_context
    ctx["set_user"](ctx["service_a"])
    detail = ctx["client"].get(f"/api/service/quotes/{quote['id']}")
    assert detail.status_code == 200
    body = detail.json()
    card = body.get("vehicle_document")
    assert card is not None
    assert card.get("document_type") == "quote"
    assert card.get("label") == "Nabídka"
    assert card.get("file_url")
    assert card.get("verify_url")
    assert "verify" in (card.get("actions") or [])
    assert body.get("vehicle_document_id")
    assert re.match(r"/api/v1/vehicles/\d+/documents/\d+/file", body.get("pdf_url") or "")


def test_invoice_from_quote_still_works_after_platform_quote(quote_platform_context) -> None:
    quote = _create_vehicle_quote(quote_platform_context)
    ctx = quote_platform_context
    ctx["set_user"](ctx["service_a"])
    invoice_resp = ctx["client"].post(
        f"/api/service/invoices/from-quote/{quote['id']}",
        json={"tax_rate": 21},
    )
    assert invoice_resp.status_code == 201, invoice_resp.text
    inv = invoice_resp.json()
    assert inv.get("id")
    assert inv.get("vehicle_id") == ctx["vehicle"].id

    issued = ctx["client"].post(f"/api/service/invoices/{inv['id']}/issue")
    assert issued.status_code == 200, issued.text

    doc = (
        ctx["db"]
        .query(VehicleDocument)
        .filter(
            VehicleDocument.source_type == "service_invoice",
            VehicleDocument.source_id == int(inv["id"]),
        )
        .first()
    )
    assert doc is not None
