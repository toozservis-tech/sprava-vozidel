from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IntakeProtocolChecklistItemPayload:
    label: str
    value: str


@dataclass
class IntakeProtocolPhotoSlotPayload:
    slot_key: str
    label: str
    status: str
    image_path: Optional[str] = None


@dataclass
class IntakeProtocolDocumentPayload:
    document_number: str
    document_status: str
    status_label: str
    document_title: str
    created_at_label: str

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
    fuel_level: Optional[str]

    received_at_label: str
    arrival_condition: str
    customer_request: str
    visible_defect: str
    technician_note: str

    checklist_items: list[IntakeProtocolChecklistItemPayload] = field(default_factory=list)
    photo_slots: list[IntakeProtocolPhotoSlotPayload] = field(default_factory=list)

    customer_signature_present: bool = False
    customer_signature_label: str = "Neuvedeno"
    service_signature_label: str = "Neuvedeno"

    verify_url: Optional[str] = None
    verification_code: Optional[str] = None
