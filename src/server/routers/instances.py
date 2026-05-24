"""
Instances API router
Registrace a správa instancí aplikace (multi-tenant)
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.security import create_access_token
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Instance, Tenant

router = APIRouter(prefix="/api/instances", tags=["instances"])


# ============================================
# Pydantic schémata
# ============================================


class DeviceInfo(BaseModel):
    hostname: Optional[str] = None
    os: Optional[str] = None
    app_version: Optional[str] = None


class RegisterInstanceRequest(BaseModel):
    license_key: str
    device_info: DeviceInfo


class PingRequest(BaseModel):
    app_version: Optional[str] = None


class RegisterInstanceResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: int
    instance_id: int


class PingResponse(BaseModel):
    status: str


# ============================================
# Dependency pro získání aktuální instance z JWT
# ============================================


def get_current_instance(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=True)),
) -> Instance:
    """
    Získá aktuální instanci z JWT tokenu.

    Raises:
        HTTPException: Pokud token není platný nebo instance neexistuje
    """
    token = credentials.credentials

    # Dekódovat token
    try:
        # Pro instance tokeny používáme jwt.decode přímo, protože decode_access_token
        # očekává email v "sub", ale instance tokeny mají tenant_id a instance_id
        import jwt
        from jwt import PyJWTError as JWTError

        from src.core.config import JWT_ALGORITHM, JWT_SECRET_KEY

        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

        tenant_id = payload.get("tenant_id")
        instance_id = payload.get("instance_id")

        if not tenant_id or not instance_id:
            raise HTTPException(
                status_code=401, detail="Token neobsahuje tenant_id nebo instance_id"
            )

        # Najít instanci
        instance = (
            db.query(Instance)
            .filter(Instance.id == instance_id, Instance.tenant_id == tenant_id)
            .first()
        )

        if not instance:
            raise HTTPException(status_code=404, detail="Instance nenalezena")

        return instance
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Neplatný token: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=401, detail=f"Chyba při ověřování tokenu: {str(e)}"
        )


# ============================================
# Endpointy
# ============================================


@router.post("/register", response_model=RegisterInstanceResponse)
def register_instance(payload: RegisterInstanceRequest, db: Session = Depends(get_db)):
    """
    Registruje novou instanci aplikace.

    Pokud tenant s daným license_key neexistuje, vytvoří se nový.
    """
    # Najít nebo vytvořit tenanta
    tenant = db.query(Tenant).filter(Tenant.license_key == payload.license_key).first()
    if not tenant:
        # Vytvořit nového tenanta s generickým názvem
        tenant = Tenant(
            name=f"Tenant {payload.license_key}", license_key=payload.license_key
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        try:
            from src.modules.vehicle_hub.workspace_routing import ensure_tenant_workspace_slug

            ensure_tenant_workspace_slug(
                db,
                tenant,
                seed_label=tenant.name,
                route_kind="user",
            )
            db.commit()
            db.refresh(tenant)
        except Exception:
            db.rollback()

    # Vytvořit instanci
    device_id = (
        payload.device_info.hostname or f"device_{datetime.utcnow().timestamp()}"
    )
    instance = Instance(
        tenant_id=tenant.id,
        device_id=device_id,
        app_version=payload.device_info.app_version,
        last_seen_at=datetime.utcnow(),
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)

    # Vytvořit JWT token
    token_data = {"tenant_id": tenant.id, "instance_id": instance.id}
    access_token = create_access_token(data=token_data)

    return RegisterInstanceResponse(
        access_token=access_token,
        token_type="bearer",
        tenant_id=tenant.id,
        instance_id=instance.id,
    )


@router.post("/ping", response_model=PingResponse)
def ping_instance(
    payload: PingRequest,
    current_instance: Instance = Depends(get_current_instance),
    db: Session = Depends(get_db),
):
    """
    Aktualizuje last_seen_at pro instanci.
    Volá se pravidelně (např. při startu appky a pak každých X minut).
    """
    # Aktualizovat last_seen_at
    current_instance.last_seen_at = datetime.utcnow()
    if payload.app_version:
        current_instance.app_version = payload.app_version

    db.commit()

    return PingResponse(status="ok")
