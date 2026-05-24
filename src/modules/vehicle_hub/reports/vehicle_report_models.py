from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class VehicleReportMode(str, Enum):
    PUBLIC = "public"
    OWNER = "owner"
    WORKSHOP = "workshop"
    INTERNAL_AUDIT = "internal_audit"


@dataclass(slots=True)
class VehicleReportDocument:
    type: str
    version: str
    generated_at: str
    document_id: str
    verification_code: str
    fingerprint: str
    export_mode: str
    issued_by: Optional[str] = None
    public_token: Optional[str] = None
    verification_url: Optional[str] = None
    verification_enabled: bool = False
    revision: int = 1
    generated_by_user_id: Optional[int] = None
    generated_by_role: Optional[str] = None


@dataclass(slots=True)
class VehicleReportVehicle:
    internal_id: int
    nickname: Optional[str]
    vin: Optional[str]
    spz: Optional[str]
    brand: Optional[str]
    model: Optional[str]
    variant: Optional[str]
    year: Optional[int]
    first_registration_date: Optional[str]
    engine_ccm: Optional[int]
    power_kw: Optional[int]
    fuel_type: Optional[str]
    transmission: Optional[str]
    odometer_km: Optional[int]
    stk_valid_to: Optional[str]
    primary_photo_path: Optional[str] = None


@dataclass(slots=True)
class VehicleReportSummary:
    records_count: int
    last_service_date: Optional[str]
    last_service_km: Optional[int]
    last_oil_service_date: Optional[str]
    last_brake_service_date: Optional[str]
    open_recommendations: list[str] = field(default_factory=list)
    record_quality_flags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VehicleReportMileagePoint:
    date: str
    mileage_km: int
    source_type: str
    source_label: str
    reference: str
    anomaly_flags: list[str] = field(default_factory=list)
    anomaly_note: Optional[str] = None


@dataclass(slots=True)
class VehicleReportMileageTimeline:
    points: list[VehicleReportMileagePoint] = field(default_factory=list)
    first_known_date: Optional[str] = None
    first_known_mileage_km: Optional[int] = None
    last_known_date: Optional[str] = None
    last_known_mileage_km: Optional[int] = None
    anomalies_count: int = 0


@dataclass(slots=True)
class VehicleReportServiceRecord:
    id: int
    date: Optional[str]
    odometer_km: Optional[int]
    category: Optional[str]
    title: str
    performed_work: Optional[str]
    parts: list[str] = field(default_factory=list)
    notes: Optional[str] = None
    attachments_count: int = 0
    supplier: Optional[str] = None
    workshop: Optional[str] = None
    technician: Optional[str] = None
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None
    source_type: Optional[str] = None
    verification_status: Optional[str] = None
    audit_note: Optional[str] = None
    totals: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VehicleReportOwner:
    label: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    address: Optional[str] = None


@dataclass(slots=True)
class VehicleServiceReportPayload:
    document: VehicleReportDocument
    vehicle: VehicleReportVehicle
    summary: VehicleReportSummary
    service_records: list[VehicleReportServiceRecord] = field(default_factory=list)
    mileage_timeline: VehicleReportMileageTimeline = field(default_factory=VehicleReportMileageTimeline)
    owner: Optional[VehicleReportOwner] = None
    verification_qr_payload: Optional[str] = None
    # Předávací odkaz pro nového vlastníka (jen v PDF při prodeji); neúčastní se hashování dokumentu.
    new_owner_claim_qr_payload: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def isoformat_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
