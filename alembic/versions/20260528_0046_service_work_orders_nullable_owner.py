"""nullable owner on service work orders for unowned vehicles

Revision ID: 20260528_0046
Revises: 20260526_0045
Create Date: 2026-05-28 14:00:00.000000

Nedestruktivní migrace. Před produkčním nasazením:
    pg_dump "$DATABASE_URL" --format=custom --file="backup_before_20260528_0046.dump"

Umožňuje zakázky bez majitele (service_provisioned_unowned). Existující řádky
mají owner_customer_id vyplněné; rollback nastaví NOT NULL pouze pokud žádný NULL.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "20260528_0046"
down_revision = "20260526_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("service_work_orders") as batch_op:
            batch_op.alter_column(
                "owner_customer_id",
                existing_type=sa.Integer(),
                nullable=True,
            )
        return
    inspector = inspect(bind)
    if "service_work_orders" not in set(inspector.get_table_names()):
        return
    columns = {col["name"]: col for col in inspector.get_columns("service_work_orders")}
    owner_col = columns.get("owner_customer_id")
    if owner_col and owner_col.get("nullable") is True:
        return
    op.alter_column(
        "service_work_orders",
        "owner_customer_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        null_count = bind.execute(
            text("SELECT COUNT(*) FROM service_work_orders WHERE owner_customer_id IS NULL")
        ).scalar()
        if int(null_count or 0) > 0:
            raise RuntimeError(
                "Rollback 20260528_0046 blocked: service_work_orders contains rows with NULL owner_customer_id."
            )
        with op.batch_alter_table("service_work_orders") as batch_op:
            batch_op.alter_column(
                "owner_customer_id",
                existing_type=sa.Integer(),
                nullable=False,
            )
        return
    inspector = inspect(bind)
    if "service_work_orders" not in set(inspector.get_table_names()):
        return
    null_count = bind.execute(
        text("SELECT COUNT(*) FROM service_work_orders WHERE owner_customer_id IS NULL")
    ).scalar()
    if int(null_count or 0) > 0:
        raise RuntimeError(
            "Rollback 20260528_0046 blocked: service_work_orders contains rows with NULL owner_customer_id."
        )
    op.alter_column(
        "service_work_orders",
        "owner_customer_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
