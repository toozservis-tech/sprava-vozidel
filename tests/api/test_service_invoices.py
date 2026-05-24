"""API testy: servisní faktury (Fáze 1)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    GlobalAuditLog,
    ServiceCustomerLink,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.routers_v1 import service_invoices as service_invoices_router


def _make_app(db):
    app = FastAPI()
    app.include_router(service_invoices_router.router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[service_invoices_router.get_db] = override_get_db
    return app


@pytest.fixture()
def invoice_context(tmp_path: Path):
    db_path = tmp_path / "service_invoices.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="Inv Tenant", license_key="inv-tenant-key")
    tenant_b = Tenant(name="Other Tenant", license_key="inv-tenant-b-key")
    db.add_all([tenant, tenant_b])
    db.commit()
    db.refresh(tenant)
    db.refresh(tenant_b)

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
    stranger = Customer(
        tenant_id=tenant.id,
        email="stranger@example.com",
        name="Cizí zákazník",
        role="user",
    )
    service_other_tenant = Customer(
        tenant_id=tenant_b.id,
        email="service-other@example.com",
        name="Servis jiný tenant",
        role="service",
    )
    db.add_all([service_a, service_b, owner, stranger, service_other_tenant])
    db.commit()
    for c in (service_a, service_b, owner, stranger, service_other_tenant):
        db.refresh(c)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        brand="Skoda",
        model="Octavia",
        vin="VININV12345678901",
        plate="1AB2345",
        stk_valid_until=date(2030, 1, 1),
    )
    vehicle_no_access = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        brand="Skoda",
        model="Fabia",
        vin="VINNOACCESS123456",
        plate="2CD3456",
        stk_valid_until=date(2030, 1, 1),
    )
    db.add_all([vehicle, vehicle_no_access])
    db.commit()
    db.refresh(vehicle)
    db.refresh(vehicle_no_access)

    for vid, primary in ((vehicle.id, True), (vehicle_no_access.id, False)):
        db.add(
            VehicleOwnership(
                tenant_id=tenant.id,
                vehicle_id=vid,
                customer_id=owner.id,
                ownership_type="owner",
                ownership_origin="manual",
                is_primary=primary,
                is_active=True,
            )
        )

    for svc in (service_a, service_b):
        db.add(
            ServiceCustomerLink(
                service_tenant_id=tenant.id,
                service_customer_id=svc.id,
                customer_tenant_id=tenant.id,
                customer_id=owner.id,
                status="active",
            )
        )
    db.add(
        ServiceCustomerLink(
            service_tenant_id=tenant.id,
            service_customer_id=service_a.id,
            customer_tenant_id=tenant.id,
            customer_id=stranger.id,
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
        app.dependency_overrides[service_invoices_router.get_current_user] = lambda: user

    client = TestClient(app)
    try:
        yield {
            "db": db,
            "client": client,
            "app": app,
            "set_user": set_user,
            "tenant": tenant,
            "tenant_b": tenant_b,
            "service_a": service_a,
            "service_b": service_b,
            "service_other_tenant": service_other_tenant,
            "owner": owner,
            "stranger": stranger,
            "vehicle": vehicle,
            "vehicle_no_access": vehicle_no_access,
        }
    finally:
        db.close()
        engine.dispose()


LINE = {
    "description": "Výměna oleje",
    "quantity": 1,
    "unit": "ks",
    "unit_price": 1000,
    "tax_rate": 21,
}


def test_a_create_draft_invoice(invoice_context) -> None:
    ctx = invoice_context
    ctx["set_user"](ctx["service_a"])
    r = ctx["client"].post(
        "/api/service/invoices",
        json={
            "customer_id": ctx["owner"].id,
            "vehicle_id": ctx["vehicle"].id,
            "lines": [LINE],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "draft"
    assert body["invoice_number"] is None
    assert body["service_id"] == ctx["service_a"].id
    assert body["tenant_id"] == ctx["tenant"].id
    assert body["customer_id"] == ctx["owner"].id
    assert body["customer_label"] == ctx["owner"].name
    assert "Octavia" in str(body["vehicle_label"] or "")
    assert float(body["total"]) > 0
    row = (
        ctx["db"]
        .query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.entity_type == "service_invoice",
            GlobalAuditLog.entity_id == int(body["id"]),
            GlobalAuditLog.action == "invoice_created",
        )
        .first()
    )
    assert row is not None


def test_b_unauthorized_customer_forbidden(invoice_context) -> None:
    """403 až po validním payloadu: vehicle_id + lines, ale servis bez aktivní vazby na zákazníka."""
    ctx = invoice_context
    ctx["set_user"](ctx["service_b"])
    r = ctx["client"].post(
        "/api/service/invoices",
        json={
            "customer_id": ctx["stranger"].id,
            "vehicle_id": ctx["vehicle"].id,
            "lines": [LINE],
        },
    )
    assert r.status_code == 403, r.text


def test_c_foreign_vehicle_no_approved_link_forbidden(invoice_context) -> None:
    ctx = invoice_context
    ctx["set_user"](ctx["service_a"])
    r = ctx["client"].post(
        "/api/service/invoices",
        json={
            "customer_id": ctx["owner"].id,
            "vehicle_id": ctx["vehicle_no_access"].id,
            "lines": [LINE],
        },
    )
    assert r.status_code == 403


def test_d_issue_assigns_number_and_audits(invoice_context) -> None:
    ctx = invoice_context
    ctx["set_user"](ctx["service_a"])
    c = ctx["client"]
    created = c.post(
        "/api/service/invoices",
        json={"customer_id": ctx["owner"].id, "vehicle_id": ctx["vehicle"].id, "lines": [LINE]},
    )
    assert created.status_code == 201
    inv_id = created.json()["id"]
    r = c.post(f"/api/service/invoices/{inv_id}/issue")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "issued"
    assert body["invoice_number"]
    assert body["invoice_number"].startswith("FV-")
    row = (
        ctx["db"]
        .query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.entity_type == "service_invoice",
            GlobalAuditLog.entity_id == int(inv_id),
            GlobalAuditLog.action == "invoice_issued",
        )
        .order_by(GlobalAuditLog.id.desc())
        .first()
    )
    assert row is not None


def test_e_cancel_audits(invoice_context) -> None:
    ctx = invoice_context
    ctx["set_user"](ctx["service_a"])
    c = ctx["client"]
    created = c.post(
        "/api/service/invoices",
        json={
            "customer_id": ctx["owner"].id,
            "vehicle_id": ctx["vehicle"].id,
            "lines": [LINE],
        },
    )
    assert created.status_code == 201, created.text
    inv_id = created.json()["id"]
    r = c.post(f"/api/service/invoices/{inv_id}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"
    row = (
        ctx["db"]
        .query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.entity_type == "service_invoice",
            GlobalAuditLog.entity_id == int(inv_id),
            GlobalAuditLog.action == "invoice_cancelled",
        )
        .first()
    )
    assert row is not None


def test_cancel_issued_invoice_allowed(invoice_context) -> None:
    ctx = invoice_context
    ctx["set_user"](ctx["service_a"])
    c = ctx["client"]
    created = c.post(
        "/api/service/invoices",
        json={
            "customer_id": ctx["owner"].id,
            "vehicle_id": ctx["vehicle"].id,
            "lines": [LINE],
        },
    )
    assert created.status_code == 201, created.text
    inv_id = created.json()["id"]
    assert c.post(f"/api/service/invoices/{inv_id}/issue").status_code == 200
    r = c.post(f"/api/service/invoices/{inv_id}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_f_pdf_export_200(invoice_context) -> None:
    ctx = invoice_context
    ctx["set_user"](ctx["service_a"])
    c = ctx["client"]
    created = c.post(
        "/api/service/invoices",
        json={
            "customer_id": ctx["owner"].id,
            "vehicle_id": ctx["vehicle"].id,
            "lines": [LINE],
        },
    )
    assert created.status_code == 201, created.text
    inv_id = created.json()["id"]
    r = c.get(f"/api/service/invoices/{inv_id}/pdf")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF")
    row = (
        ctx["db"]
        .query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.entity_type == "service_invoice",
            GlobalAuditLog.entity_id == int(inv_id),
            GlobalAuditLog.action == "invoice_pdf_exported",
        )
        .order_by(GlobalAuditLog.id.desc())
        .first()
    )
    assert row is not None


def test_g_cross_tenant_access_forbidden(invoice_context) -> None:
    ctx = invoice_context
    ctx["set_user"](ctx["service_a"])
    c = ctx["client"]
    created = c.post(
        "/api/service/invoices",
        json={
            "customer_id": ctx["owner"].id,
            "vehicle_id": ctx["vehicle"].id,
            "lines": [LINE],
        },
    )
    assert created.status_code == 201, created.text
    inv_id = created.json()["id"]
    ctx["set_user"](ctx["service_other_tenant"])
    r = c.get(f"/api/service/invoices/{inv_id}")
    assert r.status_code == 404


def test_h_list_scoped_to_current_service(invoice_context) -> None:
    ctx = invoice_context
    ctx["set_user"](ctx["service_a"])
    c = ctx["client"]
    r1 = c.post(
        "/api/service/invoices",
        json={
            "customer_id": ctx["owner"].id,
            "vehicle_id": ctx["vehicle"].id,
            "lines": [LINE],
        },
    )
    assert r1.status_code == 201, r1.text
    inv_id_a = r1.json()["id"]

    ctx["set_user"](ctx["service_b"])
    r2 = c.post(
        "/api/service/invoices",
        json={
            "customer_id": ctx["owner"].id,
            "vehicle_id": ctx["vehicle"].id,
            "lines": [LINE],
        },
    )
    assert r2.status_code == 201, r2.text
    inv_id_b = r2.json()["id"]

    lst_b = c.get("/api/service/invoices")
    assert lst_b.status_code == 200
    ids_b = {int(x["id"]) for x in lst_b.json()["items"]}
    assert inv_id_b in ids_b
    assert inv_id_a not in ids_b


def test_non_service_role_forbidden(invoice_context) -> None:
    ctx = invoice_context
    ctx["set_user"](ctx["owner"])
    r = ctx["client"].post(
        "/api/service/invoices",
        json={
            "customer_id": ctx["owner"].id,
            "vehicle_id": ctx["vehicle"].id,
            "lines": [LINE],
        },
    )
    assert r.status_code == 403, r.text


def test_create_non_vehicle_invoice_explicit_flag(invoice_context) -> None:
    """Ruční koncept bez vozidla: non_vehicle_invoice=true, bez vehicle_id."""
    ctx = invoice_context
    ctx["set_user"](ctx["service_a"])
    r = ctx["client"].post(
        "/api/service/invoices",
        json={
            "customer_id": ctx["owner"].id,
            "non_vehicle_invoice": True,
            "lines": [LINE],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["vehicle_id"] is None
    assert body.get("extra", {}).get("manual_non_vehicle_invoice") is True
