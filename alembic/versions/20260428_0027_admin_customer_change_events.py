"""Admin: historie změn účtu uživatele + e-mailová notifikace (výběr položek).

Revision ID: 20260428_0027
Revises: 20260428_0026
Create Date: 2026-04-28 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "20260428_0027"
down_revision = "20260428_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_customer_change_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("admin_email", sa.String(length=255), nullable=True, index=True),
        sa.Column("change_key", sa.String(length=128), nullable=False, index=True),
        sa.Column("summary_line", sa.Text(), nullable=False),
        sa.Column("detail_text", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"), index=True),
        sa.Column("notified_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("notified_to_email", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_admin_customer_change_events_customer_pending",
        "admin_customer_change_events",
        ["customer_id", "notified_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_admin_customer_change_events_customer_pending", table_name="admin_customer_change_events")
    op.drop_table("admin_customer_change_events")
