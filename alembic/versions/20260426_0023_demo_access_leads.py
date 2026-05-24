"""Demo access leads (email gate + IP for public demo).

Revision ID: 20260426_0023
Revises: 20260426_0022
Create Date: 2026-04-26 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "20260426_0023"
down_revision = "20260426_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_access_leads",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("visitor_email", sa.String(length=255), nullable=False),
        sa.Column("client_ip", sa.String(length=128), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("contact_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_demo_access_leads_visitor_email", "demo_access_leads", ["visitor_email"], unique=False)
    op.create_index("ix_demo_access_leads_client_ip", "demo_access_leads", ["client_ip"], unique=False)
    op.create_index("ix_demo_access_leads_created_at", "demo_access_leads", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_demo_access_leads_created_at", table_name="demo_access_leads")
    op.drop_index("ix_demo_access_leads_client_ip", table_name="demo_access_leads")
    op.drop_index("ix_demo_access_leads_visitor_email", table_name="demo_access_leads")
    op.drop_table("demo_access_leads")
