"""
Vehicle photo storage helpers (tenant-separated keys, path resolution, validation).

Backend is source of truth: DB row (VehiclePhotoAsset) + storage_key under DATA_DIR/vehicle_photos/.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional

_STORAGE_KEY_RE = re.compile(r"^tenants/\d+/vehicles/\d+/[a-zA-Z0-9._-]+$")
_LEGACY_REL_RE = re.compile(r"^[a-zA-Z0-9/_.-]+$")


def normalize_storage_key(raw: str | None) -> Optional[str]:
    """Vrátí bezpečný storage_key nebo None."""
    if not raw:
        return None
    key = str(raw).strip().replace("\\", "/").lstrip("/")
    if ".." in key or key.startswith(".."):
        return None
    if _STORAGE_KEY_RE.fullmatch(key):
        return key
    # Legacy relativní cesty z vehicles.photo_path (např. tenant_1/vehicle_5/...)
    if _LEGACY_REL_RE.fullmatch(key) and ".." not in key:
        return key
    return None


def resolve_storage_file(photos_root: Path, storage_key: str | None) -> Path | None:
    """Vrátí existující soubor pod photos_root, nebo None (traversal-safe)."""
    key = normalize_storage_key(storage_key)
    if not key:
        return None
    base = photos_root.resolve()
    candidate = (photos_root / key).resolve()
    if not str(candidate).startswith(str(base)):
        return None
    try:
        if not candidate.is_file():
            return None
    except OSError:
        # NFS / špatné oprávnění: nesmí shodit API (seznam vozidel apod.)
        return None
    return candidate


def build_main_storage_key(*, tenant_id: int, vehicle_id: int, filename: str) -> str:
    return f"tenants/{int(tenant_id)}/vehicles/{int(vehicle_id)}/{filename}"


def build_work_order_storage_key(
    *,
    tenant_id: int,
    vehicle_id: int,
    work_order_id: int,
    filename: str,
) -> str:
    return f"tenants/{int(tenant_id)}/vehicles/{int(vehicle_id)}/work_orders/{int(work_order_id)}/{filename}"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jpeg_dimensions(data: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image
        from io import BytesIO

        with Image.open(BytesIO(data)) as im:
            return int(im.width), int(im.height)
    except Exception:
        return None, None
