"""Geokódování adres přes Mapy.cz API (našeptávání pro servisní mapu)."""
from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import quote
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from src.core.branding import APP_SERVER_PRODUCT_TOKEN
from src.core.config import MAPY_COM_API_KEY

logger = logging.getLogger(__name__)

_MAPY_SUGGEST_URL = "https://api.mapy.cz/v1/suggest"
_MAPY_SUGGEST_TIMEOUT_SEC = 4.0
_MAPY_SUGGEST_CACHE_TTL_SEC = 24 * 60 * 60
_MAPY_SUGGEST_CACHE_MAX = 8000
_MAPY_SUGGEST_CACHE: dict[str, dict[str, Any]] = {}


def _cache_get(key: str) -> list[dict[str, Any]] | None:
    row = _MAPY_SUGGEST_CACHE.get(key)
    if not row:
        return None
    if row.get("expires_at", 0) < time.time():
        _MAPY_SUGGEST_CACHE.pop(key, None)
        return None
    payload = row.get("payload")
    return payload if isinstance(payload, list) else None


def _cache_set(key: str, payload: list[dict[str, Any]]) -> None:
    if len(_MAPY_SUGGEST_CACHE) >= _MAPY_SUGGEST_CACHE_MAX:
        oldest = next(iter(_MAPY_SUGGEST_CACHE.keys()), None)
        if oldest is not None:
            _MAPY_SUGGEST_CACHE.pop(oldest, None)
    _MAPY_SUGGEST_CACHE[key] = {
        "expires_at": time.time() + _MAPY_SUGGEST_CACHE_TTL_SEC,
        "payload": payload,
    }


def _mapy_item_to_hit(item: dict[str, Any]) -> dict[str, Any] | None:
    position = item.get("position") if isinstance(item.get("position"), dict) else {}
    lat = position.get("lat")
    lon = position.get("lon")
    if lat is None or lon is None:
        return None
    name = str(item.get("name") or "").strip()
    location = str(item.get("location") or "").strip()
    label = str(item.get("label") or "").strip()
    display_name = name
    if location and location not in name:
        display_name = f"{name}, {location}" if name else location
    return {
        "lat": lat,
        "lon": lon,
        "display_name": display_name or name or location,
        "address": {"display": display_name, "location": location, "label": label},
        "type": item.get("type"),
        "category": item.get("type"),
        "source": "mapy_com",
    }


def mapy_geocode_suggest(query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """Vrátí záznamy adres z Mapy.cz Suggest API."""
    if not MAPY_COM_API_KEY:
        return []
    q = str(query or "").strip()
    if len(q) < 2:
        return []
    lim = max(1, min(int(limit), 12))
    cache_key = f"mapy:{lim}:{q.lower()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    params = [
        f"query={quote(q, safe='')}",
        "type=regional.address",
        "type=regional.street",
        "type=regional.municipality",
        "type=regional.municipality_part",
        "locality=cz",
        "lang=cs",
        f"limit={lim}",
        f"apikey={quote(MAPY_COM_API_KEY, safe='')}",
    ]
    request_url = f"{_MAPY_SUGGEST_URL}?{'&'.join(params)}"
    try:
        req = UrlRequest(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": f"{APP_SERVER_PRODUCT_TOKEN}-MapyGeocodeSuggest/1.0",
            },
        )
        with urlopen(req, timeout=_MAPY_SUGGEST_TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8", errors="ignore")
        data = json.loads(body)
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            _cache_set(cache_key, [])
            return []
        hits: list[dict[str, Any]] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            hit = _mapy_item_to_hit(raw)
            if hit:
                hits.append(hit)
        _cache_set(cache_key, hits)
        return hits
    except Exception as exc:
        logger.warning("mapy_geocode_suggest failed: %s", exc)
        return []


def mapy_reverse_geocode(lat: float, lon: float) -> dict[str, str | None] | None:
    """Reverzní geokódování přes Mapy.cz API."""
    if not MAPY_COM_API_KEY:
        return None
    request_url = (
        "https://api.mapy.cz/v1/rgeocode"
        f"?lat={quote(str(lat), safe='')}"
        f"&lon={quote(str(lon), safe='')}"
        f"&lang=cs"
        f"&apikey={quote(MAPY_COM_API_KEY, safe='')}"
    )
    try:
        req = UrlRequest(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": f"{APP_SERVER_PRODUCT_TOKEN}-MapyReverseGeocode/1.0",
            },
        )
        with urlopen(req, timeout=_MAPY_SUGGEST_TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8", errors="ignore")
        data = json.loads(body)
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list) or not items:
            return None
        first = items[0] if isinstance(items[0], dict) else {}
        location = str(first.get("location") or "").strip()
        name = str(first.get("name") or "").strip()
        label = location or name
        city = None
        region = None
        country = None
        for part in first.get("regionalStructure") or []:
            if not isinstance(part, dict):
                continue
            ptype = str(part.get("type") or "")
            pname = str(part.get("name") or "")
            if ptype == "regional.municipality" and not city:
                city = pname
            elif ptype == "regional.region" and not region:
                region = pname
            elif ptype == "regional.country" and not country:
                country = pname
        return {
            "location_label": label or None,
            "city": city,
            "region": region,
            "country": country,
        }
    except Exception as exc:
        logger.warning("mapy_reverse_geocode failed: %s", exc)
        return None
