"""
SPA fallback pro /web/... a kořen /app — nesmí vracet JSON 404 na deep linky.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.server.bootstrap import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_web_app_deep_link_returns_html(client: TestClient):
    r = client.get("/web/app/u/test-workspace/dashboard")
    assert r.status_code == 200
    assert "text/html" in (r.headers.get("content-type") or "").lower()
    body = r.text[:500].lower()
    assert "html" in body


def test_web_root_returns_html(client: TestClient):
    r = client.get("/web/")
    assert r.status_code == 200
    assert "text/html" in (r.headers.get("content-type") or "").lower()


def test_web_login_returns_html(client: TestClient):
    r = client.get("/web/login")
    assert r.status_code == 200
    assert "text/html" in (r.headers.get("content-type") or "").lower()


def test_web_missing_asset_returns_404_not_index(client: TestClient):
    r = client.get("/web/assets/does-not-exist-asset-xyz-999999.png")
    assert r.status_code == 404
    assert "text/html" not in (r.headers.get("content-type") or "").lower()


def test_api_me_anonymous_still_json(client: TestClient):
    r = client.get("/api/me")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/json")
    assert r.json().get("authenticated") is False


def test_health_still_json(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert "application/json" in (r.headers.get("content-type") or "")


def test_verify_email_page_returns_html(client: TestClient):
    r = client.get("/web/verify-email.html")
    assert r.status_code == 200
    assert "text/html" in (r.headers.get("content-type") or "").lower()


def test_verify_document_page_returns_html(client: TestClient):
    r = client.get("/web/verify.html")
    assert r.status_code == 200
    assert "text/html" in (r.headers.get("content-type") or "").lower()


def test_existing_web_static_file_served(client: TestClient):
    r = client.get("/web/storage_migration.js")
    assert r.status_code == 200
    ct = r.headers.get("content-type") or ""
    assert "javascript" in ct or "ecmascript" in ct or "text/plain" in ct
