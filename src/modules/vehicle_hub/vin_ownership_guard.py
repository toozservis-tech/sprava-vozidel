"""Server-side VIN ownership guard for create/decode flows."""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Vehicle, VehicleOwnership

logger = logging.getLogger(__name__)

VIN_ALREADY_REGISTERED_OTHER_USER = "VIN_ALREADY_REGISTERED_OTHER_USER"
VIN_ALREADY_REGISTERED_OTHER_USER_MESSAGE = (
    "Vozidlo s tímto VIN je již evidováno v aplikaci pod jiným uživatelem."
)

VinVisibilityStatus = Literal["not_found", "same_tenant", "other_tenant"]


@dataclass(frozen=True)
class VinVisibilityResult:
    status: VinVisibilityStatus
    normalized_vin: str

    @property
    def can_continue(self) -> bool:
        return self.status != "other_tenant"


class VinAlreadyRegisteredOtherUserError(Exception):
    """Raised when a VIN exists under a different tenant."""

    def __init__(self, normalized_vin: str) -> None:
        self.normalized_vin = normalized_vin
        super().__init__(VIN_ALREADY_REGISTERED_OTHER_USER_MESSAGE)


def normalize_vin_for_guard(raw: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(raw or "").upper()).strip()


def validate_normalized_vin_for_guard(vin: str) -> None:
    if not vin:
        return
    if len(vin) != 17:
        raise HTTPException(status_code=422, detail="VIN musí mít přesně 17 znaků")
    if not all(c in "ABCDEFGHJKLMNPRSTUVWXYZ0123456789" for c in vin):
        raise HTTPException(
            status_code=422,
            detail="VIN obsahuje nepovolené znaky (I, O, Q nejsou povoleny)",
        )


def vin_other_tenant_block_payload() -> dict[str, object]:
    return {
        "code": VIN_ALREADY_REGISTERED_OTHER_USER,
        "message": VIN_ALREADY_REGISTERED_OTHER_USER_MESSAGE,
        "can_continue": False,
    }


def _vin_hash(vin: str) -> str:
    return hashlib.sha256(vin.encode("utf-8")).hexdigest()


def log_vin_other_tenant_block(*, current_tenant_id: int | None, vin: str, endpoint: str) -> None:
    logger.warning(
        "event=vin_duplicate_other_tenant_blocked current_tenant_id=%s vin_sha256=%s endpoint=%s",
        current_tenant_id,
        _vin_hash(vin),
        endpoint,
    )


def check_vin_visibility_for_create(
    db: Session,
    current_tenant_id: int | None,
    vin: str | None,
    *,
    validate: bool = True,
    exclude_vehicle_id: int | None = None,
) -> VinVisibilityResult:
    normalized_vin = normalize_vin_for_guard(vin)
    if validate:
        validate_normalized_vin_for_guard(normalized_vin)
    if not normalized_vin:
        return VinVisibilityResult(status="not_found", normalized_vin="")

    query = db.query(Vehicle).filter(Vehicle.vin.isnot(None))
    if exclude_vehicle_id is not None:
        query = query.filter(Vehicle.id != int(exclude_vehicle_id))

    for candidate in query.all():
        if normalize_vin_for_guard(getattr(candidate, "vin", None)) != normalized_vin:
            continue
        active_owner = (
            db.query(VehicleOwnership)
            .filter(
                VehicleOwnership.vehicle_id == int(candidate.id),
                VehicleOwnership.is_active.is_(True),
                VehicleOwnership.is_primary.is_(True),
            )
            .order_by(VehicleOwnership.id.asc())
            .first()
        )
        if active_owner is None:
            has_ownership_rows = (
                db.query(VehicleOwnership.id)
                .filter(VehicleOwnership.vehicle_id == int(candidate.id))
                .first()
                is not None
            )
            if has_ownership_rows:
                return VinVisibilityResult(status="not_found", normalized_vin=normalized_vin)

            candidate_tenant_id = getattr(candidate, "tenant_id", None)
            if current_tenant_id is not None and candidate_tenant_id == current_tenant_id:
                return VinVisibilityResult(status="same_tenant", normalized_vin=normalized_vin)
            return VinVisibilityResult(status="other_tenant", normalized_vin=normalized_vin)

        candidate_tenant_id = getattr(active_owner, "tenant_id", None)
        if current_tenant_id is not None and candidate_tenant_id == current_tenant_id:
            return VinVisibilityResult(status="same_tenant", normalized_vin=normalized_vin)
        return VinVisibilityResult(status="other_tenant", normalized_vin=normalized_vin)

    return VinVisibilityResult(status="not_found", normalized_vin=normalized_vin)


def assert_vin_visible_for_create(
    db: Session,
    current_tenant_id: int | None,
    vin: str | None,
    *,
    endpoint: str,
    validate: bool = True,
    exclude_vehicle_id: int | None = None,
) -> VinVisibilityResult:
    result = check_vin_visibility_for_create(
        db,
        current_tenant_id,
        vin,
        validate=validate,
        exclude_vehicle_id=exclude_vehicle_id,
    )
    if result.status == "other_tenant":
        log_vin_other_tenant_block(
            current_tenant_id=current_tenant_id,
            vin=result.normalized_vin,
            endpoint=endpoint,
        )
        raise VinAlreadyRegisteredOtherUserError(result.normalized_vin)
    return result
