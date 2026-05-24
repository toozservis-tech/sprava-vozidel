"""
Stabilní fond účtů pro integrační testy proti lokálnímu API — bez náhodných emailů při každém běhu.

Konfigurace: proměnné CI_* nebo TEST_USER_EMAIL / TEST_USER_PASSWORD zvenku.
Po registraci opakovaně volání /user/register selže → přihlášení (/user/login).
"""

from __future__ import annotations

import os
import re
from datetime import datetime

import requests

CI_DEFAULT_PHONE_E164 = os.getenv("CI_DEFAULT_PHONE_E164", "+420737262711")
CI_DEFAULT_PASSWORD = os.getenv("TEST_USER_PASSWORD", "testpass123")

E2E_USER_EMAIL = os.getenv("E2E_USER_EMAIL", "e2e.user@toozservis.cz").strip().lower()
E2E_USER_PASSWORD = os.getenv("E2E_USER_PASSWORD", os.getenv("TEST_USER_PASSWORD", CI_DEFAULT_PASSWORD))
E2E_SERVICE_EMAIL = os.getenv("E2E_SERVICE_EMAIL", "e2e.service@toozservis.cz").strip().lower()
E2E_SERVICE_PASSWORD = os.getenv("E2E_SERVICE_PASSWORD", os.getenv("TEST_SERVICE_PASSWORD", CI_DEFAULT_PASSWORD))

NON_ALLOWLISTED_TEST_ACCOUNT_MESSAGE = (
    "Refusing to create non-allowlisted test account. "
    "Use fixed E2E_USER_EMAIL or E2E_SERVICE_EMAIL."
)

_RANDOM_TEST_EMAIL_PATTERNS = (
    re.compile(r"\be2e[.+_-].*(timestamp|pw-|[0-9]{8,}|[0-9a-f]{10,})", re.I),
    re.compile(r"\btest\+", re.I),
    re.compile(r"\bpw-", re.I),
    re.compile(r"[0-9a-f]{12,}@", re.I),
    re.compile(r"\d{10,}@"),
)


def _normalize_email(email: str | None) -> str:
    return str(email or "").strip().lower()


def fixed_test_account_emails() -> set[str]:
    return {_normalize_email(E2E_USER_EMAIL), _normalize_email(E2E_SERVICE_EMAIL)}


def is_isolated_test_database_url(database_url: str | None = None) -> bool:
    """True jen pro lokální dočasnou/testovací DB, ne pro sdílenou staging/runtime DB."""
    if database_url is None:
        try:
            from src.core.config import DATABASE_URL

            database_url = DATABASE_URL
        except Exception:
            database_url = os.getenv("DATABASE_URL", "")
    value = str(database_url or "").lower()
    if not value:
        return False
    return (
        ":memory:" in value
        or "test_vehicles" in value
        or "pytest" in value
        or "/tmp/" in value
        or "tmp/" in value
    )


def is_runtime_like_database_url(database_url: str | None = None) -> bool:
    return not is_isolated_test_database_url(database_url)


def looks_like_random_test_email(email: str | None) -> bool:
    normalized = _normalize_email(email)
    return any(pattern.search(normalized) for pattern in _RANDOM_TEST_EMAIL_PATTERNS)


def assert_allowed_test_email(email: str, *, database_url: str | None = None) -> str:
    """Guard proti plnění staging/runtime DB náhodnými testovacími účty."""
    normalized = _normalize_email(email)
    if not normalized:
        raise AssertionError(NON_ALLOWLISTED_TEST_ACCOUNT_MESSAGE)
    if is_isolated_test_database_url(database_url):
        return normalized
    if normalized not in fixed_test_account_emails():
        raise AssertionError(NON_ALLOWLISTED_TEST_ACCOUNT_MESSAGE)
    if looks_like_random_test_email(normalized):
        raise AssertionError(NON_ALLOWLISTED_TEST_ACCOUNT_MESSAGE)
    return normalized


def _ensure_license_row(db, tenant_id: int, *, plan: str = "free") -> None:
    from sqlalchemy import text

    exists = db.execute(
        text("SELECT id FROM licenses WHERE tenant_id = :tenant_id LIMIT 1"),
        {"tenant_id": int(tenant_id)},
    ).first()
    if exists:
        db.execute(
            text(
                """
                UPDATE licenses
                SET plan = :plan,
                    status = 'active',
                    vehicles_limit = CASE WHEN :plan = 'premium' THEN 0 ELSE vehicles_limit END,
                    updated_at = :now
                WHERE tenant_id = :tenant_id
                """
            ),
            {"tenant_id": int(tenant_id), "plan": plan, "now": datetime.utcnow()},
        )
        return
    db.execute(
        text(
            """
            INSERT INTO licenses (
                tenant_id, plan, status, vehicles_limit, valid_from,
                vin_decode_enabled, ares_enabled, reminders_enabled,
                created_at, updated_at
            )
            VALUES (
                :tenant_id, :plan, 'active', :vehicles_limit, :now,
                :vin_decode, 1, 1,
                :now, :now
            )
            """
        ),
        {
            "tenant_id": int(tenant_id),
            "plan": plan,
            "vehicles_limit": 0 if plan in {"premium", "service_full"} else 1,
            "vin_decode": 1 if plan in {"premium", "service_full"} else 0,
            "now": datetime.utcnow(),
        },
    )


def _ensure_fixed_customer(db, *, email: str, password: str, role: str, name: str):
    from sqlalchemy import func

    from src.core.security import hash_password
    from src.modules.vehicle_hub.models import Customer, Tenant
    from src.modules.vehicle_hub.tenant_provisioning import create_dedicated_tenant
    from src.modules.vehicle_hub.workspace_routing import ensure_tenant_workspace_slug

    normalized = assert_allowed_test_email(email)
    route_kind = "service" if role == "service" else "user"
    customer = db.query(Customer).filter(func.lower(Customer.email) == normalized).first()
    if customer is None:
        tenant = create_dedicated_tenant(
            db,
            owner_email=normalized,
            owner_name=name,
            workspace_route_kind=route_kind,
        )
        customer = Customer(
            tenant_id=tenant.id,
            email=normalized,
            email_normalized=normalized,
            password_hash=hash_password(password),
            name=name,
            role=role,
            account_status="active",
            email_verified_at=datetime.utcnow(),
            email_verification_sent_at=datetime.utcnow(),
            registration_ip="127.0.0.1",
            registration_user_agent="pytest-fixed-account",
            is_disabled=False,
            is_deleted=False,
        )
        db.add(customer)
        db.flush()
    else:
        tenant = db.query(Tenant).filter(Tenant.id == int(customer.tenant_id)).first()
        if tenant is None:
            tenant = create_dedicated_tenant(
                db,
                owner_email=normalized,
                owner_name=name,
                workspace_route_kind=route_kind,
            )
            customer.tenant_id = tenant.id
        customer.email = normalized
        customer.email_normalized = normalized
        customer.password_hash = hash_password(password)
        customer.name = customer.name or name
        customer.role = role
        customer.account_status = "active"
        customer.email_verified_at = customer.email_verified_at or datetime.utcnow()
        customer.email_verification_token_hash = None
        customer.email_verification_expires_at = None
        customer.email_verification_sent_at = customer.email_verification_sent_at or datetime.utcnow()
        customer.is_disabled = False
        customer.is_deleted = False
        customer.deleted_at = None
        customer.disabled_at = None
        customer.force_password_change = False
        db.add(customer)
        db.flush()
    if tenant is not None:
        ensure_tenant_workspace_slug(db, tenant, seed_label=name or normalized, route_kind=route_kind)
    _ensure_license_row(db, int(customer.tenant_id), plan="service_full" if role == "service" else "premium")
    db.commit()
    db.refresh(customer)
    return customer


def reset_fixed_test_user_state(db):
    return _ensure_fixed_customer(
        db,
        email=E2E_USER_EMAIL,
        password=E2E_USER_PASSWORD,
        role="user",
        name="E2E Fixed User",
    )


def ensure_fixed_test_user(db=None):
    if db is not None:
        return reset_fixed_test_user_state(db)
    from src.modules.vehicle_hub.database import SessionLocal

    session = SessionLocal()
    try:
        return reset_fixed_test_user_state(session)
    finally:
        session.close()


def reset_fixed_test_service_state(db):
    return _ensure_fixed_customer(
        db,
        email=E2E_SERVICE_EMAIL,
        password=E2E_SERVICE_PASSWORD,
        role="service",
        name="E2E Fixed Service",
    )


def ensure_fixed_test_service(db=None):
    if db is not None:
        return reset_fixed_test_service_state(db)
    from src.modules.vehicle_hub.database import SessionLocal

    session = SessionLocal()
    try:
        return reset_fixed_test_service_state(session)
    finally:
        session.close()


def _verify_customer_email_in_db(email: str) -> None:
    """Pro integrační testy: označí e-mail jako ověřený (stejná DB jako API)."""
    from datetime import datetime

    from sqlalchemy import func

    from src.modules.vehicle_hub.database import SessionLocal
    from src.modules.vehicle_hub.models import Customer

    db = SessionLocal()
    try:
        c = db.query(Customer).filter(func.lower(Customer.email) == str(email).strip().lower()).first()
        if not c:
            return
        c.email_verified_at = datetime.utcnow()
        c.account_status = "active"
        c.email_verification_token_hash = None
        c.email_verification_expires_at = None
        db.commit()
    finally:
        db.close()


def plant_email_verification_token_for_test(email: str, raw_token: str | None = None) -> str:
    """Nastaví známý ověřovací token pro integrační testy (hash v DB, ne plaintext)."""
    from datetime import datetime, timedelta

    from sqlalchemy import func

    from src.modules.vehicle_hub.database import SessionLocal
    from src.modules.vehicle_hub.models import Customer
    from src.modules.vehicle_hub.registration_security import (
        generate_email_verification_secret,
        hash_email_verification_token,
    )

    raw = raw_token or generate_email_verification_secret()
    db = SessionLocal()
    try:
        c = db.query(Customer).filter(func.lower(Customer.email) == str(email).strip().lower()).first()
        if not c:
            raise RuntimeError(f"Customer not found for email verification test: {email}")
        c.email_verified_at = None
        c.account_status = "pending_email_verification"
        c.email_verification_token_hash = hash_email_verification_token(raw)
        c.email_verification_expires_at = datetime.utcnow() + timedelta(minutes=30)
        db.commit()
    finally:
        db.close()
    return raw


def ensure_user_token(
    api_url: str,
    email: str,
    *,
    password: str | None = None,
    name: str = "CI user",
    phone: str | None = None,
) -> tuple[str, int]:
    """Vrátí token pro allowlistovaný fixed účet bez zakládání náhodných uživatelů."""
    requested_email = _normalize_email(email)
    if requested_email in fixed_test_account_emails():
        normalized_email = assert_allowed_test_email(requested_email)
    else:
        hint = f"{requested_email} {name or ''}".lower()
        normalized_email = E2E_SERVICE_EMAIL if ("service" in hint or "svc" in hint or "servis" in hint) else E2E_USER_EMAIL
    pwd = password or (E2E_SERVICE_PASSWORD if normalized_email == E2E_SERVICE_EMAIL else E2E_USER_PASSWORD)
    if normalized_email == E2E_SERVICE_EMAIL:
        ensure_fixed_test_service()
    else:
        ensure_fixed_test_user()

    login = requests.post(
        f"{api_url}/user/login",
        json={"email": normalized_email, "password": pwd},
        timeout=15,
    )
    if login.status_code == 429:
        import pytest

        pytest.skip("Runtime login rate limit is already exhausted for the fixed E2E account.")
    if login.status_code == 403:
        try:
            detail = str(login.json().get("detail") or "")
        except Exception:
            detail = ""
        if "ověřte e-mailovou adresu" in detail.lower():
            _verify_customer_email_in_db(normalized_email)
            login = requests.post(
                f"{api_url}/user/login",
                json={"email": normalized_email, "password": pwd},
                timeout=15,
            )
    assert login.status_code == 200, (
        f"fixed account login failed {login.status_code} ({login.text!r})"
    )
    data = login.json()
    uid = data.get("user", {}).get("id")
    assert uid is not None, login.text
    return data["access_token"], int(uid)


TEST_USER_EMAIL_DEFAULT = os.getenv("TEST_USER_EMAIL", E2E_USER_EMAIL)

# Lifecycle / převody (dva účty)
CI_API_SELLER = os.getenv("CI_API_SELLER", "ci.api.seller@example.com")
CI_API_BUYER = os.getenv("CI_API_BUYER", "ci.api.buyer@example.com")
CI_API_OWNER_INTAKE = os.getenv("CI_API_OWNER_INTAKE", "ci.api.owner-intake@example.com")
CI_API_SERVICE_INTAKE = os.getenv("CI_API_SERVICE_INTAKE", "ci.api.service-intake@example.com")

# Admin / rbac
CI_API_NONADMIN = os.getenv("CI_API_NONADMIN", "ci.api.non-admin@example.com")

# Servisní workspace (pevně oddělené dvojice, aby se scénáře navzájem nekazily)
CI_WS_SERVICE_LINK = os.getenv("CI_WS_SERVICE_LINK", "ci.ws.service-link@example.com")
CI_WS_CUSTOMER_LINK = os.getenv("CI_WS_CUSTOMER_LINK", "ci.ws.customer-link@example.com")
CI_WS_SERVICE_INVITE = os.getenv("CI_WS_SERVICE_INVITE", "ci.ws.service-invite@example.com")
CI_WS_INVITED = os.getenv("CI_WS_INVITED", "ci.ws.invited@example.com")
CI_WS_SERVICE_SEARCH = os.getenv("CI_WS_SERVICE_SEARCH", "ci.ws.service-search@example.com")
CI_WS_CUSTOMER_SEARCH = os.getenv("CI_WS_CUSTOMER_SEARCH", "ci.ws.customer-search@example.com")
CI_WS_SERVICE_DETAIL = os.getenv("CI_WS_SERVICE_DETAIL", "ci.ws.service-detail@example.com")
CI_WS_CUSTOMER_DETAIL = os.getenv("CI_WS_CUSTOMER_DETAIL", "ci.ws.customer-detail@example.com")
CI_WS_SERVICE_PENDING = os.getenv("CI_WS_SERVICE_PENDING", "ci.ws.service-pending@example.com")
CI_WS_INVITE_PENDING = os.getenv("CI_WS_INVITE_PENDING", "ci.ws.invite-pending@example.com")

# Přístupové žádosti servisu
CI_SAR_SERVICE = os.getenv("CI_SAR_SERVICE", "ci.sar.service@example.com")
CI_SAR_USER = os.getenv("CI_SAR_USER", "ci.sar.user@example.com")
CI_SAR_LOOKUP_SERVICE = os.getenv("CI_SAR_LOOKUP_SERVICE", "ci.sar.lookup-service@example.com")
CI_SAR_OWNER_A = os.getenv("CI_SAR_OWNER_A", "ci.sar.owner-a@example.com")
CI_SAR_OWNER_B = os.getenv("CI_SAR_OWNER_B", "ci.sar.owner-b@example.com")

# Auth scénáře
CI_AUTH_SHARED = os.getenv("CI_AUTH_SHARED", "ci.auth.shared@example.com")
CI_CASE_USER = os.getenv("CI_CASE_USER", "CaseUser.ci@Example.com")
CI_CASE_NORM = os.getenv("CI_CASE_NORM", "Ci.case.norm@Example.com")
CI_AUTH_DELETE_FLOW = os.getenv("CI_AUTH_DELETE_FLOW", "ci.auth.delete-flow@example.com")
CI_AUTH_PASSRESET = os.getenv("CI_AUTH_PASSRESET", "ci.auth.passreset@example.com")
CI_AUTH_2FA = os.getenv("CI_AUTH_2FA", "ci.auth.2fa@example.com")
CI_AUTH_DUP_EMAIL = os.getenv("CI_AUTH_DUP_EMAIL", "ci.auth.duplicate@example.com")
CI_AUTH_REGISTER_OK = os.getenv("CI_AUTH_REGISTER_OK", "ci.auth.register-success@example.com")

# Servisní žádosti registrace — pevný IČO pro test blokace duplicitního IČO
CI_SVC_REQ_A = os.getenv("CI_SVC_REQ_A", "ci.svc.req-a@example.com")
CI_SVC_REQ_B = os.getenv("CI_SVC_REQ_B", "ci.svc.req-b@example.com")
CI_SVC_REQ_DUP_EMAIL = os.getenv("CI_SVC_REQ_DUP_EMAIL", "ci.svc.req-dup-email@example.com")
CI_SVC_REQ_STANDALONE = os.getenv("CI_SVC_REQ_STANDALONE", "ci.svc.req-standalone@example.com")
# Platná IČO ověřená vůči ARES REST; každé scénář používá jiné IČO (kolize v DB = 400).
# IČO jen pro scénář „stejný e-mail dvakrát“ (nesmí kolidovat s jinými servisními žádostmi v DB).
CI_SVC_REQ_ICO_DUP_PENDING = os.getenv("CI_SVC_REQ_ICO_DUP_PENDING", "25063677")
CI_FIXED_ICO_BLOCKED_PAIR = os.getenv("CI_FIXED_ICO_BLOCKED_PAIR", "04997476")
CI_SVC_REQ_ICO_PRIMARY = os.getenv("CI_SVC_REQ_ICO_PRIMARY", "24729035")

CI_VIN_DECODE = os.getenv("CI_VIN_DECODE", "ci.vin.decode@example.com")

# Nikdy neregistrovaný — login probe 401 / forgot 200
CI_ABSENT_MAILBOX = os.getenv("CI_ABSENT_MAILBOX", "zzz.ci.nonexistent-login@example.com")

# Antifraud registrace (jeden účet na scénář)
CI_AF_PHONE_BAD = os.getenv("CI_AF_PHONE_BAD", "ci.af.phone-bad@example.com")
CI_AF_VERIFY_FLOW = os.getenv("CI_AF_VERIFY_FLOW", "ci.af.verify@example.com")
CI_AF_EXPIRED = os.getenv("CI_AF_EXPIRED", "ci.af.expired@example.com")
CI_AF_RESEND = os.getenv("CI_AF_RESEND", "ci.af.resend@example.com")
CI_AF_TOKENSECRET = os.getenv("CI_AF_TOKENSECRET", "ci.af.tokensecret@example.com")
CI_AF_PLAIN_VERIFY_TOKEN = os.getenv("CI_AF_PLAIN_VERIFY_TOKEN", "ci-antifraud-plain-verify-token-001")


def release_customer_emails_for_re_register(emails: list[str]) -> None:
    """
    Uvolní unikátní email: existující řádek customers označí jako smazaný a přejmenuje email,
    aby šel znovu použít POST /user/register se stejnou adresou.

    Čisté SQL přes DATABASE_URL (bez načtení ORM řádku kvůli driftu schématu).
    """
    if not emails:
        return

    from sqlalchemy import create_engine, text

    from src.core.config import DATABASE_URL

    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        for raw in emails:
            e = str(raw or "").strip().lower()
            if not e:
                continue
            row = conn.execute(text("SELECT id FROM customers WHERE lower(email) = :em"), {"em": e}).first()
            if not row:
                continue
            cid = int(row[0])
            conn.execute(
                text(
                    """
                    UPDATE customers
                    SET email = :ne,
                        is_deleted = 1,
                        is_disabled = 1
                    WHERE id = :id
                    """
                ),
                {"ne": f"released-ci-{cid}@ci-released.invalid", "id": cid},
            )


def clear_customer_totp_in_db(email: str) -> None:
    """Zruší zapnutý TOTP před integračním 2FA testem (musí používat tutéž runtime DB jako API)."""
    from sqlalchemy import func

    from src.modules.vehicle_hub.database import SessionLocal
    from src.modules.vehicle_hub.models import Customer, CustomerSecuritySettings

    db = SessionLocal()
    try:
        c = db.query(Customer).filter(func.lower(Customer.email) == str(email).lower()).first()
        if not c:
            return
        s = db.query(CustomerSecuritySettings).filter(CustomerSecuritySettings.customer_id == c.id).first()
        if not s:
            return
        s.two_factor_enabled = False
        s.totp_secret = None
        s.totp_enabled_at = None
        db.commit()
    finally:
        db.close()


def clear_service_registration_requests_emails(emails: list[str]) -> None:
    """Smaže záznamy service_registration_requests pro dané emaily (ICO / duplicitní scénáře)."""
    if not emails:
        return

    from sqlalchemy import func

    from src.modules.vehicle_hub.database import SessionLocal
    from src.modules.vehicle_hub.models import ServiceRegistrationRequest

    targets = [e.strip().lower() for e in emails if e.strip()]
    if not targets:
        return

    db = SessionLocal()
    try:
        db.query(ServiceRegistrationRequest).filter(
            func.lower(ServiceRegistrationRequest.email).in_(targets)
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
