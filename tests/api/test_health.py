"""
Smoke testy pro health a základní endpointy
"""
import pytest
import requests


def test_health_endpoint(api_url):
    """Test /health endpoint"""
    response = requests.get(f"{api_url}/health", timeout=5)
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"
    assert "version" in data


def test_root_endpoint(api_url):
    """Root endpoint má vracet redirect na web UI."""
    response = requests.get(f"{api_url}/", timeout=5, allow_redirects=False)
    assert response.status_code == 302
    assert response.headers.get("location") == "/web/index.html"


def test_version_endpoint(api_url):
    """Test /version endpoint"""
    response = requests.get(f"{api_url}/version", timeout=5)
    assert response.status_code == 200
    data = response.json()
    assert "version" in data or "project" in data
