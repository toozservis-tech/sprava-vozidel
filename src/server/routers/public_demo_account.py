"""
Veřejný ukázkový účet — zapnuto přes SPRAVA_VOZIDEL_PUBLIC_DEMO_CREDENTIALS.

GET vrací jen stav. Přístup: návštěvník zadá e-mail + souhlas → odešle se e-mail
s náhodným odkazem. Odkaz lze použít jen jednou a jen ze stejné IP jako při žádosti
(očekává se otevření na stejném připojení). Vyžaduje nakonfigurované SMTP.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from src.core.branding import APP_DISPLAY_NAME
from src.core.config import PUBLIC_API_BASE_URL
from src.core.env_aliases import env_prefer_new
from src.core.rate_limiter import rate_limiter
from src.core.security import create_access_token
from src.modules.email_client.service import EmailService
from src.modules.email_client.templates import render_email_callout, render_email_layout
from src.modules.vehicle_hub.account_state import (
    customer_is_deleted,
    customer_is_disabled,
    customer_session_version,
    touch_customer_last_login,
)
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import CustomerSecuritySettings, DemoAccessToken
from src.server.main_helpers import get_customer_by_email, normalize_email
from src.server.security_tracking import extract_client_ip, log_security_event

router = APIRouter(prefix="/api/public/demo-account", tags=["public-demo-account"])

_DEMO_LINK_INVALID = (
    "Odkaz je neplatný, vypršel nebo byl již použit. Vyžádejte si prosím nový odkaz na přihlášení."
)


class PublicDemoAccountResponse(BaseModel):
    enabled: bool = False
    gated: bool = True
    access_via_email_link: bool = True
    disclaimer: str = Field(
        default=(
            "Ukázkový účet obsahuje pouze obecná ilustrační data pro vyzkoušení ovládání. "
            "Nejsou v něm žádné interní postupy ani obchodní know-how provozovatele."
        )
    )


class DemoAccessRequestBody(BaseModel):
    visitor_email: str
    contact_consent: bool = False


class DemoAccessLinkQueuedResponse(BaseModel):
    ok: bool = True
    message: str = "Odkaz do ukázky jsme odeslali na váš e-mail."


class DemoRedeemRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=256)


class DemoRedeemResponse(BaseModel):
    """Stejný tvar jako úspěšné POST /user/login — bez hesla v odpovědi (Chrome ho neukládá)."""

    ok: bool = True
    access_token: str
    user: dict
    disclaimer: str = Field(
        default=(
            "Ukázkový účet obsahuje pouze obecná ilustrační data pro vyzkoušení ovládání. "
            "Nejsou v něm žádné interní postupy ani obchodní know-how provozovatele."
        )
    )


_LOOSE_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _truthy_env(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


def _int_env(primary: str, legacy: str, default: int, *, minimum: int = 1) -> int:
    raw = (env_prefer_new(primary, legacy) or "").strip()
    if not raw:
        return max(minimum, default)
    try:
        return max(minimum, int(raw))
    except ValueError:
        return max(minimum, default)


def _demo_credentials() -> tuple[str, str] | None:
    email = (env_prefer_new("SPRAVA_VOZIDEL_DEMO_ACCOUNT_EMAIL", "TOOZHUB_DEMO_ACCOUNT_EMAIL") or "").strip()
    password = env_prefer_new("SPRAVA_VOZIDEL_DEMO_ACCOUNT_PASSWORD", "TOOZHUB_DEMO_ACCOUNT_PASSWORD") or ""
    if not email or not password:
        return None
    return email, password


def _hash_demo_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _ip_for_demo_bind(request: Request) -> str:
    try:
        return (extract_client_ip(request) or "").strip()
    except Exception:
        return ""


def _ips_match(stored: str | None, current: str | None) -> bool:
    a = (stored or "").strip()
    b = (current or "").strip()
    if not a or not b:
        return False
    return a == b


def _demo_link_ttl_hours() -> int:
    return _int_env(
        "SPRAVA_VOZIDEL_DEMO_LINK_TTL_HOURS",
        "TOOZHUB_DEMO_LINK_TTL_HOURS",
        24,
        minimum=1,
    )


def _public_demo_entry_url(token: str) -> str:
    base = str(PUBLIC_API_BASE_URL or "").strip().rstrip("/")
    if not base:
        base = "https://hub.toozservis.cz"
    path = "/web/demo.html"
    return f"{base}{path}?token={quote(token, safe='')}"


@router.get("", response_model=PublicDemoAccountResponse)
def get_public_demo_account() -> PublicDemoAccountResponse:
    flag = env_prefer_new("SPRAVA_VOZIDEL_PUBLIC_DEMO_CREDENTIALS", "TOOZHUB_PUBLIC_DEMO_CREDENTIALS")
    if not _truthy_env(flag):
        return PublicDemoAccountResponse(enabled=False, gated=True, access_via_email_link=True)

    if _demo_credentials() is None:
        return PublicDemoAccountResponse(enabled=False, gated=True, access_via_email_link=True)

    return PublicDemoAccountResponse(enabled=True, gated=True, access_via_email_link=True)


@router.post("/access", response_model=DemoAccessLinkQueuedResponse)
def request_demo_access(
    payload: DemoAccessRequestBody,
    request: Request,
    db: Session = Depends(get_db),
) -> DemoAccessLinkQueuedResponse:
    flag = env_prefer_new("SPRAVA_VOZIDEL_PUBLIC_DEMO_CREDENTIALS", "TOOZHUB_PUBLIC_DEMO_CREDENTIALS")
    if not _truthy_env(flag):
        raise HTTPException(status_code=404, detail="Ukázkový režim není aktivní.")

    creds = _demo_credentials()
    if creds is None:
        raise HTTPException(status_code=503, detail="Ukázkový účet není nakonfigurován.")

    demo_email, _demo_password = creds

    if not payload.contact_consent:
        raise HTTPException(
            status_code=400,
            detail="Pro odeslání odkazu je potřeba souhlas se zasláním informací v souvislosti s nabídkou a ukázkou.",
        )

    visitor = normalize_email((payload.visitor_email or "").strip())
    if not visitor or not _LOOSE_EMAIL_RE.match(visitor):
        raise HTTPException(status_code=400, detail="Zadejte platný e-mail.")
    if visitor == normalize_email(demo_email):
        raise HTTPException(
            status_code=400,
            detail="Zadejte svůj kontaktní e-mail, ne přihlašovací údaj ukázkového účtu.",
        )

    email_service = EmailService()
    if not email_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Odesílání odkazu není k dispozici (chybí SMTP). Kontaktujte správce aplikace.",
        )

    client_ip = _ip_for_demo_bind(request)
    if not client_ip:
        raise HTTPException(
            status_code=400,
            detail="Nepodařilo se zjistit vaši síťovou adresu. Zkuste to z jiného připojení nebo kontaktujte podporu.",
        )

    ip_key = f"demo_access_ip:{client_ip or 'unknown'}"
    ip_max = _int_env(
        "SPRAVA_VOZIDEL_DEMO_ACCESS_MAX_PER_IP_HOUR",
        "TOOZHUB_DEMO_ACCESS_MAX_PER_IP_HOUR",
        24,
        minimum=3,
    )
    em_max = _int_env(
        "SPRAVA_VOZIDEL_DEMO_ACCESS_MAX_PER_EMAIL_HOUR",
        "TOOZHUB_DEMO_ACCESS_MAX_PER_EMAIL_HOUR",
        8,
        minimum=2,
    )

    if not rate_limiter.check_rate_limit(ip_key, max_calls=ip_max, period=3600):
        raise HTTPException(
            status_code=429,
            detail="Příliš mnoho pokusů z této sítě. Zkuste to prosím později.",
        )
    email_key = f"demo_access_email:{visitor}"
    if not rate_limiter.check_rate_limit(email_key, max_calls=em_max, period=3600):
        raise HTTPException(
            status_code=429,
            detail="Pro tento e-mail bylo vyčerpáno dočasné omezení. Zkuste to prosím později.",
        )

    ua = (request.headers.get("user-agent") or "").strip() or None
    if ua and len(ua) > 4000:
        ua = ua[:4000]

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_demo_token(raw_token)
    now = datetime.utcnow()
    ttl_hours = _demo_link_ttl_hours()
    expires_at = now + timedelta(hours=ttl_hours)

    try:
        db.query(DemoAccessToken).filter(
            DemoAccessToken.visitor_email == visitor,
            DemoAccessToken.consumed_at.is_(None),
        ).delete(synchronize_session=False)

        row = DemoAccessToken(
            token_hash=token_hash,
            visitor_email=visitor,
            request_ip=client_ip[:128],
            user_agent=ua,
            contact_consent=True,
            created_at=now,
            expires_at=expires_at,
        )
        db.add(row)
        db.commit()
    except OperationalError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Databáze nemá připravenou tabulku pro ukázkové odkazy. Spusťte migrace (alembic).",
        ) from exc

    entry_url = _public_demo_entry_url(raw_token)
    hours_cs = f"{ttl_hours} hodin" if ttl_hours != 24 else "24 hodin"

    plain = f"""Dobrý den,

požádali jste o přístup k interaktivní ukázce aplikace {APP_DISPLAY_NAME}.

Otevřete odkaz v prohlížeči na stejném připojení (síti), ze kterého jste o ukázku požádali.
Odkaz je jednorázový a vyprší za {hours_cs}.

{entry_url}

Pokud jste o ukázku nežádali, tento e-mail ignorujte.

S pozdravem,
{APP_DISPLAY_NAME}
"""
    html_body = render_email_layout(
        title="Váš odkaz do ukázky",
        subtitle=f"Platnost odkazu: {hours_cs}. Použijte stejné připojení jako při žádosti.",
        intro="Dobrý den,",
        paragraphs=[
            f"níže najdete odkaz do interaktivní ukázky aplikace {APP_DISPLAY_NAME}.",
            "Odkaz je jednorázový a je vázaný na síť, ze které jste o ukázku požádali.",
        ],
        panels=[
            render_email_callout(
                title="Důležité",
                rows=[
                    ("Platnost odkazu", hours_cs),
                    ("Ověřený e-mail", visitor),
                ],
                accent="#2563eb",
            )
        ],
        cta_label="Otevřít ukázku",
        cta_url=entry_url,
        accent="#2563eb",
    )

    try:
        email_service.send_simple_email(
            to=visitor,
            subject=f"Odkaz do ukázky — {APP_DISPLAY_NAME}",
            body=plain,
            html_body=html_body,
        )
    except Exception as exc:
        db.query(DemoAccessToken).filter(DemoAccessToken.token_hash == token_hash).delete(synchronize_session=False)
        db.commit()
        raise HTTPException(
            status_code=503,
            detail="Odkaz se nepodařilo odeslat e-mailem. Zkuste to později nebo kontaktujte podporu.",
        ) from exc

    return DemoAccessLinkQueuedResponse()


@router.post("/redeem", response_model=DemoRedeemResponse)
def redeem_demo_access(
    payload: DemoRedeemRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> DemoRedeemResponse:
    flag = env_prefer_new("SPRAVA_VOZIDEL_PUBLIC_DEMO_CREDENTIALS", "TOOZHUB_PUBLIC_DEMO_CREDENTIALS")
    if not _truthy_env(flag):
        raise HTTPException(status_code=404, detail=_DEMO_LINK_INVALID)

    creds = _demo_credentials()
    if creds is None:
        raise HTTPException(status_code=503, detail=_DEMO_LINK_INVALID)

    demo_email, _demo_password_unused = creds
    token_raw = (payload.token or "").strip()
    if not token_raw:
        raise HTTPException(status_code=400, detail=_DEMO_LINK_INVALID)

    token_hash = _hash_demo_token(token_raw)
    now = datetime.utcnow()
    client_ip = _ip_for_demo_bind(request)

    row = db.query(DemoAccessToken).filter(DemoAccessToken.token_hash == token_hash).one_or_none()
    if row is None:
        raise HTTPException(status_code=400, detail=_DEMO_LINK_INVALID)
    if row.consumed_at is not None or row.expires_at < now:
        raise HTTPException(status_code=400, detail=_DEMO_LINK_INVALID)
    if not _ips_match(row.request_ip, client_ip):
        raise HTTPException(status_code=400, detail=_DEMO_LINK_INVALID)

    customer = get_customer_by_email(db, normalize_email(demo_email))
    if not customer:
        raise HTTPException(
            status_code=503,
            detail="Ukázkový účet není v databázi. Spusťte seed ukázkového účtu.",
        )
    if customer_is_deleted(customer):
        raise HTTPException(status_code=403, detail="Ukázkový účet je nedostupný.")
    if customer_is_disabled(customer):
        raise HTTPException(status_code=403, detail="Ukázkový účet je nedostupný.")

    security_settings = (
        db.query(CustomerSecuritySettings)
        .filter(CustomerSecuritySettings.customer_id == customer.id)
        .first()
    )
    if security_settings and security_settings.two_factor_enabled and security_settings.totp_secret:
        raise HTTPException(
            status_code=400,
            detail="Pro vstup z odkazu musí být u ukázkového účtu vypnuté dvoufázové ověření.",
        )

    updated = (
        db.query(DemoAccessToken)
        .filter(
            DemoAccessToken.id == row.id,
            DemoAccessToken.consumed_at.is_(None),
        )
        .update({"consumed_at": now}, synchronize_session=False)
    )
    if updated != 1:
        db.rollback()
        raise HTTPException(status_code=400, detail=_DEMO_LINK_INVALID)

    touch_customer_last_login(customer)
    try:
        db.commit()
    except OperationalError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Dočasná chyba databáze. Zkuste to znovu.") from exc

    access_token = create_access_token(
        data={"sub": customer.email, "sv": customer_session_version(customer)}
    )
    log_security_event(
        event_type="login_success",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"role": customer.role or "user", "via": "public_demo_magic_link"},
    )

    disclaimer = PublicDemoAccountResponse().disclaimer
    return DemoRedeemResponse(
        access_token=access_token,
        user={
            "id": customer.id,
            "email": customer.email,
            "name": customer.name,
            "ico": customer.ico,
            "role": customer.role or "user",
        },
        disclaimer=disclaimer,
    )
