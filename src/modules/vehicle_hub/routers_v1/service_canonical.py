from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.core.config import DATA_DIR
from src.core.rbac import normalize_role

from ..audit_log import write_global_audit_log
from ..database import get_db
from ..models import (
    Customer,
    ServiceAccessRequest,
    ServiceIntake,
    ServiceLaborSession,
    ServiceRecord,
    Vehicle,
    VehiclePhotoAsset,
    VehicleServiceLink,
)
from ..ownership import get_primary_vehicle_owner
from ..schema_management import assert_module_ready
from ..service_access import (
    get_active_vehicle_service_link,
    masked_plate,
    masked_vin,
    normalize_lookup_query,
    require_service_vehicle_link,
    resolve_vehicle_for_lookup,
    vehicle_label,
)
from ..user_in_app_notifications import notify_owner_service_access_requested
from ..vehicle_photo_assets import jpeg_dimensions
from .auth import get_current_user
from .service_workspace import _require_service_workspace_role

"""
PRODUCTION CRITICAL LOGIC:
- service access enforcement
- lifecycle remove/transfer
- audit log
Jakákoliv změna musí projít production auditem.
"""

router = APIRouter(prefix="/api/service", tags=["service-canonical"])

SERVICE_CASE_PHOTO_ROOT = DATA_DIR / "vehicle_case_photos"
SERVICE_CASE_PHOTO_ROOT.mkdir(parents=True, exist_ok=True)

PLATE_RE = re.compile(r"\b([0-9A-Z]{2,3}\s?[0-9A-Z]{3,5})\b", re.IGNORECASE)
SERVICE_TEMPLATES = {"oil_change", "brakes", "tires", "diagnostics", "other"}


class SpzPhotoIntakeRequest(BaseModel):
    file_name: Optional[str] = Field(default=None, max_length=255)
    file_mime_type: Optional[str] = Field(default="image/jpeg", max_length=128)
    file_content_base64: Optional[str] = Field(default=None, max_length=40_000_000)
    manual_spz: Optional[str] = Field(default=None, max_length=32)
    ocr_text: Optional[str] = Field(default=None, max_length=2000)


class IntakeAccessRequestPayload(BaseModel):
    message: Optional[str] = Field(default=None, max_length=500)


class CasePhotoUploadItem(BaseModel):
    photo_kind: str = Field(default="intake_overview", max_length=64)
    file_name: str = Field(..., min_length=1, max_length=255)
    file_mime_type: str = Field(default="image/jpeg", max_length=128)
    file_content_base64: str = Field(..., min_length=20, max_length=40_000_000)


class CasePhotoUploadRequest(BaseModel):
    photos: list[CasePhotoUploadItem] = Field(default_factory=list, min_length=1, max_length=24)


class ServiceRecordFromCaseRequest(BaseModel):
    template_type: str = Field(default="other", max_length=64)
    description: str = Field(..., min_length=3, max_length=8000)
    performed_at: Optional[datetime] = None
    mileage: Optional[int] = Field(default=None, ge=0)
    category: Optional[str] = Field(default=None, max_length=64)
    price: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = Field(default=None, max_length=8000)
    next_service_due_date: Optional[str] = Field(default=None, max_length=16)
    recommended_next_service_km: Optional[int] = Field(default=None, ge=0)
    recommended_next_service_date: Optional[str] = Field(default=None, max_length=16)


def _normalize_spz(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _parse_spz(payload: SpzPhotoIntakeRequest) -> tuple[str, float, str]:
    manual = _normalize_spz(payload.manual_spz)
    if manual:
        return manual, 1.0, "manual"
    haystack = " ".join([str(payload.ocr_text or ""), str(payload.file_name or "")])
    match = PLATE_RE.search(haystack.upper())
    if match:
        return _normalize_spz(match.group(1)), 0.72, "ocr_parse"
    return "", 0.0, "not_found"


def _decode_file(content_base64: str | None) -> bytes:
    if not content_base64:
        return b""
    raw = str(content_base64)
    if "," in raw and raw.split(",", 1)[0].lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Soubor není validní base64.") from exc


def _case_or_404(db: Session, current_user: Customer, case_id: int) -> ServiceIntake:
    case = db.query(ServiceIntake).filter(ServiceIntake.id == int(case_id)).first()
    if not case:
        raise HTTPException(status_code=404, detail="Servisní případ nebyl nalezen.")
    if int(case.service_id) != int(current_user.id):
        raise HTTPException(status_code=403, detail="Servis nemá přístup k tomuto případu.")
    return case


def _serialize_case(case: ServiceIntake) -> dict[str, Any]:
    labor_hours = round((int(case.total_labor_seconds or 0) / 3600), 2)
    return {
        "id": int(case.id),
        "vehicle_id": int(case.vehicle_id) if case.vehicle_id else None,
        "customer_id": int(case.customer_id) if case.customer_id else None,
        "intake_status": case.intake_status,
        "intake_source": case.intake_source,
        "intake_spz_raw": case.intake_spz_raw,
        "intake_spz_normalized": case.intake_spz_normalized,
        "ocr_confidence": case.ocr_confidence,
        "owner_approval_required": bool(case.owner_approval_required),
        "owner_approval_status": case.owner_approval_status,
        "check_in_at": case.check_in_at.isoformat() if case.check_in_at else None,
        "work_started_at": case.work_started_at.isoformat() if case.work_started_at else None,
        "work_finished_at": case.work_finished_at.isoformat() if case.work_finished_at else None,
        "total_labor_seconds": int(case.total_labor_seconds or 0),
        "labor_hours_decimal": labor_hours,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
    }


@router.post("/vehicle-intake/from-spz-photo")
def create_intake_from_spz_photo(
    payload: SpzPhotoIntakeRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    spz, confidence, source = _parse_spz(payload)
    vehicle = None
    owner = None
    status = "not_found"
    if spz:
        vehicle, owner, _normalized, _identifier_type, status = resolve_vehicle_for_lookup(db, current_user=current_user, query=spz)
    approved_link = (
        get_active_vehicle_service_link(db, service_customer_id=int(current_user.id), vehicle_id=int(vehicle.id))
        if vehicle else None
    )
    case = ServiceIntake(
        tenant_id=int(getattr(current_user, "tenant_id", None) or 1),
        service_tenant_id=getattr(current_user, "tenant_id", None),
        service_id=int(current_user.id),
        vehicle_id=int(vehicle.id) if vehicle else None,
        customer_id=int(owner.id) if owner else None,
        intake_status="approved_for_service" if approved_link else "waiting_owner_approval",
        intake_source="spz_ocr" if source == "ocr_parse" else "manual_search",
        intake_spz_raw=payload.manual_spz or payload.ocr_text or payload.file_name,
        intake_spz_normalized=spz or None,
        ocr_confidence=confidence,
        owner_approval_required=not bool(approved_link),
        owner_approval_status="approved" if approved_link else "pending",
        check_in_at=datetime.utcnow(),
        created_by=int(current_user.id),
    )
    db.add(case)
    db.flush()
    write_global_audit_log(
        db,
        entity_type="service_case",
        entity_id=int(case.id),
        action="service_intake_created_from_spz_photo",
        actor_type="service_staff",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=getattr(current_user, "tenant_id", None),
        vehicle_id=int(vehicle.id) if vehicle else None,
        metadata={"spz_confidence": confidence, "lookup_status": status, "source": source},
    )
    db.commit()
    return {"case": _serialize_case(case), "lookup_status": status, "vehicle": {"id": int(vehicle.id), "label": vehicle_label(vehicle)} if vehicle and approved_link else None, "requires_owner_approval": not bool(approved_link)}


@router.post("/vehicle-intake/{case_id}/owner-access-request")
def request_owner_access_for_intake(
    case_id: int,
    payload: IntakeAccessRequestPayload | None = None,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    case = _case_or_404(db, current_user, case_id)
    if not case.vehicle_id:
        raise HTTPException(status_code=422, detail="Případ zatím není spárovaný s existujícím vozidlem.")
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(case.vehicle_id)).first()
    owner = get_primary_vehicle_owner(db, vehicle) if vehicle else None
    if not vehicle or not owner:
        raise HTTPException(status_code=404, detail="K vozidlu nelze určit aktuálního vlastníka.")
    existing = db.query(ServiceAccessRequest).filter(
        ServiceAccessRequest.service_customer_id == int(current_user.id),
        ServiceAccessRequest.vehicle_id == int(vehicle.id),
        ServiceAccessRequest.status == "pending",
    ).first()
    created_new_access_request = False
    if existing:
        request_row = existing
    else:
        created_new_access_request = True
        request_row = ServiceAccessRequest(
            tenant_id=int(vehicle.tenant_id or getattr(current_user, "tenant_id", None) or 1),
            service_customer_id=int(current_user.id),
            owner_customer_id=int(owner.id),
            vehicle_id=int(vehicle.id),
            requested_scope="history_read_create_record",
            status="pending",
            request_message=(payload.message if payload else None) or "Žádost vznikla při příjmu vozidla do servisu.",
        )
        db.add(request_row)
        db.flush()
    case.service_access_request_id = int(request_row.id)
    case.intake_status = "waiting_owner_approval"
    case.owner_approval_required = True
    case.owner_approval_status = "pending"
    write_global_audit_log(db, entity_type="vehicle_service_request", entity_id=int(request_row.id), action="service_access_requested_from_intake", actor_type="service_staff", actor_user_id=int(current_user.id), actor_role=getattr(current_user, "role", None), tenant_id=getattr(current_user, "tenant_id", None), vehicle_id=int(vehicle.id), metadata={"case_id": int(case.id)})
    if created_new_access_request:
        try:
            notify_owner_service_access_requested(
                db,
                owner_customer_id=int(owner.id),
                service=current_user,
                vehicle=vehicle,
                request_message=request_row.request_message,
            )
        except Exception as exc:
            print(f"[SERVICE_CANONICAL] In-app oznámení majiteli (intake žádost) selhalo: {exc}")
    db.commit()
    return {"requested": True, "request_id": int(request_row.id), "case": _serialize_case(case)}


@router.post("/vehicle-intake/{case_id}/upload-photos")
def upload_intake_photos(
    case_id: int,
    payload: CasePhotoUploadRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    case = _case_or_404(db, current_user, case_id)
    if not case.vehicle_id:
        raise HTTPException(status_code=422, detail="Fotky lze uložit až po spárování případu s vozidlem.")
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(case.vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno.")
    allowed_kinds = {"primary_thumbnail", "intake_overview", "damage_evidence", "repair_area_before", "repair_area_after", "document_scan", "other"}
    created = []
    date_key = datetime.utcnow().strftime("%Y-%m-%d")
    vin_key = re.sub(r"[^A-Z0-9_-]", "_", str(vehicle.vin or f"vehicle-{vehicle.id}").upper())
    for item in payload.photos:
        kind = item.photo_kind if item.photo_kind in allowed_kinds else "other"
        content = _decode_file(item.file_content_base64)
        if not content:
            raise HTTPException(status_code=422, detail="Nahraná fotka je prázdná.")
        if not str(item.file_mime_type or "").lower().startswith("image/"):
            raise HTTPException(status_code=415, detail="Podporované jsou pouze obrázky.")
        digest = hashlib.sha256(content).hexdigest()
        ext = Path(item.file_name).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            ext = ".jpg"
        rel_path = Path(vin_key) / date_key / f"case-{int(case.id)}" / kind / f"{secrets.token_hex(10)}{ext}"
        dest = SERVICE_CASE_PHOTO_ROOT / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        width, height = (None, None)
        try:
            width, height = jpeg_dimensions(content)
        except Exception:
            pass
        row = VehiclePhotoAsset(
            tenant_id=int(vehicle.tenant_id or getattr(current_user, "tenant_id", None) or 1),
            vehicle_id=int(vehicle.id),
            related_case_id=int(case.id),
            owner_customer_id=int(case.customer_id) if case.customer_id else None,
            role="gallery",
            photo_kind=kind,
            vin=vehicle.vin,
            capture_date=datetime.utcnow(),
            storage_key=str(rel_path),
            storage_path_original=str(dest),
            storage_path_preview=str(dest),
            original_filename=item.file_name,
            mime_type=item.file_mime_type,
            file_size_bytes=len(content),
            width=width,
            height=height,
            sha256_hex=digest,
            uploaded_by_customer_id=int(current_user.id),
            sort_order=0,
        )
        db.add(row)
        db.flush()
        created.append({"id": int(row.id), "photo_kind": kind, "file_hash": digest, "storage_path_original": str(dest)})
    write_global_audit_log(db, entity_type="service_case", entity_id=int(case.id), action="service_case_photos_uploaded", actor_type="service_staff", actor_user_id=int(current_user.id), actor_role=getattr(current_user, "role", None), tenant_id=getattr(current_user, "tenant_id", None), vehicle_id=int(vehicle.id), metadata={"photo_count": len(created), "photo_ids": [item["id"] for item in created]})
    db.commit()
    return {"uploaded": created, "case": _serialize_case(case)}


@router.post("/vehicle-intake/{case_id}/start-work")
def start_work(
    case_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    case = _case_or_404(db, current_user, case_id)
    open_session = db.query(ServiceLaborSession).filter(ServiceLaborSession.service_case_id == int(case.id), ServiceLaborSession.stopped_at.is_(None)).first()
    if open_session:
        raise HTTPException(status_code=409, detail="Na tomto případu už běží měření práce.")
    now = datetime.utcnow()
    session = ServiceLaborSession(
        tenant_id=int(getattr(current_user, "tenant_id", None) or 1),
        service_case_id=int(case.id),
        vehicle_id=int(case.vehicle_id) if case.vehicle_id else None,
        service_customer_id=int(current_user.id),
        technician_id=int(current_user.id),
        started_at=now,
    )
    db.add(session)
    case.work_started_at = case.work_started_at or now
    case.intake_status = "in_progress"
    write_global_audit_log(db, entity_type="service_labor_session", entity_id=None, action="labor_started", actor_type="service_staff", actor_user_id=int(current_user.id), actor_role=getattr(current_user, "role", None), tenant_id=getattr(current_user, "tenant_id", None), vehicle_id=int(case.vehicle_id) if case.vehicle_id else None, metadata={"case_id": int(case.id)})
    db.commit()
    return {"started": True, "case": _serialize_case(case)}


@router.post("/vehicle-intake/{case_id}/stop-work")
def stop_work(
    case_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    case = _case_or_404(db, current_user, case_id)
    session = db.query(ServiceLaborSession).filter(ServiceLaborSession.service_case_id == int(case.id), ServiceLaborSession.stopped_at.is_(None)).order_by(ServiceLaborSession.started_at.desc()).first()
    if not session:
        raise HTTPException(status_code=409, detail="Na tomto případu neběží žádné měření práce.")
    now = datetime.utcnow()
    session.stopped_at = now
    session.duration_seconds = max(0, int((now - session.started_at).total_seconds()))
    total = db.query(ServiceLaborSession).filter(ServiceLaborSession.service_case_id == int(case.id)).all()
    case.total_labor_seconds = sum(int(row.duration_seconds or 0) for row in total)
    case.work_finished_at = now
    case.intake_status = "paused"
    write_global_audit_log(db, entity_type="service_labor_session", entity_id=int(session.id), action="labor_stopped", actor_type="service_staff", actor_user_id=int(current_user.id), actor_role=getattr(current_user, "role", None), tenant_id=getattr(current_user, "tenant_id", None), vehicle_id=int(case.vehicle_id) if case.vehicle_id else None, metadata={"case_id": int(case.id), "duration_seconds": session.duration_seconds})
    db.commit()
    return {"stopped": True, "case": _serialize_case(case)}


@router.post("/vehicle-intake/{case_id}/create-service-record")
def create_service_record_from_case(
    case_id: int,
    payload: ServiceRecordFromCaseRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    case = _case_or_404(db, current_user, case_id)
    if not case.vehicle_id:
        raise HTTPException(status_code=422, detail="Finální servisní záznam vyžaduje spárované vozidlo.")
    link = require_service_vehicle_link(db, current_user=current_user, vehicle_id=int(case.vehicle_id), require_create_record=True)
    owner = get_primary_vehicle_owner(db, db.query(Vehicle).filter(Vehicle.id == int(case.vehicle_id)).first())
    template = str(payload.template_type or "other").strip().lower()
    if template not in SERVICE_TEMPLATES:
        raise HTTPException(status_code=422, detail="Neplatná servisní šablona.")
    record = ServiceRecord(
        tenant_id=int(getattr(current_user, "tenant_id", None) or link.tenant_id or 1),
        vehicle_id=int(case.vehicle_id),
        user_id=int(current_user.id),
        customer_id=int(owner.id) if owner else None,
        service_id=int(current_user.id),
        performed_at=payload.performed_at or datetime.utcnow(),
        mileage=payload.mileage,
        description=payload.description,
        price=payload.price,
        note=payload.note,
        category=(payload.category or template).upper(),
        service_type=template,
        record_status="submitted",
        origin="service_verified",
        service_case_id=int(case.id),
        created_by_service_customer_id=int(current_user.id),
        service_access_link_id=int(link.id),
        labor_seconds=int(case.total_labor_seconds or 0),
        recommended_next_service_text=("Dalsi interval dle sablony: " + template),
        recommended_next_service_km=payload.recommended_next_service_km,
        visibility_scope="summary_previous_owner_full_current_owner",
    )
    db.add(record)
    case.intake_status = "completed"
    case.owner_approval_status = "approved"
    case.service_access_link_id = int(link.id)
    db.flush()
    write_global_audit_log(db, entity_type="service_record", entity_id=int(record.id), action="service_record_created_from_intake", actor_type="service_staff", actor_user_id=int(current_user.id), actor_role=getattr(current_user, "role", None), tenant_id=getattr(current_user, "tenant_id", None), vehicle_id=int(case.vehicle_id), metadata={"case_id": int(case.id), "template_type": template, "labor_seconds": int(case.total_labor_seconds or 0)})
    db.commit()
    return {"created": True, "record_id": int(record.id), "case": _serialize_case(case)}


@router.get("/vehicles/assigned")
def assigned_service_vehicles(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    rows = (
        db.query(Vehicle)
        .join(VehicleServiceLink, Vehicle.id == VehicleServiceLink.vehicle_id)
        .filter(
            VehicleServiceLink.service_customer_id == int(current_user.id),
            VehicleServiceLink.status == "approved",
            Vehicle.status != "archived",
        )
        .order_by(Vehicle.created_at.desc(), Vehicle.id.desc())
        .all()
    )
    return {
        "items": [
            {
                "id": int(vehicle.id),
                "vehicle_name": vehicle_label(vehicle),
                "vehicle_plate": vehicle.plate,
                "vin_masked": f"{str(vehicle.vin or '')[:3]}***{str(vehicle.vin or '')[-4:]}" if vehicle.vin else None,
                "stk_valid_until": vehicle.stk_valid_until.isoformat() if vehicle.stk_valid_until else None,
            }
            for vehicle in rows
        ]
    }


@router.get("/vehicles/search")
def search_service_vehicles(
    q: str = Query(..., min_length=2, max_length=128),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    normalized, identifier_type = normalize_lookup_query(q)
    vehicle, owner, _normalized, _identifier_type, status = resolve_vehicle_for_lookup(db, current_user=current_user, query=normalized)
    approved = bool(vehicle and get_active_vehicle_service_link(db, service_customer_id=int(current_user.id), vehicle_id=int(vehicle.id)))
    return {
        "query": q,
        "identifier_type": identifier_type,
        "status": status,
        "items": [
            {
                "vehicle_id": int(vehicle.id),
                "vehicle_name": vehicle_label(vehicle),
                "plate_masked": masked_plate(vehicle.plate),
                "vin_masked": masked_vin(vehicle.vin),
                "can_open_detail": approved,
                "can_request_access": bool(vehicle and owner and not approved and status != "pending_request"),
            }
        ] if vehicle else [],
    }


@router.get("/vehicle-intake/{case_id}")
def get_intake_case(
    case_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    return {"case": _serialize_case(_case_or_404(db, current_user, case_id))}


@router.get("/vehicle-intake")
def list_intake_cases(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    rows = (
        db.query(ServiceIntake)
        .filter(ServiceIntake.service_id == int(current_user.id))
        .order_by(ServiceIntake.updated_at.desc(), ServiceIntake.id.desc())
        .all()
    )
    return {"items": [_serialize_case(row) for row in rows]}


@router.post("/inventory/import-delivery-note")
def import_delivery_note_stub(
    payload: dict[str, Any],
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    write_global_audit_log(
        db,
        entity_type="service_inventory",
        entity_id=None,
        action="delivery_note_import_requested",
        actor_type="service_staff",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=getattr(current_user, "tenant_id", None),
        metadata={"source_type": "delivery_note", "keys": sorted(payload.keys())[:20]},
    )
    db.commit()
    return {"imported": True, "status": "processed", "items": [], "message": "Dodací list byl auditně přijat pro skladový import."}
