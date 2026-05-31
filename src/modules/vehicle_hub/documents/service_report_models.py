from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ServiceReportWorkItemPayload:
    name: str
    quantity_label: str
    unit: str
    note: Optional[str] = None


@dataclass
class ServiceReportPartPayload:
    name: str
    quantity_label: str
    unit: str
    note: Optional[str] = None


@dataclass
class ServiceReportTimePayload:
    label: str
    duration_label: str
    note: Optional[str] = None


@dataclass
class ServiceReportPhotoPayload:
    label: str
    photo_type: str
    image_path: Optional[str] = None


@dataclass
class ServiceReportDocumentPayload:
    document_number: str
    document_status: str
    status_label: str
    document_title: str
    created_at_label: str
    performed_at_label: str

    service_name: str
    service_ico: Optional[str]
    service_dic: Optional[str]
    service_address: str
    service_email: Optional[str]
    service_phone: Optional[str]

    vehicle_label: str
    vehicle_plate: Optional[str]
    vehicle_vin: Optional[str]
    vehicle_odometer_km: Optional[int]

    work_order_id: Optional[int]
    work_order_number: str
    work_order_title: str
    intervention_title: str
    defect_description: str

    service_record_id: int
    record_status_label: str
    performed_work_summary: str
    recommendations: str
    technician_conclusion: str

    labor_items: list[ServiceReportWorkItemPayload] = field(default_factory=list)
    part_items: list[ServiceReportPartPayload] = field(default_factory=list)
    time_items: list[ServiceReportTimePayload] = field(default_factory=list)
    total_work_minutes: Optional[int] = None

    photos: list[ServiceReportPhotoPayload] = field(default_factory=list)
    photo_count: int = 0

    service_signature_label: str = "Neuvedeno"

    verify_url: Optional[str] = None
    verification_code: Optional[str] = None
