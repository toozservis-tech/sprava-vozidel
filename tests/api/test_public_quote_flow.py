from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, ServiceQuote, ServiceWorkOrder, Tenant, Vehicle
from src.modules.vehicle_hub.quote_public_access import ensure_quote_access_token
from src.modules.vehicle_hub.routers_v1 import service_dashboard as service_dashboard_module
from src.server.routers.public_quote import approve_public_quote, get_public_quote, reject_public_quote


@pytest.fixture()
def db_context(tmp_path: Path):
    db_path = tmp_path / "public_quote.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        tenant = Tenant(name="Quote Tenant", license_key="quote-public-key")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        service = Customer(
            tenant_id=tenant.id,
            email="service@example.com",
            name="ToozServis",
            ico="12345678",
            role="service",
        )
        owner = Customer(
            tenant_id=tenant.id,
            email="owner@example.com",
            name="Owner Person",
            phone="+420111222333",
            role="user",
        )
        db.add_all([service, owner])
        db.commit()
        db.refresh(service)
        db.refresh(owner)

        vehicle = Vehicle(
            tenant_id=tenant.id,
            user_email=owner.email,
            brand="Skoda",
            model="Octavia",
            plate="1AB2345",
            vin="VINPUBLICQUOTE1234",
            stk_valid_until=date(2030, 1, 1),
        )
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)

        work_order = ServiceWorkOrder(
            tenant_id=tenant.id,
            service_customer_id=service.id,
            owner_customer_id=owner.id,
            vehicle_id=vehicle.id,
            technician_id=service.id,
            source_type="manual",
            title="Servisní práce",
            status="awaiting_client_approval",
        )
        db.add(work_order)
        db.commit()
        db.refresh(work_order)

        quote = ServiceQuote(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            service_id=service.id,
            work_order_id=work_order.id,
            items_json='[{"name":"Výměna oleje","quantity":1,"unit_price":3490,"total_price":3490}]',
            labor_hours=1.5,
            labor_rate=890,
            total_price=3490,
            status="sent",
        )
        db.add(quote)
        db.flush()
        token = ensure_quote_access_token(db, quote=quote, created_by_user_id=service.id)
        db.commit()
        db.refresh(quote)
        db.refresh(token)

        yield {
            "db": db,
            "tenant": tenant,
            "service": service,
            "owner": owner,
            "vehicle": vehicle,
            "work_order": work_order,
            "quote": quote,
            "token": token,
        }
    finally:
        db.close()
        engine.dispose()


def _request(path: str) -> SimpleNamespace:
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        headers={"user-agent": "pytest-mobile"},
        client=SimpleNamespace(host="127.0.0.1"),
    )


def test_public_quote_view_has_no_pii_and_logs_open(db_context) -> None:
    db = db_context["db"]
    token = db_context["token"]

    payload = get_public_quote(token=token.token, request=_request(f"/api/public/quote/{token.token}"), db=db)

    assert payload["vehicle_label"] == "Skoda Octavia"
    assert payload["service_name"] == "ToozServis"
    assert payload["total_price"] == 3490
    assert payload["decision_available"] is True
    assert "customer_name" not in payload
    assert "phone" not in payload
    row = db.execute(
        text("SELECT action FROM service_quote_access_logs WHERE quote_id = :quote_id ORDER BY id DESC LIMIT 1"),
        {"quote_id": payload["quote_id"]},
    ).fetchone()
    assert row[0] == "public_quote_opened"


def test_public_quote_approve_updates_quote_and_work_order(db_context) -> None:
    db = db_context["db"]
    token = db_context["token"]
    quote = db_context["quote"]
    work_order = db_context["work_order"]

    response = approve_public_quote(token=token.token, request=_request(f"/api/public/quote/{token.token}/approve"), db=db)

    db.refresh(quote)
    db.refresh(work_order)
    assert response["status"] == "approved"
    assert quote.status == "approved"
    assert quote.approved_at is not None
    assert work_order.status == "approved"
    access_row = db.execute(
        text(
            "SELECT action, remote_addr, user_agent FROM service_quote_access_logs WHERE quote_id = :quote_id ORDER BY id DESC LIMIT 1"
        ),
        {"quote_id": quote.id},
    ).fetchone()
    assert access_row[0] == "public_quote_approved"
    assert access_row[1] == "127.0.0.1"
    assert "pytest-mobile" in (access_row[2] or "")
    audit_row = db.execute(
        text("SELECT action FROM service_quote_audit_logs WHERE quote_id = :quote_id ORDER BY id DESC LIMIT 1"),
        {"quote_id": quote.id},
    ).fetchone()
    assert audit_row[0] == "public_quote_approved"
    wo_audit = db.execute(
        text(
            "SELECT action FROM service_work_order_audit_logs WHERE work_order_id = :wid ORDER BY id DESC LIMIT 1"
        ),
        {"wid": work_order.id},
    ).fetchone()
    assert wo_audit is not None
    assert wo_audit[0] == "public_quote_approved"
    assert service_dashboard_module._quote_status_consistency_note(quote=quote, work_order=work_order) is None


def test_public_quote_reject_updates_status_and_audits(db_context) -> None:
    db = db_context["db"]
    token = db_context["token"]
    quote = db_context["quote"]
    work_order = db_context["work_order"]

    work_order.status = "approved"
    work_order.approved_at = datetime.utcnow()
    db.add(work_order)
    db.commit()

    response = reject_public_quote(token=token.token, request=_request(f"/api/public/quote/{token.token}/reject"), db=db)

    db.refresh(quote)
    db.refresh(work_order)
    assert response["status"] == "rejected"
    assert quote.status == "rejected"
    assert quote.rejected_at is not None
    assert work_order.status == "awaiting_client_approval"
    assert work_order.approved_at is None
    audit_row = db.execute(
        text("SELECT action FROM service_quote_audit_logs WHERE quote_id = :quote_id ORDER BY id DESC LIMIT 1"),
        {"quote_id": quote.id},
    ).fetchone()
    assert audit_row[0] == "public_quote_rejected"
    wo_audit = db.execute(
        text(
            "SELECT action FROM service_work_order_audit_logs WHERE work_order_id = :wid ORDER BY id DESC LIMIT 1"
        ),
        {"wid": work_order.id},
    ).fetchone()
    assert wo_audit is not None
    assert wo_audit[0] == "public_quote_rejected_work_order_sync"
    assert service_dashboard_module._quote_status_consistency_note(quote=quote, work_order=work_order) is None


@pytest.fixture()
def db_context_quote_only(tmp_path: Path):
    db_path = tmp_path / "public_quote_no_wo.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        tenant = Tenant(name="Quote Only", license_key="quote-only-key")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        service = Customer(
            tenant_id=tenant.id,
            email="svc2@example.com",
            name="Servis2",
            role="service",
        )
        owner = Customer(
            tenant_id=tenant.id,
            email="own2@example.com",
            name="Owner2",
            role="user",
        )
        db.add_all([service, owner])
        db.commit()
        db.refresh(service)
        db.refresh(owner)

        vehicle = Vehicle(
            tenant_id=tenant.id,
            user_email=owner.email,
            brand="VW",
            model="Golf",
            plate="3XY1111",
            vin="VINNOQUOTEWO9999",
            stk_valid_until=date(2030, 1, 1),
        )
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)

        quote = ServiceQuote(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            service_id=service.id,
            work_order_id=None,
            items_json="[]",
            total_price=100,
            status="sent",
        )
        db.add(quote)
        db.flush()
        token = ensure_quote_access_token(db, quote=quote, created_by_user_id=service.id)
        db.commit()
        db.refresh(quote)
        db.refresh(token)

        yield {"db": db, "quote": quote, "token": token}
    finally:
        db.close()
        engine.dispose()


def test_public_quote_approve_reject_safe_without_work_order(db_context_quote_only) -> None:
    db = db_context_quote_only["db"]
    token = db_context_quote_only["token"]
    quote = db_context_quote_only["quote"]

    approve_public_quote(token=token.token, request=_request(f"/api/public/quote/{token.token}/approve"), db=db)
    db.refresh(quote)
    assert quote.status == "approved"

    with pytest.raises(HTTPException) as exc:
        reject_public_quote(token=token.token, request=_request(f"/api/public/quote/{token.token}/reject"), db=db)
    assert exc.value.status_code == 409


def test_public_quote_second_approve_returns_409(db_context) -> None:
    db = db_context["db"]
    token = db_context["token"]
    approve_public_quote(token=token.token, request=_request(f"/api/public/quote/{token.token}/approve"), db=db)
    with pytest.raises(HTTPException) as exc:
        approve_public_quote(token=token.token, request=_request(f"/api/public/quote/{token.token}/approve"), db=db)
    assert exc.value.status_code == 409


def test_public_quote_second_reject_returns_409(db_context) -> None:
    db = db_context["db"]
    token = db_context["token"]
    reject_public_quote(token=token.token, request=_request(f"/api/public/quote/{token.token}/reject"), db=db)
    with pytest.raises(HTTPException) as exc:
        reject_public_quote(token=token.token, request=_request(f"/api/public/quote/{token.token}/reject"), db=db)
    assert exc.value.status_code == 409
