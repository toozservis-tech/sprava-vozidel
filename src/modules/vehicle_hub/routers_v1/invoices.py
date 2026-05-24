"""
Invoices API v1.0 router
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, Invoice
from .auth import get_current_user
from .schemas import InvoiceCreateV1, InvoiceOutV1, InvoiceUpdateV1

router = APIRouter(prefix="/invoices", tags=["invoices-v1"])


@router.get("", response_model=List[InvoiceOutV1])
def get_invoices(
    current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Získá seznam všech faktur aktuálního uživatele"""
    try:
        invoices = (
            db.query(Invoice)
            .filter(
                Invoice.tenant_id == current_user.tenant_id,
                Invoice.user_id == current_user.id,
            )
            .all()
        )
        return invoices
    except Exception as e:
        print(f"[INVOICES] Error getting invoices: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při načítání faktur: {str(e)}"
        )


@router.get("/{invoice_id}", response_model=InvoiceOutV1)
def get_invoice(
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Získá detail faktury"""
    try:
        invoice = (
            db.query(Invoice)
            .filter(
                Invoice.id == invoice_id,
                Invoice.tenant_id == current_user.tenant_id,
                Invoice.user_id == current_user.id,
            )
            .first()
        )

        if not invoice:
            raise HTTPException(status_code=404, detail="Faktura nenalezena")

        return invoice
    except HTTPException:
        raise
    except Exception as e:
        print(f"[INVOICES] Error getting invoice {invoice_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při načítání faktury: {str(e)}"
        )


@router.post("", response_model=InvoiceOutV1, status_code=201)
def create_invoice(
    invoice_data: InvoiceCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Vytvoří novou fakturu"""
    try:
        invoice = Invoice(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            number=invoice_data.number,
            date=invoice_data.date,
            description=invoice_data.description,
            amount=invoice_data.amount,
            vehicle_id=invoice_data.vehicle_id,
            contact_id=invoice_data.contact_id,
        )

        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        return invoice
    except Exception as e:
        db.rollback()
        print(f"[INVOICES] Error creating invoice: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při vytváření faktury: {str(e)}"
        )


@router.put("/{invoice_id}", response_model=InvoiceOutV1)
def update_invoice(
    invoice_id: int,
    invoice_data: InvoiceUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aktualizuje fakturu"""
    try:
        invoice = (
            db.query(Invoice)
            .filter(
                Invoice.id == invoice_id,
                Invoice.tenant_id == current_user.tenant_id,
                Invoice.user_id == current_user.id,
            )
            .first()
        )

        if not invoice:
            raise HTTPException(status_code=404, detail="Faktura nenalezena")

        # Aktualizovat pouze poskytnutá pole
        if invoice_data.number is not None:
            invoice.number = invoice_data.number
        if invoice_data.date is not None:
            invoice.date = invoice_data.date
        if invoice_data.description is not None:
            invoice.description = invoice_data.description
        if invoice_data.amount is not None:
            invoice.amount = invoice_data.amount
        if invoice_data.vehicle_id is not None:
            invoice.vehicle_id = invoice_data.vehicle_id
        if invoice_data.contact_id is not None:
            invoice.contact_id = invoice_data.contact_id

        db.commit()
        db.refresh(invoice)

        return invoice
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[INVOICES] Error updating invoice {invoice_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při aktualizaci faktury: {str(e)}"
        )


@router.delete("/{invoice_id}", status_code=204)
def delete_invoice(
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Smaže fakturu"""
    try:
        invoice = (
            db.query(Invoice)
            .filter(
                Invoice.id == invoice_id,
                Invoice.tenant_id == current_user.tenant_id,
                Invoice.user_id == current_user.id,
            )
            .first()
        )

        if not invoice:
            raise HTTPException(status_code=404, detail="Faktura nenalezena")

        db.delete(invoice)
        db.commit()

        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[INVOICES] Error deleting invoice {invoice_id}: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Chyba při mazání faktury: {str(e)}"
        )
