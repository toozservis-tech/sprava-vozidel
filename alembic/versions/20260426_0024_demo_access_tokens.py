"""Demo access magic links (email + IP-bound one-time tokens).

Revision ID: 20260426_0024
Revises: 20260426_0023
Create Date: 2026-04-26 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "20260426_0024"
down_revision = "20260426_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_access_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("visitor_email", sa.String(length=255), nullable=False),
        sa.Column("request_ip", sa.String(length=128), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("contact_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_demo_access_tokens_token_hash", "demo_access_tokens", ["token_hash"], unique=True)
    op.create_index("ix_demo_access_tokens_visitor_email", "demo_access_tokens", ["visitor_email"], unique=False)
    op.create_index("ix_demo_access_tokens_created_at", "demo_access_tokens", ["created_at"], unique=False)
    op.create_index("ix_demo_access_tokens_expires_at", "demo_access_tokens", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_demo_access_tokens_expires_at", table_name="demo_access_tokens")
    op.drop_index("ix_demo_access_tokens_created_at", table_name="demo_access_tokens")
    op.drop_index("ix_demo_access_tokens_visitor_email", table_name="demo_access_tokens")
    op.drop_index("ix_demo_access_tokens_token_hash", table_name="demo_access_tokens")
    op.drop_table("demo_access_tokens")
