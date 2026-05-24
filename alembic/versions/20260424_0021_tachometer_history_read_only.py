"""Add read_only flag to tachometer history entries.

Revision ID: 20260424_0021
Revises: 20260421_0020_customer_admin_ordinal
Create Date: 2026-04-24 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "20260424_0021"
down_revision = "20260421_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vehicle_tachometer_history_entries",
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(
        "ix_vehicle_tachometer_history_entries_read_only",
        "vehicle_tachometer_history_entries",
        ["read_only"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_vehicle_tachometer_history_entries_read_only", table_name="vehicle_tachometer_history_entries")
    op.drop_column("vehicle_tachometer_history_entries", "read_only")
