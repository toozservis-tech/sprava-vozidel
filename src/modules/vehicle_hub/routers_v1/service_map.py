"""Veřejné API servisní mapy."""
from __future__ import annotations

import hashlib
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.rbac import is_service

from ..audit_log import write_global_audit_log
from ..database import get_db
from ..models import Customer, ServiceLocation, ServiceLocationReport
from ..schema_management import assert_module_ready
from .auth import get_current_user
from ..service_map.claim_service import create_service_location_claim
from ..service_map.constants import CATEGORY_LABELS, SOURCE_LABELS, VERIFICATION_DUPLICATE
from ..service_map.mapy_geocoding import mapy_geocode_suggest
from ..service_map.search_query import parse_service_map_search_text
from ..service_map.search_service import (
    USER_SEARCH_DEFAULT_LIMIT,
    USER_SEARCH_MAX_LIMIT,
    haversine_km,
    search_service_locations,
    serialize_location,
)

router = APIRouter(prefix="/service-map", tags=["service-map-v1"])


class ServiceLocationReportIn(BaseModel):
    report_type: str = Field(..., min_length=3, max_length=32)
    report_text: Optional[str] = Field(default=None, max_length=2000)


class ServiceLocationClaimIn(BaseModel):
    ico: Optional[str] = Field(default=None, max_length=16)
    dic: Optional[str] = Field(default=None, max_length=16)
    business_name: Optional[str] = Field(default=None, max_length=255)
    claim_method: Optional[str] = Field(default="admin_review", max_length=32)


def _hash_client_value(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_service_account(user: Customer) -> None:
    if not is_service(getattr(user, "role", None)):
        raise HTTPException(status_code=403, detail="Pouze servisní účet může nárokovat místo.")


@router.get("/search")
def service_map_search(
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lng: Optional[float] = Query(default=None, ge=-180, le=180),
    radius_km: float = Query(default=30.0, ge=1, le=100),
    north: Optional[float] = Query(default=None, ge=-90, le=90),
    south: Optional[float] = Query(default=None, ge=-90, le=90),
    east: Optional[float] = Query(default=None, ge=-180, le=180),
    west: Optional[float] = Query(default=None, ge=-180, le=180),
    category: Optional[str] = Query(default=None, max_length=32),
    q: Optional[str] = Query(default=None, max_length=128),
    verified_only: bool = Query(default=False),
    vehicle_scope: Optional[str] = Query(default=None, max_length=32),
    limit: int = Query(default=USER_SEARCH_DEFAULT_LIMIT, ge=1, le=USER_SEARCH_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "service_map", detail_prefix="Servisní mapa není připravená")

    search_lat = lat
    search_lng = lng
    search_category = category
    search_q = q
    parsed = parse_service_map_search_text(q) if q else {}
    if parsed.get("category") and not search_category:
        search_category = str(parsed["category"])
    location_query = parsed.get("location_query")
    if location_query and search_lat is None and search_lng is None:
        hits = mapy_geocode_suggest(str(location_query), limit=1)
        if hits:
            search_lat = float(hits[0]["lat"])
            search_lng = float(hits[0]["lon"])
            search_q = None
    elif parsed.get("category") and not parsed.get("location_query"):
        search_q = None

    items, total, meta = search_service_locations(
        db,
        lat=search_lat,
        lng=search_lng,
        radius_km=radius_km,
        north=north,
        south=south,
        east=east,
        west=west,
        category=search_category,
        q=search_q,
        verified_only=verified_only,
        vehicle_scope=vehicle_scope,
        limit=limit,
        offset=offset,
        admin_mode=False,
    )
    return {"items": items, "total": total, **meta}


@router.get("/locations/{location_id}")
def service_map_location_detail(
    location_id: int,
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lng: Optional[float] = Query(default=None, ge=-180, le=180),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "service_map", detail_prefix="Servisní mapa není připravená")
    row = db.query(ServiceLocation).filter(ServiceLocation.id == location_id, ServiceLocation.is_active.is_(True)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Servisní místo nenalezeno.")
    if row.verification_status == VERIFICATION_DUPLICATE:
        raise HTTPException(status_code=404, detail="Servisní místo nenalezeno.")

    distance = None
    if lat is not None and lng is not None:
        distance = haversine_km(float(lat), float(lng), float(row.lat), float(row.lng))

    payload = serialize_location(row, distance_km=distance)
    payload["category_label"] = CATEGORY_LABELS.get(row.category, row.category)
    payload["source_label"] = SOURCE_LABELS.get(row.source_type, row.source_type)
    payload["street"] = row.street
    payload["postal_code"] = row.postal_code
    payload["region"] = row.region
    payload["unverified_notice"] = (
        "Neověřený záznam – údaje se mohou lišit."
        if row.verification_status in {"imported", "duplicate"}
        else None
    )
    return payload


@router.post("/locations/{location_id}/report")
def service_map_report_location(
    location_id: int,
    body: ServiceLocationReportIn,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "service_map", detail_prefix="Servisní mapa není připravená")
    row = db.query(ServiceLocation).filter(ServiceLocation.id == location_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Servisní místo nenalezeno.")

    report = ServiceLocationReport(
        service_location_id=location_id,
        report_type=body.report_type.strip(),
        report_text=(body.report_text or "").strip() or None,
        reported_by_user_id=int(current_user.id),
        status="open",
    )
    db.add(report)
    db.flush()
    write_global_audit_log(
        db,
        entity_type="service_location_report",
        entity_id=int(report.id),
        action="report_created",
        actor_user_id=int(current_user.id),
        tenant_id=int(getattr(current_user, "tenant_id", 0) or 0) or None,
        metadata={"service_location_id": location_id, "report_type": body.report_type},
    )
    db.commit()
    return {"id": int(report.id), "status": report.status}


@router.post("/locations/{location_id}/claim")
def service_map_claim_location(
    location_id: int,
    body: ServiceLocationClaimIn,
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "service_map", detail_prefix="Servisní mapa není připravená")
    _require_service_account(current_user)
    tenant_id = int(getattr(current_user, "tenant_id", 0) or 0)
    if tenant_id <= 0:
        raise HTTPException(status_code=400, detail="Servisní tenant není k dispozici.")

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    claim = create_service_location_claim(
        db,
        location_id=location_id,
        service_tenant_id=tenant_id,
        submitted_by_user_id=int(current_user.id),
        ico=body.ico,
        dic=body.dic,
        business_name=body.business_name,
        claim_method=body.claim_method or "admin_review",
        ip_hash=_hash_client_value(ip),
        user_agent_hash=_hash_client_value(ua),
    )
    return {
        "id": int(claim.id),
        "claim_status": claim.claim_status,
        "service_location_id": int(claim.service_location_id),
    }
