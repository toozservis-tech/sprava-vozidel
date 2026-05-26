"""central vehicle identity fields

Revision ID: 20260526_0045
Revises: 20260523_0043
Create Date: 2026-05-26 14:30:00.000000

Nedestruktivní migrace. Před produkčním nasazením:
    pg_dump "$DATABASE_URL" --format=custom --file="backup_before_20260526_0045.dump"

Migrace pouze přidává nullable/status sloupce a doplňuje normalizované hodnoty
z existujících VIN/SPZ. Nevytváří ownership, nemaže vozidla a neslučuje duplicity.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "20260526_0045"
down_revision = "20260523_0043"
branch_labels = None
depends_on = None


def _has_column(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def _add_column_if_missing(inspector, table: str, column: sa.Column) -> None:
    if not _has_column(inspector, table, column.name):
        op.add_column(table, column)


def _create_index_if_missing(index_name: str, table: str, columns: list[str]) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes(table)}
    if index_name not in existing:
        op.create_index(index_name, table, columns, unique=False)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "vehicles" not in tables:
        return

    _add_column_if_missing(inspector, "vehicles", sa.Column("normalized_vin", sa.String(length=17), nullable=True))
    _add_column_if_missing(inspector, "vehicles", sa.Column("normalized_plate", sa.String(length=32), nullable=True))
    _add_column_if_missing(
        inspector,
        "vehicles",
        sa.Column("global_vehicle_status", sa.String(length=32), nullable=False, server_default="owned_vehicle"),
    )
    _add_column_if_missing(
        inspector,
        "vehicles",
        sa.Column("source_origin", sa.String(length=32), nullable=False, server_default="legacy"),
    )
    _add_column_if_missing(
        inspector,
        "vehicles",
        sa.Column("claim_status", sa.String(length=32), nullable=False, server_default="none"),
    )
    _add_column_if_missing(inspector, "vehicles", sa.Column("claimed_at", sa.DateTime(), nullable=True))
    _add_column_if_missing(inspector, "vehicles", sa.Column("claimed_by_customer_id", sa.Integer(), nullable=True))
    _add_column_if_missing(inspector, "vehicles", sa.Column("provisioned_by_service_tenant_id", sa.Integer(), nullable=True))
    _add_column_if_missing(inspector, "vehicles", sa.Column("merge_guard_hash", sa.String(length=64), nullable=True))

    _create_index_if_missing("ix_vehicles_normalized_vin", "vehicles", ["normalized_vin"])
    _create_index_if_missing("ix_vehicles_normalized_plate", "vehicles", ["normalized_plate"])
    _create_index_if_missing("ix_vehicles_global_vehicle_status", "vehicles", ["global_vehicle_status"])
    _create_index_if_missing("ix_vehicles_source_origin", "vehicles", ["source_origin"])
    _create_index_if_missing("ix_vehicles_claim_status", "vehicles", ["claim_status"])
    _create_index_if_missing("ix_vehicles_claimed_at", "vehicles", ["claimed_at"])
    _create_index_if_missing("ix_vehicles_claimed_by_customer_id", "vehicles", ["claimed_by_customer_id"])
    _create_index_if_missing("ix_vehicles_provisioned_by_service_tenant_id", "vehicles", ["provisioned_by_service_tenant_id"])
    _create_index_if_missing("ix_vehicles_merge_guard_hash", "vehicles", ["merge_guard_hash"])

    # Backfill only derived fields. No ownership, tenant or service links are modified.
    bind.execute(
        text(
            """
            UPDATE vehicles
            SET
                normalized_vin = NULLIF(upper(replace(replace(coalesce(vin, ''), ' ', ''), '-', '')), ''),
                normalized_plate = NULLIF(upper(replace(replace(coalesce(plate, ''), ' ', ''), '-', '')), '')
            WHERE normalized_vin IS NULL OR normalized_plate IS NULL
            """
        )
    )
    bind.execute(
        text(
            """
            UPDATE vehicles
            SET global_vehicle_status = CASE
                    WHEN provisioned_by_service_customer_id IS NOT NULL
                         AND NOT EXISTS (
                             SELECT 1 FROM vehicle_ownerships vo
                             WHERE vo.vehicle_id = vehicles.id AND vo.is_active = 1
                         )
                    THEN 'service_provisioned_unowned'
                    ELSE coalesce(global_vehicle_status, 'owned_vehicle')
                END,
                source_origin = CASE
                    WHEN provisioned_by_service_customer_id IS NOT NULL
                         AND coalesce(source_origin, 'legacy') = 'legacy'
                    THEN 'service_created'
                    ELSE coalesce(source_origin, 'legacy')
                END
            """
        )
    )


def downgrade() -> None:
    # Intentionally no-op: this migration is data-safety oriented and must not
    # drop columns or discard normalized identity metadata during rollback drills.
    pass
