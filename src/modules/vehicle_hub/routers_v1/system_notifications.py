"""
System notifications feed for authenticated users.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, List

from fastapi import APIRouter, Depends
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, SystemNotification, License
from ..schema_management import assert_module_ready
from .auth import get_current_user
from src.server.maintenance_runtime_notice import build_maintenance_runtime_notification_item
from src.server.system_notification_markup import notification_message_kind
from src.server.runtime_settings import load_runtime_settings

router = APIRouter(prefix="/system-notifications", tags=["system-notifications"])


@router.get("")
def list_system_notifications(
    limit: int = 20,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Vrátí aktivní systémová oznámení cílená na aktuálního uživatele.
    """
    assert_module_ready(db, "system_notifications", detail_prefix="Systémová oznámení nejsou připravená")
    now = datetime.utcnow()
    safe_limit = max(1, min(limit, 100))

    license_row = db.query(License).filter(License.tenant_id == current_user.tenant_id).first()
    user_plan = (license_row.plan if license_row else "free") or "free"

    rows: List[SystemNotification] = (
        db.query(SystemNotification)
        .filter(
            SystemNotification.is_active.is_(True),
            or_(SystemNotification.starts_at.is_(None), SystemNotification.starts_at <= now),
            or_(SystemNotification.expires_at.is_(None), SystemNotification.expires_at > now),
            or_(
                SystemNotification.target_type == "all",
                and_(
                    SystemNotification.target_type == "tenant",
                    SystemNotification.target_value == str(current_user.tenant_id),
                ),
                and_(
                    SystemNotification.target_type == "user",
                    SystemNotification.target_value == str(current_user.id),
                ),
                and_(
                    SystemNotification.target_type == "plan",
                    SystemNotification.target_value == str(user_plan).strip().lower(),
                ),
            ),
        )
        .order_by(SystemNotification.created_at.desc(), SystemNotification.id.desc())
        .limit(safe_limit)
        .all()
    )

    items = []
    for row in rows:
        items.append(
            {
                "id": row.id,
                "title": row.title,
                "message": row.message,
                "message_kind": notification_message_kind(row.message),
                "severity": row.severity or "info",
                "target_type": row.target_type,
                "target_value": row.target_value,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            }
        )

    runtime_settings_loaded = load_runtime_settings()
    maintenance_item = build_maintenance_runtime_notification_item(runtime_settings_loaded)
    if maintenance_item:
        items.insert(0, maintenance_item)
        if len(items) > safe_limit:
            items = items[:safe_limit]

    return {
        "items": items,
        "count": len(items),
    }
