from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from src.core.rbac import is_admin, is_service, normalize_role
from src.modules.vehicle_hub.models import Customer, Vehicle
from src.modules.vehicle_hub.ownership import user_owns_vehicle

from .vehicle_report_models import VehicleReportMode


MODE_LABELS = {
    VehicleReportMode.PUBLIC: "Veřejný / pro prodej",
    VehicleReportMode.OWNER: "Vlastník",
    VehicleReportMode.WORKSHOP: "Servis",
    VehicleReportMode.INTERNAL_AUDIT: "Interní audit",
}

MODE_DESCRIPTIONS = {
    VehicleReportMode.PUBLIC: "Bez osobních údajů vlastníka, vhodné ke sdílení mimo účet.",
    VehicleReportMode.OWNER: "Kompletní výpis pro vlastníka včetně omezených owner údajů.",
    VehicleReportMode.WORKSHOP: "Výpis pro servis s provozní identifikací servisu a interními poznámkami.",
    VehicleReportMode.INTERNAL_AUDIT: "Rozšířený auditní výpis se stopou změn a autorů.",
}


@dataclass(frozen=True)
class VehicleReportModeOption:
    mode: str
    label: str
    description: str
    is_default: bool = False


def _default_mode_for_roles(allowed_modes: Iterable[VehicleReportMode], *, role: str, is_owner: bool) -> VehicleReportMode:
    allowed = list(allowed_modes)
    if is_owner and VehicleReportMode.OWNER in allowed:
        return VehicleReportMode.OWNER
    if normalize_role(role) == "service" and VehicleReportMode.WORKSHOP in allowed:
        return VehicleReportMode.WORKSHOP
    if VehicleReportMode.PUBLIC in allowed:
        return VehicleReportMode.PUBLIC
    return allowed[0]


def get_allowed_report_modes(*, db: Session, vehicle: Vehicle, current_user: Customer) -> list[VehicleReportMode]:
    allowed: list[VehicleReportMode] = [VehicleReportMode.PUBLIC]
    owns_vehicle = user_owns_vehicle(db, current_user, vehicle)
    role = normalize_role(getattr(current_user, "role", None))

    if owns_vehicle or is_admin(role):
        allowed.append(VehicleReportMode.OWNER)
    if is_service(role) or is_admin(role):
        allowed.append(VehicleReportMode.WORKSHOP)
    if is_admin(role):
        allowed.append(VehicleReportMode.INTERNAL_AUDIT)

    deduped: list[VehicleReportMode] = []
    seen: set[str] = set()
    for item in allowed:
        if item.value in seen:
            continue
        seen.add(item.value)
        deduped.append(item)
    return deduped


def resolve_report_mode(
    *,
    db: Session,
    vehicle: Vehicle,
    current_user: Customer,
    requested_mode: str | None,
) -> VehicleReportMode:
    allowed_modes = get_allowed_report_modes(db=db, vehicle=vehicle, current_user=current_user)
    default_mode = _default_mode_for_roles(
        allowed_modes,
        role=str(getattr(current_user, "role", "") or ""),
        is_owner=user_owns_vehicle(db, current_user, vehicle),
    )
    if not requested_mode:
        return default_mode

    normalized = str(requested_mode or "").strip().lower()
    for mode in allowed_modes:
        if mode.value == normalized:
            return mode
    raise PermissionError("Požadovaný režim exportu není pro tento účet povolen.")


def list_mode_options(*, db: Session, vehicle: Vehicle, current_user: Customer) -> list[VehicleReportModeOption]:
    allowed_modes = get_allowed_report_modes(db=db, vehicle=vehicle, current_user=current_user)
    default_mode = _default_mode_for_roles(
        allowed_modes,
        role=str(getattr(current_user, "role", "") or ""),
        is_owner=user_owns_vehicle(db, current_user, vehicle),
    )
    return [
        VehicleReportModeOption(
            mode=mode.value,
            label=MODE_LABELS[mode],
            description=MODE_DESCRIPTIONS[mode],
            is_default=mode == default_mode,
        )
        for mode in allowed_modes
    ]
