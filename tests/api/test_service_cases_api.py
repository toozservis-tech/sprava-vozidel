"""PR 1: /api/v1/services/workspace/service-cases — ServiceIntake fasáda."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import (
    Customer,
    GlobalAuditLog,
    ServiceIntake,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub import schema_management as schema_management_mod
from src.modules.vehicle_hub.routers_v1 import service_workspace_cases as cases_router
from src.modules.vehicle_hub.routers_v1.auth import get_current_user


@pytest.fixture()
def cases_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(schema_management_mod, "assert_module_ready", lambda *a, **k: None)

    db_path = tmp_path / "cases.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="T-cases", license_key="lic-cases")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    def mk_service(email: str, name: str) -> Customer:
        s = Customer(
            tenant_id=tenant.id,
            email=email,
            password_hash="x",
            name=name,
            role="service",
        )
        db.add(s)
        db.commit()
        db.refresh(s)
        return s

    def mk_owner(email: str) -> Customer:
        o = Customer(
            tenant_id=tenant.id,
            email=email,
            password_hash="x",
            name="Owner",
            role="user",
        )
        db.add(o)
        db.commit()
        db.refresh(o)
        return o

    svc_a = mk_service("svc.a@example.com", "Servis A")
    svc_b = mk_service("svc.b@example.com", "Servis B")
    owner_a = mk_owner("owner.a@example.com")
    owner_b = mk_owner("owner.b@example.com")

    def mk_vehicle(*, plate: str, owner: Customer) -> Vehicle:
        v = Vehicle(
            tenant_id=tenant.id,
            user_email=owner.email,
            nickname="Car",
            plate=plate,
            vin=f"VIN{plate}",
            brand="Škoda",
            model="Octavia",
            current_mileage_km=150_000,
        )
        db.add(v)
        db.commit()
        db.refresh(v)
        db.add(
            VehicleOwnership(
                tenant_id=tenant.id,
                vehicle_id=v.id,
                customer_id=owner.id,
                ownership_type="owner",
                ownership_origin="manual",
                is_primary=True,
                is_active=True,
            )
        )
        db.commit()
        return v

    v_a = mk_vehicle(plate="1A1111", owner=owner_a)
    v_b = mk_vehicle(plate="2B2222", owner=owner_b)

    def link_service_vehicle(service: Customer, owner: Customer, vehicle: Vehicle) -> VehicleServiceLink:
        ln = VehicleServiceLink(
            tenant_id=tenant.id,
            service_customer_id=service.id,
            owner_customer_id=owner.id,
            vehicle_id=vehicle.id,
            status="approved",
            approved_at=__import__("datetime").datetime.utcnow(),
            approved_by_customer_id=owner.id,
        )
        db.add(ln)
        db.commit()
        db.refresh(ln)
        return ln

    link_a = link_service_vehicle(svc_a, owner_a, v_a)
    link_b = link_service_vehicle(svc_b, owner_b, v_b)

    app = FastAPI()
    app.include_router(cases_router.router, prefix="/api/v1")

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db

    def set_user(u: Customer):
        app.dependency_overrides[get_current_user] = lambda: u

    client = TestClient(app)
    try:
        yield {
            "client": client,
            "db": db,
            "set_user": set_user,
            "svc_a": svc_a,
            "svc_b": svc_b,
            "v_a": v_a,
            "v_b": v_b,
            "link_a": link_a,
            "link_b": link_b,
            "owner_a": owner_a,
            "owner_b": owner_b,
            "tenant": tenant,
        }
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def test_user_cannot_create_case(cases_ctx):
    ctx = cases_ctx
    db = ctx["db"]
    u = Customer(
        tenant_id=ctx["tenant"].id,
        email="plain@example.com",
        password_hash="x",
        name="User",
        role="user",
    )
    db.add(u)
    db.commit()
    ctx["set_user"](u)
    r = ctx["client"].post(
        "/api/v1/services/workspace/service-cases/",
        json={"vehicle_id": ctx["v_a"].id, "customer_request": "x"},
    )
    assert r.status_code == 403


def test_service_with_work_access_can_create_case(cases_ctx):
    ctx = cases_ctx
    from src.modules.vehicle_hub.models import ServiceWorkAccess

    db = ctx["db"]
    db.add(
        ServiceWorkAccess(
            tenant_id=ctx["tenant"].id,
            service_customer_id=ctx["svc_a"].id,
            vehicle_id=ctx["v_b"].id,
            status="active",
            reason="Jednorázový zásah",
            source="intake",
        )
    )
    db.commit()
    ctx["set_user"](ctx["svc_a"])
    r = ctx["client"].post(
        "/api/v1/services/workspace/service-cases/",
        json={"vehicle_id": ctx["v_b"].id, "customer_request": "Bez linku, s work access"},
    )
    assert r.status_code == 201, r.text


def test_service_without_link_cannot_create_case(cases_ctx):
    ctx = cases_ctx
    db = ctx["db"]
    # servis A bez linku k v_b
    ctx["set_user"](ctx["svc_a"])
    r = ctx["client"].post(
        "/api/v1/services/workspace/service-cases/",
        json={"vehicle_id": ctx["v_b"].id, "customer_request": "x"},
    )
    assert r.status_code == 403


def test_service_with_link_creates_case_and_audit(cases_ctx):
    ctx = cases_ctx
    ctx["set_user"](ctx["svc_a"])
    r = ctx["client"].post(
        "/api/v1/services/workspace/service-cases/",
        json={
            "vehicle_id": ctx["v_a"].id,
            "customer_request": "Výměna oleje",
            "intake_note": "Poznámka",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["vehicle_id"] == ctx["v_a"].id
    assert data["service_customer_id"] == ctx["svc_a"].id
    assert data["customer_request"] == "Výměna oleje"
    case_id = int(data["id"])
    row = ctx["db"].query(ServiceIntake).filter(ServiceIntake.id == case_id).first()
    assert row is not None
    assert row.intake_source == "service_cases_api"
    aud = (
        ctx["db"]
        .query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.action == "SERVICE_CASE_CREATED",
            GlobalAuditLog.entity_id == case_id,
        )
        .first()
    )
    assert aud is not None


def test_list_only_own_cases(cases_ctx):
    ctx = cases_ctx
    db = ctx["db"]

    c1 = ServiceIntake(
        tenant_id=ctx["tenant"].id,
        service_id=ctx["svc_a"].id,
        vehicle_id=ctx["v_a"].id,
        customer_id=ctx["owner_a"].id,
        service_access_link_id=ctx["link_a"].id,
        intake_status="intake_started",
        intake_source="service_cases_api",
        owner_approval_required=False,
        owner_approval_status="approved",
    )
    c2 = ServiceIntake(
        tenant_id=ctx["tenant"].id,
        service_id=ctx["svc_b"].id,
        vehicle_id=ctx["v_b"].id,
        customer_id=ctx["owner_b"].id,
        service_access_link_id=ctx["link_b"].id,
        intake_status="draft",
        intake_source="service_cases_api",
        owner_approval_required=False,
        owner_approval_status="approved",
    )
    db.add_all([c1, c2])
    db.commit()

    ctx["set_user"](ctx["svc_a"])
    r = ctx["client"].get("/api/v1/services/workspace/service-cases/")
    assert r.status_code == 200
    items = r.json()["items"]
    ids = {i["id"] for i in items}
    assert c1.id in ids
    assert c2.id not in ids


def test_get_own_detail_with_vehicle(cases_ctx):
    ctx = cases_ctx
    db = ctx["db"]
    c1 = ServiceIntake(
        tenant_id=ctx["tenant"].id,
        service_id=ctx["svc_a"].id,
        vehicle_id=ctx["v_a"].id,
        customer_id=ctx["owner_a"].id,
        service_access_link_id=ctx["link_a"].id,
        intake_status="intake_started",
        intake_source="service_cases_api",
        owner_approval_required=False,
        owner_approval_status="approved",
    )
    db.add(c1)
    db.commit()
    db.refresh(c1)
    ctx["set_user"](ctx["svc_a"])
    r = ctx["client"].get(f"/api/v1/services/workspace/service-cases/{c1.id}")
    assert r.status_code == 200
    d = r.json()
    assert "vehicle" in d
    assert d["vehicle"]["plate"] == ctx["v_a"].plate
    assert "internal_note" not in d


def test_other_service_get_detail_404(cases_ctx):
    ctx = cases_ctx
    db = ctx["db"]
    c1 = ServiceIntake(
        tenant_id=ctx["tenant"].id,
        service_id=ctx["svc_a"].id,
        vehicle_id=ctx["v_a"].id,
        customer_id=ctx["owner_a"].id,
        service_access_link_id=ctx["link_a"].id,
        intake_status="intake_started",
        intake_source="service_cases_api",
        owner_approval_required=False,
        owner_approval_status="approved",
    )
    db.add(c1)
    db.commit()
    db.refresh(c1)
    ctx["set_user"](ctx["svc_b"])
    r = ctx["client"].get(f"/api/v1/services/workspace/service-cases/{c1.id}")
    assert r.status_code == 404


def test_patch_own_case(cases_ctx):
    ctx = cases_ctx
    db = ctx["db"]
    c1 = ServiceIntake(
        tenant_id=ctx["tenant"].id,
        service_id=ctx["svc_a"].id,
        vehicle_id=ctx["v_a"].id,
        customer_id=ctx["owner_a"].id,
        service_access_link_id=ctx["link_a"].id,
        intake_status="intake_started",
        intake_source="service_cases_api",
        owner_approval_required=False,
        owner_approval_status="approved",
    )
    db.add(c1)
    db.commit()
    db.refresh(c1)
    ctx["set_user"](ctx["svc_a"])
    r = ctx["client"].patch(
        f"/api/v1/services/workspace/service-cases/{c1.id}",
        json={"customer_request": "Upraveno", "intake_note": "IN"},
    )
    assert r.status_code == 200
    db.refresh(c1)
    assert c1.customer_request == "Upraveno"
    assert c1.intake_note == "IN"
    aud = (
        db.query(GlobalAuditLog)
        .filter(GlobalAuditLog.action == "SERVICE_CASE_UPDATED", GlobalAuditLog.entity_id == c1.id)
        .order_by(GlobalAuditLog.id.desc())
        .first()
    )
    assert aud is not None


def test_patch_invalid_status_422(cases_ctx):
    ctx = cases_ctx
    db = ctx["db"]
    c1 = ServiceIntake(
        tenant_id=ctx["tenant"].id,
        service_id=ctx["svc_a"].id,
        vehicle_id=ctx["v_a"].id,
        customer_id=ctx["owner_a"].id,
        service_access_link_id=ctx["link_a"].id,
        intake_status="intake_started",
        intake_source="service_cases_api",
        owner_approval_required=False,
        owner_approval_status="approved",
    )
    db.add(c1)
    db.commit()
    db.refresh(c1)
    ctx["set_user"](ctx["svc_a"])
    r = ctx["client"].patch(
        f"/api/v1/services/workspace/service-cases/{c1.id}",
        json={"status": "work_in_progress"},
    )
    assert r.status_code == 422


def test_initial_mileage_does_not_update_vehicle(cases_ctx):
    ctx = cases_ctx
    ctx["set_user"](ctx["svc_a"])
    before = ctx["v_a"].current_mileage_km
    r = ctx["client"].post(
        "/api/v1/services/workspace/service-cases/",
        json={"vehicle_id": ctx["v_a"].id, "initial_mileage_km": 151_234},
    )
    assert r.status_code == 201, r.text
    assert r.json()["mileage_in"] == 151_234
    ctx["db"].refresh(ctx["v_a"])
    assert ctx["v_a"].current_mileage_km == before
