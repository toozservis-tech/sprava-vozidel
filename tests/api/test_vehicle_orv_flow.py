from __future__ import annotations

import base64
import json
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.licensing import service as licensing_service
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle as VehicleModel, VehicleORVScan
from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router
from src.modules.vehicle_hub import orv_scans


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "vehicle_orv_flow.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_owner(db_session):
    tenant = Tenant(name="ORV Tenant", license_key="orv-tenant-key")
    db_session.add(tenant)
    db_session.flush()

    owner = Customer(
        tenant_id=tenant.id,
        email="orv-user@example.com",
        password_hash="hash",
        role="user",
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return owner


def _png_base64(color: tuple[int, int, int]) -> str:
    image = Image.new("RGB", (1200, 800), color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_parse_orv_separates_vehicle_and_owner_data(db_session, monkeypatch, tmp_path: Path) -> None:
    owner = _seed_owner(db_session)
    monkeypatch.setattr(orv_scans, "ORV_SCANS_DIR", tmp_path / "orv_scans")

    extracted_texts = iter(
        [
            "\n".join(
                [
                    "Registrační značka: 1AB2345",
                    "Číslo ORV: UVA123456",
                    "Vlastník: Jan Novak",
                    "Adresa vlastníka: Ulice 1, Praha",
                    "Provozovatel: ACME s.r.o.",
                    "Adresa provozovatele: Servisni 10, Brno",
                    "Datum první registrace: 01.02.2020",
                ]
            ),
            "\n".join(
                [
                    "VIN: TMBJF73T2B9044629",
                    "Značka: SKODA",
                    "Obchodní označení: OCTAVIA",
                    "Typ: 5E",
                    "Palivo: BENZIN",
                    "Výkon: 110 kW",
                    "Objem: 1395 cm3",
                    "Kategorie: M1",
                ]
            ),
        ]
    )
    monkeypatch.setattr(orv_scans, "_extract_ocr_text", lambda *args, **kwargs: next(extracted_texts))

    response = vehicles_router.parse_orv(
        payload=vehicles_router.ORVParseRequestV1(
            front_image_base64=_png_base64((220, 220, 220)),
            back_image_base64=_png_base64((180, 180, 180)),
            source="ios_orv_scan",
        ),
        current_user=owner,
        db=db_session,
    )

    assert response["vehicle_fields"]["vin"] == "TMBJF73T2B9044629"
    assert response["vehicle_fields"]["plate"] == "1AB 2345"
    assert response["vehicle_fields"]["orv_number"] == "UVA123456"
    assert response["vehicle_fields"]["brand"] == "SKODA"
    assert response["vehicle_fields"]["model"] == "OCTAVIA"
    assert response["owner_fields"]["owner_name"] == "Jan Novak"
    assert response["owner_fields"]["operator_name"] == "ACME s.r.o."
    assert "vin" not in response["missing_fields"]

    scan = db_session.query(VehicleORVScan).filter(VehicleORVScan.id == response["scan_id"]).one()
    assert scan.front_image_hash
    assert scan.back_image_hash
    assert scan.front_captured is True
    assert scan.back_captured is True
    assert json.loads(scan.parsed_vehicle_json)["vin"] == "TMBJF73T2B9044629"
    assert json.loads(scan.parsed_owner_json)["owner_name"] == "Jan Novak"


def test_parse_orv_requires_both_sides(db_session) -> None:
    owner = _seed_owner(db_session)
    with pytest.raises(vehicles_router.HTTPException) as exc:
        orv_scans.create_orv_scan_record(
            db=db_session,
            current_user=owner,
            front_image_base64=_png_base64((220, 220, 220)),
            back_image_base64="",
            front_image_mime_type="image/png",
            back_image_mime_type="image/png",
            source="ios_orv_scan",
        )

    assert exc.value.status_code == 422


def test_create_vehicle_with_orv_scan_persists_audit_metadata(db_session, monkeypatch, tmp_path: Path) -> None:
    owner = _seed_owner(db_session)
    monkeypatch.setattr(orv_scans, "ORV_SCANS_DIR", tmp_path / "orv_scans")
    monkeypatch.setattr(licensing_service, "assert_vehicle_quota", lambda db, tenant_id: None)

    extracted_texts = iter(
        [
            "Registrační značka: 1AB2345\nČíslo ORV: UVA123456\nVlastník: Jan Novak",
            "VIN: TMBJF73T2B9044629\nZnačka: SKODA\nObchodní označení: OCTAVIA",
        ]
    )
    monkeypatch.setattr(orv_scans, "_extract_ocr_text", lambda *args, **kwargs: next(extracted_texts))

    parsed = vehicles_router.parse_orv(
        payload=vehicles_router.ORVParseRequestV1(
            front_image_base64=_png_base64((10, 10, 10)),
            back_image_base64=_png_base64((30, 30, 30)),
            source="ios_orv_scan",
        ),
        current_user=owner,
        db=db_session,
    )

    created = vehicles_router.create_vehicle(
        vehicle_data=vehicles_router.VehicleCreateV1(
            nickname="Skoda ORV",
            brand="SKODA",
            model="OCTAVIA",
            vin="TMBJF73T2B9044629",
            plate="1AB2345",
            stk_valid_until=date(2030, 1, 1),
            orv_scan_id=parsed["scan_id"],
            orv_number="UVA123456",
            orv_use_owner_data=True,
            data_trust_state="verified_by_user",
        ),
        current_user=owner,
        db=db_session,
    )

    vehicle = db_session.query(VehicleModel).filter(VehicleModel.id == created["id"]).one()
    scan = db_session.query(VehicleORVScan).filter(VehicleORVScan.id == parsed["scan_id"]).one()

    assert vehicle.orv_number == "UVA123456"
    assert vehicle.orv_scan_source == "ios_orv_scan"
    assert vehicle.orv_front_image_path
    assert vehicle.orv_back_image_path
    assert vehicle.data_trust_state == "verified_by_user"
    assert scan.status == "confirmed"
    assert scan.vehicle_id == vehicle.id
    assert scan.use_owner_data is True


def test_create_vehicle_rejects_orv_scan_without_vin(db_session, monkeypatch, tmp_path: Path) -> None:
    owner = _seed_owner(db_session)
    monkeypatch.setattr(orv_scans, "ORV_SCANS_DIR", tmp_path / "orv_scans")
    monkeypatch.setattr(licensing_service, "assert_vehicle_quota", lambda db, tenant_id: None)

    extracted_texts = iter(
        [
            "Registrační značka: 1AB2345\nČíslo ORV: UVA123456",
            "Značka: SKODA\nObchodní označení: OCTAVIA",
        ]
    )
    monkeypatch.setattr(orv_scans, "_extract_ocr_text", lambda *args, **kwargs: next(extracted_texts))

    parsed = vehicles_router.parse_orv(
        payload=vehicles_router.ORVParseRequestV1(
            front_image_base64=_png_base64((90, 90, 90)),
            back_image_base64=_png_base64((120, 120, 120)),
            source="ios_orv_scan",
        ),
        current_user=owner,
        db=db_session,
    )

    response = vehicles_router.create_vehicle(
        vehicle_data=vehicles_router.VehicleCreateV1(
            nickname="Bez VIN",
            brand="SKODA",
            model="OCTAVIA",
            plate="1AB2345",
            stk_valid_until=date(2030, 1, 1),
            orv_scan_id=parsed["scan_id"],
            orv_number="UVA123456",
        ),
        current_user=owner,
        db=db_session,
    )

    assert response.status_code == 422
    assert "VIN" in response.body.decode("utf-8")


def test_parse_orv_handles_multiline_owner_operator_blocks_and_field_confidence() -> None:
    parsed = orv_scans.parse_orv_payload(
        front_text="\n".join(
            [
                "Registrační značka",
                "1AB2345",
                "Číslo ORV",
                "UVA123456",
                "Datum první registrace",
                "01.02.2020",
                "Vlastník",
                "Jan Novak",
                "IČO: 12345678",
                "Ulice 1",
                "Praha 4",
                "Provozovatel",
                "ACME s.r.o.",
                "Servisní 10",
                "Brno",
            ]
        ),
        back_text="\n".join(
            [
                "VIN",
                "TMBJF73T2B9044629",
                "Značka",
                "SKODA",
                "Obchodní označení",
                "OCTAVIA COMBI",
                "Výkon",
                "110 kW",
                "Objem",
                "1395 cm3",
                "Kategorie",
                "M1",
            ]
        ),
    )

    assert parsed.vehicle_fields["vin"] == "TMBJF73T2B9044629"
    assert parsed.vehicle_fields["plate"] == "1AB 2345"
    assert parsed.vehicle_fields["orv_number"] == "UVA123456"
    assert parsed.vehicle_fields["first_registration_date"] == "01.02.2020"
    assert parsed.vehicle_fields["engine_power_kw"] == "110 kW"
    assert parsed.vehicle_fields["engine_displacement_cc"] == "1395 cm3"
    assert parsed.vehicle_fields["category"] == "M1"
    assert parsed.owner_fields["owner_name"] == "Jan Novak"
    assert parsed.owner_fields["owner_identifier"] == "12345678"
    assert parsed.owner_fields["owner_address"] == "Ulice 1, Praha 4"
    assert parsed.owner_fields["operator_name"] == "ACME s.r.o."
    assert parsed.owner_fields["operator_address"] == "Servisní 10, Brno"

    confidence = {item["field_name"]: item for item in parsed.confidence_items}
    assert confidence["vin"]["state"] == "high"
    assert confidence["plate"]["state"] == "high"
    assert confidence["orv_number"]["state"] == "high"
    assert confidence["owner_name"]["confidence"] >= 0.8
    assert confidence["operator_address"]["confidence"] >= 0.6


def test_parse_orv_handles_common_ocr_noise_better() -> None:
    parsed = orv_scans.parse_orv_payload(
        front_text="\n".join(
            [
                "REGISTRACNI ZNACKA: 1AB23 45",
                "CISLO ORV: UVA-123456",
                "DATUM PRVNI REGISTRACE 1.2.2020",
                "VLASTNIK: Jan Novak",
            ]
        ),
        back_text="\n".join(
            [
                "VIN: TMBJF73T2B9O44629",
                "ZNACKA: SKODA",
                "OBCHODNI OZNACENI: OCTAVIA",
                "VYKON: 110 kW",
                "OBJEM: 1395 ccm",
                "KATEGORIE: M1",
            ]
        ),
    )

    assert parsed.vehicle_fields["plate"] == "1AB 2345"
    assert parsed.vehicle_fields["orv_number"] == "UVA123456"
    assert parsed.vehicle_fields["vin"] == "TMBJF73T2B9044629"
    assert parsed.vehicle_fields["engine_displacement_cc"] == "1395 cm3"
    assert parsed.vehicle_fields["engine_power_kw"] == "110 kW"

    confidence = {item["field_name"]: item for item in parsed.confidence_items}
    assert confidence["vin"]["confidence"] >= 0.7
    assert confidence["vin"]["state"] in {"high", "review"}
    assert confidence["first_registration_date"]["state"] == "high"


def test_parse_orv_marks_unlabeled_or_missing_fields_as_review_or_missing() -> None:
    parsed = orv_scans.parse_orv_payload(
        front_text="Jan Novak\nPraha",
        back_text="SKODA\nOCTAVIA\n1395 cm3",
    )

    confidence = {item["field_name"]: item for item in parsed.confidence_items}
    assert parsed.vehicle_fields["vin"] is None
    assert parsed.vehicle_fields["plate"] is None
    assert "vin" in parsed.missing_fields
    assert "plate" in parsed.missing_fields
    assert confidence["vin"]["state"] == "missing"
    assert confidence["plate"]["state"] == "missing"
    assert confidence["brand"]["state"] == "missing"
    assert confidence["owner_name"]["state"] == "missing"
    assert any("VIN" in warning for warning in parsed.warnings)


def test_create_orv_scan_normalizes_large_images_before_ocr(db_session, monkeypatch, tmp_path: Path) -> None:
    owner = _seed_owner(db_session)
    monkeypatch.setattr(orv_scans, "ORV_SCANS_DIR", tmp_path / "orv_scans")

    large_image = Image.new("RGB", (4200, 2800), (240, 240, 240))
    buffer = BytesIO()
    large_image.save(buffer, format="PNG")
    original_bytes = buffer.getvalue()
    payload = base64.b64encode(original_bytes).decode("ascii")

    observed_lengths: list[int] = []
    extracted_texts = iter(
        [
            "Registrační značka: 1AB2345\nČíslo ORV: UVA123456",
            "VIN: TMBJF73T2B9044629\nZnačka: SKODA\nObchodní označení: OCTAVIA",
        ]
    )

    def fake_extract(image_bytes: bytes, *_args, **_kwargs) -> str:
        observed_lengths.append(len(image_bytes))
        return next(extracted_texts)

    monkeypatch.setattr(orv_scans, "_extract_ocr_text", fake_extract)

    scan = orv_scans.create_orv_scan_record(
        db=db_session,
        current_user=owner,
        front_image_base64=payload,
        back_image_base64=payload,
        front_image_mime_type="image/png",
        back_image_mime_type="image/png",
        source="ios_orv_scan",
    )

    assert observed_lengths
    assert all(length < len(original_bytes) for length in observed_lengths)
    assert scan.front_image_path.endswith(".jpg")
    assert scan.back_image_path.endswith(".jpg")
