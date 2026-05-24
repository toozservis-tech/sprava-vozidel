from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Iterable

from .decoder.vin_validator import validate_vin


ORV_SOURCE = "web_orv_scan"

_PLATE_PATTERN = re.compile(r"\b([0-9A-Z]{2,8})\b")
_VIN_PATTERN = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_ORV_NUMBER_PATTERN = re.compile(
    r"(?:CISLO\s+ORV|CISLO\s+OSVEDCENI|OSVEDCENI\s+C\.?|REGISTRACNI\s+DOKLAD)\s*[:\-]?\s*([A-Z0-9]{2,4}\s?[0-9]{5,8})"
)
_ICO_PATTERN = re.compile(r"\b([0-9]{8})\b")
_DATE_PATTERN = re.compile(r"\b([0-3]?\d[./-][0-1]?\d[./-](?:19|20)\d{2})\b")


def _ascii(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return normalized.encode("ascii", "ignore").decode("ascii")


def _clean_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", _ascii(text).upper().replace("\r", "\n"))


def _clean_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in _clean_text(text).splitlines() if line.strip()]


def _next_value_line(lines: list[str], index: int) -> str | None:
    for next_index in range(index + 1, min(len(lines), index + 3)):
        candidate = lines[next_index].strip(" :-")
        if candidate and len(candidate) > 1 and not re.fullmatch(r"[A-Z]\.?([0-9]\.?)*", candidate):
            return candidate
    return None


def _extract_labeled_value(
    lines: list[str],
    *patterns: str,
    fallback_pattern: str | None = None,
    transform=None,
    confidence: float = 0.88,
    fallback_confidence: float = 0.72,
) -> tuple[Any | None, float, str | None]:
    compiled_patterns = [re.compile(pattern) for pattern in patterns]
    for index, line in enumerate(lines):
        for pattern in compiled_patterns:
            match = pattern.match(line)
            if not match:
                continue
            raw = (match.group(1) or "").strip()
            if not raw:
                raw = _next_value_line(lines, index) or ""
            if not raw:
                continue
            value = transform(raw) if transform else raw
            if value in (None, "", []):
                continue
            return value, confidence, "label"
    if fallback_pattern:
        joined = "\n".join(lines)
        fallback_match = re.search(fallback_pattern, joined)
        if fallback_match:
            raw = (fallback_match.group(1) or "").strip()
            value = transform(raw) if transform else raw
            if value not in (None, "", []):
                return value, fallback_confidence, "fallback"
    return None, 0.0, None


def _normalize_plate(value: str | None) -> str | None:
    candidate = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    if not candidate or len(candidate) < 5 or len(candidate) > 8:
        return None
    if not _PLATE_PATTERN.fullmatch(candidate):
        return None
    if len(candidate) == 7:
        return f"{candidate[:3]} {candidate[3:]}"
    return candidate


def _normalize_orv_number(value: str | None) -> str | None:
    candidate = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    if len(candidate) < 6:
        return None
    if len(candidate) in {7, 8, 9, 10}:
        return candidate
    return None


def _normalize_vin_candidate(value: str | None) -> tuple[str | None, list[str]]:
    candidate = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    if not candidate:
        return None, []
    if len(candidate) != 17:
        return None, ["VIN nemá 17 znaků."]
    if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", candidate):
        return None, ["VIN obsahuje nepovolené znaky."]
    is_valid, errors = validate_vin(candidate)
    if is_valid:
        return candidate, []
    non_checksum_errors = [error for error in errors if "checksum" not in error.lower()]
    if non_checksum_errors:
        return None, non_checksum_errors
    return candidate, errors


def _normalize_date(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    match = _DATE_PATTERN.search(raw)
    if match:
        return _normalize_date(match.group(1))
    return None


def _normalize_int(value: str | None) -> int | None:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _normalize_name(value: str | None) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" ,;-")
    return text or None


def _normalize_address(value: str | None) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" ,;-")
    if not text or len(text) < 4:
        return None
    return text


def _guess_identifier(lines: Iterable[str], block_hint: str) -> str | None:
    joined = "\n".join(lines)
    block_match = re.search(block_hint, joined)
    if not block_match:
        return None
    block = block_match.group(0)
    date_match = _DATE_PATTERN.search(block)
    if date_match:
        return _normalize_date(date_match.group(1))
    ico_match = _ICO_PATTERN.search(block)
    if ico_match:
        return ico_match.group(1)
    return None


def _fallback_line_value(lines: list[str], pattern: str, *, transform=None, confidence: float = 0.66) -> tuple[Any | None, float]:
    joined = "\n".join(lines)
    match = re.search(pattern, joined)
    if not match:
        return None, 0.0
    value = (match.group(1) or "").strip()
    if not value:
        return None, 0.0
    transformed = transform(value) if transform else value
    if transformed in (None, "", []):
        return None, 0.0
    return transformed, confidence


def parse_czech_orv_texts(front_text: str, back_text: str) -> dict[str, Any]:
    front_lines = _clean_lines(front_text)
    back_lines = _clean_lines(back_text)
    all_lines = front_lines + back_lines

    warnings: list[str] = []
    missing_fields: list[str] = []
    vehicle: dict[str, Any] = {}
    owner: dict[str, Any] = {
        "owner": {"name": None, "identifier": None, "address": None},
        "operator": {"name": None, "identifier": None, "address": None},
    }
    vehicle_confidence: dict[str, float] = {}
    owner_confidence: dict[str, float] = {}
    document_confidence: dict[str, float] = {}

    plate, plate_conf, _ = _extract_labeled_value(
        front_lines,
        r"^(?:A|REGISTRACNI ZNACKA|STATNI POZNAVACI ZNACKA)\s*[:\-]?\s*(.+)$",
        fallback_pattern=r"(?:^|\n)([0-9][A-Z0-9]{1,2}\s?[0-9]{4}|\d[A-Z]{2}\s?\d{4})\b",
        transform=_normalize_plate,
    )
    if plate:
        vehicle["plate"] = plate
        vehicle_confidence["plate"] = plate_conf
    else:
        missing_fields.append("plate")

    orv_number, orv_number_conf, _ = _extract_labeled_value(
        front_lines,
        r"^(?:CISLO ORV|CISLO OSVEDCENI|OSVEDCENI C\.?|CISLO DOKLADU)\s*[:\-]?\s*(.+)$",
        fallback_pattern=_ORV_NUMBER_PATTERN.pattern,
        transform=_normalize_orv_number,
        confidence=0.86,
        fallback_confidence=0.69,
    )
    if orv_number:
        document_confidence["orv_number"] = orv_number_conf

    vin, vin_conf, _ = _extract_labeled_value(
        back_lines,
        r"^(?:E|VIN|IDENTIFIKACNI CISLO VOZIDLA)\s*[:\-]?\s*(.+)$",
        fallback_pattern=_VIN_PATTERN.pattern,
        transform=lambda raw: _normalize_vin_candidate(raw)[0],
        confidence=0.92,
        fallback_confidence=0.78,
    )
    vin_validation_warnings: list[str] = []
    if vin:
        vin, vin_validation_warnings = _normalize_vin_candidate(vin)
    if vin:
        vehicle["vin"] = vin
        vehicle_confidence["vin"] = vin_conf
    else:
        missing_fields.append("vin")
    warnings.extend(vin_validation_warnings)

    brand, brand_conf, _ = _extract_labeled_value(
        back_lines,
        r"^(?:D\.?1|ZNACKA|VYROBCE)\s*[:\-]?\s*(.+)$",
        transform=_normalize_name,
    )
    if brand:
        vehicle["brand"] = brand.title()
        vehicle_confidence["brand"] = brand_conf

    model, model_conf, _ = _extract_labeled_value(
        back_lines,
        r"^(?:D\.?3|OBCHODNI OZNACENI|MODEL)\s*[:\-]?\s*(.+)$",
        fallback_pattern=r"(?:OBCHODNI OZNACENI|MODEL)\s*[:\-]?\s*([A-Z0-9 .\-]{2,80})",
        transform=_normalize_name,
    )
    if model:
        vehicle["model"] = model.title()
        vehicle_confidence["model"] = model_conf

    type_label, type_conf, _ = _extract_labeled_value(
        back_lines,
        r"^(?:D\.?2|TYP VARIANTA VERZE|TYP)\s*[:\-]?\s*(.+)$",
        transform=_normalize_name,
        confidence=0.82,
    )
    if type_label:
        vehicle["type"] = type_label
        vehicle_confidence["type"] = type_conf

    first_registration_date, first_reg_conf, _ = _extract_labeled_value(
        front_lines,
        r"^(?:B\.?1|B|I|DATUM PRVNI REGISTRACE|DATUM PRVNI REGISTRACE VOZIDLA)\s*[:\-]?\s*(.+)$",
        fallback_pattern=r"(?:DATUM PRVNI REGISTRACE|PRVNI REGISTRACE)\s*[:\-]?\s*([0-3]?\d[./-][0-1]?\d[./-](?:19|20)\d{2})",
        transform=_normalize_date,
        confidence=0.84,
        fallback_confidence=0.7,
    )
    if first_registration_date:
        vehicle["first_registration_date"] = first_registration_date
        vehicle_confidence["first_registration_date"] = first_reg_conf
        try:
            vehicle["year"] = int(first_registration_date[:4])
            vehicle_confidence["year"] = max(first_reg_conf - 0.04, 0.5)
        except Exception:
            pass

    category, category_conf, _ = _extract_labeled_value(
        back_lines,
        r"^(?:J|KATEGORIE VOZIDLA)\s*[:\-]?\s*(.+)$",
        transform=_normalize_name,
    )
    if category:
        vehicle["category"] = category
        vehicle_confidence["category"] = category_conf

    fuel, fuel_conf, _ = _extract_labeled_value(
        back_lines,
        r"^(?:P\.?3|PALIVO|DRUH PALIVA)\s*[:\-]?\s*(.+)$",
        transform=_normalize_name,
    )
    if fuel:
        vehicle["fuel"] = fuel.title()
        vehicle_confidence["fuel"] = fuel_conf

    power_kw, power_conf, _ = _extract_labeled_value(
        back_lines,
        r"^(?:P\.?2|VYKON|MAXIMALNI VYKON)\s*[:\-]?\s*(.+)$",
        transform=_normalize_int,
    )
    if power_kw is not None:
        vehicle["power_kw"] = power_kw
        vehicle_confidence["power_kw"] = power_conf

    engine_cc, engine_conf, _ = _extract_labeled_value(
        back_lines,
        r"^(?:P\.?1|OBJEM|ZDVIHOVY OBJEM)\s*[:\-]?\s*(.+)$",
        transform=_normalize_int,
    )
    if engine_cc is not None:
        vehicle["engine_displacement_cc"] = engine_cc
        vehicle_confidence["engine_displacement_cc"] = engine_conf

    seats, seats_conf, _ = _extract_labeled_value(
        back_lines,
        r"^(?:S\.?1|POCET MIST)\s*[:\-]?\s*(.+)$",
        transform=_normalize_int,
        confidence=0.8,
    )
    if seats is not None:
        vehicle["seats"] = seats
        vehicle_confidence["seats"] = seats_conf

    max_speed, max_speed_conf, _ = _extract_labeled_value(
        back_lines,
        r"^(?:T|NEJVYSSI RYCHLOST)\s*[:\-]?\s*(.+)$",
        transform=_normalize_int,
        confidence=0.76,
    )
    if max_speed is not None:
        vehicle["max_speed_kph"] = max_speed
        vehicle_confidence["max_speed_kph"] = max_speed_conf

    emission, emission_conf, _ = _extract_labeled_value(
        back_lines,
        r"^(?:V\.?9|EMISNI PREDPIS|EMISE)\s*[:\-]?\s*(.+)$",
        transform=_normalize_name,
        confidence=0.74,
    )
    if emission:
        vehicle["emission_standard"] = emission
        vehicle_confidence["emission_standard"] = emission_conf

    gross_weight, gross_conf, _ = _extract_labeled_value(
        back_lines,
        r"^(?:F\.?1|NEJVYSSI POVOLENA HMOTNOST)\s*[:\-]?\s*(.+)$",
        transform=_normalize_int,
        confidence=0.72,
    )
    if gross_weight is not None:
        vehicle["gross_weight_kg"] = gross_weight
        vehicle_confidence["gross_weight_kg"] = gross_conf

    curb_weight, curb_conf, _ = _extract_labeled_value(
        back_lines,
        r"^(?:G|PROVOZNI HMOTNOST)\s*[:\-]?\s*(.+)$",
        transform=_normalize_int,
        confidence=0.72,
    )
    if curb_weight is not None:
        vehicle["curb_weight_kg"] = curb_weight
        vehicle_confidence["curb_weight_kg"] = curb_conf

    owner_name, owner_name_conf, _ = _extract_labeled_value(
        front_lines,
        r"^(?:C\.?1\.?1|VLASTNIK(?: / MAJITEL)?|VLASTNIK JMENO)\s*[:\-]?\s*(.+)$",
        transform=_normalize_name,
        confidence=0.81,
    )
    if owner_name:
        owner["owner"]["name"] = owner_name.title()
        owner_confidence["owner.name"] = owner_name_conf

    owner_address, owner_address_conf, _ = _extract_labeled_value(
        front_lines,
        r"^(?:C\.?1\.?3|ADRESA VLASTNIKA|SIDLO VLASTNIKA)\s*[:\-]?\s*(.+)$",
        transform=_normalize_address,
        confidence=0.78,
    )
    if owner_address:
        owner["owner"]["address"] = owner_address.title()
        owner_confidence["owner.address"] = owner_address_conf

    operator_name, operator_name_conf, _ = _extract_labeled_value(
        front_lines,
        r"^(?:C\.?2\.?1|PROVOZOVATEL(?: / UZIVATEL)?|PROVOZOVATEL JMENO)\s*[:\-]?\s*(.+)$",
        transform=_normalize_name,
        confidence=0.81,
    )
    if operator_name:
        owner["operator"]["name"] = operator_name.title()
        owner_confidence["operator.name"] = operator_name_conf

    operator_address, operator_address_conf, _ = _extract_labeled_value(
        front_lines,
        r"^(?:C\.?2\.?3|ADRESA PROVOZOVATELE|SIDLO PROVOZOVATELE)\s*[:\-]?\s*(.+)$",
        transform=_normalize_address,
        confidence=0.78,
    )
    if operator_address:
        owner["operator"]["address"] = operator_address.title()
        owner_confidence["operator.address"] = operator_address_conf

    if owner["owner"]["name"] and not owner["owner"]["identifier"]:
        owner["owner"]["identifier"] = _guess_identifier(
            front_lines,
            r"C\.?1.*?(?=C\.?2|D\.?1|$)",
        )
        if owner["owner"]["identifier"]:
            owner_confidence["owner.identifier"] = 0.68

    if owner["operator"]["name"] and not owner["operator"]["identifier"]:
        owner["operator"]["identifier"] = _guess_identifier(
            front_lines,
            r"C\.?2.*?(?=D\.?1|E|$)",
        )
        if owner["operator"]["identifier"]:
            owner_confidence["operator.identifier"] = 0.68

    if not owner["owner"]["name"]:
        fallback_owner_name, fallback_conf = _fallback_line_value(
            front_lines,
            r"VLASTNIK(?: / MAJITEL)?\s*[:\-]?\s*([A-Z0-9 .,\-]{4,80})",
            transform=_normalize_name,
            confidence=0.63,
        )
        if fallback_owner_name:
            owner["owner"]["name"] = fallback_owner_name.title()
            owner_confidence["owner.name"] = fallback_conf

    if not owner["operator"]["name"]:
        fallback_operator_name, fallback_conf = _fallback_line_value(
            front_lines,
            r"PROVOZOVATEL(?: / UZIVATEL)?\s*[:\-]?\s*([A-Z0-9 .,\-]{4,80})",
            transform=_normalize_name,
            confidence=0.63,
        )
        if fallback_operator_name:
            owner["operator"]["name"] = fallback_operator_name.title()
            owner_confidence["operator.name"] = fallback_conf

    if not vehicle.get("brand") and vehicle.get("model"):
        vehicle["brand"] = vehicle["model"].split(" ", 1)[0]
        vehicle_confidence["brand"] = 0.42
        warnings.append("Značka vozidla byla jen odhadnuta z obchodního označení.")

    if vehicle.get("brand") and not vehicle.get("model"):
        vehicle["model"] = vehicle.get("type") or None
        if vehicle["model"]:
            vehicle_confidence["model"] = 0.41
            warnings.append("Model vozidla byl odhadnut z pole typ/varianta/verze.")

    low_confidence_fields = [
        field_name
        for field_name, score in {
            **vehicle_confidence,
            **owner_confidence,
            **document_confidence,
        }.items()
        if score and score < 0.65
    ]

    if not orv_number:
        missing_fields.append("orv_number")
        warnings.append("Číslo ORV se nepodařilo spolehlivě přečíst.")

    if not vehicle.get("plate"):
        warnings.append("Registrační značka chybí nebo není jistá. Před uložením ji doplňte ručně.")

    if not vehicle.get("vin"):
        warnings.append("VIN se nepodařilo spolehlivě přečíst. Vozidlo nepůjde uložit bez ručního doplnění VIN.")

    if low_confidence_fields:
        warnings.append("Některá pole mají nižší jistotu OCR. Označené údaje před uložením zkontrolujte.")

    combined_confidences = [
        value
        for value in list(vehicle_confidence.values()) + list(owner_confidence.values()) + list(document_confidence.values())
        if value > 0
    ]
    overall_confidence = round(sum(combined_confidences) / len(combined_confidences), 2) if combined_confidences else 0.0

    document_metadata = {
        "document_type": "czech_orv",
        "source": ORV_SOURCE,
        "orv_number": orv_number,
        "front_text_length": len("\n".join(front_lines)),
        "back_text_length": len("\n".join(back_lines)),
    }

    return {
        "document": document_metadata,
        "vehicle": vehicle,
        "owner": owner,
        "confidence": {
            "overall": overall_confidence,
            "vehicle_fields": vehicle_confidence,
            "owner_fields": owner_confidence,
            "document_fields": document_confidence,
            "low_confidence_fields": low_confidence_fields,
        },
        "warnings": list(dict.fromkeys(warnings)),
        "missing_fields": list(dict.fromkeys(missing_fields)),
        "ocr": {
            "front_text": "\n".join(front_lines),
            "back_text": "\n".join(back_lines),
        },
    }
