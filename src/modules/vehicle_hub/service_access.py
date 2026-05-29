from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from src.core.rbac import is_admin, is_service, normalize_role

from .audit_log import write_global_audit_log
from .central_vehicle_identity import normalize_plate, query_hash
from .models import (
    Customer,
    ServiceAccessRequest,
    ServiceCustomerLink,
    ServiceWorkAccess,
    ServiceVehicleAccess,
    ServiceVehicleLookupAudit,
    ServiceRecord,
    Vehicle,
    VehicleServiceLink,
)
from .ownership import get_primary_vehicle_owner

_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def normalize_lookup_query(raw_value: Optional[str]) -> tuple[str, str]:
    value = str(raw_value or "").strip().upper()
    collapsed = normalize_plate(value)
    if not collapsed:
        return "", "unknown"
    if _VIN_RE.fullmatch(collapsed):
        return collapsed, "vin"
    return collapsed, "plate"


def masked_vin(vin: Optional[str]) -> Optional[str]:
    normalized = str(vin or "").strip().upper()
    if len(normalized) < 7:
        return None
    return f"{normalized[:3]}***{normalized[-4:]}"


def masked_plate(plate: Optional[str]) -> Optional[str]:
    """SPZ nikdy nevracet plně v poli označeném jako maskované."""
    raw = str(plate or "").strip().upper().replace(" ", "")
    if not raw:
        return None
    if len(raw) <= 4:
        return "***"
    return f"{raw[:2]}***{raw[-2:]}"


def vehicle_label(vehicle: Vehicle) -> str:
    composed = " ".join(part for part in [vehicle.brand, vehicle.model] if part).strip()
    return vehicle.nickname or composed or vehicle.plate or f"Vozidlo #{vehicle.id}"


def get_active_vehicle_service_link(
    db: Session,
    *,
    service_customer_id: int,
    vehicle_id: int,
) -> Optional[VehicleServiceLink]:
    return (
        db.query(VehicleServiceLink)
        .filter(
            VehicleServiceLink.service_customer_id == int(service_customer_id),
            VehicleServiceLink.vehicle_id == int(vehicle_id),
            VehicleServiceLink.status == "approved",
        )
        .first()
    )


def service_work_access_table_available(db: Session) -> bool:
    try:
        return inspect(db.get_bind()).has_table("service_work_access")
    except Exception:
        return True


def get_active_service_work_access(
    db: Session,
    *,
    service_customer_id: int,
    vehicle_id: int,
) -> Optional[ServiceWorkAccess]:
    if not service_work_access_table_available(db):
        return None
    return (
        db.query(ServiceWorkAccess)
        .filter(
            ServiceWorkAccess.service_customer_id == int(service_customer_id),
            ServiceWorkAccess.vehicle_id == int(vehicle_id),
            ServiceWorkAccess.status == "active",
        )
        .first()
    )


def service_has_work_access(db: Session, *, current_user: Customer, vehicle: Vehicle) -> bool:
    if not is_service(normalize_role(getattr(current_user, "role", None))):
        return False
    if get_active_vehicle_service_link(
        db,
        service_customer_id=int(current_user.id),
        vehicle_id=int(vehicle.id),
    ) is not None:
        return True
    if (
        get_primary_vehicle_owner(db, vehicle) is None
        and getattr(vehicle, "provisioned_by_service_customer_id", None) == getattr(current_user, "id", None)
        and str(getattr(vehicle, "global_vehicle_status", "") or "") == "service_provisioned_unowned"
    ):
        return True
    return get_active_service_work_access(
        db,
        service_customer_id=int(current_user.id),
        vehicle_id=int(vehicle.id),
    ) is not None


def create_or_update_service_work_access(
    db: Session,
    *,
    current_user: Customer,
    vehicle: Vehicle,
    reason: Optional[str],
    source: Optional[str],
    work_order_id: Optional[int] = None,
) -> ServiceWorkAccess:
    if not service_work_access_table_available(db):
        raise HTTPException(status_code=503, detail="Pracovní přístup servisu není připravený.")
    now = datetime.utcnow()
    owner = get_primary_vehicle_owner(db, vehicle)
    row = (
        db.query(ServiceWorkAccess)
        .filter(
            ServiceWorkAccess.service_customer_id == int(current_user.id),
            ServiceWorkAccess.vehicle_id == int(vehicle.id),
        )
        .first()
    )
    source_value = str(source or "manual").strip().lower()[:64] or "manual"
    reason_value = (str(reason or "").strip() or None)
    if row:
        row.status = "active"
        row.owner_customer_id = int(owner.id) if owner else None
        if work_order_id is not None:
            row.work_order_id = int(work_order_id)
        if reason_value:
            row.reason = reason_value
        row.source = source_value
        row.last_used_at = now
        row.updated_at = now
    else:
        row = ServiceWorkAccess(
            tenant_id=int(getattr(vehicle, "tenant_id", None) or getattr(current_user, "tenant_id", None) or 1),
            service_customer_id=int(current_user.id),
            vehicle_id=int(vehicle.id),
            owner_customer_id=int(owner.id) if owner else None,
            work_order_id=int(work_order_id) if work_order_id is not None else None,
            status="active",
            source=source_value,
            reason=reason_value,
            created_by_customer_id=int(current_user.id),
            last_used_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    db.flush()
    write_global_audit_log(
        db,
        entity_type="service_work_access",
        entity_id=int(row.id),
        action="service_work_access_upserted",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(getattr(row, "tenant_id", None) or getattr(vehicle, "tenant_id", None) or 1),
        vehicle_id=int(vehicle.id),
        metadata={
            "service_customer_id": int(current_user.id),
            "vehicle_id": int(vehicle.id),
            "owner_customer_id": int(owner.id) if owner else None,
            "work_order_id": int(work_order_id) if work_order_id is not None else None,
            "source": source_value,
        },
    )
    db.flush()
    return row


def service_can_read_vehicle(db: Session, current_user: Customer, vehicle_id: int) -> bool:
    """
    Čtení vozidla servisním účtem.

    Autorita: ``VehicleServiceLink`` ve stavu ``approved``.
    ``ServiceVehicleAccess`` je pouze legacy zrcadlo udržované z ``create_or_update_vehicle_service_link`` —
    ponecháno pro zpětnou kompatibilitu dat, dokud neproběhne plná migrace.
    """
    if not is_service(normalize_role(getattr(current_user, "role", None))):
        return False
    if get_active_vehicle_service_link(
        db,
        service_customer_id=int(current_user.id),
        vehicle_id=int(vehicle_id),
    ) is not None:
        return True

    # LEGACY read path (bez vlastního rozhodování mimo synchronizaci s VehicleServiceLink)
    legacy_access = (
        db.query(ServiceVehicleAccess.id)
        .filter(
            ServiceVehicleAccess.service_customer_id == int(current_user.id),
            ServiceVehicleAccess.vehicle_id == int(vehicle_id),
            ServiceVehicleAccess.status.in_(["active", "approved"]),
        )
        .first()
    )
    return legacy_access is not None


def require_service_vehicle_link(
    db: Session,
    *,
    current_user: Customer,
    vehicle_id: int,
    require_create_record: bool = False,
) -> VehicleServiceLink:
    """Zápisy servisu jen přes aktivní ``VehicleServiceLink`` (legacy tabulka sama o sobě nestačí)."""
    link = get_active_vehicle_service_link(
        db,
        service_customer_id=int(current_user.id),
        vehicle_id=int(vehicle_id),
    )
    if not link:
        raise HTTPException(
            status_code=403,
            detail="Servis nemá schválený přístup k tomuto vozidlu.",
        )
    if require_create_record and not bool(link.scope_create_service_record):
        raise HTTPException(
            status_code=403,
            detail="Servis nemá oprávnění vytvářet nové servisní záznamy pro toto vozidlo.",
        )
    link.last_used_at = datetime.utcnow()
    db.flush()
    return link


def require_approved_service_vehicle_access(
    db: Session,
    *,
    current_user: Customer,
    vehicle_id: int,
) -> tuple[Vehicle, Customer, VehicleServiceLink]:
    """
    Schválený VehicleServiceLink + vozidlo + majitel (řádek z linku, fallback primary owner).

    Pro PR service-cases API: pouze servisní účty s aktivním approved linkem.
    """
    role = normalize_role(getattr(current_user, "role", None))
    if not is_service(role) and not is_admin(role):
        raise HTTPException(status_code=403, detail="Přístup mají pouze servisní účty.")
    link = get_active_vehicle_service_link(
        db,
        service_customer_id=int(current_user.id),
        vehicle_id=int(vehicle_id),
    )
    if not link:
        raise HTTPException(
            status_code=403,
            detail="Servis nemá schválený přístup k tomuto vozidlu.",
        )
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno.")
    owner = db.query(Customer).filter(Customer.id == int(link.owner_customer_id)).first()
    if not owner:
        owner = get_primary_vehicle_owner(db, vehicle)
    if not owner:
        raise HTTPException(status_code=422, detail="K vozidlu nelze určit majitele pro servisní případ.")
    return vehicle, owner, link


def forbid_service_record_mutation(current_user: Customer) -> None:
    if is_service(normalize_role(getattr(current_user, "role", None))):
        raise HTTPException(
            status_code=403,
            detail="Servis může po schválení přístupu vytvářet nové servisní záznamy, ale nesmí upravovat ani mazat starší historii.",
        )


def log_vehicle_lookup(
    db: Session,
    *,
    current_user: Customer,
    raw_query: str,
    normalized_query: str,
    identifier_type: str,
    vehicle: Optional[Vehicle],
    owner_customer: Optional[Customer],
    result_status: str,
    returned_candidate_count: int,
) -> ServiceVehicleLookupAudit:
    audit = ServiceVehicleLookupAudit(
        tenant_id=current_user.tenant_id or 1,
        service_customer_id=current_user.id,
        lookup_query_raw=raw_query or None,
        lookup_query_normalized=normalized_query or None,
        lookup_query_hash=query_hash(normalized_query),
        lookup_identifier_type=identifier_type or "unknown",
        matched_vehicle_id=getattr(vehicle, "id", None),
        matched_owner_customer_id=getattr(owner_customer, "id", None),
        result_status=result_status,
        returned_candidate_count=max(0, int(returned_candidate_count or 0)),
        created_at=datetime.utcnow(),
    )
    db.add(audit)
    db.flush()
    return audit


def resolve_vehicle_for_lookup(
    db: Session,
    *,
    current_user: Customer,
    query: str,
) -> tuple[Optional[Vehicle], Optional[Customer], str, str, str]:
    normalized_query, identifier_type = normalize_lookup_query(query)
    if not normalized_query:
        raise HTTPException(status_code=422, detail="Zadejte SPZ nebo VIN vozidla.")

    candidate_query = db.query(Vehicle).order_by(Vehicle.created_at.asc(), Vehicle.id.asc())

    if identifier_type == "vin":
        vehicle = (
            candidate_query
            .filter(
                (getattr(Vehicle, "normalized_vin", Vehicle.vin) == normalized_query)
                | (Vehicle.vin == normalized_query)
            )
            .first()
        )
    else:
        vehicle = (
            candidate_query
            .filter(
                (getattr(Vehicle, "normalized_plate", Vehicle.plate) == normalized_query)
                | (Vehicle.plate == normalized_query)
            )
            .first()
        )

    if not vehicle:
        return None, None, normalized_query, identifier_type, "not_found"

    owner_customer = get_primary_vehicle_owner(db, vehicle)
    if not owner_customer:
        return vehicle, None, normalized_query, identifier_type, "owner_missing"

    existing_link = get_active_vehicle_service_link(
        db,
        service_customer_id=current_user.id,
        vehicle_id=vehicle.id,
    )
    if existing_link:
        return vehicle, owner_customer, normalized_query, identifier_type, "already_approved"

    pending_request = (
        db.query(ServiceAccessRequest.id)
        .filter(
            ServiceAccessRequest.service_customer_id == current_user.id,
            ServiceAccessRequest.vehicle_id == vehicle.id,
            ServiceAccessRequest.status == "pending",
        )
        .first()
    )
    if pending_request:
        return vehicle, owner_customer, normalized_query, identifier_type, "pending_request"

    return vehicle, owner_customer, normalized_query, identifier_type, "matched"


def create_or_update_vehicle_service_link(
    db: Session,
    *,
    tenant_id: Optional[int],
    service_customer_id: int,
    owner_customer_id: int,
    vehicle_id: int,
    approved_by_customer_id: int,
    source_type: str,
    source_request_id: Optional[int] = None,
    note: Optional[str] = None,
) -> VehicleServiceLink:
    now = datetime.utcnow()
    resolved_tenant_id = tenant_id
    if resolved_tenant_id is None:
        vehicle = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id)).first()
        resolved_tenant_id = getattr(vehicle, "tenant_id", None)
    if resolved_tenant_id is None:
        owner = db.query(Customer).filter(Customer.id == int(owner_customer_id)).first()
        resolved_tenant_id = getattr(owner, "tenant_id", None)

    link = (
        db.query(VehicleServiceLink)
        .filter(
            VehicleServiceLink.service_customer_id == int(service_customer_id),
            VehicleServiceLink.vehicle_id == int(vehicle_id),
        )
        .first()
    )
    previously_approved = bool(
        link and str(getattr(link, "status", "") or "").strip().lower() == "approved"
    )
    if not previously_approved:
        from src.modules.licensing.service import assert_service_vehicle_link_quota

        assert_service_vehicle_link_quota(db, service_customer_id=int(service_customer_id))
    if link:
        link.owner_customer_id = int(owner_customer_id)
        link.source_request_id = source_request_id
        link.source_type = source_type
        link.status = "approved"
        link.scope_vehicle_history_read = True
        link.scope_create_service_record = True
        link.scope_edit_existing_records = False
        link.scope_delete_existing_records = False
        link.owner_data_access_level = "none"
        link.approved_at = now
        link.approved_by_customer_id = int(approved_by_customer_id)
        link.revoked_at = None
        link.revoked_by_customer_id = None
        link.revoked_reason = None
        if note is not None:
            link.note = note
        link.updated_at = now
        db.flush()
    else:
        link = VehicleServiceLink(
            tenant_id=int(resolved_tenant_id or 1),
            service_customer_id=int(service_customer_id),
            owner_customer_id=int(owner_customer_id),
            vehicle_id=int(vehicle_id),
            source_request_id=source_request_id,
            source_type=source_type,
            status="approved",
            scope_vehicle_history_read=True,
            scope_create_service_record=True,
            scope_edit_existing_records=False,
            scope_delete_existing_records=False,
            owner_data_access_level="none",
            approved_at=now,
            approved_by_customer_id=int(approved_by_customer_id),
            note=note,
            created_at=now,
            updated_at=now,
        )
        db.add(link)
        db.flush()

    legacy_access = (
        db.query(ServiceVehicleAccess)
        .filter(
            ServiceVehicleAccess.service_customer_id == int(service_customer_id),
            ServiceVehicleAccess.customer_id == int(owner_customer_id),
            ServiceVehicleAccess.vehicle_id == int(vehicle_id),
        )
        .first()
    )
    if legacy_access:
        legacy_access.status = "active"
        legacy_access.granted_by_customer_id = int(approved_by_customer_id)
        legacy_access.note = note
        legacy_access.revoked_at = None
        legacy_access.updated_at = now
    else:
        db.add(
            ServiceVehicleAccess(
                service_customer_id=int(service_customer_id),
                customer_id=int(owner_customer_id),
                vehicle_id=int(vehicle_id),
                status="active",
                granted_by_customer_id=int(approved_by_customer_id),
                note=note,
                revoked_at=None,
                created_at=now,
                updated_at=now,
            )
        )

    service_link = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == int(service_customer_id),
            ServiceCustomerLink.customer_id == int(owner_customer_id),
        )
        .first()
    )
    if service_link:
        service_link.status = "active"
        service_link.updated_at = now
        if note is not None:
            service_link.note = note
    else:
        service_customer = db.query(Customer).filter(Customer.id == int(service_customer_id)).first()
        owner_customer = db.query(Customer).filter(Customer.id == int(owner_customer_id)).first()
        if service_customer and owner_customer:
            from src.modules.licensing.service import assert_service_customer_link_quota

            assert_service_customer_link_quota(db, service_customer_id=int(service_customer_id))
            db.add(
                ServiceCustomerLink(
                    service_tenant_id=service_customer.tenant_id,
                    service_customer_id=int(service_customer_id),
                    customer_tenant_id=owner_customer.tenant_id,
                    customer_id=int(owner_customer_id),
                    status="active",
                    note=note or "Propojeno přes schválení vozidla",
                    created_at=now,
                    updated_at=now,
                )
            )

    db.flush()
    return link


def revoke_vehicle_service_link(
    db: Session,
    *,
    service_customer_id: int,
    vehicle_id: int,
    revoked_by_customer_id: int,
    reason: Optional[str],
) -> Optional[VehicleServiceLink]:
    now = datetime.utcnow()
    link = (
        db.query(VehicleServiceLink)
        .filter(
            VehicleServiceLink.service_customer_id == int(service_customer_id),
            VehicleServiceLink.vehicle_id == int(vehicle_id),
            VehicleServiceLink.status == "approved",
        )
        .first()
    )
    if link:
        link.status = "revoked"
        link.revoked_at = now
        link.revoked_by_customer_id = int(revoked_by_customer_id)
        link.revoked_reason = reason
        link.updated_at = now

    legacy_access = (
        db.query(ServiceVehicleAccess)
        .filter(
            ServiceVehicleAccess.service_customer_id == int(service_customer_id),
            ServiceVehicleAccess.vehicle_id == int(vehicle_id),
            ServiceVehicleAccess.status.in_(["active", "approved"]),
        )
        .first()
    )
    if legacy_access:
        legacy_access.status = "revoked"
        legacy_access.revoked_at = now
        legacy_access.updated_at = now

    if link:
        linked_request = (
            db.query(ServiceAccessRequest)
            .filter(ServiceAccessRequest.approved_link_id == link.id)
            .order_by(ServiceAccessRequest.id.desc())
            .first()
        )
        if linked_request:
            linked_request.status = "revoked"
            linked_request.decided_at = now
            linked_request.decided_by_customer_id = int(revoked_by_customer_id)
            linked_request.decision_note = reason
            linked_request.updated_at = now

    return link


def backfill_vehicle_service_links_from_legacy_access(db: Session) -> None:
    rows = (
        db.query(ServiceVehicleAccess)
        .filter(ServiceVehicleAccess.status.in_(["active", "approved"]))
        .all()
    )
    for row in rows:
        create_or_update_vehicle_service_link(
            db,
            tenant_id=getattr(row, "tenant_id", None),
            service_customer_id=int(row.service_customer_id),
            owner_customer_id=int(row.customer_id),
            vehicle_id=int(row.vehicle_id),
            approved_by_customer_id=int(row.granted_by_customer_id or row.customer_id),
            source_type="legacy_service_vehicle_access",
            note=row.note,
        )


def attach_service_access_to_record(
    *,
    record: ServiceRecord,
    current_user: Customer,
    access_link: Optional[VehicleServiceLink],
) -> None:
    if is_service(normalize_role(getattr(current_user, "role", None))):
        record.created_by_service_customer_id = int(current_user.id)
        record.service_access_link_id = int(access_link.id) if access_link else None


def upsert_service_customer_link_after_request_approval(
    db: Session,
    *,
    service_customer_id: int,
    service_tenant_id: Optional[int],
    owner_customer: Customer,
    note: Optional[str] = None,
) -> None:
    """Po schválení žádosti o přístup aktivuje řádek ServiceCustomerLink (stejná logika jako services router)."""
    existing = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == int(service_customer_id),
            ServiceCustomerLink.customer_id == int(owner_customer.id),
        )
        .first()
    )
    if existing:
        existing.status = "active"
        existing.service_tenant_id = service_tenant_id
        existing.customer_tenant_id = owner_customer.tenant_id
        if note is not None:
            existing.note = note
        existing.updated_at = datetime.utcnow()
        db.flush()
        return

    from src.modules.licensing.service import assert_service_customer_link_quota

    assert_service_customer_link_quota(db, service_customer_id=int(service_customer_id))
    db.add(
        ServiceCustomerLink(
            service_tenant_id=service_tenant_id,
            service_customer_id=int(service_customer_id),
            customer_tenant_id=owner_customer.tenant_id,
            customer_id=int(owner_customer.id),
            status="active",
            note=note,
        )
    )
    db.flush()


def finalize_service_access_decision(
    db: Session,
    *,
    request_row: ServiceAccessRequest,
    vehicle: Vehicle,
    owner_customer: Customer,
    service_customer: Customer,
    decision: str,
    decided_by: Customer,
    decision_note: Optional[str],
    source_route: str,
) -> Optional[VehicleServiceLink]:
    """
    Jednotná persist vrstva: VehicleServiceLink + ServiceCustomerLink + globální audit.
    Volá se z PUT /services/access-requests i z POST /vehicles/.../approve.
    """
    decision_key = str(decision or "").strip().lower()
    now = datetime.utcnow()
    request_row.decided_at = now
    request_row.decided_by_customer_id = int(decided_by.id)
    request_row.decision_note = (decision_note or "").strip() or None
    request_row.updated_at = now

    vin_norm = str(getattr(vehicle, "vin", None) or "").strip().upper() or None

    if decision_key == "approved":
        link = create_or_update_vehicle_service_link(
            db,
            tenant_id=vehicle.tenant_id or owner_customer.tenant_id or service_customer.tenant_id,
            service_customer_id=int(service_customer.id),
            owner_customer_id=int(owner_customer.id),
            vehicle_id=int(vehicle.id),
            approved_by_customer_id=int(decided_by.id),
            source_type="request_approved",
            source_request_id=int(request_row.id),
            note=(request_row.request_message or "").strip() or None,
        )
        request_row.status = "approved"
        request_row.approved_link_id = int(link.id)
        upsert_service_customer_link_after_request_approval(
            db,
            service_customer_id=int(service_customer.id),
            service_tenant_id=service_customer.tenant_id,
            owner_customer=owner_customer,
            note="Propojeno přes schválenou žádost o přístup k vozidlu",
        )
        write_global_audit_log(
            db,
            entity_type="vehicle_service_access",
            entity_id=int(link.id),
            action="service_access_approved",
            actor_type="user",
            actor_user_id=int(decided_by.id),
            actor_role=getattr(decided_by, "role", None),
            tenant_id=int(vehicle.tenant_id or owner_customer.tenant_id or 1),
            vehicle_id=int(vehicle.id),
            metadata={
                "request_id": int(request_row.id),
                "service_id": int(service_customer.id),
                "vehicle_id": int(vehicle.id),
                "owner_customer_id": int(owner_customer.id),
                "approved_by_customer_id": int(decided_by.id),
                "vin": vin_norm,
                "source_route": source_route,
            },
        )
        return link

    if decision_key != "rejected":
        raise ValueError("decision must be approved or rejected")

    request_row.status = "rejected"
    write_global_audit_log(
        db,
        entity_type="service_access_request",
        entity_id=int(request_row.id),
        action="service_access_rejected",
        actor_type="user",
        actor_user_id=int(decided_by.id),
        actor_role=getattr(decided_by, "role", None),
        tenant_id=int(vehicle.tenant_id or owner_customer.tenant_id or 1),
        vehicle_id=int(vehicle.id),
        metadata={
            "request_id": int(request_row.id),
            "service_id": int(service_customer.id),
            "vehicle_id": int(vehicle.id),
            "owner_customer_id": int(owner_customer.id),
            "decided_by_customer_id": int(decided_by.id),
            "vin": vin_norm,
            "source_route": source_route,
        },
    )
    return None
