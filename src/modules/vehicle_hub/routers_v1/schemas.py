"""
Pydantic schémata pro API v1.0
"""
from pydantic import BaseModel, EmailStr, Field, field_serializer, model_validator
from typing import Any, Dict, List, Optional
from datetime import datetime, date

from src.core.datetime_cz import naive_utc_to_iso_z


# ==========================
#   VOZIDLA
# ==========================

class VehicleCreateV1(BaseModel):
    nickname: str = Field(..., min_length=2)
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine: Optional[str] = None
    vin: Optional[str] = None
    plate: Optional[str] = None
    notes: Optional[str] = None
    stk_valid_until: date
    current_mileage_km: Optional[int] = Field(default=None, ge=0)
    last_stk_mileage_km: Optional[int] = Field(default=None, ge=0)
    tyres_info: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_valid_until: Optional[date] = None
    orv_scan_id: Optional[int] = Field(default=None, gt=0)
    orv_number: Optional[str] = None
    orv_use_owner_data: bool = False
    data_trust_state: Optional[str] = None
    catalog_image_id: Optional[str] = None
    catalog_image_url: Optional[str] = None
    # assigned_service_id: Optional[int] = None  # ID servisu přiřazeného k vozidlu - DOČASNĚ ZAKÁZÁNO


class VehicleUpdateV1(BaseModel):
    nickname: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine: Optional[str] = None
    vin: Optional[str] = None
    plate: Optional[str] = None
    notes: Optional[str] = None
    stk_valid_until: Optional[date] = None
    current_mileage_km: Optional[int] = Field(default=None, ge=0)
    last_stk_mileage_km: Optional[int] = Field(default=None, ge=0)
    tyres_info: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_valid_until: Optional[date] = None
    orv_scan_id: Optional[int] = Field(default=None, gt=0)
    orv_number: Optional[str] = None
    orv_use_owner_data: Optional[bool] = None
    data_trust_state: Optional[str] = None
    catalog_image_id: Optional[str] = None
    catalog_image_url: Optional[str] = None
    regenerate_technical_overview: Optional[bool] = None
    # assigned_service_id: Optional[int] = None  # ID servisu přiřazeného k vozidlu - DOČASNĚ ZAKÁZÁNO


class VehicleOutV1(BaseModel):
    id: int
    user_email: str
    nickname: Optional[str]
    brand: Optional[str]
    model: Optional[str]
    year: Optional[int]
    fuel: Optional[str] = None
    body_type: Optional[str] = None
    engine: Optional[str]
    vin: Optional[str]
    plate: Optional[str]
    orv_number: Optional[str] = None
    orv_scan_source: Optional[str] = None
    orv_front_image_path: Optional[str] = None
    orv_back_image_path: Optional[str] = None
    orv_scanned_at: Optional[datetime] = None
    orv_confidence_json: Optional[str] = None
    data_trust_state: Optional[str] = None
    notes: Optional[str]
    primary_photo: Optional[Dict[str, Any]] = None
    photo_path: Optional[str] = None
    catalog_image_id: Optional[str] = None
    catalog_image_url: Optional[str] = None
    can_regenerate_catalog_image: bool = False
    remaining_catalog_image_regenerations: int = 0
    stk_valid_until: Optional[date]
    current_mileage_km: Optional[int] = None
    last_stk_mileage_km: Optional[int] = None
    mileage_checked_at: Optional[datetime] = None
    tyres_info: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_valid_until: Optional[date] = None
    current_owner_since: Optional[datetime] = None
    has_qr_token: bool = False
    qr_public_mode: Optional[str] = None
    qr_last_access_at: Optional[datetime] = None
    public_history_url: Optional[str] = None
    qr_svg: Optional[str] = None
    # assigned_service_id: Optional[int] = None  # DOČASNĚ ZAKÁZÁNO
    tenant_id: Optional[int] = None  # Multi-tenant podpora
    created_at: datetime
    technical_overview: Optional[Dict[str, Any]] = None
    provisioned_by_service_customer_id: Optional[int] = None
    provisioned_by_service_label: Optional[str] = None
    added_by_service_name: Optional[str] = None

    class Config:
        from_attributes = True


class VehicleMileageRecordV1(BaseModel):
    mileage_km: int = Field(..., ge=0)
    note: Optional[str] = Field(default=None, max_length=1000)
    confirm_lower_than_current: bool = False
    source: Optional[str] = Field(default="manual", max_length=32)


class VehicleMileageRecordResultV1(BaseModel):
    vehicle: VehicleOutV1
    created_record_id: Optional[int] = None
    created_vehicle_mileage_id: Optional[int] = None


class VehicleMileageLogEntryOutV1(BaseModel):
    """Jeden řádek historie km (tabulka vehicle_mileage)."""

    id: int
    mileage_km: int
    source: str
    note: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ORVParsedVehicleFieldsV1(BaseModel):
    plate: Optional[str] = None
    vin: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    type_label: Optional[str] = None
    variant: Optional[str] = None
    version: Optional[str] = None
    commercial_name: Optional[str] = None
    category: Optional[str] = None
    vehicle_kind: Optional[str] = None
    fuel: Optional[str] = None
    engine_power_kw: Optional[str] = None
    engine_displacement_cc: Optional[str] = None
    first_registration_date: Optional[str] = None
    first_registration_cz_date: Optional[str] = None
    seats_count: Optional[str] = None
    max_speed_kmh: Optional[str] = None
    emissions: Optional[str] = None
    consumption: Optional[str] = None
    weights: Optional[str] = None
    orv_number: Optional[str] = None


class ORVParsedOwnerFieldsV1(BaseModel):
    owner_name: Optional[str] = None
    owner_identifier: Optional[str] = None
    owner_address: Optional[str] = None
    operator_name: Optional[str] = None
    operator_identifier: Optional[str] = None
    operator_address: Optional[str] = None


class ORVParseFieldConfidenceV1(BaseModel):
    field_name: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    state: str = "review"


class ORVParseRequestV1(BaseModel):
    """Buď přední+zadní strana, nebo jeden snímek (malý ORV / jednostránkový techničák)."""

    front_image_base64: Optional[str] = None
    back_image_base64: Optional[str] = None
    single_orv_image_base64: Optional[str] = None
    front_image_mime_type: Optional[str] = Field(default="image/jpeg", max_length=255)
    back_image_mime_type: Optional[str] = Field(default="image/jpeg", max_length=255)
    single_orv_image_mime_type: Optional[str] = Field(default="image/jpeg", max_length=255)
    source: Optional[str] = Field(default="ios_orv_scan", max_length=64)

    @model_validator(mode="after")
    def _validate_orv_images(self) -> "ORVParseRequestV1":
        single = (self.single_orv_image_base64 or "").strip()
        front = (self.front_image_base64 or "").strip()
        back = (self.back_image_base64 or "").strip()
        if single:
            if front or back:
                raise ValueError("Zadejte buď jeden snímek ORV, nebo přední a zadní stranu, ne obojí.")
            if len(single) < 100:
                raise ValueError("Snímek ORV je příliš krátký.")
        elif len(front) < 100 or len(back) < 100:
            raise ValueError("Pro zpracování ORV jsou povinné obě strany dokladu, nebo jeden snímek malého techničáku.")
        return self


class ORVParseResponseV1(BaseModel):
    scan_id: int
    trust_state: str
    vehicle_fields: ORVParsedVehicleFieldsV1
    owner_fields: ORVParsedOwnerFieldsV1
    confidence: List[ORVParseFieldConfidenceV1] = []
    warnings: List[str] = []
    missing_fields: List[str] = []


class ORVReviewAuditRequestV1(BaseModel):
    """Údaje z kontrolní obrazovky před přenosem do formuláře vozidla (vozidlo se ještě neukládá)."""

    nickname: Optional[str] = Field(default=None, max_length=200)
    brand: Optional[str] = Field(default=None, max_length=120)
    model: Optional[str] = Field(default=None, max_length=120)
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    engine: Optional[str] = Field(default=None, max_length=500)
    vin: str = Field(..., min_length=5, max_length=32)
    plate: Optional[str] = Field(default=None, max_length=32)
    orv_number: Optional[str] = Field(default=None, max_length=64)


class ORVReviewAuditResponseV1(BaseModel):
    scan_id: int
    field_diffs: Dict[str, Any] = Field(default_factory=dict)
    vin_validation: Dict[str, Any] = Field(default_factory=dict)


class VehiclePreviewDecodedV1(BaseModel):
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    body_type: Optional[str] = None
    exterior_color: Optional[str] = None
    source: str = "manual-fallback"


class VehiclePreviewFromVinRequestV1(BaseModel):
    vin: str = Field(..., min_length=5, max_length=32)
    preferred_color: Optional[str] = Field(default=None, max_length=32)
    force_refresh: bool = False
    decoded: Optional[VehiclePreviewDecodedV1] = None


class VehiclePreviewCatalogImageAlternativeV1(BaseModel):
    url: str
    thumbnail_url: Optional[str] = None
    score: int = 0
    source_domain: Optional[str] = None


class VehiclePreviewCatalogImageV1(BaseModel):
    id: Optional[str] = None
    url: str
    thumbnail_url: Optional[str] = None
    source_domain: Optional[str] = None
    provider: str
    score: int = 0
    representative: bool = True
    verified_real_vehicle: bool = False
    license_note: str


class VehiclePreviewFromVinResponseV1(BaseModel):
    ok: bool
    vin: str
    decoded: Optional[VehiclePreviewDecodedV1] = None
    catalog_image: Optional[VehiclePreviewCatalogImageV1] = None
    alternatives: List[VehiclePreviewCatalogImageAlternativeV1] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    reason: Optional[str] = None
    can_regenerate: bool = False
    remaining_regenerations: int = 0
    saved_to_gallery: bool = False
    saved_gallery_photo_id: Optional[int] = None
    primary_photo_asset_id: Optional[int] = None


class VehicleCatalogImageGenerateRequestV1(BaseModel):
    preferred_color: Optional[str] = Field(default=None, max_length=32)
    save_to_gallery: bool = True


# ==========================
#   SERVISNÍ PŘÍSTUPY
# ==========================

class ServiceVehicleLookupRequestV1(BaseModel):
    query: str = Field(..., min_length=2, max_length=128)


class ServiceVehicleLookupCandidateOutV1(BaseModel):
    id: str
    vehicle_id: Optional[int] = None
    owner_customer_id: Optional[int] = None
    nickname: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    plate_masked: Optional[str] = None
    vin_masked: Optional[str] = None
    city: Optional[str] = None
    owner_label: Optional[str] = None
    status: str
    can_request_access: bool = True
    can_open_detail: bool = False
    can_create_work_order: bool = False
    match_score: Optional[float] = None
    match_type: Optional[str] = None
    blocking_reason: Optional[str] = None


class ServiceVehicleLookupResponseV1(BaseModel):
    candidates: List[ServiceVehicleLookupCandidateOutV1] = []


class ServiceAccessRequestCreateV1(BaseModel):
    vehicle_id: Optional[int] = Field(default=None, gt=0)
    lookup_query: str = Field(..., min_length=2, max_length=128)
    note: Optional[str] = Field(default=None, max_length=500)


class ServiceAccessRequestDecisionV1(BaseModel):
    decision: str = Field(..., min_length=3, max_length=32)
    note: Optional[str] = Field(default=None, max_length=500)


class ServiceAccessRequestOutV1(BaseModel):
    id: int
    vehicle_id: int
    service_id: int
    service_name: str
    service_email: Optional[str] = None
    vehicle_name: Optional[str] = None
    vehicle_plate: Optional[str] = None
    requested_at: Optional[datetime] = None
    status: str
    note: Optional[str] = None
    scope_summary: Optional[str] = None


class ServiceAccessRequestListOutV1(BaseModel):
    requests: List[ServiceAccessRequestOutV1] = []


class VehicleServiceLinkOutV1(BaseModel):
    service_id: int
    vehicle_id: int
    customer_id: int
    service_name: str
    service_email: str
    vehicle_name: Optional[str] = None
    vehicle_plate: Optional[str] = None
    status: Optional[str] = None
    updated_at: Optional[datetime] = None


class VehicleServiceLinkListOutV1(BaseModel):
    grants: List[VehicleServiceLinkOutV1] = []


class ConnectServiceByEmailRequestV1(BaseModel):
    """Propojení zákaznického účtu se servisem podle známého e-mailu servisu."""
    service_email: str = Field(..., min_length=3, max_length=320)


class ServiceApprovedVehicleOutV1(BaseModel):
    id: int
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    vehicle_name: Optional[str] = None
    vehicle_plate: Optional[str] = None
    last_shared_at: Optional[datetime] = None


class ServiceApprovedVehicleListOutV1(BaseModel):
    items: List[ServiceApprovedVehicleOutV1] = []


# ==========================
#   SERVISNÍ ZÁZNAMY
# ==========================

class ServiceRecordCreateV1(BaseModel):
    performed_at: datetime
    mileage: Optional[int] = Field(default=None, ge=0)
    description: str = Field(..., min_length=3)
    price: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = None
    category: str = Field(..., min_length=1)  # OLEJ, BRZDY, PNEU, STK, DIAGNOSTIKA, ...
    attachments: Optional[str] = None  # JSON string nebo text
    next_service_due_date: Optional[date] = None
    customer_id: Optional[int] = Field(default=None, gt=0)
    service_id: Optional[int] = Field(default=None, gt=0)
    work_order_id: Optional[int] = Field(default=None, gt=0)
    quote_id: Optional[int] = Field(default=None, gt=0)
    record_status: str = Field(default="draft", min_length=5, max_length=32)
    service_type: Optional[str] = Field(default=None, max_length=64)
    recommended_next_service_text: Optional[str] = Field(default=None, max_length=2000)
    recommended_next_service_date: Optional[date] = None
    notes_customer_visible: Optional[str] = None
    total_price: Optional[float] = Field(default=None, ge=0)


class ServiceRecordUpdateV1(BaseModel):
    performed_at: Optional[datetime] = None
    mileage: Optional[int] = Field(
        default=None,
        ge=0,
        description="Při PUT se ignoruje — nájezd existujícího záznamu nelze měnit.",
    )
    description: Optional[str] = Field(default=None, min_length=3)
    price: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = None
    category: Optional[str] = Field(default=None, min_length=1)
    attachments: Optional[str] = None
    next_service_due_date: Optional[date] = None
    customer_id: Optional[int] = Field(default=None, gt=0)
    service_id: Optional[int] = Field(default=None, gt=0)
    work_order_id: Optional[int] = Field(default=None, gt=0)
    quote_id: Optional[int] = Field(default=None, gt=0)
    record_status: Optional[str] = Field(default=None, min_length=5, max_length=32)
    service_type: Optional[str] = Field(default=None, max_length=64)
    recommended_next_service_text: Optional[str] = Field(default=None, max_length=2000)
    recommended_next_service_date: Optional[date] = None
    notes_customer_visible: Optional[str] = None
    total_price: Optional[float] = Field(default=None, ge=0)


class ServiceRecordOutV1(BaseModel):
    id: int
    vehicle_id: int
    user_id: Optional[int]
    customer_id: Optional[int] = None
    service_id: Optional[int] = None
    work_order_id: Optional[int] = None
    quote_id: Optional[int] = None
    performed_at: Optional[datetime]  # Může být None
    mileage: Optional[int]
    description: str
    price: Optional[float]
    note: Optional[str]
    category: Optional[str]
    attachments: Optional[str]
    next_service_due_date: Optional[date]
    record_status: str = "draft"
    service_type: Optional[str] = None
    recommended_next_service_text: Optional[str] = None
    recommended_next_service_date: Optional[date] = None
    notes_customer_visible: Optional[str] = None
    total_price: Optional[float] = None
    created_by_ai: bool = False  # True pokud byl záznam vytvořen AI asistentem
    created_by_service_customer_id: Optional[int] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deletion_reason: Optional[str] = None
    snapshot_hash: Optional[str] = None
    updated_at: Optional[datetime] = None

    viewer_mutations_allowed: bool = True
    viewer_financials_redacted: bool = False
    ownership_segment_index: Optional[int] = None
    current_viewer_segment_index: Optional[int] = None
    ownership_segment_owner_label: Optional[str] = None
    
    class Config:
        from_attributes = True


# ==========================
#   SERVISNÍ PŘÍJEM (INTAKE)
# ==========================

class ServiceIntakeCreateV1(BaseModel):
    vehicle_id: int
    customer_id: int
    odometer_km: Optional[int] = None
    fluids_ok: Optional[str] = None  # JSON string
    damage_description: Optional[str] = None
    photos: Optional[str] = None  # JSON string s listem URL
    work_description: Optional[str] = None
    signature: Optional[str] = None


class ServiceIntakeOutV1(BaseModel):
    id: int
    service_id: int
    vehicle_id: int
    customer_id: int
    odometer_km: Optional[int]
    fluids_ok: Optional[str]
    damage_description: Optional[str]
    photos: Optional[str]
    work_description: Optional[str]
    signature: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==========================
#   REZERVACE
# ==========================

class ReservationCreateV1(BaseModel):
    service_id: int
    vehicle_id: int
    service_type: Optional[str] = None
    note: Optional[str] = None
    start_datetime: datetime
    end_datetime: Optional[datetime] = None
    created_via: Optional[str] = Field(default=None, max_length=64)


class ReservationUpdateV1(BaseModel):
    service_type: Optional[str] = None
    note: Optional[str] = None
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    status: Optional[str] = None  # PENDING, CONFIRMED, CANCELLED


class ReservationOutV1(BaseModel):
    id: int
    service_id: int
    customer_id: int
    vehicle_id: int
    service_type: Optional[str]
    note: Optional[str]
    start_datetime: datetime
    end_datetime: Optional[datetime]
    status: str
    created_at: datetime
    service_name: Optional[str] = None
    service_email: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    vehicle_name: Optional[str] = None
    vehicle_plate: Optional[str] = None
    source_platform: Optional[str] = None
    
    class Config:
        from_attributes = True


class ReservationVehicleOptionOutV1(BaseModel):
    id: int
    name: str
    plate: Optional[str] = None
    owner_email: Optional[str] = None
    is_shared: bool = False
    source: Optional[str] = None


class VehicleQrTokenCreateV1(BaseModel):
    public_mode: str = Field(default="basic", min_length=5, max_length=32)
    explicit_full_consent: bool = False


class VehicleQrTokenOutV1(BaseModel):
    id: int
    vehicle_id: int
    token: str
    public_mode: str
    explicit_full_consent: bool
    issued_at: datetime
    revoked_at: Optional[datetime] = None
    last_access_at: Optional[datetime] = None
    signature_hash: str
    active: bool = True
    public_history_url: Optional[str] = None
    qr_svg: Optional[str] = None


class PublicServiceIdentityOutV1(BaseModel):
    name: Optional[str] = None
    ico: Optional[str] = None
    verified_status: bool = False


class PublicServiceRecordHistoryItemOutV1(BaseModel):
    id: int
    performed_at: Optional[datetime] = None
    mileage: Optional[int] = None
    category: Optional[str] = None
    description: Optional[str] = None
    record_status: str = "draft"
    service_type: Optional[str] = None
    recommended_next_service_text: Optional[str] = None
    recommended_next_service_date: Optional[date] = None
    notes_customer_visible: Optional[str] = None
    total_price: Optional[float] = None
    quote_id: Optional[int] = None
    quote_status: Optional[str] = None
    service_identity: PublicServiceIdentityOutV1 = PublicServiceIdentityOutV1()


class VehiclePublicHistoryOutV1(BaseModel):
    vehicle_id: int
    token_status: str
    public_mode: str
    vin: Optional[str] = None
    vehicle_label: Optional[str] = None
    year: Optional[int] = None
    engine: Optional[str] = None
    records: List[PublicServiceRecordHistoryItemOutV1] = []
    recommended_next_service_text: Optional[str] = None
    recommended_next_service_date: Optional[date] = None


# ==========================
#   PŘIPOMÍNKY
# ==========================

class ReminderOutV1(BaseModel):
    id: Optional[int] = None  # ID pro ruční připomínky
    type: str  # STK, OLEJ, SERVIS, VLASTNI, GENERAL
    vehicle_id: Optional[int] = None
    vehicle_name: Optional[str] = None
    text: str
    due_date: Optional[date] = None
    notify_at: Optional[datetime] = None
    notification_method: Optional[str] = None  # app, email, both; None = globální nastavení
    is_manual: bool = False  # True = ruční, False = automatická
    is_completed: Optional[bool] = False
    is_recurring: bool = False
    recurrence_group_id: Optional[str] = None
    recurrence_index: Optional[int] = None

    @field_serializer("notify_at", when_used="json")
    def _serialize_notify_at_json(self, value: Optional[datetime]) -> Optional[str]:
        return naive_utc_to_iso_z(value)


class ReminderCreateV1(BaseModel):
    """Model pro vytvoření ruční připomínky"""
    vehicle_id: Optional[int] = None
    type: str  # STK, OLEJ, SERVIS, VLASTNI
    text: str
    due_date: Optional[date] = None
    notify_at: Optional[datetime] = None
    notification_method: Optional[str] = None
    repeat_count: Optional[int] = Field(default=0, ge=0, le=24, description="Kolikrát zopakovat (0=bez opakování)")
    repeat_interval_days: Optional[int] = Field(default=0, ge=0, le=3650, description="Interval opakování ve dnech (0=neopakovat)")


class ReminderUpdateV1(BaseModel):
    """Model pro aktualizaci připomínky"""
    type: Optional[str] = None  # Typ připomínky (STK, OLEJ, SERVIS, VLASTNI)
    vehicle_id: Optional[int] = None  # ID vozidla (nebo None pro obecnou)
    text: Optional[str] = None
    due_date: Optional[date] = None
    notify_at: Optional[datetime] = None
    notification_method: Optional[str] = None
    is_completed: Optional[bool] = None


# ==========================
#   NASTAVENÍ PŘIPOMÍNEK
# ==========================

class STKReminderSettings(BaseModel):
    enabled: bool = True
    days_before: int = 30  # Kolik dní před koncem STK připomínat

class OilReminderSettings(BaseModel):
    enabled: bool = True
    km_interval: int = 15000  # Interval v km
    km_warning: int = 5000  # Varování X km před
    days_interval: int = 365  # Interval ve dnech
    days_warning: int = 30  # Varování X dní před

class ServiceCategorySettings(BaseModel):
    enabled: bool = True
    km_interval: Optional[int] = None
    days_interval: Optional[int] = None

class GeneralReminderSettings(BaseModel):
    enabled: bool = True
    days_before: int = 30  # Kolik dní před plánovaným servisem

class NotificationSettings(BaseModel):
    """Globální nastavení upozornění pro připomínky"""
    notification_method: str = "app"  # "app" = pouze v aplikaci, "email" = e-mail, "both" = obojí
    notify_days_before: int = 7  # Počet dní předem upozornit

class ReminderSettingsV1(BaseModel):
    enabled: bool = True
    stk: Optional[STKReminderSettings] = None
    oil: Optional[OilReminderSettings] = None
    service_categories: Optional[Dict[str, ServiceCategorySettings]] = None
    general: Optional[GeneralReminderSettings] = None
    notification: Optional[NotificationSettings] = None  # Globální nastavení upozornění

class ReminderSettingsOutV1(BaseModel):
    enabled: bool
    stk: STKReminderSettings
    oil: OilReminderSettings
    service_categories: Dict[str, ServiceCategorySettings]
    general: GeneralReminderSettings
    notification: NotificationSettings  # Globální nastavení upozornění


# ==========================
#   AI ENDPOINT
# ==========================

class AIRecordRequestV1(BaseModel):
    shared_secret: str
    user_id: int
    vehicle_id: Optional[int] = None
    message: str


class AIRecordResponseV1(BaseModel):
    status: str
    record_id: Optional[int] = None
    vehicle_id: int
    parsed: dict


# ==========================
#   ANALYTIKA
# ==========================

class AnalyticsSummaryOutV1(BaseModel):
    scope: str  # "all" | "vehicle"
    vehicle_id: Optional[int] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    total_records: int
    priced_records: int
    total_cost_czk: float
    average_cost_czk: Optional[float] = None
    min_cost_czk: Optional[float] = None
    max_cost_czk: Optional[float] = None
    mileage_min: Optional[int] = None
    mileage_max: Optional[int] = None
    latest_service_at: Optional[datetime] = None


class AnalyticsCategoryItemV1(BaseModel):
    category: str
    records_count: int
    priced_records_count: int
    total_cost_czk: float
    average_cost_czk: Optional[float] = None
    latest_service_at: Optional[datetime] = None


class AnalyticsCategoryBreakdownOutV1(BaseModel):
    scope: str  # "all" | "vehicle"
    vehicle_id: Optional[int] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    total_records: int
    categories: List[AnalyticsCategoryItemV1]


class AnalyticsMonthlyEntryV1(BaseModel):
    month: str  # YYYY-MM
    label: str  # MM/YYYY
    records_count: int
    priced_records_count: int
    total_cost_czk: float


class AnalyticsMonthlyCostsOutV1(BaseModel):
    scope: str  # "all" | "vehicle"
    vehicle_id: Optional[int] = None
    months: int
    generated_at: datetime
    total_records: int
    priced_records: int
    total_cost_czk: float
    entries: List[AnalyticsMonthlyEntryV1]
