"""add vehicle report documents verification table

Revision ID: 20260405_0003
Revises: 20260405_0002
Create Date: 2026-04-05 21:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260405_0003"
down_revision = "20260405_0002"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in set(inspector.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _has_table(inspector, "vehicle_report_documents"):
        return

    op.create_table(
        "vehicle_report_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False, index=True),
        sa.Column("generated_by_user_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("document_type", sa.String(), nullable=False, index=True),
        sa.Column("export_mode", sa.String(), nullable=False, index=True),
        sa.Column("document_id", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("public_token", sa.String(), nullable=True, unique=True, index=True),
        sa.Column("verification_code", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("hash_sha256", sa.String(), nullable=False, index=True),
        sa.Column("payload_hash_sha256", sa.String(), nullable=False, index=True),
        sa.Column("verification_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(), nullable=False, server_default="valid", index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("schema_version", sa.String(), nullable=False, server_default="2.1"),
        sa.Column("finalized_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("finalized_by", sa.String(), nullable=True),
        sa.Column("replaced_by_document_id", sa.String(), nullable=True, index=True),
        sa.Column("issued_service_name", sa.String(), nullable=True),
        sa.Column("vehicle_brand", sa.String(), nullable=True),
        sa.Column("vehicle_model", sa.String(), nullable=True),
        sa.Column("vehicle_vin_masked", sa.String(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("vehicle_id", "export_mode", "version", name="uq_vehicle_report_document_version"),
    )


def downgrade() -> None:
    pass
