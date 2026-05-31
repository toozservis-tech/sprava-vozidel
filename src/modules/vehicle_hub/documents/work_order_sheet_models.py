from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WorkOrderSheetItemPayload:
    category: str
    name: str
    quantity_label: str
    unit: str
    note: Optional[str] = None


@dataclass
class WorkOrderSheetPhotoPayload:
    label: str
    photo_type: str


@dataclass
class WorkOrderSheetDocumentPayload:
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
    billing_contact_name: Optional[str]
    billing_contact_phone: Optional[str]
    billing_contact_email: Optional[str]

    vehicle_label: str
    vehicle_plate: Optional[str]
    vehicle_vin: Optional[str]
    vehicle_odometer_km: Optional[int]
    fuel_level: Optional[str]

    intake_received_at_label: str
    defect_description: str
    customer_request: str
    technical_note: str
    intake_note: str

    work_order_id: int
    work_order_number: str
    work_order_status: str
    work_order_status_label: str
    work_order_title: str
    work_order_description: str
    received_at_label: str
    completed_at_label: str
    technician_name: str

    labor_items: list[WorkOrderSheetItemPayload] = field(default_factory=list)
    part_items: list[WorkOrderSheetItemPayload] = field(default_factory=list)
    time_items: list[WorkOrderSheetItemPayload] = field(default_factory=list)

    intake_photos: list[WorkOrderSheetPhotoPayload] = field(default_factory=list)
    intake_photo_count: int = 0

    customer_signature_present: bool = False
    customer_signature_label: str = "Neuvedeno"
    service_signature_label: str = "Neuvedeno"

    verify_url: Optional[str] = None
    verification_code: Optional[str] = None
