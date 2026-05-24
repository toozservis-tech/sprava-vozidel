"""Customer workspace entitlements (user + service UI / API access).

Revision ID: 20260428_0025
Revises: 20260426_0024
Create Date: 2026-04-28 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "20260428_0025"
down_revision = "20260426_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("workspace_entitlements", sa.Text(), nullable=True),
    )
    op.add_column(
        "customers",
        sa.Column("workspace_ui_default", sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("customers", "workspace_ui_default")
    op.drop_column("customers", "workspace_entitlements")
