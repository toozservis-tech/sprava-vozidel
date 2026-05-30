from __future__ import annotations

import hashlib
import json
import re
import secrets
from pathlib import Path

from src.core.config import DATA_DIR

VEHICLE_DOCUMENTS_ROOT = DATA_DIR / "vehicle_documents"


def safe_filename(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", str(name or "document").strip())
    clean = clean.strip("-._") or "document"
    return clean[:120]


def document_pdf_path(
    *,
    tenant_id: int,
    vehicle_id: int,
    document_type: str,
    filename: str,
) -> Path:
    return (
        VEHICLE_DOCUMENTS_ROOT
        / "tenants"
        / str(int(tenant_id))
        / "vehicles"
        / str(int(vehicle_id))
        / safe_filename(document_type)
        / safe_filename(filename)
    )


def document_thumbnail_path(
    *,
    tenant_id: int,
    vehicle_id: int,
    document_type: str,
    filename: str,
) -> Path:
    base = document_pdf_path(
        tenant_id=tenant_id,
        vehicle_id=vehicle_id,
        document_type=document_type,
        filename=filename,
    )
    return base.parent / "thumbnails" / f"{base.stem}.jpg"


def ensure_document_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_document_bytes(path: Path, content: bytes) -> None:
    ensure_document_dir(path)
    path.write_bytes(content)


def read_document_bytes(path: Path) -> bytes:
    return path.read_bytes()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def generate_verification_token() -> str:
    return secrets.token_urlsafe(24).rstrip("=")


def parse_metadata(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def dump_metadata(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)
