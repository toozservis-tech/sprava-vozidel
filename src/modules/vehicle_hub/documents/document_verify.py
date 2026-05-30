from __future__ import annotations

from typing import Optional

from src.modules.vehicle_hub.models import VehicleDocument
from src.modules.vehicle_hub.reports.vehicle_report_verification import (
    VERIFY_STATUS_NOT_FOUND,
    build_public_verify_url,
    mask_vin,
    normalize_verification_code,
)


def serialize_vehicle_document_verification(row: VehicleDocument | None) -> dict:
    if row is None:
        return {
            "valid": False,
            "status": VERIFY_STATUS_NOT_FOUND,
            "document_type": None,
            "document_status": None,
            "document_id": None,
            "vehicle_label": None,
            "created_at": None,
            "verification_url": None,
            "checksum": None,
        }

    metadata = {}
    if row.metadata_json:
        try:
            import json
            metadata = json.loads(row.metadata_json)
        except json.JSONDecodeError:
            metadata = {}

    vehicle_label_parts = []
    brand = metadata.get("vehicle_brand")
    model = metadata.get("vehicle_model")
    plate = metadata.get("vehicle_plate_masked") or metadata.get("vehicle_plate")
    if brand or model:
        vehicle_label_parts.append(" ".join(p for p in [brand, model] if p))
    if plate:
        vehicle_label_parts.append(str(plate))
    vehicle_label = " · ".join(vehicle_label_parts) if vehicle_label_parts else "Vozidlo"

    verify_url = build_public_verify_url(row.verification_token) if row.verification_token else None
    status = str(row.document_status or "completed")
    valid = status in {"completed", "approved", "archived"} and row.archived_at is None

    return {
        "valid": valid,
        "status": "valid" if valid else status,
        "document_type": row.document_type,
        "document_status": row.document_status,
        "document_id": int(row.id),
        "vehicle_label": vehicle_label,
        "created_at": row.created_at.replace(microsecond=0).isoformat() + "Z" if row.created_at else None,
        "verification_url": verify_url,
        "checksum": metadata.get("hash_sha256"),
    }


def build_verification_code(seed: str) -> str:
    import hashlib
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest().upper()[:12]
    return normalize_verification_code(digest)


def mask_plate(plate: Optional[str]) -> Optional[str]:
    clean = str(plate or "").strip().upper()
    if not clean:
        return None
    if len(clean) <= 4:
        return clean[:1] + "***"
    return clean[:2] + "***" + clean[-2:]
