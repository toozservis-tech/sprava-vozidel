"""service map locations catalog

Revision ID: 20260524_0044
Revises: 20260523_0043
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "20260524_0044"
down_revision = "20260523_0043"
branch_labels = None
depends_on = None


def _create_index_if_missing(table: str, name: str, columns: list[str], unique: bool = False) -> None:
    bind = op.get_bind()
    indexes = {idx["name"] for idx in inspect(bind).get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "service_locations" not in tables:
        op.create_table(
            "service_locations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_type", sa.String(length=32), nullable=False),
            sa.Column("source_external_id", sa.String(length=128), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("normalized_name", sa.String(length=255), nullable=True),
            sa.Column("category", sa.String(length=32), nullable=False),
            sa.Column("lat", sa.Float(), nullable=False),
            sa.Column("lng", sa.Float(), nullable=False),
            sa.Column("address_text", sa.String(length=512), nullable=True),
            sa.Column("street", sa.String(length=255), nullable=True),
            sa.Column("city", sa.String(length=128), nullable=True),
            sa.Column("postal_code", sa.String(length=16), nullable=True),
            sa.Column("region", sa.String(length=128), nullable=True),
            sa.Column("district", sa.String(length=128), nullable=True),
            sa.Column("phone", sa.String(length=64), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("website", sa.String(length=512), nullable=True),
            sa.Column("opening_hours", sa.Text(), nullable=True),
            sa.Column("services_json", sa.Text(), nullable=True),
            sa.Column("vehicle_scope_json", sa.Text(), nullable=True),
            sa.Column("verification_status", sa.String(length=32), nullable=False, server_default="imported"),
            sa.Column("confidence_score", sa.Float(), nullable=True),
            sa.Column("last_imported_at", sa.DateTime(), nullable=True),
            sa.Column("last_verified_at", sa.DateTime(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("linked_service_tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if "service_location_sources" not in tables:
        op.create_table(
            "service_location_sources",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("service_location_id", sa.Integer(), sa.ForeignKey("service_locations.id"), nullable=False),
            sa.Column("source_type", sa.String(length=32), nullable=False),
            sa.Column("source_external_id", sa.String(length=128), nullable=True),
            sa.Column("raw_payload_hash", sa.String(length=64), nullable=True),
            sa.Column("raw_payload_json", sa.Text(), nullable=True),
            sa.Column("import_batch_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if "service_location_claims" not in tables:
        op.create_table(
            "service_location_claims",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("service_location_id", sa.Integer(), sa.ForeignKey("service_locations.id"), nullable=False),
            sa.Column("service_tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("claim_status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("claim_method", sa.String(length=32), nullable=True),
            sa.Column("ico", sa.String(length=16), nullable=True),
            sa.Column("dic", sa.String(length=16), nullable=True),
            sa.Column("business_name", sa.String(length=255), nullable=True),
            sa.Column("submitted_by_user_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("approved_by_admin_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("submitted_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("fraud_flags_json", sa.Text(), nullable=True),
            sa.Column("audit_hash", sa.String(length=64), nullable=True),
        )

    if "service_location_reports" not in tables:
        op.create_table(
            "service_location_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("service_location_id", sa.Integer(), sa.ForeignKey("service_locations.id"), nullable=False),
            sa.Column("report_type", sa.String(length=32), nullable=False),
            sa.Column("report_text", sa.Text(), nullable=True),
            sa.Column("reported_by_user_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
            sa.Column("resolved_by_admin_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
        )

    _create_index_if_missing("service_locations", "ix_service_locations_lat", ["lat"])
    _create_index_if_missing("service_locations", "ix_service_locations_lng", ["lng"])
    _create_index_if_missing("service_locations", "ix_service_locations_lat_lng", ["lat", "lng"])
    _create_index_if_missing("service_locations", "ix_service_locations_category", ["category"])
    _create_index_if_missing("service_locations", "ix_service_locations_verification_status", ["verification_status"])
    _create_index_if_missing("service_locations", "ix_service_locations_is_active", ["is_active"])
    _create_index_if_missing("service_locations", "ix_service_locations_normalized_name_city", ["normalized_name", "city"])
    _create_index_if_missing(
        "service_locations",
        "uq_service_locations_source_type_external_id",
        ["source_type", "source_external_id"],
        unique=True,
    )
    _create_index_if_missing("service_location_sources", "ix_service_location_sources_location_id", ["service_location_id"])
    _create_index_if_missing("service_location_sources", "ix_service_location_sources_import_batch_id", ["import_batch_id"])
    _create_index_if_missing("service_location_claims", "ix_service_location_claims_location_id", ["service_location_id"])
    _create_index_if_missing("service_location_claims", "ix_service_location_claims_tenant_id", ["service_tenant_id"])
    _create_index_if_missing("service_location_claims", "ix_service_location_claims_status", ["claim_status"])
    _create_index_if_missing("service_location_reports", "ix_service_location_reports_location_id", ["service_location_id"])
    _create_index_if_missing("service_location_reports", "ix_service_location_reports_status", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    for table in (
        "service_location_reports",
        "service_location_claims",
        "service_location_sources",
        "service_locations",
    ):
        if table in tables:
            op.drop_table(table)
