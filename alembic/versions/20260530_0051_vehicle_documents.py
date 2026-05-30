"""vehicle documents platform table

Revision ID: 20260530_0051
Revises: 20260529_0050
Create Date: 2026-05-30 11:00:00.000000

Nedestruktivní migrace. Přidává tabulku vehicle_documents pro C1.0 platformu.

Před nasazením na produkci doporučený DB backup:
  cp /opt/toozhub2/data/vehicles.db /opt/toozhub2/data/vehicles.db.bak-$(date +%Y%m%d%H%M%S)

Rollback: downgrade neodstraňuje tabulku (bezpečný rollback — tabulka zůstane prázdná/nevyužitá).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260530_0051"
down_revision = "20260529_0050"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in set(inspector.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _has_table(inspector, "vehicle_documents"):
        return

    op.create_table(
        "vehicle_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False, index=True),
        sa.Column("document_type", sa.String(64), nullable=False, index=True),
        sa.Column("document_status", sa.String(32), nullable=False, server_default="draft", index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("document_number", sa.String(64), nullable=True, index=True),
        sa.Column("source_type", sa.String(64), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True, index=True),
        sa.Column("service_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("owner_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("created_by_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("visibility_scope", sa.String(32), nullable=False, server_default="service_private", index=True),
        sa.Column("verification_token", sa.String(128), nullable=True, unique=True, index=True),
        sa.Column("storage_path", sa.String(512), nullable=True),
        sa.Column("thumbnail_path", sa.String(512), nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=False, server_default="application/pdf"),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_vehicle_documents_vehicle_type_created",
        "vehicle_documents",
        ["vehicle_id", "document_type", "created_at"],
    )


def downgrade() -> None:
    pass
