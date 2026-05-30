"""
User-facing service access requests — /api/v1/user/service-requests
"""
from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.core.auth import get_current_user_email
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, ServiceAccessRequest, Vehicle
from src.modules.vehicle_hub.ownership import get_owned_vehicle_ids
from src.modules.vehicle_hub.routers_v1.services import _access_scope_summary, _ensure_services_schema
from src.modules.vehicle_hub.service_access import masked_plate, masked_vin, vehicle_label
from src.server.main_helpers import get_customer_by_email

router = APIRouter(prefix="/user", tags=["user-service-requests"])


def _require_user_customer(db: Session, email: str) -> Customer:
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nebyl nalezen.")
    role_key = str(getattr(customer, "role", "") or "").strip().lower()
    if role_key in {"service"}:
        raise HTTPException(status_code=403, detail="Endpoint je dostupný pouze v uživatelském režimu.")
    return customer


def _serialize_user_service_request(
    request_row: ServiceAccessRequest,
    service: Customer,
    vehicle: Vehicle,
) -> dict[str, Any]:
    return {
        "request_id": int(request_row.id),
        "vehicle_id": int(request_row.vehicle_id),
        "vehicle_name": vehicle_label(vehicle),
        "vehicle_label": vehicle_label(vehicle),
        "vehicle_plate_masked": masked_plate(vehicle.plate),
        "vehicle_vin_masked": masked_vin(vehicle.vin),
        "service_id": int(request_row.service_customer_id),
        "service_name": service.name or service.email,
        "reason": (request_row.request_message or "").strip() or None,
        "status": str(request_row.status or "pending"),
        "requested_at": request_row.requested_at.isoformat() if request_row.requested_at else None,
        "scope": (request_row.requested_scope or "").strip() or _access_scope_summary(),
    }


@router.get("/service-requests")
def list_user_service_requests(
    status: str | None = None,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    """
    Vrátí žádosti servisů o propojení s vozidly aktuálního uživatele.
    Bez interních servisních poznámek, faktur, cen a billing kontaktů.
    """
    _ensure_services_schema(db)
    customer = _require_user_customer(db, email)

    owned_vehicle_ids = sorted(get_owned_vehicle_ids(db, customer, tenant_id=getattr(customer, "tenant_id", None)))
    if not owned_vehicle_ids:
        return {"requests": [], "meta": {"total": 0, "pending": 0}}

    query = (
        db.query(ServiceAccessRequest, Customer, Vehicle)
        .join(Customer, ServiceAccessRequest.service_customer_id == Customer.id)
        .join(Vehicle, ServiceAccessRequest.vehicle_id == Vehicle.id)
        .filter(
            ServiceAccessRequest.owner_customer_id == customer.id,
            ServiceAccessRequest.vehicle_id.in_(owned_vehicle_ids),
        )
    )
    status_filter = str(status or "").strip().lower()
    if status_filter:
        query = query.filter(ServiceAccessRequest.status == status_filter)

    rows = query.order_by(ServiceAccessRequest.requested_at.desc(), ServiceAccessRequest.id.desc()).limit(50).all()
    items: List[dict[str, Any]] = [
        _serialize_user_service_request(request_row, service, vehicle)
        for request_row, service, vehicle in rows
    ]
    pending = sum(1 for item in items if str(item.get("status") or "").lower() == "pending")
    return {"requests": items, "meta": {"total": len(items), "pending": pending}}
