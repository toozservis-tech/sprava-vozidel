"""
Helper funkce pro multi-tenant autorizaci
"""
from typing import Optional

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from src.core.config import JWT_ALGORITHM, JWT_SECRET_KEY

from ..database import get_db
from ..models import Tenant


def get_current_tenant(
    db: Session = Depends(get_db), credentials: Optional[str] = None
) -> Tenant:
    """
    Získá aktuálního tenanta z JWT tokenu.
    Pro instance tokeny (tenant_id + instance_id) nebo user tokeny (email -> customer -> tenant_id)

    Raises:
        HTTPException: Pokud token není platný nebo tenant neexistuje
    """
    import jwt
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from jwt import PyJWTError as JWTError

    # Zkusit získat token z Authorization headeru
    security = HTTPBearer(auto_error=False)
    try:
        creds: HTTPAuthorizationCredentials = Depends(security)
        if creds:
            token = creds.credentials
        elif credentials:
            token = credentials
        else:
            raise HTTPException(status_code=401, detail="Chybí autorizační token")
    except Exception:
        if credentials:
            token = credentials
        else:
            raise HTTPException(status_code=401, detail="Chybí autorizační token")

    # Dekódovat token
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

        # Zkusit získat tenant_id přímo (pro instance tokeny)
        tenant_id = payload.get("tenant_id")
        if tenant_id:
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
            if tenant:
                return tenant

        # Pokud není tenant_id, zkusit získat z emailu (pro user tokeny)
        email = payload.get("sub")
        if email:
            from ..models import Customer

            customer = db.query(Customer).filter(Customer.email == email).first()
            if customer and customer.tenant_id:
                tenant = (
                    db.query(Tenant).filter(Tenant.id == customer.tenant_id).first()
                )
                if tenant:
                    return tenant

        raise HTTPException(status_code=401, detail="Token neobsahuje tenant_id")
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Neplatný token: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=401, detail=f"Chyba při ověřování tokenu: {str(e)}"
        )
