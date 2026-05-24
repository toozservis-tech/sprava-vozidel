"""Serializace servisního záznamu pro audit a admin akce."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def service_record_audit_snapshot(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "vehicle_id": record.vehicle_id,
        "user_id": record.user_id,
        "customer_id": getattr(record, "customer_id", None),
        "service_id": getattr(record, "service_id", None),
        "work_order_id": getattr(record, "work_order_id", None),
        "quote_id": getattr(record, "quote_id", None),
        "performed_at": record.performed_at.isoformat() if record.performed_at else None,
        "mileage": record.mileage,
        "description": record.description,
        "price": record.price,
        "note": record.note,
        "category": record.category,
        "attachments": record.attachments,
        "next_service_due_date": (
            record.next_service_due_date.isoformat() if record.next_service_due_date else None
        ),
        "record_status": getattr(record, "record_status", "draft"),
        "service_type": getattr(record, "service_type", None),
        "recommended_next_service_text": getattr(record, "recommended_next_service_text", None),
        "recommended_next_service_date": (
            record.recommended_next_service_date.isoformat()
            if getattr(record, "recommended_next_service_date", None)
            else None
        ),
        "notes_customer_visible": getattr(record, "notes_customer_visible", None),
        "total_price": getattr(record, "total_price", None),
        "created_by_ai": bool(record.created_by_ai),
        "is_deleted": bool(getattr(record, "is_deleted", False)),
        "deleted_at": record.deleted_at.isoformat() if getattr(record, "deleted_at", None) else None,
        "deleted_by_user_id": getattr(record, "deleted_by_user_id", None),
        "deletion_reason": getattr(record, "deletion_reason", None),
    }


def snapshot_json_and_hash(snapshot: dict[str, Any]) -> tuple[str, str]:
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    snapshot_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
    return snapshot_json, snapshot_hash
