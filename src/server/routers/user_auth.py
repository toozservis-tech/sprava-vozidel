from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import json
import re
import secrets
import time
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import func

from src.core.config import (
    ENVIRONMENT,
    LOGIN_RATE_LIMIT_MAX,
    PUBLIC_API_BASE_URL,
    REGISTER_RATE_LIMIT_EMAIL_MAX,
    REGISTER_RATE_LIMIT_IP_MAX,
)
from src.core.branding import APP_DISPLAY_NAME
from src.core.rate_limiter import rate_limiter
from src.server.e2e_rate_limit import e2e_rate_limit_bypass_active
from src.core.security import create_access_token, hash_password, needs_rehash, verify_password
from src.modules.email_client.templates import build_app_url, render_email_layout, render_panel
from src.modules.vehicle_hub.account_state import (
    customer_is_deleted,
    customer_is_disabled,
    customer_session_version,
    increment_customer_session_version,
    touch_customer_last_login,
)
from src.modules.vehicle_hub.customer_ordinal import assign_admin_ordinal_if_missing
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, CustomerSecuritySettings, ServiceRegistrationRequest
from src.modules.vehicle_hub.routers_v1.auth import get_current_user as get_v1_current_user
from src.modules.vehicle_hub.routers_v1.ares_lookup import lookup_ares as lookup_ares_v1
from src.modules.vehicle_hub.registration_security import (
    assert_ico_exists_in_ares,
    collect_email_domain_risk_flags,
    generate_email_verification_secret,
    hash_email_verification_token,
    is_disposable_email_domain,
    normalize_validate_phone_e164,
)
from src.modules.vehicle_hub.tenant_provisioning import create_dedicated_tenant, ensure_default_license_for_tenant
from src.modules.licensing.service import activate_initial_user_trial_on_first_login
from src.server.main_helpers import (
    ForgotPasswordRequest,
    LoginResponse,
    RegisterTokenResponse,
    ResendVerificationEmailRequest,
    ResetPasswordRequest,
    ServiceRegisterRequest,
    ServiceRegisterResponse,
    ServiceInviteOnboardingRequest,
    TokenResponse,
    TwoFactorLoginVerifyRequest,
    UserLogin,
    UserRegister,
    VerifyEmailRequest,
    get_active_ip_block,
    get_customer_by_email,
    normalize_email,
    normalize_ico,
    send_registration_alert_email,
)
from src.server.security_helpers import (
    create_2fa_login_challenge,
    get_2fa_login_challenge,
    pop_2fa_login_challenge,
    set_2fa_login_challenge,
    verify_totp,
)
from src.server.security_tracking import extract_client_ip, log_security_event


router = APIRouter()

_EMAIL_VERIFICATION_TTL = timedelta(minutes=30)


def _login_blocked_pending_email_verification(customer: Customer) -> bool:
    return customer.email_verified_at is None


def _send_email_verification_link_email(*, email: str, name: str | None, token: str) -> None:
    try:
        from src.modules.email_client.service import EmailService

        email_service = EmailService()
        if not email_service.is_configured():
            print("[REGISTER] WARNING: SMTP není nakonfigurováno, ověřovací e-mail nebyl odeslán")
            return

        user_name = (name or "uživateli").strip()
        verify_url = f"{build_app_url('/web/verify-email.html')}?token={quote(token, safe='')}"

        email_body = f"""
Dobrý den {user_name},

dokončete registraci v aplikaci {APP_DISPLAY_NAME} kliknutím na odkaz níže (platnost {int(_EMAIL_VERIFICATION_TTL.total_seconds() // 60)} minut):

{verify_url}

Pokud jste o účet nežádali, tento e-mail ignorujte.

{APP_DISPLAY_NAME}
"""

        html_body = render_email_layout(
            title="Ověřte e-mailovou adresu",
            subtitle="Jednorázový odkaz pro dokončení registrace.",
            intro=f"Dobrý den {user_name},",
            paragraphs=[
                f"pro aktivaci účtu v aplikaci {APP_DISPLAY_NAME} je nutné ověřit tuto e-mailvou adresu.",
                f"Odkaz je platný {int(_EMAIL_VERIFICATION_TTL.total_seconds() // 60)} minut.",
            ],
            panels=[
                render_panel(
                    title="Ověření",
                    rows=[("Účet", email)],
                )
            ],
            cta_label="Ověřit e-mail",
            cta_url=verify_url,
            accent="#f59e0b",
        )
        email_service.send_simple_email(
            to=email,
            subject=f"Ověření e-mailu — {APP_DISPLAY_NAME}",
            body=email_body,
            html_body=html_body,
        )
    except Exception as exc:
        print(f"[REGISTER] ERROR: Ověřovací e-mail se nepodařilo odeslat: {exc}")


def _schedule_verification_email(customer: Customer, raw_token: str, background_tasks: BackgroundTasks) -> None:
    background_tasks.add_task(
        _send_email_verification_link_email,
        email=customer.email,
        name=customer.name,
        token=raw_token,
    )


def _send_registration_alert_email_background(
    *,
    registration_type: str,
    account_email: str,
    account_name: str | None = None,
    account_ico: str | None = None,
    metadata: dict | None = None,
) -> None:
    from src.modules.vehicle_hub.database import SessionLocal

    db = SessionLocal()
    try:
        developer_alert = send_registration_alert_email(
            db,
            registration_type=registration_type,
            account_email=account_email,
            account_name=account_name,
            account_ico=account_ico,
            metadata=metadata,
        )
        if developer_alert.get("status") not in {"sent", "no_recipients", "smtp_not_configured"}:
            print(f"[REGISTER] Developer alert status: {developer_alert.get('status')} error={developer_alert.get('error')}")
    finally:
        db.close()


@router.post("/user/register", response_model=RegisterTokenResponse)
def register_user(
    user_data: UserRegister,
    background_tasks: BackgroundTasks,
    request: Request,
    db=Depends(get_db),
):
    normalized_email = normalize_email(user_data.email)
    normalized_ico = normalize_ico(user_data.ico)
    domain_part = normalized_email.split("@", 1)[-1].strip().lower() if "@" in normalized_email else ""

    if not user_data.password or len(user_data.password) < 6:
        raise HTTPException(status_code=400, detail="Heslo musí mít alespoň 6 znaků")

    client_ip = extract_client_ip(request) or "unknown"
    if not e2e_rate_limit_bypass_active(request) and not rate_limiter.check_rate_limit(
        f"register_ip:{client_ip}", max_calls=REGISTER_RATE_LIMIT_IP_MAX, period=3600
    ):
        raise HTTPException(status_code=429, detail="Příliš mnoho pokusů o registraci. Zkuste to později.")
    if not e2e_rate_limit_bypass_active(request) and not rate_limiter.check_rate_limit(
        f"register_email:{normalized_email}", max_calls=REGISTER_RATE_LIMIT_EMAIL_MAX, period=3600
    ):
        raise HTTPException(status_code=429, detail="Příliš mnoho pokusů o registraci pro tento e-mail.")

    existing = get_customer_by_email(db, normalized_email)
    if existing:
        raise HTTPException(status_code=400, detail="Uživatel s tímto emailem již existuje")

    if is_disposable_email_domain(domain_part):
        log_security_event(
            event_type="registration_risk_flagged",
            request=request,
            user_email=normalized_email,
            endpoint=str(request.url.path),
            details={"reason": "disposable_email_domain", "domain": domain_part},
        )
        raise HTTPException(
            status_code=422,
            detail="Tento typ e-mailové adresy není pro registraci podporován. Použijte běžnou doménu.",
        )

    domain_flags, domain_ok = collect_email_domain_risk_flags(domain_part)
    if not domain_ok:
        log_security_event(
            event_type="registration_risk_flagged",
            request=request,
            user_email=normalized_email,
            endpoint=str(request.url.path),
            details={"reason": "email_domain_rejected", "flags": domain_flags},
        )
        raise HTTPException(
            status_code=422,
            detail="E-mailová doména neexistuje nebo neumožňuje doručování zpráv. Zkontrolujte překlep.",
        )

    risk_flags: list[str] = list(domain_flags)

    try:
        phone_e164 = normalize_validate_phone_e164(user_data.phone)
    except ValueError as exc:
        log_security_event(
            event_type="registration_rejected_invalid_phone",
            request=request,
            user_email=normalized_email,
            endpoint=str(request.url.path),
            details={"reason": "invalid_phone"},
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if risk_flags:
        log_security_event(
            event_type="registration_risk_flagged",
            request=request,
            user_email=normalized_email,
            endpoint=str(request.url.path),
            details={"risk_flags": risk_flags},
        )

    try:
        hashed_password = hash_password(user_data.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    raw_token = generate_email_verification_secret()
    token_hash = hash_email_verification_token(raw_token)
    now = datetime.utcnow()
    reg_ip = (extract_client_ip(request) or "")[:128] or None
    reg_ua = (request.headers.get("user-agent") or "")[:2000] or None

    dedicated_tenant = create_dedicated_tenant(
        db,
        owner_email=normalized_email,
        owner_name=user_data.name,
    )

    phone_digits = re.sub(r"\D+", "", phone_e164 or "")

    customer = Customer(
        tenant_id=dedicated_tenant.id,
        email=normalized_email,
        password_hash=hashed_password,
        name=user_data.name,
        ico=normalized_ico,
        dic=user_data.dic,
        street=user_data.street,
        street_number=user_data.street_number,
        city=user_data.city,
        zip=user_data.zip,
        phone=user_data.phone,
        phone_e164=phone_e164,
        email_normalized=normalized_email,
        phone_normalized=phone_digits or None,
        account_status="pending_email_verification",
        email_verification_token_hash=token_hash,
        email_verification_expires_at=now + _EMAIL_VERIFICATION_TTL,
        email_verification_sent_at=now,
        registration_ip=reg_ip,
        registration_user_agent=reg_ua,
        registration_risk_flags=risk_flags or None,
    )

    db.add(customer)
    db.flush()
    assign_admin_ordinal_if_missing(db, customer)
    db.commit()
    db.refresh(customer)

    ensure_default_license_for_tenant(db, dedicated_tenant.id)

    log_security_event(
        event_type="registration_created",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"account_status": customer.account_status, "risk_flag_count": len(risk_flags)},
    )

    _schedule_verification_email(customer, raw_token, background_tasks)
    log_security_event(
        event_type="email_verification_sent",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"channel": "email"},
    )

    email_status_label = "pending"
    phone_status_label = "unverified"

    background_tasks.add_task(
        _send_registration_alert_email_background,
        registration_type="user",
        account_email=customer.email,
        account_name=customer.name,
        account_ico=customer.ico,
        metadata={
            "customer_id": customer.id,
            "tenant_id": customer.tenant_id,
            "role": customer.role or "user",
            "email_status": email_status_label,
            "phone_status": phone_status_label,
            "fraud_score": len(risk_flags),
            "risk_flags": json.dumps(risk_flags, ensure_ascii=False) if risk_flags else "[]",
            "registration_ip": reg_ip,
            "registration_user_agent": reg_ua,
            "account_status": customer.account_status,
        },
    )

    return RegisterTokenResponse(
        access_token=None,
        user={
            "id": customer.id,
            "email": customer.email,
            "name": customer.name,
            "ico": customer.ico,
            "role": customer.role or "user",
            "account_status": customer.account_status,
        },
        verification_required=True,
        message="Registrace přijata. Na e-mail vám byl odeslán ověřovací odkaz.",
        email_sent=True,
        registration_email_status="queued",
    )


@router.post("/user/register/service-request", response_model=ServiceRegisterResponse)
def register_service_request(payload: ServiceRegisterRequest, request: Request, db=Depends(get_db)):
    normalized_email = normalize_email(payload.email)
    ico_digits = normalize_ico(payload.ico) or ""
    domain_part = normalized_email.split("@", 1)[-1].strip().lower() if "@" in normalized_email else ""

    if not payload.password or len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Heslo musí mít alespoň 6 znaků")
    if len(ico_digits) != 8:
        raise HTTPException(status_code=400, detail="IČO musí obsahovat přesně 8 číslic")

    if is_disposable_email_domain(domain_part):
        raise HTTPException(
            status_code=422,
            detail="Tento typ e-mailové adresy není pro registraci podporován. Použijte běžnou doménu.",
        )
    domain_flags, domain_ok = collect_email_domain_risk_flags(domain_part)
    if not domain_ok:
        raise HTTPException(
            status_code=422,
            detail="E-mailová doména neexistuje nebo neumožňuje doručování zpráv. Zkontrolujte překlep.",
        )
    risk_flags: list[str] = list(domain_flags)

    try:
        phone_e164 = normalize_validate_phone_e164(payload.phone)
    except ValueError as exc:
        log_security_event(
            event_type="registration_rejected_invalid_phone",
            request=request,
            user_email=normalized_email,
            endpoint=str(request.url.path),
            details={"flow": "service_request"},
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        assert_ico_exists_in_ares(ico_digits)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    reg_ip = (extract_client_ip(request) or "")[:128] or None
    reg_ua = (request.headers.get("user-agent") or "")[:2000] or None

    if get_customer_by_email(db, normalized_email):
        raise HTTPException(status_code=400, detail="Účet s tímto emailem již existuje")

    existing_service_customer_same_ico = (
        db.query(Customer)
        .filter(
            Customer.role == "service",
            Customer.ico == ico_digits,
            func.lower(Customer.email) != normalized_email,
        )
        .first()
    )
    if existing_service_customer_same_ico:
        raise HTTPException(
            status_code=400,
            detail="Toto IČO je už registrováno u jiného servisního účtu.",
        )

    existing_request_same_ico = (
        db.query(ServiceRegistrationRequest)
        .filter(
            ServiceRegistrationRequest.ico == ico_digits,
            func.lower(ServiceRegistrationRequest.email) != normalized_email,
            ServiceRegistrationRequest.status.in_(["pending", "approved"]),
        )
        .first()
    )
    if existing_request_same_ico:
        raise HTTPException(
            status_code=400,
            detail="Toto IČO už má aktivní nebo schválenou servisní registraci.",
        )

    existing_request = (
        db.query(ServiceRegistrationRequest)
        .filter(func.lower(ServiceRegistrationRequest.email) == normalized_email)
        .first()
    )

    hashed_password = hash_password(payload.password)
    now = datetime.utcnow()

    if existing_request:
        if existing_request.status == "pending":
            raise HTTPException(
                status_code=400,
                detail="Žádost pro tento email už čeká na schválení developerem.",
            )
        if existing_request.status == "approved":
            raise HTTPException(
                status_code=400,
                detail="Tato servisní registrace už byla schválena. Přihlaste se.",
            )

        existing_request.status = "pending"
        existing_request.password_hash = hashed_password
        existing_request.ico = ico_digits
        existing_request.service_name = payload.service_name.strip()
        existing_request.responsible_person = payload.responsible_person.strip()
        existing_request.phone = payload.phone.strip()
        existing_request.street = payload.street.strip()
        existing_request.street_number = (payload.street_number or "").strip() or None
        existing_request.city = payload.city.strip()
        existing_request.zip = payload.zip.strip()
        existing_request.dic = (payload.dic or "").strip() or None
        existing_request.registration_purpose = payload.registration_purpose.strip()
        existing_request.reviewed_by_customer_id = None
        existing_request.reviewed_at = None
        existing_request.review_note = None
        existing_request.approved_customer_id = None
        existing_request.approved_tenant_id = None
        existing_request.updated_at = now
        db.commit()
        db.refresh(existing_request)

        developer_alert = send_registration_alert_email(
            db,
            registration_type="service",
            account_email=existing_request.email,
            account_name=existing_request.service_name,
            account_ico=existing_request.ico,
            metadata={
                "request_id": existing_request.id,
                "status": existing_request.status,
                "city": existing_request.city,
                "responsible_person": existing_request.responsible_person,
                "phone": existing_request.phone,
                "phone_e164": phone_e164,
                "purpose": existing_request.registration_purpose[:180],
                "event": "service_request_resubmitted",
                "email_status": "pending",
                "phone_status": "unverified",
                "fraud_score": len(risk_flags),
                "risk_flags": json.dumps(risk_flags, ensure_ascii=False) if risk_flags else "[]",
                "registration_ip": reg_ip,
                "registration_user_agent": reg_ua,
                "role": "service",
            },
        )
        if developer_alert.get("status") not in {"sent", "no_recipients", "smtp_not_configured"}:
            print(f"[REGISTER] Developer alert status: {developer_alert.get('status')} error={developer_alert.get('error')}")

        return ServiceRegisterResponse(
            request_id=existing_request.id,
            status="pending",
            message="Žádost o servisní registraci byla znovu odeslána ke schválení.",
        )

    new_request = ServiceRegistrationRequest(
        status="pending",
        email=normalized_email,
        password_hash=hashed_password,
        ico=ico_digits,
        service_name=payload.service_name.strip(),
        responsible_person=payload.responsible_person.strip(),
        phone=payload.phone.strip(),
        street=payload.street.strip(),
        street_number=(payload.street_number or "").strip() or None,
        city=payload.city.strip(),
        zip=payload.zip.strip(),
        dic=(payload.dic or "").strip() or None,
        registration_purpose=payload.registration_purpose.strip(),
        created_at=now,
        updated_at=now,
    )

    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    developer_alert = send_registration_alert_email(
        db,
        registration_type="service",
        account_email=new_request.email,
        account_name=new_request.service_name,
        account_ico=new_request.ico,
        metadata={
            "request_id": new_request.id,
            "status": new_request.status,
            "city": new_request.city,
            "responsible_person": new_request.responsible_person,
            "phone": new_request.phone,
            "phone_e164": phone_e164,
            "purpose": new_request.registration_purpose[:180],
            "event": "service_request_created",
            "email_status": "pending",
            "phone_status": "unverified",
            "fraud_score": len(risk_flags),
            "risk_flags": json.dumps(risk_flags, ensure_ascii=False) if risk_flags else "[]",
            "registration_ip": reg_ip,
            "registration_user_agent": reg_ua,
            "role": "service",
        },
    )
    if developer_alert.get("status") not in {"sent", "no_recipients", "smtp_not_configured"}:
        print(f"[REGISTER] Developer alert status: {developer_alert.get('status')} error={developer_alert.get('error')}")

    return ServiceRegisterResponse(
        request_id=new_request.id,
        status="pending",
        message="Žádost o servisní účet byla přijata. Aktivace proběhne po ověření developerem.",
    )


@router.post("/user/login", response_model=LoginResponse)
def login_user(login_data: UserLogin, request: Request, db=Depends(get_db)):
    normalized_email = normalize_email(login_data.email)
    masked = normalized_email[:2] + "***" + normalized_email[-1:] if len(normalized_email) > 3 else "***"
    print(f"[LOGIN] Request received for {masked} (path={request.url.path})")
    try:
        client_ip = extract_client_ip(request) or "unknown"
        ip_block = get_active_ip_block(db, client_ip)
        if ip_block:
            detail_payload = {
                "reason": "blocked_ip",
                "blocked_at": ip_block.blocked_at.isoformat() if ip_block.blocked_at else None,
                "expires_at": ip_block.expires_at.isoformat() if ip_block.expires_at else None,
            }
            if ip_block.reason:
                detail_payload["block_reason"] = ip_block.reason
            log_security_event(
                event_type="login_blocked_ip",
                request=request,
                user_email=normalized_email,
                endpoint=str(request.url.path),
                details=detail_payload,
            )
            raise HTTPException(
                status_code=403,
                detail="Přístup z této IP adresy je dočasně zablokován.",
            )

        key = f"login:{normalized_email}:{client_ip}"
        if not e2e_rate_limit_bypass_active(request) and not rate_limiter.check_rate_limit(
            key, max_calls=LOGIN_RATE_LIMIT_MAX, period=60
        ):
            log_security_event(
                event_type="login_rate_limited",
                request=request,
                user_email=normalized_email,
                endpoint=str(request.url.path),
                details={"reason": "rate_limit", "max_calls": LOGIN_RATE_LIMIT_MAX, "period_sec": 60},
            )
            raise HTTPException(
                status_code=429,
                detail="Příliš mnoho pokusů o přihlášení. Zkuste to znovu za minutu.",
            )

        customer = get_customer_by_email(db, normalized_email)
        if not customer:
            log_security_event(
                event_type="login_failed",
                request=request,
                user_email=normalized_email,
                endpoint=str(request.url.path),
                details={"reason": "user_not_found"},
            )
            raise HTTPException(status_code=401, detail="Neplatný email nebo heslo")

        if customer_is_deleted(customer):
            log_security_event(
                event_type="login_failed",
                request=request,
                user_email=normalized_email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"reason": "account_deleted"},
            )
            raise HTTPException(status_code=403, detail="Účet byl deaktivován.")

        if customer_is_disabled(customer):
            log_security_event(
                event_type="login_failed",
                request=request,
                user_email=normalized_email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"reason": "account_disabled"},
            )
            raise HTTPException(status_code=403, detail="Účet je dočasně pozastaven.")

        if not customer.password_hash:
            log_security_event(
                event_type="login_failed",
                request=request,
                user_email=normalized_email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"reason": "password_not_set_use_onboarding"},
            )
            raise HTTPException(
                status_code=403,
                detail="Účet dokončete odkazem z e-mailu (nastavení hesla) — přihlášení pouze heslem zatím není k dispozici.",
            )

        if not verify_password(login_data.password, customer.password_hash):
            log_security_event(
                event_type="login_failed",
                request=request,
                user_email=normalized_email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"reason": "invalid_password"},
            )
            raise HTTPException(status_code=401, detail="Neplatný email nebo heslo")

        if _login_blocked_pending_email_verification(customer):
            log_security_event(
                event_type="login_blocked_email_unverified",
                request=request,
                user_email=normalized_email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"account_status": getattr(customer, "account_status", None)},
            )
            raise HTTPException(
                status_code=403,
                detail="Nejdříve ověřte e-mailovou adresu.",
            )

        original_last_login_at = customer.last_login_at
        requested_role = (login_data.expected_role or "").strip().lower()
        if requested_role in {"user", "service"}:
            from src.modules.vehicle_hub.workspace_entitlements import effective_workspace_kinds

            kinds = effective_workspace_kinds(customer)
            if requested_role == "service" and "service" not in kinds:
                log_security_event(
                    event_type="login_failed",
                    request=request,
                    user_email=normalized_email,
                    customer_id=customer.id,
                    tenant_id=customer.tenant_id,
                    endpoint=str(request.url.path),
                    details={"reason": "role_mismatch_service", "workspace_kinds": list(kinds)},
                )
                raise HTTPException(
                    status_code=403,
                    detail="Tento účet nemá povolený servisní režim přihlášení. Přepněte na Uživatel.",
                )
            if requested_role == "user" and "user" not in kinds:
                log_security_event(
                    event_type="login_failed",
                    request=request,
                    user_email=normalized_email,
                    customer_id=customer.id,
                    tenant_id=customer.tenant_id,
                    endpoint=str(request.url.path),
                    details={"reason": "role_mismatch_user", "workspace_kinds": list(kinds)},
                )
                raise HTTPException(
                    status_code=403,
                    detail="Tento účet nemá povolený uživatelský režim přihlášení. Přepněte na Servis.",
                )

        if needs_rehash(customer.password_hash):
            customer.password_hash = hash_password(login_data.password)
            db.commit()

        security_settings = (
            db.query(CustomerSecuritySettings)
            .filter(CustomerSecuritySettings.customer_id == customer.id)
            .first()
        )
        if security_settings and security_settings.two_factor_enabled and security_settings.totp_secret:
            challenge_token, expires_in = create_2fa_login_challenge(
                customer=customer,
                expected_role=requested_role if requested_role in {"user", "service"} else None,
            )
            log_security_event(
                event_type="login_2fa_challenge_issued",
                request=request,
                user_email=customer.email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"role": customer.role or "user", "expires_in_sec": expires_in},
            )
            return LoginResponse(
                two_factor_required=True,
                challenge_token=challenge_token,
                challenge_expires_in=expires_in,
            )

        activate_initial_user_trial_on_first_login(
            db,
            customer,
            previous_last_login_at=original_last_login_at,
        )
        touch_customer_last_login(customer)
        db.commit()
        access_token = create_access_token(data={"sub": customer.email, "sv": customer_session_version(customer)})

        log_security_event(
            event_type="login_success",
            request=request,
            user_email=customer.email,
            customer_id=customer.id,
            tenant_id=customer.tenant_id,
            endpoint=str(request.url.path),
            details={"role": customer.role or "user"},
        )

        return LoginResponse(
            access_token=access_token,
            user={
                "id": customer.id,
                "email": customer.email,
                "name": customer.name,
                "ico": customer.ico,
                "role": customer.role or "user",
                "force_password_change": bool(getattr(customer, "force_password_change", False)),
            },
            password_change_required=bool(getattr(customer, "force_password_change", False)),
        )
    except HTTPException:
        raise
    except Exception as exc:
        import traceback

        error_details = traceback.format_exc()
        print(f"[LOGIN ERROR] {str(exc)}")
        print(f"[LOGIN ERROR] Traceback:\n{error_details}")
        raise HTTPException(
            status_code=500,
            detail=f"Interní chyba serveru: {str(exc)}",
        ) from exc


@router.post("/user/login/2fa", response_model=TokenResponse)
def verify_login_two_factor(
    payload: TwoFactorLoginVerifyRequest,
    request: Request,
    db=Depends(get_db),
):
    challenge = get_2fa_login_challenge(payload.challenge_token)
    if not challenge:
        raise HTTPException(
            status_code=401,
            detail="2FA výzva vypršela nebo je neplatná. Přihlaste se znovu.",
        )

    expires_at = float(challenge.get("expires_at", 0))
    if expires_at <= time.time():
        pop_2fa_login_challenge(payload.challenge_token)
        raise HTTPException(
            status_code=401,
            detail="2FA výzva vypršela. Přihlaste se znovu.",
        )

    attempts = int(challenge.get("attempts", 0))
    if attempts >= 5:
        pop_2fa_login_challenge(payload.challenge_token)
        raise HTTPException(
            status_code=429,
            detail="Překročen počet pokusů o 2FA ověření. Přihlaste se znovu.",
        )

    email = challenge.get("email")
    customer = get_customer_by_email(db, str(email or ""))
    if not customer:
        pop_2fa_login_challenge(payload.challenge_token)
        raise HTTPException(status_code=401, detail="Uživatel pro 2FA ověření nebyl nalezen")
    if customer_is_deleted(customer):
        pop_2fa_login_challenge(payload.challenge_token)
        raise HTTPException(status_code=403, detail="Účet byl deaktivován.")
    if customer_is_disabled(customer):
        pop_2fa_login_challenge(payload.challenge_token)
        raise HTTPException(status_code=403, detail="Účet je dočasně pozastaven.")
    if _login_blocked_pending_email_verification(customer):
        pop_2fa_login_challenge(payload.challenge_token)
        raise HTTPException(status_code=403, detail="Nejdříve ověřte e-mailovou adresu.")

    expected_role = str(challenge.get("expected_role") or "").strip().lower()
    if expected_role in {"user", "service"}:
        from src.modules.vehicle_hub.workspace_entitlements import effective_workspace_kinds

        kinds = effective_workspace_kinds(customer)
        if expected_role == "service" and "service" not in kinds:
            pop_2fa_login_challenge(payload.challenge_token)
            raise HTTPException(status_code=403, detail="Tento účet nemá povolený servisní režim.")
        if expected_role == "user" and "user" not in kinds:
            pop_2fa_login_challenge(payload.challenge_token)
            raise HTTPException(status_code=403, detail="Tento účet nemá povolený uživatelský režim.")

    security_settings = (
        db.query(CustomerSecuritySettings)
        .filter(CustomerSecuritySettings.customer_id == customer.id)
        .first()
    )
    if not security_settings or not security_settings.two_factor_enabled or not security_settings.totp_secret:
        pop_2fa_login_challenge(payload.challenge_token)
        raise HTTPException(status_code=400, detail="2FA není pro tento účet aktivní")

    if not verify_totp(security_settings.totp_secret, payload.code):
        challenge["attempts"] = attempts + 1
        set_2fa_login_challenge(payload.challenge_token, challenge)
        log_security_event(
            event_type="login_2fa_failed",
            request=request,
            user_email=customer.email,
            customer_id=customer.id,
            tenant_id=customer.tenant_id,
            endpoint=str(request.url.path),
            details={"attempts": challenge["attempts"]},
        )
        raise HTTPException(status_code=401, detail="Neplatný 2FA kód")

    original_last_login_at = customer.last_login_at
    pop_2fa_login_challenge(payload.challenge_token)
    activate_initial_user_trial_on_first_login(
        db,
        customer,
        previous_last_login_at=original_last_login_at,
    )
    touch_customer_last_login(customer)
    db.commit()
    access_token = create_access_token(data={"sub": customer.email, "sv": customer_session_version(customer)})

    log_security_event(
        event_type="login_2fa_success",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"role": customer.role or "user"},
    )

    return TokenResponse(
        access_token=access_token,
        user={
            "id": customer.id,
            "email": customer.email,
            "name": customer.name,
            "ico": customer.ico,
            "role": customer.role or "user",
            "force_password_change": bool(getattr(customer, "force_password_change", False)),
        },
    )


@router.post("/user/onboarding/service-invite", response_model=LoginResponse)
def complete_service_invite_onboarding(
    payload: ServiceInviteOnboardingRequest,
    request: Request,
    db=Depends(get_db),
):
    from src.modules.vehicle_hub.routers_v1.service_workspace_customer_centre import consume_service_onboarding_token_core

    customer, access_token = consume_service_onboarding_token_core(
        db,
        raw_token=payload.token,
        new_password=payload.password,
        request=request,
    )
    log_security_event(
        event_type="service_invite_onboarding_completed",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "service_invite"},
    )
    return LoginResponse(
        access_token=access_token,
        user={
            "id": customer.id,
            "email": customer.email,
            "name": customer.name,
            "ico": customer.ico,
            "role": customer.role or "user",
            "force_password_change": False,
        },
        password_change_required=False,
    )


@router.get("/user/ares")
def get_ares_data(
    ico: str,
    current_user: Customer = Depends(get_v1_current_user),
    db=Depends(get_db),
):
    """Deprecated wrapper. Source-of-truth je /api/v1/ares/{ico}."""
    return lookup_ares_v1(ico=ico, current_user=current_user, db=db)


def _send_forgot_password_email_background(target_email: str, reset_url: str) -> None:
    """Odeslání reset e-mailu na pozadí — neblokuje HTTP odpověď (SMTP může trvat desítky sekund)."""
    from src.modules.email_client.service import EmailService

    email_service = EmailService()
    if not email_service.is_configured():
        print("[RESET] background: SMTP není nakonfigurován, e-mail se neodeslal")
        return

    print(f"[RESET] background: odesílám na {target_email} …")
    email_body = f"""
Dobrý den,

obdrželi jsme žádost o obnovení hesla k vašemu účtu v aplikaci {APP_DISPLAY_NAME}.

Pro vytvoření nového hesla klikněte na následující odkaz:
{reset_url}

Tento odkaz je platný 24 hodin.

Pokud jste tento požadavek nevytvořili, ignorujte tento email.

S pozdravem,
{APP_DISPLAY_NAME}
"""
    html_body = render_email_layout(
        title="Obnovení hesla",
        subtitle="Požadavek na změnu hesla k vašemu účtu.",
        intro="Dobrý den,",
        paragraphs=[
            f"obdrželi jsme žádost o obnovení hesla k vašemu účtu v aplikaci {APP_DISPLAY_NAME}.",
            "Odkaz je platný 24 hodin. Pokud jste o změnu hesla nežádali, tento e-mail ignorujte.",
        ],
        panels=[
            render_panel(
                title="Bezpečnostní informace",
                rows=[
                    ("Platnost odkazu", "24 hodin"),
                    ("Účet", target_email),
                ],
                accent="#ef4444",
                tone="#fef2f2",
            )
        ],
        cta_label="Obnovit heslo",
        cta_url=reset_url,
        accent="#f59e0b",
    )
    try:
        email_service.send_simple_email(
            to=target_email,
            subject=f"Obnovení hesla - {APP_DISPLAY_NAME}",
            body=email_body,
            html_body=html_body,
        )
        print(f"[RESET] background OK: odesláno na {target_email}")
    except Exception as email_ex:
        print(f"[RESET] background ERROR: {email_ex}")
        import traceback

        traceback.print_exc()


def _verify_email_audit_details(*, token_hash: str, reason: str | None = None, **extra) -> dict:
    """Audit metadata — nikdy plaintext token, jen hash digest."""
    payload: dict = {"token_hash": token_hash}
    if reason:
        payload["reason"] = reason
    payload.update(extra)
    return payload


@router.post("/user/verify-email")
def verify_email_token(payload: VerifyEmailRequest, request: Request, db=Depends(get_db)):
    """Jednorázové ověření e-mailu — token jen jako vstup, v DB je hash."""
    token = payload.token.strip()
    th = hash_email_verification_token(token)

    log_security_event(
        event_type="email_verification_started",
        request=request,
        endpoint="/user/verify-email",
        details=_verify_email_audit_details(token_hash=th),
    )

    customer = (
        db.query(Customer)
        .filter(
            Customer.email_verification_token_hash == th,
        )
        .first()
    )
    if not customer:
        log_security_event(
            event_type="email_verification_failed",
            request=request,
            endpoint="/user/verify-email",
            details=_verify_email_audit_details(token_hash=th, reason="token_not_found"),
        )
        raise HTTPException(
            status_code=400,
            detail={
                "code": "token_invalid",
                "message": "Neplatný nebo již použitý ověřovací odkaz.",
            },
        )

    if customer.email_verified_at is not None:
        log_security_event(
            event_type="email_verification_success",
            request=request,
            user_email=customer.email,
            customer_id=customer.id,
            tenant_id=customer.tenant_id,
            endpoint="/user/verify-email",
            details=_verify_email_audit_details(
                token_hash=th,
                account_status=customer.account_status,
                already_verified=True,
            ),
        )
        return {
            "verified": True,
            "already_verified": True,
            "message": "Účet je již ověřen. Můžete se přihlásit.",
        }

    if customer.email_verification_expires_at and datetime.utcnow() > customer.email_verification_expires_at:
        log_security_event(
            event_type="email_verification_failed",
            request=request,
            user_email=customer.email,
            customer_id=customer.id,
            tenant_id=customer.tenant_id,
            endpoint="/user/verify-email",
            details=_verify_email_audit_details(token_hash=th, reason="token_expired"),
        )
        raise HTTPException(
            status_code=400,
            detail={
                "code": "token_expired",
                "message": "Ověřovací odkaz vypršel. Požádejte o nový pomocí tlačítka pro opětovné odeslání.",
            },
        )

    customer.email_verified_at = datetime.utcnow()
    customer.account_status = "active"
    customer.email_verification_expires_at = None
    db.commit()

    success_details = _verify_email_audit_details(
        token_hash=th,
        account_status=customer.account_status,
    )
    log_security_event(
        event_type="email_verified",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint="/user/verify-email",
        details=success_details,
    )
    log_security_event(
        event_type="email_verification_success",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint="/user/verify-email",
        details=success_details,
    )
    return {"verified": True, "message": "E-mail byl ověřen. Nyní se můžete přihlásit."}


@router.post("/user/resend-verification-email")
def resend_verification_email(
    payload: ResendVerificationEmailRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db=Depends(get_db),
):
    """Stejná odpověď vždy — bez prozrazení existence účtu."""
    normalized = normalize_email(payload.email)
    client_ip = extract_client_ip(request) or "unknown"
    if not rate_limiter.check_rate_limit(f"resend_verify_ip:{client_ip}", max_calls=30, period=3600):
        raise HTTPException(status_code=429, detail="Příliš mnoho požadavků. Zkuste to později.")
    if not rate_limiter.check_rate_limit(f"resend_verify_mail:{normalized}", max_calls=5, period=900):
        raise HTTPException(status_code=429, detail="Příliš mnoho požadavků pro tento e-mail. Zkuste to později.")

    generic = {"message": "Pokud účet existuje a čeká na ověření e-mailu, byl odeslán nový odkaz."}

    customer = get_customer_by_email(db, normalized)
    if not customer or customer.email_verified_at is not None:
        return generic
    if customer_is_deleted(customer) or customer_is_disabled(customer):
        return generic

    raw = generate_email_verification_secret()
    customer.email_verification_token_hash = hash_email_verification_token(raw)
    customer.email_verification_expires_at = datetime.utcnow() + _EMAIL_VERIFICATION_TTL
    customer.email_verification_sent_at = datetime.utcnow()
    db.commit()

    background_tasks.add_task(
        _send_email_verification_link_email,
        email=customer.email,
        name=customer.name,
        token=raw,
    )
    log_security_event(
        event_type="email_verification_sent",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint="/user/resend-verification-email",
        details={"channel": "email", "resend": True},
    )
    return generic


@router.post("/user/forgot-password")
@router.post("/user/request-password-reset")
def forgot_password(
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    normalized_email = normalize_email(payload.email)
    customer = get_customer_by_email(db, normalized_email)

    if not customer:
        return {"message": "Pokud email existuje, byl odeslán reset odkaz"}

    if customer.email_verified_at is None:
        return {"message": "Pokud email existuje, byl odeslán reset odkaz"}

    target_email = customer.email
    reset_token = secrets.token_urlsafe(32)
    reset_token_expires = datetime.utcnow() + timedelta(hours=24)

    customer.reset_token = reset_token
    customer.reset_token_expires = reset_token_expires
    db.commit()

    reset_url = f"{PUBLIC_API_BASE_URL}/reset-password.html?token={reset_token}"

    from src.modules.email_client.service import EmailService

    email_service = EmailService()
    if email_service.is_configured():
        background_tasks.add_task(_send_forgot_password_email_background, target_email, reset_url)
        return {"message": "Pokud email existuje, byl odeslán reset odkaz", "email_sent": True}

    print("[RESET] WARNING: Email NENI nakonfigurovan (chybi SMTP udaje)")
    print(f"[RESET] Reset URL (pro testování): {reset_url}")
    response = {
        "message": "Email není nakonfigurován. Nastavte SMTP údaje v .env souboru.",
        "email_sent": False,
    }
    if ENVIRONMENT != "production":
        response["reset_url"] = reset_url
    return response


@router.get("/reset-password.html", response_class=HTMLResponse)
def reset_password_page():
    web_path = Path(__file__).parent.parent.parent.parent / "web" / "reset-password.html"
    if web_path.exists():
        return FileResponse(web_path)
    raise HTTPException(status_code=404, detail="Reset password page not found")


@router.get("/web/verify-email.html", response_class=HTMLResponse)
def verify_email_page():
    web_path = Path(__file__).parent.parent.parent.parent / "web" / "verify-email.html"
    if web_path.exists():
        return FileResponse(web_path)
    raise HTTPException(status_code=404, detail="Verify email page not found")


@router.post("/user/reset-password")
def reset_password(payload: ResetPasswordRequest, db=Depends(get_db)):
    if not payload.new_password or len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Heslo musí mít alespoň 6 znaků")

    customer = db.query(Customer).filter(
        Customer.reset_token == payload.token,
        Customer.reset_token_expires > datetime.utcnow(),
    ).first()
    if not customer:
        raise HTTPException(status_code=400, detail="Neplatný nebo expirovaný reset token")

    customer.password_hash = hash_password(payload.new_password)
    customer.reset_token = None
    customer.reset_token_expires = None
    increment_customer_session_version(customer)
    db.commit()

    return {"message": "Heslo bylo úspěšně změněno"}
