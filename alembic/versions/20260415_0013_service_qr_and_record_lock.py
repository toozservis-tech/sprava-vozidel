"""service qr security and record lock

Revision ID: 20260415_0013
Revises: 20260412_0012
Create Date: 2026-04-15 12:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260415_0013"
down_revision = "20260412_0012"
branch_labels = None
depends_on = None


def _column_names(inspector, table_name: str) -> set[str]:
    return {str(col.get("name")) for col in inspector.get_columns(table_name) if col.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "vehicle_qr_tokens" not in tables:
        op.create_table(
            "vehicle_qr_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("token", sa.String(length=255), nullable=False),
            sa.Column("public_mode", sa.String(length=32), nullable=False, server_default="basic"),
            sa.Column("explicit_full_consent", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("issued_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("last_access_at", sa.DateTime(), nullable=True),
            sa.Column("signature_hash", sa.String(length=128), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("token", name="uq_vehicle_qr_tokens_token"),
        )

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "vehicle_qr_access_logs" not in tables:
        op.create_table(
            "vehicle_qr_access_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
            sa.Column("qr_token_id", sa.Integer(), sa.ForeignKey("vehicle_qr_tokens.id"), nullable=False),
            sa.Column("access_path", sa.String(length=255), nullable=True),
            sa.Column("access_status", sa.String(length=64), nullable=False, server_default="ok"),
            sa.Column("public_mode", sa.String(length=32), nullable=False, server_default="basic"),
            sa.Column("access_signature_valid", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("remote_addr", sa.String(length=128), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    inspector = inspect(bind)
    service_record_columns = _column_names(inspector, "service_records") if "service_records" in tables else set()
    if "service_records" in tables:
        # SQLite: add_column s ForeignKey vyžaduje batch režim (copy-and-move), jinak NotImplementedError.
        cols = service_record_columns
        if any(
            name not in cols
            for name in (
                "customer_id",
                "service_id",
                "work_order_id",
                "record_status",
                "service_type",
                "recommended_next_service_text",
                "recommended_next_service_date",
                "notes_customer_visible",
                "total_price",
                "updated_at",
            )
        ):
            with op.batch_alter_table("service_records") as batch_op:
                if "customer_id" not in cols:
                    batch_op.add_column(sa.Column("customer_id", sa.Integer(), nullable=True))
                    batch_op.create_foreign_key(
                        "fk_service_records_customer_id",
                        "customers",
                        ["customer_id"],
                        ["id"],
                    )
                if "service_id" not in cols:
                    batch_op.add_column(sa.Column("service_id", sa.Integer(), nullable=True))
                    batch_op.create_foreign_key(
                        "fk_service_records_service_customer_id",
                        "customers",
                        ["service_id"],
                        ["id"],
                    )
                if "work_order_id" not in cols:
                    batch_op.add_column(sa.Column("work_order_id", sa.Integer(), nullable=True))
                    batch_op.create_foreign_key(
                        "fk_service_records_work_order_id",
                        "service_work_orders",
                        ["work_order_id"],
                        ["id"],
                    )
                if "record_status" not in cols:
                    batch_op.add_column(
                        sa.Column(
                            "record_status",
                            sa.String(length=32),
                            nullable=False,
                            server_default="draft",
                        )
                    )
                if "service_type" not in cols:
                    batch_op.add_column(sa.Column("service_type", sa.String(length=64), nullable=True))
                if "recommended_next_service_text" not in cols:
                    batch_op.add_column(sa.Column("recommended_next_service_text", sa.Text(), nullable=True))
                if "recommended_next_service_date" not in cols:
                    batch_op.add_column(sa.Column("recommended_next_service_date", sa.Date(), nullable=True))
                if "notes_customer_visible" not in cols:
                    batch_op.add_column(sa.Column("notes_customer_visible", sa.Text(), nullable=True))
                if "total_price" not in cols:
                    batch_op.add_column(sa.Column("total_price", sa.Float(), nullable=True))
                if "updated_at" not in cols:
                    batch_op.add_column(
                        sa.Column(
                            "updated_at",
                            sa.DateTime(),
                            nullable=False,
                            server_default=sa.text("CURRENT_TIMESTAMP"),
                        )
                    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "vehicle_qr_access_logs" in tables:
        op.drop_table("vehicle_qr_access_logs")
        tables = set(inspect(bind).get_table_names())
    if "vehicle_qr_tokens" in tables:
        op.drop_table("vehicle_qr_tokens")
