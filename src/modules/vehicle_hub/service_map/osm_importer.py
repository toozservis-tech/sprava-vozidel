"""Import servisních míst z OpenStreetMap / Overpass JSON."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import ServiceLocation, ServiceLocationSource
from .constants import (
    CATEGORY_AUTOSERVIS,
    CATEGORY_KAROSARNA,
    CATEGORY_OTHER,
    CATEGORY_PNEUSERVIS,
    CATEGORY_STK,
    CATEGORY_TRUCK,
    DUPLICATE_RADIUS_METERS,
    PROTECTED_VERIFICATION,
    SOURCE_OSM,
    SOURCE_VERIFIED_SERVICE,
    VERIFICATION_DUPLICATE,
    VERIFICATION_IMPORTED,
)
from .normalize import normalize_phone, normalize_service_name, normalize_website, names_similar
from .search_service import haversine_km


def _tag(tags: dict[str, Any], key: str) -> str | None:
    value = tags.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _yes(tags: dict[str, Any], key: str) -> bool:
    return (_tag(tags, key) or "").lower() in {"yes", "1", "true"}


def categorize_osm_tags(tags: dict[str, Any]) -> str:
    if _tag(tags, "shop") == "car_repair" or _yes(tags, "service:vehicle:car_repair") or _yes(tags, "car:repair"):
        return CATEGORY_AUTOSERVIS
    if _tag(tags, "shop") == "tyres" or _yes(tags, "service:vehicle:tyres") or _yes(tags, "car:tyres"):
        return CATEGORY_PNEUSERVIS
    if _tag(tags, "amenity") == "vehicle_inspection" or _yes(tags, "service:vehicle:inspection"):
        return CATEGORY_STK
    if _yes(tags, "service:vehicle:hgv"):
        return CATEGORY_TRUCK
    if _yes(tags, "service:vehicle:body_repair"):
        return CATEGORY_KAROSARNA
    if _tag(tags, "craft") == "mechanic":
        if _yes(tags, "service:vehicle:tyres"):
            return CATEGORY_PNEUSERVIS
        if _yes(tags, "service:vehicle:inspection"):
            return CATEGORY_STK
        return CATEGORY_AUTOSERVIS
    return CATEGORY_OTHER


def _display_name(tags: dict[str, Any], category: str) -> str:
    for key in ("name", "brand", "operator"):
        value = _tag(tags, key)
        if value:
            return value
    labels = {
        CATEGORY_AUTOSERVIS: "Autoservis",
        CATEGORY_PNEUSERVIS: "Pneuservis",
        CATEGORY_STK: "STK stanice",
        CATEGORY_TRUCK: "Servis nákladních vozidel",
        CATEGORY_KAROSARNA: "Karosárna",
    }
    return labels.get(category, "Servisní místo")


def _build_address(tags: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    street = _tag(tags, "addr:street")
    housenumber = _tag(tags, "addr:housenumber")
    city = _tag(tags, "addr:city") or _tag(tags, "addr:town") or _tag(tags, "addr:village")
    postal = _tag(tags, "addr:postcode")
    street_line = " ".join(part for part in [street, housenumber] if part) or None
    parts = [street_line, postal, city]
    address_text = ", ".join(p for p in parts if p) or None
    return address_text, street_line, city, postal


def _element_coords(element: dict[str, Any]) -> tuple[float, float] | None:
    if element.get("type") == "node":
        lat, lon = element.get("lat"), element.get("lon")
        if lat is not None and lon is not None:
            return float(lat), float(lon)
    center = element.get("center") or {}
    lat, lon = center.get("lat"), center.get("lon")
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    return None


def _is_relevant_osm_element(element: dict[str, Any]) -> bool:
    tags = element.get("tags") or {}
    if not tags:
        return False
    if _tag(tags, "shop") in {"car_repair", "tyres"}:
        return True
    if _tag(tags, "craft") == "mechanic":
        return True
    if _tag(tags, "amenity") == "vehicle_inspection":
        return True
    for key in (
        "service:vehicle:inspection",
        "service:vehicle:tyres",
        "service:vehicle:car_repair",
        "service:vehicle:hgv",
        "service:vehicle:body_repair",
        "car:repair",
        "car:tyres",
    ):
        if _yes(tags, key):
            return True
    return False


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _find_duplicate_candidate(
    db: Session,
    *,
    lat: float,
    lng: float,
    name: str,
    phone: str | None,
    website: str | None,
    exclude_id: int | None = None,
) -> ServiceLocation | None:
    lat_delta = DUPLICATE_RADIUS_METERS / 111000.0
    lng_delta = DUPLICATE_RADIUS_METERS / (111000.0 * 0.65)
    rows = (
        db.query(ServiceLocation)
        .filter(ServiceLocation.lat >= lat - lat_delta, ServiceLocation.lat <= lat + lat_delta)
        .filter(ServiceLocation.lng >= lng - lng_delta, ServiceLocation.lng <= lng + lng_delta)
        .all()
    )
    norm_phone = normalize_phone(phone)
    norm_web = normalize_website(website)
    for row in rows:
        if exclude_id and int(row.id) == int(exclude_id):
            continue
        dist_m = haversine_km(lat, lng, float(row.lat), float(row.lng)) * 1000.0
        if dist_m > DUPLICATE_RADIUS_METERS:
            continue
        if names_similar(name, row.name):
            return row
        if norm_phone and normalize_phone(row.phone) == norm_phone:
            return row
        if norm_web and normalize_website(row.website) == norm_web:
            return row
    return None


def _is_import_protected(row: ServiceLocation) -> bool:
    if row.source_type == SOURCE_VERIFIED_SERVICE:
        return True
    if row.verification_status in PROTECTED_VERIFICATION:
        return True
    if row.linked_service_tenant_id:
        return True
    return False


def import_osm_overpass_json(db: Session, payload: dict[str, Any], *, import_batch_id: str | None = None) -> dict[str, Any]:
    batch_id = import_batch_id or str(uuid.uuid4())
    now = datetime.utcnow()
    elements = payload.get("elements") or []
    created = updated = duplicates = skipped = protected_skipped = 0
    category_counts: dict[str, int] = {}

    for element in elements:
        if not isinstance(element, dict):
            skipped += 1
            continue
        if not _is_relevant_osm_element(element):
            skipped += 1
            continue
        coords = _element_coords(element)
        if not coords:
            skipped += 1
            continue
        lat, lng = coords
        tags = element.get("tags") or {}
        category = categorize_osm_tags(tags)
        if category == CATEGORY_OTHER and _tag(tags, "craft") != "mechanic":
            skipped += 1
            continue

        osm_type = str(element.get("type") or "node")
        osm_id = element.get("id")
        external_id = f"{osm_type}/{osm_id}" if osm_id is not None else None
        if not external_id:
            skipped += 1
            continue

        name = _display_name(tags, category)
        address_text, street, city, postal = _build_address(tags)
        phone = _tag(tags, "phone") or _tag(tags, "contact:phone")
        email = _tag(tags, "email") or _tag(tags, "contact:email")
        website = _tag(tags, "website") or _tag(tags, "contact:website")
        opening_hours = _tag(tags, "opening_hours")

        raw_hash = _payload_hash(element)
        existing = (
            db.query(ServiceLocation)
            .filter(ServiceLocation.source_type == SOURCE_OSM, ServiceLocation.source_external_id == external_id)
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
                        source_type=SOURCE_OSM,
                        source_external_id=external_id,
                        raw_payload_hash=raw_hash,
                        raw_payload_json=json.dumps(element, ensure_ascii=False, default=str),
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
            existing.address_text = address_text
            existing.street = street
            existing.city = city
            existing.postal_code = postal
            existing.phone = phone
            existing.email = email
            existing.website = website
            existing.opening_hours = opening_hours
            existing.last_imported_at = now
            existing.confidence_score = 0.55
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
                source_type=SOURCE_OSM,
                source_external_id=external_id,
                name=name,
                normalized_name=normalize_service_name(name),
                category=category,
                lat=lat,
                lng=lng,
                address_text=address_text,
                street=street,
                city=city,
                postal_code=postal,
                phone=phone,
                email=email,
                website=website,
                opening_hours=opening_hours,
                verification_status=verification,
                confidence_score=0.55,
                last_imported_at=now,
                is_active=True,
            )
            db.add(location)
            db.flush()
            created += 1

        category_counts[category] = category_counts.get(category, 0) + 1

        db.add(
            ServiceLocationSource(
                service_location_id=location.id,
                source_type=SOURCE_OSM,
                source_external_id=external_id,
                raw_payload_hash=raw_hash,
                raw_payload_json=json.dumps(element, ensure_ascii=False, default=str),
                import_batch_id=batch_id,
            )
        )

    db.commit()
    return {
        "import_batch_id": batch_id,
        "elements_total": len(elements),
        "inserted": created,
        "updated": updated,
        "duplicates_suspected": duplicates,
        "skipped_invalid": skipped,
        "protected_skipped": protected_skipped,
        "categories_count": category_counts,
        "created": created,
        "duplicates_flagged": duplicates,
        "skipped": skipped,
    }
