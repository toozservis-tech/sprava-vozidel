"""
Lehký runtime reader pro administrátorské nastavení.
Používá se v částech aplikace, které potřebují číst konfiguraci bez
závislosti na admin API routeru.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Any, Dict

from src.core.config import DATA_DIR

ADMIN_SETTINGS_FILE = DATA_DIR / "admin_settings.json"

_settings_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
_settings_cache_mtime_ns: int | None = None
_cache_lock = Lock()


def invalidate_runtime_settings_cache() -> None:
    """Po zápisu administrátorského JSON zrušit čtení z cache."""
    global _settings_cache_mtime_ns, _settings_cache
    with _cache_lock:
        _settings_cache = {}
        _settings_cache_mtime_ns = None


def _normalize_loaded_payload(payload: Any) -> Dict[str, Dict[str, Dict[str, Any]]]:
    if not isinstance(payload, dict):
        return {}

    normalized: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for category, entries in payload.items():
        if not isinstance(category, str) or not isinstance(entries, dict):
            continue
        cat: Dict[str, Dict[str, Any]] = {}
        for key, item in entries.items():
            if not isinstance(key, str) or not isinstance(item, dict):
                continue
            cat[key] = {
                "value": item.get("value"),
                "value_type": item.get("value_type"),
                "description": item.get("description"),
            }
        normalized[category] = cat
    return normalized


def load_runtime_settings(*, force_reload: bool = False) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Načte admin settings z JSON souboru s jednoduchou mtime cache.
    """
    global _settings_cache_mtime_ns, _settings_cache

    settings_path = Path(ADMIN_SETTINGS_FILE)
    if not settings_path.exists():
        with _cache_lock:
            _settings_cache = {}
            _settings_cache_mtime_ns = None
        return {}

    try:
        stat = settings_path.stat()
        mtime_ns = int(stat.st_mtime_ns)
    except OSError:
        return {}

    with _cache_lock:
        if not force_reload and _settings_cache_mtime_ns == mtime_ns:
            return deepcopy(_settings_cache)

        try:
            with settings_path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except Exception:
            _settings_cache = {}
            _settings_cache_mtime_ns = mtime_ns
            return {}

        _settings_cache = _normalize_loaded_payload(loaded)
        _settings_cache_mtime_ns = mtime_ns
        return deepcopy(_settings_cache)


def get_runtime_setting(
    category: str,
    key: str,
    default: Any = None,
    *,
    settings: Dict[str, Dict[str, Dict[str, Any]]] | None = None,
) -> Any:
    source = settings if settings is not None else load_runtime_settings()
    payload = source.get(str(category), {}).get(str(key))
    if isinstance(payload, dict) and "value" in payload:
        return payload.get("value")
    return default


def get_runtime_setting_text(
    category: str,
    key: str,
    default: str = "",
    *,
    settings: Dict[str, Dict[str, Dict[str, Any]]] | None = None,
) -> str:
    value = get_runtime_setting(category, key, default, settings=settings)
    if value is None:
        return default
    return str(value).strip()


def get_runtime_setting_bool(
    category: str,
    key: str,
    default: bool = False,
    *,
    settings: Dict[str, Dict[str, Dict[str, Any]]] | None = None,
) -> bool:
    value = get_runtime_setting(category, key, default, settings=settings)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def get_runtime_setting_int(
    category: str,
    key: str,
    default: int = 0,
    *,
    settings: Dict[str, Dict[str, Dict[str, Any]]] | None = None,
) -> int:
    value = get_runtime_setting(category, key, default, settings=settings)
    if value is None:
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default
