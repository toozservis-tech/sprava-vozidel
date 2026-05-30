from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QuoteLinePayload:
    description: str
    quantity: float
    unit: str
    unit_price: float
    tax_rate: float
    line_total: float


@dataclass
class QuoteDocumentPayload:
    quote_id: int
    quote_number: str
    document_status: str
    status_label: str
    is_draft: bool
    created_at_label: str
    valid_until_label: str
    validity_note: Optional[str]
    currency: str
    subtotal: float
    tax_total: float
    total: float
    service_name: str
    service_ico: Optional[str]
    service_dic: Optional[str]
    service_address: str
    service_email: Optional[str]
    service_phone: Optional[str]
    customer_name: str
    customer_address: str
    customer_ico: Optional[str]
    customer_dic: Optional[str]
    vehicle_label: str
    vehicle_plate: Optional[str]
    vehicle_vin: Optional[str]
    vehicle_odometer_km: Optional[int]
    work_order_id: Optional[int]
    verify_url: Optional[str]
    verification_code: Optional[str]
    lines: list[QuoteLinePayload] = field(default_factory=list)
