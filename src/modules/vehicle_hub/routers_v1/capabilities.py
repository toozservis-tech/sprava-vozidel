"""
System capabilities for frontend/admin gating.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schema_management import get_capabilities
from .auth import get_current_user
from ..models import Customer

router = APIRouter(prefix="/system", tags=["system-capabilities"])


@router.get("/capabilities")
def list_system_capabilities(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    return get_capabilities(db)
