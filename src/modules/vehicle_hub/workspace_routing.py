"""
Workspace slug + URL routing helpers (tenant-scoped readable slug, not an auth mechanism).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from sqlalchemy.orm import Session

from .models import Customer, Tenant

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_workspace_label(value: str, *, max_len: int = 48) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return "workspace"
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_bytes = normalized.encode("ascii", "ignore")
    base = ascii_bytes.decode("ascii")
    base = _SLUG_RE.sub("-", base).strip("-")
    base = base[:max_len].strip("-") or "workspace"
    return base


def _allocate_unique_workspace_slug(
    db: Session,
    *,
    route_kind: str,
    base_slug: str,
    exclude_tenant_id: Optional[int] = None,
) -> str:
    kind = (route_kind or "user").strip().lower()
    if kind not in {"user", "service"}:
        kind = "user"
    candidate = base_slug or "workspace"
    suffix = 1
    while True:
        q = db.query(Tenant.id).filter(
            Tenant.workspace_route_kind == kind,
            Tenant.workspace_slug == candidate,
        )
        if exclude_tenant_id is not None:
            q = q.filter(Tenant.id != exclude_tenant_id)
        if q.first() is None:
            return candidate
        suffix += 1
        candidate = f"{base_slug}-{suffix}"


def ensure_tenant_workspace_slug(
    db: Session,
    tenant: Tenant,
    *,
    seed_label: str,
    route_kind: Optional[str] = None,
) -> Tenant:
    """Assign workspace_slug / workspace_route_kind if missing; stable once set."""
    kind = (route_kind or tenant.workspace_route_kind or "user").strip().lower()
    if kind not in {"user", "service"}:
        kind = "user"

    if not getattr(tenant, "workspace_route_kind", None):
        tenant.workspace_route_kind = kind
    elif route_kind and not getattr(tenant, "workspace_slug", None):
        # First-time slug allocation should use the caller-provided kind (e.g. new tenant).
        tenant.workspace_route_kind = kind

    if getattr(tenant, "workspace_slug", None):
        db.flush()
        return tenant

    base = slugify_workspace_label(seed_label)
    tenant.workspace_slug = _allocate_unique_workspace_slug(
        db,
        route_kind=str(tenant.workspace_route_kind or kind),
        base_slug=base,
        exclude_tenant_id=tenant.id,
    )
    db.flush()
    return tenant


def resolve_workspace_route_kind_for_customer(customer: Customer) -> str:
    from .workspace_entitlements import default_workspace_route_kind

    return default_workspace_route_kind(customer)


def build_app_path_for_kind(db: Session, customer: Customer, tenant: Tenant, rk: str) -> str:
    kind = (rk or "user").strip().lower()
    if kind not in {"user", "service"}:
        kind = "user"
    ensure_tenant_workspace_slug(
        db,
        tenant,
        seed_label=str(tenant.name or customer.name or customer.email or "workspace"),
        route_kind=kind,
    )
    prefix = "s" if kind == "service" else "u"
    slug = str(tenant.workspace_slug or "").strip() or "workspace"
    return f"/app/{prefix}/{slug}/dashboard"


def build_default_app_path(db: Session, customer: Customer, tenant: Tenant) -> str:
    rk = resolve_workspace_route_kind_for_customer(customer)
    return build_app_path_for_kind(db, customer, tenant, rk)


def map_account_type(role: str) -> str:
    r = str(role or "").strip().lower()
    if r in {"admin", "developer_admin"}:
        return "admin"
    if r == "service":
        return "service"
    return "user"
