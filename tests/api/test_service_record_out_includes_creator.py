"""ServiceRecordOutV1 obsahuje created_by_service_customer_id pro servisní UI."""
from __future__ import annotations

from src.modules.vehicle_hub.routers_v1.schemas import ServiceRecordOutV1


def test_service_record_out_schema_has_service_creator_field() -> None:
    fields = ServiceRecordOutV1.model_fields.keys()
    assert "created_by_service_customer_id" in fields
