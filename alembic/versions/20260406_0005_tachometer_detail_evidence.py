"""tachometer detail evidence

Revision ID: 20260406_0005
Revises: 20260406_0004
Create Date: 2026-04-06 03:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260406_0005"
down_revision = "20260406_0004"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {str(col.get("name")) for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for column_name in [
        "findings_summary",
        "findings_items_json",
        "detail_snapshot_json",
        "source_detail_reference",
    ]:
        if not _has_column(inspector, "vehicle_tachometer_history_entries", column_name):
            op.add_column(
                "vehicle_tachometer_history_entries",
                sa.Column(column_name, sa.Text(), nullable=True),
            )
            inspector = inspect(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for column_name in [
        "source_detail_reference",
        "detail_snapshot_json",
        "findings_items_json",
        "findings_summary",
    ]:
        if _has_column(inspector, "vehicle_tachometer_history_entries", column_name):
            op.drop_column("vehicle_tachometer_history_entries", column_name)
            inspector = inspect(bind)
