"""
Časová zóna pro české uživatele (Europe/Prague).

Databáze ukládá naivní UTC u sloupců DateTime. Do JSON/API se má posílat ISO s příponou Z,
aby klient datetime správně interpretoval. Kalendářní logiku (např. „dnes“ u připomínek)
počítáme podle data v Praze, ne podle lokálního data serveru v UTC.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

ZONE_PRAGUE = ZoneInfo("Europe/Prague")


def prague_today() -> date:
    return datetime.now(ZONE_PRAGUE).date()


def prague_day_start_as_naive_utc(d: date) -> datetime:
    """Začátek kalendářního dne d v Praze jako naivní UTC (shodně s ostatními časy v DB)."""
    aware = datetime.combine(d, datetime.min.time(), tzinfo=ZONE_PRAGUE)
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def prague_day_bounds_naive_utc(d: date) -> tuple[datetime, datetime]:
    """Interval [start, end) pro kalendářní den d v Praze v naivním UTC."""
    start = prague_day_start_as_naive_utc(d)
    end = prague_day_start_as_naive_utc(d + timedelta(days=1))
    return start, end


def naive_utc_to_iso_z(value: Optional[datetime]) -> Optional[str]:
    """Převod uloženého okamžiku (UTC, často naivní) na ISO řetězec s příponou Z pro JSON."""
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    else:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def format_prague_generated_label() -> str:
    """Řetězec data a času pro patičky PDF / exporty (aktuální okamžik v čase ČR)."""
    now_utc = datetime.now(timezone.utc)
    local = now_utc.astimezone(ZONE_PRAGUE)
    return local.strftime("%d.%m.%Y v %H:%M") + " (Česko)"
