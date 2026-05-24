from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import VehicleReportDocument
from src.modules.vehicle_hub.reports.vehicle_report_verification import (
    VERIFY_STATUS_NOT_FOUND,
    normalize_verification_code,
    serialize_document_verification,
)
from src.server.security_tracking import log_security_event

router = APIRouter(prefix="/api/public/documents", tags=["public-documents"])


class VerifyByCodeRequest(BaseModel):
    verification_code: str = Field(..., min_length=4, max_length=32)


@router.get("/verify/{token}")
def verify_public_document(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    record = (
        db.query(VehicleReportDocument)
        .filter(
            VehicleReportDocument.public_token == str(token or "").strip(),
            VehicleReportDocument.verification_enabled.is_(True),
        )
        .first()
    )
    payload = serialize_document_verification(record)
    log_security_event(
        event_type="public_document_verify",
        request=request,
        user_email=None,
        customer_id=None,
        tenant_id=getattr(record, "tenant_id", None),
        endpoint=str(request.url.path),
        details={
            "lookup": "token",
            "public_token": str(token or "").strip(),
            "status": payload["status"],
            "document_id": payload["document_id"],
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
    record = (
        db.query(VehicleReportDocument)
        .filter(VehicleReportDocument.verification_code == normalized_code)
        .first()
    )
    payload = serialize_document_verification(record)
    if payload["status"] == VERIFY_STATUS_NOT_FOUND:
        payload["verification_code"] = normalized_code
    log_security_event(
        event_type="public_document_verify",
        request=request,
        user_email=None,
        customer_id=None,
        tenant_id=getattr(record, "tenant_id", None),
        endpoint=str(request.url.path) if request else "/api/public/documents/verify-by-code",
        details={
            "lookup": "verification_code",
            "verification_code": normalized_code,
            "status": payload["status"],
            "document_id": payload["document_id"],
        },
    )
    return payload
