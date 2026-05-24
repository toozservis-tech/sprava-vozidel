"""
Kompatibilní importy pro starší kód a testy:
``from src.modules.vehicle_hub import service_workspace_customer_centre``.

SOURCE OF TRUTH (HTTP routy + veškerá business logika zákaznického centra servisu):
``src.modules.vehicle_hub.routers_v1.service_workspace_customer_centre``
"""

from __future__ import annotations

from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.routers_v1.service_workspace_customer_centre import (
    AddressPayloadV1,
    CustomerConfirmLinkRequestV1,
    CustomerCreateRequestV1,
    CustomerExactSearchRequestV1,
    CustomerLinkFromLookupRequestV1,
    ServiceCustomerOnboardingRequestV1,
    VehicleCreatePayloadV1,
    confirm_service_customer_link_core,
    consume_service_onboarding_token_core,
    customer_create_with_onboarding,
    customer_exact_search,
    customer_link_from_lookup_route,
    execute_customer_link_from_lookup,
    get_customer_detail_by_link_id,
    router,
)

__all__ = [
    "get_db",
    "router",
    "AddressPayloadV1",
    "CustomerConfirmLinkRequestV1",
    "CustomerCreateRequestV1",
    "CustomerExactSearchRequestV1",
    "CustomerLinkFromLookupRequestV1",
    "ServiceCustomerOnboardingRequestV1",
    "VehicleCreatePayloadV1",
    "confirm_service_customer_link_core",
    "consume_service_onboarding_token_core",
    "customer_create_with_onboarding",
    "customer_exact_search",
    "customer_link_from_lookup_route",
    "execute_customer_link_from_lookup",
    "get_customer_detail_by_link_id",
]
