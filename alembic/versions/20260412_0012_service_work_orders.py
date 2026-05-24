"""service work orders dashboard

Revision ID: 20260412_0012
Revises: 20260407_0011
Create Date: 2026-04-12 10:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260412_0012"
down_revision = "20260407_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "service_work_orders" not in tables:
        op.create_table(
            "service_work_orders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("service_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("owner_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
            sa.Column("technician_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("source_type", sa.String(length=32), nullable=False, server_default="manual"),
            sa.Column("source_reservation_id", sa.Integer(), sa.ForeignKey("reservations.id"), nullable=True),
            sa.Column("source_document_id", sa.Integer(), sa.ForeignKey("service_document_ingestions.id"), nullable=True),
            sa.Column("source_intake_id", sa.Integer(), sa.ForeignKey("service_intakes.id"), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=64), nullable=False, server_default="awaiting_client_approval"),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "service_work_order_audit_logs" not in tables:
        op.create_table(
            "service_work_order_audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("service_work_orders.id"), nullable=False),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
            sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False, server_default="update"),
            sa.Column("previous_snapshot_json", sa.Text(), nullable=False),
            sa.Column("new_snapshot_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "service_work_order_audit_logs" in tables:
        op.drop_table("service_work_order_audit_logs")
        tables = set(inspect(bind).get_table_names())
    if "service_work_orders" in tables:
        op.drop_table("service_work_orders")
