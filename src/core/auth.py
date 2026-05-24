"""
Autentizační modul pro Správu vozidel
- JWT token validace
- Získání aktuálního uživatele
"""
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from .security import decode_access_token_payload
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer
from src.modules.vehicle_hub.account_state import (
    ensure_customer_account_state_schema,
    customer_is_deleted,
    customer_is_disabled,
    customer_session_version,
)

# HTTPBearer pro získání tokenu z Authorization headeru
security = HTTPBearer()
security_optional = HTTPBearer(auto_error=False)


def get_current_user_email(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> str:
    """
    Získá email aktuálně přihlášeného uživatele z JWT tokenu.
    
    Args:
        credentials: HTTPAuthorizationCredentials z HTTPBearer
        
    Returns:
        Email uživatele
        
    Raises:
        HTTPException: Pokud je token neplatný nebo chybí
    """
    token = credentials.credentials
    payload = decode_access_token_payload(token)
    email = (payload or {}).get("sub")

    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Neplatný nebo expirovaný token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    ensure_customer_account_state_schema(db)

    normalized_email = str(email).strip().lower()
    customer = db.query(Customer).filter(func.lower(Customer.email) == normalized_email).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Neplatný nebo expirovaný token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if customer_is_deleted(customer) or customer_is_disabled(customer):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Účet je neaktivní",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_session_version = payload.get("sv")
    try:
        token_session_version_int = int(token_session_version if token_session_version is not None else 0)
    except (TypeError, ValueError):
        token_session_version_int = 0

    if token_session_version_int != customer_session_version(customer):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session byla ukončena, přihlaste se znovu",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return email


def get_current_customer_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
    db: Session = Depends(get_db),
) -> Optional[Customer]:
    """
    Vrátí Customer pro platný Bearer token, jinak None (pro veřejné endpointy jako GET /api/me).
    """
    if credentials is None or not getattr(credentials, "credentials", None):
        return None
    token = credentials.credentials
    payload = decode_access_token_payload(token)
    email = (payload or {}).get("sub")
    if email is None:
        return None

    ensure_customer_account_state_schema(db)

    normalized_email = str(email).strip().lower()
    customer = db.query(Customer).filter(func.lower(Customer.email) == normalized_email).first()
    if not customer:
        return None

    if customer_is_deleted(customer) or customer_is_disabled(customer):
        return None

    token_session_version = payload.get("sv")
    try:
        token_session_version_int = int(token_session_version if token_session_version is not None else 0)
    except (TypeError, ValueError):
        token_session_version_int = 0

    if token_session_version_int != customer_session_version(customer):
        return None

    return customer
