"""Customer.partner_public_profile JSON text for partner directory detail.

Revision ID: 20260504_0032
Revises: 20260504_0031
Create Date: 2026-05-04 18:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20260504_0032"
down_revision = "20260504_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("customers")}
    if "partner_public_profile" not in cols:
        op.add_column(
            "customers",
            sa.Column("partner_public_profile", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("customers")}
    if "partner_public_profile" in cols:
        op.drop_column("customers", "partner_public_profile")
