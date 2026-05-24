"""
Vehicles API v1.0 router
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
import base64
import binascii
import html
from io import BytesIO
import json
import mimetypes
import os
import pickle
from pathlib import Path
import re
import secrets
import time
import threading
import unicodedata
from urllib.parse import urljoin

from requests.cookies import RequestsCookieJar

from fastapi import APIRouter, HTTPException, Depends, Body, Request
from fastapi.responses import FileResponse, Response, JSONResponse
from pydantic import BaseModel, Field
import requests
from sqlalchemy import func, nullslast
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Any, Dict, List, Optional

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except Exception:
        pass
    PILLOW_AVAILABLE = True
except Exception:
    Image = None
    ImageOps = None
    UnidentifiedImageError = Exception
    PILLOW_AVAILABLE = False

from src.core import config as app_config
from src.core.config import DATA_DIR
from src.core.rbac import is_admin, is_service, normalize_role, vehicle_write_policy
from src.server.security_tracking import extract_client_ip
from ..tachometer_parser import normalize_result as normalize_tachometer_result
from ..database import get_db
from ..audit_log import write_global_audit_log
from ..tachometer_browser import (
    TachometerBrowserError,
    TachometerBrowserInvalidCaptcha,
    TachometerBrowserSessionExpired,
    create_browser_session,
    get_browser_session_captcha,
    submit_browser_session,
)
from ..models import (
    Vehicle as VehicleModel,
    VehicleCatalogImage as VehicleCatalogImageModel,
    VehiclePhoto as VehiclePhotoModel,
    VehiclePhotoAsset as VehiclePhotoAssetModel,
    VehicleMileage as VehicleMileageModel,
    VehicleQrToken as VehicleQrTokenModel,
    Customer,
    GlobalAuditLog as GlobalAuditLogModel,
    ServiceInvoice,
    ServiceRecord as ServiceRecordModel,
    VehicleTachometerHistoryEntry as VehicleTachometerHistoryEntryModel,
)
from ..orv_scans import apply_orv_review_audit, apply_orv_scan_to_vehicle, create_orv_scan_record, serialize_orv_scan
from ..ownership import (
    backfill_vehicle_owner_assignment,
    ensure_vehicle_owner_assignment,
    get_current_owner_since,
    get_primary_vehicle_owner,
    get_primary_vehicle_owner_assignment,
    release_vehicle_owner_assignment,
    transfer_vehicle_to_new_owner,
    user_owns_vehicle,
)
from ..schema_management import assert_module_ready
from ..vehicle_photo_assets import (
    build_main_storage_key,
    jpeg_dimensions,
    resolve_storage_file,
    sha256_hex,
)
from ..vehicle_public_history import build_public_history_page_url, render_vehicle_qr_svg
from ..services.catalog_image_service import (
    LOCAL_CATALOG_ROUTE,
    PLACEHOLDER_URL as CATALOG_PLACEHOLDER_URL,
    ensure_catalog_image_storage,
    get_vehicle_catalog_image_service,
    resolve_catalog_image_storage_file,
)
from ..decoder.models import VinDecodeRequest, VehicleDecodeResponse, VehicleDecodedData
from ..vin_ownership_guard import (
    VinAlreadyRegisteredOtherUserError,
    assert_vin_visible_for_create,
    vin_other_tenant_block_payload,
)

logger = logging.getLogger(__name__)
from .auth import get_current_user, can_access_vehicle


def _finalize_vehicle_technical_overview(db: Session, vehicle: VehicleModel) -> None:
    """Druhý zápis — strukturovaný přehled ze VIN/MDČR. Selhání nesmí zablokovat vlastní vozidlo."""
    try:
        from ..services.vehicle_technical_overview import persist_vehicle_technical_overview

        persist_vehicle_technical_overview(db, vehicle)
        db.commit()
        db.refresh(vehicle)
    except Exception as exc:
        logger.warning(
            "[VEHICLE] vehicle_technical_overview persist skipped vehicle_id=%s err=%s",
            getattr(vehicle, "id", None),
            exc,
            exc_info=True,
        )
        try:
            db.rollback()
        except Exception:
            pass


from .schemas import (
    VehicleCreateV1,
    VehicleUpdateV1,
    VehicleOutV1,
    VehicleMileageLogEntryOutV1,
    VehicleMileageRecordResultV1,
    VehicleMileageRecordV1,
    ORVParseRequestV1,
    ORVParseResponseV1,
    ORVReviewAuditRequestV1,
    ORVReviewAuditResponseV1,
    VehicleCatalogImageGenerateRequestV1,
    VehiclePreviewFromVinRequestV1,
    VehiclePreviewFromVinResponseV1,
)

router = APIRouter(prefix="/vehicles", tags=["vehicles-v1"])

VEHICLE_PHOTOS_DIR = DATA_DIR / "vehicle_photos"
VEHICLE_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
VEHICLE_UPLOADS_VEHICLES_DIR = DATA_DIR / "uploads" / "vehicles"
VEHICLE_UPLOADS_VEHICLES_DIR.mkdir(parents=True, exist_ok=True)
MAX_VEHICLE_PHOTO_RAW_SIZE_BYTES = 40 * 1024 * 1024
MAX_VEHICLE_PHOTO_OUTPUT_SIZE_BYTES = 10 * 1024 * 1024
VEHICLE_PHOTO_TARGET_SIZE = (1280, 720)
VEHICLE_PHOTO_JPEG_QUALITY = 82
VEHICLE_PHOTO_MIN_JPEG_QUALITY = 52
MAX_VEHICLE_GALLERY_PHOTOS = 24
PRIMARY_PHOTO_CLIENT_MARKER = "__primary_photo__"


def _canonical_catalog_vehicle_fields(
    catalog_image_id: str | None,
    catalog_image_url: str | None,
) -> tuple[str | None, str | None]:
    """
    Sjednotí katalogové odkazy pro uložení na vozidle: při zaslání jen ID doplní interní /file URL.
    Placeholder SVG se pro DB ukládání ignoruje (bez ID neukládáme prázdný náhled jako URL).
    """
    cid = str(catalog_image_id or "").strip() or None
    curl = str(catalog_image_url or "").strip()
    if curl == CATALOG_PLACEHOLDER_URL:
        curl = ""
    if cid and not curl:
        curl = LOCAL_CATALOG_ROUTE.format(image_id=cid)
    return cid, curl or None


def _catalog_image_url_for_gallery_import(catalog_image_id: str | None, catalog_image_url: str | None) -> str | None:
    """Zdrojová URL pro _store_catalog_image_in_gallery — musí být platná vzdálená nebo interní /catalog-images/... URL."""
    cid, curl = _canonical_catalog_vehicle_fields(catalog_image_id, catalog_image_url)
    if not curl or curl == CATALOG_PLACEHOLDER_URL:
        return None
    return curl


def _maybe_autoset_primary_from_catalog_gallery_row(
    db: Session,
    *,
    vehicle: VehicleModel,
    gallery_asset_id: int | None,
    current_user: Customer,
    replace_existing: bool = False,
) -> None:
    """Po uložení ilustrační fotky do galerie ji nastaví jako hlavní fotku vozidla."""
    if not gallery_asset_id:
        return
    if not replace_existing and _resolve_primary_photo_file(vehicle=vehicle, db=db):
        return
    row = (
        db.query(VehiclePhotoAssetModel)
        .filter(
            VehiclePhotoAssetModel.id == int(gallery_asset_id),
            VehiclePhotoAssetModel.vehicle_id == int(vehicle.id),
            VehiclePhotoAssetModel.role == "gallery",
            VehiclePhotoAssetModel.deleted_at.is_(None),
        )
        .first()
    )
    if row is None:
        return
    gallery_file = resolve_storage_file(VEHICLE_PHOTOS_DIR, row.storage_key)
    if not gallery_file or not gallery_file.is_file():
        return
    try:
        normalized_content = _normalize_vehicle_photo(gallery_file.read_bytes())
    except HTTPException:
        logger.warning(
            "[CATALOG_IMAGE] autoset primary skipped reason=normalize_failed vehicle_id=%s gallery_id=%s",
            vehicle.id,
            gallery_asset_id,
        )
        return
    _persist_primary_vehicle_photo(
        vehicle=vehicle,
        current_user=current_user,
        normalized_content=normalized_content,
        db=db,
        audit_action="primary_photo_set_from_catalog_image",
        metadata={"gallery_photo_asset_id": int(gallery_asset_id)},
    )


def _catalog_image_regen_limit_enabled() -> bool:
    return bool(getattr(app_config, "VEHICLE_IMAGE_REGEN_LIMIT_ENABLED", True))


def _remaining_catalog_image_regenerations(
    db: Session,
    *,
    vehicle_id: int,
    vehicle: VehicleModel | None = None,
) -> int:
    """Zbývající pokusy při zapnutém limitu (základně max. jedno generování na vozidlo).

    Nemá-li vozidlo použitelnou hlavní fotku (uživatel ji smazal / rozbitý odkaz), vrátíme vždy
    alespoň 1 — aby šlo znovu vygenerovat katalogovou ilustraci a obnovit úvodní snímek.
    """
    if not _catalog_image_regen_limit_enabled():
        return 999
    base = max(0, 1 - _count_catalog_image_regenerations(db, vehicle_id=int(vehicle_id)))
    v = vehicle
    if v is None:
        v = db.query(VehicleModel).filter(VehicleModel.id == int(vehicle_id)).first()
    if v is not None and _resolve_primary_photo_file(vehicle=v, db=db) is None:
        return max(base, 1)
    return base


def _write_bytes_to_vehicle_photos_file(target_file: Path, content: bytes) -> None:
    """Uloží soubor pod VEHICLE_PHOTOS_DIR; srozumitelná odpověď při chybějících oprávněních (EACCES)."""
    try:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_bytes(content)
    except OSError as exc:
        errno = getattr(exc, "errno", None)
        if errno == 13 or isinstance(exc, PermissionError):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Server nemá oprávnění zapisovat do úložiště fotek. "
                    f"Kontaktujte správce: {VEHICLE_PHOTOS_DIR.resolve()} musí být zapisovatelný pro účet, "
                    "pod kterým běží backend (příkaz např. chown -R <uživatel_aplikace> tento adresář)."
                ),
            ) from exc
        raise HTTPException(status_code=500, detail=f"Uložení souboru selhalo: {exc}") from exc


class VehiclePhotoUploadRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    file_mime_type: str = Field(default="image/jpeg", max_length=255)
    file_content_base64: str = Field(..., min_length=20, max_length=60_000_000)
    # Volitelně celý zdrojový snímek (telefon) — v galerii se zobrazí ořez, originál zůstane v úložišti.
    original_file_content_base64: Optional[str] = Field(default=None, max_length=60_000_000)
    original_file_name: Optional[str] = Field(default=None, max_length=255)
    original_file_mime_type: Optional[str] = Field(default=None, max_length=255)


def _unlink_gallery_original_file(storage_key_or_none: Optional[str]) -> None:
    if not storage_key_or_none:
        return
    candidate = resolve_storage_file(VEHICLE_PHOTOS_DIR, str(storage_key_or_none).strip())
    if candidate and candidate.is_file():
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass


def _validate_and_store_gallery_original_bytes(
    *,
    raw_b64: Optional[str],
    suggested_name: Optional[str],
    suggested_mime: Optional[str],
    tenant_id: int,
    vehicle_id: int,
) -> Optional[str]:
    """
    Dekóduje a uloží originál vedle ořezu. Vrací relativní storage_key pro sloupec storage_path_original.
    """
    if not raw_b64 or not str(raw_b64).strip():
        return None
    content = _decode_base64_payload(str(raw_b64).strip())
    if not content:
        raise HTTPException(status_code=422, detail="Originál fotky je prázdný.")
    if len(content) > MAX_VEHICLE_PHOTO_RAW_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Originál je příliš velký (max 40 MB).")
    mime = str(suggested_mime or "").lower().strip()
    if mime and not mime.startswith("image/"):
        raise HTTPException(status_code=415, detail="Originál musí být obrázek.")
    if not PILLOW_AVAILABLE:
        raise HTTPException(status_code=503, detail="Server není připraven na ukládání originálu fotky (Pillow).")
    try:
        with Image.open(BytesIO(content)) as im:
            im.load()
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=422, detail="Originál není platný obrázek.") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Originál se nepodařilo načíst jako obrázek.") from exc

    base_name = str(suggested_name or "original.jpg").strip() or "original.jpg"
    ext = Path(base_name).suffix.lower()
    allowed = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".bmp"}
    if ext not in allowed:
        ext = ".jpg"
    fname = f"gallery_orig_{secrets.token_hex(10)}{ext}"
    storage_key = build_main_storage_key(tenant_id=tenant_id, vehicle_id=int(vehicle_id), filename=fname)
    target_file = VEHICLE_PHOTOS_DIR / storage_key
    _write_bytes_to_vehicle_photos_file(target_file, content)
    return storage_key


TACHOMETER_BASE_URL = "https://www.kontrolatachometru.cz"
TACHOMETER_LANDING_PATH = "/"
TACHOMETER_SEARCH_PATH = "/Home/Search"
TACHOMETER_CHALLENGE_TTL_SECONDS = 10 * 60
_TACHOMETER_HTTP_TIMEOUT_SECONDS = 20
_TACHOMETER_CAPTCHA_ERROR_TEXT = "Špatně opsaný kód z obrázku"
_TACHOMETER_CHALLENGE_PERSIST_V = 1
TACHOMETER_CHALLENGE_PERSIST_DIR = DATA_DIR / "tachometer_challenges"
TACHOMETER_CHALLENGE_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
_TACHOMETER_CHALLENGE_STORE: Dict[str, Dict[str, Any]] = {}
_TACHOMETER_CHALLENGE_LOCK = threading.Lock()


class TachometerChallengeResponse(BaseModel):
    challenge_id: str
    captcha_image_base64: str
    captcha_mime_type: str
    expires_in_seconds: int


class TachometerChallengeRequest(BaseModel):
    vin: Optional[str] = Field(default=None, min_length=5, max_length=32)


class TachometerLookupRequest(BaseModel):
    challenge_id: str = Field(..., min_length=10, max_length=255)
    vin: str = Field(..., min_length=5, max_length=32)
    captcha_code: str = Field(..., min_length=2, max_length=16)


class TachometerInspectionOut(BaseModel):
    check_date: Optional[datetime] = None
    mileage_km: int
    protocol_number: Optional[str] = None
    inspection_type: Optional[str] = None
    inspection_kind: Optional[str] = None
    result_label: Optional[str] = None
    note_text: Optional[str] = None
    findings_summary: Optional[str] = None
    findings_items: List[str] = []
    detail_available: bool = False
    detail_snapshot_json: Optional[Dict[str, Any]] = None
    source_detail_reference: Optional[Dict[str, Any]] = None
    documents: List[Dict[str, Any]] = []


class TachometerLookupResponse(BaseModel):
    vin: str
    latest_mileage_km: int
    latest_check_date: Optional[datetime] = None
    inspections: List[TachometerInspectionOut]
    source: str = "kontrolatachometru.cz"


class VehicleTachometerStartRequest(BaseModel):
    vin: str = Field(..., min_length=5, max_length=32)


class VehicleTachometerStartResponse(BaseModel):
    session_id: str
    captcha_image: str
    captcha_image_url: Optional[str] = None
    expires_in_seconds: int


class VehicleTachometerFinishRequest(BaseModel):
    session_id: str = Field(..., min_length=10, max_length=255)
    captcha_code: str = Field(..., min_length=2, max_length=16)
    confirm_lower_than_current: bool = False


class VehicleTachometerFinishResponse(BaseModel):
    vehicle: VehicleOutV1
    latest_mileage_km: int
    latest_check_date: Optional[datetime] = None
    inspections: List[TachometerInspectionOut]
    created_record_id: Optional[int] = None
    created_vehicle_mileage_id: Optional[int] = None
    source: str = "kontrolatachometru.cz"


class VehicleTachometerInitResponse(BaseModel):
    session_id: str
    captcha_image_base64: str
    captcha_mime_type: str
    expires_in_seconds: int


class VehicleTachometerSubmitRequest(BaseModel):
    session_id: str = Field(..., min_length=10, max_length=255)
    captcha_code: str = Field(..., min_length=2, max_length=16)
    confirm_lower_than_current: bool = False


class VehicleTachometerSubmitResponse(BaseModel):
    vehicle: VehicleOutV1
    latest_mileage_km: int
    latest_check_date: Optional[datetime] = None
    inspections: List[TachometerInspectionOut]
    created_record_id: Optional[int] = None
    created_vehicle_mileage_id: Optional[int] = None
    source: str = "kontrolatachometru.cz"


class VehicleTachometerHistoryEntryResponse(BaseModel):
    id: int
    check_date: Optional[datetime] = None
    mileage_km: Optional[int] = None
    protocol_number: Optional[str] = None
    inspection_type: Optional[str] = None
    inspection_kind: Optional[str] = None
    result_label: Optional[str] = None
    note_text: Optional[str] = None
    source: Optional[str] = None
    status: str = "imported"
    read_only: bool = True
    summary: Optional[str] = None
    findings_summary: Optional[str] = None
    findings_items: List[str] = []
    detail_available: bool = False
    detail_snapshot_json: Optional[Dict[str, Any]] = None
    source_detail_reference: Optional[Dict[str, Any]] = None
    is_monotonic_valid: bool = True
    anomaly: bool = False
    anomaly_type: Optional[str] = None
    anomaly_delta_km: Optional[int] = None
    merged_duplicate_count: int = 0
    merged_entry_ids: List[int] = []
    merge_reason: Optional[str] = None
    has_documents: bool = False
    documents_count: int = 0
    documents: List[VehicleTachometerDocumentResponse] = []


class VehicleTachometerDocumentResponse(BaseModel):
    document_id: str
    title: str
    document_type: str
    available: bool
    open_mode: str
    reason: Optional[str] = None
    external_url: Optional[str] = None
    internal_proxy_url: Optional[str] = None
    source_reference: Optional[str] = None


class VehicleTachometerHistoryEntryDetailResponse(VehicleTachometerHistoryEntryResponse):
    pass


@dataclass
class _NormalizedTachometerHistoryItem:
    canonical_entry: VehicleTachometerHistoryEntryModel
    merged_entries: list[VehicleTachometerHistoryEntryModel]
    is_monotonic_valid: bool = True
    anomaly: bool = False
    anomaly_type: str | None = None
    anomaly_delta_km: int | None = None
    merge_reason: str | None = None


def _ensure_vehicle_schema_columns(db: Session) -> None:
    assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")


def _ensure_vehicle_photo_column(db: Session) -> None:
    """
    Backward-compatible alias používaný napříč routery.
    """
    _ensure_vehicle_schema_columns(db)


def _close_tachometer_http_session(data: dict[str, Any] | None) -> None:
    if not data:
        return
    http_session = data.get("http_session")
    if http_session is not None and isinstance(http_session, requests.Session):
        try:
            http_session.close()
        except Exception:
            pass


def _tachometer_challenge_session_id_is_safe(session_id: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9._-]{8,500}$", str(session_id or "")))


def _tachometer_challenge_persist_path(session_id: str) -> Path:
    if not _tachometer_challenge_session_id_is_safe(session_id):
        raise ValueError("invalid session id")
    return TACHOMETER_CHALLENGE_PERSIST_DIR / f"{session_id}.tach.pkl"


def _tachometer_delete_persisted_challenge(session_id: str) -> None:
    if not _tachometer_challenge_session_id_is_safe(session_id):
        return
    try:
        path = _tachometer_challenge_persist_path(session_id)
    except ValueError:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _tachometer_write_persisted_challenge(session_id: str, payload: dict[str, Any]) -> None:
    path = _tachometer_challenge_persist_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = pickle.dumps(payload, protocol=4)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(raw)
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _tachometer_read_persisted_challenge(session_id: str) -> dict[str, Any] | None:
    if not _tachometer_challenge_session_id_is_safe(session_id):
        return None
    try:
        path = _tachometer_challenge_persist_path(session_id)
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        data = pickle.loads(path.read_bytes())
    except Exception:
        _tachometer_delete_persisted_challenge(session_id)
        return None
    if not isinstance(data, dict) or int(data.get("v", 0) or 0) != _TACHOMETER_CHALLENGE_PERSIST_V:
        _tachometer_delete_persisted_challenge(session_id)
        return None
    cts = data.get("created_at_ts")
    if not isinstance(cts, (int, float)) or time.time() - float(cts) > TACHOMETER_CHALLENGE_TTL_SECONDS:
        _tachometer_delete_persisted_challenge(session_id)
        return None
    cjp = data.get("cookie_jar_pickle")
    if not isinstance(cjp, (bytes, bytearray)) or not cjp:
        _tachometer_delete_persisted_challenge(session_id)
        return None
    return {
        "created_at": datetime.utcfromtimestamp(float(cts)),
        "created_at_ts": float(cts),
        "request_verification_token": str(data.get("request_verification_token", "") or ""),
        "cookies": data.get("cookies") if isinstance(data.get("cookies"), dict) else {},
        "cookie_jar_pickle": bytes(cjp),
        "http_session": None,
        "expected_vin": data.get("expected_vin"),
        "vehicle_id": data.get("vehicle_id"),
    }


def _tachometer_cleanup_orphan_persisted_files() -> None:
    if not TACHOMETER_CHALLENGE_PERSIST_DIR.is_dir():
        return
    cutoff = time.time() - TACHOMETER_CHALLENGE_TTL_SECONDS - 60.0
    for p in TACHOMETER_CHALLENGE_PERSIST_DIR.glob("*.tach.pkl"):
        if not p.is_file() or p.name.startswith("."):
            continue
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
        except OSError:
            pass


def _tachometer_challenge_is_expired(data: dict[str, Any]) -> bool:
    cts = data.get("created_at_ts")
    if isinstance(cts, (int, float)):
        return float(cts) < time.time() - TACHOMETER_CHALLENGE_TTL_SECONDS
    ca = data.get("created_at")
    if isinstance(ca, datetime):
        return ca < datetime.utcnow() - timedelta(seconds=TACHOMETER_CHALLENGE_TTL_SECONDS)
    return True


def _cleanup_tachometer_challenge_store() -> None:
    with _TACHOMETER_CHALLENGE_LOCK:
        expired = [
            challenge_id
            for challenge_id, data in _TACHOMETER_CHALLENGE_STORE.items()
            if _tachometer_challenge_is_expired(data)
        ]
        for challenge_id in expired:
            data = _TACHOMETER_CHALLENGE_STORE.pop(challenge_id, None)
            if not data:
                continue
            _close_tachometer_http_session(data)
            _tachometer_delete_persisted_challenge(challenge_id)
    _tachometer_cleanup_orphan_persisted_files()


def _get_tachometer_challenge(session_id: str) -> dict[str, Any] | None:
    if not _tachometer_challenge_session_id_is_safe(session_id):
        return None
    _cleanup_tachometer_challenge_store()
    with _TACHOMETER_CHALLENGE_LOCK:
        ch = _TACHOMETER_CHALLENGE_STORE.get(session_id)
    if ch is not None:
        if not _tachometer_challenge_is_expired(ch):
            return ch
        with _TACHOMETER_CHALLENGE_LOCK:
            old = _TACHOMETER_CHALLENGE_STORE.pop(session_id, None)
        _close_tachometer_http_session(old)
        _tachometer_delete_persisted_challenge(session_id)
    loaded = _tachometer_read_persisted_challenge(session_id)
    if loaded is None:
        return None
    with _TACHOMETER_CHALLENGE_LOCK:
        ex = _TACHOMETER_CHALLENGE_STORE.get(session_id)
        if ex is not None and not _tachometer_challenge_is_expired(ex):
            return ex
        if ex is not None and _tachometer_challenge_is_expired(ex):
            replace_old = _TACHOMETER_CHALLENGE_STORE.pop(session_id, None)
        else:
            replace_old = None
        if replace_old is not None:
            _close_tachometer_http_session(replace_old)
        _TACHOMETER_CHALLENGE_STORE[session_id] = loaded
    return loaded


def _normalize_vin(raw: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]", "", str(raw or "").upper())
    return value.strip()


def _strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    no_tags = re.sub(r"<[^>]+>", "", raw, flags=re.S)
    text = html.unescape(no_tags).replace("\xa0", " ")
    return " ".join(text.split())


def _extract_hidden_token(page_html: str) -> str | None:
    match = re.search(
        r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"',
        page_html,
        flags=re.I,
    )
    if match:
        return html.unescape(match.group(1))
    match2 = re.search(
        r'<input[^>]+name=["\']__RequestVerificationToken["\'][^>]*\bvalue=["\']([^"\']+)["\']',
        page_html,
        flags=re.I,
    )
    if match2:
        return html.unescape(match2.group(1))
    return None


def _extract_captcha_src(page_html: str) -> str | None:
    match = re.search(r'<img[^>]+id="captcha_IMG"[^>]+src="([^"]+)"', page_html, flags=re.I)
    if match:
        return html.unescape(match.group(1))
    match2 = re.search(r'src="([^"]+)"[^>]+id="captcha_IMG"', page_html, flags=re.I)
    if match2:
        return html.unescape(match2.group(1))
    return None


def _contains_captcha_error(page_html: str) -> bool:
    decoded = html.unescape(page_html or "").lower()
    normalized_ascii = (
        unicodedata.normalize("NFKD", decoded).encode("ascii", "ignore").decode("ascii")
    )
    return (
        "špatně opsaný kód z obrázku" in decoded
        or "spatne opsany kod z obrazku" in normalized_ascii
        or "submitted code is incorrect" in decoded
    )


def _serialize_tachometer_captcha_payload(
    *,
    session_id: str,
    captcha_bytes: bytes,
    captcha_mime_type: str,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "captcha_image_base64": base64.b64encode(captcha_bytes).decode("ascii"),
        "captcha_mime_type": captcha_mime_type,
        "expires_in_seconds": TACHOMETER_CHALLENGE_TTL_SECONDS,
    }


def _parse_data_url_image(data_url: str) -> tuple[str, str]:
    raw = str(data_url or "").strip()
    if raw.startswith("data:") and ";base64," in raw:
        header, payload = raw.split(",", 1)
        mime = header[5:].split(";", 1)[0].strip() or "image/png"
        return mime, payload.strip()
    return "image/png", raw


def _start_response_to_legacy_init_response(
    started: "VehicleTachometerStartResponse",
) -> "VehicleTachometerInitResponse":
    mime, payload = _parse_data_url_image(getattr(started, "captcha_image", "") or "")
    return VehicleTachometerInitResponse(
        session_id=started.session_id,
        captcha_image_base64=payload,
        captcha_mime_type=mime,
        expires_in_seconds=started.expires_in_seconds,
    )


def _legacy_invalid_captcha_detail_from_new(detail: Any) -> Any:
    if not isinstance(detail, dict):
        return detail
    mime, payload = _parse_data_url_image(str(detail.get("captcha_image") or ""))
    return {
        "code": "CAPTCHA_INVALID",
        "message": str(detail.get("message") or _TACHOMETER_CAPTCHA_ERROR_TEXT),
        "session_id": detail.get("session_id"),
        "captcha_image_base64": payload,
        "captcha_mime_type": mime,
        "expires_in_seconds": detail.get("expires_in_seconds") or TACHOMETER_CHALLENGE_TTL_SECONDS,
    }


def _fetch_tachometer_captcha_image(
    *,
    session: requests.Session,
    captcha_src: str,
) -> tuple[bytes, str]:
    captcha_response = session.get(
        urljoin(TACHOMETER_BASE_URL, captcha_src),
        timeout=_TACHOMETER_HTTP_TIMEOUT_SECONDS,
    )
    captcha_response.raise_for_status()
    captcha_bytes = captcha_response.content
    if not captcha_bytes:
        raise HTTPException(
            status_code=502,
            detail="Captcha obrázek je prázdný. Zkuste to prosím znovu.",
        )
    captcha_mime_type = (
        captcha_response.headers.get("Content-Type", "image/png").split(";", 1)[0].strip()
        or "image/png"
    )
    return captcha_bytes, captcha_mime_type


def _store_tachometer_challenge_session(
    *,
    session_id: str,
    session: requests.Session,
    request_verification_token: str,
    expected_vin: Optional[str],
    vehicle_id: Optional[int],
) -> None:
    now_ts = time.time()
    cookie_jar_pickle = pickle.dumps(session.cookies, protocol=4)
    rec: dict[str, Any] = {
        "created_at": datetime.utcfromtimestamp(now_ts),
        "created_at_ts": now_ts,
        "request_verification_token": request_verification_token,
        "cookies": requests.utils.dict_from_cookiejar(session.cookies),
        "cookie_jar_pickle": cookie_jar_pickle,
        "http_session": session,
        "expected_vin": expected_vin,
        "vehicle_id": vehicle_id,
    }
    persist: dict[str, Any] = {
        "v": _TACHOMETER_CHALLENGE_PERSIST_V,
        "created_at_ts": now_ts,
        "request_verification_token": request_verification_token,
        "expected_vin": expected_vin,
        "vehicle_id": vehicle_id,
        "cookie_jar_pickle": cookie_jar_pickle,
    }
    with _TACHOMETER_CHALLENGE_LOCK:
        _TACHOMETER_CHALLENGE_STORE[session_id] = rec
    if _tachometer_challenge_session_id_is_safe(session_id):
        try:
            _tachometer_write_persisted_challenge(session_id, persist)
        except OSError:
            # Paměť jde použít na stejném workru; pro jiný worker by jinak chyběl soubor s cookies.
            pass


def _refresh_tachometer_challenge_from_html(
    *,
    session_id: str,
    page_html: str,
    session: requests.Session,
    existing_challenge: dict[str, Any],
) -> dict[str, Any] | None:
    token = _extract_hidden_token(page_html)
    captcha_src = _extract_captcha_src(page_html)
    if not token or not captcha_src:
        return None
    try:
        captcha_bytes, captcha_mime_type = _fetch_tachometer_captcha_image(
            session=session,
            captcha_src=captcha_src,
        )
    except HTTPException:
        return None

    _store_tachometer_challenge_session(
        session_id=session_id,
        session=session,
        request_verification_token=token,
        expected_vin=existing_challenge.get("expected_vin"),
        vehicle_id=existing_challenge.get("vehicle_id"),
    )
    return _serialize_tachometer_captcha_payload(
        session_id=session_id,
        captcha_bytes=captcha_bytes,
        captcha_mime_type=captcha_mime_type,
    )


def _parse_km_value(raw: str | None) -> int | None:
    if not raw:
        return None
    digits = re.sub(r"[^0-9]", "", _strip_html(raw))
    if not digits:
        return None
    return int(digits)


def _parse_cz_date(raw: str | None) -> datetime | None:
    value = _strip_html(raw)
    if not value:
        return None
    for fmt in ("%d.%m.%Y", "%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _extract_td_value(row_html: str, data_attr: str) -> str | None:
    pattern = rf"<td[^>]*{re.escape(data_attr)}[^>]*>(.*?)</td>"
    match = re.search(pattern, row_html, flags=re.I | re.S)
    if match:
        return match.group(1)
    return None


def _same_origin_external_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    value = html.unescape(str(raw_url)).strip()
    if not value or value.lower().startswith("javascript:"):
        return None
    absolute = urljoin(TACHOMETER_BASE_URL, value)
    if not absolute.startswith(TACHOMETER_BASE_URL):
        return None
    return absolute


def _extract_tachometer_document_links(fragment_html: str, protocol_number: str | None) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    link_index = 0
    for href, label in re.findall(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", fragment_html or "", flags=re.I | re.S):
        external_url = _same_origin_external_url(href)
        title = _strip_html(label) or f"Dokument {link_index + 1}"
        href_lower = str(href).lower()
        title_lower = title.lower()
        if not external_url:
            continue
        if ".pdf" not in href_lower and "pdf" not in title_lower and "protokol" not in title_lower and "dokument" not in title_lower:
            continue
        link_index += 1
        documents.append(
            {
                "document_id": f"{protocol_number or 'tachometer'}:document:{link_index}",
                "title": title,
                "document_type": "protocol" if "protokol" in title_lower or ".pdf" in href_lower else "document",
                "available": True,
                "open_mode": "external_url",
                "reason": None,
                "external_url": external_url,
                "internal_proxy_url": None,
                "source_reference": href,
            }
        )
    return documents


def _extract_tachometer_detail_reference(fragment_html: str) -> dict[str, Any] | None:
    form_match = re.search(r"<form[^>]+action=[\"']([^\"']+)[\"'][^>]*>(.*?)</form>", fragment_html or "", flags=re.I | re.S)
    if form_match:
        action = _same_origin_external_url(form_match.group(1))
        if action:
            inputs = {
                str(name): str(value)
                for name, value in re.findall(
                    r"<input[^>]+name=[\"']([^\"']+)[\"'][^>]+value=[\"']([^\"']*)[\"'][^>]*>",
                    form_match.group(2),
                    flags=re.I | re.S,
                )
            }
            return {
                "kind": "form",
                "action": action,
                "method": "POST",
                "inputs": inputs,
            }

    href_match = re.search(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>.*?Detail prohlídky.*?</a>", fragment_html or "", flags=re.I | re.S)
    if href_match:
        external_url = _same_origin_external_url(href_match.group(1))
        if external_url:
            return {
                "kind": "url",
                "url": external_url,
            }

    onclick_match = re.search(
        r"onclick=[\"'][^\"']*(?:location\.href|window\.open)\s*=\s*[\"']([^\"']+)[\"']",
        fragment_html or "",
        flags=re.I | re.S,
    )
    if onclick_match:
        external_url = _same_origin_external_url(onclick_match.group(1))
        if external_url:
            return {
                "kind": "url",
                "url": external_url,
            }

    button_fragment = re.search(r"(<button[^>]*>.*?Detail prohlídky.*?</button>)", fragment_html or "", flags=re.I | re.S)
    if button_fragment:
        button_html = button_fragment.group(1)
        data_attrs = dict(
            re.findall(r"(data-[a-z0-9_-]+)=[\"']([^\"']+)[\"']", button_html, flags=re.I)
        )
        if data_attrs:
            return {
                "kind": "button_data",
                "data": data_attrs,
            }
        return {
            "kind": "button_label",
            "label": "Detail prohlídky",
        }
    return None


def _is_openable_tachometer_detail_reference(detail_reference: dict[str, Any] | None) -> bool:
    if not isinstance(detail_reference, dict):
        return False
    return str(detail_reference.get("kind") or "") in {"url", "form", "button_data"}


def _extract_tachometer_text_blocks(fragment_html: str | None) -> list[str]:
    normalized = re.sub(r"(?i)</(?:tr|li|p|div|h\d)>", "\n", fragment_html or "")
    normalized = re.sub(r"(?i)<br\s*/?>", "\n", normalized)
    blocks = []
    for raw_line in normalized.split("\n"):
        line = _strip_html(raw_line)
        if line:
            blocks.append(line)
    return blocks


def _extract_tachometer_findings(fragment_html: str | None) -> list[str]:
    items: list[str] = []
    ignored_exact = {
        "detail prohlídky",
        "zjištěné závady",
        "zjistene zavady",
    }
    for item_html in re.findall(r"<li[^>]*>(.*?)</li>", fragment_html or "", flags=re.I | re.S):
        item_text = _strip_html(item_html)
        if item_text and item_text.lower() not in ignored_exact:
            items.append(item_text)

    blocks = _extract_tachometer_text_blocks(fragment_html)
    for index, block in enumerate(blocks):
        lowered = block.lower()
        if not any(token in lowered for token in ("závad", "zavad", "nedostat", "vada", "chyb")):
            continue
        if index + 1 < len(blocks):
            next_block = blocks[index + 1]
            next_lower = next_block.lower()
            if (
                next_block not in items
                and next_lower not in ignored_exact
                and not any(token in next_lower for token in ("detail prohlídky", "stav km", "číslo protokolu"))
            ):
                items.append(next_block)
        if block not in items and ":" not in block and lowered not in ignored_exact:
            items.append(block)

    deduped: list[str] = []
    for item in items:
        cleaned = " ".join(item.split()).strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def _build_tachometer_detail_snapshot(fragment_html: str | None) -> dict[str, Any] | None:
    if not fragment_html:
        return None
    text_blocks = _extract_tachometer_text_blocks(fragment_html)
    if not text_blocks:
        return None

    field_rows = []
    for label_html, value_html in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>\s*<t[dh][^>]*>(.*?)</t[dh]>", fragment_html, flags=re.I | re.S):
        label = _strip_html(label_html)
        value = _strip_html(value_html)
        if label and value:
            field_rows.append({"label": label, "value": value})

    findings_items = _extract_tachometer_findings(fragment_html)
    if not field_rows and not findings_items:
        detail_text = " ".join(text_blocks)
        if detail_text.lower() == "detail prohlídky":
            return None
    return {
        "text_blocks": text_blocks,
        "field_rows": field_rows,
        "findings_items": findings_items,
        "raw_text": " ".join(text_blocks),
    }


def _follow_tachometer_detail_reference(
    *,
    session: requests.Session,
    detail_reference: dict[str, Any],
) -> str | None:
    try:
        kind = str(detail_reference.get("kind") or "")
        if kind == "url":
            url = str(detail_reference.get("url") or "")
            if not url.startswith(TACHOMETER_BASE_URL):
                return None
            response = session.get(url, timeout=_TACHOMETER_HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.text
        if kind == "form":
            action = str(detail_reference.get("action") or "")
            if not action.startswith(TACHOMETER_BASE_URL):
                return None
            inputs = detail_reference.get("inputs")
            if not isinstance(inputs, dict):
                inputs = {}
            response = session.post(action, data=inputs, timeout=_TACHOMETER_HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.text
    except requests.RequestException:
        return None
    return None


def _resolve_tachometer_detail_data(
    *,
    row_html: str,
    inline_detail_html: str | None,
    protocol_number: str | None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    documents = _extract_tachometer_document_links(inline_detail_html or row_html, protocol_number)
    detail_reference = _extract_tachometer_detail_reference(inline_detail_html or row_html)
    detail_snapshot = _build_tachometer_detail_snapshot(inline_detail_html)

    if detail_snapshot is None and detail_reference and session is not None and detail_reference.get("kind") in {"url", "form"}:
        fetched_html = _follow_tachometer_detail_reference(session=session, detail_reference=detail_reference)
        if fetched_html:
            documents = _extract_tachometer_document_links(fetched_html, protocol_number) or documents
            detail_snapshot = _build_tachometer_detail_snapshot(fetched_html)

    findings_items = []
    findings_summary = None
    if isinstance(detail_snapshot, dict):
        findings_items = [
            str(item).strip()
            for item in detail_snapshot.get("findings_items", [])
            if str(item).strip()
        ]
        if findings_items:
            findings_summary = " • ".join(findings_items[:3])

    return {
        "documents": documents,
        "detail_snapshot_json": detail_snapshot,
        "source_detail_reference": detail_reference,
        "findings_items": findings_items,
        "findings_summary": findings_summary,
        "detail_available": bool(detail_snapshot or _is_openable_tachometer_detail_reference(detail_reference)),
    }


def _parse_tachometer_inspections(
    search_html: str,
    *,
    session: requests.Session | None = None,
) -> List[TachometerInspectionOut]:
    section_match = re.search(
        r"Seznam prohl[íi]dek.*?(<table[^>]*>.*?</table>)",
        search_html,
        flags=re.I | re.S,
    )
    section_html = section_match.group(1) if section_match else search_html
    rows = re.findall(r"<tr[^>]*>.*?</tr>", section_html, flags=re.I | re.S)
    inspections: list[TachometerInspectionOut] = []
    row_index = 0
    while row_index < len(rows):
        row = rows[row_index]
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.I | re.S)
        if len(cells) < 5:
            row_index += 1
            continue
        check_date = _parse_cz_date(cells[0])
        mileage_km = _parse_km_value(cells[4])
        if mileage_km is None:
            row_index += 1
            continue
        inspection_type = _strip_html(cells[1]) or None
        inspection_kind = _strip_html(cells[3]) or None
        protocol_number = _strip_html(cells[2]) or None
        note_text = _strip_html(cells[5]) or None if len(cells) > 5 else None
        result_label = normalize_tachometer_result(cells[6]) if len(cells) > 6 else None
        inline_detail_html = None
        if row_index + 1 < len(rows):
            next_row = rows[row_index + 1]
            next_cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", next_row, flags=re.I | re.S)
            next_text = _strip_html(next_row)
            next_text_lower = next_text.lower()
            if len(next_cells) <= 2 and any(token in next_text_lower for token in ("detail prohlídky", "závad", "zavad", "nedostat", "protokol", "emise")):
                inline_detail_html = next_row
                row_index += 1

        detail_data = _resolve_tachometer_detail_data(
            row_html=row,
            inline_detail_html=inline_detail_html,
            protocol_number=protocol_number,
            session=session,
        )
        inspections.append(
            TachometerInspectionOut(
                check_date=check_date,
                mileage_km=mileage_km,
                protocol_number=protocol_number,
                inspection_type=inspection_type,
                inspection_kind=inspection_kind,
                result_label=result_label,
                note_text=note_text,
                findings_summary=detail_data["findings_summary"],
                findings_items=detail_data["findings_items"],
                detail_available=bool(detail_data["detail_available"]),
                detail_snapshot_json=detail_data["detail_snapshot_json"],
                source_detail_reference=detail_data["source_detail_reference"],
                documents=detail_data["documents"],
            )
        )
        row_index += 1

    if not inspections:
        return []

    if any(item.check_date is not None for item in inspections):
        inspections.sort(
            key=lambda item: item.check_date or datetime.min,
            reverse=True,
        )
    else:
        inspections.sort(key=lambda item: item.mileage_km, reverse=True)

    return inspections


def _get_accessible_vehicle_or_404(vehicle_id: int, current_user: Customer, db: Session) -> VehicleModel:
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
    return vehicle


def _build_tachometer_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; SpravaVozidel/1.0; +https://hub.toozservis.cz)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
    )
    return session


def _create_tachometer_session(
    *,
    expected_vin: Optional[str],
    vehicle_id: Optional[int],
) -> VehicleTachometerInitResponse:
    _cleanup_tachometer_challenge_store()
    session = _build_tachometer_session()
    try:
        page_response = session.get(
            urljoin(TACHOMETER_BASE_URL, TACHOMETER_LANDING_PATH),
            timeout=_TACHOMETER_HTTP_TIMEOUT_SECONDS,
        )
        page_response.raise_for_status()
        token = _extract_hidden_token(page_response.text)
        captcha_src = _extract_captcha_src(page_response.text)
        if not token or not captcha_src:
            raise HTTPException(
                status_code=502,
                detail="Nepodařilo se načíst captcha z Kontroly tachometru.",
            )

        captcha_bytes, captcha_mime_type = _fetch_tachometer_captcha_image(
            session=session,
            captcha_src=captcha_src,
        )

        session_id = secrets.token_urlsafe(24)
        _store_tachometer_challenge_session(
            session_id=session_id,
            session=session,
            request_verification_token=token,
            expected_vin=expected_vin,
            vehicle_id=vehicle_id,
        )
        return VehicleTachometerInitResponse(
            **_serialize_tachometer_captcha_payload(
                session_id=session_id,
                captcha_bytes=captcha_bytes,
                captcha_mime_type=captcha_mime_type,
            )
        )
    except HTTPException:
        session.close()
        raise
    except requests.RequestException as exc:
        session.close()
        raise HTTPException(
            status_code=502,
            detail=f"Nepodařilo se spojit s kontrolatachometru.cz: {exc}",
        ) from exc


def _lookup_tachometer_with_session(
    *,
    session_id: str,
    vin: str,
    captcha_code: str,
) -> TachometerLookupResponse:
    challenge = _get_tachometer_challenge(session_id)
    if not challenge:
        raise HTTPException(
            status_code=410,
            detail="Captcha session vypršela nebo je neplatná. Načtěte nový obrázek.",
        )

    expected_vin = challenge.get("expected_vin")
    if expected_vin and expected_vin != vin:
        raise HTTPException(
            status_code=409,
            detail="Captcha session patří k jinému vozidlu. Načtěte nový obrázek pro aktuální VIN.",
        )

    if len(captcha_code) < 2:
        raise HTTPException(status_code=422, detail="Zadejte captcha kód z obrázku.")

    def _pop_and_close_tachometer_challenge() -> None:
        with _TACHOMETER_CHALLENGE_LOCK:
            removed = _TACHOMETER_CHALLENGE_STORE.pop(session_id, None)
        _close_tachometer_http_session(removed)
        _tachometer_delete_persisted_challenge(session_id)

    try:
        http_session = challenge.get("http_session")
        if isinstance(http_session, requests.Session):
            session = http_session
        else:
            cjp = challenge.get("cookie_jar_pickle")
            if isinstance(cjp, (bytes, bytearray)) and cjp:
                try:
                    jar = pickle.loads(bytes(cjp))
                    session = _build_tachometer_session()
                    if isinstance(jar, RequestsCookieJar):
                        session.cookies = jar
                    elif isinstance(jar, dict):
                        session.cookies.update(jar)
                    else:
                        raise ValueError("unexpected cookie container")
                except Exception:
                    session = _build_tachometer_session()
                    cookie_dict = challenge.get("cookies", {})
                    if isinstance(cookie_dict, dict):
                        session.cookies.update(cookie_dict)
            else:
                session = _build_tachometer_session()
                cookie_dict = challenge.get("cookies", {})
                if isinstance(cookie_dict, dict):
                    session.cookies.update(cookie_dict)
        # Portálový formulář má enctype="multipart/form-data" (MVCxClientCaptcha + antiforgery).
        # Vynucené Content-Type: application/x-www-form-urlencoded na session může rozbít
        # parsování — posíláme stejné tělo jako prohlížeč (multipart, pole bez názvů souborů).
        request_headers = {
            "Referer": urljoin(TACHOMETER_BASE_URL, TACHOMETER_LANDING_PATH),
            "Origin": TACHOMETER_BASE_URL,
        }
        response = session.post(
            urljoin(TACHOMETER_BASE_URL, TACHOMETER_SEARCH_PATH),
            files={
                "__RequestVerificationToken": (None, str(challenge.get("request_verification_token", "") or "")),
                "VIN": (None, vin),
                "captcha$TB": (None, captcha_code),
            },
            headers=request_headers,
            timeout=_TACHOMETER_HTTP_TIMEOUT_SECONDS,
        )
        if not (200 <= response.status_code < 300):
            lowered = (response.text or "").lower()
            is_html = "<!doctype" in lowered or "<html" in lowered
            if response.status_code in {400, 403} or (response.status_code == 500 and is_html):
                raise HTTPException(
                    status_code=410,
                    detail="Captcha session vypršela nebo je neplatná. Načtěte nový obrázek.",
                )
            raise HTTPException(
                status_code=502,
                detail="Portál kontrolatachometru.cz momentálně nevrátil použitelnou odpověď. Zkuste to prosím znovu.",
            )

        search_html = response.text
        if _contains_captcha_error(search_html):
            refreshed_payload = _refresh_tachometer_challenge_from_html(
                session_id=session_id,
                page_html=search_html,
                session=session,
                existing_challenge=challenge,
            )
            if refreshed_payload:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "CAPTCHA_INVALID",
                        "message": _TACHOMETER_CAPTCHA_ERROR_TEXT,
                        **refreshed_payload,
                    },
                )
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "CAPTCHA_INVALID",
                    "message": _TACHOMETER_CAPTCHA_ERROR_TEXT,
                    "session_id": session_id,
                },
            )

        inspections = _parse_tachometer_inspections(search_html, session=session)
        if not inspections:
            raise HTTPException(
                status_code=404,
                detail="Pro zadané VIN nebyly nalezeny žádné údaje STK/emisí.",
            )

        latest = inspections[0]
        _pop_and_close_tachometer_challenge()
        return TachometerLookupResponse(
            vin=vin,
            latest_mileage_km=latest.mileage_km,
            latest_check_date=latest.check_date,
            inspections=inspections,
        )
    except HTTPException as exc:
        is_captcha_retry = bool(
            exc.status_code == 422
            and isinstance(exc.detail, dict)
            and (exc.detail or {}).get("code") == "CAPTCHA_INVALID"
        )
        if not is_captcha_retry:
            _pop_and_close_tachometer_challenge()
        raise
    except requests.RequestException as exc:
        _pop_and_close_tachometer_challenge()
        raise HTTPException(
            status_code=502,
            detail="Portál kontrolatachometru.cz je dočasně nedostupný. Zkuste to prosím znovu později.",
        ) from exc


def _store_tachometer_mileage_result(
    *,
    vehicle: VehicleModel,
    lookup: TachometerLookupResponse,
    current_user: Customer,
    db: Session,
    confirm_lower_than_current: bool = False,
) -> tuple[dict, Optional[int]]:
    new_km = int(lookup.latest_mileage_km)
    cm = getattr(vehicle, "current_mileage_km", None)
    if confirm_lower_than_current:
        vehicle.current_mileage_km = new_km
    else:
        base_cm = int(cm) if cm is not None else new_km
        vehicle.current_mileage_km = max(base_cm, new_km)

    vehicle.last_stk_mileage_km = new_km
    vehicle.mileage_checked_at = datetime.utcnow()

    _validate_mileage_consistency(
        current_mileage_km=vehicle.current_mileage_km,
        last_stk_mileage_km=vehicle.last_stk_mileage_km,
    )

    latest = lookup.inspections[0]
    record_note_parts = ["Zdroj: kontrolatachometru.cz (import portálu)"]
    if latest.protocol_number:
        record_note_parts.append(f"Protokol: {latest.protocol_number}")
    if latest.inspection_type:
        record_note_parts.append(f"Typ: {latest.inspection_type}")
    note_text = " | ".join(record_note_parts)
    note_stored = note_text[:1000] if note_text else None

    vm_query = (
        db.query(VehicleMileageModel)
        .filter(
            VehicleMileageModel.vehicle_id == vehicle.id,
            VehicleMileageModel.source == "stk",
            VehicleMileageModel.mileage_km == new_km,
        )
    )
    proto = (latest.protocol_number or "").strip()
    if proto:
        vm_query = vm_query.filter(VehicleMileageModel.note.contains(proto))
    vm_existing = vm_query.first()

    vm_id: Optional[int]
    if vm_existing is not None:
        vm_id = int(vm_existing.id)
    else:
        vm_row = VehicleMileageModel(
            tenant_id=int(vehicle.tenant_id),
            vehicle_id=int(vehicle.id),
            mileage_km=new_km,
            source="stk",
            note=note_stored,
            created_by_user_id=getattr(current_user, "id", None),
        )
        db.add(vm_row)
        db.flush()
        vm_id = int(vm_row.id)
        write_global_audit_log(
            db,
            entity_type="vehicle",
            entity_id=int(vehicle.id),
            action="tachometer_stk_import",
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
            tenant_id=int(vehicle.tenant_id),
            metadata={
                "vehicle_mileage_id": vm_id,
                "mileage_km": new_km,
                "protocol_number": proto or None,
                "source": "kontrolatachometru.cz",
            },
        )

    _upsert_tachometer_history_entries(
        vehicle=vehicle,
        lookup=lookup,
        imported_at=datetime.utcnow(),
        db=db,
    )

    db.commit()
    db.refresh(vehicle)
    return _vehicle_to_response_payload(vehicle, current_user, db), vm_id


def _upsert_tachometer_history_entries(
    *,
    vehicle: VehicleModel,
    lookup: TachometerLookupResponse,
    imported_at: datetime,
    db: Session,
) -> None:
    for inspection in lookup.inspections:
        protocol_number = (inspection.protocol_number or "").strip() or None
        source = lookup.source or "kontrolatachometru.cz"
        summary = _build_tachometer_entry_summary(
            inspection_type=inspection.inspection_type,
            inspection_kind=getattr(inspection, "inspection_kind", None),
            protocol_number=protocol_number,
            source=source,
        )
        documents = _build_tachometer_documents(
            protocol_number=protocol_number,
            parsed_documents=list(getattr(inspection, "documents", []) or []),
            detail_available=bool(getattr(inspection, "detail_available", False)),
            source_detail_reference=getattr(inspection, "source_detail_reference", None),
        )
        raw_payload = {
            "check_date": inspection.check_date.isoformat() if inspection.check_date else None,
            "mileage_km": inspection.mileage_km,
            "protocol_number": protocol_number,
            "inspection_type": inspection.inspection_type,
            "inspection_kind": getattr(inspection, "inspection_kind", None),
            "source": source,
            "result_label": getattr(inspection, "result_label", None),
            "note_text": getattr(inspection, "note_text", None),
            "findings_summary": inspection.findings_summary,
            "findings_items": list(getattr(inspection, "findings_items", []) or []),
            "detail_available": bool(getattr(inspection, "detail_available", False)),
            "detail_snapshot_json": getattr(inspection, "detail_snapshot_json", None),
            "source_detail_reference": getattr(inspection, "source_detail_reference", None),
        }

        entry = (
            db.query(VehicleTachometerHistoryEntryModel)
            .filter(
                VehicleTachometerHistoryEntryModel.vehicle_id == vehicle.id,
                VehicleTachometerHistoryEntryModel.check_date == inspection.check_date,
                VehicleTachometerHistoryEntryModel.mileage_km == inspection.mileage_km,
                VehicleTachometerHistoryEntryModel.protocol_number == protocol_number,
            )
            .first()
        )
        if entry is None:
            entry = VehicleTachometerHistoryEntryModel(
                tenant_id=vehicle.tenant_id,
                vehicle_id=vehicle.id,
                check_date=inspection.check_date,
                mileage_km=inspection.mileage_km,
                protocol_number=protocol_number,
                inspection_type=inspection.inspection_type,
                source=source,
                status="imported",
                read_only=True,
                summary=summary,
                findings_summary=inspection.findings_summary,
                findings_items_json=json.dumps(list(getattr(inspection, "findings_items", []) or []), ensure_ascii=False),
                detail_snapshot_json=(
                    json.dumps(getattr(inspection, "detail_snapshot_json", None), ensure_ascii=False)
                    if getattr(inspection, "detail_snapshot_json", None)
                    else None
                ),
                source_detail_reference=(
                    json.dumps(getattr(inspection, "source_detail_reference", None), ensure_ascii=False)
                    if getattr(inspection, "source_detail_reference", None)
                    else None
                ),
                documents_json=json.dumps(documents, ensure_ascii=False),
                raw_payload_json=json.dumps(raw_payload, ensure_ascii=False),
                imported_at=imported_at,
                last_seen_at=imported_at,
            )
            db.add(entry)
        else:
            entry.inspection_type = inspection.inspection_type
            entry.source = source
            entry.status = "imported"
            entry.read_only = True
            entry.summary = summary
            entry.findings_summary = inspection.findings_summary
            entry.findings_items_json = json.dumps(list(getattr(inspection, "findings_items", []) or []), ensure_ascii=False)
            entry.detail_snapshot_json = (
                json.dumps(getattr(inspection, "detail_snapshot_json", None), ensure_ascii=False)
                if getattr(inspection, "detail_snapshot_json", None)
                else None
            )
            entry.source_detail_reference = (
                json.dumps(getattr(inspection, "source_detail_reference", None), ensure_ascii=False)
                if getattr(inspection, "source_detail_reference", None)
                else None
            )
            entry.documents_json = json.dumps(documents, ensure_ascii=False)
            entry.raw_payload_json = json.dumps(raw_payload, ensure_ascii=False)
            entry.last_seen_at = imported_at


def _backfill_tachometer_history_entries_from_service_records(
    vehicle_id: int,
    db: Session,
) -> list[VehicleTachometerHistoryEntryModel]:
    existing_entries = (
        db.query(VehicleTachometerHistoryEntryModel)
        .filter(VehicleTachometerHistoryEntryModel.vehicle_id == vehicle_id)
        .order_by(
            VehicleTachometerHistoryEntryModel.check_date.asc(),
            VehicleTachometerHistoryEntryModel.mileage_km.asc(),
            VehicleTachometerHistoryEntryModel.id.asc(),
        )
        .all()
    )
    if existing_entries:
        return existing_entries

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if vehicle is None:
        return []

    records = (
        db.query(ServiceRecordModel)
        .filter(
            ServiceRecordModel.vehicle_id == vehicle_id,
            ServiceRecordModel.description == "Načteno z kontroly tachometru (MDČR)",
            ServiceRecordModel.is_deleted.is_(False),
        )
        .order_by(ServiceRecordModel.performed_at.asc(), ServiceRecordModel.mileage.asc(), ServiceRecordModel.id.asc())
        .all()
    )

    imported_any = False
    for record in records:
        parsed_note = _parse_tachometer_record_note(getattr(record, "note", None))
        protocol_number = parsed_note["protocol_number"]
        source = parsed_note["source"] or "kontrolatachometru.cz"
        entry = VehicleTachometerHistoryEntryModel(
            tenant_id=vehicle.tenant_id,
            vehicle_id=vehicle.id,
            check_date=getattr(record, "performed_at", None),
            mileage_km=getattr(record, "mileage", None),
            protocol_number=protocol_number,
            inspection_type=parsed_note["inspection_type"],
            source=source,
            status="imported_legacy",
            summary=_build_tachometer_entry_summary(
                inspection_type=parsed_note["inspection_type"],
                protocol_number=protocol_number,
                source=source,
            ),
            findings_summary=None,
            findings_items_json=None,
            detail_snapshot_json=None,
            source_detail_reference=None,
            documents_json=json.dumps(_build_unavailable_tachometer_documents(protocol_number), ensure_ascii=False),
            raw_payload_json=json.dumps(
                {
                    "legacy_service_record_id": record.id,
                    "check_date": getattr(record, "performed_at", None).isoformat() if getattr(record, "performed_at", None) else None,
                    "mileage_km": getattr(record, "mileage", None),
                    "protocol_number": protocol_number,
                    "inspection_type": parsed_note["inspection_type"],
                    "source": source,
                },
                ensure_ascii=False,
            ),
            imported_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
        db.add(entry)
        imported_any = True

    if imported_any:
        db.commit()

    return (
        db.query(VehicleTachometerHistoryEntryModel)
        .filter(VehicleTachometerHistoryEntryModel.vehicle_id == vehicle_id)
        .order_by(
            VehicleTachometerHistoryEntryModel.check_date.asc(),
            VehicleTachometerHistoryEntryModel.mileage_km.asc(),
            VehicleTachometerHistoryEntryModel.id.asc(),
        )
        .all()
    )


def _tachometer_history_query(
    vehicle_id: int,
    db: Session,
) -> list[VehicleTachometerHistoryEntryModel]:
    return _backfill_tachometer_history_entries_from_service_records(vehicle_id, db)


def _build_tachometer_history_entries(vehicle_id: int, db: Session) -> list[VehicleTachometerHistoryEntryResponse]:
    items = _normalized_tachometer_history(vehicle_id, db)
    return [_tachometer_history_entry_to_summary(item) for item in items]


def _get_tachometer_history_entry_or_404(
    *,
    vehicle_id: int,
    entry_id: int,
    db: Session,
) -> VehicleTachometerHistoryEntryModel:
    _tachometer_history_query(vehicle_id, db)
    entry = (
        db.query(VehicleTachometerHistoryEntryModel)
        .filter(
            VehicleTachometerHistoryEntryModel.id == entry_id,
            VehicleTachometerHistoryEntryModel.vehicle_id == vehicle_id,
        )
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Záznam historie STK / tachometru nebyl nalezen.")
    return entry


def _get_normalized_tachometer_history_item_or_404(
    *,
    vehicle_id: int,
    entry_id: int,
    db: Session,
) -> _NormalizedTachometerHistoryItem:
    for item in _normalized_tachometer_history(vehicle_id, db):
        if int(getattr(item.canonical_entry, "id", 0) or 0) == entry_id:
            return item
    raise HTTPException(status_code=404, detail="Záznam historie STK / tachometru nebyl nalezen.")


def _get_vehicle_photo_file(photo_path: str | None) -> Path | None:
    if not photo_path:
        return None
    if str(photo_path).strip() == PRIMARY_PHOTO_CLIENT_MARKER:
        return None
    base = VEHICLE_PHOTOS_DIR.resolve()
    candidate = (VEHICLE_PHOTOS_DIR / str(photo_path)).resolve()
    if not str(candidate).startswith(str(base)):
        return None
    try:
        if not candidate.is_file():
            return None
    except OSError:
        return None
    return candidate


def _get_primary_photo_asset_row(db: Session, vehicle: VehicleModel) -> VehiclePhotoAssetModel | None:
    aid = getattr(vehicle, "primary_photo_asset_id", None)
    if not aid:
        return None
    return (
        db.query(VehiclePhotoAssetModel)
        .filter(
            VehiclePhotoAssetModel.id == int(aid),
            VehiclePhotoAssetModel.vehicle_id == int(vehicle.id),
            VehiclePhotoAssetModel.deleted_at.is_(None),
        )
        .first()
    )


def _resolve_primary_photo_file(*, vehicle: VehicleModel, db: Session) -> Path | None:
    asset = _get_primary_photo_asset_row(db, vehicle)
    if asset is not None:
        resolved = resolve_storage_file(VEHICLE_PHOTOS_DIR, asset.storage_key)
        if resolved is not None:
            return resolved
    return _get_vehicle_photo_file(getattr(vehicle, "photo_path", None))


def _count_active_gallery_assets(db: Session, vehicle_id: int) -> int:
    return int(
        db.query(VehiclePhotoAssetModel)
        .filter(
            VehiclePhotoAssetModel.vehicle_id == int(vehicle_id),
            VehiclePhotoAssetModel.role == "gallery",
            VehiclePhotoAssetModel.deleted_at.is_(None),
        )
        .count()
    )


def _count_catalog_image_regenerations(db: Session, *, vehicle_id: int) -> int:
    return int(
        db.query(GlobalAuditLogModel)
        .filter(
            GlobalAuditLogModel.vehicle_id == int(vehicle_id),
            GlobalAuditLogModel.action == "vehicle_catalog_image_regenerated",
        )
        .count()
    )


def _soft_delete_photo_asset(db: Session, asset: VehiclePhotoAssetModel) -> None:
    asset.deleted_at = datetime.utcnow()
    db.flush()


def _unlink_asset_file(asset: VehiclePhotoAssetModel) -> None:
    path = resolve_storage_file(VEHICLE_PHOTOS_DIR, asset.storage_key)
    if path and path.is_file():
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def _primary_photo_payload_for_api(*, vehicle: VehicleModel, db: Session) -> tuple[dict[str, Any], str | None]:
    """
    Vrátí (primary_photo dict, photo_path pro legacy klienty).
    photo_path je buď PRIMARY_PHOTO_CLIENT_MARKER (fyzicky dostupná fotka), None, nebo legacy relativní cesta.
    """
    path = _resolve_primary_photo_file(vehicle=vehicle, db=db)
    has_ref = bool(getattr(vehicle, "primary_photo_asset_id", None)) or bool(
        str(getattr(vehicle, "photo_path", None) or "").strip()
    )
    asset = _get_primary_photo_asset_row(db, vehicle)
    primary: dict[str, Any] = {
        "available": bool(path),
        "asset_id": int(asset.id) if asset and path else None,
        "broken": bool(has_ref and not path),
    }
    if path:
        return primary, PRIMARY_PHOTO_CLIENT_MARKER
    legacy_path = getattr(vehicle, "photo_path", None)
    if legacy_path and str(legacy_path).strip() != PRIMARY_PHOTO_CLIENT_MARKER:
        # Legacy klienti: vrátíme skutečnou relativní cestu jen pokud soubor existuje (jinak None + broken).
        if _get_vehicle_photo_file(legacy_path):
            primary["available"] = True
            primary["broken"] = False
            return primary, str(legacy_path).strip()
    primary["broken"] = bool(has_ref)
    return primary, None


def _guess_vehicle_image_media_type(image_file: Path) -> str:
    guessed = mimetypes.guess_type(str(image_file))[0]
    if guessed:
        return guessed

    suffix = str(getattr(image_file, "suffix", "") or "").lower()
    if suffix == ".webp":
        return "image/webp"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".gif":
        return "image/gif"
    if suffix == ".bmp":
        return "image/bmp"
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix == ".avif":
        return "image/avif"
    return "application/octet-stream"


def _gallery_vehicle_subdir(vehicle_id: int) -> Path:
    directory = VEHICLE_UPLOADS_VEHICLES_DIR / str(int(vehicle_id))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _persist_primary_vehicle_photo(
    *,
    vehicle: VehicleModel,
    current_user: Customer,
    normalized_content: bytes,
    db: Session,
    audit_action: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tenant_id = int(getattr(vehicle, "tenant_id", None) or getattr(current_user, "tenant_id", None) or 0)
    owner = get_primary_vehicle_owner(db, vehicle)
    owner_id = int(getattr(owner, "id", 0) or 0) or None
    filename = f"main_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(6)}.jpg"
    storage_key = build_main_storage_key(tenant_id=tenant_id, vehicle_id=int(vehicle.id), filename=filename)
    target_file = VEHICLE_PHOTOS_DIR / storage_key
    _write_bytes_to_vehicle_photos_file(target_file, normalized_content)

    previous_asset = _get_primary_photo_asset_row(db, vehicle)
    previous_legacy_file = _get_vehicle_photo_file(getattr(vehicle, "photo_path", None))

    if previous_asset is not None:
        _soft_delete_photo_asset(db, previous_asset)
        _unlink_asset_file(previous_asset)

    digest = sha256_hex(normalized_content)
    w_px, h_px = jpeg_dimensions(normalized_content)
    row = VehiclePhotoAssetModel(
        tenant_id=tenant_id,
        vehicle_id=int(vehicle.id),
        owner_customer_id=owner_id,
        role="main",
        storage_key=storage_key,
        original_filename=filename,
        mime_type="image/jpeg",
        file_size_bytes=len(normalized_content),
        width=w_px,
        height=h_px,
        sha256_hex=digest,
        uploaded_by_customer_id=int(getattr(current_user, "id", 0) or 0) or None,
        created_at=datetime.utcnow(),
        deleted_at=None,
        sort_order=0,
    )
    db.add(row)
    db.flush()
    vehicle.primary_photo_asset_id = int(row.id)
    vehicle.photo_path = None

    write_global_audit_log(
        db,
        entity_type="vehicle",
        entity_id=int(vehicle.id),
        action=audit_action,
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=tenant_id,
        metadata={
            "vehicle_photo_asset_id": int(row.id),
            "storage_key": storage_key,
            "sha256_hex": digest,
            **(metadata or {}),
        },
    )
    db.flush()

    if previous_legacy_file and previous_legacy_file.is_file() and previous_legacy_file.resolve() != target_file.resolve():
        try:
            previous_legacy_file.unlink(missing_ok=True)
        except Exception:
            pass

    return {
        "tenant_id": tenant_id,
        "photo_path": PRIMARY_PHOTO_CLIENT_MARKER,
        "photo_url": f"/api/v1/vehicles/{vehicle.id}/photo?v={int(datetime.utcnow().timestamp())}",
        "vehicle_photo_asset_id": int(row.id),
        "storage_key": storage_key,
    }


def _get_vehicle_gallery_file(relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    base = VEHICLE_UPLOADS_VEHICLES_DIR.resolve()
    normalized = str(relative_path).replace("\\", "/").lstrip("/")
    candidate = (VEHICLE_UPLOADS_VEHICLES_DIR / normalized).resolve()
    if not str(candidate).startswith(str(base)):
        return None
    if not candidate.is_file():
        return None
    return candidate


def _extract_service_record_attachment_files(attachments_raw: str | None) -> list[Path]:
    if not attachments_raw:
        return []
    try:
        import json
        payload = json.loads(attachments_raw)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []

    base = (DATA_DIR / "service_record_attachments").resolve()
    files: list[Path] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        key = item.get("storage_key") or item.get("path")
        if not key:
            continue
        candidate = (base / str(key)).resolve()
        if str(candidate).startswith(str(base)):
            files.append(candidate)
    return files


def _decode_base64_payload(payload: str) -> bytes:
    raw = str(payload or "").strip()
    if not raw:
        return b""
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    raw = re.sub(r"\s+", "", raw)
    pad = (-len(raw)) % 4
    if pad:
        raw = raw + ("=" * pad)
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Soubor není validní base64 payload: {exc}") from exc


def _download_catalog_image_content(url: str) -> tuple[bytes, str]:
    clean_url = str(url or "").strip()
    if not clean_url:
        raise HTTPException(status_code=422, detail="Katalogová fotka nemá URL ke stažení.")
    if not re.match(r"^https?://", clean_url, re.IGNORECASE):
        raise HTTPException(status_code=422, detail="Katalogová fotka musí být vzdálená HTTP(S) URL.")
    response = requests.get(clean_url, timeout=12)
    response.raise_for_status()
    content = response.content or b""
    if not content:
        raise HTTPException(status_code=422, detail="Stažená katalogová fotka je prázdná.")
    return content, str(response.headers.get("content-type") or "image/jpeg")


def _read_local_catalog_image_content(db: Session, url: str) -> tuple[bytes, str]:
    match = re.match(r"^/api/v1/vehicles/catalog-images/([a-zA-Z0-9]+)/file$", str(url or "").strip())
    if not match:
        raise HTTPException(status_code=422, detail="Katalogová fotka nemá validní interní URL.")
    image_id = match.group(1)
    row = db.query(VehicleCatalogImageModel).filter(VehicleCatalogImageModel.id == image_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Katalogová fotka nebyla nalezena.")
    catalog_file = resolve_catalog_image_storage_file(row)
    if not catalog_file or not catalog_file.exists():
        raise HTTPException(status_code=404, detail="Soubor katalogové fotky neexistuje.")
    content = catalog_file.read_bytes()
    if not content:
        raise HTTPException(status_code=422, detail="Katalogová fotka je prázdná.")
    return content, "image/jpeg"


def _store_catalog_image_in_gallery(
    *,
    vehicle: VehicleModel,
    current_user: Customer,
    image_url: str,
    source_label: str,
    db: Session,
    allow_duplicate: bool = False,
) -> int | None:
    if _count_active_gallery_assets(db, int(vehicle.id)) >= MAX_VEHICLE_GALLERY_PHOTOS:
        logger.info("[CATALOG_IMAGE] gallery skip reason=max_limit vehicle_id=%s", vehicle.id)
        return None

    if re.match(r"^/api/v1/vehicles/catalog-images/[a-zA-Z0-9]+/file$", str(image_url or "").strip()):
        content, mime_type = _read_local_catalog_image_content(db, image_url)
    else:
        content, mime_type = _download_catalog_image_content(image_url)
    if mime_type and not mime_type.lower().startswith("image/"):
        raise HTTPException(status_code=415, detail="Katalogová fotka není obrázek.")
    normalized_content = _normalize_vehicle_photo(content)

    tenant_id = int(getattr(vehicle, "tenant_id", None) or getattr(current_user, "tenant_id", None) or 0)
    owner = get_primary_vehicle_owner(db, vehicle)
    owner_id = int(getattr(owner, "id", 0) or 0) or None
    fname = f"catalog_{secrets.token_hex(8)}.jpg"
    storage_key = build_main_storage_key(tenant_id=tenant_id, vehicle_id=int(vehicle.id), filename=fname)
    target_file = VEHICLE_PHOTOS_DIR / storage_key
    _write_bytes_to_vehicle_photos_file(target_file, normalized_content)
    digest = sha256_hex(normalized_content)
    w_px, h_px = jpeg_dimensions(normalized_content)

    existing = None
    if not allow_duplicate:
        existing = (
            db.query(VehiclePhotoAssetModel)
            .filter(
                VehiclePhotoAssetModel.vehicle_id == int(vehicle.id),
                VehiclePhotoAssetModel.role == "gallery",
                VehiclePhotoAssetModel.sha256_hex == digest,
                VehiclePhotoAssetModel.deleted_at.is_(None),
            )
            .first()
        )
    if existing is not None:
        try:
            target_file.unlink(missing_ok=True)
        except Exception:
            pass
        return int(existing.id)

    row = VehiclePhotoAssetModel(
        tenant_id=tenant_id,
        vehicle_id=int(vehicle.id),
        owner_customer_id=owner_id,
        role="gallery",
        photo_kind="catalog_image",
        vin=getattr(vehicle, "vin", None),
        storage_key=storage_key,
        original_filename=f"{source_label or 'catalog_image'}.jpg"[:255],
        mime_type="image/jpeg",
        file_size_bytes=len(normalized_content),
        width=w_px,
        height=h_px,
        sha256_hex=digest,
        uploaded_by_customer_id=int(getattr(current_user, "id", 0) or 0) or None,
        created_at=datetime.utcnow(),
        deleted_at=None,
        sort_order=0,
    )
    db.add(row)
    db.flush()
    write_global_audit_log(
        db,
        entity_type="vehicle_gallery_photo",
        entity_id=int(row.id),
        action="catalog_image_saved_to_gallery",
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=tenant_id,
        vehicle_id=int(vehicle.id),
        metadata={"vehicle_id": int(vehicle.id), "vehicle_photo_asset_id": int(row.id), "storage_key": storage_key},
    )
    return int(row.id)


def _normalize_vehicle_photo(content: bytes) -> bytes:
    if not PILLOW_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Server není připraven zpracovat fotku vozidla. Chybí knihovna Pillow.",
        )

    try:
        with Image.open(BytesIO(content)) as image:
            resampling = getattr(Image, "Resampling", Image)
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "L"}:
                rgba_image = image.convert("RGBA")
                flattened = Image.new("RGB", rgba_image.size, (255, 255, 255))
                flattened.paste(rgba_image, mask=rgba_image.getchannel("A"))
                image = flattened
            elif image.mode == "L":
                image = image.convert("RGB")
            else:
                image = image.copy()

            image = ImageOps.fit(
                image,
                VEHICLE_PHOTO_TARGET_SIZE,
                method=resampling.LANCZOS,
                centering=(0.5, 0.5),
            )

            for quality in range(
                VEHICLE_PHOTO_JPEG_QUALITY,
                VEHICLE_PHOTO_MIN_JPEG_QUALITY - 1,
                -6,
            ):
                normalized_buffer = BytesIO()
                image.save(
                    normalized_buffer,
                    format="JPEG",
                    quality=quality,
                    optimize=True,
                )
                normalized = normalized_buffer.getvalue()
                if len(normalized) <= MAX_VEHICLE_PHOTO_OUTPUT_SIZE_BYTES:
                    return normalized
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=415, detail="Soubor není podporovaný nebo je poškozený obrázek.") from exc
    except OSError as exc:
        raise HTTPException(status_code=415, detail="Soubor není podporovaný nebo je poškozený obrázek.") from exc

    raise HTTPException(
        status_code=413,
        detail="Fotku se nepodařilo zpracovat pod výsledný limit 10 MB.",
    )


def _parse_tachometer_record_note(note: str | None) -> dict[str, str | None]:
    parsed = {
        "source": None,
        "protocol_number": None,
        "inspection_type": None,
    }
    if not note:
        return parsed

    for raw_part in str(note).split("|"):
        part = raw_part.strip()
        if not part or ":" not in part:
            continue
        key, value = part.split(":", 1)
        normalized_key = key.strip().lower()
        normalized_value = value.strip() or None
        if normalized_key == "zdroj":
            parsed["source"] = normalized_value
        elif normalized_key == "protokol":
            parsed["protocol_number"] = normalized_value
        elif normalized_key == "typ":
            parsed["inspection_type"] = normalized_value
    return parsed


def _build_tachometer_entry_summary(
    *,
    inspection_type: str | None,
    inspection_kind: str | None,
    protocol_number: str | None,
    source: str | None,
) -> str:
    parts = []
    if inspection_type:
        parts.append(inspection_type)
    if inspection_kind:
        parts.append(inspection_kind)
    if protocol_number:
        parts.append(f"Protokol {protocol_number}")
    if source:
        parts.append(f"Zdroj {source}")
    if not parts:
        return "Importovaný záznam z kontroly tachometru."
    return " • ".join(parts)


def _build_unavailable_tachometer_documents(protocol_number: str | None) -> list[dict[str, Any]]:
    if not protocol_number:
        return []
    return [
        {
            "document_id": f"protocol:{protocol_number}",
            "title": f"Protokol {protocol_number}",
            "document_type": "protocol",
            "available": False,
            "open_mode": "unavailable",
            "reason": "Dokument není dostupný v uložených datech.",
            "external_url": None,
            "internal_proxy_url": None,
            "source_reference": None,
        }
    ]


def _build_tachometer_documents(
    *,
    protocol_number: str | None,
    parsed_documents: list[dict[str, Any]],
    detail_available: bool,
    source_detail_reference: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if parsed_documents:
        return parsed_documents
    if not protocol_number:
        return []
    documents = _build_unavailable_tachometer_documents(protocol_number)
    if detail_available and documents:
        documents[0]["reason"] = "Portál vrátil detail kontroly, ale nevrátil otevřitelný dokument / PDF."
    if source_detail_reference and documents:
        documents[0]["source_reference"] = json.dumps(source_detail_reference, ensure_ascii=False)
    return documents


def _deserialize_string_list(raw_payload: str | None) -> list[str]:
    if not raw_payload:
        return []
    try:
        payload = json.loads(raw_payload)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [str(item).strip() for item in payload if str(item).strip()]


def _deserialize_json_object(raw_payload: str | None) -> dict[str, Any] | None:
    if not raw_payload:
        return None
    try:
        payload = json.loads(raw_payload)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _tachometer_entry_metadata(
    entry: VehicleTachometerHistoryEntryModel,
) -> dict[str, Any]:
    payload = _deserialize_json_object(getattr(entry, "raw_payload_json", None)) or {}
    inspection_type = str(payload.get("inspection_type") or getattr(entry, "inspection_type", None) or "").strip() or None
    inspection_kind = str(payload.get("inspection_kind") or "").strip() or None
    result_label = str(payload.get("result_label") or "").strip() or None
    note_text = str(payload.get("note_text") or "").strip() or None

    if inspection_type and not inspection_kind and " / " in inspection_type:
        primary, secondary = inspection_type.split(" / ", 1)
        inspection_type = primary.strip() or inspection_type
        inspection_kind = secondary.strip() or None

    return {
        "inspection_type": inspection_type,
        "inspection_kind": inspection_kind,
        "result_label": result_label,
        "note_text": note_text,
    }


def _tachometer_history_sort_key(entry: VehicleTachometerHistoryEntryModel) -> tuple[datetime, int, int]:
    return (
        getattr(entry, "check_date", None) or datetime.min,
        int(getattr(entry, "mileage_km", None) or -1),
        int(getattr(entry, "id", 0) or 0),
    )


def _tachometer_entry_precision_score(entry: VehicleTachometerHistoryEntryModel) -> int:
    score = 0
    documents = _serialize_tachometer_documents(getattr(entry, "documents_json", None))
    if any(item.available for item in documents):
        score += 40
    if _deserialize_json_object(getattr(entry, "detail_snapshot_json", None)):
        score += 30
    if _deserialize_json_object(getattr(entry, "source_detail_reference", None)):
        score += 20
    if _deserialize_string_list(getattr(entry, "findings_items_json", None)):
        score += 10
    if getattr(entry, "protocol_number", None):
        score += 5
    if str(getattr(entry, "status", "") or "").lower() != "imported_legacy":
        score += 3
    return score


def _select_canonical_tachometer_entry(
    entries: list[VehicleTachometerHistoryEntryModel],
) -> VehicleTachometerHistoryEntryModel:
    return max(
        entries,
        key=lambda entry: (
            int(getattr(entry, "mileage_km", None) or -1),
            _tachometer_entry_precision_score(entry),
            1 if getattr(entry, "check_date", None) is not None else 0,
            int(getattr(entry, "id", 0) or 0),
        ),
    )


def _deduplicate_tachometer_history_entries(
    entries: list[VehicleTachometerHistoryEntryModel],
) -> list[_NormalizedTachometerHistoryItem]:
    sorted_entries = sorted(entries, key=_tachometer_history_sort_key)
    groups: list[list[VehicleTachometerHistoryEntryModel]] = []
    current_group: list[VehicleTachometerHistoryEntryModel] = []

    for entry in sorted_entries:
        if not current_group:
            current_group = [entry]
            continue

        current_date = (getattr(current_group[-1], "check_date", None) or datetime.min).date()
        entry_date = (getattr(entry, "check_date", None) or datetime.min).date()
        current_mileage = int(getattr(current_group[-1], "mileage_km", None) or -1)
        entry_mileage = int(getattr(entry, "mileage_km", None) or -1)

        if entry_date == current_date and current_mileage >= 0 and entry_mileage >= 0 and abs(entry_mileage - current_mileage) <= 5:
            current_group.append(entry)
            continue

        groups.append(current_group)
        current_group = [entry]

    if current_group:
        groups.append(current_group)

    normalized: list[_NormalizedTachometerHistoryItem] = []
    for group in groups:
        canonical_entry = _select_canonical_tachometer_entry(group)
        merged_entries = sorted(group, key=_tachometer_history_sort_key)
        merge_reason = None
        if len(merged_entries) > 1:
            merge_reason = (
                "Sloučeno jako near-duplicate: stejné datum kontroly a rozdíl km do 5 km; "
                "ponechán záznam s vyšším km nebo přesnějším zdrojem."
            )
        normalized.append(
            _NormalizedTachometerHistoryItem(
                canonical_entry=canonical_entry,
                merged_entries=merged_entries,
                merge_reason=merge_reason,
            )
        )
    return normalized


def _apply_tachometer_history_monotonicity(
    items: list[_NormalizedTachometerHistoryItem],
) -> list[_NormalizedTachometerHistoryItem]:
    previous_mileage: int | None = None
    for item in items:
        current_mileage = getattr(item.canonical_entry, "mileage_km", None)
        if current_mileage is None:
            item.is_monotonic_valid = previous_mileage is None
            continue
        if previous_mileage is not None and int(current_mileage) < int(previous_mileage):
            item.is_monotonic_valid = False
            item.anomaly = True
            item.anomaly_type = "km_decrease"
            item.anomaly_delta_km = int(current_mileage) - int(previous_mileage)
        else:
            item.is_monotonic_valid = True
            item.anomaly = False
            item.anomaly_type = None
            item.anomaly_delta_km = None
        previous_mileage = int(current_mileage)
    return items


def _normalized_tachometer_history(vehicle_id: int, db: Session) -> list[_NormalizedTachometerHistoryItem]:
    raw_entries = _tachometer_history_query(vehicle_id, db)
    deduped = _deduplicate_tachometer_history_entries(raw_entries)
    return _apply_tachometer_history_monotonicity(deduped)


def _serialize_tachometer_documents(documents_raw: str | None) -> list[VehicleTachometerDocumentResponse]:
    if not documents_raw:
        return []
    try:
        payload = json.loads(documents_raw)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []

    serialized: list[VehicleTachometerDocumentResponse] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("document_id") or "Dokument").strip()
        if not title:
            title = "Dokument"
        serialized.append(
            VehicleTachometerDocumentResponse(
                document_id=str(item.get("document_id") or title),
                title=title,
                document_type=str(item.get("document_type") or "document"),
                available=bool(item.get("available")),
                open_mode=str(item.get("open_mode") or "unavailable"),
                reason=(str(item.get("reason")).strip() if item.get("reason") is not None else None),
                external_url=(str(item.get("external_url")).strip() if item.get("external_url") else None),
                internal_proxy_url=(str(item.get("internal_proxy_url")).strip() if item.get("internal_proxy_url") else None),
                source_reference=(str(item.get("source_reference")).strip() if item.get("source_reference") else None),
            )
        )
    return serialized


def _tachometer_history_entry_to_summary(
    item: _NormalizedTachometerHistoryItem,
) -> VehicleTachometerHistoryEntryResponse:
    entry = item.canonical_entry
    metadata = _tachometer_entry_metadata(entry)
    documents = _serialize_tachometer_documents(getattr(entry, "documents_json", None))
    available_documents = [item for item in documents if item.available]
    detail_snapshot = _deserialize_json_object(getattr(entry, "detail_snapshot_json", None))
    detail_reference = _deserialize_json_object(getattr(entry, "source_detail_reference", None))
    return VehicleTachometerHistoryEntryResponse(
        id=int(entry.id),
        check_date=getattr(entry, "check_date", None),
        mileage_km=getattr(entry, "mileage_km", None),
        protocol_number=getattr(entry, "protocol_number", None),
        inspection_type=metadata["inspection_type"],
        inspection_kind=metadata["inspection_kind"],
        result_label=metadata["result_label"],
        note_text=metadata["note_text"],
        source=getattr(entry, "source", None),
        status=str(getattr(entry, "status", None) or "imported"),
        read_only=bool(getattr(entry, "read_only", True)),
        summary=getattr(entry, "summary", None),
        findings_summary=getattr(entry, "findings_summary", None),
        findings_items=_deserialize_string_list(getattr(entry, "findings_items_json", None)),
        detail_available=bool(detail_snapshot or _is_openable_tachometer_detail_reference(detail_reference)),
        detail_snapshot_json=detail_snapshot,
        source_detail_reference=detail_reference,
        is_monotonic_valid=item.is_monotonic_valid,
        anomaly=item.anomaly,
        anomaly_type=item.anomaly_type,
        anomaly_delta_km=item.anomaly_delta_km,
        merged_duplicate_count=max(len(item.merged_entries) - 1, 0),
        merged_entry_ids=[int(getattr(merged_entry, "id", 0) or 0) for merged_entry in item.merged_entries],
        merge_reason=item.merge_reason,
        has_documents=bool(available_documents),
        documents_count=len(available_documents),
        documents=documents,
    )


def _tachometer_history_entry_to_detail(
    item: _NormalizedTachometerHistoryItem,
) -> VehicleTachometerHistoryEntryDetailResponse:
    entry = item.canonical_entry
    metadata = _tachometer_entry_metadata(entry)
    documents = _serialize_tachometer_documents(getattr(entry, "documents_json", None))
    available_documents = [item for item in documents if item.available]
    detail_snapshot = _deserialize_json_object(getattr(entry, "detail_snapshot_json", None))
    detail_reference = _deserialize_json_object(getattr(entry, "source_detail_reference", None))
    return VehicleTachometerHistoryEntryDetailResponse(
        id=int(entry.id),
        check_date=getattr(entry, "check_date", None),
        mileage_km=getattr(entry, "mileage_km", None),
        protocol_number=getattr(entry, "protocol_number", None),
        inspection_type=metadata["inspection_type"],
        inspection_kind=metadata["inspection_kind"],
        result_label=metadata["result_label"],
        note_text=metadata["note_text"],
        source=getattr(entry, "source", None),
        status=str(getattr(entry, "status", None) or "imported"),
        read_only=bool(getattr(entry, "read_only", True)),
        summary=getattr(entry, "summary", None),
        findings_summary=getattr(entry, "findings_summary", None),
        findings_items=_deserialize_string_list(getattr(entry, "findings_items_json", None)),
        detail_available=bool(detail_snapshot or _is_openable_tachometer_detail_reference(detail_reference)),
        detail_snapshot_json=detail_snapshot,
        source_detail_reference=detail_reference,
        is_monotonic_valid=item.is_monotonic_valid,
        anomaly=item.anomaly,
        anomaly_type=item.anomaly_type,
        anomaly_delta_km=item.anomaly_delta_km,
        merged_duplicate_count=max(len(item.merged_entries) - 1, 0),
        merged_entry_ids=[int(getattr(merged_entry, "id", 0) or 0) for merged_entry in item.merged_entries],
        merge_reason=item.merge_reason,
        has_documents=bool(available_documents),
        documents_count=len(available_documents),
        documents=documents,
    )


def _vehicle_to_response_payload(
    vehicle: VehicleModel,
    current_user: Customer,
    db: Session,
    *,
    include_technical_overview: bool = True,
) -> dict:
    owner = get_primary_vehicle_owner(db, vehicle)
    current_owner_since = get_current_owner_since(db, vehicle)
    primary_photo_payload, photo_path_token = _primary_photo_payload_for_api(vehicle=vehicle, db=db)
    active_qr_token = (
        db.query(VehicleQrTokenModel)
        .filter(
            VehicleQrTokenModel.vehicle_id == int(vehicle.id),
            VehicleQrTokenModel.active.is_(True),
            VehicleQrTokenModel.revoked_at.is_(None),
        )
        .order_by(VehicleQrTokenModel.issued_at.desc(), VehicleQrTokenModel.id.desc())
        .first()
    )
    public_history_url = (
        build_public_history_page_url(str(active_qr_token.token))
        if active_qr_token and getattr(active_qr_token, "token", None)
        else None
    )
    remaining_catalog_image_regenerations = _remaining_catalog_image_regenerations(
        db, vehicle_id=int(vehicle.id), vehicle=vehicle
    )
    payload = {
        "id": vehicle.id,
        "user_email": getattr(vehicle, "user_email", None),
        "nickname": getattr(vehicle, "nickname", None),
        "brand": getattr(vehicle, "brand", None),
        "model": getattr(vehicle, "model", None),
        "year": getattr(vehicle, "year", None),
        "fuel": getattr(vehicle, "fuel", None),
        "body_type": getattr(vehicle, "body_type", None),
        "engine": getattr(vehicle, "engine", None),
        "vin": getattr(vehicle, "vin", None),
        "plate": getattr(vehicle, "plate", None),
        "orv_number": getattr(vehicle, "orv_number", None),
        "orv_scan_source": getattr(vehicle, "orv_scan_source", None),
        "orv_front_image_path": getattr(vehicle, "orv_front_image_path", None),
        "orv_back_image_path": getattr(vehicle, "orv_back_image_path", None),
        "orv_scanned_at": getattr(vehicle, "orv_scanned_at", None),
        "orv_confidence_json": getattr(vehicle, "orv_confidence_json", None),
        "data_trust_state": getattr(vehicle, "data_trust_state", None),
        "notes": getattr(vehicle, "notes", None),
        "primary_photo": primary_photo_payload,
        "photo_path": photo_path_token,
        "catalog_image_id": getattr(vehicle, "catalog_image_id", None),
        "catalog_image_url": getattr(vehicle, "catalog_image_url", None),
        "can_regenerate_catalog_image": (not _catalog_image_regen_limit_enabled()) or remaining_catalog_image_regenerations > 0,
        "remaining_catalog_image_regenerations": remaining_catalog_image_regenerations,
        "stk_valid_until": getattr(vehicle, "stk_valid_until", None),
        "current_mileage_km": getattr(vehicle, "current_mileage_km", None),
        "last_stk_mileage_km": getattr(vehicle, "last_stk_mileage_km", None),
        "mileage_checked_at": getattr(vehicle, "mileage_checked_at", None),
        "tyres_info": getattr(vehicle, "tyres_info", None),
        "insurance_provider": getattr(vehicle, "insurance_provider", None),
        "insurance_valid_until": getattr(vehicle, "insurance_valid_until", None),
        "current_owner_since": current_owner_since,
        "has_qr_token": bool(active_qr_token),
        "qr_public_mode": getattr(active_qr_token, "public_mode", None) if active_qr_token else None,
        "qr_last_access_at": getattr(active_qr_token, "last_access_at", None) if active_qr_token else None,
        "public_history_url": public_history_url,
        "qr_svg": render_vehicle_qr_svg(public_history_url) if public_history_url else None,
        "tenant_id": getattr(vehicle, "tenant_id", None),
        "created_at": getattr(vehicle, "created_at", None),
    }

    if include_technical_overview:
        try:
            from ..services.vehicle_technical_overview import technical_overview_for_api

            sto = getattr(vehicle, "vehicle_technical_overview", None)
            payload["technical_overview"] = technical_overview_for_api(sto) if sto else None
        except Exception:
            payload["technical_overview"] = None
    else:
        payload["technical_overview"] = None

    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    current_email = str(getattr(current_user, "email", "") or "").strip().lower()
    owner_email = str(getattr(owner, "email", None) or getattr(vehicle, "user_email", "") or "").strip().lower()
    is_owner = bool(current_email) and current_email == owner_email
    is_admin_role = is_admin(role_key)

    prov_id = getattr(vehicle, "provisioned_by_service_customer_id", None)
    payload["provisioned_by_service_customer_id"] = int(prov_id) if prov_id else None
    payload["provisioned_by_service_label"] = None
    if prov_id and is_owner:
        svc = db.query(Customer).filter(Customer.id == int(prov_id)).first()
        if svc:
            payload["provisioned_by_service_label"] = (svc.name or svc.email or "Servis").strip()
    payload["added_by_service_name"] = payload.get("provisioned_by_service_label")
    if not is_owner and not is_admin_role:
        payload["user_email"] = "hidden"
        payload["tenant_id"] = None

    return payload


def _vehicle_preferred_catalog_color(vehicle: VehicleModel) -> str | None:
    """Vytáhne barvu karoserie z uložených VIN poznámek, pokud ji decoder už propsal."""
    text_parts = [
        getattr(vehicle, "notes", None),
        getattr(vehicle, "tyres_info", None),
        getattr(vehicle, "body_type", None),
    ]
    haystack = "\n".join(str(part or "") for part in text_parts if part)
    if not haystack:
        return None
    patterns = (
        r"Barva\s+karoserie\s*:\s*([^\n\r;,.]+)",
        r"Barva\s*:\s*([^\n\r;,.]+)",
        r"Karoserie\s*/\s*barva\s*:\s*([^\n\r;,.]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, haystack, flags=re.IGNORECASE)
        if match:
            value = str(match.group(1) or "").strip()
            if value:
                return value
    return None


@router.post("/preview-from-vin", response_model=VehiclePreviewFromVinResponseV1)
async def preview_from_vin(
    payload: VehiclePreviewFromVinRequestV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from ..decoder.router import decode_vin_core

    vin = str(payload.vin or "").strip().upper().replace(" ", "").replace("-", "")
    try:
        assert_vin_visible_for_create(
            db,
            getattr(current_user, "tenant_id", None),
            vin,
            endpoint="/api/v1/vehicles/preview-from-vin",
        )
    except VinAlreadyRegisteredOtherUserError:
        return JSONResponse(status_code=409, content=vin_other_tenant_block_payload())
    warnings: list[str] = []
    decode_data = None
    if payload.decoded and payload.decoded.make and payload.decoded.model:
        decode_data = VehicleDecodedData(
            vin=vin,
            make=payload.decoded.make,
            model=payload.decoded.model,
            production_year=payload.decoded.year,
            body_type=payload.decoded.body_type,
            exterior_color=payload.decoded.exterior_color,
            source_priority=[payload.decoded.source or "existing-vin-decoder"],
        )
        logger.info("[VIN_PREVIEW] using decoded hint vin=%s source=%s", vin[:6], payload.decoded.source or "client-hint")
    else:
        try:
            decode_response: VehicleDecodeResponse = await decode_vin_core(
                VinDecodeRequest(vin=vin),
                db,
                current_user,
            )
        except VinAlreadyRegisteredOtherUserError:
            return JSONResponse(status_code=409, content=vin_other_tenant_block_payload())
        except Exception as exc:
            logger.warning("[VIN_PREVIEW] decode invocation failed vin=%s error=%s", vin[:6], exc)
            fallback_image = {
                "id": None,
                "url": "/web/assets/vehicle-placeholder.svg",
                "thumbnail_url": "/web/assets/vehicle-placeholder.svg",
                "source_domain": None,
                "provider": "disabled",
                "score": 0,
                "representative": True,
                "verified_real_vehicle": False,
                "license_note": "Ilustrační katalogová fotka – nejde o skutečnou fotku vozidla.",
            }
            return VehiclePreviewFromVinResponseV1(
                ok=False,
                vin=vin,
                decoded=None,
                catalog_image=fallback_image,
                alternatives=[],
                warnings=["VIN decode failed; preview fallback used."],
                reason=str(exc),
                can_regenerate=not _catalog_image_regen_limit_enabled(),
                remaining_regenerations=999 if not _catalog_image_regen_limit_enabled() else 0,
            )

        if not decode_response.success or not decode_response.data:
            fallback_image = {
                "id": None,
                "url": "/web/assets/vehicle-placeholder.svg",
                "thumbnail_url": "/web/assets/vehicle-placeholder.svg",
                "source_domain": None,
                "provider": "disabled",
                "score": 0,
                "representative": True,
                "verified_real_vehicle": False,
                "license_note": "Ilustrační katalogová fotka – nejde o skutečnou fotku vozidla.",
            }
            return VehiclePreviewFromVinResponseV1(
                ok=False,
                vin=vin,
                decoded=None,
                catalog_image=fallback_image,
                alternatives=[],
                warnings=list(decode_response.errors or []),
                reason=(decode_response.errors or ["VIN decode failed"])[0],
                can_regenerate=not _catalog_image_regen_limit_enabled(),
                remaining_regenerations=999 if not _catalog_image_regen_limit_enabled() else 0,
            )
        decode_data = decode_response.data

    service = get_vehicle_catalog_image_service()
    result = service.preview_from_decoded_vehicle(
        db=db,
        vin=vin,
        decoded_vehicle=decode_data,
        preferred_color=payload.preferred_color or getattr(decode_data, "exterior_color", None),
        force_refresh=payload.force_refresh,
        current_user=current_user,
    )
    warnings.extend(result.warnings)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("[VIN_PREVIEW] catalog image commit failed vin=%s error=%s", vin[:6], exc)
        fallback_image = {
            "id": None,
            "url": "/web/assets/vehicle-placeholder.svg",
            "thumbnail_url": "/web/assets/vehicle-placeholder.svg",
            "source_domain": None,
            "provider": "disabled",
            "score": 0,
            "representative": True,
            "verified_real_vehicle": False,
            "license_note": "Ilustrační katalogová fotka – nejde o skutečnou fotku vozidla.",
        }
        return VehiclePreviewFromVinResponseV1(
            ok=False,
            vin=vin,
            decoded=result.decoded,
            catalog_image=fallback_image,
            alternatives=[],
            warnings=warnings + ["Katalogovou fotku se nepodařilo uložit."],
            reason="Catalog image persistence failed",
            can_regenerate=not _catalog_image_regen_limit_enabled(),
            remaining_regenerations=999 if not _catalog_image_regen_limit_enabled() else 1,
        )
    return VehiclePreviewFromVinResponseV1(
        ok=result.ok,
        vin=result.vin,
        decoded=result.decoded,
        catalog_image=result.catalog_image,
        alternatives=result.alternatives,
        warnings=warnings,
        reason=result.reason,
        can_regenerate=True,
        remaining_regenerations=999 if not _catalog_image_regen_limit_enabled() else 1,
    )


@router.post("/{vehicle_id}/catalog-image/generate", response_model=VehiclePreviewFromVinResponseV1)
def generate_catalog_image_for_vehicle(
    vehicle_id: int,
    payload: VehicleCatalogImageGenerateRequestV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(vehicle_id)).first()
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    regeneration_count = _count_catalog_image_regenerations(db, vehicle_id=int(vehicle_id))
    remaining_before = _remaining_catalog_image_regenerations(db, vehicle_id=int(vehicle_id), vehicle=vehicle)
    if _catalog_image_regen_limit_enabled() and remaining_before <= 0:
        raise HTTPException(status_code=429, detail="Další katalogovou fotku už jste pro toto vozidlo vyčerpali.")

    service = get_vehicle_catalog_image_service()
    last_integrity_error: IntegrityError | None = None
    result = None
    saved_to_gallery = False
    saved_gallery_photo_id: int | None = None
    primary_photo_asset_id: int | None = None

    for attempt in range(2):
        try:
            result = service.preview_from_vehicle_snapshot(
                db=db,
                vin=getattr(vehicle, "vin", None),
                make=getattr(vehicle, "brand", None),
                model=getattr(vehicle, "model", None),
                year=getattr(vehicle, "year", None),
                body_type=getattr(vehicle, "body_type", None),
                preferred_color=payload.preferred_color or _vehicle_preferred_catalog_color(vehicle),
                force_refresh=True,
                current_user=current_user,
            )

            saved_to_gallery = False
            saved_gallery_photo_id = None
            primary_photo_asset_id = None
            catalog_provider = str((result.catalog_image or {}).get("provider") or "").strip().lower()
            catalog_url = str((result.catalog_image or {}).get("url") or "").strip()
            valid_catalog_image = bool(catalog_url) and catalog_url != "/web/assets/vehicle-placeholder.svg" and catalog_provider not in {"disabled", "placeholder"} and (
                catalog_provider != "mock" or app_config.VEHICLE_IMAGE_PROVIDER == "mock"
            )
            if result.catalog_image and valid_catalog_image:
                vehicle.catalog_image_id = result.catalog_image.get("id")
                vehicle.catalog_image_url = result.catalog_image.get("url")
                if payload.save_to_gallery and result.catalog_image.get("provider") != "disabled":
                    try:
                        stored_photo_id = _store_catalog_image_in_gallery(
                            vehicle=vehicle,
                            current_user=current_user,
                            image_url=str(result.catalog_image.get("url") or ""),
                            source_label="catalog_image",
                            db=db,
                            allow_duplicate=True,
                        )
                        saved_to_gallery = stored_photo_id is not None
                        saved_gallery_photo_id = int(stored_photo_id) if stored_photo_id is not None else None
                        if saved_gallery_photo_id is not None:
                            _maybe_autoset_primary_from_catalog_gallery_row(
                                db,
                                vehicle=vehicle,
                                gallery_asset_id=saved_gallery_photo_id,
                                current_user=current_user,
                                replace_existing=True,
                            )
                            primary_photo_asset_id = int(getattr(vehicle, "primary_photo_asset_id", 0) or 0) or None
                    except Exception as exc:
                        logger.warning("[CATALOG_IMAGE] gallery save failed vehicle_id=%s error=%s", vehicle_id, exc)
                        result.warnings.append("Katalogová fotka se zobrazila, ale nepodařilo se ji uložit do galerie.")
            elif result.catalog_image and str(result.catalog_image.get("url") or "").strip() == "/web/assets/vehicle-placeholder.svg":
                if str(getattr(vehicle, "catalog_image_url", "") or "").strip() == "/web/assets/vehicle-placeholder.svg":
                    vehicle.catalog_image_id = None
                    vehicle.catalog_image_url = None
                result.warnings.append("Pro toto vozidlo se nepodařilo najít reprezentativní katalogovou fotku; placeholder se neuložil jako galerie.")
            elif result.catalog_image and catalog_provider == "mock" and app_config.VEHICLE_IMAGE_PROVIDER != "mock":
                vehicle.catalog_image_id = None
                vehicle.catalog_image_url = None
                result.warnings.append("Testovací mock katalogová fotka se v produkčním režimu neuložila. Nahrajte vlastní fotku nebo zkuste generování znovu.")

            write_global_audit_log(
                db,
                entity_type="vehicle",
                entity_id=int(vehicle.id),
                action="vehicle_catalog_image_regenerated",
                actor_user_id=getattr(current_user, "id", None),
                actor_role=getattr(current_user, "role", None),
                tenant_id=getattr(current_user, "tenant_id", None),
                vehicle_id=int(vehicle.id),
                metadata={
                    "vehicle_id": int(vehicle.id),
                    "provider": (result.catalog_image or {}).get("provider"),
                    "saved_to_gallery": saved_to_gallery,
                    "saved_gallery_photo_id": saved_gallery_photo_id,
                    "primary_photo_asset_id": primary_photo_asset_id,
                },
            )
            db.commit()
            break
        except IntegrityError as exc:
            db.rollback()
            if "vehicle_catalog_images.id" not in str(exc):
                raise
            last_integrity_error = exc
            logger.warning(
                "[CATALOG_IMAGE] duplicate catalog image row recovered vehicle_id=%s attempt=%s error=%s",
                vehicle_id,
                attempt + 1,
                exc,
            )
            vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(vehicle_id)).first()
            if vehicle is None:
                raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    else:
        if last_integrity_error is not None:
            raise last_integrity_error

    db.refresh(vehicle)

    return VehiclePreviewFromVinResponseV1(
        ok=result.ok,
        vin=result.vin or str(getattr(vehicle, "vin", "") or ""),
        decoded=result.decoded,
        catalog_image=result.catalog_image,
        alternatives=result.alternatives,
        warnings=result.warnings,
        reason=result.reason,
        can_regenerate=(not _catalog_image_regen_limit_enabled()) or max(0, remaining_before - 1) > 0,
        remaining_regenerations=999 if not _catalog_image_regen_limit_enabled() else max(0, remaining_before - 1),
        saved_to_gallery=saved_to_gallery,
        saved_gallery_photo_id=saved_gallery_photo_id,
        primary_photo_asset_id=primary_photo_asset_id,
    )


@router.get("/catalog-images/{image_id}/file")
def get_catalog_image_file(
    image_id: str,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")
    row = db.query(VehicleCatalogImageModel).filter(VehicleCatalogImageModel.id == str(image_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Katalogová fotka nebyla nalezena")
    # Katalogové ilustrace (make/model cache) jsou sdílené — tenant_id v DB značí původ cache, ne ACL.
    try:
        ensure_catalog_image_storage(row, db=db)
        db.commit()
    except Exception as exc:
        logger.warning("[CATALOG_IMAGE] lazy storage hydration failed image_id=%s error=%s", image_id, exc)
        db.rollback()
    catalog_file = resolve_catalog_image_storage_file(row)
    if not catalog_file or not catalog_file.exists():
        raise HTTPException(status_code=404, detail="Soubor katalogové fotky neexistuje")
    return FileResponse(path=str(catalog_file), media_type="image/jpeg", filename=f"{image_id}.jpg")


def _validate_mileage_consistency(
    *,
    current_mileage_km: int | None,
    last_stk_mileage_km: int | None,
) -> None:
    if current_mileage_km is None or last_stk_mileage_km is None:
        return
    if current_mileage_km < last_stk_mileage_km:
        raise HTTPException(
            status_code=422,
            detail=(
                "Aktuální stav km nesmí být menší než poslední známý stav km ze STK/emisí "
                f"({last_stk_mileage_km:,} km)."
            ).replace(",", " "),
        )


def _find_duplicate_vehicle_by_vin(
    *,
    db: Session,
    tenant_id: int | None,
    vin: str | None,
    exclude_vehicle_id: int | None = None,
) -> VehicleModel | None:
    normalized_vin = _normalize_vin(vin or "")
    if not normalized_vin:
        return None

    query = db.query(VehicleModel).filter(VehicleModel.vin.isnot(None))
    if tenant_id is None:
        query = query.filter(VehicleModel.tenant_id.is_(None))
    else:
        query = query.filter(VehicleModel.tenant_id == tenant_id)

    if exclude_vehicle_id is not None:
        query = query.filter(VehicleModel.id != exclude_vehicle_id)

    for candidate in query.all():
        candidate_vin = _normalize_vin(getattr(candidate, "vin", "") or "")
        if candidate_vin == normalized_vin:
            return candidate
    return None


def _find_existing_vehicle_by_vin_globally(
    *,
    db: Session,
    vin: str | None,
    exclude_vehicle_id: int | None = None,
) -> VehicleModel | None:
    normalized_vin = _normalize_vin(vin or "")
    if not normalized_vin:
        return None
    query = db.query(VehicleModel).filter(VehicleModel.vin.isnot(None))
    if exclude_vehicle_id is not None:
        query = query.filter(VehicleModel.id != exclude_vehicle_id)
    candidates = query.order_by(VehicleModel.created_at.asc(), VehicleModel.id.asc()).all()
    for candidate in candidates:
        if _normalize_vin(getattr(candidate, "vin", "") or "") == normalized_vin:
            return candidate
    return None


def _apply_vehicle_claim_payload(vehicle: VehicleModel, vehicle_data: VehicleCreateV1) -> None:
    normalized_vin = _normalize_vin(vehicle_data.vin or "")
    if normalized_vin:
        vehicle.vin = normalized_vin
    if vehicle_data.nickname:
        vehicle.nickname = vehicle_data.nickname
    if vehicle_data.brand:
        vehicle.brand = vehicle_data.brand
    if vehicle_data.model:
        vehicle.model = vehicle_data.model
    if vehicle_data.year is not None:
        vehicle.year = vehicle_data.year
    if vehicle_data.engine:
        vehicle.engine = vehicle_data.engine
    if vehicle_data.plate:
        vehicle.plate = vehicle_data.plate
    if vehicle_data.notes:
        vehicle.notes = vehicle_data.notes
    if vehicle_data.stk_valid_until is not None:
        vehicle.stk_valid_until = vehicle_data.stk_valid_until
    if vehicle_data.current_mileage_km is not None:
        vehicle.current_mileage_km = vehicle_data.current_mileage_km
    if vehicle_data.last_stk_mileage_km is not None:
        vehicle.last_stk_mileage_km = vehicle_data.last_stk_mileage_km
        vehicle.mileage_checked_at = datetime.utcnow()
    if vehicle_data.tyres_info:
        vehicle.tyres_info = vehicle_data.tyres_info
    if vehicle_data.insurance_provider:
        vehicle.insurance_provider = vehicle_data.insurance_provider
    if vehicle_data.insurance_valid_until is not None:
        vehicle.insurance_valid_until = vehicle_data.insurance_valid_until


def _revoke_vehicle_service_links_for_owner_release(
    db: Session,
    *,
    vehicle_id: int,
    revoked_by_customer_id: int,
    reason: str,
) -> None:
    from ..models import VehicleServiceLink

    now = datetime.utcnow()
    (
        db.query(VehicleServiceLink)
        .filter(
            VehicleServiceLink.vehicle_id == int(vehicle_id),
            VehicleServiceLink.status == "approved",
        )
        .update(
            {
                VehicleServiceLink.status: "revoked",
                VehicleServiceLink.revoked_at: now,
                VehicleServiceLink.revoked_by_customer_id: int(revoked_by_customer_id),
                VehicleServiceLink.revoked_reason: reason,
                VehicleServiceLink.updated_at: now,
            },
            synchronize_session=False,
        )
    )


@router.post("/parse-orv", response_model=ORVParseResponseV1)
def parse_orv(
    payload: ORVParseRequestV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_vehicle_schema_columns(db)
    scan = create_orv_scan_record(
        db=db,
        current_user=current_user,
        front_image_base64=payload.front_image_base64,
        back_image_base64=payload.back_image_base64,
        front_image_mime_type=payload.front_image_mime_type,
        back_image_mime_type=payload.back_image_mime_type,
        single_orv_image_base64=payload.single_orv_image_base64,
        single_orv_image_mime_type=payload.single_orv_image_mime_type,
        source=payload.source,
    )
    return serialize_orv_scan(scan)


@router.patch("/orv-scans/{scan_id}/review-audit", response_model=ORVReviewAuditResponseV1)
def save_orv_review_audit(
    scan_id: int,
    payload: ORVReviewAuditRequestV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Audit před uložením vozidla: uloží rozdíly oproti OCR a validaci VIN.
    Samotné vozidlo vzniká až odesláním nadřazeného formuláře (POST /vehicles).
    """
    _ensure_vehicle_schema_columns(db)
    result = apply_orv_review_audit(
        db=db,
        scan_id=scan_id,
        current_user=current_user,
        nickname=payload.nickname,
        brand=payload.brand,
        model=payload.model,
        year=payload.year,
        engine=payload.engine,
        vin=payload.vin,
        plate=payload.plate,
        orv_number=payload.orv_number,
    )
    return ORVReviewAuditResponseV1(**result)


@router.post("", response_model=VehicleOutV1)
def create_vehicle(
    vehicle_data: VehicleCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vytvoří nové vozidlo"""
    import logging
    from sqlalchemy.exc import IntegrityError
    from fastapi.responses import JSONResponse
    
    logger = logging.getLogger(__name__)

    _ensure_vehicle_photo_column(db)
    
    # Zkontrolovat tenant_id
    tenant_id = getattr(current_user, 'tenant_id', None)
    if not tenant_id:
        logger.error(f"[VEHICLE_CREATE] User {current_user.email} nemá tenant_id")
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "TENANT_MISSING",
                    "message": "Uživatel nemá přiřazený tenant. Kontaktujte administrátora.",
                    "details": {"user_email": current_user.email}
                }
            }
        )
    
    logger.info(f"[VEHICLE_CREATE] tenant_id={tenant_id} vin={vehicle_data.vin} plate={vehicle_data.plate}")
    
    try:
        # Validace povinných polí
        if not vehicle_data.nickname or len(vehicle_data.nickname.strip()) < 2:
            raise HTTPException(status_code=422, detail="Zadejte název vozidla (min. 2 znaky)")
        if not vehicle_data.stk_valid_until:
            raise HTTPException(status_code=422, detail="Zadejte platnost STK (datum)")
        _validate_mileage_consistency(
            current_mileage_km=vehicle_data.current_mileage_km,
            last_stk_mileage_km=vehicle_data.last_stk_mileage_km,
        )
        guard_result = assert_vin_visible_for_create(
            db,
            tenant_id,
            vehicle_data.vin,
            endpoint="/api/v1/vehicles",
            validate=False,
        )
        normalized_vin = guard_result.normalized_vin
        
        # KROK 1: Zkontrolovat quota
        from ...licensing.service import assert_vehicle_quota, LicenseError
        try:
            assert_vehicle_quota(db, tenant_id)
        except LicenseError as e:
            logger.warning(f"[VEHICLE_CREATE] error_code={e.code} details={e.details}")
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": {
                        "code": e.code,
                        "message": e.detail,
                        "details": e.details
                    }
                }
            )
        
        if vehicle_data.orv_scan_id and not normalized_vin:
            raise HTTPException(status_code=422, detail="ORV scan vyžaduje potvrzený VIN. Doplňte jej ručně před uložením.")

        existing_global_vehicle = _find_existing_vehicle_by_vin_globally(db=db, vin=normalized_vin)
        if existing_global_vehicle is not None:
            active_owner_assignment = get_primary_vehicle_owner_assignment(db, int(existing_global_vehicle.id))
            active_owner = get_primary_vehicle_owner(db, existing_global_vehicle)
            if active_owner and active_owner.id == current_user.id and active_owner_assignment and active_owner_assignment.is_active:
                logger.warning("[VEHICLE_CREATE] error_code=VEHICLE_DUPLICATE details={which_field: vin, scope: global_same_owner}")
                return JSONResponse(
                    status_code=409,
                    content={
                        "error": {
                            "code": "VEHICLE_DUPLICATE",
                            "message": "Vozidlo s tímto VIN už ve vašem profilu existuje",
                            "details": {"which_field": "vin", "value": normalized_vin},
                        }
                    },
                )
            if active_owner and active_owner.id != current_user.id and active_owner_assignment and active_owner_assignment.is_active:
                raise HTTPException(
                    status_code=409,
                    detail="Vozidlo s tímto VIN už má aktivního vlastníka. Pro převod jej nejdřív odeberte z původního profilu.",
                )

            _apply_vehicle_claim_payload(existing_global_vehicle, vehicle_data)
            claim_cat_id, claim_cat_url = _canonical_catalog_vehicle_fields(
                vehicle_data.catalog_image_id,
                vehicle_data.catalog_image_url,
            )
            existing_global_vehicle.catalog_image_id = claim_cat_id
            existing_global_vehicle.catalog_image_url = claim_cat_url
            apply_orv_scan_to_vehicle(
                db=db,
                vehicle=existing_global_vehicle,
                current_user=current_user,
                scan_id=vehicle_data.orv_scan_id,
                orv_number=vehicle_data.orv_number,
                use_owner_data=vehicle_data.orv_use_owner_data,
                data_trust_state=vehicle_data.data_trust_state or "verified_by_user",
                create_payload=vehicle_data.dict(),
            )
            transfer_vehicle_to_new_owner(
                db,
                vehicle=existing_global_vehicle,
                new_owner=current_user,
                assigned_by_customer_id=current_user.id,
                ownership_origin="vin_claim",
            )
            claim_gallery_catalog_url = _catalog_image_url_for_gallery_import(
                vehicle_data.catalog_image_id,
                vehicle_data.catalog_image_url,
            )
            catalog_gallery_photo_id_claim: int | None = None
            if claim_gallery_catalog_url:
                try:
                    catalog_gallery_photo_id_claim = _store_catalog_image_in_gallery(
                        vehicle=existing_global_vehicle,
                        current_user=current_user,
                        image_url=claim_gallery_catalog_url,
                        source_label="catalog_image_from_claim",
                        db=db,
                    )
                except Exception as exc:
                    logger.warning("[VEHICLE_CREATE] catalog gallery save skipped vehicle_id=%s error=%s", existing_global_vehicle.id, exc)
            _maybe_autoset_primary_from_catalog_gallery_row(
                db,
                vehicle=existing_global_vehicle,
                gallery_asset_id=catalog_gallery_photo_id_claim,
                current_user=current_user,
            )
            write_global_audit_log(
                db,
                entity_type="vehicle",
                entity_id=int(existing_global_vehicle.id),
                action="vehicle_create_vin_claim",
                actor_user_id=current_user.id,
                actor_role=getattr(current_user, "role", None),
                tenant_id=tenant_id,
                metadata={"vin": normalized_vin},
            )
            db.commit()
            db.refresh(existing_global_vehicle)
            logger.info(f"[VEHICLE_CREATE] claimed existing vehicle by VIN: id={existing_global_vehicle.id}")
            _finalize_vehicle_technical_overview(db, existing_global_vehicle)
            return _vehicle_to_response_payload(existing_global_vehicle, current_user, db)

        duplicate_vehicle = _find_duplicate_vehicle_by_vin(
            db=db,
            tenant_id=tenant_id,
            vin=normalized_vin,
        )
        if duplicate_vehicle is not None:
            logger.warning("[VEHICLE_CREATE] error_code=VEHICLE_DUPLICATE details={which_field: vin}")
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "VEHICLE_DUPLICATE",
                        "message": "Vozidlo s tímto VIN již existuje",
                        "details": {"which_field": "vin", "value": normalized_vin},
                    }
                },
            )

        # KROK 2: Vytvořit vozidlo
        canon_cat_id, canon_cat_url = _canonical_catalog_vehicle_fields(
            vehicle_data.catalog_image_id,
            vehicle_data.catalog_image_url,
        )
        vehicle = VehicleModel(
            user_email=current_user.email,
            tenant_id=tenant_id,
            nickname=vehicle_data.nickname,
            brand=vehicle_data.brand,
            model=vehicle_data.model,
            year=vehicle_data.year,
            engine=vehicle_data.engine,
            vin=normalized_vin or None,
            plate=vehicle_data.plate,
            notes=vehicle_data.notes,
            catalog_image_id=canon_cat_id,
            catalog_image_url=canon_cat_url,
            stk_valid_until=vehicle_data.stk_valid_until,
            current_mileage_km=vehicle_data.current_mileage_km,
            last_stk_mileage_km=vehicle_data.last_stk_mileage_km,
            mileage_checked_at=(
                datetime.utcnow()
                if vehicle_data.last_stk_mileage_km is not None
                else None
            ),
            tyres_info=vehicle_data.tyres_info,
            insurance_provider=vehicle_data.insurance_provider,
            insurance_valid_until=vehicle_data.insurance_valid_until
        )
        
        db.add(vehicle)
        db.flush()
        apply_orv_scan_to_vehicle(
            db=db,
            vehicle=vehicle,
            current_user=current_user,
            scan_id=vehicle_data.orv_scan_id,
            orv_number=vehicle_data.orv_number,
            use_owner_data=vehicle_data.orv_use_owner_data,
            data_trust_state=vehicle_data.data_trust_state or "verified_by_user",
            create_payload=vehicle_data.dict(),
        )
        ensure_vehicle_owner_assignment(
            db,
            vehicle=vehicle,
            owner=current_user,
            assigned_by_customer_id=current_user.id,
        )
        create_gallery_catalog_url = _catalog_image_url_for_gallery_import(
            vehicle_data.catalog_image_id,
            vehicle_data.catalog_image_url,
        )
        catalog_gallery_photo_id_create: int | None = None
        if create_gallery_catalog_url:
            try:
                catalog_gallery_photo_id_create = _store_catalog_image_in_gallery(
                    vehicle=vehicle,
                    current_user=current_user,
                    image_url=create_gallery_catalog_url,
                    source_label="catalog_image_from_create",
                    db=db,
                )
            except Exception as exc:
                logger.warning("[VEHICLE_CREATE] catalog gallery save skipped vehicle_id=%s error=%s", vehicle.id, exc)
        _maybe_autoset_primary_from_catalog_gallery_row(
            db,
            vehicle=vehicle,
            gallery_asset_id=catalog_gallery_photo_id_create,
            current_user=current_user,
        )
        write_global_audit_log(
            db,
            entity_type="vehicle",
            entity_id=int(vehicle.id),
            action="vehicle_create",
            actor_user_id=current_user.id,
            actor_role=getattr(current_user, "role", None),
            tenant_id=tenant_id,
            metadata={"nickname": vehicle.nickname, "plate": vehicle.plate},
        )
        db.commit()
        db.refresh(vehicle)

        logger.info(f"[VEHICLE_CREATE] ✅ Vozidlo vytvořeno: id={vehicle.id}")
        _finalize_vehicle_technical_overview(db, vehicle)
        return _vehicle_to_response_payload(vehicle, current_user, db)

    except VinAlreadyRegisteredOtherUserError:
        db.rollback()
        return JSONResponse(status_code=409, content=vin_other_tenant_block_payload())

    except IntegrityError as e:
        db.rollback()
        error_str = str(e.orig) if hasattr(e, 'orig') else str(e)
        
        # Detekce duplicitního VIN nebo SPZ
        which_field = None
        if 'vin' in error_str.lower() or 'unique constraint' in error_str.lower():
            # Zkontrolovat, zda je to VIN nebo SPZ
            if vehicle_data.vin:
                existing = db.query(VehicleModel).filter(
                    VehicleModel.vin == vehicle_data.vin,
                    VehicleModel.tenant_id == tenant_id
                ).first()
                if existing:
                    which_field = "vin"
        if not which_field and vehicle_data.plate:
            existing = db.query(VehicleModel).filter(
                VehicleModel.plate == vehicle_data.plate,
                VehicleModel.tenant_id == tenant_id
            ).first()
            if existing:
                which_field = "plate"
        
        if which_field:
            logger.warning(f"[VEHICLE_CREATE] error_code=VEHICLE_DUPLICATE details={{which_field: {which_field}}}")
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "VEHICLE_DUPLICATE",
                        "message": f"Vozidlo s tímto {which_field.upper()} již existuje",
                        "details": {"which_field": which_field, "value": getattr(vehicle_data, which_field)}
                    }
                }
            )
        else:
            # Obecná IntegrityError
            logger.error(f"[VEHICLE_CREATE] error_code=INTEGRITY_ERROR details={{error: {error_str}}}")
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INTEGRITY_ERROR",
                        "message": "Chyba při ukládání vozidla do databáze",
                        "details": {"error": error_str}
                    }
                }
            )
    
    except HTTPException as e:
        # LicenseError dědí z HTTPException
        if hasattr(e, 'code'):
            # LicenseError
            logger.warning(f"[VEHICLE_CREATE] error_code={e.code} details={getattr(e, 'details', {})}")
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": {
                        "code": e.code,
                        "message": e.detail,
                        "details": getattr(e, 'details', {})
                    }
                }
            )
        else:
            # Obecná HTTPException
            logger.error(f"[VEHICLE_CREATE] error_code=HTTP_ERROR status={e.status_code}")
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": {
                        "code": "HTTP_ERROR",
                        "message": e.detail,
                        "details": {}
                    }
                }
            )
    
    except Exception as e:
        db.rollback()
        import traceback
        error_traceback = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        logger.error(f"[VEHICLE_CREATE] error_code=UNKNOWN_ERROR details={{error: {str(e)}}}")
        logger.error(f"[VEHICLE_CREATE] Traceback:\n{error_traceback}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "UNKNOWN_ERROR",
                    "message": f"Neočekávaná chyba: {str(e)}",
                    "details": {"error_type": type(e).__name__}
                }
            }
        )


@router.get("", response_model=List[VehicleOutV1])
def get_vehicles(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací všechna vozidla uživatele"""
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    _ensure_vehicle_photo_column(db)
    
    try:
        logger.info(f"[VEHICLES] ========================================")
        logger.info(f"[VEHICLES] GET /api/v1/vehicles - Načítání vozidel")
        logger.info(f"[VEHICLES] User: {current_user.email}")
        logger.info(f"[VEHICLES] Tenant ID: {getattr(current_user, 'tenant_id', 'N/A')}")
        print(f"[VEHICLES] Načítání vozidel pro uživatele: {current_user.email}")
        print(f"[VEHICLES] Tenant ID uživatele: {getattr(current_user, 'tenant_id', 'N/A')}")
        
        tenant_id = getattr(current_user, "tenant_id", None)
        if tenant_id is None:
            logger.error("[VEHICLES] User bez tenant_id - fail safe 403")
            raise HTTPException(status_code=403, detail="Uživatel nemá přiřazený tenant")

        print(f"[VEHICLES] Filtrování podle tenant_id: {tenant_id}")
        owned_vehicle_ids = set()
        from ..models import VehicleOwnership
        current_user_id = getattr(current_user, "id", None)

        if current_user_id is not None:
            # Filtrovat podle tenantu *vozidla*, ne vehicle_ownerships.tenant_id.
            # U starších/ručních záznamů může být ownership.tenant_id nesouladný s customers.tenant_id
            # i s vehicles.tenant_id — admin a user_owns_vehicle vozidlo ukážou, seznam v aplikaci dřív ne.
            ownership_rows = (
                db.query(VehicleOwnership.vehicle_id)
                .join(VehicleModel, VehicleModel.id == VehicleOwnership.vehicle_id)
                .filter(
                    VehicleOwnership.customer_id == current_user_id,
                    VehicleOwnership.is_active.is_(True),
                    VehicleModel.tenant_id == tenant_id,
                )
                .all()
            )
            for (vehicle_id,) in ownership_rows:
                if vehicle_id:
                    owned_vehicle_ids.add(int(vehicle_id))

        # Legacy `vehicles.user_email` se musí sloučit vždy, ne jen když je ownership prázdný.
        # Jinak vozidlo bez řádku v vehicle_ownership (ale se správným user_email) zmizí ze seznamu,
        # jakmile uživatel získá alespoň jedno vozidlo přes vehicle_ownership.
        legacy_vehicles = (
            db.query(VehicleModel)
            .filter(
                func.lower(VehicleModel.user_email) == func.lower(current_user.email),
                VehicleModel.tenant_id == tenant_id,
                VehicleModel.status != "archived",
            )
            .all()
        )
        for vehicle in legacy_vehicles:
            backfill_vehicle_owner_assignment(db, vehicle)
            owned_vehicle_ids.add(int(vehicle.id))
        if legacy_vehicles:
            db.commit()

        vehicles = []
        if owned_vehicle_ids:
            vehicles = (
                db.query(VehicleModel)
                .filter(
                    VehicleModel.id.in_(owned_vehicle_ids),
                    VehicleModel.tenant_id == tenant_id,
                    VehicleModel.status != "archived",
                )
                .all()
            )

        print(f"[VEHICLES] Nalezeno {len(vehicles)} vozidel")
        
        # Zkusit explicitně serializovat každé vozidlo, abychom zachytili případné chyby
        result = []
        for idx, vehicle in enumerate(vehicles):
            try:
                # Zkontrolovat, zda vozidlo má všechny potřebné atributy
                if not hasattr(vehicle, 'id'):
                    logger.warning(f"[VEHICLES] WARNING: Vozidlo #{idx} nemá ID, přeskočeno")
                    print(f"[VEHICLES] WARNING: Vozidlo nemá ID, přeskočeno")
                    continue
                
                logger.debug(f"[VEHICLES] Serializuji vozidlo ID {vehicle.id}")
                vehicle_dict = _vehicle_to_response_payload(
                    vehicle, current_user, db, include_technical_overview=False
                )
                VehicleOutV1(**vehicle_dict)
                result.append(vehicle_dict)
            except Exception as veh_error:
                import traceback
                vehicle_id = getattr(vehicle, 'id', 'unknown')
                error_traceback = "".join(traceback.format_exception(type(veh_error), veh_error, veh_error.__traceback__))
                logger.error(f"[VEHICLES] ERROR: Chyba při validaci vozidla ID {vehicle_id}: {veh_error}")
                logger.error(f"[VEHICLES] Traceback:\n{error_traceback}")
                print(f"[VEHICLES] ERROR: Chyba při validaci vozidla ID {vehicle_id}: {veh_error}")
                traceback.print_exc()
                # Pokračovat s dalšími vozidly místo selhání celého dotazu
        
        logger.info(f"[VEHICLES] ✅ Úspěšně načteno {len(result)} vozidel")
        print(f"[VEHICLES] Vracím {len(result)} validních vozidel")
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_traceback = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        error_msg = str(e) if str(e) else "Neznámá chyba"
        logger.error(f"[VEHICLES] ❌ FATAL ERROR: {error_msg}")
        logger.error(f"[VEHICLES] Traceback:\n{error_traceback}")
        print(f"[VEHICLES] FATAL ERROR: {error_msg}")
        traceback.print_exc()
        error_type = type(e).__name__
        print(f"[ERROR] Chyba při načítání vozidel: {error_type}: {error_msg}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání vozidel: {error_type}: {error_msg}")


@router.post("/{vehicle_id}/tachometer/start", response_model=VehicleTachometerStartResponse)
def start_vehicle_tachometer(
    vehicle_id: int,
    payload: VehicleTachometerStartRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VehicleTachometerStartResponse:
    vehicle = _get_accessible_vehicle_or_404(vehicle_id, current_user, db)
    vin = _normalize_vin(getattr(vehicle, "vin", "") or "")
    if len(vin) != 17:
        raise HTTPException(
            status_code=422,
            detail="Pro kontrolu tachometru musí mít vozidlo uložené validní VIN (17 znaků).",
        )
    requested_vin = _normalize_vin(getattr(payload, "vin", "") or "")
    if requested_vin != vin:
        raise HTTPException(status_code=409, detail="Zadané VIN neodpovídá vozidlu.")
    try:
        started = create_browser_session(vehicle_id=vehicle.id, vin=vin)
    except TachometerBrowserError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return VehicleTachometerStartResponse(
        session_id=started.session_id,
        captcha_image=started.captcha_image_data_url,
        captcha_image_url=f"/api/v1/vehicles/{vehicle.id}/tachometer/captcha/{started.session_id}",
        expires_in_seconds=started.expires_in_seconds,
    )


@router.post("/{vehicle_id}/tachometer/init", response_model=VehicleTachometerInitResponse)
def init_vehicle_tachometer(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VehicleTachometerInitResponse:
    vehicle = _get_accessible_vehicle_or_404(vehicle_id, current_user, db)
    vin = _normalize_vin(getattr(vehicle, "vin", "") or "")
    started = start_vehicle_tachometer(
        vehicle_id=vehicle_id,
        payload=VehicleTachometerStartRequest(vin=vin),
        current_user=current_user,
        db=db,
    )
    return _start_response_to_legacy_init_response(started)


@router.get("/{vehicle_id}/tachometer/captcha/{session_id}")
def get_vehicle_tachometer_captcha(
    vehicle_id: int,
    session_id: str,
) -> Response:
    try:
        mime, payload = get_browser_session_captcha(session_id=session_id, vehicle_id=vehicle_id)
    except TachometerBrowserSessionExpired as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except TachometerBrowserError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    }
    return Response(content=payload, media_type=mime, headers=headers)


@router.post("/{vehicle_id}/tachometer/finish", response_model=VehicleTachometerFinishResponse)
def finish_vehicle_tachometer(
    vehicle_id: int,
    payload: VehicleTachometerFinishRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VehicleTachometerFinishResponse:
    vehicle = _get_accessible_vehicle_or_404(vehicle_id, current_user, db)
    vin = _normalize_vin(getattr(vehicle, "vin", "") or "")
    if len(vin) != 17:
        raise HTTPException(
            status_code=422,
            detail="Pro kontrolu tachometru musí mít vozidlo uložené validní VIN (17 znaků).",
        )
    try:
        result_html = submit_browser_session(
            session_id=payload.session_id,
            vehicle_id=vehicle.id,
            vin=vin,
            captcha_code=str(payload.captcha_code or "").strip(),
        )
    except TachometerBrowserInvalidCaptcha as exc:
        logger.info("[TACHOMETER] invalid captcha vehicle_id=%s vin=%s", vehicle.id, vin)
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Špatně opsaný kód z obrázku",
                "session_id": payload.session_id,
                "captcha_image": exc.captcha_image_data_url,
                "captcha_image_url": f"/api/v1/vehicles/{vehicle.id}/tachometer/captcha/{payload.session_id}",
                "expires_in_seconds": TACHOMETER_CHALLENGE_TTL_SECONDS,
            },
        ) from exc
    except TachometerBrowserSessionExpired as exc:
        logger.warning("[TACHOMETER] expired session vehicle_id=%s vin=%s", vehicle.id, vin)
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except TachometerBrowserError as exc:
        logger.exception("[TACHOMETER] browser submit failed vehicle_id=%s vin=%s", vehicle.id, vin)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    inspections = _parse_tachometer_inspections(result_html)
    if not inspections:
        raise HTTPException(
            status_code=404,
            detail="Pro zadané VIN nebyly nalezeny žádné údaje STK/emisí.",
        )
    latest = inspections[0]
    lookup = TachometerLookupResponse(
        vin=vin,
        latest_mileage_km=latest.mileage_km,
        latest_check_date=latest.check_date,
        inspections=inspections,
        source="kontrolatachometru.cz",
    )

    max_vm = (
        db.query(func.max(VehicleMileageModel.mileage_km))
        .filter(VehicleMileageModel.vehicle_id == vehicle.id)
        .scalar()
    )
    ceiling_values: list[int] = []
    cm = getattr(vehicle, "current_mileage_km", None)
    if cm is not None:
        ceiling_values.append(int(cm))
    if max_vm is not None:
        ceiling_values.append(int(max_vm))
    reference_max = max(ceiling_values) if ceiling_values else None
    new_km = int(lookup.latest_mileage_km)
    if (
        reference_max is not None
        and new_km < reference_max
        and not payload.confirm_lower_than_current
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Stav km z portálu je nižší než dosud evidované maximum. Pokud jde o opravu dat, "
                    "potvrďte zápis znovu (confirm_lower_than_current)."
                ),
                "current_mileage_km": reference_max,
                "max_vehicle_mileage_km": int(max_vm) if max_vm is not None else None,
                "vehicle_current_mileage_km": int(cm) if cm is not None else None,
                "portal_mileage_km": new_km,
            },
        )

    vehicle_payload, created_vm_id = _store_tachometer_mileage_result(
        vehicle=vehicle,
        lookup=lookup,
        current_user=current_user,
        db=db,
        confirm_lower_than_current=bool(payload.confirm_lower_than_current),
    )
    return VehicleTachometerFinishResponse(
        vehicle=vehicle_payload,
        latest_mileage_km=lookup.latest_mileage_km,
        latest_check_date=lookup.latest_check_date,
        inspections=lookup.inspections,
        created_record_id=None,
        created_vehicle_mileage_id=created_vm_id,
    )


@router.post("/{vehicle_id}/tachometer/submit", response_model=VehicleTachometerSubmitResponse)
def submit_vehicle_tachometer(
    vehicle_id: int,
    payload: VehicleTachometerSubmitRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VehicleTachometerSubmitResponse:
    try:
        finished = finish_vehicle_tachometer(
            vehicle_id=vehicle_id,
            payload=VehicleTachometerFinishRequest(
                session_id=payload.session_id,
                captcha_code=payload.captcha_code,
                confirm_lower_than_current=bool(payload.confirm_lower_than_current),
            ),
            current_user=current_user,
            db=db,
        )
    except HTTPException as exc:
        if exc.status_code == 400 and isinstance(exc.detail, dict):
            detail = _legacy_invalid_captcha_detail_from_new(exc.detail)
            raise HTTPException(status_code=422, detail=detail) from exc
        raise

    return VehicleTachometerSubmitResponse(
        vehicle=finished.vehicle,
        latest_mileage_km=finished.latest_mileage_km,
        latest_check_date=finished.latest_check_date,
        inspections=finished.inspections,
        created_record_id=finished.created_record_id,
        created_vehicle_mileage_id=finished.created_vehicle_mileage_id,
        source=finished.source,
    )


@router.get("/{vehicle_id}/tachometer/history", response_model=List[VehicleTachometerHistoryEntryResponse])
def get_vehicle_tachometer_history(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[VehicleTachometerHistoryEntryResponse]:
    _ = _get_accessible_vehicle_or_404(vehicle_id, current_user, db)
    return _build_tachometer_history_entries(vehicle_id, db)


@router.get(
    "/{vehicle_id}/tachometer/history/{entry_id}",
    response_model=VehicleTachometerHistoryEntryDetailResponse,
)
def get_vehicle_tachometer_history_entry_detail(
    vehicle_id: int,
    entry_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VehicleTachometerHistoryEntryDetailResponse:
    _ = _get_accessible_vehicle_or_404(vehicle_id, current_user, db)
    item = _get_normalized_tachometer_history_item_or_404(vehicle_id=vehicle_id, entry_id=entry_id, db=db)
    return _tachometer_history_entry_to_detail(item)


@router.get(
    "/{vehicle_id}/tachometer/history/{entry_id}/documents",
    response_model=List[VehicleTachometerDocumentResponse],
)
def get_vehicle_tachometer_history_entry_documents(
    vehicle_id: int,
    entry_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[VehicleTachometerDocumentResponse]:
    _ = _get_accessible_vehicle_or_404(vehicle_id, current_user, db)
    item = _get_normalized_tachometer_history_item_or_404(vehicle_id=vehicle_id, entry_id=entry_id, db=db)
    entry = item.canonical_entry
    return _serialize_tachometer_documents(getattr(entry, "documents_json", None))


@router.get("/{vehicle_id}", response_model=VehicleOutV1)
def get_vehicle(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací konkrétní vozidlo podle ID"""
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Kontrola přístupu
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    return _vehicle_to_response_payload(vehicle, current_user, db)


@router.get("/{vehicle_id}/technical-overview/debug")
def debug_vehicle_technical_overview(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Interní diagnostika struktury technického přehledu a klíčů MDČR — nepoužívat ve veřejném UI.
    Nevrací osobní údaje ani API klíč.
    """
    assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    from ..decoder.mdcr_client import fetch_mdcr_vehicle_raw_data_sync
    from ..services.vehicle_technical_overview import build_technical_overview_debug_payload

    vin_raw = str(getattr(vehicle, "vin", "") or "").strip().upper().replace(" ", "").replace("-", "")
    sto = getattr(vehicle, "vehicle_technical_overview", None)
    if not isinstance(sto, dict):
        sto = {}

    raw_wrap = sto.get("raw") if isinstance(sto.get("raw"), dict) else {}
    mdcr_raw = raw_wrap.get("mdcr") if isinstance(raw_wrap, dict) else None
    if not isinstance(mdcr_raw, dict) or len(mdcr_raw) == 0:
        if len(vin_raw) == 17:
            mdcr_raw = fetch_mdcr_vehicle_raw_data_sync(vin_raw) or {}
        else:
            mdcr_raw = {}

    return build_technical_overview_debug_payload(
        vin=vin_raw,
        overview_stored=sto if sto else None,
        mdcr_raw=mdcr_raw if isinstance(mdcr_raw, dict) else {},
    )


@router.get("/{vehicle_id}/mileage-log", response_model=List[VehicleMileageLogEntryOutV1])
def list_vehicle_mileage_log(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Chronologický výpis ručních a importovaných zápisů km (bez tarifu dokumentů)."""
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
    rows = (
        db.query(VehicleMileageModel)
        .filter(VehicleMileageModel.vehicle_id == vehicle_id)
        .order_by(VehicleMileageModel.created_at.asc(), VehicleMileageModel.id.asc())
        .all()
    )
    return [VehicleMileageLogEntryOutV1.model_validate(r) for r in rows]


@router.post("/{vehicle_id}/mileage", response_model=VehicleMileageRecordResultV1)
def record_vehicle_mileage(
    vehicle_id: int,
    payload: VehicleMileageRecordV1,
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Zapíše stav tachometru do tabulky vehicle_mileage (odděleně od servisní historie)."""
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()

    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    max_vm = (
        db.query(func.max(VehicleMileageModel.mileage_km))
        .filter(VehicleMileageModel.vehicle_id == vehicle_id)
        .scalar()
    )
    ceiling_values = []
    cm = getattr(vehicle, "current_mileage_km", None)
    if cm is not None:
        ceiling_values.append(int(cm))
    if max_vm is not None:
        ceiling_values.append(int(max_vm))
    reference_max = max(ceiling_values) if ceiling_values else None

    if (
        reference_max is not None
        and payload.mileage_km < reference_max
        and not payload.confirm_lower_than_current
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Nový stav km je nižší než dosud evidované maximum (aktuální stav vozidla nebo "
                    "historie zápisů km). Pokud jde o opravu, potvrďte zápis znovu."
                ),
                "current_mileage_km": reference_max,
                "max_vehicle_mileage_km": int(max_vm) if max_vm is not None else None,
                "vehicle_current_mileage_km": int(cm) if cm is not None else None,
            },
        )

    _validate_mileage_consistency(
        current_mileage_km=payload.mileage_km,
        last_stk_mileage_km=getattr(vehicle, "last_stk_mileage_km", None),
    )

    allowed_sources = frozenset({"manual", "stk", "service", "import"})
    raw_src = str(getattr(payload, "source", None) or "manual").strip().lower()
    mileage_source = raw_src if raw_src in allowed_sources else "manual"

    previous_mileage_km = int(cm) if cm is not None else None
    vehicle.current_mileage_km = payload.mileage_km

    vm_row = VehicleMileageModel(
        tenant_id=int(vehicle.tenant_id),
        vehicle_id=int(vehicle.id),
        mileage_km=int(payload.mileage_km),
        source=mileage_source,
        note=(payload.note.strip() if payload.note else None),
        created_by_user_id=getattr(current_user, "id", None),
    )
    db.add(vm_row)
    db.flush()
    write_global_audit_log(
        db,
        entity_type="vehicle",
        entity_id=int(vehicle.id),
        action="mileage_recorded",
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(vehicle.tenant_id),
        vehicle_id=int(vehicle.id),
        ip=extract_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        metadata={
            "vehicle_mileage_id": vm_row.id,
            "previous_mileage_km": previous_mileage_km,
            "new_mileage_km": int(payload.mileage_km),
            "mileage_km": payload.mileage_km,
            "source": mileage_source,
        },
    )
    db.commit()
    db.refresh(vehicle)
    db.refresh(vm_row)

    return VehicleMileageRecordResultV1(
        vehicle=_vehicle_to_response_payload(vehicle, current_user, db),
        created_record_id=None,
        created_vehicle_mileage_id=int(vm_row.id),
    )


@router.put("/{vehicle_id}", response_model=VehicleOutV1)
def update_vehicle(
    vehicle_id: int,
    vehicle_data: VehicleUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aktualizuje vozidlo"""
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()

    regen = bool(getattr(vehicle_data, "regenerate_technical_overview", None))
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Kontrola přístupu
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    effective_current_mileage = (
        vehicle_data.current_mileage_km
        if vehicle_data.current_mileage_km is not None
        else getattr(vehicle, "current_mileage_km", None)
    )
    effective_last_stk_mileage = (
        vehicle_data.last_stk_mileage_km
        if vehicle_data.last_stk_mileage_km is not None
        else getattr(vehicle, "last_stk_mileage_km", None)
    )
    _validate_mileage_consistency(
        current_mileage_km=effective_current_mileage,
        last_stk_mileage_km=effective_last_stk_mileage,
    )

    if vehicle_data.vin is not None:
        normalized_vin = _normalize_vin(vehicle_data.vin)
        if vehicle_data.orv_scan_id and not normalized_vin:
            raise HTTPException(status_code=422, detail="ORV scan vyžaduje potvrzený VIN. Doplňte jej ručně před uložením.")
        if normalized_vin:
            duplicate_vehicle = _find_duplicate_vehicle_by_vin(
                db=db,
                tenant_id=getattr(vehicle, "tenant_id", None),
                vin=normalized_vin,
                exclude_vehicle_id=vehicle.id,
            )
            if duplicate_vehicle is not None:
                raise HTTPException(status_code=409, detail="Vozidlo s tímto VIN již existuje")
            vehicle.vin = normalized_vin
        else:
            vehicle.vin = None
    
    # Aktualizace polí
    if vehicle_data.nickname is not None:
        vehicle.nickname = vehicle_data.nickname
    if vehicle_data.brand is not None:
        vehicle.brand = vehicle_data.brand
    if vehicle_data.model is not None:
        vehicle.model = vehicle_data.model
    if vehicle_data.year is not None:
        vehicle.year = vehicle_data.year
    if vehicle_data.engine is not None:
        vehicle.engine = vehicle_data.engine
    if vehicle_data.plate is not None:
        vehicle.plate = vehicle_data.plate
    if vehicle_data.notes is not None:
        vehicle.notes = vehicle_data.notes
    if vehicle_data.stk_valid_until is not None:
        vehicle.stk_valid_until = vehicle_data.stk_valid_until
    if vehicle_data.current_mileage_km is not None:
        vehicle.current_mileage_km = vehicle_data.current_mileage_km
    if vehicle_data.last_stk_mileage_km is not None:
        vehicle.last_stk_mileage_km = vehicle_data.last_stk_mileage_km
        vehicle.mileage_checked_at = datetime.utcnow()
    if vehicle_data.tyres_info is not None:
        vehicle.tyres_info = vehicle_data.tyres_info
    if vehicle_data.insurance_provider is not None:
        vehicle.insurance_provider = vehicle_data.insurance_provider
    if vehicle_data.insurance_valid_until is not None:
        vehicle.insurance_valid_until = vehicle_data.insurance_valid_until
    if vehicle_data.data_trust_state is not None:
        vehicle.data_trust_state = vehicle_data.data_trust_state
    if vehicle_data.orv_number is not None:
        vehicle.orv_number = str(vehicle_data.orv_number or "").strip() or None
    apply_orv_scan_to_vehicle(
        db=db,
        vehicle=vehicle,
        current_user=current_user,
        scan_id=vehicle_data.orv_scan_id,
        orv_number=vehicle_data.orv_number,
        use_owner_data=bool(vehicle_data.orv_use_owner_data),
        data_trust_state=vehicle_data.data_trust_state or getattr(vehicle, "data_trust_state", None) or "verified_by_user",
        create_payload=vehicle_data.dict(exclude_unset=False),
    )
    
    # DOČASNĚ ZAKÁZÁNO: Aktualizace assigned_service_id - dokud se neprovede migrace databáze
    # if vehicle_data.assigned_service_id is not None:
    #     if vehicle_data.assigned_service_id == 0 or vehicle_data.assigned_service_id == -1:
    #         vehicle.assigned_service_id = None
    #     else:
    #         service = db.query(Customer).filter(
    #             Customer.id == vehicle_data.assigned_service_id,
    #             Customer.role == "service"
    #         ).first()
    #         if not service:
    #             raise HTTPException(status_code=400, detail="Zadaný servis neexistuje nebo není servisem")
    #         vehicle.assigned_service_id = service.id
    # elif hasattr(vehicle_data, 'assigned_service_id') and vehicle_data.assigned_service_id is None:
    #     vehicle.assigned_service_id = None
    
    write_global_audit_log(
        db,
        entity_type="vehicle",
        entity_id=int(vehicle.id),
        action="vehicle_update",
        actor_user_id=current_user.id,
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(vehicle.tenant_id),
        metadata={"vehicle_id": int(vehicle.id)},
    )
    db.commit()
    db.refresh(vehicle)

    if regen:
        try:
            from ..services.vehicle_technical_overview import persist_vehicle_technical_overview

            overview = persist_vehicle_technical_overview(db, vehicle)
            stats = (overview or {}).get("stats") or {}
            write_global_audit_log(
                db,
                entity_type="vehicle",
                entity_id=int(vehicle.id),
                action="vehicle_technical_overview_refreshed",
                actor_user_id=current_user.id,
                actor_role=getattr(current_user, "role", None),
                tenant_id=int(vehicle.tenant_id),
                vehicle_id=int(vehicle.id),
                metadata={
                    "vin": getattr(vehicle, "vin", None),
                    "sources": (overview or {}).get("source_summary"),
                    "filled": stats.get("filled"),
                    "empty": stats.get("empty"),
                    "total": stats.get("total"),
                    "mdcr_key_count": stats.get("mdcr_key_count"),
                    "by_section": stats.get("by_section"),
                    "filled_fields": stats.get("filled"),
                    "empty_fields": stats.get("empty"),
                },
            )
            db.commit()
            db.refresh(vehicle)
        except Exception as exc:
            logger.warning("[VEHICLE_UPDATE] technical overview refresh failed vehicle_id=%s err=%s", vehicle_id, exc, exc_info=True)
            try:
                db.rollback()
            except Exception:
                pass

    if not regen:
        try:
            from ..services.vehicle_large_technical_certificate_storage import (
                try_refresh_vehicle_large_technical_certificate_disk,
            )

            try_refresh_vehicle_large_technical_certificate_disk(vehicle)
        except Exception as exc:
            logger.warning(
                "[VEHICLE_UPDATE] large TP refresh (bez regenerate_technical_overview) selhal vehicle_id=%s err=%s",
                vehicle_id,
                exc,
                exc_info=True,
            )

    return _vehicle_to_response_payload(vehicle, current_user, db)


@router.get("/{vehicle_id}/photos")
def list_vehicle_gallery_photos(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
    rows = (
        db.query(VehiclePhotoAssetModel)
        .filter(
            VehiclePhotoAssetModel.vehicle_id == int(vehicle_id),
            VehiclePhotoAssetModel.role == "gallery",
            VehiclePhotoAssetModel.deleted_at.is_(None),
        )
        .order_by(VehiclePhotoAssetModel.sort_order.asc(), VehiclePhotoAssetModel.created_at.desc(), VehiclePhotoAssetModel.id.desc())
        .all()
    )
    return {
        "photos": [
            {
                "id": int(r.id),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "url": f"/api/v1/vehicles/{vehicle_id}/photos/{r.id}/file",
                "has_original": bool(
                    getattr(r, "storage_path_original", None) and str(getattr(r, "storage_path_original", "") or "").strip()
                ),
            }
            for r in rows
        ]
    }


@router.post("/{vehicle_id}/photos")
def upload_vehicle_gallery_photo(
    vehicle_id: int,
    payload: VehiclePhotoUploadRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    content = _decode_base64_payload(payload.file_content_base64)
    if not content:
        raise HTTPException(status_code=422, detail="Nahraný soubor je prázdný.")
    if len(content) > MAX_VEHICLE_PHOTO_RAW_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Fotka je příliš velká pro zpracování (max 40 MB vstupních dat).")
    mime_type = str(payload.file_mime_type or "").lower().strip()
    if mime_type and not mime_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Podporované jsou pouze obrázky.")
    if _count_active_gallery_assets(db, int(vehicle_id)) >= MAX_VEHICLE_GALLERY_PHOTOS:
        raise HTTPException(
            status_code=400,
            detail=f"Galerie má limit {MAX_VEHICLE_GALLERY_PHOTOS} fotek na vozidlo.",
        )
    normalized_content = _normalize_vehicle_photo(content)

    tenant_id = int(getattr(vehicle, "tenant_id", None) or getattr(current_user, "tenant_id", None) or 0)
    owner = get_primary_vehicle_owner(db, vehicle)
    owner_id = int(getattr(owner, "id", 0) or 0) or None
    fname = f"gallery_{secrets.token_hex(8)}.jpg"
    storage_key = build_main_storage_key(tenant_id=tenant_id, vehicle_id=int(vehicle_id), filename=fname)
    target_file = VEHICLE_PHOTOS_DIR / storage_key
    _write_bytes_to_vehicle_photos_file(target_file, normalized_content)
    digest = sha256_hex(normalized_content)
    w_px, h_px = jpeg_dimensions(normalized_content)

    row = VehiclePhotoAssetModel(
        tenant_id=tenant_id,
        vehicle_id=int(vehicle_id),
        owner_customer_id=owner_id,
        role="gallery",
        storage_key=storage_key,
        original_filename=str(payload.file_name or "gallery.jpg")[:255],
        mime_type="image/jpeg",
        file_size_bytes=len(normalized_content),
        width=w_px,
        height=h_px,
        sha256_hex=digest,
        uploaded_by_customer_id=int(getattr(current_user, "id", 0) or 0) or None,
        created_at=datetime.utcnow(),
        deleted_at=None,
        sort_order=0,
    )
    db.add(row)
    db.flush()
    orig_key = None
    try:
        orig_key = _validate_and_store_gallery_original_bytes(
            raw_b64=payload.original_file_content_base64,
            suggested_name=payload.original_file_name,
            suggested_mime=payload.original_file_mime_type,
            tenant_id=tenant_id,
            vehicle_id=int(vehicle_id),
        )
    except HTTPException:
        _unlink_gallery_original_file(getattr(row, "storage_path_original", None))
        try:
            if target_file.is_file():
                target_file.unlink(missing_ok=True)
        except OSError:
            pass
        db.rollback()
        raise
    if orig_key:
        row.storage_path_original = orig_key
        db.flush()
    write_global_audit_log(
        db,
        entity_type="vehicle_gallery_photo",
        entity_id=int(row.id),
        action="gallery_photo_upload",
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=tenant_id,
        metadata={
            "vehicle_id": int(vehicle_id),
            "vehicle_photo_asset_id": int(row.id),
            "storage_key": storage_key,
            "has_original": bool(orig_key),
        },
    )
    promoted_primary = False
    if not _resolve_primary_photo_file(vehicle=vehicle, db=db):
        _persist_primary_vehicle_photo(
            vehicle=vehicle,
            current_user=current_user,
            normalized_content=normalized_content,
            db=db,
            audit_action="primary_photo_autoset_from_gallery",
            metadata={"vehicle_id": int(vehicle_id), "gallery_photo_asset_id": int(row.id)},
        )
        promoted_primary = True
    db.commit()
    db.refresh(row)
    return {
        "id": int(row.id),
        "url": f"/api/v1/vehicles/{vehicle_id}/photos/{row.id}/file",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "promoted_to_primary": promoted_primary,
    }


@router.get("/{vehicle_id}/photos/{photo_id}/file/original")
def get_vehicle_gallery_photo_original_file(
    vehicle_id: int,
    photo_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Plný originál (pokud byl při nahrání uložen vedle ořezu)."""
    assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
    row = (
        db.query(VehiclePhotoAssetModel)
        .filter(
            VehiclePhotoAssetModel.id == int(photo_id),
            VehiclePhotoAssetModel.vehicle_id == int(vehicle_id),
            VehiclePhotoAssetModel.role == "gallery",
            VehiclePhotoAssetModel.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Fotka nebyla nalezena")
    orig_key = getattr(row, "storage_path_original", None)
    if not orig_key or not str(orig_key).strip():
        raise HTTPException(status_code=404, detail="K této galerijní fotce není na serveru uložený původní soubor.")
    photo_file = resolve_storage_file(VEHICLE_PHOTOS_DIR, str(orig_key).strip())
    if not photo_file:
        raise HTTPException(status_code=404, detail="Soubor originálu neexistuje")
    media_type = _guess_vehicle_image_media_type(photo_file)
    return FileResponse(path=str(photo_file), media_type=media_type, filename=photo_file.name)


@router.get("/{vehicle_id}/photos/{photo_id}/file")
def get_vehicle_gallery_photo_file(
    vehicle_id: int,
    photo_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
    row = (
        db.query(VehiclePhotoAssetModel)
        .filter(
            VehiclePhotoAssetModel.id == int(photo_id),
            VehiclePhotoAssetModel.vehicle_id == int(vehicle_id),
            VehiclePhotoAssetModel.role == "gallery",
            VehiclePhotoAssetModel.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Fotka nebyla nalezena")
    photo_file = resolve_storage_file(VEHICLE_PHOTOS_DIR, row.storage_key)
    if not photo_file:
        write_global_audit_log(
            db,
            entity_type="vehicle_gallery_photo",
            entity_id=int(photo_id),
            action="gallery_photo_missing_file",
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
            tenant_id=int(getattr(row, "tenant_id", 0) or 0) or None,
            metadata={"vehicle_id": int(vehicle_id), "storage_key": row.storage_key},
        )
        db.flush()
        raise HTTPException(status_code=404, detail="Soubor fotky neexistuje")
    media_type = _guess_vehicle_image_media_type(photo_file)
    return FileResponse(path=str(photo_file), media_type=media_type, filename=photo_file.name)


@router.put("/{vehicle_id}/photos/{photo_id}/file")
def replace_vehicle_gallery_photo_file(
    vehicle_id: int,
    photo_id: int,
    payload: VehiclePhotoUploadRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Přepíše existující galerijní snímek novým obrázkem (serverová normalizace JPEG jako u nahrání)."""
    assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
    row = (
        db.query(VehiclePhotoAssetModel)
        .filter(
            VehiclePhotoAssetModel.id == int(photo_id),
            VehiclePhotoAssetModel.vehicle_id == int(vehicle_id),
            VehiclePhotoAssetModel.role == "gallery",
            VehiclePhotoAssetModel.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Fotka nebyla nalezena")

    content = _decode_base64_payload(payload.file_content_base64)
    if not content:
        raise HTTPException(status_code=422, detail="Nahraný soubor je prázdný.")
    if len(content) > MAX_VEHICLE_PHOTO_RAW_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Fotka je příliš velká pro zpracování (max 40 MB vstupních dat).")
    mime_type = str(payload.file_mime_type or "").lower().strip()
    if mime_type and not mime_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Podporované jsou pouze obrázky.")
    normalized_content = _normalize_vehicle_photo(content)
    tenant_id = int(getattr(row, "tenant_id", 0) or 0) or 0
    if payload.original_file_content_base64 and str(payload.original_file_content_base64).strip():
        old_orig = getattr(row, "storage_path_original", None)
        new_orig_key = _validate_and_store_gallery_original_bytes(
            raw_b64=payload.original_file_content_base64,
            suggested_name=payload.original_file_name,
            suggested_mime=payload.original_file_mime_type,
            tenant_id=tenant_id,
            vehicle_id=int(vehicle_id),
        )
        if new_orig_key:
            if old_orig and str(old_orig).strip() and str(new_orig_key).strip() != str(old_orig).strip():
                _unlink_gallery_original_file(str(old_orig).strip())
            row.storage_path_original = new_orig_key
    target_file = VEHICLE_PHOTOS_DIR / row.storage_key
    _write_bytes_to_vehicle_photos_file(target_file, normalized_content)
    digest = sha256_hex(normalized_content)
    w_px, h_px = jpeg_dimensions(normalized_content)
    row.file_size_bytes = len(normalized_content)
    row.width = w_px
    row.height = h_px
    row.sha256_hex = digest
    row.mime_type = "image/jpeg"
    row.original_filename = str(payload.file_name or "gallery.jpg")[:255]
    row.uploaded_by_customer_id = int(getattr(current_user, "id", 0) or 0) or None
    write_global_audit_log(
        db,
        entity_type="vehicle_gallery_photo",
        entity_id=int(photo_id),
        action="gallery_photo_replace",
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=tenant_id or None,
        metadata={"vehicle_id": int(vehicle_id), "vehicle_photo_asset_id": int(photo_id), "storage_key": row.storage_key},
    )
    db.commit()
    db.refresh(row)
    return {
        "id": int(row.id),
        "url": f"/api/v1/vehicles/{vehicle_id}/photos/{row.id}/file",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.delete("/photos/{photo_id}")
def delete_vehicle_gallery_photo(
    photo_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")
    row = db.query(VehiclePhotoAssetModel).filter(VehiclePhotoAssetModel.id == int(photo_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Fotka nebyla nalezena")
    if str(getattr(row, "role", "") or "") != "gallery":
        raise HTTPException(status_code=400, detail="Tento záznam nelze smazat jako galerijní fotku.")
    if not can_access_vehicle(int(row.vehicle_id), current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
    photo_file = resolve_storage_file(VEHICLE_PHOTOS_DIR, row.storage_key)
    vid = int(row.vehicle_id)
    tid = int(getattr(row, "tenant_id", 0) or 0)
    write_global_audit_log(
        db,
        entity_type="vehicle_gallery_photo",
        entity_id=int(photo_id),
        action="gallery_photo_delete",
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=tid or None,
        metadata={"vehicle_id": vid, "storage_key": row.storage_key},
    )
    orig_key = getattr(row, "storage_path_original", None)
    _soft_delete_photo_asset(db, row)
    db.commit()
    if photo_file:
        try:
            photo_file.unlink(missing_ok=True)
        except Exception:
            pass
    _unlink_gallery_original_file(str(orig_key).strip() if orig_key else None)
    return {"message": "Fotka byla odstraněna."}


@router.get("/{vehicle_id}/photo")
def get_vehicle_photo(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Vrátí fotku vozidla (pokud je nahraná)."""
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    photo_file = _resolve_primary_photo_file(vehicle=vehicle, db=db)
    if not photo_file:
        if _get_primary_photo_asset_row(db, vehicle) or getattr(vehicle, "photo_path", None):
            write_global_audit_log(
                db,
                entity_type="vehicle",
                entity_id=int(vehicle_id),
                action="vehicle_primary_photo_missing_file",
                actor_user_id=getattr(current_user, "id", None),
                actor_role=getattr(current_user, "role", None),
                tenant_id=int(getattr(vehicle, "tenant_id", 0) or 0) or None,
                metadata={
                    "primary_photo_asset_id": getattr(vehicle, "primary_photo_asset_id", None),
                    "legacy_photo_path": getattr(vehicle, "photo_path", None),
                },
            )
            db.flush()
        raise HTTPException(status_code=404, detail="Fotka vozidla nebyla nalezena")

    media_type = _guess_vehicle_image_media_type(photo_file)
    return FileResponse(path=str(photo_file), media_type=media_type, filename=photo_file.name)


@router.post("/{vehicle_id}/photo")
def upload_vehicle_photo(
    vehicle_id: int,
    payload: VehiclePhotoUploadRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Nahraje/aktualizuje fotku vozidla (pro uživatele i servis)."""
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    content = _decode_base64_payload(payload.file_content_base64)
    if not content:
        raise HTTPException(status_code=422, detail="Nahraný soubor je prázdný.")
    if len(content) > MAX_VEHICLE_PHOTO_RAW_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Fotka je příliš velká pro zpracování (max 40 MB vstupních dat).")

    mime_type = str(payload.file_mime_type or "").lower().strip()
    if mime_type and not mime_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Podporované jsou pouze obrázky.")

    normalized_content = _normalize_vehicle_photo(content)

    result = _persist_primary_vehicle_photo(
        vehicle=vehicle,
        current_user=current_user,
        normalized_content=normalized_content,
        db=db,
        audit_action="primary_photo_upload",
    )
    db.commit()
    db.refresh(vehicle)

    return {
        "message": "Fotka vozidla byla úspěšně nahrána a serverově normalizována na 1280x720 JPEG.",
        "photo_path": result["photo_path"],
        "photo_url": result["photo_url"],
    }


@router.post("/{vehicle_id}/photo/promote/{photo_id}")
def promote_vehicle_gallery_photo_to_primary(
    vehicle_id: int,
    photo_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    row = (
        db.query(VehiclePhotoAssetModel)
        .filter(
            VehiclePhotoAssetModel.id == int(photo_id),
            VehiclePhotoAssetModel.vehicle_id == int(vehicle_id),
            VehiclePhotoAssetModel.role == "gallery",
            VehiclePhotoAssetModel.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Galerijní fotka nebyla nalezena")

    gallery_file = resolve_storage_file(VEHICLE_PHOTOS_DIR, row.storage_key)
    if not gallery_file:
        raise HTTPException(status_code=404, detail="Soubor galerijní fotky neexistuje")

    normalized_content = _normalize_vehicle_photo(gallery_file.read_bytes())
    result = _persist_primary_vehicle_photo(
        vehicle=vehicle,
        current_user=current_user,
        normalized_content=normalized_content,
        db=db,
        audit_action="primary_photo_promote_from_gallery",
        metadata={"vehicle_id": int(vehicle_id), "gallery_photo_asset_id": int(photo_id)},
    )
    db.commit()
    db.refresh(vehicle)
    return {
        "message": "Galerijní fotka byla nastavena jako hlavní fotka vozidla.",
        "photo_path": result["photo_path"],
        "photo_url": result["photo_url"],
        "gallery_photo_id": int(photo_id),
    }


@router.delete("/{vehicle_id}/photo")
def delete_vehicle_photo(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Smaže fotku vozidla."""
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    asset = _get_primary_photo_asset_row(db, vehicle)
    legacy_file = _get_vehicle_photo_file(getattr(vehicle, "photo_path", None))
    vehicle.primary_photo_asset_id = None
    vehicle.photo_path = None
    if asset is not None:
        _soft_delete_photo_asset(db, asset)
    write_global_audit_log(
        db,
        entity_type="vehicle",
        entity_id=int(vehicle_id),
        action="primary_photo_delete",
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(getattr(vehicle, "tenant_id", 0) or 0) or None,
        metadata={"previous_vehicle_photo_asset_id": int(asset.id) if asset else None},
    )
    db.commit()

    if asset is not None:
        _unlink_asset_file(asset)
    if legacy_file:
        try:
            legacy_file.unlink(missing_ok=True)
        except Exception:
            pass

    return {"message": "Fotka vozidla byla smazána."}


@router.get("/{vehicle_id}/invoices")
def user_list_vehicle_invoices(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if is_service(normalize_role(getattr(current_user, "role", None))):
        raise HTTPException(status_code=403, detail="Pouze uživatelský účet.")
    assert_module_ready(db, "service_invoices", detail_prefix="Faktury nejsou připravené")
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k fakturám tohoto vozidla.")

    rows = (
        db.query(ServiceInvoice)
        .filter(
            ServiceInvoice.vehicle_id == int(vehicle_id),
            ServiceInvoice.status == "issued",
        )
        .order_by(nullslast(ServiceInvoice.issued_at.desc()), ServiceInvoice.id.desc())
        .limit(200)
        .all()
    )
    return {
        "items": [
            {
                "id": int(inv.id),
                "invoice_number": inv.invoice_number,
                "status": inv.status,
                "total": inv.total,
                "currency": inv.currency,
                "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
                "service_record_id": int(inv.service_record_id) if getattr(inv, "service_record_id", None) else None,
            }
            for inv in rows
        ]
    }


@router.get("/{vehicle_id}/invoices/{invoice_id}/pdf")
def user_download_vehicle_invoice_pdf(
    vehicle_id: int,
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from .service_invoices import render_internal_service_invoice_pdf

    if is_service(normalize_role(getattr(current_user, "role", None))):
        raise HTTPException(status_code=403, detail="Pouze uživatelský účet.")
    assert_module_ready(db, "service_invoices", detail_prefix="Faktury nejsou připravené")
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k dokladu.")

    inv = (
        db.query(ServiceInvoice)
        .filter(
            ServiceInvoice.id == int(invoice_id),
            ServiceInvoice.vehicle_id == int(vehicle_id),
            ServiceInvoice.status == "issued",
        )
        .first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Faktura nebyla nalezena.")

    pdf_bytes = render_internal_service_invoice_pdf(db, invoice=inv)
    write_global_audit_log(
        db,
        entity_type="service_invoice",
        entity_id=int(inv.id),
        action="service_invoice_user_pdf_download",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=str(getattr(current_user, "role", None) or ""),
        tenant_id=int(inv.tenant_id),
        vehicle_id=int(vehicle_id),
        metadata={
            "invoice_number": inv.invoice_number,
            "service_record_id": int(inv.service_record_id) if getattr(inv, "service_record_id", None) else None,
        },
    )
    db.commit()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="invoice-{int(inv.id)}.pdf"'},
    )


@router.delete("/{vehicle_id}")
def delete_vehicle(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Legacy endpoint: přímé odebrání je blokované, používá se řízený lifecycle flow."""
    raise HTTPException(
        status_code=409,
        detail=(
            "Vozidlo nelze odstranit přímým smazáním. Použijte /api/v1/vehicles/{vehicle_id}/remove/init "
            "a /api/v1/vehicles/{vehicle_id}/remove/confirm s důvodem odstranění."
        ),
    )
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Kontrola přístupu - pouze vlastník může smazat
    owner_decision = vehicle_write_policy(
        role=current_user.role,
        is_owner=user_owns_vehicle(db, current_user, vehicle),
    )
    if not owner_decision.allowed:
        raise HTTPException(status_code=403, detail="Nemáte oprávnění smazat toto vozidlo")
    
    try:
        released = release_vehicle_owner_assignment(db, vehicle=vehicle, owner=current_user)
        if not released:
            raise HTTPException(status_code=409, detail="Aktuální vlastnická vazba vozidla už není aktivní.")

        _revoke_vehicle_service_links_for_owner_release(
            db,
            vehicle_id=vehicle_id,
            revoked_by_customer_id=current_user.id,
            reason="Vozidlo bylo odebráno z profilu vlastníka.",
        )

        write_global_audit_log(
            db,
            entity_type="vehicle",
            entity_id=int(vehicle_id),
            action="vehicle_removed_from_profile",
            actor_user_id=current_user.id,
            actor_role=getattr(current_user, "role", None),
            tenant_id=int(getattr(vehicle, "tenant_id", 0) or 0) or None,
            metadata={},
        )
        db.commit()

        return {
            "message": (
                "Vozidlo bylo odebráno z vašeho profilu. Historie a servisní záznamy zůstaly "
                "bezpečně uložené pro případný budoucí převod na nového vlastníka."
            )
        }
    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Chyba při odebrání vozidla z profilu: {str(e)}")
