from __future__ import annotations

import logging
from urllib.parse import urlparse

import requests

from src.core import config as app_config

from .base import VehicleImageProviderAdapter, VehicleImageProviderCandidate

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://www.searchapi.io/api/v1/search"


class SearchApiVehicleImageProvider:
    name = "searchapi"

    def __init__(self, *, api_key: str, endpoint: str | None = None) -> None:
        self.api_key = api_key.strip()
        self.endpoint = (endpoint or DEFAULT_ENDPOINT).strip() or DEFAULT_ENDPOINT

    def search(self, query: str, *, limit: int) -> list[VehicleImageProviderCandidate]:
        params = {
            "engine": "google_images",
            "q": query,
            "num": max(1, int(limit or 1)),
            "api_key": self.api_key,
        }
        response = requests.get(self.endpoint, params=params, timeout=8)
        response.raise_for_status()
        payload = response.json()
        images = payload.get("images_results") or payload.get("image_results") or []
        out: list[VehicleImageProviderCandidate] = []
        for item in images[: max(1, int(limit or 1))]:
            source_url = item.get("source") or item.get("link") or item.get("original")
            domain = item.get("source_domain")
            if not domain and source_url:
                domain = urlparse(str(source_url)).netloc or None
            out.append(
                VehicleImageProviderCandidate(
                    title=str(item.get("title") or ""),
                    image_url=str(item.get("original") or item.get("image") or item.get("thumbnail") or ""),
                    thumbnail_url=item.get("thumbnail"),
                    source_url=source_url,
                    source_domain=domain,
                    width=_to_int(item.get("original_width") or item.get("width")),
                    height=_to_int(item.get("original_height") or item.get("height")),
                    snippet=item.get("snippet") or item.get("source_name"),
                    provider=self.name,
                    raw_payload=item,
                )
            )
        return out


def _to_int(value) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except Exception:
        return None


def build_provider() -> VehicleImageProviderAdapter:
    return SearchApiVehicleImageProvider(
        api_key=app_config.VEHICLE_IMAGE_API_KEY,
        endpoint=app_config.VEHICLE_IMAGE_SEARCH_ENDPOINT or DEFAULT_ENDPOINT,
    )
