"""
Jednotkové testy pomocných funkcí Comgate integrace.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import (
    License,
    LicensePaymentTransaction,
    LicenseSubscription,
    PaymentEvent,
    Tenant,
)
from src.modules.vehicle_hub.routers_v1 import license_status


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_tenant_with_license(db, *, tenant_id: int = 1, plan: str = "basic") -> None:
    tenant = Tenant(id=tenant_id, name=f"Tenant {tenant_id}", license_key=f"TEST-{tenant_id}")
    db.add(tenant)
    db.flush()

    limits = {"free": 1, "basic": 5, "premium": 0}
    db.add(
        License(
            tenant_id=tenant_id,
            plan=plan,
            status="active",
            vehicles_limit=limits.get(plan, 1),
            valid_from=datetime.utcnow(),
            valid_to=None,
            vin_decode_enabled=(plan == "premium"),
            ares_enabled=True,
            reminders_enabled=True,
        )
    )
    db.commit()


def test_comgate_ref_id_roundtrip_basic():
    ref_id = license_status._build_comgate_ref_id(12345, "basic")
    assert len(ref_id) == 17
    assert ref_id.startswith("L")

    parsed = license_status._parse_comgate_ref_id(ref_id)
    assert parsed == (12345, "basic", "monthly")


def test_comgate_ref_id_roundtrip_premium_yearly():
    ref_id = license_status._build_comgate_ref_id(987654, "premium", "yearly")
    parsed = license_status._parse_comgate_ref_id(ref_id)
    assert parsed == (987654, "premium", "yearly")


def test_comgate_ref_id_old_format_defaults_to_monthly():
    ref_id_new = license_status._build_comgate_ref_id(42, "basic", "yearly")
    # Legacy formát neobsahuje billing period (odebereme period znak).
    ref_id_old = ref_id_new[:8] + ref_id_new[9:]
    parsed = license_status._parse_comgate_ref_id(ref_id_old)
    assert parsed == (42, "basic", "monthly")


def test_parse_comgate_response_text_decodes_values():
    raw = "code=0&message=OK&transId=ABC123&redirect=https%3A%2F%2Fpayments.example%2Fgo"
    parsed = license_status._parse_comgate_response_text(raw)
    assert parsed["code"] == "0"
    assert parsed["message"] == "OK"
    assert parsed["transId"] == "ABC123"
    assert parsed["redirect"] == "https://payments.example/go"


def test_load_comgate_config_reports_configured(monkeypatch):
    monkeypatch.setattr(license_status, "load_runtime_settings", lambda: {})
    monkeypatch.setenv("COMGATE_ENABLED", "1")
    monkeypatch.setenv("COMGATE_MERCHANT", "MERCHANT123")
    monkeypatch.setenv("COMGATE_SECRET", "SECRET123")
    monkeypatch.setenv("COMGATE_PRICE_BASIC_HALERS", "29900")
    monkeypatch.setenv("COMGATE_PRICE_PREMIUM_HALERS", "59900")
    monkeypatch.delenv("COMGATE_PRICE_BASIC_YEARLY_HALERS", raising=False)
    monkeypatch.delenv("COMGATE_PRICE_PREMIUM_YEARLY_HALERS", raising=False)

    cfg = license_status._load_comgate_config()
    assert cfg["enabled"] is True
    assert cfg["configured"] is True
    assert cfg["plans"]["basic"]["monthly"] == 29900
    assert cfg["plans"]["premium"]["monthly"] == 59900
    # Roční cena se bez explicitního override nastaví na 10x měsíční.
    assert cfg["plans"]["basic"]["yearly"] == 299000
    assert cfg["plans"]["premium"]["yearly"] == 599000


def test_load_comgate_config_defaults_to_pricing(monkeypatch):
    monkeypatch.setattr(license_status, "load_runtime_settings", lambda: {})
    monkeypatch.delenv("COMGATE_PRICE_BASIC_HALERS", raising=False)
    monkeypatch.delenv("COMGATE_PRICE_PREMIUM_HALERS", raising=False)
    monkeypatch.delenv("COMGATE_PRICE_BASIC_YEARLY_HALERS", raising=False)
    monkeypatch.delenv("COMGATE_PRICE_PREMIUM_YEARLY_HALERS", raising=False)

    cfg = license_status._load_comgate_config()
    assert cfg["plans"]["basic"]["monthly"] == 9900
    assert cfg["plans"]["premium"]["monthly"] == 29900
    assert cfg["plans"]["basic"]["yearly"] == 99000
    assert cfg["plans"]["premium"]["yearly"] == 299000


def test_load_comgate_config_includes_test_one_time_fallback_flag(monkeypatch):
    monkeypatch.setattr(license_status, "load_runtime_settings", lambda: {})
    monkeypatch.setenv("COMGATE_TEST_ONE_TIME_FALLBACK", "1")
    cfg = license_status._load_comgate_config()
    assert cfg["test_one_time_fallback"] is True


def test_detects_recurring_not_enabled_message():
    assert license_status._is_comgate_recurring_not_enabled_message("Recurrent payments are not enabled for you")
    assert not license_status._is_comgate_recurring_not_enabled_message("OK")


def test_resolve_plan_from_status_payload_prefers_refid():
    ref_id = license_status._build_comgate_ref_id(42, "basic")
    payload = {"refId": ref_id, "label": "Správa vozidel PREMIUM"}
    assert license_status._resolve_plan_from_status_payload(payload) == "basic"


def test_resolve_billing_period_from_status_payload_prefers_refid():
    ref_id = license_status._build_comgate_ref_id(77, "premium", "yearly")
    payload = {"refId": ref_id, "label": "Správa vozidel PREMIUM MĚSÍČNĚ"}
    assert license_status._resolve_billing_period_from_status_payload(payload) == "yearly"


def test_add_billing_period_monthly_handles_month_end():
    start_at = datetime(2026, 1, 31, 12, 0, 0)
    result = license_status._add_billing_period(start_at, "monthly")
    assert result == datetime(2026, 2, 28, 12, 0, 0)


def test_add_billing_period_yearly_handles_leap_day():
    start_at = datetime(2024, 2, 29, 9, 30, 0)
    result = license_status._add_billing_period(start_at, "yearly")
    assert result == datetime(2025, 2, 28, 9, 30, 0)


def test_subscription_schema_guard_is_non_destructive(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        monkeypatch.setattr(license_status, "_SCHEMA_READY", False)
        ok = license_status._ensure_subscription_schema(db, strict=False)
        assert ok is False
        with pytest.raises(Exception):
            license_status._ensure_subscription_schema(db, strict=True)
    finally:
        db.close()
        engine.dispose()


def test_trans_id_idempotency_guard(db_session, monkeypatch):
    monkeypatch.setattr(license_status, "_SCHEMA_READY", False)
    _seed_tenant_with_license(db_session, tenant_id=21, plan="basic")

    assert license_status._is_trans_already_paid(db_session, "TRANS-1") is False
    license_status._record_payment_transaction(
        db_session,
        payment_type="initial",
        tenant_id=21,
        provider="comgate",
        trans_id="TRANS-1",
        ref_id="REF-1",
        plan="basic",
        billing_period="monthly",
        amount_halers=9900,
        currency="CZK",
        event_type="checkout_created",
        provider_status="PENDING",
        payload={"status": "PENDING"},
    )
    db_session.commit()
    assert license_status._is_trans_already_paid(db_session, "TRANS-1") is False

    license_status._record_payment_transaction(
        db_session,
        payment_type="initial",
        tenant_id=21,
        provider="comgate",
        trans_id="TRANS-1",
        ref_id="REF-1",
        plan="basic",
        billing_period="monthly",
        amount_halers=9900,
        currency="CZK",
        event_type="paid_confirmed",
        provider_status="PAID",
        payload={"status": "PAID"},
    )
    db_session.commit()
    assert license_status._is_trans_already_paid(db_session, "TRANS-1") is True


def test_status_transition_cancel_at_period_end_to_canceled_free(db_session, monkeypatch):
    monkeypatch.setattr(license_status, "_SCHEMA_READY", False)
    monkeypatch.setattr(
        license_status,
        "_send_subscription_notification",
        lambda *args, **kwargs: {"email_sent": 0, "push_sent": 0},
    )
    monkeypatch.setattr(
        license_status,
        "_load_comgate_config",
        lambda: {
            "configured": True,
            "merchant": "M",
            "secret": "S",
            "test_mode": True,
            "currency": "CZK",
            "status_url": "https://example.invalid/status",
            "plans": {
                "basic": {"monthly": 9900, "yearly": 99000},
                "premium": {"monthly": 29900, "yearly": 299000},
            },
        },
    )
    monkeypatch.setattr(
        license_status,
        "_load_subscription_runtime_config",
        lambda: {"recurring_url": "https://example.invalid/recurring", "grace_days": 7, "notify_days": []},
    )

    _seed_tenant_with_license(db_session, tenant_id=31, plan="basic")
    db_session.add(
        LicenseSubscription(
            tenant_id=31,
            provider="comgate",
            status="cancel_at_period_end",
            plan_current="basic",
            billing_period="monthly",
            auto_renew_enabled=False,
            pending_plan_change="free",
            current_period_start=datetime.utcnow() - timedelta(days=30),
            current_period_end=datetime.utcnow() - timedelta(minutes=1),
            next_charge_at=None,
        )
    )
    db_session.commit()

    summary = license_status.process_license_subscription_jobs(db_session)
    assert summary["cancel_finalized"] == 1

    subscription = (
        db_session.query(LicenseSubscription)
        .filter(LicenseSubscription.tenant_id == 31)
        .first()
    )
    license_obj = db_session.query(License).filter(License.tenant_id == 31).first()

    assert subscription is not None
    assert subscription.status == "canceled"
    assert subscription.plan_current == "free"
    assert subscription.auto_renew_enabled is False
    assert license_obj is not None
    assert license_obj.plan == "free"


def test_status_transition_active_to_grace_then_downgrade_free(db_session, monkeypatch):
    monkeypatch.setattr(license_status, "_SCHEMA_READY", False)
    monkeypatch.setattr(
        license_status,
        "_send_subscription_notification",
        lambda *args, **kwargs: {"email_sent": 0, "push_sent": 0},
    )
    monkeypatch.setattr(
        license_status,
        "_load_comgate_config",
        lambda: {
            "configured": True,
            "merchant": "M",
            "secret": "S",
            "test_mode": True,
            "currency": "CZK",
            "status_url": "https://example.invalid/status",
            "plans": {
                "basic": {"monthly": 9900, "yearly": 99000},
                "premium": {"monthly": 29900, "yearly": 299000},
            },
        },
    )
    monkeypatch.setattr(
        license_status,
        "_load_subscription_runtime_config",
        lambda: {"recurring_url": "https://example.invalid/recurring", "grace_days": 7, "notify_days": []},
    )

    _seed_tenant_with_license(db_session, tenant_id=41, plan="basic")
    db_session.add(
        LicenseSubscription(
            tenant_id=41,
            provider="comgate",
            status="active",
            plan_current="basic",
            billing_period="monthly",
            auto_renew_enabled=True,
            init_recurring_id=None,
            current_period_start=datetime.utcnow() - timedelta(days=30),
            current_period_end=datetime.utcnow() - timedelta(minutes=2),
            next_charge_at=datetime.utcnow() - timedelta(minutes=1),
        )
    )
    db_session.commit()

    first_cycle = license_status.process_license_subscription_jobs(db_session)
    assert first_cycle["renewal_failed"] == 1

    subscription = (
        db_session.query(LicenseSubscription)
        .filter(LicenseSubscription.tenant_id == 41)
        .first()
    )
    assert subscription is not None
    assert subscription.status == "grace"
    assert subscription.grace_until is not None

    subscription.grace_until = datetime.utcnow() - timedelta(minutes=1)
    db_session.add(subscription)
    db_session.commit()

    second_cycle = license_status.process_license_subscription_jobs(db_session)
    assert second_cycle["downgraded_free"] == 1

    db_session.refresh(subscription)
    license_obj = db_session.query(License).filter(License.tenant_id == 41).first()
    assert subscription.status == "canceled"
    assert subscription.plan_current == "free"
    assert license_obj is not None
    assert license_obj.plan == "free"


def test_activate_legacy_manual_subscription_from_paid_payment(db_session, monkeypatch):
    monkeypatch.setattr(license_status, "_SCHEMA_READY", False)
    _seed_tenant_with_license(db_session, tenant_id=51, plan="free")

    subscription = license_status._activate_legacy_manual_subscription_from_paid_payment(
        db_session,
        tenant_id=51,
        plan="basic",
        billing_period="monthly",
        trans_id="LEGACY-TRANS-1",
    )

    license_obj = db_session.query(License).filter(License.tenant_id == 51).first()
    assert license_obj is not None
    assert license_obj.plan == "basic"
    assert subscription.status == "legacy_manual"
    assert subscription.auto_renew_enabled is False
    assert subscription.init_recurring_id is None
    assert subscription.next_charge_at is None


def test_remaining_period_ratio_bounds():
    now = datetime(2026, 3, 8, 12, 0, 0)
    start = now - timedelta(days=10)
    end = now + timedelta(days=20)
    ratio = license_status._remaining_period_ratio(start, end, now=now)
    assert ratio == pytest.approx(20 / 30, rel=1e-6)

    assert license_status._remaining_period_ratio(start, end, now=end + timedelta(seconds=1)) == 0.0
    assert license_status._remaining_period_ratio(start, end, now=start - timedelta(seconds=1)) == 1.0


def test_build_legacy_checkout_quote_downgrade_creates_credit(db_session, monkeypatch):
    monkeypatch.setattr(license_status, "_SCHEMA_READY", False)
    _seed_tenant_with_license(db_session, tenant_id=61, plan="premium")

    now = datetime(2026, 3, 8, 12, 0, 0)
    subscription = LicenseSubscription(
        tenant_id=61,
        provider="comgate",
        status="legacy_manual",
        plan_current="premium",
        billing_period="monthly",
        auto_renew_enabled=False,
        current_period_start=now - timedelta(days=10),
        current_period_end=now + timedelta(days=20),
        credit_balance_halers=0,
    )
    db_session.add(subscription)
    db_session.commit()

    cfg = {
        "plans": {
            "basic": {"monthly": 9900, "yearly": 99000},
            "premium": {"monthly": 29900, "yearly": 299000},
        }
    }
    quote = license_status._build_legacy_checkout_quote(
        cfg=cfg,
        subscription=subscription,
        target_plan="basic",
        billing_period="monthly",
        now=now,
    )

    assert quote["kind"] == "legacy_proration_change"
    assert quote["base_amount_halers"] < 0
    assert quote["charge_amount_halers"] == 0
    assert quote["balance_after_halers"] > 0


def test_build_legacy_checkout_quote_upgrade_uses_existing_credit(db_session, monkeypatch):
    monkeypatch.setattr(license_status, "_SCHEMA_READY", False)
    _seed_tenant_with_license(db_session, tenant_id=62, plan="basic")

    now = datetime(2026, 3, 8, 12, 0, 0)
    subscription = LicenseSubscription(
        tenant_id=62,
        provider="comgate",
        status="legacy_manual",
        plan_current="basic",
        billing_period="monthly",
        auto_renew_enabled=False,
        current_period_start=now - timedelta(days=10),
        current_period_end=now + timedelta(days=20),
        credit_balance_halers=10000,  # 100 Kč kredit
    )
    db_session.add(subscription)
    db_session.commit()

    cfg = {
        "plans": {
            "basic": {"monthly": 9900, "yearly": 99000},
            "premium": {"monthly": 29900, "yearly": 299000},
        }
    }
    quote = license_status._build_legacy_checkout_quote(
        cfg=cfg,
        subscription=subscription,
        target_plan="premium",
        billing_period="monthly",
        now=now,
    )

    assert quote["kind"] == "legacy_proration_change"
    assert quote["base_amount_halers"] > 0
    assert quote["charge_amount_halers"] == max(0, quote["base_amount_halers"] - 10000)
    assert quote["balance_after_halers"] >= 0


def test_sanitize_comgate_payload_removes_sensitive_fields():
    payload = {
        "merchant": "M123",
        "secret": "super-secret",
        "transId": "TX-1",
        "status": "PAID",
        "cardNumber": "411111******1111",
        "cardValid": "12/30",
        "payer_name": "John Doe",
        "phone": "+420123456789",
        "price": "9900",
        "curr": "CZK",
    }
    sanitized = license_status.sanitize_comgate_payload(payload)
    assert sanitized["merchant"] == "M123"
    assert sanitized["transId"] == "TX-1"
    assert sanitized["status"] == "PAID"
    assert "secret" not in sanitized
    assert "cardNumber" not in sanitized
    assert "cardValid" not in sanitized
    assert "payer_name" not in sanitized
    assert "phone" not in sanitized


def test_activate_subscription_without_init_recurring_id_keeps_recurring_blocked(db_session, monkeypatch):
    monkeypatch.setattr(license_status, "_SCHEMA_READY", True)
    _seed_tenant_with_license(db_session, tenant_id=71, plan="free")
    subscription = license_status._activate_subscription_from_paid_payment(
        db_session,
        tenant_id=71,
        plan="basic",
        billing_period="monthly",
        trans_id="INIT-71",
        init_recurring_id=None,
    )
    assert subscription.status == "active"
    assert subscription.auto_renew_enabled is False
    assert subscription.recurring_ready is False
    assert subscription.recurring_block_reason == "missing_init_recurring_id"
    assert subscription.provider_init_transaction_id == "INIT-71"


def test_activate_subscription_with_init_recurring_id_marks_ready(db_session, monkeypatch):
    monkeypatch.setattr(license_status, "_SCHEMA_READY", True)
    _seed_tenant_with_license(db_session, tenant_id=72, plan="free")
    subscription = license_status._activate_subscription_from_paid_payment(
        db_session,
        tenant_id=72,
        plan="basic",
        billing_period="monthly",
        trans_id="INIT-72",
        init_recurring_id="REC-72",
    )
    assert subscription.auto_renew_enabled is True
    assert subscription.recurring_ready is True
    assert subscription.init_recurring_id == "REC-72"


def test_recurring_charge_without_init_recurring_id_is_rejected(db_session, monkeypatch):
    monkeypatch.setattr(license_status, "_SCHEMA_READY", True)
    _seed_tenant_with_license(db_session, tenant_id=73, plan="basic")
    subscription = LicenseSubscription(
        tenant_id=73,
        provider="comgate",
        status="active",
        plan_current="basic",
        billing_period="monthly",
        auto_renew_enabled=True,
        current_period_start=datetime.utcnow() - timedelta(days=30),
        current_period_end=datetime.utcnow(),
        next_charge_at=datetime.utcnow() - timedelta(minutes=1),
        recurring_ready=False,
    )
    db_session.add(subscription)
    db_session.commit()

    result = license_status._charge_subscription_recurring(
        db=db_session,
        cfg={"merchant": "M", "secret": "S", "currency": "CZK", "test_mode": True},
        runtime_cfg={"recurring_url": "https://example.invalid/recurring", "recurring_enabled": True},
        subscription=subscription,
        tenant_id=73,
        plan="basic",
        billing_period="monthly",
    )
    assert result["ok"] is False
    assert result["reason"] == "missing_init_recurring_id"


def test_recurring_worker_creates_recurring_payment_row(db_session, monkeypatch):
    monkeypatch.setattr(license_status, "_SCHEMA_READY", True)
    monkeypatch.setattr(
        license_status,
        "_send_subscription_notification",
        lambda *args, **kwargs: {"email_sent": 0, "push_sent": 0},
    )
    monkeypatch.setattr(
        license_status,
        "_load_comgate_config",
        lambda: {
            "configured": True,
            "merchant": "M",
            "secret": "S",
            "test_mode": True,
            "currency": "CZK",
            "status_url": "https://example.invalid/status",
            "plans": {
                "basic": {"monthly": 9900, "yearly": 99000},
                "premium": {"monthly": 29900, "yearly": 299000},
            },
        },
    )
    monkeypatch.setattr(
        license_status,
        "_load_subscription_runtime_config",
        lambda: {
            "recurring_url": "https://example.invalid/recurring",
            "recurring_enabled": True,
            "grace_days": 7,
            "notify_days": [],
        },
    )

    def fake_post(url, payload):
        if "recurring" in url:
            return {"code": "0", "message": "OK", "transId": "REN-74"}
        if "status" in url:
            return {"code": "0", "status": "PAID", "price": "9900", "refId": payload.get("transId", "REN-74")}
        raise AssertionError(url)

    monkeypatch.setattr(license_status, "_post_comgate", fake_post)

    _seed_tenant_with_license(db_session, tenant_id=74, plan="basic")
    subscription = LicenseSubscription(
        tenant_id=74,
        provider="comgate",
        status="active",
        plan_current="basic",
        billing_period="monthly",
        auto_renew_enabled=True,
        init_recurring_id="REC-74",
        provider_init_transaction_id="INIT-74",
        recurring_ready=True,
        current_period_start=datetime.utcnow() - timedelta(days=30),
        current_period_end=datetime.utcnow() - timedelta(minutes=1),
        next_charge_at=datetime.utcnow() - timedelta(minutes=1),
    )
    db_session.add(subscription)
    db_session.commit()

    summary = license_status.process_license_subscription_jobs(db_session)
    assert summary["renewal_success"] == 1
    tx = db_session.query(LicensePaymentTransaction).filter(LicensePaymentTransaction.trans_id == "REN-74").first()
    assert tx is not None
    assert tx.payment_type == "recurring"
    assert tx.event_type == "renewal_paid"


def test_duplicate_callback_does_not_extend_period_twice(db_session, monkeypatch):
    monkeypatch.setattr(license_status, "_SCHEMA_READY", True)
    monkeypatch.setattr(license_status, "_send_subscription_notification", lambda *args, **kwargs: {"email_sent": 0, "push_sent": 0})
    monkeypatch.setattr(license_status, "load_runtime_settings", lambda: {})
    monkeypatch.setattr(
        license_status,
        "_load_comgate_config",
        lambda: {
            "configured": True,
            "merchant": "M",
            "secret": "S",
            "test_mode": True,
            "test_one_time_fallback": False,
            "currency": "CZK",
            "status_url": "https://example.invalid/status",
            "plans": {
                "basic": {"monthly": 9900, "yearly": 99000},
                "premium": {"monthly": 29900, "yearly": 299000},
            },
        },
    )
    monkeypatch.setattr(
        license_status,
        "_post_comgate",
        lambda url, payload: {"code": "0", "status": "PAID", "price": "9900", "refId": payload.get("refId") or ref_id, "curr": "CZK"},
    )

    _seed_tenant_with_license(db_session, tenant_id=75, plan="free")
    ref_id = license_status._build_comgate_ref_id(75, "basic", "monthly")
    license_status._record_payment_transaction(
        db_session,
        subscription_id=None,
        tenant_id=75,
        provider="comgate",
        trans_id="INIT-75",
        ref_id=ref_id,
        payment_type="initial",
        plan="basic",
        billing_period="monthly",
        amount_halers=9900,
        currency="CZK",
        event_type="checkout_created",
        provider_status="PENDING",
        payload={"status": "PENDING"},
    )
    db_session.commit()

    app = FastAPI()
    app.include_router(license_status.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    first = client.get("/api/v1/license/comgate/result", params={"transId": "INIT-75", "refId": ref_id})
    second = client.get("/api/v1/license/comgate/result", params={"transId": "INIT-75", "refId": ref_id})
    assert first.status_code == 200
    assert second.text == "OK_DUPLICATE"

    subscription = db_session.query(LicenseSubscription).filter(LicenseSubscription.tenant_id == 75).first()
    assert subscription is not None
    first_period_end = subscription.current_period_end
    assert first_period_end is not None
    refreshed = db_session.query(LicenseSubscription).filter(LicenseSubscription.tenant_id == 75).first()
    assert refreshed.current_period_end == first_period_end
    duplicate_events = (
        db_session.query(PaymentEvent)
        .filter(PaymentEvent.provider_transaction_id == "INIT-75", PaymentEvent.processing_status == "ignored_duplicate")
        .count()
    )
    assert duplicate_events == 1
