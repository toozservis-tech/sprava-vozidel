"""
Helpers pro stav účtu zákazníka (disable/delete/session invalidace).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from sqlalchemy.orm import Session

from .schema_management import assert_module_ready

_SCHEMA_READY = False


def ensure_customer_account_state_schema(db: Session) -> None:
    """
    Ověří, že account-state schéma bylo aplikováno migrací.
    """
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    assert_module_ready(db, "security", detail_prefix="Bezpečnostní/account schéma není připravené")
    _SCHEMA_READY = True


def customer_is_deleted(customer: Any) -> bool:
    return bool(getattr(customer, "is_deleted", False))


def customer_is_disabled(customer: Any) -> bool:
    return bool(getattr(customer, "is_disabled", False))


def customer_session_version(customer: Any) -> int:
    raw = getattr(customer, "session_version", 0)
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def touch_customer_last_seen(customer: Any) -> None:
    try:
        setattr(customer, "last_seen_at", datetime.utcnow())
    except Exception:
        return


def touch_customer_last_login(customer: Any) -> None:
    try:
        now = datetime.utcnow()
        setattr(customer, "last_login_at", now)
        setattr(customer, "last_seen_at", now)
    except Exception:
        return


def increment_customer_session_version(customer: Any) -> int:
    next_version = customer_session_version(customer) + 1
    try:
        setattr(customer, "session_version", next_version)
    except Exception:
        return customer_session_version(customer)
    return next_version


def snapshot_customer_state(customer: Any) -> Dict[str, Any]:
    return {
        "is_deleted": customer_is_deleted(customer),
        "is_disabled": customer_is_disabled(customer),
        "session_version": customer_session_version(customer),
        "deleted_at": getattr(customer, "deleted_at", None),
        "disabled_at": getattr(customer, "disabled_at", None),
        "last_login_at": getattr(customer, "last_login_at", None),
        "last_seen_at": getattr(customer, "last_seen_at", None),
    }
