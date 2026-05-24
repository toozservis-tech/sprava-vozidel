"""Kvóty SERVICE FREE vs FULL — přímé volání licenční vrstvy (SQLite in-memory)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.licensing.service import (
    LicenseError,
    activate_initial_user_trial_on_first_login,
    assert_service_customer_link_quota,
    assert_feature,
    assert_service_invoice_monthly_quota,
    assert_service_monthly_service_record_quota,
    assert_service_vehicle_link_quota,
    assert_vehicle_quota,
    get_license_status,
    upgrade_license_plan,
)
import src.modules.licensing.service as licensing_service
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    GlobalAuditLog,
    License,
    ServiceCustomerLink,
    ServiceInvoice,
    ServiceRecord,
    Tenant,
    Vehicle,
    VehicleServiceLink,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_service_tenant_free(db, *, key_suffix: str = "a") -> tuple[Tenant, Customer]:
    t = Tenant(
        name="SVC",
        license_key=f"lic-sf-{key_suffix}",
        workspace_route_kind="service",
        workspace_slug=f"wsvc-{key_suffix}"[:160],
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    svc = Customer(
        tenant_id=t.id,
        email=f"svc.sf.{key_suffix}@example.com",
        password_hash="x",
        name="Servis",
        role="service",
    )
    db.add(svc)
    db.commit()
    db.refresh(svc)
    lic = License(
        tenant_id=t.id,
        plan="service_free",
        status="active",
        vehicles_limit=1,
        valid_from=datetime.utcnow(),
    )
    db.add(lic)
    db.commit()
    return t, svc


def _seed_registered_user_free(db, *, suffix: str = "trial") -> tuple[Tenant, Customer, License]:
    t = Tenant(
        name=f"Trial {suffix}",
        license_key=f"lic-trial-{suffix}",
        workspace_route_kind="user",
        workspace_slug=f"trial-{suffix}"[:160],
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    verified_at = datetime(2026, 5, 22, 8, 0, 0)
    u = Customer(
        tenant_id=t.id,
        email=f"{suffix}@example.com",
        password_hash="x",
        name="Trial",
        role="user",
        account_status="active",
        email_verified_at=verified_at,
        email_verification_sent_at=verified_at - timedelta(minutes=5),
        registration_ip="127.0.0.1",
        registration_user_agent="pytest",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    lic = License(
        tenant_id=t.id,
        plan="free",
        status="active",
        vehicles_limit=1,
        valid_from=datetime.utcnow(),
    )
    db.add(lic)
    db.commit()
    db.refresh(lic)
    return t, u, lic


def test_service_free_customer_link_quota_fourth_blocks(db_session):
    db = db_session
    t, svc = _seed_service_tenant_free(db, key_suffix="cl")
    for i in range(3):
        u = Customer(
            tenant_id=t.id,
            email=f"u{i}-cl@ex.com",
            password_hash="x",
            name=f"U{i}",
            role="user",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        db.add(
            ServiceCustomerLink(
                service_tenant_id=t.id,
                service_customer_id=svc.id,
                customer_tenant_id=t.id,
                customer_id=u.id,
                status="active",
            )
        )
    db.commit()

    with pytest.raises(LicenseError) as ei:
        assert_service_customer_link_quota(db, service_customer_id=int(svc.id))
    assert ei.value.code == "SERVICE_FREE_CUSTOMER_LINKS_EXCEEDED"


def test_service_free_vehicle_link_quota_blocks(db_session):
    db = db_session
    t, svc = _seed_service_tenant_free(db, key_suffix="vl")
    u = Customer(tenant_id=t.id, email="one-vl@ex.com", password_hash="x", name="O", role="user")
    db.add(u)
    db.commit()
    db.refresh(u)
    for i in range(3):
        vin = ("1HGBH41JX" + f"{i:08d}")[:17]
        assert len(vin) == 17
        v = Vehicle(
            tenant_id=t.id,
            user_email=u.email,
            nickname=f"V{i}",
            vin=vin,
        )
        db.add(v)
        db.flush()
        db.add(
            VehicleServiceLink(
                tenant_id=t.id,
                service_customer_id=svc.id,
                owner_customer_id=u.id,
                vehicle_id=v.id,
                status="approved",
                source_type="test",
                approved_at=datetime.utcnow(),
                approved_by_customer_id=u.id,
            )
        )
    db.commit()

    with pytest.raises(LicenseError) as ei:
        assert_service_vehicle_link_quota(db, service_customer_id=int(svc.id))
    assert ei.value.code == "SERVICE_FREE_VEHICLE_LINKS_EXCEEDED"


def test_service_free_invoice_monthly_quota_blocks(db_session):
    db = db_session
    t, svc = _seed_service_tenant_free(db, key_suffix="inv")
    cust = Customer(tenant_id=t.id, email="cust-inv@ex.com", password_hash="x", name="C", role="user")
    db.add(cust)
    db.commit()
    db.refresh(cust)
    v = Vehicle(tenant_id=t.id, user_email=cust.email, nickname="X", vin="TMB11111111111111")
    db.add(v)
    db.commit()
    db.refresh(v)
    for _ in range(3):
        db.add(
            ServiceInvoice(
                tenant_id=t.id,
                service_id=svc.id,
                customer_id=cust.id,
                vehicle_id=v.id,
                status="issued",
                subtotal=100.0,
                tax_total=21.0,
                total=121.0,
                issued_at=datetime.utcnow(),
            )
        )
    db.commit()

    with pytest.raises(LicenseError) as ei:
        assert_service_invoice_monthly_quota(db, service_customer_id=int(svc.id))
    assert ei.value.code == "SERVICE_FREE_MONTHLY_INVOICES_EXCEEDED"


def test_service_free_monthly_service_record_quota_blocks(db_session):
    db = db_session
    t, svc = _seed_service_tenant_free(db, key_suffix="sr")
    cust = Customer(tenant_id=t.id, email="c2-sr@ex.com", password_hash="x", name="C", role="user")
    db.add(cust)
    db.commit()
    db.refresh(cust)
    v = Vehicle(tenant_id=t.id, user_email=cust.email, nickname="Y", vin="TMB22222222222222")
    db.add(v)
    db.commit()
    db.refresh(v)
    now = datetime.utcnow()
    for i in range(3):
        db.add(
            ServiceRecord(
                tenant_id=t.id,
                vehicle_id=v.id,
                description=f"r{i}",
                created_by_service_customer_id=svc.id,
                origin="service_workspace",
                performed_at=now,
                updated_at=now,
            )
        )
    db.commit()

    with pytest.raises(LicenseError) as ei:
        assert_service_monthly_service_record_quota(db, service_customer_id=int(svc.id))
    assert ei.value.code == "SERVICE_FREE_MONTHLY_SERVICE_RECORDS_EXCEEDED"


def test_user_free_second_vehicle_quota(db_session):
    db = db_session
    t = Tenant(name="U", license_key="lic-uf", workspace_route_kind="user", workspace_slug="uslug1")
    db.add(t)
    db.commit()
    db.refresh(t)
    lic = License(tenant_id=t.id, plan="free", status="active", vehicles_limit=1, valid_from=datetime.utcnow())
    db.add(lic)
    u = Customer(tenant_id=t.id, email="owner-uf@ex.com", password_hash="x", name="O", role="user")
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(
        Vehicle(
            tenant_id=t.id,
            user_email=u.email,
            nickname="First",
            stk_valid_until=date.today(),
        )
    )
    db.commit()

    with pytest.raises(LicenseError) as ei:
        assert_vehicle_quota(db, int(t.id))
    assert ei.value.code == "LICENSE_QUOTA_EXCEEDED"


def test_first_login_activates_user_premium_trial(db_session):
    db = db_session
    t, u, lic = _seed_registered_user_free(db, suffix="first-login")

    start = datetime(2026, 5, 21, 10, 0, 0)
    trial = activate_initial_user_trial_on_first_login(db, u, license_obj=lic, now=start)
    db.commit()

    assert trial is not None
    assert trial.plan == "free"
    assert trial.trial_plan == "premium"
    assert trial.trial_source == "first_verified_login"
    assert trial.trial_started_at == start
    assert trial.trial_used_at == start
    assert trial.trial_ends_at == start + timedelta(days=30)
    status = get_license_status(db, int(t.id), u.email)
    assert status["plan"] == "free"
    assert status["effective_plan"] == "premium"
    assert status["trial_active"] is True
    assert status["trial_started_at"] == start.isoformat()
    assert status["trial_ends_at"] == (start + timedelta(days=30)).isoformat()
    assert status["is_expired_trial"] is False
    assert db.query(GlobalAuditLog).filter(GlobalAuditLog.action == "initial_trial_activated").count() == 1


def test_unverified_user_does_not_get_trial(db_session):
    db = db_session
    t, u, lic = _seed_registered_user_free(db, suffix="unverified")
    u.email_verified_at = None
    u.account_status = "pending_email_verification"
    db.commit()

    trial = activate_initial_user_trial_on_first_login(db, u, license_obj=lic, now=datetime(2026, 5, 22, 9))
    db.commit()

    assert trial is None
    db.refresh(lic)
    assert lic.trial_used_at is None
    assert get_license_status(db, int(t.id), u.email)["plan"] == "free"


def test_first_login_trial_is_used_once_and_second_login_does_not_extend(db_session):
    db = db_session
    _t, u, lic = _seed_registered_user_free(db, suffix="once")
    start = datetime(2026, 5, 22, 9, 0, 0)

    first = activate_initial_user_trial_on_first_login(db, u, license_obj=lic, now=start)
    db.commit()
    u.last_login_at = start
    db.commit()
    original_end = first.trial_ends_at

    second = activate_initial_user_trial_on_first_login(
        db,
        u,
        license_obj=lic,
        now=start + timedelta(days=1),
        previous_last_login_at=u.last_login_at,
    )
    db.commit()

    assert second is None
    db.refresh(lic)
    assert lic.trial_ends_at == original_end
    assert db.query(GlobalAuditLog).filter(GlobalAuditLog.action == "initial_trial_activated").count() == 1


def test_expired_user_trial_behaves_as_free_without_data_loss(db_session):
    db = db_session
    t, u, _lic = _seed_registered_user_free(db, suffix="expired-trial")
    start = datetime.utcnow() - timedelta(days=40)
    lic = db.query(License).filter(License.tenant_id == t.id).first()
    lic.trial_started_at = start
    lic.trial_used_at = start
    lic.trial_ends_at = datetime.utcnow() - timedelta(days=1)
    lic.trial_plan = "premium"
    lic.trial_source = "first_verified_login"
    db.add(
        lic
    )
    for i in range(2):
        db.add(
            Vehicle(
                tenant_id=t.id,
                user_email=u.email,
                nickname=f"Kept {i}",
                vin=f"TRIAL{i:012d}"[:17],
            )
        )
    db.commit()

    status = get_license_status(db, int(t.id), u.email)
    assert status["stored_plan"] == "free"
    assert status["plan"] == "free"
    assert status["effective_plan"] == "free"
    assert status["is_expired_trial"] is True
    assert status["vehicles_current"] == 2
    assert status["is_over_limit"] is True

    with pytest.raises(LicenseError) as ei:
        assert_vehicle_quota(db, int(t.id))
    assert ei.value.code == "LICENSE_QUOTA_EXCEEDED"
    assert ei.value.details["plan"] == "free"
    assert db.query(Vehicle).filter(Vehicle.tenant_id == t.id).count() == 2


def test_paid_basic_user_is_not_overwritten_by_trial(db_session):
    db = db_session
    t, u, lic = _seed_registered_user_free(db, suffix="paid-basic")
    lic.plan = "basic"
    lic.vehicles_limit = 3
    lic.valid_to = None
    db.commit()

    trial = activate_initial_user_trial_on_first_login(db, u, license_obj=lic, now=datetime(2026, 5, 22, 10))
    db.commit()

    assert trial is None
    db.refresh(lic)
    assert lic.plan == "basic"
    assert lic.trial_used_at is None
    assert get_license_status(db, int(t.id), u.email)["plan"] == "basic"


def test_paid_premium_user_is_not_overwritten_by_trial(db_session):
    db = db_session
    t, u, lic = _seed_registered_user_free(db, suffix="paid-premium")
    lic.plan = "premium"
    lic.vehicles_limit = 0
    lic.valid_to = None
    db.commit()

    trial = activate_initial_user_trial_on_first_login(db, u, license_obj=lic, now=datetime(2026, 5, 22, 10))
    db.commit()

    assert trial is None
    db.refresh(lic)
    assert lic.plan == "premium"
    assert lic.trial_used_at is None
    status = get_license_status(db, int(t.id), u.email)
    assert status["plan"] == "premium"
    assert status["effective_plan"] == "premium"


def test_lifetime_user_is_not_overwritten_by_trial(db_session):
    db = db_session
    t, u, lic = _seed_registered_user_free(db, suffix="lifetime")
    lic.plan = "lifetime"
    lic.vehicles_limit = 0
    db.commit()

    trial = activate_initial_user_trial_on_first_login(db, u, license_obj=lic, now=datetime(2026, 5, 22, 10))
    db.commit()

    assert trial is None
    db.refresh(lic)
    assert lic.plan == "lifetime"
    assert lic.trial_used_at is None
    assert get_license_status(db, int(t.id), u.email)["plan"] == "lifetime"


def test_service_and_admin_accounts_do_not_get_trial(db_session):
    db = db_session
    svc_t, svc = _seed_service_tenant_free(db, key_suffix="no-trial")
    svc.email_verified_at = datetime.utcnow()
    svc.email_verification_sent_at = datetime.utcnow()
    db.commit()
    svc_lic = db.query(License).filter(License.tenant_id == svc_t.id).first()

    assert activate_initial_user_trial_on_first_login(db, svc, license_obj=svc_lic) is None

    t, admin, admin_lic = _seed_registered_user_free(db, suffix="admin-no-trial")
    admin.role = "admin"
    db.commit()
    assert activate_initial_user_trial_on_first_login(db, admin, license_obj=admin_lic) is None
    assert get_license_status(db, int(t.id), admin.email)["plan"] == "free"


def test_old_existing_free_account_without_registration_email_flow_is_not_changed(db_session):
    db = db_session
    t, u, lic = _seed_registered_user_free(db, suffix="old-free")
    u.email_verification_sent_at = None
    u.registration_ip = None
    u.registration_user_agent = None
    db.commit()

    assert activate_initial_user_trial_on_first_login(db, u, license_obj=lic, now=datetime(2026, 5, 22, 10)) is None
    db.refresh(lic)
    assert lic.trial_used_at is None
    assert get_license_status(db, int(t.id), u.email)["plan"] == "free"


def test_backfill_function_is_not_available_for_runtime_use():
    assert not hasattr(licensing_service, "backfill_missing_initial_user_trials")


def test_feature_gating_during_and_after_trial(db_session):
    db = db_session
    t, u, lic = _seed_registered_user_free(db, suffix="feature-gate")
    start = datetime(2026, 5, 22, 10, 0, 0)
    activate_initial_user_trial_on_first_login(db, u, license_obj=lic, now=start)
    db.commit()

    status = get_license_status(db, int(t.id), u.email)
    assert status["plan"] == "free"
    assert status["effective_plan"] == "premium"
    assert_feature(db, int(t.id), "vin_decode")
    assert_feature(db, int(t.id), "documents")
    assert_feature(db, int(t.id), "reservations")

    lic.trial_ends_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    status = get_license_status(db, int(t.id), u.email)
    assert status["plan"] == "free"
    assert status["effective_plan"] == "free"
    assert status["vehicles_limit"] == 1
    assert status["trial_active"] is False
    assert status["is_expired_trial"] is True
    with pytest.raises(LicenseError):
        assert_feature(db, int(t.id), "documents")


def test_locked_feature_messages_are_user_safe(db_session):
    db = db_session
    t, _u, _lic = _seed_registered_user_free(db, suffix="locked-messages")

    with pytest.raises(LicenseError) as vin_error:
        assert_feature(db, int(t.id), "vin_decode")
    assert "Tato funkce je dostupná v licenci Premium" in str(vin_error.value.detail)
    assert "sqlite" not in str(vin_error.value.detail).lower()
    assert "no such column" not in str(vin_error.value.detail).lower()

    with pytest.raises(LicenseError) as docs_error:
        assert_feature(db, int(t.id), "documents")
    assert str(docs_error.value.detail) == "Dokumenty a PDF exporty jsou dostupné od licence Basic."

    with pytest.raises(LicenseError) as reservations_error:
        assert_feature(db, int(t.id), "reservations")
    assert str(reservations_error.value.detail) == "Objednání servisu je dostupné od licence Basic."


def test_paid_upgrade_keeps_paid_plan_after_expired_trial(db_session):
    db = db_session
    t, u, lic = _seed_registered_user_free(db, suffix="paid-after-trial")
    start = datetime.utcnow() - timedelta(days=40)
    lic.trial_started_at = start
    lic.trial_used_at = start
    lic.trial_ends_at = datetime.utcnow() - timedelta(days=1)
    lic.trial_plan = "premium"
    db.commit()

    upgrade_license_plan(db, int(t.id), "premium")
    status = get_license_status(db, int(t.id), u.email)

    lic = db.query(License).filter(License.tenant_id == int(t.id)).first()
    assert lic.valid_to is None
    assert status["plan"] == "premium"
    assert status["effective_plan"] == "premium"
    assert status["trial_active"] is False
    assert status["is_expired_trial"] is False
