"""service parts inventory

Revision ID: 20260529_0050
Revises: 20260529_0049
Create Date: 2026-05-29 20:55:00.000000

Nedestruktivni migrace. Pridava sklad servisnich dilu a vazbu na polozky zakazky.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260529_0050"
down_revision = "20260529_0049"
branch_labels = None
depends_on = None


def _table_exists(inspector, name: str) -> bool:
    return name in set(inspector.get_table_names())


def _column_exists(inspector, table: str, column: str) -> bool:
    if not _table_exists(inspector, table):
        return False
    return column in {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _table_exists(inspector, "service_inventory_items"):
        op.create_table(
            "service_inventory_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_tenant_id", sa.Integer(), nullable=False),
            sa.Column("service_customer_id", sa.Integer(), nullable=False),
            sa.Column("internal_code", sa.String(length=128), nullable=True),
            sa.Column("name", sa.String(length=512), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("brand", sa.String(length=255), nullable=True),
            sa.Column("supplier_name", sa.String(length=255), nullable=True),
            sa.Column("unit", sa.String(length=32), nullable=False, server_default="ks"),
            sa.Column("quantity_on_hand", sa.Float(), nullable=False, server_default="0"),
            sa.Column("min_quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("purchase_price", sa.Float(), nullable=True),
            sa.Column("sale_price", sa.Float(), nullable=True),
            sa.Column("vat_rate", sa.Float(), nullable=True),
            sa.Column("location", sa.String(length=255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["service_customer_id"], ["customers.id"]),
            sa.ForeignKeyConstraint(["service_tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in (
            "service_tenant_id",
            "service_customer_id",
            "internal_code",
            "is_active",
            "created_at",
        ):
            op.create_index(f"ix_service_inventory_items_{column}", "service_inventory_items", [column])

    if not _table_exists(inspector, "service_inventory_movements"):
        op.create_table(
            "service_inventory_movements",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("service_tenant_id", sa.Integer(), nullable=False),
            sa.Column("inventory_item_id", sa.Integer(), nullable=False),
            sa.Column("work_order_id", sa.Integer(), nullable=True),
            sa.Column("work_order_item_id", sa.Integer(), nullable=True),
            sa.Column("movement_type", sa.String(length=32), nullable=False),
            sa.Column("quantity_delta", sa.Float(), nullable=False),
            sa.Column("quantity_before", sa.Float(), nullable=False),
            sa.Column("quantity_after", sa.Float(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("actor_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["actor_id"], ["customers.id"]),
            sa.ForeignKeyConstraint(["inventory_item_id"], ["service_inventory_items.id"]),
            sa.ForeignKeyConstraint(["service_tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["work_order_id"], ["service_work_orders.id"]),
            sa.ForeignKeyConstraint(["work_order_item_id"], ["service_work_order_items.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in (
            "service_tenant_id",
            "inventory_item_id",
            "work_order_id",
            "work_order_item_id",
            "movement_type",
            "actor_id",
            "created_at",
        ):
            op.create_index(f"ix_service_inventory_movements_{column}", "service_inventory_movements", [column])

    inspector = inspect(bind)
    if not _column_exists(inspector, "service_work_order_items", "inventory_item_id"):
        with op.batch_alter_table("service_work_order_items") as batch_op:
            batch_op.add_column(sa.Column("inventory_item_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_service_work_order_items_inventory_item_id",
                "service_inventory_items",
                ["inventory_item_id"],
                ["id"],
            )
            batch_op.create_index("ix_service_work_order_items_inventory_item_id", ["inventory_item_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _column_exists(inspector, "service_work_order_items", "inventory_item_id"):
        with op.batch_alter_table("service_work_order_items") as batch_op:
            batch_op.drop_index("ix_service_work_order_items_inventory_item_id")
            batch_op.drop_constraint("fk_service_work_order_items_inventory_item_id", type_="foreignkey")
            batch_op.drop_column("inventory_item_id")

    if _table_exists(inspector, "service_inventory_movements"):
        for column in (
            "created_at",
            "actor_id",
            "movement_type",
            "work_order_item_id",
            "work_order_id",
            "inventory_item_id",
            "service_tenant_id",
        ):
            op.drop_index(f"ix_service_inventory_movements_{column}", table_name="service_inventory_movements")
        op.drop_table("service_inventory_movements")

    if _table_exists(inspector, "service_inventory_items"):
        for column in (
            "created_at",
            "is_active",
            "internal_code",
            "service_customer_id",
            "service_tenant_id",
        ):
            op.drop_index(f"ix_service_inventory_items_{column}", table_name="service_inventory_items")
        op.drop_table("service_inventory_items")
