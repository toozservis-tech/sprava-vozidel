"""Add vehicle catalog image cache and vehicle catalog image refs.

Revision ID: 20260426_0022
Revises: 20260424_0021
Create Date: 2026-04-26 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "20260426_0022"
down_revision = "20260424_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("catalog_image_id", sa.String(length=64), nullable=True))
    op.add_column("vehicles", sa.Column("catalog_image_url", sa.Text(), nullable=True))
    op.create_index("ix_vehicles_catalog_image_id", "vehicles", ["catalog_image_id"], unique=False)

    op.create_table(
        "vehicle_catalog_images",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("make", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("normalized_make", sa.String(), nullable=True),
        sa.Column("normalized_model", sa.String(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("year_from", sa.Integer(), nullable=True),
        sa.Column("year_to", sa.Integer(), nullable=True),
        sa.Column("body_type", sa.String(), nullable=True),
        sa.Column("color_bucket", sa.String(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_domain", sa.String(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_payload_json", sa.Text(), nullable=True),
        sa.Column("image_hash", sa.String(length=64), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_representative", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_verified_real_vehicle", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("license_note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint("provider", "image_hash", name="uq_vehicle_catalog_images_provider_image_hash"),
    )
    op.create_index(
        "ix_vehicle_catalog_images_lookup",
        "vehicle_catalog_images",
        ["normalized_make", "normalized_model", "year", "body_type", "color_bucket"],
        unique=False,
    )
    op.create_index(
        "ix_vehicle_catalog_images_provider_image_hash",
        "vehicle_catalog_images",
        ["provider", "image_hash"],
        unique=False,
    )
    op.create_index("ix_vehicle_catalog_images_expires_at", "vehicle_catalog_images", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_vehicle_catalog_images_expires_at", table_name="vehicle_catalog_images")
    op.drop_index("ix_vehicle_catalog_images_provider_image_hash", table_name="vehicle_catalog_images")
    op.drop_index("ix_vehicle_catalog_images_lookup", table_name="vehicle_catalog_images")
    op.drop_table("vehicle_catalog_images")
    op.drop_index("ix_vehicles_catalog_image_id", table_name="vehicles")
    op.drop_column("vehicles", "catalog_image_url")
    op.drop_column("vehicles", "catalog_image_id")
