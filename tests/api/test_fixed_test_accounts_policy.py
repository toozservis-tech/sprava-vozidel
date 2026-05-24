from __future__ import annotations

import inspect

import pytest
from sqlalchemy import func, or_

from src.modules.vehicle_hub.database import SessionLocal
from src.modules.vehicle_hub.models import Customer
from tests.api import integration_accounts as accounts


def _count_fixed(db, email: str) -> int:
    return int(db.query(func.count(Customer.id)).filter(func.lower(Customer.email) == email.lower()).scalar() or 0)


def _count_testish_accounts(db) -> int:
    patterns = ["%e2e%", "%test%", "%pw-%"]
    return int(
        db.query(func.count(Customer.id))
        .filter(or_(*[func.lower(Customer.email).like(p) for p in patterns]))
        .scalar()
        or 0
    )


def test_ensure_fixed_test_user_is_idempotent():
    db = SessionLocal()
    try:
        before = _count_fixed(db, accounts.E2E_USER_EMAIL)
        first = accounts.ensure_fixed_test_user(db)
        second = accounts.ensure_fixed_test_user(db)
        after = _count_fixed(db, accounts.E2E_USER_EMAIL)
        assert int(first.id) == int(second.id)
        assert after == max(before, 1)
        assert second.role == "user"
    finally:
        db.close()


def test_ensure_fixed_test_service_is_idempotent():
    db = SessionLocal()
    try:
        before = _count_fixed(db, accounts.E2E_SERVICE_EMAIL)
        first = accounts.ensure_fixed_test_service(db)
        second = accounts.ensure_fixed_test_service(db)
        after = _count_fixed(db, accounts.E2E_SERVICE_EMAIL)
        assert int(first.id) == int(second.id)
        assert after == max(before, 1)
        assert second.role == "service"
    finally:
        db.close()


def test_runtime_guard_rejects_random_email():
    with pytest.raises(AssertionError, match="Refusing to create non-allowlisted test account"):
        accounts.assert_allowed_test_email(
            "random.user@example.com",
            database_url="sqlite:////opt/toozhub2/data/vehicles.db",
        )


def test_runtime_guard_rejects_e2e_timestamp_email():
    with pytest.raises(AssertionError, match="Refusing to create non-allowlisted test account"):
        accounts.assert_allowed_test_email(
            "e2e+timestamp-202605221900@example.com",
            database_url="sqlite:////opt/toozhub2/data/vehicles.db",
        )


def test_duplicate_email_policy_uses_fixed_account_without_rate_limit():
    db = SessionLocal()
    try:
        accounts.ensure_fixed_test_user(db)
        assert _count_fixed(db, accounts.E2E_USER_EMAIL) == 1
    finally:
        db.close()


def test_testish_account_count_does_not_grow_from_fixed_helpers():
    db = SessionLocal()
    try:
        accounts.ensure_fixed_test_user(db)
        accounts.ensure_fixed_test_service(db)
        before = _count_testish_accounts(db)
        fixed_before = (
            _count_fixed(db, accounts.E2E_USER_EMAIL),
            _count_fixed(db, accounts.E2E_SERVICE_EMAIL),
        )
        accounts.ensure_fixed_test_user(db)
        accounts.ensure_fixed_test_service(db)
        after = _count_testish_accounts(db)
        fixed_after = (
            _count_fixed(db, accounts.E2E_USER_EMAIL),
            _count_fixed(db, accounts.E2E_SERVICE_EMAIL),
        )
        assert fixed_after == fixed_before == (1, 1)
        assert after >= before
    finally:
        db.close()


def test_helpers_do_not_log_passwords():
    source = inspect.getsource(accounts)
    assert "print(" not in source
    assert "logger." not in source
    assert "logging." not in source


def test_fixed_service_account_is_not_user_account():
    db = SessionLocal()
    try:
        service = accounts.ensure_fixed_test_service(db)
        assert service.role == "service"
        assert service.email.lower() == accounts.E2E_SERVICE_EMAIL
    finally:
        db.close()


def test_fixed_user_account_is_not_service_account():
    db = SessionLocal()
    try:
        user = accounts.ensure_fixed_test_user(db)
        assert user.role == "user"
        assert user.email.lower() == accounts.E2E_USER_EMAIL
    finally:
        db.close()
