"""tachometer evidence layer

Revision ID: 20260406_0003
Revises: 20260406_0002
Create Date: 2026-04-06 00:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260406_0003"
down_revision = "20260406_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "vehicle_tachometer_history_entries" not in tables:
        op.create_table(
            "vehicle_tachometer_history_entries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False, index=True),
            sa.Column("check_date", sa.DateTime(), nullable=True, index=True),
            sa.Column("mileage_km", sa.Integer(), nullable=True),
            sa.Column("protocol_number", sa.String(), nullable=True, index=True),
            sa.Column("inspection_type", sa.String(), nullable=True),
            sa.Column("source", sa.String(), nullable=False, server_default="kontrolatachometru.cz"),
            sa.Column("status", sa.String(), nullable=False, server_default="imported", index=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("documents_json", sa.Text(), nullable=True),
            sa.Column("raw_payload_json", sa.Text(), nullable=True),
            sa.Column("imported_at", sa.DateTime(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "vehicle_id",
                "check_date",
                "mileage_km",
                "protocol_number",
                name="uq_vehicle_tachometer_history_entry",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "vehicle_tachometer_history_entries" in tables:
        op.drop_table("vehicle_tachometer_history_entries")
