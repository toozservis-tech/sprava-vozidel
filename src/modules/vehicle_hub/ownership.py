"""
Ownership helpers for explicit vehicle <-> owner binding.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Customer, Vehicle, VehicleOwnership

# Po odebrání z účtu nesmí legacy `vehicles.user_email` dál odpovídat e-mailu uživatele —
# jinak GET /vehicles + backfill znovu aktivuje vlastnictví.
RELEASED_VEHICLE_EMAIL_SUFFIX = "@unassigned.vehicle.internal"


def released_placeholder_user_email(vehicle_id: int) -> str:
    return f"_released_vehicle_{int(vehicle_id)}{RELEASED_VEHICLE_EMAIL_SUFFIX}"


def is_unassigned_placeholder_vehicle_email(email: Optional[str]) -> bool:
    return _normalize_email(email).endswith(RELEASED_VEHICLE_EMAIL_SUFFIX.lower())


def _normalize_email(email: Optional[str]) -> str:
    return str(email or "").strip().lower()


def get_customer_by_email(db: Session, email: Optional[str]) -> Optional[Customer]:
    normalized = _normalize_email(email)
    if not normalized:
        return None
    return db.query(Customer).filter(func.lower(Customer.email) == normalized).first()


def get_primary_vehicle_owner_assignment(db: Session, vehicle_id: int) -> Optional[VehicleOwnership]:
    return (
        db.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == vehicle_id,
            VehicleOwnership.is_active.is_(True),
            VehicleOwnership.is_primary.is_(True),
        )
        .order_by(VehicleOwnership.id.asc())
        .first()
    )


def get_primary_vehicle_owner(db: Session, vehicle: Vehicle) -> Optional[Customer]:
    assignment = get_primary_vehicle_owner_assignment(db, int(vehicle.id))
    if assignment:
        return db.query(Customer).filter(Customer.id == assignment.customer_id).first()
    backfilled = backfill_vehicle_owner_assignment(db, vehicle)
    if backfilled:
        return db.query(Customer).filter(Customer.id == backfilled.customer_id).first()
    return None


def user_owns_vehicle(db: Session, customer: Customer, vehicle: Vehicle) -> bool:
    assignment = (
        db.query(VehicleOwnership.id)
        .filter(
            VehicleOwnership.vehicle_id == vehicle.id,
            VehicleOwnership.customer_id == customer.id,
            VehicleOwnership.is_active.is_(True),
        )
        .first()
    )
    if assignment is not None:
        return True
    backfilled = backfill_vehicle_owner_assignment(db, vehicle)
    if backfilled is None:
        return False
    return int(backfilled.customer_id) == int(customer.id)


def ensure_vehicle_owner_assignment(
    db: Session,
    *,
    vehicle: Vehicle,
    owner: Customer,
    assigned_by_customer_id: Optional[int] = None,
    ownership_origin: str = "manual",
) -> VehicleOwnership:
    now = datetime.utcnow()
    (
        db.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == vehicle.id,
            VehicleOwnership.customer_id != owner.id,
            VehicleOwnership.is_active.is_(True),
        )
        .update(
            {
                VehicleOwnership.is_active: False,
                VehicleOwnership.is_primary: False,
                VehicleOwnership.owned_until: now,
                VehicleOwnership.revoked_at: now,
                VehicleOwnership.updated_at: now,
            },
            synchronize_session=False,
        )
    )

    existing = (
        db.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == vehicle.id,
            VehicleOwnership.customer_id == owner.id,
            VehicleOwnership.ownership_type == "owner",
        )
        .first()
    )
    if existing:
        existing.is_active = True
        existing.is_primary = True
        existing.ownership_origin = ownership_origin or existing.ownership_origin or "manual"
        existing.owned_from = existing.owned_from or existing.assigned_at or now
        existing.owned_until = None
        existing.revoked_at = None
        existing.tenant_id = owner.tenant_id
        existing.updated_at = now
        db.flush()
        return existing

    ownership = VehicleOwnership(
        tenant_id=owner.tenant_id,
        vehicle_id=vehicle.id,
        customer_id=owner.id,
        ownership_type="owner",
        ownership_origin=ownership_origin or "manual",
        is_primary=True,
        is_active=True,
        assigned_by_customer_id=assigned_by_customer_id,
        owned_from=now,
        assigned_at=now,
    )
    db.add(ownership)
    db.flush()
    return ownership


def backfill_vehicle_owner_assignment(db: Session, vehicle: Vehicle) -> Optional[VehicleOwnership]:
    if getattr(vehicle, "status", None) == "archived":
        return None
    if is_unassigned_placeholder_vehicle_email(getattr(vehicle, "user_email", None)):
        return None
    owner = get_customer_by_email(db, getattr(vehicle, "user_email", None))
    if not owner:
        return None
    return ensure_vehicle_owner_assignment(
        db,
        vehicle=vehicle,
        owner=owner,
        assigned_by_customer_id=owner.id,
        ownership_origin="legacy_backfill",
    )


def release_vehicle_owner_assignment(
    db: Session,
    *,
    vehicle: Vehicle,
    owner: Customer,
) -> bool:
    now = datetime.utcnow()
    updated = (
        db.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == vehicle.id,
            VehicleOwnership.customer_id == owner.id,
            VehicleOwnership.is_active.is_(True),
        )
        .update(
            {
                VehicleOwnership.is_active: False,
                VehicleOwnership.is_primary: False,
                VehicleOwnership.owned_until: now,
                VehicleOwnership.revoked_at: now,
                VehicleOwnership.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    db.flush()
    return bool(updated)


def transfer_vehicle_to_new_owner(
    db: Session,
    *,
    vehicle: Vehicle,
    new_owner: Customer,
    assigned_by_customer_id: Optional[int] = None,
    ownership_origin: str = "vin_claim",
) -> VehicleOwnership:
    from .models import VehicleServiceLink

    release_time = datetime.utcnow()
    (
        db.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == vehicle.id,
            VehicleOwnership.customer_id != new_owner.id,
            VehicleOwnership.is_active.is_(True),
        )
        .update(
            {
                VehicleOwnership.is_active: False,
                VehicleOwnership.is_primary: False,
                VehicleOwnership.owned_until: release_time,
                VehicleOwnership.revoked_at: release_time,
                VehicleOwnership.updated_at: release_time,
            },
            synchronize_session=False,
        )
    )
    vehicle.tenant_id = new_owner.tenant_id
    vehicle.user_email = new_owner.email
    (
        db.query(VehicleServiceLink)
        .filter(
            VehicleServiceLink.vehicle_id == vehicle.id,
            VehicleServiceLink.status == "approved",
        )
        .update(
            {
                VehicleServiceLink.owner_customer_id: new_owner.id,
                VehicleServiceLink.tenant_id: new_owner.tenant_id,
                VehicleServiceLink.updated_at: release_time,
            },
            synchronize_session=False,
        )
    )
    db.flush()
    return ensure_vehicle_owner_assignment(
        db,
        vehicle=vehicle,
        owner=new_owner,
        assigned_by_customer_id=assigned_by_customer_id or new_owner.id,
        ownership_origin=ownership_origin,
    )


def get_current_owner_since(db: Session, vehicle: Vehicle) -> Optional[datetime]:
    assignment = get_primary_vehicle_owner_assignment(db, int(vehicle.id))
    if assignment:
        return assignment.owned_from or assignment.assigned_at
    return None


def get_owned_vehicle_ids(
    db: Session,
    customer: Customer,
    *,
    tenant_id: Optional[int] = None,
) -> set[int]:
    """
    Vrátí ID vozidel, která aktuálně patří zákazníkovi.

    Primárně používá explicitní ownership vazbu. Legacy `vehicles.user_email`
    slouží pouze jako compat fallback pro bezpečný přechod a při nalezení
    starých dat se pokusí založit ownership assignment.
    """
    customer_id = getattr(customer, "id", None)
    if customer_id is None:
        return set()

    tenant_scope = tenant_id if tenant_id is not None else getattr(customer, "tenant_id", None)
    ownership_query = db.query(VehicleOwnership.vehicle_id).filter(
        VehicleOwnership.customer_id == customer_id,
        VehicleOwnership.is_active.is_(True),
    )
    if tenant_scope is not None:
        ownership_query = ownership_query.filter(VehicleOwnership.tenant_id == tenant_scope)

    owned_vehicle_ids = {
        int(vehicle_id)
        for (vehicle_id,) in ownership_query.all()
        if vehicle_id is not None
    }

    normalized_email = _normalize_email(getattr(customer, "email", None))
    if normalized_email:
        legacy_query = db.query(Vehicle).filter(
            func.lower(Vehicle.user_email) == normalized_email,
            Vehicle.status != "archived",
        )
        if tenant_scope is not None:
            legacy_query = legacy_query.filter(Vehicle.tenant_id == tenant_scope)

        legacy_vehicles = legacy_query.all()
        if not legacy_vehicles and tenant_scope is not None:
            legacy_vehicles = (
                db.query(Vehicle)
                .filter(
                    func.lower(Vehicle.user_email) == normalized_email,
                    Vehicle.status != "archived",
                )
                .all()
            )
        for vehicle in legacy_vehicles:
            backfill_vehicle_owner_assignment(db, vehicle)
            if getattr(vehicle, "id", None) is not None:
                owned_vehicle_ids.add(int(vehicle.id))
        if legacy_vehicles:
            db.flush()

    return owned_vehicle_ids


def get_owned_vehicle_rows(
    db: Session,
    customer: Customer,
    *,
    tenant_id: Optional[int] = None,
) -> list[Vehicle]:
    owned_vehicle_ids = get_owned_vehicle_ids(db, customer, tenant_id=tenant_id)
    if not owned_vehicle_ids:
        return []

    query = db.query(Vehicle).filter(Vehicle.id.in_(sorted(owned_vehicle_ids)))
    return query.order_by(Vehicle.created_at.desc(), Vehicle.id.desc()).all()


def get_owned_vehicle(
    db: Session,
    customer: Customer,
    vehicle_id: int,
    *,
    tenant_id: Optional[int] = None,
) -> Optional[Vehicle]:
    owned_vehicle_ids = get_owned_vehicle_ids(db, customer, tenant_id=tenant_id)
    if int(vehicle_id) not in owned_vehicle_ids:
        return None

    tenant_scope = tenant_id if tenant_id is not None else getattr(customer, "tenant_id", None)
    query = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id))
    if tenant_scope is not None:
        query = query.filter(Vehicle.tenant_id == tenant_scope)
    return query.first()
