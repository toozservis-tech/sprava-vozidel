"""
License Status API - endpoint pro získání informací o licenci
"""
from __future__ import annotations

import calendar
import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.core.branding import APP_DISPLAY_NAME
from ..audit_log import write_global_audit_log
from ..database import get_db
from ..models import (
    Customer,
    License,
    LicenseAuditLog,
    LicensePaymentTransaction,
    LicenseSubscription,
    PaymentEvent,
)
from ..schema_management import assert_module_ready
from src.server.runtime_settings import (
    get_runtime_setting_bool,
    get_runtime_setting_int,
    get_runtime_setting_text,
    load_runtime_settings,
)
from .auth import get_current_user
from ...licensing.service import (
    ADMIN_TENANT_ID,
    get_license_plan_base,
    get_license_status,
    map_catalog_plan_to_storage_plan,
    normalize_license_plan_key,
    pairing_role_for_tenant_license,
    upgrade_license_plan,
)
from ...email_client.service import EmailService, EmailMessage
from ...email_client.templates import build_app_url, render_email_layout, render_panel
from ..push_notifications import send_push_to_customer

router = APIRouter(prefix="/license", tags=["license"])
logger = logging.getLogger(__name__)

_PLAN_CODES = {"basic": "B", "premium": "P", "full": "F"}
_PLAN_CODES_REVERSED = {value: key for key, value in _PLAN_CODES.items()}
_BILLING_PERIOD_CODES = {"monthly": "M", "yearly": "Y"}
_BILLING_PERIOD_CODES_REVERSED = {value: key for key, value in _BILLING_PERIOD_CODES.items()}
_COMGATE_REF_PREFIX = "L"
_COMGATE_REF_TENANT_WIDTH = 6
_COMGATE_REF_NONCE_WIDTH = 8
_COMGATE_REF_MAX_TENANT_ID = (36 ** _COMGATE_REF_TENANT_WIDTH) - 1
_SUBSCRIPTION_PLAN_SET = {"free", "basic", "premium", "lifetime", "full"}
_SUBSCRIPTION_PERIOD_SET = {"monthly", "yearly"}
_SUBSCRIPTION_STATUS_SET = {
    "active",
    "cancel_at_period_end",
    "grace",
    "canceled",
    "legacy_manual",
}
_PAID_PLAN_SET = {"basic", "premium", "full"}
_SUBSCRIPTION_REQUIRED_TABLES = (
    "license_subscriptions",
    "license_payment_transactions",
)
_SUBSCRIPTION_REQUIRED_COLUMNS = {
    "license_subscriptions": {
        "credit_balance_halers",
    },
}
_SCHEMA_READY = False
_COMGATE_ALLOWED_PAYLOAD_KEYS = {
    "merchant",
    "test",
    "price",
    "curr",
    "label",
    "refId",
    "refid",
    "transId",
    "transid",
    "status",
    "method",
    "account",
    "fee",
    "paymentErrorReason",
    "paymenterrorreason",
    "code",
    "message",
    "_non_recurring_fallback",
    "_test_fallback_non_recurring",
}
_COMGATE_RECURRING_ID_KEYS = (
    "initRecurringId",
    "initrecurringid",
    "init_recurring_id",
    "recurringId",
    "recurringid",
    "recurring_id",
)


class LicenseStatusResponse(BaseModel):
    """Response s informacemi o licenci"""
    tenant_id: str
    plan: str
    effective_plan: Optional[str] = None
    status: str
    vehicles_limit: int
    vehicles_current: int
    vehicles_current_user: Optional[int] = None
    vehicles_remaining: Optional[int] = None
    is_unlimited: bool
    vehicles_count: Optional[int] = None
    license_limit: Optional[int] = None
    is_over_limit: Optional[bool] = None
    plan_base: Optional[str] = None
    plan_workspace_kind: Optional[str] = None
    plan_public_label: Optional[str] = None
    display_plan: Optional[str] = None
    stored_plan: Optional[str] = None
    valid_to: Optional[str] = None
    trial_started_at: Optional[str] = None
    trial_ends_at: Optional[str] = None
    trial_used_at: Optional[str] = None
    trial_plan: Optional[str] = None
    trial_active: bool = False
    trial_days_remaining: Optional[int] = None
    is_expired_trial: bool = False
    vin_decode_enabled: bool = True
    ares_enabled: bool = True
    reminders_enabled: bool = True
    vehicle_history_enabled: bool = False
    documents_enabled: bool = False
    costs_tracking_enabled: bool = False
    statistics_enabled: bool = False
    sharing_with_service_enabled: bool = False
    capabilities: Optional[dict] = None
    is_lifetime: bool = False
    subscription: Optional["SubscriptionStatusResponse"] = None
    license_banner: Optional["LicenseBannerResponse"] = None


class LicenseBannerResponse(BaseModel):
    tone: str = "warning"
    message: str
    cta_label: Optional[str] = "Detail"


class LicenseUpgradeRequest(BaseModel):
    plan: str


class SubscriptionStatusResponse(BaseModel):
    status: str
    auto_renew_enabled: bool
    recurring_ready: bool = False
    recurring_state_label: Optional[str] = None
    recurring_block_reason: Optional[str] = None
    billing_period: Optional[str] = None
    current_period_end: Optional[str] = None
    next_charge_at: Optional[str] = None
    grace_until: Optional[str] = None
    pending_plan_change: Optional[str] = None
    days_to_end: Optional[int] = None
    credit_balance_halers: int = 0


try:  # pydantic v2
    LicenseStatusResponse.model_rebuild()
except AttributeError:  # pydantic v1
    LicenseStatusResponse.update_forward_refs(
        SubscriptionStatusResponse=SubscriptionStatusResponse,
        LicenseBannerResponse=LicenseBannerResponse,
    )


class ComgateConfigResponse(BaseModel):
    provider: str
    enabled: bool
    configured: bool
    test_mode: bool
    currency: str
    method: str
    plans: Dict[str, Dict[str, Optional[int]]]


class ComgateCheckoutRequest(BaseModel):
    plan: str
    billing_period: str = "monthly"


class ComgateCheckoutResponse(BaseModel):
    provider: str
    plan: str
    billing_period: str
    trans_id: Optional[str] = None
    redirect_url: str = ""
    payment_status: str
    requires_payment: bool = True
    amount_halers: Optional[int] = None
    credit_balance_halers: Optional[int] = None
    message: Optional[str] = None


class SubscriptionChangePlanRequest(BaseModel):
    plan: str


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _load_comgate_config() -> Dict[str, object]:
    runtime_settings = load_runtime_settings()

    enabled = get_runtime_setting_bool("comgate", "enabled", _env_flag("COMGATE_ENABLED", False), settings=runtime_settings)
    merchant = get_runtime_setting_text("comgate", "merchant", os.getenv("COMGATE_MERCHANT", ""), settings=runtime_settings)
    secret = get_runtime_setting_text("comgate", "secret", os.getenv("COMGATE_SECRET", ""), settings=runtime_settings)
    test_mode = get_runtime_setting_bool("comgate", "test_mode", _env_flag("COMGATE_TEST_MODE", True), settings=runtime_settings)
    currency = get_runtime_setting_text("comgate", "currency", os.getenv("COMGATE_CURRENCY", "CZK") or "CZK", settings=runtime_settings).upper() or "CZK"
    method = get_runtime_setting_text("comgate", "method", os.getenv("COMGATE_METHOD", "ALL") or "ALL", settings=runtime_settings).upper() or "ALL"
    subscription_method = (
        get_runtime_setting_text(
            "comgate",
            "subscription_method",
            os.getenv("COMGATE_SUBSCRIPTION_METHOD", "CARD") or "CARD",
            settings=runtime_settings,
        ).upper()
        or "CARD"
    )
    test_one_time_fallback = get_runtime_setting_bool(
        "comgate",
        "test_one_time_fallback",
        _env_flag("COMGATE_TEST_ONE_TIME_FALLBACK", True),
        settings=runtime_settings,
    )
    lang = get_runtime_setting_text("comgate", "lang", os.getenv("COMGATE_LANG", "cs") or "cs", settings=runtime_settings).lower() or "cs"
    country = get_runtime_setting_text("comgate", "country", os.getenv("COMGATE_COUNTRY", "CZ") or "CZ", settings=runtime_settings).upper() or "CZ"

    create_url = (
        get_runtime_setting_text(
            "comgate",
            "create_url",
            os.getenv("COMGATE_CREATE_URL", "https://payments.comgate.cz/v1.0/create")
            or "https://payments.comgate.cz/v1.0/create",
            settings=runtime_settings,
        )
        or "https://payments.comgate.cz/v1.0/create"
    )
    status_url = (
        get_runtime_setting_text(
            "comgate",
            "status_url",
            os.getenv("COMGATE_STATUS_URL", "https://payments.comgate.cz/v1.0/status")
            or "https://payments.comgate.cz/v1.0/status",
            settings=runtime_settings,
        )
        or "https://payments.comgate.cz/v1.0/status"
    )

    basic_monthly = max(
        0,
        get_runtime_setting_int(
            "comgate",
            "price_basic_monthly_halers",
            _env_int("COMGATE_PRICE_BASIC_HALERS", 9900),
            settings=runtime_settings,
        ),
    )
    premium_monthly = max(
        0,
        get_runtime_setting_int(
            "comgate",
            "price_premium_monthly_halers",
            _env_int("COMGATE_PRICE_PREMIUM_HALERS", 29900),
            settings=runtime_settings,
        ),
    )
    full_monthly = max(
        0,
        get_runtime_setting_int(
            "comgate",
            "price_full_monthly_halers",
            _env_int("COMGATE_PRICE_FULL_HALERS", 59900),
            settings=runtime_settings,
        ),
    )
    basic_yearly_default = basic_monthly * 10 if basic_monthly > 0 else 0
    premium_yearly_default = premium_monthly * 10 if premium_monthly > 0 else 0
    full_yearly_default = full_monthly * 10 if full_monthly > 0 else 0
    plans = {
        "basic": {
            "monthly": basic_monthly,
            "yearly": max(
                0,
                get_runtime_setting_int(
                    "comgate",
                    "price_basic_yearly_halers",
                    _env_int("COMGATE_PRICE_BASIC_YEARLY_HALERS", basic_yearly_default),
                    settings=runtime_settings,
                ),
            ),
        },
        "premium": {
            "monthly": premium_monthly,
            "yearly": max(
                0,
                get_runtime_setting_int(
                    "comgate",
                    "price_premium_yearly_halers",
                    _env_int("COMGATE_PRICE_PREMIUM_YEARLY_HALERS", premium_yearly_default),
                    settings=runtime_settings,
                ),
            ),
        },
        "full": {
            "monthly": full_monthly,
            "yearly": max(
                0,
                get_runtime_setting_int(
                    "comgate",
                    "price_full_yearly_halers",
                    _env_int("COMGATE_PRICE_FULL_YEARLY_HALERS", full_yearly_default),
                    settings=runtime_settings,
                ),
            ),
        },
    }
    configured = bool(
        enabled
        and merchant
        and secret
        and create_url
        and status_url
        and plans["basic"]["monthly"] > 0
        and plans["premium"]["monthly"] > 0
        and plans["basic"]["yearly"] > 0
        and plans["premium"]["yearly"] > 0
        and plans["full"]["monthly"] > 0
        and plans["full"]["yearly"] > 0
    )
    return {
        "provider": "comgate",
        "enabled": enabled,
        "configured": configured,
        "merchant": merchant,
        "secret": secret,
        "test_mode": test_mode,
        "currency": currency,
        "method": method,
        "subscription_method": subscription_method,
        "test_one_time_fallback": test_one_time_fallback,
        "lang": lang,
        "country": country,
        "create_url": create_url,
        "status_url": status_url,
        "plans": plans,
    }


def _is_comgate_recurring_not_enabled_message(message: str) -> bool:
    normalized = str(message or "").strip().lower()
    if not normalized:
        return False
    return (
        "recurrent payments are not enabled" in normalized
        or "recurring" in normalized and "not enabled" in normalized
        or "opakované platby" in normalized and "nejsou povoleny" in normalized
    )


def _is_comgate_card_method_not_available(code: str, message: str) -> bool:
    normalized_code = str(code or "").strip()
    normalized_message = str(message or "").strip().lower()
    if normalized_code == "1109":
        return True
    if not normalized_message:
        return False
    return (
        "invalid payment method [card]" in normalized_message
        or "payment method [card]" in normalized_message and "invalid" in normalized_message
        or "payment method [card]" in normalized_message and "not allowed" in normalized_message
        or "payment method [card]" in normalized_message and "not enabled" in normalized_message
        or "platba kartou" in normalized_message and "není povolena" in normalized_message
        or "platební metoda [card]" in normalized_message and "neplat" in normalized_message
    )


def _normalize_plan(plan: str) -> str:
    normalized = str(plan or "").strip().lower()
    if normalized not in {"free", "basic", "premium", "full"}:
        raise HTTPException(
            status_code=400,
            detail="Neplatný plán. Povolené hodnoty: free, basic, premium, full.",
        )
    return normalized


def _normalize_billing_period(period: str) -> str:
    normalized = str(period or "").strip().lower()
    if normalized not in {"monthly", "yearly"}:
        raise HTTPException(status_code=400, detail="Neplatné období. Povolené: monthly, yearly.")
    return normalized


def _base36_encode(value: int) -> str:
    if value < 0:
        raise ValueError("value must be non-negative")
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if value == 0:
        return "0"
    result = []
    current = value
    while current:
        current, remainder = divmod(current, 36)
        result.append(alphabet[remainder])
    return "".join(reversed(result))


def _base36_decode(value: str) -> int:
    return int(str(value).strip().upper(), 36)


def _build_comgate_ref_id(tenant_id: int, plan: str, billing_period: str = "monthly") -> str:
    normalized_plan = _normalize_plan(plan)
    normalized_period = _normalize_billing_period(billing_period)
    if normalized_plan not in _PLAN_CODES:
        raise ValueError("Comgate checkout je dostupný jen pro BASIC / PREMIUM / FULL.")
    if tenant_id < 0 or tenant_id > _COMGATE_REF_MAX_TENANT_ID:
        raise ValueError("tenant_id je mimo podporovaný rozsah pro refId.")

    tenant_part = _base36_encode(tenant_id).zfill(_COMGATE_REF_TENANT_WIDTH)[-_COMGATE_REF_TENANT_WIDTH:]
    nonce_value = secrets.randbelow(36 ** _COMGATE_REF_NONCE_WIDTH)
    nonce_part = _base36_encode(nonce_value).zfill(_COMGATE_REF_NONCE_WIDTH)[-_COMGATE_REF_NONCE_WIDTH:]
    plan_code = _PLAN_CODES[normalized_plan]
    period_code = _BILLING_PERIOD_CODES[normalized_period]
    return f"{_COMGATE_REF_PREFIX}{tenant_part}{plan_code}{period_code}{nonce_part}"


def _parse_comgate_ref_id(ref_id: str) -> Optional[Tuple[int, str, str]]:
    value = str(ref_id or "").strip().upper()
    if not value.startswith(_COMGATE_REF_PREFIX):
        return None
    expected_new_length = 1 + _COMGATE_REF_TENANT_WIDTH + 1 + 1 + _COMGATE_REF_NONCE_WIDTH
    expected_old_length = 1 + _COMGATE_REF_TENANT_WIDTH + 1 + _COMGATE_REF_NONCE_WIDTH

    if len(value) == expected_new_length:
        tenant_part = value[1 : 1 + _COMGATE_REF_TENANT_WIDTH]
        plan_code = value[1 + _COMGATE_REF_TENANT_WIDTH]
        period_code = value[1 + _COMGATE_REF_TENANT_WIDTH + 1]
        if plan_code not in _PLAN_CODES_REVERSED or period_code not in _BILLING_PERIOD_CODES_REVERSED:
            return None
        try:
            tenant_id = _base36_decode(tenant_part)
        except (TypeError, ValueError):
            return None
        return tenant_id, _PLAN_CODES_REVERSED[plan_code], _BILLING_PERIOD_CODES_REVERSED[period_code]

    if len(value) == expected_old_length:
        tenant_part = value[1 : 1 + _COMGATE_REF_TENANT_WIDTH]
        plan_code = value[1 + _COMGATE_REF_TENANT_WIDTH]
        if plan_code not in _PLAN_CODES_REVERSED:
            return None
        try:
            tenant_id = _base36_decode(tenant_part)
        except (TypeError, ValueError):
            return None
        # Starý formát bez billing period bereme jako monthly.
        return tenant_id, _PLAN_CODES_REVERSED[plan_code], "monthly"

    return None


def _parse_comgate_response_text(raw: str) -> Dict[str, str]:
    parsed = parse_qs(str(raw or ""), keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}


def _request_frontend_base_url() -> str:
    from src.core.env_aliases import env_prefer_new

    configured = (
        os.getenv("FRONTEND_BASE_URL")
        or os.getenv("PUBLIC_API_BASE_URL")
        or env_prefer_new("SPRAVA_VOZIDEL_API_URL", "TOOZHUB_API_URL")
        or "http://127.0.0.1:8000"
    )
    return str(configured).strip().rstrip("/")


def _request_backend_public_url(request: Request) -> str:
    from src.core.env_aliases import env_prefer_new

    configured = os.getenv("PUBLIC_API_BASE_URL") or env_prefer_new("SPRAVA_VOZIDEL_API_URL", "TOOZHUB_API_URL")
    if configured and str(configured).strip():
        return str(configured).strip().rstrip("/")
    return str(request.base_url).rstrip("/")


def _build_frontend_return_url(plan: str, status: str, billing_period: str) -> str:
    base = _request_frontend_base_url()
    if base.endswith("/web/index.html"):
        page = base
    else:
        page = f"{base}/web/index.html"
    query = urlencode(
        {
            "payment_provider": "comgate",
            "payment_status": status,
            "plan": plan,
            "billing_period": billing_period,
        }
    )
    return f"{page}?{query}"


def _post_comgate(url: str, payload: Dict[str, str]) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        # Comgate Merchant API vrací key=value pár formát (ne text/html).
        "Accept": "application/x-www-form-urlencoded",
    }
    try:
        response = httpx.post(url, data=payload, headers=headers, timeout=15.0)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Comgate není dostupný: {exc}") from exc

    text = response.text or ""
    data = _parse_comgate_response_text(text)

    if response.status_code >= 400:
        message = data.get("message") or text[:300] or f"HTTP {response.status_code}"
        raise HTTPException(status_code=502, detail=f"Comgate chyba: {message}")

    return data


def _resolve_plan_from_status_payload(status_payload: Dict[str, str]) -> Optional[str]:
    ref_id = status_payload.get("refId") or status_payload.get("refid") or ""
    parsed_ref = _parse_comgate_ref_id(ref_id)
    if parsed_ref:
        return parsed_ref[1]

    label = str(status_payload.get("label") or "").strip().lower()
    if "full" in label:
        return "full"
    if "premium" in label:
        return "premium"
    if "basic" in label:
        return "basic"
    return None


def _resolve_billing_period_from_status_payload(status_payload: Dict[str, str]) -> str:
    ref_id = status_payload.get("refId") or status_payload.get("refid") or ""
    parsed_ref = _parse_comgate_ref_id(ref_id)
    if parsed_ref:
        return parsed_ref[2]

    label = str(status_payload.get("label") or "").strip().lower()
    if "roční" in label or "rocni" in label or "yearly" in label or "annual" in label:
        return "yearly"
    return "monthly"


def _price_for_plan(cfg: Dict[str, object], plan: str, billing_period: str) -> int:
    period = _normalize_billing_period(billing_period)
    plan_prices = cfg.get("plans", {}).get(plan, {}) if isinstance(cfg.get("plans"), dict) else {}
    return int(plan_prices.get(period) or 0)


def _safe_int(value: object) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _payload_hash(payload: Optional[Dict[str, object]]) -> Optional[str]:
    if payload is None:
        return None
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def sanitize_comgate_payload(payload: Optional[Dict[str, object]]) -> Dict[str, object]:
    if not isinstance(payload, dict):
        return {}

    sanitized: Dict[str, object] = {}
    for key in _COMGATE_ALLOWED_PAYLOAD_KEYS:
        if key in payload and payload.get(key) not in (None, ""):
            sanitized[key] = payload.get(key)

    code = payload.get("provider_response_code", payload.get("code"))
    message = payload.get("provider_response_message", payload.get("message"))
    if code not in (None, ""):
        sanitized["provider_response_code"] = code
    if message not in (None, ""):
        sanitized["provider_response_message"] = message

    # Neztrácíme recurring diagnostiku, ale neukládáme citlivý payload.
    recurring_id = None
    for key in _COMGATE_RECURRING_ID_KEYS:
        candidate = str(payload.get(key) or "").strip()
        if candidate:
            recurring_id = candidate
            break
    if recurring_id:
        sanitized["initRecurringId"] = recurring_id

    return sanitized


def _utcnow() -> datetime:
    return datetime.utcnow()


def _billing_catalog_plan_from_subscription_storage(db: Session, tenant_id: int, storage_plan: Optional[str]) -> str:
    raw = str(storage_plan or "").strip().lower()
    pair = pairing_role_for_tenant_license(db, tenant_id)
    norm = normalize_license_plan_key(raw, pair) or "free"
    if pair == "service":
        return "full" if get_license_plan_base(norm) == "full" else "free"
    base = get_license_plan_base(norm)
    if base in {"basic", "premium"}:
        return base
    return "free"


def _compute_license_ui_banner(
    *,
    status: Dict[str, Any],
    subscription_payload: Optional[Dict[str, Any]],
) -> Optional[Dict[str, str]]:
    if str(status.get("plan_workspace_kind") or "") == "user":
        if bool(status.get("is_expired_trial")):
            return {
                "tone": "warning",
                "message": (
                    "Zkušební období plné verze skončilo. Účet běží ve FREE režimu; "
                    "data zůstávají uložená. Pro další plnou práci vyberte a uhraďte licenci."
                ),
                "cta_label": "Vybrat licenci",
            }
        if bool(status.get("trial_active")):
            days = status.get("trial_days_remaining")
            day_text = f"{days} dní" if days is not None else "30 dní"
            return {
                "tone": "info",
                "message": (
                    f"Běží zkušební období plné verze. Zbývá {day_text}; "
                    "po skončení se účet přepne do FREE režimu bez ztráty dat."
                ),
                "cta_label": "Licence",
            }
        return None

    if str(status.get("plan_workspace_kind") or "") != "service":
        return None
    if not subscription_payload:
        return None
    now = _utcnow()
    sub_status = str(subscription_payload.get("status") or "").strip().lower()
    period_end = _from_iso(str(subscription_payload.get("current_period_end") or ""))
    days_left = _days_until(period_end, now)

    if sub_status == "grace":
        grace_until = _from_iso(str(subscription_payload.get("grace_until") or ""))
        gu = grace_until.strftime("%d.%m.%Y") if grace_until else "–"
        return {
            "tone": "warning",
            "message": (
                f"⚠ Platba předplatného se nepovedla. Před omezením účtu máte ochranou lhůtu do {gu}. "
                "Zkontrolujte kartu nebo aktivujte platbu v sekci Licence."
            ),
            "cta_label": "Detail",
        }

    plan_base = str(status.get("plan_base") or "").strip().lower()
    if plan_base != "full":
        return None
    if period_end is None:
        return None
    if days_left is None:
        return None
    if days_left < 0:
        return {
            "tone": "warning",
            "message": "⚠ Platné období licence vypršelo. Obnovte předplatné v sekci Licence.",
            "cta_label": "Detail",
        }
    if days_left <= 25:
        ds = period_end.strftime("%d.%m.%Y")
        return {
            "tone": "warning",
            "message": f"⚠ Licence vyprší za {days_left} dní ({ds}). Zajistěte včasnou obnovu.",
            "cta_label": "Detail",
        }
    return None


def _to_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.replace(microsecond=0).isoformat() + "Z"


def _from_iso(value: Optional[str]) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    # DB držíme v UTC without tzinfo.
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _add_billing_period(start_at: datetime, billing_period: str) -> datetime:
    period = _normalize_billing_period(billing_period)
    if period == "yearly":
        target_year = start_at.year + 1
        target_month = start_at.month
    else:
        target_year = start_at.year + (1 if start_at.month == 12 else 0)
        target_month = 1 if start_at.month == 12 else start_at.month + 1

    max_day = calendar.monthrange(target_year, target_month)[1]
    target_day = min(start_at.day, max_day)
    return start_at.replace(year=target_year, month=target_month, day=target_day)


def _days_until(value: Optional[datetime], now: Optional[datetime] = None) -> Optional[int]:
    if not value:
        return None
    current = now or _utcnow()
    delta = value - current
    return int(delta.total_seconds() // 86400)


def _remaining_period_ratio(
    current_period_start: Optional[datetime],
    current_period_end: Optional[datetime],
    *,
    now: Optional[datetime] = None,
) -> float:
    if not current_period_start or not current_period_end:
        return 0.0
    if current_period_end <= current_period_start:
        return 0.0
    current_now = now or _utcnow()
    total_seconds = max((current_period_end - current_period_start).total_seconds(), 1.0)
    remaining_seconds = (current_period_end - current_now).total_seconds()
    if remaining_seconds <= 0:
        return 0.0
    if remaining_seconds >= total_seconds:
        return 1.0
    return float(remaining_seconds / total_seconds)


def _compute_charge_amount_from_balance(*, balance_halers: int, base_amount_halers: int) -> int:
    if base_amount_halers <= 0:
        return 0
    return max(0, int(base_amount_halers) - int(balance_halers))


def _apply_balance_after_payment(*, balance_halers: int, base_amount_halers: int, paid_amount_halers: int) -> int:
    return int(balance_halers) + int(paid_amount_halers) - int(base_amount_halers)


def _legacy_quote_payload_from_checkout_tx(tx: Optional[LicensePaymentTransaction]) -> Optional[Dict[str, Any]]:
    if not tx:
        return None
    raw = str(tx.payload_json or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    quote = parsed.get("legacy_quote")
    if not isinstance(quote, dict):
        return None
    return quote


def _checkout_is_non_recurring_fallback(tx: Optional[LicensePaymentTransaction]) -> bool:
    if not tx:
        return False

    event_type = str(tx.event_type or "").strip().lower()
    if event_type in {
        "checkout_created_test_fallback",
        "checkout_created_legacy_quote_test_fallback",
        "checkout_created_fallback",
        "checkout_created_legacy_quote_fallback",
    }:
        return True

    provider_status = str(tx.provider_status or "").strip().upper()
    if provider_status in {"PENDING_TEST_FALLBACK", "PENDING_FALLBACK"}:
        return True

    raw = str(tx.payload_json or "").strip()
    if not raw:
        return False
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False

    marker = payload.get("_non_recurring_fallback")
    if marker is None:
        marker = payload.get("_test_fallback_non_recurring")
    if marker is None:
        return False
    return str(marker).strip().lower() in {"1", "true", "yes", "on"}


def _build_legacy_checkout_quote(
    *,
    cfg: Dict[str, object],
    subscription: LicenseSubscription,
    target_plan: str,
    billing_period: str,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    current_now = now or _utcnow()
    current_plan = _normalize_plan_soft(subscription.plan_current or "free")
    target_plan_norm = _normalize_plan_soft(str(target_plan or "").strip().lower(), default="premium")
    billing_period_norm = _normalize_billing_period(billing_period)
    effective_period = _normalize_billing_period_soft(subscription.billing_period, default=billing_period_norm)

    quote_kind = "legacy_full_cycle"
    source_full_halers = 0
    target_full_halers = _price_for_plan(cfg, target_plan_norm, billing_period_norm)
    if target_full_halers <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cena plánu {target_plan_norm.upper()} ({billing_period_norm}) není nastavena.",
        )

    source_remaining_halers = 0
    target_remaining_halers = target_full_halers
    remaining_ratio = 0.0
    keep_period_boundaries = False
    quote_base_amount_halers = target_full_halers
    quote_period = billing_period_norm

    if (
        current_plan in _PAID_PLAN_SET
        and target_plan_norm in _PAID_PLAN_SET
        and current_plan != target_plan_norm
        and effective_period == billing_period_norm
        and subscription.current_period_start is not None
        and subscription.current_period_end is not None
        and subscription.current_period_end > current_now
    ):
        source_full_halers = _price_for_plan(cfg, current_plan, effective_period)
        target_full_halers = _price_for_plan(cfg, target_plan_norm, effective_period)
        if source_full_halers <= 0 or target_full_halers <= 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Pro přepočet Legacy období chybí ceny plánů. "
                    "Doplňte Comgate ceny pro aktuální i cílový plán."
                ),
            )
        remaining_ratio = _remaining_period_ratio(
            subscription.current_period_start,
            subscription.current_period_end,
            now=current_now,
        )
        source_remaining_halers = int(round(source_full_halers * remaining_ratio))
        target_remaining_halers = int(round(target_full_halers * remaining_ratio))
        quote_base_amount_halers = target_remaining_halers - source_remaining_halers
        keep_period_boundaries = True
        quote_kind = "legacy_proration_change"
        quote_period = effective_period

    balance_before_halers = int(subscription.credit_balance_halers or 0)
    charge_amount_halers = _compute_charge_amount_from_balance(
        balance_halers=balance_before_halers,
        base_amount_halers=quote_base_amount_halers,
    )
    balance_after_halers = _apply_balance_after_payment(
        balance_halers=balance_before_halers,
        base_amount_halers=quote_base_amount_halers,
        paid_amount_halers=charge_amount_halers,
    )

    return {
        "kind": quote_kind,
        "source_plan": current_plan,
        "target_plan": target_plan_norm,
        "billing_period": quote_period,
        "base_amount_halers": int(quote_base_amount_halers),
        "charge_amount_halers": int(charge_amount_halers),
        "balance_before_halers": int(balance_before_halers),
        "balance_after_halers": int(balance_after_halers),
        "keep_period_boundaries": bool(keep_period_boundaries),
        "remaining_ratio": float(remaining_ratio),
        "source_full_halers": int(source_full_halers),
        "target_full_halers": int(target_full_halers),
        "source_remaining_halers": int(source_remaining_halers),
        "target_remaining_halers": int(target_remaining_halers),
        "current_period_start": _to_iso(subscription.current_period_start),
        "current_period_end": _to_iso(subscription.current_period_end),
    }


def _subscription_notify_days(*, settings: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None) -> List[int]:
    raw = get_runtime_setting_text(
        "comgate",
        "subscription_notify_days",
        str(os.getenv("COMGATE_SUBSCRIPTION_NOTIFY_DAYS", "14,7,1") or "14,7,1").strip(),
        settings=settings,
    )
    result: List[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            val = int(chunk)
        except ValueError:
            continue
        if val >= 0:
            result.append(val)
    if not result:
        return [14, 7, 1]
    return sorted(set(result), reverse=True)


def _load_subscription_runtime_config() -> Dict[str, object]:
    runtime_settings = load_runtime_settings()
    return {
        "recurring_url": (
            get_runtime_setting_text(
                "comgate",
                "recurring_url",
                os.getenv("COMGATE_RECURRING_URL", "https://payments.comgate.cz/v1.0/recurring")
                or "https://payments.comgate.cz/v1.0/recurring",
                settings=runtime_settings,
            )
            or "https://payments.comgate.cz/v1.0/recurring"
        ),
        "recurring_enabled": get_runtime_setting_bool(
            "comgate",
            "recurring_enabled",
            _env_flag("COMGATE_RECURRING_ENABLED", True),
            settings=runtime_settings,
        ),
        "grace_days": max(
            1,
            get_runtime_setting_int(
                "comgate",
                "subscription_grace_days",
                _env_int("COMGATE_SUBSCRIPTION_GRACE_DAYS", 7),
                settings=runtime_settings,
            ),
        ),
        "notify_days": _subscription_notify_days(settings=runtime_settings),
    }


def _normalize_plan_soft(plan: Optional[str], default: str = "free") -> str:
    normalized = str(plan or "").strip().lower()
    if normalized.startswith("service_"):
        normalized = normalized[len("service_") :]
    if normalized in _SUBSCRIPTION_PLAN_SET:
        return normalized
    return default


def _catalog_base_plan_soft(plan: Optional[str], default: str = "free") -> str:
    """Stejné jako `_normalize_plan_soft` — alias pro kontext „Comgate/basic katalog“. """
    return _normalize_plan_soft(plan, default=default)


def _normalize_billing_period_soft(period: Optional[str], default: str = "monthly") -> str:
    normalized = str(period or "").strip().lower()
    if normalized in _SUBSCRIPTION_PERIOD_SET:
        return normalized
    return default


def _ensure_subscription_schema(db: Session, *, strict: bool = True) -> bool:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return True
    try:
        assert_module_ready(db, "subscriptions", detail_prefix="Licenční předplatné není připravené")
        _SCHEMA_READY = True
        return True
    except HTTPException:
        if strict:
            raise
        return False


def _normalize_subscription_status(value: Optional[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in _SUBSCRIPTION_STATUS_SET:
        return "legacy_manual"
    return normalized


def _detect_recurring_url_version(url: Optional[str]) -> str:
    raw = str(url or "").strip().lower()
    if "/v2.0/" in raw:
        return "v2.0"
    if "/v1.0/" in raw:
        return "v1.0"
    return "unknown"


def _subscription_recurring_state_label(subscription: LicenseSubscription) -> str:
    recurring_ready = bool(getattr(subscription, "recurring_ready", False))
    auto_renew_enabled = bool(subscription.auto_renew_enabled)
    init_recurring_id = str(subscription.init_recurring_id or "").strip()
    if auto_renew_enabled and recurring_ready and init_recurring_id:
        return "active"
    if auto_renew_enabled and not recurring_ready:
        return "pending_initial_card_payment"
    if not auto_renew_enabled and recurring_ready:
        return "inactive"
    return "not_available"


def _serialize_subscription(
    subscription: Optional[LicenseSubscription],
    *,
    license_plan: str,
    now: Optional[datetime] = None,
) -> Optional[Dict[str, object]]:
    current_now = now or _utcnow()
    if not subscription:
        if get_license_plan_base(license_plan) in {"basic", "premium", "full"}:
            return {
                "status": "legacy_manual",
                "auto_renew_enabled": False,
                "recurring_ready": False,
                "recurring_state_label": "pending_initial_card_payment",
                "recurring_block_reason": "missing_subscription",
                "billing_period": None,
                "current_period_end": None,
                "next_charge_at": None,
                "grace_until": None,
                "pending_plan_change": None,
                "days_to_end": None,
                "credit_balance_halers": 0,
            }
        return None

    period_end = subscription.current_period_end
    return {
        "status": _normalize_subscription_status(subscription.status),
        "auto_renew_enabled": bool(subscription.auto_renew_enabled),
        "recurring_ready": bool(getattr(subscription, "recurring_ready", False)),
        "recurring_state_label": _subscription_recurring_state_label(subscription),
        "recurring_block_reason": getattr(subscription, "recurring_block_reason", None),
        "billing_period": subscription.billing_period,
        "current_period_end": _to_iso(period_end),
        "next_charge_at": _to_iso(subscription.next_charge_at),
        "grace_until": _to_iso(subscription.grace_until),
        "pending_plan_change": subscription.pending_plan_change,
        "days_to_end": _days_until(period_end, current_now),
        "credit_balance_halers": int(subscription.credit_balance_halers or 0),
    }


def _finalize_license_http_payload(
    db: Session,
    *,
    tenant_id: int,
    status: Dict[str, Any],
) -> Dict[str, Any]:
    subscription = _get_subscription(db, tenant_id)
    sub_payload = _serialize_subscription(subscription, license_plan=status.get("effective_plan") or status.get("plan", "free"))
    merged = dict(status)
    merged["subscription"] = sub_payload
    merged["license_banner"] = _compute_license_ui_banner(status=merged, subscription_payload=sub_payload)
    return merged


def _get_subscription(db: Session, tenant_id: int) -> Optional[LicenseSubscription]:
    return db.query(LicenseSubscription).filter(LicenseSubscription.tenant_id == tenant_id).first()


def _upsert_subscription(db: Session, tenant_id: int) -> LicenseSubscription:
    subscription = _get_subscription(db, tenant_id)
    if subscription:
        return subscription
    subscription = LicenseSubscription(
        tenant_id=tenant_id,
        provider="comgate",
        status="legacy_manual",
        auto_renew_enabled=False,
        credit_balance_halers=0,
        failed_renewal_attempts=0,
    )
    db.add(subscription)
    db.flush()
    return subscription


def _write_license_audit(
    db: Session,
    *,
    tenant_id: int,
    subscription_id: Optional[int],
    action: str,
    old_status: Optional[str] = None,
    new_status: Optional[str] = None,
    reason: Optional[str] = None,
    actor_type: str = "system",
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    db.add(
        LicenseAuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            subscription_id=subscription_id,
            action=(action or "")[:128],
            old_status=old_status,
            new_status=new_status,
            reason=reason,
            actor_type=(actor_type or "system")[:32],
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=_utcnow(),
        )
    )


def _record_payment_event(
    db: Session,
    *,
    payment_id: Optional[int],
    provider: str,
    event_type: str,
    provider_transaction_id: Optional[str],
    raw_payload: Optional[Dict[str, object]],
    processing_status: str,
    error_message: Optional[str] = None,
) -> PaymentEvent:
    sanitized_payload = sanitize_comgate_payload(raw_payload)
    event = PaymentEvent(
        payment_id=payment_id,
        provider=provider,
        event_type=event_type,
        provider_transaction_id=provider_transaction_id,
        payload_hash=_payload_hash(raw_payload),
        sanitized_payload_json=_canonical_json(sanitized_payload)[:20000] if sanitized_payload else None,
        received_at=_utcnow(),
        processed_at=_utcnow(),
        processing_status=processing_status,
        error_message=error_message,
    )
    db.add(event)
    db.flush()
    return event


def extract_init_recurring_id(
    status_payload: Optional[Dict[str, object]],
    callback_payload: Optional[Dict[str, object]],
    payment_row: Optional[LicensePaymentTransaction],
) -> Optional[str]:
    for source in (status_payload, callback_payload):
        if not isinstance(source, dict):
            continue
        for key in _COMGATE_RECURRING_ID_KEYS:
            candidate = str(source.get(key) or "").strip()
            if candidate:
                return candidate

    if payment_row:
        payload_json = str(payment_row.payload_json or "").strip()
        if payload_json:
            try:
                payload = json.loads(payload_json)
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict):
                for key in _COMGATE_RECURRING_ID_KEYS:
                    candidate = str(payload.get(key) or "").strip()
                    if candidate:
                        return candidate
    return None


def _record_payment_transaction(
    db: Session,
    *,
    subscription_id: Optional[int] = None,
    tenant_id: int,
    provider: str,
    trans_id: Optional[str],
    ref_id: Optional[str],
    payment_type: Optional[str],
    parent_provider_transaction_id: Optional[str] = None,
    parent_init_recurring_id: Optional[str] = None,
    plan: Optional[str],
    billing_period: Optional[str],
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
    amount_halers: Optional[int],
    currency: Optional[str],
    event_type: str,
    provider_status: Optional[str],
    payload: Optional[Dict[str, object]],
) -> LicensePaymentTransaction:
    tx = None
    if trans_id:
        tx = (
            db.query(LicensePaymentTransaction)
            .filter(LicensePaymentTransaction.trans_id == trans_id)
            .first()
        )
    if not tx:
        tx = LicensePaymentTransaction(
            tenant_id=tenant_id,
            provider=provider,
            trans_id=trans_id,
        )
        db.add(tx)
    tx.tenant_id = tenant_id
    tx.subscription_id = subscription_id
    tx.provider = provider
    tx.ref_id = ref_id
    tx.payment_type = payment_type
    tx.parent_provider_transaction_id = parent_provider_transaction_id
    tx.parent_init_recurring_id = parent_init_recurring_id
    tx.plan = plan
    tx.billing_period = billing_period
    tx.period_start = period_start
    tx.period_end = period_end
    tx.amount_halers = amount_halers
    tx.currency = currency
    tx.event_type = event_type
    tx.provider_status = provider_status
    if payload is not None:
        sanitized_payload = sanitize_comgate_payload(payload)
        tx.payload_json = _canonical_json(sanitized_payload)[:20000] if sanitized_payload else None
        tx.raw_provider_payload_hash = _payload_hash(payload)
        tx.provider_response_code = str(payload.get("provider_response_code") or payload.get("code") or "")[:64] or None
        tx.provider_response_message = str(
            payload.get("provider_response_message") or payload.get("message") or ""
        )[:2000] or None
    tx.updated_at = _utcnow()
    db.flush()
    return tx


def _is_trans_already_paid(db: Session, trans_id: str) -> bool:
    existing = (
        db.query(LicensePaymentTransaction)
        .filter(LicensePaymentTransaction.trans_id == trans_id)
        .first()
    )
    if not existing:
        return False
    return str(existing.event_type or "").strip().lower() in {"paid_confirmed", "renewal_paid"}


def _notification_targets_for_tenant(db: Session, tenant_id: int) -> List[Customer]:
    rows = (
        db.query(Customer)
        .filter(
            Customer.tenant_id == tenant_id,
            Customer.email.isnot(None),
            Customer.password_hash.isnot(None),
            Customer.role != "service",
        )
        .order_by(Customer.id.asc())
        .all()
    )
    return rows


def _send_subscription_notification(
    db: Session,
    *,
    tenant_id: int,
    email_subject: str,
    email_text: str,
    push_title: str,
    push_body: str,
) -> Dict[str, int]:
    targets = _notification_targets_for_tenant(db, tenant_id)
    email_sent = 0
    push_sent = 0
    email_service = EmailService()
    email_ready = email_service.is_configured()

    for target in targets:
        if email_ready:
            try:
                html_body = render_email_layout(
                    title=email_subject,
                    subtitle="Informace o stavu předplatného a licence.",
                    intro="Dobrý den,",
                    paragraphs=[email_text],
                    panels=[
                        render_panel(
                            title="Účet",
                            rows=[("Příjemce", target.email)],
                            accent="#3b82f6",
                            tone="#eff6ff",
                        )
                    ],
                    cta_label="Otevřít licenci",
                    cta_url=build_app_url(),
                    accent="#f59e0b",
                )
                message = EmailMessage(
                    to=[target.email],
                    subject=email_subject,
                    body=email_text,
                    html_body=html_body,
                )
                email_service.send_email(message)
                email_sent += 1
            except Exception as exc:
                logger.warning(
                    "[LICENSE SUBSCRIPTION] Email notify failed tenant=%s customer=%s: %s",
                    tenant_id,
                    target.id,
                    exc,
                )
        try:
            push_result = send_push_to_customer(
                db,
                tenant_id=tenant_id,
                customer_id=target.id,
                title=push_title,
                body=push_body,
                url="/web/index.html",
                tag="license-subscription",
            )
            push_sent += int(push_result.get("sent", 0))
        except Exception as exc:
            logger.warning(
                "[LICENSE SUBSCRIPTION] Push notify failed tenant=%s customer=%s: %s",
                tenant_id,
                target.id,
                exc,
            )

    return {"email_sent": email_sent, "push_sent": push_sent}


def _activate_subscription_from_paid_payment(
    db: Session,
    *,
    tenant_id: int,
    plan: str,
    billing_period: str,
    trans_id: str,
    init_recurring_id: Optional[str],
) -> LicenseSubscription:
    paid_at = _utcnow()
    upgrade_license_plan(db, tenant_id, plan)

    subscription = _upsert_subscription(db, tenant_id)
    previous_status = _normalize_subscription_status(subscription.status)
    subscription.provider = "comgate"
    subscription.status = "active"
    subscription.plan_current = plan
    subscription.billing_period = billing_period
    subscription.auto_renew_enabled = bool(init_recurring_id)
    subscription.pending_plan_change = None
    subscription.credit_balance_halers = 0
    subscription.init_recurring_id = str(init_recurring_id).strip() if init_recurring_id else None
    subscription.provider_init_transaction_id = trans_id
    subscription.recurring_ready = bool(init_recurring_id)
    subscription.recurring_block_reason = None if init_recurring_id else "missing_init_recurring_id"
    subscription.current_period_start = paid_at
    subscription.current_period_end = _add_billing_period(paid_at, billing_period)
    subscription.next_charge_at = subscription.current_period_end if subscription.auto_renew_enabled else None
    subscription.grace_until = None
    subscription.cancel_requested_at = None
    subscription.last_payment_at = paid_at
    subscription.last_trans_id = trans_id
    subscription.last_recurring_result = "ready" if init_recurring_id else "missing_init_recurring_id"
    subscription.failed_renewal_attempts = 0
    subscription.notified_renewal_failed_at = None
    subscription.notified_grace_end_at = None
    subscription.notified_period_d14_at = None
    subscription.notified_period_d7_at = None
    subscription.notified_period_d1_at = None
    subscription.updated_at = paid_at
    db.add(subscription)
    db.flush()
    _write_license_audit(
        db,
        tenant_id=tenant_id,
        subscription_id=subscription.id,
        action="subscription_activated",
        old_status=previous_status,
        new_status="active",
        reason="initial_payment_paid",
        actor_type="provider",
    )
    if not init_recurring_id:
        _write_license_audit(
            db,
            tenant_id=tenant_id,
            subscription_id=subscription.id,
            action="missing_init_recurring_id",
            old_status="active",
            new_status="active",
            reason="initial_payment_paid_without_recurring_reference",
            actor_type="provider",
        )
    return subscription


def _activate_legacy_manual_subscription_from_paid_payment(
    db: Session,
    *,
    tenant_id: int,
    plan: str,
    billing_period: str,
    trans_id: str,
) -> LicenseSubscription:
    paid_at = _utcnow()
    upgrade_license_plan(db, tenant_id, plan)

    subscription = _upsert_subscription(db, tenant_id)
    previous_status = _normalize_subscription_status(subscription.status)
    subscription.provider = "comgate"
    subscription.status = "legacy_manual"
    subscription.plan_current = plan
    subscription.billing_period = billing_period
    subscription.auto_renew_enabled = False
    subscription.pending_plan_change = None
    subscription.init_recurring_id = None
    subscription.provider_init_transaction_id = trans_id
    subscription.recurring_ready = False
    subscription.recurring_block_reason = "missing_init_recurring_id"
    subscription.credit_balance_halers = int(subscription.credit_balance_halers or 0)
    subscription.current_period_start = paid_at
    subscription.current_period_end = _add_billing_period(paid_at, billing_period)
    subscription.next_charge_at = None
    subscription.grace_until = None
    subscription.cancel_requested_at = None
    subscription.last_payment_at = paid_at
    subscription.last_trans_id = trans_id
    subscription.last_recurring_result = "manual_only"
    subscription.failed_renewal_attempts = 0
    subscription.notified_renewal_failed_at = None
    subscription.notified_grace_end_at = None
    subscription.notified_period_d14_at = None
    subscription.notified_period_d7_at = None
    subscription.notified_period_d1_at = None
    subscription.updated_at = paid_at
    db.add(subscription)
    db.flush()
    _write_license_audit(
        db,
        tenant_id=tenant_id,
        subscription_id=subscription.id,
        action="subscription_activated",
        old_status=previous_status,
        new_status="legacy_manual",
        reason="fallback_or_manual_payment",
        actor_type="provider",
    )
    return subscription


def _apply_legacy_quote_without_payment(
    db: Session,
    *,
    tenant_id: int,
    subscription: LicenseSubscription,
    quote: Dict[str, Any],
) -> LicenseSubscription:
    now = _utcnow()
    cat_plan = _catalog_base_plan_soft(str(quote.get("target_plan") or subscription.plan_current or "free"))
    storage_plan = map_catalog_plan_to_storage_plan(db, tenant_id, cat_plan)
    billing_period = _normalize_billing_period_soft(str(quote.get("billing_period") or subscription.billing_period), default="monthly")
    keep_period_boundaries = bool(quote.get("keep_period_boundaries"))

    upgrade_license_plan(db, tenant_id, storage_plan)
    subscription.provider = "comgate"
    subscription.status = "legacy_manual"
    subscription.plan_current = storage_plan
    subscription.billing_period = billing_period
    subscription.auto_renew_enabled = False
    subscription.pending_plan_change = None
    subscription.init_recurring_id = None
    subscription.provider_init_transaction_id = None
    subscription.recurring_ready = False
    subscription.recurring_block_reason = "legacy_manual_proration"
    subscription.next_charge_at = None
    subscription.grace_until = None
    subscription.cancel_requested_at = None
    subscription.failed_renewal_attempts = 0
    subscription.last_recurring_result = "manual_only"
    subscription.credit_balance_halers = int(quote.get("balance_after_halers") or 0)

    if keep_period_boundaries:
        q_start = _from_iso(str(quote.get("current_period_start") or ""))
        q_end = _from_iso(str(quote.get("current_period_end") or ""))
        if subscription.current_period_end and subscription.current_period_end > now:
            # Preferujeme aktuální běžící období v DB.
            pass
        elif q_end and q_end > now:
            subscription.current_period_start = q_start
            subscription.current_period_end = q_end
        else:
            subscription.current_period_start = now
            subscription.current_period_end = _add_billing_period(now, billing_period)
    else:
        subscription.current_period_start = now
        subscription.current_period_end = _add_billing_period(now, billing_period)
    subscription.updated_at = now
    db.add(subscription)

    _record_payment_transaction(
        db=db,
        subscription_id=subscription.id,
        tenant_id=tenant_id,
        provider="comgate",
        trans_id=None,
        ref_id=None,
        payment_type="manual_renewal",
        plan=storage_plan,
        billing_period=billing_period,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        amount_halers=0,
        currency="CZK",
        event_type="legacy_quote_applied_no_payment",
        provider_status="APPLIED",
        payload={"legacy_quote": quote},
    )

    db.commit()
    db.refresh(subscription)
    return subscription


def _apply_legacy_quote_after_paid_callback(
    db: Session,
    *,
    tenant_id: int,
    subscription: LicenseSubscription,
    quote: Dict[str, Any],
    trans_id: str,
    paid_amount_halers: int,
) -> LicenseSubscription:
    now = _utcnow()
    cat_plan = _catalog_base_plan_soft(str(quote.get("target_plan") or subscription.plan_current or "free"))
    storage_plan = map_catalog_plan_to_storage_plan(db, tenant_id, cat_plan)
    billing_period = _normalize_billing_period_soft(str(quote.get("billing_period") or subscription.billing_period), default="monthly")
    keep_period_boundaries = bool(quote.get("keep_period_boundaries"))
    base_amount_halers = _safe_int(quote.get("base_amount_halers")) or 0
    balance_before_halers = int(subscription.credit_balance_halers or 0)
    balance_after_halers = _apply_balance_after_payment(
        balance_halers=balance_before_halers,
        base_amount_halers=base_amount_halers,
        paid_amount_halers=int(paid_amount_halers),
    )

    upgrade_license_plan(db, tenant_id, storage_plan)
    subscription.provider = "comgate"
    subscription.status = "legacy_manual"
    subscription.plan_current = storage_plan
    subscription.billing_period = billing_period
    subscription.auto_renew_enabled = False
    subscription.pending_plan_change = None
    subscription.init_recurring_id = None
    subscription.provider_init_transaction_id = trans_id
    subscription.recurring_ready = False
    subscription.recurring_block_reason = "legacy_manual_proration"
    subscription.next_charge_at = None
    subscription.grace_until = None
    subscription.cancel_requested_at = None
    subscription.failed_renewal_attempts = 0
    subscription.last_payment_at = now
    subscription.last_trans_id = trans_id
    subscription.last_recurring_result = "manual_only"
    subscription.credit_balance_halers = int(balance_after_halers)

    if keep_period_boundaries:
        q_start = _from_iso(str(quote.get("current_period_start") or ""))
        q_end = _from_iso(str(quote.get("current_period_end") or ""))
        if subscription.current_period_end and subscription.current_period_end > now:
            pass
        elif q_end and q_end > now:
            subscription.current_period_start = q_start
            subscription.current_period_end = q_end
        else:
            subscription.current_period_start = now
            subscription.current_period_end = _add_billing_period(now, billing_period)
    else:
        subscription.current_period_start = now
        subscription.current_period_end = _add_billing_period(now, billing_period)

    subscription.updated_at = now
    db.add(subscription)
    db.flush()
    return subscription


def _apply_recurring_payment_success(
    db: Session,
    *,
    subscription: LicenseSubscription,
    plan: str,
    billing_period: str,
    trans_id: str,
    period_start: Optional[datetime],
    period_end: Optional[datetime],
) -> LicenseSubscription:
    now = _utcnow()
    previous_status = _normalize_subscription_status(subscription.status)
    effective_start = period_start or subscription.current_period_end or now
    effective_end = period_end or _add_billing_period(effective_start, billing_period)
    if subscription.current_period_end and subscription.current_period_end >= effective_end:
        return subscription

    upgrade_license_plan(db, int(subscription.tenant_id), plan)
    subscription.status = "active"
    subscription.plan_current = plan
    subscription.billing_period = billing_period
    subscription.current_period_start = effective_start
    subscription.current_period_end = effective_end
    subscription.next_charge_at = effective_end if subscription.auto_renew_enabled else None
    subscription.grace_until = None
    subscription.last_payment_at = now
    subscription.last_trans_id = trans_id
    subscription.failed_renewal_attempts = 0
    subscription.recurring_ready = bool(subscription.init_recurring_id)
    subscription.recurring_block_reason = None if subscription.recurring_ready else "missing_init_recurring_id"
    subscription.last_recurring_result = "paid"
    subscription.updated_at = now
    db.add(subscription)
    db.flush()
    _write_license_audit(
        db,
        tenant_id=int(subscription.tenant_id),
        subscription_id=subscription.id,
        action="recurring_payment_paid",
        old_status=previous_status,
        new_status="active",
        reason="provider_callback_paid",
        actor_type="provider",
    )
    return subscription


def _subscription_notification_stamp_field(days: int) -> Optional[str]:
    if days == 14:
        return "notified_period_d14_at"
    if days == 7:
        return "notified_period_d7_at"
    if days == 1:
        return "notified_period_d1_at"
    return None


def _build_renewal_ref_id(tenant_id: int, plan: str, billing_period: str = "monthly") -> str:
    return _build_comgate_ref_id(tenant_id, plan, billing_period)


def _charge_subscription_recurring(
    *,
    db: Session,
    cfg: Dict[str, object],
    runtime_cfg: Dict[str, object],
    subscription: LicenseSubscription,
    tenant_id: int,
    plan: str,
    billing_period: str,
) -> Dict[str, object]:
    status = _normalize_subscription_status(subscription.status)
    if not bool(runtime_cfg.get("recurring_enabled", True)):
        return {"ok": False, "reason": "recurring_disabled_by_config"}
    if not bool(subscription.auto_renew_enabled):
        return {"ok": False, "reason": "auto_renew_disabled"}
    if status in {"canceled"}:
        return {"ok": False, "reason": "subscription_inactive"}

    init_recurring_id = str(subscription.init_recurring_id or "").strip()
    if not init_recurring_id:
        return {"ok": False, "reason": "missing_init_recurring_id"}

    price = _price_for_plan(cfg, plan, billing_period)
    if price <= 0:
        return {"ok": False, "reason": "missing_price"}

    now = _utcnow()
    period_start = subscription.current_period_end or now
    if period_start < now - timedelta(days=3):
        period_start = now
    period_end = _add_billing_period(period_start, billing_period)

    existing_period_tx = (
        db.query(LicensePaymentTransaction)
        .filter(
            LicensePaymentTransaction.subscription_id == subscription.id,
            LicensePaymentTransaction.payment_type == "recurring",
            LicensePaymentTransaction.period_start == period_start,
            LicensePaymentTransaction.period_end == period_end,
            LicensePaymentTransaction.provider_status.in_(["PENDING", "PAID", "AUTHORIZED"]),
        )
        .first()
    )
    if existing_period_tx:
        return {
            "ok": False,
            "reason": "duplicate_period_charge",
            "existing_trans_id": existing_period_tx.trans_id,
            "period_start": period_start,
            "period_end": period_end,
        }

    recurring_payload = {
        "merchant": str(cfg["merchant"]),
        "secret": str(cfg["secret"]),
        "initRecurringId": init_recurring_id,
        "price": str(price),
        "curr": str(cfg["currency"]),
        "label": f"{APP_DISPLAY_NAME} {plan.upper()} {'MĚSÍČNĚ' if billing_period == 'monthly' else 'ROČNĚ'}",
        "refId": _build_renewal_ref_id(tenant_id, plan, billing_period),
        "test": "1" if bool(cfg["test_mode"]) else "0",
    }
    account = str(cfg.get("account") or "").strip()
    name = str(cfg.get("name") or "").strip()
    if account:
        recurring_payload["account"] = account
    if name:
        recurring_payload["name"] = name

    recurring_result = _post_comgate(str(runtime_cfg["recurring_url"]), recurring_payload)
    if str(recurring_result.get("code", "")) != "0":
        return {
            "ok": False,
            "reason": recurring_result.get("message") or "recurring_create_failed",
            "provider_payload": recurring_result,
            "period_start": period_start,
            "period_end": period_end,
        }

    trans_id = str(recurring_result.get("transId") or "").strip()
    if not trans_id:
        return {
            "ok": False,
            "reason": "missing_trans_id",
            "provider_payload": recurring_result,
            "period_start": period_start,
            "period_end": period_end,
        }

    status_result = _post_comgate(
        str(cfg["status_url"]),
        {
            "merchant": str(cfg["merchant"]),
            "secret": str(cfg["secret"]),
            "transId": trans_id,
            "test": "1" if bool(cfg["test_mode"]) else "0",
        },
    )
    payment_status = str(status_result.get("status") or "").strip().upper()
    if payment_status != "PAID":
        return {
            "ok": False,
            "reason": f"status_{payment_status or 'unknown'}",
            "trans_id": trans_id,
            "provider_payload": status_result,
            "period_start": period_start,
            "period_end": period_end,
        }

    paid_price = _safe_int(status_result.get("price"))
    if paid_price is not None and paid_price != price:
        return {
            "ok": False,
            "reason": "price_mismatch",
            "trans_id": trans_id,
            "provider_payload": status_result,
            "period_start": period_start,
            "period_end": period_end,
        }

    return {
        "ok": True,
        "trans_id": trans_id,
        "paid_price": paid_price if paid_price is not None else price,
        "provider_payload": status_result,
        "period_start": period_start,
        "period_end": period_end,
        "parent_init_recurring_id": init_recurring_id,
        "parent_provider_transaction_id": subscription.provider_init_transaction_id or subscription.last_trans_id,
    }


def process_license_subscription_jobs(db: Session) -> Dict[str, int]:
    """
    Background zpracování obnov, grace režimu a upozornění.
    """
    summary = {
        "renewal_success": 0,
        "renewal_failed": 0,
        "downgraded_free": 0,
        "notified": 0,
        "cancel_finalized": 0,
        "errors": 0,
    }

    if not _ensure_subscription_schema(db, strict=False):
        summary["errors"] += 1
        return summary

    cfg = _load_comgate_config()
    runtime_cfg = _load_subscription_runtime_config()
    now = _utcnow()

    subscriptions = (
        db.query(LicenseSubscription)
        .filter(LicenseSubscription.provider == "comgate")
        .order_by(LicenseSubscription.id.asc())
        .all()
    )

    for subscription in subscriptions:
        try:
            tenant_id = int(subscription.tenant_id)
            lic = db.query(License).filter(License.tenant_id == tenant_id).first()
            if lic and get_license_plan_base(str(lic.plan or "")) == "lifetime":
                continue
            billing_catalog = _billing_catalog_plan_from_subscription_storage(db, tenant_id, subscription.plan_current)
            billing_period = _normalize_billing_period_soft(subscription.billing_period, default="monthly")
            status = _normalize_subscription_status(subscription.status)

            # D-14/D-7/D-1 upozornění
            days_to_end = _days_until(subscription.current_period_end, now)
            if days_to_end is not None and days_to_end >= 0:
                for notify_day in runtime_cfg["notify_days"]:
                    if days_to_end == notify_day:
                        stamp_field = _subscription_notification_stamp_field(notify_day)
                        if stamp_field and getattr(subscription, stamp_field) is None:
                            plan_note = billing_catalog.upper()
                            payload = _send_subscription_notification(
                                db,
                                tenant_id=tenant_id,
                                email_subject=f"{APP_DISPLAY_NAME}: blíží se konec předplatného",
                                email_text=(
                                    f"Vaše předplatné ({plan_note}) končí za {notify_day} dní. "
                                    "V aplikaci můžete předplatné obnovit, změnit plán nebo zrušit automatické prodloužení."
                                ),
                                push_title="Předplatné brzy končí",
                                push_body=f"Předplatné končí za {notify_day} dní. Zkontrolujte volby v sekci Licence.",
                            )
                            if payload["email_sent"] > 0 or payload["push_sent"] > 0:
                                setattr(subscription, stamp_field, now)
                                summary["notified"] += 1

            # Finalizace cancel-at-period-end
            if status == "cancel_at_period_end" and subscription.current_period_end and subscription.current_period_end <= now:
                catalog_end = _normalize_plan_soft(subscription.pending_plan_change, default="free")
                storage_plan = map_catalog_plan_to_storage_plan(db, tenant_id, catalog_end)
                upgrade_license_plan(db, tenant_id, storage_plan)
                subscription.status = "canceled"
                subscription.auto_renew_enabled = False
                subscription.plan_current = storage_plan
                subscription.pending_plan_change = None
                subscription.next_charge_at = None
                subscription.grace_until = None
                subscription.failed_renewal_attempts = 0
                subscription.updated_at = now
                db.add(subscription)
                db.commit()
                summary["cancel_finalized"] += 1
                continue

            # Grace expirovala -> downgrade na FREE
            if status == "grace" and subscription.grace_until and subscription.grace_until <= now:
                storage_free = map_catalog_plan_to_storage_plan(db, tenant_id, "free")
                upgrade_license_plan(db, tenant_id, storage_free)
                subscription.status = "canceled"
                subscription.auto_renew_enabled = False
                subscription.plan_current = storage_free
                subscription.pending_plan_change = None
                subscription.next_charge_at = None
                subscription.failed_renewal_attempts = 0
                subscription.updated_at = now
                db.add(subscription)
                db.commit()
                if subscription.notified_grace_end_at is None:
                    payload = _send_subscription_notification(
                        db,
                        tenant_id=tenant_id,
                        email_subject=f"{APP_DISPLAY_NAME}: předplatné bylo ukončeno",
                        email_text=(
                            "Vaše předplatné nebylo úspěšně obnoveno ani v ochranné lhůtě. "
                            "Plán byl převeden na FREE. V aplikaci můžete předplatné kdykoli obnovit."
                        ),
                        push_title="Předplatné ukončeno",
                        push_body="Plán byl převeden na FREE. Předplatné můžete znovu aktivovat v sekci Licence.",
                    )
                    if payload["email_sent"] > 0 or payload["push_sent"] > 0:
                        subscription.notified_grace_end_at = now
                        db.add(subscription)
                        db.commit()
                summary["downgraded_free"] += 1
                continue

            # Obnova předplatného
            if (
                status == "active"
                and subscription.auto_renew_enabled
                and subscription.next_charge_at is not None
                and subscription.next_charge_at <= now
                and billing_catalog in {"basic", "premium", "full"}
            ):
                if not cfg["configured"]:
                    summary["renewal_failed"] += 1
                    continue

                result = _charge_subscription_recurring(
                    db=db,
                    cfg=cfg,
                    runtime_cfg=runtime_cfg,
                    subscription=subscription,
                    tenant_id=tenant_id,
                    plan=billing_catalog,
                    billing_period=billing_period,
                )
                subscription.last_recurring_attempt_at = now
                subscription.last_recurring_result = str(result.get("reason") or ("paid" if result.get("ok") else "failed"))[:255]
                reason = str(result.get("reason") or "")
                if reason in {"duplicate_period_charge", "recurring_disabled_by_config", "auto_renew_disabled", "subscription_inactive"}:
                    db.add(subscription)
                    db.commit()
                    continue
                if result.get("ok"):
                    trans_id = str(result.get("trans_id") or "").strip()
                    catalog_plan_raw = str(subscription.pending_plan_change or billing_catalog).strip().lower()
                    catalog_plan = _normalize_plan_soft(catalog_plan_raw, default=billing_catalog)
                    storage_plan = map_catalog_plan_to_storage_plan(db, tenant_id, catalog_plan)
                    upgrade_license_plan(db, tenant_id, storage_plan)
                    period_start = result.get("period_start") or subscription.current_period_end or now
                    period_end = result.get("period_end") or _add_billing_period(period_start, billing_period)

                    previous_status = _normalize_subscription_status(subscription.status)
                    subscription.status = "active"
                    subscription.plan_current = storage_plan
                    subscription.pending_plan_change = None
                    subscription.current_period_start = period_start
                    subscription.current_period_end = period_end
                    subscription.next_charge_at = period_end
                    subscription.last_payment_at = now
                    subscription.last_trans_id = trans_id
                    subscription.failed_renewal_attempts = 0
                    subscription.grace_until = None
                    subscription.recurring_ready = True
                    subscription.recurring_block_reason = None
                    subscription.notified_renewal_failed_at = None
                    subscription.notified_period_d14_at = None
                    subscription.notified_period_d7_at = None
                    subscription.notified_period_d1_at = None
                    subscription.updated_at = now
                    tx = _record_payment_transaction(
                        db,
                        subscription_id=subscription.id,
                        tenant_id=tenant_id,
                        provider="comgate",
                        trans_id=trans_id,
                        ref_id=str((result.get("provider_payload") or {}).get("refId") or ""),
                        payment_type="recurring",
                        parent_provider_transaction_id=str(result.get("parent_provider_transaction_id") or "") or None,
                        parent_init_recurring_id=str(result.get("parent_init_recurring_id") or "") or None,
                        plan=storage_plan,
                        billing_period=billing_period,
                        period_start=period_start,
                        period_end=period_end,
                        amount_halers=_safe_int(result.get("paid_price")),
                        currency=str(cfg["currency"]),
                        event_type="renewal_paid",
                        provider_status="PAID",
                        payload=result.get("provider_payload"),
                    )
                    _record_payment_event(
                        db,
                        payment_id=tx.id,
                        provider="comgate",
                        event_type="recurring_status_paid",
                        provider_transaction_id=trans_id,
                        raw_payload=result.get("provider_payload"),
                        processing_status="processed",
                    )
                    _write_license_audit(
                        db,
                        tenant_id=tenant_id,
                        subscription_id=subscription.id,
                        action="recurring_payment_paid",
                        old_status=previous_status,
                        new_status="active",
                        reason="recurring_charge_paid",
                        actor_type="system",
                    )
                    db.add(subscription)
                    db.commit()
                    summary["renewal_success"] += 1
                    continue

                # failure -> grace mode
                previous_status = _normalize_subscription_status(subscription.status)
                subscription.status = "grace"
                subscription.failed_renewal_attempts = int(subscription.failed_renewal_attempts or 0) + 1
                if subscription.grace_until is None or subscription.grace_until < now:
                    subscription.grace_until = now + timedelta(days=int(runtime_cfg["grace_days"]))
                if reason == "missing_init_recurring_id":
                    subscription.recurring_ready = False
                    subscription.recurring_block_reason = "missing_init_recurring_id"
                subscription.updated_at = now
                tx = _record_payment_transaction(
                    db,
                    subscription_id=subscription.id,
                    tenant_id=tenant_id,
                    provider="comgate",
                    trans_id=str(result.get("trans_id") or "") or None,
                    ref_id=None,
                    payment_type="recurring",
                    parent_provider_transaction_id=str(subscription.provider_init_transaction_id or subscription.last_trans_id or "") or None,
                    parent_init_recurring_id=str(subscription.init_recurring_id or "") or None,
                    plan=billing_catalog,
                    billing_period=billing_period,
                    period_start=result.get("period_start"),
                    period_end=result.get("period_end"),
                    amount_halers=_price_for_plan(cfg, billing_catalog, billing_period),
                    currency=str(cfg["currency"]),
                    event_type="renewal_failed",
                    provider_status=reason or "FAILED",
                    payload=result.get("provider_payload") if isinstance(result.get("provider_payload"), dict) else {"reason": reason},
                )
                _record_payment_event(
                    db,
                    payment_id=tx.id,
                    provider="comgate",
                    event_type="recurring_status_failed",
                    provider_transaction_id=str(result.get("trans_id") or "") or None,
                    raw_payload=result.get("provider_payload") if isinstance(result.get("provider_payload"), dict) else {"reason": reason},
                    processing_status="processed",
                    error_message=reason or "FAILED",
                )
                _write_license_audit(
                    db,
                    tenant_id=tenant_id,
                    subscription_id=subscription.id,
                    action="recurring_payment_failed",
                    old_status=previous_status,
                    new_status="grace",
                    reason=reason or "FAILED",
                    actor_type="system",
                )
                if subscription.notified_renewal_failed_at is None:
                    payload = _send_subscription_notification(
                        db,
                        tenant_id=tenant_id,
                        email_subject=f"{APP_DISPLAY_NAME}: obnova předplatného se nepovedla",
                        email_text=(
                            "Nepodařilo se provést automatickou obnovu předplatného. "
                            f"Běží ochranná lhůta {runtime_cfg['grace_days']} dní, během které můžete platbu obnovit v sekci Licence."
                        ),
                        push_title="Obnova předplatného selhala",
                        push_body=(
                            f"Automatická obnova se nepovedla. Máte {runtime_cfg['grace_days']} dní "
                            "na obnovu předplatného v sekci Licence."
                        ),
                    )
                    if payload["email_sent"] > 0 or payload["push_sent"] > 0:
                        subscription.notified_renewal_failed_at = now
                        summary["notified"] += 1
                db.add(subscription)
                db.commit()
                summary["renewal_failed"] += 1
        except Exception as exc:
            logger.exception("[LICENSE SUBSCRIPTION] Worker item failed (sub_id=%s): %s", subscription.id, exc)
            summary["errors"] += 1
            db.rollback()

    return summary


@router.get("/status", response_model=LicenseStatusResponse)
def get_license_status_endpoint(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Vrací status licence pro aktuálního uživatele.
    
    Returns:
        LicenseStatusResponse s informacemi o licenci
    """
    tenant_id = getattr(current_user, 'tenant_id', None)
    if not tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Uživatel nemá přiřazený tenant"
        )
    
    _ensure_subscription_schema(db)
    status = get_license_status(db, tenant_id, current_user.email)
    return LicenseStatusResponse(**_finalize_license_http_payload(db, tenant_id=int(tenant_id), status=status))


@router.post("/upgrade", response_model=LicenseStatusResponse)
def upgrade_license_endpoint(
    payload: LicenseUpgradeRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Uživatel mění licenci pro svůj tenant (tenant_id z JWT).
    """
    target_tenant_id = getattr(current_user, 'tenant_id', None)
    if not target_tenant_id:
        raise HTTPException(status_code=400, detail="Tenant není k dispozici.")
    
    # Povolit pouze administrátory (role admin nebo admin tenant z ENV)
    is_admin_role = getattr(current_user, "role", "") == "admin"
    is_admin_tenant = ADMIN_TENANT_ID is not None and target_tenant_id == ADMIN_TENANT_ID
    if not (is_admin_role or is_admin_tenant):
        raise HTTPException(
            status_code=403,
            detail="Pouze administrátor může měnit licenční plán."
        )
    
    status = upgrade_license_plan(db, target_tenant_id, payload.plan)
    write_global_audit_log(
        db,
        entity_type="license",
        entity_id=int(target_tenant_id),
        action="license_upgrade",
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(target_tenant_id),
        metadata={"plan": payload.plan},
    )
    db.commit()
    return LicenseStatusResponse(**_finalize_license_http_payload(db, tenant_id=int(target_tenant_id), status=status))


@router.post("/subscription/cancel", response_model=LicenseStatusResponse)
def cancel_subscription_endpoint(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant není k dispozici.")

    _ensure_subscription_schema(db)
    subscription = _get_subscription(db, tenant_id)
    if not subscription:
        raise HTTPException(status_code=409, detail="Pro tento účet zatím není aktivní předplatné.")

    current_catalog = _billing_catalog_plan_from_subscription_storage(db, int(tenant_id), subscription.plan_current)
    if current_catalog == "free":
        raise HTTPException(status_code=400, detail="FREE plán nemá aktivní předplatné pro zrušení.")

    if _normalize_subscription_status(subscription.status) == "canceled":
        raise HTTPException(status_code=400, detail="Předplatné je již ukončeno.")

    previous_status = _normalize_subscription_status(subscription.status)
    subscription.auto_renew_enabled = False
    subscription.status = "cancel_at_period_end"
    subscription.cancel_requested_at = _utcnow()
    subscription.next_charge_at = None
    subscription.pending_plan_change = "free"
    subscription.updated_at = _utcnow()
    db.add(subscription)
    _write_license_audit(
        db,
        tenant_id=int(tenant_id),
        subscription_id=subscription.id,
        action="auto_renew_disabled",
        old_status=previous_status,
        new_status="cancel_at_period_end",
        reason="user_requested_cancel",
        actor_type="user",
        user_id=getattr(current_user, "id", None),
    )
    db.commit()

    status = get_license_status(db, tenant_id, current_user.email)
    return LicenseStatusResponse(**_finalize_license_http_payload(db, tenant_id=int(tenant_id), status=status))


@router.post("/subscription/resume", response_model=LicenseStatusResponse)
def resume_subscription_endpoint(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant není k dispozici.")

    _ensure_subscription_schema(db)
    subscription = _get_subscription(db, tenant_id)
    if not subscription:
        raise HTTPException(status_code=409, detail="Pro tento účet zatím není aktivní předplatné.")

    current_catalog = _billing_catalog_plan_from_subscription_storage(db, int(tenant_id), subscription.plan_current)
    if current_catalog == "free":
        raise HTTPException(status_code=400, detail="FREE plán nemá předplatné k obnovení.")

    if not str(subscription.init_recurring_id or "").strip():
        raise HTTPException(status_code=409, detail="Předplatné nelze obnovit bez recurring tokenu. Proveďte novou platbu.")

    previous_status = _normalize_subscription_status(subscription.status)
    subscription.auto_renew_enabled = True
    subscription.status = "active"
    subscription.cancel_requested_at = None
    subscription.pending_plan_change = None
    subscription.grace_until = None
    if subscription.current_period_end:
        subscription.next_charge_at = subscription.current_period_end
    subscription.updated_at = _utcnow()
    db.add(subscription)
    _write_license_audit(
        db,
        tenant_id=int(tenant_id),
        subscription_id=subscription.id,
        action="auto_renew_enabled",
        old_status=previous_status,
        new_status="active",
        reason="user_requested_resume",
        actor_type="user",
        user_id=getattr(current_user, "id", None),
    )
    db.commit()

    status = get_license_status(db, tenant_id, current_user.email)
    return LicenseStatusResponse(**_finalize_license_http_payload(db, tenant_id=int(tenant_id), status=status))


@router.post("/subscription/change-plan", response_model=LicenseStatusResponse)
def change_subscription_plan_endpoint(
    payload: SubscriptionChangePlanRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant není k dispozici.")

    _ensure_subscription_schema(db)
    workspace = pairing_role_for_tenant_license(db, int(tenant_id))
    target_plan = _normalize_plan(payload.plan)

    if workspace == "service":
        if target_plan not in {"free", "full"}:
            raise HTTPException(
                status_code=400,
                detail="Servisní předplatné lze měnit jen na FULL nebo ukončit přechodem na základní verzi (FREE).",
            )
    elif target_plan == "full":
        raise HTTPException(status_code=400, detail="Plán FULL je určený jen pro servisní účty.")

    subscription = _get_subscription(db, tenant_id)
    if not subscription:
        raise HTTPException(status_code=409, detail="Pro tento účet zatím není aktivní předplatné.")

    current_catalog = _billing_catalog_plan_from_subscription_storage(db, int(tenant_id), subscription.plan_current)
    if current_catalog == "free":
        raise HTTPException(status_code=409, detail="Plán FREE nemá předplatné. Nejprve aktivujte placený plán.")

    if target_plan == current_catalog:
        status = get_license_status(db, tenant_id, current_user.email)
        return LicenseStatusResponse(**_finalize_license_http_payload(db, tenant_id=int(tenant_id), status=status))

    if target_plan == "free":
        subscription.pending_plan_change = "free"
        subscription.auto_renew_enabled = False
        subscription.status = "cancel_at_period_end"
        subscription.cancel_requested_at = _utcnow()
        subscription.next_charge_at = None
    else:
        subscription.pending_plan_change = target_plan
        if _normalize_subscription_status(subscription.status) == "cancel_at_period_end":
            subscription.status = "active"
            subscription.auto_renew_enabled = True
            subscription.cancel_requested_at = None
        if subscription.current_period_end:
            subscription.next_charge_at = subscription.current_period_end

    subscription.updated_at = _utcnow()
    db.add(subscription)
    db.commit()

    status = get_license_status(db, tenant_id, current_user.email)
    return LicenseStatusResponse(**_finalize_license_http_payload(db, tenant_id=int(tenant_id), status=status))


@router.get("/comgate/config", response_model=ComgateConfigResponse)
def get_comgate_config(
    current_user: Customer = Depends(get_current_user),
):
    """
    Vrací runtime konfiguraci Comgate integrace pro frontend.
    """
    _ = current_user  # endpoint je dostupný jen pro přihlášené
    cfg = _load_comgate_config()
    return ComgateConfigResponse(
        provider="comgate",
        enabled=bool(cfg["enabled"] and cfg["configured"]),
        configured=bool(cfg["configured"]),
        test_mode=bool(cfg["test_mode"]),
        currency=str(cfg["currency"]),
        method=str(cfg.get("subscription_method") or cfg["method"]),
        plans={
            "basic": {
                "monthly": int(cfg["plans"]["basic"]["monthly"]) if cfg["plans"]["basic"]["monthly"] else None,
                "yearly": int(cfg["plans"]["basic"]["yearly"]) if cfg["plans"]["basic"]["yearly"] else None,
            },
            "premium": {
                "monthly": int(cfg["plans"]["premium"]["monthly"]) if cfg["plans"]["premium"]["monthly"] else None,
                "yearly": int(cfg["plans"]["premium"]["yearly"]) if cfg["plans"]["premium"]["yearly"] else None,
            },
            "full": {
                "monthly": int(cfg["plans"]["full"]["monthly"]) if cfg["plans"]["full"]["monthly"] else None,
                "yearly": int(cfg["plans"]["full"]["yearly"]) if cfg["plans"]["full"]["yearly"] else None,
            },
        },
    )


@router.post("/comgate/checkout", response_model=ComgateCheckoutResponse)
def create_comgate_checkout(
    payload: ComgateCheckoutRequest,
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Vytvoří Comgate platbu pro BASIC / PREMIUM (uživatelé) nebo FULL (servis) a vrátí redirect URL.
    """
    plan = _normalize_plan(payload.plan)
    billing_period = _normalize_billing_period(payload.billing_period)
    if plan == "free":
        raise HTTPException(status_code=400, detail="FREE plán nevyžaduje platbu přes Comgate.")

    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Tenant není k dispozici.")

    _ensure_subscription_schema(db)
    cfg = _load_comgate_config()
    runtime_cfg = _load_subscription_runtime_config()
    if not cfg["configured"]:
        raise HTTPException(
            status_code=503,
            detail=(
                "Comgate není nakonfigurovaný. Nastavte COMGATE_ENABLED=1, COMGATE_MERCHANT, COMGATE_SECRET "
                "a ceny v haléřích: COMGATE_PRICE_BASIC_HALERS, COMGATE_PRICE_PREMIUM_HALERS, COMGATE_PRICE_FULL_HALERS "
                "(servis FULL), volitelně roční varianty *_YEARLY_HALERS."
            ),
        )

    if tenant_id > _COMGATE_REF_MAX_TENANT_ID:
        raise HTTPException(status_code=400, detail="Tenant ID je mimo podporovaný rozsah pro Comgate refId.")

    tenant_id_int = int(tenant_id)
    workspace = pairing_role_for_tenant_license(db, tenant_id_int)
    if workspace == "service":
        if plan != "full":
            raise HTTPException(
                status_code=400,
                detail="Servisní placená licence je pouze FULL. Základní verze je zdarma — bez platby přes Comgate.",
            )
    elif plan == "full":
        raise HTTPException(status_code=400, detail="Plán FULL je určený jen pro servisní účty.")

    subscription = _get_subscription(db, tenant_id_int)
    subscription_status = _normalize_subscription_status(subscription.status) if subscription else ""
    legacy_quote: Optional[Dict[str, Any]] = None
    effective_billing_period = billing_period

    if subscription and subscription_status == "legacy_manual":
        legacy_quote = _build_legacy_checkout_quote(
            cfg=cfg,
            subscription=subscription,
            target_plan=plan,
            billing_period=billing_period,
        )
        effective_billing_period = _normalize_billing_period_soft(
            str(legacy_quote.get("billing_period") or billing_period),
            default=billing_period,
        )
        price = int(legacy_quote.get("charge_amount_halers") or 0)
        if price <= 0:
            applied_subscription = _apply_legacy_quote_without_payment(
                db,
                tenant_id=tenant_id_int,
                subscription=subscription,
                quote=legacy_quote,
            )
            return ComgateCheckoutResponse(
                provider="comgate",
                plan=plan,
                billing_period=effective_billing_period,
                trans_id=None,
                redirect_url="",
                payment_status="applied",
                requires_payment=False,
                amount_halers=0,
                credit_balance_halers=int(applied_subscription.credit_balance_halers or 0),
                message=(
                    "Změna plánu byla provedena bez platby. "
                    "Rozdíl byl započten do kreditního salda."
                ),
            )
    else:
        price = _price_for_plan(cfg, plan, billing_period)

    if price <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cena plánu {plan.upper()} ({effective_billing_period}) není nastavena.",
        )

    ref_id = _build_comgate_ref_id(tenant_id_int, plan, effective_billing_period)
    full_name = str(getattr(current_user, "name", "") or "").strip() or str(current_user.email).strip()
    phone_raw = str(getattr(current_user, "phone", "") or "").strip()
    phone = phone_raw.replace(" ", "")

    create_payload: Dict[str, str] = {
        "merchant": str(cfg["merchant"]),
        "secret": str(cfg["secret"]),
        # Backend (HTTP POST) režim dle Comgate API.
        "prepareOnly": "true",
        "price": str(price),
        "curr": str(cfg["currency"]),
        "label": f"{APP_DISPLAY_NAME} {plan.upper()} {'MĚSÍČNĚ' if effective_billing_period == 'monthly' else 'ROČNĚ'}",
        "refId": ref_id,
        "method": str(cfg.get("subscription_method") or "CARD"),
        "country": str(cfg["country"]),
        "lang": str(cfg["lang"]),
        "email": str(current_user.email),
        "fullName": full_name,
        "test": "1" if bool(cfg["test_mode"]) else "0",
        "url_paid": _build_frontend_return_url(plan, "paid", effective_billing_period),
        "url_cancelled": _build_frontend_return_url(plan, "cancelled", effective_billing_period),
        "url_pending": _build_frontend_return_url(plan, "pending", effective_billing_period),
        "url_result": f"{_request_backend_public_url(request)}/api/v1/license/comgate/result",
    }
    if bool(runtime_cfg.get("recurring_enabled", True)):
        create_payload["initRecurring"] = "true"
    if phone:
        create_payload["phone"] = phone

    create_result = _post_comgate(str(cfg["create_url"]), create_payload)
    if str(create_result.get("code", "")) != "0":
        error_code = str(create_result.get("code") or "").strip()
        message = create_result.get("message") or "Neznámá chyba vytvoření platby"
        can_try_test_fallback = bool(
            cfg.get("test_mode")
            and cfg.get("test_one_time_fallback")
            and _is_comgate_recurring_not_enabled_message(message)
        )
        can_try_live_card_fallback = _is_comgate_card_method_not_available(error_code, message)
        can_try_non_recurring_fallback = bool(can_try_test_fallback or can_try_live_card_fallback)
        if can_try_non_recurring_fallback:
            fallback_payload = dict(create_payload)
            if can_try_test_fallback:
                fallback_payload.pop("initRecurring", None)
            fallback_method = str(cfg.get("method") or "").strip().upper() or "ALL"
            if fallback_method == str(create_payload.get("method") or "").strip().upper():
                fallback_method = "ALL"
            fallback_payload["method"] = fallback_method
            logger.warning(
                "[COMGATE] create fallback: code=%s message=%s method=%s fallback_method=%s keep_init_recurring=%s tenant=%s plan=%s period=%s",
                error_code,
                message,
                create_payload.get("method"),
                fallback_method,
                "yes" if "initRecurring" in fallback_payload else "no",
                tenant_id_int,
                plan,
                effective_billing_period,
            )
            create_result = _post_comgate(str(cfg["create_url"]), fallback_payload)
            create_result["_non_recurring_fallback"] = "1"
            if str(create_result.get("code", "")) != "0":
                fallback_message = create_result.get("message") or "Neznámá chyba vytvoření test fallback platby"
                raise HTTPException(
                    status_code=502,
                    detail=f"Comgate odmítl fallback platbu: {fallback_message} (původně: {message})",
                )
        else:
            raise HTTPException(status_code=502, detail=f"Comgate odmítl vytvoření platby: {message}")

    trans_id = str(create_result.get("transId") or "").strip()
    redirect_url = str(create_result.get("redirect") or "").strip()
    if not trans_id or not redirect_url:
        raise HTTPException(status_code=502, detail="Comgate nevrátil transId nebo redirect URL.")

    fallback_non_recurring = str(
        create_result.get("_non_recurring_fallback")
        or create_result.get("_test_fallback_non_recurring")
        or ""
    ) == "1"
    tx_payload = dict(create_result)
    if legacy_quote:
        tx_payload["legacy_quote"] = legacy_quote

    tx = _record_payment_transaction(
        db=db,
        subscription_id=subscription.id if subscription else None,
        tenant_id=tenant_id_int,
        provider="comgate",
        trans_id=trans_id,
        ref_id=ref_id,
        payment_type="initial",
        plan=plan,
        billing_period=effective_billing_period,
        amount_halers=price,
        currency=str(cfg["currency"]),
        event_type=(
            "checkout_created_legacy_quote_fallback"
            if fallback_non_recurring and legacy_quote
            else "checkout_created_fallback"
            if fallback_non_recurring
            else "checkout_created_legacy_quote"
            if legacy_quote
            else "checkout_created"
        ),
        provider_status="PENDING_FALLBACK" if fallback_non_recurring else "PENDING",
        payload=tx_payload,
    )
    _record_payment_event(
        db,
        payment_id=tx.id,
        provider="comgate",
        event_type="checkout_created",
        provider_transaction_id=trans_id,
        raw_payload=tx_payload,
        processing_status="processed",
    )
    _write_license_audit(
        db,
        tenant_id=tenant_id_int,
        subscription_id=subscription.id if subscription else None,
        action="checkout_created",
        old_status=_normalize_subscription_status(subscription.status) if subscription else None,
        new_status=_normalize_subscription_status(subscription.status) if subscription else None,
        reason="comgate_checkout_created",
        actor_type="user",
        user_id=getattr(current_user, "id", None),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()

    return ComgateCheckoutResponse(
        provider="comgate",
        plan=plan,
        billing_period=effective_billing_period,
        trans_id=trans_id,
        redirect_url=redirect_url,
        payment_status="pending",
        requires_payment=True,
        amount_halers=price,
        credit_balance_halers=int(subscription.credit_balance_halers or 0) if subscription else 0,
        message=(
            "Částka byla přepočtena podle zbývajícího období a kreditního salda."
            if legacy_quote
            else None
        ),
    )


@router.api_route("/comgate/result", methods=["GET", "POST"])
async def comgate_result(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Server callback od Comgate.
    Nevěříme příchozím datům naslepo, ale ověřujeme je přes /status volání.
    """
    if not _ensure_subscription_schema(db, strict=False):
        return PlainTextResponse("SUBSCRIPTION_SCHEMA_MISSING", status_code=503)
    cfg = _load_comgate_config()
    if not cfg["configured"]:
        return PlainTextResponse("COMGATE_NOT_CONFIGURED", status_code=503)

    payload: Dict[str, str] = {key: value for key, value in request.query_params.items()}
    if request.method.upper() == "POST":
        # Čteme raw body bez request.form(), aby callback nepadal na chybějícím
        # python-multipart při x-www-form-urlencoded.
        body = (await request.body()).decode("utf-8", errors="ignore")
        for key, value in _parse_comgate_response_text(body).items():
            payload.setdefault(key, value)

    trans_id = str(payload.get("transId") or payload.get("transid") or "").strip()
    if not trans_id:
        return PlainTextResponse("MISSING_TRANS_ID", status_code=400)

    status_result = _post_comgate(
        str(cfg["status_url"]),
        {
            "merchant": str(cfg["merchant"]),
            "secret": str(cfg["secret"]),
            "transId": trans_id,
            "test": "1" if bool(cfg["test_mode"]) else "0",
        },
    )
    if str(status_result.get("code", "")) != "0":
        logger.warning("[COMGATE] Status check failed for transId=%s payload=%s", trans_id, status_result)
        _record_payment_event(
            db,
            payment_id=None,
            provider="comgate",
            event_type="callback_status_unconfirmed",
            provider_transaction_id=trans_id,
            raw_payload=status_result,
            processing_status="ignored",
            error_message="status_not_confirmed",
        )
        db.commit()
        return PlainTextResponse("STATUS_NOT_CONFIRMED", status_code=200)

    payment_status = str(status_result.get("status") or "").strip().upper()
    existing_checkout_tx = (
        db.query(LicensePaymentTransaction)
        .filter(LicensePaymentTransaction.trans_id == trans_id)
        .first()
    )
    if _is_trans_already_paid(db, trans_id):
        logger.info("[COMGATE] Duplicate paid callback ignored transId=%s", trans_id)
        _record_payment_event(
            db,
            payment_id=existing_checkout_tx.id if existing_checkout_tx else None,
            provider="comgate",
            event_type="callback_duplicate_ignored",
            provider_transaction_id=trans_id,
            raw_payload=status_result,
            processing_status="ignored_duplicate",
        )
        db.commit()
        return PlainTextResponse("OK_DUPLICATE", status_code=200)

    if payment_status != "PAID":
        _record_payment_event(
            db,
            payment_id=existing_checkout_tx.id if existing_checkout_tx else None,
            provider="comgate",
            event_type=f"callback_status_{payment_status.lower() or 'unknown'}",
            provider_transaction_id=trans_id,
            raw_payload=status_result,
            processing_status="ignored",
        )
        if existing_checkout_tx:
            existing_checkout_tx.provider_status = payment_status
            db.add(existing_checkout_tx)
        db.commit()
        return PlainTextResponse("IGNORED", status_code=200)

    resolved_plan = _resolve_plan_from_status_payload(status_result)
    if not resolved_plan:
        logger.warning("[COMGATE] Unable to resolve plan from status payload for transId=%s", trans_id)
        return PlainTextResponse("PLAN_NOT_FOUND", status_code=200)

    resolved_billing_period = _resolve_billing_period_from_status_payload(status_result)
    parsed_ref = _parse_comgate_ref_id(str(status_result.get("refId") or payload.get("refId") or ""))
    if not parsed_ref:
        logger.warning("[COMGATE] Invalid refId for transId=%s", trans_id)
        return PlainTextResponse("REFID_INVALID", status_code=200)
    tenant_id, plan_from_ref, period_from_ref = parsed_ref
    if plan_from_ref != resolved_plan:
        logger.warning(
            "[COMGATE] Plan mismatch for transId=%s ref=%s resolved=%s",
            trans_id,
            plan_from_ref,
            resolved_plan,
        )
        return PlainTextResponse("PLAN_MISMATCH", status_code=200)
    if period_from_ref != resolved_billing_period:
        logger.warning(
            "[COMGATE] Period mismatch for transId=%s ref=%s resolved=%s",
            trans_id,
            period_from_ref,
            resolved_billing_period,
        )
        return PlainTextResponse("PERIOD_MISMATCH", status_code=200)

    configured_price = _price_for_plan(cfg, resolved_plan, resolved_billing_period)
    tx_expected_price = (
        int(existing_checkout_tx.amount_halers)
        if existing_checkout_tx and existing_checkout_tx.amount_halers is not None
        else None
    )
    expected_price = tx_expected_price if tx_expected_price is not None else configured_price
    paid_price = _safe_int(status_result.get("price"))
    if expected_price <= 0:
        logger.warning(
            "[COMGATE] Expected price is missing for plan=%s period=%s tx_amount=%s",
            resolved_plan,
            resolved_billing_period,
            tx_expected_price,
        )
        return PlainTextResponse("PRICE_NOT_CONFIGURED", status_code=200)
    if paid_price is None or paid_price != expected_price:
        logger.warning(
            "[COMGATE] Price mismatch transId=%s expected=%s paid=%s",
            trans_id,
            expected_price,
            paid_price,
        )
        return PlainTextResponse("PRICE_MISMATCH", status_code=200)

    ref_id_from_status = str(status_result.get("refId") or payload.get("refId") or "")
    if existing_checkout_tx:
        if existing_checkout_tx.ref_id and existing_checkout_tx.ref_id != ref_id_from_status:
            logger.warning(
                "[COMGATE] refId mismatch transId=%s tx_ref=%s status_ref=%s",
                trans_id,
                existing_checkout_tx.ref_id,
                ref_id_from_status,
            )
            return PlainTextResponse("REFID_MISMATCH", status_code=200)
        if existing_checkout_tx.plan and existing_checkout_tx.plan != resolved_plan:
            logger.warning(
                "[COMGATE] plan mismatch transId=%s tx_plan=%s status_plan=%s",
                trans_id,
                existing_checkout_tx.plan,
                resolved_plan,
            )
            return PlainTextResponse("PLAN_TX_MISMATCH", status_code=200)
        if existing_checkout_tx.billing_period and existing_checkout_tx.billing_period != resolved_billing_period:
            logger.warning(
                "[COMGATE] period mismatch transId=%s tx_period=%s status_period=%s",
                trans_id,
                existing_checkout_tx.billing_period,
                resolved_billing_period,
            )
            return PlainTextResponse("PERIOD_TX_MISMATCH", status_code=200)
        if existing_checkout_tx.amount_halers and int(existing_checkout_tx.amount_halers) != expected_price:
            logger.warning(
                "[COMGATE] checkout amount mismatch transId=%s tx_amount=%s expected=%s",
                trans_id,
                existing_checkout_tx.amount_halers,
                expected_price,
            )
            return PlainTextResponse("PRICE_TX_MISMATCH", status_code=200)

    storage_plan = map_catalog_plan_to_storage_plan(db, tenant_id, resolved_plan)

    legacy_quote = _legacy_quote_payload_from_checkout_tx(existing_checkout_tx)
    fallback_non_recurring_checkout = _checkout_is_non_recurring_fallback(existing_checkout_tx)
    payment_type = str(getattr(existing_checkout_tx, "payment_type", "") or "").strip().lower() or "initial"

    try:
        init_recurring_id = extract_init_recurring_id(status_result, payload, existing_checkout_tx)
        if legacy_quote:
            subscription = _upsert_subscription(db, tenant_id)
            subscription = _apply_legacy_quote_after_paid_callback(
                db,
                tenant_id=tenant_id,
                subscription=subscription,
                quote=legacy_quote,
                trans_id=trans_id,
                paid_amount_halers=paid_price if paid_price is not None else expected_price,
            )
        elif payment_type == "recurring" and existing_checkout_tx and existing_checkout_tx.subscription_id:
            subscription = (
                db.query(LicenseSubscription)
                .filter(LicenseSubscription.id == existing_checkout_tx.subscription_id)
                .first()
            )
            if not subscription:
                logger.warning("[COMGATE] Missing subscription for recurring transId=%s", trans_id)
                _record_payment_event(
                    db,
                    payment_id=existing_checkout_tx.id,
                    provider="comgate",
                    event_type="callback_missing_subscription",
                    provider_transaction_id=trans_id,
                    raw_payload=status_result,
                    processing_status="error",
                    error_message="missing_subscription",
                )
                db.commit()
                return PlainTextResponse("MISSING_SUBSCRIPTION", status_code=200)
            subscription = _apply_recurring_payment_success(
                db,
                subscription=subscription,
                plan=storage_plan,
                billing_period=resolved_billing_period,
                trans_id=trans_id,
                period_start=existing_checkout_tx.period_start,
                period_end=existing_checkout_tx.period_end,
            )
        elif init_recurring_id:
            subscription = _activate_subscription_from_paid_payment(
                db,
                tenant_id=tenant_id,
                plan=storage_plan,
                billing_period=resolved_billing_period,
                trans_id=trans_id,
                init_recurring_id=init_recurring_id,
            )
        elif bool((cfg.get("test_mode") and cfg.get("test_one_time_fallback")) or fallback_non_recurring_checkout):
            # Fallback jednorázová platba bez recurring tokenu (test/live).
            subscription = _activate_legacy_manual_subscription_from_paid_payment(
                db,
                tenant_id=tenant_id,
                plan=storage_plan,
                billing_period=resolved_billing_period,
                trans_id=trans_id,
            )
        else:
            logger.warning("[COMGATE] Missing initRecurringId for transId=%s", trans_id)
            subscription = _activate_subscription_from_paid_payment(
                db,
                tenant_id=tenant_id,
                plan=storage_plan,
                billing_period=resolved_billing_period,
                trans_id=trans_id,
                init_recurring_id=None,
            )
        paid_tx_payload: Dict[str, object] = dict(status_result)
        if legacy_quote:
            paid_tx_payload["legacy_quote"] = legacy_quote
        if init_recurring_id:
            paid_tx_payload["initRecurringId"] = init_recurring_id
        tx = _record_payment_transaction(
            db,
            subscription_id=subscription.id if subscription else None,
            tenant_id=tenant_id,
            provider="comgate",
            trans_id=trans_id,
            ref_id=ref_id_from_status,
            payment_type=payment_type,
            parent_provider_transaction_id=(
                str(existing_checkout_tx.parent_provider_transaction_id or "") or None
                if existing_checkout_tx else None
            ),
            parent_init_recurring_id=(
                str(existing_checkout_tx.parent_init_recurring_id or init_recurring_id or "") or None
                if existing_checkout_tx else (str(init_recurring_id or "") or None)
            ),
            plan=storage_plan,
            billing_period=resolved_billing_period,
            period_start=getattr(existing_checkout_tx, "period_start", None),
            period_end=getattr(existing_checkout_tx, "period_end", None),
            amount_halers=paid_price if paid_price is not None else expected_price,
            currency=str(status_result.get("curr") or cfg["currency"]),
            event_type="renewal_paid" if payment_type == "recurring" else "paid_confirmed",
            provider_status=payment_status,
            payload=paid_tx_payload,
        )
        _record_payment_event(
            db,
            payment_id=tx.id,
            provider="comgate",
            event_type="callback_paid_confirmed",
            provider_transaction_id=trans_id,
            raw_payload=paid_tx_payload,
            processing_status="processed",
        )
        if subscription.notified_first_payment_at is None:
            is_legacy_manual = _normalize_subscription_status(subscription.status) == "legacy_manual"
            is_legacy_quote_payment = bool(legacy_quote)
            is_recurring_ready = bool(subscription.auto_renew_enabled and getattr(subscription, "recurring_ready", False))
            is_non_recurring_fallback_payment = bool(
                is_legacy_manual
                and not is_legacy_quote_payment
                and not init_recurring_id
                and fallback_non_recurring_checkout
            )
            note = _send_subscription_notification(
                db,
                tenant_id=tenant_id,
                email_subject=f"{APP_DISPLAY_NAME}: předplatné aktivní",
                email_text=(
                    (
                        (
                            f"Platba byla potvrzena a plán {resolved_plan.upper()} je aktivní. "
                            "Od této chvíle je zapnuté automatické měsíční/roční prodloužení podle vybraného období. "
                            "V sekci Licence můžete kdykoli zrušit automatické prodloužení k datu konce období."
                        )
                        if is_recurring_ready
                        else (
                            f"Platba byla potvrzena a plán {resolved_plan.upper()} je aktivní. "
                            "Automatické obnovení se zatím nezapnulo, protože chybí recurring reference z Comgate. "
                            "Pro zapnutí auto-obnovy bude potřeba nová kartová platba."
                        )
                    )
                    if not is_legacy_manual
                    else (
                        (
                            f"Platba byla potvrzena a plán {resolved_plan.upper()} je aktivní. "
                            "Částka byla přepočtena podle zbývajícího období a kreditního salda. "
                            "V sekci Licence vidíte aktuální kredit/nedoplatek."
                        )
                        if is_legacy_quote_payment
                        else (
                            (
                                f"Platba byla potvrzena a plán {resolved_plan.upper()} je aktivní. "
                                "Platba proběhla v jednorázovém fallback režimu (bez recurring tokenu), "
                                "automatické prodloužení se proto zatím nezapnulo. "
                                "Po aktivaci karetních recurring plateb v Comgate se při další platbě auto-obnova zapne."
                            )
                            if is_non_recurring_fallback_payment and not bool(cfg.get("test_mode"))
                            else (
                            f"Platba byla potvrzena a plán {resolved_plan.upper()} je aktivní. "
                            "Toto je testovací jednorázová platba bez recurring tokenu, automatické prodloužení se proto nezapnulo. "
                            "Po aktivaci recurring v Comgate bude další platba už plně předplatná."
                            )
                        )
                    )
                ),
                push_title="Předplatné aktivní",
                push_body=(
                    (
                        (
                            f"Plán {resolved_plan.upper()} je aktivní. V sekci Licence můžete spravovat auto-obnovu nebo změnit plán."
                            if is_recurring_ready
                            else f"Plán {resolved_plan.upper()} je aktivní, ale auto-obnova zatím není připravená."
                        )
                    )
                    if not is_legacy_manual
                    else (
                        (
                            f"Plán {resolved_plan.upper()} je aktivní, částka byla přepočtena dle období/kreditu."
                            if is_legacy_quote_payment
                            else (
                                f"Plán {resolved_plan.upper()} je aktivní (dočasně jednorázová platba bez auto-obnovy)."
                                if is_non_recurring_fallback_payment and not bool(cfg.get("test_mode"))
                                else f"Plán {resolved_plan.upper()} je aktivní (test jednorázové platby)."
                            )
                        )
                    )
                ),
            )
            if note["email_sent"] > 0 or note["push_sent"] > 0:
                subscription.notified_first_payment_at = _utcnow()
                db.add(subscription)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("[COMGATE] Failed to upgrade tenant=%s plan=%s transId=%s", tenant_id, resolved_plan, trans_id)
        return PlainTextResponse(f"UPGRADE_FAILED:{exc}", status_code=200)

    logger.info("[COMGATE] License upgraded tenant=%s plan=%s transId=%s", tenant_id, resolved_plan, trans_id)
    return PlainTextResponse("OK", status_code=200)
