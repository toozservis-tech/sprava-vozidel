"""
Service Intake API v1.0 router (Příjem zakázky v servisu)
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from src.core.rbac import is_admin

from ..database import get_db
from ..models import ServiceIntake as ServiceIntakeModel, Vehicle as VehicleModel, Customer
from .auth import get_current_user, require_service_workspace
from .schemas import ServiceIntakeCreateV1, ServiceIntakeOutV1

router = APIRouter(prefix="/service", tags=["service-intake-v1"])


@router.post("/intake", response_model=ServiceIntakeOutV1)
def create_service_intake(
    intake_data: ServiceIntakeCreateV1,
    current_user: Customer = Depends(require_service_workspace()),
    db: Session = Depends(get_db)
):
    """Vytvoří nový příjem zakázky v servisu (pouze pro role service)"""
    service_id = current_user.id
    
    # Ověřit, že vozidlo existuje
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == intake_data.vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Ověřit, že zákazník existuje
    customer = db.query(Customer).filter(Customer.id == intake_data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Zákazník nenalezen")
    
    # Vytvořit intake
    intake = ServiceIntakeModel(
        service_id=service_id,
        vehicle_id=intake_data.vehicle_id,
        customer_id=intake_data.customer_id,
        odometer_km=intake_data.odometer_km,
        fluids_ok=intake_data.fluids_ok,
        damage_description=intake_data.damage_description,
        photos=intake_data.photos,
        work_description=intake_data.work_description,
        signature=intake_data.signature
    )
    
    db.add(intake)
    db.commit()
    db.refresh(intake)
    
    return intake


@router.get("/intake/{intake_id}", response_model=ServiceIntakeOutV1)
def get_service_intake(
    intake_id: int,
    current_user: Customer = Depends(require_service_workspace()),
    db: Session = Depends(get_db)
):
    """Vrací konkrétní příjem zakázky"""
    intake = db.query(ServiceIntakeModel).filter(ServiceIntakeModel.id == intake_id).first()
    
    if not intake:
        raise HTTPException(status_code=404, detail="Příjem zakázky nenalezen")
    
    # Kontrola, zda patří aktuálnímu servisu
    if intake.service_id != current_user.id and not is_admin(current_user.role):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto příjmu zakázky")
    
    return intake


@router.get("/intake", response_model=List[ServiceIntakeOutV1])
def list_service_intakes(
    service_id: Optional[int] = Query(None),
    current_user: Customer = Depends(require_service_workspace()),
    db: Session = Depends(get_db)
):
    """Vrací seznam příjmů zakázek pro servis"""
    service_id_to_query = service_id if service_id else current_user.id
    
    # Admin může vidět všechny, service pouze své
    if not is_admin(current_user.role) and service_id_to_query != current_user.id:
        raise HTTPException(status_code=403, detail="Nemáte přístup k příjmům zakázek jiného servisu")
    
    intakes = db.query(ServiceIntakeModel).filter(
        ServiceIntakeModel.service_id == service_id_to_query
    ).order_by(ServiceIntakeModel.created_at.desc()).all()
    
    return intakes


