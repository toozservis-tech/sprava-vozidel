"""Veřejný profil servisu v katalogu partnerů (JSON v ``customers.partner_public_profile``)."""
from __future__ import annotations

import json
from typing import Any, Optional

PROFILE_DEFAULTS: dict[str, Any] = {
    "tagline": "",
    "about": "",
    "services_offered": [],
    "equipment": [],
    "opening_hours": "",
    "brands": [],
}

_MAX_STORED_UTF8_BYTES = 24_000


def _normalize_str_list(val: Any, *, max_items: int, item_max: int) -> list[str]:
    out: list[str] = []
    if not isinstance(val, list):
        return out
    for raw in val[:max_items]:
        s = str(raw or "").strip()
        if not s:
            continue
        out.append(s[:item_max])
    return out


def normalize_partner_public_profile_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "tagline": str(data.get("tagline") or "")[:280],
        "about": str(data.get("about") or "")[:4000],
        "services_offered": _normalize_str_list(data.get("services_offered"), max_items=40, item_max=120),
        "equipment": _normalize_str_list(data.get("equipment"), max_items=40, item_max=120),
        "opening_hours": str(data.get("opening_hours") or "")[:500],
        "brands": _normalize_str_list(data.get("brands"), max_items=30, item_max=80),
    }


def partner_public_profile_from_db(raw: Optional[str]) -> dict[str, Any]:
    if not raw or not str(raw).strip():
        return dict(PROFILE_DEFAULTS)
    try:
        data = json.loads(raw)
    except Exception:
        return dict(PROFILE_DEFAULTS)
    if not isinstance(data, dict):
        return dict(PROFILE_DEFAULTS)
    return normalize_partner_public_profile_dict(data)


def partner_public_profile_to_stored_json(data: dict[str, Any]) -> str:
    normalized = normalize_partner_public_profile_dict(data)
    blob = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    if len(blob.encode("utf-8")) > _MAX_STORED_UTF8_BYTES:
        raise ValueError("Veřejný profil je příliš rozsáhlý. Zkraťte text nebo seznamy.")
    return blob
