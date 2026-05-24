"""
Pomocné funkce pro bezpečnostní sledování přístupů (IP + geolokace).
"""
from __future__ import annotations

import ipaddress
import json
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import quote
from urllib.request import Request as UrlRequest, urlopen

from src.core.branding import APP_SERVER_PRODUCT_TOKEN
from src.modules.vehicle_hub.database import SessionLocal
from src.modules.vehicle_hub.models import SecurityAccessLog

_TRUTHY = {"1", "true", "yes", "on"}
_GEOLOOKUP_ENABLED = os.getenv("ENABLE_IP_GEOLOOKUP", "1").strip().lower() in _TRUTHY
_GEOLOOKUP_TIMEOUT = float(os.getenv("IP_GEOLOOKUP_TIMEOUT_SEC", "1.2"))
_GEOLOOKUP_URL = os.getenv("IP_GEOLOOKUP_PROVIDER_URL", "https://ipwho.is/{ip}")
_GEOLOOKUP_CACHE_TTL_SEC = int(os.getenv("IP_GEOLOOKUP_CACHE_TTL_SEC", "43200"))
_GEOLOOKUP_CACHE_MAX_ITEMS = int(os.getenv("IP_GEOLOOKUP_CACHE_MAX_ITEMS", "1000"))
_BROWSER_GEO_ENABLED = os.getenv("ENABLE_BROWSER_GEOLOCATION_OVERRIDE", "1").strip().lower() in _TRUTHY
_REVERSE_GEO_ENABLED = os.getenv("ENABLE_REVERSE_GEOCODE", "1").strip().lower() in _TRUTHY
_REVERSE_GEOLOOKUP_TIMEOUT = float(os.getenv("REVERSE_GEOLOOKUP_TIMEOUT_SEC", "1.6"))
_REVERSE_GEOLOOKUP_URL = os.getenv(
    "REVERSE_GEOLOOKUP_PROVIDER_URL",
    "https://nominatim.openstreetmap.org/reverse?format=jsonv2&accept-language=cs&lat={lat}&lon={lon}",
)
_REVERSE_GEOLOOKUP_CACHE_TTL_SEC = int(os.getenv("REVERSE_GEOLOOKUP_CACHE_TTL_SEC", "43200"))
_REVERSE_GEOLOOKUP_CACHE_MAX_ITEMS = int(os.getenv("REVERSE_GEOLOOKUP_CACHE_MAX_ITEMS", "1200"))
_ACTIVITY_LOG_MIN_INTERVAL_SEC = max(15, int(os.getenv("USER_ACTIVITY_LOG_MIN_INTERVAL_SEC", "90")))
_ACTIVITY_CACHE_MAX_ITEMS = max(200, int(os.getenv("USER_ACTIVITY_CACHE_MAX_ITEMS", "5000")))

_geo_cache: Dict[str, Dict[str, Any]] = {}
_reverse_geo_cache: Dict[str, Dict[str, Any]] = {}
_activity_cache: Dict[str, float] = {}


def _normalize_ip(candidate: Optional[str]) -> Optional[str]:
    if not candidate:
        return None
    raw = str(candidate).strip()
    if not raw:
        return None

    # X-Forwarded-For miva seznam adres oddeleny carkou.
    first = raw.split(",")[0].strip()

    # Pokus o IPv4:port fallback
    if first.count(":") == 1 and "." in first:
        host_part = first.split(":", 1)[0].strip()
        try:
            ipaddress.ip_address(host_part)
            return host_part
        except ValueError:
            pass

    try:
        ipaddress.ip_address(first)
        return first
    except ValueError:
        return None


def _is_private_or_loopback(ip_value: Optional[str]) -> bool:
    normalized = _normalize_ip(ip_value)
    if not normalized:
        return False
    try:
        parsed = ipaddress.ip_address(normalized)
        return parsed.is_private or parsed.is_loopback or parsed.is_link_local
    except ValueError:
        return False


def extract_client_ip(request: Any) -> Optional[str]:
    """
    Ziska klientskou IP adresu.
    Kdyz request prichazi pres lokalni proxy/tunnel, preferuje forwarding hlavicky.
    """
    direct_ip = None
    if request is not None and getattr(request, "client", None) is not None:
        direct_ip = _normalize_ip(getattr(request.client, "host", None))

    if not direct_ip and request is not None:
        scope = getattr(request, "scope", None)
        if isinstance(scope, dict):
            client = scope.get("client")
            if isinstance(client, (list, tuple)) and client:
                direct_ip = _normalize_ip(client[0])

    if request is None or not hasattr(request, "headers"):
        return direct_ip

    headers = request.headers
    forwarded_headers = (
        "cf-connecting-ip",
        "x-forwarded-for",
        "x-real-ip",
        "x-original-forwarded-for",
    )

    # Za proxy je casto direct_ip None nebo privatni — vzdy zkusit forwarding hlavicky.
    if _is_private_or_loopback(direct_ip) or direct_ip is None:
        for header_name in forwarded_headers:
            candidate = _normalize_ip(headers.get(header_name))
            if candidate:
                return candidate

    return direct_ip


def _build_location_label(city: Optional[str], region: Optional[str], country: Optional[str]) -> Optional[str]:
    parts = [part for part in [city, region, country] if part]
    return ", ".join(parts) if parts else None


def _get_from_cache(ip_value: str) -> Optional[Dict[str, Any]]:
    cached = _geo_cache.get(ip_value)
    if not cached:
        return None
    if cached.get("expires_at", 0) < time.time():
        _geo_cache.pop(ip_value, None)
        return None
    return cached.get("payload")


def _save_to_cache(ip_value: str, payload: Dict[str, Any]) -> None:
    if len(_geo_cache) >= _GEOLOOKUP_CACHE_MAX_ITEMS:
        oldest_key = next(iter(_geo_cache.keys()), None)
        if oldest_key is not None:
            _geo_cache.pop(oldest_key, None)
    _geo_cache[ip_value] = {
        "expires_at": time.time() + _GEOLOOKUP_CACHE_TTL_SEC,
        "payload": payload,
    }


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_browser_geo(request: Any) -> Optional[Dict[str, Any]]:
    """
    Zkusi nacist geolokaci z klientskych hlavicek (pokud uzivatel povolil GPS).
    """
    if not _BROWSER_GEO_ENABLED:
        return None
    if request is None or not hasattr(request, "headers"):
        return None

    lat = _safe_float(request.headers.get("x-geo-lat"))
    lon = _safe_float(request.headers.get("x-geo-lon"))
    if lat is None or lon is None:
        return None
    if lat < -90 or lat > 90 or lon < -180 or lon > 180:
        return None

    accuracy = _safe_float(request.headers.get("x-geo-accuracy"))
    if accuracy is not None and accuracy < 0:
        accuracy = None

    captured_at = request.headers.get("x-geo-captured-at")

    return {
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "accuracy": round(accuracy, 1) if accuracy is not None else None,
        "captured_at": captured_at,
        "source": "browser_geolocation",
    }


def _reverse_geo_cache_key(latitude: float, longitude: float) -> str:
    # Zarovname na 4 desetinna mista (~11m), aby cache dobre fungovala.
    return f"{latitude:.4f},{longitude:.4f}"


def _get_reverse_geo_from_cache(cache_key: str) -> Optional[Dict[str, Any]]:
    cached = _reverse_geo_cache.get(cache_key)
    if not cached:
        return None
    if cached.get("expires_at", 0) < time.time():
        _reverse_geo_cache.pop(cache_key, None)
        return None
    return cached.get("payload")


def _save_reverse_geo_to_cache(cache_key: str, payload: Dict[str, Any]) -> None:
    if len(_reverse_geo_cache) >= _REVERSE_GEOLOOKUP_CACHE_MAX_ITEMS:
        oldest_key = next(iter(_reverse_geo_cache.keys()), None)
        if oldest_key is not None:
            _reverse_geo_cache.pop(oldest_key, None)
    _reverse_geo_cache[cache_key] = {
        "expires_at": time.time() + _REVERSE_GEOLOOKUP_CACHE_TTL_SEC,
        "payload": payload,
    }


def reverse_geocode_location(latitude: Optional[float], longitude: Optional[float]) -> Optional[Dict[str, Any]]:
    """
    Prevede GPS souradnice na citelnou lokaci (obec/mesto/kraj/stat).
    """
    if not _REVERSE_GEO_ENABLED:
        return None
    if latitude is None or longitude is None:
        return None

    cache_key = _reverse_geo_cache_key(latitude, longitude)
    cached = _get_reverse_geo_from_cache(cache_key)
    if cached is not None:
        return cached

    try:
        request_url = _REVERSE_GEOLOOKUP_URL.format(
            lat=quote(str(latitude), safe=""),
            lon=quote(str(longitude), safe=""),
        )
        req = UrlRequest(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": f"{APP_SERVER_PRODUCT_TOKEN}-SecurityTracker/1.0",
            },
        )
        with urlopen(req, timeout=_REVERSE_GEOLOOKUP_TIMEOUT) as response:
            body = response.read().decode("utf-8", errors="ignore")
        data = json.loads(body)

        if not isinstance(data, dict):
            return None

        address = data.get("address")
        if not isinstance(address, dict):
            address = {}

        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or data.get("name")
        )
        region = address.get("state") or address.get("county") or address.get("region")
        country = address.get("country")
        location_label = data.get("display_name") or _build_location_label(city, region, country)

        payload = {
            "country": country,
            "region": region,
            "city": city,
            "location_label": location_label,
            "source": "browser_geolocation_reverse",
        }
        _save_reverse_geo_to_cache(cache_key, payload)
        return payload
    except Exception:
        return None


def lookup_ip_location(ip_value: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Vrati pribliznou lokaci pro IP.
    Pri chybe vraci None a neblokuje hlavni request.
    """
    ip_normalized = _normalize_ip(ip_value)
    if not ip_normalized:
        return None
    if _is_private_or_loopback(ip_normalized):
        return {
            "country": None,
            "region": None,
            "city": None,
            "latitude": None,
            "longitude": None,
            "timezone": None,
            "isp": None,
            "source": "private",
            "location_label": "Privatni/LAN adresa",
        }
    if not _GEOLOOKUP_ENABLED:
        return None

    cached = _get_from_cache(ip_normalized)
    if cached is not None:
        return cached

    try:
        request_url = _GEOLOOKUP_URL.format(ip=quote(ip_normalized, safe=""))
        req = UrlRequest(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": f"{APP_SERVER_PRODUCT_TOKEN}-SecurityTracker/1.0",
            },
        )
        with urlopen(req, timeout=_GEOLOOKUP_TIMEOUT) as response:
            body = response.read().decode("utf-8", errors="ignore")
        data = json.loads(body)

        # ipwho.is format
        if isinstance(data, dict) and data.get("success") is False:
            return None

        country = data.get("country")
        region = data.get("region") or data.get("regionName")
        city = data.get("city")
        latitude = data.get("latitude") or data.get("lat")
        longitude = data.get("longitude") or data.get("lon")
        timezone = None
        timezone_data = data.get("timezone")
        if isinstance(timezone_data, dict):
            timezone = timezone_data.get("id") or timezone_data.get("name")
        elif isinstance(timezone_data, str):
            timezone = timezone_data
        connection = data.get("connection")
        isp = connection.get("isp") if isinstance(connection, dict) else data.get("isp")

        payload = {
            "country": country,
            "region": region,
            "city": city,
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone,
            "isp": isp,
            "source": "ipwho.is",
            "location_label": _build_location_label(city, region, country),
        }
        _save_to_cache(ip_normalized, payload)
        return payload
    except Exception:
        return None


def log_security_event(
    *,
    event_type: str,
    request: Any = None,
    user_email: Optional[str] = None,
    customer_id: Optional[int] = None,
    tenant_id: Optional[int] = None,
    endpoint: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Zapis bezpecnostni udalost do tabulky security_access_logs.
    Nikdy nevyhazuje vyjimku ven (aby neblokoval hlavni flow).
    """
    session = SessionLocal()
    try:
        ip_address = extract_client_ip(request)
        user_agent = None
        if request is not None and hasattr(request, "headers"):
            user_agent = request.headers.get("user-agent")

        base_details: Dict[str, Any] = {}
        if isinstance(details, dict):
            base_details.update(details)
        elif details is not None:
            base_details["details_raw"] = str(details)

        geo = lookup_ip_location(ip_address) or {}
        browser_geo = _extract_browser_geo(request)

        country = geo.get("country")
        region = geo.get("region")
        city = geo.get("city")
        latitude = geo.get("latitude")
        longitude = geo.get("longitude")
        source = geo.get("source")

        if browser_geo:
            latitude = browser_geo.get("latitude")
            longitude = browser_geo.get("longitude")
            source = browser_geo.get("source")

            reverse_geo = reverse_geocode_location(latitude, longitude) or {}
            country = reverse_geo.get("country") or country
            region = reverse_geo.get("region") or region
            city = reverse_geo.get("city") or city
            source = reverse_geo.get("source") or source

            if browser_geo.get("accuracy") is not None:
                base_details["geo_accuracy_m"] = browser_geo.get("accuracy")
            if browser_geo.get("captured_at"):
                base_details["geo_captured_at"] = browser_geo.get("captured_at")

        base_details["geo_source"] = source or "unknown"

        entry = SecurityAccessLog(
            tenant_id=tenant_id,
            customer_id=customer_id,
            user_email=(user_email or "").strip().lower() or None,
            event_type=event_type,
            endpoint=endpoint,
            ip_address=ip_address,
            country=country,
            region=region,
            city=city,
            latitude=latitude,
            longitude=longitude,
            timezone=geo.get("timezone"),
            isp=geo.get("isp"),
            source=source,
            user_agent=user_agent,
            details=json.dumps(base_details, ensure_ascii=False) if base_details else None,
        )
        session.add(entry)
        session.commit()
    except Exception as exc:
        session.rollback()
        print(f"[SECURITY] Failed to store security event '{event_type}': {exc}")
    finally:
        session.close()


def _remember_activity(user_email: str) -> bool:
    """
    Vrati True jen pokud se ma aktualni aktivita zapsat (throttle per user).
    """
    normalized = (user_email or "").strip().lower()
    if not normalized:
        return False

    now = time.time()
    last_seen = _activity_cache.get(normalized)
    if last_seen is not None and (now - last_seen) < _ACTIVITY_LOG_MIN_INTERVAL_SEC:
        return False

    _activity_cache[normalized] = now

    # Lehke omezeni velikosti cache bez drahych operaci.
    if len(_activity_cache) > _ACTIVITY_CACHE_MAX_ITEMS:
        cutoff = now - (_ACTIVITY_LOG_MIN_INTERVAL_SEC * 4)
        stale_keys = [key for key, ts in _activity_cache.items() if ts < cutoff]
        for key in stale_keys:
            _activity_cache.pop(key, None)
        # Pokud stale cleanup nestacil, orezat nejstarsi zaznamy.
        if len(_activity_cache) > _ACTIVITY_CACHE_MAX_ITEMS:
            ordered = sorted(_activity_cache.items(), key=lambda item: item[1])
            to_drop = len(_activity_cache) - _ACTIVITY_CACHE_MAX_ITEMS
            for key, _ in ordered[:to_drop]:
                _activity_cache.pop(key, None)

    return True


def log_user_activity(
    *,
    request: Any = None,
    user_email: Optional[str],
    customer_id: Optional[int] = None,
    tenant_id: Optional[int] = None,
    endpoint: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Zapis heartbeat aktivity prihláseného uživatele (throttled).
    """
    normalized = (user_email or "").strip().lower()
    if not normalized:
        return
    if not _remember_activity(normalized):
        return

    payload: Dict[str, Any] = {"kind": "heartbeat"}
    if details:
        payload.update(details)

    log_security_event(
        event_type="api_activity",
        request=request,
        user_email=normalized,
        customer_id=customer_id,
        tenant_id=tenant_id,
        endpoint=endpoint,
        details=payload,
    )
