from __future__ import annotations

import base64
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from starlette.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub import orv_scans
from src.modules.vehicle_hub.models import Customer, Tenant, VehicleORVScan
from src.modules.vehicle_hub.orv_parser import parse_czech_orv_texts
from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router
from src.modules.vehicle_hub.routers_v1.schemas import ORVParseRequestV1, ORVReviewAuditRequestV1, VehicleCreateV1


FRONT_TEXT = """
A 1AB 2345
B 15.05.2018
Cislo ORV UH123456
C.1.1 Jan Novak
C.1.3 Praha 4, Modranska 12
C.2.1 Autopujcovna Novak s.r.o.
C.2.3 Brno, Vyskocilova 5
"""

BACK_TEXT = """
D.1 SKODA
D.2 3T / VAR / VER
D.3 SUPERB
E TMBJF73T2B9044629
J M1
P.1 1968
P.2 125
P.3 NAFTA
S.1 5
T 225
V.9 EURO 6
"""

VALID_BASE64_IMAGE = base64.b64encode((b"fake-orv-image-bytes-" * 5)).decode("ascii")

# PIL normalizace vyžaduje platný obrázek; v unit testech pouze ověřujeme OCR/parsing.
@pytest.fixture(autouse=True)
def _orv_passthrough_image_normalize(monkeypatch):
    monkeypatch.setattr(orv_scans, "_normalize_orv_image_bytes", lambda content, **kwargs: content)


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "vehicle_orv.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = session_local()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_user(db_session):
    tenant = Tenant(name="ORV Tenant", license_key="orv-tenant-key")
    db_session.add(tenant)
    db_session.flush()
    user = Customer(
        tenant_id=tenant.id,
        email="orv@example.com",
        password_hash="hash",
        role="user",
        name="ORV Tester",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_parse_czech_orv_texts_extracts_vin_plate_and_orv_number():
    result = parse_czech_orv_texts(FRONT_TEXT, BACK_TEXT)

    assert result["vehicle"]["vin"] == "TMBJF73T2B9044629"
    assert result["vehicle"]["plate"] == "1AB 2345"
    assert result["document"]["orv_number"] == "UH123456"


def test_parse_czech_orv_texts_separates_vehicle_and_owner_data():
    result = parse_czech_orv_texts(FRONT_TEXT, BACK_TEXT)

    assert result["vehicle"]["brand"] == "Skoda"
    assert result["vehicle"]["model"] == "Superb"
    assert result["owner"]["owner"]["name"] == "Jan Novak"
    assert "Praha" in str(result["owner"]["owner"]["address"])
    assert result["owner"]["operator"]["name"] == "Autopujcovna Novak S.R.O."


def test_parse_czech_orv_texts_flags_missing_vin_for_manual_review():
    result = parse_czech_orv_texts(FRONT_TEXT, BACK_TEXT.replace("TMBJF73T2B9044629", ""))

    assert "vin" in result["missing_fields"]
    assert any("VIN" in warning for warning in result["warnings"])


def _patch_orv_ocr_front_back(monkeypatch):
    calls = {"n": 0}

    def fake_ocr(image_bytes, file_name, mime_type):
        del image_bytes, file_name, mime_type
        calls["n"] += 1
        return FRONT_TEXT if calls["n"] == 1 else BACK_TEXT

    monkeypatch.setattr(orv_scans, "_extract_ocr_text", fake_ocr)


def test_parse_orv_requires_both_images(db_session, monkeypatch):
    user = _seed_user(db_session)
    original_decode = orv_scans._decode_base64_image
    empty_but_long_marker = "A" * 120

    def fake_decode(payload: str) -> bytes:
        if payload == empty_but_long_marker:
            return b""
        return original_decode(payload)

    monkeypatch.setattr(orv_scans, "_decode_base64_image", fake_decode)
    with pytest.raises(HTTPException) as exc_info:
        vehicles_router.parse_orv(
            payload=ORVParseRequestV1(
                front_image_base64=VALID_BASE64_IMAGE,
                back_image_base64=empty_but_long_marker,
                source="web_orv_scan",
            ),
            current_user=user,
            db=db_session,
        )
    assert "obě strany" in str(exc_info.value.detail).lower()


def test_orv_parse_request_rejects_single_plus_dual_images():
    with pytest.raises(ValidationError):
        ORVParseRequestV1(
            single_orv_image_base64=VALID_BASE64_IMAGE,
            front_image_base64=VALID_BASE64_IMAGE,
            back_image_base64=VALID_BASE64_IMAGE,
        )


def test_parse_orv_accepts_single_card_scan(db_session, monkeypatch):
    user = _seed_user(db_session)
    combined = (
        "A 1AB 2345\n"
        "VIN: TMBJF73T2B9044629\n"
        "Cislo ORV UH123456\n"
    )

    def fake_ocr(image_bytes, file_name, mime_type):
        del image_bytes, file_name, mime_type
        return combined

    monkeypatch.setattr(orv_scans, "_extract_ocr_text", fake_ocr)
    response = vehicles_router.parse_orv(
        payload=ORVParseRequestV1(
            single_orv_image_base64=VALID_BASE64_IMAGE,
            source="web_add_vehicle_single",
        ),
        current_user=user,
        db=db_session,
    )
    assert response["scan_id"] > 0
    vf = response["vehicle_fields"]
    assert vf.get("vin") == "TMBJF73T2B9044629"
    assert vf.get("orv_number") == "UH123456"
    scan = db_session.query(VehicleORVScan).filter(VehicleORVScan.id == response["scan_id"]).first()
    assert scan is not None
    assert scan.front_image_hash == scan.back_image_hash


def test_parse_orv_persists_scan_draft_and_hashes(db_session, monkeypatch):
    user = _seed_user(db_session)
    _patch_orv_ocr_front_back(monkeypatch)
    response = vehicles_router.parse_orv(
        payload=ORVParseRequestV1(
            front_image_base64=VALID_BASE64_IMAGE,
            back_image_base64=VALID_BASE64_IMAGE,
            source="web_orv_scan",
        ),
        current_user=user,
        db=db_session,
    )
    assert response["scan_id"] > 0
    scan = db_session.query(VehicleORVScan).filter(VehicleORVScan.id == response["scan_id"]).first()
    assert scan is not None
    assert scan.front_image_hash
    assert scan.back_image_hash
    assert scan.trust_state == "scanned_unverified"
    assert scan.status == "review"
    combined_ocr = f"{scan.front_ocr_text or ''}\n{scan.back_ocr_text or ''}"
    assert "TMBJF73T2B9044629" in combined_ocr


def test_create_vehicle_from_orv_scan_links_metadata(db_session, monkeypatch):
    user = _seed_user(db_session)
    _patch_orv_ocr_front_back(monkeypatch)
    parse_response = vehicles_router.parse_orv(
        payload=ORVParseRequestV1(
            front_image_base64=VALID_BASE64_IMAGE,
            back_image_base64=VALID_BASE64_IMAGE,
            source="web_orv_scan",
        ),
        current_user=user,
        db=db_session,
    )
    created_payload = vehicles_router.create_vehicle(
        vehicle_data=VehicleCreateV1(
            nickname="Test ORV Vehicle",
            plate="1AB 2345",
            brand="Skoda",
            model="Superb Combi",
            year=2018,
            engine="2.0 TDI 125 kW",
            vin="TMBJF73T2B9044629",
            stk_valid_until=date(2030, 12, 31),
            orv_scan_id=parse_response["scan_id"],
            orv_use_owner_data=False,
        ),
        current_user=user,
        db=db_session,
    )
    assert created_payload["orv_number"] == "UH123456"
    assert created_payload["orv_scan_source"] == "web_orv_scan"
    assert created_payload["data_trust_state"] == "verified_by_user"
    scan = db_session.query(VehicleORVScan).filter(VehicleORVScan.id == parse_response["scan_id"]).first()
    assert scan is not None
    assert scan.vehicle_id == created_payload["id"]
    assert scan.manual_overrides_json


def test_create_vehicle_from_orv_without_vin_is_rejected(db_session, monkeypatch):
    user = _seed_user(db_session)
    calls = {"n": 0}

    def fake_ocr(image_bytes, file_name, mime_type):
        del image_bytes, file_name, mime_type
        calls["n"] += 1
        if calls["n"] == 1:
            return FRONT_TEXT
        return BACK_TEXT.replace("TMBJF73T2B9044629", "")

    monkeypatch.setattr(orv_scans, "_extract_ocr_text", fake_ocr)
    parse_response = vehicles_router.parse_orv(
        payload=ORVParseRequestV1(
            front_image_base64=VALID_BASE64_IMAGE,
            back_image_base64=VALID_BASE64_IMAGE,
            source="web_orv_scan",
        ),
        current_user=user,
        db=db_session,
    )
    response = vehicles_router.create_vehicle(
        vehicle_data=VehicleCreateV1(
            nickname="Test ORV No VIN",
            plate="1AB 2345",
            brand="Skoda",
            model="Superb",
            stk_valid_until=date(2030, 12, 31),
            orv_scan_id=parse_response["scan_id"],
        ),
        current_user=user,
        db=db_session,
    )
    assert isinstance(response, JSONResponse)
    assert response.status_code == 422
    assert b"VIN" in response.body


def test_save_orv_review_audit_persists_json(db_session, monkeypatch):
    user = _seed_user(db_session)
    calls = {"n": 0}

    def fake_ocr(image_bytes, file_name, mime_type):
        del image_bytes, file_name, mime_type
        calls["n"] += 1
        return FRONT_TEXT if calls["n"] == 1 else BACK_TEXT

    monkeypatch.setattr(orv_scans, "_extract_ocr_text", fake_ocr)

    parse_response = vehicles_router.parse_orv(
        payload=ORVParseRequestV1(
            front_image_base64=VALID_BASE64_IMAGE,
            back_image_base64=VALID_BASE64_IMAGE,
            source="web_orv_scan",
        ),
        current_user=user,
        db=db_session,
    )
    scan_id = int(parse_response["scan_id"])

    audit_out = vehicles_router.save_orv_review_audit(
        scan_id=scan_id,
        payload=ORVReviewAuditRequestV1(
            nickname="Superb combi",
            brand="Skoda",
            model="Superb",
            year=2018,
            engine="NAFTA · 125 kW",
            vin="TMBJF73T2B9044629",
            plate="1AB 2345",
            orv_number="UH123456",
        ),
        current_user=user,
        db=db_session,
    )
    assert audit_out.scan_id == scan_id
    assert audit_out.vin_validation.get("valid") is True

    scan = db_session.query(VehicleORVScan).filter(VehicleORVScan.id == scan_id).first()
    assert scan is not None
    assert scan.orv_review_audit_json
    stored = json.loads(scan.orv_review_audit_json)
    assert stored["vin_validation"]["normalized"] == "TMBJF73T2B9044629"
    assert stored["ocr_front_sha256"] == scan.front_image_hash
    assert "field_diffs" in stored
