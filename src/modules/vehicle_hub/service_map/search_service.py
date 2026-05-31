"""Vyhledávání servisních míst – radius nebo map bounds."""
from __future__ import annotations

import json
import math
from typing import Any, Iterable

from sqlalchemy.orm import Session

from ..models import ServiceLocation
from .constants import (
    ALL_CATEGORIES,
    CATEGORY_SME,
    CATEGORY_STK,
    DEFAULT_MAP_LAT,
    DEFAULT_MAP_LNG,
    VERIFICATION_CLAIMED,
    VERIFICATION_IMPORTED,
    VERIFICATION_VERIFIED,
)
from .normalize import normalize_service_name

USER_SEARCH_MAX_RADIUS_KM = 100.0
USER_SEARCH_DEFAULT_LIMIT = 100
USER_SEARCH_MAX_LIMIT = 500
ADMIN_SEARCH_MAX_RADIUS_KM = 200.0
ADMIN_SEARCH_MAX_LIMIT = 500

PII_FORBIDDEN_KEYS = frozenset(
    {
        "vin",
        "spz",
        "owner_name",
        "owner_email",
        "owner_phone",
        "vehicle_id",
        "registration_ip",
    }
)

USER_VISIBLE_VERIFICATION_STATUSES = frozenset(
    {
        VERIFICATION_IMPORTED,
        VERIFICATION_CLAIMED,
        VERIFICATION_VERIFIED,
    }
)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _radius_bbox(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    lat_delta = radius_km / 111.0
    lng_delta = radius_km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta


def _parse_json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def serialize_location(row: ServiceLocation, *, distance_km: float | None = None) -> dict[str, Any]:
    payload = {
        "id": int(row.id),
        "name": row.name,
        "category": row.category,
        "lat": float(row.lat),
        "lng": float(row.lng),
        "address_text": row.address_text,
        "city": row.city,
        "phone": row.phone,
        "website": row.website,
        "opening_hours": row.opening_hours,
        "services": _parse_json_list(row.services_json),
        "vehicle_scope": _parse_json_list(row.vehicle_scope_json),
        "verification_status": row.verification_status,
        "distance_km": round(distance_km, 2) if distance_km is not None else None,
        "source_type": row.source_type,
        "last_verified_at": row.last_verified_at.isoformat() if row.last_verified_at else None,
        "is_verified": row.verification_status in {VERIFICATION_VERIFIED, VERIFICATION_CLAIMED},
    }
    return payload


def _apply_common_filters(
    query,
    *,
    category: str | None,
    q: str | None,
    verified_only: bool,
    admin_mode: bool = False,
):
    if not admin_mode:
        query = query.filter(ServiceLocation.verification_status.in_(USER_VISIBLE_VERIFICATION_STATUSES))
    if category and category != "all":
        if category == "stk":
            query = query.filter(ServiceLocation.category.in_([CATEGORY_STK, CATEGORY_SME]))
        elif category in ALL_CATEGORIES:
            query = query.filter(ServiceLocation.category == category)
    if verified_only:
        query = query.filter(ServiceLocation.verification_status.in_([VERIFICATION_VERIFIED, VERIFICATION_CLAIMED]))
    if q:
        needle = f"%{(q or '').strip()}%"
        if needle != "%%":
            normalized_needle = f"%{normalize_service_name(q)}%"
            query = query.filter(
                (ServiceLocation.name.ilike(needle))
                | (ServiceLocation.city.ilike(needle))
                | (ServiceLocation.address_text.ilike(needle))
                | (ServiceLocation.normalized_name.ilike(normalized_needle))
            )
    return query


def search_service_locations(
    db: Session,
    *,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float = 30.0,
    north: float | None = None,
    south: float | None = None,
    east: float | None = None,
    west: float | None = None,
    category: str | None = None,
    q: str | None = None,
    verified_only: bool = False,
    vehicle_scope: str | None = None,
    limit: int = USER_SEARCH_DEFAULT_LIMIT,
    offset: int = 0,
    admin_mode: bool = False,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    max_radius = ADMIN_SEARCH_MAX_RADIUS_KM if admin_mode else USER_SEARCH_MAX_RADIUS_KM
    max_limit = ADMIN_SEARCH_MAX_LIMIT if admin_mode else USER_SEARCH_MAX_LIMIT
    default_limit = USER_SEARCH_DEFAULT_LIMIT if not admin_mode else 200

    limit = max(1, min(int(limit or default_limit), max_limit))
    offset = max(0, int(offset or 0))

    bounds_mode = all(v is not None for v in (north, south, east, west))
    center_lat = float(lat if lat is not None else DEFAULT_MAP_LAT)
    center_lng = float(lng if lng is not None else DEFAULT_MAP_LNG)

    query = db.query(ServiceLocation).filter(ServiceLocation.is_active.is_(True))
    query = _apply_common_filters(query, category=category, q=q, verified_only=verified_only, admin_mode=admin_mode)

    meta: dict[str, Any] = {"mode": "radius", "limit": limit, "offset": offset}

    if bounds_mode:
        lat_min = min(float(south), float(north))  # type: ignore[arg-type]
        lat_max = max(float(south), float(north))  # type: ignore[arg-type]
        lng_min = min(float(west), float(east))  # type: ignore[arg-type]
        lng_max = max(float(west), float(east))  # type: ignore[arg-type]
        query = query.filter(
            ServiceLocation.lat >= lat_min,
            ServiceLocation.lat <= lat_max,
            ServiceLocation.lng >= lng_min,
            ServiceLocation.lng <= lng_max,
        )
        meta["mode"] = "bounds"
        meta["bounds"] = {"north": lat_max, "south": lat_min, "east": lng_max, "west": lng_min}
        effective_radius = None
    else:
        radius_km = max(1.0, min(float(radius_km or 30.0), max_radius))
        lat_min, lat_max, lng_min, lng_max = _radius_bbox(center_lat, center_lng, radius_km)
        query = query.filter(
            ServiceLocation.lat >= lat_min,
            ServiceLocation.lat <= lat_max,
            ServiceLocation.lng >= lng_min,
            ServiceLocation.lng <= lng_max,
        )
        meta["radius_km"] = radius_km
        effective_radius = radius_km

    candidates: Iterable[ServiceLocation] = query.all()
    scored: list[tuple[ServiceLocation, float]] = []
    for row in candidates:
        dist = haversine_km(center_lat, center_lng, float(row.lat), float(row.lng))
        if effective_radius is not None and dist > effective_radius:
            continue
        if vehicle_scope:
            scope = _parse_json_list(row.vehicle_scope_json)
            if scope and vehicle_scope not in scope:
                continue
        scored.append((row, dist))

    scored.sort(key=lambda item: item[1])
    db_items = [serialize_location(row, distance_km=dist) for row, dist in scored]

    total = len(db_items)
    page = db_items[offset : offset + limit]
    items = page

    if total > limit and bounds_mode:
        lat_span = float(meta["bounds"]["north"]) - float(meta["bounds"]["south"])
        lng_span = float(meta["bounds"]["east"]) - float(meta["bounds"]["west"])
        if lat_span > 1.2 or lng_span > 1.2:
            meta["hint"] = "Přibližte mapu pro přesnější výběr servisů."

    meta["total_matched"] = total
    meta["returned"] = len(items)
    return items, total, meta
