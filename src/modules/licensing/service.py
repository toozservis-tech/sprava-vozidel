"""
License Service - produkční licencování pro Správu vozidel
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

from src.core.env_aliases import env_prefer_new

from ..vehicle_hub.models import (
    Customer,
    GlobalAuditLog,
    License,
    LicenseSubscription,
    ServiceCustomerLink,
    ServiceInvoice,
    ServiceRecord,
    Tenant,
    Vehicle,
    VehicleServiceLink,
)
from ..vehicle_hub.database import Base
from ..vehicle_hub.audit_log import write_global_audit_log
from ..vehicle_hub.ownership import get_customer_by_email, get_owned_vehicle_ids

logger = logging.getLogger(__name__)

# Admin bypass – prefer SPRAVA_VOZIDEL_*, fallback TOOZHUB_* (deprecated)
_admin_tenant_raw = env_prefer_new("SPRAVA_VOZIDEL_ADMIN_TENANT_ID", "TOOZHUB_ADMIN_TENANT_ID")
ADMIN_TENANT_ID = _admin_tenant_raw
if ADMIN_TENANT_ID:
    try:
        ADMIN_TENANT_ID = int(ADMIN_TENANT_ID)
    except ValueError:
        ADMIN_TENANT_ID = None
        logger.warning(
            "[LICENSE] Invalid admin tenant id (SPRAVA_VOZIDEL_ADMIN_TENANT_ID / TOOZHUB_ADMIN_TENANT_ID): %s",
            _admin_tenant_raw,
        )

# Volitelný "legacy" režim: admin tenant je vždy premium a obchází limity.
# Výchozí je vypnuto, aby se plán dal reálně měnit (nutné např. pro platby).
_admin_force_raw = env_prefer_new("SPRAVA_VOZIDEL_ADMIN_FORCE_PREMIUM", "TOOZHUB_ADMIN_FORCE_PREMIUM") or "0"
ADMIN_FORCE_PREMIUM = _admin_force_raw.strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def is_admin_tenant(tenant_id: int) -> bool:
    return ADMIN_TENANT_ID is not None and tenant_id == ADMIN_TENANT_ID


class LicenseError(HTTPException):
    """Vlastní výjimka pro licence chyby"""
    def __init__(self, code: str, message: str, details: dict = None, status_code: int = 403):
        self.code = code
        self.details = details or {}
        super().__init__(status_code=status_code, detail=message)


USER_LICENSE_PLANS = ("free", "basic", "premium", "lifetime")
# Servis: základní (zdarma, omezeně) + FULL (placené předplatné) + lifetime (jen admin)
SERVICE_LICENSE_PLANS = ("service_free", "service_full", "service_lifetime")
ALL_LICENSE_PLANS = USER_LICENSE_PLANS + SERVICE_LICENSE_PLANS

USER_PLAN_METADATA: Dict[str, Dict[str, object]] = {
    "free": {"label": "Free", "workspace_kind": "user"},
    "basic": {"label": "Basic", "workspace_kind": "user"},
    "premium": {"label": "Premium", "workspace_kind": "user"},
    "lifetime": {"label": "Lifetime", "workspace_kind": "user"},
}

SERVICE_PLAN_METADATA: Dict[str, Dict[str, object]] = {
    "service_free": {"label": "Základní (zdarma)", "workspace_kind": "service"},
    "service_full": {"label": "FULL", "workspace_kind": "service"},
    "service_lifetime": {"label": "Service Lifetime", "workspace_kind": "service"},
}

LICENSE_PLAN_METADATA: Dict[str, Dict[str, object]] = {
    **USER_PLAN_METADATA,
    **SERVICE_PLAN_METADATA,
}


def get_license_workspace_kind_for_role(role: Optional[str]) -> str:
    normalized_role = str(role or "").strip().lower()
    return "service" if normalized_role == "service" else "user"


def get_allowed_license_plans_for_role(role: Optional[str]) -> List[str]:
    workspace_kind = get_license_workspace_kind_for_role(role)
    if workspace_kind == "service":
        return list(SERVICE_LICENSE_PLANS)
    return list(USER_LICENSE_PLANS)


def get_license_plan_workspace_kind(plan: Optional[str]) -> str:
    normalized_plan = str(plan or "").strip().lower()
    if normalized_plan.startswith("service_"):
        return "service"
    return "user"


def pairing_role_for_tenant_license(db: Session, tenant_id: int) -> str:
    """Určení user vs service pro mapování Comgate/UI plánů na řádek licences.

    Dříve stačilo `tenants.workspace_route_kind == user` a ignoroval se skutečný plán
    v tabulce licences i role service účtu → admin nastavil service_full, ale API dál
    párovalo jako uživatelský tenant a UI vidělo nesmysl / starý stav.
    """
    tid = int(tenant_id)
    row = db.query(Tenant.workspace_route_kind).filter(Tenant.id == tid).first()
    rk = str(row[0] or "").strip().lower() if row else ""

    lic_plan: Optional[str] = None
    lic_obj = db.query(License).filter(License.tenant_id == tid).first()
    if lic_obj is not None:
        lic_plan = effective_service_license_storage_plan(str(lic_obj.plan or "").strip().lower())

    if lic_plan and str(lic_plan).startswith("service_"):
        return "service"

    svc = (
        db.query(Customer.id)
        .filter(Customer.tenant_id == tid, Customer.role == "service")
        .limit(1)
        .first()
    )
    if svc:
        return "service"

    if rk == "service":
        return "service"
    if rk == "user":
        return "user"

    return "user"


def map_catalog_plan_to_storage_plan(db: Session, tenant_id: int, catalog_plan: Optional[str]) -> str:
    """Z Comgate/UI katalogu na kanonický klíč v tabulce licences."""
    pair = pairing_role_for_tenant_license(db, tenant_id)
    raw = str(catalog_plan or "").strip().lower()
    if pair == "service":
        if raw in {"full"}:
            return "service_full"
        if raw == "free":
            return "service_free"
        # Zpětná kompatibilita plateb/stavu: dřívější „basic/premium“ servisu → jedna placená FULL
        if raw in {"basic", "premium"}:
            return "service_full"
    return normalize_license_plan_key(raw, pair) or "free"


def get_license_plan_base(plan: Optional[str]) -> str:
    normalized_plan = str(plan or "").strip().lower()
    if normalized_plan.startswith("service_"):
        normalized_plan = normalized_plan[len("service_"):]
    if normalized_plan == "premium_trial":
        return "premium"
    if normalized_plan in {"free", "basic", "premium", "lifetime", "full"}:
        return normalized_plan
    return "free"


def normalize_license_plan_key(plan: Optional[str], role: Optional[str] = None) -> Optional[str]:
    if plan is None:
        return None
    normalized_plan = str(plan or "").strip().lower()
    if not normalized_plan:
        return None

    workspace_kind = get_license_workspace_kind_for_role(role)
    base_plan = get_license_plan_base(normalized_plan)
    if workspace_kind == "service":
        if normalized_plan in SERVICE_LICENSE_PLANS:
            return normalized_plan
        resolved = f"service_{base_plan}"
        if resolved in {"service_basic", "service_premium"}:
            return "service_full"
        return resolved

    if normalized_plan in USER_LICENSE_PLANS:
        return normalized_plan
    return base_plan


def effective_service_license_storage_plan(plan: Optional[str]) -> str:
    """Zpětná kompatibilita řádků v DB se starými klíči service_basic / service_premium."""
    p = str(plan or "").strip().lower()
    if p in {"service_basic", "service_premium"}:
        return "service_full"
    return p


def get_license_plan_public_label(plan: Optional[str]) -> str:
    normalized_plan = str(plan or "").strip().lower()
    if normalized_plan == "premium_trial":
        return "Premium trial"
    metadata = LICENSE_PLAN_METADATA.get(normalized_plan)
    if metadata and metadata.get("label"):
        return str(metadata["label"])
    return get_license_plan_base(plan).title()


# Mapování plánů na limity
PLAN_LIMITS = {
    "free": 1,
    "basic": 3,
    "premium": 0,  # 0 = unlimited
    "premium_trial": 0,
    "lifetime": 0,  # neomezeně, administrátorské přidělení
    "service_free": 1,
    "service_full": 0,
    "service_lifetime": 0,
    # Legacy řádky (alias přes effective_plan při čtení)
    "service_basic": 0,
    "service_premium": 0,
}

FREE_SERVICE_RECORDS_LIMIT = 1
FREE_ACTIVE_MANUAL_REMINDERS_LIMIT = 1
USER_INITIAL_TRIAL_DAYS = 30
USER_INITIAL_TRIAL_PLAN = "premium"
USER_INITIAL_TRIAL_EFFECTIVE_PLAN = "premium_trial"
USER_INITIAL_TRIAL_SOURCE = "first_verified_login"

# Servisní FREE: technické kvóty (oddělené od uživatelských tarifů zákazníka)
SERVICE_FREE_MAX_CUSTOMER_LINKS = 3
SERVICE_FREE_MAX_APPROVED_VEHICLE_SERVICE_LINKS = 3
SERVICE_FREE_MAX_ISSUED_INVOICES_PER_CALENDAR_MONTH = 3
SERVICE_FREE_MAX_SERVICE_RECORDS_PER_CALENDAR_MONTH = 3

SERVICE_CUSTOMER_LINK_STATUSES_COUNTED = (
    "active",
    "invited",
    "pending_customer_confirm",
)


def _license_valid_to_expired(license_obj: License, now: Optional[datetime] = None) -> bool:
    valid_to = getattr(license_obj, "valid_to", None)
    if valid_to is None:
        return False
    current_now = now or datetime.utcnow()
    return current_now > valid_to


def is_initial_user_trial_active(license_obj: License, now: Optional[datetime] = None) -> bool:
    trial_ends_at = getattr(license_obj, "trial_ends_at", None)
    trial_used_at = getattr(license_obj, "trial_used_at", None)
    trial_plan = str(getattr(license_obj, "trial_plan", "") or "").strip().lower()
    if trial_plan != USER_INITIAL_TRIAL_PLAN or trial_used_at is None or trial_ends_at is None:
        return False
    current_now = now or datetime.utcnow()
    return current_now <= trial_ends_at


def is_expired_user_trial(license_obj: License, now: Optional[datetime] = None) -> bool:
    trial_ends_at = getattr(license_obj, "trial_ends_at", None)
    trial_used_at = getattr(license_obj, "trial_used_at", None)
    if trial_used_at is None or trial_ends_at is None:
        return False
    current_now = now or datetime.utcnow()
    return current_now > trial_ends_at


def _paid_user_plan_is_active(license_obj: License, *, now: Optional[datetime] = None) -> bool:
    plan = normalize_license_plan_key(getattr(license_obj, "plan", None), "user") or "free"
    if plan == "lifetime":
        return True
    if plan not in {"basic", "premium"}:
        return False
    return not _license_valid_to_expired(license_obj, now)


def _write_initial_trial_audit(
    db: Session,
    *,
    action: str,
    customer: Optional[Customer],
    tenant_id: Optional[int],
    plan: str,
    trial_ends_at: Optional[datetime] = None,
    reason: Optional[str] = None,
    dedupe: bool = False,
) -> None:
    if dedupe and tenant_id is not None:
        exists = (
            db.query(GlobalAuditLog.id)
            .filter(
                GlobalAuditLog.tenant_id == int(tenant_id),
                GlobalAuditLog.entity_type == "license",
                GlobalAuditLog.action == action,
            )
            .first()
        )
        if exists:
            return
    metadata = {
        "event_type": action,
        "timestamp": datetime.utcnow().isoformat(),
        "plan": plan,
    }
    if trial_ends_at is not None:
        metadata["trial_ends_at"] = trial_ends_at.isoformat()
    if reason:
        metadata["reason"] = reason
    write_global_audit_log(
        db,
        entity_type="license",
        entity_id=None,
        action=action,
        actor_user_id=int(customer.id) if customer is not None and getattr(customer, "id", None) else None,
        actor_role=str(getattr(customer, "role", "") or "") if customer is not None else None,
        tenant_id=int(tenant_id) if tenant_id is not None else None,
        metadata=metadata,
    )


def _skip_initial_trial(
    db: Session,
    *,
    customer: Optional[Customer],
    tenant_id: Optional[int],
    plan: str = "free",
    reason: str,
) -> None:
    _write_initial_trial_audit(
        db,
        action="initial_trial_skipped",
        customer=customer,
        tenant_id=tenant_id,
        plan=plan,
        reason=reason,
    )


def effective_license_plan_for_runtime(
    db: Session,
    license_obj: License,
    tenant_id: int,
    *,
    now: Optional[datetime] = None,
) -> str:
    pairing = pairing_role_for_tenant_license(db, tenant_id)
    normalized_plan = (
        normalize_license_plan_key(effective_service_license_storage_plan(license_obj.plan), pairing)
        or "free"
    )
    if pairing == "user" and _paid_user_plan_is_active(license_obj, now=now):
        return normalized_plan
    if pairing == "user" and normalized_plan == "free" and is_expired_user_trial(license_obj, now):
        _write_initial_trial_audit(
            db,
            action="initial_trial_expired_effective_free",
            customer=None,
            tenant_id=tenant_id,
            plan="free",
            trial_ends_at=getattr(license_obj, "trial_ends_at", None),
            dedupe=True,
        )
        return "free"
    if pairing == "user" and normalized_plan == "free" and is_initial_user_trial_active(license_obj, now):
        return USER_INITIAL_TRIAL_PLAN
    return normalized_plan


def activate_initial_user_trial_on_first_login(
    db: Session,
    customer: Customer,
    *,
    tenant: Optional[Tenant] = None,
    license_obj: Optional[License] = None,
    now: Optional[datetime] = None,
    previous_last_login_at: Optional[datetime] = None,
) -> Optional[License]:
    """Zapne první 30denní Premium trial po ověření e-mailu a prvním loginu."""
    current_now = now or datetime.utcnow()
    if not customer or str(getattr(customer, "role", "user") or "user").strip().lower() != "user":
        _skip_initial_trial(
            db,
            customer=customer,
            tenant_id=getattr(customer, "tenant_id", None),
            reason="not_user_role",
        )
        return None
    tenant_id = getattr(customer, "tenant_id", None)
    if not tenant_id:
        _skip_initial_trial(db, customer=customer, tenant_id=None, reason="missing_tenant")
        return None
    if ADMIN_FORCE_PREMIUM and is_admin_tenant(int(tenant_id)):
        _skip_initial_trial(db, customer=customer, tenant_id=int(tenant_id), reason="admin_force_premium")
        return None
    if getattr(customer, "email_verified_at", None) is None:
        _skip_initial_trial(db, customer=customer, tenant_id=int(tenant_id), reason="email_not_verified")
        return None
    original_last_login_at = (
        previous_last_login_at if previous_last_login_at is not None else getattr(customer, "last_login_at", None)
    )
    if original_last_login_at is not None:
        _skip_initial_trial(db, customer=customer, tenant_id=int(tenant_id), reason="not_first_login")
        return None
    if str(getattr(customer, "account_status", "") or "").strip().lower() != "active":
        _skip_initial_trial(db, customer=customer, tenant_id=int(tenant_id), reason="account_not_active")
        return None
    if getattr(customer, "email_verification_sent_at", None) is None:
        _skip_initial_trial(db, customer=customer, tenant_id=int(tenant_id), reason="not_registration_email_flow")
        return None

    tenant = tenant or db.query(Tenant).filter(Tenant.id == int(tenant_id)).first()
    if tenant is not None and str(getattr(tenant, "workspace_route_kind", "") or "").strip().lower() == "service":
        _skip_initial_trial(db, customer=customer, tenant_id=int(tenant_id), reason="service_tenant")
        return None

    license_obj = license_obj or get_or_create_license(db, int(tenant_id))
    stored_plan = normalize_license_plan_key(
        effective_service_license_storage_plan(getattr(license_obj, "plan", None)),
        pairing_role_for_tenant_license(db, int(tenant_id)),
    ) or "free"
    if stored_plan == "lifetime":
        _skip_initial_trial(db, customer=customer, tenant_id=int(tenant_id), plan=stored_plan, reason="lifetime")
        return None
    if stored_plan != "free" or _paid_user_plan_is_active(license_obj, now=current_now):
        _skip_initial_trial(
            db,
            customer=customer,
            tenant_id=int(tenant_id),
            plan=stored_plan,
            reason="paid_or_non_free_license",
        )
        return None
    if getattr(license_obj, "valid_to", None) is not None:
        _skip_initial_trial(
            db,
            customer=customer,
            tenant_id=int(tenant_id),
            plan=stored_plan,
            reason="license_valid_to_present",
        )
        return None
    if getattr(license_obj, "trial_used_at", None) is not None:
        _skip_initial_trial(
            db,
            customer=customer,
            tenant_id=int(tenant_id),
            plan=stored_plan,
            reason="trial_already_used",
        )
        return None

    trial_ends_at = current_now + timedelta(days=USER_INITIAL_TRIAL_DAYS)
    _write_initial_trial_audit(
        db,
        action="initial_trial_eligible",
        customer=customer,
        tenant_id=int(tenant_id),
        plan=USER_INITIAL_TRIAL_EFFECTIVE_PLAN,
        trial_ends_at=trial_ends_at,
    )
    license_obj.trial_started_at = current_now
    license_obj.trial_ends_at = trial_ends_at
    license_obj.trial_used_at = current_now
    license_obj.trial_source = USER_INITIAL_TRIAL_SOURCE
    license_obj.trial_plan = USER_INITIAL_TRIAL_PLAN
    license_obj.updated_at = current_now
    db.add(license_obj)
    _write_initial_trial_audit(
        db,
        action="initial_trial_activated",
        customer=customer,
        tenant_id=int(tenant_id),
        plan=USER_INITIAL_TRIAL_EFFECTIVE_PLAN,
        trial_ends_at=trial_ends_at,
    )
    return license_obj


def activate_initial_user_trial(
    db: Session,
    customer: Customer,
    *,
    now: Optional[datetime] = None,
) -> Optional[License]:
    return activate_initial_user_trial_on_first_login(db, customer, now=now)


def _normalized_service_workspace_plan(db: Session, service_customer_id: int) -> Optional[str]:
    """Efektivní servisní plán (service_free / service_full / …) pro účet Customer role=service."""
    svc = db.query(Customer).filter(Customer.id == int(service_customer_id)).first()
    if not svc or str(svc.role or "").strip().lower() != "service":
        return None
    lic = get_or_create_license(db, int(svc.tenant_id))
    pair = pairing_role_for_tenant_license(db, int(svc.tenant_id))
    return normalize_license_plan_key(
        effective_service_license_storage_plan(lic.plan),
        pair,
    ) or "free"


def assert_service_customer_link_quota(db: Session, *, service_customer_id: int) -> None:
    """Limit aktivních/čekajících zákaznických vazeb pro SERVICE FREE."""
    tid = db.query(Customer.tenant_id).filter(Customer.id == int(service_customer_id)).scalar()
    if tid is not None and ADMIN_FORCE_PREMIUM and is_admin_tenant(int(tid)):
        return
    plan = _normalized_service_workspace_plan(db, service_customer_id)
    if plan != "service_free":
        return
    current = (
        int(
            db.query(func.count(ServiceCustomerLink.id))
            .filter(
                ServiceCustomerLink.service_customer_id == int(service_customer_id),
                ServiceCustomerLink.status.in_(SERVICE_CUSTOMER_LINK_STATUSES_COUNTED),
            )
            .scalar()
            or 0
        )
    )
    if current >= SERVICE_FREE_MAX_CUSTOMER_LINKS:
        raise LicenseError(
            code="SERVICE_FREE_CUSTOMER_LINKS_EXCEEDED",
            message=(
                "Ve tarifu Základní (zdarma) můžete mít nejvýše "
                f"{SERVICE_FREE_MAX_CUSTOMER_LINKS} aktivní zákaznické vazby. Upgradujte na FULL."
            ),
            details={
                "plan": plan,
                "limit": SERVICE_FREE_MAX_CUSTOMER_LINKS,
                "current": current,
                "service_customer_id": int(service_customer_id),
            },
        )


def assert_service_vehicle_link_quota(db: Session, *, service_customer_id: int) -> None:
    """Limit schválených VehicleServiceLink řádků pro SERVICE FREE (nová nebo reaktivovaná vazba)."""
    plan = _normalized_service_workspace_plan(db, service_customer_id)
    if plan != "service_free":
        return
    svc_tid = db.query(Customer.tenant_id).filter(Customer.id == int(service_customer_id)).scalar()
    if svc_tid and ADMIN_FORCE_PREMIUM and is_admin_tenant(int(svc_tid)):
        return
    current = (
        int(
            db.query(func.count(VehicleServiceLink.id))
            .filter(
                VehicleServiceLink.service_customer_id == int(service_customer_id),
                VehicleServiceLink.status == "approved",
            )
            .scalar()
            or 0
        )
    )
    if current >= SERVICE_FREE_MAX_APPROVED_VEHICLE_SERVICE_LINKS:
        raise LicenseError(
            code="SERVICE_FREE_VEHICLE_LINKS_EXCEEDED",
            message=(
                "Ve tarifu Základní (zdarma) lze mít nejvýše "
                f"{SERVICE_FREE_MAX_APPROVED_VEHICLE_SERVICE_LINKS} aktivní vozidla propojená se servisem. Upgradujte na FULL."
            ),
            details={
                "plan": plan,
                "limit": SERVICE_FREE_MAX_APPROVED_VEHICLE_SERVICE_LINKS,
                "current": current,
                "service_customer_id": int(service_customer_id),
            },
        )


def assert_service_invoice_monthly_quota(db: Session, *, service_customer_id: int) -> None:
    """Limit vystavených faktur (issued) za kalendářní měsíc pro SERVICE FREE."""
    plan = _normalized_service_workspace_plan(db, service_customer_id)
    if plan != "service_free":
        return
    svc_tid = db.query(Customer.tenant_id).filter(Customer.id == int(service_customer_id)).scalar()
    if svc_tid and ADMIN_FORCE_PREMIUM and is_admin_tenant(int(svc_tid)):
        return
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    current = (
        int(
            db.query(func.count(ServiceInvoice.id))
            .filter(
                ServiceInvoice.service_id == int(service_customer_id),
                ServiceInvoice.status == "issued",
                ServiceInvoice.issued_at.isnot(None),
                ServiceInvoice.issued_at >= month_start,
            )
            .scalar()
            or 0
        )
    )
    if current >= SERVICE_FREE_MAX_ISSUED_INVOICES_PER_CALENDAR_MONTH:
        raise LicenseError(
            code="SERVICE_FREE_MONTHLY_INVOICES_EXCEEDED",
            message=(
                "Ve tarifu Základní (zdarma) lze vystavit nejvýše "
                f"{SERVICE_FREE_MAX_ISSUED_INVOICES_PER_CALENDAR_MONTH} faktur za kalendářní měsíc. Upgradujte na FULL."
            ),
            details={
                "plan": plan,
                "limit": SERVICE_FREE_MAX_ISSUED_INVOICES_PER_CALENDAR_MONTH,
                "current": current,
                "service_customer_id": int(service_customer_id),
            },
        )


def assert_service_monthly_service_record_quota(db: Session, *, service_customer_id: int) -> None:
    """Limit servisních záznamů vytvořených servisem za měsíc (SERVICE FREE)."""
    plan = _normalized_service_workspace_plan(db, service_customer_id)
    if plan != "service_free":
        return
    svc_tid = db.query(Customer.tenant_id).filter(Customer.id == int(service_customer_id)).scalar()
    if svc_tid and ADMIN_FORCE_PREMIUM and is_admin_tenant(int(svc_tid)):
        return
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    current = (
        int(
            db.query(func.count(ServiceRecord.id))
            .filter(
                ServiceRecord.created_by_service_customer_id == int(service_customer_id),
                ServiceRecord.is_deleted.is_(False),
                ServiceRecord.updated_at >= month_start,
            )
            .scalar()
            or 0
        )
    )
    if current >= SERVICE_FREE_MAX_SERVICE_RECORDS_PER_CALENDAR_MONTH:
        raise LicenseError(
            code="SERVICE_FREE_MONTHLY_SERVICE_RECORDS_EXCEEDED",
            message=(
                "Ve tarifu Základní (zdarma) lze za kalendářní měsíc založit nejvýše "
                f"{SERVICE_FREE_MAX_SERVICE_RECORDS_PER_CALENDAR_MONTH} servisní záznamy. Upgradujte na FULL."
            ),
            details={
                "plan": plan,
                "limit": SERVICE_FREE_MAX_SERVICE_RECORDS_PER_CALENDAR_MONTH,
                "current": current,
                "service_customer_id": int(service_customer_id),
            },
        )


# Mapování plánů na dostupné funkce (ARES necháváme povolený pro všechny)
PLAN_FEATURES = {
    "free": {
        "vin_decode_enabled": False,
        "ares_enabled": True,
        # Připomínky jsou základní hodnota produktu, dostupná i ve FREE plánu.
        "reminders_enabled": True,
        "reservations_enabled": False,
        "vehicle_history_enabled": False,
        "documents_enabled": False,
        "costs_tracking_enabled": False,
        "statistics_enabled": False,
        "sharing_with_service_enabled": False,
    },
    "basic": {
        "vin_decode_enabled": False,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": True,
        "vehicle_history_enabled": True,
        "documents_enabled": True,
        "costs_tracking_enabled": False,
        "statistics_enabled": False,
        "sharing_with_service_enabled": False,
    },
    "premium": {
        "vin_decode_enabled": True,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": True,
        "vehicle_history_enabled": True,
        "documents_enabled": True,
        "costs_tracking_enabled": True,
        "statistics_enabled": True,
        "sharing_with_service_enabled": True,
    },
    "premium_trial": {
        "vin_decode_enabled": True,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": True,
        "vehicle_history_enabled": True,
        "documents_enabled": True,
        "costs_tracking_enabled": True,
        "statistics_enabled": True,
        "sharing_with_service_enabled": True,
    },
    # Dofull Premium + doživotní platnost, pouze admin (bez Comgate)
    "lifetime": {
        "vin_decode_enabled": True,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": True,
        "vehicle_history_enabled": True,
        "documents_enabled": True,
        "costs_tracking_enabled": True,
        "statistics_enabled": True,
        "sharing_with_service_enabled": True,
    },
    "service_free": {
        "vin_decode_enabled": False,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": False,
        "vehicle_history_enabled": False,
        "documents_enabled": False,
        "costs_tracking_enabled": False,
        "statistics_enabled": False,
        "sharing_with_service_enabled": False,
    },
    "service_full": {
        "vin_decode_enabled": True,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": True,
        "vehicle_history_enabled": True,
        "documents_enabled": True,
        "costs_tracking_enabled": True,
        "statistics_enabled": True,
        "sharing_with_service_enabled": True,
    },
    # Zachováno pro přímý tah z legacy DB (stejné jako FULL)
    "service_basic": {
        "vin_decode_enabled": True,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": True,
        "vehicle_history_enabled": True,
        "documents_enabled": True,
        "costs_tracking_enabled": True,
        "statistics_enabled": True,
        "sharing_with_service_enabled": True,
    },
    "service_premium": {
        "vin_decode_enabled": True,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": True,
        "vehicle_history_enabled": True,
        "documents_enabled": True,
        "costs_tracking_enabled": True,
        "statistics_enabled": True,
        "sharing_with_service_enabled": True,
    },
    "service_lifetime": {
        "vin_decode_enabled": True,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": True,
        "vehicle_history_enabled": True,
        "documents_enabled": True,
        "costs_tracking_enabled": True,
        "statistics_enabled": True,
        "sharing_with_service_enabled": True,
    },
}


def get_or_create_license(db: Session, tenant_id: int) -> License:
    """
    Získá nebo vytvoří licenci pro tenant_id.
    Pokud licence neexistuje, vytvoří default free licenci.
    
    Args:
        db: Databázová session
        tenant_id: ID tenanta
        
    Returns:
        License objekt
    """
    admin_force_premium = ADMIN_FORCE_PREMIUM and is_admin_tenant(tenant_id)
    
    # Normální tenant - zkusit najít existující licenci
    license_obj = db.query(License).filter(License.tenant_id == tenant_id).first()
    
    # Pokud licence existuje, ujistit se, že má správné funkce podle plánu
    if license_obj:
        needs_update = False

        if admin_force_premium and license_obj.plan != "premium":
            license_obj.plan = "premium"
            needs_update = True
        if admin_force_premium and license_obj.status != "active":
            license_obj.status = "active"
            needs_update = True
        if admin_force_premium:
            if license_obj.valid_to is not None:
                license_obj.valid_to = None
                needs_update = True
            if not license_obj.valid_from:
                license_obj.valid_from = datetime.utcnow()
                needs_update = True

        pairing = pairing_role_for_tenant_license(db, tenant_id)
        effective_row_plan = effective_service_license_storage_plan(license_obj.plan)
        current_plan_key = normalize_license_plan_key(effective_row_plan, pairing) or "free"
        if pairing == "service" and license_obj.plan != current_plan_key and license_obj.plan in {
            "service_basic",
            "service_premium",
        }:
            license_obj.plan = current_plan_key
            needs_update = True

        features = PLAN_FEATURES.get(current_plan_key, PLAN_FEATURES["free"])

        # Synchronizovat feature flagy, které máme uložené v DB
        db_feature_keys = ["vin_decode_enabled", "ares_enabled", "reminders_enabled"]
        for key in db_feature_keys:
            expected = features.get(key, getattr(license_obj, key, False))
            if getattr(license_obj, key, False) != expected:
                setattr(license_obj, key, expected)
                needs_update = True

        # Aktualizovat limit podle plánu, pokud se liší
        expected_limit = 0 if admin_force_premium else PLAN_LIMITS.get(current_plan_key, 1)
        if license_obj.vehicles_limit != expected_limit:
            license_obj.vehicles_limit = expected_limit
            needs_update = True

        if needs_update:
            license_obj.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(license_obj)
            logger.info(f"[LICENSE] Updated license features for tenant_id={tenant_id}, plan={license_obj.plan}")
    
    if not license_obj:
        # Vytvořit default free licenci
        plan = "premium" if admin_force_premium else "free"
        
        # Zjistit roli tenanta, pokud to jde
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant and tenant.workspace_route_kind == "service" and not admin_force_premium:
            plan = "service_free"

        vehicles_limit = PLAN_LIMITS.get(plan, 1)
        features = PLAN_FEATURES.get(plan, PLAN_FEATURES["free"])
        now = datetime.utcnow()
        valid_to = None
            
        license_obj = License(
            tenant_id=tenant_id,
            plan=plan,
            status="active",
            vehicles_limit=vehicles_limit,
            valid_from=now,
            valid_to=valid_to,
            vin_decode_enabled=features["vin_decode_enabled"],
            ares_enabled=features.get("ares_enabled", True),
            reminders_enabled=features["reminders_enabled"]
        )
        db.add(license_obj)
        try:
            db.commit()
            db.refresh(license_obj)
            logger.info(f"[LICENSE] Created default free license for tenant_id={tenant_id}")
        except IntegrityError:
            db.rollback()
            # Možná byla mezitím vytvořena jiným procesem
            license_obj = db.query(License).filter(License.tenant_id == tenant_id).first()
            if not license_obj:
                raise
    
    return license_obj


def get_vehicle_count(db: Session, tenant_id: int) -> int:
    """
    Spočítá počet vozidel pro tenant_id.
    
    Args:
        db: Databázová session
        tenant_id: ID tenanta
        
    Returns:
        Počet vozidel
    """
    return db.query(Vehicle).filter(Vehicle.tenant_id == tenant_id, Vehicle.status != "archived").count()


def get_vehicle_count_for_user(db: Session, tenant_id: int, user_email: Optional[str]) -> int:
    """
    Spočítá počet vozidel konkrétního uživatele v rámci tenantu.

    Pokud user_email není dostupný, vrací tenant-wide počet.
    """
    normalized_email = str(user_email or "").strip().lower()
    if not normalized_email:
        return get_vehicle_count(db, tenant_id)

    customer = get_customer_by_email(db, normalized_email)
    if customer is None:
        # Deprecated compat fallback for users/customers that ještě nemají
        # explicitní ownership/customer vazbu. Nesmí být hlavní autoritou.
        return db.query(Vehicle).filter(
            Vehicle.tenant_id == tenant_id,
            func.lower(Vehicle.user_email) == normalized_email,
            Vehicle.status != "archived",
        ).count()

    return len(get_owned_vehicle_ids(db, customer, tenant_id=tenant_id))


def is_unlimited(license_obj: License) -> bool:
    """
    Zkontroluje, zda je licence unlimited (vehicles_limit == 0).
    
    Args:
        license_obj: License objekt
        
    Returns:
        True pokud je unlimited
    """
    return license_obj.vehicles_limit == 0


def assert_vehicle_quota(db: Session, tenant_id: int) -> None:
    """
    Zkontroluje, zda tenant může přidat další vozidlo.
    Pokud ne, vyhodí LicenseError.
    
    Args:
        db: Databázová session
        tenant_id: ID tenanta
        
    Raises:
        LicenseError: Pokud je quota překročena
    """
    license_obj = get_or_create_license(db, tenant_id)
    
    # Legacy admin bypass - aktivní jen při explicitním zapnutí.
    if ADMIN_FORCE_PREMIUM and is_admin_tenant(tenant_id):
        return
    
    # Zkontrolovat status
    if license_obj.status != "active":
        raise LicenseError(
            code="LICENSE_INACTIVE",
            message=f"Licence není aktivní (status: {license_obj.status})",
            details={"status": license_obj.status, "tenant_id": tenant_id}
        )
    
    # Zkontrolovat valid_to (admin bypass valid_to)
    if license_obj.valid_to and not (ADMIN_FORCE_PREMIUM and is_admin_tenant(tenant_id)):
        if datetime.utcnow() > license_obj.valid_to and not is_expired_user_trial(license_obj):
            raise LicenseError(
                code="LICENSE_EXPIRED",
                message=f"Licence vypršela (valid_to: {license_obj.valid_to})",
                details={"valid_to": license_obj.valid_to.isoformat(), "tenant_id": tenant_id}
            )
    
    # Zkontrolovat quota
    effective_plan = effective_license_plan_for_runtime(db, license_obj, tenant_id)
    effective_limit = PLAN_LIMITS.get(effective_plan, license_obj.vehicles_limit)
    if effective_limit == 0:
        return  # Unlimited - OK
    
    current = get_vehicle_count(db, tenant_id)
    if current >= effective_limit:
        raise LicenseError(
            code="LICENSE_QUOTA_EXCEEDED",
            message=f"Limit vozidel překročen ({current}/{effective_limit})",
            details={
                "plan": effective_plan,
                "stored_plan": license_obj.plan,
                "limit": effective_limit,
                "current": current
            },
            status_code=403
        )


def assert_feature(db: Session, tenant_id: int, feature_name: str) -> None:
    """
    Zkontroluje, zda je feature povoleno pro tenant_id.
    Pokud ne, vyhodí LicenseError.
    
    Args:
        db: Databázová session
        tenant_id: ID tenanta
        feature_name: Název feature ("vin_decode", "ares", "reminders", "documents", "reservations")
        
    Raises:
        LicenseError: Pokud je feature zakázáno
    """
    license_obj = get_or_create_license(db, tenant_id)
    
    # Legacy admin bypass - aktivní jen při explicitním zapnutí.
    if ADMIN_FORCE_PREMIUM and is_admin_tenant(tenant_id):
        return

    feat_key = effective_license_plan_for_runtime(db, license_obj, tenant_id)
    features = PLAN_FEATURES.get(feat_key, PLAN_FEATURES["free"])

    if feature_name == "documents":
        if not bool(features.get("documents_enabled", False)):
            raise LicenseError(
                code="FEATURE_DISABLED",
                message="Dokumenty a PDF exporty jsou dostupné od licence Basic.",
                details={
                    "feature_name": "documents",
                    "plan": license_obj.plan,
                    "tenant_id": tenant_id,
                },
                status_code=403,
            )
        return

    if feature_name == "reservations":
        if not bool(features.get("reservations_enabled", False)):
            raise LicenseError(
                code="FEATURE_DISABLED",
                message="Objednání servisu je dostupné od licence Basic.",
                details={
                    "feature_name": "reservations",
                    "plan": license_obj.plan,
                    "tenant_id": tenant_id,
                },
                status_code=403,
            )
        return

    if feature_name == "sharing_with_service":
        if not bool(features.get("sharing_with_service_enabled", False)):
            raise LicenseError(
                code="FEATURE_DISABLED",
                message="Sdílení vozidel se servisem je dostupné od licence Basic.",
                details={
                    "feature_name": "sharing_with_service",
                    "plan": license_obj.plan,
                    "tenant_id": tenant_id,
                },
                status_code=403,
            )
        return
    
    # Mapování feature name na sloupec
    feature_map = {
        "vin_decode": "vin_decode_enabled",
        "ares": "ares_enabled",
        "reminders": "reminders_enabled",
        "reservations": "reservations_enabled",
    }
    
    if feature_name not in feature_map:
        raise LicenseError(
            code="INVALID_FEATURE",
            message=f"Neplatný feature: {feature_name}",
            details={"feature_name": feature_name}
        )
    
    column_name = feature_map[feature_name]
    is_enabled = bool(features.get(column_name, getattr(license_obj, column_name, False)))
    
    if not is_enabled:
        message = "Tato funkce je dostupná po zakoupení odpovídající licence."
        if feature_name == "vin_decode":
            message = (
                "Tato funkce je dostupná v licenci Premium. Pro automatické načtení údajů z VIN "
                "si aktivujte Premium licenci nebo využijte zkušební Premium verzi."
            )
        raise LicenseError(
            code="FEATURE_DISABLED",
            message=message,
            details={
                "feature_name": feature_name,
                "plan": license_obj.plan,
                "tenant_id": tenant_id
            },
            status_code=403
        )


def get_license_status(db: Session, tenant_id: int, user_email: Optional[str] = None) -> dict:
    """
    Získá status licence pro tenant_id.
    
    Args:
        db: Databázová session
        tenant_id: ID tenanta
        
    Returns:
        dict s informacemi o licenci včetně feature flags
    """
    license_obj = get_or_create_license(db, tenant_id)
    tenant_vehicle_count = get_vehicle_count(db, tenant_id)
    user_vehicle_count = get_vehicle_count_for_user(db, tenant_id, user_email)
    pairing = pairing_role_for_tenant_license(db, tenant_id)
    stored_plan = normalize_license_plan_key(
        effective_service_license_storage_plan(license_obj.plan),
        pairing,
    ) or "free"
    normalized_plan = effective_license_plan_for_runtime(db, license_obj, tenant_id)
    features = PLAN_FEATURES.get(normalized_plan, PLAN_FEATURES.get(license_obj.plan, PLAN_FEATURES["free"]))
    tier_limit = PLAN_LIMITS.get(normalized_plan, license_obj.vehicles_limit)
    is_unl = tier_limit == 0

    vehicles_remaining = None if is_unl else max(0, tier_limit - tenant_vehicle_count)

    current_now = datetime.utcnow()
    trial_valid_to = getattr(license_obj, "trial_ends_at", None)
    is_expired_trial = bool(
        pairing == "user"
        and stored_plan == "free"
        and is_expired_user_trial(license_obj, current_now)
    )
    trial_active = bool(
        pairing == "user"
        and stored_plan == "free"
        and is_initial_user_trial_active(license_obj, current_now)
    )
    trial_days_remaining = None
    if trial_valid_to:
        trial_days_remaining = max(0, (trial_valid_to.date() - current_now.date()).days)

    over_limit = (not is_unl) and tenant_vehicle_count > int(tier_limit or 0)
    display_plan = "Premium trial" if trial_active else get_license_plan_public_label(normalized_plan)
    capabilities = {
        "vin_decode_enabled": bool(features.get("vin_decode_enabled", license_obj.vin_decode_enabled)),
        "ares_enabled": bool(features.get("ares_enabled", license_obj.ares_enabled)),
        "reminders_enabled": bool(features.get("reminders_enabled", license_obj.reminders_enabled)),
        "reservations_enabled": bool(features.get("reservations_enabled", False)),
        "vehicle_history_enabled": bool(features.get("vehicle_history_enabled", False)),
        "documents_enabled": bool(features.get("documents_enabled", False)),
        "costs_tracking_enabled": bool(features.get("costs_tracking_enabled", False)),
        "statistics_enabled": bool(features.get("statistics_enabled", False)),
        "sharing_with_service_enabled": bool(features.get("sharing_with_service_enabled", False)),
    }
    status = {
        "is_expired_trial": is_expired_trial,
        "trial_active": trial_active,
        "trial_days_remaining": trial_days_remaining,
        "stored_plan": stored_plan,
        "effective_plan": normalized_plan,
        "display_plan": display_plan,
        "capabilities": capabilities,
        "valid_to": license_obj.valid_to.isoformat() if license_obj.valid_to else None,
        "trial_started_at": (
            license_obj.trial_started_at.isoformat() if getattr(license_obj, "trial_started_at", None) else None
        ),
        "trial_ends_at": trial_valid_to.isoformat() if trial_valid_to else None,
        "trial_used_at": license_obj.trial_used_at.isoformat() if getattr(license_obj, "trial_used_at", None) else None,
        "trial_plan": getattr(license_obj, "trial_plan", None),
        "tenant_id": str(tenant_id),
        "plan": stored_plan,
        "plan_base": get_license_plan_base(normalized_plan),
        "plan_workspace_kind": get_license_plan_workspace_kind(normalized_plan),
        "plan_public_label": get_license_plan_public_label(normalized_plan),
        "status": license_obj.status,
        "vehicles_limit": tier_limit if not is_unl else 0,
        # Tenant-wide počet (používá se pro licenční limity)
        "vehicles_current": tenant_vehicle_count,
        # Uživatelský počet (pro UI kontext "moje vozidla")
        "vehicles_current_user": user_vehicle_count,
        "vehicles_remaining": vehicles_remaining,
        "is_unlimited": is_unl,
        # Aliasy pro klientské UI (dashboard)
        "vehicles_count": tenant_vehicle_count,
        "license_limit": None if is_unl else int(tier_limit or 0),
        "is_over_limit": bool(over_limit),
        "vin_decode_enabled": bool(features.get("vin_decode_enabled", license_obj.vin_decode_enabled)),
        "ares_enabled": bool(features.get("ares_enabled", license_obj.ares_enabled)),
        "reminders_enabled": bool(features.get("reminders_enabled", license_obj.reminders_enabled)),
    }

    # Doplnit ostatní feature flagy podle efektivního plánu (nejsou vždy v DB řádku Licence)
    status.update({
        "reservations_enabled": bool(features.get("reservations_enabled", False)),
        "vehicle_history_enabled": bool(features.get("vehicle_history_enabled", False)),
        "documents_enabled": bool(features.get("documents_enabled", False)),
        "costs_tracking_enabled": bool(features.get("costs_tracking_enabled", False)),
        "statistics_enabled": bool(features.get("statistics_enabled", False)),
        "sharing_with_service_enabled": bool(features.get("sharing_with_service_enabled", False)),
        "is_lifetime": get_license_plan_base(normalized_plan) == "lifetime",
    })

    return status


def upgrade_license_plan(db: Session, tenant_id: int, plan: str) -> dict:
    """
    Nastaví licenci na požadovaný plán a vrátí aktuální stav.
    
    Args:
        db: databázová session
        tenant_id: cílový tenant
        plan: "free" | "basic" | "premium" | "lifetime"
    
    Returns:
        dict ve formátu get_license_status
    """
    plan_key = str(plan or "").strip().lower()
    legacy_upgrade_aliases = {"service_basic": "service_full", "service_premium": "service_full"}
    plan_key = legacy_upgrade_aliases.get(plan_key, plan_key)
    if plan_key not in PLAN_FEATURES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Neplatný plán. Povolené hodnoty: free, basic, premium, lifetime, "
                "service_free, service_full, service_lifetime (+ legacy alias service_basic/service_premium → FULL)."
            ),
        )

    license_obj = get_or_create_license(db, tenant_id)
    features = PLAN_FEATURES[plan_key]
    vehicles_limit = PLAN_LIMITS.get(plan_key, 1)

    license_obj.plan = plan_key
    license_obj.status = "active"
    license_obj.vehicles_limit = vehicles_limit
    license_obj.vin_decode_enabled = features["vin_decode_enabled"]
    license_obj.ares_enabled = features.get("ares_enabled", True)
    license_obj.reminders_enabled = features["reminders_enabled"]
    license_obj.updated_at = datetime.utcnow()
    if get_license_plan_base(plan_key) in {"basic", "premium", "full"}:
        license_obj.valid_to = None
    if plan_key == "service_full":
        license_obj.valid_to = None

    if get_license_plan_base(plan_key) == "lifetime":
        license_obj.valid_to = None
        sub = (
            db.query(LicenseSubscription)
            .filter(LicenseSubscription.tenant_id == tenant_id)
            .first()
        )
        if sub is not None:
            sub.status = "legacy_manual"
            sub.auto_renew_enabled = False
            sub.next_charge_at = None
            sub.current_period_end = None
            sub.grace_until = None
            sub.pending_plan_change = None
            sub.plan_current = plan_key
            sub.billing_period = None
            sub.updated_at = datetime.utcnow()
            db.add(sub)
    
    db.add(license_obj)
    db.commit()
    db.refresh(license_obj)
    
    return get_license_status(db, tenant_id, user_email=None)
