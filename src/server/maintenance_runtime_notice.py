"""
Virtuální systémové oznámení z runtime admin_settings – plánovaná údržba bez nutnosti řádku v DB.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from html import escape
from typing import Any, Dict, Optional

from src.server.runtime_settings import (
    get_runtime_setting_text,
    get_runtime_setting_bool,
)

# Negativní ID – nekoliduje s autoinkrementní tabulkou.
MAINTENANCE_RUNTIME_NOTICE_ID = -100_001


def _parse_iso_date_optional(raw: str) -> Optional[date]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def maintenance_notice_active_for_today(settings: Dict[str, Dict[str, Dict[str, Any]]] | None) -> bool:
    if not get_runtime_setting_bool(
        "general",
        "maintenance_notice_enabled",
        False,
        settings=settings,
    ):
        return False
    message = get_runtime_setting_text(
        "general",
        "maintenance_notice_message",
        "",
        settings=settings,
    ).strip()
    if not message:
        return False
    start = _parse_iso_date_optional(
        get_runtime_setting_text("general", "maintenance_notice_period_start", "", settings=settings)
    )
    end = _parse_iso_date_optional(get_runtime_setting_text("general", "maintenance_notice_period_end", "", settings=settings))
    today = _today_utc()
    if start is not None and today < start:
        return False
    if end is not None and today > end:
        return False
    return True


def build_maintenance_runtime_notification_item(settings: Dict[str, Dict[str, Dict[str, Any]]] | None) -> Optional[
    Dict[str, Any]
]:
    if not maintenance_notice_active_for_today(settings):
        return None
    title = get_runtime_setting_text(
        "general",
        "maintenance_notice_title",
        "Oznámení",
        settings=settings,
    ).strip() or "Oznámení"
    message = get_runtime_setting_text(
        "general",
        "maintenance_notice_message",
        "",
        settings=settings,
    ).strip()

    stamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"

    return {
        "id": MAINTENANCE_RUNTIME_NOTICE_ID,
        "title": title,
        "message": message,
        "message_kind": "plain",
        "severity": "warning",
        "target_type": "all",
        "target_value": None,
        "created_at": stamp,
        "expires_at": None,
    }


def maintenance_lockout_message_html(settings: Dict[str, Dict[str, Dict[str, Any]]] | None) -> str:
    """Vlastní doplněk na 503 stránku (HTML-escapovaný)."""
    enabled = get_runtime_setting_bool("general", "maintenance_notice_enabled", False, settings=settings)
    raw = (
        get_runtime_setting_text(
            "general",
            "maintenance_notice_message",
            "",
            settings=settings,
        ).strip()
        if enabled
        else ""
    )
    return escape(raw)
