from __future__ import annotations

import secrets
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from src.core.config import FRONTEND_BASE_URL

from .audit_log import write_global_audit_log
from .models import ServiceQuote, ServiceQuoteAccessLog, ServiceQuoteAccessToken


def build_public_quote_page_url(token: str) -> str:
    base = str(FRONTEND_BASE_URL or "").strip().rstrip("/")
    if not base:
        base = "http://127.0.0.1:8000"
    if base.endswith("/web/index.html"):
        return f"{base.rsplit('/', 1)[0]}/public-quote.html?token={token}"
    if base.endswith("/index.html"):
        return f"{base.rsplit('/', 1)[0]}/public-quote.html?token={token}"
    if base.endswith("/web"):
        return f"{base}/public-quote.html?token={token}"
    return f"{base}/web/public-quote.html?token={token}"


def get_active_quote_access_token(db: Session, *, quote_id: int) -> Optional[ServiceQuoteAccessToken]:
    token = (
        db.query(ServiceQuoteAccessToken)
        .filter(ServiceQuoteAccessToken.quote_id == int(quote_id))
        .order_by(ServiceQuoteAccessToken.issued_at.desc(), ServiceQuoteAccessToken.id.desc())
        .first()
    )
    if not token:
        return None
    if getattr(token, "revoked_at", None):
        return None
    expires_at = getattr(token, "expires_at", None)
    if expires_at and expires_at <= datetime.utcnow():
        return None
    return token


def ensure_quote_access_token(
    db: Session,
    *,
    quote: ServiceQuote,
    created_by_user_id: Optional[int],
) -> ServiceQuoteAccessToken:
    existing = get_active_quote_access_token(db, quote_id=int(quote.id))
    if existing:
        return existing

    token = ServiceQuoteAccessToken(
        tenant_id=int(quote.tenant_id or 1),
        quote_id=int(quote.id),
        created_by_user_id=int(created_by_user_id) if created_by_user_id else None,
        token=secrets.token_urlsafe(32),
        issued_at=datetime.utcnow(),
    )
    db.add(token)
    db.flush()
    _write_quote_access_log(db, quote=quote, access_token=token, action="token_created", request=None)
    write_global_audit_log(
        db,
        entity_type="service_quote",
        entity_id=int(quote.id),
        action="quote_access_token_created",
        actor_user_id=int(created_by_user_id) if created_by_user_id else None,
        actor_role="service" if created_by_user_id else "system",
        tenant_id=getattr(quote, "tenant_id", None),
        metadata={"quote_access_token_id": int(token.id)},
    )
    return token


def get_quote_access_token_or_404(db: Session, *, token_value: str) -> ServiceQuoteAccessToken:
    token = (
        db.query(ServiceQuoteAccessToken)
        .filter(ServiceQuoteAccessToken.token == str(token_value or "").strip())
        .order_by(ServiceQuoteAccessToken.issued_at.desc(), ServiceQuoteAccessToken.id.desc())
        .first()
    )
    if not token:
        raise HTTPException(status_code=404, detail="Veřejná nabídka nebyla nalezena.")
    if getattr(token, "revoked_at", None):
        raise HTTPException(status_code=410, detail="Veřejný odkaz nabídky byl zneplatněn.")
    expires_at = getattr(token, "expires_at", None)
    if expires_at and expires_at <= datetime.utcnow():
        raise HTTPException(status_code=410, detail="Platnost veřejné nabídky vypršela.")
    return token


def serialize_public_quote_payload(
    quote: ServiceQuote,
    *,
    vehicle_label: Optional[str],
    service_name: Optional[str],
    service_ico: Optional[str],
) -> dict[str, object]:
    items = []
    try:
        import json

        parsed = json.loads(str(getattr(quote, "items_json", None) or "[]"))
        if isinstance(parsed, list):
            items = [item for item in parsed if isinstance(item, dict)]
    except Exception:
        items = []
    return {
        "quote_id": int(quote.id),
        "vehicle_label": vehicle_label,
        "service_name": service_name,
        "service_ico": service_ico,
        "items": items,
        "labor_hours": getattr(quote, "labor_hours", None),
        "labor_rate": getattr(quote, "labor_rate", None),
        "total_price": getattr(quote, "total_price", None),
        "status": getattr(quote, "status", None),
        "approved_at": getattr(quote, "approved_at", None),
        "rejected_at": getattr(quote, "rejected_at", None),
        "created_at": getattr(quote, "created_at", None),
        "updated_at": getattr(quote, "updated_at", None),
    }


def _write_quote_access_log(
    db: Session,
    *,
    quote: ServiceQuote,
    access_token: Optional[ServiceQuoteAccessToken],
    action: str,
    request: Optional[Request],
) -> None:
    db.add(
        ServiceQuoteAccessLog(
            tenant_id=int(getattr(quote, "tenant_id", None) or 1),
            quote_id=int(quote.id),
            quote_access_token_id=int(access_token.id) if access_token else None,
            action=str(action),
            remote_addr=(
                str(getattr(request.client, "host", "") or "")[:128] or None
                if request is not None
                else None
            ),
            user_agent=(
                str(request.headers.get("user-agent") or "")[:4000] or None
                if request is not None
                else None
            ),
            created_at=datetime.utcnow(),
        )
    )


def log_public_quote_action(
    db: Session,
    *,
    quote: ServiceQuote,
    access_token: Optional[ServiceQuoteAccessToken],
    action: str,
    request: Optional[Request],
) -> None:
    _write_quote_access_log(db, quote=quote, access_token=access_token, action=action, request=request)
    write_global_audit_log(
        db,
        entity_type="service_quote",
        entity_id=int(quote.id),
        action=str(action),
        actor_user_id=None,
        actor_role="public",
        tenant_id=getattr(quote, "tenant_id", None),
        metadata={
            "quote_access_token_id": int(access_token.id) if access_token else None,
            "remote_addr": (
                str(getattr(request.client, "host", "") or "")[:128] or None if request is not None else None
            ),
            "user_agent": (
                str(request.headers.get("user-agent") or "")[:512] or None if request is not None else None
            ),
        },
    )
