"""sanitize baseline schema for active modules

Revision ID: 20260326_0001
Revises: 
Create Date: 2026-03-26 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "20260326_0001"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in set(inspector.get_table_names())


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return column_name in {str(col.get("name")) for col in inspector.get_columns(table_name)}


def _create_table_if_missing(inspector, table_name: str, *columns, **kwargs) -> None:
    if _has_table(inspector, table_name):
        return
    op.create_table(table_name, *columns, **kwargs)


def _add_column_if_missing(inspector, table_name: str, column: sa.Column) -> None:
    if _has_column(inspector, table_name, column.name):
        return
    op.add_column(table_name, column)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    _create_table_if_missing(
        inspector,
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("license_key", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    inspector = inspect(bind)

    _create_table_if_missing(
        inspector,
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("email", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("ico", sa.String(), nullable=True),
        sa.Column("street", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("zip", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("notify_email", sa.Boolean(), nullable=True, server_default=sa.text("1")),
        sa.Column("notify_sms", sa.Boolean(), nullable=True, server_default=sa.text("0")),
        sa.Column("notify_stk", sa.Boolean(), nullable=True, server_default=sa.text("1")),
        sa.Column("notify_oil", sa.Boolean(), nullable=True, server_default=sa.text("1")),
        sa.Column("notify_general", sa.Boolean(), nullable=True, server_default=sa.text("1")),
        sa.Column("role", sa.String(), nullable=False, server_default="user"),
        sa.Column("reminder_settings", sa.Text(), nullable=True),
        sa.Column("reset_token", sa.String(), nullable=True, index=True),
        sa.Column("reset_token_expires", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    inspector = inspect(bind)

    _create_table_if_missing(
        inspector,
        "vehicles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("user_email", sa.String(), nullable=False, index=True),
        sa.Column("nickname", sa.String(), nullable=True),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("engine", sa.String(), nullable=True),
        sa.Column("vin", sa.String(), nullable=True),
        sa.Column("plate", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("stk_valid_until", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    inspector = inspect(bind)

    _create_table_if_missing(
        inspector,
        "service_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("performed_at", sa.DateTime(), nullable=True),
        sa.Column("mileage", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
    )
    inspector = inspect(bind)

    _create_table_if_missing(
        inspector,
        "reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False, index=True),
        sa.Column("service_type", sa.String(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("start_datetime", sa.DateTime(), nullable=False),
        sa.Column("end_datetime", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    inspector = inspect(bind)

    _create_table_if_missing(
        inspector,
        "reminders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=True, index=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    inspector = inspect(bind)

    _create_table_if_missing(
        inspector,
        "licenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, unique=True, index=True),
        sa.Column("plan", sa.String(), nullable=False, server_default="free"),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("vehicles_limit", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    inspector = inspect(bind)

    _create_table_if_missing(
        inspector,
        "version_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=False),
    )
    inspector = inspect(bind)

    _create_table_if_missing(
        inspector,
        "instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("device_id", sa.String(), nullable=True),
        sa.Column("app_version", sa.String(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
    )
    inspector = inspect(bind)

    for column in [
        sa.Column("dic", sa.String(), nullable=True),
        sa.Column("street_number", sa.String(), nullable=True),
        sa.Column("is_disabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("disabled_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
    ]:
        _add_column_if_missing(inspector, "customers", column)
    inspector = inspect(bind)

    _create_table_if_missing(
        inspector,
        "customer_security_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, unique=True, index=True),
        sa.Column("two_factor_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("totp_secret", sa.String(), nullable=True),
        sa.Column("totp_enabled_at", sa.DateTime(), nullable=True),
        sa.Column("biometric_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("biometric_preferred", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    _create_table_if_missing(
        inspector,
        "service_registration_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("ico", sa.String(), nullable=False, index=True),
        sa.Column("service_name", sa.String(), nullable=False),
        sa.Column("responsible_person", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("dic", sa.String(), nullable=True),
        sa.Column("street", sa.String(), nullable=False),
        sa.Column("street_number", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=False),
        sa.Column("zip", sa.String(), nullable=False),
        sa.Column("registration_purpose", sa.Text(), nullable=False),
        sa.Column("reviewed_by_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("approved_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("approved_tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    _create_table_if_missing(
        inspector,
        "service_customer_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("service_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("customer_tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True, index=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("service_customer_id", "customer_id", name="uq_service_customer_link"),
    )
    _create_table_if_missing(
        inspector,
        "service_vehicle_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False, index=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("granted_by_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("service_customer_id", "customer_id", "vehicle_id", name="uq_service_vehicle_access"),
    )
    _create_table_if_missing(
        inspector,
        "service_customer_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("service_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("invite_email", sa.String(), nullable=False, index=True),
        sa.Column("invite_name", sa.String(), nullable=True),
        sa.Column("invite_message", sa.Text(), nullable=True),
        sa.Column("token", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("status", sa.String(), nullable=False, index=True),
        sa.Column("linked_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("linked_customer_tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True, index=True),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    _create_table_if_missing(
        inspector,
        "service_document_ingestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("service_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=True, index=True),
        sa.Column("source_type", sa.String(), nullable=False, server_default="invoice", index=True),
        sa.Column("original_filename", sa.String(), nullable=True),
        sa.Column("original_mime_type", sa.String(), nullable=True),
        sa.Column("stored_file_path", sa.Text(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("parsed_payload_json", sa.Text(), nullable=True),
        sa.Column("parse_confidence", sa.Float(), nullable=True),
        sa.Column("processing_status", sa.String(), nullable=False, server_default="processed", index=True),
        sa.Column("document_number", sa.String(), nullable=True, index=True),
        sa.Column("supplier_name", sa.String(), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(), nullable=True, server_default="CZK"),
        sa.Column("subtotal_without_vat", sa.Float(), nullable=True),
        sa.Column("vat_amount", sa.Float(), nullable=True),
        sa.Column("total_with_vat", sa.Float(), nullable=True),
        sa.Column("labor_total", sa.Float(), nullable=True),
        sa.Column("materials_total", sa.Float(), nullable=True),
        sa.Column("auto_created_service_record_id", sa.Integer(), sa.ForeignKey("service_records.id"), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    for column in [
        sa.Column("photo_path", sa.Text(), nullable=True),
        sa.Column("current_mileage_km", sa.Integer(), nullable=True),
        sa.Column("last_stk_mileage_km", sa.Integer(), nullable=True),
        sa.Column("mileage_checked_at", sa.DateTime(), nullable=True),
        sa.Column("tyres_info", sa.Text(), nullable=True),
        sa.Column("insurance_provider", sa.String(), nullable=True),
        sa.Column("insurance_valid_until", sa.Date(), nullable=True),
    ]:
        _add_column_if_missing(inspector, "vehicles", column)
    inspector = inspect(bind)

    _create_table_if_missing(
        inspector,
        "vehicle_ownerships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False, index=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("ownership_type", sa.String(), nullable=False, server_default="owner", index=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("1"), index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1"), index=True),
        sa.Column("assigned_by_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("vehicle_id", "customer_id", "ownership_type", name="uq_vehicle_owner_assignment"),
    )

    for column in [
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("attachments", sa.Text(), nullable=True),
        sa.Column("next_service_due_date", sa.Date(), nullable=True),
        sa.Column("created_by_ai", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("deletion_reason", sa.Text(), nullable=True),
        sa.Column("snapshot_hash", sa.String(), nullable=True),
    ]:
        _add_column_if_missing(inspector, "service_records", column)
    inspector = inspect(bind)

    _create_table_if_missing(
        inspector,
        "service_record_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("service_record_id", sa.Integer(), sa.ForeignKey("service_records.id"), nullable=False, index=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False, index=True),
        sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("action", sa.String(), nullable=False, server_default="update"),
        sa.Column("previous_snapshot_json", sa.Text(), nullable=False),
        sa.Column("new_snapshot_json", sa.Text(), nullable=True),
        sa.Column("snapshot_hash", sa.String(), nullable=True, index=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    for column in [
        sa.Column("notify_at", sa.DateTime(), nullable=True),
        sa.Column("notification_method", sa.String(length=16), nullable=True),
        sa.Column("last_notified_at", sa.DateTime(), nullable=True),
        sa.Column("is_manual", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    ]:
        _add_column_if_missing(inspector, "reminders", column)

    _add_column_if_missing(inspector, "reservations", sa.Column("source_platform", sa.String(length=64), nullable=True))
    inspector = inspect(bind)

    _create_table_if_missing(
        inspector,
        "license_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, unique=True, index=True),
        sa.Column("provider", sa.String(), nullable=False, server_default="comgate", index=True),
        sa.Column("status", sa.String(), nullable=False, server_default="legacy_manual", index=True),
        sa.Column("plan_current", sa.String(), nullable=True, index=True),
        sa.Column("billing_period", sa.String(), nullable=True),
        sa.Column("auto_renew_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("pending_plan_change", sa.String(), nullable=True),
        sa.Column("init_recurring_id", sa.String(), nullable=True, index=True),
        sa.Column("credit_balance_halers", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("current_period_start", sa.DateTime(), nullable=True),
        sa.Column("current_period_end", sa.DateTime(), nullable=True, index=True),
        sa.Column("next_charge_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("grace_until", sa.DateTime(), nullable=True, index=True),
        sa.Column("cancel_requested_at", sa.DateTime(), nullable=True),
        sa.Column("last_payment_at", sa.DateTime(), nullable=True),
        sa.Column("last_trans_id", sa.String(), nullable=True),
        sa.Column("failed_renewal_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("notified_first_payment_at", sa.DateTime(), nullable=True),
        sa.Column("notified_renewal_failed_at", sa.DateTime(), nullable=True),
        sa.Column("notified_grace_end_at", sa.DateTime(), nullable=True),
        sa.Column("notified_period_d14_at", sa.DateTime(), nullable=True),
        sa.Column("notified_period_d7_at", sa.DateTime(), nullable=True),
        sa.Column("notified_period_d1_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_license_subscription_tenant_id"),
    )
    _create_table_if_missing(
        inspector,
        "license_payment_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("provider", sa.String(), nullable=False, server_default="comgate", index=True),
        sa.Column("trans_id", sa.String(), nullable=True, unique=True, index=True),
        sa.Column("ref_id", sa.String(), nullable=True, index=True),
        sa.Column("plan", sa.String(), nullable=True, index=True),
        sa.Column("billing_period", sa.String(), nullable=True),
        sa.Column("amount_halers", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(), nullable=True, server_default="CZK"),
        sa.Column("event_type", sa.String(), nullable=False, server_default="unknown", index=True),
        sa.Column("provider_status", sa.String(), nullable=True, index=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    _create_table_if_missing(
        inspector,
        "push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("endpoint", sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
    )
    _create_table_if_missing(
        inspector,
        "security_access_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True, index=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("user_email", sa.String(), nullable=True, index=True),
        sa.Column("event_type", sa.String(), nullable=False, index=True),
        sa.Column("endpoint", sa.String(), nullable=True, index=True),
        sa.Column("ip_address", sa.String(), nullable=True, index=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("timezone", sa.String(), nullable=True),
        sa.Column("isp", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    _create_table_if_missing(
        inspector,
        "developer_action_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("developer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("developer_email", sa.String(), nullable=True, index=True),
        sa.Column("action_type", sa.String(), nullable=False, index=True),
        sa.Column("target_resource", sa.String(), nullable=False, index=True),
        sa.Column("parameters_json", sa.Text(), nullable=True),
        sa.Column("result", sa.String(), nullable=False, server_default="success", index=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("request_ip", sa.String(), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    _create_table_if_missing(
        inspector,
        "security_blocked_ips",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ip_address", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("blocked_by_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("blocked_by_email", sa.String(), nullable=True, index=True),
        sa.Column("blocked_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("unblocked_at", sa.DateTime(), nullable=True),
        sa.Column("unblocked_by_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("unblocked_by_email", sa.String(), nullable=True, index=True),
    )
    _create_table_if_missing(
        inspector,
        "system_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_type", sa.String(), nullable=False, server_default="all", index=True),
        sa.Column("target_value", sa.String(), nullable=True, index=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False, server_default="info", index=True),
        sa.Column("starts_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1"), index=True),
        sa.Column("created_by_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("created_by_email", sa.String(), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    bind.execute(
        text(
            """
            INSERT INTO vehicle_ownerships (
                tenant_id, vehicle_id, customer_id, ownership_type, is_primary, is_active,
                assigned_by_customer_id, assigned_at, created_at, updated_at
            )
            SELECT
                v.tenant_id,
                v.id,
                c.id,
                'owner',
                1,
                1,
                c.id,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM vehicles v
            JOIN customers c
              ON lower(c.email) = lower(v.user_email)
             AND c.tenant_id = v.tenant_id
            LEFT JOIN vehicle_ownerships vo
              ON vo.vehicle_id = v.id
             AND vo.customer_id = c.id
             AND vo.ownership_type = 'owner'
            WHERE vo.id IS NULL
              AND v.user_email IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    # Sanitation baseline is additive and intentionally non-destructive.
    pass
