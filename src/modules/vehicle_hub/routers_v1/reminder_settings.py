"""
Reminder Settings API v1.0 router (Nastavení připomínek)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
import json

from ..database import get_db
from ..models import Customer
from .auth import get_current_user
from .schemas import (
    ReminderSettingsV1, 
    ReminderSettingsOutV1,
    STKReminderSettings,
    OilReminderSettings,
    ServiceCategorySettings,
    GeneralReminderSettings,
    NotificationSettings
)

router = APIRouter(prefix="/reminders", tags=["reminders-v1"])


# Výchozí nastavení připomínek
DEFAULT_REMINDER_SETTINGS = {
    "enabled": True,
    "stk": {
        "enabled": True,
        "days_before": 30  # Připomínat X dní před koncem STK
    },
    "oil": {
        "enabled": True,
        "km_interval": 15000,  # Interval v km
        "km_warning": 5000,  # Varování X km před
        "days_interval": 365,  # Interval ve dnech
        "days_warning": 30  # Varování X dní před
    },
    "service_categories": {
        # Pro každou kategorii servisu
        # "OLEJ": {"enabled": True, "km_interval": 15000, "days_interval": 365},
        # "BRZDY": {"enabled": True, "km_interval": 30000, "days_interval": 730},
    },
    "general": {
        "enabled": True,
        "days_before": 30  # Připomínat X dní před plánovaným servisem
    },
    "notification": {
        "notification_method": "email",  # "app", "email", "both"
        "notify_days_before": 7  # Počet dní předem upozornit
    }
}


def get_reminder_settings(user: Customer) -> Dict[str, Any]:
    """Získá nastavení připomínek uživatele nebo výchozí"""
    if user.reminder_settings:
        try:
            settings = json.loads(user.reminder_settings)
            # Sloučit s výchozími nastaveními
            default_copy = json.loads(json.dumps(DEFAULT_REMINDER_SETTINGS))
            return _merge_settings(default_copy, settings)
        except (json.JSONDecodeError, TypeError):
            return DEFAULT_REMINDER_SETTINGS.copy()
    return DEFAULT_REMINDER_SETTINGS.copy()


def _merge_settings(default: Dict, user: Dict) -> Dict:
    """Rekurzivně sloučí uživatelská nastavení s výchozími"""
    result = default.copy()
    for key, value in user.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = _merge_settings(result[key], value)
        else:
            result[key] = value
    return result


@router.get("/settings", response_model=ReminderSettingsOutV1)
def get_reminder_settings_endpoint(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací nastavení připomínek aktuálního uživatele"""
    settings = get_reminder_settings(current_user)
    
    # Převedení na Pydantic modely
    return ReminderSettingsOutV1(
        enabled=settings.get("enabled", True),
        stk=STKReminderSettings(**settings.get("stk", DEFAULT_REMINDER_SETTINGS["stk"])),
        oil=OilReminderSettings(**settings.get("oil", DEFAULT_REMINDER_SETTINGS["oil"])),
        service_categories={
            k: ServiceCategorySettings(**v) 
            for k, v in settings.get("service_categories", {}).items()
        },
        general=GeneralReminderSettings(**settings.get("general", DEFAULT_REMINDER_SETTINGS["general"])),
        notification=NotificationSettings(**settings.get("notification", DEFAULT_REMINDER_SETTINGS["notification"]))
    )


@router.put("/settings", response_model=ReminderSettingsOutV1)
def update_reminder_settings(
    settings_data: ReminderSettingsV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aktualizuje nastavení připomínek uživatele"""
    try:
        # Načíst aktuální nastavení uživatele
        current_settings = get_reminder_settings(current_user)
        
        # Validovat a sloučit s aktuálními nastaveními
        settings_dict = settings_data.dict(exclude_unset=True)
        merged_settings = _merge_settings(current_settings, settings_dict)
        
        # Uložit jako JSON string
        current_user.reminder_settings = json.dumps(merged_settings)
        db.commit()
        db.refresh(current_user)
        
        # Vrátit kompletní nastavení
        return ReminderSettingsOutV1(
            enabled=merged_settings.get("enabled", True),
            stk=STKReminderSettings(**merged_settings.get("stk", DEFAULT_REMINDER_SETTINGS["stk"])),
            oil=OilReminderSettings(**merged_settings.get("oil", DEFAULT_REMINDER_SETTINGS["oil"])),
            service_categories={
                k: ServiceCategorySettings(**v) 
                for k, v in merged_settings.get("service_categories", {}).items()
            },
            general=GeneralReminderSettings(**merged_settings.get("general", DEFAULT_REMINDER_SETTINGS["general"])),
            notification=NotificationSettings(**merged_settings.get("notification", DEFAULT_REMINDER_SETTINGS["notification"]))
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Chyba při ukládání nastavení: {str(e)}")
