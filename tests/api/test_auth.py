"""
Testy pro autentizaci
"""
import base64
import hashlib
import hmac
import io
import struct
import time
import zipfile
from uuid import uuid4

import pytest
import requests

from tests.api.integration_accounts import (
    CI_ABSENT_MAILBOX,
    CI_AUTH_2FA,
    CI_AUTH_DELETE_FLOW,
    CI_AUTH_DUP_EMAIL,
    CI_AUTH_PASSRESET,
    CI_AUTH_REGISTER_OK,
    CI_AUTH_SHARED,
    CI_CASE_NORM,
    CI_CASE_USER,
    CI_DEFAULT_PASSWORD,
    CI_FIXED_ICO_BLOCKED_PAIR,
    CI_SVC_REQ_A,
    CI_SVC_REQ_B,
    CI_SVC_REQ_DUP_EMAIL,
    CI_SVC_REQ_ICO_DUP_PENDING,
    CI_SVC_REQ_ICO_PRIMARY,
    CI_SVC_REQ_STANDALONE,
    E2E_USER_EMAIL,
    E2E_USER_PASSWORD,
    clear_customer_totp_in_db,
    clear_service_registration_requests_emails,
    ensure_fixed_test_user,
    ensure_user_token,
    fixed_test_account_emails,
)


def _calculate_totp(secret: str, unix_time: int | None = None) -> str:
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    key = base64.b32decode(normalized + padding, casefold=True)
    counter = int((unix_time or int(time.time())) // 30)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{binary % 1000000:06d}"


def _register_user(api_url: str, email: str | None = None, password: str | None = None):
    """Zajistí účet (register nebo login) a vrátí normalizovaný email + token."""
    from datetime import datetime

    from sqlalchemy import func, text

    from src.core.security import hash_password
    from src.modules.vehicle_hub.database import SessionLocal
    from src.modules.vehicle_hub.models import Customer
    from src.modules.vehicle_hub.tenant_provisioning import create_dedicated_tenant

    pwd = password if password is not None else E2E_USER_PASSWORD
    raw = email or E2E_USER_EMAIL
    normalized = raw.strip().lower()
    if normalized not in fixed_test_account_emails():
        normalized = E2E_USER_EMAIL
        pwd = E2E_USER_PASSWORD
    db = SessionLocal()
    try:
        customer = db.query(Customer).filter(func.lower(Customer.email) == normalized).first()
        if customer is None:
            tenant = create_dedicated_tenant(db, owner_email=normalized, owner_name="Auth CI")
            customer = Customer(
                tenant_id=tenant.id,
                email=normalized,
                password_hash=hash_password(pwd),
                name="Auth CI",
                role="user",
                account_status="active",
                email_verified_at=datetime.utcnow(),
                email_verification_sent_at=datetime.utcnow(),
                registration_ip="127.0.0.1",
                registration_user_agent="pytest",
            )
            db.add(customer)
            db.flush()
            exists = db.execute(
                text("SELECT id FROM licenses WHERE tenant_id = :tenant_id LIMIT 1"),
                {"tenant_id": int(tenant.id)},
            ).first()
            if not exists:
                db.execute(
                    text(
                        """
                        INSERT INTO licenses (
                            tenant_id, plan, status, vehicles_limit, valid_from,
                            vin_decode_enabled, ares_enabled, reminders_enabled,
                            created_at, updated_at
                        )
                        VALUES (
                            :tenant_id, 'free', 'active', 1, :now,
                            0, 1, 1,
                            :now, :now
                        )
                        """
                    ),
                    {"tenant_id": int(tenant.id), "now": datetime.utcnow()},
                )
            db.commit()
            db.refresh(customer)
        elif customer.email_verified_at is None:
            customer.email_verified_at = datetime.utcnow()
            customer.account_status = "active"
            db.commit()
    finally:
        db.close()

    login = requests.post(
        f"{api_url}/user/login",
        json={"email": normalized, "password": pwd},
        timeout=15,
    )
    if login.status_code == 429:
        pytest.skip("Runtime login rate limit is already exhausted for the fixed E2E account.")
    assert login.status_code == 200, login.text
    data = login.json()
    return normalized, pwd, data["access_token"], {}


def test_register_success(api_url):
    """Účet lze jednou zaregistrovat; nová pravidla vyžadují ověření e-mailu před loginem."""
    from tests.api.integration_accounts import _verify_customer_email_in_db

    try:
        requests.get(f"{api_url}/health", timeout=2)
    except Exception:
        pytest.skip("API server nedostupný")

    email = E2E_USER_EMAIL
    password = E2E_USER_PASSWORD
    ensure_fixed_test_user()

    response = requests.post(
        f"{api_url}/user/register",
        json={
            "email": email,
            "password": password,
            "name": "Test User",
            "phone": "+420737262711",
        },
        timeout=5,
    )

    if response.status_code == 200:
        data = response.json()
        if data.get("verification_required"):
            assert not data.get("access_token")
            assert data.get("user", {}).get("email") == email.lower()
            blocked = requests.post(
                f"{api_url}/user/login",
                json={"email": email, "password": password},
                timeout=5,
            )
            assert blocked.status_code == 403
            assert "ověřte e-mail" in (blocked.json().get("detail") or "").lower()
            _verify_customer_email_in_db(email)
            ok_login = requests.post(
                f"{api_url}/user/login",
                json={"email": email, "password": password},
                timeout=5,
            )
            assert ok_login.status_code == 200
            assert ok_login.json().get("access_token")
            return
        assert "access_token" in data
        assert data.get("token_type") == "bearer"
        assert "user" in data
        return

    assert response.status_code in {400, 409, 429}
    if response.status_code == 429:
        pytest.skip("Runtime register rate limit is already exhausted; duplicate behavior is covered by TestClient.")
    login_resp = requests.post(
        f"{api_url}/user/login",
        json={"email": email, "password": password},
        timeout=5,
    )
    if login_resp.status_code == 429:
        pytest.skip("Runtime login rate limit is already exhausted for the fixed E2E account.")
    if login_resp.status_code == 403:
        try:
            _d = str(login_resp.json().get("detail") or "")
        except Exception:
            _d = ""
        if "ověřte e-mailovou adresu" in _d.lower():
            _verify_customer_email_in_db(email)
            login_resp = requests.post(
                f"{api_url}/user/login",
                json={"email": email, "password": password},
                timeout=5,
            )
    assert login_resp.status_code == 200, login_resp.text
    body = login_resp.json()
    assert body.get("access_token")


def test_register_duplicate_email(api_url):
    """Test registrace s duplicitním emailem"""
    from fastapi.testclient import TestClient

    from src.server.bootstrap import create_app

    duplicate_email = E2E_USER_EMAIL
    password = E2E_USER_PASSWORD
    ensure_fixed_test_user()

    client = TestClient(create_app())
    response = client.post(
        "/user/register",
        json={
            "email": duplicate_email.upper(),
            "password": password,
            "name": "Test User Duplicate",
            "phone": "+420737262711",
        },
    )

    assert response.status_code in {400, 409}


def test_login_success(api_url):
    """Test úspěšného přihlášení"""
    email, password, _, _ = _register_user(api_url)
    
    response = requests.post(
        f"{api_url}/user/login",
        json={
            "email": email,
            "password": password
        },
        timeout=5
    )
    if response.status_code == 429:
        pytest.skip("Runtime login rate limit is already exhausted for the fixed E2E account.")
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data.get("token_type") == "bearer"


def test_login_wrong_password(api_url):
    """Test přihlášení se špatným heslem"""
    email, _, _, _ = _register_user(api_url)

    response = requests.post(
        f"{api_url}/user/login",
        json={
            "email": email,
            "password": "wrongpassword"
        },
        timeout=5
    )
    
    assert response.status_code == 401


def test_login_nonexistent_user(api_url):
    """Test přihlášení neexistujícího uživatele"""
    response = requests.post(
        f"{api_url}/user/login",
        json={
            "email": CI_ABSENT_MAILBOX,
            "password": "password123"
        },
        timeout=5
    )
    
    assert response.status_code == 401


def test_login_case_insensitive_email(api_url):
    """Přihlášení by mělo ignorovat velikost písmen v emailu"""
    mixed_case_email = E2E_USER_EMAIL
    _, password, _, _ = _register_user(api_url, email=mixed_case_email)

    response = requests.post(
        f"{api_url}/user/login",
        json={
            "email": mixed_case_email.upper(),
            "password": password,
        },
        timeout=5,
    )

    if response.status_code == 429:
        pytest.skip("Runtime login rate limit is already exhausted for the fixed E2E account.")
    assert response.status_code == 200


def test_register_stores_normalized_email(api_url):
    """Registrace musí uložit normalizovaný email a blokovat duplicitu"""
    from tests.api.integration_accounts import _verify_customer_email_in_db

    mixed_case_email = E2E_USER_EMAIL
    normalized_email = mixed_case_email.lower()
    password = E2E_USER_PASSWORD
    ensure_fixed_test_user()

    probe = requests.post(
        f"{api_url}/user/login",
        json={"email": normalized_email, "password": password},
        timeout=5,
    )
    if probe.status_code != 200:
        register_response = requests.post(
            f"{api_url}/user/register",
            json={
                "email": mixed_case_email,
                "password": password,
                "name": "Case User",
                "phone": "+420737262711",
            },
            timeout=5,
        )
        if register_response.status_code == 400 and "již existuje" in register_response.text.lower():
            _verify_customer_email_in_db(normalized_email)
            probe2 = requests.post(
                f"{api_url}/user/login",
                json={"email": normalized_email, "password": password},
                timeout=5,
            )
            if probe2.status_code == 429:
                pytest.skip("Runtime login rate limit is already exhausted for the fixed E2E account.")
            assert probe2.status_code == 200, probe2.text
            assert probe2.json().get("user", {}).get("email") == normalized_email
        else:
            if register_response.status_code == 429:
                pytest.skip("Runtime register rate limit is already exhausted; duplicate behavior is covered by fixed policy tests.")
            assert register_response.status_code == 200, register_response.text
            register_data = register_response.json()
            assert register_data["user"]["email"] == normalized_email
    else:
        headers = {"Authorization": f"Bearer {probe.json()['access_token']}"}
        me = requests.get(f"{api_url}/user/me", headers=headers, timeout=5)
        assert me.status_code == 200
        assert me.json()["email"] == normalized_email

    duplicate_response = requests.post(
        f"{api_url}/user/register",
        json={
            "email": normalized_email,
            "password": password,
            "name": "Case User Duplicate",
            "phone": "+420737262711",
        },
        timeout=5,
    )
    assert duplicate_response.status_code in {400, 409, 429}
    if duplicate_response.status_code == 429:
        pytest.skip("Runtime register rate limit is already exhausted; duplicate behavior is covered by fixed policy tests.")


def test_get_current_user(api_url):
    """Test získání aktuálního uživatele"""
    email, _, token, _ = _register_user(api_url)
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(
        f"{api_url}/user/me",
        headers=headers,
        timeout=5
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "email" in data
    assert data["email"] == email


def test_get_current_user_unauthorized(api_url):
    """Test získání uživatele bez autentizace"""
    response = requests.get(
        f"{api_url}/user/me",
        timeout=5
    )
    
    assert response.status_code == 401 or response.status_code == 403


def test_account_export_and_delete_flow(api_url):
    """Uživatel musí umět stáhnout export a následně trvale smazat účet."""
    pytest.skip("Destruktivní delete-flow nesmí běžet proti fixed staging/runtime účtu bez schválení.")
    email, password, token, _ = _register_user(
        api_url, email=CI_AUTH_DELETE_FLOW, password="DeleteMe123"
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Přidat minimálně jedno vozidlo, aby export obsahoval i PDF report.
    create_vehicle_response = requests.post(
        f"{api_url}/api/v1/vehicles",
        json={
            "nickname": "Delete Flow Car",
            "plate": f"DEL{uuid4().hex[:4].upper()}",
            "brand": "Skoda",
            "model": "Octavia",
            "year": 2020,
            "stk_valid_until": "2030-12-31",
        },
        headers=headers,
        timeout=10,
    )
    assert create_vehicle_response.status_code == 200

    export_response = requests.get(
        f"{api_url}/user/me/export",
        headers=headers,
        timeout=30,
    )
    assert export_response.status_code == 200
    assert "application/zip" in (export_response.headers.get("content-type", "")).lower()

    zip_buffer = io.BytesIO(export_response.content)
    with zipfile.ZipFile(zip_buffer, "r") as archive:
        names = set(archive.namelist())
        assert "data/kompletni_export.json" in names
        assert "data/ucet_prehled.json" in names
        assert any(name.startswith("vozidla_pdf/") and name.endswith(".pdf") for name in names)

    # Bez potvrzení exportu musí mazání selhat.
    no_export_confirmation_response = requests.delete(
        f"{api_url}/user/me",
        json={
            "current_password": password,
            "confirmation_text": "SMAZAT UCET",
            "export_downloaded": False,
        },
        headers=headers,
        timeout=10,
    )
    assert no_export_confirmation_response.status_code == 400

    # Správné potvrzení + heslo => účet se smaže.
    delete_response = requests.delete(
        f"{api_url}/user/me",
        json={
            "current_password": password,
            "confirmation_text": "SMAZAT UCET",
            "export_downloaded": True,
        },
        headers=headers,
        timeout=20,
    )
    assert delete_response.status_code == 200
    delete_payload = delete_response.json()
    assert delete_payload.get("deleted") is True

    # Po smazání už se nelze přihlásit.
    login_response = requests.post(
        f"{api_url}/user/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    assert login_response.status_code == 401


def test_forgot_password_endpoint_returns_200(api_url):
    """Forgot password endpoint musí vracet 200 i pro neexistující email."""
    response = requests.post(
        f"{api_url}/user/forgot-password",
        json={"email": CI_ABSENT_MAILBOX},
        timeout=5,
    )
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


def test_request_password_reset_legacy_alias_returns_200(api_url):
    """Legacy alias endpoint musí fungovat kvůli zpětné kompatibilitě klientů."""
    response = requests.post(
        f"{api_url}/user/request-password-reset",
        json={"email": CI_ABSENT_MAILBOX},
        timeout=5,
    )
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


def test_password_reset_invalidates_previous_jwt(api_url):
    """Po resetu hesla musí starý Bearer token vracet 401 (session_version bump)."""
    import pytest
    from urllib.parse import parse_qs, urlparse

    try:
        requests.get(f"{api_url}/health", timeout=2)
    except Exception:
        pytest.skip("API server nedostupný (spusťte backend pro integrační test).")

    email = CI_AUTH_PASSRESET
    pwd_default = CI_DEFAULT_PASSWORD
    pwd_new = "newpass999"

    recovered = requests.post(
        f"{api_url}/user/login",
        json={"email": email, "password": pwd_new},
        timeout=10,
    )
    if recovered.status_code == 200:
        rtok = recovered.json()["access_token"]
        ch = requests.put(
            f"{api_url}/user/change-password",
            headers={"Authorization": f"Bearer {rtok}"},
            json={"current_password": pwd_new, "new_password": pwd_default},
            timeout=10,
        )
        assert ch.status_code == 200, ch.text

    email, password, old_token, _ = _register_user(api_url, email=email, password=pwd_default)
    forgot = requests.post(f"{api_url}/user/forgot-password", json={"email": email}, timeout=10)
    assert forgot.status_code == 200
    payload = forgot.json()
    reset_url = str(payload.get("reset_url") or "").strip()
    if not reset_url:
        pytest.skip("reset_url není v odpovědi (typicky produkce se SMTP bez dev leaku)")
    token = (parse_qs(urlparse(reset_url).query).get("token") or [None])[0]
    assert token
    reset = requests.post(
        f"{api_url}/user/reset-password",
        json={"token": token, "new_password": pwd_new},
        timeout=10,
    )
    assert reset.status_code == 200

    me = requests.get(
        f"{api_url}/user/me",
        headers={"Authorization": f"Bearer {old_token}"},
        timeout=10,
    )
    assert me.status_code == 401

    login = requests.post(
        f"{api_url}/user/login",
        json={"email": email, "password": pwd_new},
        timeout=10,
    )
    assert login.status_code == 200
    assert login.json().get("access_token")


def test_login_role_mismatch_returns_403(api_url):
    """Přihlášení uživatele v režimu service musí vrátit 403."""
    email, password, _, _ = _register_user(api_url, email=E2E_USER_EMAIL)

    response = requests.post(
        f"{api_url}/user/login",
        json={
            "email": email,
            "password": password,
            "expected_role": "service",
        },
        timeout=5,
    )

    assert response.status_code == 403


def test_login_with_two_factor_flow(api_url):
    """Kompletní 2FA flow: setup -> enable -> login challenge -> verify."""
    email_for_2fa = E2E_USER_EMAIL
    clear_customer_totp_in_db(email_for_2fa)
    email, password, token, _ = _register_user(api_url, email=email_for_2fa)
    headers = {"Authorization": f"Bearer {token}"}

    setup_response = requests.post(
        f"{api_url}/user/security/totp/setup",
        headers=headers,
        timeout=5,
    )
    assert setup_response.status_code == 200
    setup_data = setup_response.json()
    secret = setup_data.get("secret")
    assert secret

    enable_code = _calculate_totp(secret)
    enable_response = requests.post(
        f"{api_url}/user/security/totp/enable",
        headers=headers,
        json={"code": enable_code},
        timeout=5,
    )
    assert enable_response.status_code == 200
    assert enable_response.json().get("two_factor_enabled") is True

    login_response = requests.post(
        f"{api_url}/user/login",
        json={"email": email, "password": password},
        timeout=5,
    )
    assert login_response.status_code == 200
    login_data = login_response.json()
    assert login_data.get("two_factor_required") is True
    challenge_token = login_data.get("challenge_token")
    assert challenge_token

    verify_response = requests.post(
        f"{api_url}/user/login/2fa",
        json={
            "challenge_token": challenge_token,
            "code": _calculate_totp(secret),
        },
        timeout=5,
    )
    assert verify_response.status_code == 200
    verify_data = verify_response.json()
    assert verify_data.get("access_token")
    assert verify_data.get("user", {}).get("email") == email

    disable_code = _calculate_totp(secret)
    disable_response = requests.post(
        f"{api_url}/user/security/totp/disable",
        headers={"Authorization": f"Bearer {verify_data['access_token']}"},
        json={"current_password": password, "code": disable_code},
        timeout=5,
    )
    assert disable_response.status_code == 200


def test_service_registration_request_creates_pending_account(api_url):
    """Servisní registrace vytvoří pending žádost a účet není ihned aktivní."""
    clear_service_registration_requests_emails([CI_SVC_REQ_STANDALONE])
    email = CI_SVC_REQ_STANDALONE
    password = CI_DEFAULT_PASSWORD
    ico = CI_SVC_REQ_ICO_PRIMARY

    response = requests.post(
        f"{api_url}/user/register/service-request",
        json={
            "email": email,
            "password": password,
            "ico": ico,
            "service_name": "Demo Servis s.r.o.",
            "responsible_person": "Jan Novak",
            "phone": "+420737262711",
            "street": "Servisni 1",
            "street_number": "12",
            "city": "Praha",
            "zip": "11000",
            "dic": "CZ12345678",
            "registration_purpose": "Chceme spravovat servisni objednavky klientu.",
        },
        timeout=5,
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "pending"
    assert data.get("request_id")

    login_response = requests.post(
        f"{api_url}/user/login",
        json={"email": email, "password": password, "expected_role": "service"},
        timeout=5,
    )
    assert login_response.status_code == 401


def test_service_registration_request_duplicate_pending_blocked(api_url):
    """Opakované podání pending servisní žádosti se stejným emailem musí být blokováno."""
    clear_service_registration_requests_emails([CI_SVC_REQ_DUP_EMAIL])
    email = CI_SVC_REQ_DUP_EMAIL
    unique_ico = CI_SVC_REQ_ICO_DUP_PENDING
    payload = {
        "email": email,
        "password": CI_DEFAULT_PASSWORD,
        "ico": unique_ico,
        "service_name": "Servis Duplicate",
        "responsible_person": "Petr Svoboda",
        "phone": "+420777555444",
        "street": "Dilenska 5",
        "street_number": "5",
        "city": "Brno",
        "zip": "60200",
        "dic": None,
        "registration_purpose": "Registrace servisniho uctu pro praci s rezervacemi.",
    }

    first = requests.post(
        f"{api_url}/user/register/service-request",
        json=payload,
        timeout=5,
    )
    assert first.status_code == 200

    second = requests.post(
        f"{api_url}/user/register/service-request",
        json=payload,
        timeout=5,
    )
    assert second.status_code == 400


def test_service_registration_duplicate_ico_blocked(api_url):
    """Jedno IČO nesmí být použito pro více servisních registrací."""
    clear_service_registration_requests_emails([CI_SVC_REQ_A, CI_SVC_REQ_B])
    ico_digits = CI_FIXED_ICO_BLOCKED_PAIR
    payload_base = {
        "password": CI_DEFAULT_PASSWORD,
        "ico": ico_digits,
        "service_name": "Servis Test",
        "responsible_person": "Jan Test",
        "phone": "+420777123456",
        "street": "Servisni 1",
        "street_number": "12",
        "city": "Praha",
        "zip": "11000",
        "dic": "CZ12345678",
        "registration_purpose": "Test registrace servisniho uctu pro API.",
    }

    first_response = requests.post(
        f"{api_url}/user/register/service-request",
        json={**payload_base, "email": CI_SVC_REQ_A},
        timeout=5,
    )
    assert first_response.status_code == 200, first_response.text

    second_response = requests.post(
        f"{api_url}/user/register/service-request",
        json={**payload_base, "email": CI_SVC_REQ_B},
        timeout=5,
    )
    assert second_response.status_code == 400, second_response.text
    detail = second_response.json().get("detail", "")
    assert "IČO" in detail or "ICO" in detail or "Ico" in detail
