from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.rbac import is_service, normalize_role
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.documents.document_registry import DOCUMENT_REGISTRY
from src.modules.vehicle_hub.documents.document_service import (
    create_platform_document,
    get_document_for_user,
    list_documents_for_vehicle,
    resolve_document_file_path,
    serialize_document_card,
)
from src.modules.vehicle_hub.models import Customer, Vehicle
from src.modules.vehicle_hub.routers_v1.auth import can_access_vehicle, get_current_user

router = APIRouter(prefix="/vehicles", tags=["vehicle-documents-v1"])


class PlatformDocumentCreateIn(BaseModel):
    document_type: str = Field(..., min_length=2, max_length=64)
    document_status: str = Field(default="draft", max_length=32)
    title: Optional[str] = Field(default=None, max_length=255)
    visibility_scope: Optional[str] = Field(default=None, max_length=32)


class VehicleDocumentCardOut(BaseModel):
    id: int
    document_type: str
    label: str
    status: str
    title: str
    document_number: Optional[str] = None
    created_at: Optional[str] = None
    vehicle_id: int
    vehicle_label: str
    service_display: str
    thumbnail_url: str
    file_url: str
    verify_url: Optional[str] = None
    actions: list[str]


@router.get("/{vehicle_id}/documents", response_model=list[VehicleDocumentCardOut])
def list_vehicle_documents(
    vehicle_id: int,
    document_type: Optional[str] = Query(default=None),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id)).first()
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno.")
    rows = list_documents_for_vehicle(
        db,
        vehicle_id=int(vehicle_id),
        current_user=current_user,
        document_type=document_type,
    )
    return [serialize_document_card(row, vehicle=vehicle) for row in rows]


@router.get("/{vehicle_id}/documents/{document_id}", response_model=VehicleDocumentCardOut)
def get_vehicle_document(
    vehicle_id: int,
    document_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id)).first()
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno.")
    doc = get_document_for_user(
        db,
        vehicle_id=int(vehicle_id),
        document_id=int(document_id),
        current_user=current_user,
    )
    return serialize_document_card(doc, vehicle=vehicle)


@router.post("/{vehicle_id}/documents/platform", response_model=VehicleDocumentCardOut)
def create_vehicle_platform_document(
    vehicle_id: int,
    body: PlatformDocumentCreateIn,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    role_key = normalize_role(getattr(current_user, "role", None))
    if not is_service(role_key):
        raise HTTPException(status_code=403, detail="Platformní dokument může vytvořit pouze servis.")

    vehicle = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id)).first()
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno.")
    if not can_access_vehicle(int(vehicle_id), current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k vozidlu.")

    doc = create_platform_document(
        db,
        vehicle=vehicle,
        current_user=current_user,
        document_type=body.document_type,
        document_status=body.document_status,
        title=body.title,
        visibility_scope=body.visibility_scope,
    )
    return serialize_document_card(doc, vehicle=vehicle)


@router.get("/{vehicle_id}/documents/{document_id}/file")
def download_vehicle_document_file(
    vehicle_id: int,
    document_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = get_document_for_user(
        db,
        vehicle_id=int(vehicle_id),
        document_id=int(document_id),
        current_user=current_user,
    )
    path = resolve_document_file_path(doc)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Soubor dokumentu nenalezen.")
    content = path.read_bytes()
    filename = path.name
    return Response(
        content=content,
        media_type=doc.mime_type or "application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/{vehicle_id}/documents/{document_id}/thumbnail")
def vehicle_document_thumbnail(
    vehicle_id: int,
    document_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = get_document_for_user(
        db,
        vehicle_id=int(vehicle_id),
        document_id=int(document_id),
        current_user=current_user,
    )
    if doc.thumbnail_path:
        path = resolve_document_file_path(doc)
        thumb_root = path.parent / "thumbnails"
        thumb_path = thumb_root / f"{path.stem}.jpg"
        if thumb_path.exists():
            return Response(content=thumb_path.read_bytes(), media_type="image/jpeg")

    from src.modules.vehicle_hub.documents.document_registry import get_document_type

    type_def = get_document_type(str(doc.document_type))
    label = type_def.label
    status = str(doc.document_status or "draft")
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="240" height="320" viewBox="0 0 240 320">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#eef2ff"/><stop offset="100%" stop-color="#f8fafc"/>
  </linearGradient></defs>
  <rect width="240" height="320" rx="12" fill="url(#g)" stroke="#dbe5f0"/>
  <rect x="16" y="16" width="208" height="48" rx="8" fill="#ffffff" stroke="#dbe5f0"/>
  <text x="24" y="44" font-family="DejaVu Sans, Arial, sans-serif" font-size="12" fill="#64748b">{label}</text>
  <text x="24" y="62" font-family="DejaVu Sans, Arial, sans-serif" font-size="11" fill="#2563eb">{status.upper()}</text>
  <rect x="16" y="80" width="208" height="180" rx="8" fill="#ffffff" stroke="#dbe5f0"/>
  <text x="24" y="110" font-family="DejaVu Sans, Arial, sans-serif" font-size="14" fill="#0f172a">Dokument</text>
  <text x="24" y="132" font-family="DejaVu Sans, Arial, sans-serif" font-size="11" fill="#64748b">Platform preview</text>
  <rect x="24" y="150" width="192" height="8" rx="4" fill="#eef2ff"/>
  <rect x="24" y="168" width="160" height="8" rx="4" fill="#eef2ff"/>
  <rect x="24" y="186" width="176" height="8" rx="4" fill="#eef2ff"/>
</svg>"""
    return Response(content=svg.encode("utf-8"), media_type="image/svg+xml")


@router.get("/documents/registry")
def vehicle_documents_registry():
    return {
        key: {
            "label": item.label,
            "allowed_statuses": sorted(item.allowed_statuses),
            "default_visibility": item.default_visibility,
            "renderer_status": item.renderer_status,
        }
        for key, item in DOCUMENT_REGISTRY.items()
    }
