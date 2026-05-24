from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Reminder, ServiceCustomerLink, Tenant, Vehicle, VehicleOwnership
from src.modules.vehicle_hub.routers_v1 import reminders as reminders_router
from src.modules.vehicle_hub.routers_v1 import service_workspace as workspace_router
from src.modules.vehicle_hub.routers_v1.schemas import ReminderUpdateV1


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "reminder_completion_rules.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_context(db_session):
    tenant = Tenant(name="Reminder Rules Tenant", license_key="reminder-rules-tenant-key")
    db_session.add(tenant)
    db_session.flush()

    user = Customer(
        tenant_id=tenant.id,
        email="rules-user@example.com",
        password_hash="hash",
        role="user",
        name="Rules User",
    )
    service = Customer(
        tenant_id=tenant.id,
        email="rules-service@example.com",
        password_hash="hash",
        role="service",
        name="Rules Service",
    )
    db_session.add_all([user, service])
    db_session.flush()

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=user.email,
        nickname="Reminder Rules Car",
        brand="Skoda",
        model="Superb",
        vin="TMBJF73T2B9044629",
        plate="1AA1111",
        stk_valid_until=date.today() + timedelta(days=90),
    )
    db_session.add(vehicle)
    db_session.flush()

    db_session.add(
        VehicleOwnership(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            customer_id=user.id,
            ownership_type="owner",
            is_primary=True,
            is_active=True,
            assigned_by_customer_id=user.id,
            assigned_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db_session.add(
        ServiceCustomerLink(
            service_tenant_id=tenant.id,
            service_customer_id=service.id,
            customer_tenant_id=tenant.id,
            customer_id=user.id,
            status="active",
            note="linked for reminder rules",
        )
    )
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(service)
    db_session.refresh(vehicle)
    return tenant, user, service, vehicle


def test_manual_one_off_reminder_can_be_completed_and_resets_notification_marker(db_session) -> None:
    _, user, _, vehicle = _seed_context(db_session)
    reminder = Reminder(
        tenant_id=user.tenant_id,
        customer_id=user.id,
        vehicle_id=vehicle.id,
        type="SERVIS",
        text="Jednorázová ruční připomínka",
        due_date=date.today() + timedelta(days=3),
        last_notified_at=datetime.utcnow(),
        is_manual=True,
        is_completed=False,
    )
    db_session.add(reminder)
    db_session.commit()
    db_session.refresh(reminder)

    updated = reminders_router.update_reminder(
        reminder_id=reminder.id,
        reminder_update=ReminderUpdateV1(is_completed=True),
        current_user=user,
        db=db_session,
    )

    db_session.refresh(reminder)
    assert updated.is_completed is True
    assert updated.is_recurring is False
    assert reminder.is_completed is True
    assert reminder.last_notified_at is None


def test_recurring_reminder_cannot_be_completed_via_customer_update(db_session) -> None:
    """Řada s recurrence_group_id nesmí jít „dokončit“ jedním přepnutím u majitele."""
    _, user, _, vehicle = _seed_context(db_session)

    reminder = Reminder(
        tenant_id=user.tenant_id,
        customer_id=user.id,
        vehicle_id=vehicle.id,
        type="SERVIS",
        text="Opakovaná kontrola servisu",
        due_date=date.today() + timedelta(days=5),
        is_manual=True,
        is_completed=False,
        recurrence_group_id="series-customer-rules",
        recurrence_index=1,
        repeat_interval_days=30,
    )
    db_session.add(reminder)
    db_session.commit()
    db_session.refresh(reminder)

    with pytest.raises(reminders_router.HTTPException) as exc:
        reminders_router.update_reminder(
            reminder_id=reminder.id,
            reminder_update=ReminderUpdateV1(is_completed=True),
            current_user=user,
            db=db_session,
        )

    assert exc.value.status_code == 422
    assert "nelze uzavřít jednorázovým přepnutím" in str(exc.value.detail)


def test_recurring_reminder_cannot_be_completed_via_service_workspace_update(db_session) -> None:
    _, user, service, vehicle = _seed_context(db_session)
    reminder = Reminder(
        tenant_id=user.tenant_id,
        customer_id=user.id,
        vehicle_id=vehicle.id,
        type="SERVIS",
        text="Servisní opakovaná připomínka",
        due_date=date.today() + timedelta(days=7),
        is_manual=True,
        is_completed=False,
        recurrence_group_id="series-123",
        recurrence_index=1,
        repeat_interval_days=30,
    )
    db_session.add(reminder)
    db_session.commit()
    db_session.refresh(reminder)

    with pytest.raises(workspace_router.HTTPException) as exc:
        workspace_router.update_service_workspace_reminder(
            reminder_id=reminder.id,
            payload=workspace_router.ServiceWorkspaceReminderUpdateRequest(is_completed=True),
            current_user=service,
            db=db_session,
        )

    assert exc.value.status_code == 422
    assert "nelze uzavřít jednorázovým přepnutím" in str(exc.value.detail)
