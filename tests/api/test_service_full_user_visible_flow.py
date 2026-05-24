"""End-to-end servisní tok: žádost → schválení → záznam → km → přílohy → faktura → uživatel."""
from __future__ import annotations

import base64
import json
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.auth import get_current_user_email
from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import (
    Customer,
    GlobalAuditLog,
    ServiceCustomerLink,
    SystemNotification,
    Tenant,
    Vehicle,
    VehicleMileage,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub import schema_management as schema_management_mod
from src.modules.vehicle_hub.routers_v1 import services as services_router
from src.modules.vehicle_hub.routers_v1 import service_workspace as workspace_router
from src.modules.vehicle_hub.routers_v1 import vehicle_lifecycle as lifecycle_router
from src.modules.vehicle_hub.routers_v1 import service_records as records_router
from src.modules.vehicle_hub.routers_v1 import service_invoices as invoices_router
from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router
from src.modules.vehicle_hub.routers_v1 import admin_service_read as admin_read_router
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.server import admin_api as admin_api_module


def _tiny_png_b64() -> str:
    data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
        b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return base64.b64encode(data).decode("ascii")


@pytest.fixture()
def full_flow_ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(schema_management_mod, "assert_module_ready", lambda *a, **k: None)

    db_path = tmp_path / "full_flow.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="T-flow", license_key="lic-flow")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(
        tenant_id=tenant.id,
        email="owner.flow@example.com",
        password_hash="x",
        name="Owner Flow",
        role="user",
    )
    service = Customer(
        tenant_id=tenant.id,
        email="service.flow@example.com",
        password_hash="x",
        name="Service Flow",
        role="service",
    )
    other = Customer(
        tenant_id=tenant.id,
        email="other.flow@example.com",
        password_hash="x",
        name="Other User",
        role="user",
    )
    admin = Customer(
        tenant_id=tenant.id,
        email="admin.flow@example.com",
        password_hash="x",
        name="Admin Flow",
        role="developer_admin",
    )
    db.add_all([owner, service, other, admin])
    db.commit()
    db.refresh(owner)
    db.refresh(service)
    db.refresh(other)
    db.refresh(admin)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        brand="Test",
        model="Car",
        vin="TMB12345678901234",
        plate="PHFLOW1",
        current_mileage_km=10000,
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
            ownership_origin="manual",
            is_primary=True,
            is_active=True,
        )
    )
    db.add(
        ServiceCustomerLink(
            service_tenant_id=tenant.id,
            service_customer_id=service.id,
            customer_tenant_id=tenant.id,
            customer_id=owner.id,
            status="active",
        )
    )
    db.commit()

    app = FastAPI()
    app.include_router(services_router.router, prefix="/api/v1")
    app.include_router(workspace_router.router, prefix="/api/v1")
    app.include_router(lifecycle_router.router, prefix="/api/v1")
    app.include_router(records_router.router, prefix="/api/v1")
    app.include_router(invoices_router.router)
    app.include_router(vehicles_router.router, prefix="/api/v1")
    app.include_router(admin_read_router.router, prefix="/api/v1")
    app.include_router(admin_api_module.router)

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_email] = lambda: admin.email

    email_calls: list[dict] = []

    def capture_email(*, to_email: str, subject: str, plain_body: str) -> bool:
        email_calls.append({"to": to_email, "subject": subject, "body": plain_body})
        return True

    monkeypatch.setattr(
        "src.modules.vehicle_hub.service_access_messaging.send_service_access_request_email",
        capture_email,
    )

    def set_user(user: Customer):
        app.dependency_overrides[get_current_user] = lambda: user

    client = TestClient(app)
    try:
        yield {
            "db": db,
            "client": client,
            "set_user": set_user,
            "owner": owner,
            "service": service,
            "other": other,
            "admin": admin,
            "vehicle": vehicle,
            "tenant": tenant,
            "email_calls": email_calls,
        }
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def test_full_service_user_visible_flow(full_flow_ctx):
    ctx = full_flow_ctx
    db = ctx["db"]
    client = ctx["client"]
    owner = ctx["owner"]
    service = ctx["service"]
    other = ctx["other"]
    vehicle = ctx["vehicle"]

    ctx["set_user"](service)
    pre_rec = client.post(
        f"/api/v1/vehicles/{vehicle.id}/records",
        json={
            "performed_at": datetime.utcnow().isoformat(),
            "mileage": 50000,
            "description": "before link",
            "price": 1,
            "category": "SERVIS",
        },
    )
    assert pre_rec.status_code == 403

    r_req = client.post(
        "/api/v1/services/access-requests",
        json={"vehicle_id": vehicle.id, "lookup_query": vehicle.plate, "note": "Prosím přístup"},
    )
    assert r_req.status_code == 200, r_req.text
    rid = int(r_req.json()["request_id"])

    ncount = (
        db.query(SystemNotification)
        .filter(SystemNotification.target_type == "user", SystemNotification.target_value == str(owner.id))
        .count()
    )
    assert ncount >= 1
    assert len(ctx["email_calls"]) >= 1
    body_email = ctx["email_calls"][-1]["body"]
    assert "PHFLOW1" not in body_email and vehicle.vin not in body_email

    assert db.query(VehicleServiceLink).filter(VehicleServiceLink.vehicle_id == vehicle.id).count() == 0

    ctx["set_user"](owner)
    r_appr = client.put(f"/api/v1/services/access-requests/{rid}", json={"decision": "approved"})
    assert r_appr.status_code == 200, r_appr.text

    link = (
        db.query(VehicleServiceLink)
        .filter(
            VehicleServiceLink.vehicle_id == vehicle.id,
            VehicleServiceLink.service_customer_id == service.id,
            VehicleServiceLink.status == "approved",
        )
        .first()
    )
    assert link is not None
    aud_appr = (
        db.query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.action == "service_access_approved",
            GlobalAuditLog.entity_type == "vehicle_service_access",
            GlobalAuditLog.entity_id == int(link.id),
        )
        .first()
    )
    assert aud_appr is not None

    ctx["set_user"](service)
    r_create = client.post(
        f"/api/v1/vehicles/{vehicle.id}/records",
        json={
            "performed_at": datetime.utcnow().isoformat(),
            "mileage": 50500,
            "description": "Servisní zákrok",
            "price": 2000,
            "category": "SERVIS",
            "record_status": "submitted",
        },
    )
    assert r_create.status_code == 200, r_create.text
    rec_id = int(r_create.json()["id"])
    db.refresh(vehicle)
    assert vehicle.current_mileage_km == 50500
    assert (
        db.query(VehicleMileage)
        .filter(
            VehicleMileage.vehicle_id == vehicle.id,
            VehicleMileage.source == "service_record",
            VehicleMileage.service_record_id == rec_id,
        )
        .count()
        == 1
    )

    png = _tiny_png_b64()
    up_before = client.post(
        f"/api/v1/vehicles/{vehicle.id}/records/attachments/upload",
        json={
            "service_record_id": rec_id,
            "attachment_kind": "before_repair",
            "file_name": "b.png",
            "file_mime_type": "image/png",
            "file_content_base64": png,
        },
    )
    assert up_before.status_code == 200, up_before.text
    up_after = client.post(
        f"/api/v1/vehicles/{vehicle.id}/records/attachments/upload",
        json={
            "service_record_id": rec_id,
            "attachment_kind": "after_repair",
            "file_name": "a.png",
            "file_mime_type": "image/png",
            "file_content_base64": png,
        },
    )
    assert up_after.status_code == 200, up_after.text

    ctx["set_user"](owner)
    rec_list = client.get(f"/api/v1/vehicles/{vehicle.id}/records")
    assert rec_list.status_code == 200
    records = rec_list.json()
    target = next(x for x in records if int(x["id"]) == rec_id)
    raw_att = target.get("attachments")
    if isinstance(raw_att, str):
        att = json.loads(raw_att)
    else:
        att = raw_att or []
    kinds = {str(a.get("attachment_kind")) for a in att}
    assert "before_repair" in kinds and "after_repair" in kinds

    ctx["set_user"](other)
    assert client.get(f"/api/v1/vehicles/{vehicle.id}/records").status_code == 403

    ctx["set_user"](service)
    inv = client.post(
        "/api/service/invoices",
        json={
            "customer_id": owner.id,
            "vehicle_id": vehicle.id,
            "from_service_record": True,
            "service_record_id": rec_id,
            "lines": [
                {"description": "Práce", "quantity": 1, "unit": "ks", "unit_price": 1000, "tax_rate": 21},
            ],
        },
    )
    assert inv.status_code == 201, inv.text
    inv_id = int(inv.json()["id"])
    assert client.post(f"/api/service/invoices/{inv_id}/issue").status_code == 200

    ctx["set_user"](owner)
    li = client.get(f"/api/v1/vehicles/{vehicle.id}/invoices")
    assert li.status_code == 200
    items = li.json()["items"]
    assert any(int(x["id"]) == inv_id for x in items)
    pdf = client.get(f"/api/v1/vehicles/{vehicle.id}/invoices/{inv_id}/pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")

    assert (
        db.query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.entity_type == "service_invoice",
            GlobalAuditLog.entity_id == inv_id,
            GlobalAuditLog.action == "service_invoice_user_pdf_download",
        )
        .first()
    )

    ctx["set_user"](other)
    assert client.get(f"/api/v1/vehicles/{vehicle.id}/invoices").status_code == 403

    ctx["set_user"](ctx["admin"])
    assert client.get("/api/v1/admin/service-read/access-requests").status_code == 200
    assert client.get("/api/v1/admin/service-read/vehicle-service-links").status_code == 200
    assert client.get("/api/v1/admin/service-read/service-invoices").status_code == 200
    assert client.get("/api/v1/admin/service-read/service-records").status_code == 200

    api_inv = client.get(f"/admin-api/service-invoices?vehicle_id={vehicle.id}&status=issued")
    assert api_inv.status_code == 200, api_inv.text
    inv_payload = api_inv.json()
    assert inv_payload.get("total", 0) >= 1
    assert any(int(x.get("invoice_id", 0)) == inv_id for x in inv_payload.get("items", []))

    assert db.query(GlobalAuditLog).filter(GlobalAuditLog.action == "service_record_create").count() >= 1


def test_smtp_failure_does_not_block_access_request(full_flow_ctx, monkeypatch):
    ctx = full_flow_ctx
    client = ctx["client"]
    vehicle = ctx["vehicle"]
    service = ctx["service"]

    def boom(**_kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(
        "src.modules.vehicle_hub.service_access_messaging.send_service_access_request_email",
        boom,
    )
    ctx["set_user"](service)
    r = client.post(
        "/api/v1/services/access-requests",
        json={"vehicle_id": vehicle.id, "lookup_query": vehicle.plate},
    )
    assert r.status_code == 200, r.text
    rid = int(r.json()["request_id"])
    row = (
        ctx["db"]
        .query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.entity_type == "service_access_request",
            GlobalAuditLog.entity_id == rid,
            GlobalAuditLog.action == "service_access_request_email_failed",
        )
        .first()
    )
    assert row is not None
