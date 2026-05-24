"""public quote access

Revision ID: 20260415_0015
Revises: 20260415_0014
Create Date: 2026-04-15 19:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260415_0015"
down_revision = "20260415_0014"
branch_labels = None
depends_on = None


def _column_names(inspector, table_name: str) -> set[str]:
    return {str(col.get("name")) for col in inspector.get_columns(table_name) if col.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "service_quote_access_tokens" not in tables:
        op.create_table(
            "service_quote_access_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("quote_id", sa.Integer(), sa.ForeignKey("service_quotes.id"), nullable=False),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("token", sa.String(length=255), nullable=False),
            sa.Column("issued_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("last_access_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("token", name="uq_service_quote_access_tokens_token"),
        )

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "service_quote_access_logs" not in tables:
        op.create_table(
            "service_quote_access_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("quote_id", sa.Integer(), sa.ForeignKey("service_quotes.id"), nullable=False),
            sa.Column("quote_access_token_id", sa.Integer(), sa.ForeignKey("service_quote_access_tokens.id"), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("remote_addr", sa.String(length=128), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    inspector = inspect(bind)
    if "service_quotes" in set(inspector.get_table_names()):
        columns = _column_names(inspector, "service_quotes")
        if "approved_at" not in columns:
            op.add_column("service_quotes", sa.Column("approved_at", sa.DateTime(), nullable=True))
        if "rejected_at" not in columns:
            op.add_column("service_quotes", sa.Column("rejected_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "service_quote_access_logs" in tables:
        op.drop_table("service_quote_access_logs")
        tables = set(inspect(bind).get_table_names())
    if "service_quote_access_tokens" in tables:
        op.drop_table("service_quote_access_tokens")
