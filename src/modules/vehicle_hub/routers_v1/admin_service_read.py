"""Read-only admin přehledy servisních entit (dohledatelnost)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.core.rbac import is_admin

from ..database import get_db
from ..models import (
    ServiceAccessRequest,
    ServiceInvoice,
    ServiceRecord,
    Vehicle,
    VehicleServiceLink,
)
from ..schema_management import assert_module_ready
from .auth import get_current_user

router = APIRouter(prefix="/admin/service-read", tags=["admin-service-read-v1"])


def _require_admin_ro(user: Customer) -> None:
    if not is_admin(getattr(user, "role", None)):
        raise HTTPException(status_code=403, detail="Pouze administrace.")


@router.get("/access-requests")
def admin_list_service_access_requests(
    vehicle_id: Optional[int] = Query(default=None, ge=1),
    vin: Optional[str] = Query(default=None, min_length=3, max_length=32),
    service_id: Optional[int] = Query(default=None, ge=1),
    user_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin_ro(current_user)
    assert_module_ready(db, "service_workspace", detail_prefix="Servisní schéma není připravené")

    q = db.query(ServiceAccessRequest).join(Vehicle, ServiceAccessRequest.vehicle_id == Vehicle.id)
    if vehicle_id is not None:
        q = q.filter(ServiceAccessRequest.vehicle_id == int(vehicle_id))
    if vin is not None:
        q = q.filter(Vehicle.vin == str(vin).strip().upper())
    if service_id is not None:
        q = q.filter(ServiceAccessRequest.service_customer_id == int(service_id))
    if user_id is not None:
        q = q.filter(ServiceAccessRequest.owner_customer_id == int(user_id))
    rows = q.order_by(ServiceAccessRequest.id.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": int(r.id),
                "tenant_id": int(r.tenant_id),
                "vehicle_id": int(r.vehicle_id),
                "owner_customer_id": int(r.owner_customer_id),
                "service_customer_id": int(r.service_customer_id),
                "status": r.status,
                "requested_at": r.requested_at.isoformat() if r.requested_at else None,
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
                "approved_link_id": int(r.approved_link_id) if r.approved_link_id else None,
            }
            for r in rows
        ]
    }


@router.get("/vehicle-service-links")
def admin_list_vehicle_service_links(
    vehicle_id: Optional[int] = Query(default=None, ge=1),
    vin: Optional[str] = Query(default=None, min_length=3, max_length=32),
    service_id: Optional[int] = Query(default=None, ge=1),
    user_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin_ro(current_user)
    assert_module_ready(db, "service_workspace", detail_prefix="Servisní schéma není připravené")

    q = db.query(VehicleServiceLink).join(Vehicle, VehicleServiceLink.vehicle_id == Vehicle.id)
    if vehicle_id is not None:
        q = q.filter(VehicleServiceLink.vehicle_id == int(vehicle_id))
    if vin is not None:
        q = q.filter(Vehicle.vin == str(vin).strip().upper())
    if service_id is not None:
        q = q.filter(VehicleServiceLink.service_customer_id == int(service_id))
    if user_id is not None:
        q = q.filter(VehicleServiceLink.owner_customer_id == int(user_id))
    rows = q.order_by(VehicleServiceLink.id.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": int(r.id),
                "tenant_id": int(r.tenant_id),
                "vehicle_id": int(r.vehicle_id),
                "owner_customer_id": int(r.owner_customer_id),
                "service_customer_id": int(r.service_customer_id),
                "status": r.status,
                "source_request_id": int(r.source_request_id) if r.source_request_id else None,
                "approved_at": r.approved_at.isoformat() if r.approved_at else None,
            }
            for r in rows
        ]
    }


@router.get("/service-invoices")
def admin_list_service_invoices(
    vehicle_id: Optional[int] = Query(default=None, ge=1),
    vin: Optional[str] = Query(default=None, min_length=3, max_length=32),
    service_id: Optional[int] = Query(default=None, ge=1),
    user_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin_ro(current_user)
    assert_module_ready(db, "service_invoices", detail_prefix="Faktury nejsou připravené")

    q = db.query(ServiceInvoice).outerjoin(Vehicle, ServiceInvoice.vehicle_id == Vehicle.id)
    if vehicle_id is not None:
        q = q.filter(ServiceInvoice.vehicle_id == int(vehicle_id))
    if vin is not None:
        q = q.filter(Vehicle.vin == str(vin).strip().upper())
    if service_id is not None:
        q = q.filter(ServiceInvoice.service_id == int(service_id))
    if user_id is not None:
        q = q.filter(ServiceInvoice.customer_id == int(user_id))
    rows = q.order_by(ServiceInvoice.id.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": int(r.id),
                "tenant_id": int(r.tenant_id),
                "service_id": int(r.service_id),
                "customer_id": int(r.customer_id),
                "vehicle_id": int(r.vehicle_id) if r.vehicle_id else None,
                "service_record_id": int(r.service_record_id) if getattr(r, "service_record_id", None) else None,
                "status": r.status,
                "invoice_number": r.invoice_number,
                "total": r.total,
                "currency": r.currency,
            }
            for r in rows
        ]
    }


@router.get("/service-records")
def admin_list_service_records(
    vehicle_id: Optional[int] = Query(default=None, ge=1),
    vin: Optional[str] = Query(default=None, min_length=3, max_length=32),
    service_id: Optional[int] = Query(default=None, ge=1),
    user_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin_ro(current_user)
    assert_module_ready(db, "service_records", detail_prefix="Servisní záznamy nejsou připravené")

    q = db.query(ServiceRecord).join(Vehicle, ServiceRecord.vehicle_id == Vehicle.id).filter(
        ServiceRecord.is_deleted.is_(False)
    )
    if vehicle_id is not None:
        q = q.filter(ServiceRecord.vehicle_id == int(vehicle_id))
    if vin is not None:
        q = q.filter(Vehicle.vin == str(vin).strip().upper())
    if service_id is not None:
        q = q.filter(ServiceRecord.service_id == int(service_id))
    if user_id is not None:
        q = q.filter(ServiceRecord.customer_id == int(user_id))
    rows = q.order_by(ServiceRecord.id.desc()).limit(limit).all()
    return {
        "items": [
            {
                "id": int(r.id),
                "tenant_id": int(r.tenant_id),
                "vehicle_id": int(r.vehicle_id),
                "customer_id": int(r.customer_id) if r.customer_id else None,
                "service_id": int(r.service_id) if r.service_id else None,
                "mileage": r.mileage,
                "performed_at": r.performed_at.isoformat() if r.performed_at else None,
                "record_status": r.record_status,
            }
            for r in rows
        ]
    }
