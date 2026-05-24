"""
Provisioning helpery pro izolaci tenantu po uživatelích.
"""
from __future__ import annotations

import secrets
from typing import Optional

from sqlalchemy.orm import Session

from .models import Tenant
from .workspace_routing import ensure_tenant_workspace_slug


def _build_tenant_name(owner_email: str, owner_name: Optional[str] = None) -> str:
    normalized_email = (owner_email or "").strip().lower()
    title = (owner_name or "").strip()
    if title:
        return title
    if "@" in normalized_email:
        return f"Tenant {normalized_email.split('@', 1)[0]}"
    return "Tenant user"


def generate_unique_license_key(db: Session, prefix: str = "th2") -> str:
    """
    Vygeneruje unikátní licenční klíč tenantu.
    """
    normalized_prefix = (prefix or "th2").strip().lower()
    for _ in range(20):
        candidate = f"{normalized_prefix}-{secrets.token_hex(10)}"
        exists = db.query(Tenant).filter(Tenant.license_key == candidate).first()
        if not exists:
            return candidate
    # Prakticky by se to nemělo stát, fallback pro jistotu.
    return f"{normalized_prefix}-{secrets.token_hex(16)}"


def create_dedicated_tenant(
    db: Session,
    owner_email: str,
    owner_name: Optional[str] = None,
    *,
    workspace_route_kind: str = "user",
) -> Tenant:
    """
    Vytvoří nový tenant určený pro jediného uživatele.
    Vrací objekt s vyplněným tenant.id (přes flush).
    """
    tenant = Tenant(
        name=_build_tenant_name(owner_email=owner_email, owner_name=owner_name),
        license_key=generate_unique_license_key(db),
    )
    db.add(tenant)
    db.flush()
    seed = (owner_name or "").strip() or owner_email
    ensure_tenant_workspace_slug(
        db,
        tenant,
        seed_label=seed,
        route_kind=workspace_route_kind,
    )
    return tenant


def ensure_default_license_for_tenant(db: Session, tenant_id: int) -> None:
    """
    Zajistí vytvoření výchozí licence (free) pro tenant.
    """
    try:
        from src.modules.licensing.service import get_or_create_license
    except Exception:
        return
    get_or_create_license(db, tenant_id)
