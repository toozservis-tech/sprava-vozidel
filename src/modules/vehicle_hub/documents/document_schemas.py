from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

DOCUMENT_TYPES = frozenset({
    "invoice",
    "quote",
    "work_order_sheet",
    "intake_protocol",
    "service_report",
    "handover_protocol",
    "vehicle_history",
})

DOCUMENT_STATUSES = frozenset({
    "draft",
    "pending",
    "approved",
    "completed",
    "cancelled",
    "archived",
})

VISIBILITY_SCOPES = frozenset({
    "service_private",
    "owner_visible",
    "safe_after_claim",
    "public_verified",
    "internal_only",
})


@dataclass
class PlatformDocumentPayload:
    document_type: str
    document_status: str
    title: str
    document_number: Optional[str] = None
    vehicle_label: str = "Vozidlo"
    vehicle_plate: Optional[str] = None
    vehicle_vin_masked: Optional[str] = None
    service_name: str = "Servis"
    service_ico: Optional[str] = None
    customer_label: Optional[str] = None
    verify_url: Optional[str] = None
    verification_code: Optional[str] = None
    body_lines: list[str] = field(default_factory=list)
    platform_version: str = "C1.0"
