"""Regression tests: login audit must never wait for external geo network I/O."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.server import security_tracking


def _request(ip="8.8.8.8"):
    return SimpleNamespace(client=SimpleNamespace(host=ip), headers={})


def test_login_audit_keeps_event_and_ip_without_external_geolocation(monkeypatch):
    session = MagicMock()
    remote_lookup = MagicMock(side_effect=AssertionError("external IP lookup on login"))
    reverse_lookup = MagicMock(side_effect=AssertionError("external reverse lookup on login"))
    monkeypatch.setattr(security_tracking, "SessionLocal", lambda: session)
    monkeypatch.setattr(security_tracking, "lookup_ip_location", remote_lookup)
    monkeypatch.setattr(security_tracking, "reverse_geocode_location", reverse_lookup)
    monkeypatch.setattr(security_tracking, "_geo_cache", {})
    monkeypatch.setattr(security_tracking, "_reverse_geo_cache", {})
    monkeypatch.setattr(
        security_tracking,
        "_extract_browser_geo",
        lambda request: {"latitude": 50.0, "longitude": 15.0, "source": "browser_geolocation"},
    )

    security_tracking.log_security_event(
        event_type="login_success",
        request=_request(),
        user_email="service@example.com",
        customer_id=7,
        tenant_id=2,
        endpoint="/user/login",
    )

    remote_lookup.assert_not_called()
    reverse_lookup.assert_not_called()
    session.add.assert_called_once()
    row = session.add.call_args.args[0]
    assert row.event_type == "login_success"
    assert row.ip_address == "8.8.8.8"
    assert row.user_email == "service@example.com"
    assert row.tenant_id == 2
    assert row.customer_id == 7
    session.commit.assert_called_once()
    session.close.assert_called_once()


def test_login_audit_uses_cached_location_if_available(monkeypatch):
    session = MagicMock()
    remote_lookup = MagicMock(side_effect=AssertionError("unexpected remote lookup"))
    monkeypatch.setattr(security_tracking, "SessionLocal", lambda: session)
    monkeypatch.setattr(security_tracking, "lookup_ip_location", remote_lookup)
    monkeypatch.setattr(security_tracking, "_extract_browser_geo", lambda request: None)
    monkeypatch.setattr(
        security_tracking,
        "_geo_cache",
        {"8.8.8.8": {"expires_at": float("inf"), "payload": {"country": "CZ", "source": "cache"}}},
    )

    security_tracking.log_security_event(event_type="login_failed", request=_request())

    remote_lookup.assert_not_called()
    assert session.add.call_args.args[0].country == "CZ"
    session.commit.assert_called_once()


def test_non_login_audit_keeps_existing_geolocation_behavior(monkeypatch):
    session = MagicMock()
    remote_lookup = MagicMock(return_value={"country": "CZ", "source": "ipwho.is"})
    monkeypatch.setattr(security_tracking, "SessionLocal", lambda: session)
    monkeypatch.setattr(security_tracking, "lookup_ip_location", remote_lookup)
    monkeypatch.setattr(security_tracking, "_extract_browser_geo", lambda request: None)

    security_tracking.log_security_event(event_type="document_verified", request=_request())

    remote_lookup.assert_called_once_with("8.8.8.8")
    assert session.add.call_args.args[0].country == "CZ"
    session.commit.assert_called_once()
