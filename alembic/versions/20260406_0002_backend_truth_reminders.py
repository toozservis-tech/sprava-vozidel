"""backend truth reconciliation for reminders

Revision ID: 20260406_0002
Revises: 20260326_0001
Create Date: 2026-04-06 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260406_0002"
down_revision = "20260326_0001"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {str(col.get("name")) for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _has_column(inspector, "reminders", "recurrence_group_id"):
        op.add_column("reminders", sa.Column("recurrence_group_id", sa.String(), nullable=True))
    if not _has_column(inspector, "reminders", "recurrence_index"):
        op.add_column(
            "reminders",
            sa.Column("recurrence_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )
    if not _has_column(inspector, "reminders", "repeat_interval_days"):
        op.add_column("reminders", sa.Column("repeat_interval_days", sa.Integer(), nullable=True))

    inspector = inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("reminders")}
    if "ix_reminders_recurrence_group_id" not in indexes:
        op.create_index("ix_reminders_recurrence_group_id", "reminders", ["recurrence_group_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("reminders")}
    if "ix_reminders_recurrence_group_id" in indexes:
        op.drop_index("ix_reminders_recurrence_group_id", table_name="reminders")

    inspector = inspect(bind)
    if _has_column(inspector, "reminders", "repeat_interval_days"):
        op.drop_column("reminders", "repeat_interval_days")
    if _has_column(inspector, "reminders", "recurrence_index"):
        op.drop_column("reminders", "recurrence_index")
    if _has_column(inspector, "reminders", "recurrence_group_id"):
        op.drop_column("reminders", "recurrence_group_id")
