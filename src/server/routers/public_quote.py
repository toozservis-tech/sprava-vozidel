from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, ServiceQuote, ServiceQuoteAccessToken, ServiceWorkOrder, Vehicle
from src.modules.vehicle_hub.quote_public_access import (
    get_quote_access_token_or_404,
    log_public_quote_action,
    serialize_public_quote_payload,
)
from src.modules.vehicle_hub.routers_v1.service_dashboard import (
    _quote_snapshot,
    _sync_work_order_on_quote_rejected,
    _work_order_snapshot,
    _write_quote_audit,
    _write_work_order_audit,
)
from src.server.security_tracking import log_security_event

router = APIRouter(prefix="/api/public/quote", tags=["public-quote"])


def _public_actor(tenant_id: int | None) -> SimpleNamespace:
    return SimpleNamespace(id=None, role="public", tenant_id=tenant_id)


def _load_public_quote(
    db: Session,
    *,
    token_value: str,
) -> tuple[ServiceQuoteAccessToken, ServiceQuote, Vehicle | None, Customer | None]:
    access_token = get_quote_access_token_or_404(db, token_value=token_value)
    quote = db.query(ServiceQuote).filter(ServiceQuote.id == int(access_token.quote_id)).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Nabídka k veřejnému odkazu nebyla nalezena.")
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(quote.vehicle_id)).first()
    service_customer = db.query(Customer).filter(Customer.id == int(quote.service_id)).first()
    return access_token, quote, vehicle, service_customer


def _public_payload(quote: ServiceQuote, vehicle: Vehicle | None, service_customer: Customer | None) -> dict[str, object]:
    vehicle_label = (
        " ".join(part for part in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None)] if part).strip()
        if vehicle
        else None
    )
    vehicle_label = vehicle_label or getattr(vehicle, "nickname", None) if vehicle else None
    payload = serialize_public_quote_payload(
        quote,
        vehicle_label=vehicle_label,
        service_name=(getattr(service_customer, "name", None) or getattr(service_customer, "email", None)),
        service_ico=getattr(service_customer, "ico", None),
    )
    payload["status_label"] = {
        "draft": "Koncept",
        "sent": "Odesláno",
        "approved": "Schváleno",
        "rejected": "Odmítnuto",
    }.get(str(quote.status or "").lower(), str(quote.status or "draft"))
    payload["decision_available"] = str(quote.status or "").lower() in {"draft", "sent"}
    return payload


@router.get("/{token}")
def get_public_quote(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        access_token, quote, vehicle, service_customer = _load_public_quote(db, token_value=token)
    except HTTPException as exc:
        log_security_event(
            event_type="public_quote_access",
            request=request,
            user_email=None,
            customer_id=None,
            tenant_id=None,
            endpoint=str(request.url.path),
            details={"status": "error", "detail": exc.detail},
        )
        raise

    access_token.last_access_at = datetime.utcnow()
    log_public_quote_action(db, quote=quote, access_token=access_token, action="public_quote_opened", request=request)
    payload = _public_payload(quote, vehicle, service_customer)
    db.commit()
    return payload


@router.post("/{token}/approve")
def approve_public_quote(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    access_token, quote, _vehicle, _service_customer = _load_public_quote(db, token_value=token)
    if str(quote.status or "").lower() == "approved":
        raise HTTPException(status_code=409, detail="Nabídka už byla schválena.")
    if str(quote.status or "").lower() == "rejected":
        raise HTTPException(status_code=409, detail="Nabídka už byla odmítnuta.")

    actor = _public_actor(getattr(quote, "tenant_id", None))
    previous_snapshot = _quote_snapshot(quote)
    quote.status = "approved"
    quote.approved_at = datetime.utcnow()
    quote.rejected_at = None
    access_token.last_access_at = datetime.utcnow()
    db.flush()
    _write_quote_audit(
        db,
        quote=quote,
        action="public_quote_approved",
        actor=actor,
        previous_snapshot=previous_snapshot,
        new_snapshot=_quote_snapshot(quote),
    )
    log_public_quote_action(db, quote=quote, access_token=access_token, action="public_quote_approved", request=request)

    if quote.work_order_id:
        work_order = db.query(ServiceWorkOrder).filter(ServiceWorkOrder.id == int(quote.work_order_id)).first()
        if work_order and str(work_order.status or "").lower() != "approved":
            previous_work_order = _work_order_snapshot(work_order)
            work_order.status = "approved"
            if work_order.approved_at is None:
                work_order.approved_at = datetime.utcnow()
            db.flush()
            _write_work_order_audit(
                db,
                work_order=work_order,
                action="public_quote_approved",
                actor=actor,
                previous_snapshot=previous_work_order,
                new_snapshot=_work_order_snapshot(work_order),
            )

    db.commit()
    return {
        "status": "approved",
        "approved_at": quote.approved_at,
        "message": "Nabídka byla schválena.",
    }


@router.post("/{token}/reject")
def reject_public_quote(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    access_token, quote, _vehicle, _service_customer = _load_public_quote(db, token_value=token)
    if str(quote.status or "").lower() == "rejected":
        raise HTTPException(status_code=409, detail="Nabídka už byla odmítnuta.")
    if str(quote.status or "").lower() == "approved":
        raise HTTPException(status_code=409, detail="Nabídka už byla schválena.")

    actor = _public_actor(getattr(quote, "tenant_id", None))
    previous_snapshot = _quote_snapshot(quote)
    quote.status = "rejected"
    quote.rejected_at = datetime.utcnow()
    quote.approved_at = None
    access_token.last_access_at = datetime.utcnow()
    db.flush()
    _write_quote_audit(
        db,
        quote=quote,
        action="public_quote_rejected",
        actor=actor,
        previous_snapshot=previous_snapshot,
        new_snapshot=_quote_snapshot(quote),
    )
    log_public_quote_action(db, quote=quote, access_token=access_token, action="public_quote_rejected", request=request)

    _sync_work_order_on_quote_rejected(
        db,
        quote=quote,
        actor=actor,
        audit_action="public_quote_rejected_work_order_sync",
    )

    db.commit()
    return {
        "status": "rejected",
        "rejected_at": quote.rejected_at,
        "message": "Nabídka byla odmítnuta.",
    }
