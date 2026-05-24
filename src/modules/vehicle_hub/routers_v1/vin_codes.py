"""
VIN Codes API v1.0 router
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, VINCode
from .auth import get_current_user
from .schemas import VINCodeCreateV1, VINCodeOutV1, VINCodeUpdateV1

router = APIRouter(prefix="/vin-codes", tags=["vin-codes-v1"])


@router.get("", response_model=List[VINCodeOutV1])
def get_vin_codes(
    current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Získá seznam všech VIN kódů aktuálního uživatele"""
    try:
        vin_codes = (
            db.query(VINCode)
            .filter(
                VINCode.tenant_id == current_user.tenant_id,
                VINCode.user_id == current_user.id,
            )
            .all()
        )
        return vin_codes
    except Exception as e:
        print(f"[VIN_CODES] Error getting VIN codes: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při načítání VIN kódů: {str(e)}"
        )


@router.get("/{vin_code_id}", response_model=VINCodeOutV1)
def get_vin_code(
    vin_code_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Získá detail VIN kódu"""
    try:
        vin_code = (
            db.query(VINCode)
            .filter(
                VINCode.id == vin_code_id,
                VINCode.tenant_id == current_user.tenant_id,
                VINCode.user_id == current_user.id,
            )
            .first()
        )

        if not vin_code:
            raise HTTPException(status_code=404, detail="VIN kód nenalezen")

        return vin_code
    except HTTPException:
        raise
    except Exception as e:
        print(f"[VIN_CODES] Error getting VIN code {vin_code_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při načítání VIN kódu: {str(e)}"
        )


@router.post("", response_model=VINCodeOutV1, status_code=201)
def create_vin_code(
    vin_code_data: VINCodeCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Vytvoří nový VIN kód"""
    try:
        vin_code = VINCode(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            mask=vin_code_data.mask,
            complete=vin_code_data.complete,
            manufacturer=vin_code_data.manufacturer,
            model=vin_code_data.model,
            engine=vin_code_data.engine,
            subtype=vin_code_data.subtype,
            link=vin_code_data.link,
            additional_info=vin_code_data.additional_info,
        )

        db.add(vin_code)
        db.commit()
        db.refresh(vin_code)

        return vin_code
    except Exception as e:
        db.rollback()
        print(f"[VIN_CODES] Error creating VIN code: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při vytváření VIN kódu: {str(e)}"
        )


@router.put("/{vin_code_id}", response_model=VINCodeOutV1)
def update_vin_code(
    vin_code_id: int,
    vin_code_data: VINCodeUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aktualizuje VIN kód"""
    try:
        vin_code = (
            db.query(VINCode)
            .filter(
                VINCode.id == vin_code_id,
                VINCode.tenant_id == current_user.tenant_id,
                VINCode.user_id == current_user.id,
            )
            .first()
        )

        if not vin_code:
            raise HTTPException(status_code=404, detail="VIN kód nenalezen")

        # Aktualizovat pouze poskytnutá pole
        if vin_code_data.mask is not None:
            vin_code.mask = vin_code_data.mask
        if vin_code_data.complete is not None:
            vin_code.complete = vin_code_data.complete
        if vin_code_data.manufacturer is not None:
            vin_code.manufacturer = vin_code_data.manufacturer
        if vin_code_data.model is not None:
            vin_code.model = vin_code_data.model
        if vin_code_data.engine is not None:
            vin_code.engine = vin_code_data.engine
        if vin_code_data.subtype is not None:
            vin_code.subtype = vin_code_data.subtype
        if vin_code_data.link is not None:
            vin_code.link = vin_code_data.link
        if vin_code_data.additional_info is not None:
            vin_code.additional_info = vin_code_data.additional_info

        db.commit()
        db.refresh(vin_code)

        return vin_code
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[VIN_CODES] Error updating VIN code {vin_code_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při aktualizaci VIN kódu: {str(e)}"
        )


@router.delete("/{vin_code_id}", status_code=204)
def delete_vin_code(
    vin_code_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Smaže VIN kód"""
    try:
        vin_code = (
            db.query(VINCode)
            .filter(
                VINCode.id == vin_code_id,
                VINCode.tenant_id == current_user.tenant_id,
                VINCode.user_id == current_user.id,
            )
            .first()
        )

        if not vin_code:
            raise HTTPException(status_code=404, detail="VIN kód nenalezen")

        db.delete(vin_code)
        db.commit()

        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[VIN_CODES] Error deleting VIN code {vin_code_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při mazání VIN kódu: {str(e)}"
        )
