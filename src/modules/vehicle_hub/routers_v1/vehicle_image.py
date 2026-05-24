"""
API v1: URL náhledu vozidla podle značky/modelu (server řeší Unsplash / šablonu / fallback).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..models import Customer
from ..database import get_db
from ..services.catalog_image_service import PLACEHOLDER_URL, get_vehicle_catalog_image_service
from .auth import get_current_user
from sqlalchemy.orm import Session

router = APIRouter(prefix="/vehicle-image", tags=["vehicle-image-v1"])


class VehicleImageOutV1(BaseModel):
    url: str
    provider: str = Field(description="unsplash | template | placeholder")
    photographer_name: Optional[str] = None
    photographer_url: Optional[str] = None


@router.get("", response_model=VehicleImageOutV1)
def get_vehicle_image(
    make: str = Query("", max_length=120, description="Značka vozidla"),
    model: str = Query("", max_length=120, description="Model"),
    year: Optional[int] = Query(None, ge=1900, le=2100, description="Rok výroby"),
    nickname: str = Query("", max_length=200, description="Přezdívka / název — doplnění dotazu, pokud chybí make+model"),
    _user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Vrátí URL obrázku vhodného pro zobrazení v UI (jednotný ořez řeší klient přes object-fit;
    Unsplash URL obsahuje parametry w/h/fit=crop).
    """
    service = get_vehicle_catalog_image_service()
    result = service.preview_from_vehicle_snapshot(
        db=db,
        vin=None,
        make=make or "",
        model=model or "",
        year=year,
        body_type=None,
        preferred_color=None,
        force_refresh=False,
        current_user=_user,
    )
    image = result.catalog_image or {}
    if not image.get("url"):
        image = {
            "url": PLACEHOLDER_URL,
            "provider": "disabled",
            "photographer_name": None,
            "photographer_url": None,
        }
    return VehicleImageOutV1(
        url=str(image.get("url") or PLACEHOLDER_URL),
        provider=str(image.get("provider") or "disabled"),
        photographer_name=None,
        photographer_url=None,
    )
