"""
Společné konstanty a nástroje pro formát systémových oznámení (broadcast ↔ feed).
Samostatný modul — bez závislostí na admin_api (import z API routerů uživatelů).
"""
from __future__ import annotations

import re
from typing import Optional

import bleach


NOTIFICATION_HTML_MARKER = "__TOOZH_NOTIFY_HTML_v1\n"


def notification_message_kind(value: Optional[str]) -> str:
    return "html" if str(value or "").startswith(NOTIFICATION_HTML_MARKER) else "plain"


def notification_visible_text_len(fragment: str) -> int:
    plain = bleach.clean(fragment or "", tags=[], strip=True)
    return len(re.sub(r"\s+", " ", plain).strip())


def sanitize_notification_rich_html(fragment: str) -> str:
    """Povolené značení pro feed oznámení (tučné, řádky, zarovnání přes text-align)."""
    from bleach.css_sanitizer import CSSSanitizer

    css = CSSSanitizer(allowed_css_properties=["text-align"])
    return bleach.clean(
        fragment or "",
        tags={"p", "div", "br", "span", "b", "strong", "i", "em", "u"},
        attributes={"*": ["style"]},
        css_sanitizer=css,
        strip=True,
    )


def strip_notification_html_marker(value: Optional[str]) -> tuple[str, str]:
    """Vrátí (kind, bez_prefixu_obsah). Kind je 'html' nebo 'plain'."""
    s = str(value or "")
    if s.startswith(NOTIFICATION_HTML_MARKER):
        return "html", s[len(NOTIFICATION_HTML_MARKER) :]
    return "plain", s
