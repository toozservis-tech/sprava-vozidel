"""Reset hesla: bump session_version → staré JWT 401 (bez živého API serveru)."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.security import create_access_token, hash_password
from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import Customer, Tenant
from src.server.routers.user_account import router as user_account_router
from src.server.routers.user_auth import router as user_auth_router


@pytest.fixture()
def reset_client(tmp_path: Path):
    db_path = tmp_path / "reset.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="T", license_key="k-reset-session")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    reset_tok = "reset-secret-token-xyz"
    customer = Customer(
        tenant_id=tenant.id,
        email="resetme@example.com",
        password_hash=hash_password("oldpass12"),
        name="Reset User",
        session_version=0,
        reset_token=reset_tok,
        reset_token_expires=datetime.utcnow() + timedelta(hours=1),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    app = FastAPI()
    app.include_router(user_auth_router)
    app.include_router(user_account_router)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)
    try:
        yield client, db, customer, reset_tok
    finally:
        client.close()
        db.close()
        engine.dispose()


def test_reset_password_invalidates_jwt_via_session_version(reset_client) -> None:
    client, db, customer, reset_tok = reset_client
    email = customer.email
    old_jwt = create_access_token(data={"sub": email, "sv": 0})

    r = client.post("/user/reset-password", json={"token": reset_tok, "new_password": "newpass99"})
    assert r.status_code == 200

    db.refresh(customer)
    assert int(customer.session_version or 0) == 1

    me = client.get("/user/me", headers={"Authorization": f"Bearer {old_jwt}"})
    assert me.status_code == 401

    new_jwt = create_access_token(data={"sub": email, "sv": int(customer.session_version or 0)})
    me2 = client.get("/user/me", headers={"Authorization": f"Bearer {new_jwt}"})
    assert me2.status_code == 200
