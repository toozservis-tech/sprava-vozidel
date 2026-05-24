from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import hashlib
import json
import os
import secrets
from typing import Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from src.core.rbac import normalize_role
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle, VehicleReportDocument

from .vehicle_report_models import VehicleServiceReportPayload

VERIFY_STATUS_VALID = "valid"
VERIFY_STATUS_SUPERSEDED = "superseded"
VERIFY_STATUS_REVOKED = "revoked"
VERIFY_STATUS_NOT_FOUND = "not_found"
VERIFY_BASE_URL = os.getenv("PUBLIC_VERIFY_BASE_URL", "https://hub.toozservis.cz/verify").rstrip("/")


def build_public_verify_url(public_token: str) -> str:
    return f"{VERIFY_BASE_URL}/{public_token}"


def mask_vin(vin: Optional[str]) -> Optional[str]:
    clean = str(vin or "").strip().upper()
    if not clean:
        return None
    if len(clean) <= 8:
        return clean[:2] + ("*" * max(len(clean) - 4, 1)) + clean[-2:]
    return clean[:3] + ("*" * (len(clean) - 7)) + clean[-4:]


def normalize_verification_code(raw_code: str | None) -> str:
    clean = "".join(ch for ch in str(raw_code or "").upper() if ch.isalnum())
    if len(clean) <= 4:
        return clean
    chunks = [clean[idx:idx + 4] for idx in range(0, min(len(clean), 12), 4)]
    return "-".join(chunk for chunk in chunks if chunk)


def _hash_json(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _build_document_id() -> str:
    return f"TSV-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3).upper()}"


def _build_verification_code(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest().upper()[:12]
    return normalize_verification_code(digest)


def _resolve_issuer_name(db: Session, vehicle: Vehicle, current_user: Customer) -> str:
    tenant = db.query(Tenant).filter(Tenant.id == vehicle.tenant_id).first()
    tenant_name = str(getattr(tenant, "name", "") or "").strip()
    if tenant_name:
        return tenant_name
    current_name = str(getattr(current_user, "name", "") or "").strip()
    if current_name:
        return current_name
    return "Správa vozidel"


def _resolve_finalized_by(current_user: Customer) -> str:
    name = str(getattr(current_user, "name", "") or "").strip()
    role = normalize_role(getattr(current_user, "role", None))
    if name:
        return f"{name} ({role})"
    email = str(getattr(current_user, "email", "") or "").strip().lower()
    if email:
        return f"{email} ({role})"
    return role or "system"


def build_payload_hash(payload: VehicleServiceReportPayload) -> str:
    data = payload.to_dict()
    data["verification_qr_payload"] = None
    data["new_owner_claim_qr_payload"] = None
    document = data.get("document") or {}
    for key, fallback in [
        ("generated_at", ""),
        ("document_id", ""),
        ("verification_code", ""),
        ("fingerprint", ""),
        ("public_token", ""),
        ("verification_url", ""),
        ("revision", 0),
        ("verification_enabled", False),
    ]:
        document[key] = fallback
    return _hash_json(data)


def _build_document_hash(
    payload: VehicleServiceReportPayload,
    *,
    document_id: str,
    verification_code: str,
    public_token: str,
    finalized_at_iso: str,
    revision: int,
) -> str:
    data = payload.to_dict()
    data["verification_qr_payload"] = None
    data["new_owner_claim_qr_payload"] = None
    document = data.get("document") or {}
    document["generated_at"] = finalized_at_iso
    document["document_id"] = document_id
    document["verification_code"] = verification_code
    document["fingerprint"] = ""
    document["public_token"] = public_token
    document["verification_url"] = build_public_verify_url(public_token)
    document["revision"] = revision
    document["verification_enabled"] = True
    return _hash_json(data)


def _apply_document_to_payload(
    payload: VehicleServiceReportPayload,
    row: VehicleReportDocument,
) -> VehicleServiceReportPayload:
    verification_url = build_public_verify_url(row.public_token) if row.public_token and row.verification_enabled else None
    payload.document = replace(
        payload.document,
        generated_at=row.finalized_at.replace(microsecond=0).isoformat() + "Z",
        document_id=row.document_id,
        verification_code=row.verification_code,
        fingerprint=row.hash_sha256,
        issued_by=row.issued_service_name or payload.document.issued_by,
        public_token=row.public_token,
        verification_url=verification_url,
        verification_enabled=bool(row.verification_enabled and row.public_token),
        revision=int(row.version or 1),
    )
    payload.verification_qr_payload = verification_url
    return payload


def finalize_vehicle_report_document(
    *,
    db: Session,
    vehicle: Vehicle,
    current_user: Customer,
    payload: VehicleServiceReportPayload,
) -> tuple[VehicleServiceReportPayload, VehicleReportDocument]:
    issued_by = _resolve_issuer_name(db, vehicle, current_user)
    payload.document = replace(payload.document, issued_by=issued_by)
    payload_hash = build_payload_hash(payload)

    existing = (
        db.query(VehicleReportDocument)
        .filter(
            VehicleReportDocument.tenant_id == vehicle.tenant_id,
            VehicleReportDocument.vehicle_id == vehicle.id,
            VehicleReportDocument.export_mode == payload.document.export_mode,
            VehicleReportDocument.payload_hash_sha256 == payload_hash,
            VehicleReportDocument.verification_enabled.is_(True),
            VehicleReportDocument.status == VERIFY_STATUS_VALID,
        )
        .order_by(desc(VehicleReportDocument.finalized_at), desc(VehicleReportDocument.id))
        .first()
    )
    if existing:
        return _apply_document_to_payload(payload, existing), existing

    finalized_at = datetime.utcnow().replace(microsecond=0)
    document_id = _build_document_id()
    public_token = secrets.token_urlsafe(24).rstrip("=")
    verification_code = _build_verification_code(f"{document_id}:{public_token}:{payload_hash}")

    latest_version = (
        db.query(func.max(VehicleReportDocument.version))
        .filter(
            VehicleReportDocument.tenant_id == vehicle.tenant_id,
            VehicleReportDocument.vehicle_id == vehicle.id,
            VehicleReportDocument.export_mode == payload.document.export_mode,
        )
        .scalar()
    )
    next_version = int(latest_version or 0) + 1
    finalized_at_iso = finalized_at.isoformat() + "Z"
    document_hash = _build_document_hash(
        payload,
        document_id=document_id,
        verification_code=verification_code,
        public_token=public_token,
        finalized_at_iso=finalized_at_iso,
        revision=next_version,
    )

    previous_valid_rows = (
        db.query(VehicleReportDocument)
        .filter(
            VehicleReportDocument.tenant_id == vehicle.tenant_id,
            VehicleReportDocument.vehicle_id == vehicle.id,
            VehicleReportDocument.export_mode == payload.document.export_mode,
            VehicleReportDocument.status == VERIFY_STATUS_VALID,
        )
        .all()
    )
    for previous in previous_valid_rows:
        previous.status = VERIFY_STATUS_SUPERSEDED
        previous.replaced_by_document_id = document_id

    row = VehicleReportDocument(
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        generated_by_user_id=getattr(current_user, "id", None),
        document_type=payload.document.type,
        export_mode=payload.document.export_mode,
        document_id=document_id,
        public_token=public_token,
        verification_code=verification_code,
        hash_sha256=document_hash,
        payload_hash_sha256=payload_hash,
        verification_enabled=True,
        status=VERIFY_STATUS_VALID,
        version=next_version,
        schema_version=payload.document.version,
        finalized_at=finalized_at,
        finalized_by=_resolve_finalized_by(current_user),
        issued_service_name=issued_by,
        vehicle_brand=payload.vehicle.brand,
        vehicle_model=payload.vehicle.model,
        vehicle_vin_masked=mask_vin(payload.vehicle.vin),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _apply_document_to_payload(payload, row), row


def serialize_document_verification(row: VehicleReportDocument | None) -> dict:
    if row is None:
        return {
            "status": VERIFY_STATUS_NOT_FOUND,
            "document_type": None,
            "document_id": None,
            "issued_at": None,
            "issued_service_name": None,
            "vehicle_brand": None,
            "vehicle_model": None,
            "vehicle_vin_masked": None,
            "version": None,
            "schema_version": None,
            "is_current_version": False,
            "verification_code": None,
            "verification_enabled": False,
        }

    status = str(row.status or VERIFY_STATUS_VALID)
    return {
        "status": status,
        "document_type": row.document_type,
        "document_id": row.document_id,
        "issued_at": row.finalized_at.replace(microsecond=0).isoformat() + "Z" if row.finalized_at else None,
        "issued_service_name": row.issued_service_name,
        "vehicle_brand": row.vehicle_brand,
        "vehicle_model": row.vehicle_model,
        "vehicle_vin_masked": row.vehicle_vin_masked,
        "version": row.version,
        "schema_version": row.schema_version,
        "is_current_version": status == VERIFY_STATUS_VALID,
        "verification_code": row.verification_code,
        "verification_enabled": bool(row.verification_enabled and row.public_token),
    }
