from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.core.rbac import is_admin, is_service, normalize_role
from src.modules.vehicle_hub.models import Customer, Vehicle, VehicleDocument
from src.modules.vehicle_hub.ownership import user_owns_vehicle
from src.modules.vehicle_hub.reports.vehicle_report_verification import build_public_verify_url, mask_vin
from src.modules.vehicle_hub.service_access import service_can_read_vehicle

from .document_registry import DOCUMENT_REGISTRY, get_document_type
from .document_renderer import render_platform_document_pdf
from .document_schemas import DOCUMENT_STATUSES, DOCUMENT_TYPES, VISIBILITY_SCOPES, PlatformDocumentPayload
from .document_storage import (
    VEHICLE_DOCUMENTS_ROOT,
    dump_metadata,
    generate_verification_token,
    parse_metadata,
    safe_filename,
    sha256_bytes,
    write_document_bytes,
)
from .document_verify import build_verification_code, mask_plate, serialize_vehicle_document_verification


def _vehicle_label(vehicle: Vehicle) -> str:
    parts = [getattr(vehicle, "brand", None), getattr(vehicle, "model", None), getattr(vehicle, "nickname", None)]
    label = " ".join(str(p) for p in parts if p).strip()
    return label or str(getattr(vehicle, "plate", None) or f"Vozidlo #{vehicle.id}")


def _resolve_owner_id(db: Session, vehicle: Vehicle) -> Optional[int]:
    from src.modules.vehicle_hub.ownership import get_primary_vehicle_owner
    owner = get_primary_vehicle_owner(db, vehicle)
    return int(owner.id) if owner else None


def user_can_view_document(db: Session, *, current_user: Customer, doc: VehicleDocument) -> bool:
    from src.modules.vehicle_hub.routers_v1.auth import can_access_vehicle

    role_key = normalize_role(getattr(current_user, "role", None))
    if is_admin(role_key):
        return True

    if not can_access_vehicle(int(doc.vehicle_id), current_user, db):
        return False

    scope = str(doc.visibility_scope or "")
    if is_service(role_key):
        if int(doc.service_customer_id or 0) == int(current_user.id):
            return True
        if scope in {"owner_visible", "safe_after_claim", "public_verified"}:
            return service_can_read_vehicle(db, current_user, int(doc.vehicle_id))
        return False

    if scope == "service_private":
        return False
    if scope == "internal_only":
        return False
    if scope in {"owner_visible", "safe_after_claim", "public_verified"}:
        vehicle = db.query(Vehicle).filter(Vehicle.id == doc.vehicle_id).first()
        if vehicle and user_owns_vehicle(db, current_user, vehicle):
            return True
    return False


def _card_actions(doc: VehicleDocument) -> list[str]:
    actions = ["open", "download"]
    if doc.verification_token:
        actions.append("verify")
    if str(doc.visibility_scope) in {"owner_visible", "public_verified", "safe_after_claim"}:
        actions.append("share")
    return actions


def serialize_document_card(doc: VehicleDocument, *, vehicle: Vehicle | None = None) -> dict[str, Any]:
    type_def = DOCUMENT_REGISTRY.get(str(doc.document_type))
    label = type_def.label if type_def else str(doc.document_type)
    metadata = parse_metadata(doc.metadata_json)
    vlabel = _vehicle_label(vehicle) if vehicle else metadata.get("vehicle_label") or "Vozidlo"
    service_name = metadata.get("service_display") or "Servis"
    base = f"/api/v1/vehicles/{int(doc.vehicle_id)}/documents/{int(doc.id)}"
    return {
        "id": int(doc.id),
        "document_type": doc.document_type,
        "label": label,
        "status": doc.document_status,
        "title": doc.title,
        "document_number": doc.document_number,
        "created_at": doc.created_at.isoformat() + "Z" if doc.created_at else None,
        "vehicle_id": int(doc.vehicle_id),
        "vehicle_label": vlabel,
        "service_display": service_name,
        "thumbnail_url": f"{base}/thumbnail",
        "file_url": f"{base}/file",
        "verify_url": build_public_verify_url(doc.verification_token) if doc.verification_token else None,
        "actions": _card_actions(doc),
    }


def list_documents_for_vehicle(
    db: Session,
    *,
    vehicle_id: int,
    current_user: Customer,
    document_type: Optional[str] = None,
) -> list[VehicleDocument]:
    from src.modules.vehicle_hub.routers_v1.auth import can_access_vehicle

    if not can_access_vehicle(int(vehicle_id), current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k vozidlu.")

    query = (
        db.query(VehicleDocument)
        .filter(VehicleDocument.vehicle_id == int(vehicle_id))
        .order_by(VehicleDocument.created_at.desc(), VehicleDocument.id.desc())
    )
    if document_type:
        query = query.filter(VehicleDocument.document_type == str(document_type).strip().lower())

    rows = query.all()
    return [row for row in rows if user_can_view_document(db, current_user=current_user, doc=row)]


def get_document_for_user(
    db: Session,
    *,
    vehicle_id: int,
    document_id: int,
    current_user: Customer,
) -> VehicleDocument:
    doc = (
        db.query(VehicleDocument)
        .filter(
            VehicleDocument.id == int(document_id),
            VehicleDocument.vehicle_id == int(vehicle_id),
        )
        .first()
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Dokument nenalezen.")
    if not user_can_view_document(db, current_user=current_user, doc=doc):
        raise HTTPException(status_code=403, detail="Nemáte přístup k dokumentu.")
    return doc


def create_platform_document(
    db: Session,
    *,
    vehicle: Vehicle,
    current_user: Customer,
    document_type: str,
    document_status: str = "draft",
    title: Optional[str] = None,
    visibility_scope: Optional[str] = None,
    service_customer: Optional[Customer] = None,
) -> VehicleDocument:
    normalized_type = str(document_type or "").strip().lower()
    if normalized_type not in DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Neplatný typ dokumentu: {document_type}")

    normalized_status = str(document_status or "draft").strip().lower()
    if normalized_status not in DOCUMENT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Neplatný stav dokumentu: {document_status}")

    type_def = get_document_type(normalized_type)
    if normalized_status not in type_def.allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Stav {normalized_status} není povolen pro {normalized_type}.")

    scope = str(visibility_scope or type_def.default_visibility).strip().lower()
    if scope not in VISIBILITY_SCOPES:
        raise HTTPException(status_code=400, detail=f"Neplatný visibility scope: {visibility_scope}")

    service = service_customer
    role_key = normalize_role(getattr(current_user, "role", None))
    if service is None and is_service(role_key):
        service = current_user

    service_name = str(getattr(service, "name", None) or getattr(service, "email", None) or "Servis") if service else "Servis"
    service_ico = getattr(service, "ico", None) if service else None
    owner_id = _resolve_owner_id(db, vehicle)

    token = generate_verification_token() if type_def.requires_verification else None
    verification_code = build_verification_code(f"{vehicle.id}:{normalized_type}:{token}") if token else None
    verify_url = build_public_verify_url(token) if token else None

    doc_number = f"PLT-{datetime.utcnow().strftime('%Y%m%d')}-{vehicle.id}"
    payload = PlatformDocumentPayload(
        document_type=normalized_type,
        document_status=normalized_status,
        title=title or f"{type_def.label} — { _vehicle_label(vehicle) }",
        document_number=doc_number,
        vehicle_label=_vehicle_label(vehicle),
        vehicle_plate=getattr(vehicle, "plate", None),
        vehicle_vin_masked=mask_vin(getattr(vehicle, "vin", None)),
        service_name=service_name,
        service_ico=service_ico,
        verify_url=verify_url,
        verification_code=verification_code,
    )
    pdf_bytes = render_platform_document_pdf(payload)
    pdf_hash = sha256_bytes(pdf_bytes)
    filename = safe_filename(f"{doc_number}.pdf")
    storage_relative = f"tenants/{int(vehicle.tenant_id)}/vehicles/{int(vehicle.id)}/{normalized_type}/{filename}"
    pdf_path = VEHICLE_DOCUMENTS_ROOT / storage_relative
    write_document_bytes(pdf_path, pdf_bytes)

    now = datetime.utcnow()
    row = VehicleDocument(
        tenant_id=int(vehicle.tenant_id),
        vehicle_id=int(vehicle.id),
        document_type=normalized_type,
        document_status=normalized_status,
        title=payload.title,
        document_number=doc_number,
        source_type=type_def.source_type,
        source_id=None,
        service_customer_id=int(service.id) if service else None,
        owner_customer_id=owner_id,
        created_by_customer_id=int(current_user.id),
        visibility_scope=scope,
        verification_token=token,
        storage_path=storage_relative,
        thumbnail_path=None,
        mime_type="application/pdf",
        file_size=len(pdf_bytes),
        created_at=now,
        updated_at=now,
        metadata_json=dump_metadata({
            "hash_sha256": pdf_hash,
            "verification_code": verification_code,
            "vehicle_brand": getattr(vehicle, "brand", None),
            "vehicle_model": getattr(vehicle, "model", None),
            "vehicle_plate_masked": mask_plate(getattr(vehicle, "plate", None)),
            "vehicle_label": _vehicle_label(vehicle),
            "service_display": service_name,
        }),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def resolve_document_file_path(doc: VehicleDocument):
    from pathlib import Path

    relative = str(doc.storage_path or "").strip()
    if relative:
        return VEHICLE_DOCUMENTS_ROOT / relative
    metadata = parse_metadata(doc.metadata_json)
    rel = metadata.get("storage_relative")
    if rel:
        return VEHICLE_DOCUMENTS_ROOT / str(rel)
    return VEHICLE_DOCUMENTS_ROOT / f"tenants/{doc.tenant_id}/vehicles/{doc.vehicle_id}/{doc.document_type}/doc-{doc.id}.pdf"
