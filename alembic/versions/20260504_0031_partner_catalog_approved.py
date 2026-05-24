"""Customer.partner_catalog_approved for service partner directory.

Revision ID: 20260504_0031
Revises: 20260503_0030
Create Date: 2026-05-04 14:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "20260504_0031"
down_revision = "20260503_0030"
branch_labels = None
depends_on = None


def _execute_approved_updates(connection, *, has_srr: bool) -> None:
    """Nastaví partner_catalog_approved = true pro existující servisy (dialekt přes bind param)."""
    if has_srr:
        connection.execute(
            text(
                """
                UPDATE customers
                SET partner_catalog_approved = :approved
                WHERE id IN (
                    SELECT approved_customer_id
                    FROM service_registration_requests
                    WHERE status = 'approved'
                      AND approved_customer_id IS NOT NULL
                )
                """
            ),
            {"approved": True},
        )
        connection.execute(
            text(
                """
                UPDATE customers
                SET partner_catalog_approved = :approved
                WHERE role = 'service'
                  AND password_hash IS NOT NULL
                  AND COALESCE(is_deleted, 0) = 0
                  AND NOT EXISTS (
                      SELECT 1
                      FROM service_registration_requests srr
                      WHERE srr.status = 'approved'
                        AND srr.approved_customer_id = customers.id
                  )
                """
            ),
            {"approved": True},
        )
    else:
        connection.execute(
            text(
                """
                UPDATE customers
                SET partner_catalog_approved = :approved
                WHERE role = 'service'
                  AND password_hash IS NOT NULL
                  AND COALESCE(is_deleted, 0) = 0
                """
            ),
            {"approved": True},
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    cols = {c["name"] for c in inspector.get_columns("customers")}
    if "partner_catalog_approved" not in cols:
        op.add_column(
            "customers",
            sa.Column(
                "partner_catalog_approved",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    has_srr = "service_registration_requests" in tables
    _execute_approved_updates(bind, has_srr=has_srr)

    # Konzistence: nové řádky přes ORM (výchozí false); u PostgreSQL lze server_default nechat false
    try:
        op.alter_column(
            "customers",
            "partner_catalog_approved",
            server_default=None,
            existing_type=sa.Boolean(),
            existing_nullable=False,
        )
    except Exception:
        # SQLite starší ovladače nemusí alter_column server_default podporovat — ignorovat
        pass


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("customers")}
    if "partner_catalog_approved" in cols:
        op.drop_column("customers", "partner_catalog_approved")
