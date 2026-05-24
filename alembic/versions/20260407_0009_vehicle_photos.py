"""vehicle_photos gallery table

Revision ID: 20260407_0009
Revises: 20260407_0008
Create Date: 2026-04-07 14:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260407_0009"
down_revision = "20260407_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "vehicle_photos" in tables:
        idx_names = {i.get("name") for i in inspector.get_indexes("vehicle_photos")}
        if "ix_vehicle_photos_vehicle_id" not in idx_names:
            op.create_index("ix_vehicle_photos_vehicle_id", "vehicle_photos", ["vehicle_id"])
        return
    op.create_table(
        "vehicle_photos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False, index=True),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    idx_after = {i.get("name") for i in inspect(bind).get_indexes("vehicle_photos")}
    if "ix_vehicle_photos_vehicle_id" not in idx_after:
        op.create_index("ix_vehicle_photos_vehicle_id", "vehicle_photos", ["vehicle_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "vehicle_photos" in inspector.get_table_names():
        op.drop_table("vehicle_photos")
