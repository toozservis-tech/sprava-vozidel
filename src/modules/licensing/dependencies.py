"""
FastAPI dependencies pro licenční systém
"""
from typing import Callable

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..vehicle_hub.database import get_db
from ..vehicle_hub.routers_v1.auth import get_current_user
from ..vehicle_hub.models import Customer
from .licensing_service import get_effective_entitlement, require_plan_active
from .types import EffectiveEntitlement


def require_plan_active_dependency(
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user)
) -> None:
    """
    Dependency pro kontrolu, zda je plán aktivní.
    
    Raises:
        HTTPException 403: Pokud status není ACTIVE
    """
    entitlement = get_effective_entitlement(db, current_user)
    if not entitlement.is_active:
        raise HTTPException(
            status_code=403,
            detail=f"License is not active (status: {entitlement.status.value}). Please activate your license.",
        )


def require_feature(feature_name: str):
    """
    Dependency factory pro kontrolu feature flagu.
    Zatím optional - pro budoucí použití.
    
    Usage:
        @router.get("/advanced-report")
        def get_advanced_report(
            _: None = Depends(require_feature("feature_advanced_reports"))
        ):
            ...
    
    Args:
        feature_name: Název feature flagu (např. "feature_advanced_reports")
        
    Returns:
        Dependency funkce
    """
    def _check_feature(
        current_user: Customer = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> None:
        """
        Kontroluje, zda má uživatel přístup k dané funkci.
        
        Raises:
            HTTPException 403: Pokud funkce není dostupná nebo licence není aktivní
        """
        entitlement = get_effective_entitlement(db, current_user)
        
        # Kontrola, zda je licence aktivní
        if not entitlement.is_active:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Funkce '{feature_name}' není dostupná - licence není aktivní "
                    f"(status: {entitlement.status.value})."
                )
            )
        
        # TODO: Implementovat feature flagy podle plánu
        # Prozatím vracíme chybu
        raise HTTPException(
            status_code=501,
            detail=f"Feature flags are not yet implemented"
        )
    
    return _check_feature


def get_effective_entitlement_dependency(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> EffectiveEntitlement:
    """
    Dependency pro získání efektivního oprávnění uživatele.
    
    Returns:
        EffectiveEntitlement s kompletními informacemi o licenci
    """
    return get_effective_entitlement(db, current_user)










