from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .audit_log import write_global_audit_log
from .models import Customer, ServiceRecord, Vehicle, VehicleOwnership
from .ownership import ensure_vehicle_owner_assignment, get_primary_vehicle_owner_assignment

_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def normalize_vin(vin: Optional[str]) -> str:
    value = re.sub(r"[^A-Za-z0-9]", "", str(vin or "").upper())
    return value.strip()


def normalize_plate(plate: Optional[str]) -> str:
    return re.sub(r"[\s-]+", "", str(plate or "").strip().upper())


def validate_normalized_vin(vin: str, *, required: bool = False) -> None:
    if not vin:
        if required:
            raise HTTPException(status_code=422, detail="VIN je povinný.")
        return
    if not _VIN_RE.fullmatch(vin):
        raise HTTPException(status_code=422, detail="VIN musí mít 17 znaků a nesmí obsahovat I, O ani Q.")


def query_hash(value: str) -> Optional[str]:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def sync_vehicle_identity_fields(vehicle: Vehicle) -> None:
    vin = normalize_vin(getattr(vehicle, "vin", None))
    plate = normalize_plate(getattr(vehicle, "plate", None))
    if hasattr(vehicle, "normalized_vin"):
        vehicle.normalized_vin = vin or None
    if hasattr(vehicle, "normalized_plate"):
        vehicle.normalized_plate = plate or None
    if hasattr(vehicle, "merge_guard_hash"):
        strong = vin or (f"plate:{plate}" if plate else "")
        vehicle.merge_guard_hash = query_hash(strong) if strong else None


def find_vehicle_by_identifiers(
    db: Session,
    *,
    vin: Optional[str] = None,
    plate: Optional[str] = None,
    exclude_vehicle_id: Optional[int] = None,
) -> tuple[Optional[Vehicle], str]:
    vin_norm = normalize_vin(vin)
    plate_norm = normalize_plate(plate)

    query = db.query(Vehicle)
    if exclude_vehicle_id is not None:
        query = query.filter(Vehicle.id != int(exclude_vehicle_id))

    if vin_norm:
        candidates = query.filter(
            or_(
                getattr(Vehicle, "normalized_vin", Vehicle.vin) == vin_norm,
                Vehicle.vin == vin_norm,
            )
        ).order_by(Vehicle.created_at.asc(), Vehicle.id.asc()).all()
        for candidate in candidates:
            if normalize_vin(getattr(candidate, "normalized_vin", None) or getattr(candidate, "vin", None)) == vin_norm:
                return candidate, "vin"

    if plate_norm:
        candidates = query.filter(
            or_(
                getattr(Vehicle, "normalized_plate", Vehicle.plate) == plate_norm,
                Vehicle.plate == plate_norm,
            )
        ).order_by(Vehicle.created_at.asc(), Vehicle.id.asc()).all()
        for candidate in candidates:
            if normalize_plate(getattr(candidate, "normalized_plate", None) or getattr(candidate, "plate", None)) == plate_norm:
                return candidate, "plate"

    return None, "none"


def active_owner_assignment(db: Session, vehicle_id: int) -> Optional[VehicleOwnership]:
    return get_primary_vehicle_owner_assignment(db, int(vehicle_id))


def vehicle_state(db: Session, vehicle: Vehicle) -> str:
    assignment = active_owner_assignment(db, int(vehicle.id))
    if assignment:
        return "owned_vehicle"
    raw = str(getattr(vehicle, "global_vehicle_status", "") or "").strip()
    if raw:
        return raw
    if getattr(vehicle, "provisioned_by_service_customer_id", None):
        return "service_provisioned_unowned"
    return "service_provisioned_unowned"


def mark_vehicle_claimed(
    db: Session,
    *,
    vehicle: Vehicle,
    owner: Customer,
    actor: Customer,
    ownership_origin: str = "service_unowned_claim",
) -> VehicleOwnership:
    sync_vehicle_identity_fields(vehicle)
    vehicle.tenant_id = owner.tenant_id
    vehicle.user_email = owner.email
    if hasattr(vehicle, "global_vehicle_status"):
        vehicle.global_vehicle_status = "claimed_by_owner"
    if hasattr(vehicle, "claim_status"):
        vehicle.claim_status = "claimed"
    if hasattr(vehicle, "claimed_at"):
        vehicle.claimed_at = datetime.utcnow()
    if hasattr(vehicle, "claimed_by_customer_id"):
        vehicle.claimed_by_customer_id = int(owner.id)
    if hasattr(vehicle, "source_origin") and not getattr(vehicle, "source_origin", None):
        vehicle.source_origin = "service_created"
    ownership = ensure_vehicle_owner_assignment(
        db,
        vehicle=vehicle,
        owner=owner,
        assigned_by_customer_id=int(actor.id),
        ownership_origin=ownership_origin,
    )
    db.flush()
    return ownership


def _owner_safe_parts_from_record_attachments(raw: Optional[str]) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict):
        return []
    parts = payload.get("owner_safe_parts")
    if not isinstance(parts, list):
        return []
    safe: list[dict[str, Any]] = []
    for entry in parts:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        safe.append(
            {
                "name": name,
                "quantity": entry.get("quantity"),
                "unit": str(entry.get("unit") or "").strip() or None,
            }
        )
    return safe


def build_owner_safe_service_history(db: Session, *, vehicle_id: int, owner_customer_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(ServiceRecord)
        .filter(
            ServiceRecord.vehicle_id == int(vehicle_id),
            ServiceRecord.is_deleted.is_(False),
        )
        .order_by(ServiceRecord.performed_at.desc().nullslast(), ServiceRecord.id.desc())
        .all()
    )
    safe_scopes = {"safe_history_after_claim", "owner_visible_no_prices", "full_current_owner"}
    items: list[dict[str, Any]] = []
    for row in rows:
        scope = str(getattr(row, "visibility_scope", "") or "full_current_owner")
        if scope not in safe_scopes:
            continue
        parts = _owner_safe_parts_from_record_attachments(getattr(row, "attachments", None))
        items.append(
            {
                "id": int(row.id),
                "performed_at": row.performed_at.isoformat() if row.performed_at else None,
                "mileage": row.mileage,
                "category": row.category,
                "service_type": row.service_type,
                "description": row.notes_customer_visible or row.description,
                "work_summary": row.description,
                "parts": parts,
                "recommended_next_service_text": row.recommended_next_service_text,
                "recommended_next_service_date": row.recommended_next_service_date.isoformat() if row.recommended_next_service_date else None,
                "source_label": "Servisní záznam",
                "visibility_scope": "safe_history_after_claim" if scope != "full_current_owner" else "full_current_owner",
            }
        )
    write_global_audit_log(
        db,
        entity_type="vehicle_safe_history",
        entity_id=int(vehicle_id),
        action="safe_history_viewed",
        actor_user_id=int(owner_customer_id),
        actor_role="user",
        tenant_id=None,
        vehicle_id=int(vehicle_id),
        metadata={"projection": "owner_safe_service_history"},
    )
    db.flush()
    return items
