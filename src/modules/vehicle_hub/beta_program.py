from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from src.modules.licensing.service import PLAN_FEATURES, PLAN_LIMITS, get_or_create_license

from .database import Base
from .models import (
    BetaActivityMetric,
    BetaApplication,
    BetaFeedback,
    BetaParticipant,
    BetaReward,
    Customer,
    LicenseSubscription,
    Reservation,
    SecurityAccessLog,
    ServiceRecord,
    Tenant,
    Vehicle,
)

APPLICANT_TYPE_SET = {"service", "user", "company"}
BETA_APPLICATION_STATUS_SET = {"pending", "approved", "rejected", "waitlist"}
BETA_PARTICIPANT_STATUS_SET = {"active", "paused", "revoked"}
BETA_FEEDBACK_CATEGORY_SET = {"feedback", "bug_report"}
BETA_FEEDBACK_STATUS_SET = {"new", "reviewed", "planned", "resolved", "dismissed"}
BETA_FEEDBACK_SEVERITY_SET = {"low", "medium", "high", "critical"}
BETA_REWARD_DECISION_SET = {"grant", "decline"}

_SCHEMA_READY = False


def ensure_beta_program_schema(db: Session) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    Base.metadata.create_all(
        bind=db.bind,
        tables=[
            BetaApplication.__table__,
            BetaParticipant.__table__,
            BetaActivityMetric.__table__,
            BetaFeedback.__table__,
            BetaReward.__table__,
        ],
    )
    _SCHEMA_READY = True


def normalize_beta_email(value: str) -> str:
    return str(value or "").strip().lower()


def normalize_beta_phone(value: Optional[str]) -> Optional[str]:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits or None


def _phones_equivalent(left: Optional[str], right: Optional[str]) -> bool:
    left_normalized = normalize_beta_phone(left)
    right_normalized = normalize_beta_phone(right)
    if not left_normalized or not right_normalized:
        return False
    if left_normalized == right_normalized:
        return True
    if min(len(left_normalized), len(right_normalized)) >= 9:
        return left_normalized[-9:] == right_normalized[-9:]
    return False


def normalize_applicant_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in APPLICANT_TYPE_SET:
        raise ValueError("Neplatný applicant_type. Povolené hodnoty: service, user, company.")
    return normalized


def normalize_beta_feedback_category(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in BETA_FEEDBACK_CATEGORY_SET:
        raise ValueError("Neplatná kategorie feedbacku.")
    return normalized


def normalize_beta_feedback_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in BETA_FEEDBACK_STATUS_SET:
        raise ValueError("Neplatný status feedbacku.")
    return normalized


def normalize_beta_feedback_severity(value: Optional[str]) -> str:
    normalized = str(value or "medium").strip().lower()
    if normalized not in BETA_FEEDBACK_SEVERITY_SET:
        raise ValueError("Neplatná závažnost feedbacku.")
    return normalized


def _normalize_beta_reward_decision(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in BETA_REWARD_DECISION_SET:
        raise ValueError("Neplatné reward rozhodnutí.")
    return normalized


def _safe_iso(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None
    return value.isoformat()


def _customer_is_service(customer: Optional[Customer]) -> bool:
    if not customer:
        return False
    return str(customer.role or "").strip().lower() == "service"


def _serialize_customer(customer: Optional[Customer]) -> Optional[Dict[str, Any]]:
    if not customer:
        return None
    return {
        "id": customer.id,
        "email": customer.email,
        "name": customer.name,
        "role": customer.role,
        "tenant_id": customer.tenant_id,
        "phone": customer.phone,
    }


def _serialize_tenant(tenant: Optional[Tenant]) -> Optional[Dict[str, Any]]:
    if not tenant:
        return None
    return {
        "id": tenant.id,
        "name": tenant.name,
        "license_key": tenant.license_key,
        "created_at": _safe_iso(tenant.created_at),
    }


def _load_customer(db: Session, customer_id: Optional[int]) -> Optional[Customer]:
    if not customer_id:
        return None
    return db.query(Customer).filter(Customer.id == int(customer_id)).first()


def _load_tenant(db: Session, tenant_id: Optional[int]) -> Optional[Tenant]:
    if not tenant_id:
        return None
    return db.query(Tenant).filter(Tenant.id == int(tenant_id)).first()


def _find_customer_by_email(db: Session, email_normalized: str) -> Optional[Customer]:
    if not email_normalized:
        return None
    return (
        db.query(Customer)
        .filter(func.lower(Customer.email) == email_normalized)
        .order_by(Customer.id.asc())
        .first()
    )


def _find_customers_by_phone(db: Session, phone_normalized: Optional[str]) -> List[Customer]:
    if not phone_normalized:
        return []
    rows = db.query(Customer).filter(Customer.phone.isnot(None)).all()
    return [row for row in rows if _phones_equivalent(row.phone, phone_normalized)]


def _candidate_ids_from_customer(customer: Customer) -> Dict[str, Optional[int]]:
    user_id = customer.id if not _customer_is_service(customer) else None
    service_account_id = customer.id if _customer_is_service(customer) else None
    return {
        "user_id": user_id,
        "service_account_id": service_account_id,
        "tenant_id": customer.tenant_id,
    }


def _apply_link_fields(
    application: BetaApplication,
    *,
    user_id: Optional[int],
    service_account_id: Optional[int],
    tenant_id: Optional[int],
    link_method: Optional[str],
    link_confidence: Optional[float],
    link_note: Optional[str],
    linked_by_customer_id: Optional[int],
) -> None:
    application.user_id = user_id
    application.service_account_id = service_account_id
    application.tenant_id = tenant_id
    application.link_method = link_method
    application.link_confidence = link_confidence
    application.link_note = link_note
    application.linked_by_customer_id = linked_by_customer_id
    application.linked_at = datetime.utcnow() if link_method else None
    application.updated_at = datetime.utcnow()


def refresh_beta_application_link(
    db: Session,
    application: BetaApplication,
    *,
    manual_user_id: Optional[int] = None,
    manual_service_account_id: Optional[int] = None,
    manual_tenant_id: Optional[int] = None,
    manual_reason: Optional[str] = None,
    actor_customer_id: Optional[int] = None,
    commit: bool = True,
) -> BetaApplication:
    ensure_beta_program_schema(db)

    now = datetime.utcnow()
    if (
        manual_user_id is None
        and manual_service_account_id is None
        and manual_tenant_id is None
        and application.link_method == "manual_admin"
    ):
        return application

    if manual_user_id is not None or manual_service_account_id is not None or manual_tenant_id is not None:
        user = _load_customer(db, manual_user_id)
        service = _load_customer(db, manual_service_account_id)
        tenant = _load_tenant(db, manual_tenant_id)

        if manual_user_id is not None and not user:
            raise HTTPException(status_code=404, detail="Ruční link: user_id neexistuje.")
        if manual_service_account_id is not None:
            if not service:
                raise HTTPException(status_code=404, detail="Ruční link: service_account_id neexistuje.")
            if not _customer_is_service(service):
                raise HTTPException(status_code=400, detail="Ruční link: service_account_id musí patřit servisnímu účtu.")
        if manual_tenant_id is not None and not tenant:
            raise HTTPException(status_code=404, detail="Ruční link: tenant_id neexistuje.")

        tenant_id = (
            int(manual_tenant_id)
            if manual_tenant_id is not None
            else (user.tenant_id if user else (service.tenant_id if service else None))
        )
        application.user_id = user.id if user else None
        application.service_account_id = service.id if service else None
        application.tenant_id = tenant_id
        application.link_method = "manual_admin"
        application.link_confidence = 1.0
        application.link_note = (manual_reason or "Manual developer admin link").strip()
        application.linked_by_customer_id = actor_customer_id
        application.linked_at = now
        application.updated_at = now
        if commit:
            db.add(application)
            db.commit()
            db.refresh(application)
        return application

    candidate = _find_customer_by_email(db, application.email_normalized)
    if candidate:
        ids = _candidate_ids_from_customer(candidate)
        _apply_link_fields(
            application,
            user_id=ids["user_id"],
            service_account_id=ids["service_account_id"],
            tenant_id=ids["tenant_id"],
            link_method="email_auto",
            link_confidence=0.98,
            link_note="Auto-linked by email match.",
            linked_by_customer_id=None,
        )
    else:
        phone_matches = _find_customers_by_phone(db, application.phone_normalized)
        if len(phone_matches) == 1:
            ids = _candidate_ids_from_customer(phone_matches[0])
            _apply_link_fields(
                application,
                user_id=ids["user_id"],
                service_account_id=ids["service_account_id"],
                tenant_id=ids["tenant_id"],
                link_method="phone_auto",
                link_confidence=0.78,
                link_note="Auto-linked by phone match.",
                linked_by_customer_id=None,
            )
        elif len(phone_matches) > 1:
            _apply_link_fields(
                application,
                user_id=None,
                service_account_id=None,
                tenant_id=None,
                link_method=None,
                link_confidence=None,
                link_note=f"Phone matched multiple accounts: {', '.join(str(row.id) for row in phone_matches[:5])}",
                linked_by_customer_id=None,
            )
        else:
            _apply_link_fields(
                application,
                user_id=None,
                service_account_id=None,
                tenant_id=None,
                link_method=None,
                link_confidence=None,
                link_note="No matching account found yet.",
                linked_by_customer_id=None,
            )

    application.linked_at = now if application.link_method else None
    application.updated_at = now
    if commit:
        db.add(application)
        db.commit()
        db.refresh(application)
    return application


def _find_existing_participant(
    db: Session,
    *,
    email_normalized: str,
    phone_normalized: Optional[str],
) -> Optional[BetaParticipant]:
    ensure_beta_program_schema(db)
    query = db.query(BetaParticipant).filter(BetaParticipant.email_normalized == email_normalized)
    participant = (
        query.filter(BetaParticipant.status.in_(["active", "paused"]))
        .order_by(BetaParticipant.id.desc())
        .first()
    )
    if participant:
        return participant
    if phone_normalized:
        return (
            db.query(BetaParticipant)
            .filter(
                BetaParticipant.phone_normalized == phone_normalized,
                BetaParticipant.status.in_(["active", "paused"]),
            )
            .order_by(BetaParticipant.id.desc())
            .first()
        )
    return None


def submit_beta_application(
    db: Session,
    *,
    name: str,
    email: str,
    phone: str,
    applicant_type: str,
    vehicle_count: Optional[int],
    note: Optional[str],
    gdpr_consent: bool,
) -> tuple[BetaApplication, bool]:
    ensure_beta_program_schema(db)

    email_normalized = normalize_beta_email(email)
    phone_normalized = normalize_beta_phone(phone)
    applicant_type_normalized = normalize_applicant_type(applicant_type)

    if not gdpr_consent:
        raise HTTPException(status_code=400, detail="Bez GDPR souhlasu nelze přihlášku odeslat.")

    existing_participant = _find_existing_participant(
        db,
        email_normalized=email_normalized,
        phone_normalized=phone_normalized,
    )
    if existing_participant:
        raise HTTPException(status_code=400, detail="Tento kontakt už je zařazen do beta programu.")

    existing_application = (
        db.query(BetaApplication)
        .filter(BetaApplication.email_normalized == email_normalized)
        .order_by(BetaApplication.id.desc())
        .first()
    )

    updated_existing = False
    now = datetime.utcnow()
    if existing_application and existing_application.status in {"pending", "rejected", "waitlist"}:
        updated_existing = True
        existing_application.status = "pending"
        existing_application.applicant_type = applicant_type_normalized
        existing_application.name = str(name or "").strip()
        existing_application.email = str(email or "").strip()
        existing_application.email_normalized = email_normalized
        existing_application.phone = str(phone or "").strip()
        existing_application.phone_normalized = phone_normalized
        existing_application.vehicle_count = int(vehicle_count or 0)
        existing_application.note = (note or "").strip() or None
        existing_application.gdpr_consent = True
        existing_application.reviewed_by_customer_id = None
        existing_application.reviewed_at = None
        existing_application.review_note = None
        existing_application.decision_reason = None
        existing_application.updated_at = now
        application = existing_application
    elif existing_application and existing_application.status == "approved":
        raise HTTPException(status_code=400, detail="Tato beta přihláška už byla schválena.")
    else:
        application = BetaApplication(
            status="pending",
            applicant_type=applicant_type_normalized,
            name=str(name or "").strip(),
            email=str(email or "").strip(),
            email_normalized=email_normalized,
            phone=str(phone or "").strip(),
            phone_normalized=phone_normalized,
            vehicle_count=int(vehicle_count or 0),
            note=(note or "").strip() or None,
            gdpr_consent=True,
            created_at=now,
            updated_at=now,
        )
        db.add(application)
        db.flush()

    refresh_beta_application_link(db, application, commit=False)
    db.add(application)
    db.commit()
    db.refresh(application)
    return application, updated_existing


def _resolve_participant_tenant_id(
    db: Session,
    *,
    participant: Optional[BetaParticipant] = None,
    user_id: Optional[int] = None,
    service_account_id: Optional[int] = None,
    tenant_id: Optional[int] = None,
) -> Optional[int]:
    if tenant_id is not None:
        return int(tenant_id)
    if participant and participant.tenant_id is not None:
        return int(participant.tenant_id)
    if participant and participant.user_id:
        linked_user = _load_customer(db, participant.user_id)
        if linked_user:
            return int(linked_user.tenant_id)
    if participant and participant.service_account_id:
        linked_service = _load_customer(db, participant.service_account_id)
        if linked_service:
            return int(linked_service.tenant_id)
    if user_id is not None:
        linked_user = _load_customer(db, user_id)
        if linked_user:
            return int(linked_user.tenant_id)
    if service_account_id is not None:
        linked_service = _load_customer(db, service_account_id)
        if linked_service:
            return int(linked_service.tenant_id)
    return None


def _find_participant_by_application(db: Session, application_id: int) -> Optional[BetaParticipant]:
    return (
        db.query(BetaParticipant)
        .filter(BetaParticipant.application_id == application_id)
        .order_by(BetaParticipant.id.desc())
        .first()
    )


def approve_beta_application(
    db: Session,
    *,
    application_id: int,
    actor: Customer,
    approval_note: Optional[str] = None,
    decision_reason: Optional[str] = None,
    manual_user_id: Optional[int] = None,
    manual_service_account_id: Optional[int] = None,
    manual_tenant_id: Optional[int] = None,
) -> BetaParticipant:
    ensure_beta_program_schema(db)

    application = db.query(BetaApplication).filter(BetaApplication.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Beta přihláška nebyla nalezena.")

    existing_participant = _find_participant_by_application(db, application.id)
    if existing_participant:
        return existing_participant

    refresh_beta_application_link(
        db,
        application,
        manual_user_id=manual_user_id,
        manual_service_account_id=manual_service_account_id,
        manual_tenant_id=manual_tenant_id,
        manual_reason=decision_reason or approval_note,
        actor_customer_id=actor.id,
        commit=False,
    )

    tenant_id = _resolve_participant_tenant_id(
        db,
        user_id=application.user_id,
        service_account_id=application.service_account_id,
        tenant_id=application.tenant_id,
    )
    if application.user_id is None and application.service_account_id is None and tenant_id is None:
        raise HTTPException(
            status_code=400,
            detail="Přihlášku nelze schválit bez vazby na reálný účet nebo tenant.",
        )

    duplicate_participant = _find_existing_participant(
        db,
        email_normalized=application.email_normalized,
        phone_normalized=application.phone_normalized,
    )
    if duplicate_participant:
        raise HTTPException(status_code=400, detail="Tento kontakt už má aktivního beta účastníka.")

    now = datetime.utcnow()
    participant = BetaParticipant(
        application_id=application.id,
        status="active",
        applicant_type=application.applicant_type,
        name=application.name,
        email=application.email,
        email_normalized=application.email_normalized,
        phone=application.phone,
        phone_normalized=application.phone_normalized,
        declared_vehicle_count=application.vehicle_count,
        user_id=application.user_id,
        service_account_id=application.service_account_id,
        tenant_id=tenant_id,
        linked_by_customer_id=application.linked_by_customer_id or actor.id,
        linked_at=application.linked_at or now,
        approved_by_customer_id=actor.id,
        approved_at=now,
        approval_note=(approval_note or "").strip() or None,
        created_at=now,
        updated_at=now,
    )
    db.add(participant)
    db.flush()

    application.status = "approved"
    application.reviewed_by_customer_id = actor.id
    application.reviewed_at = now
    application.review_note = (approval_note or "").strip() or None
    application.decision_reason = (decision_reason or approval_note or "Approved for beta").strip()
    application.tenant_id = tenant_id
    application.updated_at = now

    db.add(application)
    refresh_beta_metrics_for_participant(db, participant=participant, commit=False)
    db.commit()
    db.refresh(participant)
    return participant


def reject_beta_application(
    db: Session,
    *,
    application_id: int,
    actor: Customer,
    decision_reason: str,
    review_note: Optional[str] = None,
) -> BetaApplication:
    ensure_beta_program_schema(db)

    application = db.query(BetaApplication).filter(BetaApplication.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Beta přihláška nebyla nalezena.")
    if _find_participant_by_application(db, application.id):
        raise HTTPException(status_code=400, detail="Schválenou přihlášku nelze zamítnout.")

    application.status = "rejected"
    application.reviewed_by_customer_id = actor.id
    application.reviewed_at = datetime.utcnow()
    application.review_note = (review_note or "").strip() or None
    application.decision_reason = str(decision_reason or "").strip()
    application.updated_at = datetime.utcnow()
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


def get_or_create_beta_metrics(db: Session, participant: BetaParticipant) -> BetaActivityMetric:
    ensure_beta_program_schema(db)
    metrics = (
        db.query(BetaActivityMetric)
        .filter(BetaActivityMetric.participant_id == participant.id)
        .first()
    )
    if metrics:
        return metrics

    metrics = BetaActivityMetric(
        participant_id=participant.id,
        user_id=participant.user_id,
        service_account_id=participant.service_account_id,
        tenant_id=participant.tenant_id,
        login_count=0,
        vehicles_created_count=0,
        service_records_count=0,
        reservations_count=0,
        feedback_count=0,
        bug_reports_count=0,
        activity_score=0.0,
        impact_score=0.0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(metrics)
    db.flush()
    return metrics


def _latest_datetime(*values: Optional[datetime]) -> Optional[datetime]:
    valid = [value for value in values if value is not None]
    if not valid:
        return None
    return max(valid)


def _user_scope_email_candidates(participant: BetaParticipant, linked_user: Optional[Customer]) -> List[str]:
    emails = {participant.email_normalized}
    if linked_user and linked_user.email:
        emails.add(normalize_beta_email(linked_user.email))
    return [email for email in emails if email]


def _count_login_events(
    db: Session,
    *,
    participant: BetaParticipant,
    linked_user: Optional[Customer],
    linked_service: Optional[Customer],
    tenant_id: Optional[int],
) -> int:
    if participant.applicant_type in {"service", "company"} and tenant_id is not None:
        return (
            db.query(SecurityAccessLog)
            .filter(
                SecurityAccessLog.tenant_id == tenant_id,
                SecurityAccessLog.event_type == "login_success",
            )
            .count()
        )

    email_candidates = _user_scope_email_candidates(participant, linked_user)
    query = db.query(SecurityAccessLog).filter(SecurityAccessLog.event_type == "login_success")

    if participant.service_account_id:
        service_email = normalize_beta_email(linked_service.email) if linked_service and linked_service.email else None
        conditions = [SecurityAccessLog.customer_id == participant.service_account_id]
        if service_email:
            conditions.append(func.lower(SecurityAccessLog.user_email) == service_email)
        return query.filter(or_(*conditions)).count()

    conditions = []
    if participant.user_id:
        conditions.append(SecurityAccessLog.customer_id == participant.user_id)
    if email_candidates:
        conditions.append(func.lower(SecurityAccessLog.user_email).in_(email_candidates))
    if not conditions:
        return 0
    return query.filter(or_(*conditions)).count()


def _vehicle_ids_for_user_scope(db: Session, email_candidates: Iterable[str]) -> List[int]:
    normalized = [email for email in email_candidates if email]
    if not normalized:
        return []
    return [
        int(row[0])
        for row in (
            db.query(Vehicle.id)
            .filter(func.lower(Vehicle.user_email).in_(normalized))
            .all()
        )
    ]


def _count_user_scope_vehicles(db: Session, email_candidates: Iterable[str]) -> int:
    normalized = [email for email in email_candidates if email]
    if not normalized:
        return 0
    return db.query(Vehicle).filter(func.lower(Vehicle.user_email).in_(normalized)).count()


def _count_user_scope_records(db: Session, *, participant: BetaParticipant, email_candidates: Iterable[str]) -> int:
    vehicle_ids = _vehicle_ids_for_user_scope(db, email_candidates)
    conditions = []
    if vehicle_ids:
        conditions.append(ServiceRecord.vehicle_id.in_(vehicle_ids))
    if participant.user_id:
        conditions.append(ServiceRecord.user_id == participant.user_id)
    if not conditions:
        return 0
    return db.query(ServiceRecord).filter(or_(*conditions)).count()


def _count_user_scope_reservations(db: Session, *, participant: BetaParticipant, email_candidates: Iterable[str]) -> int:
    vehicle_ids = _vehicle_ids_for_user_scope(db, email_candidates)
    conditions = []
    if vehicle_ids:
        conditions.append(Reservation.vehicle_id.in_(vehicle_ids))
    if participant.user_id:
        conditions.append(Reservation.customer_id == participant.user_id)
    if not conditions:
        return 0
    return db.query(Reservation).filter(or_(*conditions)).count()


def _feedback_stats(db: Session, participant_id: int) -> Dict[str, int]:
    feedback_rows = (
        db.query(BetaFeedback)
        .filter(BetaFeedback.participant_id == participant_id)
        .order_by(BetaFeedback.id.asc())
        .all()
    )
    stats = {
        "feedback_count": 0,
        "bug_reports_count": 0,
        "planned_count": 0,
        "resolved_count": 0,
        "reviewed_count": 0,
        "critical_bug_count": 0,
        "high_bug_count": 0,
    }
    for row in feedback_rows:
        category = str(row.category or "").lower()
        status = str(row.status or "").lower()
        severity = str(row.severity or "").lower()
        if category == "bug_report":
            stats["bug_reports_count"] += 1
            if severity == "critical":
                stats["critical_bug_count"] += 1
            if severity == "high":
                stats["high_bug_count"] += 1
        else:
            stats["feedback_count"] += 1
        if status == "reviewed":
            stats["reviewed_count"] += 1
        if status == "planned":
            stats["planned_count"] += 1
        if status == "resolved":
            stats["resolved_count"] += 1
    return stats


def refresh_beta_metrics_for_participant(
    db: Session,
    *,
    participant: Optional[BetaParticipant] = None,
    participant_id: Optional[int] = None,
    commit: bool = True,
) -> BetaActivityMetric:
    ensure_beta_program_schema(db)

    if participant is None:
        if participant_id is None:
            raise ValueError("participant or participant_id is required")
        participant = db.query(BetaParticipant).filter(BetaParticipant.id == participant_id).first()
    if not participant:
        raise HTTPException(status_code=404, detail="Beta participant nebyl nalezen.")

    linked_user = _load_customer(db, participant.user_id)
    linked_service = _load_customer(db, participant.service_account_id)
    tenant_id = _resolve_participant_tenant_id(
        db,
        participant=participant,
        user_id=participant.user_id,
        service_account_id=participant.service_account_id,
        tenant_id=participant.tenant_id,
    )

    email_candidates = _user_scope_email_candidates(participant, linked_user)
    feedback_summary = _feedback_stats(db, participant.id)

    if participant.applicant_type in {"service", "company"} and tenant_id is not None:
        vehicles_created_count = db.query(Vehicle).filter(Vehicle.tenant_id == tenant_id, Vehicle.status != "archived").count()
        service_records_count = db.query(ServiceRecord).filter(ServiceRecord.tenant_id == tenant_id).count()
        reservations_count = db.query(Reservation).filter(Reservation.tenant_id == tenant_id).count()
    else:
        vehicles_created_count = _count_user_scope_vehicles(db, email_candidates)
        service_records_count = _count_user_scope_records(db, participant=participant, email_candidates=email_candidates)
        reservations_count = _count_user_scope_reservations(db, participant=participant, email_candidates=email_candidates)

    login_count = _count_login_events(
        db,
        participant=participant,
        linked_user=linked_user,
        linked_service=linked_service,
        tenant_id=tenant_id,
    )

    feedback_count = int(feedback_summary["feedback_count"])
    bug_reports_count = int(feedback_summary["bug_reports_count"])

    security_last_active = None
    if participant.applicant_type in {"service", "company"} and tenant_id is not None:
        security_last_active = (
            db.query(func.max(SecurityAccessLog.created_at))
            .filter(
                SecurityAccessLog.tenant_id == tenant_id,
                SecurityAccessLog.event_type.in_(["login_success", "api_activity"]),
            )
            .scalar()
        )
    else:
        conditions = []
        if participant.user_id:
            conditions.append(SecurityAccessLog.customer_id == participant.user_id)
        if email_candidates:
            conditions.append(func.lower(SecurityAccessLog.user_email).in_(email_candidates))
        if participant.service_account_id:
            service_email = normalize_beta_email(linked_service.email) if linked_service and linked_service.email else None
            conditions.append(SecurityAccessLog.customer_id == participant.service_account_id)
            if service_email:
                conditions.append(func.lower(SecurityAccessLog.user_email) == service_email)
        if conditions:
            security_last_active = (
                db.query(func.max(SecurityAccessLog.created_at))
                .filter(
                    SecurityAccessLog.event_type.in_(["login_success", "api_activity"]),
                    or_(*conditions),
                )
                .scalar()
            )

    vehicle_last_active = None
    if participant.applicant_type in {"service", "company"} and tenant_id is not None:
        vehicle_last_active = db.query(func.max(Vehicle.created_at)).filter(Vehicle.tenant_id == tenant_id).scalar()
    else:
        if email_candidates:
            vehicle_last_active = (
                db.query(func.max(Vehicle.created_at))
                .filter(func.lower(Vehicle.user_email).in_(email_candidates))
                .scalar()
            )

    record_last_active = None
    if participant.applicant_type in {"service", "company"} and tenant_id is not None:
        record_last_active = (
            db.query(func.max(ServiceRecord.performed_at))
            .filter(ServiceRecord.tenant_id == tenant_id)
            .scalar()
        )
    else:
        vehicle_ids = _vehicle_ids_for_user_scope(db, email_candidates)
        conditions = []
        if vehicle_ids:
            conditions.append(ServiceRecord.vehicle_id.in_(vehicle_ids))
        if participant.user_id:
            conditions.append(ServiceRecord.user_id == participant.user_id)
        if conditions:
            record_last_active = (
                db.query(func.max(ServiceRecord.performed_at))
                .filter(or_(*conditions))
                .scalar()
            )

    reservation_last_active = None
    if participant.applicant_type in {"service", "company"} and tenant_id is not None:
        reservation_last_active = (
            db.query(func.max(Reservation.created_at))
            .filter(Reservation.tenant_id == tenant_id)
            .scalar()
        )
    else:
        vehicle_ids = _vehicle_ids_for_user_scope(db, email_candidates)
        conditions = []
        if vehicle_ids:
            conditions.append(Reservation.vehicle_id.in_(vehicle_ids))
        if participant.user_id:
            conditions.append(Reservation.customer_id == participant.user_id)
        if conditions:
            reservation_last_active = (
                db.query(func.max(Reservation.created_at))
                .filter(or_(*conditions))
                .scalar()
            )

    feedback_last_active = (
        db.query(func.max(BetaFeedback.created_at))
        .filter(BetaFeedback.participant_id == participant.id)
        .scalar()
    )

    last_active_at = _latest_datetime(
        security_last_active,
        getattr(linked_user, "last_seen_at", None),
        getattr(linked_service, "last_seen_at", None),
        vehicle_last_active,
        record_last_active,
        reservation_last_active,
        feedback_last_active,
    )

    breadth = sum(
        1
        for value in [
            vehicles_created_count,
            service_records_count,
            reservations_count,
            feedback_count,
            bug_reports_count,
        ]
        if int(value or 0) > 0
    )
    recency_bonus = 0
    if last_active_at is not None:
        now = datetime.utcnow()
        if last_active_at >= now - timedelta(days=7):
            recency_bonus = 12
        elif last_active_at >= now - timedelta(days=30):
            recency_bonus = 6
        elif last_active_at >= now - timedelta(days=60):
            recency_bonus = 2

    activity_score = float(
        login_count
        + (vehicles_created_count * 6)
        + (service_records_count * 7)
        + (reservations_count * 5)
        + (feedback_count * 8)
        + (bug_reports_count * 10)
        + (breadth * 4)
        + recency_bonus
    )
    impact_score = float(
        activity_score
        + (feedback_summary["reviewed_count"] * 3)
        + (feedback_summary["planned_count"] * 7)
        + (feedback_summary["resolved_count"] * 10)
        + (feedback_summary["high_bug_count"] * 6)
        + (feedback_summary["critical_bug_count"] * 12)
        + (10 if participant.applicant_type in {"service", "company"} else 0)
    )

    metrics = get_or_create_beta_metrics(db, participant)
    metrics.user_id = participant.user_id
    metrics.service_account_id = participant.service_account_id
    metrics.tenant_id = tenant_id
    metrics.login_count = int(login_count)
    metrics.vehicles_created_count = int(vehicles_created_count)
    metrics.service_records_count = int(service_records_count)
    metrics.reservations_count = int(reservations_count)
    metrics.feedback_count = int(feedback_count)
    metrics.bug_reports_count = int(bug_reports_count)
    metrics.last_active_at = last_active_at
    metrics.activity_score = activity_score
    metrics.impact_score = impact_score
    metrics.calculated_at = datetime.utcnow()
    metrics.metrics_payload_json = json.dumps(
        {
            "breadth": breadth,
            "recency_bonus": recency_bonus,
            "feedback_reviewed_count": feedback_summary["reviewed_count"],
            "feedback_planned_count": feedback_summary["planned_count"],
            "feedback_resolved_count": feedback_summary["resolved_count"],
            "critical_bug_count": feedback_summary["critical_bug_count"],
            "high_bug_count": feedback_summary["high_bug_count"],
            "scope": participant.applicant_type,
            "tenant_id": tenant_id,
        },
        ensure_ascii=False,
    )
    metrics.updated_at = datetime.utcnow()

    participant.tenant_id = tenant_id
    participant.last_active_at = last_active_at
    participant.updated_at = datetime.utcnow()

    db.add(metrics)
    db.add(participant)
    if commit:
        db.commit()
        db.refresh(metrics)
    return metrics


def refresh_beta_metrics_for_all(
    db: Session,
    *,
    participant_ids: Optional[Iterable[int]] = None,
) -> List[BetaActivityMetric]:
    ensure_beta_program_schema(db)

    query = db.query(BetaParticipant).filter(BetaParticipant.status.in_(["active", "paused"]))
    if participant_ids:
        query = query.filter(BetaParticipant.id.in_([int(participant_id) for participant_id in participant_ids]))
    participants = query.order_by(BetaParticipant.id.asc()).all()

    refreshed: List[BetaActivityMetric] = []
    for participant in participants:
        refreshed.append(refresh_beta_metrics_for_participant(db, participant=participant, commit=False))
    db.commit()
    return refreshed


def build_lifetime_premium_recommendation(
    db: Session,
    *,
    participant: BetaParticipant,
    metrics: Optional[BetaActivityMetric] = None,
    reward: Optional[BetaReward] = None,
) -> Dict[str, Any]:
    ensure_beta_program_schema(db)
    metrics = metrics or refresh_beta_metrics_for_participant(db, participant=participant, commit=False)
    reward = reward or (
        db.query(BetaReward)
        .filter(
            BetaReward.participant_id == participant.id,
            BetaReward.reward_type == "lifetime_premium",
        )
        .order_by(BetaReward.id.desc())
        .first()
    )
    feedback_summary = _feedback_stats(db, participant.id)
    feedback_total = feedback_summary["feedback_count"] + feedback_summary["bug_reports_count"]
    breadth = sum(
        1
        for value in [
            metrics.vehicles_created_count,
            metrics.service_records_count,
            metrics.reservations_count,
            metrics.feedback_count,
            metrics.bug_reports_count,
        ]
        if int(value or 0) > 0
    )
    recent_activity = metrics.last_active_at is not None and metrics.last_active_at >= datetime.utcnow() - timedelta(days=45)
    already_granted = bool(reward and reward.status == "granted")

    recommended = bool(
        not already_granted
        and participant.status == "active"
        and recent_activity
        and metrics.activity_score >= 45
        and metrics.impact_score >= 75
        and breadth >= 3
        and feedback_total >= 2
        and (
            feedback_summary["planned_count"] > 0
            or feedback_summary["resolved_count"] > 0
            or feedback_summary["critical_bug_count"] > 0
            or feedback_summary["high_bug_count"] > 0
        )
    )

    reasons: List[str] = []
    missing: List[str] = []

    if metrics.activity_score >= 45:
        reasons.append(f"Aktivita dosáhla skóre {metrics.activity_score:.0f}.")
    else:
        missing.append(f"Aktivita je zatím jen {metrics.activity_score:.0f}/45.")

    if metrics.impact_score >= 75:
        reasons.append(f"Impact skóre je {metrics.impact_score:.0f}.")
    else:
        missing.append(f"Impact skóre je zatím {metrics.impact_score:.0f}/75.")

    if breadth >= 3:
        reasons.append(f"Tester použil {breadth} klíčové oblasti produktu.")
    else:
        missing.append("Chybí širší pokrytí klíčových oblastí produktu.")

    if feedback_total >= 2:
        reasons.append(f"Poslal {feedback_total} hodnotných feedback/bug vstupů.")
    else:
        missing.append("Potřebujeme více konkrétního feedbacku nebo bug reportů.")

    if recent_activity:
        reasons.append("Aktivita je čerstvá v posledních 45 dnech.")
    else:
        missing.append("Tester nebyl aktivní v posledních 45 dnech.")

    if feedback_summary["planned_count"] > 0 or feedback_summary["resolved_count"] > 0:
        reasons.append("Část feedbacku už byla zařazena nebo vyřešena.")
    elif feedback_summary["critical_bug_count"] > 0 or feedback_summary["high_bug_count"] > 0:
        reasons.append("Nahlásil aspoň jeden vysoce prioritní bug.")
    else:
        missing.append("Zatím chybí potvrzený vyšší přínos do roadmapy nebo bugfixů.")

    status = "eligible" if recommended else "observe"
    if already_granted:
        status = "already_granted"
    elif reward and reward.status == "declined":
        status = "declined"

    return {
        "status": status,
        "recommended": recommended,
        "reasons": reasons,
        "missing": missing,
        "feedback_total": feedback_total,
        "breadth": breadth,
        "already_granted": already_granted,
        "current_reward_status": reward.status if reward else None,
    }


def submit_beta_feedback(
    db: Session,
    *,
    participant: BetaParticipant,
    title: str,
    message: str,
    category: str,
    severity: Optional[str],
    context_area: Optional[str],
    route_path: Optional[str],
    source: str = "portal",
) -> BetaFeedback:
    ensure_beta_program_schema(db)

    if participant.status != "active":
        raise HTTPException(status_code=403, detail="Feedback mohou posílat jen aktivní beta testeři.")

    feedback = BetaFeedback(
        participant_id=participant.id,
        application_id=participant.application_id,
        user_id=participant.user_id,
        service_account_id=participant.service_account_id,
        tenant_id=participant.tenant_id,
        category=normalize_beta_feedback_category(category),
        status="new",
        severity=normalize_beta_feedback_severity(severity),
        title=str(title or "").strip(),
        message=str(message or "").strip(),
        context_area=(context_area or "").strip() or None,
        route_path=(route_path or "").strip() or None,
        source=(source or "portal").strip() or "portal",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(feedback)
    db.flush()
    refresh_beta_metrics_for_participant(db, participant=participant, commit=False)
    db.commit()
    db.refresh(feedback)
    return feedback


def review_beta_feedback(
    db: Session,
    *,
    feedback_id: int,
    actor: Customer,
    status: str,
    admin_note: Optional[str],
) -> BetaFeedback:
    ensure_beta_program_schema(db)

    feedback = db.query(BetaFeedback).filter(BetaFeedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Beta feedback nebyl nalezen.")

    feedback.status = normalize_beta_feedback_status(status)
    feedback.admin_note = (admin_note or "").strip() or None
    feedback.reviewed_by_customer_id = actor.id
    feedback.reviewed_at = datetime.utcnow()
    feedback.updated_at = datetime.utcnow()
    db.add(feedback)

    participant = (
        db.query(BetaParticipant)
        .filter(BetaParticipant.id == feedback.participant_id)
        .first()
    )
    if participant:
        refresh_beta_metrics_for_participant(db, participant=participant, commit=False)
    db.commit()
    db.refresh(feedback)
    return feedback


def grant_beta_lifetime_premium(
    db: Session,
    *,
    participant_id: int,
    actor: Customer,
    decision_reason: str,
    decision: str = "grant",
) -> BetaReward:
    ensure_beta_program_schema(db)

    normalized_decision = _normalize_beta_reward_decision(decision)
    participant = db.query(BetaParticipant).filter(BetaParticipant.id == participant_id).first()
    if not participant:
        raise HTTPException(status_code=404, detail="Beta participant nebyl nalezen.")

    reward = (
        db.query(BetaReward)
        .filter(
            BetaReward.participant_id == participant.id,
            BetaReward.reward_type == "lifetime_premium",
        )
        .order_by(BetaReward.id.desc())
        .first()
    )

    now = datetime.utcnow()
    if normalized_decision == "decline":
        if reward and reward.status == "granted":
            raise HTTPException(status_code=400, detail="Již přidělený lifetime premium nelze tímto endpointem zamítnout.")
        if not reward:
            reward = BetaReward(
                participant_id=participant.id,
                reward_type="lifetime_premium",
                status="declined",
                tenant_id=participant.tenant_id,
                approved_by_customer_id=actor.id,
                approved_at=now,
                decision_reason=str(decision_reason or "").strip(),
                granted_license_plan=None,
                granted_until=None,
                audit_payload_json=json.dumps({"decision": "decline"}, ensure_ascii=False),
                created_at=now,
                updated_at=now,
            )
        else:
            reward.status = "declined"
            reward.approved_by_customer_id = actor.id
            reward.approved_at = now
            reward.decision_reason = str(decision_reason or "").strip()
            reward.granted_license_plan = None
            reward.granted_until = None
            reward.audit_payload_json = json.dumps({"decision": "decline"}, ensure_ascii=False)
            reward.updated_at = now
        db.add(reward)
        db.commit()
        db.refresh(reward)
        return reward

    if reward and reward.status == "granted":
        return reward

    tenant_id = _resolve_participant_tenant_id(
        db,
        participant=participant,
        user_id=participant.user_id,
        service_account_id=participant.service_account_id,
        tenant_id=participant.tenant_id,
    )
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Lifetime premium nelze přidělit bez navázaného tenant účtu.")

    license_obj = get_or_create_license(db, tenant_id)
    premium_features = PLAN_FEATURES["premium"]
    previous_license_snapshot = {
        "plan": license_obj.plan,
        "status": license_obj.status,
        "vehicles_limit": license_obj.vehicles_limit,
        "valid_from": _safe_iso(license_obj.valid_from),
        "valid_to": _safe_iso(license_obj.valid_to),
    }
    license_obj.plan = "premium"
    license_obj.status = "active"
    license_obj.vehicles_limit = PLAN_LIMITS["premium"]
    license_obj.valid_from = license_obj.valid_from or now
    license_obj.valid_to = None
    license_obj.vin_decode_enabled = premium_features["vin_decode_enabled"]
    license_obj.ares_enabled = premium_features["ares_enabled"]
    license_obj.reminders_enabled = premium_features["reminders_enabled"]
    license_obj.updated_at = now
    db.add(license_obj)

    subscription = (
        db.query(LicenseSubscription)
        .filter(LicenseSubscription.tenant_id == tenant_id)
        .first()
    )
    previous_subscription_snapshot = None
    if subscription:
        previous_subscription_snapshot = {
            "provider": subscription.provider,
            "status": subscription.status,
            "plan_current": subscription.plan_current,
            "billing_period": subscription.billing_period,
            "auto_renew_enabled": bool(subscription.auto_renew_enabled),
            "current_period_end": _safe_iso(subscription.current_period_end),
            "next_charge_at": _safe_iso(subscription.next_charge_at),
        }
    else:
        subscription = LicenseSubscription(
            tenant_id=tenant_id,
            provider="beta",
            status="legacy_manual",
            auto_renew_enabled=False,
            credit_balance_halers=0,
            failed_renewal_attempts=0,
            created_at=now,
            updated_at=now,
        )

    subscription.provider = "beta"
    subscription.status = "legacy_manual"
    subscription.plan_current = "premium"
    subscription.billing_period = None
    subscription.auto_renew_enabled = False
    subscription.pending_plan_change = None
    subscription.init_recurring_id = None
    subscription.current_period_start = now
    subscription.current_period_end = None
    subscription.next_charge_at = None
    subscription.grace_until = None
    subscription.cancel_requested_at = None
    subscription.last_payment_at = now
    subscription.last_trans_id = "beta_lifetime_reward"
    subscription.failed_renewal_attempts = 0
    subscription.notified_first_payment_at = None
    subscription.notified_renewal_failed_at = None
    subscription.notified_grace_end_at = None
    subscription.notified_period_d14_at = None
    subscription.notified_period_d7_at = None
    subscription.notified_period_d1_at = None
    subscription.updated_at = now
    db.add(subscription)

    payload = {
        "decision": "grant",
        "license_before": previous_license_snapshot,
        "subscription_before": previous_subscription_snapshot,
        "license_after": {
            "plan": "premium",
            "status": "active",
            "valid_to": None,
        },
    }

    if not reward:
        reward = BetaReward(
            participant_id=participant.id,
            reward_type="lifetime_premium",
            status="granted",
            tenant_id=tenant_id,
            approved_by_customer_id=actor.id,
            approved_at=now,
            decision_reason=str(decision_reason or "").strip(),
            granted_license_plan="premium",
            granted_until=None,
            audit_payload_json=json.dumps(payload, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
    else:
        reward.status = "granted"
        reward.tenant_id = tenant_id
        reward.approved_by_customer_id = actor.id
        reward.approved_at = now
        reward.decision_reason = str(decision_reason or "").strip()
        reward.granted_license_plan = "premium"
        reward.granted_until = None
        reward.audit_payload_json = json.dumps(payload, ensure_ascii=False)
        reward.updated_at = now
    db.add(reward)
    db.commit()
    db.refresh(reward)
    return reward


def find_beta_participant_for_customer(db: Session, customer: Customer) -> Optional[BetaParticipant]:
    ensure_beta_program_schema(db)

    if not customer:
        return None

    normalized_email = normalize_beta_email(customer.email or "")
    participant = (
        db.query(BetaParticipant)
        .filter(
            BetaParticipant.status.in_(["active", "paused"]),
            or_(
                BetaParticipant.user_id == customer.id,
                BetaParticipant.service_account_id == customer.id,
                BetaParticipant.email_normalized == normalized_email,
            ),
        )
        .order_by(BetaParticipant.id.desc())
        .first()
    )
    if participant:
        return participant

    return (
        db.query(BetaParticipant)
        .filter(
            BetaParticipant.status.in_(["active", "paused"]),
            BetaParticipant.applicant_type == "company",
            BetaParticipant.tenant_id == customer.tenant_id,
        )
        .order_by(BetaParticipant.id.desc())
        .first()
    )


def serialize_beta_reward(reward: Optional[BetaReward]) -> Optional[Dict[str, Any]]:
    if not reward:
        return None
    return {
        "id": reward.id,
        "participant_id": reward.participant_id,
        "reward_type": reward.reward_type,
        "status": reward.status,
        "tenant_id": reward.tenant_id,
        "approved_by_customer_id": reward.approved_by_customer_id,
        "approved_at": _safe_iso(reward.approved_at),
        "decision_reason": reward.decision_reason,
        "granted_license_plan": reward.granted_license_plan,
        "granted_until": _safe_iso(reward.granted_until),
        "audit_payload": json.loads(reward.audit_payload_json) if reward.audit_payload_json else None,
    }


def serialize_beta_metrics(metrics: Optional[BetaActivityMetric]) -> Optional[Dict[str, Any]]:
    if not metrics:
        return None
    payload = None
    if metrics.metrics_payload_json:
        try:
            payload = json.loads(metrics.metrics_payload_json)
        except Exception:
            payload = {"raw": metrics.metrics_payload_json}
    return {
        "participant_id": metrics.participant_id,
        "login_count": int(metrics.login_count or 0),
        "vehicles_created_count": int(metrics.vehicles_created_count or 0),
        "service_records_count": int(metrics.service_records_count or 0),
        "reservations_count": int(metrics.reservations_count or 0),
        "feedback_count": int(metrics.feedback_count or 0),
        "bug_reports_count": int(metrics.bug_reports_count or 0),
        "last_active_at": _safe_iso(metrics.last_active_at),
        "activity_score": float(metrics.activity_score or 0.0),
        "impact_score": float(metrics.impact_score or 0.0),
        "calculated_at": _safe_iso(metrics.calculated_at),
        "meta": payload,
    }


def serialize_beta_application(
    db: Session,
    application: BetaApplication,
) -> Dict[str, Any]:
    participant = _find_participant_by_application(db, application.id)
    return {
        "id": application.id,
        "status": application.status,
        "applicant_type": application.applicant_type,
        "name": application.name,
        "email": application.email,
        "phone": application.phone,
        "vehicle_count": int(application.vehicle_count or 0),
        "note": application.note,
        "gdpr_consent": bool(application.gdpr_consent),
        "user_id": application.user_id,
        "service_account_id": application.service_account_id,
        "tenant_id": application.tenant_id,
        "link_method": application.link_method,
        "link_confidence": application.link_confidence,
        "link_note": application.link_note,
        "linked_at": _safe_iso(application.linked_at),
        "linked_by_customer_id": application.linked_by_customer_id,
        "linked_user": _serialize_customer(_load_customer(db, application.user_id)),
        "linked_service_account": _serialize_customer(_load_customer(db, application.service_account_id)),
        "linked_tenant": _serialize_tenant(_load_tenant(db, application.tenant_id)),
        "reviewed_by_customer_id": application.reviewed_by_customer_id,
        "reviewed_at": _safe_iso(application.reviewed_at),
        "review_note": application.review_note,
        "decision_reason": application.decision_reason,
        "participant_id": participant.id if participant else None,
        "created_at": _safe_iso(application.created_at),
        "updated_at": _safe_iso(application.updated_at),
    }


def serialize_beta_feedback(db: Session, feedback: BetaFeedback) -> Dict[str, Any]:
    participant = db.query(BetaParticipant).filter(BetaParticipant.id == feedback.participant_id).first()
    return {
        "id": feedback.id,
        "participant_id": feedback.participant_id,
        "participant_name": participant.name if participant else None,
        "participant_email": participant.email if participant else None,
        "application_id": feedback.application_id,
        "user_id": feedback.user_id,
        "service_account_id": feedback.service_account_id,
        "tenant_id": feedback.tenant_id,
        "category": feedback.category,
        "status": feedback.status,
        "severity": feedback.severity,
        "title": feedback.title,
        "message": feedback.message,
        "context_area": feedback.context_area,
        "route_path": feedback.route_path,
        "source": feedback.source,
        "reviewed_by_customer_id": feedback.reviewed_by_customer_id,
        "reviewed_at": _safe_iso(feedback.reviewed_at),
        "admin_note": feedback.admin_note,
        "created_at": _safe_iso(feedback.created_at),
        "updated_at": _safe_iso(feedback.updated_at),
    }


def serialize_beta_participant(
    db: Session,
    participant: BetaParticipant,
    *,
    metrics: Optional[BetaActivityMetric] = None,
    reward: Optional[BetaReward] = None,
) -> Dict[str, Any]:
    metrics = metrics or get_or_create_beta_metrics(db, participant)
    reward = reward or (
        db.query(BetaReward)
        .filter(
            BetaReward.participant_id == participant.id,
            BetaReward.reward_type == "lifetime_premium",
        )
        .order_by(BetaReward.id.desc())
        .first()
    )
    recommendation = build_lifetime_premium_recommendation(
        db,
        participant=participant,
        metrics=metrics,
        reward=reward,
    )
    return {
        "id": participant.id,
        "application_id": participant.application_id,
        "status": participant.status,
        "applicant_type": participant.applicant_type,
        "name": participant.name,
        "email": participant.email,
        "phone": participant.phone,
        "declared_vehicle_count": int(participant.declared_vehicle_count or 0),
        "user_id": participant.user_id,
        "service_account_id": participant.service_account_id,
        "tenant_id": participant.tenant_id,
        "linked_at": _safe_iso(participant.linked_at),
        "approved_by_customer_id": participant.approved_by_customer_id,
        "approved_at": _safe_iso(participant.approved_at),
        "approval_note": participant.approval_note,
        "last_active_at": _safe_iso(participant.last_active_at),
        "linked_user": _serialize_customer(_load_customer(db, participant.user_id)),
        "linked_service_account": _serialize_customer(_load_customer(db, participant.service_account_id)),
        "linked_tenant": _serialize_tenant(_load_tenant(db, participant.tenant_id)),
        "metrics": serialize_beta_metrics(metrics),
        "reward": serialize_beta_reward(reward),
        "recommendation": recommendation,
        "created_at": _safe_iso(participant.created_at),
        "updated_at": _safe_iso(participant.updated_at),
    }


def build_beta_admin_dashboard(db: Session) -> Dict[str, Any]:
    ensure_beta_program_schema(db)

    applications = (
        db.query(BetaApplication)
        .order_by(BetaApplication.created_at.desc(), BetaApplication.id.desc())
        .limit(100)
        .all()
    )
    for application in applications:
        if application.status == "pending":
            refresh_beta_application_link(db, application, commit=False)

    participants = (
        db.query(BetaParticipant)
        .order_by(BetaParticipant.approved_at.desc(), BetaParticipant.id.desc())
        .limit(100)
        .all()
    )
    metrics_by_participant: Dict[int, BetaActivityMetric] = {}
    for participant in participants:
        metrics_by_participant[participant.id] = refresh_beta_metrics_for_participant(
            db,
            participant=participant,
            commit=False,
        )

    rewards = (
        db.query(BetaReward)
        .order_by(BetaReward.approved_at.desc(), BetaReward.id.desc())
        .limit(100)
        .all()
    )
    reward_by_participant: Dict[int, BetaReward] = {}
    for reward in rewards:
        reward_by_participant.setdefault(int(reward.participant_id), reward)

    feedback_items = (
        db.query(BetaFeedback)
        .order_by(BetaFeedback.created_at.desc(), BetaFeedback.id.desc())
        .limit(150)
        .all()
    )

    db.commit()

    serialized_participants = [
        serialize_beta_participant(
            db,
            participant,
            metrics=metrics_by_participant.get(participant.id),
            reward=reward_by_participant.get(participant.id),
        )
        for participant in participants
    ]
    serialized_applications = [serialize_beta_application(db, application) for application in applications]
    serialized_feedback = [serialize_beta_feedback(db, item) for item in feedback_items]
    serialized_rewards = [serialize_beta_reward(reward) for reward in rewards]

    summary = {
        "applications_pending": sum(1 for item in applications if item.status == "pending"),
        "applications_rejected": sum(1 for item in applications if item.status == "rejected"),
        "participants_active": sum(1 for item in participants if item.status == "active"),
        "participants_paused": sum(1 for item in participants if item.status == "paused"),
        "feedback_open": sum(1 for item in feedback_items if item.status in {"new", "reviewed"}),
        "bug_reports_open": sum(1 for item in feedback_items if item.category == "bug_report" and item.status in {"new", "reviewed"}),
        "lifetime_granted": sum(1 for item in rewards if item.status == "granted"),
        "lifetime_declined": sum(1 for item in rewards if item.status == "declined"),
        "lifetime_recommended": sum(
            1
            for item in serialized_participants
            if (item.get("recommendation") or {}).get("recommended")
        ),
    }

    return {
        "generated_at": _safe_iso(datetime.utcnow()),
        "summary": summary,
        "applications": serialized_applications,
        "participants": serialized_participants,
        "feedback": serialized_feedback,
        "rewards": serialized_rewards,
    }


def build_beta_portal_payload(db: Session, customer: Customer) -> Dict[str, Any]:
    ensure_beta_program_schema(db)

    participant = find_beta_participant_for_customer(db, customer)
    latest_application = (
        db.query(BetaApplication)
        .filter(BetaApplication.email_normalized == normalize_beta_email(customer.email or ""))
        .order_by(BetaApplication.id.desc())
        .first()
    )

    if participant:
        metrics = refresh_beta_metrics_for_participant(db, participant=participant, commit=False)
        reward = (
            db.query(BetaReward)
            .filter(
                BetaReward.participant_id == participant.id,
                BetaReward.reward_type == "lifetime_premium",
            )
            .order_by(BetaReward.id.desc())
            .first()
        )
        feedback_items = (
            db.query(BetaFeedback)
            .filter(BetaFeedback.participant_id == participant.id)
            .order_by(BetaFeedback.created_at.desc(), BetaFeedback.id.desc())
            .limit(50)
            .all()
        )
        db.commit()
        return {
            "is_participant": True,
            "participant": serialize_beta_participant(db, participant, metrics=metrics, reward=reward),
            "application": serialize_beta_application(db, latest_application) if latest_application else None,
            "feedback": [serialize_beta_feedback(db, item) for item in feedback_items],
            "reward": serialize_beta_reward(reward),
        }

    return {
        "is_participant": False,
        "participant": None,
        "application": serialize_beta_application(db, latest_application) if latest_application else None,
        "feedback": [],
        "reward": None,
    }
