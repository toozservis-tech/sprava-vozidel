from __future__ import annotations

from urllib.parse import urlparse

import requests

from src.core import config as app_config

from .base import VehicleImageProviderAdapter, VehicleImageProviderCandidate

DEFAULT_ENDPOINT = "https://serpapi.com/search.json"


class SerpApiVehicleImageProvider:
    name = "serpapi"

    def __init__(self, *, api_key: str, endpoint: str, engine: str, yandex_domain: str) -> None:
        self.api_key = api_key.strip()
        self.endpoint = endpoint.strip() or DEFAULT_ENDPOINT
        self.engine = (engine or "google_images").strip().lower()
        self.yandex_domain = (yandex_domain or "yandex.com").strip()

    def search(self, query: str, *, limit: int) -> list[VehicleImageProviderCandidate]:
        images = self._search_images_with_fallback(query=query, limit=limit)
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
                    width=_to_int(item.get("original_width") or item.get("width") or (item.get("size") or {}).get("width")),
                    height=_to_int(item.get("original_height") or item.get("height") or (item.get("size") or {}).get("height")),
                    snippet=item.get("snippet"),
                    provider=self.name,
                    raw_payload=item,
                )
            )
        return out

    def _search_images_with_fallback(self, *, query: str, limit: int) -> list[dict]:
        attempts: list[tuple[str, str | None]] = []
        primary_engine = self.engine if self.engine in {"google_images", "yandex_images"} else "google_images"
        attempts.append((primary_engine, None))
        if primary_engine != "google_images":
            attempts.append(("google_images", "primary provider returned no usable image results"))

        last_error: Exception | None = None
        for engine, fallback_reason in attempts:
            try:
                params = self._build_params(query=query, limit=limit, engine_override=engine)
                response = requests.get(
                    self.endpoint,
                    params=params,
                    timeout=8,
                )
                response.raise_for_status()
                payload = response.json()
                images = payload.get("images_results") or []
                if images:
                    return images
            except Exception as exc:
                last_error = exc
                if engine == "google_images":
                    break
            if fallback_reason:
                continue

        if last_error is not None:
            raise last_error
        return []

    def _build_params(self, *, query: str, limit: int, engine_override: str | None = None) -> dict[str, object]:
        normalized_limit = max(1, int(limit or 1))
        effective_engine = (engine_override or self.engine or "google_images").strip().lower()
        if effective_engine == "yandex_images":
            return {
                "engine": "yandex_images",
                "text": query,
                "p": 0,
                "yandex_domain": self.yandex_domain,
                "orientation": app_config.VEHICLE_IMAGE_SERPAPI_YANDEX_ORIENTATION,
                "image_type": app_config.VEHICLE_IMAGE_SERPAPI_YANDEX_IMAGE_TYPE,
                "family_mode": app_config.VEHICLE_IMAGE_SERPAPI_YANDEX_FAMILY_MODE,
                "api_key": self.api_key,
            }
        return {
            "engine": "google_images",
            "q": query,
            "num": normalized_limit,
            "api_key": self.api_key,
        }


def _to_int(value) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except Exception:
        return None


def build_provider() -> VehicleImageProviderAdapter:
    return SerpApiVehicleImageProvider(
        api_key=app_config.VEHICLE_IMAGE_API_KEY,
        endpoint=app_config.VEHICLE_IMAGE_SERPAPI_ENDPOINT,
        engine=app_config.VEHICLE_IMAGE_SERPAPI_ENGINE,
        yandex_domain=app_config.VEHICLE_IMAGE_SERPAPI_YANDEX_DOMAIN,
    )
