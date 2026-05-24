"""comgate recurring hardening

Revision ID: 20260503_0029
Revises: 20260429_0028
Create Date: 2026-05-03 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "20260503_0029"
down_revision = "20260429_0028"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if table not in tables:
        return
    columns = {item["name"] for item in inspector.get_columns(table)}
    if column.name not in columns:
        op.add_column(table, column)


def _create_index_if_missing(table: str, index_name: str, columns: list[str]) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if table not in tables:
        return
    indexes = {idx["name"] for idx in inspector.get_indexes(table)}
    if index_name not in indexes:
        op.create_index(index_name, table, columns)


def upgrade() -> None:
    _add_column_if_missing("license_subscriptions", sa.Column("provider_init_transaction_id", sa.String(length=255), nullable=True))
    _add_column_if_missing("license_subscriptions", sa.Column("recurring_ready", sa.Boolean(), nullable=False, server_default=sa.false()))
    _add_column_if_missing("license_subscriptions", sa.Column("recurring_block_reason", sa.String(length=255), nullable=True))
    _add_column_if_missing("license_subscriptions", sa.Column("last_recurring_attempt_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("license_subscriptions", sa.Column("last_recurring_result", sa.String(length=255), nullable=True))

    _create_index_if_missing("license_subscriptions", "ix_license_subscriptions_provider_init_transaction_id", ["provider_init_transaction_id"])

    _add_column_if_missing("license_payment_transactions", sa.Column("subscription_id", sa.Integer(), nullable=True))
    _add_column_if_missing("license_payment_transactions", sa.Column("payment_type", sa.String(length=64), nullable=True))
    _add_column_if_missing("license_payment_transactions", sa.Column("parent_provider_transaction_id", sa.String(length=255), nullable=True))
    _add_column_if_missing("license_payment_transactions", sa.Column("parent_init_recurring_id", sa.String(length=255), nullable=True))
    _add_column_if_missing("license_payment_transactions", sa.Column("period_start", sa.DateTime(), nullable=True))
    _add_column_if_missing("license_payment_transactions", sa.Column("period_end", sa.DateTime(), nullable=True))
    _add_column_if_missing("license_payment_transactions", sa.Column("raw_provider_payload_hash", sa.String(length=64), nullable=True))
    _add_column_if_missing("license_payment_transactions", sa.Column("provider_response_code", sa.String(length=64), nullable=True))
    _add_column_if_missing("license_payment_transactions", sa.Column("provider_response_message", sa.Text(), nullable=True))

    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "license_payment_transactions" in tables:
        fk_names = {fk["name"] for fk in inspector.get_foreign_keys("license_payment_transactions") if fk.get("name")}
        if bind.dialect.name != "sqlite" and "fk_license_payment_transactions_subscription_id" not in fk_names:
            op.create_foreign_key(
                "fk_license_payment_transactions_subscription_id",
                "license_payment_transactions",
                "license_subscriptions",
                ["subscription_id"],
                ["id"],
            )
    _create_index_if_missing("license_payment_transactions", "ix_license_payment_transactions_subscription_id", ["subscription_id"])
    _create_index_if_missing("license_payment_transactions", "ix_license_payment_transactions_payment_type", ["payment_type"])
    _create_index_if_missing("license_payment_transactions", "ix_license_payment_transactions_parent_provider_transaction_id", ["parent_provider_transaction_id"])
    _create_index_if_missing("license_payment_transactions", "ix_license_payment_transactions_parent_init_recurring_id", ["parent_init_recurring_id"])
    _create_index_if_missing("license_payment_transactions", "ix_license_payment_transactions_period_start", ["period_start"])
    _create_index_if_missing("license_payment_transactions", "ix_license_payment_transactions_period_end", ["period_end"])
    _create_index_if_missing("license_payment_transactions", "ix_license_payment_transactions_raw_provider_payload_hash", ["raw_provider_payload_hash"])

    if "payment_events" not in tables:
        op.create_table(
            "payment_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("payment_id", sa.Integer(), nullable=True),
            sa.Column("provider", sa.String(length=64), nullable=False, server_default="comgate"),
            sa.Column("event_type", sa.String(length=128), nullable=False),
            sa.Column("provider_transaction_id", sa.String(length=255), nullable=True),
            sa.Column("payload_hash", sa.String(length=64), nullable=True),
            sa.Column("sanitized_payload_json", sa.Text(), nullable=True),
            sa.Column("received_at", sa.DateTime(), nullable=False),
            sa.Column("processed_at", sa.DateTime(), nullable=True),
            sa.Column("processing_status", sa.String(length=64), nullable=False, server_default="received"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["payment_id"], ["license_payment_transactions.id"]),
        )
    _create_index_if_missing("payment_events", "ix_payment_events_payment_id", ["payment_id"])
    _create_index_if_missing("payment_events", "ix_payment_events_event_type", ["event_type"])
    _create_index_if_missing("payment_events", "ix_payment_events_provider_transaction_id", ["provider_transaction_id"])
    _create_index_if_missing("payment_events", "ix_payment_events_payload_hash", ["payload_hash"])
    _create_index_if_missing("payment_events", "ix_payment_events_received_at", ["received_at"])
    _create_index_if_missing("payment_events", "ix_payment_events_processed_at", ["processed_at"])
    _create_index_if_missing("payment_events", "ix_payment_events_processing_status", ["processing_status"])

    if "license_audit_log" not in tables:
        op.create_table(
            "license_audit_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("subscription_id", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(length=128), nullable=False),
            sa.Column("old_status", sa.String(length=64), nullable=True),
            sa.Column("new_status", sa.String(length=64), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("actor_type", sa.String(length=32), nullable=False, server_default="system"),
            sa.Column("ip_address", sa.String(length=128), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["customers.id"]),
            sa.ForeignKeyConstraint(["subscription_id"], ["license_subscriptions.id"]),
        )
    _create_index_if_missing("license_audit_log", "ix_license_audit_log_tenant_id", ["tenant_id"])
    _create_index_if_missing("license_audit_log", "ix_license_audit_log_user_id", ["user_id"])
    _create_index_if_missing("license_audit_log", "ix_license_audit_log_subscription_id", ["subscription_id"])
    _create_index_if_missing("license_audit_log", "ix_license_audit_log_action", ["action"])
    _create_index_if_missing("license_audit_log", "ix_license_audit_log_actor_type", ["actor_type"])
    _create_index_if_missing("license_audit_log", "ix_license_audit_log_created_at", ["created_at"])

    op.execute("UPDATE license_subscriptions SET recurring_ready = 0 WHERE recurring_ready IS NULL")
    if bind.dialect.name != "sqlite":
        op.alter_column("license_subscriptions", "recurring_ready", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "license_audit_log" in tables:
        indexes = {idx["name"] for idx in inspector.get_indexes("license_audit_log")}
        for name in (
            "ix_license_audit_log_created_at",
            "ix_license_audit_log_actor_type",
            "ix_license_audit_log_action",
            "ix_license_audit_log_subscription_id",
            "ix_license_audit_log_user_id",
            "ix_license_audit_log_tenant_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="license_audit_log")
        op.drop_table("license_audit_log")

    if "payment_events" in tables:
        indexes = {idx["name"] for idx in inspector.get_indexes("payment_events")}
        for name in (
            "ix_payment_events_processing_status",
            "ix_payment_events_processed_at",
            "ix_payment_events_received_at",
            "ix_payment_events_payload_hash",
            "ix_payment_events_provider_transaction_id",
            "ix_payment_events_event_type",
            "ix_payment_events_payment_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="payment_events")
        op.drop_table("payment_events")

    if "license_payment_transactions" in tables:
        indexes = {idx["name"] for idx in inspector.get_indexes("license_payment_transactions")}
        for name in (
            "ix_license_payment_transactions_raw_provider_payload_hash",
            "ix_license_payment_transactions_period_end",
            "ix_license_payment_transactions_period_start",
            "ix_license_payment_transactions_parent_init_recurring_id",
            "ix_license_payment_transactions_parent_provider_transaction_id",
            "ix_license_payment_transactions_payment_type",
            "ix_license_payment_transactions_subscription_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="license_payment_transactions")
        fk_names = {fk["name"] for fk in inspector.get_foreign_keys("license_payment_transactions") if fk.get("name")}
        if bind.dialect.name != "sqlite" and "fk_license_payment_transactions_subscription_id" in fk_names:
            op.drop_constraint("fk_license_payment_transactions_subscription_id", "license_payment_transactions", type_="foreignkey")
        columns = {item["name"] for item in inspector.get_columns("license_payment_transactions")}
        for name in (
            "provider_response_message",
            "provider_response_code",
            "raw_provider_payload_hash",
            "period_end",
            "period_start",
            "parent_init_recurring_id",
            "parent_provider_transaction_id",
            "payment_type",
            "subscription_id",
        ):
            if name in columns:
                op.drop_column("license_payment_transactions", name)

    if "license_subscriptions" in tables:
        indexes = {idx["name"] for idx in inspector.get_indexes("license_subscriptions")}
        if "ix_license_subscriptions_provider_init_transaction_id" in indexes:
            op.drop_index("ix_license_subscriptions_provider_init_transaction_id", table_name="license_subscriptions")
        columns = {item["name"] for item in inspector.get_columns("license_subscriptions")}
        for name in (
            "last_recurring_result",
            "last_recurring_attempt_at",
            "recurring_block_reason",
            "recurring_ready",
            "provider_init_transaction_id",
        ):
            if name in columns:
                op.drop_column("license_subscriptions", name)
