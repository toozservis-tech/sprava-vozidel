"""Normalizace názvů a kontaktů pro deduplikaci."""
from __future__ import annotations

import re
import unicodedata


def strip_diacritics(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_service_name(name: str | None) -> str:
    raw = strip_diacritics((name or "").lower().strip())
    raw = re.sub(r"[^\w\s]", " ", raw, flags=re.UNICODE)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:255]


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 9:
        return None
    if digits.startswith("420") and len(digits) > 9:
        digits = digits[3:]
    return digits[-9:]


def normalize_website(url: str | None) -> str | None:
    if not url:
        return None
    value = url.strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = value.rstrip("/")
    if value.startswith("www."):
        value = value[4:]
    return value[:512] or None


def names_similar(a: str | None, b: str | None) -> bool:
    na = normalize_service_name(a)
    nb = normalize_service_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    return False
