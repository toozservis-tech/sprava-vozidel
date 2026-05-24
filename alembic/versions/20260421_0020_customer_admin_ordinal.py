"""customer admin ordinal and deletion archive labels

Revision ID: 20260421_0020
Revises: 20260420_0019
Create Date: 2026-04-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "20260421_0020"
down_revision = "20260420_0019"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(inspect(bind).get_table_names())


def _cols(bind, table: str) -> set[str]:
    if table not in _tables(bind):
        return set()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if "customer_deletion_labels" not in _tables(bind):
        op.create_table(
            "customer_deletion_labels",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("ordinal_at_delete", sa.Integer(), nullable=False),
            sa.Column("hash_depth", sa.Integer(), nullable=False),
            sa.Column("email_before", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_customer_deletion_labels_customer_id", "customer_deletion_labels", ["customer_id"])
        op.create_index("ix_customer_deletion_labels_ordinal_at_delete", "customer_deletion_labels", ["ordinal_at_delete"])

    if "admin_ordinal" not in _cols(bind, "customers"):
        with op.batch_alter_table("customers") as batch:
            batch.add_column(sa.Column("admin_ordinal", sa.Integer(), nullable=True))
        op.create_index("ix_customers_admin_ordinal", "customers", ["admin_ordinal"])

    dialect = bind.dialect.name
    if dialect == "sqlite":
        op.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_admin_ordinal_active "
                "ON customers(admin_ordinal) "
                "WHERE COALESCE(is_deleted,0)=0 AND admin_ordinal IS NOT NULL"
            )
        )
    elif dialect == "postgresql":
        op.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_admin_ordinal_active "
                "ON customers (admin_ordinal) "
                "WHERE COALESCE(is_deleted, false) = false AND admin_ordinal IS NOT NULL"
            )
        )

    rows = bind.execute(
        text(
            "SELECT id FROM customers WHERE COALESCE(is_deleted,0)=0 "
            "ORDER BY CASE WHEN created_at IS NULL THEN 1 ELSE 0 END, created_at ASC, id ASC"
        )
    ).fetchall()
    for i, row in enumerate(rows, start=1):
        cid = row[0]
        bind.execute(
            text("UPDATE customers SET admin_ordinal = :ord WHERE id = :id"),
            {"ord": i, "id": cid},
        )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(text("DROP INDEX IF EXISTS uq_customers_admin_ordinal_active"))

    if "customer_deletion_labels" in _tables(bind):
        op.drop_table("customer_deletion_labels")

    try:
        op.drop_index("ix_customers_admin_ordinal", table_name="customers")
    except Exception:
        pass

    if "admin_ordinal" in _cols(bind, "customers"):
        with op.batch_alter_table("customers") as batch:
            batch.drop_column("admin_ordinal")
