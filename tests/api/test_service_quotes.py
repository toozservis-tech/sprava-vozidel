from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceCustomerLink,
    ServiceQuote,
    ServiceRecord,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.routers_v1 import service_dashboard as service_dashboard_router


def _service_user(service: Customer) -> SimpleNamespace:
    return SimpleNamespace(
        id=service.id,
        email=service.email,
        name=service.name,
        role="service",
        tenant_id=service.tenant_id,
    )


def _db_context(tmp_path: Path):
    db_path = tmp_path / "service_quotes.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    tenant = Tenant(name="Quote Tenant", license_key="quote-tenant-key")
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
        name="Linked Customer",
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
        vin="VINQUOTE1234567890",
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
    db.add(
        VehicleServiceLink(
            tenant_id=tenant.id,
            service_customer_id=service.id,
            owner_customer_id=owner.id,
            vehicle_id=vehicle.id,
            status="approved",
        )
    )
    db.add(
        ServiceRecord(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            user_id=service.id,
            customer_id=owner.id,
            service_id=service.id,
            performed_at=datetime(2026, 4, 15, 9, 0, 0),
            mileage=146000,
            description="Výměna oleje a filtrů",
            category="OLEJ",
            record_status="submitted",
            total_price=3490,
            created_by_service_customer_id=service.id,
        )
    )
    db.commit()
    record = db.query(ServiceRecord).order_by(ServiceRecord.id.desc()).first()
    return engine, db, service, owner, vehicle, record


def test_create_quote_from_record_links_back_and_audits(tmp_path: Path) -> None:
    engine, db, service, _owner, _vehicle, record = _db_context(tmp_path)
    try:
        payload = service_dashboard_router.create_service_quote_from_record(
            record_id=record.id,
            current_user=_service_user(service),
            db=db,
        )

        assert payload["service_record_id"] == record.id
        assert payload["status"] == "draft"
        assert payload["total_price"] == 3490
        assert payload["items"][0]["name"] == "Výměna oleje a filtrů"
        assert "public-quote.html?token=" in str(payload["public_quote_url"])
        db.refresh(record)
        assert record.quote_id is not None

        row = db.execute(
            text("SELECT action FROM service_quote_audit_logs WHERE quote_id = :quote_id ORDER BY id DESC LIMIT 1"),
            {"quote_id": int(record.quote_id)},
        ).fetchone()
        assert row[0] == "create_quote"
    finally:
        db.close()
        engine.dispose()


def test_update_quote_logs_price_and_status_and_generates_pdf(tmp_path: Path) -> None:
    engine, db, service, owner, vehicle, record = _db_context(tmp_path)
    try:
        quote = ServiceQuote(
            tenant_id=service.tenant_id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            service_id=service.id,
            service_record_id=record.id,
            items_json='[{"name":"Servis","quantity":1,"unit_price":3000,"total_price":3000}]',
            total_price=3000,
            status="draft",
        )
        db.add(quote)
        db.commit()
        db.refresh(quote)

        service_dashboard_router.update_service_quote(
            quote_id=quote.id,
            payload=service_dashboard_router.ServiceQuoteUpdateRequest(total_price=4200),
            current_user=_service_user(service),
            db=db,
        )
        service_dashboard_router.update_service_quote(
            quote_id=quote.id,
            payload=service_dashboard_router.ServiceQuoteUpdateRequest(status="sent"),
            current_user=_service_user(service),
            db=db,
        )

        actions = db.execute(
            text("SELECT action FROM service_quote_audit_logs WHERE quote_id = :quote_id ORDER BY id"),
            {"quote_id": quote.id},
        ).fetchall()
        assert [row[0] for row in actions][-2:] == ["quote_price_change", "quote_status_change"]

        response = service_dashboard_router.get_service_quote_pdf(
            quote_id=quote.id,
            current_user=_service_user(service),
            db=db,
        )
        assert response.media_type == "application/pdf"
        assert response.body.startswith(b"%PDF")
    finally:
        db.close()
        engine.dispose()


def test_vehicle_quote_list_returns_summary(tmp_path: Path) -> None:
    engine, db, service, owner, vehicle, record = _db_context(tmp_path)
    try:
        quote = ServiceQuote(
            tenant_id=service.tenant_id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            service_id=service.id,
            service_record_id=record.id,
            items_json='[{"name":"Servis","quantity":1,"unit_price":3000,"total_price":3000}]',
            total_price=3000,
            status="sent",
        )
        db.add(quote)
        db.commit()
        db.refresh(quote)
        from src.modules.vehicle_hub.quote_public_access import ensure_quote_access_token

        ensure_quote_access_token(db, quote=quote, created_by_user_id=service.id)
        db.commit()

        payload = service_dashboard_router.list_vehicle_quotes(
            vehicle_id=vehicle.id,
            current_user=_service_user(service),
            db=db,
        )
        assert len(payload["items"]) == 1
        assert payload["items"][0]["quote_id"] == quote.id
        assert payload["items"][0]["status"] == "sent"
        assert "public-quote.html?token=" in str(payload["items"][0]["public_quote_url"])
    finally:
        db.close()
        engine.dispose()


def test_vehicle_quote_list_filters_and_sorts(tmp_path: Path) -> None:
    engine, db, service, owner, vehicle, _record = _db_context(tmp_path)
    try:

        def add_quote(status: str, price: float, created_at: datetime) -> None:
            row = ServiceQuote(
                tenant_id=service.tenant_id,
                vehicle_id=vehicle.id,
                customer_id=owner.id,
                service_id=service.id,
                items_json="[]",
                total_price=price,
                status=status,
            )
            row.created_at = created_at
            db.add(row)

        add_quote("draft", 1000, datetime(2026, 4, 10, 9, 0, 0))
        add_quote("sent", 4000, datetime(2026, 4, 12, 9, 0, 0))
        add_quote("approved", 2000, datetime(2026, 4, 11, 9, 0, 0))
        db.commit()

        drafts = service_dashboard_router.list_vehicle_quotes(
            vehicle_id=vehicle.id,
            status="draft",
            sort="created_at",
            order="desc",
            current_user=_service_user(service),
            db=db,
        )
        assert len(drafts["items"]) == 1
        assert drafts["items"][0]["status"] == "draft"

        by_price = service_dashboard_router.list_vehicle_quotes(
            vehicle_id=vehicle.id,
            status=None,
            sort="total_price",
            order="desc",
            current_user=_service_user(service),
            db=db,
        )
        prices = [float(row["total_price"]) for row in by_price["items"]]
        assert prices == [4000, 2000, 1000]

        by_status = service_dashboard_router.list_vehicle_quotes(
            vehicle_id=vehicle.id,
            status=None,
            sort="status",
            order="asc",
            current_user=_service_user(service),
            db=db,
        )
        assert [row["status"] for row in by_status["items"]] == ["draft", "sent", "approved"]
    finally:
        db.close()
        engine.dispose()


def test_vehicle_quote_list_rejects_invalid_sort(tmp_path: Path) -> None:
    engine, db, service, _owner, vehicle, _record = _db_context(tmp_path)
    try:
        with pytest.raises(HTTPException) as exc:
            service_dashboard_router.list_vehicle_quotes(
                vehicle_id=vehicle.id,
                status=None,
                sort="not_a_field",
                order="desc",
                current_user=_service_user(service),
                db=db,
            )
        assert exc.value.status_code == 422
    finally:
        db.close()
        engine.dispose()


def _quote_authorization_env(
    tmp_path: Path,
    *,
    with_customer_link: bool = True,
    vehicle_link_mode: str = "approved",
):
    """vehicle_link_mode: none | approved | revoked"""
    db_path = tmp_path / "quote_auth.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    tenant = Tenant(name="Auth Tenant", license_key="auth-tenant-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    service = Customer(
        tenant_id=tenant.id,
        email="svc@example.com",
        name="Servis",
        role="service",
    )
    owner = Customer(
        tenant_id=tenant.id,
        email="owner@example.com",
        name="Owner",
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
        vin="VINAUTH0000000001",
        plate="2CD3456",
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
            ownership_origin="manual",
            is_primary=True,
            is_active=True,
        )
    )
    if with_customer_link:
        db.add(
            ServiceCustomerLink(
                service_tenant_id=tenant.id,
                service_customer_id=service.id,
                customer_tenant_id=tenant.id,
                customer_id=owner.id,
                status="active",
            )
        )
    if vehicle_link_mode != "none":
        db.add(
            VehicleServiceLink(
                tenant_id=tenant.id,
                service_customer_id=service.id,
                owner_customer_id=owner.id,
                vehicle_id=vehicle.id,
                status=vehicle_link_mode,
            )
        )
    db.commit()
    return engine, db, service, owner, vehicle


def test_create_service_quote_rejects_without_approved_vehicle_link(tmp_path: Path) -> None:
    """A: no approved VehicleServiceLink — only vehicle_id must still fail."""
    engine, db, service, owner, vehicle = _quote_authorization_env(
        tmp_path,
        with_customer_link=True,
        vehicle_link_mode="none",
    )
    try:
        with pytest.raises(HTTPException) as exc:
            service_dashboard_router.create_service_quote(
                payload=service_dashboard_router.ServiceQuoteCreateRequest(
                    vehicle_id=vehicle.id,
                    customer_id=owner.id,
                    items=[service_dashboard_router.ServiceQuoteItemInput(name="P", quantity=1, unit_price=100, total_price=100)],
                ),
                current_user=_service_user(service),
                db=db,
            )
        assert exc.value.status_code == 403
    finally:
        db.close()
        engine.dispose()


def test_create_service_quote_rejects_customer_link_only_no_vehicle_link(tmp_path: Path) -> None:
    """B: active ServiceCustomerLink but no VehicleServiceLink row."""
    engine, db, service, owner, vehicle = _quote_authorization_env(
        tmp_path,
        with_customer_link=True,
        vehicle_link_mode="none",
    )
    try:
        with pytest.raises(HTTPException) as exc:
            service_dashboard_router.create_service_quote(
                payload=service_dashboard_router.ServiceQuoteCreateRequest(vehicle_id=vehicle.id),
                current_user=_service_user(service),
                db=db,
            )
        assert exc.value.status_code == 403
    finally:
        db.close()
        engine.dispose()


def test_create_service_quote_rejects_revoked_vehicle_link(tmp_path: Path) -> None:
    """C: VehicleServiceLink exists but not approved."""
    engine, db, service, owner, vehicle = _quote_authorization_env(
        tmp_path,
        with_customer_link=True,
        vehicle_link_mode="revoked",
    )
    try:
        with pytest.raises(HTTPException) as exc:
            service_dashboard_router.create_service_quote(
                payload=service_dashboard_router.ServiceQuoteCreateRequest(vehicle_id=vehicle.id),
                current_user=_service_user(service),
                db=db,
            )
        assert exc.value.status_code == 403
    finally:
        db.close()
        engine.dispose()


def test_create_service_quote_succeeds_with_full_authorization(tmp_path: Path) -> None:
    """D + F (authorized): with or without redundant customer_id in payload."""
    engine, db, service, owner, vehicle = _quote_authorization_env(
        tmp_path,
        with_customer_link=True,
        vehicle_link_mode="approved",
    )
    try:
        out = service_dashboard_router.create_service_quote(
            payload=service_dashboard_router.ServiceQuoteCreateRequest(
                vehicle_id=vehicle.id,
                items=[service_dashboard_router.ServiceQuoteItemInput(name="Job", quantity=1, unit_price=500, total_price=500)],
            ),
            current_user=_service_user(service),
            db=db,
        )
        assert out["vehicle_id"] == vehicle.id
        assert out["customer_id"] == owner.id
        assert out["total_price"] == 500

        out2 = service_dashboard_router.create_service_quote(
            payload=service_dashboard_router.ServiceQuoteCreateRequest(
                vehicle_id=vehicle.id,
                customer_id=owner.id,
                items=[service_dashboard_router.ServiceQuoteItemInput(name="Job2", quantity=1, unit_price=100, total_price=100)],
            ),
            current_user=_service_user(service),
            db=db,
        )
        assert out2["customer_id"] == owner.id
    finally:
        db.close()
        engine.dispose()


def test_create_service_quote_rejects_wrong_payload_customer_id(tmp_path: Path) -> None:
    """E: customer_id does not match ownership-derived owner."""
    engine, db, service, owner, vehicle = _quote_authorization_env(
        tmp_path,
        with_customer_link=True,
        vehicle_link_mode="approved",
    )
    try:
        other = Customer(
            tenant_id=owner.tenant_id,
            email="other@example.com",
            name="Other",
            role="user",
        )
        db.add(other)
        db.flush()
        db.refresh(other)
        db.add(
            ServiceCustomerLink(
                service_tenant_id=service.tenant_id,
                service_customer_id=service.id,
                customer_tenant_id=other.tenant_id,
                customer_id=other.id,
                status="active",
            )
        )
        db.commit()

        with pytest.raises(HTTPException) as exc:
            service_dashboard_router.create_service_quote(
                payload=service_dashboard_router.ServiceQuoteCreateRequest(
                    vehicle_id=vehicle.id,
                    customer_id=other.id,
                    items=[service_dashboard_router.ServiceQuoteItemInput(name="X", quantity=1, unit_price=1, total_price=1)],
                ),
                current_user=_service_user(service),
                db=db,
            )
        assert exc.value.status_code == 403
        assert "vlastníkovi" in str(exc.value.detail).lower()
    finally:
        db.close()
        engine.dispose()


def test_create_service_quote_rejects_foreign_vehicle_id_without_access(tmp_path: Path) -> None:
    """F: knowing only another vehicle's id — no link for that vehicle."""
    engine, db, service, owner, vehicle = _quote_authorization_env(
        tmp_path,
        with_customer_link=False,
        vehicle_link_mode="none",
    )
    try:
        with pytest.raises(HTTPException) as exc:
            service_dashboard_router.create_service_quote(
                payload=service_dashboard_router.ServiceQuoteCreateRequest(vehicle_id=vehicle.id),
                current_user=_service_user(service),
                db=db,
            )
        assert exc.value.status_code == 403
    finally:
        db.close()
        engine.dispose()


def test_create_service_quote_rejects_cross_tenant_vehicle(tmp_path: Path) -> None:
    engine, db, service, owner, vehicle = _quote_authorization_env(
        tmp_path,
        with_customer_link=True,
        vehicle_link_mode="approved",
    )
    try:
        t2 = Tenant(name="Other tenant", license_key="t2")
        db.add(t2)
        db.commit()
        db.refresh(t2)
        v2 = Vehicle(
            tenant_id=t2.id,
            user_email="x@y.z",
            brand="X",
            model="Y",
            vin="VINCROSS999999999",
            plate="9ZZ9999",
            stk_valid_until=date(2030, 1, 1),
        )
        db.add(v2)
        db.commit()
        db.refresh(v2)

        with pytest.raises(HTTPException) as exc:
            service_dashboard_router.create_service_quote(
                payload=service_dashboard_router.ServiceQuoteCreateRequest(vehicle_id=v2.id),
                current_user=_service_user(service),
                db=db,
            )
        assert exc.value.status_code == 403
    finally:
        db.close()
        engine.dispose()


def test_service_quote_approved_syncs_work_order_but_rejected_does_not(tmp_path: Path) -> None:
    engine, db, service, owner, vehicle, record = _db_context(tmp_path)
    try:
        work_order = service_dashboard_router.create_service_work_order(
            payload=service_dashboard_router.ServiceWorkOrderCreateRequest(
                owner_id=owner.id,
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Test zakázka",
                status="awaiting_client_approval",
            ),
            current_user=_service_user(service),
            db=db,
        )
        quote = ServiceQuote(
            tenant_id=service.tenant_id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            service_id=service.id,
            work_order_id=work_order["id"],
            service_record_id=record.id,
            items_json='[{"name":"Servis","quantity":1,"unit_price":3000,"total_price":3000}]',
            total_price=3000,
            status="draft",
        )
        db.add(quote)
        db.commit()
        db.refresh(quote)

        service_dashboard_router.update_service_quote(
            quote_id=quote.id,
            payload=service_dashboard_router.ServiceQuoteUpdateRequest(status="approved"),
            current_user=_service_user(service),
            db=db,
        )
        refreshed_work_order = db.query(service_dashboard_router.ServiceWorkOrder).filter(service_dashboard_router.ServiceWorkOrder.id == work_order["id"]).first()
        assert refreshed_work_order is not None
        assert refreshed_work_order.status == "approved"

        service_dashboard_router.update_service_quote(
            quote_id=quote.id,
            payload=service_dashboard_router.ServiceQuoteUpdateRequest(status="rejected"),
            current_user=_service_user(service),
            db=db,
        )
        db.refresh(refreshed_work_order)
        assert refreshed_work_order.status == "awaiting_client_approval"
        assert refreshed_work_order.approved_at is None
        wo_reject_audit = db.execute(
            text(
                "SELECT action FROM service_work_order_audit_logs WHERE work_order_id = :wid ORDER BY id DESC LIMIT 1"
            ),
            {"wid": refreshed_work_order.id},
        ).fetchone()
        assert wo_reject_audit is not None
        assert wo_reject_audit[0] == "quote_rejected_work_order_sync"
    finally:
        db.close()
        engine.dispose()
