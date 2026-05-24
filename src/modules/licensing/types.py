"""
Typy a enumy pro licenční systém
"""
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..vehicle_hub.models import Customer


class LicensePlan(str, Enum):
    """Licenční plán"""
    FREE = "FREE"
    BASIC = "BASIC"
    PREMIUM = "PREMIUM"
    LIFETIME = "LIFETIME"  # admin-only, beze subscription / Comgate


class LicenseStatus(str, Enum):
    """Status licence"""
    ACTIVE = "ACTIVE"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAST_DUE = "PAST_DUE"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"


@dataclass
class EffectiveEntitlement:
    """
    Efektivní oprávnění uživatele - kombinace plánu a statusu
    """
    plan: LicensePlan
    status: LicenseStatus
    period_end: Optional[datetime] = None
    vehicles_count: int = 0
    vehicles_limit: Optional[int] = None
    is_over_limit: bool = False
    
    @property
    def is_active(self) -> bool:
        """Je licence aktivní? (zatím jen ACTIVE, bez grace)"""
        return self.status == LicenseStatus.ACTIVE
    
    @property
    def can_add_vehicles(self) -> bool:
        """Může uživatel přidávat vozidla?"""
        if not self.is_active:
            return False
        if self.is_over_limit:
            return False
        return True











