from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.core.rate_limiter import rate_limiter
from src.modules.vehicle_hub.audit_log import write_global_audit_log
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Vehicle, VehicleTransferToken
from src.modules.vehicle_hub.routers_v1.vehicle_lifecycle import (
    ClaimByTransferRequest,
    claim_vehicle_by_transfer,
    perform_transfer_technical_refresh_before_claim,
)
from src.modules.vehicle_hub.routers_v1.auth import get_current_user


router = APIRouter(prefix="/api/public/vehicle-transfer", tags=["public-vehicle-transfer"])

logger = logging.getLogger(__name__)

_PUBLIC_TRANSFER_RL_MAX = 60
_PUBLIC_TRANSFER_RL_PERIOD_SEC = 60


def _token_hash(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _masked_vin(vin: str | None) -> str | None:
    text = str(vin or "").strip().upper()
    if not text:
        return None
    return f"{text[:3]}***{text[-4:]}"


def _mask_spz_public(spz: str | None) -> str | None:
    raw = re.sub(r"\s+", "", str(spz or "").upper())
    if not raw:
        return None
    if len(raw) <= 3:
        return "***"
    return f"***{raw[-4:]}"


def _enforce_public_transfer_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    key = f"vehicle_transfer_public:{ip}"
    if not rate_limiter.check_rate_limit(key, max_calls=_PUBLIC_TRANSFER_RL_MAX, period=_PUBLIC_TRANSFER_RL_PERIOD_SEC):
        raise HTTPException(status_code=429, detail="Příliš mnoho požadavků — zkuste to později.")


@router.get("/{token}")
def get_vehicle_transfer_token(token: str, request: Request, db: Session = Depends(get_db)):
    _enforce_public_transfer_rate_limit(request)
    token_row = db.query(VehicleTransferToken).filter(VehicleTransferToken.token_hash == _token_hash(token)).first()
    if not token_row:
        write_global_audit_log(
            db,
            entity_type="vehicle_transfer_token",
            entity_id=None,
            action="transfer_token_invalid_lookup",
            actor_type="public",
            tenant_id=None,
            vehicle_id=None,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            metadata={"hint": "unknown_token_hash"},
        )
        db.commit()
        raise HTTPException(status_code=404, detail="Předávací token nebyl nalezen.")
    now = datetime.utcnow()
    if token_row.expires_at < now and token_row.status == "active":
        token_row.status = "expired"
        db.flush()

    vehicle = db.query(Vehicle).filter(Vehicle.id == int(token_row.vehicle_id)).first()
    write_global_audit_log(
        db,
        entity_type="vehicle_transfer_token",
        entity_id=int(token_row.id),
        action="transfer_token_opened",
        actor_type="public",
        tenant_id=getattr(vehicle, "tenant_id", None) if vehicle else None,
        vehicle_id=int(token_row.vehicle_id),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"status": token_row.status},
    )
    db.commit()

    vin_masked = _masked_vin(getattr(vehicle, "vin", None)) if vehicle else None
    brand = getattr(vehicle, "brand", None) if vehicle else None
    model = getattr(vehicle, "model", None) if vehicle else None
    year = getattr(vehicle, "year", None) if vehicle else None

    return {
        "status": token_row.status,
        "expires_at": token_row.expires_at.isoformat() if token_row.expires_at else None,
        "requires_login": True,
        "requires_confirmation": ["vin", "spz"],
        "vehicle": {
            "brand": brand,
            "model": model,
            "year": year,
            "vin_masked": vin_masked,
            "spz_masked": _mask_spz_public(getattr(vehicle, "plate", None)) if vehicle else None,
            "lifecycle_note": None,
        },
    }


@router.post("/{token}/refresh-technical")
def refresh_technical_before_transfer_claim(
    token: str,
    payload: ClaimByTransferRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Doplní / obnoví technický přehled před převodem (alias na sdílenou implementaci)."""
    _enforce_public_transfer_rate_limit(request)
    if payload.token != token:
        raise HTTPException(status_code=409, detail="Token v URL a těle požadavku se neshoduje.")
    return perform_transfer_technical_refresh_before_claim(db, payload, current_user)


@router.post("/{token}/claim")
def claim_public_vehicle_transfer(
    token: str,
    payload: ClaimByTransferRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.token != token:
        raise HTTPException(status_code=409, detail="Token v URL a těle požadavku se neshoduje.")
    return claim_vehicle_by_transfer(payload=payload, current_user=current_user, db=db)
