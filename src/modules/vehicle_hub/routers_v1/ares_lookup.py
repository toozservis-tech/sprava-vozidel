"""
ARES Lookup API v1.0 router
GET endpoint pro ARES IČO lookup
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import requests

from ..database import get_db
from ..models import Customer
from .auth import get_current_user_optional

router = APIRouter(prefix="/ares", tags=["ares-lookup-v1"])


class AresLookupResponse(BaseModel):
    """Odpověď pro ARES lookup"""
    ico: str
    company_name: Optional[str] = None
    dic: Optional[str] = None
    street: Optional[str] = None
    house_number: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    source: str = "ares"


@router.get("/{ico}", response_model=AresLookupResponse)
def lookup_ares(
    ico: str,
    current_user: Optional[Customer] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    ARES lookup podle IČO pro auto-fill formulářů.
    Dostupné i bez přihlášení (stránka registrace), u přihlášeného tenanta
    stále platí licenční příznak ares_enabled.
    """
    import logging
    from fastapi import HTTPException
    from ...licensing.service import assert_feature
    
    logger = logging.getLogger(__name__)
    
    # Při přihlášeném účtu kontrola feature; anonymní = povoleno (pouze veřejné údaje z ARES)
    if current_user is not None:
        tenant_id = getattr(current_user, "tenant_id", None)
        if tenant_id:
            try:
                assert_feature(db, tenant_id, "ares")
            except HTTPException as e:
                logger.warning(f"[ARES_LOOKUP] ARES disabled for tenant_id={tenant_id}")
                raise
    
    ico_clean = ico.strip().replace(' ', '')
    
    # Validace IČO
    if not ico_clean.isdigit() or len(ico_clean) != 8:
        logger.warning(f"[ARES_LOOKUP] Invalid IČO format: {ico_clean}")
        raise HTTPException(status_code=422, detail="IČO musí obsahovat přesně 8 číslic")
    
    logger.info(f"[ARES_LOOKUP] Processing IČO lookup: {ico_clean}")
    
    try:
        # Volání ARES API
        url = f"https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/{ico_clean}"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="IČO nenalezeno v ARES")
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=503,
                detail=f"ARES unavailable (status: {response.status_code})"
            )
        
        data = response.json()
        
        # Mapování dat z ARES API
        company_name = None
        dic = None
        street = None
        house_number = None
        city = None
        zip_code = None
        
        # Název firmy
        if "obchodniJmeno" in data:
            company_name = data["obchodniJmeno"]
        elif "nazev" in data:
            company_name = data["nazev"]
        
        # DIČ
        if "dic" in data:
            dic = data["dic"]
        
        # Adresa ze sídla
        if "sidlo" in data:
            sidlo = data["sidlo"]
            
            # Ulice
            if "nazevUlice" in sidlo:
                street = sidlo["nazevUlice"]
            
            # Číslo popisné - kombinace cisloDomovni + cisloOrientacni
            house_parts = []
            if "cisloDomovni" in sidlo:
                house_parts.append(str(sidlo["cisloDomovni"]))
            if "cisloOrientacni" in sidlo:
                house_parts.append(str(sidlo["cisloOrientacni"]))
            if "cisloOrientacniPismeno" in sidlo:
                house_parts.append(str(sidlo["cisloOrientacniPismeno"]))
            
            if house_parts:
                house_number = "/".join(house_parts)
            
            # Město
            if "nazevObce" in sidlo:
                city = sidlo["nazevObce"]
            
            # PSČ
            if "psc" in sidlo:
                zip_code = str(sidlo["psc"])
        
        logger.info(f"[ARES_LOOKUP] Success: company={company_name}, city={city}")
        
        return AresLookupResponse(
            ico=ico_clean,
            company_name=company_name,
            dic=dic,
            street=street,
            house_number=house_number,
            city=city,
            zip=zip_code,
            source="ares"
        )
        
    except HTTPException:
        raise
    except requests.exceptions.Timeout:
        logger.error(f"[ARES_LOOKUP] Timeout for IČO: {ico_clean}")
        raise HTTPException(status_code=503, detail="ARES unavailable (timeout)")
    except requests.exceptions.RequestException as e:
        logger.error(f"[ARES_LOOKUP] Request error for IČO {ico_clean}: {str(e)}")
        raise HTTPException(status_code=503, detail=f"ARES unavailable: {str(e)}")
    except Exception as e:
        logger.error(f"[ARES_LOOKUP] Unexpected error for IČO {ico_clean}: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chyba při načítání z ARES: {str(e)}")
