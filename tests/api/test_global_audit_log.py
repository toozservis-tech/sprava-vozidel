"""Smoke: append-only audit_log zápis."""
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.audit_log import write_global_audit_log
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import GlobalAuditLog, Tenant


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "audit.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_write_global_audit_log_persists(db_session) -> None:
    t = Tenant(name="Audit T", license_key="audit-tenant-key")
    db_session.add(t)
    db_session.flush()
    write_global_audit_log(
        db_session,
        entity_type="vehicle",
        entity_id=42,
        action="vehicle_create",
        actor_user_id=None,
        actor_role="user",
        tenant_id=t.id,
        metadata={"x": 1},
    )
    db_session.commit()
    row = db_session.query(GlobalAuditLog).first()
    assert row is not None
    assert row.entity_type == "vehicle"
    assert row.entity_id == 42
    assert row.action == "vehicle_create"
    assert row.actor_user_id is None
    assert "x" in (row.metadata_json or "")
