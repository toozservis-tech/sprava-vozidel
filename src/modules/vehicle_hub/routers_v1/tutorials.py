"""
Interaktivní návody — pouze metadata o průběhu (bez vozidlových údajů).
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, TutorialAuditLog, UserTutorialProgress
from .auth import get_current_user

router = APIRouter(prefix="/tutorials", tags=["tutorials"])


class TutorialProgressRowOut(BaseModel):
    tutorial_id: str
    step_id: Optional[str] = None
    status: str
    last_failure_code: Optional[str] = None
    updated_at: Optional[datetime] = None


class TutorialProgressGetResponse(BaseModel):
    items: List[TutorialProgressRowOut]


class TutorialStartBody(BaseModel):
    tutorial_id: str = Field(..., min_length=1, max_length=96)
    step_id: Optional[str] = Field(default=None, max_length=160)


class TutorialStepBody(BaseModel):
    tutorial_id: str = Field(..., min_length=1, max_length=96)
    step_id: str = Field(..., min_length=1, max_length=160)
    failure_code: Optional[str] = Field(default=None, max_length=80)


class TutorialCompleteBody(BaseModel):
    tutorial_id: str = Field(..., min_length=1, max_length=96)


class TutorialSkipBody(BaseModel):
    tutorial_id: str = Field(..., min_length=1, max_length=96)


def _tenant_id(user: Customer) -> int:
    tid = getattr(user, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=403, detail="Chybí tenant účtu")
    return int(tid)


def _append_audit(
    db: Session,
    *,
    user: Customer,
    tutorial_id: str,
    step_id: Optional[str],
    status: str,
    failure_code: Optional[str],
) -> None:
    row = TutorialAuditLog(
        customer_id=user.id,
        tenant_id=_tenant_id(user),
        tutorial_id=tutorial_id[:96],
        step_id=(step_id[:160] if step_id else None),
        status=status[:48],
        failure_code=(failure_code[:80] if failure_code else None),
        created_at=datetime.utcnow(),
    )
    db.add(row)


def _upsert_progress(
    db: Session,
    *,
    user: Customer,
    tutorial_id: str,
    step_id: Optional[str],
    status: str,
    last_failure_code: Optional[str] = None,
) -> UserTutorialProgress:
    tid = _tenant_id(user)
    existing = (
        db.query(UserTutorialProgress)
        .filter(
            UserTutorialProgress.customer_id == user.id,
            UserTutorialProgress.tutorial_id == tutorial_id,
        )
        .first()
    )
    now = datetime.utcnow()
    if existing:
        existing.step_id = step_id
        existing.status = status
        existing.last_failure_code = last_failure_code
        existing.updated_at = now
        existing.tenant_id = tid
        return existing
    row = UserTutorialProgress(
        customer_id=user.id,
        tenant_id=tid,
        tutorial_id=tutorial_id[:96],
        step_id=step_id,
        status=status,
        last_failure_code=last_failure_code,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    return row


@router.get("/progress", response_model=TutorialProgressGetResponse)
def list_tutorial_progress(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(UserTutorialProgress)
        .filter(UserTutorialProgress.customer_id == current_user.id)
        .order_by(UserTutorialProgress.updated_at.desc())
        .all()
    )
    return TutorialProgressGetResponse(
        items=[
            TutorialProgressRowOut(
                tutorial_id=r.tutorial_id,
                step_id=r.step_id,
                status=r.status,
                last_failure_code=r.last_failure_code,
                updated_at=r.updated_at,
            )
            for r in rows
        ]
    )


@router.post("/progress/start")
def tutorial_progress_start(
    body: TutorialStartBody,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _upsert_progress(
        db,
        user=current_user,
        tutorial_id=body.tutorial_id.strip(),
        step_id=body.step_id.strip() if body.step_id else None,
        status="in_progress",
        last_failure_code=None,
    )
    _append_audit(
        db,
        user=current_user,
        tutorial_id=body.tutorial_id.strip(),
        step_id=body.step_id.strip() if body.step_id else None,
        status="start",
        failure_code=None,
    )
    db.commit()
    return {"ok": True}


@router.post("/progress/step")
def tutorial_progress_step(
    body: TutorialStepBody,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    failure = body.failure_code.strip() if body.failure_code else None
    _upsert_progress(
        db,
        user=current_user,
        tutorial_id=body.tutorial_id.strip(),
        step_id=body.step_id.strip(),
        status="in_progress",
        last_failure_code=failure,
    )
    _append_audit(
        db,
        user=current_user,
        tutorial_id=body.tutorial_id.strip(),
        step_id=body.step_id.strip(),
        status="failure" if failure else "step",
        failure_code=failure,
    )
    db.commit()
    return {"ok": True}


@router.post("/progress/complete")
def tutorial_progress_complete(
    body: TutorialCompleteBody,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _upsert_progress(
        db,
        user=current_user,
        tutorial_id=body.tutorial_id.strip(),
        step_id=None,
        status="completed",
        last_failure_code=None,
    )
    _append_audit(
        db,
        user=current_user,
        tutorial_id=body.tutorial_id.strip(),
        step_id=None,
        status="completed",
        failure_code=None,
    )
    db.commit()
    return {"ok": True}


@router.post("/progress/skip")
def tutorial_progress_skip(
    body: TutorialSkipBody,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _upsert_progress(
        db,
        user=current_user,
        tutorial_id=body.tutorial_id.strip(),
        step_id=None,
        status="skipped",
        last_failure_code=None,
    )
    _append_audit(
        db,
        user=current_user,
        tutorial_id=body.tutorial_id.strip(),
        step_id=None,
        status="skipped",
        failure_code=None,
    )
    db.commit()
    return {"ok": True}
