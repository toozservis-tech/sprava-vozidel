"""
VIN Lookup API v1.0 router
GET endpoint pro jednoduché VIN lookup
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from ..database import get_db
from ..decoder.models import VinDecodeRequest, VehicleDecodeResponse
from ..models import Customer
from ..routers_v1.auth import get_current_user_optional
from ..vin_ownership_guard import (
    VinAlreadyRegisteredOtherUserError,
    assert_vin_visible_for_create,
    vin_other_tenant_block_payload,
)

router = APIRouter(prefix="/vin", tags=["vin-lookup-v1"])


class VinLookupResponse(BaseModel):
    """Zjednodušená odpověď pro VIN lookup"""
    vin: str
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine: Optional[str] = None
    source: str = "unknown"
    detail: Optional[str] = None


@router.get("/{vin}", response_model=VinLookupResponse)
async def lookup_vin(
    vin: str,
    db: Session = Depends(get_db),
    current_user: Optional[Customer] = Depends(get_current_user_optional),
):
    """
    Jednoduchý VIN lookup endpoint pro auto-fill formulářů
    
    Args:
        vin: VIN kód (17 znaků)
        
    Returns:
        VinLookupResponse s dekódovanými daty
    """
    import logging
    logger = logging.getLogger(__name__)
    
    vin_clean = vin.strip().upper().replace(" ", "").replace("-", "")
    
    # Validace VIN
    if len(vin_clean) != 17:
        logger.warning(f"[VIN_LOOKUP] Invalid VIN length: {len(vin_clean)}")
        raise HTTPException(status_code=422, detail="VIN musí mít přesně 17 znaků")
    
    if not vin_clean.isalnum():
        logger.warning(f"[VIN_LOOKUP] Invalid VIN format (non-alphanumeric)")
        raise HTTPException(status_code=422, detail="VIN může obsahovat pouze alfanumerické znaky")
    
    logger.info(f"[VIN_LOOKUP] Processing VIN lookup: {vin_clean[:3]}...{vin_clean[-3:]}")
    
    try:
        if current_user is not None and getattr(current_user, "tenant_id", None):
            assert_vin_visible_for_create(
                db,
                getattr(current_user, "tenant_id", None),
                vin_clean,
                endpoint="/api/v1/vin/{vin}",
                validate=False,
            )
        # Použít existující decoder (lazy import pro vyhnutí se cyklu)
        from ..decoder.router import decode_vin_core  # import uvnitř funkce
        decode_request = VinDecodeRequest(vin=vin_clean)
        decode_response: VehicleDecodeResponse = await decode_vin_core(decode_request, db, current_user)
        
        if not decode_response.success or not decode_response.data:
            # Pokud decoder nevrátil data, vrať prázdnou odpověď
            return VinLookupResponse(
                vin=vin_clean,
                source="manual",
                detail="VIN provider not configured or no data available"
            )
        
        data = decode_response.data
        
        # Mapování dat z decoder response
        make = data.make if hasattr(data, 'make') and data.make else None
        model = data.model if hasattr(data, 'model') and data.model else None
        year = None
        engine = None
        
        # Rok - zkusit různé atributy
        if hasattr(data, 'year') and data.year:
            year = data.year
        elif hasattr(data, 'model_year') and data.model_year:
            year = data.model_year
        elif hasattr(data, 'production_year') and data.production_year:
            year = data.production_year
        
        # Motor - kombinace displacement + power + fuel_type
        engine_parts = []
        if hasattr(data, 'engine_displacement_cc') and data.engine_displacement_cc:
            engine_parts.append(f"{data.engine_displacement_cc} cm³")
        if hasattr(data, 'engine_power_kw') and data.engine_power_kw:
            engine_parts.append(f"{data.engine_power_kw} kW")
        if hasattr(data, 'fuel_type') and data.fuel_type:
            engine_parts.append(data.fuel_type)
        
        if engine_parts:
            engine = " / ".join(engine_parts)
        elif hasattr(data, 'engine') and data.engine:
            engine = data.engine
        elif hasattr(data, 'engine_code') and data.engine_code:
            engine = data.engine_code
        elif hasattr(data, 'engine_type') and data.engine_type:
            engine = data.engine_type
        
        # Určit source
        source = "unknown"
        if hasattr(data, 'source_priority') and data.source_priority:
            source = data.source_priority[0] if isinstance(data.source_priority, list) and data.source_priority else str(data.source_priority)
        elif decode_response.errors:
            source = "partial"
        else:
            source = "provider"
        
        logger.info(f"[VIN_LOOKUP] Success: make={make}, model={model}, year={year}, source={source}")
        
        return VinLookupResponse(
            vin=vin_clean,
            make=make,
            model=model,
            year=year,
            engine=engine,
            source=source
        )
        
    except VinAlreadyRegisteredOtherUserError:
        return JSONResponse(status_code=409, content=vin_other_tenant_block_payload())
    except HTTPException:
        raise
    except Exception as e:
        # Pokud decoder selže, vrať prázdnou odpověď s vysvětlením
        logger.error(f"[VIN_LOOKUP] Error: {type(e).__name__}: {str(e)}")
        return VinLookupResponse(
            vin=vin_clean,
            source="manual",
            detail=f"VIN provider error: {str(e)}"
        )
