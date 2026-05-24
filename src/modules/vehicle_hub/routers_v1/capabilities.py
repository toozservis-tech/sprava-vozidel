"""
System capabilities for frontend/admin gating.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schema_management import get_capabilities
from .auth import get_current_user
from ..models import Customer
from src.modules.vehicle_hub.service_map.map_config import build_map_tile_config
from src.server.security_tracking import reverse_geocode_location

router = APIRouter(prefix="/system", tags=["system-capabilities"])


@router.get("/maps-config")
def get_maps_config(
    current_user: Customer = Depends(get_current_user),
):
    """Mapový podklad pro servisní mapu (Leaflet) – pouze tile provider z ENV."""
    _ = current_user
    return build_map_tile_config()


@router.get("/reverse-geocode")
def reverse_geocode(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    current_user: Customer = Depends(get_current_user),
):
    """Převod GPS souřadnic na přibližnou adresu pro UI „Moje poloha“."""
    _ = current_user
    result = reverse_geocode_location(lat, lon) or {}
    return {
        "lat": lat,
        "lon": lon,
        "location_label": result.get("location_label"),
        "city": result.get("city"),
        "region": result.get("region"),
        "country": result.get("country"),
    }


@router.get("/capabilities")
def list_system_capabilities(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    return get_capabilities(db)
