"""vehicle orv scans

Revision ID: 20260406_0004
Revises: 20260406_0003
Create Date: 2026-04-06 01:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260406_0004"
down_revision = "20260406_0003"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {str(col.get("name")) for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    vehicle_columns = [
        ("orv_number", sa.String(), True),
        ("orv_scan_source", sa.String(), True),
        ("orv_front_image_path", sa.Text(), True),
        ("orv_back_image_path", sa.Text(), True),
        ("orv_scanned_at", sa.DateTime(), True),
        ("orv_confidence_json", sa.Text(), True),
        ("data_trust_state", sa.String(), True),
    ]
    for column_name, column_type, nullable in vehicle_columns:
        if not _has_column(inspector, "vehicles", column_name):
            op.add_column("vehicles", sa.Column(column_name, column_type, nullable=nullable))

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "vehicle_orv_scans" not in tables:
        op.create_table(
            "vehicle_orv_scans",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("initiated_by_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=True),
            sa.Column("source", sa.String(), nullable=False, server_default="ios_orv_scan"),
            sa.Column("status", sa.String(), nullable=False, server_default="processing"),
            sa.Column("trust_state", sa.String(), nullable=False, server_default="scanned_unverified"),
            sa.Column("use_owner_data", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("front_captured", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("back_captured", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("orv_number", sa.String(), nullable=True),
            sa.Column("front_image_path", sa.Text(), nullable=True),
            sa.Column("back_image_path", sa.Text(), nullable=True),
            sa.Column("front_image_hash", sa.String(), nullable=True),
            sa.Column("back_image_hash", sa.String(), nullable=True),
            sa.Column("front_ocr_text", sa.Text(), nullable=True),
            sa.Column("back_ocr_text", sa.Text(), nullable=True),
            sa.Column("parsed_vehicle_json", sa.Text(), nullable=True),
            sa.Column("parsed_owner_json", sa.Text(), nullable=True),
            sa.Column("confidence_json", sa.Text(), nullable=True),
            sa.Column("warnings_json", sa.Text(), nullable=True),
            sa.Column("missing_fields_json", sa.Text(), nullable=True),
            sa.Column("extracted_fields_json", sa.Text(), nullable=True),
            sa.Column("manual_overrides_json", sa.Text(), nullable=True),
            sa.Column("processed_at", sa.DateTime(), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "vehicle_orv_scans" in tables:
        op.drop_table("vehicle_orv_scans")

    inspector = inspect(bind)
    for column_name in [
        "data_trust_state",
        "orv_confidence_json",
        "orv_scanned_at",
        "orv_back_image_path",
        "orv_front_image_path",
        "orv_scan_source",
        "orv_number",
    ]:
        if _has_column(inspector, "vehicles", column_name):
            op.drop_column("vehicles", column_name)
            inspector = inspect(bind)
