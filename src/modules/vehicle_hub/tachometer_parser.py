from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import html
import json
import re
import unicodedata
from typing import Any, Dict, List, Optional


def strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    no_tags = re.sub(r"<[^>]+>", "", raw, flags=re.S)
    text = html.unescape(no_tags).replace("\xa0", " ")
    return " ".join(text.split())


def normalize_km(raw: str | None) -> int | None:
    digits = re.sub(r"[^0-9]", "", strip_html(raw))
    if not digits:
        return None
    return int(digits)


def normalize_inspection_date(raw: str | None) -> datetime | None:
    value = strip_html(raw)
    if not value:
        return None
    for fmt in ("%d.%m.%Y", "%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def normalize_inspection_type(raw: str | None) -> str | None:
    value = strip_html(raw).upper()
    if not value:
        return None
    if "EMIS" in value or value == "SME":
        return "SME"
    if "STK" in value:
        return "STK"
    return value[:64]


def normalize_result(raw: str | None) -> str | None:
    value = strip_html(raw)
    if not value:
        return None
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    if "zpusobil" in normalized:
        return "Zpusobile"
    if "nezpusobil" in normalized:
        return "Nezpusobile"
    if "vyhovel" in normalized:
        return "Vyhovel"
    if "nevyhovel" in normalized:
        return "Nevyhovel"
    return value[:128]


def normalize_defects(raw: str | None) -> str | None:
    value = strip_html(raw)
    return value[:4000] if value else None


@dataclass
class ParsedTachometerInspection:
    inspection_date: datetime | None
    inspection_type: str | None
    inspection_kind: str | None
    odometer_km: int
    protocol_number: str | None
    result_label: str | None
    defects_text: str | None
    note_text: str | None
    raw_payload_json: Dict[str, Any]
    source_hash: str


def _pick_cell(cells: List[str], index: int) -> str | None:
    if index < 0 or index >= len(cells):
        return None
    return cells[index]


def _build_source_hash(vin: str, payload: Dict[str, Any]) -> str:
    serialized = json.dumps(
        {
            "vin": vin,
            "inspection_date": payload.get("inspection_date"),
            "inspection_type": payload.get("inspection_type"),
            "inspection_kind": payload.get("inspection_kind"),
            "odometer_km": payload.get("odometer_km"),
            "protocol_number": payload.get("protocol_number"),
            "result_label": payload.get("result_label"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def parse_tachometer_inspections(search_html: str, vin: str) -> List[ParsedTachometerInspection]:
    section_match = re.search(
        r"Seznam prohl[íi]dek.*?(<table[^>]*>.*?</table>)",
        search_html,
        flags=re.I | re.S,
    )
    section_html = section_match.group(1) if section_match else search_html
    rows = re.findall(r"<tr[^>]*>.*?</tr>", section_html, flags=re.I | re.S)
    inspections: List[ParsedTachometerInspection] = []

    for row_html in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.I | re.S)
        if len(cells) < 5:
            continue

        inspection_date = normalize_inspection_date(_pick_cell(cells, 0))
        inspection_type = normalize_inspection_type(_pick_cell(cells, 1))
        protocol_number = strip_html(_pick_cell(cells, 2)) or None
        inspection_kind = strip_html(_pick_cell(cells, 3)) or None
        odometer_km = normalize_km(_pick_cell(cells, 4))
        if odometer_km is None:
            continue

        note_text = strip_html(_pick_cell(cells, 5)) or None
        result_label = normalize_result(_pick_cell(cells, 6))
        defects_text = normalize_defects(_pick_cell(cells, 7))

        raw_payload = {
            "inspection_date": inspection_date.isoformat() if inspection_date else None,
            "inspection_type": inspection_type,
            "inspection_kind": inspection_kind,
            "odometer_km": odometer_km,
            "protocol_number": protocol_number,
            "result_label": result_label,
            "defects_text": defects_text,
            "note_text": note_text,
            "cells": [strip_html(cell) for cell in cells],
            "row_html": row_html,
        }
        inspections.append(
            ParsedTachometerInspection(
                inspection_date=inspection_date,
                inspection_type=inspection_type,
                inspection_kind=inspection_kind,
                odometer_km=odometer_km,
                protocol_number=protocol_number,
                result_label=result_label,
                defects_text=defects_text,
                note_text=note_text,
                raw_payload_json=raw_payload,
                source_hash=_build_source_hash(vin, raw_payload),
            )
        )

    if any(item.inspection_date is not None for item in inspections):
        inspections.sort(
            key=lambda item: item.inspection_date or datetime.min,
            reverse=True,
        )
    else:
        inspections.sort(key=lambda item: item.odometer_km, reverse=True)

    return inspections
