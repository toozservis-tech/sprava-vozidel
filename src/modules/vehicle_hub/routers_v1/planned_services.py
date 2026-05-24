"""
Planned Services API v1.0 router
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, PlannedService
from .auth import get_current_user
from .schemas import PlannedServiceCreateV1, PlannedServiceOutV1, PlannedServiceUpdateV1

router = APIRouter(prefix="/planned-services", tags=["planned-services-v1"])


@router.get("", response_model=List[PlannedServiceOutV1])
def get_planned_services(
    current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Získá seznam všech plánovaných servisů aktuálního uživatele"""
    try:
        planned_services = (
            db.query(PlannedService)
            .filter(
                PlannedService.tenant_id == current_user.tenant_id,
                PlannedService.user_id == current_user.id,
            )
            .all()
        )
        return planned_services
    except Exception as e:
        print(f"[PLANNED_SERVICES] Error getting planned services: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Chyba při načítání plánovaných servisů: {str(e)}",
        )


@router.get("/{planned_service_id}", response_model=PlannedServiceOutV1)
def get_planned_service(
    planned_service_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Získá detail plánovaného servisu"""
    try:
        planned_service = (
            db.query(PlannedService)
            .filter(
                PlannedService.id == planned_service_id,
                PlannedService.tenant_id == current_user.tenant_id,
                PlannedService.user_id == current_user.id,
            )
            .first()
        )

        if not planned_service:
            raise HTTPException(status_code=404, detail="Plánovaný servis nenalezen")

        return planned_service
    except HTTPException:
        raise
    except Exception as e:
        print(
            f"[PLANNED_SERVICES] Error getting planned service {planned_service_id}: {e}"
        )
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Chyba při načítání plánovaného servisu: {str(e)}",
        )


@router.post("", response_model=PlannedServiceOutV1, status_code=201)
def create_planned_service(
    planned_service_data: PlannedServiceCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Vytvoří nový plánovaný servis"""
    try:
        planned_service = PlannedService(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            vehicle_id=planned_service_data.vehicle_id,
            date=planned_service_data.date,
            description=planned_service_data.description,
            urgent=planned_service_data.urgent or False,
        )

        db.add(planned_service)
        db.commit()
        db.refresh(planned_service)

        return planned_service
    except Exception as e:
        db.rollback()
        print(f"[PLANNED_SERVICES] Error creating planned service: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Chyba při vytváření plánovaného servisu: {str(e)}",
        )


@router.put("/{planned_service_id}", response_model=PlannedServiceOutV1)
def update_planned_service(
    planned_service_id: int,
    planned_service_data: PlannedServiceUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aktualizuje plánovaný servis"""
    try:
        planned_service = (
            db.query(PlannedService)
            .filter(
                PlannedService.id == planned_service_id,
                PlannedService.tenant_id == current_user.tenant_id,
                PlannedService.user_id == current_user.id,
            )
            .first()
        )

        if not planned_service:
            raise HTTPException(status_code=404, detail="Plánovaný servis nenalezen")

        # Aktualizovat pouze poskytnutá pole
        if planned_service_data.vehicle_id is not None:
            planned_service.vehicle_id = planned_service_data.vehicle_id
        if planned_service_data.date is not None:
            planned_service.date = planned_service_data.date
        if planned_service_data.description is not None:
            planned_service.description = planned_service_data.description
        if planned_service_data.urgent is not None:
            planned_service.urgent = planned_service_data.urgent

        db.commit()
        db.refresh(planned_service)

        return planned_service
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(
            f"[PLANNED_SERVICES] Error updating planned service {planned_service_id}: {e}"
        )
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Chyba při aktualizaci plánovaného servisu: {str(e)}",
        )


@router.delete("/{planned_service_id}", status_code=204)
def delete_planned_service(
    planned_service_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Smaže plánovaný servis"""
    try:
        planned_service = (
            db.query(PlannedService)
            .filter(
                PlannedService.id == planned_service_id,
                PlannedService.tenant_id == current_user.tenant_id,
                PlannedService.user_id == current_user.id,
            )
            .first()
        )

        if not planned_service:
            raise HTTPException(status_code=404, detail="Plánovaný servis nenalezen")

        db.delete(planned_service)
        db.commit()

        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(
            f"[PLANNED_SERVICES] Error deleting planned service {planned_service_id}: {e}"
        )
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Chyba při mazání plánovaného servisu: {str(e)}",
        )
