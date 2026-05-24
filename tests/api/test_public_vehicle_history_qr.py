from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, ServiceQuote, ServiceRecord, Tenant, Vehicle, VehicleQrToken
from src.modules.vehicle_hub.quote_public_access import ensure_quote_access_token
from src.modules.vehicle_hub.routers_v1.vehicles import _vehicle_to_response_payload
from src.modules.vehicle_hub.vehicle_public_history import build_vehicle_qr_signature
from src.server.routers.public_vehicle_history import get_public_vehicle_history


@pytest.fixture()
def db_context(tmp_path: Path):
    db_path = tmp_path / "public_vehicle_history.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        tenant = Tenant(name="QR Tenant", license_key="qr-tenant-key")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        service = Customer(
            tenant_id=tenant.id,
            email="service@example.com",
            name="Trusted Service",
            ico="12345678",
            role="service",
        )
        owner = Customer(
            tenant_id=tenant.id,
            email="owner@example.com",
            name="Owner Person",
            role="user",
        )
        db.add_all([service, owner])
        db.commit()
        db.refresh(service)
        db.refresh(owner)

        vehicle = Vehicle(
            tenant_id=tenant.id,
            user_email=owner.email,
            nickname="Octavia",
            brand="Skoda",
            model="Octavia",
            vin="TMB12345678901234",
            plate="1AB2345",
            year=2021,
            engine="2.0 TDI",
            stk_valid_until=date(2030, 1, 1),
        )
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)

        issued_at = datetime(2026, 4, 15, 12, 0, 0)
        token = VehicleQrToken(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            created_by_user_id=service.id,
            token="public-token-1",
            public_mode="full",
            explicit_full_consent=False,
            active=True,
            issued_at=issued_at,
            signature_hash=build_vehicle_qr_signature(
                token="public-token-1",
                vehicle_id=vehicle.id,
                issued_at=issued_at,
            ),
        )
        db.add(token)
        db.flush()

        approved_record = ServiceRecord(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            user_id=service.id,
            customer_id=owner.id,
            service_id=service.id,
            performed_at=datetime(2026, 4, 10, 9, 0, 0),
            mileage=145000,
            description="Výměna oleje",
            category="OLEJ",
            record_status="approved",
            recommended_next_service_text="Další servis za 12 měsíců",
            recommended_next_service_date=date(2027, 4, 10),
            notes_customer_visible="Použijte olej 5W-30.",
            note="Interní poznámka servisu",
            total_price=3490,
            created_by_service_customer_id=service.id,
        )
        db.add(approved_record)
        db.flush()
        quote = ServiceQuote(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            service_id=service.id,
            service_record_id=approved_record.id,
            items_json='[{"name":"Výměna oleje","quantity":1,"unit_price":3490,"total_price":3490}]',
            total_price=3490,
            status="approved",
        )
        db.add(quote)
        db.flush()
        ensure_quote_access_token(db, quote=quote, created_by_user_id=service.id)
        approved_record.quote_id = quote.id
        db.add(
            ServiceRecord(
                tenant_id=tenant.id,
                vehicle_id=vehicle.id,
                user_id=service.id,
                customer_id=owner.id,
                service_id=service.id,
                performed_at=datetime(2026, 4, 12, 9, 0, 0),
                mileage=145500,
                description="Draft záznam",
                category="DIAGNOSTIKA",
                record_status="draft",
                notes_customer_visible="Nemá být veřejně",
                created_by_service_customer_id=service.id,
            )
        )
        db.commit()

        yield {"db": db, "token": token, "vehicle": vehicle}
    finally:
        db.close()
        engine.dispose()


def _request(path: str) -> SimpleNamespace:
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        headers={"user-agent": "pytest"},
        client=SimpleNamespace(host="127.0.0.1"),
    )


def test_public_vehicle_history_falls_back_from_full_to_verified_without_consent(db_context) -> None:
    db = db_context["db"]
    token = db_context["token"]

    payload = get_public_vehicle_history(token=token.token, request=_request(f"/api/public/vehicle-history/{token.token}"), db=db)

    assert payload["public_mode"] == "verified"
    assert payload["vin"] == "TMB12345678901234"
    assert len(payload["records"]) == 1
    assert payload["records"][0]["service_identity"]["name"] == "Trusted Service"
    assert payload["records"][0]["service_identity"]["verified_status"] is True
    assert "notes_customer_visible" not in payload["records"][0]
    assert payload["records"][0]["description"] == "Výměna oleje"
    assert payload["records"][0]["quote_status"] == "approved"
    assert payload["records"][0]["quote_id"] is not None
    assert "public-quote.html?token=" in str(payload["records"][0]["public_quote_url"])

    access_count = db.execute(text("SELECT COUNT(*) FROM vehicle_qr_access_logs")).scalar_one()
    assert access_count == 1


def test_public_vehicle_history_rejects_invalid_signature_and_audits(db_context) -> None:
    db = db_context["db"]
    token = db_context["token"]
    token.signature_hash = "broken"
    db.add(token)
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        get_public_vehicle_history(token=token.token, request=_request(f"/api/public/vehicle-history/{token.token}"), db=db)

    assert exc_info.value.status_code == 409
    row = db.execute(
        text("SELECT access_status, access_signature_valid FROM vehicle_qr_access_logs ORDER BY id DESC LIMIT 1")
    ).fetchone()
    assert row[0] == "invalid_signature"
    assert row[1] in (0, False)


def test_vehicle_detail_payload_exposes_active_qr_metadata_for_owner(db_context) -> None:
    db = db_context["db"]
    vehicle = db_context["vehicle"]

    owner = db.query(Customer).filter(Customer.email == "owner@example.com").one()
    payload = _vehicle_to_response_payload(vehicle, owner, db)

    assert payload["has_qr_token"] is True
    assert payload["qr_public_mode"] == "full"
    assert payload["public_history_url"].endswith("public-vehicle-history.html?token=public-token-1")
    assert "<svg" in str(payload["qr_svg"])
