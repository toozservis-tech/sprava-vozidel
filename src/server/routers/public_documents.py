from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.documents.document_verify import serialize_vehicle_document_verification
from src.modules.vehicle_hub.models import VehicleDocument, VehicleReportDocument
from src.modules.vehicle_hub.reports.vehicle_report_verification import (
    VERIFY_STATUS_NOT_FOUND,
    normalize_verification_code,
    serialize_document_verification,
)
from src.server.security_tracking import log_security_event

router = APIRouter(prefix="/api/public/documents", tags=["public-documents"])


class VerifyByCodeRequest(BaseModel):
    verification_code: str = Field(..., min_length=4, max_length=32)


def _lookup_report_by_token(db: Session, token: str) -> VehicleReportDocument | None:
    return (
        db.query(VehicleReportDocument)
        .filter(
            VehicleReportDocument.public_token == str(token or "").strip(),
            VehicleReportDocument.verification_enabled.is_(True),
        )
        .first()
    )


def _lookup_vehicle_document_by_token(db: Session, token: str) -> VehicleDocument | None:
    return (
        db.query(VehicleDocument)
        .filter(VehicleDocument.verification_token == str(token or "").strip())
        .first()
    )


def _merge_verify_payload(*, legacy: dict | None, platform: dict | None) -> dict:
    if platform and platform.get("document_id"):
        return platform
    if legacy and legacy.get("document_id"):
        valid = str(legacy.get("status")) == "valid"
        return {
            "valid": valid,
            "status": legacy.get("status"),
            "document_type": legacy.get("document_type"),
            "document_status": "completed" if valid else legacy.get("status"),
            "document_id": legacy.get("document_id"),
            "vehicle_label": " ".join(
                p for p in [legacy.get("vehicle_brand"), legacy.get("vehicle_model")] if p
            ) or None,
            "vehicle_brand": legacy.get("vehicle_brand"),
            "vehicle_model": legacy.get("vehicle_model"),
            "vehicle_vin_masked": legacy.get("vehicle_vin_masked"),
            "created_at": legacy.get("issued_at"),
            "verification_url": None,
            "checksum": None,
            "version": legacy.get("version"),
            "schema_version": legacy.get("schema_version"),
            "is_current_version": legacy.get("is_current_version"),
            "verification_code": legacy.get("verification_code"),
            "verification_enabled": legacy.get("verification_enabled"),
            "issued_service_name": legacy.get("issued_service_name"),
        }
    return serialize_vehicle_document_verification(None)


@router.get("/verify/{token}")
def verify_public_document(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    report = _lookup_report_by_token(db, token)
    legacy_payload = serialize_document_verification(report)
    platform_doc = None if report else _lookup_vehicle_document_by_token(db, token)
    platform_payload = serialize_vehicle_document_verification(platform_doc)
    payload = _merge_verify_payload(legacy=legacy_payload, platform=platform_payload)

    log_security_event(
        event_type="public_document_verify",
        request=request,
        user_email=None,
        customer_id=None,
        tenant_id=getattr(report, "tenant_id", None) or getattr(platform_doc, "tenant_id", None),
        endpoint=str(request.url.path),
        details={
            "lookup": "token",
            "public_token": str(token or "").strip(),
            "status": payload.get("status"),
            "document_id": payload.get("document_id"),
            "source": "vehicle_report" if report else ("vehicle_document" if platform_doc else "none"),
        },
    )
    return payload


@router.post("/verify-by-code")
def verify_public_document_by_code(
    body: VerifyByCodeRequest = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
):
    normalized_code = normalize_verification_code(body.verification_code)
    report = (
        db.query(VehicleReportDocument)
        .filter(VehicleReportDocument.verification_code == normalized_code)
        .first()
    )
    legacy_payload = serialize_document_verification(report)
    platform_doc = None
    if not report:
        import json
        candidates = db.query(VehicleDocument).filter(VehicleDocument.metadata_json.isnot(None)).all()
        for row in candidates:
            try:
                meta = json.loads(row.metadata_json or "{}")
            except json.JSONDecodeError:
                continue
            if normalize_verification_code(meta.get("verification_code")) == normalized_code:
                platform_doc = row
                break
    platform_payload = serialize_vehicle_document_verification(platform_doc)
    payload = _merge_verify_payload(legacy=legacy_payload, platform=platform_payload)
    if payload.get("status") == VERIFY_STATUS_NOT_FOUND:
        payload["verification_code"] = normalized_code
    log_security_event(
        event_type="public_document_verify",
        request=request,
        user_email=None,
        customer_id=None,
        tenant_id=getattr(report, "tenant_id", None) or getattr(platform_doc, "tenant_id", None),
        endpoint=str(request.url.path) if request else "/api/public/documents/verify-by-code",
        details={
            "lookup": "verification_code",
            "verification_code": normalized_code,
            "status": payload.get("status"),
            "document_id": payload.get("document_id"),
        },
    )
    return payload
