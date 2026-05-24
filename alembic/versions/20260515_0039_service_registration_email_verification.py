"""Service registration requests: e-mail verification before admin processing.

Revision ID: 20260515_0039
Revises: 20260513_0038
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20260515_0039"
down_revision = "20260513_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "service_registration_requests" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("service_registration_requests")}
    if "email_verified_at" not in cols:
        op.add_column("service_registration_requests", sa.Column("email_verified_at", sa.DateTime(), nullable=True))
    if "email_verification_token_hash" not in cols:
        op.add_column(
            "service_registration_requests",
            sa.Column("email_verification_token_hash", sa.String(length=128), nullable=True),
        )
    if "email_verification_expires_at" not in cols:
        op.add_column(
            "service_registration_requests",
            sa.Column("email_verification_expires_at", sa.DateTime(), nullable=True),
        )
    if "email_verification_sent_at" not in cols:
        op.add_column(
            "service_registration_requests",
            sa.Column("email_verification_sent_at", sa.DateTime(), nullable=True),
        )

    inspector = inspect(bind)
    try:
        ix_names = {i["name"] for i in inspector.get_indexes("service_registration_requests")}
    except Exception:
        ix_names = set()
    if "ix_service_registration_requests_email_verification_token_hash" not in ix_names:
        op.create_index(
            "ix_service_registration_requests_email_verification_token_hash",
            "service_registration_requests",
            ["email_verification_token_hash"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "service_registration_requests" not in inspector.get_table_names():
        return
    try:
        ix_names = {i["name"] for i in inspector.get_indexes("service_registration_requests")}
    except Exception:
        ix_names = set()
    if "ix_service_registration_requests_email_verification_token_hash" in ix_names:
        op.drop_index(
            "ix_service_registration_requests_email_verification_token_hash",
            table_name="service_registration_requests",
        )
    cols = {c["name"] for c in inspector.get_columns("service_registration_requests")}
    for col in (
        "email_verification_sent_at",
        "email_verification_expires_at",
        "email_verification_token_hash",
        "email_verified_at",
    ):
        if col in cols:
            op.drop_column("service_registration_requests", col)
        inspector = inspect(bind)
        cols = {c["name"] for c in inspector.get_columns("service_registration_requests")}
