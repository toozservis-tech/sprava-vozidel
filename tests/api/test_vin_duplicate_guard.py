from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from src.modules.vehicle_hub.database import Base, SessionLocal, engine
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.server.main import app


client = TestClient(app)


def _make_customer(db, label: str) -> Customer:
    suffix = uuid4().hex
    tenant = Tenant(name=f"VIN Guard {label} {suffix}", license_key=f"vin-guard-{label}-{suffix}")
    db.add(tenant)
    db.flush()
    user = Customer(
        tenant_id=tenant.id,
        email=f"vin-guard-{label}-{suffix}@example.test",
        password_hash="test",
        name=f"VIN Guard {label}",
    )
    db.add(user)
    db.flush()
    return user


def _cleanup(db, *users: Customer) -> None:
    tenant_ids = [int(u.tenant_id) for u in users if u and u.tenant_id]
    emails = [str(u.email) for u in users if u and u.email]
    if tenant_ids:
        db.query(Vehicle).filter(Vehicle.tenant_id.in_(tenant_ids)).delete(synchronize_session=False)
        db.query(Customer).filter(Customer.email.in_(emails)).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).delete(synchronize_session=False)
        db.commit()


def test_decode_vin_blocks_other_tenant_before_mdcr(monkeypatch):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    owner = other = None
    vin = "TMBJF73T2B9044629"
    mdcr_called = {"value": False}

    async def fake_mdcr(_vin: str):
        mdcr_called["value"] = True
        return None

    try:
        owner = _make_customer(db, "owner")
        other = _make_customer(db, "other")
        db.add(
            Vehicle(
                tenant_id=owner.tenant_id,
                user_email=owner.email,
                nickname="Owner car",
                vin=vin,
                plate="GDPR123",
                brand="SecretBrand",
                model="SecretModel",
            )
        )
        db.commit()

        app.dependency_overrides[get_current_user] = lambda: other
        monkeypatch.setattr("src.modules.licensing.service.assert_feature", lambda *_args, **_kwargs: None)
        monkeypatch.setattr("src.modules.vehicle_hub.decoder.router.fetch_vehicle_by_vin_from_mdcr", fake_mdcr)

        response = client.post("/api/vehicles/decode-vin", json={"vin": vin})

        assert response.status_code == 409
        payload = response.json()
        assert payload == {
            "code": "VIN_ALREADY_REGISTERED_OTHER_USER",
            "message": "Vozidlo s tímto VIN je již evidováno v aplikaci pod jiným uživatelem.",
            "can_continue": False,
        }
        body = response.text.lower()
        for forbidden in ("gdpr123", "secretbrand", "secretmodel", "owner", "tenant_id", "vehicle_id", "technical"):
            assert forbidden not in body
        assert mdcr_called["value"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        if owner or other:
            _cleanup(db, *(u for u in (owner, other) if u))
        db.close()


def test_create_vehicle_blocks_other_tenant_without_creating_vehicle(monkeypatch):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    owner = other = None
    vin = "WVWZZZ1KZ6W000000"

    try:
        owner = _make_customer(db, "create-owner")
        other = _make_customer(db, "create-other")
        db.add(
            Vehicle(
                tenant_id=owner.tenant_id,
                user_email=owner.email,
                nickname="Existing car",
                vin=vin,
                plate="GDPR456",
                brand="PrivateBrand",
                model="PrivateModel",
            )
        )
        db.commit()

        app.dependency_overrides[get_current_user] = lambda: other
        monkeypatch.setattr("src.modules.licensing.service.assert_vehicle_quota", lambda *_args, **_kwargs: None)

        response = client.post(
            "/api/v1/vehicles",
            json={
                "nickname": "Attempted clone",
                "vin": vin,
                "plate": "NEW123",
                "stk_valid_until": "2030-12-31",
            },
        )

        assert response.status_code == 409
        assert response.json()["code"] == "VIN_ALREADY_REGISTERED_OTHER_USER"
        assert (
            db.query(Vehicle)
            .filter(Vehicle.tenant_id == other.tenant_id, Vehicle.vin == vin)
            .first()
            is None
        )
        body = response.text.lower()
        for forbidden in ("gdpr456", "privatebrand", "privatemodel", "tenant_id", "vehicle_id"):
            assert forbidden not in body
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        if owner or other:
            _cleanup(db, *(u for u in (owner, other) if u))
        db.close()
