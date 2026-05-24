"""
GET /api/me — session context for SPA routing (JWT/session is source of truth).
"""
from __future__ import annotations

from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.auth import get_current_customer_optional
from src.core.branding import APP_DISPLAY_NAME
from src.modules.vehicle_hub.audit_log import write_global_audit_log
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, Tenant
from src.modules.vehicle_hub.workspace_entitlements import (
    default_workspace_route_kind,
    effective_workspace_kinds,
    customer_may_use_workspace_kind,
)
from src.modules.vehicle_hub.workspace_routing import (
    build_app_path_for_kind,
    build_default_app_path,
    ensure_tenant_workspace_slug,
    map_account_type,
    resolve_workspace_route_kind_for_customer,
)

router = APIRouter(tags=["session"])


class ApiMeAnonymousResponse(BaseModel):
    authenticated: Literal[False] = False
    app_name: str = APP_DISPLAY_NAME


class ApiMeAuthenticatedResponse(BaseModel):
    authenticated: Literal[True] = True
    app_name: str = APP_DISPLAY_NAME
    account_type: str
    account_id: int = Field(description="Interní ID zákaznického účtu (Customer.id)")
    display_name: Optional[str] = None
    email: str
    account_slug: str
    tenant_id: int
    workspace_route_kind: str = Field(description="user|service namespace for slug uniqueness")
    workspace_entitlements: List[str] = Field(
        default_factory=list,
        description="Povolené režimy UI/API: user, service (rozšíření účtu)",
    )
    workspace_ui_default: Optional[str] = Field(
        default=None,
        description="Výchozí režim při více entitlements (user|service)",
    )
    default_app_path: str
    role: str
    license_plan: Optional[str] = None
    license_effective_plan: Optional[str] = None
    license_trial_active: bool = False
    license_trial_ends_at: Optional[str] = None
    license_status: Optional[str] = None
    permissions: dict[str, Any] = Field(default_factory=dict)


def _normalize_assert_route(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    x = str(raw).strip().lower()
    if x in {"u", "user"}:
        return "user"
    if x in {"s", "service"}:
        return "service"
    return None


def _normalize_tenant_workspace_route_kind(tenant: Tenant, customer: Customer) -> None:
    """Coerce legacy/invalid workspace_route_kind to user|service from the authenticated account."""
    raw = (getattr(tenant, "workspace_route_kind", None) or "").strip().lower()
    if raw in {"user", "service"}:
        return
    tenant.workspace_route_kind = resolve_workspace_route_kind_for_customer(customer)


@router.get("/api/me")
def api_me(
    request: Request,
    db: Session = Depends(get_db),
    customer: Optional[Customer] = Depends(get_current_customer_optional),
    assert_route: Optional[str] = Query(None, description="Expected workspace path: u|s|user|service"),
    assert_slug: Optional[str] = Query(None, description="Workspace slug from browser URL"),
) -> dict[str, Any]:
    if not customer:
        return ApiMeAnonymousResponse().model_dump()

    tenant = db.query(Tenant).filter(Tenant.id == customer.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=500, detail="Tenant nenalezen")

    _normalize_tenant_workspace_route_kind(tenant, customer)

    kinds = effective_workspace_kinds(customer)
    entitlements_list = sorted(kinds)

    rk_seed = default_workspace_route_kind(customer)
    ensure_tenant_workspace_slug(
        db,
        tenant,
        seed_label=str(tenant.name or customer.name or customer.email or "workspace"),
        route_kind=rk_seed,
    )
    db.commit()
    db.refresh(tenant)

    lic_plan: Optional[str] = None
    lic_effective_plan: Optional[str] = None
    lic_trial_active = False
    lic_trial_ends_at: Optional[str] = None
    lic_status: Optional[str] = None
    try:
        from src.modules.licensing.service import get_license_status

        lic = get_license_status(db, int(customer.tenant_id), user_email=customer.email)
        lic_plan = str(lic.get("plan") or "") or None
        lic_effective_plan = str(lic.get("effective_plan") or lic.get("plan") or "") or None
        lic_trial_active = bool(lic.get("trial_active"))
        lic_trial_ends_at = str(lic.get("trial_ends_at") or "") or None
        lic_status = str(lic.get("status") or "") or None
    except Exception:
        pass

    assert_kind = _normalize_assert_route(assert_route)
    slug_cmp = (assert_slug or "").strip().lower()
    if assert_kind and slug_cmp:
        if not customer_may_use_workspace_kind(customer, assert_kind):
            write_global_audit_log(
                db,
                entity_type="workspace_route",
                entity_id=customer.tenant_id,
                action="workspace_route_denied",
                actor_user_id=customer.id,
                actor_role=str(customer.role or ""),
                tenant_id=customer.tenant_id,
                metadata={
                    "reason": "workspace_entitlement_missing",
                    "assert_route": assert_kind,
                    "allowed_kinds": list(entitlements_list),
                    "asserted_slug": slug_cmp,
                    "resolved_slug": str(tenant.workspace_slug or ""),
                    "path": str(request.url.path),
                    "result": "denied",
                },
            )
            db.commit()
            raise HTTPException(
                status_code=403,
                detail={
                    "reason": "workspace_route_mismatch",
                    "default_app_path": build_app_path_for_kind(db, customer, tenant, rk_seed),
                },
            )

        resolved = str(tenant.workspace_slug or "").strip().lower()
        if slug_cmp != resolved:
            write_global_audit_log(
                db,
                entity_type="workspace_route",
                entity_id=customer.tenant_id,
                action="workspace_route_denied",
                actor_user_id=customer.id,
                actor_role=str(customer.role or ""),
                tenant_id=customer.tenant_id,
                metadata={
                    "reason": "slug_mismatch",
                    "assert_route": assert_kind,
                    "asserted_slug": slug_cmp,
                    "resolved_slug": resolved,
                    "path": str(request.url.path),
                    "result": "denied",
                },
            )
            db.commit()
            raise HTTPException(
                status_code=403,
                detail={
                    "reason": "workspace_slug_mismatch",
                    "default_app_path": build_app_path_for_kind(db, customer, tenant, rk_seed),
                },
            )
        rk = assert_kind
    else:
        rk = rk_seed

    default_path = build_app_path_for_kind(db, customer, tenant, rk)
    body = ApiMeAuthenticatedResponse(
        authenticated=True,
        account_type=map_account_type(str(customer.role or "")),
        account_id=int(customer.id),
        display_name=customer.name,
        email=str(customer.email or ""),
        account_slug=str(tenant.workspace_slug or ""),
        tenant_id=int(customer.tenant_id),
        workspace_route_kind=rk,
        workspace_entitlements=entitlements_list,
        workspace_ui_default=getattr(customer, "workspace_ui_default", None),
        default_app_path=default_path,
        role=str(customer.role or "user"),
        license_plan=lic_plan,
        license_effective_plan=lic_effective_plan,
        license_trial_active=lic_trial_active,
        license_trial_ends_at=lic_trial_ends_at,
        license_status=lic_status,
        permissions={
            "force_password_change": bool(getattr(customer, "force_password_change", False)),
        },
    )
    return body.model_dump()
