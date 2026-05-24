"""
Part Orders API v1.0 router
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, PartOrder
from .auth import get_current_user
from .schemas import PartOrderCreateV1, PartOrderOutV1, PartOrderUpdateV1

router = APIRouter(prefix="/part-orders", tags=["part-orders-v1"])


@router.get("", response_model=List[PartOrderOutV1])
def get_part_orders(
    current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Získá seznam všech objednávek dílů aktuálního uživatele"""
    try:
        part_orders = (
            db.query(PartOrder)
            .filter(
                PartOrder.tenant_id == current_user.tenant_id,
                PartOrder.user_id == current_user.id,
            )
            .all()
        )
        return part_orders
    except Exception as e:
        print(f"[PART_ORDERS] Error getting part orders: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při načítání objednávek dílů: {str(e)}"
        )


@router.get("/{part_order_id}", response_model=PartOrderOutV1)
def get_part_order(
    part_order_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Získá detail objednávky dílů"""
    try:
        part_order = (
            db.query(PartOrder)
            .filter(
                PartOrder.id == part_order_id,
                PartOrder.tenant_id == current_user.tenant_id,
                PartOrder.user_id == current_user.id,
            )
            .first()
        )

        if not part_order:
            raise HTTPException(status_code=404, detail="Objednávka dílů nenalezena")

        return part_order
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PART_ORDERS] Error getting part order {part_order_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Chyba při načítání objednávky dílů: {str(e)}",
        )


@router.post("", response_model=PartOrderOutV1, status_code=201)
def create_part_order(
    part_order_data: PartOrderCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Vytvoří novou objednávku dílů"""
    try:
        part_order = PartOrder(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            order_number=part_order_data.order_number,
            date=part_order_data.date,
            supplier_id=part_order_data.supplier_id,
            items=part_order_data.items,
            total_amount=part_order_data.total_amount,
        )

        db.add(part_order)
        db.commit()
        db.refresh(part_order)

        return part_order
    except Exception as e:
        db.rollback()
        print(f"[PART_ORDERS] Error creating part order: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Chyba při vytváření objednávky dílů: {str(e)}",
        )


@router.put("/{part_order_id}", response_model=PartOrderOutV1)
def update_part_order(
    part_order_id: int,
    part_order_data: PartOrderUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aktualizuje objednávku dílů"""
    try:
        part_order = (
            db.query(PartOrder)
            .filter(
                PartOrder.id == part_order_id,
                PartOrder.tenant_id == current_user.tenant_id,
                PartOrder.user_id == current_user.id,
            )
            .first()
        )

        if not part_order:
            raise HTTPException(status_code=404, detail="Objednávka dílů nenalezena")

        # Aktualizovat pouze poskytnutá pole
        if part_order_data.order_number is not None:
            part_order.order_number = part_order_data.order_number
        if part_order_data.date is not None:
            part_order.date = part_order_data.date
        if part_order_data.supplier_id is not None:
            part_order.supplier_id = part_order_data.supplier_id
        if part_order_data.items is not None:
            part_order.items = part_order_data.items
        if part_order_data.total_amount is not None:
            part_order.total_amount = part_order_data.total_amount

        db.commit()
        db.refresh(part_order)

        return part_order
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[PART_ORDERS] Error updating part order {part_order_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Chyba při aktualizaci objednávky dílů: {str(e)}",
        )


@router.delete("/{part_order_id}", status_code=204)
def delete_part_order(
    part_order_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Smaže objednávku dílů"""
    try:
        part_order = (
            db.query(PartOrder)
            .filter(
                PartOrder.id == part_order_id,
                PartOrder.tenant_id == current_user.tenant_id,
                PartOrder.user_id == current_user.id,
            )
            .first()
        )

        if not part_order:
            raise HTTPException(status_code=404, detail="Objednávka dílů nenalezena")

        db.delete(part_order)
        db.commit()

        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[PART_ORDERS] Error deleting part order {part_order_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při mazání objednávky dílů: {str(e)}"
        )
