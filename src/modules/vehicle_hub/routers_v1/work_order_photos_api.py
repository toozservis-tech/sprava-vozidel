"""Work order photo documentation (VehiclePhotoAsset + runtime storage)."""

from __future__ import annotations

import base64
import binascii
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.config import DATA_DIR

from ..audit_log import write_global_audit_log
from ..database import get_db
from ..models import Customer, VehiclePhotoAsset, Vehicle as VehicleModel
from ..vehicle_photo_assets import (
    build_work_order_storage_key,
    jpeg_dimensions,
    resolve_storage_file,
    sha256_hex,
)
from .auth import get_current_user

WORK_ORDER_PHOTO_TYPES = {
    "intake",
    "damage",
    "work_progress",
    "part",
    "completion",
    "internal",
}

WORK_ORDER_PHOTO_TYPE_LABELS = {
    "intake": "Vstupní stav",
    "damage": "Poškození",
    "work_progress": "Průběh práce",
    "part": "Díl",
    "completion": "Výstupní stav",
    "internal": "Interní fotka",
}

VISIBILITY_SCOPES = {
    "service_private",
    "owner_visible",
    "safe_after_claim",
    "internal_only",
}

OWNER_SAFE_PHOTO_VISIBILITY = {"owner_visible", "safe_after_claim"}

MAX_WORK_ORDER_PHOTO_RAW_BYTES = 10 * 1024 * 1024
ALLOWED_MIME_PREFIXES = ("image/jpeg", "image/png", "image/webp")

VEHICLE_PHOTOS_DIR = DATA_DIR / "vehicle_photos"


class WorkOrderPhotoUploadRequest(BaseModel):
    photo_type: str = Field(..., min_length=1, max_length=64)
    visibility_scope: str = Field(default="service_private", max_length=32)
    file_name: str = Field(..., min_length=1, max_length=255)
    file_mime_type: str = Field(default="image/jpeg", max_length=128)
    file_content_base64: str = Field(..., min_length=20, max_length=40_000_000)


class WorkOrderPhotoVisibilityUpdateRequest(BaseModel):
    visibility_scope: str = Field(..., min_length=1, max_length=32)


def _decode_base64_payload(payload: str) -> bytes:
    raw = str(payload or "").strip()
    if not raw:
        return b""
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    raw = re.sub(r"\s+", "", raw)
    pad = (-len(raw)) % 4
    if pad:
        raw = raw + ("=" * pad)
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Soubor není validní base64.") from exc


def _normalize_photo_type(raw: str) -> str:
    value = str(raw or "").strip().lower()
    if value not in WORK_ORDER_PHOTO_TYPES:
        raise HTTPException(status_code=422, detail="Neplatný typ fotky zakázky.")
    return value


def _normalize_visibility_scope(*, photo_type: str, raw: Optional[str]) -> str:
    value = str(raw or "service_private").strip().lower()
    if value not in VISIBILITY_SCOPES:
        raise HTTPException(status_code=422, detail="Neplatný rozsah viditelnosti fotky.")
    if photo_type == "internal":
        return "internal_only"
    if value == "internal_only" and photo_type != "internal":
        raise HTTPException(
            status_code=422,
            detail="Viditelnost internal_only je povolena jen pro typ internal.",
        )
    return value


def _write_bytes_to_photos_dir(target_file: Path, content: bytes) -> None:
    try:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_bytes(content)
    except OSError as exc:
        errno = getattr(exc, "errno", None)
        if errno == 13 or isinstance(exc, PermissionError):
            raise HTTPException(
                status_code=503,
                detail="Server nemá oprávnění zapisovat fotky do úložiště.",
            ) from exc
        raise HTTPException(status_code=500, detail="Uložení fotky selhalo.") from exc


def _normalize_work_order_image(content: bytes) -> bytes:
    from .vehicles import _normalize_vehicle_photo

    return _normalize_vehicle_photo(content)


def _get_photo_or_404(
    db: Session,
    *,
    current_user: Customer,
    work_order_id: int,
    photo_id: int,
) -> tuple[object, VehiclePhotoAsset]:
    from . import service_dashboard as sd

    order = sd._get_work_order_or_404(db, current_user=current_user, work_order_id=work_order_id)
    row = (
        db.query(VehiclePhotoAsset)
        .filter(
            VehiclePhotoAsset.id == int(photo_id),
            VehiclePhotoAsset.work_order_id == int(order.id),
            VehiclePhotoAsset.service_customer_id == int(current_user.id),
            VehiclePhotoAsset.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        write_global_audit_log(
            db,
            entity_type="work_order_photo",
            entity_id=int(photo_id),
            action="work_order_photo_forbidden_access",
            actor_user_id=int(current_user.id),
            actor_role=getattr(current_user, "role", None),
            tenant_id=int(order.tenant_id),
            vehicle_id=int(order.vehicle_id),
            metadata={"work_order_id": int(order.id), "photo_id": int(photo_id)},
        )
        db.flush()
        raise HTTPException(status_code=404, detail="Fotka zakázky nebyla nalezena.")
    if int(row.vehicle_id) != int(order.vehicle_id):
        raise HTTPException(status_code=403, detail="Fotka nepatří k vozidlu zakázky.")
    return order, row


def _serialize_work_order_photo(
    *,
    row: VehiclePhotoAsset,
    work_order_id: int,
) -> dict[str, object]:
    return {
        "id": int(row.id),
        "work_order_id": int(work_order_id),
        "vehicle_id": int(row.vehicle_id),
        "photo_type": str(row.photo_kind or "other"),
        "photo_type_label": WORK_ORDER_PHOTO_TYPE_LABELS.get(str(row.photo_kind or ""), str(row.photo_kind or "")),
        "visibility_scope": str(row.visibility_scope or "service_private"),
        "filename": str(row.original_filename or ""),
        "mime_type": str(row.mime_type or "image/jpeg"),
        "file_size_bytes": int(row.file_size_bytes or 0),
        "width": row.width,
        "height": row.height,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "uploaded_by_customer_id": int(row.uploaded_by_customer_id) if row.uploaded_by_customer_id else None,
        "download_url": f"/api/service/work-orders/{int(work_order_id)}/photos/{int(row.id)}/file",
        "preview_url": f"/api/service/work-orders/{int(work_order_id)}/photos/{int(row.id)}/file",
    }


def list_work_order_photos_for_order(db: Session, *, work_order_id: int, service_customer_id: int) -> list[dict[str, object]]:
    rows = (
        db.query(VehiclePhotoAsset)
        .filter(
            VehiclePhotoAsset.work_order_id == int(work_order_id),
            VehiclePhotoAsset.service_customer_id == int(service_customer_id),
            VehiclePhotoAsset.deleted_at.is_(None),
        )
        .order_by(VehiclePhotoAsset.id.asc())
        .all()
    )
    return [_serialize_work_order_photo(row=row, work_order_id=work_order_id) for row in rows]


def filter_owner_safe_work_order_photos(rows: list[VehiclePhotoAsset]) -> list[dict[str, object]]:
    """Owner-facing projection: only explicitly safe visibility, never internal/private."""
    safe: list[dict[str, object]] = []
    for row in rows:
        scope = str(getattr(row, "visibility_scope", "") or "")
        if scope not in OWNER_SAFE_PHOTO_VISIBILITY:
            continue
        if str(getattr(row, "photo_kind", "") or "").lower() == "internal":
            continue
        safe.append(
            {
                "id": int(row.id),
                "photo_type": str(row.photo_kind or ""),
                "visibility_scope": scope,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return safe


def list_work_order_photos(
    work_order_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from . import service_dashboard as sd

    sd._require_service_workspace_role(current_user)
    sd._ensure_service_dashboard_schema(db)
    order = sd._get_work_order_or_404(db, current_user=current_user, work_order_id=work_order_id)
    items = list_work_order_photos_for_order(
        db,
        work_order_id=int(order.id),
        service_customer_id=int(current_user.id),
    )
    write_global_audit_log(
        db,
        entity_type="work_order_photo",
        entity_id=int(order.id),
        action="work_order_photo_viewed",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(order.tenant_id),
        vehicle_id=int(order.vehicle_id),
        metadata={"work_order_id": int(order.id), "count": len(items)},
    )
    db.commit()
    return {"items": items, "count": len(items)}


def upload_work_order_photo(
    work_order_id: int,
    payload: WorkOrderPhotoUploadRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from . import service_dashboard as sd

    sd._require_service_workspace_role(current_user)
    sd._ensure_service_dashboard_schema(db)
    order = sd._get_work_order_or_404(db, current_user=current_user, work_order_id=work_order_id)
    photo_type = _normalize_photo_type(payload.photo_type)
    visibility = _normalize_visibility_scope(photo_type=photo_type, raw=payload.visibility_scope)
    mime = str(payload.file_mime_type or "").strip().lower()
    if not any(mime.startswith(prefix) for prefix in ALLOWED_MIME_PREFIXES):
        raise HTTPException(status_code=415, detail="Povolené formáty: JPEG, PNG, WebP.")
    raw = _decode_base64_payload(payload.file_content_base64)
    if not raw:
        raise HTTPException(status_code=422, detail="Nahraná fotka je prázdná.")
    if len(raw) > MAX_WORK_ORDER_PHOTO_RAW_BYTES:
        raise HTTPException(status_code=413, detail="Fotka je příliš velká (max 10 MB).")
    normalized = _normalize_work_order_image(raw)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(order.vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo zakázky nebylo nalezeno.")
    tenant_id = int(order.tenant_id)
    filename = f"wo_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(6)}.jpg"
    storage_key = build_work_order_storage_key(
        tenant_id=tenant_id,
        vehicle_id=int(vehicle.id),
        work_order_id=int(order.id),
        filename=filename,
    )
    target_file = VEHICLE_PHOTOS_DIR / storage_key
    base = VEHICLE_PHOTOS_DIR.resolve()
    resolved = target_file.resolve()
    if not str(resolved).startswith(str(base)):
        raise HTTPException(status_code=500, detail="Neplatná cesta úložiště.")
    _write_bytes_to_photos_dir(target_file, normalized)
    digest = sha256_hex(normalized)
    w_px, h_px = jpeg_dimensions(normalized)
    owner = None
    if order.owner_customer_id is not None:
        owner = db.query(Customer).filter(Customer.id == int(order.owner_customer_id)).first()
    row = VehiclePhotoAsset(
        tenant_id=tenant_id,
        vehicle_id=int(vehicle.id),
        work_order_id=int(order.id),
        service_customer_id=int(current_user.id),
        owner_customer_id=int(owner.id) if owner else None,
        role="work_order",
        photo_kind=photo_type,
        visibility_scope=visibility,
        vin=vehicle.vin,
        capture_date=datetime.utcnow(),
        storage_key=storage_key,
        storage_path_original=None,
        storage_path_preview=None,
        original_filename=str(payload.file_name or filename)[:255],
        mime_type="image/jpeg",
        file_size_bytes=len(normalized),
        width=w_px,
        height=h_px,
        sha256_hex=digest,
        uploaded_by_customer_id=int(current_user.id),
        sort_order=0,
    )
    db.add(row)
    db.flush()
    write_global_audit_log(
        db,
        entity_type="work_order_photo",
        entity_id=int(row.id),
        action="work_order_photo_uploaded",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=tenant_id,
        vehicle_id=int(vehicle.id),
        metadata={
            "work_order_id": int(order.id),
            "photo_type": photo_type,
            "visibility_scope": visibility,
            "file_size_bytes": len(normalized),
        },
    )
    sd._write_work_order_audit(
        db,
        work_order=order,
        action="photo_uploaded",
        actor=current_user,
        previous_snapshot=sd._work_order_snapshot(order),
        new_snapshot=sd._work_order_snapshot(order),
    )
    db.commit()
    db.refresh(row)
    return _serialize_work_order_photo(row=row, work_order_id=int(order.id))


def download_work_order_photo(
    work_order_id: int,
    photo_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from . import service_dashboard as sd

    sd._require_service_workspace_role(current_user)
    order, row = _get_photo_or_404(
        db,
        current_user=current_user,
        work_order_id=work_order_id,
        photo_id=photo_id,
    )
    photo_file = resolve_storage_file(VEHICLE_PHOTOS_DIR, row.storage_key)
    if not photo_file:
        raise HTTPException(status_code=404, detail="Soubor fotky nebyl nalezen.")
    write_global_audit_log(
        db,
        entity_type="work_order_photo",
        entity_id=int(row.id),
        action="work_order_photo_viewed",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(order.tenant_id),
        vehicle_id=int(order.vehicle_id),
        metadata={"work_order_id": int(order.id), "photo_id": int(row.id)},
    )
    db.commit()
    return FileResponse(
        path=str(photo_file),
        media_type=str(row.mime_type or "image/jpeg"),
        filename=str(row.original_filename or "photo.jpg"),
    )


def update_work_order_photo_visibility(
    work_order_id: int,
    photo_id: int,
    payload: WorkOrderPhotoVisibilityUpdateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from . import service_dashboard as sd

    sd._require_service_workspace_role(current_user)
    order, row = _get_photo_or_404(
        db,
        current_user=current_user,
        work_order_id=work_order_id,
        photo_id=photo_id,
    )
    photo_type = str(row.photo_kind or "").lower()
    previous = str(row.visibility_scope or "service_private")
    new_scope = _normalize_visibility_scope(photo_type=photo_type, raw=payload.visibility_scope)
    row.visibility_scope = new_scope
    db.flush()
    write_global_audit_log(
        db,
        entity_type="work_order_photo",
        entity_id=int(row.id),
        action="work_order_photo_visibility_changed",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(order.tenant_id),
        vehicle_id=int(order.vehicle_id),
        metadata={
            "work_order_id": int(order.id),
            "photo_id": int(row.id),
            "before": previous,
            "after": new_scope,
        },
    )
    db.commit()
    return _serialize_work_order_photo(row=row, work_order_id=int(order.id))


def delete_work_order_photo(
    work_order_id: int,
    photo_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from . import service_dashboard as sd

    sd._require_service_workspace_role(current_user)
    order, row = _get_photo_or_404(
        db,
        current_user=current_user,
        work_order_id=work_order_id,
        photo_id=photo_id,
    )
    row.deleted_at = datetime.utcnow()
    db.flush()
    write_global_audit_log(
        db,
        entity_type="work_order_photo",
        entity_id=int(row.id),
        action="work_order_photo_deleted",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(order.tenant_id),
        vehicle_id=int(order.vehicle_id),
        metadata={"work_order_id": int(order.id), "photo_id": int(row.id)},
    )
    sd._write_work_order_audit(
        db,
        work_order=order,
        action="photo_deleted",
        actor=current_user,
        previous_snapshot=sd._work_order_snapshot(order),
        new_snapshot=sd._work_order_snapshot(order),
    )
    db.commit()
    return {"deleted": True, "photo_id": int(row.id)}


def register_work_order_photo_routes(router: APIRouter) -> None:
    router.get("/work-orders/{work_order_id}/photos")(list_work_order_photos)
    router.post("/work-orders/{work_order_id}/photos")(upload_work_order_photo)
    router.get("/work-orders/{work_order_id}/photos/{photo_id}/file")(download_work_order_photo)
    router.put("/work-orders/{work_order_id}/photos/{photo_id}/visibility")(update_work_order_photo_visibility)
    router.delete("/work-orders/{work_order_id}/photos/{photo_id}")(delete_work_order_photo)
