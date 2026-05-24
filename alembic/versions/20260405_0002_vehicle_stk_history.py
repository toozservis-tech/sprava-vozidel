"""add vehicle stk history and audit tables

Revision ID: 20260405_0002
Revises: 20260326_0001
Create Date: 2026-04-05 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260405_0002"
down_revision = "20260326_0001"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in set(inspector.get_table_names())


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return column_name in {str(col.get("name")) for col in inspector.get_columns(table_name)}


def _add_column_if_missing(inspector, table_name: str, column: sa.Column) -> None:
    if _has_column(inspector, table_name, column.name):
        return
    op.add_column(table_name, column)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    for column in [
        sa.Column("latest_stk_odometer_km", sa.Integer(), nullable=True),
        sa.Column("latest_stk_odometer_date", sa.DateTime(), nullable=True),
        sa.Column("latest_stk_sync_at", sa.DateTime(), nullable=True),
        sa.Column("latest_stk_source", sa.String(), nullable=True),
        sa.Column("latest_stk_import_status", sa.String(), nullable=True),
    ]:
        _add_column_if_missing(inspector, "vehicles", column)

    inspector = inspect(bind)
    if not _has_table(inspector, "vehicle_inspection_histories"):
        op.create_table(
            "vehicle_inspection_histories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False, index=True),
            sa.Column("vin", sa.String(), nullable=False, index=True),
            sa.Column("inspection_date", sa.DateTime(), nullable=True, index=True),
            sa.Column("inspection_type", sa.String(), nullable=True, index=True),
            sa.Column("inspection_kind", sa.String(), nullable=True),
            sa.Column("odometer_km", sa.Integer(), nullable=True, index=True),
            sa.Column("protocol_number", sa.String(), nullable=True, index=True),
            sa.Column("result_label", sa.String(), nullable=True),
            sa.Column("defects_text", sa.Text(), nullable=True),
            sa.Column("note_text", sa.Text(), nullable=True),
            sa.Column("source", sa.String(), nullable=False, index=True),
            sa.Column("source_hash", sa.String(), nullable=False, index=True),
            sa.Column("imported_at", sa.DateTime(), nullable=False),
            sa.Column("raw_payload_json", sa.Text(), nullable=True),
            sa.UniqueConstraint("vehicle_id", "source_hash", name="uq_vehicle_inspection_history_source_hash"),
        )

    inspector = inspect(bind)
    if not _has_table(inspector, "vehicle_stk_import_audit_logs"):
        op.create_table(
            "vehicle_stk_import_audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False, index=True),
            sa.Column("vin", sa.String(), nullable=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
            sa.Column("action", sa.String(), nullable=False, index=True),
            sa.Column("status", sa.String(), nullable=False, index=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, index=True),
        )


def downgrade() -> None:
    pass
