from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import AdminCustomerChangeEvent, Customer, CustomerDeletionLabel, Tenant
from src.server import admin_api


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "admin_user_archive_purge.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_admin_and_deleted_user(db_session):
    admin_tenant = Tenant(name="Admin Tenant", license_key="admin-tenant-key")
    deleted_tenant = Tenant(name="Deleted Tenant", license_key="deleted-tenant-key")
    db_session.add_all([admin_tenant, deleted_tenant])
    db_session.commit()
    db_session.refresh(admin_tenant)
    db_session.refresh(deleted_tenant)

    admin = Customer(
        tenant_id=admin_tenant.id,
        email="developer@example.com",
        password_hash="hash",
        role="developer_admin",
        name="Developer",
    )
    deleted = Customer(
        tenant_id=deleted_tenant.id,
        email="deleted+archive-1@example.invalid",
        password_hash="hash",
        role="user",
        name="Deleted User",
        is_deleted=True,
        deleted_at=datetime.utcnow(),
    )
    db_session.add_all([admin, deleted])
    db_session.commit()
    db_session.refresh(deleted)

    label = CustomerDeletionLabel(
        customer_id=deleted.id,
        ordinal_at_delete=1,
        hash_depth=1,
        email_before="deleted@example.com",
    )
    change_event = AdminCustomerChangeEvent(
        customer_id=deleted.id,
        admin_email="developer@example.com",
        change_key="account.deleted",
        summary_line="Účet byl archivován",
    )
    db_session.add_all([label, change_event])
    db_session.commit()
    return admin, deleted


def test_purge_deleted_user_archive_removes_only_soft_deleted_accounts(
    monkeypatch: pytest.MonkeyPatch,
    db_session,
) -> None:
    admin, deleted = _seed_admin_and_deleted_user(db_session)
    deleted_id = int(deleted.id)
    admin_id = int(admin.id)

    monkeypatch.setattr(admin_api, "log_developer_action", lambda *_, **__: None)

    result = admin_api.purge_deleted_users_archive(
        admin_api.UserArchivePurgeRequest(
            customer_ids=[deleted_id],
            purge_all=False,
            confirm_phrase=admin_api.ARCHIVED_USERS_PURGE_CONFIRM_PHRASE,
        ),
        request=None,
        email=admin.email,
        db=db_session,
    )

    assert result["purged"] == 1
    assert result["customer_ids"] == [deleted_id]
    assert result["deleted_counts"]["customer_deletion_labels"] == 1
    assert db_session.query(Customer).filter(Customer.id == deleted_id).count() == 0
    assert db_session.query(CustomerDeletionLabel).filter(CustomerDeletionLabel.customer_id == deleted_id).count() == 0
    assert db_session.query(AdminCustomerChangeEvent).filter(AdminCustomerChangeEvent.customer_id == deleted_id).count() == 0
    assert db_session.query(Customer).filter(Customer.id == admin_id).count() == 1


def test_purge_deleted_user_archive_accepts_case_and_space_variants(
    monkeypatch: pytest.MonkeyPatch,
    db_session,
) -> None:
    admin, deleted = _seed_admin_and_deleted_user(db_session)
    deleted_id = int(deleted.id)

    monkeypatch.setattr(admin_api, "log_developer_action", lambda *_, **__: None)

    result = admin_api.purge_deleted_users_archive(
        admin_api.UserArchivePurgeRequest(
            customer_ids=[deleted_id],
            purge_all=False,
            confirm_phrase="  vymazat   archiv  ",
        ),
        request=None,
        email=admin.email,
        db=db_session,
    )

    assert result["purged"] == 1
    assert db_session.query(Customer).filter(Customer.id == deleted_id).count() == 0


def test_purge_deleted_user_archive_accepts_trailing_punctuation(
    monkeypatch: pytest.MonkeyPatch,
    db_session,
) -> None:
    admin, deleted = _seed_admin_and_deleted_user(db_session)
    deleted_id = int(deleted.id)

    monkeypatch.setattr(admin_api, "log_developer_action", lambda *_, **__: None)

    result = admin_api.purge_deleted_users_archive(
        admin_api.UserArchivePurgeRequest(
            customer_ids=[deleted_id],
            purge_all=False,
            confirm_phrase="VYMAZAT ARCHIV.",
        ),
        request=None,
        email=admin.email,
        db=db_session,
    )

    assert result["purged"] == 1
    assert db_session.query(Customer).filter(Customer.id == deleted_id).count() == 0


def test_purge_deleted_user_archive_rejects_wrong_confirm_phrase(
    monkeypatch: pytest.MonkeyPatch,
    db_session,
) -> None:
    admin, deleted = _seed_admin_and_deleted_user(db_session)
    deleted_id = int(deleted.id)

    monkeypatch.setattr(admin_api, "log_developer_action", lambda *_, **__: None)

    with pytest.raises(HTTPException) as exc_info:
        admin_api.purge_deleted_users_archive(
            admin_api.UserArchivePurgeRequest(
                customer_ids=[deleted_id],
                purge_all=False,
                confirm_phrase="SPATNE",
            ),
            request=None,
            email=admin.email,
            db=db_session,
        )

    assert exc_info.value.status_code == 400
    assert db_session.query(Customer).filter(Customer.id == deleted_id).count() == 1
    assert db_session.query(CustomerDeletionLabel).filter(CustomerDeletionLabel.customer_id == deleted_id).count() == 1
