from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.modules.vehicle_hub.audit_log import write_global_audit_log
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Vehicle, VehicleQrAccessLog, VehicleQrToken
from src.modules.vehicle_hub.vehicle_public_history import (
    is_vehicle_qr_signature_valid,
    serialize_public_history_payload,
)
from src.server.security_tracking import log_security_event

router = APIRouter(prefix="/api/public/vehicle-history", tags=["public-vehicle-history"])


def _log_vehicle_qr_access(
    db: Session,
    *,
    qr_token: VehicleQrToken,
    request: Request,
    access_status: str,
    signature_valid: bool,
) -> None:
    db.add(
        VehicleQrAccessLog(
            tenant_id=int(qr_token.tenant_id or 1),
            vehicle_id=int(qr_token.vehicle_id),
            qr_token_id=int(qr_token.id),
            access_path=str(request.url.path),
            access_status=access_status,
            public_mode=str(qr_token.public_mode or "basic"),
            access_signature_valid=bool(signature_valid),
            remote_addr=str(getattr(request.client, "host", "") or "")[:128] or None,
            user_agent=str(request.headers.get("user-agent") or "")[:4000] or None,
            created_at=datetime.utcnow(),
        )
    )
    write_global_audit_log(
        db,
        entity_type="vehicle_qr_token",
        entity_id=int(qr_token.id),
        action="public_vehicle_history_access",
        actor_user_id=None,
        actor_role="public",
        tenant_id=getattr(qr_token, "tenant_id", None),
        metadata={
            "vehicle_id": int(qr_token.vehicle_id),
            "access_status": access_status,
            "signature_valid": bool(signature_valid),
            "public_mode": str(qr_token.public_mode or "basic"),
        },
    )


@router.get("/{token}")
def get_public_vehicle_history(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    qr_token = (
        db.query(VehicleQrToken)
        .filter(VehicleQrToken.token == str(token or "").strip())
        .order_by(VehicleQrToken.issued_at.desc(), VehicleQrToken.id.desc())
        .first()
    )
    if not qr_token:
        log_security_event(
            event_type="public_vehicle_history_access",
            request=request,
            user_email=None,
            customer_id=None,
            tenant_id=None,
            endpoint=str(request.url.path),
            details={"status": "not_found"},
        )
        raise HTTPException(status_code=404, detail="Veřejná historie vozidla nebyla nalezena.")

    signature_valid = is_vehicle_qr_signature_valid(qr_token)
    if not signature_valid:
        _log_vehicle_qr_access(
            db,
            qr_token=qr_token,
            request=request,
            access_status="invalid_signature",
            signature_valid=False,
        )
        db.commit()
        raise HTTPException(status_code=409, detail="Veřejný QR token neprošel integritní kontrolou.")

    if not bool(getattr(qr_token, "active", False)) or getattr(qr_token, "revoked_at", None):
        _log_vehicle_qr_access(
            db,
            qr_token=qr_token,
            request=request,
            access_status="revoked",
            signature_valid=True,
        )
        db.commit()
        raise HTTPException(status_code=410, detail="Veřejný QR token byl zneplatněn.")

    vehicle = db.query(Vehicle).filter(Vehicle.id == int(qr_token.vehicle_id)).first()
    if not vehicle:
        _log_vehicle_qr_access(
            db,
            qr_token=qr_token,
            request=request,
            access_status="vehicle_missing",
            signature_valid=True,
        )
        db.commit()
        raise HTTPException(status_code=404, detail="Vozidlo pro veřejnou historii nebylo nalezeno.")

    qr_token.last_access_at = datetime.utcnow()
    _log_vehicle_qr_access(
        db,
        qr_token=qr_token,
        request=request,
        access_status="ok",
        signature_valid=True,
    )
    payload = serialize_public_history_payload(db, vehicle=vehicle, qr_token=qr_token)
    db.commit()

    log_security_event(
        event_type="public_vehicle_history_access",
        request=request,
        user_email=None,
        customer_id=None,
        tenant_id=getattr(qr_token, "tenant_id", None),
        endpoint=str(request.url.path),
        details={
            "status": "ok",
            "vehicle_id": int(qr_token.vehicle_id),
            "qr_token_id": int(qr_token.id),
            "public_mode": payload.get("public_mode"),
        },
    )
    return payload
