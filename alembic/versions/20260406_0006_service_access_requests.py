"""service access requests and vehicle links

Revision ID: 20260406_0006
Revises: 20260406_0005
Create Date: 2026-04-06 11:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "20260406_0006"
down_revision = "20260406_0005"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {str(col.get("name")) for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "service_vehicle_lookup_audit" not in tables:
        op.create_table(
            "service_vehicle_lookup_audit",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("service_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("lookup_query_raw", sa.String(), nullable=True),
            sa.Column("lookup_query_normalized", sa.String(), nullable=True),
            sa.Column("lookup_query_hash", sa.String(), nullable=True),
            sa.Column("lookup_identifier_type", sa.String(), nullable=False, server_default="unknown"),
            sa.Column("matched_vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=True),
            sa.Column("matched_owner_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("result_status", sa.String(), nullable=False, server_default="not_found"),
            sa.Column("returned_candidate_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "service_access_requests" not in tables:
        op.create_table(
            "service_access_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("service_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("owner_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
            sa.Column("lookup_audit_id", sa.Integer(), sa.ForeignKey("service_vehicle_lookup_audit.id"), nullable=True),
            sa.Column("requested_scope", sa.String(), nullable=False, server_default="history_read_create_record"),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("request_message", sa.Text(), nullable=True),
            sa.Column("requested_at", sa.DateTime(), nullable=False),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
            sa.Column("decided_by_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("decision_note", sa.Text(), nullable=True),
            sa.Column("approved_link_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "vehicle_service_links" not in tables:
        op.create_table(
            "vehicle_service_links",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("service_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("owner_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
            sa.Column("source_request_id", sa.Integer(), sa.ForeignKey("service_access_requests.id"), nullable=True),
            sa.Column("source_type", sa.String(), nullable=False, server_default="request_approved"),
            sa.Column("status", sa.String(), nullable=False, server_default="approved"),
            sa.Column("scope_vehicle_history_read", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("scope_create_service_record", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("scope_edit_existing_records", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("scope_delete_existing_records", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("owner_data_access_level", sa.String(), nullable=False, server_default="none"),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("approved_by_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_by_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("revoked_reason", sa.Text(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("service_customer_id", "vehicle_id", name="uq_vehicle_service_link_pair"),
        )

    inspector = inspect(bind)
    if not _has_column(inspector, "service_records", "created_by_service_customer_id"):
        op.add_column(
            "service_records",
            sa.Column("created_by_service_customer_id", sa.Integer(), nullable=True),
        )
    inspector = inspect(bind)
    if not _has_column(inspector, "service_records", "service_access_link_id"):
        op.add_column(
            "service_records",
            sa.Column("service_access_link_id", sa.Integer(), nullable=True),
        )

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "service_vehicle_access" in tables and "vehicle_service_links" in tables:
        bind.execute(
            text(
                """
                INSERT INTO vehicle_service_links (
                    tenant_id,
                    service_customer_id,
                    owner_customer_id,
                    vehicle_id,
                    source_request_id,
                    source_type,
                    status,
                    scope_vehicle_history_read,
                    scope_create_service_record,
                    scope_edit_existing_records,
                    scope_delete_existing_records,
                    owner_data_access_level,
                    approved_at,
                    approved_by_customer_id,
                    revoked_at,
                    revoked_by_customer_id,
                    revoked_reason,
                    note,
                    last_used_at,
                    created_at,
                    updated_at
                )
                SELECT
                    COALESCE(v.tenant_id, 1),
                    sva.service_customer_id,
                    sva.customer_id,
                    sva.vehicle_id,
                    NULL,
                    'legacy_service_vehicle_access',
                    CASE WHEN sva.status = 'active' THEN 'approved' ELSE 'revoked' END,
                    1,
                    1,
                    0,
                    0,
                    'none',
                    COALESCE(sva.updated_at, sva.created_at),
                    COALESCE(sva.granted_by_customer_id, sva.customer_id),
                    sva.revoked_at,
                    NULL,
                    CASE WHEN sva.status = 'revoked' THEN 'legacy_revoked' ELSE NULL END,
                    sva.note,
                    NULL,
                    COALESCE(sva.created_at, CURRENT_TIMESTAMP),
                    COALESCE(sva.updated_at, sva.created_at, CURRENT_TIMESTAMP)
                FROM service_vehicle_access sva
                LEFT JOIN vehicles v ON v.id = sva.vehicle_id
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM vehicle_service_links vsl
                    WHERE vsl.service_customer_id = sva.service_customer_id
                      AND vsl.vehicle_id = sva.vehicle_id
                )
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _has_column(inspector, "service_records", "service_access_link_id"):
        op.drop_column("service_records", "service_access_link_id")
        inspector = inspect(bind)
    if _has_column(inspector, "service_records", "created_by_service_customer_id"):
        op.drop_column("service_records", "created_by_service_customer_id")
        inspector = inspect(bind)

    tables = set(inspector.get_table_names())
    if "service_access_requests" in tables:
        op.drop_table("service_access_requests")
        tables = set(inspect(bind).get_table_names())
    if "service_vehicle_lookup_audit" in tables:
        op.drop_table("service_vehicle_lookup_audit")
        tables = set(inspect(bind).get_table_names())
    if "vehicle_service_links" in tables:
        op.drop_table("vehicle_service_links")
