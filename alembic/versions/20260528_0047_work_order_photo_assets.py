"""work order photo columns on vehicle_photo_assets

Revision ID: 20260528_0047
Revises: 20260528_0046
Create Date: 2026-05-28 18:00:00.000000

Nedestruktivní migrace. Před produkčním nasazením zálohujte DB, např.:
    cp /opt/toozhub2/data/vehicles.db /opt/toozhub2/data/vehicles.db.backup_before_20260528_0047
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260528_0047"
down_revision = "20260528_0046"
branch_labels = None
depends_on = None


def _add_columns() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "vehicle_photo_assets" not in set(inspector.get_table_names()):
        return
    existing = {col["name"] for col in inspector.get_columns("vehicle_photo_assets")}
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("vehicle_photo_assets") as batch_op:
            if "work_order_id" not in existing:
                batch_op.add_column(sa.Column("work_order_id", sa.Integer(), nullable=True))
            if "visibility_scope" not in existing:
                batch_op.add_column(
                    sa.Column(
                        "visibility_scope",
                        sa.String(length=32),
                        nullable=False,
                        server_default="service_private",
                    )
                )
            if "service_customer_id" not in existing:
                batch_op.add_column(sa.Column("service_customer_id", sa.Integer(), nullable=True))
        return
    if "work_order_id" not in existing:
        op.add_column("vehicle_photo_assets", sa.Column("work_order_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_vehicle_photo_assets_work_order_id",
            "vehicle_photo_assets",
            "service_work_orders",
            ["work_order_id"],
            ["id"],
        )
        op.create_index("ix_vehicle_photo_assets_work_order_id", "vehicle_photo_assets", ["work_order_id"])
    if "visibility_scope" not in existing:
        op.add_column(
            "vehicle_photo_assets",
            sa.Column("visibility_scope", sa.String(length=32), nullable=False, server_default="service_private"),
        )
        op.create_index("ix_vehicle_photo_assets_visibility_scope", "vehicle_photo_assets", ["visibility_scope"])
    if "service_customer_id" not in existing:
        op.add_column("vehicle_photo_assets", sa.Column("service_customer_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_vehicle_photo_assets_service_customer_id",
            "vehicle_photo_assets",
            "customers",
            ["service_customer_id"],
            ["id"],
        )
        op.create_index("ix_vehicle_photo_assets_service_customer_id", "vehicle_photo_assets", ["service_customer_id"])


def upgrade() -> None:
    _add_columns()


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "vehicle_photo_assets" not in set(inspector.get_table_names()):
        return
    existing = {col["name"] for col in inspector.get_columns("vehicle_photo_assets")}
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("vehicle_photo_assets") as batch_op:
            if "service_customer_id" in existing:
                batch_op.drop_column("service_customer_id")
            if "visibility_scope" in existing:
                batch_op.drop_column("visibility_scope")
            if "work_order_id" in existing:
                batch_op.drop_column("work_order_id")
        return
    if "service_customer_id" in existing:
        op.drop_index("ix_vehicle_photo_assets_service_customer_id", table_name="vehicle_photo_assets")
        op.drop_constraint("fk_vehicle_photo_assets_service_customer_id", "vehicle_photo_assets", type_="foreignkey")
        op.drop_column("vehicle_photo_assets", "service_customer_id")
    if "visibility_scope" in existing:
        op.drop_index("ix_vehicle_photo_assets_visibility_scope", table_name="vehicle_photo_assets")
        op.drop_column("vehicle_photo_assets", "visibility_scope")
    if "work_order_id" in existing:
        op.drop_index("ix_vehicle_photo_assets_work_order_id", table_name="vehicle_photo_assets")
        op.drop_constraint("fk_vehicle_photo_assets_work_order_id", "vehicle_photo_assets", type_="foreignkey")
        op.drop_column("vehicle_photo_assets", "work_order_id")
