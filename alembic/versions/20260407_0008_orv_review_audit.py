"""ORV review audit JSON on vehicle_orv_scans

Revision ID: 20260407_0008
Revises: 20260406_0007
Create Date: 2026-04-07 12:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260407_0008"
down_revision = "20260406_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "vehicle_orv_scans" not in tables:
        return
    cols = {c["name"] for c in inspector.get_columns("vehicle_orv_scans")}
    if "orv_review_audit_json" not in cols:
        op.add_column(
            "vehicle_orv_scans",
            sa.Column("orv_review_audit_json", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "vehicle_orv_scans" not in tables:
        return
    cols = {c["name"] for c in inspector.get_columns("vehicle_orv_scans")}
    if "orv_review_audit_json" in cols:
        op.drop_column("vehicle_orv_scans", "orv_review_audit_json")
