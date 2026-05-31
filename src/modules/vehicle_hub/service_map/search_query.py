"""Parsování textu vyhledávání servisní mapy (kategorie vs. adresa)."""
from __future__ import annotations

import re
from typing import Any

_CATEGORY_KEYWORDS: list[tuple[str, str]] = [
    ("pneuservis", "pneuservis"),
    ("pneu servis", "pneuservis"),
    ("pneu", "pneuservis"),
    ("autoservis", "autoservis"),
    ("auto servis", "autoservis"),
    ("nákladní", "truck_service"),
    ("nakladni", "truck_service"),
    ("kamion", "truck_service"),
    ("emise", "sme"),
    ("stk", "stk"),
]


def parse_service_map_search_text(raw: str | None) -> dict[str, Any]:
    """
    Rozloží dotaz uživatele na kategorii a text lokality.
    Např. „autoservis Opatovec“ → category=autoservis, location_query=Opatovec.
    """
    text = str(raw or "").strip()
    if not text:
        return {"category": None, "location_query": None, "free_text": None}

    lowered = text.lower()
    category = None
    remainder = text

    for keyword, cat in sorted(_CATEGORY_KEYWORDS, key=lambda pair: -len(pair[0])):
        pattern = re.compile(rf"(^|\s){re.escape(keyword)}(\s|$)", re.IGNORECASE)
        if pattern.search(lowered) or lowered == keyword:
            category = cat
            remainder = pattern.sub(" ", remainder, count=1).strip(" ,")
            break

    if category and not remainder:
        return {"category": category, "location_query": None, "free_text": None}

    if category:
        return {"category": category, "location_query": remainder or None, "free_text": None}

    return {"category": None, "location_query": text, "free_text": text}
