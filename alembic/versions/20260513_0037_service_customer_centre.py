"""Service customer centre: onboarding tokens, lookup indexes, link metadata, vehicle provenance.

Revision ID: 20260513_0037
Revises: 20260511_0036
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "20260513_0037"
down_revision = "20260511_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    is_sqlite = bind.dialect.name == "sqlite"

    # --- customers ---
    cust_cols = {c["name"] for c in inspector.get_columns("customers")} if "customers" in tables else set()
    if "customers" in tables:
        if "force_password_change" not in cust_cols:
            op.add_column(
                "customers",
                sa.Column(
                    "force_password_change",
                    sa.Boolean(),
                    nullable=False,
                    server_default="0",
                ),
            )
        if "email_normalized" not in cust_cols:
            op.add_column("customers", sa.Column("email_normalized", sa.String(length=320), nullable=True))
        if "phone_normalized" not in cust_cols:
            op.add_column("customers", sa.Column("phone_normalized", sa.String(length=32), nullable=True))

    # --- vehicles ---
    veh_cols = {c["name"] for c in inspector.get_columns("vehicles")} if "vehicles" in tables else set()
    if "vehicles" in tables:
        if "provisioned_by_service_customer_id" not in veh_cols:
            if is_sqlite:
                op.add_column(
                    "vehicles",
                    sa.Column("provisioned_by_service_customer_id", sa.Integer(), nullable=True),
                )
            else:
                op.add_column(
                    "vehicles",
                    sa.Column(
                        "provisioned_by_service_customer_id",
                        sa.Integer(),
                        sa.ForeignKey("customers.id"),
                        nullable=True,
                    ),
                )

    # --- service_customer_links ---
    scl_cols = (
        {c["name"] for c in inspector.get_columns("service_customer_links")}
        if "service_customer_links" in tables
        else set()
    )
    if "service_customer_links" in tables:
        if "link_source" not in scl_cols:
            op.add_column("service_customer_links", sa.Column("link_source", sa.String(length=40), nullable=True))
        if "consent_basis" not in scl_cols:
            op.add_column("service_customer_links", sa.Column("consent_basis", sa.Text(), nullable=True))
        if "consent_note" not in scl_cols:
            op.add_column("service_customer_links", sa.Column("consent_note", sa.Text(), nullable=True))
        if "internal_service_note" not in scl_cols:
            op.add_column("service_customer_links", sa.Column("internal_service_note", sa.Text(), nullable=True))
        if "approved_at" not in scl_cols:
            op.add_column("service_customer_links", sa.Column("approved_at", sa.DateTime(), nullable=True))
        if "revoked_at" not in scl_cols:
            op.add_column("service_customer_links", sa.Column("revoked_at", sa.DateTime(), nullable=True))
        if "created_by_service_user_id" not in scl_cols:
            if is_sqlite:
                op.add_column(
                    "service_customer_links",
                    sa.Column("created_by_service_user_id", sa.Integer(), nullable=True),
                )
            else:
                op.add_column(
                    "service_customer_links",
                    sa.Column(
                        "created_by_service_user_id",
                        sa.Integer(),
                        sa.ForeignKey("customers.id"),
                        nullable=True,
                    ),
                )
        if "last_interaction_at" not in scl_cols:
            op.add_column("service_customer_links", sa.Column("last_interaction_at", sa.DateTime(), nullable=True))

    # --- service_vehicle_access ---
    sva_cols = (
        {c["name"] for c in inspector.get_columns("service_vehicle_access")}
        if "service_vehicle_access" in tables
        else set()
    )
    if "service_vehicle_access" in tables:
        if "service_tenant_id" not in sva_cols:
            if is_sqlite:
                op.add_column(
                    "service_vehicle_access",
                    sa.Column("service_tenant_id", sa.Integer(), nullable=True),
                )
            else:
                op.add_column(
                    "service_vehicle_access",
                    sa.Column(
                        "service_tenant_id",
                        sa.Integer(),
                        sa.ForeignKey("tenants.id"),
                        nullable=True,
                    ),
                )
        if "access_scope_json" not in sva_cols:
            op.add_column("service_vehicle_access", sa.Column("access_scope_json", sa.Text(), nullable=True))
        if "revoke_reason" not in sva_cols:
            op.add_column("service_vehicle_access", sa.Column("revoke_reason", sa.Text(), nullable=True))

    # --- user_onboarding_tokens ---
    if "user_onboarding_tokens" not in tables:
        if is_sqlite:
            op.create_table(
                "user_onboarding_tokens",
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("user_id", sa.Integer(), nullable=False),
                sa.Column("token_hash", sa.String(length=128), nullable=False),
                sa.Column("token_type", sa.String(length=64), nullable=False),
                sa.Column("expires_at", sa.DateTime(), nullable=False),
                sa.Column("used_at", sa.DateTime(), nullable=True),
                sa.Column("created_by_service_tenant_id", sa.Integer(), nullable=True),
                sa.Column("created_by_user_id", sa.Integer(), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("ip_created", sa.String(length=128), nullable=True),
                sa.Column("user_agent_created", sa.Text(), nullable=True),
            )
        else:
            op.create_table(
                "user_onboarding_tokens",
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("user_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
                sa.Column("token_hash", sa.String(length=128), nullable=False),
                sa.Column("token_type", sa.String(length=64), nullable=False),
                sa.Column("expires_at", sa.DateTime(), nullable=False),
                sa.Column("used_at", sa.DateTime(), nullable=True),
                sa.Column(
                    "created_by_service_tenant_id",
                    sa.Integer(),
                    sa.ForeignKey("tenants.id"),
                    nullable=True,
                ),
                sa.Column(
                    "created_by_user_id",
                    sa.Integer(),
                    sa.ForeignKey("customers.id"),
                    nullable=True,
                ),
                sa.Column("created_at", sa.DateTime(), nullable=False),
                sa.Column("ip_created", sa.String(length=128), nullable=True),
                sa.Column("user_agent_created", sa.Text(), nullable=True),
            )
        op.create_index("ix_user_onboarding_tokens_user_id", "user_onboarding_tokens", ["user_id"])
        op.create_index("ix_user_onboarding_tokens_token_hash", "user_onboarding_tokens", ["token_hash"])
        op.create_index("ix_user_onboarding_tokens_token_type", "user_onboarding_tokens", ["token_type"])
        op.create_index(
            "ix_user_onboarding_tokens_user_hash",
            "user_onboarding_tokens",
            ["user_id", "token_hash"],
        )

    # Backfill normalized columns (best-effort, portable SQL)
    if "customers" in tables:
        try:
            op.execute(
                sa.text(
                    "UPDATE customers SET email_normalized = LOWER(TRIM(email)) WHERE email IS NOT NULL AND (email_normalized IS NULL OR email_normalized = '')"
                )
            )
        except Exception:
            pass

    # Indexes (create if not exist — ignore failures on SQLite duplicates)
    for ix_name, table, cols in (
        ("ix_customers_email_normalized", "customers", ["email_normalized"]),
        ("ix_customers_phone_normalized", "customers", ["phone_normalized"]),
        ("ix_service_customer_links_service_tenant_customer", "service_customer_links", ["service_tenant_id", "customer_id"]),
        ("ix_service_vehicle_access_service_tenant_vehicle", "service_vehicle_access", ["service_tenant_id", "vehicle_id"]),
    ):
        if table in tables:
            existing = {i["name"] for i in inspector.get_indexes(table)}
            if ix_name not in existing:
                try:
                    op.create_index(ix_name, table, cols)
                except Exception:
                    pass


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "user_onboarding_tokens" in tables:
        op.drop_table("user_onboarding_tokens")

    for ix_name, table in (
        ("ix_service_vehicle_access_service_tenant_vehicle", "service_vehicle_access"),
        ("ix_service_customer_links_service_tenant_customer", "service_customer_links"),
        ("ix_customers_phone_normalized", "customers"),
        ("ix_customers_email_normalized", "customers"),
    ):
        if table in tables:
            idxs = {i["name"] for i in inspector.get_indexes(table)}
            if ix_name in idxs:
                try:
                    op.drop_index(ix_name, table_name=table)
                except Exception:
                    pass

    def drop_col(tbl: str, col: str) -> None:
        if tbl not in tables:
            return
        cols = {c["name"] for c in inspector.get_columns(tbl)}
        if col in cols:
            try:
                op.drop_column(tbl, col)
            except Exception:
                pass

    for col in (
        "revoke_reason",
        "access_scope_json",
        "service_tenant_id",
    ):
        drop_col("service_vehicle_access", col)

    for col in (
        "last_interaction_at",
        "created_by_service_user_id",
        "revoked_at",
        "approved_at",
        "internal_service_note",
        "consent_note",
        "consent_basis",
        "link_source",
    ):
        drop_col("service_customer_links", col)

    drop_col("vehicles", "provisioned_by_service_customer_id")

    for col in ("phone_normalized", "email_normalized", "force_password_change"):
        drop_col("customers", col)
