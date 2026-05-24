"""vehicle ownership periods and origin tracking

Revision ID: 20260406_0007
Revises: 20260406_0006
Create Date: 2026-04-06 23:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "20260406_0007"
down_revision = "20260406_0006"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {str(col.get("name")) for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _has_column(inspector, "vehicle_ownerships", "ownership_origin"):
        op.add_column(
            "vehicle_ownerships",
            sa.Column("ownership_origin", sa.String(), nullable=True),
        )
        inspector = inspect(bind)

    if not _has_column(inspector, "vehicle_ownerships", "owned_from"):
        op.add_column(
            "vehicle_ownerships",
            sa.Column("owned_from", sa.DateTime(), nullable=True),
        )
        inspector = inspect(bind)

    if not _has_column(inspector, "vehicle_ownerships", "owned_until"):
        op.add_column(
            "vehicle_ownerships",
            sa.Column("owned_until", sa.DateTime(), nullable=True),
        )

    bind.execute(
        text(
            """
            UPDATE vehicle_ownerships
            SET ownership_origin = COALESCE(NULLIF(ownership_origin, ''), 'legacy_backfill'),
                owned_from = COALESCE(owned_from, assigned_at, created_at, CURRENT_TIMESTAMP)
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _has_column(inspector, "vehicle_ownerships", "owned_until"):
        op.drop_column("vehicle_ownerships", "owned_until")
        inspector = inspect(bind)
    if _has_column(inspector, "vehicle_ownerships", "owned_from"):
        op.drop_column("vehicle_ownerships", "owned_from")
        inspector = inspect(bind)
    if _has_column(inspector, "vehicle_ownerships", "ownership_origin"):
        op.drop_column("vehicle_ownerships", "ownership_origin")
