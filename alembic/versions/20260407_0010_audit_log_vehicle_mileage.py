"""audit_log + vehicle_mileage

Revision ID: 20260407_0010
Revises: 20260407_0009
Create Date: 2026-04-07 18:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260407_0010"
down_revision = "20260407_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "audit_log" not in tables:
        op.create_table(
            "audit_log",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True, index=True),
            sa.Column("entity_type", sa.String(length=64), nullable=False, index=True),
            sa.Column("entity_id", sa.Integer(), nullable=True, index=True),
            sa.Column("action", sa.String(length=128), nullable=False, index=True),
            sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
            sa.Column("actor_role", sa.String(length=64), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    if "vehicle_mileage" not in tables:
        op.create_table(
            "vehicle_mileage",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False, index=True),
            sa.Column("mileage_km", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column(
                "created_by_user_id",
                sa.Integer(),
                sa.ForeignKey("customers.id"),
                nullable=True,
                index=True,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if "vehicle_mileage" in tables:
        op.drop_table("vehicle_mileage")
    if "audit_log" in tables:
        op.drop_table("audit_log")
