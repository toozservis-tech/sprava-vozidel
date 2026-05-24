"""initial user trial fields

Revision ID: 20260522_0042
Revises: 20260516_0041
Create Date: 2026-05-22 05:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "20260522_0042"
down_revision = "20260516_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("licenses")}

    if "trial_started_at" not in cols:
        op.add_column("licenses", sa.Column("trial_started_at", sa.DateTime(), nullable=True))
    if "trial_ends_at" not in cols:
        op.add_column("licenses", sa.Column("trial_ends_at", sa.DateTime(), nullable=True))
    if "trial_used_at" not in cols:
        op.add_column("licenses", sa.Column("trial_used_at", sa.DateTime(), nullable=True))
    if "trial_source" not in cols:
        op.add_column("licenses", sa.Column("trial_source", sa.String(length=64), nullable=True))
    if "trial_plan" not in cols:
        op.add_column("licenses", sa.Column("trial_plan", sa.String(length=32), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("licenses")}

    with op.batch_alter_table("licenses") as batch_op:
        if "trial_plan" in cols:
            batch_op.drop_column("trial_plan")
        if "trial_source" in cols:
            batch_op.drop_column("trial_source")
        if "trial_used_at" in cols:
            batch_op.drop_column("trial_used_at")
        if "trial_ends_at" in cols:
            batch_op.drop_column("trial_ends_at")
        if "trial_started_at" in cols:
            batch_op.drop_column("trial_started_at")
