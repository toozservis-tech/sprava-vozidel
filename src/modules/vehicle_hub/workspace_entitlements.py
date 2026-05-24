"""
Rozšíření účtu o více pracovních režimů (uživatel / servis) bez nutnosti měnit primární roli.

- ``workspace_entitlements`` na Customer: JSON pole ``["user","service"]`` (podmnožina).
- Pokud je NULL, chování se odvozuje pouze z ``role`` (zpětná kompatibilita).
- ``workspace_ui_default``: při dvou režimech výchozí cesta pro /api/me bez URL kontextu.
"""
from __future__ import annotations

import json
from typing import Any, FrozenSet, Optional

from src.core.rbac import ROLE_SERVICE, is_admin, normalize_role


def _parse_entitlements_raw(raw: Any) -> Optional[list]:
    if raw is None:
        return None
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else None
        except (TypeError, ValueError):
            return None
    return None


def effective_workspace_kinds(customer: Any) -> FrozenSet[str]:
    """Vrátí {'user'} a/nebo {'service'} podle explicitního JSON nebo role."""
    parsed = _parse_entitlements_raw(getattr(customer, "workspace_entitlements", None))
    if parsed:
        out = {str(x).strip().lower() for x in parsed if str(x).strip().lower() in {"user", "service"}}
        if out:
            return frozenset(out)
    role = normalize_role(getattr(customer, "role", None))
    if role == ROLE_SERVICE:
        return frozenset({"service"})
    return frozenset({"user"})


def default_workspace_route_kind(customer: Any) -> str:
    """Výchozí segment /app/u|s při absenci assert_route v /api/me."""
    kinds = effective_workspace_kinds(customer)
    if len(kinds) == 1:
        return next(iter(kinds))
    pref = str(getattr(customer, "workspace_ui_default", None) or "").strip().lower()
    if pref in kinds:
        return pref
    return "user" if "user" in kinds else "service"


def customer_may_use_workspace_kind(customer: Any, kind: str) -> bool:
    k = str(kind or "").strip().lower()
    if k not in {"user", "service"}:
        return False
    return k in effective_workspace_kinds(customer)


def customer_has_service_workspace_access(customer: Any) -> bool:
    """Servisní API / přehledy: admin vývojář + explicitní 'service' v entitlements + role service."""
    if is_admin(getattr(customer, "role", None)):
        return True
    return "service" in effective_workspace_kinds(customer)


def customer_has_user_workspace_access(customer: Any) -> bool:
    """Uživatelské flow (např. /reservations/my): admin + explicitní 'user'."""
    if is_admin(getattr(customer, "role", None)):
        return True
    return "user" in effective_workspace_kinds(customer)


def customer_acts_as_service_operator(customer: Any) -> bool:
    """Stejná logika jako dříve „service-like“ pro filtrování podle service_id == customer.id."""
    return customer_has_service_workspace_access(customer)


def normalize_workspace_entitlements_for_storage(raw: Any) -> Optional[str]:
    """
    Z admin API: list/str -> uložitelný JSON string, nebo None = smazat override (default podle role).
    """
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    items = raw
    if isinstance(raw, str):
        try:
            items = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("workspace_entitlements musí být JSON pole řetězců") from exc
    if not isinstance(items, list):
        raise ValueError("workspace_entitlements musí být pole")
    kinds = sorted({str(x).strip().lower() for x in items if str(x).strip().lower() in {"user", "service"}})
    if not kinds:
        return None
    return json.dumps(kinds, separators=(",", ":"))


def normalize_workspace_ui_default_for_storage(raw: Any, kinds: FrozenSet[str]) -> Optional[str]:
    if raw is None or str(raw).strip() == "":
        return None
    v = str(raw).strip().lower()
    if v not in {"user", "service"}:
        raise ValueError("workspace_ui_default musí být 'user' nebo 'service'")
    if v not in kinds:
        raise ValueError("workspace_ui_default musí být jeden z aktivních entitlements")
    return v
