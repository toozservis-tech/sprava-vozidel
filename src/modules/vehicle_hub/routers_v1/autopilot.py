"""
Autopilot M2M API v1.0 router
API pro machine-to-machine komunikaci s integrací Autopilot
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import hashlib
import hmac

from src.core.branding import APP_DISPLAY_NAME
from ..database import get_db
from ..models import Vehicle as VehicleModel, ServiceRecord as ServiceRecordModel, Customer
from ..ownership import get_owned_vehicle_rows, get_primary_vehicle_owner
from src.core.config import AUTOPILOT_SHARED_SECRET


router = APIRouter(prefix="/api/autopilot", tags=["autopilot-m2m"])


def verify_autopilot_secret(x_autopilot_secret: str = Header(None)) -> bool:
    """
    Ověří shared secret pro Autopilot API.
    Používá konstantní časovou porovnávání pro ochranu proti timing útokům.
    """
    if not AUTOPILOT_SHARED_SECRET:
        raise HTTPException(
            status_code=500,
            detail="AUTOPILOT_SHARED_SECRET není nakonfigurován na serveru"
        )
    
    if not x_autopilot_secret:
        raise HTTPException(
            status_code=401,
            detail="Chybí X-Autopilot-Secret header"
        )
    
    # Konstantní časové porovnání (ochrana proti timing útokům)
    if not hmac.compare_digest(x_autopilot_secret, AUTOPILOT_SHARED_SECRET):
        raise HTTPException(
            status_code=401,
            detail="Neplatný Autopilot secret"
        )
    
    return True


@router.get("/health")
def autopilot_health():
    """Health check pro Autopilot API (nevyžaduje autentizaci)"""
    return {
        "status": "online",
        "service": f"{APP_DISPLAY_NAME} Autopilot API",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/user/{user_id}/vehicles")
def get_user_vehicles(
    user_id: int,
    _: bool = Depends(verify_autopilot_secret),
    db: Session = Depends(get_db)
):
    """
    Získá seznam vozidel uživatele.
    Vyžaduje X-Autopilot-Secret header.
    """
    user = db.query(Customer).filter(Customer.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    
    vehicles = get_owned_vehicle_rows(db, user, tenant_id=getattr(user, "tenant_id", None))
    
    return {
        "user_id": user_id,
        "vehicles": [
            {
                "id": v.id,
                "nickname": v.nickname,
                "brand": v.brand,
                "model": v.model,
                "plate": v.plate,
                "vin": v.vin
            }
            for v in vehicles
        ]
    }


@router.get("/vehicle/{vehicle_id}/last-service")
def get_last_service(
    vehicle_id: int,
    _: bool = Depends(verify_autopilot_secret),
    db: Session = Depends(get_db)
):
    """
    Získá poslední servisní záznam vozidla.
    Vyžaduje X-Autopilot-Secret header.
    """
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    last_record = db.query(ServiceRecordModel).filter(
        ServiceRecordModel.vehicle_id == vehicle_id
    ).order_by(ServiceRecordModel.performed_at.desc()).first()
    
    if not last_record:
        return {
            "vehicle_id": vehicle_id,
            "last_service": None,
            "message": "Žádný servisní záznam"
        }
    
    return {
        "vehicle_id": vehicle_id,
        "last_service": {
            "id": last_record.id,
            "performed_at": last_record.performed_at.isoformat() if last_record.performed_at else None,
            "mileage": last_record.mileage,
            "description": last_record.description,
            "category": last_record.category,
            "price": last_record.price
        }
    }


@router.post("/vehicle/{vehicle_id}/quick-record")
def create_quick_record(
    vehicle_id: int,
    description: str,
    mileage: Optional[int] = None,
    price: Optional[float] = None,
    category: Optional[str] = None,
    _: bool = Depends(verify_autopilot_secret),
    db: Session = Depends(get_db)
):
    """
    Rychlé vytvoření servisního záznamu z Autopilota.
    Vyžaduje X-Autopilot-Secret header.
    """
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Získat ID uživatele z vozidla
    user = get_primary_vehicle_owner(db, vehicle)
    user_id = user.id if user else None
    
    record = ServiceRecordModel(
        tenant_id=vehicle.tenant_id or getattr(user, "tenant_id", None) or 1,
        vehicle_id=vehicle_id,
        user_id=user_id,
        performed_at=datetime.now(),
        mileage=mileage,
        description=description,
        price=price,
        category=category or "GENERAL",
        note=f"Vytvořeno z autopilot integrace ({APP_DISPLAY_NAME})"
    )
    
    db.add(record)
    db.commit()
    db.refresh(record)
    
    return {
        "status": "ok",
        "record_id": record.id,
        "vehicle_id": vehicle_id,
        "message": "Servisní záznam vytvořen"
    }











