"""Web Push helpery pro Správu vozidel."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from src.core.config import (
    WEB_PUSH_ENABLED,
    VAPID_PUBLIC_KEY,
    VAPID_PRIVATE_KEY,
    VAPID_CLAIMS_SUBJECT,
)
from .models import PushSubscription

try:  # pragma: no cover - fallback při chybějící dependency
    from pywebpush import webpush, WebPushException

    PYWEBPUSH_AVAILABLE = True
except Exception:  # pragma: no cover
    webpush = None

    class WebPushException(Exception):
        """Fallback exception třída, pokud pywebpush není dostupný."""

    PYWEBPUSH_AVAILABLE = False


def push_status() -> Dict[str, Any]:
    """Vrátí aktuální stav push infrastruktury."""
    configured = bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)
    ready = bool(WEB_PUSH_ENABLED and PYWEBPUSH_AVAILABLE and configured)

    reason = "ok"
    if not WEB_PUSH_ENABLED:
        reason = "WEB_PUSH_ENABLED=0"
    elif not PYWEBPUSH_AVAILABLE:
        reason = "pywebpush_not_installed"
    elif not configured:
        reason = "missing_vapid_keys"

    return {
        "enabled": bool(WEB_PUSH_ENABLED),
        "library_available": bool(PYWEBPUSH_AVAILABLE),
        "configured": configured,
        "ready": ready,
        "reason": reason,
        "vapid_public_key": VAPID_PUBLIC_KEY,
    }


def _build_subscription_payload(subscription: PushSubscription) -> Dict[str, Any]:
    return {
        "endpoint": subscription.endpoint,
        "keys": {
            "p256dh": subscription.p256dh,
            "auth": subscription.auth,
        },
    }


def _extract_push_status_code(exc: Exception) -> Optional[int]:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    return getattr(response, "status_code", None)


def send_web_push_message(
    subscription: PushSubscription,
    *,
    title: str,
    body: str,
    url: str = "/web/index.html",
    icon: str = "/web/assets/toozservis-logo-icon.png",
    badge: str = "/web/assets/toozservis-logo-icon.png",
    tag: Optional[str] = None,
    ttl: int = 60 * 60 * 24,
) -> Tuple[bool, Optional[str], Optional[int]]:
    """Pošle push notifikaci na jednu subscription."""
    status = push_status()
    if not status["ready"]:
        return False, status["reason"], None

    payload = {
        "title": title,
        "body": body,
        "url": url,
        "icon": icon,
        "badge": badge,
        "tag": tag,
        "timestamp": int(datetime.utcnow().timestamp() * 1000),
    }

    try:
        webpush(
            subscription_info=_build_subscription_payload(subscription),
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_CLAIMS_SUBJECT},
            ttl=ttl,
        )
        return True, None, None
    except WebPushException as exc:
        code = _extract_push_status_code(exc)
        return False, str(exc), code
    except Exception as exc:  # pragma: no cover
        return False, str(exc), None


def send_push_to_customer(
    db: Session,
    *,
    tenant_id: int,
    customer_id: int,
    title: str,
    body: str,
    url: str = "/web/index.html",
    icon: str = "/web/assets/toozservis-logo-icon.png",
    badge: str = "/web/assets/toozservis-logo-icon.png",
    tag: Optional[str] = None,
) -> Dict[str, Any]:
    """Pošle push notifikaci na všechny aktivní subscriptions zákazníka."""
    status = push_status()
    if not status["ready"]:
        return {
            "total": 0,
            "sent": 0,
            "failed": 0,
            "expired": 0,
            "reason": status["reason"],
        }

    subscriptions = (
        db.query(PushSubscription)
        .filter(
            PushSubscription.tenant_id == tenant_id,
            PushSubscription.customer_id == customer_id,
            PushSubscription.is_active == True,
        )
        .all()
    )

    if not subscriptions:
        return {
            "total": 0,
            "sent": 0,
            "failed": 0,
            "expired": 0,
            "reason": "no_active_subscriptions",
        }

    sent = 0
    failed = 0
    expired = 0
    now = datetime.utcnow()

    for subscription in subscriptions:
        ok, error_message, status_code = send_web_push_message(
            subscription,
            title=title,
            body=body,
            url=url,
            icon=icon,
            badge=badge,
            tag=tag,
        )
        if ok:
            sent += 1
            subscription.last_error = None
            subscription.last_seen_at = now
            subscription.is_active = True
            continue

        failed += 1
        subscription.last_error = (error_message or "unknown_error")[:2000]
        if status_code in {404, 410}:
            subscription.is_active = False
            expired += 1

    db.commit()

    return {
        "total": len(subscriptions),
        "sent": sent,
        "failed": failed,
        "expired": expired,
        "reason": "ok" if sent > 0 else "send_failed",
    }
