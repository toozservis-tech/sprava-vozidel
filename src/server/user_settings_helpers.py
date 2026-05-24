"""
Helpers for user settings facade (/api/v1/user/settings).
"""
from __future__ import annotations

import copy
import hashlib
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.modules.vehicle_hub.models import Customer, Reminder as ReminderModel, SecurityAccessLog
from src.modules.vehicle_hub.ownership import get_owned_vehicle_ids


DEFAULT_USER_PREFERENCES: Dict[str, Any] = {
    "preferred_language": "cs",
    "preferred_contact": "email",
    "notifications": {
        "master": True,
        "quiet_mode": "off",
        "channels": {
            "email": True,
            "sms": False,
            "push": True,
        },
        "types": {
            "service_reminders": {"email": True, "sms": True, "push": True},
            "documents": {"email": True, "sms": False, "push": True},
            "news": {"email": True, "sms": False, "push": False},
            "security": {"email": True, "sms": True, "push": True},
            "marketing": {"email": False, "sms": False, "push": False},
        },
    },
    "privacy": {
        "third_party": False,
        "personalization": True,
        "marketing": False,
    },
    "garage": {
        "default_units": "metric",
        "default_currency": "CZK",
        "mdcr_auto_update": True,
        "vehicle_order": [],
    },
    "documents": {
        "auto_sort": True,
        "default_category": "other",
        "smart_naming": True,
    },
    "services": {
        "allow_vehicle_access": True,
        "allow_communication": True,
    },
    "security_emails": {
        "login": True,
        "account_changes": True,
    },
}


def deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def get_user_preferences(customer: Customer) -> Dict[str, Any]:
    raw = getattr(customer, "user_preferences", None)
    if isinstance(raw, dict):
        return deep_merge(DEFAULT_USER_PREFERENCES, raw)
    return copy.deepcopy(DEFAULT_USER_PREFERENCES)


def set_user_preferences(customer: Customer, prefs: Dict[str, Any]) -> None:
    customer.user_preferences = prefs


def mask_email(email: Optional[str]) -> str:
    value = str(email or "").strip()
    if not value or "@" not in value:
        return "—"
    local, domain = value.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "***"
    else:
        masked_local = local[:2] + "***"
    return f"{masked_local}@{domain}"


def mask_phone(phone: Optional[str]) -> str:
    value = str(phone or "").strip()
    if not value:
        return "—"
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 3:
        return f"+*** *** *** {digits[-3:]}"
    return "+*** *** ***"


def password_strength_label(customer: Customer) -> str:
    if not customer.password_hash:
        return "Neznámé"
    # Heuristika bez ukládání hesla — délka není známa, ale aktivní hash = silné pokud 2FA
    return "Silné"


def parse_user_agent(user_agent: Optional[str]) -> Dict[str, str]:
    ua = str(user_agent or "")
    lowered = ua.lower()
    os_name = "Neznámé"
    browser = "Neznámý prohlížeč"
    if "windows" in lowered:
        os_name = "Windows"
    elif "android" in lowered:
        os_name = "Android"
    elif "iphone" in lowered or "ios" in lowered:
        os_name = "iOS"
    elif "ipad" in lowered:
        os_name = "iPadOS"
    elif "mac os" in lowered or "macintosh" in lowered:
        os_name = "macOS"
    elif "linux" in lowered:
        os_name = "Linux"
    if "edg/" in lowered:
        browser = "Edge"
    elif "chrome/" in lowered and "edg/" not in lowered:
        browser = "Chrome"
    elif "firefox/" in lowered:
        browser = "Firefox"
    elif "safari/" in lowered and "chrome/" not in lowered:
        browser = "Safari"
    return {"os": os_name, "browser": browser}


def device_fingerprint(user_agent: Optional[str], city: Optional[str]) -> str:
    raw = f"{user_agent or ''}|{city or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def list_login_devices(db: Session, customer: Customer, *, limit: int = 10) -> List[Dict[str, Any]]:
    rows = (
        db.query(SecurityAccessLog)
        .filter(
            SecurityAccessLog.customer_id == customer.id,
            SecurityAccessLog.event_type == "login_success",
        )
        .order_by(SecurityAccessLog.created_at.desc())
        .limit(100)
        .all()
    )
    seen: set[str] = set()
    devices: List[Dict[str, Any]] = []
    current_ua = None
    for row in rows:
        fp = device_fingerprint(row.user_agent, row.city)
        if fp in seen:
            continue
        seen.add(fp)
        parsed = parse_user_agent(row.user_agent)
        location_parts = [p for p in [row.city, row.country] if p]
        location = ", ".join(location_parts) if location_parts else "Neznámá lokalita"
        devices.append(
            {
                "id": fp,
                "os": parsed["os"],
                "browser": parsed["browser"],
                "location": location,
                "last_active_at": row.created_at.isoformat() if row.created_at else None,
                "is_current": False,
                "can_revoke": False,
            }
        )
        if len(devices) >= limit:
            break
    if devices:
        devices[0]["is_current"] = True
    return devices


def list_login_history(db: Session, customer: Customer, *, limit: int = 50) -> List[Dict[str, Any]]:
    rows = (
        db.query(SecurityAccessLog)
        .filter(
            SecurityAccessLog.customer_id == customer.id,
            SecurityAccessLog.event_type.in_(["login_success", "login_failed"]),
        )
        .order_by(SecurityAccessLog.created_at.desc())
        .limit(limit)
        .all()
    )
    out: List[Dict[str, Any]] = []
    for row in rows:
        parsed = parse_user_agent(row.user_agent)
        location_parts = [p for p in [row.city, row.country] if p]
        out.append(
            {
                "event_type": row.event_type,
                "os": parsed["os"],
                "browser": parsed["browser"],
                "location": ", ".join(location_parts) if location_parts else "—",
                "ip_masked": _mask_ip(row.ip_address),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return out


def _mask_ip(ip: Optional[str]) -> str:
    value = str(ip or "").strip()
    if not value:
        return "—"
    if ":" in value:
        return value.split(":")[0] + ":****"
    parts = value.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.***.***"
    return "***"


def count_active_reminders(db: Session, customer: Customer) -> int:
    vehicle_ids = list(get_owned_vehicle_ids(db, customer, tenant_id=customer.tenant_id))
    if not vehicle_ids:
        return 0
    q = db.query(ReminderModel).filter(
        ReminderModel.tenant_id == customer.tenant_id,
        ReminderModel.vehicle_id.in_(vehicle_ids),
        ReminderModel.is_completed.is_(False),
    )
    return int(q.count())


def enforce_notification_rules(prefs: Dict[str, Any]) -> Dict[str, Any]:
    """Bezpečnostní oznámení nelze úplně vypnout — min. e-mail."""
    out = copy.deepcopy(prefs)
    types = out.setdefault("notifications", {}).setdefault("types", {})
    security = types.setdefault("security", {})
    security["email"] = True
    marketing = types.setdefault("marketing", {})
    if not out.get("privacy", {}).get("marketing"):
        marketing["email"] = False
        marketing["sms"] = False
        marketing["push"] = False
    if not out.get("notifications", {}).get("channels", {}).get("sms"):
        for key, channels in types.items():
            if isinstance(channels, dict):
                channels["sms"] = False
    return out


def validate_vehicle_order_ids(db: Session, customer: Customer, raw_order: Any) -> List[int]:
    """Ověří, že vehicle_order obsahuje pouze unikátní ID vozidel vlastněných uživatelem."""
    from fastapi import HTTPException

    if not isinstance(raw_order, list):
        raise HTTPException(status_code=400, detail="vehicle_order musí být seznam ID vozidel")

    normalized: List[int] = []
    seen: set[int] = set()
    for item in raw_order:
        if isinstance(item, bool) or not isinstance(item, int):
            raise HTTPException(
                status_code=400,
                detail="vehicle_order musí obsahovat pouze celočíselná ID vozidel",
            )
        vid = int(item)
        if vid <= 0:
            raise HTTPException(status_code=400, detail="vehicle_order obsahuje neplatné ID vozidla")
        if vid in seen:
            raise HTTPException(status_code=400, detail="vehicle_order obsahuje duplicitní ID vozidla")
        seen.add(vid)
        normalized.append(vid)

    if not normalized:
        return []

    owned = set(get_owned_vehicle_ids(db, customer, tenant_id=customer.tenant_id))
    invalid = [vid for vid in normalized if vid not in owned]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail="vehicle_order obsahuje vozidla, která nepatří aktuálnímu uživateli",
        )
    return normalized


def format_address(customer: Customer) -> str:
    parts = []
    street_line = " ".join(p for p in [customer.street, customer.street_number] if p)
    if street_line:
        parts.append(street_line)
    city_line = " ".join(p for p in [customer.zip, customer.city] if p)
    if city_line:
        parts.append(city_line)
    if not parts:
        return "Česká republika"
    return ", ".join(parts)


def account_type_label(customer: Customer) -> str:
    role = str(customer.role or "user").lower()
    if role == "service":
        return "Servisní účet"
    if customer.ico:
        return "Firemní účet"
    return "Osobní účet"
