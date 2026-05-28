"""service work order billing contacts

Revision ID: 20260528_0048
Revises: 20260528_0047
Create Date: 2026-05-28 19:00:00.000000

Nedestruktivní migrace. Před produkčním nasazením zálohujte DB.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260528_0048"
down_revision = "20260528_0047"
branch_labels = None
depends_on = None


def _table_exists(inspector, name: str) -> bool:
    return name in set(inspector.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _table_exists(inspector, "service_work_order_billing_contacts"):
        return

    op.create_table(
        "service_work_order_billing_contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("service_customer_id", sa.Integer(), nullable=False),
        sa.Column("work_order_id", sa.Integer(), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("street", sa.String(length=255), nullable=True),
        sa.Column("street_number", sa.String(length=32), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("zip", sa.String(length=16), nullable=True),
        sa.Column("ico", sa.String(length=32), nullable=True),
        sa.Column("dic", sa.String(length=32), nullable=True),
        sa.Column("billing_customer_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["billing_customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["service_customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["service_work_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("work_order_id", name="uq_service_work_order_billing_contact_work_order"),
    )
    op.create_index(
        "ix_service_work_order_billing_contacts_tenant_id",
        "service_work_order_billing_contacts",
        ["tenant_id"],
    )
    op.create_index(
        "ix_service_work_order_billing_contacts_service_customer_id",
        "service_work_order_billing_contacts",
        ["service_customer_id"],
    )
    op.create_index(
        "ix_service_work_order_billing_contacts_work_order_id",
        "service_work_order_billing_contacts",
        ["work_order_id"],
    )
    op.create_index(
        "ix_service_work_order_billing_contacts_vehicle_id",
        "service_work_order_billing_contacts",
        ["vehicle_id"],
    )
    op.create_index(
        "ix_service_work_order_billing_contacts_billing_customer_id",
        "service_work_order_billing_contacts",
        ["billing_customer_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not _table_exists(inspector, "service_work_order_billing_contacts"):
        return
    op.drop_table("service_work_order_billing_contacts")
