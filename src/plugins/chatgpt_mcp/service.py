from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.modules.vehicle_hub.account_state import customer_is_deleted, customer_is_disabled
from src.modules.vehicle_hub.audit_log import write_global_audit_log
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceIntake,
    ServiceLaborSession,
    ServiceRecord,
    Vehicle,
    VehicleMileage,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.ownership import get_primary_vehicle_owner
from src.modules.vehicle_hub.service_access import (
    get_active_vehicle_service_link,
    log_vehicle_lookup,
    masked_plate,
    masked_vin,
    normalize_lookup_query,
    require_approved_service_vehicle_access,
    require_service_vehicle_link,
    resolve_vehicle_for_lookup,
    vehicle_label,
)
from src.modules.vehicle_hub.workspace_entitlements import customer_has_service_workspace_access


PLUGIN_SOURCE = "chatgpt_mcp"


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _correlation_id() -> str:
    return f"mcp-{uuid.uuid4()}"


def _actor_id_from_env() -> int:
    raw = str(os.getenv("CHATGPT_MCP_SERVICE_USER_ID") or "").strip()
    if not raw:
        raise RuntimeError("CHATGPT_MCP_SERVICE_USER_ID is not configured")
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("CHATGPT_MCP_SERVICE_USER_ID must be an integer") from exc
    if value <= 0:
        raise RuntimeError("CHATGPT_MCP_SERVICE_USER_ID must be > 0")
    return value


def resolve_actor(db: Session) -> Customer:
    """Private/dev MCP identity. Public directory release will replace this with OAuth subject mapping."""
    actor = db.query(Customer).filter(Customer.id == _actor_id_from_env()).first()
    if not actor:
        raise RuntimeError("Configured ChatGPT MCP service user does not exist")
    if customer_is_deleted(actor) or customer_is_disabled(actor):
        raise RuntimeError("Configured ChatGPT MCP service user is inactive")
    if not customer_has_service_workspace_access(actor):
        raise RuntimeError("Configured ChatGPT MCP user has no service workspace access")
    return actor


def plugin_status(db: Session) -> dict[str, Any]:
    actor = resolve_actor(db)
    vehicle_count = (
        db.query(VehicleServiceLink)
        .filter(
            VehicleServiceLink.service_customer_id == int(actor.id),
            VehicleServiceLink.status == "approved",
        )
        .count()
    )
    open_cases = (
        db.query(ServiceIntake)
        .filter(
            ServiceIntake.service_id == int(actor.id),
            ServiceIntake.intake_status.notin_(["completed", "cancelled"]),
        )
        .count()
    )
    return {
        "ok": True,
        "plugin": "TooZ Mechanic",
        "mode": "private_service_operator",
        "actor_id": int(actor.id),
        "workspace": "service",
        "assigned_vehicle_count": int(vehicle_count),
        "open_case_count": int(open_cases),
        "owner_personal_data_exposed": False,
    }


def list_assigned_vehicles(db: Session, *, limit: int = 20) -> dict[str, Any]:
    actor = resolve_actor(db)
    bounded = max(1, min(int(limit or 20), 50))
    rows = (
        db.query(Vehicle)
        .join(VehicleServiceLink, Vehicle.id == VehicleServiceLink.vehicle_id)
        .filter(
            VehicleServiceLink.service_customer_id == int(actor.id),
            VehicleServiceLink.status == "approved",
            Vehicle.status != "archived",
        )
        .order_by(Vehicle.updated_at.desc(), Vehicle.id.desc())
        .limit(bounded)
        .all()
    )
    return {
        "items": [
            {
                "vehicle_id": int(v.id),
                "label": vehicle_label(v),
                "brand": v.brand,
                "model": v.model,
                "year": v.year,
                "engine": v.engine,
                "fuel": v.fuel,
                "plate": v.plate,
                "vin": v.vin,
                "current_mileage_km": v.current_mileage_km,
                "stk_valid_until": _iso(v.stk_valid_until),
            }
            for v in rows
        ],
        "count": len(rows),
    }


def lookup_vehicle(db: Session, *, query: str) -> dict[str, Any]:
    actor = resolve_actor(db)
    normalized, identifier_type = normalize_lookup_query(query)
    vehicle, owner, normalized, identifier_type, status = resolve_vehicle_for_lookup(
        db, current_user=actor, query=normalized
    )
    approved = bool(
        vehicle
        and get_active_vehicle_service_link(
            db,
            service_customer_id=int(actor.id),
            vehicle_id=int(vehicle.id),
        )
    )
    log_vehicle_lookup(
        db,
        current_user=actor,
        raw_query=query,
        normalized_query=normalized,
        identifier_type=identifier_type,
        vehicle=vehicle,
        owner_customer=owner,
        result_status=status,
        returned_candidate_count=1 if vehicle else 0,
    )
    write_global_audit_log(
        db,
        entity_type="chatgpt_plugin",
        entity_id=None,
        action="mcp_vehicle_lookup",
        actor_type="service_staff",
        actor_user_id=int(actor.id),
        actor_role=getattr(actor, "role", None),
        tenant_id=getattr(actor, "tenant_id", None),
        vehicle_id=int(vehicle.id) if vehicle else None,
        correlation_id=_correlation_id(),
        metadata={"identifier_type": identifier_type, "result_status": status, "approved": approved},
    )
    db.commit()

    if not vehicle:
        return {
            "status": status,
            "identifier_type": identifier_type,
            "items": [],
        }

    public_shape = {
        "vehicle_id": int(vehicle.id),
        "label": vehicle_label(vehicle),
        "plate_masked": masked_plate(vehicle.plate),
        "vin_masked": masked_vin(vehicle.vin),
        "can_open_detail": approved,
        "can_request_access": bool(owner and not approved and status != "pending_request"),
    }
    if not approved:
        return {"status": status, "identifier_type": identifier_type, "items": [public_shape]}

    public_shape.update(
        {
            "plate": vehicle.plate,
            "vin": vehicle.vin,
            "brand": vehicle.brand,
            "model": vehicle.model,
            "year": vehicle.year,
            "engine": vehicle.engine,
            "fuel": vehicle.fuel,
            "current_mileage_km": vehicle.current_mileage_km,
            "stk_valid_until": _iso(vehicle.stk_valid_until),
        }
    )
    return {"status": status, "identifier_type": identifier_type, "items": [public_shape]}


def vehicle_context(db: Session, *, vehicle_id: int, history_limit: int = 12) -> dict[str, Any]:
    actor = resolve_actor(db)
    vehicle, _owner, link = require_approved_service_vehicle_access(
        db, current_user=actor, vehicle_id=int(vehicle_id)
    )
    bounded = max(1, min(int(history_limit or 12), 30))
    records = (
        db.query(ServiceRecord)
        .filter(ServiceRecord.vehicle_id == int(vehicle.id), ServiceRecord.is_deleted.is_(False))
        .order_by(ServiceRecord.performed_at.desc(), ServiceRecord.id.desc())
        .limit(bounded)
        .all()
    )
    mileage = (
        db.query(VehicleMileage)
        .filter(VehicleMileage.vehicle_id == int(vehicle.id))
        .order_by(VehicleMileage.created_at.desc(), VehicleMileage.id.desc())
        .limit(8)
        .all()
    )
    cases = (
        db.query(ServiceIntake)
        .filter(
            ServiceIntake.service_id == int(actor.id),
            ServiceIntake.vehicle_id == int(vehicle.id),
        )
        .order_by(ServiceIntake.updated_at.desc(), ServiceIntake.id.desc())
        .limit(8)
        .all()
    )
    link.last_used_at = datetime.utcnow()
    db.commit()
    return {
        "vehicle": {
            "vehicle_id": int(vehicle.id),
            "label": vehicle_label(vehicle),
            "vin": vehicle.vin,
            "plate": vehicle.plate,
            "brand": vehicle.brand,
            "model": vehicle.model,
            "year": vehicle.year,
            "engine": vehicle.engine,
            "fuel": vehicle.fuel,
            "current_mileage_km": vehicle.current_mileage_km,
            "stk_valid_until": _iso(vehicle.stk_valid_until),
            "technical_overview": vehicle.vehicle_technical_overview,
        },
        "service_history": [
            {
                "record_id": int(r.id),
                "performed_at": _iso(r.performed_at),
                "mileage": r.mileage,
                "description": r.description,
                "category": r.category,
                "service_type": r.service_type,
                "record_status": r.record_status,
                "origin": r.origin,
                "labor_seconds": r.labor_seconds,
                "price": r.price if r.price is not None else r.total_price,
            }
            for r in records
        ],
        "mileage_history": [
            {
                "mileage_km": int(m.mileage_km),
                "source": m.source,
                "created_at": _iso(m.created_at),
                "note": m.note,
            }
            for m in mileage
        ],
        "service_cases": [
            _serialize_case(c) for c in cases
        ],
        "owner_personal_data_exposed": False,
    }


def _serialize_case(case: ServiceIntake) -> dict[str, Any]:
    return {
        "case_id": int(case.id),
        "vehicle_id": int(case.vehicle_id) if case.vehicle_id else None,
        "status": case.intake_status,
        "customer_request": case.customer_request,
        "intake_note": case.intake_note,
        "diagnosis_summary": case.diagnosis_summary,
        "repair_summary": case.repair_summary,
        "visible_to_owner_note": case.visible_to_owner_note,
        "odometer_km": case.odometer_km,
        "mileage_out": case.mileage_out,
        "total_labor_seconds": int(case.total_labor_seconds or 0),
        "work_started_at": _iso(case.work_started_at),
        "work_finished_at": _iso(case.work_finished_at),
        "created_at": _iso(case.created_at),
        "updated_at": _iso(case.updated_at),
    }


def create_service_case(
    db: Session,
    *,
    vehicle_id: int,
    customer_request: str,
    mileage_km: int | None = None,
    intake_note: str | None = None,
) -> dict[str, Any]:
    actor = resolve_actor(db)
    vehicle, owner, link = require_approved_service_vehicle_access(
        db, current_user=actor, vehicle_id=int(vehicle_id)
    )
    text = str(customer_request or "").strip()
    if len(text) < 3:
        raise ValueError("customer_request must contain at least 3 characters")
    if mileage_km is not None and int(mileage_km) < 0:
        raise ValueError("mileage_km must be >= 0")

    existing = (
        db.query(ServiceIntake)
        .filter(
            ServiceIntake.service_id == int(actor.id),
            ServiceIntake.vehicle_id == int(vehicle.id),
            ServiceIntake.intake_status.notin_(["completed", "cancelled"]),
        )
        .order_by(ServiceIntake.updated_at.desc(), ServiceIntake.id.desc())
        .first()
    )
    if existing:
        return {"created": False, "reason": "open_case_exists", "case": _serialize_case(existing)}

    now = datetime.utcnow()
    case = ServiceIntake(
        tenant_id=int(getattr(actor, "tenant_id", None) or vehicle.tenant_id or 1),
        service_tenant_id=getattr(actor, "tenant_id", None),
        service_id=int(actor.id),
        vehicle_id=int(vehicle.id),
        customer_id=int(owner.id),
        service_access_link_id=int(link.id),
        intake_status="approved_for_service",
        intake_source=PLUGIN_SOURCE,
        owner_approval_required=False,
        owner_approval_status="approved",
        check_in_at=now,
        created_by=int(actor.id),
        customer_request=text,
        intake_note=(str(intake_note).strip() if intake_note else None),
        odometer_km=int(mileage_km) if mileage_km is not None else None,
    )
    db.add(case)
    db.flush()
    write_global_audit_log(
        db,
        entity_type="service_case",
        entity_id=int(case.id),
        action="mcp_service_case_created",
        actor_type="service_staff",
        actor_user_id=int(actor.id),
        actor_role=getattr(actor, "role", None),
        tenant_id=getattr(actor, "tenant_id", None),
        vehicle_id=int(vehicle.id),
        correlation_id=_correlation_id(),
        metadata={"source": PLUGIN_SOURCE},
    )
    db.commit()
    return {"created": True, "case": _serialize_case(case)}


def record_diagnosis(
    db: Session,
    *,
    case_id: int,
    symptoms: list[str] | None = None,
    dtcs: list[str] | None = None,
    measurements: list[dict[str, Any]] | None = None,
    conclusion: str | None = None,
    internal_note: str | None = None,
    visible_to_owner_note: str | None = None,
) -> dict[str, Any]:
    actor = resolve_actor(db)
    case = _case_for_actor(db, actor, case_id)
    if not case.vehicle_id:
        raise ValueError("Service case has no vehicle")
    require_service_vehicle_link(
        db,
        current_user=actor,
        vehicle_id=int(case.vehicle_id),
        require_create_record=True,
    )
    payload = {
        "schema": "tooz.diagnosis.v1",
        "symptoms": [str(x).strip() for x in (symptoms or []) if str(x).strip()][:40],
        "dtcs": [str(x).strip().upper() for x in (dtcs or []) if str(x).strip()][:40],
        "measurements": (measurements or [])[:80],
        "conclusion": (str(conclusion).strip() if conclusion else None),
        "recorded_at": datetime.utcnow().isoformat(),
        "source": PLUGIN_SOURCE,
    }
    case.diagnosis_summary = json.dumps(payload, ensure_ascii=False, default=str)
    if internal_note is not None:
        case.internal_note = str(internal_note).strip() or None
    if visible_to_owner_note is not None:
        case.visible_to_owner_note = str(visible_to_owner_note).strip() or None
    case.diagnosis_started_at = case.diagnosis_started_at or datetime.utcnow()
    case.diagnosis_completed_at = datetime.utcnow()
    if case.intake_status in {"approved_for_service", "paused"}:
        case.intake_status = "diagnosed"
    write_global_audit_log(
        db,
        entity_type="service_case",
        entity_id=int(case.id),
        action="mcp_diagnosis_recorded",
        actor_type="service_staff",
        actor_user_id=int(actor.id),
        actor_role=getattr(actor, "role", None),
        tenant_id=getattr(actor, "tenant_id", None),
        vehicle_id=int(case.vehicle_id),
        correlation_id=_correlation_id(),
        metadata={"dtc_count": len(payload["dtcs"]), "measurement_count": len(payload["measurements"])},
    )
    db.commit()
    return {"saved": True, "case": _serialize_case(case), "diagnosis": payload}


def _case_for_actor(db: Session, actor: Customer, case_id: int) -> ServiceIntake:
    case = db.query(ServiceIntake).filter(ServiceIntake.id == int(case_id)).first()
    if not case:
        raise LookupError("Service case not found")
    if int(case.service_id) != int(actor.id):
        raise PermissionError("Service operator has no access to this case")
    return case


def start_work(db: Session, *, case_id: int) -> dict[str, Any]:
    actor = resolve_actor(db)
    case = _case_for_actor(db, actor, case_id)
    if case.vehicle_id:
        require_service_vehicle_link(db, current_user=actor, vehicle_id=int(case.vehicle_id))
    existing = (
        db.query(ServiceLaborSession)
        .filter(
            ServiceLaborSession.service_case_id == int(case.id),
            ServiceLaborSession.stopped_at.is_(None),
        )
        .order_by(ServiceLaborSession.started_at.desc())
        .first()
    )
    if existing:
        return {
            "started": False,
            "reason": "already_running",
            "session_id": int(existing.id),
            "started_at": _iso(existing.started_at),
            "case": _serialize_case(case),
        }
    now = datetime.utcnow()
    session = ServiceLaborSession(
        tenant_id=int(getattr(actor, "tenant_id", None) or 1),
        service_case_id=int(case.id),
        vehicle_id=int(case.vehicle_id) if case.vehicle_id else None,
        service_customer_id=int(actor.id),
        technician_id=int(actor.id),
        started_at=now,
    )
    db.add(session)
    db.flush()
    case.work_started_at = case.work_started_at or now
    case.work_finished_at = None
    case.intake_status = "in_progress"
    write_global_audit_log(
        db,
        entity_type="service_labor_session",
        entity_id=int(session.id),
        action="mcp_labor_started",
        actor_type="service_staff",
        actor_user_id=int(actor.id),
        actor_role=getattr(actor, "role", None),
        tenant_id=getattr(actor, "tenant_id", None),
        vehicle_id=int(case.vehicle_id) if case.vehicle_id else None,
        correlation_id=_correlation_id(),
        metadata={"case_id": int(case.id)},
    )
    db.commit()
    return {"started": True, "session_id": int(session.id), "case": _serialize_case(case)}


def stop_work(db: Session, *, case_id: int) -> dict[str, Any]:
    actor = resolve_actor(db)
    case = _case_for_actor(db, actor, case_id)
    session = (
        db.query(ServiceLaborSession)
        .filter(
            ServiceLaborSession.service_case_id == int(case.id),
            ServiceLaborSession.stopped_at.is_(None),
        )
        .order_by(ServiceLaborSession.started_at.desc())
        .first()
    )
    if not session:
        return {"stopped": False, "reason": "not_running", "case": _serialize_case(case)}
    now = datetime.utcnow()
    session.stopped_at = now
    session.duration_seconds = max(0, int((now - session.started_at).total_seconds()))
    db.flush()
    rows = db.query(ServiceLaborSession).filter(ServiceLaborSession.service_case_id == int(case.id)).all()
    case.total_labor_seconds = sum(int(row.duration_seconds or 0) for row in rows)
    case.work_finished_at = now
    case.intake_status = "paused"
    write_global_audit_log(
        db,
        entity_type="service_labor_session",
        entity_id=int(session.id),
        action="mcp_labor_stopped",
        actor_type="service_staff",
        actor_user_id=int(actor.id),
        actor_role=getattr(actor, "role", None),
        tenant_id=getattr(actor, "tenant_id", None),
        vehicle_id=int(case.vehicle_id) if case.vehicle_id else None,
        correlation_id=_correlation_id(),
        metadata={"case_id": int(case.id), "duration_seconds": int(session.duration_seconds or 0)},
    )
    db.commit()
    return {"stopped": True, "duration_seconds": int(session.duration_seconds or 0), "case": _serialize_case(case)}


def finalize_service_record(
    db: Session,
    *,
    case_id: int,
    description: str,
    category: str = "diagnostics",
    mileage_km: int | None = None,
    price: float | None = None,
    repair_summary: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    actor = resolve_actor(db)
    case = _case_for_actor(db, actor, case_id)
    if not case.vehicle_id:
        raise ValueError("Service case has no vehicle")
    link = require_service_vehicle_link(
        db,
        current_user=actor,
        vehicle_id=int(case.vehicle_id),
        require_create_record=True,
    )
    existing = (
        db.query(ServiceRecord)
        .filter(
            ServiceRecord.service_case_id == int(case.id),
            ServiceRecord.is_deleted.is_(False),
        )
        .order_by(ServiceRecord.id.asc())
        .first()
    )
    if existing:
        return {
            "created": False,
            "reason": "already_finalized",
            "record_id": int(existing.id),
            "case": _serialize_case(case),
        }
    text = str(description or "").strip()
    if len(text) < 3:
        raise ValueError("description must contain at least 3 characters")
    if price is not None and float(price) < 0:
        raise ValueError("price must be >= 0")
    if mileage_km is not None and int(mileage_km) < 0:
        raise ValueError("mileage_km must be >= 0")
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(case.vehicle_id)).first()
    owner = get_primary_vehicle_owner(db, vehicle) if vehicle else None
    record = ServiceRecord(
        tenant_id=int(getattr(actor, "tenant_id", None) or link.tenant_id or 1),
        vehicle_id=int(case.vehicle_id),
        user_id=int(actor.id),
        customer_id=int(owner.id) if owner else None,
        service_id=int(actor.id),
        performed_at=datetime.utcnow(),
        mileage=int(mileage_km) if mileage_km is not None else case.odometer_km,
        description=text,
        price=float(price) if price is not None else None,
        note=(str(note).strip() if note else None),
        category=str(category or "diagnostics").strip().upper()[:64],
        service_type=str(category or "diagnostics").strip().lower()[:64],
        record_status="submitted",
        origin="service_verified",
        service_case_id=int(case.id),
        created_by_ai=True,
        created_by_service_customer_id=int(actor.id),
        service_access_link_id=int(link.id),
        labor_seconds=int(case.total_labor_seconds or 0),
        visibility_scope="summary_previous_owner_full_current_owner",
    )
    db.add(record)
    db.flush()
    case.repair_summary = str(repair_summary).strip() if repair_summary else case.repair_summary
    case.intake_status = "completed"
    case.intake_completed_at = datetime.utcnow()
    case.owner_approval_status = "approved"
    case.service_access_link_id = int(link.id)
    if record.mileage is not None:
        db.add(
            VehicleMileage(
                tenant_id=int(vehicle.tenant_id or getattr(actor, "tenant_id", None) or 1),
                vehicle_id=int(vehicle.id),
                mileage_km=int(record.mileage),
                source="service_record",
                service_record_id=int(record.id),
                note="ChatGPT MCP verified service record",
                created_by_user_id=int(actor.id),
            )
        )
        if vehicle.current_mileage_km is None or int(record.mileage) >= int(vehicle.current_mileage_km or 0):
            vehicle.current_mileage_km = int(record.mileage)
    write_global_audit_log(
        db,
        entity_type="service_record",
        entity_id=int(record.id),
        action="mcp_service_record_finalized",
        actor_type="service_staff",
        actor_user_id=int(actor.id),
        actor_role=getattr(actor, "role", None),
        tenant_id=getattr(actor, "tenant_id", None),
        vehicle_id=int(case.vehicle_id),
        correlation_id=_correlation_id(),
        metadata={"case_id": int(case.id), "source": PLUGIN_SOURCE, "created_by_ai": True},
    )
    db.commit()
    return {"created": True, "record_id": int(record.id), "case": _serialize_case(case)}
