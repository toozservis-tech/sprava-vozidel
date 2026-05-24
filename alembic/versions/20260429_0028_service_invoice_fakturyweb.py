"""service invoice FakturyWeb export fields

Revision ID: 20260429_0028
Revises: 20260428_0027
Create Date: 2026-04-29 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "20260429_0028"
down_revision = "20260428_0027"
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


def upgrade() -> None:
    _add_column_if_missing("service_invoices", sa.Column("extra_json", sa.Text(), nullable=True))
    _add_column_if_missing("service_invoices", sa.Column("fakturyweb_code", sa.String(length=128), nullable=True))
    _add_column_if_missing("service_invoices", sa.Column("fakturyweb_number", sa.String(length=64), nullable=True))
    _add_column_if_missing("service_invoices", sa.Column("fakturyweb_status", sa.String(length=64), nullable=True))
    _add_column_if_missing("service_invoices", sa.Column("fakturyweb_pdf_url", sa.Text(), nullable=True))
    _add_column_if_missing("service_invoices", sa.Column("fakturyweb_exported_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("service_invoices", sa.Column("fakturyweb_last_sync_at", sa.DateTime(), nullable=True))

    bind = op.get_bind()
    inspector = inspect(bind)
    if "service_invoices" in set(inspector.get_table_names()):
        indexes = {idx["name"] for idx in inspector.get_indexes("service_invoices")}
        if "ix_service_invoices_fakturyweb_code" not in indexes:
            op.create_index("ix_service_invoices_fakturyweb_code", "service_invoices", ["fakturyweb_code"])
        if "ix_service_invoices_fakturyweb_number" not in indexes:
            op.create_index("ix_service_invoices_fakturyweb_number", "service_invoices", ["fakturyweb_number"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "service_invoices" not in set(inspector.get_table_names()):
        return
    indexes = {idx["name"] for idx in inspector.get_indexes("service_invoices")}
    if "ix_service_invoices_fakturyweb_number" in indexes:
        op.drop_index("ix_service_invoices_fakturyweb_number", table_name="service_invoices")
    if "ix_service_invoices_fakturyweb_code" in indexes:
        op.drop_index("ix_service_invoices_fakturyweb_code", table_name="service_invoices")

    columns = {item["name"] for item in inspector.get_columns("service_invoices")}
    for name in (
        "fakturyweb_last_sync_at",
        "fakturyweb_exported_at",
        "fakturyweb_pdf_url",
        "fakturyweb_status",
        "fakturyweb_number",
        "fakturyweb_code",
        "extra_json",
    ):
        if name in columns:
            op.drop_column("service_invoices", name)
