"""vehicle_photo_assets + vehicles.primary_photo_asset_id + data migration

Revision ID: 20260417_0018
Revises: 20260417_0017
Create Date: 2026-04-17
"""
from __future__ import annotations

import secrets
import shutil
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "20260417_0018"
down_revision = "20260417_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "vehicle_photo_assets" not in tables:
        op.create_table(
            "vehicle_photo_assets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=False),
            sa.Column("owner_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("storage_key", sa.String(length=512), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("mime_type", sa.String(length=128), nullable=False),
            sa.Column("file_size_bytes", sa.Integer(), nullable=False),
            sa.Column("width", sa.Integer(), nullable=True),
            sa.Column("height", sa.Integer(), nullable=True),
            sa.Column("sha256_hex", sa.String(length=64), nullable=False),
            sa.Column("uploaded_by_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        )
        op.create_index("ix_vehicle_photo_assets_vehicle_id", "vehicle_photo_assets", ["vehicle_id"])
        op.create_index("ix_vehicle_photo_assets_tenant_id", "vehicle_photo_assets", ["tenant_id"])
        op.create_index("ix_vehicle_photo_assets_role", "vehicle_photo_assets", ["role"])

    inspector = inspect(bind)
    vcols = {c["name"] for c in inspector.get_columns("vehicles")}
    if "primary_photo_asset_id" not in vcols:
        with op.batch_alter_table("vehicles") as batch_op:
            batch_op.add_column(sa.Column("primary_photo_asset_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_vehicles_primary_photo_asset_id",
                "vehicle_photo_assets",
                ["primary_photo_asset_id"],
                ["id"],
            )

    try:
        from src.core.config import DATA_DIR
    except Exception:
        DATA_DIR = Path(__file__).resolve().parents[2] / "data"

    photos_root = Path(DATA_DIR) / "vehicle_photos"
    uploads_root = Path(DATA_DIR) / "uploads" / "vehicles"
    photos_root.mkdir(parents=True, exist_ok=True)

    conn = bind

    def _safe_copy(src: Path, dst: Path) -> bool:
        try:
            if not src.is_file():
                return False
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return dst.is_file()
        except Exception:
            return False

    # --- Migrate primary photos from vehicles.photo_path ---
    vehicles_rows = conn.execute(
        text("SELECT id, tenant_id, photo_path FROM vehicles WHERE photo_path IS NOT NULL AND trim(photo_path) != ''")
    ).fetchall()
    for vid, tenant_id, photo_path in vehicles_rows:
        rel = str(photo_path or "").strip().replace("\\", "/").lstrip("/")
        if not rel or rel == "__primary_photo__":
            continue
        src = (photos_root / rel).resolve()
        base = photos_root.resolve()
        if not str(src).startswith(str(base)) or not src.is_file():
            conn.execute(text("UPDATE vehicles SET photo_path = NULL WHERE id = :vid"), {"vid": int(vid)})
            continue
        fname = f"main_mig_{secrets.token_hex(6)}.jpg"
        storage_key = f"tenants/{int(tenant_id)}/vehicles/{int(vid)}/{fname}"
        dst = (photos_root / storage_key).resolve()
        if not str(dst).startswith(str(base)):
            continue
        if not _safe_copy(src, dst):
            continue
        size_b = dst.stat().st_size
        conn.execute(
            text(
                """
                INSERT INTO vehicle_photo_assets (
                    tenant_id, vehicle_id, owner_customer_id, role, storage_key,
                    original_filename, mime_type, file_size_bytes, width, height,
                    sha256_hex, uploaded_by_customer_id, created_at, deleted_at, sort_order
                ) VALUES (
                    :tenant_id, :vehicle_id, NULL, 'main', :storage_key,
                    :original_filename, 'image/jpeg', :file_size_bytes, NULL, NULL,
                    'legacy', NULL, CURRENT_TIMESTAMP, NULL, 0
                )
                """
            ),
            {
                "tenant_id": int(tenant_id),
                "vehicle_id": int(vid),
                "storage_key": storage_key,
                "original_filename": fname,
                "file_size_bytes": int(size_b),
            },
        )
        new_id_row = conn.execute(text("SELECT last_insert_rowid() AS id")).fetchone()
        new_id = int(new_id_row[0]) if new_id_row else None
        if new_id:
            conn.execute(
                text("UPDATE vehicles SET primary_photo_asset_id = :aid, photo_path = NULL WHERE id = :vid"),
                {"aid": new_id, "vid": int(vid)},
            )

    # --- Migrate gallery rows from vehicle_photos ---
    if "vehicle_photos" in tables:
        g_rows = conn.execute(
            text("SELECT id, tenant_id, vehicle_id, file_path FROM vehicle_photos ORDER BY id ASC")
        ).fetchall()
        for row_id, tenant_id, vehicle_id, file_path in g_rows:
            rel = str(file_path or "").strip().replace("\\", "/").lstrip("/")
            if not rel:
                continue
            src = (uploads_root / rel).resolve()
            ubase = uploads_root.resolve()
            if not str(src).startswith(str(ubase)) or not src.is_file():
                continue
            fname = f"gallery_mig_{int(row_id)}_{secrets.token_hex(4)}.jpg"
            storage_key = f"tenants/{int(tenant_id)}/vehicles/{int(vehicle_id)}/{fname}"
            dst = (photos_root / storage_key).resolve()
            pbase = photos_root.resolve()
            if not str(dst).startswith(str(pbase)):
                continue
            if not _safe_copy(src, dst):
                continue
            size_b = dst.stat().st_size
            conn.execute(
                text(
                    """
                    INSERT INTO vehicle_photo_assets (
                        tenant_id, vehicle_id, owner_customer_id, role, storage_key,
                        original_filename, mime_type, file_size_bytes, width, height,
                        sha256_hex, uploaded_by_customer_id, created_at, deleted_at, sort_order
                    ) VALUES (
                        :tenant_id, :vehicle_id, NULL, 'gallery', :storage_key,
                        :original_filename, 'image/jpeg', :file_size_bytes, NULL, NULL,
                        'legacy', NULL, CURRENT_TIMESTAMP, NULL, 0
                    )
                    """
                ),
                {
                    "tenant_id": int(tenant_id),
                    "vehicle_id": int(vehicle_id),
                    "storage_key": storage_key,
                    "original_filename": fname,
                    "file_size_bytes": int(size_b),
                },
            )
        conn.execute(text("DELETE FROM vehicle_photos"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    vcols = {c["name"] for c in inspector.get_columns("vehicles")}
    if "primary_photo_asset_id" in vcols:
        with op.batch_alter_table("vehicles") as batch_op:
            batch_op.drop_constraint("fk_vehicles_primary_photo_asset_id", type_="foreignkey")
            batch_op.drop_column("primary_photo_asset_id")
    inspector = inspect(bind)
    if "vehicle_photo_assets" in inspector.get_table_names():
        op.drop_table("vehicle_photo_assets")
