"""
Service Records API v1.0 router
"""
from __future__ import annotations

from datetime import datetime
import base64
import binascii
import os
from io import BytesIO
import json
import mimetypes
from pathlib import Path
import re
import secrets
import unicodedata
from urllib.parse import quote

import requests
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Any, List, Optional
from sqlalchemy import desc, func, nullslast

from src.core.config import DATA_DIR
from src.core.rbac import is_admin, is_service
from src.server.security_tracking import log_security_event
from ..database import get_db
from ..mileage_reports import (
    build_mileage_timeline_payload,
    collect_vehicle_mileage_timeline_points,
    render_mileage_timeline_chart_png,
    summarize_mileage_timeline,
)
from ..audit_log import write_global_audit_log
from ..central_vehicle_identity import vehicle_state
from ..ownership import get_primary_vehicle_owner
from ..models import (
    Customer,
    ServiceRecord as ServiceRecordModel,
    ServiceRecordAuditLog,
    ServiceVehicleAccess,
    Vehicle as VehicleModel,
    VehicleMileage,
    VehicleOwnership,
    VehicleReportDocument,
    VehicleServiceLink,
    VehicleTachometerHistoryEntry,
)
from ..schema_management import assert_module_ready
from ..service_access import (
    attach_service_access_to_record,
    normalize_lookup_query,
    require_service_vehicle_link,
)
from ..service_record_snapshot import service_record_audit_snapshot as _service_record_snapshot
from ..service_record_snapshot import snapshot_json_and_hash as _snapshot_json_and_hash
from ..service_record_view import (
    assert_viewer_may_mutate_service_record,
    find_record_for_attachment_storage_key,
    viewer_augmentation_for_service_record_api,
    viewer_policy_applies_for_customer_workspace,
    viewer_record_same_ownership_era,
)
from ..reports.vehicle_report_access import resolve_report_mode
from ..reports.vehicle_report_builder import build_vehicle_service_report_payload
from ..services.vehicle_large_technical_certificate_storage import (
    regenerate_vehicle_large_technical_certificate_pdf,
    technical_certificate_generated_at,
)
from ..reports.vehicle_report_pdf import render_vehicle_service_report_pdf
from ..reports.vehicle_report_verification import finalize_vehicle_report_document
from ...licensing.service import (
    FREE_SERVICE_RECORDS_LIMIT,
    assert_service_monthly_service_record_quota,
    get_license_status,
)
from .auth import get_current_user, can_access_vehicle
from .schemas import ServiceRecordCreateV1, ServiceRecordUpdateV1, ServiceRecordOutV1
from .service_workspace import (
    ALLOWED_SOURCE_TYPES,
    _build_service_record_description,
    _extract_text_from_file,
    _parse_document_payload,
)
router = APIRouter(prefix="/vehicles", tags=["service-records-v1"])

SERVICE_RECORD_ATTACHMENTS_DIR = DATA_DIR / "service_record_attachments"
SERVICE_RECORD_ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
MAX_ATTACHMENT_SIZE_BYTES = 15 * 1024 * 1024
ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".csv",
    ".json",
    ".xml",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
}
SERVICE_RECORD_ATTACHMENT_KINDS = frozenset(
    {"before_repair", "after_repair", "invoice_attachment", "protocol", "other"}
)
MILEAGE_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[ .]\d{3}){1,2}|\d{4,7})\s*km\b", re.IGNORECASE)
MILEAGE_KEYWORD_RE = re.compile(
    r"(?:stav\s*(?:tachometru|km)|tachometr|najeto|najazdeno|odometer)\s*[:\-]?\s*(\d{1,3}(?:[ .]\d{3}){1,2}|\d{4,7})",
    re.IGNORECASE,
)
CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("OLEJ", ("olej", "oil", "maziv")),
    ("FILTRY", ("filtr", "filter")),
    ("BRZDY", ("brzd", "kotou", "desti")),
    ("PNEU", ("pneu", "pneum", "guma", "tire")),
    ("STK", ("stk", "emise", "emis")),
    ("DIAGNOSTIKA", ("diagnost", "diag")),
    ("KLIMATIZACE", ("klimat", "ac servis", "ac-service", "air condition")),
    ("ELEKTRIKA", ("akumul", "bateri", "alternator", "starter", "elektr")),
    ("CHLADICI", ("chladic", "chladi", "coolant")),
    ("VYFUK", ("vyfuk", "výfuk", "dpf")),
    ("KAROSERIE", ("karoser", "lakov", "plech")),
    ("OSVETLENI", ("svetl", "žárov", "zarov", "xenon", "led")),
    ("OPRAVA", ("oprava", "servis", "repair")),
]


class VehicleReportExportQuery(BaseModel):
    mode: Optional[str] = Field(default=None, max_length=32)
SUSPICIOUS_SUMMARY_PATTERNS = [
    re.compile(r"\b\d{1,5}\s*/\s*\d{1,5}[A-Za-z]?\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b.*\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", re.IGNORECASE),
    re.compile(
        r"^(celkov[aá]\s+částka|celkova\s+castka|celkem|zbýv[aá]\s+uhradit|zbyva\s+uhradit|uhrazeno)\b",
        re.IGNORECASE,
    ),
]
SERVICE_RECORD_STATUSES = {"draft", "submitted", "approved", "locked"}
SERVICE_RECORD_IMMUTABLE_STATUSES = {"approved", "locked"}

SERVICE_RECORD_DESC_EDIT_MARKER = "\n\n(* původní záznam: "


def _enforce_free_service_record_limit(
    db: Session,
    *,
    tenant_id: int,
    user_email: Optional[str],
) -> None:
    license_status = get_license_status(db, tenant_id, user_email)
    plan_base = str(license_status.get("plan_base") or "").strip().lower()
    # Servisní ZÁKLADní má omezení jako osobní Free (1 záznam), uživatelské Basic+ bez limitu záznamů zde.
    if plan_base != "free":
        return

    records_count = int(
        db.query(func.count(ServiceRecordModel.id)).filter(
            ServiceRecordModel.tenant_id == tenant_id,
            ServiceRecordModel.is_deleted.is_(False),
        ).scalar() or 0
    )
    if records_count >= FREE_SERVICE_RECORDS_LIMIT:
        raise HTTPException(
            status_code=403,
            detail=(
                "V základní (bezplatné) verzi můžete uložit pouze 1 servisní záznam. "
                "Pro neomezený počet záznamů aktivujte placenou licenci FULL."
            ),
        )


SERVICE_RECORD_DESC_EDIT_SUFFIX = " *)"


def _split_service_record_description_annotation(description: str) -> tuple[str, str | None]:
    """Oddělí hlavní text a volitelný transparentní odkaz na předchozí znění."""
    raw = (description or "").strip()
    if SERVICE_RECORD_DESC_EDIT_MARKER in raw:
        idx = raw.rfind(SERVICE_RECORD_DESC_EDIT_MARKER)
        main = raw[:idx].strip()
        tail = raw[idx + len(SERVICE_RECORD_DESC_EDIT_MARKER) :]
        if tail.endswith(SERVICE_RECORD_DESC_EDIT_SUFFIX):
            previous = tail[: -len(SERVICE_RECORD_DESC_EDIT_SUFFIX)].strip()
            return main, previous
    return raw, None


def _normalize_service_description_for_compare(text: str) -> str:
    s = unicodedata.normalize("NFKC", (text or "").strip().lower())
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[.,;:\-–—/\\|·]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _llm_service_descriptions_materially_differ(old_main: str, new_main: str) -> bool | None:
    """
    Volitelné porovnání přes OpenAI (OPENAI_API_KEY).
    Vrací None, pokud LLM nelze použít — pak se použije heuristika níže.
    """
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    model = (os.getenv("OPENAI_SERVICE_RECORD_COMPARE_MODEL") or "gpt-4o-mini").strip()
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=22,
            json={
                "model": model,
                "temperature": 0,
                "max_tokens": 6,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Jsi kontrolor editací servisního popisu vozidla. Odpověz přesně ANO nebo NE.\n"
                            "ANO = nový text mění význam, rozsah prací nebo fakta oproti původnímu.\n"
                            "NE = pouze pravopis, interpunkce, diakritika, formulace se stejným významem, "
                            "přeskupení stejných údajů."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"PŮVODNÍ:\n{old_main}\n\nNOVÝ:\n{new_main}\n\nMění se význam podstatně? Odpověz ANO nebo NE.",
                    },
                ],
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        text = str(payload.get("choices", [{}])[0].get("message", {}).get("content", "")).strip().upper()
        if text.startswith("ANO") or text.startswith("YES"):
            return True
        if text.startswith("NE") or text.startswith("NO"):
            return False
    except Exception:
        pass
    return None


def _service_descriptions_materially_differ(old_main: str, new_main: str) -> bool:
    old_main = (old_main or "").strip()
    new_main = (new_main or "").strip()
    if old_main == new_main:
        return False
    llm = _llm_service_descriptions_materially_differ(old_main, new_main)
    if llm is not None:
        return llm
    return _normalize_service_description_for_compare(old_main) != _normalize_service_description_for_compare(
        new_main
    )


def _merge_service_record_description_update(previous_full: str, incoming_text: str) -> str:
    """
    Uloží nový popis; při podstatné změně připojí transparentní odkaz na předchozí znění.
    Při pouze stylistické úpravě vrátí čistý text bez patičky.
    """
    incoming_text = (incoming_text or "").strip()
    previous_full = (previous_full or "").strip()
    main_prev, _ = _split_service_record_description_annotation(previous_full)
    new_main, _ = _split_service_record_description_annotation(incoming_text)
    if not _service_descriptions_materially_differ(main_prev, new_main):
        return new_main
    return f"{new_main}{SERVICE_RECORD_DESC_EDIT_MARKER}{main_prev}{SERVICE_RECORD_DESC_EDIT_SUFFIX}"


def _normalize_record_status(raw_value: Optional[str], *, default: str = "draft") -> str:
    value = str(raw_value or default).strip().lower()
    if value not in SERVICE_RECORD_STATUSES:
        raise HTTPException(status_code=422, detail="Neplatný stav servisního záznamu.")
    return value


def _attachment_request_looks_like_image(*, file_name: str, file_mime_type: str) -> bool:
    """Fotodokumentace u záznamu nepatří k „exportu dokumentů / PDF“ — povolíme i ve FREE tarifu."""
    mime = str(file_mime_type or "").lower().strip()
    if mime.startswith("image/"):
        return True
    ext = Path(str(file_name or "")).suffix.lower()
    return ext in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".bmp",
        ".heic",
        ".heif",
    }


def _require_documents_plan(db: Session, *, tenant_id: Optional[int]) -> None:
    """Vynutí tarifní příznak documents_enabled (FREE vypnuto, BASIC/PREMIUM zapnuto)."""
    from ...licensing.service import LicenseError, assert_feature

    tid = int(tenant_id or 0)
    if tid <= 0:
        raise HTTPException(
            status_code=403,
            detail="Export dokumentů nelze ověřit: chybí tenant kontext.",
        )
    try:
        assert_feature(db, tid, "documents")
    except LicenseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _assert_record_is_mutable(record: ServiceRecordModel) -> None:
    current_status = _normalize_record_status(getattr(record, "record_status", None), default="draft")
    if current_status in SERVICE_RECORD_IMMUTABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Schválený nebo uzamčený servisní záznam už nelze upravovat.",
        )


def _serialize_service_record_out_v1(
    db: Session,
    vehicle_id: int,
    current_user: Customer,
    record: ServiceRecordModel,
) -> ServiceRecordOutV1:
    merged = ServiceRecordOutV1.model_validate(record).model_dump()
    merged.update(viewer_augmentation_for_service_record_api(db, vehicle_id, current_user, record))
    return ServiceRecordOutV1(**merged)


def _assert_current_user_can_edit_record(current_user: Customer, record: ServiceRecordModel) -> None:
    if not is_service(getattr(current_user, "role", None)):
        return
    if int(getattr(record, "created_by_service_customer_id", 0) or 0) != int(getattr(current_user, "id", 0) or 0):
        raise HTTPException(
            status_code=403,
            detail="Servis smí upravit jen vlastní servisní záznamy vytvořené v tomto workflow.",
        )


class ServiceRecordAttachmentUploadRequest(BaseModel):
    service_record_id: int = Field(..., gt=0)
    attachment_kind: str = Field(..., min_length=4, max_length=32)
    file_name: str = Field(..., min_length=1, max_length=255)
    file_mime_type: str = Field(default="application/octet-stream", max_length=255)
    file_content_base64: str = Field(..., min_length=20, max_length=25_000_000)


class ServiceRecordAutoFromDocumentRequest(BaseModel):
    source_type: str = Field(default="invoice", max_length=32)
    file_name: str = Field(..., min_length=1, max_length=255)
    file_mime_type: str = Field(default="application/octet-stream", max_length=255)
    file_content_base64: str = Field(..., min_length=20, max_length=25_000_000)
    manual_text: Optional[str] = Field(default=None, max_length=300_000)
    manual_note: Optional[str] = Field(default=None, max_length=2000)
    fallback_category: Optional[str] = Field(default=None, max_length=32)
    fallback_mileage: Optional[int] = Field(default=None, ge=0)
    fallback_performed_at: Optional[datetime] = None
    fallback_description: Optional[str] = Field(default=None, max_length=500)
    fallback_price: Optional[float] = Field(default=None, ge=0)


class ServiceRecordDocumentPrefillRequest(ServiceRecordAutoFromDocumentRequest):
    pass


class DocumentsHubAttachmentItemV1(BaseModel):
    vehicle_id: int
    vehicle_name: str
    record_id: int
    performed_at: Optional[datetime] = None
    description: Optional[str] = None
    category: Optional[str] = None
    file_name: str
    mime_type: Optional[str] = None
    download_url: str
    source_type: Optional[str] = None
    attachment_kind: Optional[str] = None


class DocumentsHubReportItemV1(BaseModel):
    vehicle_id: int
    vehicle_name: str
    document_id: str
    document_type: str
    export_mode: str
    status: str
    finalized_at: Optional[datetime] = None
    verification_code: Optional[str] = None
    verify_url: Optional[str] = None
    classic_pdf_url: str
    verified_pdf_url: Optional[str] = None
    has_verified_report: bool = False


class DocumentsHubTachometerItemV1(BaseModel):
    vehicle_id: int
    vehicle_name: str
    history_entry_id: int
    check_date: Optional[datetime] = None
    protocol_number: Optional[str] = None
    mileage_km: Optional[int] = None
    available_documents_count: int = 0
    detail_url: str


class DocumentsHubTechnicalCertificateItemV1(BaseModel):
    vehicle_id: int
    vehicle_name: str
    document_title: str = "Velký technický průkaz"
    download_url: str
    generated_at: Optional[datetime] = None


class DocumentsHubSummaryOutV1(BaseModel):
    scope: str
    vehicles_total: int
    attachments_total: int
    reports_total: int
    tachometer_documents_total: int
    technical_certificates_total: int = 0
    attachments: list[DocumentsHubAttachmentItemV1] = []
    reports: list[DocumentsHubReportItemV1] = []
    tachometer_documents: list[DocumentsHubTachometerItemV1] = []
    technical_certificates: list[DocumentsHubTechnicalCertificateItemV1] = []


def _sanitize_file_stem(filename: str) -> str:
    stem = Path(filename or "doklad").stem
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return cleaned[:64] or "doklad"


def _ascii_slug(value: str, *, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").strip())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_value).strip("-")
    return (cleaned or fallback).upper()


def _normalize_role(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _vehicle_display_name(vehicle: VehicleModel | None) -> str:
    if vehicle is None:
        return "Vozidlo"
    return str(getattr(vehicle, "nickname", None) or getattr(vehicle, "plate", None) or f"Vozidlo #{getattr(vehicle, 'id', '?')}")


def _visible_vehicle_ids_for_documents(db: Session, *, current_user: Customer) -> list[int]:
    role_key = _normalize_role(getattr(current_user, "role", None))
    tenant_id = getattr(current_user, "tenant_id", None)

    if is_admin(role_key):
        query = db.query(VehicleModel.id)
        if tenant_id is not None:
            query = query.filter(VehicleModel.tenant_id == tenant_id)
        return [int(row[0]) for row in query.all() if row and row[0] is not None]

    if is_service(role_key):
        approved_ids = (
            db.query(VehicleServiceLink.vehicle_id)
            .filter(
                VehicleServiceLink.service_customer_id == current_user.id,
                VehicleServiceLink.status == "approved",
            )
            .all()
        )
        legacy_ids = (
            db.query(ServiceVehicleAccess.vehicle_id)
            .filter(
                ServiceVehicleAccess.service_customer_id == current_user.id,
                ServiceVehicleAccess.status == "active",
            )
            .all()
        )
        merged = {int(row[0]) for row in approved_ids + legacy_ids if row and row[0] is not None}
        return sorted(merged)

    owned_ids = (
        db.query(VehicleOwnership.vehicle_id)
        .filter(
            VehicleOwnership.customer_id == current_user.id,
            VehicleOwnership.tenant_id == tenant_id,
            VehicleOwnership.is_active.is_(True),
        )
        .all()
    )
    return sorted({int(row[0]) for row in owned_ids if row and row[0] is not None})


def _resolve_attachment_file(relative_key: str) -> Path | None:
    raw_key = str(relative_key or "").strip().replace("\\", "/")
    if not raw_key:
        return None
    candidate = (SERVICE_RECORD_ATTACHMENTS_DIR / raw_key).resolve()
    base = SERVICE_RECORD_ATTACHMENTS_DIR.resolve()
    if not str(candidate).startswith(str(base)):
        return None
    return candidate


def _extract_attachment_file_paths(attachments_raw: str | None) -> list[Path]:
    if not attachments_raw:
        return []
    try:
        payload = json.loads(attachments_raw)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []

    files: list[Path] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        key = item.get("storage_key") or item.get("path")
        if not key:
            continue
        resolved = _resolve_attachment_file(str(key))
        if resolved:
            files.append(resolved)
    return files


def _parse_attachments_payload(attachments_raw: str | None) -> list[dict[str, Any]]:
    if not attachments_raw:
        return []
    try:
        payload = json.loads(attachments_raw)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _count_available_tachometer_documents(documents_raw: str | None) -> int:
    payload = _parse_attachments_payload(documents_raw)
    return sum(1 for item in payload if bool(item.get("available")))


def _parsed_summary_needs_refresh(summary: Any) -> bool:
    if not isinstance(summary, dict):
        return True
    supplier_name = str(summary.get("supplier_name") or "").strip()
    if not supplier_name or "@" in supplier_name:
        return True
    items = summary.get("items")
    if not isinstance(items, list) or not items:
        # U faktur očekáváme položky; prázdný/rozbitý summary raději přepočítat.
        return True
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if any(pattern.search(name) for pattern in SUSPICIOUS_SUMMARY_PATTERNS):
            return True
    if summary.get("labor_total") is None and summary.get("materials_total") is None:
        return True
    return False


def _description_needs_refresh(description: Any) -> bool:
    text = str(description or "").strip()
    if not text:
        return True
    lower = text.lower()
    if "import" not in lower:
        return False
    if any(pattern.search(text) for pattern in SUSPICIOUS_SUMMARY_PATTERNS):
        return True
    return False


def _rebuild_attachment_parsed_summary(attachment: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    storage_key = attachment.get("storage_key") or attachment.get("path")
    if not storage_key:
        return None, None
    attachment_file = _resolve_attachment_file(str(storage_key))
    if not attachment_file or not attachment_file.is_file():
        return None, None

    source_type = str(attachment.get("source_type") or "invoice").strip().lower() or "invoice"
    if source_type not in ALLOWED_SOURCE_TYPES:
        source_type = "invoice"

    mime_type = str(attachment.get("mime_type") or "").strip() or None
    file_name = str(attachment.get("file_name") or attachment_file.name).strip() or attachment_file.name

    raw_content = attachment_file.read_bytes()
    extracted_text, extraction_warning, extraction_engine = _extract_text_from_file(
        content=raw_content,
        file_name=file_name,
        mime_type=mime_type,
    )
    parsed_data = _parse_document_payload(
        source_type=source_type,
        extracted_text=extracted_text,
        manual_text=None,
        manual_note=None,
        extraction_engine=extraction_engine,
        extraction_warning=extraction_warning,
    )
    service_report = _build_service_report_payload(parsed_data, source_type)
    return service_report, parsed_data


def _refresh_record_attachments_summary(record: ServiceRecordModel) -> bool:
    attachments_payload = _parse_attachments_payload(record.attachments)
    if not attachments_payload:
        return False

    payload_changed = False
    first_parsed_data: Optional[dict[str, Any]] = None

    for attachment in attachments_payload:
        current_summary = attachment.get("parsed_summary")
        if not _parsed_summary_needs_refresh(current_summary):
            continue
        rebuilt_summary, parsed_data = _rebuild_attachment_parsed_summary(attachment)
        if not rebuilt_summary:
            continue
        attachment["parsed_summary"] = rebuilt_summary
        payload_changed = True
        if first_parsed_data is None and parsed_data:
            first_parsed_data = parsed_data

    if not payload_changed:
        return False

    record.attachments = json.dumps(attachments_payload, ensure_ascii=False)
    if first_parsed_data and _description_needs_refresh(record.description):
        record.description = _build_service_record_description(first_parsed_data)
    return True


def _decode_base64_payload(payload: str) -> bytes:
    raw = str(payload or "").strip()
    if not raw:
        return b""
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    # RFC 2045 občas zalomí base64; klienti také vkládají mezery
    raw = re.sub(r"\s+", "", raw)
    pad = (-len(raw)) % 4
    if pad:
        raw = raw + ("=" * pad)
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Soubor není validní base64 payload: {exc}") from exc


def _store_attachment_for_vehicle(
    *,
    vehicle_id: int,
    vehicle: VehicleModel,
    current_user: Customer,
    file_name: str,
    file_mime_type: str,
    content: bytes,
) -> dict[str, Any]:
    if not content:
        raise HTTPException(status_code=422, detail="Nahraný soubor je prázdný.")
    if len(content) > MAX_ATTACHMENT_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Soubor je příliš velký (max 15 MB).")

    filename = str(file_name or "doklad")
    extension = Path(filename).suffix.lower().strip()
    mime_type = str(file_mime_type or "").lower().strip() or "application/octet-stream"

    if extension and extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Nepodporovaný typ souboru.")
    if not extension:
        if mime_type == "application/pdf":
            extension = ".pdf"
        elif mime_type in {"image/heic", "image/heif", "image/heic-sequence"}:
            extension = ".heic"
        elif mime_type.startswith("image/"):
            extension = ".jpg"
        elif mime_type.startswith("text/"):
            extension = ".txt"
        else:
            raise HTTPException(status_code=415, detail="Nepodporovaný typ souboru.")

    tenant_id = int(getattr(vehicle, "tenant_id", None) or getattr(current_user, "tenant_id", None) or 0)
    target_dir = SERVICE_RECORD_ATTACHMENTS_DIR / f"tenant_{tenant_id}" / f"vehicle_{vehicle_id}"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=507, detail=f"Nelze připravit úložiště přílohy: {exc}") from exc

    safe_stem = _sanitize_file_stem(filename)
    unique_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{safe_stem}_{secrets.token_hex(4)}{extension}"
    target_file = target_dir / unique_name
    try:
        target_file.write_bytes(content)
    except OSError as exc:
        raise HTTPException(status_code=507, detail=f"Nelze uložit přílohu servisního záznamu: {exc}") from exc

    storage_key = target_file.relative_to(SERVICE_RECORD_ATTACHMENTS_DIR).as_posix()
    return {
        "file_name": filename,
        "mime_type": mime_type,
        "file_size": len(content),
        "storage_key": storage_key,
        "download_url": f"/api/v1/vehicles/{vehicle_id}/records/attachments/download?key={storage_key}",
        "absolute_path": str(target_file),
    }


def _extract_mileage_from_text(raw_text: str) -> Optional[int]:
    text = str(raw_text or "")
    if not text:
        return None

    found: list[int] = []
    for match in MILEAGE_RE.finditer(text):
        token = str(match.group(1) or "").replace(" ", "").replace(".", "")
        try:
            value = int(token)
        except Exception:
            continue
        if 500 <= value <= 2_000_000:
            found.append(value)

    for match in MILEAGE_KEYWORD_RE.finditer(text):
        token = str(match.group(1) or "").replace(" ", "").replace(".", "")
        try:
            value = int(token)
        except Exception:
            continue
        if 500 <= value <= 2_000_000:
            found.append(value)
    if not found:
        return None
    return max(found)


def _to_iso_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return None
    return None


def _format_money_for_note(amount: Any, currency: str = "CZK") -> str:
    try:
        parsed = float(amount)
    except Exception:
        return "Neuvedeno"
    symbol = "Kč" if str(currency or "").upper() == "CZK" else str(currency or "").upper()
    return f"{parsed:,.2f}".replace(",", " ").replace(".", ",") + f" {symbol}"


def _normalize_parsed_items(parsed_data: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in parsed_data.get("items") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        quantity = item.get("quantity")
        unit = str(item.get("unit") or "").strip() or None
        total_price = item.get("total_price")
        unit_price = item.get("unit_price")
        currency = str(item.get("currency") or parsed_data.get("currency") or "CZK").upper()
        normalized.append(
            {
                "name": name,
                "quantity": quantity,
                "unit": unit,
                "unit_price": unit_price,
                "total_price": total_price,
                "currency": currency,
            }
        )
        if len(normalized) >= 30:
            break
    return normalized


def _parse_optional_float(raw_value: Any) -> Optional[float]:
    if raw_value is None:
        return None
    try:
        normalized = str(raw_value).replace("\xa0", " ").replace(" ", "").replace(",", ".")
        if not normalized:
            return None
        value = float(normalized)
        if not (value == value):  # NaN guard
            return None
        return value
    except Exception:
        return None


def _is_labor_item_name_or_unit(name: Any, unit: Any) -> bool:
    unit_value = str(unit or "").strip().lower()
    if unit_value in {"h", "hod", "hod.", "hodina", "hodiny", "hr", "nh"}:
        return True

    lower_name = str(name or "").strip().lower()
    if not lower_name:
        return False

    labor_keywords = (
        "práce",
        "prace",
        "servisní práce",
        "servisni prace",
        "hodinová sazba",
        "hodinova sazba",
        "diagnost",
        "montáž",
        "montaz",
        "demontáž",
        "demontaz",
        "oprava",
        "seřízení",
        "serizeni",
    )
    return any(keyword in lower_name for keyword in labor_keywords)


def _infer_labor_material_breakdown(items: list[dict[str, Any]]) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    labor_total = 0.0
    materials_total = 0.0
    labor_hours = 0.0
    labor_hour_rate: Optional[float] = None
    labor_found = False
    material_found = False

    for item in items:
        if not isinstance(item, dict):
            continue
        total_price = _parse_optional_float(item.get("total_price"))
        if total_price is None or total_price <= 0:
            continue

        name = item.get("name")
        unit = item.get("unit")
        quantity = _parse_optional_float(item.get("quantity"))
        unit_price = _parse_optional_float(item.get("unit_price"))
        is_labor = _is_labor_item_name_or_unit(name, unit)

        if is_labor:
            labor_found = True
            labor_total += float(total_price)
            unit_value = str(unit or "").strip().lower()
            if quantity is not None and quantity > 0 and unit_value in {"h", "hod", "hod.", "hodina", "hodiny", "hr", "nh"}:
                labor_hours += float(quantity)
                if labor_hour_rate is None and unit_price is not None and unit_price > 0:
                    labor_hour_rate = float(unit_price)
                elif labor_hour_rate is None:
                    labor_hour_rate = float(total_price) / float(quantity)
            elif labor_hour_rate is None and unit_price is not None and unit_price > 0:
                labor_hour_rate = float(unit_price)
        else:
            material_found = True
            materials_total += float(total_price)

    return (
        round(labor_total, 2) if labor_found else None,
        round(materials_total, 2) if material_found else None,
        round(labor_hours, 2) if labor_hours > 0 else None,
        round(float(labor_hour_rate), 2) if labor_hour_rate is not None and labor_hour_rate > 0 else None,
    )


def _suggest_category_from_parsed_data(parsed_data: dict[str, Any], source_type: str) -> str:
    text_parts: list[str] = []
    for item in parsed_data.get("items") or []:
        if isinstance(item, dict):
            text_parts.append(str(item.get("name") or ""))
    text_parts.extend(
        [
            str(parsed_data.get("supplier_name") or ""),
            str(parsed_data.get("service_summary") or ""),
            str(parsed_data.get("document_number") or ""),
            str(source_type or ""),
        ]
    )
    haystack = " ".join(text_parts).lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return "JINE"


def _build_service_report_payload(parsed_data: dict[str, Any], source_type: str) -> dict[str, Any]:
    supplier_email = parsed_data.get("supplier_email")
    supplier_website = parsed_data.get("supplier_website")
    service_link = parsed_data.get("service_link") or supplier_website or (f"mailto:{supplier_email}" if supplier_email else None)
    currency = str(parsed_data.get("currency") or "CZK").upper()
    items = _normalize_parsed_items(parsed_data)
    inferred_labor_total, inferred_materials_total, inferred_labor_hours, inferred_labor_hour_rate = _infer_labor_material_breakdown(items)

    labor_total = _parse_optional_float(parsed_data.get("labor_total"))
    materials_total = _parse_optional_float(parsed_data.get("materials_total"))
    labor_hours = _parse_optional_float(parsed_data.get("labor_hours"))
    labor_hour_rate = _parse_optional_float(parsed_data.get("labor_hour_rate"))

    if labor_total is None:
        labor_total = inferred_labor_total
    if materials_total is None:
        materials_total = inferred_materials_total
    if labor_hours is None:
        labor_hours = inferred_labor_hours
    if labor_hour_rate is None:
        labor_hour_rate = inferred_labor_hour_rate

    return {
        "source_type": source_type,
        "document_number": parsed_data.get("document_number"),
        "supplier_name": parsed_data.get("supplier_name"),
        "supplier_email": supplier_email,
        "supplier_website": supplier_website,
        "service_link": service_link,
        "customer_name": parsed_data.get("customer_name"),
        "service_summary": parsed_data.get("service_summary"),
        "technician_name": parsed_data.get("technician_name"),
        "technician_initials": parsed_data.get("technician_initials"),
        "issue_date": _to_iso_date(parsed_data.get("issue_date")),
        "due_date": _to_iso_date(parsed_data.get("due_date")),
        "currency": currency,
        "labor_hours": labor_hours,
        "labor_hour_rate": labor_hour_rate,
        "subtotal_without_vat": parsed_data.get("subtotal_without_vat"),
        "vat_amount": parsed_data.get("vat_amount"),
        "total_with_vat": parsed_data.get("total_with_vat"),
        "labor_total": labor_total,
        "materials_total": materials_total,
        "items": items,
    }


def _build_service_report_note(
    *,
    source_type: str,
    parsed_data: dict[str, Any],
    manual_note: Optional[str] = None,
) -> str:
    source_label_map = {
        "invoice": "Faktura",
        "delivery_note": "Dodací list",
        "work_order": "Zakázkový list",
        "receipt": "Účtenka",
        "manual": "Ruční zápis",
    }
    source_label = source_label_map.get(str(source_type or "").lower(), "Doklad")
    currency = str(parsed_data.get("currency") or "CZK").upper()

    lines: list[str] = [f"Servisní zpráva ({source_label})"]
    if parsed_data.get("supplier_name"):
        lines.append(f"Dodavatel: {parsed_data.get('supplier_name')}")
    if parsed_data.get("supplier_email"):
        lines.append(f"Kontakt servisu: {parsed_data.get('supplier_email')}")
    if parsed_data.get("service_link"):
        lines.append(f"Odkaz na servis: {parsed_data.get('service_link')}")
    if parsed_data.get("customer_name"):
        lines.append(f"Odběratel: {parsed_data.get('customer_name')}")
    if parsed_data.get("service_summary"):
        lines.append(f"Rozsah prací: {parsed_data.get('service_summary')}")
    if parsed_data.get("technician_name"):
        technician_line = f"Technik: {parsed_data.get('technician_name')}"
        if parsed_data.get("technician_initials"):
            technician_line += f" ({parsed_data.get('technician_initials')})"
        lines.append(technician_line)
    if parsed_data.get("document_number"):
        lines.append(f"Číslo dokladu: {parsed_data.get('document_number')}")
    if parsed_data.get("issue_date"):
        lines.append(f"Datum dokladu: {_to_iso_date(parsed_data.get('issue_date'))}")
    if parsed_data.get("due_date"):
        lines.append(f"Splatnost: {_to_iso_date(parsed_data.get('due_date'))}")
    if parsed_data.get("total_with_vat") is not None:
        lines.append(f"Celkem: {_format_money_for_note(parsed_data.get('total_with_vat'), currency)}")

    items = _normalize_parsed_items(parsed_data)
    if items:
        lines.append("Položky:")
        for item in items[:8]:
            item_line = f"- {item.get('name')}"
            qty = item.get("quantity")
            if qty is not None:
                try:
                    qty_value = float(qty)
                    qty_text = f"{qty_value:g}"
                except Exception:
                    qty_text = str(qty)
                unit = str(item.get("unit") or "").strip()
                item_line += f" ({qty_text}{(' ' + unit) if unit else ''})"
            if item.get("total_price") is not None:
                item_currency = str(item.get("currency") or currency).upper()
                item_line += f" – {_format_money_for_note(item.get('total_price'), item_currency)}"
            lines.append(item_line)
        if len(items) > 8:
            lines.append(f"... a dalších {len(items) - 8} položek")

    cleaned_manual_note = str(manual_note or "").strip()
    if cleaned_manual_note:
        lines.append(f"Poznámka: {cleaned_manual_note}")
    return "\n".join(lines).strip()


def _build_document_prefill_data(
    *,
    source_type: str,
    parsed_data: dict[str, Any],
    extracted_text: str,
    manual_text: Optional[str],
    manual_note: Optional[str],
    fallback_category: Optional[str],
    fallback_mileage: Optional[int],
    fallback_performed_at: Optional[datetime],
    fallback_description: Optional[str],
    fallback_price: Optional[float],
) -> dict[str, Any]:
    issue_date = parsed_data.get("issue_date")
    fallback_dt = fallback_performed_at
    if fallback_dt is not None and fallback_dt.tzinfo is not None:
        fallback_dt = fallback_dt.astimezone().replace(tzinfo=None)
    performed_at = fallback_dt
    if performed_at is None and issue_date is not None:
        try:
            performed_at = datetime.combine(issue_date, datetime.min.time())
        except Exception:
            performed_at = None
    if performed_at is None:
        performed_at = datetime.utcnow()

    parsed_total = parsed_data.get("total_with_vat")
    if parsed_total is None:
        subtotal = parsed_data.get("subtotal_without_vat")
        vat_amount = parsed_data.get("vat_amount")
        if subtotal is not None and vat_amount is not None:
            parsed_total = round(float(subtotal) + float(vat_amount), 2)
    total_price_value = float(fallback_price) if fallback_price is not None else (
        float(parsed_total) if parsed_total is not None else None
    )

    combined_text_for_mileage = "\n".join(
        part for part in [(extracted_text or "").strip(), str(manual_text or "").strip()] if part
    )
    auto_mileage = _extract_mileage_from_text(combined_text_for_mileage)
    mileage_value = fallback_mileage if fallback_mileage is not None else auto_mileage

    description_text = str(fallback_description or "").strip() or _build_service_record_description(parsed_data)
    if not description_text:
        description_text = "Import dokladu"

    category_value = str(fallback_category or "").strip().upper() or _suggest_category_from_parsed_data(
        parsed_data, source_type
    )
    if not category_value:
        category_value = "JINE"

    service_report = _build_service_report_payload(parsed_data, source_type)
    note_text = _build_service_report_note(
        source_type=source_type,
        parsed_data=parsed_data,
        manual_note=manual_note,
    )
    return {
        "performed_at": performed_at,
        "mileage": mileage_value,
        "description": description_text,
        "price": total_price_value,
        "note": note_text or None,
        "category": category_value,
        "service_report": service_report,
    }


@router.post("/{vehicle_id}/records", response_model=ServiceRecordOutV1)
def create_service_record(
    vehicle_id: int,
    record_data: ServiceRecordCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vytvoří nový servisní záznam"""
    try:
        assert_module_ready(db, "service_records", detail_prefix="Servisní historie není připravena")
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        
        # Načíst vozidlo kvůli tenant kontextu
        vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

        # Tenant kontext je povinný - primárně z vozidla, fallback z uživatele (legacy) a nakonec tenant 1
        tenant_id = vehicle.tenant_id or getattr(current_user, "tenant_id", None) or 1
        if is_service(getattr(current_user, "role", None)):
            assert_service_monthly_service_record_quota(db, service_customer_id=int(current_user.id))
        _enforce_free_service_record_limit(
            db,
            tenant_id=tenant_id,
            user_email=getattr(current_user, "email", None),
        )

        access_link = None
        owner_customer = get_primary_vehicle_owner(db, vehicle)
        service_owns_unassigned_vehicle = (
            is_service(getattr(current_user, "role", None))
            and owner_customer is None
            and getattr(vehicle, "provisioned_by_service_customer_id", None) == getattr(current_user, "id", None)
            and vehicle_state(db, vehicle) == "service_provisioned_unowned"
        )
        if str(getattr(current_user, "role", "") or "").strip().lower() == "service":
            if not service_owns_unassigned_vehicle:
                access_link = require_service_vehicle_link(
                    db,
                    current_user=current_user,
                    vehicle_id=vehicle_id,
                    require_create_record=True,
                )
                vin_norm, vin_kind = normalize_lookup_query(getattr(vehicle, "vin", None))
                if vin_kind != "vin" or not vin_norm:
                    raise HTTPException(
                        status_code=422,
                        detail="Pro servisní záznam je nutný platný VIN u vozidla (17 znaků). Doplňte jej v evidenci vozidla.",
                    )

        record_status = _normalize_record_status(getattr(record_data, "record_status", None), default="draft")

        # Vytvořit záznam
        user_id = current_user.id
        record = ServiceRecordModel(
            tenant_id=tenant_id,
            vehicle_id=vehicle_id,
            user_id=user_id,
            customer_id=int(getattr(record_data, "customer_id", None) or getattr(owner_customer, "id", 0) or 0) or None,
            service_id=int(getattr(record_data, "service_id", None) or (current_user.id if is_service(getattr(current_user, "role", None)) else 0) or 0) or None,
            work_order_id=getattr(record_data, "work_order_id", None),
            quote_id=getattr(record_data, "quote_id", None),
            performed_at=record_data.performed_at,
            mileage=record_data.mileage,
            description=record_data.description,
            price=record_data.price,
            note=record_data.note,
            category=record_data.category,
            attachments=record_data.attachments,
            next_service_due_date=record_data.next_service_due_date,
            record_status=record_status,
            service_type=getattr(record_data, "service_type", None),
            recommended_next_service_text=getattr(record_data, "recommended_next_service_text", None),
            recommended_next_service_date=getattr(record_data, "recommended_next_service_date", None),
            notes_customer_visible=getattr(record_data, "notes_customer_visible", None),
            total_price=getattr(record_data, "total_price", None) if getattr(record_data, "total_price", None) is not None else record_data.price,
        )
        attach_service_access_to_record(record=record, current_user=current_user, access_link=access_link)
        if service_owns_unassigned_vehicle:
            record.created_by_service_customer_id = int(current_user.id)
            record.service_id = int(current_user.id)
            record.origin = "service_created"
            record.visibility_scope = "safe_history_after_claim"
        
        db.add(record)
        db.flush()
        snapshot = _service_record_snapshot(record)
        _, snapshot_hash = _snapshot_json_and_hash(snapshot)
        record.snapshot_hash = snapshot_hash

        mileage_raw = getattr(record_data, "mileage", None)
        if mileage_raw is not None:
            try:
                mi = int(mileage_raw)
            except (TypeError, ValueError):
                mi = None
            if mi is not None and mi >= 0:
                prev = vehicle.current_mileage_km
                prev_i = int(prev) if prev is not None else None
                if prev_i is None or mi > prev_i:
                    vehicle.current_mileage_km = mi
                    vehicle.mileage_checked_at = datetime.utcnow()
                    db.add(
                        VehicleMileage(
                            tenant_id=int(tenant_id),
                            vehicle_id=int(vehicle_id),
                            mileage_km=mi,
                            source="service_record",
                            note=f"service_record_id={int(record.id)}",
                            service_record_id=int(record.id),
                            created_by_user_id=int(current_user.id),
                        )
                    )
                    write_global_audit_log(
                        db,
                        entity_type="vehicle",
                        entity_id=int(vehicle_id),
                        action="vehicle_mileage_updated_from_service_record",
                        actor_user_id=user_id,
                        actor_role=getattr(current_user, "role", None),
                        tenant_id=tenant_id,
                        vehicle_id=int(vehicle_id),
                        metadata={
                            "service_record_id": int(record.id),
                            "new_mileage_km": mi,
                            "previous_mileage_km": prev_i,
                        },
                    )
                elif prev_i is not None and mi < prev_i:
                    write_global_audit_log(
                        db,
                        entity_type="service_record",
                        entity_id=int(record.id),
                        action="service_record_mileage_below_current",
                        actor_user_id=user_id,
                        actor_role=getattr(current_user, "role", None),
                        tenant_id=tenant_id,
                        vehicle_id=int(vehicle_id),
                        metadata={
                            "submitted_mileage_km": mi,
                            "vehicle_current_mileage_km": prev_i,
                            "severity": "warning",
                        },
                    )

        write_global_audit_log(
            db,
            entity_type="service_record",
            entity_id=int(record.id),
            action="service_record_create",
            actor_user_id=user_id,
            actor_role=getattr(current_user, "role", None),
            tenant_id=tenant_id,
            vehicle_id=int(vehicle_id),
            metadata={
                "vehicle_id": int(vehicle_id),
                "vin": (str(getattr(vehicle, "vin", None) or "").strip().upper() or None),
                "service_access_link_id": int(access_link.id) if access_link else None,
                "created_by_service_customer_id": int(current_user.id)
                if is_service(getattr(current_user, "role", None))
                else None,
                "record_status": record_status,
                "service_id": getattr(record, "service_id", None),
            },
        )
        db.commit()
        db.refresh(record)
        
        return _serialize_service_record_out_v1(db, vehicle_id, current_user, record)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[SERVICE_RECORDS] Error creating record for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření servisního záznamu: {str(e)}")


@router.post("/{vehicle_id}/records/attachments/upload")
def upload_service_record_attachment(
    vehicle_id: int,
    payload: ServiceRecordAttachmentUploadRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Nahraje přílohu k servisnímu záznamu (typ před/po apod.) a připojí ji k záznamu."""
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key == "service":
        require_service_vehicle_link(
            db,
            current_user=current_user,
            vehicle_id=vehicle_id,
            require_create_record=False,
        )
    elif not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    kind = str(payload.attachment_kind or "").strip()
    if kind not in SERVICE_RECORD_ATTACHMENT_KINDS:
        raise HTTPException(
            status_code=422,
            detail="Neplatný attachment_kind (očekáváno: before_repair, after_repair, invoice_attachment, protocol, other).",
        )

    record = (
        db.query(ServiceRecordModel)
        .filter(
            ServiceRecordModel.id == int(payload.service_record_id),
            ServiceRecordModel.vehicle_id == int(vehicle_id),
            ServiceRecordModel.is_deleted.is_(False),
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Servisní záznam nebyl nalezen.")
    if role_key == "service":
        assert_viewer_may_mutate_service_record(db, vehicle_id, current_user, record)

    if not _attachment_request_looks_like_image(
        file_name=payload.file_name, file_mime_type=payload.file_mime_type
    ):
        _require_documents_plan(db, tenant_id=vehicle.tenant_id)

    content = _decode_base64_payload(payload.file_content_base64)
    attachment_meta = _store_attachment_for_vehicle(
        vehicle_id=vehicle_id,
        vehicle=vehicle,
        current_user=current_user,
        file_name=payload.file_name,
        file_mime_type=payload.file_mime_type,
        content=content,
    )

    items = _parse_attachments_payload(record.attachments)
    new_item = {
        "attachment_kind": kind,
        "service_record_id": int(record.id),
        "vehicle_id": int(vehicle_id),
        "file_name": attachment_meta["file_name"],
        "mime_type": attachment_meta["mime_type"],
        "file_size": attachment_meta["file_size"],
        "storage_key": attachment_meta["storage_key"],
        "download_url": attachment_meta["download_url"],
        "source_type": kind,
    }
    items.append(new_item)
    record.attachments = json.dumps(items, ensure_ascii=False)

    write_global_audit_log(
        db,
        entity_type="service_record",
        entity_id=int(record.id),
        action="service_record_attachment_upload",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(record.tenant_id),
        vehicle_id=int(vehicle_id),
        metadata={
            "attachment_kind": kind,
            "storage_key": attachment_meta["storage_key"],
            "vehicle_id": int(vehicle_id),
        },
    )
    db.commit()

    return {
        "service_record_id": int(record.id),
        "attachment_kind": kind,
        "vehicle_id": int(vehicle_id),
        "file_name": attachment_meta["file_name"],
        "mime_type": attachment_meta["mime_type"],
        "file_size": attachment_meta["file_size"],
        "storage_key": attachment_meta["storage_key"],
        "download_url": attachment_meta["download_url"],
    }


@router.post("/{vehicle_id}/records/auto-from-document")
def create_service_record_from_document(
    vehicle_id: int,
    payload: ServiceRecordAutoFromDocumentRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Automaticky vytvoří servisní záznam z nahraného dokladu (PDF/fotka/text).
    Používá stejný parser jako servisní workspace, aby se neduplikovala logika.
    """
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    _require_documents_plan(db, tenant_id=vehicle.tenant_id)
    tenant_id = vehicle.tenant_id or getattr(current_user, "tenant_id", None) or 1
    if is_service(getattr(current_user, "role", None)):
        assert_service_monthly_service_record_quota(db, service_customer_id=int(current_user.id))
    _enforce_free_service_record_limit(
        db,
        tenant_id=tenant_id,
        user_email=getattr(current_user, "email", None),
    )

    source_type = str(payload.source_type or "invoice").strip().lower()
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="Neplatný typ dokladu.")

    raw_content = _decode_base64_payload(payload.file_content_base64)
    attachment_meta = _store_attachment_for_vehicle(
        vehicle_id=vehicle_id,
        vehicle=vehicle,
        current_user=current_user,
        file_name=payload.file_name,
        file_mime_type=payload.file_mime_type,
        content=raw_content,
    )

    extracted_text, extraction_warning, extraction_engine = _extract_text_from_file(
        content=raw_content,
        file_name=payload.file_name,
        mime_type=payload.file_mime_type,
    )

    parsed_data = _parse_document_payload(
        source_type=source_type,
        extracted_text=extracted_text,
        manual_text=payload.manual_text,
        manual_note=payload.manual_note,
        extraction_engine=extraction_engine,
        extraction_warning=extraction_warning,
    )

    parse_confidence = float(parsed_data.get("confidence") or 0.0)
    processing_status = "processed"
    if not ((extracted_text or "").strip() or str(payload.manual_text or "").strip()):
        processing_status = "failed"
    elif parse_confidence < 0.35:
        processing_status = "needs_review"

    prefill = _build_document_prefill_data(
        source_type=source_type,
        parsed_data=parsed_data,
        extracted_text=extracted_text,
        manual_text=payload.manual_text,
        manual_note=payload.manual_note,
        fallback_category=payload.fallback_category,
        fallback_mileage=payload.fallback_mileage,
        fallback_performed_at=payload.fallback_performed_at,
        fallback_description=payload.fallback_description,
        fallback_price=payload.fallback_price,
    )

    attachments_payload = json.dumps(
        [
            {
                "kind": "user_document",
                "file_name": attachment_meta["file_name"],
                "mime_type": attachment_meta["mime_type"],
                "file_size": attachment_meta["file_size"],
                "storage_key": attachment_meta["storage_key"],
                "download_url": attachment_meta["download_url"],
                "source_type": source_type,
                "parsed_summary": prefill["service_report"],
            }
        ],
        ensure_ascii=False,
    )

    tenant_id = vehicle.tenant_id or getattr(current_user, "tenant_id", None) or 1
    access_link = None
    owner_customer = get_primary_vehicle_owner(db, vehicle)
    if str(getattr(current_user, "role", "") or "").strip().lower() == "service":
        access_link = require_service_vehicle_link(
            db,
            current_user=current_user,
            vehicle_id=vehicle_id,
            require_create_record=True,
        )
    record = ServiceRecordModel(
        tenant_id=tenant_id,
        vehicle_id=vehicle_id,
        user_id=current_user.id,
        customer_id=int(getattr(owner_customer, "id", 0) or 0) or None,
        service_id=int(current_user.id or 0) or None,
        quote_id=None,
        performed_at=prefill["performed_at"],
        mileage=prefill["mileage"],
        description=prefill["description"],
        price=prefill["price"],
        note=prefill["note"],
        category=prefill["category"],
        attachments=attachments_payload,
        record_status="draft",
        total_price=prefill["price"],
    )
    attach_service_access_to_record(record=record, current_user=current_user, access_link=access_link)
    db.add(record)
    db.flush()
    snapshot = _service_record_snapshot(record)
    _, snapshot_hash = _snapshot_json_and_hash(snapshot)
    record.snapshot_hash = snapshot_hash
    write_global_audit_log(
        db,
        entity_type="service_record",
        entity_id=int(record.id),
        action="service_record_create_from_document",
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=tenant_id,
        metadata={
            "vehicle_id": int(vehicle_id),
            "record_status": "draft",
            "source_type": source_type,
        },
    )
    db.commit()
    db.refresh(record)

    return {
        "record": record,
        "processing_status": processing_status,
        "parse_confidence": parse_confidence,
        "parsed_data": parsed_data,
        "prefill": prefill,
        "extraction_engine": extraction_engine,
        "extraction_warning": extraction_warning,
    }


@router.post("/{vehicle_id}/records/document-prefill")
def preview_service_record_from_document(
    vehicle_id: int,
    payload: ServiceRecordDocumentPrefillRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Vytěží data z dokladu a vrátí předvyplnění formuláře servisního záznamu.
    Záznam se v této fázi NEukládá.
    """
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    _require_documents_plan(db, tenant_id=vehicle.tenant_id)

    source_type = str(payload.source_type or "invoice").strip().lower()
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="Neplatný typ dokladu.")

    raw_content = _decode_base64_payload(payload.file_content_base64)
    extracted_text, extraction_warning, extraction_engine = _extract_text_from_file(
        content=raw_content,
        file_name=payload.file_name,
        mime_type=payload.file_mime_type,
    )
    parsed_data = _parse_document_payload(
        source_type=source_type,
        extracted_text=extracted_text,
        manual_text=payload.manual_text,
        manual_note=payload.manual_note,
        extraction_engine=extraction_engine,
        extraction_warning=extraction_warning,
    )

    parse_confidence = float(parsed_data.get("confidence") or 0.0)
    processing_status = "processed"
    if not ((extracted_text or "").strip() or str(payload.manual_text or "").strip()):
        processing_status = "failed"
    elif parse_confidence < 0.35:
        processing_status = "needs_review"

    prefill = _build_document_prefill_data(
        source_type=source_type,
        parsed_data=parsed_data,
        extracted_text=extracted_text,
        manual_text=payload.manual_text,
        manual_note=payload.manual_note,
        fallback_category=payload.fallback_category,
        fallback_mileage=payload.fallback_mileage,
        fallback_performed_at=payload.fallback_performed_at,
        fallback_description=payload.fallback_description,
        fallback_price=payload.fallback_price,
    )

    return {
        "processing_status": processing_status,
        "parse_confidence": parse_confidence,
        "parsed_data": parsed_data,
        "prefill": prefill,
        "extraction_engine": extraction_engine,
        "extraction_warning": extraction_warning,
    }


@router.get("/{vehicle_id}/records/attachments/download")
def download_service_record_attachment(
    vehicle_id: int,
    key: str = Query(..., min_length=3, max_length=500),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bezpečné stažení přílohy servisního záznamu."""
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    _require_documents_plan(db, tenant_id=vehicle.tenant_id)

    expected_segment = f"/vehicle_{vehicle_id}/"
    normalized_key = str(key or "").replace("\\", "/")
    if expected_segment not in f"/{normalized_key}":
        raise HTTPException(status_code=403, detail="Příloha nepatří k tomuto vozidlu.")

    owning_record = find_record_for_attachment_storage_key(db, vehicle_id, normalized_key)
    if owning_record is not None and not viewer_record_same_ownership_era(db, vehicle_id, current_user, owning_record):
        raise HTTPException(
            status_code=403,
            detail="Doklady předchozích majitelů nejsou z důvodu ochrany soukromí dostupné.",
        )

    attachment_file = _resolve_attachment_file(normalized_key)
    if not attachment_file or not attachment_file.is_file():
        raise HTTPException(status_code=404, detail="Příloha nebyla nalezena.")

    if owning_record is not None:
        write_global_audit_log(
            db,
            entity_type="service_record",
            entity_id=int(owning_record.id),
            action="service_record_attachment_download",
            actor_user_id=int(current_user.id),
            actor_role=str(getattr(current_user, "role", None) or ""),
            tenant_id=int(owning_record.tenant_id),
            vehicle_id=int(vehicle_id),
            metadata={"storage_key": normalized_key, "attachment_view": "download"},
        )
        db.commit()

    media_type = mimetypes.guess_type(str(attachment_file.name))[0] or "application/octet-stream"
    safe_filename_ascii = attachment_file.name.encode("ascii", "ignore").decode("ascii") or "doklad"
    safe_filename_utf8 = quote(attachment_file.name, safe="")
    content_disposition = f'inline; filename="{safe_filename_ascii}"; filename*=UTF-8\'\'{safe_filename_utf8}'
    return FileResponse(
        path=str(attachment_file),
        media_type=media_type,
        headers={"Content-Disposition": content_disposition},
    )


@router.get("/documents/hub", response_model=DocumentsHubSummaryOutV1)
def get_documents_hub_summary(
    attachments_limit: int = Query(default=30, ge=1, le=100),
    reports_limit: int = Query(default=20, ge=1, le=100),
    tachometer_limit: int = Query(default=20, ge=1, le=100),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_documents_plan(db, tenant_id=getattr(current_user, "tenant_id", None))
    vehicle_ids = _visible_vehicle_ids_for_documents(db, current_user=current_user)
    role_key = _normalize_role(getattr(current_user, "role", None))
    scope = "tenant" if is_admin(role_key) else ("service" if is_service(role_key) else "user")

    if not vehicle_ids:
        return DocumentsHubSummaryOutV1(
            scope=scope,
            vehicles_total=0,
            attachments_total=0,
            reports_total=0,
            tachometer_documents_total=0,
            technical_certificates_total=0,
        )

    vehicles = (
        db.query(VehicleModel)
        .filter(VehicleModel.id.in_(vehicle_ids))
        .all()
    )
    vehicle_by_id = {int(vehicle.id): vehicle for vehicle in vehicles}

    attachment_records = (
        db.query(ServiceRecordModel)
        .filter(
            ServiceRecordModel.vehicle_id.in_(vehicle_ids),
            ServiceRecordModel.is_deleted.is_(False),
            ServiceRecordModel.attachments.isnot(None),
        )
        .order_by(desc(ServiceRecordModel.performed_at), desc(ServiceRecordModel.id))
        .limit(max(attachments_limit * 3, attachments_limit))
        .all()
    )
    attachment_items: list[DocumentsHubAttachmentItemV1] = []
    for record in attachment_records:
        vehicle = vehicle_by_id.get(int(record.vehicle_id))
        if viewer_policy_applies_for_customer_workspace(current_user):
            if not viewer_record_same_ownership_era(db, int(record.vehicle_id), current_user, record):
                continue
        for attachment in _parse_attachments_payload(record.attachments):
            download_url = str(
                attachment.get("download_url")
                or (
                    f"/api/v1/vehicles/{int(record.vehicle_id)}/records/attachments/download"
                    f"?key={quote(str(attachment.get('storage_key') or ''), safe='')}"
                    if attachment.get("storage_key")
                    else ""
                )
            ).strip()
            if not download_url:
                continue
            file_name = str(attachment.get("file_name") or "").strip() or "Doklad"
            attachment_items.append(
                DocumentsHubAttachmentItemV1(
                    vehicle_id=int(record.vehicle_id),
                    vehicle_name=_vehicle_display_name(vehicle),
                    record_id=int(record.id),
                    performed_at=getattr(record, "performed_at", None),
                    description=getattr(record, "description", None),
                    category=getattr(record, "category", None),
                    file_name=file_name,
                    mime_type=(str(attachment.get("mime_type")).strip() if attachment.get("mime_type") else None),
                    download_url=download_url,
                    source_type=(str(attachment.get("source_type")).strip() if attachment.get("source_type") else None),
                    attachment_kind=(
                        str(attachment.get("attachment_kind")).strip()
                        if attachment.get("attachment_kind")
                        else None
                    ),
                )
            )
            if len(attachment_items) >= attachments_limit:
                break
        if len(attachment_items) >= attachments_limit:
            break

    report_rows = (
        db.query(VehicleReportDocument)
        .filter(VehicleReportDocument.vehicle_id.in_(vehicle_ids))
        .order_by(desc(VehicleReportDocument.finalized_at), desc(VehicleReportDocument.id))
        .all()
    )
    latest_report_by_vehicle: dict[int, VehicleReportDocument] = {}
    for row in report_rows:
        vehicle_key = int(row.vehicle_id)
        if vehicle_key not in latest_report_by_vehicle:
            latest_report_by_vehicle[vehicle_key] = row

    def _report_sort_key(vehicle: VehicleModel) -> datetime:
        row = latest_report_by_vehicle.get(int(vehicle.id))
        value = (
            getattr(row, "finalized_at", None)
            or getattr(vehicle, "updated_at", None)
            or getattr(vehicle, "created_at", None)
        )
        if isinstance(value, datetime):
            return value
        return datetime.min

    sorted_report_vehicles = sorted(
        vehicles,
        key=_report_sort_key,
        reverse=True,
    )[:reports_limit]

    report_items = []
    for vehicle in sorted_report_vehicles:
        row = latest_report_by_vehicle.get(int(vehicle.id))
        report_items.append(
            DocumentsHubReportItemV1(
                vehicle_id=int(vehicle.id),
                vehicle_name=_vehicle_display_name(vehicle),
                document_id=str(getattr(row, "document_id", None) or f"CLASSIC-PDF-{int(vehicle.id)}"),
                document_type=str(getattr(row, "document_type", None) or "service_records_pdf"),
                export_mode=str(getattr(row, "export_mode", None) or "classic"),
                status=str(getattr(row, "status", None) or "ready"),
                finalized_at=getattr(row, "finalized_at", None),
                verification_code=(str(row.verification_code).strip() if row and row.verification_code else None),
                verify_url=(f"/verify/{row.public_token}" if row and getattr(row, "public_token", None) else None),
                classic_pdf_url=f"/api/v1/vehicles/{int(vehicle.id)}/export/pdf",
                verified_pdf_url=(f"/api/v1/vehicles/{int(vehicle.id)}/report.pdf" if row else None),
                has_verified_report=bool(row),
            )
        )

    tachometer_rows = (
        db.query(VehicleTachometerHistoryEntry)
        .filter(VehicleTachometerHistoryEntry.vehicle_id.in_(vehicle_ids))
        .order_by(desc(VehicleTachometerHistoryEntry.check_date), desc(VehicleTachometerHistoryEntry.id))
        .limit(max(tachometer_limit * 2, tachometer_limit))
        .all()
    )
    tachometer_items: list[DocumentsHubTachometerItemV1] = []
    for row in tachometer_rows:
        available_count = _count_available_tachometer_documents(getattr(row, "documents_json", None))
        if available_count <= 0:
            continue
        tachometer_items.append(
            DocumentsHubTachometerItemV1(
                vehicle_id=int(row.vehicle_id),
                vehicle_name=_vehicle_display_name(vehicle_by_id.get(int(row.vehicle_id))),
                history_entry_id=int(row.id),
                check_date=getattr(row, "check_date", None),
                protocol_number=getattr(row, "protocol_number", None),
                mileage_km=getattr(row, "mileage_km", None),
                available_documents_count=available_count,
                detail_url=f"/api/v1/vehicles/{int(row.vehicle_id)}/tachometer/history/{int(row.id)}",
            )
        )
        if len(tachometer_items) >= tachometer_limit:
            break

    technical_certificate_items = [
        DocumentsHubTechnicalCertificateItemV1(
            vehicle_id=int(v.id),
            vehicle_name=_vehicle_display_name(v),
            document_title="Velký technický průkaz",
            download_url=f"/api/v1/vehicles/{int(v.id)}/documents/large-technical-certificate.pdf",
            generated_at=technical_certificate_generated_at(
                tenant_id=int(v.tenant_id),
                vehicle_id=int(v.id),
            ),
        )
        for v in sorted(vehicles, key=lambda item: (_vehicle_display_name(item).lower(), int(item.id)))
    ]

    return DocumentsHubSummaryOutV1(
        scope=scope,
        vehicles_total=len(vehicle_ids),
        attachments_total=len(attachment_items),
        reports_total=len(vehicle_ids),
        tachometer_documents_total=len(tachometer_items),
        technical_certificates_total=len(technical_certificate_items),
        attachments=attachment_items,
        reports=report_items,
        tachometer_documents=tachometer_items,
        technical_certificates=technical_certificate_items,
    )


@router.get("/{vehicle_id}/mileage-timeline")
def get_vehicle_mileage_timeline(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Sloučená časová osa km pro audit a náhled: servisní záznamy, servisní příjmy, STK/tachometr.
    Stejná logika jako graf v PDF reportu servisní historie.
    """
    assert_module_ready(db, "service_records", detail_prefix="Servisní historie není připravena")
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    _require_documents_plan(db, tenant_id=vehicle.tenant_id)
    return build_mileage_timeline_payload(db, vehicle_id)


@router.get("/{vehicle_id}/report.pdf")
def export_vehicle_report_pdf(
    vehicle_id: int,
    mode: Optional[str] = Query(default=None),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Nový export digitálního servisního výpisu vozidla včetně veřejného ověření.
    """
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    _require_documents_plan(db, tenant_id=vehicle.tenant_id)

    try:
        resolved_mode = resolve_report_mode(
            db=db,
            vehicle=vehicle,
            current_user=current_user,
            requested_mode=mode,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    payload = build_vehicle_service_report_payload(
        db=db,
        vehicle=vehicle,
        current_user=current_user,
        mode=resolved_mode,
    )
    payload, _document_row = finalize_vehicle_report_document(
        db=db,
        vehicle=vehicle,
        current_user=current_user,
        payload=payload,
    )
    pdf_content = render_vehicle_service_report_pdf(payload)

    brand = _ascii_slug(str(vehicle.brand or ""), fallback="VOZIDLO")
    model_name = _ascii_slug(str(vehicle.model or ""), fallback="DETAIL")
    vin = re.sub(r"[^A-Za-z0-9._-]+", "", str(vehicle.vin or "").strip()) or f"id-{vehicle.id}"
    filename = f"toozservis-vypis-vozidla-{brand}-{model_name}-{vin}.pdf"
    safe_filename_ascii = filename.encode("ascii", "ignore").decode("ascii") or f"vehicle-report-{vehicle.id}.pdf"
    safe_filename_utf8 = quote(filename, safe="")
    content_disposition = f'inline; filename="{safe_filename_ascii}"; filename*=UTF-8\'\'{safe_filename_utf8}'

    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition},
    )


@router.get("/{vehicle_id}/pdf", name="generate_pdf")
def generate_service_records_pdf(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    PDF servisní historie ke stažení — stejný renderer a vizuální styl jako digitální výpis,
    aby byl výstup konzistentní (tabulky, rámečky, časová osa km, graf). Dříve samostatná
    ReportLab šablona zapisovala do data/pdfs a mohla selhat na oprávněních; výstup jde přímo z paměti.
    """
    assert_module_ready(db, "service_records", detail_prefix="Servisní historie není připravena")
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    _require_documents_plan(db, tenant_id=vehicle.tenant_id)

    try:
        resolved_mode = resolve_report_mode(
            db=db,
            vehicle=vehicle,
            current_user=current_user,
            requested_mode=None,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    write_global_audit_log(
        db,
        entity_type="vehicle",
        entity_id=int(vehicle_id),
        action="pdf_export",
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=getattr(vehicle, "tenant_id", None),
        metadata={"endpoint": "vehicles_pdf", "renderer": "vehicle_service_report_pdf"},
    )
    db.commit()

    payload = build_vehicle_service_report_payload(
        db=db,
        vehicle=vehicle,
        current_user=current_user,
        mode=resolved_mode,
    )
    payload, _document_row = finalize_vehicle_report_document(
        db=db,
        vehicle=vehicle,
        current_user=current_user,
        payload=payload,
    )
    pdf_content = render_vehicle_service_report_pdf(payload)

    brand = _ascii_slug(str(vehicle.brand or ""), fallback="VOZIDLO")
    model_name = _ascii_slug(str(vehicle.model or ""), fallback="DETAIL")
    vin = re.sub(r"[^A-Za-z0-9._-]+", "", str(vehicle.vin or "").strip()) or f"id-{vehicle.id}"
    filename = f"servisni-historie-{brand}-{model_name}-{vin}.pdf"
    safe_filename_ascii = filename.encode("ascii", "ignore").decode("ascii") or f"servisni-historie-{vehicle.id}.pdf"
    safe_filename_utf8 = quote(filename, safe="")
    content_disposition = f'attachment; filename="{safe_filename_ascii}"; filename*=UTF-8\'\'{safe_filename_utf8}'

    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition},
    )


@router.get("/{vehicle_id}/export/pdf")
def export_vehicle_pdf_alias(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stejný výstup jako ``GET /vehicles/{vehicle_id}/pdf``."""
    return generate_service_records_pdf(vehicle_id, current_user, db)


@router.get("/{vehicle_id}/documents/large-technical-certificate.pdf")
def export_large_technical_certificate_pdf(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Informační PDF ve stylu klasického „velkého“ technického průkazu (hlavička Správa vozidel).
    Nahrazuje státní doklad pouze jako přehled dat v aplikaci.
    """
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    _require_documents_plan(db, tenant_id=vehicle.tenant_id)

    write_global_audit_log(
        db,
        entity_type="vehicle",
        entity_id=int(vehicle_id),
        action="large_technical_certificate_export",
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=getattr(vehicle, "tenant_id", None),
        metadata={"endpoint": "large_technical_certificate_pdf", "renderer": "large_technical_certificate_pdf"},
    )
    db.commit()

    pdf_content = regenerate_vehicle_large_technical_certificate_pdf(vehicle)

    brand = _ascii_slug(str(vehicle.brand or ""), fallback="VOZIDLO")
    model_name = _ascii_slug(str(vehicle.model or ""), fallback="MODEL")
    plate = _ascii_slug(str(vehicle.plate or ""), fallback="SPZ")
    vin = re.sub(r"[^A-Za-z0-9._-]+", "", str(vehicle.vin or "").strip()) or f"id-{vehicle.id}"
    filename = f"velky-technicny-prukaz-{brand}-{model_name}-{plate}-{vin}.pdf"
    safe_filename_ascii = filename.encode("ascii", "ignore").decode("ascii") or f"velky-tp-{vehicle.id}.pdf"
    safe_filename_utf8 = quote(filename, safe="")
    content_disposition = f'attachment; filename="{safe_filename_ascii}"; filename*=UTF-8\'\'{safe_filename_utf8}'

    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition},
    )


@router.get("/{vehicle_id}/records", response_model=List[ServiceRecordOutV1])
def get_service_records(
    vehicle_id: int,
    include_deleted: bool = Query(default=False),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací všechny servisní záznamy pro vozidlo"""
    try:
        assert_module_ready(db, "service_records", detail_prefix="Servisní historie není připravena")
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        
        # Načíst záznamy - řadit podle performed_at (nejnovější první)
        query = db.query(ServiceRecordModel).filter(
            ServiceRecordModel.vehicle_id == vehicle_id
        )
        if not include_deleted:
            query = query.filter(ServiceRecordModel.is_deleted.is_(False))
        records = query.order_by(nullslast(desc(ServiceRecordModel.performed_at))).all()

        return [_serialize_service_record_out_v1(db, vehicle_id, current_user, r) for r in records]
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SERVICE_RECORDS] Error getting records for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání servisních záznamů: {str(e)}")


@router.get("/{vehicle_id}/records/{record_id}", response_model=ServiceRecordOutV1)
def get_service_record(
    vehicle_id: int,
    record_id: int,
    include_deleted: bool = Query(default=False),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací konkrétní servisní záznam"""
    try:
        assert_module_ready(db, "service_records", detail_prefix="Servisní historie není připravena")
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        record = db.query(ServiceRecordModel).filter(
            ServiceRecordModel.id == record_id,
            ServiceRecordModel.vehicle_id == vehicle_id
        ).first()
        
        if not record:
            raise HTTPException(status_code=404, detail="Servisní záznam nenalezen")
        if bool(getattr(record, "is_deleted", False)) and not include_deleted:
            raise HTTPException(status_code=404, detail="Servisní záznam byl archivován")

        refreshed = _refresh_record_attachments_summary(record)
        if refreshed:
            db.add(record)
            db.commit()
            db.refresh(record)

        return _serialize_service_record_out_v1(db, vehicle_id, current_user, record)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SERVICE_RECORDS] Error getting record {record_id} for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání servisního záznamu: {str(e)}")


@router.put("/{vehicle_id}/records/{record_id}", response_model=ServiceRecordOutV1)
def update_service_record(
    vehicle_id: int,
    record_id: int,
    record_data: ServiceRecordUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Aktualizuje servisní záznam.
    POZOR: Záznamy vytvořené AI asistentem (created_by_ai=True) nelze smazat, pouze upravit.
    """
    try:
        assert_module_ready(db, "service_records", detail_prefix="Servisní historie není připravena")
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        
        record = db.query(ServiceRecordModel).filter(
            ServiceRecordModel.id == record_id,
            ServiceRecordModel.vehicle_id == vehicle_id
        ).first()
        
        if not record:
            raise HTTPException(status_code=404, detail="Servisní záznam nenalezen")
        if bool(getattr(record, "is_deleted", False)):
            raise HTTPException(status_code=409, detail="Archivovaný servisní záznam nelze upravovat")
        _assert_record_is_mutable(record)
        assert_viewer_may_mutate_service_record(db, vehicle_id, current_user, record)
        _assert_current_user_can_edit_record(current_user, record)

        previous_snapshot = _service_record_snapshot(record)
        previous_status = _normalize_record_status(getattr(record, "record_status", None), default="draft")
        # Aktualizace polí
        if record_data.performed_at is not None:
            record.performed_at = record_data.performed_at
        # Nájezd u existujícího záznamu je neměnný (důvěra v doklad); hodnota zůstává z DB.
        if record_data.description is not None:
            record.description = _merge_service_record_description_update(
                str(record.description or ""),
                record_data.description,
            )
        if record_data.price is not None:
            record.price = record_data.price
        if record_data.note is not None:
            record.note = record_data.note
        if record_data.category is not None:
            record.category = record_data.category
        if record_data.attachments is not None:
            record.attachments = record_data.attachments
        if record_data.next_service_due_date is not None:
            record.next_service_due_date = record_data.next_service_due_date
        if record_data.customer_id is not None:
            record.customer_id = record_data.customer_id
        if record_data.service_id is not None:
            record.service_id = record_data.service_id
        if record_data.work_order_id is not None:
            record.work_order_id = record_data.work_order_id
        if record_data.quote_id is not None:
            record.quote_id = record_data.quote_id
        if record_data.service_type is not None:
            record.service_type = record_data.service_type
        if record_data.recommended_next_service_text is not None:
            record.recommended_next_service_text = record_data.recommended_next_service_text
        if record_data.recommended_next_service_date is not None:
            record.recommended_next_service_date = record_data.recommended_next_service_date
        if record_data.notes_customer_visible is not None:
            record.notes_customer_visible = record_data.notes_customer_visible
        if record_data.total_price is not None:
            record.total_price = record_data.total_price
        if record_data.record_status is not None:
            record.record_status = _normalize_record_status(record_data.record_status, default=previous_status)

        new_snapshot = _service_record_snapshot(record)
        previous_snapshot_json, _ = _snapshot_json_and_hash(previous_snapshot)
        new_snapshot_json, snapshot_hash = _snapshot_json_and_hash(new_snapshot)
        record.snapshot_hash = snapshot_hash
        new_status = _normalize_record_status(getattr(record, "record_status", None), default=previous_status)
        audit_action = "status_change" if new_status != previous_status else "update"
        db.add(
            ServiceRecordAuditLog(
                tenant_id=record.tenant_id,
                service_record_id=record.id,
                vehicle_id=record.vehicle_id,
                changed_by_user_id=getattr(current_user, "id", None),
                action=audit_action,
                previous_snapshot_json=previous_snapshot_json,
                new_snapshot_json=new_snapshot_json,
                snapshot_hash=snapshot_hash,
                change_reason=None,
            )
        )
        write_global_audit_log(
            db,
            entity_type="service_record",
            entity_id=int(record.id),
            action="service_record_status_change" if new_status != previous_status else "service_record_update",
            actor_user_id=getattr(current_user, "id", None),
            actor_role=getattr(current_user, "role", None),
            tenant_id=getattr(record, "tenant_id", None),
            metadata={
                "vehicle_id": int(record.vehicle_id),
                "previous_status": previous_status,
                "new_status": new_status,
            },
        )
        
        db.commit()
        db.refresh(record)
        
        return _serialize_service_record_out_v1(db, vehicle_id, current_user, record)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[SERVICE_RECORDS] Error updating record {record_id} for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při aktualizaci servisního záznamu: {str(e)}")


@router.delete("/{vehicle_id}/records/{record_id}")
def delete_service_record(
    vehicle_id: int,
    record_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mazání servisních záznamů není podporováno. Záznam lze pouze upravit (PUT).
    Obnovu archivovaných záznamů provádí administrátor přes admin rozhraní.
    """
    raise HTTPException(
        status_code=403,
        detail=(
            "Servisní záznam nelze odstranit. Upravte ho přes úpravu záznamu. "
            "Pokud potřebujete obnovit dříve archivovaný záznam, kontaktujte podporu."
        ),
    )
