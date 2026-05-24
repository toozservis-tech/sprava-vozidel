"""
Dev-only workspace introspection (never exposed in production unless explicitly enabled).
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from typing import Optional

from src.core.auth import get_current_customer_optional
from src.core.config import ENVIRONMENT
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, Tenant
from src.modules.vehicle_hub.workspace_routing import (
    build_default_app_path,
    ensure_tenant_workspace_slug,
    resolve_workspace_route_kind_for_customer,
)

router = APIRouter(tags=["debug"])


def _workspace_debug_allowed() -> bool:
    if ENVIRONMENT != "production":
        return True
    return os.getenv("ENABLE_WORKSPACE_DEBUG_ENDPOINT", "").strip().lower() in {"1", "true", "yes", "on"}


@router.get("/api/_debug/workspace")
def debug_workspace(
    db: Session = Depends(get_db),
    customer: Optional[Customer] = Depends(get_current_customer_optional),
) -> dict:
    if not _workspace_debug_allowed():
        raise HTTPException(status_code=404, detail="Not Found")
    if not customer:
        raise HTTPException(status_code=401, detail="Authentication required")

    tenant = db.query(Tenant).filter(Tenant.id == customer.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=500, detail="Tenant nenalezen")

    rk = resolve_workspace_route_kind_for_customer(customer)
    ensure_tenant_workspace_slug(
        db,
        tenant,
        seed_label=str(tenant.name or customer.name or customer.email or "workspace"),
        route_kind=rk,
    )
    db.commit()
    db.refresh(tenant)

    default_app_path = build_default_app_path(db, customer, tenant)
    return {
        "tenant_id": tenant.id,
        "account_id": customer.id,
        "slug": str(tenant.workspace_slug or ""),
        "route_kind": rk,
        "default_app_path": default_app_path,
    }
