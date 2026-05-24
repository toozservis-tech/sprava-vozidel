"""
Servisní případy (service-cases) jako fasáda nad ServiceIntake / service_intakes.

PR 1: create, list, detail, patch — bez OCR, faktur a PDF.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..audit_log import write_global_audit_log
from ..database import get_db
from ..models import Customer, ServiceIntake, Vehicle
from ..schema_management import assert_module_ready
from ..service_access import require_approved_service_vehicle_access
from ..workspace_entitlements import customer_has_service_workspace_access
from .auth import get_current_user

router = APIRouter(prefix="/services/workspace/service-cases", tags=["service-workspace-cases"])

_PATCH_STATUSES = frozenset({"draft", "intake_started", "intake_completed", "cancelled"})
_DEFAULT_LIMIT = 50
_MAX_LIMIT = 100


def _ensure_ws(db: Session) -> None:
    assert_module_ready(db, "service_workspace", detail_prefix="Servisní workspace není připraven")


def _require_service_workspace(user: Customer) -> None:
    if not customer_has_service_workspace_access(user):
        raise HTTPException(
            status_code=403,
            detail="Servisní centrum je dostupné pouze pro servisní účty.",
        )


class ServiceCaseCreateV1(BaseModel):
    vehicle_id: int = Field(..., gt=0)
    customer_request: Optional[str] = Field(default=None, max_length=8000)
    intake_note: Optional[str] = Field(default=None, max_length=8000)
    initial_mileage_km: Optional[int] = Field(default=None, ge=0)


class ServiceCasePatchV1(BaseModel):
    customer_request: Optional[str] = Field(default=None, max_length=8000)
    intake_note: Optional[str] = Field(default=None, max_length=8000)
    internal_note: Optional[str] = Field(default=None, max_length=8000)
    visible_to_owner_note: Optional[str] = Field(default=None, max_length=8000)
    status: Optional[str] = Field(default=None, max_length=64)


def _mileage_in(row: ServiceIntake) -> Optional[int]:
    return row.odometer_km


def _serialize_case(row: ServiceIntake, *, vehicle: Optional[Vehicle] = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": int(row.id),
        "vehicle_id": int(row.vehicle_id) if row.vehicle_id else None,
        "owner_customer_id": int(row.customer_id) if row.customer_id else None,
        "service_customer_id": int(row.service_id),
        "status": row.intake_status,
        "case_phase": row.intake_status,
        "customer_request": row.customer_request,
        "intake_note": row.intake_note,
        "mileage_in": _mileage_in(row),
        "mileage_out": row.mileage_out,
        "mileage_source": row.mileage_source,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if vehicle:
        out["vehicle"] = {
            "id": int(vehicle.id),
            "plate": vehicle.plate,
            "vin": vehicle.vin,
            "brand": vehicle.brand,
            "model": vehicle.model,
        }
    return out


def _get_owned_case_or_404(db: Session, *, current_user: Customer, case_id: int) -> ServiceIntake:
    row = db.query(ServiceIntake).filter(ServiceIntake.id == int(case_id)).first()
    if not row or int(row.service_id) != int(current_user.id):
        raise HTTPException(status_code=404, detail="Servisní případ nebyl nalezen.")
    return row


@router.post("/", status_code=201)
def create_service_case(
    payload: ServiceCaseCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace(current_user)
    _ensure_ws(db)

    vehicle, owner, link = require_approved_service_vehicle_access(
        db,
        current_user=current_user,
        vehicle_id=int(payload.vehicle_id),
    )

    now = datetime.utcnow()
    case = ServiceIntake(
        tenant_id=int(vehicle.tenant_id or owner.tenant_id or current_user.tenant_id or 1),
        service_tenant_id=getattr(current_user, "tenant_id", None),
        service_id=int(current_user.id),
        vehicle_id=int(vehicle.id),
        customer_id=int(owner.id),
        service_access_link_id=int(link.id),
        intake_status="intake_started",
        intake_source="service_cases_api",
        owner_approval_required=False,
        owner_approval_status="approved",
        check_in_at=now,
        created_by=int(current_user.id),
        customer_request=(payload.customer_request or "").strip() or None,
        intake_note=(payload.intake_note or "").strip() or None,
        odometer_km=payload.initial_mileage_km,
        mileage_source=("manual" if payload.initial_mileage_km is not None else None),
    )
    db.add(case)
    db.flush()

    write_global_audit_log(
        db,
        entity_type="service_case",
        entity_id=int(case.id),
        action="SERVICE_CASE_CREATED",
        actor_user_id=int(current_user.id),
        actor_role=str(current_user.role or ""),
        tenant_id=getattr(current_user, "tenant_id", None),
        vehicle_id=int(vehicle.id),
        metadata={
            "source": "service_cases_api",
            "vehicle_service_link_id": int(link.id),
            "owner_customer_id": int(owner.id),
        },
    )
    db.commit()
    db.refresh(case)
    return _serialize_case(case)


@router.get("/")
def list_service_cases(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None, max_length=64),
    vehicle_id: Optional[int] = Query(None, gt=0),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
):
    _require_service_workspace(current_user)
    _ensure_ws(db)

    q = db.query(ServiceIntake).filter(ServiceIntake.service_id == int(current_user.id))
    if status:
        q = q.filter(ServiceIntake.intake_status == str(status).strip())
    if vehicle_id:
        q = q.filter(ServiceIntake.vehicle_id == int(vehicle_id))
    rows = q.order_by(desc(ServiceIntake.id)).limit(limit).all()
    return {"items": [_serialize_case(r) for r in rows], "count": len(rows)}


@router.get("/{case_id}")
def get_service_case(
    case_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace(current_user)
    _ensure_ws(db)

    case = _get_owned_case_or_404(db, current_user=current_user, case_id=case_id)
    vehicle = None
    if case.vehicle_id:
        vehicle = db.query(Vehicle).filter(Vehicle.id == int(case.vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo pro tento případ nebylo nalezeno.")
    return _serialize_case(case, vehicle=vehicle)


@router.patch("/{case_id}")
def patch_service_case(
    case_id: int,
    payload: ServiceCasePatchV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace(current_user)
    _ensure_ws(db)

    case = _get_owned_case_or_404(db, current_user=current_user, case_id=case_id)

    if payload.customer_request is not None:
        case.customer_request = (payload.customer_request or "").strip() or None
    if payload.intake_note is not None:
        case.intake_note = (payload.intake_note or "").strip() or None
    if payload.internal_note is not None:
        case.internal_note = (payload.internal_note or "").strip() or None
    if payload.visible_to_owner_note is not None:
        case.visible_to_owner_note = (payload.visible_to_owner_note or "").strip() or None
    if payload.status is not None:
        st = str(payload.status).strip().lower()
        if st not in _PATCH_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Nepovolený stav. Povolené: {', '.join(sorted(_PATCH_STATUSES))}.",
            )
        case.intake_status = st
        if st == "cancelled":
            case.cancelled_at = datetime.utcnow()

    case.updated_at = datetime.utcnow()

    write_global_audit_log(
        db,
        entity_type="service_case",
        entity_id=int(case.id),
        action="SERVICE_CASE_UPDATED",
        actor_user_id=int(current_user.id),
        actor_role=str(current_user.role or ""),
        tenant_id=getattr(current_user, "tenant_id", None),
        vehicle_id=int(case.vehicle_id) if case.vehicle_id else None,
        metadata={"source": "service_cases_api"},
    )
    db.commit()
    db.refresh(case)

    vehicle = None
    if case.vehicle_id:
        vehicle = db.query(Vehicle).filter(Vehicle.id == int(case.vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo pro tento případ nebylo nalezeno.")
    return _serialize_case(case, vehicle=vehicle)
