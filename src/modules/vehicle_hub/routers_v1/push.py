"""Push Notifications API v1.0."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.branding import APP_DISPLAY_NAME
from ..database import get_db
from ..models import Customer, PushSubscription
from ..push_notifications import push_status, send_push_to_customer
from ..schema_management import assert_module_ready
from .auth import get_current_user

router = APIRouter(prefix="/push", tags=["push-v1"])


class PushSubscriptionKeysIn(BaseModel):
    p256dh: str = Field(..., min_length=16, max_length=4096)
    auth: str = Field(..., min_length=8, max_length=1024)


class PushSubscribeIn(BaseModel):
    endpoint: str = Field(..., min_length=16, max_length=4096)
    keys: PushSubscriptionKeysIn


class PushUnsubscribeIn(BaseModel):
    endpoint: Optional[str] = Field(default=None, max_length=4096)


class PushTestIn(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    body: Optional[str] = Field(default=None, min_length=1, max_length=300)


class PushStatusOut(BaseModel):
    enabled: bool
    library_available: bool
    configured: bool
    ready: bool
    reason: str
    vapid_public_key: str
    active_subscriptions: int


class PushSubscriptionOut(BaseModel):
    id: int
    endpoint: str
    is_active: bool
    created_at: datetime
    last_seen_at: datetime
    last_error: Optional[str] = None



def _require_tenant_id(current_user: Customer) -> int:
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(
            status_code=403,
            detail="Uživatel nemá přiřazený tenant. Kontaktujte administrátora.",
        )
    return tenant_id


def _ensure_push_schema(db: Session) -> None:
    assert_module_ready(db, "push", detail_prefix="Push notifikace nejsou připravené")


@router.get("/status", response_model=PushStatusOut)
def get_push_status(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Vrátí stav push infrastruktury a počty subscriptions aktuálního uživatele."""
    tenant_id = _require_tenant_id(current_user)
    _ensure_push_schema(db)
    infra = push_status()

    active_count = (
        db.query(PushSubscription)
        .filter(
            PushSubscription.tenant_id == tenant_id,
            PushSubscription.customer_id == current_user.id,
            PushSubscription.is_active == True,
        )
        .count()
    )

    return PushStatusOut(
        enabled=bool(infra["enabled"]),
        library_available=bool(infra["library_available"]),
        configured=bool(infra["configured"]),
        ready=bool(infra["ready"]),
        reason=str(infra["reason"]),
        vapid_public_key=str(infra["vapid_public_key"] or ""),
        active_subscriptions=int(active_count),
    )


@router.get("/vapid-public-key")
def get_vapid_public_key(
    current_user: Customer = Depends(get_current_user),
):
    """Vrátí VAPID public key pro vytvoření browser subscription."""
    _require_tenant_id(current_user)
    infra = push_status()

    if not infra["enabled"]:
        raise HTTPException(status_code=503, detail="Web Push je vypnutý (WEB_PUSH_ENABLED=0).")
    if not infra["configured"]:
        raise HTTPException(status_code=503, detail="Chybí VAPID klíče pro Web Push.")

    return {
        "vapid_public_key": infra["vapid_public_key"],
        "ready": bool(infra["ready"]),
        "library_available": bool(infra["library_available"]),
    }


@router.get("/subscriptions", response_model=list[PushSubscriptionOut])
def list_push_subscriptions(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Vrátí seznam push subscriptions aktuálního uživatele."""
    tenant_id = _require_tenant_id(current_user)
    _ensure_push_schema(db)

    subscriptions = (
        db.query(PushSubscription)
        .filter(
            PushSubscription.tenant_id == tenant_id,
            PushSubscription.customer_id == current_user.id,
        )
        .order_by(PushSubscription.id.desc())
        .all()
    )

    return [
        PushSubscriptionOut(
            id=sub.id,
            endpoint=sub.endpoint,
            is_active=bool(sub.is_active),
            created_at=sub.created_at,
            last_seen_at=sub.last_seen_at,
            last_error=sub.last_error,
        )
        for sub in subscriptions
    ]


@router.post("/subscribe")
def subscribe_push(
    payload: PushSubscribeIn,
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Vytvoří/aktualizuje push subscription pro aktuálního uživatele."""
    tenant_id = _require_tenant_id(current_user)
    _ensure_push_schema(db)
    infra = push_status()

    if not infra["enabled"]:
        raise HTTPException(status_code=503, detail="Web Push je vypnutý (WEB_PUSH_ENABLED=0).")
    if not infra["configured"]:
        raise HTTPException(status_code=503, detail="Chybí VAPID klíče pro Web Push.")

    endpoint = payload.endpoint.strip()
    existing = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
    now = datetime.utcnow()
    user_agent = request.headers.get("user-agent")

    if existing:
        existing.tenant_id = tenant_id
        existing.customer_id = current_user.id
        existing.endpoint = endpoint
        existing.p256dh = payload.keys.p256dh.strip()
        existing.auth = payload.keys.auth.strip()
        existing.user_agent = user_agent
        existing.last_seen_at = now
        existing.updated_at = now
        existing.is_active = True
        existing.last_error = None
        db.commit()
        db.refresh(existing)
        return {
            "status": "ok",
            "action": "updated",
            "subscription_id": existing.id,
            "active": bool(existing.is_active),
        }

    created = PushSubscription(
        tenant_id=tenant_id,
        customer_id=current_user.id,
        endpoint=endpoint,
        p256dh=payload.keys.p256dh.strip(),
        auth=payload.keys.auth.strip(),
        user_agent=user_agent,
        is_active=True,
        last_error=None,
        created_at=now,
        updated_at=now,
        last_seen_at=now,
    )
    db.add(created)
    db.commit()
    db.refresh(created)

    return {
        "status": "ok",
        "action": "created",
        "subscription_id": created.id,
        "active": bool(created.is_active),
    }


@router.post("/unsubscribe")
def unsubscribe_push(
    payload: Optional[PushUnsubscribeIn] = None,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deaktivuje jednu nebo všechny push subscriptions aktuálního uživatele."""
    tenant_id = _require_tenant_id(current_user)
    _ensure_push_schema(db)
    endpoint = payload.endpoint.strip() if payload and payload.endpoint else None

    query = db.query(PushSubscription).filter(
        PushSubscription.tenant_id == tenant_id,
        PushSubscription.customer_id == current_user.id,
        PushSubscription.is_active == True,
    )
    if endpoint:
        query = query.filter(PushSubscription.endpoint == endpoint)

    rows = query.all()
    for row in rows:
        row.is_active = False
        row.updated_at = datetime.utcnow()

    db.commit()

    return {
        "status": "ok",
        "deactivated": len(rows),
        "scope": "single" if endpoint else "all",
    }


@router.post("/test")
def send_push_test(
    payload: Optional[PushTestIn] = None,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pošle testovací push notifikaci aktuálnímu uživateli."""
    tenant_id = _require_tenant_id(current_user)
    _ensure_push_schema(db)

    title = (payload.title if payload else None) or APP_DISPLAY_NAME
    body = (payload.body if payload else None) or "Test push notifikace proběhl úspěšně."

    result = send_push_to_customer(
        db,
        tenant_id=tenant_id,
        customer_id=current_user.id,
        title=title,
        body=body,
        url="/web/index.html",
        tag="sprava-vozidel-test",
    )

    return {
        "status": "ok",
        "result": result,
    }
