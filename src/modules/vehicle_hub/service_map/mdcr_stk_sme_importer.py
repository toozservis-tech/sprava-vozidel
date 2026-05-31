"""Import oficiálních STK/SME stanic z MDČR (CSV/JSON) – příprava pro budoucí napojení."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy.orm import Session

from ..models import ServiceLocation, ServiceLocationSource
from .constants import (
    CATEGORY_SME,
    CATEGORY_STK,
    PROTECTED_VERIFICATION,
    SOURCE_MDCR,
    SOURCE_OSM,
    SOURCE_VERIFIED_SERVICE,
    VERIFICATION_DUPLICATE,
    VERIFICATION_IMPORTED,
)
from .normalize import normalize_service_name
from .osm_importer import _find_duplicate_candidate, _is_import_protected


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _normalize_category(raw: str | None) -> str:
    key = (raw or "").strip().lower()
    if key in {"sme", "emisni", "emise", "emission"}:
        return CATEGORY_SME
    return CATEGORY_STK


def _iter_mdcr_records(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return
    if isinstance(payload, dict):
        for key in ("items", "stations", "data", "records"):
            block = payload.get(key)
            if isinstance(block, list):
                for item in block:
                    if isinstance(item, dict):
                        yield item
                return
        yield payload


def import_mdcr_stk_sme(
    db: Session,
    payload: Any,
    *,
    import_batch_id: str | None = None,
    file_format: str = "json",
) -> dict[str, Any]:
    batch_id = import_batch_id or str(uuid.uuid4())
    now = datetime.utcnow()
    created = updated = skipped = duplicates = protected_skipped = 0

    records: list[dict[str, Any]]
    if file_format == "csv" and isinstance(payload, str):
        reader = csv.DictReader(io.StringIO(payload))
        records = [dict(row) for row in reader]
    elif isinstance(payload, str):
        records = list(_iter_mdcr_records(json.loads(payload)))
    else:
        records = list(_iter_mdcr_records(payload))

    for record in records:
        external_id = (
            str(record.get("source_external_id") or record.get("station_code") or record.get("id") or "").strip()
        )
        name = str(record.get("name") or record.get("station_name") or "").strip()
        lat = _parse_float(record.get("lat") or record.get("latitude"))
        lng = _parse_float(record.get("lng") or record.get("lon") or record.get("longitude"))
        if not external_id or not name or lat is None or lng is None:
            skipped += 1
            continue

        category = _normalize_category(str(record.get("category") or record.get("type") or "stk"))
        phone = str(record.get("phone") or "").strip() or None
        website = str(record.get("website") or "").strip() or None
        city = str(record.get("city") or record.get("municipality") or "").strip() or None
        address_text = str(record.get("address_text") or record.get("address") or "").strip() or None

        raw_hash = _payload_hash(record)
        existing = (
            db.query(ServiceLocation)
            .filter(ServiceLocation.source_type == SOURCE_MDCR, ServiceLocation.source_external_id == external_id)
            .first()
        )
        duplicate_of = _find_duplicate_candidate(
            db,
            lat=lat,
            lng=lng,
            name=name,
            phone=phone,
            website=website,
            exclude_id=existing.id if existing else None,
        )

        if existing:
            if _is_import_protected(existing):
                db.add(
                    ServiceLocationSource(
                        service_location_id=existing.id,
                        source_type=SOURCE_MDCR,
                        source_external_id=external_id,
                        raw_payload_hash=raw_hash,
                        raw_payload_json=json.dumps(record, ensure_ascii=False, default=str),
                        import_batch_id=batch_id,
                    )
                )
                protected_skipped += 1
                continue
            existing.name = name
            existing.normalized_name = normalize_service_name(name)
            existing.category = category
            existing.lat = lat
            existing.lng = lng
            existing.city = city
            existing.address_text = address_text
            existing.phone = phone
            existing.website = website
            existing.confidence_score = 0.92
            existing.last_imported_at = now
            existing.updated_at = now
            if duplicate_of and duplicate_of.id != existing.id:
                existing.verification_status = VERIFICATION_DUPLICATE
                duplicates += 1
            location = existing
            updated += 1
        else:
            verification = VERIFICATION_IMPORTED
            if duplicate_of:
                verification = VERIFICATION_DUPLICATE
                duplicates += 1
            location = ServiceLocation(
                source_type=SOURCE_MDCR,
                source_external_id=external_id,
                name=name,
                normalized_name=normalize_service_name(name),
                category=category,
                lat=lat,
                lng=lng,
                address_text=address_text,
                city=city,
                phone=phone,
                website=website,
                verification_status=verification,
                confidence_score=0.92,
                last_imported_at=now,
                is_active=True,
            )
            db.add(location)
            db.flush()
            created += 1

        db.add(
            ServiceLocationSource(
                service_location_id=location.id,
                source_type=SOURCE_MDCR,
                source_external_id=external_id,
                raw_payload_hash=raw_hash,
                raw_payload_json=json.dumps(record, ensure_ascii=False, default=str),
                import_batch_id=batch_id,
            )
        )

    db.commit()
    return {
        "import_batch_id": batch_id,
        "inserted": created,
        "updated": updated,
        "duplicates_suspected": duplicates,
        "skipped_invalid": skipped,
        "protected_skipped": protected_skipped,
        "records_total": len(records),
        "created": created,
        "duplicates_flagged": duplicates,
        "skipped": skipped,
    }
