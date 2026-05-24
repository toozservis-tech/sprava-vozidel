"""
Globální append-only audit log (tabulka audit_log).
Zapisuje se ve stejné DB transakci jako nadřazená akce, nebo krátce po commitu licence.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from sqlalchemy.orm import Session

from .models import GlobalAuditLog as GlobalAuditLogModel

logger = logging.getLogger(__name__)


def write_global_audit_log(
    db: Session,
    *,
    entity_type: str,
    entity_id: int | None,
    action: str,
    actor_user_id: int | None = None,
    actor_role: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    tenant_id: int | None = None,
    actor_type: str | None = None,
    actor_id: int | None = None,
    vehicle_id: int | None = None,
    before_json: Mapping[str, Any] | None = None,
    after_json: Mapping[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    correlation_id: str | None = None,
) -> None:
    """Přidá řádek audit_log (volající provede commit)."""
    try:
        meta_json = json.dumps(dict(metadata), ensure_ascii=False, default=str) if metadata else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[AUDIT] metadata serializace selhala: %s", exc)
        meta_json = None

    row = GlobalAuditLogModel(
        tenant_id=tenant_id,
        actor_type=(actor_type or actor_role or None),
        actor_id=actor_id if actor_id is not None else actor_user_id,
        vehicle_id=vehicle_id,
        entity_type=(entity_type or "")[:64],
        entity_id=entity_id,
        action=(action or "")[:128],
        actor_user_id=actor_user_id,
        actor_role=(str(actor_role)[:64] if actor_role else None),
        before_json=json.dumps(dict(before_json), ensure_ascii=False, default=str) if before_json else None,
        after_json=json.dumps(dict(after_json), ensure_ascii=False, default=str) if after_json else None,
        ip=(str(ip)[:128] if ip else None),
        user_agent=str(user_agent) if user_agent else None,
        correlation_id=(str(correlation_id)[:128] if correlation_id else None),
        metadata_json=meta_json,
    )
    db.add(row)
