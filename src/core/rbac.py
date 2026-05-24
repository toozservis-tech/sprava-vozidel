"""
Centralizovaná RBAC/policy vrstva pro Správu vozidel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


ROLE_USER = "user"
ROLE_SERVICE = "service"
ROLE_ADMIN = "admin"
ROLE_DEVELOPER_ADMIN = "developer_admin"

ALL_ROLES = {
    ROLE_USER,
    ROLE_SERVICE,
    ROLE_ADMIN,
    ROLE_DEVELOPER_ADMIN,
}

ADMIN_ROLES = {
    ROLE_ADMIN,
    ROLE_DEVELOPER_ADMIN,
}

SERVICE_ROLES = {
    ROLE_SERVICE,
}


def normalize_role(role: Optional[str]) -> str:
    value = str(role or "").strip().lower()
    return value if value in ALL_ROLES else ROLE_USER


def has_role(role: Optional[str], allowed: Iterable[str]) -> bool:
    return normalize_role(role) in {normalize_role(item) for item in allowed}


def is_admin(role: Optional[str]) -> bool:
    return normalize_role(role) in ADMIN_ROLES


def is_developer_admin(role: Optional[str]) -> bool:
    return normalize_role(role) == ROLE_DEVELOPER_ADMIN


def is_service(role: Optional[str]) -> bool:
    return normalize_role(role) == ROLE_SERVICE


def is_service_or_admin(role: Optional[str]) -> bool:
    role_key = normalize_role(role)
    return role_key == ROLE_SERVICE or role_key in ADMIN_ROLES


@dataclass(frozen=True)
class RbacDecision:
    allowed: bool
    reason: str


def vehicle_read_policy(*, role: Optional[str], is_owner: bool, has_service_access: bool) -> RbacDecision:
    role_key = normalize_role(role)
    if role_key in ADMIN_ROLES:
        return RbacDecision(True, "admin")
    if is_owner:
        return RbacDecision(True, "owner")
    if role_key == ROLE_SERVICE and has_service_access:
        return RbacDecision(True, "service_link")
    return RbacDecision(False, "vehicle_read_denied")


def vehicle_write_policy(*, role: Optional[str], is_owner: bool) -> RbacDecision:
    role_key = normalize_role(role)
    if role_key in ADMIN_ROLES:
        return RbacDecision(True, "admin")
    if is_owner:
        return RbacDecision(True, "owner")
    return RbacDecision(False, "vehicle_write_denied")


def service_record_write_policy(*, role: Optional[str], is_owner: bool, has_service_access: bool) -> RbacDecision:
    role_key = normalize_role(role)
    if role_key in ADMIN_ROLES:
        return RbacDecision(True, "admin")
    if is_owner:
        return RbacDecision(True, "owner")
    if role_key == ROLE_SERVICE and has_service_access:
        return RbacDecision(True, "service_link")
    return RbacDecision(False, "service_record_write_denied")
