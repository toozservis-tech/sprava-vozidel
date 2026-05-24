from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import requests
from sqlalchemy import func

from src.modules.vehicle_hub.database import SessionLocal
from src.modules.vehicle_hub.models import Customer
from tests.api.integration_accounts import (
    CI_API_BUYER,
    CI_API_OWNER_INTAKE,
    CI_API_SELLER,
    CI_API_SERVICE_INTAKE,
    ensure_user_token,
)


def _register_user(api_url: str, *, email: str, name: str) -> tuple[str, int]:
    return ensure_user_token(api_url, email, name=name)


def _promote_user_to_service(email: str) -> None:
    db = SessionLocal()
    try:
        customer = db.query(Customer).filter(func.lower(Customer.email) == email.lower()).first()
        assert customer is not None
        customer.role = "service"
        db.commit()
    finally:
        db.close()


def _vin() -> str:
    return f"TMB{uuid4().hex[:14].upper()}"[:17].replace("I", "A").replace("O", "B").replace("Q", "C")


def _create_vehicle(api_url: str, token: str, *, plate: str, vin: str) -> int:
    response = requests.post(
        f"{api_url}/api/v1/vehicles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "nickname": "Test Lifecycle Vehicle",
            "brand": "Skoda",
            "model": "Octavia",
            "year": 2022,
            "plate": plate,
            "vin": vin,
            "stk_valid_until": (date.today() + timedelta(days=365)).isoformat(),
        },
        timeout=8,
    )
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


def test_transfer_token_claim_preserves_history(api_url):
    seller_token, _seller_id = _register_user(api_url, email=CI_API_SELLER, name="Seller")
    buyer_token, _buyer_id = _register_user(api_url, email=CI_API_BUYER, name="Buyer")
    plate = f"TR{uuid4().hex[:5].upper()}"[:7]
    vin = _vin()
    vehicle_id = _create_vehicle(api_url, seller_token, plate=plate, vin=vin)

    token_response = requests.post(
        f"{api_url}/api/v1/vehicles/{vehicle_id}/transfer-token",
        headers={"Authorization": f"Bearer {seller_token}"},
        json={"transfer_reason": "sale", "expires_in_days": 14},
        timeout=8,
    )
    assert token_response.status_code == 200, token_response.text
    transfer_token = token_response.json()["token"]

    public_response = requests.get(f"{api_url}/api/public/vehicle-transfer/{transfer_token}", timeout=8)
    assert public_response.status_code == 200, public_response.text
    assert "spz_masked" in public_response.json().get("vehicle", {})
    assert "requires_login" in public_response.json()

    claim_response = requests.post(
        f"{api_url}/api/public/vehicle-transfer/{transfer_token}/claim",
        headers={"Authorization": f"Bearer {buyer_token}"},
        json={"token": transfer_token, "spz": plate, "vin": vin},
        timeout=8,
    )
    assert claim_response.status_code == 200, claim_response.text
    assert claim_response.json()["history_preserved"] is True

    seller_vehicles = requests.get(f"{api_url}/api/v1/vehicles", headers={"Authorization": f"Bearer {seller_token}"}, timeout=8)
    buyer_vehicles = requests.get(f"{api_url}/api/v1/vehicles", headers={"Authorization": f"Bearer {buyer_token}"}, timeout=8)
    assert vehicle_id not in {int(item["id"]) for item in seller_vehicles.json()}
    assert vehicle_id in {int(item["id"]) for item in buyer_vehicles.json()}


def test_service_intake_blocks_final_record_until_access_approved(api_url):
    owner_token, _owner_id = _register_user(api_url, email=CI_API_OWNER_INTAKE, name="Owner Intake")
    service_token, service_id = _register_user(api_url, email=CI_API_SERVICE_INTAKE, name="Service Intake")
    db = SessionLocal()
    try:
        service = db.query(Customer).filter(Customer.id == service_id).first()
        assert service is not None
        service.role = "service"
        db.commit()
    finally:
        db.close()

    plate = f"IN{uuid4().hex[:5].upper()}"[:7]
    vin = _vin()
    vehicle_id = _create_vehicle(api_url, owner_token, plate=plate, vin=vin)

    service_headers = {"Authorization": f"Bearer {service_token}"}
    intake_response = requests.post(
        f"{api_url}/api/service/vehicle-intake/from-spz-photo",
        headers=service_headers,
        json={"manual_spz": plate, "file_name": "intake.jpg", "file_mime_type": "image/jpeg"},
        timeout=8,
    )
    assert intake_response.status_code == 200, intake_response.text
    case_id = int(intake_response.json()["case"]["id"])
    assert intake_response.json()["requires_owner_approval"] is True

    blocked_response = requests.post(
        f"{api_url}/api/service/vehicle-intake/{case_id}/create-service-record",
        headers=service_headers,
        json={"template_type": "oil_change", "description": "Výměna oleje"},
        timeout=8,
    )
    assert blocked_response.status_code == 403, blocked_response.text

    request_response = requests.post(
        f"{api_url}/api/service/vehicle-intake/{case_id}/owner-access-request",
        headers=service_headers,
        json={"message": "Prosím o schválení příjmu."},
        timeout=8,
    )
    assert request_response.status_code == 200, request_response.text
    request_id = int(request_response.json()["request_id"])

    approve_response = requests.post(
        f"{api_url}/api/v1/vehicles/{vehicle_id}/service-access/{request_id}/approve",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"note": "Schváleno"},
        timeout=8,
    )
    assert approve_response.status_code == 200, approve_response.text

    create_response = requests.post(
        f"{api_url}/api/service/vehicle-intake/{case_id}/create-service-record",
        headers=service_headers,
        json={"template_type": "oil_change", "description": "Výměna oleje", "recommended_next_service_km": 15000},
        timeout=8,
    )
    assert create_response.status_code == 200, create_response.text
    assert create_response.json()["created"] is True
