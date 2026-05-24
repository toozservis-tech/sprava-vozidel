"""user tutorial progress + audit log

Revision ID: 20260503_0030
Revises: 20260503_0029
Create Date: 2026-05-03 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20260503_0030"
down_revision = "20260503_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "user_tutorial_progress" not in tables:
        op.create_table(
            "user_tutorial_progress",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("tutorial_id", sa.String(length=96), nullable=False),
            sa.Column("step_id", sa.String(length=160), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("last_failure_code", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.UniqueConstraint("customer_id", "tutorial_id", name="uq_user_tutorial_progress_customer_tutorial"),
        )
        op.create_index("ix_user_tutorial_progress_customer_id", "user_tutorial_progress", ["customer_id"])
        op.create_index("ix_user_tutorial_progress_tenant_id", "user_tutorial_progress", ["tenant_id"])
        op.create_index("ix_user_tutorial_progress_tutorial_id", "user_tutorial_progress", ["tutorial_id"])
        op.create_index("ix_user_tutorial_progress_status", "user_tutorial_progress", ["status"])
        op.create_index("ix_user_tutorial_progress_last_failure_code", "user_tutorial_progress", ["last_failure_code"])

    if "tutorial_audit_log" not in tables:
        op.create_table(
            "tutorial_audit_log",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("tutorial_id", sa.String(length=96), nullable=False),
            sa.Column("step_id", sa.String(length=160), nullable=True),
            sa.Column("status", sa.String(length=48), nullable=False),
            sa.Column("failure_code", sa.String(length=80), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        )
        op.create_index("ix_tutorial_audit_log_customer_id", "tutorial_audit_log", ["customer_id"])
        op.create_index("ix_tutorial_audit_log_tenant_id", "tutorial_audit_log", ["tenant_id"])
        op.create_index("ix_tutorial_audit_log_tutorial_id", "tutorial_audit_log", ["tutorial_id"])
        op.create_index("ix_tutorial_audit_log_step_id", "tutorial_audit_log", ["step_id"])
        op.create_index("ix_tutorial_audit_log_status", "tutorial_audit_log", ["status"])
        op.create_index("ix_tutorial_audit_log_failure_code", "tutorial_audit_log", ["failure_code"])
        op.create_index("ix_tutorial_audit_log_created_at", "tutorial_audit_log", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "tutorial_audit_log" in tables:
        op.drop_table("tutorial_audit_log")
    if "user_tutorial_progress" in tables:
        op.drop_table("user_tutorial_progress")
