from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HandoverProtocolItemPayload:
    label: str
    value: str


@dataclass
class HandoverProtocolPartPayload:
    name: str
    quantity_label: str
    unit: str
    note: Optional[str] = None


@dataclass
class HandoverProtocolPhotoPayload:
    label: str
    photo_type: str
    image_path: Optional[str] = None


@dataclass
class HandoverProtocolDocumentPayload:
    document_number: str
    document_status: str
    status_label: str
    document_title: str
    created_at_label: str
    handover_at_label: str

    service_name: str
    service_ico: Optional[str]
    service_dic: Optional[str]
    service_address: str
    service_email: Optional[str]
    service_phone: Optional[str]

    customer_name: str
    customer_contact: str

    vehicle_label: str
    vehicle_plate: Optional[str]
    vehicle_vin: Optional[str]
    vehicle_odometer_km: Optional[int]
    vehicle_condition: str

    work_order_id: int
    work_order_number: str
    work_order_title: str

    work_summary: str
    part_items: list[HandoverProtocolPartPayload] = field(default_factory=list)
    recommendations: str = "Neuvedeno"

    handed_over_documents: list[HandoverProtocolItemPayload] = field(default_factory=list)
    handed_over_accessories: list[HandoverProtocolItemPayload] = field(default_factory=list)

    photos: list[HandoverProtocolPhotoPayload] = field(default_factory=list)
    photo_count: int = 0

    customer_signature_label: str = "Neuvedeno"
    service_signature_label: str = "Neuvedeno"

    verify_url: Optional[str] = None
    verification_code: Optional[str] = None
