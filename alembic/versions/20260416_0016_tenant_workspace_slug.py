"""Tenant workspace slug for /app/u|s/... routing

Revision ID: 20260416_0016
Revises: 20260415_0015
Create Date: 2026-04-16 12:00:00.000000
"""
from __future__ import annotations

import re
import unicodedata

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "20260416_0016"
down_revision = "20260415_0015"
branch_labels = None
depends_on = None

_slug_re = re.compile(r"[^a-z0-9]+")


def _slugify(value: str, max_len: int = 48) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return "workspace"
    normalized = unicodedata.normalize("NFKD", raw)
    base = normalized.encode("ascii", "ignore").decode("ascii")
    base = _slug_re.sub("-", base).strip("-")
    base = base[:max_len].strip("-") or "workspace"
    return base


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("tenants")}
    if "workspace_slug" not in cols:
        op.add_column("tenants", sa.Column("workspace_slug", sa.String(length=160), nullable=True))
    if "workspace_route_kind" not in cols:
        op.add_column("tenants", sa.Column("workspace_route_kind", sa.String(length=16), nullable=True))

    conn = bind

    used: set[tuple[str, str]] = set()
    for rk_raw, sl_raw in conn.execute(
        text(
            "SELECT workspace_route_kind, workspace_slug FROM tenants "
            "WHERE workspace_slug IS NOT NULL AND trim(workspace_slug) != ''"
        )
    ).fetchall():
        if not sl_raw:
            continue
        rk_norm = "service" if str(rk_raw or "").strip().lower() == "service" else "user"
        used.add((rk_norm, str(sl_raw).strip().lower()))

    tenants = conn.execute(
        text(
            "SELECT t.id, t.name, t.workspace_slug, t.workspace_route_kind, "
            "(SELECT MIN(c.id) FROM customers c WHERE c.tenant_id = t.id) AS anchor_customer_id "
            "FROM tenants t ORDER BY t.id"
        )
    ).fetchall()

    for row in tenants:
        tid = int(row[0])
        tname = str(row[1] or "")
        existing_slug = str(row[2] or "").strip() if row[2] is not None else ""
        existing_kind = str(row[3] or "").strip().lower() if row[3] is not None else ""
        anchor_id = row[4]

        role_row = None
        if anchor_id:
            role_row = conn.execute(
                text("SELECT role, email, name FROM customers WHERE id = :cid"),
                {"cid": int(anchor_id)},
            ).fetchone()

        svc_any = conn.execute(
            text("SELECT COUNT(*) FROM customers WHERE tenant_id = :tid AND lower(role) = 'service'"),
            {"tid": tid},
        ).scalar()
        rk = "service" if int(svc_any or 0) > 0 else "user"

        if existing_slug:
            rk_keep = existing_kind if existing_kind in {"user", "service"} else rk
            used.add((rk_keep, existing_slug.lower()))
            if existing_kind not in {"user", "service"}:
                conn.execute(
                    text("UPDATE tenants SET workspace_route_kind = :rk WHERE id = :tid"),
                    {"rk": rk_keep, "tid": tid},
                )
            continue

        seed = (role_row[2] or role_row[1] or tname or "workspace") if role_row else (tname or "workspace")
        base = _slugify(str(seed))
        candidate = base
        n = 1
        while (rk, candidate.lower()) in used:
            n += 1
            candidate = f"{base}-{n}"
        used.add((rk, candidate.lower()))
        conn.execute(
            text(
                "UPDATE tenants SET workspace_route_kind = :rk, workspace_slug = :slug "
                "WHERE id = :tid AND (workspace_slug IS NULL OR trim(workspace_slug) = '')"
            ),
            {"rk": rk, "slug": candidate, "tid": tid},
        )

    try:
        op.create_index("ix_tenants_workspace_slug", "tenants", ["workspace_slug"], unique=False)
    except Exception:
        pass
    try:
        op.create_index("ix_tenants_workspace_route_kind", "tenants", ["workspace_route_kind"], unique=False)
    except Exception:
        pass
    try:
        op.create_unique_constraint(
            "uq_tenants_workspace_slug_per_kind",
            "tenants",
            ["workspace_route_kind", "workspace_slug"],
        )
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_constraint("uq_tenants_workspace_slug_per_kind", "tenants", type_="unique")
    except Exception:
        pass
    for ix in ("ix_tenants_workspace_route_kind", "ix_tenants_workspace_slug"):
        try:
            op.drop_index(ix, table_name="tenants")
        except Exception:
            pass
    inspector = inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("tenants")}
    if "workspace_route_kind" in cols:
        op.drop_column("tenants", "workspace_route_kind")
    if "workspace_slug" in cols:
        op.drop_column("tenants", "workspace_slug")
