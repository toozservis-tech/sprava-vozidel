"""Testy servisní mapy a mapového podkladu (Mapy.com / OSM tiles)."""
from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.modules.vehicle_hub.models import Customer
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.modules.vehicle_hub.service_map import map_config as map_config_module
from src.modules.vehicle_hub.service_map.constants import VERIFICATION_DUPLICATE
from src.modules.vehicle_hub.service_map.search_service import PII_FORBIDDEN_KEYS, serialize_location
from src.server.bootstrap import create_app


PII_SAMPLE_KEYS = frozenset(
    {
        "vin",
        "spz",
        "owner_name",
        "owner_email",
        "owner_phone",
        "vehicle_id",
        "faktury",
        "zakazky",
        "zakázky",
    }
)


@pytest.fixture()
def maps_config_client():
    app = create_app()
    user = Customer(id=1, email="map-test@example.com", role="user", tenant_id=1)
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def _reload_map_config(
    *,
    provider: str = "osm_tiles",
    mapy_key: str = "",
    tile_url: str = "",
):
    with patch.object(map_config_module, "MAP_PROVIDER", provider), patch.object(
        map_config_module, "MAPY_COM_API_KEY", mapy_key
    ), patch.object(map_config_module, "MAP_TILE_URL", tile_url):
        return map_config_module.build_map_tile_config()


def test_osm_tiles_configured_true():
    cfg = _reload_map_config(provider="osm_tiles")
    assert cfg["configured"] is True
    assert cfg["provider"] == "osm_tiles"
    assert cfg["tile_url"]
    assert cfg["fallback_allowed"] is True


def test_mapy_com_without_key_does_not_crash(maps_config_client: TestClient):
    with patch.object(map_config_module, "MAP_PROVIDER", "mapy_com"), patch.object(
        map_config_module, "MAPY_COM_API_KEY", ""
    ), patch.object(map_config_module, "MAP_TILE_URL", ""):
        response = maps_config_client.get("/api/v1/system/maps-config")
    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is False
    assert data["provider"] == "mapy_com"
    assert data["reason"] == "missing_mapy_com_api_key"
    assert data["fallback_allowed"] is True
    assert data["fallback_provider"] == "osm_tiles"
    assert "tile_url" not in data or data.get("tile_url") is None


def test_mapy_com_with_fake_key_configured_true():
    fake_key = "test-fake-mapy-key-12345"
    cfg = _reload_map_config(provider="mapy_com", mapy_key=fake_key)
    assert cfg["configured"] is True
    assert cfg["provider"] == "mapy_com"
    assert fake_key in cfg["tile_url"]
    assert "api.mapy.cz" in cfg["tile_url"]
    assert cfg["attribution"]


def test_maps_config_response_has_no_pii(maps_config_client: TestClient):
    with patch.object(map_config_module, "MAP_PROVIDER", "mapy_com"), patch.object(
        map_config_module, "MAPY_COM_API_KEY", "abcd1234secret5678wxyz"
    ):
        response = maps_config_client.get("/api/v1/system/maps-config")
    assert response.status_code == 200
    body = response.text.lower()
    for key in PII_SAMPLE_KEYS:
        assert f'"{key}"' not in body


def test_mask_mapy_com_api_key_never_logs_full_key():
    masked = map_config_module.mask_mapy_com_api_key("abcd1234secret5678wxyz")
    assert masked == "abcd...wxyz"
    assert "secret5678" not in masked


def test_custom_tiles_missing_url_fallback():
    cfg = _reload_map_config(provider="custom_tiles", tile_url="")
    assert cfg["configured"] is False
    assert cfg["provider"] == "custom_tiles"
    assert cfg["fallback_provider"] == "osm_tiles"


def test_serialize_location_excludes_pii_keys():
    row = SimpleNamespace(
        id=1,
        name="Test servis",
        category="auto",
        lat=50.0,
        lng=14.0,
        address_text="Ulice 1",
        city="Praha",
        phone=None,
        website=None,
        opening_hours=None,
        services_json="[]",
        vehicle_scope_json="[]",
        verification_status="imported",
        source_type="osm",
        last_verified_at=None,
    )
    payload = serialize_location(row)
    for key in PII_FORBIDDEN_KEYS:
        assert key not in payload


def test_user_search_excludes_duplicate_verification_status():
    from src.modules.vehicle_hub.service_map.search_service import USER_VISIBLE_VERIFICATION_STATUSES

    assert VERIFICATION_DUPLICATE not in USER_VISIBLE_VERIFICATION_STATUSES


def test_service_map_search_endpoint_returns_json_shape(maps_config_client: TestClient):
    response = maps_config_client.get(
        "/api/v1/service-map/search",
        params={
            "north": 50.18,
            "south": 49.55,
            "east": 16.85,
            "west": 15.05,
            "limit": 5,
        },
    )
    if response.status_code == 503:
        pytest.skip("service_map module not ready in test DB")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    for item in data.get("items") or []:
        for key in PII_FORBIDDEN_KEYS:
            assert key not in item
