from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.central_vehicle_identity import mark_vehicle_claimed
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceCustomerLink,
    ServiceInvoice,
    ServiceQuote,
    ServiceRecord,
    ServiceWorkOrder,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehiclePhotoAsset,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.routers_v1.vehicles import get_vehicle_timeline
from src.modules.vehicle_hub.vehicle_timeline import build_vehicle_timeline


def _service_user(service: Customer) -> SimpleNamespace:
    return SimpleNamespace(
        id=service.id,
        email=service.email,
        name=service.name,
        role="service",
        tenant_id=service.tenant_id,
    )


def _owner_user(owner: Customer) -> SimpleNamespace:
    return SimpleNamespace(
        id=owner.id,
        email=owner.email,
        name=owner.name,
        role="user",
        tenant_id=owner.tenant_id,
    )


def _seed_ctx(tmp_path: Path):
    db_path = tmp_path / "vehicle_timeline.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="Timeline Tenant", license_key="tl-test-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(tenant_id=tenant.id, email="owner-timeline@test.local", role="user", account_status="active")
    service = Customer(tenant_id=tenant.id, email="service-timeline@test.local", role="service", account_status="active")
    foreign_service = Customer(
        tenant_id=tenant.id,
        email="foreign-timeline@test.local",
        role="service",
        account_status="active",
    )
    db.add_all([owner, service, foreign_service])
    db.commit()
    db.refresh(owner)
    db.refresh(service)
    db.refresh(foreign_service)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        brand="Skoda",
        model="Octavia",
        vin="TMBTIMELINE1234567",
        plate="8TL9999",
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
            approved_at=datetime.utcnow(),
            approved_by_customer_id=owner.id,
        )
    )
    db.commit()
    return engine, db, owner, service, foreign_service, vehicle


def _seed_unowned_vehicle(db, service: Customer, *, vin: str):
    vehicle = Vehicle(
        tenant_id=service.tenant_id,
        user_email=f"_unowned_{service.id}@test.local",
        brand="Skoda",
        model="Fabia",
        vin=vin,
        provisioned_by_service_customer_id=service.id,
        provisioned_by_service_tenant_id=service.tenant_id,
        global_vehicle_status="service_provisioned_unowned",
        claim_status="unclaimed",
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


def test_vehicle_timeline_service_view(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        db.add(
            ServiceWorkOrder(
                tenant_id=service.tenant_id,
                service_customer_id=service.id,
                owner_customer_id=owner.id,
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Timeline WO",
                status="in_progress",
            )
        )
        db.add(
            ServiceQuote(
                tenant_id=service.tenant_id,
                vehicle_id=vehicle.id,
                customer_id=owner.id,
                service_id=service.id,
                total_price=1000,
                status="draft",
            )
        )
        db.add(
            ServiceInvoice(
                tenant_id=service.tenant_id,
                service_id=service.id,
                customer_id=owner.id,
                vehicle_id=vehicle.id,
                status="draft",
                subtotal=100,
                tax_total=21,
                total=121,
                invoice_number="TL-2026-001",
            )
        )
        db.commit()

        payload = get_vehicle_timeline(
            int(vehicle.id),
            current_user=_service_user(service),
            db=db,
        )
        types = {item["event_type"] for item in payload["items"]}
        assert "work_order_created" in types
        assert "quote_created" in types
        assert "invoice_created" in types
    finally:
        db.close()
        engine.dispose()


def test_vehicle_timeline_owner_safe(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        db.add(
            ServiceRecord(
                tenant_id=owner.tenant_id,
                vehicle_id=vehicle.id,
                user_id=service.id,
                service_id=service.id,
                description="Bezpečný servis",
                notes_customer_visible="Výměna oleje",
                visibility_scope="safe_history_after_claim",
                price=999,
                total_price=1200,
                quote_id=55,
            )
        )
        db.add(
            ServiceQuote(
                tenant_id=service.tenant_id,
                vehicle_id=vehicle.id,
                customer_id=owner.id,
                service_id=service.id,
                total_price=5000,
                status="draft",
            )
        )
        db.commit()

        payload = get_vehicle_timeline(
            int(vehicle.id),
            current_user=_owner_user(owner),
            db=db,
        )
        blob = json.dumps(payload, ensure_ascii=False).lower()
        assert "quote_created" not in {x["event_type"] for x in payload["items"]}
        assert "invoice_created" not in {x["event_type"] for x in payload["items"]}
        for forbidden in ("invoice", "quote_id", "total_price", "billing", "999", "5000"):
            assert forbidden not in blob
        assert any(x["event_type"] == "service_record_created" for x in payload["items"])
    finally:
        db.close()
        engine.dispose()


def test_vehicle_timeline_filters_internal_photos(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        db.add(
            VehiclePhotoAsset(
                tenant_id=service.tenant_id,
                vehicle_id=vehicle.id,
                service_customer_id=service.id,
                role="work_order",
                visibility_scope="internal_only",
                photo_kind="internal",
                storage_key="internal/key.jpg",
                original_filename="internal.jpg",
                mime_type="image/jpeg",
                file_size_bytes=100,
                sha256_hex="a" * 64,
            )
        )
        db.add(
            VehiclePhotoAsset(
                tenant_id=service.tenant_id,
                vehicle_id=vehicle.id,
                service_customer_id=service.id,
                role="work_order",
                visibility_scope="owner_visible",
                photo_kind="completion",
                storage_key="safe/key.jpg",
                original_filename="safe.jpg",
                mime_type="image/jpeg",
                file_size_bytes=100,
                sha256_hex="b" * 64,
            )
        )
        db.commit()

        owner_payload = get_vehicle_timeline(int(vehicle.id), current_user=_owner_user(owner), db=db)
        owner_photos = [x for x in owner_payload["items"] if x["event_type"] == "photo_uploaded"]
        assert len(owner_photos) == 1
        assert owner_photos[0]["photo_preview"]["photo_type"] == "completion"

        service_payload = get_vehicle_timeline(int(vehicle.id), current_user=_service_user(service), db=db)
        service_photos = [x for x in service_payload["items"] if x["event_type"] == "photo_uploaded"]
        assert len(service_photos) == 1
    finally:
        db.close()
        engine.dispose()


def test_vehicle_timeline_cross_service_forbidden(tmp_path: Path) -> None:
    engine, db, owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        with pytest.raises(HTTPException) as exc:
            get_vehicle_timeline(int(vehicle.id), current_user=_service_user(foreign_service), db=db)
        assert exc.value.status_code == 403
    finally:
        db.close()
        engine.dispose()


def test_vehicle_timeline_unowned(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        vehicle = _seed_unowned_vehicle(db, service, vin="TMBUNOWNEDTL12345")
        db.add(
            ServiceWorkOrder(
                tenant_id=service.tenant_id,
                service_customer_id=service.id,
                owner_customer_id=None,
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Unowned WO",
                status="in_progress",
            )
        )
        db.commit()
        payload = get_vehicle_timeline(int(vehicle.id), current_user=_service_user(service), db=db)
        assert any(x["event_type"] == "work_order_created" for x in payload["items"])
    finally:
        db.close()
        engine.dispose()


def test_vehicle_timeline_after_claim(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        vehicle = _seed_unowned_vehicle(db, service, vin="TMBCLAIMTL1234567")
        db.add(
            ServiceRecord(
                tenant_id=service.tenant_id,
                vehicle_id=vehicle.id,
                user_id=service.id,
                service_id=service.id,
                description="Interní",
                notes_customer_visible="Bezpečný záznam po claimu",
                visibility_scope="safe_history_after_claim",
                price=3000,
            )
        )
        db.add(
            ServiceInvoice(
                tenant_id=service.tenant_id,
                service_id=service.id,
                customer_id=owner.id,
                vehicle_id=vehicle.id,
                status="issued",
                subtotal=200,
                tax_total=42,
                total=242,
                invoice_number="INV-CLAIM-TL",
            )
        )
        db.commit()
        mark_vehicle_claimed(db, vehicle=vehicle, owner=owner, actor=owner)
        db.commit()

        payload = get_vehicle_timeline(int(vehicle.id), current_user=_owner_user(owner), db=db)
        blob = json.dumps(payload, ensure_ascii=False).lower()
        assert "invoice_created" not in {x["event_type"] for x in payload["items"]}
        assert "inv-claim" not in blob
        assert any(x["event_type"] == "service_record_created" for x in payload["items"])
    finally:
        db.close()
        engine.dispose()


def test_vehicle_timeline_no_duplicate_events(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        db.add(
            ServiceRecord(
                tenant_id=owner.tenant_id,
                vehicle_id=vehicle.id,
                user_id=service.id,
                service_id=service.id,
                description="Jeden záznam",
                visibility_scope="full_current_owner",
            )
        )
        db.commit()
        payload = build_vehicle_timeline(
            db,
            vehicle=vehicle,
            viewer="owner",
            current_user=_owner_user(owner),
        )
        keys = [
            (x["event_type"], x["source_type"], x["source_id"])
            for x in payload["items"]
        ]
        assert len(keys) == len(set(keys))
    finally:
        db.close()
        engine.dispose()


def test_vehicle_timeline_no_billing_data(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        db.add(
            ServiceInvoice(
                tenant_id=service.tenant_id,
                service_id=service.id,
                customer_id=owner.id,
                vehicle_id=vehicle.id,
                status="draft",
                subtotal=100,
                tax_total=21,
                total=121,
            )
        )
        db.commit()
        owner_payload = get_vehicle_timeline(int(vehicle.id), current_user=_owner_user(owner), db=db)
        blob = json.dumps(owner_payload, ensure_ascii=False).lower()
        assert "billing" not in blob
        assert "121" not in blob
    finally:
        db.close()
        engine.dispose()


def test_vehicle_timeline_ordering(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        early = ServiceRecord(
            tenant_id=owner.tenant_id,
            vehicle_id=vehicle.id,
            user_id=service.id,
            service_id=service.id,
            description="Starší",
            performed_at=datetime(2024, 1, 1, 10, 0, 0),
            visibility_scope="full_current_owner",
        )
        late = ServiceRecord(
            tenant_id=owner.tenant_id,
            vehicle_id=vehicle.id,
            user_id=service.id,
            service_id=service.id,
            description="Novější",
            performed_at=datetime(2025, 6, 1, 10, 0, 0),
            visibility_scope="full_current_owner",
        )
        db.add_all([early, late])
        db.commit()
        payload = get_vehicle_timeline(int(vehicle.id), current_user=_owner_user(owner), db=db)
        timestamps = [x["timestamp"] for x in payload["items"] if x["event_type"] == "service_record_created"]
        assert timestamps == sorted(timestamps, reverse=True)
    finally:
        db.close()
        engine.dispose()
