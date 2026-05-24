"""
Security helpers extracted from src.server.main.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from src.core.branding import APP_DISPLAY_NAME
from src.modules.vehicle_hub.models import Customer, CustomerSecuritySettings


_pending_2fa_logins: dict[str, dict] = {}
TOTP_PERIOD_SECONDS = 30
TOTP_DIGITS = 6
TOTP_VERIFY_WINDOW_STEPS = 1
TOTP_LOGIN_CHALLENGE_TTL_SECONDS = 5 * 60
TOTP_ISSUER_NAME = APP_DISPLAY_NAME


def cleanup_expired_2fa_challenges() -> None:
    now = time.time()
    expired_tokens = [
        token
        for token, payload in _pending_2fa_logins.items()
        if float(payload.get("expires_at", 0)) <= now
    ]
    for token in expired_tokens:
        _pending_2fa_logins.pop(token, None)


def create_2fa_login_challenge(customer: Customer, expected_role: str | None = None) -> tuple[str, int]:
    cleanup_expired_2fa_challenges()
    challenge_token = secrets.token_urlsafe(32)
    expires_at = time.time() + TOTP_LOGIN_CHALLENGE_TTL_SECONDS
    _pending_2fa_logins[challenge_token] = {
        "email": customer.email,
        "tenant_id": customer.tenant_id,
        "customer_id": customer.id,
        "expected_role": expected_role or "",
        "attempts": 0,
        "expires_at": expires_at,
    }
    return challenge_token, TOTP_LOGIN_CHALLENGE_TTL_SECONDS


def get_2fa_login_challenge(token: str) -> dict | None:
    cleanup_expired_2fa_challenges()
    return _pending_2fa_logins.get(token)


def pop_2fa_login_challenge(token: str) -> dict | None:
    return _pending_2fa_logins.pop(token, None)


def set_2fa_login_challenge(token: str, payload: dict) -> None:
    _pending_2fa_logins[token] = payload


def normalize_totp_code(value: str | None) -> str:
    raw = str(value or "").strip()
    return "".join(ch for ch in raw if ch.isdigit())


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").replace("=", "")


def decode_totp_secret(secret: str) -> bytes:
    normalized = "".join((secret or "").split()).upper()
    if not normalized:
        raise ValueError("TOTP secret je prázdný")
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    return base64.b32decode(normalized + padding, casefold=True)


def calculate_totp(secret: str, for_unix_time: int) -> str:
    key = decode_totp_secret(secret)
    counter = int(for_unix_time // TOTP_PERIOD_SECONDS)
    counter_bytes = struct.pack(">Q", counter)
    digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    code = truncated % (10 ** TOTP_DIGITS)
    return f"{code:0{TOTP_DIGITS}d}"


def verify_totp(secret: str, code: str, now_ts: int | None = None) -> bool:
    normalized_code = normalize_totp_code(code)
    if len(normalized_code) != TOTP_DIGITS:
        return False
    now_unix = int(now_ts if now_ts is not None else time.time())
    for step in range(-TOTP_VERIFY_WINDOW_STEPS, TOTP_VERIFY_WINDOW_STEPS + 1):
        ts = now_unix + (step * TOTP_PERIOD_SECONDS)
        expected = calculate_totp(secret, ts)
        if hmac.compare_digest(expected, normalized_code):
            return True
    return False


def build_totp_uri(secret: str, account_email: str) -> str:
    issuer_encoded = quote(TOTP_ISSUER_NAME)
    account_encoded = quote(f"{TOTP_ISSUER_NAME}:{account_email}")
    return (
        f"otpauth://totp/{account_encoded}"
        f"?secret={secret}&issuer={issuer_encoded}&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD_SECONDS}"
    )


def get_or_create_security_settings(db, customer: Customer) -> CustomerSecuritySettings:
    settings = (
        db.query(CustomerSecuritySettings)
        .filter(CustomerSecuritySettings.customer_id == customer.id)
        .first()
    )
    if settings:
        if settings.tenant_id != customer.tenant_id:
            settings.tenant_id = customer.tenant_id
            db.commit()
            db.refresh(settings)
        return settings

    settings = CustomerSecuritySettings(
        tenant_id=customer.tenant_id,
        customer_id=customer.id,
        two_factor_enabled=False,
        biometric_enabled=False,
        biometric_preferred=False,
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings
