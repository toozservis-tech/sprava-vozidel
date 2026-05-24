"""user preferences JSON column

Revision ID: 20260523_0043
Revises: 20260522_0044
Create Date: 2026-05-23 08:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "20260523_0043"
down_revision = "20260522_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("customers")}
    if "user_preferences" not in cols:
        op.add_column("customers", sa.Column("user_preferences", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("customers")}
    if "user_preferences" in cols:
        with op.batch_alter_table("customers") as batch_op:
            batch_op.drop_column("user_preferences")
