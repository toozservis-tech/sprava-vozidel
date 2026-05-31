"""Claim workflow pro servisní mapu."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..audit_log import write_global_audit_log
from ..models import ServiceLocation, ServiceLocationClaim
from .constants import PROTECTED_VERIFICATION, VERIFICATION_CLAIMED, VERIFICATION_VERIFIED


def _audit_hash(*parts: str) -> str:
    raw = "|".join(p for p in parts if p)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_service_location_claim(
    db: Session,
    *,
    location_id: int,
    service_tenant_id: int,
    submitted_by_user_id: int,
    ico: str | None = None,
    dic: str | None = None,
    business_name: str | None = None,
    claim_method: str = "admin_review",
    ip_hash: str | None = None,
    user_agent_hash: str | None = None,
) -> ServiceLocationClaim:
    location = db.query(ServiceLocation).filter(ServiceLocation.id == location_id).first()
    if not location or not location.is_active:
        raise HTTPException(status_code=404, detail="Servisní místo nenalezeno.")

    fraud_flags: dict[str, Any] = {}
    if location.verification_status == VERIFICATION_VERIFIED and location.linked_service_tenant_id:
        if int(location.linked_service_tenant_id) != int(service_tenant_id):
            fraud_flags["verified_owner_conflict"] = True
            claim_method = "admin_review"

    pending = (
        db.query(ServiceLocationClaim)
        .filter(
            ServiceLocationClaim.service_location_id == location_id,
            ServiceLocationClaim.claim_status == "pending",
        )
        .first()
    )
    if pending:
        raise HTTPException(status_code=409, detail="Na tomto místě už probíhá nárok.")

    existing_for_tenant = (
        db.query(ServiceLocationClaim)
        .filter(
            ServiceLocationClaim.service_location_id == location_id,
            ServiceLocationClaim.service_tenant_id == service_tenant_id,
            ServiceLocationClaim.claim_status.in_(["pending", "approved"]),
        )
        .first()
    )
    if existing_for_tenant:
        raise HTTPException(status_code=409, detail="Nárok pro tento servis už existuje.")

    if ip_hash:
        fraud_flags["ip_hash"] = ip_hash
    if user_agent_hash:
        fraud_flags["user_agent_hash"] = user_agent_hash

    claim = ServiceLocationClaim(
        service_location_id=location_id,
        service_tenant_id=service_tenant_id,
        claim_status="pending",
        claim_method=claim_method,
        ico=(ico or "").strip() or None,
        dic=(dic or "").strip() or None,
        business_name=(business_name or "").strip() or None,
        submitted_by_user_id=submitted_by_user_id,
        fraud_flags_json=json.dumps(fraud_flags, ensure_ascii=False) if fraud_flags else None,
        audit_hash=_audit_hash(str(location_id), str(service_tenant_id), ip_hash or "", user_agent_hash or ""),
    )
    db.add(claim)
    db.flush()

    write_global_audit_log(
        db,
        entity_type="service_location_claim",
        entity_id=int(claim.id),
        action="claim_submitted",
        actor_user_id=submitted_by_user_id,
        tenant_id=service_tenant_id,
        metadata={"service_location_id": location_id, "claim_method": claim_method},
    )
    db.commit()
    db.refresh(claim)
    return claim


def approve_service_location_claim(
    db: Session,
    *,
    claim_id: int,
    admin_user_id: int,
) -> ServiceLocationClaim:
    claim = db.query(ServiceLocationClaim).filter(ServiceLocationClaim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Nárok nenalezen.")
    if claim.claim_status != "pending":
        raise HTTPException(status_code=409, detail="Nárok nelze schválit.")

    location = db.query(ServiceLocation).filter(ServiceLocation.id == claim.service_location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Servisní místo nenalezeno.")

    if location.verification_status in PROTECTED_VERIFICATION and location.linked_service_tenant_id:
        if int(location.linked_service_tenant_id) != int(claim.service_tenant_id):
            raise HTTPException(status_code=409, detail="Místo je již ověřené jiným servisem.")

    now = datetime.utcnow()
    before = {"verification_status": location.verification_status, "linked_service_tenant_id": location.linked_service_tenant_id}
    claim.claim_status = "approved"
    claim.approved_by_admin_id = admin_user_id
    claim.approved_at = now
    location.verification_status = VERIFICATION_VERIFIED
    location.linked_service_tenant_id = claim.service_tenant_id
    location.last_verified_at = now
    location.source_type = "verified_service"
    location.updated_at = now

    write_global_audit_log(
        db,
        entity_type="service_location_claim",
        entity_id=int(claim.id),
        action="claim_approved",
        actor_user_id=admin_user_id,
        tenant_id=int(claim.service_tenant_id),
        before_json=before,
        after_json={"verification_status": location.verification_status, "linked_service_tenant_id": location.linked_service_tenant_id},
    )
    db.commit()
    db.refresh(claim)
    return claim


def reject_service_location_claim(
    db: Session,
    *,
    claim_id: int,
    admin_user_id: int,
) -> ServiceLocationClaim:
    claim = db.query(ServiceLocationClaim).filter(ServiceLocationClaim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Nárok nenalezen.")
    if claim.claim_status != "pending":
        raise HTTPException(status_code=409, detail="Nárok nelze zamítnout.")

    claim.claim_status = "rejected"
    claim.approved_by_admin_id = admin_user_id
    claim.approved_at = datetime.utcnow()

    write_global_audit_log(
        db,
        entity_type="service_location_claim",
        entity_id=int(claim.id),
        action="claim_rejected",
        actor_user_id=admin_user_id,
        tenant_id=int(claim.service_tenant_id),
    )
    db.commit()
    db.refresh(claim)
    return claim
