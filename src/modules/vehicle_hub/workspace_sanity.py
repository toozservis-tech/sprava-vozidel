"""
Read-only workspace DB checks + optional non-destructive slug repair.

Used by scripts and tests; does not change routing architecture.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from .models import Customer, License, Tenant
from .workspace_routing import ensure_tenant_workspace_slug, resolve_workspace_route_kind_for_customer


@dataclass
class WorkspaceSanityReport:
    duplicate_slug_groups: list[dict[str, Any]]
    empty_slug_rows: list[dict[str, Any]]
    invalid_route_kind_rows: list[dict[str, Any]]
    route_kind_counts: dict[str, int]

    @property
    def has_duplicate_slugs(self) -> bool:
        return len(self.duplicate_slug_groups) > 0

    @property
    def has_empty_slugs(self) -> bool:
        return len(self.empty_slug_rows) > 0

    @property
    def route_kinds_valid(self) -> bool:
        return len(self.invalid_route_kind_rows) == 0


def collect_workspace_sanity_report(db: Session) -> WorkspaceSanityReport:
    dup_sql = text(
        """
        SELECT workspace_route_kind, workspace_slug, COUNT(*) AS cnt
        FROM tenants
        WHERE workspace_slug IS NOT NULL AND TRIM(workspace_slug) != ''
        GROUP BY workspace_route_kind, workspace_slug
        HAVING COUNT(*) > 1
        """
    )
    duplicate_slug_groups = [dict(r._mapping) for r in db.execute(dup_sql)]

    empty_sql = text(
        """
        SELECT id, workspace_slug, workspace_route_kind
        FROM tenants
        WHERE workspace_slug IS NULL OR TRIM(workspace_slug) = ''
        """
    )
    empty_slug_rows = [dict(r._mapping) for r in db.execute(empty_sql)]

    kinds_sql = text(
        """
        SELECT workspace_route_kind, COUNT(*) AS cnt
        FROM tenants
        GROUP BY workspace_route_kind
        """
    )
    route_kind_counts: dict[str, int] = {}
    invalid_route_kind_rows: list[dict[str, Any]] = []
    for r in db.execute(kinds_sql):
        row = dict(r._mapping)
        k = row.get("workspace_route_kind")
        key = (k or "").strip().lower() if k is not None else ""
        route_kind_counts[str(k) if k is not None else "NULL"] = int(row["cnt"] or 0)
        if key not in {"user", "service"}:
            invalid_route_kind_rows.append(row)

    return WorkspaceSanityReport(
        duplicate_slug_groups=duplicate_slug_groups,
        empty_slug_rows=empty_slug_rows,
        invalid_route_kind_rows=invalid_route_kind_rows,
        route_kind_counts=route_kind_counts,
    )


def repair_empty_workspace_slugs(db: Session) -> int:
    """Backfill missing slugs via ensure_tenant_workspace_slug. Returns number of tenants touched."""
    touched = 0
    q = (
        db.query(Tenant)
        .filter(or_(Tenant.workspace_slug.is_(None), func.trim(Tenant.workspace_slug) == ""))
        .order_by(Tenant.id.asc())
    )
    for tenant in q.all():
        owner = (
            db.query(Customer)
            .filter(Customer.tenant_id == tenant.id)
            .order_by(Customer.id.asc())
            .first()
        )
        rk = resolve_workspace_route_kind_for_customer(owner) if owner else "user"
        seed = str(tenant.name or (owner.email if owner else None) or (owner.name if owner else None) or "workspace")
        ensure_tenant_workspace_slug(db, tenant, seed_label=seed, route_kind=rk)
        touched += 1
    if touched:
        db.commit()
    return touched


def collect_license_workspace_mismatch_report(db: Session) -> Dict[str, Any]:
    """
    Hlásí nekonzistence mezi tenants.workspace_route_kind a licences.plan.

    - service_license_non_service_route_kind: řádek licences začíná na service_,
      ale tenant nemá workspace_route_kind == service (typicky starý stav před opravou párování).
    - service_route_kind_user_license_plan: tenant má route_kind service, ale plán v licences
      je uživatelský (free/basic/premium/lifetime) — často omyl při ruční úpravě DB.
    """
    sql = text(
        """
        SELECT
            t.id AS tenant_id,
            t.workspace_route_kind,
            COALESCE(LOWER(TRIM(l.plan)), '') AS license_plan,
            EXISTS (
                SELECT 1 FROM customers c
                WHERE c.tenant_id = t.id AND LOWER(TRIM(COALESCE(c.role, ''))) = 'service'
            ) AS has_service_role_customer
        FROM tenants t
        LEFT JOIN licenses l ON l.tenant_id = t.id
        ORDER BY t.id ASC
        """
    )
    rows_out: List[Dict[str, Any]] = []
    for r in db.execute(sql):
        row = dict(r._mapping)
        tid = int(row["tenant_id"])
        rk = str(row["workspace_route_kind"] or "").strip().lower()
        plan = str(row["license_plan"] or "").strip().lower()
        has_svc = bool(row["has_service_role_customer"])
        issues: List[str] = []
        if plan.startswith("service_"):
            if rk != "service":
                issues.append("service_license_non_service_route_kind")
        elif rk == "service" and plan and not plan.startswith("service_"):
            issues.append("service_route_kind_user_license_plan")
        if issues:
            rows_out.append(
                {
                    "tenant_id": tid,
                    "workspace_route_kind": row["workspace_route_kind"],
                    "license_plan": plan or None,
                    "has_service_role_customer": has_svc,
                    "issues": issues,
                }
            )

    auto_fixable = sum(
        1 for item in rows_out if "service_license_non_service_route_kind" in item["issues"]
    )
    return {
        "mismatch_count": len(rows_out),
        "auto_fixable_non_service_route_with_service_license_count": auto_fixable,
        "rows": rows_out,
    }


def repair_service_license_route_kinds(db: Session, *, dry_run: bool = False) -> Dict[str, Any]:
    """
    Nastaví tenants.workspace_route_kind = 'service' tam, kde licences.plan začíná na service_
    a dosud route_kind není service.

    Nevrací opačnou kategorii (service_route_kind_user_license_plan) — tu je potřeba řešit ručně.
    """
    touched_ids: List[int] = []
    q = db.query(Tenant).order_by(Tenant.id.asc())
    for tenant in q.all():
        rk = str(tenant.workspace_route_kind or "").strip().lower()
        if rk == "service":
            continue
        lic = db.query(License).filter(License.tenant_id == tenant.id).first()
        if lic is None:
            continue
        plan = str(lic.plan or "").strip().lower()
        if not plan.startswith("service_"):
            continue
        touched_ids.append(int(tenant.id))
        if not dry_run:
            tenant.workspace_route_kind = "service"
    if touched_ids and not dry_run:
        db.commit()
    return {"dry_run": dry_run, "updated_count": len(touched_ids), "tenant_ids": touched_ids}


def normalize_invalid_tenant_route_kinds(db: Session) -> int:
    """
    Set workspace_route_kind to user|service only, inferred from first customer in tenant.
    Returns number of rows updated.
    """
    updated = 0
    tenants = db.query(Tenant).all()
    for tenant in tenants:
        raw = (tenant.workspace_route_kind or "").strip().lower()
        if raw in {"user", "service"}:
            continue
        owner = (
            db.query(Customer)
            .filter(Customer.tenant_id == tenant.id)
            .order_by(Customer.id.asc())
            .first()
        )
        tenant.workspace_route_kind = resolve_workspace_route_kind_for_customer(owner) if owner else "user"
        updated += 1
    if updated:
        db.commit()
    return updated
