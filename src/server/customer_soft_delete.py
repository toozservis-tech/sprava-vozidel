"""
Sdílená logika bezpečného soft-delete zákazníka (admin API + údržbové skripty).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from src.modules.vehicle_hub.models import Customer, Vehicle, VehicleOwnership
from src.modules.vehicle_hub.account_state import (
    ensure_customer_account_state_schema,
    customer_is_deleted,
    customer_session_version,
    increment_customer_session_version,
)
from src.modules.vehicle_hub.customer_ordinal import record_customer_deletion_label


def build_deleted_alias_email(user_id: int) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"deleted+{user_id}.{stamp}@deleted.toozhub.local"


def _vehicle_ids_owned_by_customer(db: Session, customer_id: int) -> List[int]:
    rows = (
        db.query(VehicleOwnership.vehicle_id)
        .filter(
            VehicleOwnership.customer_id == customer_id,
            VehicleOwnership.is_active.is_(True),
        )
        .all()
    )
    return [int(vehicle_id) for (vehicle_id,) in rows if vehicle_id is not None]


def sync_vehicle_user_email_display_for_customer(db: Session, customer_id: int, display_email: str) -> int:
    """
    Deprecated compatibility sync for UI fields.
    Ownership logic must use vehicle_ownerships, not Vehicle.user_email.
    """
    vehicle_ids = _vehicle_ids_owned_by_customer(db, customer_id)
    if not vehicle_ids:
        return 0
    return (
        db.query(Vehicle)
        .filter(Vehicle.id.in_(vehicle_ids))
        .update({Vehicle.user_email: display_email}, synchronize_session=False)
    )


def soft_delete_customer(db: Session, user: Customer) -> Dict[str, Any]:
    """
    Stejný soft-delete jako DELETE /admin-api/users/{id}. Neprovádí commit.
    Vrací dict s klíči: already (bool), případně previous_email, deleted_alias, session_version.
    """
    ensure_customer_account_state_schema(db)
    if customer_is_deleted(user):
        return {"already": True, "email": user.email}

    previous_email = (user.email or "").strip().lower()
    record_customer_deletion_label(db, customer=user, email_before=previous_email)

    deleted_alias = build_deleted_alias_email(user.id)
    sync_vehicle_user_email_display_for_customer(db, user.id, deleted_alias)

    user.email = deleted_alias
    user.name = user.name or f"Deleted user #{user.id}"
    user.is_deleted = True
    user.is_disabled = True
    user.deleted_at = datetime.utcnow()
    user.disabled_at = datetime.utcnow()
    increment_customer_session_version(user)

    return {
        "already": False,
        "previous_email": previous_email,
        "deleted_alias": deleted_alias,
        "session_version": customer_session_version(user),
    }
