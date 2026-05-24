"""
License Service - tenant-based licencování s quota a feature flags
"""
import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

from src.core.env_aliases import env_prefer_new

from ..vehicle_hub.models import License, Vehicle, Tenant
from ..vehicle_hub.database import Base

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


class LicenseError(HTTPException):
    """Vlastní výjimka pro licence chyby"""
    def __init__(self, code: str, message: str, details: dict = None, status_code: int = 403):
        self.code = code
        self.details = details or {}
        super().__init__(status_code=status_code, detail=message)


def get_or_create_license(db: Session, tenant_id: int) -> License:
    """
    Získá nebo vytvoří licenci pro tenant_id.
    
    Args:
        db: Databázová session
        tenant_id: ID tenanta
        
    Returns:
        License objekt
    """
    # Admin bypass
    if ADMIN_TENANT_ID and tenant_id == ADMIN_TENANT_ID:
        license_obj = db.query(License).filter(License.tenant_id == tenant_id).first()
        if not license_obj:
            license_obj = License(
                tenant_id=tenant_id,
                plan_name="admin",
                status="active",
                vehicles_limit=0,  # 0 = unlimited
                vin_decode_enabled=True,
                ares_enabled=True,
                reminders_enabled=True,
                valid_to=None
            )
            db.add(license_obj)
            db.commit()
            db.refresh(license_obj)
            logger.info(f"[LICENSE] Created admin license for tenant_id={tenant_id}")
        else:
            # Ujistit se, že admin licence má správné hodnoty
            license_obj.plan_name = "admin"
            license_obj.status = "active"
            license_obj.vehicles_limit = 0
            license_obj.vin_decode_enabled = True
            license_obj.ares_enabled = True
            license_obj.reminders_enabled = True
            db.commit()
            db.refresh(license_obj)
        return license_obj
    
    # Normální tenant - zkusit najít existující licenci
    license_obj = db.query(License).filter(License.tenant_id == tenant_id).first()
    
    if not license_obj:
        # Vytvořit default free licenci
        license_obj = License(
            tenant_id=tenant_id,
            plan_name="free",
            status="active",
            vehicles_limit=1,
            vin_decode_enabled=True,
            ares_enabled=True,
            reminders_enabled=True,
            valid_to=None
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


def is_unlimited(license_obj: License) -> bool:
    """
    Zkontroluje, zda je licence unlimited (vehicles_limit == 0).
    
    Args:
        license_obj: License objekt
        
    Returns:
        True pokud je unlimited
    """
    return license_obj.vehicles_limit == 0


def count_vehicles(db: Session, tenant_id: int) -> int:
    """
    Spočítá počet vozidel pro tenant_id.
    
    Args:
        db: Databázová session
        tenant_id: ID tenanta
        
    Returns:
        Počet vozidel
    """
    return db.query(Vehicle).filter(Vehicle.tenant_id == tenant_id, Vehicle.status != "archived").count()


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
    
    # Admin bypass - unlimited
    if ADMIN_TENANT_ID and tenant_id == ADMIN_TENANT_ID:
        return
    
    # Zkontrolovat status
    if license_obj.status != "active":
        raise LicenseError(
            code="LICENSE_INACTIVE",
            message=f"Licence není aktivní (status: {license_obj.status})",
            details={"status": license_obj.status, "tenant_id": tenant_id}
        )
    
    # Zkontrolovat valid_to
    if license_obj.valid_to:
        from datetime import datetime
        if datetime.utcnow() > license_obj.valid_to:
            raise LicenseError(
                code="LICENSE_EXPIRED",
                message=f"Licence vypršela (valid_to: {license_obj.valid_to})",
                details={"valid_to": license_obj.valid_to.isoformat(), "tenant_id": tenant_id}
            )
    
    # Zkontrolovat quota
    if is_unlimited(license_obj):
        return  # Unlimited - OK
    
    current = count_vehicles(db, tenant_id)
    if current >= license_obj.vehicles_limit:
        raise LicenseError(
            code="LICENSE_QUOTA_EXCEEDED",
            message=f"Byl dosažen limit vozidel pro váš plán. Plán: {license_obj.plan_name}, Limit: {license_obj.vehicles_limit}, Aktuálně: {current}",
            details={
                "plan_name": license_obj.plan_name,
                "limit": license_obj.vehicles_limit,
                "current": current,
                "tenant_id": tenant_id
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
        feature_name: Název feature ("vin_decode", "ares", "reminders")
        
    Raises:
        LicenseError: Pokud je feature zakázáno
    """
    license_obj = get_or_create_license(db, tenant_id)
    
    # Admin bypass - všechny features povolené
    if ADMIN_TENANT_ID and tenant_id == ADMIN_TENANT_ID:
        return
    
    # Mapování feature name na sloupec
    feature_map = {
        "vin_decode": "vin_decode_enabled",
        "ares": "ares_enabled",
        "reminders": "reminders_enabled"
    }
    
    if feature_name not in feature_map:
        raise LicenseError(
            code="INVALID_FEATURE",
            message=f"Neplatný feature: {feature_name}",
            details={"feature_name": feature_name}
        )
    
    column_name = feature_map[feature_name]
    is_enabled = getattr(license_obj, column_name, False)
    
    if not is_enabled:
        raise LicenseError(
            code="FEATURE_DISABLED",
            message=f"Feature '{feature_name}' není povoleno pro váš plán",
            details={
                "feature_name": feature_name,
                "plan_name": license_obj.plan_name,
                "tenant_id": tenant_id
            },
            status_code=403
        )


def get_license_status(db: Session, tenant_id: int) -> dict:
    """
    Získá status licence pro tenant_id.
    
    Args:
        db: Databázová session
        tenant_id: ID tenanta
        
    Returns:
        dict s informacemi o licenci
    """
    license_obj = get_or_create_license(db, tenant_id)
    current_count = count_vehicles(db, tenant_id)
    
    return {
        "tenant_id": tenant_id,
        "plan_name": license_obj.plan_name,
        "status": license_obj.status,
        "vehicles_limit": license_obj.vehicles_limit,
        "vehicles_current": current_count,
        "is_unlimited": is_unlimited(license_obj),
        "features": {
            "vin_decode_enabled": license_obj.vin_decode_enabled,
            "ares_enabled": license_obj.ares_enabled,
            "reminders_enabled": license_obj.reminders_enabled
        },
        "valid_to": license_obj.valid_to.isoformat() if license_obj.valid_to else None
    }

