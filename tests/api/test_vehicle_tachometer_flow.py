from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle as VehicleModel, VehicleMileage
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router


START_HTML = """
<html>
  <body>
    <form action="/Home/Search" method="post">
      <input name="__RequestVerificationToken" type="hidden" value="token-123" />
      <img id="captcha_IMG" src="/Home/CaptchaPartial" />
    </form>
  </body>
</html>
"""

CAPTCHA_ERROR_HTML = """
<html>
  <body>
    <form action="/Home/Search" method="post">
      <input name="__RequestVerificationToken" type="hidden" value="token-456" />
      <div class="validation-summary-errors">Špatně opsaný kód z obrázku</div>
      <img id="captcha_IMG" src="/DXB.axd?DXCache=refresh-456" />
    </form>
  </body>
</html>
"""

RESULT_HTML = """
<html>
  <body>
    <h2>Seznam prohlídek - VIN TMBJF73T2B9044629</h2>
    <table>
      <thead>
        <tr>
          <th>Datum prohlídky</th>
          <th>Prohlídka</th>
          <th>Číslo protokolu</th>
          <th>Druh prohlídky</th>
          <th>Stav km</th>
          <th>Poznámka</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>15.05.2025</td>
          <td>STK</td>
          <td>CZ-3644-25-05-0162</td>
          <td>Evidenční kontrola</td>
          <td>416 588</td>
          <td></td>
          <td><button>Detail prohlídky</button></td>
        </tr>
        <tr>
          <td>22.04.2024</td>
          <td>STK</td>
          <td>CZ-3316-24-04-1239</td>
          <td>Pravidelná</td>
          <td>402 411</td>
          <td></td>
          <td><button>Detail prohlídky</button></td>
        </tr>
      </tbody>
    </table>
  </body>
</html>
"""

RESULT_HTML_WITH_INLINE_DETAIL = """
<html>
  <body>
    <h2>Seznam prohlídek - VIN TMBJF73T2B9044629</h2>
    <table>
      <tbody>
        <tr>
          <td>15.05.2025</td>
          <td>STK</td>
          <td>CZ-3644-25-05-0162</td>
          <td>Evidenční kontrola</td>
          <td>416 588</td>
          <td></td>
          <td><button>Detail prohlídky</button></td>
        </tr>
        <tr class="inspection-detail">
          <td colspan="7">
            <div class="detail-card">
              <h3>Detail prohlídky</h3>
              <p>Zjištěné závady</p>
              <ul>
                <li>B - Netěsnost motoru</li>
                <li>A - Koroze výfuku</li>
              </ul>
              <a href="/protocols/CZ-3644-25-05-0162.pdf">PDF protokol</a>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </body>
</html>
"""

RESULT_HTML_WITH_DETAIL_FORM = """
<html>
  <body>
    <h2>Seznam prohlídek - VIN TMBJF73T2B9044629</h2>
    <table>
      <tbody>
        <tr>
          <td>15.05.2025</td>
          <td>STK</td>
          <td>CZ-3644-25-05-0162</td>
          <td>Evidenční kontrola</td>
          <td>416 588</td>
          <td></td>
          <td>
            <form action="/Home/InspectionDetail" method="post">
              <input type="hidden" name="protocolId" value="CZ-3644-25-05-0162" />
              <button type="submit">Detail prohlídky</button>
            </form>
          </td>
        </tr>
      </tbody>
    </table>
  </body>
</html>
"""

DETAIL_HTML_WITH_FINDINGS = """
<html>
  <body>
    <div class="inspection-detail-body">
      <h3>Detail prohlídky</h3>
      <p>Zjištěné závady</p>
      <ul>
        <li>C - Vážná závada brzdového potrubí</li>
      </ul>
    </div>
  </body>
</html>
"""


def _merge_post_fields(data: dict | None, files: dict | None) -> dict:
    combined: dict = {}
    if data:
        combined.update(dict(data))
    if files:
        for key, value in files.items():
            if isinstance(value, tuple) and len(value) == 2:
                combined[key] = value[1]
            else:
                combined[key] = value
    return combined


class _FakeResponse:
    def __init__(self, text: str = "", content: bytes = b"", status_code: int = 200, headers: dict | None = None):
        self.text = text
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if 400 <= self.status_code:
            raise requests.HTTPError(f"{self.status_code} error")


class _FakeSession:
    last_post_data: dict | None = None

    def __init__(self):
        self.headers = {}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.cookies.set("sessionid", "cookie-123")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url: str, timeout: int = 20):
        if url.rstrip("/").endswith("www.kontrolatachometru.cz"):
            return _FakeResponse(text=START_HTML, status_code=200)
        if url.endswith("/Home/CaptchaPartial"):
            return _FakeResponse(
                content=b"fake-captcha",
                status_code=200,
                headers={"Content-Type": "image/png"},
            )
        raise AssertionError(f"Unexpected GET url: {url}")

    def post(self, url: str, data: dict | None = None, files: dict | None = None, **kwargs: object):
        _FakeSession.last_post_data = _merge_post_fields(data, files)
        if not url.endswith("/Home/Search"):
            raise AssertionError(f"Unexpected POST url: {url}")
        return _FakeResponse(text=RESULT_HTML, status_code=200)


class _FakeSessionHtml500(_FakeSession):
    def post(self, url: str, data: dict | None = None, files: dict | None = None, **kwargs: object):
        _FakeSession.last_post_data = _merge_post_fields(data, files)
        if not url.endswith("/Home/Search"):
            raise AssertionError(f"Unexpected POST url: {url}")
        return _FakeResponse(text="<!DOCTYPE html><html><body>Server Error</body></html>", status_code=500)


class _FakeSessionNoResults(_FakeSession):
    def post(self, url: str, data: dict | None = None, files: dict | None = None, **kwargs: object):
        _FakeSession.last_post_data = _merge_post_fields(data, files)
        if not url.endswith("/Home/Search"):
            raise AssertionError(f"Unexpected POST url: {url}")
        return _FakeResponse(text="<html><body>Bez tabulky</body></html>", status_code=200)


class _FakeSessionInlineDetail(_FakeSession):
    def post(self, url: str, data: dict | None = None, files: dict | None = None, **kwargs: object):
        _FakeSession.last_post_data = _merge_post_fields(data, files)
        if not url.endswith("/Home/Search"):
            raise AssertionError(f"Unexpected POST url: {url}")
        return _FakeResponse(text=RESULT_HTML_WITH_INLINE_DETAIL, status_code=200)


class _FakeSessionDetailForm(_FakeSession):
    def post(self, url: str, data: dict | None = None, files: dict | None = None, **kwargs: object):
        _FakeSession.last_post_data = _merge_post_fields(data, files)
        if url.endswith("/Home/Search"):
            return _FakeResponse(text=RESULT_HTML_WITH_DETAIL_FORM, status_code=200)
        if url.endswith("/Home/InspectionDetail"):
            return _FakeResponse(text=DETAIL_HTML_WITH_FINDINGS, status_code=200)
        raise AssertionError(f"Unexpected POST url: {url}")


class _FakeSessionCaptchaRefresh(_FakeSession):
    def get(self, url: str, timeout: int = 20):
        if url.rstrip("/").endswith("www.kontrolatachometru.cz"):
            return _FakeResponse(text=START_HTML, status_code=200)
        if url.endswith("/Home/CaptchaPartial"):
            return _FakeResponse(
                content=b"initial-captcha",
                status_code=200,
                headers={"Content-Type": "image/png"},
            )
        if "/DXB.axd?DXCache=refresh-456" in url:
            return _FakeResponse(
                content=b"refreshed-captcha",
                status_code=200,
                headers={"Content-Type": "image/png"},
            )
        raise AssertionError(f"Unexpected GET url: {url}")

    def post(self, url: str, data: dict | None = None, files: dict | None = None, **kwargs: object):
        _FakeSession.last_post_data = _merge_post_fields(data, files)
        if not url.endswith("/Home/Search"):
            raise AssertionError(f"Unexpected POST url: {url}")
        return _FakeResponse(text=CAPTCHA_ERROR_HTML, status_code=200)


@pytest.fixture(autouse=True)
def _clear_tachometer_store():
    vehicles_router._TACHOMETER_CHALLENGE_STORE.clear()
    for p in vehicles_router.TACHOMETER_CHALLENGE_PERSIST_DIR.glob("*.tach.pkl"):
        p.unlink(missing_ok=True)
    yield
    vehicles_router._TACHOMETER_CHALLENGE_STORE.clear()
    for p in vehicles_router.TACHOMETER_CHALLENGE_PERSIST_DIR.glob("*.tach.pkl"):
        p.unlink(missing_ok=True)


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "vehicle_tachometer.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_owned_vehicle(db_session):
    tenant = Tenant(name="Tachometer Tenant", license_key="tachometer-tenant-key")
    db_session.add(tenant)
    db_session.flush()

    owner = Customer(
        tenant_id=tenant.id,
        email="driver@example.com",
        password_hash="hash",
        role="user",
    )
    db_session.add(owner)
    db_session.flush()

    vehicle = VehicleModel(
        tenant_id=tenant.id,
        user_email="legacy@example.com",
        nickname="Kontrolované auto",
        vin="TMBJF73T2B9044629",
        stk_valid_until=date(2030, 1, 1),
        current_mileage_km=410_000,
        last_stk_mileage_km=402_411,
    )
    db_session.add(vehicle)
    db_session.flush()

    ensure_vehicle_owner_assignment(
        db_session,
        vehicle=vehicle,
        owner=owner,
        assigned_by_customer_id=owner.id,
    )
    db_session.commit()
    db_session.refresh(owner)
    db_session.refresh(vehicle)
    return owner, vehicle


def test_init_vehicle_tachometer_returns_captcha_for_owned_vehicle(db_session, monkeypatch) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    monkeypatch.setattr(vehicles_router.requests, "Session", _FakeSession)

    response = vehicles_router.init_vehicle_tachometer(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )

    assert response.session_id
    assert response.captcha_image_base64
    stored = vehicles_router._TACHOMETER_CHALLENGE_STORE[response.session_id]
    assert stored["vehicle_id"] == vehicle.id
    assert stored["expected_vin"] == "TMBJF73T2B9044629"


def test_submit_vehicle_tachometer_works_with_challenge_persisted_only(db_session, monkeypatch) -> None:
    """Po vymazání RAM musí submit načíst cookies z perzistentního souboru (např. jiný Gunicorn worker)."""
    owner, vehicle = _seed_owned_vehicle(db_session)
    monkeypatch.setattr(vehicles_router.requests, "Session", _FakeSession)

    init_response = vehicles_router.init_vehicle_tachometer(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )
    p = vehicles_router.TACHOMETER_CHALLENGE_PERSIST_DIR / f"{init_response.session_id}.tach.pkl"
    assert p.is_file()

    vehicles_router._TACHOMETER_CHALLENGE_STORE.clear()

    response = vehicles_router.submit_vehicle_tachometer(
        vehicle_id=vehicle.id,
        payload=vehicles_router.VehicleTachometerSubmitRequest(
            session_id=init_response.session_id,
            captcha_code="2ukkq",
        ),
        current_user=owner,
        db=db_session,
    )
    assert response.latest_mileage_km == 416_588
    assert not p.is_file()


def test_submit_vehicle_tachometer_updates_vehicle_and_creates_audit_record(db_session, monkeypatch) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    monkeypatch.setattr(vehicles_router.requests, "Session", _FakeSession)

    init_response = vehicles_router.init_vehicle_tachometer(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )

    response = vehicles_router.submit_vehicle_tachometer(
        vehicle_id=vehicle.id,
        payload=vehicles_router.VehicleTachometerSubmitRequest(
            session_id=init_response.session_id,
            captcha_code="2ukkq",
        ),
        current_user=owner,
        db=db_session,
    )

    db_session.refresh(vehicle)
    assert _FakeSession.last_post_data is not None
    assert _FakeSession.last_post_data["VIN"] == "TMBJF73T2B9044629"
    assert _FakeSession.last_post_data["captcha$TB"] == "2ukkq"
    assert response.latest_mileage_km == 416_588
    assert response.vehicle.last_stk_mileage_km == 416_588
    assert response.vehicle.current_mileage_km == 416_588
    assert vehicle.last_stk_mileage_km == 416_588
    assert vehicle.current_mileage_km == 416_588
    assert response.inspections[0].protocol_number == "CZ-3644-25-05-0162"

    assert response.created_vehicle_mileage_id is not None
    assert response.created_record_id is None
    vm_row = (
        db_session.query(VehicleMileage)
        .filter(VehicleMileage.id == response.created_vehicle_mileage_id)
        .first()
    )
    assert vm_row is not None
    assert vm_row.mileage_km == 416_588
    assert vm_row.source == "stk"
    assert "kontrolatachometru.cz" in (vm_row.note or "")

    history = vehicles_router.get_vehicle_tachometer_history(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )
    assert len(history) == 2
    assert [item.mileage_km for item in history] == [402_411, 416_588]
    assert history[0].id > 0
    assert history[0].mileage_km == 402_411
    assert history[1].protocol_number == "CZ-3644-25-05-0162"
    assert history[1].inspection_type == "STK"
    assert history[1].inspection_kind == "Evidenční kontrola"
    assert history[1].source == "kontrolatachometru.cz"
    assert history[1].status == "imported"
    assert history[1].read_only is True
    assert history[1].summary
    assert history[1].detail_available is False
    assert history[1].has_documents is False
    assert history[1].documents_count == 0
    assert len(history[1].documents) == 1
    assert history[1].documents[0].available is False
    assert history[1].source_detail_reference == {"kind": "button_label", "label": "Detail prohlídky"}
    assert history[0].is_monotonic_valid is True

    detail = vehicles_router.get_vehicle_tachometer_history_entry_detail(
        vehicle_id=vehicle.id,
        entry_id=history[1].id,
        current_user=owner,
        db=db_session,
    )
    assert detail.protocol_number == "CZ-3644-25-05-0162"
    assert len(detail.documents) == 1
    assert detail.documents[0].available is False
    assert "není dostupný v uložených datech" in str(detail.documents[0].reason)

    documents = vehicles_router.get_vehicle_tachometer_history_entry_documents(
        vehicle_id=vehicle.id,
        entry_id=history[1].id,
        current_user=owner,
        db=db_session,
    )
    assert len(documents) == 1
    assert documents[0].open_mode == "unavailable"


def test_submit_vehicle_tachometer_refreshes_captcha_after_invalid_code(db_session, monkeypatch) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    monkeypatch.setattr(vehicles_router.requests, "Session", _FakeSessionCaptchaRefresh)

    init_response = vehicles_router.init_vehicle_tachometer(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )
    initial_image = init_response.captcha_image_base64

    with pytest.raises(vehicles_router.HTTPException) as exc:
        vehicles_router.submit_vehicle_tachometer(
            vehicle_id=vehicle.id,
            payload=vehicles_router.VehicleTachometerSubmitRequest(
                session_id=init_response.session_id,
                captcha_code="wrong-code",
            ),
            current_user=owner,
            db=db_session,
        )

    assert exc.value.status_code == 422
    assert isinstance(exc.value.detail, dict)
    assert exc.value.detail["code"] == "CAPTCHA_INVALID"
    assert exc.value.detail["message"] == "Špatně opsaný kód z obrázku"
    assert exc.value.detail["session_id"] == init_response.session_id
    assert exc.value.detail["captcha_image_base64"] != initial_image
    stored = vehicles_router._TACHOMETER_CHALLENGE_STORE[init_response.session_id]
    assert stored["request_verification_token"] == "token-456"


def test_parse_tachometer_inspections_extracts_inline_detail_and_documents() -> None:
    inspections = vehicles_router._parse_tachometer_inspections(RESULT_HTML_WITH_INLINE_DETAIL)

    assert len(inspections) == 1
    assert inspections[0].protocol_number == "CZ-3644-25-05-0162"
    assert inspections[0].detail_available is True
    assert inspections[0].findings_summary == "B - Netěsnost motoru • A - Koroze výfuku"
    assert inspections[0].findings_items == ["B - Netěsnost motoru", "A - Koroze výfuku"]
    assert inspections[0].documents[0]["available"] is True
    assert inspections[0].documents[0]["external_url"] == "https://www.kontrolatachometru.cz/protocols/CZ-3644-25-05-0162.pdf"


def test_history_endpoint_returns_detail_available_without_document(db_session, monkeypatch) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    monkeypatch.setattr(vehicles_router.requests, "Session", _FakeSessionDetailForm)

    init_response = vehicles_router.init_vehicle_tachometer(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )
    vehicles_router.submit_vehicle_tachometer(
        vehicle_id=vehicle.id,
        payload=vehicles_router.VehicleTachometerSubmitRequest(
            session_id=init_response.session_id,
            captcha_code="2ukkq",
        ),
        current_user=owner,
        db=db_session,
    )

    history = vehicles_router.get_vehicle_tachometer_history(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )
    detail = vehicles_router.get_vehicle_tachometer_history_entry_detail(
        vehicle_id=vehicle.id,
        entry_id=history[-1].id,
        current_user=owner,
        db=db_session,
    )

    assert detail.detail_available is True
    assert detail.findings_summary == "C - Vážná závada brzdového potrubí"
    assert detail.findings_items == ["C - Vážná závada brzdového potrubí"]
    assert detail.has_documents is False
    assert len(detail.documents) == 1
    assert detail.documents[0].available is False
    assert "detail kontroly" in str(detail.documents[0].reason).lower()


def test_tachometer_history_deduplicates_near_duplicates_and_prefers_higher_km(db_session) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    imported_at = datetime(2026, 1, 10, 10, 0)
    duplicate_low = vehicles_router.VehicleTachometerHistoryEntryModel(
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        check_date=datetime(2024, 4, 22, 8, 0),
        mileage_km=402_410,
        protocol_number="CZ-LOW",
        inspection_type="STK / Pravidelná",
        source="kontrolatachometru.cz",
        status="imported",
        summary="Nižší km",
        imported_at=imported_at,
        last_seen_at=imported_at,
    )
    duplicate_high = vehicles_router.VehicleTachometerHistoryEntryModel(
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        check_date=datetime(2024, 4, 22, 8, 0),
        mileage_km=402_411,
        protocol_number="CZ-HIGH",
        inspection_type="STK / Pravidelná",
        source="kontrolatachometru.cz",
        status="imported",
        summary="Vyšší km",
        imported_at=imported_at,
        last_seen_at=imported_at,
    )
    db_session.add_all([duplicate_low, duplicate_high])
    db_session.commit()

    history = vehicles_router.get_vehicle_tachometer_history(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )

    assert len(history) == 1
    assert history[0].mileage_km == 402_411
    assert history[0].merged_duplicate_count == 1
    assert sorted(history[0].merged_entry_ids) == sorted([duplicate_low.id, duplicate_high.id])
    assert history[0].merge_reason is not None


def test_tachometer_history_marks_km_decrease_as_anomaly(db_session) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    imported_at = datetime(2026, 1, 10, 10, 0)
    older = vehicles_router.VehicleTachometerHistoryEntryModel(
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        check_date=datetime(2024, 4, 22, 8, 0),
        mileage_km=402_411,
        protocol_number="CZ-1",
        inspection_type="STK / Pravidelná",
        source="kontrolatachometru.cz",
        status="imported",
        summary="Older",
        imported_at=imported_at,
        last_seen_at=imported_at,
    )
    decreased = vehicles_router.VehicleTachometerHistoryEntryModel(
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        check_date=datetime(2025, 5, 15, 8, 0),
        mileage_km=402_410,
        protocol_number="CZ-2",
        inspection_type="STK / Evidenční kontrola",
        source="kontrolatachometru.cz",
        status="imported",
        summary="Decreased",
        imported_at=imported_at,
        last_seen_at=imported_at,
    )
    later = vehicles_router.VehicleTachometerHistoryEntryModel(
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        check_date=datetime(2026, 5, 15, 8, 0),
        mileage_km=416_588,
        protocol_number="CZ-3",
        inspection_type="STK / Evidenční kontrola",
        source="kontrolatachometru.cz",
        status="imported",
        summary="Later",
        imported_at=imported_at,
        last_seen_at=imported_at,
    )
    db_session.add_all([older, decreased, later])
    db_session.commit()

    history = vehicles_router.get_vehicle_tachometer_history(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )

    assert [item.mileage_km for item in history] == [402_411, 402_410, 416_588]
    assert history[0].anomaly is False
    assert history[1].anomaly is True
    assert history[1].anomaly_type == "km_decrease"
    assert history[1].anomaly_delta_km == -1
    assert history[1].is_monotonic_valid is False
    assert history[2].anomaly is False


def test_tachometer_history_output_is_stable_and_deterministic(db_session) -> None:
    imported_at = datetime(2026, 1, 10, 10, 0)
    tenant = Tenant(name="Stable Tenant", license_key="stable-tenant-key")
    db_session.add(tenant)
    db_session.flush()
    owner = Customer(
        tenant_id=tenant.id,
        email="stable@example.com",
        password_hash="hash",
        role="user",
    )
    db_session.add(owner)
    db_session.flush()
    vehicle = VehicleModel(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Stable Car",
        vin="TMBJF73T2B9044630",
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
    db_session.add_all([
        vehicles_router.VehicleTachometerHistoryEntryModel(
            tenant_id=vehicle.tenant_id,
            vehicle_id=vehicle.id,
            check_date=datetime(2025, 5, 15, 8, 0),
            mileage_km=416_588,
            protocol_number="CZ-3",
            inspection_type="C",
            source="kontrolatachometru.cz",
            status="imported",
            summary="3",
            imported_at=imported_at,
            last_seen_at=imported_at,
        ),
        vehicles_router.VehicleTachometerHistoryEntryModel(
            tenant_id=vehicle.tenant_id,
            vehicle_id=vehicle.id,
            check_date=datetime(2024, 4, 22, 8, 0),
            mileage_km=402_411,
            protocol_number="CZ-1",
            inspection_type="A",
            source="kontrolatachometru.cz",
            status="imported",
            summary="1",
            imported_at=imported_at,
            last_seen_at=imported_at,
        ),
        vehicles_router.VehicleTachometerHistoryEntryModel(
            tenant_id=vehicle.tenant_id,
            vehicle_id=vehicle.id,
            check_date=datetime(2024, 4, 22, 8, 0),
            mileage_km=402_410,
            protocol_number="CZ-2",
            inspection_type="B",
            source="kontrolatachometru.cz",
            status="imported",
            summary="2",
            imported_at=imported_at,
            last_seen_at=imported_at,
        ),
    ])
    db_session.commit()

    first = vehicles_router.get_vehicle_tachometer_history(vehicle_id=vehicle.id, current_user=owner, db=db_session)
    second = vehicles_router.get_vehicle_tachometer_history(vehicle_id=vehicle.id, current_user=owner, db=db_session)

    assert [(item.id, item.mileage_km, item.merged_duplicate_count) for item in first] == [
        (item.id, item.mileage_km, item.merged_duplicate_count) for item in second
    ]


def test_submit_vehicle_tachometer_returns_friendly_expired_message_for_html_500(db_session, monkeypatch) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    monkeypatch.setattr(vehicles_router.requests, "Session", _FakeSessionHtml500)

    init_response = vehicles_router.init_vehicle_tachometer(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )

    with pytest.raises(vehicles_router.HTTPException) as exc:
        vehicles_router.submit_vehicle_tachometer(
            vehicle_id=vehicle.id,
            payload=vehicles_router.VehicleTachometerSubmitRequest(
                session_id=init_response.session_id,
                captcha_code="2ukkq",
            ),
            current_user=owner,
            db=db_session,
        )

    assert exc.value.status_code == 410
    assert "Captcha session vypršela nebo je neplatná" in str(exc.value.detail)


def test_submit_vehicle_tachometer_returns_not_found_when_no_rows_exist(db_session, monkeypatch) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    monkeypatch.setattr(vehicles_router.requests, "Session", _FakeSessionNoResults)

    init_response = vehicles_router.init_vehicle_tachometer(
        vehicle_id=vehicle.id,
        current_user=owner,
        db=db_session,
    )

    with pytest.raises(vehicles_router.HTTPException) as exc:
        vehicles_router.submit_vehicle_tachometer(
            vehicle_id=vehicle.id,
            payload=vehicles_router.VehicleTachometerSubmitRequest(
                session_id=init_response.session_id,
                captcha_code="2ukkq",
            ),
            current_user=owner,
            db=db_session,
        )

    assert exc.value.status_code == 404
    assert "nebyly nalezeny žádné údaje STK/emisí" in str(exc.value.detail)
