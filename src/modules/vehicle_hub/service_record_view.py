"""
Čtení servisní historie podle „ér“ vlastníka vozidla (VehicleOwnership).

Po převodu vozidla nový majitel vidí záznamy předchozích majitelů zkráceně (bez cen,
příloh / dokladů), nesmí je měnit ani mazat.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.core.rbac import is_admin, is_service

from .models import Customer, ServiceRecord as ServiceRecordModel, VehicleOwnership


def viewer_policy_applies_for_customer_workspace(viewer: Customer) -> bool:
    """Redakce platí jen pro koncového uživatele (workspace řidiče), ne pro servis ani admin."""
    if is_service(getattr(viewer, "role", None)):
        return False
    if is_admin(getattr(viewer, "role", None)):
        return False
    return True


def ownership_timeline_segments(db: Session, vehicle_id: int) -> list[VehicleOwnership]:
    return (
        db.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == int(vehicle_id),
            VehicleOwnership.relation_type == "owner",
            VehicleOwnership.ownership_type == "owner",
        )
        .order_by(VehicleOwnership.owned_from.asc(), VehicleOwnership.id.asc())
        .all()
    )


def _normalize_dt(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None):
        return dt.replace(tzinfo=None)
    return dt


def _segment_end(seg: VehicleOwnership) -> Optional[datetime]:
    return _normalize_dt(seg.owned_until or seg.revoked_at)


def segment_index_for_record_time(segments: list[VehicleOwnership], t: Optional[datetime]) -> Optional[int]:
    """Určí index úseku vlastnictví pro čas provedení servisu."""
    if not segments:
        return None

    if t is None:
        for i in range(len(segments) - 1, -1, -1):
            if segments[i].is_active:
                return i
        return len(segments) - 1

    tt = _normalize_dt(t)
    assert tt is not None

    for i, seg in enumerate(segments):
        start = _normalize_dt(seg.owned_from)
        end = _segment_end(seg)
        if start and tt < start:
            continue
        if end is not None and tt >= end:
            continue
        return i

    first_start = _normalize_dt(segments[0].owned_from)
    if first_start and tt < first_start:
        return 0
    return len(segments) - 1


def current_viewer_segment_index(segments: list[VehicleOwnership], viewer_customer_id: int) -> Optional[int]:
    """Aktivní úsek přihlášeného vlastníka."""
    for i, seg in enumerate(segments):
        if int(seg.customer_id) == int(viewer_customer_id) and seg.is_active:
            return i
    for i in range(len(segments) - 1, -1, -1):
        if segments[i].is_active and segments[i].is_primary:
            return i
    return None


def mask_customer_short_label(customer: Optional[Customer]) -> str:
    if not customer:
        return "—"
    name_field = str(getattr(customer, "name", None) or "").strip()
    if name_field:
        parts = name_field.split()
        if len(parts) >= 2:
            return f"{parts[0]} {parts[-1][:1]}."
        return parts[0][:48]
    email = str(getattr(customer, "email", None) or "").strip().lower()
    if email and "@" in email:
        local, _, domain = email.partition("@")
        if len(local) >= 2:
            return f"{local[:2]}…@{domain[:1]}."
        return local[:3] + "…"
    return "—"


def segment_owner_label(db: Session, seg: VehicleOwnership) -> str:
    cust = db.query(Customer).filter(Customer.id == seg.customer_id).first()
    return mask_customer_short_label(cust)


def viewer_record_same_ownership_era(
    db: Session,
    vehicle_id: int,
    viewer: Customer,
    record: ServiceRecordModel,
) -> bool:
    """Plná práva (úpravy + finance + přílohy) jen pro záznam z aktuální éry vlastníka."""
    if not viewer_policy_applies_for_customer_workspace(viewer):
        return True

    segments = ownership_timeline_segments(db, vehicle_id)
    if len(segments) < 2:
        return True

    ci = current_viewer_segment_index(segments, int(viewer.id))
    if ci is None:
        return True

    rt = record.performed_at or record.updated_at
    ri = segment_index_for_record_time(segments, rt)
    if ri is None:
        return True
    return ri == ci


def viewer_augmentation_for_service_record_api(
    db: Session,
    vehicle_id: int,
    viewer: Customer,
    record: ServiceRecordModel,
) -> dict[str, Any]:
    """
    Pole navíc / přepsání pro ServiceRecordOutV1 (merge přes model_dump).
    """
    same_era = viewer_record_same_ownership_era(db, vehicle_id, viewer, record)
    segments = ownership_timeline_segments(db, vehicle_id)
    ci = current_viewer_segment_index(segments, int(viewer.id)) if segments else None
    rt = record.performed_at or record.updated_at
    ri = segment_index_for_record_time(segments, rt) if segments else None

    owner_label: Optional[str] = None
    if segments and ri is not None and ci is not None and ri < ci:
        owner_label = segment_owner_label(db, segments[ri])

    aug: dict[str, Any] = {
        "viewer_mutations_allowed": same_era,
        "viewer_financials_redacted": not same_era,
        "ownership_segment_index": ri,
        "current_viewer_segment_index": ci,
        "ownership_segment_owner_label": owner_label,
    }

    if same_era:
        return aug

    aug["price"] = None
    aug["total_price"] = None
    aug["note"] = None
    aug["notes_customer_visible"] = None
    aug["attachments"] = None
    return aug


def assert_viewer_may_mutate_service_record(
    db: Session,
    vehicle_id: int,
    viewer: Customer,
    record: ServiceRecordModel,
) -> None:
    from fastapi import HTTPException

    if viewer_record_same_ownership_era(db, vehicle_id, viewer, record):
        return
    raise HTTPException(
        status_code=403,
        detail="Záznamy předchozích majitelů jsou jen pro čtení — nelze je měnit ani mazat.",
    )


def _attachments_dicts(raw: Optional[str]) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except Exception:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    return []


def find_record_for_attachment_storage_key(
    db: Session,
    vehicle_id: int,
    normalized_key: str,
) -> Optional[ServiceRecordModel]:
    """Najde záznam, který přílohu vlastní (podle storage_key v JSON)."""
    records = (
        db.query(ServiceRecordModel)
        .filter(
            ServiceRecordModel.vehicle_id == int(vehicle_id),
            ServiceRecordModel.is_deleted.is_(False),
            ServiceRecordModel.attachments.isnot(None),
        )
        .order_by(ServiceRecordModel.id.asc())
        .all()
    )
    nk = str(normalized_key or "").replace("\\", "/").strip()
    if not nk:
        return None

    for rec in records:
        for att in _attachments_dicts(rec.attachments):
            sk = str(att.get("storage_key") or "").replace("\\", "/").strip()
            if sk and (sk == nk or nk.endswith(sk) or nk.endswith("/" + sk.lstrip("/"))):
                return rec
    return None
