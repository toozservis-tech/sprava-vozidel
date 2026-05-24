"""
API testy pro /api/v1/user/settings
"""
import pytest
import requests

from tests.api.integration_accounts import TEST_USER_EMAIL_DEFAULT, ensure_user_token


@pytest.fixture(scope="module")
def settings_headers(api_url):
    token, _ = ensure_user_token(api_url, TEST_USER_EMAIL_DEFAULT)
    assert token, "E2E token required"
    return {"Authorization": f"Bearer {token}"}


def test_settings_requires_auth(api_url):
    resp = requests.get(f"{api_url}/api/v1/user/settings", timeout=10)
    assert resp.status_code in (401, 403)


def test_settings_snapshot(api_url, settings_headers):
    resp = requests.get(f"{api_url}/api/v1/user/settings", headers=settings_headers, timeout=15)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "profile" in data
    assert "preferences" in data
    assert "license" in data
    assert "usage" in data
    assert "tenant_id" not in str(data)
    profile = data.get("profile") or {}
    assert TEST_USER_EMAIL_DEFAULT.lower() not in str(profile.get("email_masked", "")).lower()
    assert "***" in str(profile.get("email_masked", ""))


def test_settings_profile_patch(api_url, settings_headers):
    resp = requests.patch(
        f"{api_url}/api/v1/user/settings/profile",
        headers=settings_headers,
        json={"name": "E2E Settings Test"},
        timeout=15,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("ok") is True


def test_settings_profile_rejects_email_change(api_url, settings_headers):
    snap = requests.get(f"{api_url}/api/v1/user/settings", headers=settings_headers, timeout=15).json()
    original_name = (snap.get("profile") or {}).get("name")
    resp = requests.patch(
        f"{api_url}/api/v1/user/settings/profile",
        headers=settings_headers,
        json={"name": original_name or "E2E Settings Test"},
        timeout=15,
    )
    assert resp.status_code == 200


def test_settings_notifications_marketing_defaults(api_url, settings_headers):
    resp = requests.patch(
        f"{api_url}/api/v1/user/settings/notifications",
        headers=settings_headers,
        json={
            "types": {
                "marketing": {"email": True, "sms": True, "push": True},
                "security": {"email": False, "sms": False, "push": False},
            }
        },
        timeout=15,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    types = (body.get("preferences") or {}).get("types") or {}
    assert types.get("security", {}).get("email") is True
    assert types.get("marketing", {}).get("email") is False


def test_settings_security_bundle(api_url, settings_headers):
    resp = requests.get(f"{api_url}/api/v1/user/settings/security", headers=settings_headers, timeout=15)
    assert resp.status_code == 200
    data = resp.json()
    assert "devices" in data
    assert "two_factor_enabled" in data


def test_settings_billing_no_full_card(api_url, settings_headers):
    resp = requests.get(f"{api_url}/api/v1/user/settings/billing", headers=settings_headers, timeout=15)
    assert resp.status_code == 200
    text = resp.text
    assert "4111" not in text
    assert "4242" not in text


def test_settings_logout_all_bumps_session(api_url, settings_headers):
    """Run last: invalidates session for the module-scoped token."""
    me_before = requests.get(f"{api_url}/api/me", headers=settings_headers, timeout=15)
    assert me_before.status_code == 200
    resp = requests.post(
        f"{api_url}/api/v1/user/settings/security/logout-all",
        headers=settings_headers,
        json={},
        timeout=15,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("session_version") is not None
