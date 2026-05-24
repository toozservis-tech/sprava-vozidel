"""
Manufacturers API v1.0 router
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, Manufacturer
from .auth import get_current_user
from .schemas import ManufacturerCreateV1, ManufacturerOutV1, ManufacturerUpdateV1

router = APIRouter(prefix="/manufacturers", tags=["manufacturers-v1"])


@router.get("", response_model=List[ManufacturerOutV1])
def get_manufacturers(
    current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Získá seznam všech výrobců aktuálního uživatele"""
    try:
        manufacturers = (
            db.query(Manufacturer)
            .filter(
                Manufacturer.tenant_id == current_user.tenant_id,
                Manufacturer.user_id == current_user.id,
            )
            .all()
        )
        return manufacturers
    except Exception as e:
        print(f"[MANUFACTURERS] Error getting manufacturers: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při načítání výrobců: {str(e)}"
        )


@router.get("/{manufacturer_id}", response_model=ManufacturerOutV1)
def get_manufacturer(
    manufacturer_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Získá detail výrobce"""
    try:
        manufacturer = (
            db.query(Manufacturer)
            .filter(
                Manufacturer.id == manufacturer_id,
                Manufacturer.tenant_id == current_user.tenant_id,
                Manufacturer.user_id == current_user.id,
            )
            .first()
        )

        if not manufacturer:
            raise HTTPException(status_code=404, detail="Výrobce nenalezen")

        return manufacturer
    except HTTPException:
        raise
    except Exception as e:
        print(f"[MANUFACTURERS] Error getting manufacturer {manufacturer_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při načítání výrobce: {str(e)}"
        )


@router.post("", response_model=ManufacturerOutV1, status_code=201)
def create_manufacturer(
    manufacturer_data: ManufacturerCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Vytvoří nového výrobce"""
    try:
        manufacturer = Manufacturer(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            name=manufacturer_data.name,
            country=manufacturer_data.country,
            url=manufacturer_data.url,
            concern_id=manufacturer_data.concern_id,
        )

        db.add(manufacturer)
        db.commit()
        db.refresh(manufacturer)

        return manufacturer
    except Exception as e:
        db.rollback()
        print(f"[MANUFACTURERS] Error creating manufacturer: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při vytváření výrobce: {str(e)}"
        )


@router.put("/{manufacturer_id}", response_model=ManufacturerOutV1)
def update_manufacturer(
    manufacturer_id: int,
    manufacturer_data: ManufacturerUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aktualizuje výrobce"""
    try:
        manufacturer = (
            db.query(Manufacturer)
            .filter(
                Manufacturer.id == manufacturer_id,
                Manufacturer.tenant_id == current_user.tenant_id,
                Manufacturer.user_id == current_user.id,
            )
            .first()
        )

        if not manufacturer:
            raise HTTPException(status_code=404, detail="Výrobce nenalezen")

        # Aktualizovat pouze poskytnutá pole
        if manufacturer_data.name is not None:
            manufacturer.name = manufacturer_data.name
        if manufacturer_data.country is not None:
            manufacturer.country = manufacturer_data.country
        if manufacturer_data.url is not None:
            manufacturer.url = manufacturer_data.url
        if manufacturer_data.concern_id is not None:
            manufacturer.concern_id = manufacturer_data.concern_id

        db.commit()
        db.refresh(manufacturer)

        return manufacturer
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[MANUFACTURERS] Error updating manufacturer {manufacturer_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při aktualizaci výrobce: {str(e)}"
        )


@router.delete("/{manufacturer_id}", status_code=204)
def delete_manufacturer(
    manufacturer_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Smaže výrobce"""
    try:
        manufacturer = (
            db.query(Manufacturer)
            .filter(
                Manufacturer.id == manufacturer_id,
                Manufacturer.tenant_id == current_user.tenant_id,
                Manufacturer.user_id == current_user.id,
            )
            .first()
        )

        if not manufacturer:
            raise HTTPException(status_code=404, detail="Výrobce nenalezen")

        db.delete(manufacturer)
        db.commit()

        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[MANUFACTURERS] Error deleting manufacturer {manufacturer_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při mazání výrobce: {str(e)}"
        )
