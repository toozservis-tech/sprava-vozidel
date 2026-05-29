"""service work access

Revision ID: 20260529_0049
Revises: 20260528_0048
Create Date: 2026-05-29 12:00:00.000000

Nedestruktivni migrace. Pridava oddeleny jednorazovy pracovni pristup
servisu k vozidlu bez schvaleneho dlouhodobeho propojeni s majitelem.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260529_0049"
down_revision = "20260528_0048"
branch_labels = None
depends_on = None


def _table_exists(inspector, name: str) -> bool:
    return name in set(inspector.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _table_exists(inspector, "service_work_access"):
        return

    op.create_table(
        "service_work_access",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("service_customer_id", sa.Integer(), nullable=False),
        sa.Column("vehicle_id", sa.Integer(), nullable=False),
        sa.Column("owner_customer_id", sa.Integer(), nullable=True),
        sa.Column("work_order_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="manual"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by_customer_id", sa.Integer(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["owner_customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["service_customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["service_work_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_customer_id", "vehicle_id", name="uq_service_work_access_pair"),
    )
    for column in (
        "tenant_id",
        "service_customer_id",
        "vehicle_id",
        "owner_customer_id",
        "work_order_id",
        "status",
        "source",
        "created_by_customer_id",
    ):
        op.create_index(f"ix_service_work_access_{column}", "service_work_access", [column])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not _table_exists(inspector, "service_work_access"):
        return
    for column in (
        "created_by_customer_id",
        "source",
        "status",
        "work_order_id",
        "owner_customer_id",
        "vehicle_id",
        "service_customer_id",
        "tenant_id",
    ):
        index_name = f"ix_service_work_access_{column}"
        try:
            op.drop_index(index_name, table_name="service_work_access")
        except Exception:
            pass
    op.drop_table("service_work_access")
