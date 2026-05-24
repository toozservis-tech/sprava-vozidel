"""
Environment variable aliases for phased rename (Správa vozidel).

Prefer new names (SPRAVA_VOZIDEL_*); fall back to legacy (TOOZHUB_*).
Do not remove legacy keys until phase 3.
"""

from __future__ import annotations

import os
from typing import Optional


def env_prefer_new(*names: str) -> Optional[str]:
    """
    Return the first non-empty environment value for the given keys, in order.
    Empty string is treated as unset.
    """
    for name in names:
        if not name:
            continue
        raw = os.getenv(name)
        if raw is None:
            continue
        stripped = str(raw).strip()
        if stripped != "":
            return raw
    return None


def env_flag_prefer_new(*names: str, default: str = "0") -> str:
    """Like env_prefer_new but returns default if none set."""
    val = env_prefer_new(*names)
    return val if val is not None else default
