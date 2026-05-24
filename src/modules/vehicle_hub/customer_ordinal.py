"""
Přehledové číslo zákazníka v adminu (1, 2, 3 …) — nezávislé na databázovém id.
Při smazání se eviduje „#N“, „##N“ podle pořadí smazání daného čísla.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.modules.vehicle_hub.models import Customer, CustomerDeletionLabel


def allocate_admin_ordinal(db: Session) -> int:
    """Nejmenší kladné číslo, které mezi aktivními účty ještě není obsazené."""
    rows = (
        db.query(Customer.admin_ordinal)
        .filter(Customer.is_deleted.is_(False), Customer.admin_ordinal.isnot(None))
        .all()
    )
    used = {int(r[0]) for r in rows if r[0] is not None}
    n = 1
    while n in used:
        n += 1
    return n


def assign_admin_ordinal_if_missing(db: Session, customer: Customer) -> None:
    if customer.admin_ordinal is not None:
        return
    customer.admin_ordinal = allocate_admin_ordinal(db)


def deletion_mark_display(hash_depth: int, ordinal: int) -> str:
    depth = max(1, int(hash_depth or 1))
    return f"{'#' * depth}{int(ordinal)}"


def record_customer_deletion_label(db: Session, *, customer: Customer, email_before: str) -> CustomerDeletionLabel:
    assign_admin_ordinal_if_missing(db, customer)
    ordinal = int(customer.admin_ordinal)
    prior = (
        db.query(func.count(CustomerDeletionLabel.id))
        .filter(CustomerDeletionLabel.ordinal_at_delete == ordinal)
        .scalar()
        or 0
    )
    hash_depth = int(prior) + 1
    row = CustomerDeletionLabel(
        customer_id=int(customer.id),
        ordinal_at_delete=ordinal,
        hash_depth=hash_depth,
        email_before=(email_before or "").strip().lower(),
    )
    db.add(row)
    customer.admin_ordinal = None
    return row
