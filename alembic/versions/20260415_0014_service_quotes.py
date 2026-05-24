"""service quotes

Revision ID: 20260415_0014
Revises: 20260415_0013
Create Date: 2026-04-15 18:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260415_0014"
down_revision = "20260415_0013"
branch_labels = None
depends_on = None


def _column_names(inspector, table_name: str) -> set[str]:
    return {str(col.get("name")) for col in inspector.get_columns(table_name) if col.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "service_quotes" not in tables:
        op.create_table(
            "service_quotes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("service_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("service_work_orders.id"), nullable=True),
            sa.Column("service_record_id", sa.Integer(), nullable=True),
            sa.Column("items_json", sa.Text(), nullable=True),
            sa.Column("labor_hours", sa.Float(), nullable=True),
            sa.Column("labor_rate", sa.Float(), nullable=True),
            sa.Column("total_price", sa.Float(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "service_quote_audit_logs" not in tables:
        op.create_table(
            "service_quote_audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("quote_id", sa.Integer(), sa.ForeignKey("service_quotes.id"), nullable=False),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
            sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False, server_default="update"),
            sa.Column("previous_snapshot_json", sa.Text(), nullable=False),
            sa.Column("new_snapshot_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "service_records" in tables:
        service_record_columns = _column_names(inspector, "service_records")
        if "quote_id" not in service_record_columns:
            op.add_column("service_records", sa.Column("quote_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "service_quote_audit_logs" in tables:
        op.drop_table("service_quote_audit_logs")
        tables = set(inspect(bind).get_table_names())
    if "service_quotes" in tables:
        op.drop_table("service_quotes")
