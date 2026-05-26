from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean, Date, Text, UniqueConstraint, JSON, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base


class Tenant(Base):
    """Tenant (zákazník/firma) - multi-tenant architektura"""
    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint(
            "workspace_route_kind",
            "workspace_slug",
            name="uq_tenants_workspace_slug_per_kind",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    license_key = Column(String, unique=True, nullable=False, index=True)
    # Veřejný čitelný identifikátor pracovního prostoru (ne autorizační mechanismus).
    workspace_slug = Column(String(160), nullable=True, index=True)
    workspace_route_kind = Column(String(16), nullable=True, index=True)  # "user" | "service"
    created_at = Column(DateTime, default=datetime.utcnow)

    instances = relationship("Instance", back_populates="tenant")


class Instance(Base):
    """Instance (konkrétní instalace aplikace na PC)"""
    __tablename__ = "instances"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    device_id = Column(String, nullable=True)
    app_version = Column(String, nullable=True)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="instances")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    # identita / login
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)  # Hash hesla

    # fakturační / kontaktní údaje
    name = Column(String, nullable=True)          # jméno / název
    ico = Column(String, nullable=True)           # IČO (pro ARES)
    dic = Column(String, nullable=True)           # DIČ (daňové identifikační číslo)
    street = Column(String, nullable=True)        # název ulice
    street_number = Column(String, nullable=True) # číslo popisné
    city = Column(String, nullable=True)
    zip = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    # kde ho kontaktovat
    notify_email = Column(Boolean, default=True)
    notify_sms = Column(Boolean, default=False)

    # co chce hlídat
    notify_stk = Column(Boolean, default=True)    # konec STK
    notify_oil = Column(Boolean, default=True)    # výměna oleje
    notify_general = Column(Boolean, default=True)  # ostatní servis

    # role uživatele
    role = Column(String, default="user", nullable=False)  # user, service, admin

    # Zobrazit v uživatelském adresáři servisních partnerů (schválený servis / adminem vytvořený účet).
    partner_catalog_approved = Column(Boolean, nullable=False, default=False)

    # Veřejný textový profil servisu (JSON) pro katalog partnerů — vyplňuje servis ve workspace.
    partner_public_profile = Column(Text, nullable=True)

    # Volitelné rozšíření: JSON pole ["user","service"] — které URL/API režimy jsou povoleny (mimo výchozí odvození z role).
    workspace_entitlements = Column(Text, nullable=True)
    # Při dvou režimech: výchozí /api/me cesta (user|service); NULL = user pokud oba.
    workspace_ui_default = Column(String(8), nullable=True)

    # nastavení připomínek (JSON string)
    reminder_settings = Column(Text, nullable=True)
    
    # reset hesla
    reset_token = Column(String, nullable=True, index=True)
    reset_token_expires = Column(DateTime, nullable=True)

    # Stav účtu (developer control center)
    is_disabled = Column(Boolean, nullable=False, default=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    session_version = Column(Integer, nullable=False, default=0)
    disabled_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)

    # Přehledové číslo v adminu (1,2,3…); u smazaných NULL + záznam v customer_deletion_labels.
    admin_ordinal = Column(Integer, nullable=True, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Ověření identity / stav účtu (antifraud registrace)
    account_status = Column(String(40), nullable=False, default="pending_email_verification")
    email_verified_at = Column(DateTime, nullable=True)
    email_verification_token_hash = Column(String(128), nullable=True, index=True)
    email_verification_expires_at = Column(DateTime, nullable=True)
    email_verification_sent_at = Column(DateTime, nullable=True)
    phone_e164 = Column(String(20), nullable=True)
    phone_verified_at = Column(DateTime, nullable=True)
    registration_ip = Column(String(128), nullable=True)
    registration_user_agent = Column(Text, nullable=True)
    registration_risk_flags = Column(JSON, nullable=True)

    # Servisně založený účet / bezpečné vyhledávání (normalizované hodnoty)
    force_password_change = Column(Boolean, nullable=False, default=False)
    email_normalized = Column(String(320), nullable=True, index=True)
    phone_normalized = Column(String(32), nullable=True, index=True)

    # Uživatelské preference nastavení (JSON blob, verze 1)
    user_preferences = Column(JSON, nullable=True)


class CustomerDeletionLabel(Base):
    """Označení smazaného účtu v archivu (#N, ##N) podle pořadí smazání daného čísla."""

    __tablename__ = "customer_deletion_labels"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    ordinal_at_delete = Column(Integer, nullable=False, index=True)
    hash_depth = Column(Integer, nullable=False)
    email_before = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CustomerSecuritySettings(Base):
    """Rozšířené bezpečnostní nastavení zákazníka (2FA + biometrie preference)."""
    __tablename__ = "customer_security_settings"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, unique=True, index=True)

    two_factor_enabled = Column(Boolean, default=False, nullable=False)
    totp_secret = Column(String, nullable=True)
    totp_enabled_at = Column(DateTime, nullable=True)

    biometric_enabled = Column(Boolean, default=False, nullable=False)
    biometric_preferred = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceRegistrationRequest(Base):
    """Žádost o registraci servisního účtu čekající na schválení developerem."""
    __tablename__ = "service_registration_requests"

    id = Column(Integer, primary_key=True, index=True)

    status = Column(String, default="pending", nullable=False, index=True)  # pending, approved, rejected

    email = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)

    ico = Column(String, nullable=False, index=True)
    service_name = Column(String, nullable=False)
    responsible_person = Column(String, nullable=False)
    phone = Column(String, nullable=False)

    dic = Column(String, nullable=True)
    street = Column(String, nullable=False)
    street_number = Column(String, nullable=True)
    city = Column(String, nullable=False)
    zip = Column(String, nullable=False)

    registration_purpose = Column(Text, nullable=False)

    reviewed_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_note = Column(Text, nullable=True)

    approved_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    approved_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceCustomerLink(Base):
    """Propojení servisního účtu s koncovým zákazníkem."""
    __tablename__ = "service_customer_links"

    id = Column(Integer, primary_key=True, index=True)

    service_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    customer_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    status = Column(String, default="active", nullable=False, index=True)  # active, archived
    note = Column(Text, nullable=True)

    link_source = Column(String(40), nullable=True)
    consent_basis = Column(Text, nullable=True)
    consent_note = Column(Text, nullable=True)
    internal_service_note = Column(Text, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_by_service_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    last_interaction_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("service_customer_id", "customer_id", name="uq_service_customer_link"),
    )


class ServiceVehicleAccess(Base):
    """Explicitní povolení přístupu servisu ke konkrétnímu vozidlu zákazníka."""
    __tablename__ = "service_vehicle_access"

    id = Column(Integer, primary_key=True, index=True)

    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)

    status = Column(String, default="active", nullable=False, index=True)  # active, revoked
    granted_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    service_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    access_scope_json = Column(Text, nullable=True)
    revoke_reason = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("service_customer_id", "customer_id", "vehicle_id", name="uq_service_vehicle_access"),
    )


class UserOnboardingToken(Base):
    """Jednorázové tokeny pro založení hesla / pozvánku od servisu (jen hash v DB)."""

    __tablename__ = "user_onboarding_tokens"
    __table_args__ = ()

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, index=True)
    token_type = Column(String(64), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_by_service_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip_created = Column(String(128), nullable=True)
    user_agent_created = Column(Text, nullable=True)


class ServiceVehicleLookupAudit(Base):
    """Audit každého lookupu vozidla servisem přes SPZ/VIN."""
    __tablename__ = "service_vehicle_lookup_audit"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    lookup_query_raw = Column(String, nullable=True)
    lookup_query_normalized = Column(String, nullable=True, index=True)
    lookup_query_hash = Column(String, nullable=True, index=True)
    lookup_identifier_type = Column(String, nullable=False, default="unknown", index=True)  # plate, vin, unknown

    matched_vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)
    matched_owner_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    result_status = Column(String, nullable=False, default="not_found", index=True)
    returned_candidate_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class VehicleServiceLink(Base):
    """Produkční source of truth pro schválený nebo odvolaný přístup servisu k vozidlu."""
    __tablename__ = "vehicle_service_links"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    owner_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)

    source_request_id = Column(Integer, ForeignKey("service_access_requests.id"), nullable=True, index=True)
    source_type = Column(String, nullable=False, default="request_approved", index=True)
    status = Column(String, nullable=False, default="approved", index=True)  # approved, revoked

    scope_vehicle_history_read = Column(Boolean, nullable=False, default=True)
    scope_create_service_record = Column(Boolean, nullable=False, default=True)
    scope_edit_existing_records = Column(Boolean, nullable=False, default=False)
    scope_delete_existing_records = Column(Boolean, nullable=False, default=False)
    owner_data_access_level = Column(String, nullable=False, default="none")

    approved_at = Column(DateTime, nullable=True)
    approved_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    revoked_reason = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    last_used_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("service_customer_id", "vehicle_id", name="uq_vehicle_service_link_pair"),
    )


class ServiceAccessRequest(Base):
    """Žádost servisu o přístup ke konkrétnímu vozidlu."""
    __tablename__ = "service_access_requests"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    owner_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)

    lookup_audit_id = Column(Integer, ForeignKey("service_vehicle_lookup_audit.id"), nullable=True, index=True)
    requested_scope = Column(String, nullable=False, default="history_read_create_record")
    status = Column(String, nullable=False, default="pending", index=True)  # pending, approved, rejected, revoked
    request_message = Column(Text, nullable=True)

    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    decided_at = Column(DateTime, nullable=True)
    decided_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    decision_note = Column(Text, nullable=True)
    approved_link_id = Column(Integer, nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceCustomerInvite(Base):
    """Pozvánka od servisu pro zákazníka (registrace / propojení účtu)."""
    __tablename__ = "service_customer_invites"

    id = Column(Integer, primary_key=True, index=True)

    service_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    invite_email = Column(String, nullable=False, index=True)
    invite_name = Column(String, nullable=True)
    invite_message = Column(Text, nullable=True)

    token = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, default="pending", nullable=False, index=True)  # pending, accepted, expired, cancelled

    linked_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    linked_customer_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)

    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceDocumentIngestion(Base):
    """Automatický ingest dokladů od servisu (PDF/foto/text) + strukturovaný výstup."""
    __tablename__ = "service_document_ingestions"

    id = Column(Integer, primary_key=True, index=True)

    service_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)

    source_type = Column(String, nullable=False, default="invoice", index=True)  # invoice, delivery_note, work_order, manual
    original_filename = Column(String, nullable=True)
    original_mime_type = Column(String, nullable=True)
    stored_file_path = Column(Text, nullable=True)

    extracted_text = Column(Text, nullable=True)
    parsed_payload_json = Column(Text, nullable=True)
    parse_confidence = Column(Float, nullable=True)
    processing_status = Column(String, nullable=False, default="processed", index=True)  # processed, needs_review, failed

    document_number = Column(String, nullable=True, index=True)
    supplier_name = Column(String, nullable=True)
    issue_date = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    currency = Column(String, nullable=True, default="CZK")

    subtotal_without_vat = Column(Float, nullable=True)
    vat_amount = Column(Float, nullable=True)
    total_with_vat = Column(Float, nullable=True)
    labor_total = Column(Float, nullable=True)
    materials_total = Column(Float, nullable=True)

    auto_created_service_record_id = Column(Integer, ForeignKey("service_records.id"), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    # Legacy alias majitele pro staré klienty / kompatibilitu. Vlastníka určujte přes vehicle_ownerships,
    # neprovádějte nad tímto sloupcem nové business rozhodování (GDPR / single source of truth).
    user_email = Column(String, index=True, nullable=False)
    nickname = Column(String, nullable=True)
    brand = Column(String, nullable=True)
    model = Column(String, nullable=True)
    year = Column(Integer, nullable=True)
    fuel = Column(String, nullable=True)
    engine = Column(String, nullable=True)
    body_type = Column(String, nullable=True)
    vin = Column(String, nullable=True)
    plate = Column(String, nullable=True)
    normalized_vin = Column(String(17), nullable=True, index=True)
    normalized_plate = Column(String(32), nullable=True, index=True)
    global_vehicle_status = Column(String(32), nullable=False, default="owned_vehicle", index=True)
    source_origin = Column(String(32), nullable=False, default="legacy", index=True)
    claim_status = Column(String(32), nullable=False, default="none", index=True)
    claimed_at = Column(DateTime, nullable=True, index=True)
    claimed_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    provisioned_by_service_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    merge_guard_hash = Column(String(64), nullable=True, index=True)
    orv_number = Column(String, nullable=True, index=True)
    orv_scan_source = Column(String, nullable=True)
    orv_front_image_path = Column(Text, nullable=True)
    orv_back_image_path = Column(Text, nullable=True)
    orv_scanned_at = Column(DateTime, nullable=True)
    orv_confidence_json = Column(Text, nullable=True)
    data_trust_state = Column(String, nullable=True, index=True)
    notes = Column(String, nullable=True)
    photo_path = Column(Text, nullable=True)  # Legacy: relativní cesta v vehicle_photos/ (migrace → vehicle_photo_assets)
    catalog_image_id = Column(String(64), nullable=True, index=True)
    catalog_image_url = Column(Text, nullable=True)
    primary_photo_asset_id = Column(
        Integer,
        ForeignKey("vehicle_photo_assets.id"),
        nullable=True,
        index=True,
    )
    stk_valid_until = Column(Date, nullable=True)  # Datum konce platnosti STK
    current_mileage_km = Column(Integer, nullable=True)  # Aktuální stav tachometru zadaný uživatelem
    last_stk_mileage_km = Column(Integer, nullable=True)  # Poslední známý stav tachometru ze STK/emisí
    mileage_checked_at = Column(DateTime, nullable=True)  # Kdy proběhlo ověření km vůči STK
    latest_stk_odometer_km = Column(Integer, nullable=True)
    latest_stk_odometer_date = Column(DateTime, nullable=True)
    latest_stk_sync_at = Column(DateTime, nullable=True)
    latest_stk_source = Column(String, nullable=True)
    latest_stk_import_status = Column(String, nullable=True)
    tyres_info = Column(Text, nullable=True)  # Informace o pneumatikách
    vehicle_technical_overview = Column(JSON, nullable=True)
    insurance_provider = Column(String, nullable=True)  # Pojišťovna
    insurance_valid_until = Column(Date, nullable=True)  # Datum konce pojištění
    provisioned_by_service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Bez cascade delete-orphan: při mazání vozidla nesmí ORM „utrhnit“ servisní historii.
    records = relationship("ServiceRecord", back_populates="vehicle")


class VehiclePhoto(Base):
    """Deprecated: historická galerie (vehicle_photos). Nové zápisy používají VehiclePhotoAsset."""

    __tablename__ = "vehicle_photos"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    file_path = Column(String(512), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class VehiclePhotoAsset(Base):
    """Source of truth pro hlavní i galerijní fotky vozidla (oddělené per tenant/vehicle)."""

    __tablename__ = "vehicle_photo_assets"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    related_case_id = Column(Integer, ForeignKey("service_intakes.id"), nullable=True, index=True)
    owner_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    role = Column(String(16), nullable=False, index=True)  # main | gallery
    photo_kind = Column(String(64), nullable=False, default="other", index=True)
    vin = Column(String, nullable=True, index=True)
    capture_date = Column(DateTime, nullable=True, index=True)
    storage_key = Column(String(512), nullable=False, index=True)
    storage_path_original = Column(Text, nullable=True)
    storage_path_preview = Column(Text, nullable=True)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(128), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    sha256_hex = Column(String(64), nullable=False, index=True)
    uploaded_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True, index=True)
    sort_order = Column(Integer, nullable=False, default=0)


class VehicleCatalogImage(Base):
    """Cache ilustračních katalogových fotek oddělená od reálných fotek vozidla."""

    __tablename__ = "vehicle_catalog_images"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "image_hash",
            name="uq_vehicle_catalog_images_provider_image_hash",
        ),
    )

    id = Column(String(64), primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    make = Column(String, nullable=False)
    model = Column(String, nullable=False)
    normalized_make = Column(String, nullable=True, index=True)
    normalized_model = Column(String, nullable=True, index=True)
    year = Column(Integer, nullable=True, index=True)
    year_from = Column(Integer, nullable=True)
    year_to = Column(Integer, nullable=True)
    body_type = Column(String, nullable=True, index=True)
    color_bucket = Column(String, nullable=True, index=True)
    image_url = Column(Text, nullable=False)
    thumbnail_url = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    source_domain = Column(String, nullable=True)
    provider = Column(String(32), nullable=False, index=True)
    provider_payload_json = Column(Text, nullable=True)
    image_hash = Column(String(64), nullable=True, index=True)
    score = Column(Integer, nullable=False, default=0, index=True)
    is_representative = Column(Boolean, nullable=False, default=True, index=True)
    is_verified_real_vehicle = Column(Boolean, nullable=False, default=False)
    license_note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True, index=True)


class GlobalAuditLog(Base):
    """Append-only globální audit (akce napříč entitami)."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    actor_type = Column(String(32), nullable=True, index=True)
    actor_id = Column(Integer, nullable=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)
    entity_type = Column(String(64), nullable=False, index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    action = Column(String(128), nullable=False, index=True)
    actor_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    actor_role = Column(String(64), nullable=True)
    before_json = Column(Text, nullable=True)
    after_json = Column(Text, nullable=True)
    ip = Column(String(128), nullable=True)
    user_agent = Column(Text, nullable=True)
    occurred_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    correlation_id = Column(String(128), nullable=True, index=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class VehicleMileage(Base):
    """Historie km vozidla oddělená od servisních záznamů."""
    __tablename__ = "vehicle_mileage"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    mileage_km = Column(Integer, nullable=False)
    source = Column(String(32), nullable=False)  # manual, stk, service, import, service_record
    service_record_id = Column(Integer, ForeignKey("service_records.id"), nullable=True, index=True)
    note = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class VehicleORVScan(Base):
    """Auditní a review vrstva pro skeny ORV před založením / úpravou vozidla."""
    __tablename__ = "vehicle_orv_scans"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    initiated_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)

    source = Column(String, nullable=False, default="ios_orv_scan")
    status = Column(String, nullable=False, default="processing", index=True)
    trust_state = Column(String, nullable=False, default="scanned_unverified", index=True)
    use_owner_data = Column(Boolean, nullable=False, default=False)
    front_captured = Column(Boolean, nullable=False, default=False)
    back_captured = Column(Boolean, nullable=False, default=False)

    orv_number = Column(String, nullable=True, index=True)
    front_image_path = Column(Text, nullable=True)
    back_image_path = Column(Text, nullable=True)
    front_image_hash = Column(String, nullable=True, index=True)
    back_image_hash = Column(String, nullable=True, index=True)

    front_ocr_text = Column(Text, nullable=True)
    back_ocr_text = Column(Text, nullable=True)
    parsed_vehicle_json = Column(Text, nullable=True)
    parsed_owner_json = Column(Text, nullable=True)
    confidence_json = Column(Text, nullable=True)
    warnings_json = Column(Text, nullable=True)
    missing_fields_json = Column(Text, nullable=True)
    extracted_fields_json = Column(Text, nullable=True)
    manual_overrides_json = Column(Text, nullable=True)
    orv_review_audit_json = Column(Text, nullable=True)

    processed_at = Column(DateTime, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class VehicleOwnership(Base):
    """
    Explicitní vazba vlastník <-> vozidlo.
    `vehicles.user_email` zůstává jen jako kompatibilní alias pro staré klienty.
    """
    __tablename__ = "vehicle_ownerships"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    ownership_type = Column(String, nullable=False, default="owner", index=True)  # owner, delegated
    relation_type = Column(String, nullable=False, default="owner", index=True)
    ownership_origin = Column(String, nullable=False, default="manual", index=True)
    acquisition_reason = Column(String(64), nullable=True, index=True)
    deactivation_reason = Column(String(64), nullable=True, index=True)
    transfer_token_id = Column(Integer, ForeignKey("vehicle_transfer_tokens.id"), nullable=True, index=True)
    is_primary = Column(Boolean, nullable=False, default=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    assigned_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    owned_from = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    owned_until = Column(DateTime, nullable=True, index=True)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("vehicle_id", "customer_id", "ownership_type", name="uq_vehicle_owner_assignment"),
    )


class VehicleInspectionHistory(Base):
    """Legacy STK/import history used by PDF reporting and km timelines."""
    __tablename__ = "vehicle_inspection_histories"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    vin = Column(String, nullable=False, index=True)
    inspection_date = Column(DateTime, nullable=True, index=True)
    inspection_type = Column(String, nullable=True)
    inspection_kind = Column(String, nullable=True)
    odometer_km = Column(Integer, nullable=True)
    protocol_number = Column(String, nullable=True, index=True)
    result_label = Column(String, nullable=True)
    defects_text = Column(Text, nullable=True)
    note_text = Column(Text, nullable=True)
    source = Column(String, nullable=False, index=True)
    source_hash = Column(String, nullable=False, index=True)
    imported_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    raw_payload_json = Column(Text, nullable=True)


class VehicleStkImportAuditLog(Base):
    """Audit importů STK/tachometru z externích zdrojů."""
    __tablename__ = "vehicle_stk_import_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    vin = Column(String, nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, index=True)
    message = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class VehicleReportDocument(Base):
    """Persisted metadata for generated PDF/service reports with public verification."""
    __tablename__ = "vehicle_report_documents"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    generated_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    document_type = Column(String, nullable=False, index=True)
    export_mode = Column(String, nullable=False, index=True)
    document_id = Column(String, nullable=False, unique=True, index=True)
    public_token = Column(String, nullable=True, unique=True, index=True)
    verification_code = Column(String, nullable=False, index=True)
    hash_sha256 = Column(String, nullable=False)
    payload_hash_sha256 = Column(String, nullable=False, index=True)
    verification_enabled = Column(Boolean, nullable=False, default=True, index=True)
    status = Column(String, nullable=False, default="valid", index=True)
    version = Column(Integer, nullable=False, default=1)
    schema_version = Column(String, nullable=False, default="2.2")
    finalized_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    finalized_by = Column(String, nullable=True)
    replaced_by_document_id = Column(String, nullable=True, index=True)
    issued_service_name = Column(String, nullable=True)
    vehicle_brand = Column(String, nullable=True)
    vehicle_model = Column(String, nullable=True)
    vehicle_vin_masked = Column(String, nullable=True)
    revoked_at = Column(DateTime, nullable=True, index=True)
    revoked_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class VehicleQrToken(Base):
    """Revokovatelný veřejný QR token vozidla."""
    __tablename__ = "vehicle_qr_tokens"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)

    token = Column(String(255), nullable=False, unique=True, index=True)
    public_mode = Column(String(32), nullable=False, default="basic", index=True)
    explicit_full_consent = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True, index=True)

    issued_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True, index=True)
    last_access_at = Column(DateTime, nullable=True, index=True)
    signature_hash = Column(String(128), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class VehicleQrAccessLog(Base):
    """Audit každého veřejného přístupu přes QR token."""
    __tablename__ = "vehicle_qr_access_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    qr_token_id = Column(Integer, ForeignKey("vehicle_qr_tokens.id"), nullable=False, index=True)

    access_path = Column(String(255), nullable=True)
    access_status = Column(String(64), nullable=False, default="ok", index=True)
    public_mode = Column(String(32), nullable=False, default="basic")
    access_signature_valid = Column(Boolean, nullable=False, default=True)
    remote_addr = Column(String(128), nullable=True)
    user_agent = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class ServiceRecord(Base):
    __tablename__ = "service_records"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)  # ID uživatele, který záznam vytvořil
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    service_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    work_order_id = Column(Integer, ForeignKey("service_work_orders.id"), nullable=True, index=True)
    quote_id = Column(Integer, ForeignKey("service_quotes.id"), nullable=True, index=True)
    performed_at = Column(DateTime, default=datetime.utcnow)
    mileage = Column(Integer, nullable=True)
    description = Column(String, nullable=False)
    price = Column(Float, nullable=True)
    note = Column(String, nullable=True)
    category = Column(String, nullable=True)  # Kategorie servisu (např. "Pravidelná údržba", "Oprava", "Výměna oleje")
    attachments = Column(Text, nullable=True)  # JSON string s přílohami
    next_service_due_date = Column(Date, nullable=True)  # Datum dalšího plánovaného servisu
    record_status = Column(String(32), nullable=False, default="draft", index=True)
    service_type = Column(String(64), nullable=True)
    recommended_next_service_text = Column(Text, nullable=True)
    recommended_next_service_date = Column(Date, nullable=True)
    notes_customer_visible = Column(Text, nullable=True)
    total_price = Column(Float, nullable=True)
    created_by_ai = Column(Boolean, default=False, nullable=False)  # True pokud byl záznam vytvořen AI asistentem
    created_by_service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    service_access_link_id = Column(Integer, ForeignKey("vehicle_service_links.id"), nullable=True, index=True)
    origin = Column(String(32), nullable=False, default="user_manual", index=True)
    service_case_id = Column(Integer, ForeignKey("service_intakes.id"), nullable=True, index=True)
    labor_seconds = Column(Integer, nullable=True)
    recommended_next_service_km = Column(Integer, nullable=True)
    visibility_scope = Column(String(32), nullable=False, default="full_current_owner", index=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True, index=True)
    deleted_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    deletion_reason = Column(Text, nullable=True)
    snapshot_hash = Column(String, nullable=True, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    vehicle = relationship("Vehicle", back_populates="records")


class VehicleTachometerHistoryEntry(Base):
    """Sekundární důkazní evidence importů STK / tachometru."""
    __tablename__ = "vehicle_tachometer_history_entries"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)

    check_date = Column(DateTime, nullable=True, index=True)
    mileage_km = Column(Integer, nullable=True)
    protocol_number = Column(String, nullable=True, index=True)
    inspection_type = Column(String, nullable=True)
    source = Column(String, nullable=False, default="kontrolatachometru.cz")
    status = Column(String, nullable=False, default="imported", index=True)
    read_only = Column(Boolean, nullable=False, default=True, index=True)
    summary = Column(Text, nullable=True)
    findings_summary = Column(Text, nullable=True)
    findings_items_json = Column(Text, nullable=True)
    detail_snapshot_json = Column(Text, nullable=True)
    source_detail_reference = Column(Text, nullable=True)
    documents_json = Column(Text, nullable=True)  # JSON list reprezentující dostupné / nedostupné dokumenty
    raw_payload_json = Column(Text, nullable=True)  # Persistovaná metadata importovaného řádku
    imported_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "vehicle_id",
            "check_date",
            "mileage_km",
            "protocol_number",
            name="uq_vehicle_tachometer_history_entry",
        ),
    )


class ServiceRecordAuditLog(Base):
    """
    Minimální audit trail pro změny servisních záznamů.
    Uchovává snapshot před úpravou (interim řešení pro AUD-HIGH-007).
    """
    __tablename__ = "service_record_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_record_id = Column(Integer, ForeignKey("service_records.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    changed_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    action = Column(String, nullable=False, default="update")
    previous_snapshot_json = Column(Text, nullable=False)
    new_snapshot_json = Column(Text, nullable=True)
    snapshot_hash = Column(String, nullable=True, index=True)
    change_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class ServiceWorkOrder(Base):
    """Produkční servisní zakázka svázaná se zákazníkem, vozidlem a technikem."""
    __tablename__ = "service_work_orders"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    owner_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    technician_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    source_type = Column(String(32), nullable=False, default="manual", index=True)
    source_reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=True, index=True)
    source_document_id = Column(Integer, ForeignKey("service_document_ingestions.id"), nullable=True, index=True)
    source_intake_id = Column(Integer, ForeignKey("service_intakes.id"), nullable=True, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(64), nullable=False, default="awaiting_client_approval", index=True)
    due_date = Column(Date, nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    approved_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class ServiceWorkOrderAuditLog(Base):
    """Append-only audit trail servisních zakázek."""
    __tablename__ = "service_work_order_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    work_order_id = Column(Integer, ForeignKey("service_work_orders.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    changed_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    action = Column(String(64), nullable=False, default="update", index=True)
    previous_snapshot_json = Column(Text, nullable=False)
    new_snapshot_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class ServiceWorkOrderItem(Base):
    """Položka servisní zakázky: práce, materiál nebo ostatní náklad."""
    __tablename__ = "service_work_order_items"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    work_order_id = Column(Integer, ForeignKey("service_work_orders.id"), nullable=False, index=True)
    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)

    item_type = Column(String(32), nullable=False, index=True)
    name = Column(String(512), nullable=False)
    code = Column(String(128), nullable=True, index=True)
    quantity = Column(Float, nullable=False, default=1)
    unit = Column(String(32), nullable=False, default="ks")
    vat_rate = Column(Float, nullable=False, default=21)
    purchase_price_without_vat = Column(Float, nullable=True)
    sale_price_without_vat = Column(Float, nullable=False, default=0)
    discount_percent = Column(Float, nullable=False, default=0)
    note = Column(Text, nullable=True)
    mechanic_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    source = Column(String(32), nullable=False, default="manual", index=True)
    created_by = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)

    deleted_at = Column(DateTime, nullable=True, index=True)
    deleted_by = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceWorkOrderCsvImport(Base):
    """Auditní hlavička CSV importu dílů do servisní zakázky."""
    __tablename__ = "service_work_order_csv_imports"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    work_order_id = Column(Integer, ForeignKey("service_work_orders.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)

    filename = Column(String(255), nullable=True)
    delimiter = Column(String(8), nullable=False)
    rows_count = Column(Integer, nullable=False, default=0)
    imported_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    duplicate_count = Column(Integer, nullable=False, default=0)
    error_rows_json = Column(Text, nullable=True)
    mapping_json = Column(Text, nullable=True)
    file_sha256 = Column(String(64), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class ServiceQuote(Base):
    """Cenová nabídka navázaná na existující servisní zakázku nebo záznam."""
    __tablename__ = "service_quotes"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    service_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    work_order_id = Column(Integer, ForeignKey("service_work_orders.id"), nullable=True, index=True)
    service_record_id = Column(Integer, nullable=True, index=True)

    items_json = Column(Text, nullable=True)
    labor_hours = Column(Float, nullable=True)
    labor_rate = Column(Float, nullable=True)
    total_price = Column(Float, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="draft", index=True)
    approved_at = Column(DateTime, nullable=True, index=True)
    rejected_at = Column(DateTime, nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceQuoteAuditLog(Base):
    """Append-only audit trail změn nabídek."""
    __tablename__ = "service_quote_audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    quote_id = Column(Integer, ForeignKey("service_quotes.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    changed_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    action = Column(String(64), nullable=False, default="update", index=True)
    previous_snapshot_json = Column(Text, nullable=False)
    new_snapshot_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class ServiceQuoteAccessToken(Base):
    """Bezpečný veřejný token pro zákaznický náhled a rozhodnutí nad nabídkou."""
    __tablename__ = "service_quote_access_tokens"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    quote_id = Column(Integer, ForeignKey("service_quotes.id"), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)

    token = Column(String(255), nullable=False, unique=True, index=True)
    issued_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    revoked_at = Column(DateTime, nullable=True, index=True)
    last_access_at = Column(DateTime, nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceQuoteAccessLog(Base):
    """Append-only audit veřejného čtení a rozhodnutí zákazníka nad nabídkou."""
    __tablename__ = "service_quote_access_logs"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    quote_id = Column(Integer, ForeignKey("service_quotes.id"), nullable=False, index=True)
    quote_access_token_id = Column(Integer, ForeignKey("service_quote_access_tokens.id"), nullable=True, index=True)
    action = Column(String(64), nullable=False, index=True)
    remote_addr = Column(String(128), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class ServiceInvoiceCounter(Base):
    """Per-tenant monotonic sequence for service invoice numbers (allocated on issue)."""
    __tablename__ = "service_invoice_counters"

    tenant_id = Column(Integer, ForeignKey("tenants.id"), primary_key=True, index=True)
    next_seq = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceInvoice(Base):
    """Servisní faktura (first-class, vystavovatel = service Customer)."""
    __tablename__ = "service_invoices"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)
    service_record_id = Column(Integer, ForeignKey("service_records.id"), nullable=True, index=True)
    work_order_id = Column(Integer, ForeignKey("service_work_orders.id"), nullable=True, index=True)

    invoice_number = Column(String(64), nullable=True, unique=True, index=True)
    status = Column(String(32), nullable=False, default="draft", index=True)  # draft | issued | cancelled

    subtotal = Column(Float, nullable=False, default=0)
    tax_total = Column(Float, nullable=False, default=0)
    total = Column(Float, nullable=False, default=0)
    currency = Column(String(8), nullable=False, default="CZK")

    issued_at = Column(DateTime, nullable=True, index=True)
    due_at = Column(DateTime, nullable=True, index=True)
    cancelled_at = Column(DateTime, nullable=True, index=True)
    notes = Column(Text, nullable=True)
    extra_json = Column(Text, nullable=True)

    fakturyweb_code = Column(String(128), nullable=True, index=True)
    fakturyweb_number = Column(String(64), nullable=True, index=True)
    fakturyweb_status = Column(String(64), nullable=True)
    fakturyweb_pdf_url = Column(Text, nullable=True)
    fakturyweb_exported_at = Column(DateTime, nullable=True, index=True)
    fakturyweb_last_sync_at = Column(DateTime, nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceInvoiceLine(Base):
    __tablename__ = "service_invoice_lines"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("service_invoices.id"), nullable=False, index=True)

    description = Column(String(512), nullable=False)
    quantity = Column(Float, nullable=False, default=1)
    unit = Column(String(32), nullable=False, default="ks")
    unit_price = Column(Float, nullable=False, default=0)
    tax_rate = Column(Float, nullable=False, default=0)  # percent
    line_total = Column(Float, nullable=False, default=0)  # net + tax (server-computed)

    sort_order = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ServiceIntake(Base):
    """Příjem vozidla v servisu"""
    __tablename__ = "service_intakes"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    service_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)  # ID servisu (Customer s role='service')
    service_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    service_access_request_id = Column(Integer, ForeignKey("service_access_requests.id"), nullable=True, index=True)
    service_access_link_id = Column(Integer, ForeignKey("vehicle_service_links.id"), nullable=True, index=True)
    intake_status = Column(String(64), nullable=False, default="draft", index=True)
    intake_source = Column(String(64), nullable=False, default="manual_search", index=True)
    intake_spz_raw = Column(String, nullable=True)
    intake_spz_normalized = Column(String, nullable=True, index=True)
    intake_photo_asset_id = Column(Integer, ForeignKey("vehicle_photo_assets.id"), nullable=True, index=True)
    ocr_confidence = Column(Float, nullable=True)
    owner_approval_required = Column(Boolean, nullable=False, default=True, index=True)
    owner_approval_status = Column(String(32), nullable=False, default="not_requested", index=True)
    check_in_at = Column(DateTime, nullable=True, index=True)
    work_started_at = Column(DateTime, nullable=True, index=True)
    work_finished_at = Column(DateTime, nullable=True, index=True)
    total_labor_seconds = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    
    odometer_km = Column(Integer, nullable=True)
    fluids_ok = Column(Text, nullable=True)  # JSON string
    damage_description = Column(Text, nullable=True)
    photos = Column(Text, nullable=True)  # JSON string s listem URL
    work_description = Column(Text, nullable=True)
    signature = Column(Text, nullable=True)

    # Servisní případ (fasáda service-cases API) — rozšíření oproti historickému příjmu
    customer_request = Column(Text, nullable=True)
    intake_note = Column(Text, nullable=True)
    diagnosis_summary = Column(Text, nullable=True)
    repair_summary = Column(Text, nullable=True)
    internal_note = Column(Text, nullable=True)
    visible_to_owner_note = Column(Text, nullable=True)
    mileage_out = Column(Integer, nullable=True)
    mileage_source = Column(String(64), nullable=True)
    intake_completed_at = Column(DateTime, nullable=True)
    diagnosis_started_at = Column(DateTime, nullable=True)
    diagnosis_completed_at = Column(DateTime, nullable=True)
    handed_over_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceLaborSession(Base):
    """Zdrojové start/stop intervaly práce technika na servisním případu."""
    __tablename__ = "service_labor_sessions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_case_id = Column(Integer, ForeignKey("service_intakes.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)
    service_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    technician_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    started_at = Column(DateTime, nullable=False, index=True)
    stopped_at = Column(DateTime, nullable=True, index=True)
    duration_seconds = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class VehicleTransferToken(Base):
    """Hashovaný token pro bezpečné předání vozidla novému vlastníkovi."""
    __tablename__ = "vehicle_transfer_tokens"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    issued_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    transfer_reason = Column(String(64), nullable=False, default="sale", index=True)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    qr_payload = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    claimed_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    claimed_at = Column(DateTime, nullable=True, index=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class VehicleRemovalEvent(Base):
    """Řízené ukončení aktivní evidence vozidla bez ztráty historie."""
    __tablename__ = "vehicle_removal_events"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    initiated_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    reason_code = Column(String(64), nullable=False, index=True)
    required_followup_answer_json = Column(Text, nullable=False)
    digital_report_document_id = Column(Integer, ForeignKey("vehicle_report_documents.id"), nullable=True, index=True)
    archive_bundle_path = Column(Text, nullable=True)
    transfer_token_id = Column(Integer, ForeignKey("vehicle_transfer_tokens.id"), nullable=True, index=True)
    executed_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class Reservation(Base):
    """Rezervace v servisu"""
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    service_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)  # ID servisu (Customer s role='service')
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    
    service_type = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    start_datetime = Column(DateTime, nullable=False)
    end_datetime = Column(DateTime, nullable=True)
    status = Column(String, default="PENDING", nullable=False)  # PENDING, CONFIRMED, CANCELLED
    source_platform = Column(String, nullable=True)  # ios_app / web_browser / ...
    
    created_at = Column(DateTime, default=datetime.utcnow)


class Reminder(Base):
    """Připomínky pro uživatele"""
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)
    
    type = Column(String, nullable=False)  # STK, OLEJ, SERVIS, VLASTNI, GENERAL
    text = Column(Text, nullable=False)
    due_date = Column(Date, nullable=True)
    notify_at = Column(DateTime, nullable=True)  # Přesný termín notifikace (datum + čas)
    notification_method = Column(String, nullable=True)  # app, email, both (None = dle globálního nastavení)
    last_notified_at = Column(DateTime, nullable=True)  # Kdy byla notifikace naposledy odeslána
    is_manual = Column(Boolean, default=False, nullable=False)  # True = ruční, False = automatická
    is_completed = Column(Boolean, default=False, nullable=False)
    recurrence_group_id = Column(String, nullable=True, index=True)  # Identifikátor série opakovaných připomínek
    recurrence_index = Column(Integer, nullable=False, default=0)  # Pořadí v sérii (0 = první výskyt)
    repeat_interval_days = Column(Integer, nullable=True)  # Interval opakování ve dnech pro sérii
    
    created_at = Column(DateTime, default=datetime.utcnow)


class License(Base):
    """Licence pro tenant - quota a feature flags"""
    __tablename__ = "licenses"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), unique=True, nullable=False, index=True)
    
    plan = Column(String, nullable=False, default="free")  # "free", "basic", "premium"
    status = Column(String, nullable=False, default="active")  # "active", "inactive"
    
    vehicles_limit = Column(Integer, nullable=False, default=1)  # free=1, basic=3, premium=0 (0 = unlimited)
    
    valid_from = Column(DateTime, nullable=False, default=datetime.utcnow)
    valid_to = Column(DateTime, nullable=True)

    trial_started_at = Column(DateTime, nullable=True)
    trial_ends_at = Column(DateTime, nullable=True)
    trial_used_at = Column(DateTime, nullable=True)
    trial_source = Column(String(64), nullable=True)
    trial_plan = Column(String(32), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Feature flags (volitelné, pro budoucí použití)
    vin_decode_enabled = Column(Boolean, nullable=False, default=True)
    ares_enabled = Column(Boolean, nullable=False, default=True)
    reminders_enabled = Column(Boolean, nullable=False, default=True)
    
    __table_args__ = (
        UniqueConstraint('tenant_id', name='uq_license_tenant_id'),
    )


class LicenseSubscription(Base):
    """Stav předplatného licence (Comgate recurring lifecycle)."""
    __tablename__ = "license_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), unique=True, nullable=False, index=True)

    provider = Column(String, nullable=False, default="comgate", index=True)
    status = Column(
        String,
        nullable=False,
        default="legacy_manual",
        index=True,
    )  # active, cancel_at_period_end, grace, canceled, legacy_manual

    plan_current = Column(String, nullable=True, index=True)  # free, basic, premium
    billing_period = Column(String, nullable=True)  # monthly, yearly

    auto_renew_enabled = Column(Boolean, nullable=False, default=False)
    pending_plan_change = Column(String, nullable=True)  # free/basic/premium

    init_recurring_id = Column(String, nullable=True, index=True)
    provider_init_transaction_id = Column(String, nullable=True, index=True)
    recurring_ready = Column(Boolean, nullable=False, default=False)
    recurring_block_reason = Column(String, nullable=True)

    # Kreditní saldo v haléřích:
    # kladné = kredit uživatele, záporné = nedoplatek/debt.
    credit_balance_halers = Column(Integer, nullable=False, default=0)

    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True, index=True)
    next_charge_at = Column(DateTime, nullable=True, index=True)
    grace_until = Column(DateTime, nullable=True, index=True)

    cancel_requested_at = Column(DateTime, nullable=True)
    last_payment_at = Column(DateTime, nullable=True)
    last_trans_id = Column(String, nullable=True)
    last_recurring_attempt_at = Column(DateTime, nullable=True)
    last_recurring_result = Column(String, nullable=True)
    failed_renewal_attempts = Column(Integer, nullable=False, default=0)

    # Dedup notifikačních odeslání
    notified_first_payment_at = Column(DateTime, nullable=True)
    notified_renewal_failed_at = Column(DateTime, nullable=True)
    notified_grace_end_at = Column(DateTime, nullable=True)
    notified_period_d14_at = Column(DateTime, nullable=True)
    notified_period_d7_at = Column(DateTime, nullable=True)
    notified_period_d1_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_license_subscription_tenant_id"),
    )


class LicensePaymentTransaction(Base):
    """Audit + idempotence platebních událostí licencí."""
    __tablename__ = "license_payment_transactions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    subscription_id = Column(Integer, ForeignKey("license_subscriptions.id"), nullable=True, index=True)

    provider = Column(String, nullable=False, default="comgate", index=True)
    trans_id = Column(String, nullable=True, unique=True, index=True)
    ref_id = Column(String, nullable=True, index=True)
    payment_type = Column(String, nullable=True, index=True)
    parent_provider_transaction_id = Column(String, nullable=True, index=True)
    parent_init_recurring_id = Column(String, nullable=True, index=True)

    plan = Column(String, nullable=True, index=True)
    billing_period = Column(String, nullable=True)
    period_start = Column(DateTime, nullable=True, index=True)
    period_end = Column(DateTime, nullable=True, index=True)

    amount_halers = Column(Integer, nullable=True)
    currency = Column(String, nullable=True, default="CZK")
    event_type = Column(String, nullable=False, default="unknown", index=True)
    provider_status = Column(String, nullable=True, index=True)
    raw_provider_payload_hash = Column(String(64), nullable=True, index=True)
    provider_response_code = Column(String(64), nullable=True)
    provider_response_message = Column(Text, nullable=True)

    payload_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PaymentEvent(Base):
    """Sanitized provider events for idempotent billing audit."""
    __tablename__ = "payment_events"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("license_payment_transactions.id"), nullable=True, index=True)

    provider = Column(String, nullable=False, default="comgate", index=True)
    event_type = Column(String, nullable=False, index=True)
    provider_transaction_id = Column(String, nullable=True, index=True)
    payload_hash = Column(String(64), nullable=True, index=True)
    sanitized_payload_json = Column(Text, nullable=True)
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed_at = Column(DateTime, nullable=True, index=True)
    processing_status = Column(String, nullable=False, default="received", index=True)
    error_message = Column(Text, nullable=True)


class LicenseAuditLog(Base):
    """Dedicated billing/license lifecycle audit."""
    __tablename__ = "license_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    subscription_id = Column(Integer, ForeignKey("license_subscriptions.id"), nullable=True, index=True)
    action = Column(String(128), nullable=False, index=True)
    old_status = Column(String(64), nullable=True)
    new_status = Column(String(64), nullable=True)
    reason = Column(Text, nullable=True)
    actor_type = Column(String(32), nullable=False, default="system", index=True)
    ip_address = Column(String(128), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class EmailNotificationLog(Base):
    """Log odeslaných e-mail notifikací"""
    __tablename__ = "email_notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    email = Column(String, nullable=False, index=True)
    subject = Column(String, nullable=False)
    notification_type = Column(String, nullable=False)  # reminder, reservation, etc.
    entity_id = Column(Integer, nullable=True)  # ID připomínky, rezervace, atd.
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String, default="sent", nullable=False)  # sent, failed
    error_message = Column(Text, nullable=True)


class PushSubscription(Base):
    """Web Push subscription pro notifikace v prohlížeči."""
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)
    user_agent = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False, index=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SecurityAccessLog(Base):
    """Bezpecnostni log pristupu (login pokusy + IP/lokalita)."""
    __tablename__ = "security_access_logs"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    user_email = Column(String, nullable=True, index=True)

    event_type = Column(String, nullable=False, index=True)  # login_success, login_failed, login_rate_limited
    endpoint = Column(String, nullable=True, index=True)

    ip_address = Column(String, nullable=True, index=True)
    country = Column(String, nullable=True)
    region = Column(String, nullable=True)
    city = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    timezone = Column(String, nullable=True)
    isp = Column(String, nullable=True)
    source = Column(String, nullable=True)  # source geolokace (napr. ipwho.is, private)

    user_agent = Column(String, nullable=True)
    details = Column(Text, nullable=True)  # JSON string s doplnkovymi metadaty

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class AdminCustomerChangeEvent(Base):
    """
    Změny účtu provedené z developer adminu — přehled pro e-mailovou informaci uživatele.
    Každý řádek = jedna logická změna; notified_at vyplní odeslání souhrnu.
    """

    __tablename__ = "admin_customer_change_events"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    admin_email = Column(String(255), nullable=True, index=True)
    change_key = Column(String(128), nullable=False, index=True)
    summary_line = Column(Text, nullable=False)
    detail_text = Column(Text, nullable=True)
    payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    notified_at = Column(DateTime, nullable=True, index=True)
    notified_to_email = Column(String(255), nullable=True)


class DeveloperActionAuditLog(Base):
    """
    Immutabilní audit log vývojářských/admin akcí.
    Záznamy jsou append-only (bez API pro mazání).
    """
    __tablename__ = "developer_action_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    developer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    developer_email = Column(String, nullable=True, index=True)

    action_type = Column(String, nullable=False, index=True)
    target_resource = Column(String, nullable=False, index=True)
    parameters_json = Column(Text, nullable=True)

    result = Column(String, nullable=False, default="success", index=True)  # success, failed, blocked
    status_code = Column(Integer, nullable=True)

    request_ip = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class DemoAccessLead(Base):
    """Kontakt a audit veřejného přístupu k ukázkovému účtu (email + IP, souhlas)."""

    __tablename__ = "demo_access_leads"

    id = Column(Integer, primary_key=True, index=True)
    visitor_email = Column(String(255), nullable=False, index=True)
    client_ip = Column(String(128), nullable=True, index=True)
    user_agent = Column(Text, nullable=True)
    contact_consent = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class DemoAccessToken(Base):
    """Jednorázový odkaz do ukázky: e-mail + IP při žádosti, náhodný token (hash v DB)."""

    __tablename__ = "demo_access_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    visitor_email = Column(String(255), nullable=False, index=True)
    request_ip = Column(String(128), nullable=True, index=True)
    user_agent = Column(Text, nullable=True)
    contact_consent = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    consumed_at = Column(DateTime, nullable=True)


class SecurityBlockedIp(Base):
    """Manuální blokace IP adresy pro bezpečnostní zásahy."""
    __tablename__ = "security_blocked_ips"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, nullable=False, unique=True, index=True)
    reason = Column(Text, nullable=True)

    blocked_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    blocked_by_email = Column(String, nullable=True, index=True)
    blocked_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)

    is_active = Column(Boolean, default=True, nullable=False, index=True)

    unblocked_at = Column(DateTime, nullable=True)
    unblocked_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    unblocked_by_email = Column(String, nullable=True, index=True)


class SystemNotification(Base):
    """Systémové oznámení (broadcast) cílené na uživatele/tenant/plán."""
    __tablename__ = "system_notifications"

    id = Column(Integer, primary_key=True, index=True)

    target_type = Column(String, nullable=False, default="all", index=True)  # all | tenant | plan | user
    target_value = Column(String, nullable=True, index=True)  # tenant_id / plan / user_id

    title = Column(String, nullable=True)
    message = Column(Text, nullable=False)
    severity = Column(String, nullable=False, default="info", index=True)  # info | warning | critical

    starts_at = Column(DateTime, nullable=True, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    created_by_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    created_by_email = Column(String, nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class VersionHistory(Base):
    """Historie verzí aplikace"""
    __tablename__ = "version_history"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    applied_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class VehicleTypeTemplate(Base):
    """Šablona pro typ vozidla - ukládá standardní hodnoty pro konkrétní typ vozidla"""
    __tablename__ = "vehicle_type_templates"

    id = Column(Integer, primary_key=True, index=True)
    make = Column(String, nullable=False, index=True)  # Tovární značka
    model = Column(String, nullable=False, index=True)  # Model
    engine_code = Column(String, nullable=True, index=True)  # Kód motoru
    production_year = Column(Integer, nullable=True, index=True)  # Rok výroby
    type_label = Column(String, nullable=True)  # Typ / Varianta / Verze
    
    wheels_and_tyres = Column(Text, nullable=True)  # Standardní rozměry kol a pneumatik
    extra_records = Column(Text, nullable=True)  # Dodatečné záznamy (JSON)
    default_notes = Column(Text, nullable=True)  # Výchozí poznámky
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BotCommand(Base):
    """
    Model pro logování a zpracování příkazů AI asistenta
    
    ARCHITEKTURA BOTA:
    - BotCommand ukládá všechny příkazy uživatelů a jejich zpracování
    - Každý příkaz má intent_type (např. "create_task", "add_note", "create_reminder")
    - Status sleduje stav zpracování: "received" -> "processed" / "failed"
    - result_message obsahuje odpověď bota uživateli
    - error_message obsahuje chybu, pokud se něco pokazilo
    
    BEZPEČNOST:
    - Bot může provádět pouze explicitně naprogramované akce
    - Všechny akce jsou logovány v této tabulce
    - Každá akce má zjistitelný intent_type a status
    
    ROZŠÍŘENÍ:
    - V budoucnu se zde může přidat napojení na OpenAI/Claude API
    - Intent detection může být přesnější pomocí AI modelu
    - Akce mohou být rozšířeny o další typy (např. "update_vehicle", "delete_record")
    """
    __tablename__ = "bot_commands"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    # Identifikace uživatele a session
    user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)  # ID uživatele (pokud je přihlášen)
    user_email = Column(String, nullable=True, index=True)  # Email uživatele (pro případ, že není v DB)
    user_role = Column(String, nullable=True)  # Role uživatele (např. "owner", "customer", "admin")
    session_id = Column(String, nullable=True, index=True)  # Session ID pro spojení zpráv z jedné konverzace
    
    # Příkaz a jeho zpracování
    raw_text = Column(Text, nullable=False)  # Původní text příkazu od uživatele
    intent_type = Column(String, nullable=True, index=True)  # Typ záměru: "create_task", "add_note", "create_reminder", "unknown", atd.
    status = Column(String, default="received", nullable=False, index=True)  # Status: "received", "processing", "processed", "failed"
    
    # Výsledek zpracování
    result_message = Column(Text, nullable=True)  # Odpověď bota uživateli
    error_message = Column(Text, nullable=True)  # Chyba, pokud se něco pokazilo
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    processed_at = Column(DateTime, nullable=True)  # Kdy byl příkaz zpracován
    
    # Vztah k uživateli (pokud existuje)
    customer = relationship("Customer", foreign_keys=[user_id])


class CustomerCommand(Base):
    """
    Model pro příkazy zákazníků (Command Bot v1)
    
    Tento model ukládá příkazy od zákazníků z různých zdrojů (web chat, autopilot, atd.)
    a jejich zpracování pomocí jednoduchého intent engine.
    
    ROZLIŠENÍ OD BotCommand:
    - BotCommand je pro interní AI asistenta (přihlášení uživatelé)
    - CustomerCommand je pro externí příkazy zákazníků (mohou být anonymní)
    
    V1 FUNKCIONALITA:
    - Jednoduché pravidlo-based rozpoznávání intencí (intent_type)
    - Automatické vytváření úkolů/rezervací/poznámek podle typu
    - Příprava na budoucí AI integraci (normalized_text pole)
    """
    __tablename__ = "customer_commands"

    id = Column(Integer, primary_key=True, index=True)
    
    # Multi-tenant podpora
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Zdroj příkazu
    source = Column(String, nullable=False, index=True)  # "web_chat", "autopilot", "internal"
    
    # Identifikace zákazníka (může být anonymní)
    customer_name = Column(String, nullable=True)
    customer_email = Column(String, nullable=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True, index=True)
    
    # Text příkazu
    raw_text = Column(Text, nullable=False)  # Celý text, co zákazník napsal
    normalized_text = Column(Text, nullable=True)  # Připravené pole pro pozdější AI/normalizaci
    
    # Rozpoznání záměru
    intent_type = Column(String, nullable=False, index=True)  # "CREATE_BOOKING", "CREATE_TASK", "ADD_NOTE", "QUESTION", "UNKNOWN"
    
    # Status zpracování
    status = Column(String, default="RECEIVED", nullable=False, index=True)  # "RECEIVED", "EXECUTED", "FAILED"
    
    # Výsledek zpracování
    result_summary = Column(Text, nullable=True)  # Stručně, co se stalo – "vytvořen úkol #123"
    error_message = Column(Text, nullable=True)  # Chybová zpráva, pokud se něco pokazilo
    
    # Vztahy
    vehicle = relationship("Vehicle", foreign_keys=[vehicle_id])


class UserTutorialProgress(Base):
    """Stav dokončení interaktivních návodů (bez vozidlových osobních údajů)."""

    __tablename__ = "user_tutorial_progress"
    __table_args__ = (
        UniqueConstraint("customer_id", "tutorial_id", name="uq_user_tutorial_progress_customer_tutorial"),
    )

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    tutorial_id = Column(String(96), nullable=False, index=True)
    step_id = Column(String(160), nullable=True)
    status = Column(String(32), nullable=False, index=True)  # in_progress | completed | skipped
    last_failure_code = Column(String(80), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    customer = relationship("Customer", foreign_keys=[customer_id])


class TutorialAuditLog(Base):
    """Auditní záznamy návodů (metadata bez VIN/SPZ/obsahu formulářů)."""

    __tablename__ = "tutorial_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    tutorial_id = Column(String(96), nullable=False, index=True)
    step_id = Column(String(160), nullable=True, index=True)
    status = Column(String(48), nullable=False, index=True)
    failure_code = Column(String(80), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    customer = relationship("Customer", foreign_keys=[customer_id])


class ServiceFakturywebSettings(Base):
    """Izolované nastavení FakturyWeb API pro testovací workspace integraci (servis)."""

    __tablename__ = "service_fakturyweb_settings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "service_workspace_id", name="uq_service_fakturyweb_settings_tenant_workspace"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_workspace_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)

    email = Column(String(320), nullable=False)
    encrypted_api_key = Column(Text, nullable=False)
    api_key_mask = Column(String(64), nullable=True)

    supplier_mode = Column(String(32), nullable=False, default="manual")  # saved_company | manual
    d_id = Column(String(64), nullable=True)

    default_due_days = Column(Integer, nullable=False, default=7)
    default_payment = Column(String(32), nullable=False, default="prevod")
    default_currency = Column(String(16), nullable=False, default="Kč")
    default_style = Column(String(32), nullable=False, default="styl_7")
    default_qr = Column(Integer, nullable=False, default=1)
    test_mode_default = Column(Boolean, nullable=False, default=True)

    custom_d_name = Column(String(255), nullable=True)
    custom_d_street = Column(String(255), nullable=True)
    custom_d_city = Column(String(255), nullable=True)
    custom_d_zip = Column(String(32), nullable=True)
    custom_d_state = Column(String(64), nullable=True)
    custom_d_ico = Column(String(32), nullable=True)
    custom_d_dic = Column(String(32), nullable=True)
    custom_d_email = Column(String(320), nullable=True)
    custom_d_phone = Column(String(64), nullable=True)
    custom_d_web = Column(String(255), nullable=True)
    custom_d_bankaccount = Column(String(128), nullable=True)

    last_test_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceFakturywebInvoice(Base):
    """Lokální záznam testovací faktury vytvořené přes FakturyWeb API (E2E test sekce)."""

    __tablename__ = "service_fakturyweb_invoices"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    service_workspace_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)

    fakturyweb_code = Column(String(128), nullable=False, index=True)
    fakturyweb_number = Column(String(64), nullable=True, index=True)
    test_mode = Column(Boolean, nullable=False, default=True)

    customer_name = Column(String(512), nullable=True)
    customer_email = Column(String(320), nullable=True)

    issue_date = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    amount_estimated = Column(Numeric(12, 2), nullable=True)

    local_status = Column(String(32), nullable=False, default="created", index=True)
    remote_status_raw = Column(Text, nullable=True)
    pdf_url = Column(Text, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ServiceFakturywebAuditLog(Base):
    """Audit volání FakturyWeb workspace API (bez citlivých dat)."""

    __tablename__ = "service_fakturyweb_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)

    action = Column(String(64), nullable=False, index=True)
    local_invoice_id = Column(Integer, ForeignKey("service_fakturyweb_invoices.id"), nullable=True, index=True)

    endpoint = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=False, index=True)
    response_status = Column(String(32), nullable=True)
    response_status_id = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

class SupportSession(Base):
    __tablename__ = "support_sessions"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    status = Column(String(20), default="active", index=True) # active, closed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer")
    messages = relationship("SupportMessage", back_populates="session", cascade="all, delete-orphan")

class SupportMessage(Base):
    __tablename__ = "support_messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("support_sessions.id"), nullable=False, index=True)
    sender_type = Column(String(20), nullable=False) # 'user' or 'admin'
    sender_id = Column(Integer, nullable=True) # customer_id or admin_id
    message = Column(String, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("SupportSession", back_populates="messages")


class ServiceLocation(Base):
    """Veřejný katalog servisních míst (mapa servisů) – odděleno od dat vozidel a majitelů."""

    __tablename__ = "service_locations"

    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String(32), nullable=False, index=True)
    source_external_id = Column(String(128), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    normalized_name = Column(String(255), nullable=True, index=True)
    category = Column(String(32), nullable=False, index=True)
    lat = Column(Float, nullable=False, index=True)
    lng = Column(Float, nullable=False, index=True)
    address_text = Column(String(512), nullable=True)
    street = Column(String(255), nullable=True)
    city = Column(String(128), nullable=True, index=True)
    postal_code = Column(String(16), nullable=True)
    region = Column(String(128), nullable=True)
    district = Column(String(128), nullable=True)
    phone = Column(String(64), nullable=True)
    email = Column(String(255), nullable=True)
    website = Column(String(512), nullable=True)
    opening_hours = Column(Text, nullable=True)
    services_json = Column(Text, nullable=True)
    vehicle_scope_json = Column(Text, nullable=True)
    verification_status = Column(String(32), nullable=False, default="imported", index=True)
    confidence_score = Column(Float, nullable=True)
    last_imported_at = Column(DateTime, nullable=True)
    last_verified_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    linked_service_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    sources = relationship("ServiceLocationSource", back_populates="service_location", cascade="all, delete-orphan")
    claims = relationship("ServiceLocationClaim", back_populates="service_location", cascade="all, delete-orphan")
    reports = relationship("ServiceLocationReport", back_populates="service_location", cascade="all, delete-orphan")


class ServiceLocationSource(Base):
    __tablename__ = "service_location_sources"

    id = Column(Integer, primary_key=True, index=True)
    service_location_id = Column(Integer, ForeignKey("service_locations.id"), nullable=False, index=True)
    source_type = Column(String(32), nullable=False)
    source_external_id = Column(String(128), nullable=True)
    raw_payload_hash = Column(String(64), nullable=True, index=True)
    raw_payload_json = Column(Text, nullable=True)
    import_batch_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    service_location = relationship("ServiceLocation", back_populates="sources")


class ServiceLocationClaim(Base):
    __tablename__ = "service_location_claims"

    id = Column(Integer, primary_key=True, index=True)
    service_location_id = Column(Integer, ForeignKey("service_locations.id"), nullable=False, index=True)
    service_tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    claim_status = Column(String(32), nullable=False, default="pending", index=True)
    claim_method = Column(String(32), nullable=True)
    ico = Column(String(16), nullable=True)
    dic = Column(String(16), nullable=True)
    business_name = Column(String(255), nullable=True)
    submitted_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    approved_by_admin_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    approved_at = Column(DateTime, nullable=True)
    fraud_flags_json = Column(Text, nullable=True)
    audit_hash = Column(String(64), nullable=True)

    service_location = relationship("ServiceLocation", back_populates="claims")


class ServiceLocationReport(Base):
    __tablename__ = "service_location_reports"

    id = Column(Integer, primary_key=True, index=True)
    service_location_id = Column(Integer, ForeignKey("service_locations.id"), nullable=False, index=True)
    report_type = Column(String(32), nullable=False)
    report_text = Column(Text, nullable=True)
    reported_by_user_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="open", index=True)
    resolved_by_admin_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    service_location = relationship("ServiceLocation", back_populates="reports")
