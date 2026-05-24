"""
SEC-HIGH-004 (aktualizováno): Adresář partnerů pro majitele vozidel je celostátní katalog;
servisní účty nadále používají tenant izolaci při výpisu discovery z prostředí servisu.
"""
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, ServiceCustomerLink, Tenant
from src.modules.vehicle_hub.routers_v1 import services as services_router


def _request_with_coordinates() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/services/discovery",
        "headers": [
            (b"x-geo-lat", b"50.0755"),
            (b"x-geo-lon", b"14.4378"),
        ],
        "query_string": b"",
    }
    return Request(scope)


@pytest.fixture()
def db_context(tmp_path: Path):
    db_path = tmp_path / "services_discovery_sec_high_004.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        tenant_a = Tenant(name="Tenant A", license_key="tenant-a-key")
        tenant_b = Tenant(name="Tenant B", license_key="tenant-b-key")
        db.add_all([tenant_a, tenant_b])
        db.commit()
        db.refresh(tenant_a)
        db.refresh(tenant_b)

        user_a = Customer(
            tenant_id=tenant_a.id,
            email="sec-high-004-user-a@example.com",
            password_hash="hash-user-a",
            role="user",
            name="User A",
            city="Praha",
        )
        service_a = Customer(
            tenant_id=tenant_a.id,
            email="sec-high-004-service-a@example.com",
            password_hash="hash-service-a",
            role="service",
            name="Service A",
            city="Praha",
            partner_catalog_approved=True,
        )
        service_b = Customer(
            tenant_id=tenant_b.id,
            email="sec-high-004-service-b@example.com",
            password_hash="hash-service-b",
            role="service",
            name="Service B",
            city="Brno",
            partner_catalog_approved=True,
        )
        developer_admin = Customer(
            tenant_id=tenant_a.id,
            email="sec-high-004-admin@example.com",
            password_hash="hash-admin",
            role="developer_admin",
            name="Admin",
            city="Praha",
        )
        db.add_all([user_a, service_a, service_b, developer_admin])
        db.commit()
        db.refresh(user_a)
        db.refresh(service_a)
        db.refresh(service_b)
        db.refresh(developer_admin)

        yield {
            "db": db,
            "user_a": user_a,
            "service_a": service_a,
            "service_b": service_b,
            "developer_admin": developer_admin,
        }
    finally:
        db.close()
        engine.dispose()


def test_discovery_for_vehicle_owner_lists_all_registered_services(monkeypatch: pytest.MonkeyPatch, db_context) -> None:
    monkeypatch.setattr(services_router, "_geocode_address", lambda _: None)

    payload = services_router.get_services_discovery(
        request=_request_with_coordinates(),
        current_user=db_context["user_a"],
        db=db_context["db"],
        radius_km=0,
    )

    discovered_emails = {item["email"] for item in payload["services"]}

    assert db_context["service_a"].email in discovered_emails
    assert db_context["service_b"].email in discovered_emails
    assert db_context["developer_admin"].email not in discovered_emails


def test_discovery_hides_unapproved_partner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "discovery_unapproved.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        tenant_a = Tenant(name="Tenant A", license_key="tenant-a-key")
        tenant_b = Tenant(name="Tenant B", license_key="tenant-b-key")
        db.add_all([tenant_a, tenant_b])
        db.commit()
        db.refresh(tenant_a)
        db.refresh(tenant_b)

        user_a = Customer(
            tenant_id=tenant_a.id,
            email="user-unapproved-test@example.com",
            password_hash="hash",
            role="user",
            name="User",
            city="Praha",
        )
        approved = Customer(
            tenant_id=tenant_b.id,
            email="svc-approved@example.com",
            password_hash="hash-s",
            role="service",
            name="Approved Svc",
            partner_catalog_approved=True,
        )
        hidden = Customer(
            tenant_id=tenant_b.id,
            email="svc-hidden@example.com",
            password_hash="hash-h",
            role="service",
            name="Hidden Svc",
            partner_catalog_approved=False,
        )
        db.add_all([user_a, approved, hidden])
        db.commit()

        monkeypatch.setattr(services_router, "_geocode_address", lambda _: None)
        payload = services_router.get_services_discovery(
            request=_request_with_coordinates(),
            current_user=user_a,
            db=db,
            radius_km=0,
        )
        emails = {item["email"] for item in payload["services"]}
        assert approved.email in emails
        assert hidden.email not in emails
    finally:
        db.close()
        engine.dispose()


def test_discovery_deduplicates_same_ico_keeps_lower_id_canonical(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "discovery_dedupe.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        tenant_u = Tenant(name="Tenant U", license_key="tenant-u-key")
        tenant_s = Tenant(name="Tenant S", license_key="tenant-s-key")
        db.add_all([tenant_u, tenant_s])
        db.commit()
        db.refresh(tenant_u)
        db.refresh(tenant_s)

        user_a = Customer(
            tenant_id=tenant_u.id,
            email="dedupe-user@example.com",
            password_hash="hash",
            role="user",
            name="User",
            city="Praha",
        )
        canonical = Customer(
            tenant_id=tenant_s.id,
            email="svc-canonical@example.com",
            password_hash="h1",
            role="service",
            name="Canonical",
            ico="12345678",
            partner_catalog_approved=True,
        )
        linked_one = Customer(
            tenant_id=tenant_s.id,
            email="svc-linked@example.com",
            password_hash="h2",
            role="service",
            name="Linked",
            ico="12345678",
            partner_catalog_approved=True,
        )
        db.add_all([user_a, canonical, linked_one])
        db.commit()
        db.refresh(user_a)
        db.refresh(linked_one)

        db.add(
            ServiceCustomerLink(
                service_tenant_id=tenant_s.id,
                service_customer_id=linked_one.id,
                customer_tenant_id=tenant_u.id,
                customer_id=user_a.id,
                status="active",
            )
        )
        db.commit()

        monkeypatch.setattr(services_router, "_geocode_address", lambda _: None)
        payload = services_router.get_services_discovery(
            request=_request_with_coordinates(),
            current_user=user_a,
            db=db,
            radius_km=0,
        )
        emails = {item["email"] for item in payload["services"]}
        by_email = {item["email"]: item for item in payload["services"]}
        assert canonical.email in emails
        assert linked_one.email not in emails
        assert by_email[canonical.email]["is_linked"] is True
    finally:
        db.close()
        engine.dispose()


def test_discovery_deduplicates_by_phone_when_ico_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "discovery_dedupe_phone.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        tenant_u = Tenant(name="Tenant U", license_key="tenant-u-key")
        tenant_s = Tenant(name="Tenant S", license_key="tenant-s-key")
        db.add_all([tenant_u, tenant_s])
        db.commit()
        db.refresh(tenant_u)
        db.refresh(tenant_s)

        user_a = Customer(
            tenant_id=tenant_u.id,
            email="dedupe-phone-user@example.com",
            password_hash="hash",
            role="user",
            name="User",
            city="Praha",
        )
        with_ico_only = Customer(
            tenant_id=tenant_s.id,
            email="svc-ico-line@example.com",
            password_hash="h1",
            role="service",
            name="Company Listing",
            ico="12345678",
            phone="731552299",
            partner_catalog_approved=True,
        )
        linked_mobile = Customer(
            tenant_id=tenant_s.id,
            email="svc-mobile@example.com",
            password_hash="h2",
            role="service",
            name="Owner Mobile Account",
            ico=None,
            phone="+420731552299",
            partner_catalog_approved=True,
        )
        db.add_all([user_a, with_ico_only, linked_mobile])
        db.commit()
        db.refresh(user_a)
        db.refresh(linked_mobile)

        db.add(
            ServiceCustomerLink(
                service_tenant_id=tenant_s.id,
                service_customer_id=linked_mobile.id,
                customer_tenant_id=tenant_u.id,
                customer_id=user_a.id,
                status="active",
            )
        )
        db.commit()

        monkeypatch.setattr(services_router, "_geocode_address", lambda _: None)
        payload = services_router.get_services_discovery(
            request=_request_with_coordinates(),
            current_user=user_a,
            db=db,
            radius_km=0,
        )
        emails = {item["email"] for item in payload["services"]}
        by_email = {item["email"]: item for item in payload["services"]}
        assert with_ico_only.email in emails
        assert linked_mobile.email not in emails
        assert by_email[with_ico_only.email]["is_linked"] is True
    finally:
        db.close()
        engine.dispose()


def test_discovery_owner_filters_by_default_radius(monkeypatch: pytest.MonkeyPatch, db_context) -> None:
    def fake_geocode(addr: str):
        a = (addr or "").lower()
        if "brno" in a:
            return {"lat": 49.195, "lon": 16.607}
        return {"lat": 50.085, "lon": 14.437}

    monkeypatch.setattr(services_router, "_geocode_address", fake_geocode)

    payload = services_router.get_services_discovery(
        request=_request_with_coordinates(),
        current_user=db_context["user_a"],
        db=db_context["db"],
        radius_km=50,
    )
    emails = {item["email"] for item in payload["services"]}
    assert db_context["service_a"].email in emails
    assert db_context["service_b"].email not in emails
    assert payload["meta"].get("within_radius_filter") is True
    assert float(payload["meta"].get("discovery_radius_km") or 0) == 50


def test_discovery_for_developer_admin_keeps_global_visibility(monkeypatch: pytest.MonkeyPatch, db_context) -> None:
    monkeypatch.setattr(services_router, "_geocode_address", lambda _: None)

    payload = services_router.get_services_discovery(
        request=_request_with_coordinates(),
        current_user=db_context["developer_admin"],
        db=db_context["db"],
    )

    discovered_emails = {item["email"] for item in payload["services"]}

    assert db_context["service_a"].email in discovered_emails
    assert db_context["service_b"].email in discovered_emails
    assert db_context["developer_admin"].email in discovered_emails
