"""service invoices (phase 1)

Revision ID: 20260417_0017
Revises: 20260416_0016
Create Date: 2026-04-17 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "20260417_0017"
down_revision = "20260416_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "service_invoice_counters" not in tables:
        op.create_table(
            "service_invoice_counters",
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), primary_key=True),
            sa.Column("next_seq", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "service_invoices" not in tables:
        op.create_table(
            "service_invoices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("service_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=True),
            sa.Column("invoice_number", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("subtotal", sa.Float(), nullable=False, server_default="0"),
            sa.Column("tax_total", sa.Float(), nullable=False, server_default="0"),
            sa.Column("total", sa.Float(), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(length=8), nullable=False, server_default="CZK"),
            sa.Column("issued_at", sa.DateTime(), nullable=True),
            sa.Column("due_at", sa.DateTime(), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_service_invoices_tenant_id", "service_invoices", ["tenant_id"])
        op.create_index("ix_service_invoices_service_id", "service_invoices", ["service_id"])
        op.create_index("ix_service_invoices_customer_id", "service_invoices", ["customer_id"])
        op.create_index("ix_service_invoices_status", "service_invoices", ["status"])
        op.create_index("uq_service_invoices_invoice_number", "service_invoices", ["invoice_number"], unique=True)

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "service_invoice_lines" not in tables:
        op.create_table(
            "service_invoice_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("service_invoices.id"), nullable=False),
            sa.Column("description", sa.String(length=512), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False, server_default="1"),
            sa.Column("unit", sa.String(length=32), nullable=False, server_default="ks"),
            sa.Column("unit_price", sa.Float(), nullable=False, server_default="0"),
            sa.Column("tax_rate", sa.Float(), nullable=False, server_default="0"),
            sa.Column("line_total", sa.Float(), nullable=False, server_default="0"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_service_invoice_lines_invoice_id", "service_invoice_lines", ["invoice_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "service_invoice_lines" in tables:
        op.drop_table("service_invoice_lines")
    if "service_invoices" in tables:
        op.drop_table("service_invoices")
    if "service_invoice_counters" in tables:
        op.drop_table("service_invoice_counters")
