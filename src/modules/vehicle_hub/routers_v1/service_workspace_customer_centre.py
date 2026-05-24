"""
SOURCE OF TRUTH pro servisní „Zákazníky“ (HTTP + logika): vyhledávání, vazba, založení účtu, onboarding.

Zastaralý import z kořene balíčku: ``vehicle_hub.service_workspace_customer_centre`` je pouze tenký re-export
kvůli kompatibilitě testů a starým importům.
Centrální API „Zákazníci servisu“ — přesné vyhledávání, vazba, založení účtu, onboarding.
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional

import jwt

try:
    from jwt import PyJWTError as _JWTDecodeError
except ImportError:
    _JWTDecodeError = Exception
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from src.core.config import FRONTEND_BASE_URL, JWT_ALGORITHM, JWT_SECRET_KEY
from src.core.rate_limiter import rate_limiter
from src.modules.licensing.service import LicenseError, assert_service_customer_link_quota, assert_vehicle_quota

from src.core.security import hash_password
from src.modules.email_client.service import EmailService
from src.modules.email_client.templates import render_email_layout, render_panel
from src.modules.vehicle_hub.registration_security import normalize_validate_phone_e164

from ..audit_log import write_global_audit_log
from ..database import get_db
from ..models import (
    Customer,
    ServiceCustomerLink,
    ServiceRecord as ServiceRecordModel,
    UserOnboardingToken,
    Vehicle as VehicleModel,
    VehicleServiceLink,
)
from ..ownership import ensure_vehicle_owner_assignment, get_owned_vehicle_rows
from ..schema_management import assert_module_ready
from ..service_access import create_or_update_vehicle_service_link
from ..tenant_provisioning import create_dedicated_tenant
from .auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["service-workspace-customers-centre"])

_LOOKUP_JWT_TYP = "svc_cust_lookup"
_LINK_CONFIRM_JWT_TYP = "svc_link_confirm"
_SEARCH_RL_MAX = 40
_SEARCH_RL_PERIOD = 60
_CREATE_RL_MAX = 10
_CREATE_RL_PERIOD = 3600

SERVICE_VISIBLE_LINK_STATUSES = frozenset({"active", "invited", "pending_customer_confirm"})


class CustomerExactSearchRequestV1(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None


class CustomerLinkFromLookupRequestV1(BaseModel):
    lookup_id: str = Field(..., min_length=8, max_length=2048)
    consent_basis: str = Field(..., min_length=3, max_length=120)
    consent_note: str = Field(..., min_length=3, max_length=2000)
    internal_service_note: Optional[str] = Field(default=None, max_length=4000)


class AddressPayloadV1(BaseModel):
    street: Optional[str] = Field(default=None, max_length=200)
    city: Optional[str] = Field(default=None, max_length=120)
    zip: Optional[str] = Field(default=None, max_length=32)
    country: Optional[str] = Field(default=None, max_length=8)


class VehicleCreatePayloadV1(BaseModel):
    vin: Optional[str] = Field(default=None, max_length=64)
    plate: Optional[str] = Field(default=None, max_length=32)
    brand: Optional[str] = Field(default=None, max_length=64)
    model: Optional[str] = Field(default=None, max_length=120)
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    mileage: Optional[int] = Field(default=None, ge=0)


class CustomerCreateRequestV1(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=80)
    last_name: str = Field(..., min_length=1, max_length=80)
    email: EmailStr
    phone: str = Field(..., min_length=9, max_length=40)
    address: Optional[AddressPayloadV1] = None
    consent_basis: str = Field(..., min_length=3, max_length=120)
    consent_note: str = Field(..., min_length=3, max_length=2000)
    internal_service_note: Optional[str] = Field(default=None, max_length=4000)
    create_vehicle: bool = False
    vehicle: Optional[VehicleCreatePayloadV1] = None


class CustomerConfirmLinkRequestV1(BaseModel):
    confirm_token: str = Field(..., min_length=12, max_length=4096)


class ServiceCustomerOnboardingRequestV1(BaseModel):
    token: str = Field(..., min_length=12, max_length=4096)
    password: str = Field(..., min_length=8, max_length=128)


def _require_service_workspace_role(current_user: Customer) -> None:
    from src.modules.vehicle_hub.workspace_entitlements import customer_has_service_workspace_access

    if not customer_has_service_workspace_access(current_user):
        raise HTTPException(status_code=403, detail="Servisní centrum je dostupné pouze pro servisní účty.")


def _ensure_ws(db: Session) -> None:
    assert_module_ready(db, "service_workspace", detail_prefix="Servisní workspace není připraven")


def _normalize_email(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _digits_phone(value: Optional[str]) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _sync_normalized_customer(customer: Customer) -> None:
    customer.email_normalized = _normalize_email(customer.email) or None
    pe = getattr(customer, "phone_e164", None) or ""
    customer.phone_normalized = _digits_phone(pe) or _digits_phone(getattr(customer, "phone", None)) or None


def _mask_display_name(name: Optional[str]) -> Optional[str]:
    raw = str(name or "").strip()
    if not raw:
        return None
    parts = raw.split()
    if len(parts) == 1:
        return f"{parts[0][:2]}***"
    return f"{parts[0]} {parts[-1][:1]}."


def _mask_email(email: Optional[str]) -> Optional[str]:
    text = str(email or "").strip()
    if not text or "@" not in text:
        return None
    local, domain = text.split("@", 1)
    if len(local) <= 2:
        lm = local[:1] + "***"
    else:
        lm = f"{local[:2]}***"
    return f"{lm}@{domain}"


def _mask_phone_e164(phone: Optional[str]) -> Optional[str]:
    text = str(phone or "").strip()
    if not text:
        return None
    digits = _digits_phone(text)
    if len(digits) < 4:
        return "***"
    return f"+*** *** *** {digits[-3:]}"


def _mint_jwt(payload: dict, *, ttl_minutes: int) -> str:
    now = datetime.utcnow()
    body = dict(payload)
    body["iat"] = now
    body["exp"] = now + timedelta(minutes=ttl_minutes)
    return jwt.encode(body, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def _decode_jwt(token: str, expected_typ: str) -> dict:
    try:
        data = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except _JWTDecodeError as exc:
        raise HTTPException(status_code=400, detail="Neplatný nebo expirovaný token.") from exc
    if str(data.get("typ") or "") != expected_typ:
        raise HTTPException(status_code=400, detail="Neplatný typ tokenu.")
    return data


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _link_preview_status(db: Session, *, service_customer_id: int, customer_id: int) -> str:
    row = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == int(service_customer_id),
            ServiceCustomerLink.customer_id == int(customer_id),
            ServiceCustomerLink.status.in_(tuple(SERVICE_VISIBLE_LINK_STATUSES)),
        )
        .order_by(ServiceCustomerLink.updated_at.desc())
        .first()
    )
    if not row:
        return "none"
    if row.status == "active":
        return "active"
    if row.status == "pending_customer_confirm":
        return "pending_customer_confirm"
    if row.status == "invited":
        return "invited"
    return "none"


def _sanitize_email_error(exc: BaseException, *, max_len: int = 300) -> str:
    text = str(exc).strip().replace("\n", " ")
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _send_service_customer_invite_email(
    *,
    to_email: str,
    owner_name: str,
    service_name: str,
    onboarding_url: str,
) -> dict[str, Any]:
    svc = EmailService()
    if not svc.is_configured():
        logger.warning("[SERVICE_CUSTOMER] SMTP není nakonfigurováno — pozvánka neodeslána.")
        return {
            "attempted": True,
            "sent": False,
            "reason": "smtp_not_configured",
            "error": None,
        }
    intro = (
        f"servis {service_name} vám založil účet v aplikaci za účelem evidence vozidla, "
        "servisní historie a souvisejících dokumentů."
    )
    body_plain = (
        f"Dobrý den {owner_name},\n\n"
        f"{intro}\n\n"
        f"Pro první nastavení hesla použijte odkaz:\n{onboarding_url}\n\n"
        "Po nastavení hesla budete moci začít používat účet.\n\n"
        "Pokud jste o účet nežádali, odkaz nepoužívejte a kontaktujte podporu.\n"
    )
    html_body = render_email_layout(
        title="Účet ve Správě vozidel",
        subtitle="Založeno servisem",
        intro=f"Dobrý den {owner_name},",
        paragraphs=[intro, "Pro dokončení založení účtu nastavte heslo bezpečným odkazem níže."],
        panels=[
            render_panel(
                title="První přístup",
                rows=[("Servis", service_name), ("Odkaz", onboarding_url)],
                accent="#2563eb",
                tone="#eff6ff",
            )
        ],
        accent="#2563eb",
    )
    try:
        ok = svc.send_simple_email(
            to=to_email,
            subject=f"Váš účet — založení servisem ({service_name})",
            body=body_plain,
            html_body=html_body,
        )
        if ok is False:
            return {
                "attempted": True,
                "sent": False,
                "reason": "send_failed",
                "error": None,
            }
        return {"attempted": True, "sent": True, "reason": None, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SERVICE_CUSTOMER] Odeslání pozvánky selhalo: %s", exc)
        return {
            "attempted": True,
            "sent": False,
            "reason": "send_failed",
            "error": _sanitize_email_error(exc),
        }


def _send_link_confirm_email(
    *,
    to_email: str,
    owner_name: str,
    service_name: str,
    confirm_url: str,
) -> dict[str, Any]:
    svc = EmailService()
    if not svc.is_configured():
        logger.warning("[SERVICE_CUSTOMER] SMTP není nakonfigurováno — potvrzení vazby neodesláno.")
        return {
            "attempted": True,
            "sent": False,
            "reason": "smtp_not_configured",
            "error": None,
        }
    body_plain = (
        f"Dobrý den {owner_name},\n\n"
        f"servis {service_name} žádá o propojení účtu ve Správě vozidel.\n\n"
        f"Potvrďte prosím odkazem:\n{confirm_url}\n\n"
        "Pokud jste o propojení nežádali, odkaz ignorujte.\n"
    )
    html_body = render_email_layout(
        title="Žádost o propojení se servisem",
        subtitle="Potvrďte v aplikaci",
        intro=f"Dobrý den {owner_name},",
        paragraphs=[
            f"servis **{service_name}** eviduje žádost o propojení vašeho uživatelského účtu.",
            "Propojení umožní sdílení vozidel a servisní historie podle vašeho dalšího souhlasu u konkrétních vozidel.",
        ],
        panels=[
            render_panel(
                title="Potvrzení",
                rows=[("Servis", service_name), ("Odkaz", confirm_url)],
                accent="#059669",
                tone="#ecfdf5",
            )
        ],
        accent="#059669",
    )
    try:
        ok = svc.send_simple_email(
            to=to_email,
            subject=f"Potvrďte propojení se servisem — {service_name}",
            body=body_plain,
            html_body=html_body,
        )
        if ok is False:
            return {
                "attempted": True,
                "sent": False,
                "reason": "send_failed",
                "error": None,
            }
        return {"attempted": True, "sent": True, "reason": None, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SERVICE_CUSTOMER] Odeslání potvrzení vazby selhalo: %s", exc)
        return {
            "attempted": True,
            "sent": False,
            "reason": "send_failed",
            "error": _sanitize_email_error(exc),
        }


def _send_direct_customer_link_notice_email(
    *,
    to_email: str,
    owner_name: str,
    service_name: str,
) -> dict[str, Any]:
    """Informativní e-mail po přímém propojení existujícího zákazníka (bez tokenu v těle zprávy)."""
    _ = owner_name  # rezerva pro případné rozšíření oslovení; tělo je dle produktové šablony bez jména
    svc = EmailService()
    if not svc.is_configured():
        logger.warning("[SERVICE_CUSTOMER] SMTP není nakonfigurováno — informace o přímém propojení neodeslána.")
        return {
            "attempted": True,
            "sent": False,
            "reason": "smtp_not_configured",
            "error": None,
        }
    body_plain = (
        "Dobrý den,\n\n"
        f"servis {service_name} si vás přidal mezi své zákazníky v aplikaci Správa vozidel.\n\n"
        "To znamená, že vás servis může evidovat ve svém zákaznickém seznamu a případně vás požádat o přístup "
        "ke konkrétnímu vozidlu.\n\n"
        "Bez vašeho schválení servis nezíská přístup k detailu vozidla, pokud k němu ještě nemá schválenou vazbu.\n\n"
        "Pokud jste tuto akci nečekal/a, zkontrolujte svůj účet v aplikaci Správa vozidel nebo kontaktujte podporu.\n\n"
        "S pozdravem\n"
        "Správa vozidel\n"
    )
    html_body = render_email_layout(
        title="Servis vás přidal mezi zákazníky",
        subtitle="Správa vozidel",
        intro="Dobrý den,",
        paragraphs=[
            f"servis **{service_name}** si vás přidal mezi své zákazníky v aplikaci Správa vozidel.",
            "To znamená, že vás servis může evidovat ve svém zákaznickém seznamu a případně vás požádat o přístup ke konkrétnímu vozidlu.",
            "Bez vašeho schválení servis nezíská přístup k detailu vozidla, pokud k němu ještě nemá schválenou vazbu.",
            "Pokud jste tuto akci nečekali, zkontrolujte svůj účet v aplikaci nebo kontaktujte podporu.",
        ],
        panels=[
            render_panel(
                title="Servis",
                rows=[("Název", service_name)],
                accent="#2563eb",
                tone="#eff6ff",
            )
        ],
        accent="#2563eb",
    )
    try:
        ok = svc.send_simple_email(
            to=to_email,
            subject="Servis si vás přidal mezi zákazníky — Správa vozidel",
            body=body_plain,
            html_body=html_body,
        )
        if ok is False:
            return {
                "attempted": True,
                "sent": False,
                "reason": "send_failed",
                "error": None,
            }
        return {"attempted": True, "sent": True, "reason": None, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SERVICE_CUSTOMER] Odeslání informace o přímém propojení selhalo: %s", exc)
        return {
            "attempted": True,
            "sent": False,
            "reason": "send_failed",
            "error": _sanitize_email_error(exc),
        }


def _frontend_base() -> str:
    base = str(FRONTEND_BASE_URL or "").strip().rstrip("/")
    return base or "http://127.0.0.1:8000"


@router.post("/customers/search")
def customer_exact_search(
    payload: CustomerExactSearchRequestV1,
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_ws(db)

    email_n = _normalize_email(payload.email)
    phone_raw = str(payload.phone or "").strip()
    phone_e164: Optional[str] = None
    if phone_raw:
        try:
            phone_e164 = normalize_validate_phone_e164(phone_raw)
        except ValueError:
            raise HTTPException(status_code=422, detail="Neplatný formát telefonu.") from None

    if not email_n and not phone_e164:
        raise HTTPException(status_code=422, detail="Zadejte e-mail nebo telefon.")

    client_ip = (request.client.host if request.client else "") or "unknown"
    rl_key = f"svc_cust_search:{current_user.tenant_id}:{client_ip}"
    if not rate_limiter.check_rate_limit(rl_key, max_calls=_SEARCH_RL_MAX, period=_SEARCH_RL_PERIOD):
        raise HTTPException(status_code=429, detail="Příliš mnoho vyhledávání. Zkuste to později.")

    cid_email: Optional[int] = None
    cid_phone: Optional[int] = None

    if email_n:
        hit = db.query(Customer.id).filter(func.lower(Customer.email) == email_n).first()
        if hit:
            cid_email = int(hit[0])

    if phone_e164:
        digits = _digits_phone(phone_e164)
        hit = (
            db.query(Customer.id)
            .filter(or_(Customer.phone_e164 == phone_e164, Customer.phone_normalized == digits))
            .first()
        )
        if hit:
            cid_phone = int(hit[0])

    write_global_audit_log(
        db,
        entity_type="service_customer_security",
        entity_id=int(current_user.id),
        action="SERVICE_CUSTOMER_SEARCH",
        actor_user_id=int(current_user.id),
        actor_role=str(current_user.role or ""),
        tenant_id=int(current_user.tenant_id),
        ip=str(client_ip)[:128],
        user_agent=(request.headers.get("user-agent") or "")[:2000],
        metadata={
            "has_email_query": bool(email_n),
            "has_phone_query": bool(phone_e164),
            "match_email_user_id": cid_email,
            "match_phone_user_id": cid_phone,
        },
    )
    db.commit()

    if cid_email and cid_phone and cid_email != cid_phone:
        write_global_audit_log(
            db,
            entity_type="service_customer_security",
            entity_id=int(current_user.id),
            action="SERVICE_CUSTOMER_DUPLICATE_BLOCKED",
            actor_user_id=int(current_user.id),
            tenant_id=int(current_user.tenant_id),
            metadata={"cid_email": cid_email, "cid_phone": cid_phone},
        )
        db.commit()
        raise HTTPException(
            status_code=409,
            detail="E-mail a telefon ukazují na různé účty. Ověřte údaje u zákazníka.",
        )

    target_id = cid_email or cid_phone
    if not target_id:
        return {"found": False, "can_create_new_customer": True}

    cust = db.query(Customer).filter(Customer.id == int(target_id)).first()
    if not cust:
        return {"found": False, "can_create_new_customer": True}

    if str(cust.role or "").lower() in {"service", "admin", "developer_admin"}:
        raise HTTPException(status_code=404, detail="Pro tento kontakt nelze vytvořit zákaznickou vazbu.")

    lookup_id = _mint_jwt(
        {"typ": _LOOKUP_JWT_TYP, "cid": int(cust.id), "sid": int(current_user.id)},
        ttl_minutes=25,
    )

    link_st = _link_preview_status(db, service_customer_id=int(current_user.id), customer_id=int(cust.id))

    return {
        "found": True,
        "match_confidence": "exact",
        "customer_preview": {
            "lookup_id": lookup_id,
            "display_name_masked": _mask_display_name(cust.name),
            "email_masked": _mask_email(cust.email),
            "phone_masked": _mask_phone_e164(cust.phone_e164 or cust.phone),
            "account_status": str(cust.account_status or "unknown"),
            "link_status": link_st,
        },
    }


def execute_customer_link_from_lookup(
    *,
    payload: CustomerLinkFromLookupRequestV1,
    request: Request,
    current_user: Customer,
    db: Session,
) -> dict[str, Any]:
    """Logika propojení z lookup tokenu — volitelně z /customers/link-existing (workspace)."""

    _require_service_workspace_role(current_user)
    _ensure_ws(db)

    data = _decode_jwt(payload.lookup_id.strip(), _LOOKUP_JWT_TYP)
    cid = int(data["cid"])
    sid = int(data["sid"])
    if sid != int(current_user.id):
        raise HTTPException(status_code=403, detail="Vyhledávání patří jinému servisnímu účtu.")

    target = db.query(Customer).filter(Customer.id == cid).first()
    if not target:
        raise HTTPException(status_code=404, detail="Účet neexistuje.")

    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Nelze propojit účet se sebou samým.")

    existing = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == int(current_user.id),
            ServiceCustomerLink.customer_id == int(target.id),
        )
        .first()
    )
    if existing and existing.status == "active":
        msg = "Zákazník byl propojen se servisem."
        return {
            "linked": True,
            "pending_customer_confirm": False,
            "customer_link_id": int(existing.id),
            "customer_user_id": int(target.id),
            "link_status": "active",
            "email_sent": False,
            "notification": {
                "channel": "email",
                "sent": False,
                "reason": "already_active",
                "message": msg,
            },
            "message": msg,
        }

    service_name = (current_user.name or current_user.email or "Servis").strip()

    now = datetime.utcnow()
    if existing:
        row = existing
        row.status = "pending_customer_confirm"
        row.link_source = "service_found_existing"
        row.consent_basis = payload.consent_basis.strip()
        row.consent_note = payload.consent_note.strip()
        row.internal_service_note = (payload.internal_service_note or "").strip() or None
        row.created_by_service_user_id = int(current_user.id)
        row.updated_at = now
    else:
        assert_service_customer_link_quota(db, service_customer_id=int(current_user.id))
        row = ServiceCustomerLink(
            service_tenant_id=int(current_user.tenant_id),
            service_customer_id=int(current_user.id),
            customer_tenant_id=int(target.tenant_id),
            customer_id=int(target.id),
            status="pending_customer_confirm",
            note=None,
            link_source="service_found_existing",
            consent_basis=payload.consent_basis.strip(),
            consent_note=payload.consent_note.strip(),
            internal_service_note=(payload.internal_service_note or "").strip() or None,
            created_by_service_user_id=int(current_user.id),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()

    confirm_token_real = _mint_jwt(
        {
            "typ": _LINK_CONFIRM_JWT_TYP,
            "lid": int(row.id),
            "cid": int(target.id),
            "sid": int(current_user.id),
        },
        ttl_minutes=72 * 60,
    )

    confirm_url = f"{_frontend_base()}/web/index.html?service_link_confirm={confirm_token_real}"

    email_result = _send_link_confirm_email(
        to_email=str(target.email),
        owner_name=(target.name or "uživateli").strip(),
        service_name=service_name,
        confirm_url=confirm_url,
    )

    write_global_audit_log(
        db,
        entity_type="service_customer_security",
        entity_id=int(row.id),
        action="SERVICE_CUSTOMER_LINK_CREATED",
        actor_user_id=int(current_user.id),
        tenant_id=int(current_user.tenant_id),
        metadata={
            "customer_user_id": int(target.id),
            "status": "pending_customer_confirm",
            "lookup_flow": True,
        },
        ip=(request.client.host if request.client else "")[:128],
        user_agent=(request.headers.get("user-agent") or "")[:2000],
    )
    link_email_audit_action = (
        "SERVICE_CUSTOMER_LINK_CONFIRM_EMAIL_SENT" if email_result.get("sent") else "SERVICE_CUSTOMER_LINK_CONFIRM_EMAIL_FAILED"
    )
    write_global_audit_log(
        db,
        entity_type="service_customer_security",
        entity_id=int(target.id),
        action=link_email_audit_action,
        actor_user_id=int(current_user.id),
        tenant_id=int(current_user.tenant_id),
        metadata={
            "kind": "link_confirm",
            "sent": bool(email_result.get("sent")),
            "reason": email_result.get("reason"),
            "customer_user_id": int(target.id),
            "link_id": int(row.id),
        },
    )
    db.commit()

    if email_result.get("sent"):
        out_msg = "Zákazníkovi byl odeslán e-mail k potvrzení propojení."
        notif_msg = out_msg
    else:
        out_msg = "Vazba čeká na potvrzení, ale e-mail se nepodařilo odeslat."
        notif_msg = out_msg

    return {
        "linked": False,
        "pending_customer_confirm": True,
        "customer_link_id": int(row.id),
        "customer_user_id": int(target.id),
        "email_sent": bool(email_result.get("sent")),
        "notification": {
            "channel": "email",
            "sent": bool(email_result.get("sent")),
            "reason": email_result.get("reason"),
            "message": notif_msg,
        },
        "message": out_msg,
    }


@router.post("/customers/link-from-lookup")
def customer_link_from_lookup_route(
    payload: CustomerLinkFromLookupRequestV1,
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return execute_customer_link_from_lookup(
        payload=payload, request=request, current_user=current_user, db=db
    )


@router.post("/customers/create")
def customer_create_with_onboarding(
    payload: CustomerCreateRequestV1,
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_ws(db)

    client_ip = (request.client.host if request.client else "") or "unknown"
    rl_key = f"svc_cust_create:{current_user.tenant_id}:{client_ip}"
    if not rate_limiter.check_rate_limit(rl_key, max_calls=_CREATE_RL_MAX, period=_CREATE_RL_PERIOD):
        raise HTTPException(status_code=429, detail="Příliš mnoho zakládání účtů. Zkuste to později.")

    email_n = _normalize_email(str(payload.email))
    try:
        phone_e164 = normalize_validate_phone_e164(payload.phone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    dup = (
        db.query(Customer.id)
        .filter(or_(func.lower(Customer.email) == email_n, Customer.phone_e164 == phone_e164))
        .first()
    )
    if dup:
        raise HTTPException(
            status_code=409,
            detail="Účet s tímto e-mailem nebo telefonem už existuje. Použijte vyhledání a propojení.",
        )

    if payload.create_vehicle and not payload.vehicle:
        raise HTTPException(status_code=422, detail="Chybí údaje o vozidle.")

    full_name = f"{payload.first_name.strip()} {payload.last_name.strip()}".strip()

    tenant = create_dedicated_tenant(db, owner_email=email_n, owner_name=full_name)

    customer = Customer(
        tenant_id=int(tenant.id),
        email=email_n,
        password_hash=None,
        name=full_name,
        phone=str(payload.phone).strip(),
        phone_e164=phone_e164,
        role="user",
        account_status="service_invited_pending_email",
        notify_email=True,
        street=(payload.address.street if payload.address else None),
        city=(payload.address.city if payload.address else None),
        zip=(payload.address.zip if payload.address else None),
        force_password_change=True,
    )
    _sync_normalized_customer(customer)
    db.add(customer)
    db.flush()

    assert_service_customer_link_quota(db, service_customer_id=int(current_user.id))
    link = ServiceCustomerLink(
        service_tenant_id=int(current_user.tenant_id),
        service_customer_id=int(current_user.id),
        customer_tenant_id=int(customer.tenant_id),
        customer_id=int(customer.id),
        status="invited",
        link_source="service_created",
        consent_basis=payload.consent_basis.strip(),
        consent_note=payload.consent_note.strip(),
        internal_service_note=(payload.internal_service_note or "").strip() or None,
        created_by_service_user_id=int(current_user.id),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(link)
    db.flush()

    now_tok = datetime.utcnow()
    exp_tok = now_tok + timedelta(hours=72)
    raw_token = secrets.token_urlsafe(48)
    tok_hash = _hash_token(raw_token)
    existing_tok = (
        db.query(UserOnboardingToken)
        .filter(
            UserOnboardingToken.user_id == int(customer.id),
            UserOnboardingToken.token_type == "service_created_account_invite",
            UserOnboardingToken.used_at.is_(None),
            UserOnboardingToken.expires_at > now_tok,
        )
        .first()
    )
    if existing_tok:
        existing_tok.token_hash = tok_hash
        existing_tok.expires_at = exp_tok
        existing_tok.created_by_service_tenant_id = int(current_user.tenant_id)
        existing_tok.created_by_user_id = int(current_user.id)
        existing_tok.ip_created = str(client_ip)[:128]
        existing_tok.user_agent_created = (request.headers.get("user-agent") or "")[:2000]
    else:
        tok_row = UserOnboardingToken(
            user_id=int(customer.id),
            token_hash=tok_hash,
            token_type="service_created_account_invite",
            expires_at=exp_tok,
            created_by_service_tenant_id=int(current_user.tenant_id),
            created_by_user_id=int(current_user.id),
            created_at=now_tok,
            ip_created=str(client_ip)[:128],
            user_agent_created=(request.headers.get("user-agent") or "")[:2000],
        )
        db.add(tok_row)

    onboarding_url = f"{_frontend_base()}/web/index.html?service_onboarding_token={raw_token}"

    service_name = (current_user.name or current_user.email or "Servis").strip()
    smtp_configured = EmailService().is_configured()
    email_result = _send_service_customer_invite_email(
        to_email=email_n,
        owner_name=payload.first_name.strip(),
        service_name=service_name,
        onboarding_url=onboarding_url,
    )

    vehicle_id: Optional[int] = None
    if payload.create_vehicle and payload.vehicle:
        v = payload.vehicle
        stk_default = datetime.utcnow().date() + timedelta(days=365)
        nickname_parts = [p for p in [v.brand, v.model] if p]
        nickname = " ".join(nickname_parts).strip() or (v.plate or v.vin or "Vozidlo")
        try:
            assert_vehicle_quota(db, int(customer.tenant_id))
        except LicenseError as exc:
            write_global_audit_log(
                db,
                entity_type="license",
                entity_id=int(customer.tenant_id),
                action="vehicle_quota_denied_service_onboarding",
                actor_user_id=int(current_user.id),
                actor_role=getattr(current_user, "role", None),
                tenant_id=int(current_user.tenant_id),
                vehicle_id=None,
                metadata={
                    "target_customer_id": int(customer.id),
                    "target_tenant_id": int(customer.tenant_id),
                    "code": getattr(exc, "code", None),
                },
            )
            raise exc
        vehicle = VehicleModel(
            tenant_id=int(customer.tenant_id),
            user_email=email_n,
            nickname=nickname[:120],
            plate=(v.plate or "").strip().upper() or None,
            vin=(v.vin or "").strip().upper() or None,
            brand=(v.brand or "").strip() or None,
            model=(v.model or "").strip() or None,
            year=v.year,
            current_mileage_km=v.mileage,
            stk_valid_until=stk_default,
            provisioned_by_service_customer_id=int(current_user.id),
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(vehicle)
        db.flush()
        ensure_vehicle_owner_assignment(
            db,
            vehicle=vehicle,
            owner=customer,
            assigned_by_customer_id=int(current_user.id),
            ownership_origin="service_provisioned",
        )
        create_or_update_vehicle_service_link(
            db,
            tenant_id=int(customer.tenant_id),
            service_customer_id=int(current_user.id),
            owner_customer_id=int(customer.id),
            vehicle_id=int(vehicle.id),
            approved_by_customer_id=int(customer.id),
            source_type="service_customer_centre_vehicle",
            note="Vozidlo založeno servisem při registraci zákazníka",
        )
        vehicle_id = int(vehicle.id)

        write_global_audit_log(
            db,
            entity_type="service_customer_security",
            entity_id=int(vehicle.id),
            action="SERVICE_CUSTOMER_VEHICLE_ASSIGNED",
            actor_user_id=int(current_user.id),
            tenant_id=int(current_user.tenant_id),
            vehicle_id=int(vehicle.id),
            metadata={"customer_user_id": int(customer.id)},
        )

    write_global_audit_log(
        db,
        entity_type="service_customer_security",
        entity_id=int(customer.id),
        action="SERVICE_CUSTOMER_CREATED_USER_ACCOUNT",
        actor_user_id=int(current_user.id),
        tenant_id=int(current_user.tenant_id),
        metadata={"email_domain": email_n.split("@")[-1] if "@" in email_n else ""},
    )
    invite_audit_action = (
        "SERVICE_CUSTOMER_INVITE_EMAIL_SENT" if email_result.get("sent") else "SERVICE_CUSTOMER_INVITE_EMAIL_FAILED"
    )
    write_global_audit_log(
        db,
        entity_type="service_customer_security",
        entity_id=int(customer.id),
        action=invite_audit_action,
        actor_user_id=int(current_user.id),
        tenant_id=int(current_user.tenant_id),
        metadata={
            "kind": "service_created_account_invite",
            "sent": bool(email_result.get("sent")),
            "reason": email_result.get("reason"),
            "email_domain": email_n.split("@")[-1] if "@" in email_n else "",
            "smtp_configured": bool(smtp_configured),
        },
    )
    db.commit()

    reason_code = email_result.get("reason")
    reason_detail = (
        str(email_result.get("error") or "").strip()
        or (f"Důvod: {reason_code}" if reason_code else "")
        or "SMTP neodesláno"
    )
    if email_result.get("sent"):
        acc_msg = "Zákazník byl přidán. Pozvánka byla odeslána e-mailem."
        notif_body = "Pozvánka byla odeslána e-mailem."
    else:
        acc_msg = f"Zákazník byl přidán, ale e-mail se nepodařilo odeslat: {reason_detail}"
        notif_body = acc_msg

    return {
        "customer_user_id": int(customer.id),
        "customer_link_id": int(link.id),
        "vehicle_id": vehicle_id,
        "email_sent": bool(email_result.get("sent")),
        "notification": {
            "channel": "email",
            "sent": bool(email_result.get("sent")),
            "reason": reason_code,
            "message": notif_body,
        },
        "message": acc_msg,
    }


@router.get("/customers/by-link/{customer_link_id}")
def get_customer_detail_by_link_id(
    customer_link_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_ws(db)

    row = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.id == int(customer_link_id),
            ServiceCustomerLink.service_customer_id == int(current_user.id),
        )
        .first()
    )
    if not row or row.status not in SERVICE_VISIBLE_LINK_STATUSES:
        raise HTTPException(status_code=404, detail="Zákaznická vazba nebyla nalezena.")

    owner = db.query(Customer).filter(Customer.id == int(row.customer_id)).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Zákazník neexistuje.")

    vehicles_out: list[dict[str, Any]] = []
    for v in get_owned_vehicle_rows(db, owner, tenant_id=getattr(owner, "tenant_id", None)):
        approved = (
            db.query(VehicleServiceLink.id)
            .filter(
                VehicleServiceLink.service_customer_id == int(current_user.id),
                VehicleServiceLink.owner_customer_id == int(owner.id),
                VehicleServiceLink.vehicle_id == int(v.id),
                VehicleServiceLink.status == "approved",
            )
            .first()
        )
        last_service_at = (
            db.query(func.max(ServiceRecordModel.performed_at))
            .filter(
                ServiceRecordModel.vehicle_id == int(v.id),
                ServiceRecordModel.user_id == int(current_user.id),
            )
            .scalar()
        )
        vehicles_out.append(
            {
                "vehicle_id": int(v.id),
                "vin": v.vin,
                "plate": v.plate,
                "brand": v.brand,
                "model": v.model,
                "access_status": "approved" if approved else "pending",
                "last_service_at": last_service_at.isoformat() if last_service_at else None,
            }
        )

    disclosure_email = owner.email if row.status == "active" else _mask_email(owner.email)
    disclosure_phone = (
        (owner.phone_e164 or owner.phone)
        if row.status == "active"
        else _mask_phone_e164(owner.phone_e164 or owner.phone)
    )

    return {
        "customer": {
            "id": int(row.id),
            "customer_user_id": int(owner.id),
            "display_name": owner.name or owner.email,
            "email": disclosure_email,
            "phone": disclosure_phone,
            "account_status": str(owner.account_status or ""),
            "link_status": str(row.status or ""),
        },
        "vehicles": vehicles_out,
    }


def confirm_service_customer_link_core(db: Session, *, token: str, acting_customer: Customer) -> dict[str, Any]:
    data = _decode_jwt(token.strip(), _LINK_CONFIRM_JWT_TYP)
    lid = int(data["lid"])
    cid = int(data["cid"])
    if int(acting_customer.id) != cid:
        raise HTTPException(status_code=403, detail="Potvrzení je možné pouze přihlášeným vlastníkem účtu.")

    row = db.query(ServiceCustomerLink).filter(ServiceCustomerLink.id == lid).first()
    if not row or int(row.customer_id) != cid:
        raise HTTPException(status_code=404, detail="Vazba neexistuje.")

    if row.status != "pending_customer_confirm":
        return {
            "confirmed": False,
            "message": "Tuto vazbu nelze tímto odkazem dokončit nebo už je aktivní.",
            "link_status": row.status,
        }

    sid = int(data.get("sid") or row.service_customer_id)
    if int(row.service_customer_id) != sid:
        raise HTTPException(status_code=400, detail="Neplatný token vazby.")

    now = datetime.utcnow()
    row.status = "active"
    row.approved_at = now
    row.updated_at = now

    write_global_audit_log(
        db,
        entity_type="service_customer_security",
        entity_id=int(row.id),
        action="SERVICE_CUSTOMER_LINK_APPROVED",
        actor_user_id=int(acting_customer.id),
        tenant_id=int(acting_customer.tenant_id),
        metadata={"service_customer_id": int(row.service_customer_id)},
    )
    db.commit()
    return {"confirmed": True, "customer_link_id": int(row.id), "link_status": "active"}


def consume_service_onboarding_token_core(
    db: Session,
    *,
    raw_token: str,
    new_password: str,
    request: Optional[Request] = None,
) -> tuple[Customer, str]:
    """Vrátí (customer, access_jwt)."""
    from src.modules.vehicle_hub.account_state import customer_session_version, increment_customer_session_version
    from src.core.security import create_access_token

    th = _hash_token(raw_token.strip())
    row = (
        db.query(UserOnboardingToken)
        .filter(
            UserOnboardingToken.token_hash == th,
            UserOnboardingToken.token_type == "service_created_account_invite",
            UserOnboardingToken.used_at.is_(None),
            UserOnboardingToken.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=400, detail="Neplatný nebo použitý odkaz.")

    customer = db.query(Customer).filter(Customer.id == int(row.user_id)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Účet neexistuje.")

    customer.password_hash = hash_password(new_password)
    customer.force_password_change = False
    customer.email_verified_at = datetime.utcnow()
    customer.account_status = "active"
    row.used_at = datetime.utcnow()

    link = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.customer_id == int(customer.id),
            ServiceCustomerLink.status == "invited",
            ServiceCustomerLink.link_source == "service_created",
        )
        .order_by(ServiceCustomerLink.id.desc())
        .first()
    )
    if link:
        link.status = "active"
        link.approved_at = datetime.utcnow()
        link.updated_at = datetime.utcnow()

    increment_customer_session_version(customer)

    write_global_audit_log(
        db,
        entity_type="service_customer_security",
        entity_id=int(customer.id),
        action="SERVICE_CUSTOMER_ACCOUNT_ONBOARDING_COMPLETED",
        actor_user_id=int(customer.id),
        tenant_id=int(customer.tenant_id),
        ip=(request.client.host if request and request.client else None),
        user_agent=(request.headers.get("user-agent") if request else None),
    )
    db.commit()

    token = create_access_token(data={"sub": customer.email, "sv": customer_session_version(customer)})
    return customer, token
