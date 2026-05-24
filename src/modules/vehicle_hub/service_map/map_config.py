"""Konfigurace mapového podkladu pro frontend."""
from __future__ import annotations

from src.core.config import MAP_PROVIDER, MAP_TILE_URL, MAPY_COM_API_KEY

OSM_TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTRIBUTION = "© OpenStreetMap contributors"
MAPY_COM_ATTRIBUTION = "© Seznam.cz / Mapy.cz"
MAPY_COM_TILE_URL_BASE = "https://api.mapy.cz/v1/maptiles/basic/256/{z}/{x}/{y}?apikey="


def mask_mapy_com_api_key(api_key: str | None) -> str | None:
    """Maska pro logy – nikdy nelogovat celý klíč."""
    if not api_key:
        return None
    key = api_key.strip()
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


def _osm_tiles_response() -> dict:
    return {
        "configured": True,
        "provider": "osm_tiles",
        "tile_url": OSM_TILE_URL,
        "attribution": OSM_ATTRIBUTION,
        "fallback_allowed": True,
    }


def build_map_tile_config() -> dict:
    provider = (MAP_PROVIDER or "osm_tiles").strip().lower()

    if provider == "osm_tiles":
        return _osm_tiles_response()

    if provider == "mapy_com":
        if MAPY_COM_API_KEY:
            return {
                "configured": True,
                "provider": "mapy_com",
                "tile_url": f"{MAPY_COM_TILE_URL_BASE}{MAPY_COM_API_KEY}",
                "attribution": MAPY_COM_ATTRIBUTION,
                "fallback_allowed": True,
            }
        return {
            "configured": False,
            "provider": "mapy_com",
            "reason": "missing_mapy_com_api_key",
            "fallback_allowed": True,
            "fallback_provider": "osm_tiles",
        }

    if provider == "custom_tiles":
        if MAP_TILE_URL:
            return {
                "configured": True,
                "provider": "custom_tiles",
                "tile_url": MAP_TILE_URL,
                "attribution": "© Map tiles",
                "fallback_allowed": True,
            }
        return {
            "configured": False,
            "provider": "custom_tiles",
            "reason": "missing_map_tile_url",
            "fallback_allowed": True,
            "fallback_provider": "osm_tiles",
        }

    return _osm_tiles_response()
