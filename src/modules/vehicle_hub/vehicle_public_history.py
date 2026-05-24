from __future__ import annotations

import hashlib
from datetime import date, datetime
from io import BytesIO
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.core.config import FRONTEND_BASE_URL, JWT_SECRET_KEY

from .quote_public_access import build_public_quote_page_url, get_active_quote_access_token
from .models import Customer, ServiceQuote, ServiceRecord, Vehicle, VehicleQrToken

try:
    import qrcode
    import qrcode.image.svg  # SvgPathImage
except ImportError:  # pragma: no cover
    qrcode = None  # type: ignore[misc, assignment]


PUBLIC_HISTORY_MODES = {"basic", "verified", "full"}
PUBLIC_RECORD_VISIBLE_STATUSES = {"submitted", "approved", "locked"}


def normalize_public_mode(raw_value: Optional[str], *, default: str = "basic") -> str:
    value = str(raw_value or default).strip().lower()
    if value not in PUBLIC_HISTORY_MODES:
        raise HTTPException(status_code=422, detail="Neplatný public_mode.")
    return value


def build_vehicle_qr_signature(*, token: str, vehicle_id: int, issued_at: datetime) -> str:
    payload = f"{JWT_SECRET_KEY}|{token}|{int(vehicle_id)}|{issued_at.isoformat()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_vehicle_qr_signature_valid(qr_token: VehicleQrToken) -> bool:
    try:
        expected = build_vehicle_qr_signature(
            token=str(qr_token.token or ""),
            vehicle_id=int(qr_token.vehicle_id),
            issued_at=qr_token.issued_at or datetime.utcnow(),
        )
    except Exception:
        return False
    return expected == str(qr_token.signature_hash or "")


def build_public_history_page_url(token: str) -> str:
    base = str(FRONTEND_BASE_URL or "").strip().rstrip("/")
    if not base:
        base = "http://127.0.0.1:8000"
    if base.endswith("/web/index.html"):
        return f"{base.rsplit('/', 1)[0]}/public-vehicle-history.html?token={token}"
    if base.endswith("/index.html"):
        return f"{base.rsplit('/', 1)[0]}/public-vehicle-history.html?token={token}"
    if base.endswith("/web"):
        return f"{base}/public-vehicle-history.html?token={token}"
    return f"{base}/web/public-vehicle-history.html?token={token}"


def render_vehicle_qr_svg(public_url: str) -> str:
    if qrcode is None:
        raise HTTPException(
            status_code=503,
            detail="QR generátor není dostupný. Doplňte závislost 'qrcode' a restartujte backend.",
        )
    image = qrcode.make(
        public_url,
        image_factory=qrcode.image.svg.SvgPathImage,
        box_size=8,
        border=2,
    )
    buffer = BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")


def _serialize_service_identity(service_customer: Optional[Customer]) -> dict:
    return {
        "name": getattr(service_customer, "name", None) or getattr(service_customer, "email", None),
        "ico": getattr(service_customer, "ico", None),
        "verified_status": bool(
            service_customer
            and str(getattr(service_customer, "role", "") or "").strip().lower() == "service"
            and not bool(getattr(service_customer, "is_disabled", False))
            and not bool(getattr(service_customer, "is_deleted", False))
        ),
    }


def _service_customer_for_record(db: Session, record: ServiceRecord) -> Optional[Customer]:
    service_customer_id = (
        getattr(record, "service_id", None)
        or getattr(record, "created_by_service_customer_id", None)
    )
    if not service_customer_id:
        return None
    return db.query(Customer).filter(Customer.id == int(service_customer_id)).first()


def _effective_public_mode(qr_token: VehicleQrToken) -> str:
    requested_mode = normalize_public_mode(getattr(qr_token, "public_mode", None), default="basic")
    if requested_mode == "full" and not bool(getattr(qr_token, "explicit_full_consent", False)):
        return "verified"
    return requested_mode


def serialize_public_history_payload(
    db: Session,
    *,
    vehicle: Vehicle,
    qr_token: VehicleQrToken,
) -> dict:
    effective_mode = _effective_public_mode(qr_token)
    rows = (
        db.query(ServiceRecord)
        .filter(
            ServiceRecord.vehicle_id == int(vehicle.id),
            ServiceRecord.is_deleted.is_(False),
        )
        .order_by(ServiceRecord.performed_at.desc(), ServiceRecord.id.desc())
        .all()
    )

    records = []
    for record in rows:
        record_status = str(getattr(record, "record_status", "draft") or "draft").strip().lower()
        if record_status not in PUBLIC_RECORD_VISIBLE_STATUSES:
            continue
        service_customer = _service_customer_for_record(db, record)
        quote = None
        if getattr(record, "quote_id", None):
            quote = db.query(ServiceQuote).filter(ServiceQuote.id == int(record.quote_id)).first()
        item = {
            "id": int(record.id),
            "performed_at": record.performed_at,
            "mileage": record.mileage,
            "category": record.category,
            "record_status": record_status,
            "quote_id": int(record.quote_id) if getattr(record, "quote_id", None) else None,
            "quote_status": getattr(quote, "status", None) if quote else None,
            "public_quote_url": (
                build_public_quote_page_url(str(public_quote_token.token))
                if quote and (public_quote_token := get_active_quote_access_token(db, quote_id=int(quote.id)))
                else None
            ),
            "service_identity": _serialize_service_identity(service_customer),
        }
        if effective_mode in {"verified", "full"}:
            item.update(
                {
                    "description": record.description,
                    "service_type": getattr(record, "service_type", None),
                    "recommended_next_service_text": getattr(record, "recommended_next_service_text", None),
                    "recommended_next_service_date": getattr(record, "recommended_next_service_date", None),
                    "total_price": (
                        getattr(quote, "total_price", None)
                        if quote and getattr(quote, "total_price", None) is not None
                        else getattr(record, "total_price", None)
                        if getattr(record, "total_price", None) is not None
                        else record.price
                    ),
                }
            )
        if effective_mode == "full":
            item["notes_customer_visible"] = getattr(record, "notes_customer_visible", None)
        records.append(item)

    latest_recommendation = next(
        (
            record for record in records
            if record.get("recommended_next_service_text") or record.get("recommended_next_service_date")
        ),
        None,
    )
    return {
        "vehicle_id": int(vehicle.id),
        "token_status": "active" if bool(getattr(qr_token, "active", False)) and not getattr(qr_token, "revoked_at", None) else "revoked",
        "public_mode": effective_mode,
        "vin": getattr(vehicle, "vin", None),
        "vehicle_label": " ".join(part for part in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None)] if part).strip()
        or getattr(vehicle, "nickname", None)
        or getattr(vehicle, "plate", None),
        "year": getattr(vehicle, "year", None),
        "engine": getattr(vehicle, "engine", None),
        "records": records,
        "recommended_next_service_text": latest_recommendation.get("recommended_next_service_text") if latest_recommendation else None,
        "recommended_next_service_date": latest_recommendation.get("recommended_next_service_date") if latest_recommendation else None,
    }
