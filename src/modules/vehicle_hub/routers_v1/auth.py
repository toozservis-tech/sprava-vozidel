"""
Helper funkce pro autorizaci v1.0
"""
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..models import Customer
from ..account_state import (
    ensure_customer_account_state_schema,
    customer_is_deleted,
    customer_is_disabled,
    customer_session_version,
)
from ..service_access import service_can_read_vehicle
from ..ownership import user_owns_vehicle
from src.core.auth import get_current_user_email
from src.core.rbac import is_admin, is_service, normalize_role, service_record_write_policy, vehicle_read_policy
from src.server.security_tracking import log_user_activity


def get_current_user(
    user_email: str = Depends(get_current_user_email),
    request: Request = None,
    db: Session = Depends(get_db)
) -> Customer:
    """
    Získá aktuálního uživatele z databáze podle emailu.
    
    Raises:
        HTTPException: Pokud uživatel neexistuje
    """
    ensure_customer_account_state_schema(db)
    user = db.query(Customer).filter(Customer.email == user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    if customer_is_deleted(user) or customer_is_disabled(user):
        raise HTTPException(status_code=401, detail="Účet je neaktivní")

    log_user_activity(
        request=request,
        user_email=user.email,
        customer_id=user.id,
        tenant_id=user.tenant_id,
        endpoint=str(request.url.path) if request else None,
    )
    return user


def get_current_user_optional(
    request: Request = None,
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[Customer]:
    """
    Získá aktuálního uživatele z databáze podle emailu, pokud je přihlášen.
    Vrátí None, pokud uživatel není přihlášen nebo neexistuje.
    
    Returns:
        Customer nebo None
    """
    if not credentials:
        return None
    
    try:
        from src.core.security import decode_access_token_payload
        token = credentials.credentials
        payload = decode_access_token_payload(token)
        user_email = (payload or {}).get("sub")
        
        if not user_email:
            return None
        
        ensure_customer_account_state_schema(db)
        user = db.query(Customer).filter(Customer.email == user_email).first()
        token_session_version = (payload or {}).get("sv")
        try:
            token_session_version_int = int(token_session_version if token_session_version is not None else 0)
        except (TypeError, ValueError):
            token_session_version_int = 0

        if (
            user
            and not customer_is_deleted(user)
            and not customer_is_disabled(user)
            and token_session_version_int == customer_session_version(user)
        ):
            log_user_activity(
                request=request,
                user_email=user.email,
                customer_id=user.id,
                tenant_id=user.tenant_id,
                endpoint=str(request.url.path) if request else None,
                details={"source": "optional_auth"},
            )
            return user
        return None
    except Exception:
        return None


def require_service_workspace():
    """
    Servisní intake a podobné endpointy: role service nebo explicitní entitlement / admin.
    """
    from src.modules.vehicle_hub.workspace_entitlements import customer_has_service_workspace_access

    def checker(current_user: Customer = Depends(get_current_user)) -> Customer:
        if not customer_has_service_workspace_access(current_user):
            raise HTTPException(
                status_code=403,
                detail="Přístup zamítnut. Požadován servisní pracovní režim.",
            )
        return current_user

    return checker


def require_role(required_role: str):
    """
    Dependency pro kontrolu role uživatele.
    
    Args:
        required_role: Požadovaná role ("user", "service", "admin")
    
    Returns:
        Depends funkce, která kontroluje roli
    """
    def role_checker(
        current_user: Customer = Depends(get_current_user)
    ) -> Customer:
        if normalize_role(current_user.role) != normalize_role(required_role) and not is_admin(current_user.role):
            raise HTTPException(
                status_code=403,
                detail=f"Přístup zamítnut. Požadována role: {required_role}"
            )
        return current_user
    
    return role_checker


def get_current_user_id(
    user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db)
) -> int:
    """
    Získá ID aktuálního uživatele.
    
    Returns:
        User ID
    """
    ensure_customer_account_state_schema(db)
    user = db.query(Customer).filter(Customer.email == user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    if customer_is_deleted(user) or customer_is_disabled(user):
        raise HTTPException(status_code=401, detail="Účet je neaktivní")
    return user.id


def can_access_vehicle(
    vehicle_id: int,
    current_user: Customer,
    db: Session
) -> bool:
    """
    Kontroluje, zda má uživatel přístup k vozidlu.
    
    Rules:
    - role "user": pouze vlastní vozidla
    - role "service": vlastní vozidla + vozidla zákazníků s intake/rezervací
    - role "admin": všechna vozidla
    
    Returns:
        True pokud má přístup
    """
    from ..models import Vehicle
    
    # Admin má přístup ke všemu
    if is_admin(current_user.role):
        return True
    
    # Najít vozidlo
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        return False
    
    # Vlastník vozidla má vždy přístup
    if user_owns_vehicle(db, current_user, vehicle):
        return True

    # Servis: výhradně VehicleServiceLink (schválený přístup) nebo legacy zrcadlo v service_access.
    # Obecný vehicle_read_policy zde nesmí otevřít bypass bez explicitního odkazu.
    role_key = normalize_role(current_user.role)
    if is_service(role_key):
        if (
            not user_owns_vehicle(db, current_user, vehicle)
            and getattr(vehicle, "provisioned_by_service_customer_id", None) == getattr(current_user, "id", None)
            and str(getattr(vehicle, "global_vehicle_status", "") or "") == "service_provisioned_unowned"
        ):
            return True
        return service_can_read_vehicle(db, current_user, vehicle_id)

    return vehicle_read_policy(role=role_key, is_owner=False, has_service_access=False).allowed
