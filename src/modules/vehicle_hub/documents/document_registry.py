from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet


@dataclass(frozen=True)
class DocumentTypeDef:
    key: str
    label: str
    allowed_statuses: FrozenSet[str]
    default_visibility: str
    source_type: str
    can_owner_view: bool
    can_service_view: bool
    requires_verification: bool
    supports_thumbnail: bool
    renderer_status: str  # platform_ready | specific_renderer_pending


DOCUMENT_REGISTRY: dict[str, DocumentTypeDef] = {
    "invoice": DocumentTypeDef(
        key="invoice",
        label="Faktura",
        allowed_statuses=frozenset({"draft", "pending", "completed", "cancelled", "archived"}),
        default_visibility="service_private",
        source_type="service_invoice",
        can_owner_view=False,
        can_service_view=True,
        requires_verification=True,
        supports_thumbnail=True,
        renderer_status="platform_ready",
    ),
    "quote": DocumentTypeDef(
        key="quote",
        label="Nabídka",
        allowed_statuses=frozenset({"draft", "pending", "approved", "cancelled", "archived"}),
        default_visibility="service_private",
        source_type="service_quote",
        can_owner_view=False,
        can_service_view=True,
        requires_verification=True,
        supports_thumbnail=True,
        renderer_status="platform_ready",
    ),
    "work_order_sheet": DocumentTypeDef(
        key="work_order_sheet",
        label="Zakázkový list",
        allowed_statuses=frozenset({"draft", "pending", "completed", "cancelled", "archived"}),
        default_visibility="service_private",
        source_type="service_work_order",
        can_owner_view=False,
        can_service_view=True,
        requires_verification=True,
        supports_thumbnail=True,
        renderer_status="platform_ready",
    ),
    "intake_protocol": DocumentTypeDef(
        key="intake_protocol",
        label="Příjmový protokol",
        allowed_statuses=frozenset({"draft", "pending", "completed", "cancelled", "archived"}),
        default_visibility="service_private",
        source_type="service_intake",
        can_owner_view=False,
        can_service_view=True,
        requires_verification=True,
        supports_thumbnail=True,
        renderer_status="platform_ready",
    ),
    "service_report": DocumentTypeDef(
        key="service_report",
        label="Servisní zpráva",
        allowed_statuses=frozenset({"draft", "pending", "completed", "cancelled", "archived"}),
        default_visibility="service_private",
        source_type="service_record",
        can_owner_view=True,
        can_service_view=True,
        requires_verification=True,
        supports_thumbnail=True,
        renderer_status="platform_ready",
    ),
    "handover_protocol": DocumentTypeDef(
        key="handover_protocol",
        label="Předávací protokol",
        allowed_statuses=frozenset({"draft", "pending", "completed", "cancelled", "archived"}),
        default_visibility="service_private",
        source_type="service_work_order",
        can_owner_view=True,
        can_service_view=True,
        requires_verification=True,
        supports_thumbnail=True,
        renderer_status="platform_ready",
    ),
    "vehicle_history": DocumentTypeDef(
        key="vehicle_history",
        label="Historie vozidla",
        allowed_statuses=frozenset({"draft", "completed", "archived", "cancelled"}),
        default_visibility="public_verified",
        source_type="vehicle_report_document",
        can_owner_view=True,
        can_service_view=True,
        requires_verification=True,
        supports_thumbnail=True,
        renderer_status="platform_ready",
    ),
}


def get_document_type(key: str) -> DocumentTypeDef:
    normalized = str(key or "").strip().lower()
    if normalized not in DOCUMENT_REGISTRY:
        raise KeyError(f"Unknown document type: {key}")
    return DOCUMENT_REGISTRY[normalized]
