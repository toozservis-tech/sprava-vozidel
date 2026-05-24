"""
Deprecated compatibility layer.
All licensing decisions are delegated to src.modules.licensing.service.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..vehicle_hub.models import Customer
from .service import assert_vehicle_quota, get_license_status
from .types import EffectiveEntitlement, LicensePlan, LicenseStatus


def vehicles_count(db: Session, customer_email: str) -> int:
    customer = db.query(Customer).filter(Customer.email == customer_email).first()
    if not customer or customer.tenant_id is None:
        return 0
    status = get_license_status(db, customer.tenant_id, customer.email)
    return int(status.get("vehicles_current_user") or status.get("vehicles_current") or 0)


def get_entitlement(customer: Customer) -> Dict:
    return {
        "plan": str(getattr(customer, "_deprecated_license_plan", None) or "FREE"),
        "status": str(getattr(customer, "_deprecated_license_status", None) or "ACTIVE"),
        "period_end": None,
    }


def effective_max_vehicles(entitlement: Dict) -> Optional[int]:
    plan = str((entitlement or {}).get("plan") or "FREE").strip().upper()
    if plan == "PREMIUM":
        return None
    if plan == "BASIC":
        return 5
    return 1


def is_active(entitlement: Dict) -> bool:
    return str((entitlement or {}).get("status") or "ACTIVE").strip().upper() == "ACTIVE"


def is_over_limit(db: Session, customer_email: str, entitlement: Dict) -> bool:
    max_vehicles = effective_max_vehicles(entitlement)
    if max_vehicles is None:
        return False
    return vehicles_count(db, customer_email) >= max_vehicles


def enforce_vehicle_limit(db: Session, customer: Customer) -> None:
    if customer.tenant_id is None:
        raise HTTPException(status_code=403, detail="Uživatel nemá přiřazený tenant.")
    assert_vehicle_quota(db, customer.tenant_id)


def get_effective_entitlement(db: Session, customer: Customer) -> EffectiveEntitlement:
    if customer.tenant_id is None:
        return EffectiveEntitlement(
            plan=LicensePlan.FREE,
            status=LicenseStatus.EXPIRED,
            period_end=None,
            vehicles_count=0,
            vehicles_limit=1,
            is_over_limit=False,
        )

    status = get_license_status(db, customer.tenant_id, customer.email)
    plan_raw = str(status.get("plan") or "free").upper()
    status_raw = str(status.get("status") or "inactive").upper()
    plan = LicensePlan[plan_raw] if plan_raw in LicensePlan.__members__ else LicensePlan.FREE
    status_enum = LicenseStatus.ACTIVE if status_raw == "ACTIVE" else LicenseStatus.EXPIRED
    vehicles_limit = None if bool(status.get("is_unlimited")) else int(status.get("vehicles_limit") or 1)
    vehicles_count_value = int(status.get("vehicles_current_user") or status.get("vehicles_current") or 0)
    return EffectiveEntitlement(
        plan=plan,
        status=status_enum,
        period_end=None,
        vehicles_count=vehicles_count_value,
        vehicles_limit=vehicles_limit,
        is_over_limit=bool(status.get("vehicles_remaining") == 0 and not status.get("is_unlimited")),
    )


def require_plan_active(customer: Customer) -> None:
    entitlement = get_entitlement(customer)
    if not is_active(entitlement):
        status = entitlement.get("status", "EXPIRED")
        raise HTTPException(
            status_code=403,
            detail=f"License is not active (status: {status}). Please activate your license.",
        )
