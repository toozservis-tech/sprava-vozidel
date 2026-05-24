"""
Antifraud validace registrace: telefon E.164, e-mail doména (MX/disposable), token hash pro ověření e-mailu.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from typing import Any

import requests

from src.core.config import JWT_SECRET_KEY

_EMAIL_VERIFICATION_PEPPER = os.getenv("EMAIL_VERIFICATION_PEPPER", "").strip() or JWT_SECRET_KEY

# Minimalní interní seznam jednorázových domén (tvrdá odmítací brána — lze rozšířit).
_DISPOSABLE_DOMAINS = frozenset(
    d.lower()
    for d in (
        "mailinator.com",
        "guerrillamail.com",
        "tempmail.com",
        "10minutemail.com",
        "throwaway.email",
        "yopmail.com",
        "trashmail.com",
        "getnada.com",
        "maildrop.cc",
        "dispostable.com",
        "fakeinbox.com",
        "mailnesia.com",
        "spam4.me",
    )
)

_E164_GENERAL = re.compile(r"^\+[1-9]\d{1,14}$")


def hash_email_verification_token(token: str) -> str:
    """HMAC-SHA256 tokenu s serverovým tajným klíčem — v DB jen tento digest."""
    digest = hmac.new(
        _EMAIL_VERIFICATION_PEPPER.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def generate_email_verification_secret() -> str:
    return secrets.token_urlsafe(32)


def _all_same_digits(s: str) -> bool:
    return len(s) > 0 and len(set(s)) == 1


def _is_sequential_asc(digits: str) -> bool:
    if len(digits) < 3:
        return False
    codes = [ord(c) for c in digits]
    for i in range(1, len(codes)):
        if codes[i] != codes[i - 1] + 1:
            return False
    return True


def _is_sequential_desc(digits: str) -> bool:
    if len(digits) < 3:
        return False
    codes = [ord(c) for c in digits]
    for i in range(1, len(codes)):
        if codes[i] != codes[i - 1] - 1:
            return False
    return True


def _national_digit_run_is_suspicious(national_digits: str) -> bool:
    """Opakující se číslice, jednoduché sekvence (123456789, …)."""
    if not national_digits.isdigit() or not national_digits:
        return True
    if _all_same_digits(national_digits):
        return True
    if national_digits in {"123456789", "012345678", "987654321", "1234567890"}:
        return True
    if _is_sequential_asc(national_digits) or _is_sequential_desc(national_digits):
        return True
    # Časté „test“ vzory
    if national_digits in {"123456789", "111111111", "000000000", "999999999"}:
        return True
    return False


def normalize_validate_phone_e164(raw: str) -> str:
    """
    Vrátí normalizované E.164 (+…).
    Pro +420 vyžaduje přesně 9 číslic za předvolbou.
    Vyhodí ValueError s českou zprávou při neplatném nebo podezřelém čísle.
    """
    if raw is None:
        raise ValueError("Telefon je povinný.")
    s = str(raw).strip()
    if not s.startswith("+"):
        raise ValueError("Telefon zadejte v mezinárodním formátu E.164 (např. +420731552299).")
    s = re.sub(r"[\s\-.()]", "", s)
    if not _E164_GENERAL.match(s):
        raise ValueError("Neplatný formát telefonu (očekáván E.164, např. +420731552299).")

    if s.startswith("+420"):
        national = s[4:]
        if len(national) != 9 or not national.isdigit():
            raise ValueError("České číslo musí mít tvar +420 a přesně 9 číslic.")
        if _national_digit_run_is_suspicious(national):
            raise ValueError("Telefon odpovídá zjevně testovacímu nebo neplatnému vzoru.")
        return s

    national = s[1:]
    if _national_digit_run_is_suspicious(national):
        raise ValueError("Telefon odpovídá zjevně testovacímu nebo neplatnému vzoru.")
    return s


def is_disposable_email_domain(domain: str) -> bool:
    d = (domain or "").strip().lower().lstrip("@")
    return d in _DISPOSABLE_DOMAINS


def check_domain_mx_records(domain: str, *, lifetime_sec: float = 2.0) -> tuple[bool, str | None]:
    """
    Zkuste najít MX záznamy. Při selhání knihovny/timeoutu vrať (True, risk_flag) — neblokuje registraci.
    (False, reason) = doména neexistuje nebo nemá MX ani A — tvrdá odmítací větev.
    """
    d = (domain or "").strip().lower().lstrip("@")
    if not d:
        return False, "mx_empty_domain"

    try:
        import dns.resolver
    except ImportError:
        return True, "mx_skipped_no_dns_library"

    mx_issue: str | None = None
    try:
        answers = dns.resolver.resolve(d, "MX", lifetime=lifetime_sec)
        if answers:
            return True, None
    except Exception as exc:
        name = type(exc).__name__
        if "Timeout" in name or "timeout" in str(exc).lower():
            return True, "mx_lookup_timeout"
        if "NXDOMAIN" in name or "NoNameservers" in name:
            return False, "mx_domain_nx"
        mx_issue = f"mx_lookup_{name.lower()}"

    try:
        dns.resolver.resolve(d, "A", lifetime=lifetime_sec)
        return True, mx_issue or "mx_missing_but_a_record"
    except Exception:
        pass

    return False, "mx_no_mail_host"


def collect_email_domain_risk_flags(domain: str) -> tuple[list[str], bool]:
    """
    Vrátí (risk_flags, domain_acceptable).
    domain_acceptable False => registraci odmítnout (422).
    """
    flags: list[str] = []
    ok, mx_flag = check_domain_mx_records(domain)
    if not ok:
        if mx_flag:
            flags.append(mx_flag)
        return flags, False
    if mx_flag:
        flags.append(mx_flag)
    return flags, True


def assert_ico_exists_in_ares(ico_digits: str, *, timeout_sec: float = 10.0) -> dict[str, Any]:
    """
    Ověří IČO proti veřejnému ARES API. Vyhodí ValueError pokud není nalezeno nebo síť selže kriticky.
    """
    clean = "".join(ch for ch in str(ico_digits or "") if ch.isdigit())
    if len(clean) != 8:
        raise ValueError("IČO musí obsahovat přesně 8 číslic.")

    url = f"https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/{clean}"
    try:
        response = requests.get(url, timeout=timeout_sec)
    except requests.RequestException as exc:
        raise ValueError(f"ARES je dočasně nedostupný ({exc}). Zkuste to znovu za chvíli.") from exc

    if response.status_code == 404:
        raise ValueError("IČO nebylo nalezeno v ARES — zkontrolujte zápis.")
    if response.status_code != 200:
        raise ValueError(f"ARES odmítl dotaz (HTTP {response.status_code}).")

    try:
        return response.json()
    except Exception as exc:
        raise ValueError("ARES odpověď nebyla zpracovatelná.") from exc


# -----------------------------------------------------------------------------
# TODO: SMS OTP ověření telefonu (phone_verified_at)
# -----------------------------------------------------------------------------
# Pokud projekt nasadí SMS providera (Twilio, Vonage, český SMS brána API):
# 1. Nový endpoint POST /user/request-phone-verification (rate limit, na phone_e164).
# 2. Generovat 6místný kód, hash v DB (např. phone_verification_code_hash + expires_at),
#    stejné bezpečnostní pravidlo jako u e-mailu — token/log nikdy v plaintextu.
# 3. POST /user/verify-phone s kódem; při úspěchu phone_verified_at = now().
# 4. Servisní účty: vyžadovat phone_verified_at před plnou aktivací (kromě admin bypass).
# 5. Audit: phone_verification_sent, phone_verified, phone_verification_failed.
# Dokud provider není: API vrací phone_verification_status=unverified, klient zobrazí stav
# „telefon neověřen“; formální E.164 validace zůstává na registration_security.validate_phone_e164.
