"""Customer email verification, phone E.164, registration antifraud metadata.

Revision ID: 20260505_0033
Revises: 20260504_0032
Create Date: 2026-05-05 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20260505_0033"
down_revision = "20260504_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("customers")}

    if "account_status" not in cols:
        op.add_column("customers", sa.Column("account_status", sa.String(length=40), nullable=True))
    if "email_verified_at" not in cols:
        op.add_column("customers", sa.Column("email_verified_at", sa.DateTime(), nullable=True))
    if "email_verification_token_hash" not in cols:
        op.add_column(
            "customers",
            sa.Column("email_verification_token_hash", sa.String(length=128), nullable=True),
        )
    if "email_verification_expires_at" not in cols:
        op.add_column("customers", sa.Column("email_verification_expires_at", sa.DateTime(), nullable=True))
    if "email_verification_sent_at" not in cols:
        op.add_column("customers", sa.Column("email_verification_sent_at", sa.DateTime(), nullable=True))
    if "phone_e164" not in cols:
        op.add_column("customers", sa.Column("phone_e164", sa.String(length=20), nullable=True))
    if "phone_verified_at" not in cols:
        op.add_column("customers", sa.Column("phone_verified_at", sa.DateTime(), nullable=True))
    if "registration_ip" not in cols:
        op.add_column("customers", sa.Column("registration_ip", sa.String(length=128), nullable=True))
    if "registration_user_agent" not in cols:
        op.add_column("customers", sa.Column("registration_user_agent", sa.Text(), nullable=True))
    if "registration_risk_flags" not in cols:
        op.add_column("customers", sa.Column("registration_risk_flags", sa.JSON(), nullable=True))

    # Existující účty: považovat za aktivní a e-mailově ověřené (zpětná kompatibilita).
    op.execute(
        """
        UPDATE customers
        SET
          account_status = 'active',
          email_verified_at = COALESCE(email_verified_at, created_at, CURRENT_TIMESTAMP)
        WHERE account_status IS NULL
           OR LENGTH(TRIM(COALESCE(account_status, ''))) = 0
        """
    )

    with op.batch_alter_table("customers") as batch_op:
        batch_op.alter_column(
            "account_status",
            existing_type=sa.String(length=40),
            nullable=False,
            server_default=sa.text("'pending_email_verification'"),
        )

    inspector = inspect(bind)
    try:
        ix_names = {i["name"] for i in inspector.get_indexes("customers")}
    except Exception:
        ix_names = set()
    if "ix_customers_email_verification_token_hash" not in ix_names:
        op.create_index(
            "ix_customers_email_verification_token_hash",
            "customers",
            ["email_verification_token_hash"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    try:
        ix_names = {i["name"] for i in inspector.get_indexes("customers")}
    except Exception:
        ix_names = set()
    if "ix_customers_email_verification_token_hash" in ix_names:
        op.drop_index("ix_customers_email_verification_token_hash", table_name="customers")

    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("customers")}
    for col in (
        "registration_risk_flags",
        "registration_user_agent",
        "registration_ip",
        "phone_verified_at",
        "phone_e164",
        "email_verification_sent_at",
        "email_verification_expires_at",
        "email_verification_token_hash",
        "email_verified_at",
        "account_status",
    ):
        if col in cols:
            op.drop_column("customers", col)
        inspector = inspect(bind)
        cols = {c["name"] for c in inspector.get_columns("customers")}
