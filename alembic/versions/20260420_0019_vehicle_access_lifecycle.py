"""canonical vehicle access lifecycle

Revision ID: 20260420_0019
Revises: 20260417_0018
Create Date: 2026-04-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "20260420_0019"
down_revision = "20260417_0018"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _cols(table: str) -> set[str]:
    if table not in _tables():
        return set()
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def _add_column(table: str, column: sa.Column) -> None:
    if column.name in _cols(table):
        return
    with op.batch_alter_table(table) as batch:
        batch.add_column(column)


def upgrade() -> None:
    tables = _tables()

    if "vehicle_transfer_tokens" not in tables:
        op.create_table(
            "vehicle_transfer_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
            sa.Column("issued_by_user_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("transfer_reason", sa.String(length=64), nullable=False, server_default="sale"),
            sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
            sa.Column("qr_payload", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("claimed_by_user_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("claimed_at", sa.DateTime(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_vehicle_transfer_tokens_vehicle_id", "vehicle_transfer_tokens", ["vehicle_id"])
        op.create_index("ix_vehicle_transfer_tokens_token_hash", "vehicle_transfer_tokens", ["token_hash"])
        op.create_index("ix_vehicle_transfer_tokens_status", "vehicle_transfer_tokens", ["status"])

    tables = _tables()
    if "vehicle_removal_events" not in tables:
        op.create_table(
            "vehicle_removal_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
            sa.Column("initiated_by_user_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("reason_code", sa.String(length=64), nullable=False),
            sa.Column("required_followup_answer_json", sa.Text(), nullable=False),
            sa.Column("digital_report_document_id", sa.Integer(), sa.ForeignKey("vehicle_report_documents.id"), nullable=True),
            sa.Column("archive_bundle_path", sa.Text(), nullable=True),
            sa.Column("transfer_token_id", sa.Integer(), sa.ForeignKey("vehicle_transfer_tokens.id"), nullable=True),
            sa.Column("executed_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_vehicle_removal_events_vehicle_id", "vehicle_removal_events", ["vehicle_id"])
        op.create_index("ix_vehicle_removal_events_reason_code", "vehicle_removal_events", ["reason_code"])

    if "service_labor_sessions" not in tables:
        op.create_table(
            "service_labor_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("service_case_id", sa.Integer(), sa.ForeignKey("service_intakes.id"), nullable=False),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=True),
            sa.Column("service_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("technician_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("stopped_at", sa.DateTime(), nullable=True),
            sa.Column("duration_seconds", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_service_labor_sessions_service_case_id", "service_labor_sessions", ["service_case_id"])

    tables = _tables()
    if "service_intakes" not in tables:
        op.create_table(
            "service_intakes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("service_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("service_tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("service_access_request_id", sa.Integer(), sa.ForeignKey("service_access_requests.id"), nullable=True),
            sa.Column("service_access_link_id", sa.Integer(), sa.ForeignKey("vehicle_service_links.id"), nullable=True),
            sa.Column("intake_status", sa.String(length=64), nullable=False, server_default="draft"),
            sa.Column("intake_source", sa.String(length=64), nullable=False, server_default="manual_search"),
            sa.Column("intake_spz_raw", sa.String(), nullable=True),
            sa.Column("intake_spz_normalized", sa.String(), nullable=True),
            sa.Column("intake_photo_asset_id", sa.Integer(), nullable=True),
            sa.Column("ocr_confidence", sa.Float(), nullable=True),
            sa.Column("owner_approval_required", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("owner_approval_status", sa.String(length=32), nullable=False, server_default="not_requested"),
            sa.Column("check_in_at", sa.DateTime(), nullable=True),
            sa.Column("work_started_at", sa.DateTime(), nullable=True),
            sa.Column("work_finished_at", sa.DateTime(), nullable=True),
            sa.Column("total_labor_seconds", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("odometer_km", sa.Integer(), nullable=True),
            sa.Column("fluids_ok", sa.Text(), nullable=True),
            sa.Column("damage_description", sa.Text(), nullable=True),
            sa.Column("photos", sa.Text(), nullable=True),
            sa.Column("work_description", sa.Text(), nullable=True),
            sa.Column("signature", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_service_intakes_service_id", "service_intakes", ["service_id"])
        op.create_index("ix_service_intakes_vehicle_id", "service_intakes", ["vehicle_id"])

    for name, coltype in {
        "fuel": sa.String(),
        "body_type": sa.String(),
        "status": sa.String(length=32),
        "updated_at": sa.DateTime(),
    }.items():
        default = sa.text("'active'") if name == "status" else sa.text("CURRENT_TIMESTAMP") if name == "updated_at" else None
        _add_column("vehicles", sa.Column(name, coltype, nullable=False if name in {"status", "updated_at"} else True, server_default=default))

    for name, coltype in {
        "relation_type": sa.String(),
        "acquisition_reason": sa.String(length=64),
        "deactivation_reason": sa.String(length=64),
        "transfer_token_id": sa.Integer(),
    }.items():
        _add_column("vehicle_ownerships", sa.Column(name, coltype, nullable=True))
    op.execute(text("UPDATE vehicle_ownerships SET relation_type = COALESCE(relation_type, ownership_type, 'owner')"))

    photo_columns = {
        "related_case_id": sa.Integer(),
        "photo_kind": sa.String(length=64),
        "vin": sa.String(),
        "capture_date": sa.DateTime(),
        "storage_path_original": sa.Text(),
        "storage_path_preview": sa.Text(),
    }
    for name, coltype in photo_columns.items():
        _add_column("vehicle_photo_assets", sa.Column(name, coltype, nullable=True))
    op.execute(text("UPDATE vehicle_photo_assets SET photo_kind = COALESCE(photo_kind, CASE WHEN role = 'main' THEN 'primary_thumbnail' ELSE 'other' END)"))
    op.execute(text("UPDATE vehicle_photo_assets SET storage_path_original = COALESCE(storage_path_original, storage_key), storage_path_preview = COALESCE(storage_path_preview, storage_key)"))

    for name, coltype in {
        "actor_type": sa.String(length=32),
        "actor_id": sa.Integer(),
        "vehicle_id": sa.Integer(),
        "before_json": sa.Text(),
        "after_json": sa.Text(),
        "ip": sa.String(length=128),
        "user_agent": sa.Text(),
        "occurred_at": sa.DateTime(),
        "correlation_id": sa.String(length=128),
    }.items():
        _add_column("audit_log", sa.Column(name, coltype, nullable=True))
    op.execute(text("UPDATE audit_log SET occurred_at = COALESCE(occurred_at, created_at, CURRENT_TIMESTAMP), actor_id = COALESCE(actor_id, actor_user_id), actor_type = COALESCE(actor_type, actor_role)"))

    for name, coltype in {
        "origin": sa.String(length=32),
        "service_case_id": sa.Integer(),
        "labor_seconds": sa.Integer(),
        "recommended_next_service_km": sa.Integer(),
        "visibility_scope": sa.String(length=32),
    }.items():
        _add_column("service_records", sa.Column(name, coltype, nullable=True))
    op.execute(text("UPDATE service_records SET origin = COALESCE(origin, CASE WHEN service_id IS NOT NULL OR created_by_service_customer_id IS NOT NULL THEN 'service_verified' ELSE 'user_manual' END), visibility_scope = COALESCE(visibility_scope, 'full_current_owner')"))

    service_intake_additions = {
        "service_tenant_id": sa.Integer(),
        "service_access_request_id": sa.Integer(),
        "service_access_link_id": sa.Integer(),
        "intake_status": sa.String(length=64),
        "intake_source": sa.String(length=64),
        "intake_spz_raw": sa.String(),
        "intake_spz_normalized": sa.String(),
        "intake_photo_asset_id": sa.Integer(),
        "ocr_confidence": sa.Float(),
        "owner_approval_required": sa.Boolean(),
        "owner_approval_status": sa.String(length=32),
        "check_in_at": sa.DateTime(),
        "work_started_at": sa.DateTime(),
        "work_finished_at": sa.DateTime(),
        "total_labor_seconds": sa.Integer(),
        "created_by": sa.Integer(),
        "updated_at": sa.DateTime(),
    }
    for name, coltype in service_intake_additions.items():
        _add_column("service_intakes", sa.Column(name, coltype, nullable=True))
    op.execute(text("""
        UPDATE service_intakes
        SET intake_status = COALESCE(intake_status, 'approved_for_service'),
            intake_source = COALESCE(intake_source, 'linked_vehicle'),
            owner_approval_required = COALESCE(owner_approval_required, 0),
            owner_approval_status = COALESCE(owner_approval_status, 'approved'),
            check_in_at = COALESCE(check_in_at, created_at),
            total_labor_seconds = COALESCE(total_labor_seconds, 0),
            created_by = COALESCE(created_by, service_id),
            updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
    """))


def downgrade() -> None:
    # Produkční rollback nechává rozšířené sloupce na místě kvůli ochraně dat.
    for table in ("vehicle_removal_events", "vehicle_transfer_tokens", "service_labor_sessions"):
        if table in _tables():
            op.drop_table(table)
