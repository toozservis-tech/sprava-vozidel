from __future__ import annotations

import unicodedata
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core import config as core_config
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.mileage_reports import (
    MANUAL_MILEAGE_DESCRIPTION,
    TACHOMETER_IMPORT_DESCRIPTION,
    build_mileage_timeline_payload,
    collect_vehicle_mileage_timeline_points,
    render_mileage_timeline_chart_png,
)
from src.modules.vehicle_hub.models import (
    Customer,
    License,
    ServiceIntake,
    ServiceRecord,
    Tenant,
    Vehicle as VehicleModel,
    VehicleOwnership,
    VehicleTachometerHistoryEntry,
)
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import service_records as service_records_router


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "vehicle_pdf_mileage_chart.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _grant_basic_license_docs(db_session, tenant_id: int) -> None:
    """BASIC má documents_enabled — nutné pro PDF / mileage timeline API v testech."""
    now = datetime.utcnow()
    lic = db_session.query(License).filter(License.tenant_id == tenant_id).first()
    if lic:
        lic.plan = "basic"
        lic.status = "active"
        lic.vehicles_limit = 3
        lic.updated_at = now
        return
    db_session.add(
        License(
            tenant_id=tenant_id,
            plan="basic",
            status="active",
            vehicles_limit=3,
            valid_from=now,
            valid_to=None,
            vin_decode_enabled=False,
            ares_enabled=True,
            reminders_enabled=True,
        )
    )


def _seed_owned_vehicle(db_session):
    tenant = Tenant(name="PDF Tenant", license_key="pdf-tenant-key")
    db_session.add(tenant)
    db_session.flush()

    owner = Customer(
        tenant_id=tenant.id,
        email="pdf-driver@example.com",
        password_hash="hash",
        role="user",
    )
    db_session.add(owner)
    db_session.flush()

    vehicle = VehicleModel(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Report Car",
        plate="1AB2345",
        vin="WAUZZZ8V1JA000001",
        stk_valid_until=date(2030, 1, 1),
    )
    db_session.add(vehicle)
    db_session.flush()

    ensure_vehicle_owner_assignment(
        db_session,
        vehicle=vehicle,
        owner=owner,
        assigned_by_customer_id=owner.id,
    )
    _grant_basic_license_docs(db_session, tenant.id)
    db_session.commit()
    db_session.refresh(owner)
    db_session.refresh(vehicle)
    return owner, vehicle


def _seed_multi_source_points(db_session, vehicle: VehicleModel) -> None:
    db_session.add_all(
        [
            ServiceRecord(
                tenant_id=vehicle.tenant_id,
                vehicle_id=vehicle.id,
                performed_at=datetime(2024, 1, 10, 9, 0),
                mileage=100_000,
                description="Výměna oleje",
                category="OLEJ",
                is_deleted=False,
            ),
            ServiceRecord(
                tenant_id=vehicle.tenant_id,
                vehicle_id=vehicle.id,
                performed_at=datetime(2024, 2, 1, 10, 0),
                mileage=105_000,
                description=MANUAL_MILEAGE_DESCRIPTION,
                category="JINE",
                is_deleted=False,
            ),
            ServiceRecord(
                tenant_id=vehicle.tenant_id,
                vehicle_id=vehicle.id,
                performed_at=datetime(2024, 3, 5, 8, 30),
                mileage=110_000,
                description=TACHOMETER_IMPORT_DESCRIPTION,
                category="STK",
                is_deleted=False,
            ),
            ServiceIntake(
                tenant_id=vehicle.tenant_id,
                service_id=1,
                vehicle_id=vehicle.id,
                customer_id=1,
                odometer_km=102_000,
                created_at=datetime(2024, 1, 20, 8, 0),
            ),
            VehicleTachometerHistoryEntry(
                tenant_id=vehicle.tenant_id,
                vehicle_id=vehicle.id,
                check_date=datetime(2024, 3, 5, 8, 30),
                mileage_km=110_000,
                protocol_number="CZ-1111",
                inspection_type="STK / Pravidelná",
                source="kontrolatachometru.cz",
                status="imported",
                summary="STK / Pravidelná",
                imported_at=datetime(2024, 3, 5, 8, 35),
                last_seen_at=datetime(2024, 3, 5, 8, 35),
            ),
        ]
    )
    db_session.commit()


def _normalize_ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def test_collects_points_from_multiple_sources(db_session) -> None:
    _, vehicle = _seed_owned_vehicle(db_session)
    _seed_multi_source_points(db_session, vehicle)

    points = collect_vehicle_mileage_timeline_points(db_session, vehicle.id)

    assert [(point.source_type, point.mileage_km) for point in points] == [
        ("service", 100_000),
        ("service", 102_000),
        ("manual", 105_000),
        ("stk", 110_000),
    ]


def test_points_are_sorted_chronologically(db_session) -> None:
    _, vehicle = _seed_owned_vehicle(db_session)
    _seed_multi_source_points(db_session, vehicle)

    points = collect_vehicle_mileage_timeline_points(db_session, vehicle.id)

    assert [point.date for point in points] == sorted(point.date for point in points)


def test_detects_rollback(db_session) -> None:
    _, vehicle = _seed_owned_vehicle(db_session)
    db_session.add_all(
        [
            ServiceRecord(
                tenant_id=vehicle.tenant_id,
                vehicle_id=vehicle.id,
                performed_at=datetime(2024, 1, 1, 9, 0),
                mileage=120_000,
                description="Servis",
                is_deleted=False,
            ),
            ServiceRecord(
                tenant_id=vehicle.tenant_id,
                vehicle_id=vehicle.id,
                performed_at=datetime(2024, 1, 15, 9, 0),
                mileage=118_000,
                description=MANUAL_MILEAGE_DESCRIPTION,
                is_deleted=False,
            ),
        ]
    )
    db_session.commit()

    points = collect_vehicle_mileage_timeline_points(db_session, vehicle.id)

    assert "rollback" in points[-1].anomaly_flags
    assert points[-1].anomaly == "rollback"


def test_detects_same_day_near_duplicate(db_session) -> None:
    _, vehicle = _seed_owned_vehicle(db_session)
    db_session.add_all(
        [
            ServiceRecord(
                tenant_id=vehicle.tenant_id,
                vehicle_id=vehicle.id,
                performed_at=datetime(2024, 6, 1, 8, 0),
                mileage=50_000,
                description="Servis A",
                is_deleted=False,
            ),
            ServiceRecord(
                tenant_id=vehicle.tenant_id,
                vehicle_id=vehicle.id,
                performed_at=datetime(2024, 6, 1, 16, 0),
                mileage=50_040,
                description="Servis B",
                is_deleted=False,
            ),
        ]
    )
    db_session.commit()

    points = collect_vehicle_mileage_timeline_points(db_session, vehicle.id)

    assert all("duplicate" in p.anomaly_flags for p in points)


def test_detects_suspicious_jump(db_session) -> None:
    _, vehicle = _seed_owned_vehicle(db_session)
    db_session.add_all(
        [
            ServiceRecord(
                tenant_id=vehicle.tenant_id,
                vehicle_id=vehicle.id,
                performed_at=datetime(2024, 1, 1, 9, 0),
                mileage=100_000,
                description="Servis",
                is_deleted=False,
            ),
            ServiceRecord(
                tenant_id=vehicle.tenant_id,
                vehicle_id=vehicle.id,
                performed_at=datetime(2024, 1, 10, 9, 0),
                mileage=130_500,
                description="Další servis",
                is_deleted=False,
            ),
        ]
    )
    db_session.commit()

    points = collect_vehicle_mileage_timeline_points(db_session, vehicle.id)

    assert "suspicious_jump" in points[-1].anomaly_flags


def test_detects_suspicious_jump_by_high_daily_rate(db_session) -> None:
    _, vehicle = _seed_owned_vehicle(db_session)
    db_session.add_all(
        [
            ServiceRecord(
                tenant_id=vehicle.tenant_id,
                vehicle_id=vehicle.id,
                performed_at=datetime(2024, 1, 1, 9, 0),
                mileage=100_000,
                description="Start",
                is_deleted=False,
            ),
            ServiceRecord(
                tenant_id=vehicle.tenant_id,
                vehicle_id=vehicle.id,
                performed_at=datetime(2024, 1, 6, 9, 0),
                mileage=112_000,
                description="High daily implied",
                is_deleted=False,
            ),
        ]
    )
    db_session.commit()

    points = collect_vehicle_mileage_timeline_points(db_session, vehicle.id)

    assert "suspicious_jump" in points[-1].anomaly_flags


def test_renders_mileage_chart_png_without_crash(db_session) -> None:
    _, vehicle = _seed_owned_vehicle(db_session)
    _seed_multi_source_points(db_session, vehicle)

    points = collect_vehicle_mileage_timeline_points(db_session, vehicle.id)
    png_bytes = render_mileage_timeline_chart_png(points)

    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png_bytes) > 1_000


def test_pdf_report_embeds_mileage_chart_image(db_session, monkeypatch, tmp_path: Path) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    _seed_multi_source_points(db_session, vehicle)
    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core_config, "PDF_DIR", pdf_dir)

    response = service_records_router.generate_service_records_pdf(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )

    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF")
    assert b"/Subtype /Image" in response.body


def test_pdf_report_with_chart_is_valid_and_readable(db_session, monkeypatch, tmp_path: Path) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    _seed_multi_source_points(db_session, vehicle)
    pdf_dir = tmp_path / "pdf-readable"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core_config, "PDF_DIR", pdf_dir)

    response = service_records_router.generate_service_records_pdf(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )

    normalized_pdf = _normalize_ascii(response.body.decode("latin-1", errors="ignore")).upper()

    assert response.body.startswith(b"%PDF")
    assert b"%%EOF" in response.body
    assert normalized_pdf.count("/TYPE /PAGE") >= 1
    assert len(response.body) > 5_000


def test_mileage_timeline_api_payload(db_session) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    _seed_multi_source_points(db_session, vehicle)

    out = service_records_router.get_vehicle_mileage_timeline(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )

    assert "mileage_timeline" in out
    mt = out["mileage_timeline"]
    assert "points" in mt and "summary" in mt
    summary = mt["summary"]
    assert summary["point_count"] == len(mt["points"])
    assert summary["first_mileage_km"] == mt["points"][0]["mileage_km"]
    assert summary["last_mileage_km"] == mt["points"][-1]["mileage_km"]
    assert summary["anomaly_point_count"] >= 0
    assert "anomaly_counts" in summary


def test_build_mileage_timeline_payload_matches_collect(db_session) -> None:
    _, vehicle = _seed_owned_vehicle(db_session)
    _seed_multi_source_points(db_session, vehicle)

    payload = build_mileage_timeline_payload(db_session, vehicle.id)
    direct = collect_vehicle_mileage_timeline_points(db_session, vehicle.id)

    assert len(payload["mileage_timeline"]["points"]) == len(direct)
