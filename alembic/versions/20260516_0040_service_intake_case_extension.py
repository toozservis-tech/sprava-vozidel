"""Service intake: fields for service-cases API (no new table).

Revision ID: 20260516_0040
Revises: 20260515_0039
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20260516_0040"
down_revision = "20260515_0039"
branch_labels = None
depends_on = None


def _add_text_if_missing(table: str, name: str) -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    if name not in cols:
        op.add_column(table, sa.Column(name, sa.Text(), nullable=True))


def _add_int_if_missing(table: str, name: str) -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    if name not in cols:
        op.add_column(table, sa.Column(name, sa.Integer(), nullable=True))


def _add_str_if_missing(table: str, name: str, length: int) -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    if name not in cols:
        op.add_column(table, sa.Column(name, sa.String(length=length), nullable=True))


def _add_dt_if_missing(table: str, name: str) -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    if name not in cols:
        op.add_column(table, sa.Column(name, sa.DateTime(), nullable=True))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "service_intakes" not in inspector.get_table_names():
        return

    _add_text_if_missing("service_intakes", "customer_request")
    _add_text_if_missing("service_intakes", "intake_note")
    _add_text_if_missing("service_intakes", "diagnosis_summary")
    _add_text_if_missing("service_intakes", "repair_summary")
    _add_text_if_missing("service_intakes", "internal_note")
    _add_text_if_missing("service_intakes", "visible_to_owner_note")
    _add_int_if_missing("service_intakes", "mileage_out")
    _add_str_if_missing("service_intakes", "mileage_source", 64)
    _add_dt_if_missing("service_intakes", "intake_completed_at")
    _add_dt_if_missing("service_intakes", "diagnosis_started_at")
    _add_dt_if_missing("service_intakes", "diagnosis_completed_at")
    _add_dt_if_missing("service_intakes", "handed_over_at")
    _add_dt_if_missing("service_intakes", "cancelled_at")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "service_intakes" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("service_intakes")}
    for col in (
        "cancelled_at",
        "handed_over_at",
        "diagnosis_completed_at",
        "diagnosis_started_at",
        "intake_completed_at",
        "mileage_source",
        "mileage_out",
        "visible_to_owner_note",
        "internal_note",
        "repair_summary",
        "diagnosis_summary",
        "intake_note",
        "customer_request",
    ):
        if col in cols:
            op.drop_column("service_intakes", col)
