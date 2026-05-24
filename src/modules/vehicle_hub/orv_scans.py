from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
import unicodedata

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.core.config import DATA_DIR
from .models import Customer, Vehicle as VehicleModel, VehicleORVScan

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except Exception:
    Image = None
    ImageOps = None
    UnidentifiedImageError = Exception

try:
    import pytesseract
except Exception:
    pytesseract = None


ORV_SCANS_DIR = DATA_DIR / "vehicle_orv_scans"
ORV_SCANS_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger(__name__)
MAX_ORV_IMAGE_BYTES = 12 * 1024 * 1024
MAX_ORV_IMAGE_LONG_EDGE = 1800
MAX_ORV_IMAGE_TARGET_BYTES = 1_600_000
OCR_PASS_TIMEOUT_SECONDS = 8
VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b", re.IGNORECASE)
PLATE_RE = re.compile(r"\b(\d[A-Z0-9]{1,2}[A-Z]?\s?\d{4}|[A-Z]{2,3}\s?\d{4})\b", re.IGNORECASE)
DATE_RE = re.compile(r"\b(\d{1,2}[./]\d{1,2}[./]\d{4})\b")
ORV_NUMBER_CONTEXT_RE = re.compile(r"(?:c(?:islo)?\s+orv|osvedceni|osvedceni\s+o\s+registraci|registracni.{0,20})[:\s]*([A-Z0-9]{6,16})", re.IGNORECASE)
ICO_RE = re.compile(r"\bI[ČC]O[:\s]*([0-9]{6,12})\b", re.IGNORECASE)
ENGINE_VOLUME_RE = re.compile(r"\b(\d{2,5})\s*(?:cm3|ccm|cm\^?3|cc)\b", re.IGNORECASE)
POWER_RE = re.compile(r"\b(\d{2,4})\s*k[wvv]\b", re.IGNORECASE)

FRONT_LABELS = {
    "plate": ("registrační značka", "registracni znacka", "rz", "spz"),
    "orv_number": ("číslo orv", "cislo orv", "osvědčení o registraci", "osvedceni o registraci"),
    "first_registration_date": ("datum první registrace", "datum prvni registrace", "první registrace", "prvni registrace"),
    "first_registration_cz_date": ("datum první registrace v čr", "datum prvni registrace v cr", "registrace v cr", "registrace v čr"),
    "owner": ("vlastník", "vlastnik"),
    "operator": ("provozovatel",),
}

BACK_LABELS = {
    "vin": ("vin", "vyrobni cislo vozidla", "identifikacni cislo vozidla"),
    "brand": ("značka", "znacka"),
    "model": ("obchodní označení", "obchodni oznaceni", "model"),
    "type_label": ("typ",),
    "variant": ("varianta",),
    "version": ("verze",),
    "category": ("kategorie",),
    "vehicle_kind": ("druh vozidla",),
    "fuel": ("palivo",),
    "engine_power_kw": ("výkon", "vykon"),
    "engine_displacement_cc": ("objem", "zdvihovy objem"),
}


@dataclass
class ParsedORVResult:
    vehicle_fields: dict[str, Any]
    owner_fields: dict[str, Any]
    confidence_items: list[dict[str, Any]]
    warnings: list[str]
    missing_fields: list[str]
    front_text: str
    back_text: str


@dataclass
class ORVFieldMatch:
    value: str | None
    confidence: float
    state: str
    source: str


def _decode_base64_image(payload: str) -> bytes:
    raw = str(payload or "").strip()
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"ORV obrázek není validní base64 payload: {exc}") from exc
    if not decoded:
        raise HTTPException(status_code=422, detail="ORV obrázek je prázdný.")
    if len(decoded) > MAX_ORV_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Naskenovaný ORV obrázek je příliš velký. Zkuste scan zopakovat s menším výřezem.")
    return decoded


def _normalize_orv_image_bytes(image_bytes: bytes, *, side: str) -> bytes:
    if Image is None:
        return image_bytes
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            normalized = ImageOps.exif_transpose(image) if ImageOps is not None else image
            if getattr(normalized, "mode", "") != "RGB":
                normalized = normalized.convert("RGB")

            width, height = normalized.size
            longest_edge = max(width, height)
            if longest_edge > MAX_ORV_IMAGE_LONG_EDGE:
                scale = MAX_ORV_IMAGE_LONG_EDGE / float(longest_edge)
                resized_dimensions = (
                    max(1, int(round(width * scale))),
                    max(1, int(round(height * scale))),
                )
                resampling = getattr(Image, "Resampling", Image)
                normalized = normalized.resize(resized_dimensions, getattr(resampling, "LANCZOS", 1))

            quality = 84
            optimized = BytesIO()
            normalized.save(optimized, format="JPEG", quality=quality, optimize=True)
            while optimized.tell() > MAX_ORV_IMAGE_TARGET_BYTES and quality > 58:
                quality -= 8
                optimized = BytesIO()
                normalized.save(optimized, format="JPEG", quality=quality, optimize=True)

            return optimized.getvalue()
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=422, detail=f"Soubor pro {side} stranu ORV není platný obrázek.") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"ORV obrázek pro {side} stranu se nepodařilo připravit pro OCR.") from exc


def _extract_ocr_text(image_bytes: bytes, file_name: str, mime_type: str | None) -> str:
    del file_name, mime_type
    if Image is None or pytesseract is None:
        raise HTTPException(status_code=503, detail="OCR zpracování ORV není na serveru dostupné.")
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            normalized = ImageOps.exif_transpose(image) if ImageOps is not None else image
            if getattr(normalized, "mode", "") not in {"RGB", "L"}:
                normalized = normalized.convert("RGB")
            variants = [normalized]
            if ImageOps is not None:
                grayscale = ImageOps.grayscale(normalized)
                variants.append(ImageOps.autocontrast(grayscale))
            texts: list[str] = []
            for variant in variants:
                for config in ("--psm 6", "--psm 11"):
                    try:
                        text = pytesseract.image_to_string(
                            variant,
                            lang="ces+eng",
                            config=config,
                            timeout=OCR_PASS_TIMEOUT_SECONDS,
                        )
                    except RuntimeError as exc:
                        raise HTTPException(
                            status_code=504,
                            detail="OCR zpracování ORV trvalo příliš dlouho. Zkuste pořídit ostřejší a menší scan.",
                        ) from exc
                    cleaned = str(text or "").strip()
                    if cleaned and cleaned not in texts:
                        texts.append(cleaned)
            return "\n".join(texts).strip()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Doklad se nepodařilo správně přečíst.") from exc


def _fold_ascii(value: str) -> str:
    return unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")


def _search_key(value: str) -> str:
    lowered = _fold_ascii(value).lower()
    lowered = lowered.replace("0", "o")
    lowered = lowered.replace("1", "i")
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(lowered.split())


def _normalize_lines(text: str) -> list[str]:
    cleaned = []
    for raw_line in str(text or "").splitlines():
        line = " ".join(raw_line.replace("\xa0", " ").replace("|", " ").split()).strip()
        if line:
            cleaned.append(line)
    return cleaned


def _line_records(text: str) -> list[dict[str, str]]:
    return [
        {
            "text": line,
            "search": _search_key(line),
        }
        for line in _normalize_lines(text)
    ]


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    match = DATE_RE.search(str(value))
    if not match:
        return None
    raw = match.group(1).replace("/", ".")
    parts = raw.split(".")
    if len(parts) != 3:
        return raw
    day, month, year = parts
    return f"{int(day):02d}.{int(month):02d}.{year}"


def _normalize_numeric_field(value: str | None, pattern: re.Pattern[str], unit: str) -> str | None:
    if not value:
        return None
    match = pattern.search(str(value))
    if not match:
        return None
    return f"{int(match.group(1))} {unit}"


def _normalize_plate_value(value: str | None) -> str | None:
    if not value:
        return None
    raw = re.sub(r"[^A-Za-z0-9]", "", str(value).upper())
    raw = raw.replace("O", "0")
    if len(raw) < 6 or len(raw) > 8:
        return None
    if len(raw) > 3:
        return f"{raw[:3]} {raw[3:]}"
    return raw


VIN_TRANSLITERATION = {
    **{str(i): i for i in range(10)},
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
    "E": 5,
    "F": 6,
    "G": 7,
    "H": 8,
    "J": 1,
    "K": 2,
    "L": 3,
    "M": 4,
    "N": 5,
    "P": 7,
    "R": 9,
    "S": 2,
    "T": 3,
    "U": 4,
    "V": 5,
    "W": 6,
    "X": 7,
    "Y": 8,
    "Z": 9,
}
VIN_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]


def _vin_checksum_is_valid(vin: str) -> bool:
    if len(vin) != 17:
        return False
    try:
        total = sum(VIN_TRANSLITERATION[char] * weight for char, weight in zip(vin, VIN_WEIGHTS))
    except KeyError:
        return False
    remainder = total % 11
    expected = "X" if remainder == 10 else str(remainder)
    return vin[8] == expected


def _normalize_vin_candidate(value: str | None) -> tuple[str | None, bool, bool]:
    if not value:
        return None, False, False
    candidate = re.sub(r"[^A-Za-z0-9]", "", str(value).upper())
    if len(candidate) != 17:
        return None, False, False
    corrected = candidate.replace("O", "0").replace("Q", "0").replace("I", "1")
    if not VIN_RE.fullmatch(corrected):
        return None, False, False
    return corrected, corrected != candidate, _vin_checksum_is_valid(corrected)


def _match_from_labeled_line(records: list[dict[str, str]], keywords: tuple[str, ...]) -> tuple[str | None, str]:
    normalized_keywords = tuple(_search_key(keyword) for keyword in keywords)
    for index, record in enumerate(records):
        matched_keyword = next((keyword for keyword in normalized_keywords if keyword in record["search"]), None)
        if not matched_keyword:
            continue
        text = record["text"]
        if ":" in text:
            candidate = text.split(":", 1)[1].strip()
            if candidate:
                return candidate, "labeled_inline"
        search_text = record["search"]
        marker_index = search_text.find(matched_keyword)
        if marker_index >= 0:
            prefix_words = search_text[:marker_index].split()
            matched_words = matched_keyword.split()
            original_words = text.split()
            start_index = len(prefix_words) + len(matched_words)
            if start_index < len(original_words):
                candidate = " ".join(original_words[start_index:]).strip()
                if candidate:
                    return candidate, "labeled_same_line"
        if index + 1 < len(records):
            next_line = records[index + 1]["text"].strip()
            if next_line and not any(keyword in records[index + 1]["search"] for keyword in normalized_keywords):
                return next_line, "labeled_next_line"
    return None, "missing"


def _extract_multiline_block(records: list[dict[str, str]], keywords: tuple[str, ...]) -> tuple[list[str], str]:
    normalized_keywords = tuple(_search_key(keyword) for keyword in keywords)
    for index, record in enumerate(records):
        if not any(keyword in record["search"] for keyword in normalized_keywords):
            continue
        lines: list[str] = []
        current_text = record["text"]
        if ":" in current_text:
            first = current_text.split(":", 1)[1].strip()
            if first:
                lines.append(first)
        cursor = index + 1
        while cursor < len(records):
            next_record = records[cursor]
            if any(label in next_record["search"] for label_group in (FRONT_LABELS.values(), BACK_LABELS.values()) for label in map(_search_key, label_group)):
                break
            next_text = next_record["text"].strip()
            if next_text:
                lines.append(next_text)
            if len(lines) >= 4:
                break
            cursor += 1
        return lines, "multiline_block"
    return [], "missing"


def _score_match(value: str | None, *, labeled: bool = False, validated: bool = False, corrected: bool = False) -> tuple[float, str]:
    if not value:
        return 0.0, "missing"
    confidence = 0.62
    if labeled:
        confidence += 0.18
    if validated:
        confidence += 0.18
    if corrected:
        confidence -= 0.12
    confidence = max(0.2, min(confidence, 0.98))
    return confidence, "high" if confidence >= 0.85 else "review"


def _extract_vin(front_records: list[dict[str, str]], back_records: list[dict[str, str]]) -> ORVFieldMatch:
    for records, source_prefix in ((back_records, "back"), (front_records, "front")):
        raw_value, origin = _match_from_labeled_line(records, BACK_LABELS["vin"])
        value, corrected, checksum_valid = _normalize_vin_candidate(raw_value)
        if value:
            confidence, state = _score_match(
                value,
                labeled=origin != "missing",
                validated=checksum_valid,
                corrected=corrected,
            )
            return ORVFieldMatch(value=value, confidence=confidence, state=state, source=f"{source_prefix}_{origin}")

    combined_text = "\n".join(record["text"] for record in back_records + front_records)
    for candidate in re.findall(r"[A-Z0-9\-/ ]{11,22}", combined_text.upper()):
        value, corrected, checksum_valid = _normalize_vin_candidate(candidate)
        if value:
            confidence, state = _score_match(value, validated=checksum_valid, corrected=corrected)
            return ORVFieldMatch(value=value, confidence=confidence, state=state, source="combined_regex")
    return ORVFieldMatch(value=None, confidence=0.0, state="missing", source="missing")


def _extract_plate(front_records: list[dict[str, str]], back_records: list[dict[str, str]]) -> ORVFieldMatch:
    raw_value, origin = _match_from_labeled_line(front_records, FRONT_LABELS["plate"])
    value = _normalize_plate_value(raw_value)
    if value:
        confidence, state = _score_match(value, labeled=True, validated=True)
        return ORVFieldMatch(value=value, confidence=confidence, state=state, source=f"front_{origin}")

    search_space = "\n".join(record["text"] for record in front_records or back_records)
    match = PLATE_RE.search(search_space.upper())
    value = _normalize_plate_value(match.group(1) if match else None)
    if value:
        confidence, state = _score_match(value, validated=True)
        return ORVFieldMatch(value=value, confidence=confidence, state=state, source="front_regex")
    return ORVFieldMatch(value=None, confidence=0.0, state="missing", source="missing")


def _extract_orv_number(front_records: list[dict[str, str]], back_records: list[dict[str, str]]) -> ORVFieldMatch:
    for records, source_prefix in ((front_records, "front"), (back_records, "back")):
        raw_value, origin = _match_from_labeled_line(records, FRONT_LABELS["orv_number"])
        if raw_value:
            candidate = re.sub(r"[^A-Za-z0-9]", "", raw_value).upper()
            if 6 <= len(candidate) <= 16:
                confidence, state = _score_match(candidate, labeled=True, validated=True)
                return ORVFieldMatch(value=candidate, confidence=confidence, state=state, source=f"{source_prefix}_{origin}")

    combined_text = "\n".join(record["text"] for record in front_records + back_records)
    match = ORV_NUMBER_CONTEXT_RE.search(_search_key(combined_text))
    if match:
        candidate = re.sub(r"[^A-Za-z0-9]", "", match.group(1)).upper()
        if 6 <= len(candidate) <= 16:
            confidence, state = _score_match(candidate, validated=True)
            return ORVFieldMatch(value=candidate, confidence=confidence, state=state, source="combined_regex")
    return ORVFieldMatch(value=None, confidence=0.0, state="missing", source="missing")


def _extract_date_field(records: list[dict[str, str]], keywords: tuple[str, ...], *, fallback_first_date: bool = False) -> ORVFieldMatch:
    raw_value, origin = _match_from_labeled_line(records, keywords)
    normalized = _normalize_date(raw_value)
    if normalized:
        confidence, state = _score_match(normalized, labeled=True, validated=True)
        return ORVFieldMatch(value=normalized, confidence=confidence, state=state, source=origin)
    if fallback_first_date:
        for record in records:
            normalized = _normalize_date(record["text"])
            if normalized:
                confidence, state = _score_match(normalized, validated=True)
                return ORVFieldMatch(value=normalized, confidence=confidence, state=state, source="fallback_first_date")
    return ORVFieldMatch(value=None, confidence=0.0, state="missing", source="missing")


def _extract_generic_label_field(records: list[dict[str, str]], keywords: tuple[str, ...], *, value_normalizer=None) -> ORVFieldMatch:
    raw_value, origin = _match_from_labeled_line(records, keywords)
    value = value_normalizer(raw_value) if value_normalizer else (raw_value.strip() if raw_value else None)
    if value:
        confidence, state = _score_match(value, labeled=True)
        return ORVFieldMatch(value=value, confidence=confidence, state=state, source=origin)
    return ORVFieldMatch(value=None, confidence=0.0, state="missing", source="missing")


def _split_owner_block(block_lines: list[str]) -> tuple[str | None, str | None, str | None]:
    if not block_lines:
        return None, None, None
    lines = [line.strip() for line in block_lines if line.strip()]
    name = lines[0] if lines else None
    identifier = None
    address_lines: list[str] = []
    for line in lines[1:]:
        if identifier is None:
            ico_match = ICO_RE.search(line)
            if ico_match:
                identifier = ico_match.group(1)
                continue
            date_value = _normalize_date(line)
            if date_value:
                identifier = date_value
                continue
        address_lines.append(line)
    address = ", ".join(address_lines) if address_lines else None
    return name, identifier, address


def _confidence_payload(field_name: str, match: ORVFieldMatch) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "confidence": round(float(match.confidence), 3),
        "state": match.state,
    }


def parse_orv_payload(front_text: str, back_text: str) -> ParsedORVResult:
    front_records = _line_records(front_text)
    back_records = _line_records(back_text)
    front_blob = "\n".join(record["text"] for record in front_records)
    back_blob = "\n".join(record["text"] for record in back_records)
    if not front_blob and not back_blob:
        raise HTTPException(status_code=422, detail="Doklad se nepodařilo správně přečíst.")

    vin_match = _extract_vin(front_records, back_records)
    plate_match = _extract_plate(front_records, back_records)
    orv_number_match = _extract_orv_number(front_records, back_records)
    brand_match = _extract_generic_label_field(back_records, BACK_LABELS["brand"])
    model_match = _extract_generic_label_field(back_records, BACK_LABELS["model"])
    type_label_match = _extract_generic_label_field(back_records, BACK_LABELS["type_label"])
    variant_match = _extract_generic_label_field(back_records, BACK_LABELS["variant"])
    version_match = _extract_generic_label_field(back_records, BACK_LABELS["version"])
    category_match = _extract_generic_label_field(back_records, BACK_LABELS["category"])
    vehicle_kind_match = _extract_generic_label_field(back_records, BACK_LABELS["vehicle_kind"])
    fuel_match = _extract_generic_label_field(back_records, BACK_LABELS["fuel"])
    power_match = _extract_generic_label_field(
        back_records,
        BACK_LABELS["engine_power_kw"],
        value_normalizer=lambda value: _normalize_numeric_field(value, POWER_RE, "kW") or (value.strip() if value else None),
    )
    displacement_match = _extract_generic_label_field(
        back_records,
        BACK_LABELS["engine_displacement_cc"],
        value_normalizer=lambda value: _normalize_numeric_field(value, ENGINE_VOLUME_RE, "cm3") or (value.strip() if value else None),
    )
    first_registration_match = _extract_date_field(front_records, FRONT_LABELS["first_registration_date"], fallback_first_date=True)
    first_registration_cz_match = _extract_date_field(front_records, FRONT_LABELS["first_registration_cz_date"])
    seats_match = _extract_generic_label_field(back_records, ("počet míst", "pocet mist"))
    max_speed_match = _extract_generic_label_field(back_records, ("nejvyšší rychlost", "nejvyssi rychlost"))
    emissions_match = _extract_generic_label_field(back_records, ("emise",))
    consumption_match = _extract_generic_label_field(back_records, ("spotřeba", "spotreba"))
    weights_match = _extract_generic_label_field(back_records, ("hmotnost", "hmotnosti"))

    owner_block, owner_block_source = _extract_multiline_block(front_records, FRONT_LABELS["owner"])
    operator_block, operator_block_source = _extract_multiline_block(front_records, FRONT_LABELS["operator"])
    owner_name, owner_identifier, owner_address = _split_owner_block(owner_block)
    operator_name, operator_identifier, operator_address = _split_owner_block(operator_block)
    owner_name_match = ORVFieldMatch(
        value=owner_name,
        confidence=_score_match(owner_name, labeled=bool(owner_block))[0],
        state=_score_match(owner_name, labeled=bool(owner_block))[1],
        source=owner_block_source,
    )
    operator_name_match = ORVFieldMatch(
        value=operator_name,
        confidence=_score_match(operator_name, labeled=bool(operator_block))[0],
        state=_score_match(operator_name, labeled=bool(operator_block))[1],
        source=operator_block_source,
    )
    owner_identifier_match = ORVFieldMatch(
        value=owner_identifier,
        confidence=_score_match(owner_identifier, labeled=bool(owner_block), validated=bool(owner_identifier))[0],
        state=_score_match(owner_identifier, labeled=bool(owner_block), validated=bool(owner_identifier))[1],
        source=owner_block_source,
    )
    operator_identifier_match = ORVFieldMatch(
        value=operator_identifier,
        confidence=_score_match(operator_identifier, labeled=bool(operator_block), validated=bool(operator_identifier))[0],
        state=_score_match(operator_identifier, labeled=bool(operator_block), validated=bool(operator_identifier))[1],
        source=operator_block_source,
    )
    owner_address_match = ORVFieldMatch(
        value=owner_address,
        confidence=_score_match(owner_address, labeled=bool(owner_block))[0],
        state=_score_match(owner_address, labeled=bool(owner_block))[1],
        source=owner_block_source,
    )
    operator_address_match = ORVFieldMatch(
        value=operator_address,
        confidence=_score_match(operator_address, labeled=bool(operator_block))[0],
        state=_score_match(operator_address, labeled=bool(operator_block))[1],
        source=operator_block_source,
    )

    vehicle_fields = {
        "plate": plate_match.value,
        "vin": vin_match.value,
        "brand": brand_match.value,
        "model": model_match.value,
        "type_label": type_label_match.value,
        "variant": variant_match.value,
        "version": version_match.value,
        "commercial_name": model_match.value,
        "category": category_match.value,
        "vehicle_kind": vehicle_kind_match.value,
        "fuel": fuel_match.value,
        "engine_power_kw": power_match.value,
        "engine_displacement_cc": displacement_match.value,
        "first_registration_date": first_registration_match.value,
        "first_registration_cz_date": first_registration_cz_match.value,
        "seats_count": seats_match.value,
        "max_speed_kmh": max_speed_match.value,
        "emissions": emissions_match.value,
        "consumption": consumption_match.value,
        "weights": weights_match.value,
        "orv_number": orv_number_match.value,
    }
    owner_fields = {
        "owner_name": owner_name_match.value,
        "owner_identifier": owner_identifier_match.value,
        "owner_address": owner_address_match.value,
        "operator_name": operator_name_match.value,
        "operator_identifier": operator_identifier_match.value,
        "operator_address": operator_address_match.value,
    }

    confidence_items = [
        _confidence_payload("vin", vin_match),
        _confidence_payload("plate", plate_match),
        _confidence_payload("orv_number", orv_number_match),
        _confidence_payload("brand", brand_match),
        _confidence_payload("model", model_match),
        _confidence_payload("first_registration_date", first_registration_match),
        _confidence_payload("engine_displacement_cc", displacement_match),
        _confidence_payload("engine_power_kw", power_match),
        _confidence_payload("category", category_match),
        _confidence_payload("owner_name", owner_name_match),
        _confidence_payload("owner_identifier", owner_identifier_match),
        _confidence_payload("owner_address", owner_address_match),
        _confidence_payload("operator_name", operator_name_match),
        _confidence_payload("operator_identifier", operator_identifier_match),
        _confidence_payload("operator_address", operator_address_match),
    ]
    missing_fields = [field for field in ("vin", "plate") if not vehicle_fields.get(field)]
    warnings: list[str] = []
    if not vin_match.value:
        warnings.append("VIN se nepodařilo spolehlivě rozpoznat. Vozidlo nelze uložit bez ručního doplnění.")
    if not plate_match.value:
        warnings.append("RZ / SPZ se nepodařilo spolehlivě rozpoznat.")
    if not brand_match.value or brand_match.state != "high" or not model_match.value or model_match.state != "high":
        warnings.append("Značka nebo model nebyly rozpoznány jistě a vyžadují kontrolu.")
    if power_match.state != "missing" and power_match.state != "high":
        warnings.append("Výkon motoru byl rozpoznán nejistě a vyžaduje kontrolu.")
    if displacement_match.state != "missing" and displacement_match.state != "high":
        warnings.append("Objem motoru byl rozpoznán nejistě a vyžaduje kontrolu.")

    return ParsedORVResult(
        vehicle_fields=vehicle_fields,
        owner_fields=owner_fields,
        confidence_items=confidence_items,
        warnings=warnings,
        missing_fields=missing_fields,
        front_text=front_blob,
        back_text=back_blob,
    )


def _safe_file_stem(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "scan")).strip("._-")[:64] or "scan"


def _store_scan_image(*, tenant_id: int, scan_id: int, side: str, content: bytes, mime_type: str | None) -> str:
    del mime_type
    extension = ".jpg"
    relative = Path(f"tenant_{tenant_id}") / f"scan_{scan_id}" / f"{side}{extension}"
    absolute = ORV_SCANS_DIR / relative
    absolute.parent.mkdir(parents=True, exist_ok=True)
    absolute.write_bytes(content)
    return relative.as_posix()


def _compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def create_orv_scan_record(
    *,
    db: Session,
    current_user: Customer,
    front_image_base64: str | None = None,
    back_image_base64: str | None = None,
    front_image_mime_type: str | None = None,
    back_image_mime_type: str | None = None,
    single_orv_image_base64: str | None = None,
    single_orv_image_mime_type: str | None = None,
    source: str | None = None,
) -> VehicleORVScan:
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Uživatel nemá přiřazený tenant.")

    overall_started = time.perf_counter()
    single_raw = (single_orv_image_base64 or "").strip()

    if single_raw:
        decode_started = time.perf_counter()
        raw_bytes = _decode_base64_image(single_raw)
        if not raw_bytes:
            raise HTTPException(status_code=422, detail="ORV snímek je prázdný.")
        decode_duration_ms = round((time.perf_counter() - decode_started) * 1000, 1)

        normalize_started = time.perf_counter()
        front_bytes = _normalize_orv_image_bytes(raw_bytes, side="ORV")
        back_bytes = front_bytes
        normalize_duration_ms = round((time.perf_counter() - normalize_started) * 1000, 1)

        mime_front = str(single_orv_image_mime_type or "image/jpeg").strip() or "image/jpeg"
        mime_back = mime_front

        scan = VehicleORVScan(
            tenant_id=tenant_id,
            initiated_by_customer_id=getattr(current_user, "id", None),
            source=str(source or "ios_orv_scan").strip() or "ios_orv_scan",
            status="processing",
            trust_state="scanned_unverified",
            front_captured=True,
            back_captured=True,
        )
        db.add(scan)
        db.flush()

        scan.front_image_path = _store_scan_image(
            tenant_id=tenant_id,
            scan_id=scan.id,
            side="front",
            content=front_bytes,
            mime_type=mime_front,
        )
        scan.back_image_path = _store_scan_image(
            tenant_id=tenant_id,
            scan_id=scan.id,
            side="back",
            content=back_bytes,
            mime_type=mime_back,
        )
        digest = _compute_sha256(front_bytes)
        scan.front_image_hash = digest
        scan.back_image_hash = digest

        logger.info(
            "[ORV_PARSE] single_card scan_id=%s tenant_id=%s decode_ms=%.1f normalize_ms=%.1f bytes=%s",
            scan.id,
            tenant_id,
            decode_duration_ms,
            normalize_duration_ms,
            len(front_bytes),
        )

        front_ocr_started = time.perf_counter()
        combined = _extract_ocr_text(
            front_bytes,
            f"{_safe_file_stem(scan.source)}_single.jpg",
            mime_front,
        )
        front_ocr_duration_ms = round((time.perf_counter() - front_ocr_started) * 1000, 1)
        back_ocr_duration_ms = 0.0
        # Jedna sada řádků pro obě „strany“ — druhou předáme prázdnou, aby se při výpočtu VIN
        # nezdvojovaly řádky (regex by jinak bral např. „E TMBJF73…“ místo čistého VIN).
        front_text = combined
        back_text = ""
    else:
        decode_started = time.perf_counter()
        front_bytes = _decode_base64_image((front_image_base64 or "").strip())
        back_bytes = _decode_base64_image((back_image_base64 or "").strip())
        if not front_bytes or not back_bytes:
            raise HTTPException(status_code=422, detail="Pro zpracování ORV jsou povinné obě strany dokladu.")
        decode_duration_ms = round((time.perf_counter() - decode_started) * 1000, 1)

        normalize_started = time.perf_counter()
        front_bytes = _normalize_orv_image_bytes(front_bytes, side="přední")
        back_bytes = _normalize_orv_image_bytes(back_bytes, side="zadní")
        normalize_duration_ms = round((time.perf_counter() - normalize_started) * 1000, 1)

        scan = VehicleORVScan(
            tenant_id=tenant_id,
            initiated_by_customer_id=getattr(current_user, "id", None),
            source=str(source or "ios_orv_scan").strip() or "ios_orv_scan",
            status="processing",
            trust_state="scanned_unverified",
            front_captured=True,
            back_captured=True,
        )
        db.add(scan)
        db.flush()

        scan.front_image_path = _store_scan_image(
            tenant_id=tenant_id,
            scan_id=scan.id,
            side="front",
            content=front_bytes,
            mime_type=front_image_mime_type,
        )
        scan.back_image_path = _store_scan_image(
            tenant_id=tenant_id,
            scan_id=scan.id,
            side="back",
            content=back_bytes,
            mime_type=back_image_mime_type,
        )
        scan.front_image_hash = _compute_sha256(front_bytes)
        scan.back_image_hash = _compute_sha256(back_bytes)

        logger.info(
            "[ORV_PARSE] scan_id=%s tenant_id=%s decode_ms=%.1f normalize_ms=%.1f front_bytes=%s back_bytes=%s",
            scan.id,
            tenant_id,
            decode_duration_ms,
            normalize_duration_ms,
            len(front_bytes),
            len(back_bytes),
        )

        front_ocr_started = time.perf_counter()
        front_text = _extract_ocr_text(
            front_bytes,
            f"{_safe_file_stem(scan.source)}_front.jpg",
            front_image_mime_type or "image/jpeg",
        )
        front_ocr_duration_ms = round((time.perf_counter() - front_ocr_started) * 1000, 1)

        back_ocr_started = time.perf_counter()
        back_text = _extract_ocr_text(
            back_bytes,
            f"{_safe_file_stem(scan.source)}_back.jpg",
            back_image_mime_type or "image/jpeg",
        )
        back_ocr_duration_ms = round((time.perf_counter() - back_ocr_started) * 1000, 1)

    parse_started = time.perf_counter()
    parsed = parse_orv_payload(front_text, back_text)
    parse_duration_ms = round((time.perf_counter() - parse_started) * 1000, 1)

    scan.orv_number = parsed.vehicle_fields.get("orv_number")
    scan.front_ocr_text = parsed.front_text
    scan.back_ocr_text = parsed.back_text
    scan.parsed_vehicle_json = json.dumps(parsed.vehicle_fields, ensure_ascii=False)
    scan.parsed_owner_json = json.dumps(parsed.owner_fields, ensure_ascii=False)
    scan.confidence_json = json.dumps(parsed.confidence_items, ensure_ascii=False)
    scan.warnings_json = json.dumps(parsed.warnings, ensure_ascii=False)
    scan.missing_fields_json = json.dumps(parsed.missing_fields, ensure_ascii=False)
    extracted_fields = sorted([key for key, value in {**parsed.vehicle_fields, **parsed.owner_fields}.items() if value])
    scan.extracted_fields_json = json.dumps(extracted_fields, ensure_ascii=False)
    scan.status = "review"
    scan.processed_at = datetime.utcnow()

    db.commit()
    db.refresh(scan)
    total_duration_ms = round((time.perf_counter() - overall_started) * 1000, 1)
    logger.info(
        "[ORV_PARSE] scan_id=%s completed total_ms=%.1f front_ocr_ms=%.1f back_ocr_ms=%.1f parse_ms=%.1f extracted_fields=%s warnings=%s",
        scan.id,
        total_duration_ms,
        front_ocr_duration_ms,
        back_ocr_duration_ms,
        parse_duration_ms,
        len(extracted_fields),
        len(parsed.warnings),
    )
    return scan


def serialize_orv_scan(scan: VehicleORVScan) -> dict[str, Any]:
    def load_json(raw: str | None, fallback: Any) -> Any:
        if not raw:
            return fallback
        try:
            return json.loads(raw)
        except Exception:
            return fallback

    return {
        "scan_id": int(scan.id),
        "trust_state": scan.trust_state or "scanned_unverified",
        "vehicle_fields": load_json(scan.parsed_vehicle_json, {}),
        "owner_fields": load_json(scan.parsed_owner_json, {}),
        "confidence": load_json(scan.confidence_json, []),
        "warnings": load_json(scan.warnings_json, []),
        "missing_fields": load_json(scan.missing_fields_json, []),
    }


def _parsed_year_from_vehicle_fields(vf: dict[str, Any]) -> int | None:
    raw = str(vf.get("first_registration_cz_date") or vf.get("first_registration_date") or "").strip()
    if len(raw) >= 4:
        try:
            y = int(raw[:4])
            if 1900 <= y <= 2100:
                return y
        except ValueError:
            return None
    return None


def _parsed_engine_hint(vf: dict[str, Any]) -> str | None:
    parts: list[str] = []
    if vf.get("fuel"):
        parts.append(str(vf.get("fuel")).strip())
    if vf.get("engine_power_kw"):
        parts.append(f"{vf.get('engine_power_kw')} kW")
    if vf.get("engine_displacement_cc"):
        parts.append(f"{vf.get('engine_displacement_cc')} cm³")
    return " · ".join(parts) if parts else None


def _parsed_nickname_hint(vf: dict[str, Any]) -> str | None:
    for key in ("commercial_name", "type_label", "variant", "model"):
        v = vf.get(key)
        if v and str(v).strip():
            return str(v).strip()
    return None


def _norm_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def apply_orv_review_audit(
    *,
    db: Session,
    scan_id: int,
    current_user: Customer,
    nickname: str | None,
    brand: str | None,
    model: str | None,
    year: int | None,
    engine: str | None,
    vin: str,
    plate: str | None,
    orv_number: str | None,
) -> dict[str, Any]:
    """Uloží audit kontroly ORV před uložením vozidla (OCR + hash už jsou ve scanu)."""
    from .orv_parser import _normalize_vin_candidate

    scan = db.query(VehicleORVScan).filter(VehicleORVScan.id == int(scan_id)).first()
    if scan is None:
        raise HTTPException(status_code=404, detail="ORV scan nebyl nalezen.")
    if getattr(scan, "tenant_id", None) != getattr(current_user, "tenant_id", None):
        raise HTTPException(status_code=403, detail="ORV scan nepatří k vašemu účtu.")
    if getattr(scan, "initiated_by_customer_id", None) != getattr(current_user, "id", None):
        raise HTTPException(status_code=403, detail="ORV scan založil jiný uživatel.")
    if str(scan.status or "") != "review":
        raise HTTPException(status_code=409, detail="ORV scan už není ve stavu kontroly.")
    if scan.vehicle_id is not None:
        raise HTTPException(status_code=409, detail="ORV scan je už navázaný na vozidlo.")

    normalized_vin, vin_errors = _normalize_vin_candidate(str(vin or "").strip())
    if normalized_vin is None:
        raise HTTPException(
            status_code=422,
            detail="; ".join(vin_errors) if vin_errors else "Neplatný VIN.",
        )
    vin_validation: dict[str, Any] = {
        "valid": True,
        "normalized": normalized_vin,
        "errors": [],
        "warnings": list(vin_errors or []),
    }

    parsed_vehicle = json.loads(scan.parsed_vehicle_json or "{}")
    parsed_year = _parsed_year_from_vehicle_fields(parsed_vehicle)

    reviewed_vehicle: dict[str, Any] = {
        "nickname": _norm_optional_str(nickname),
        "brand": _norm_optional_str(brand),
        "model": _norm_optional_str(model),
        "year": year,
        "engine": _norm_optional_str(engine),
        "vin": normalized_vin,
        "plate": _norm_optional_str(plate),
        "orv_number": _norm_optional_str(orv_number),
    }

    field_diffs: dict[str, Any] = {}

    def add_diff_str(key: str, parsed_val: Any, reviewed_val: Any) -> None:
        ps = None if parsed_val is None else str(parsed_val).strip() or None
        rs = None if reviewed_val is None else str(reviewed_val).strip() or None
        if (ps or None) == (rs or None):
            return
        field_diffs[key] = {"parsed": parsed_val, "reviewed": reviewed_val}

    if (parsed_year is None and year is not None) or (parsed_year is not None and year is None) or (
        parsed_year is not None and year is not None and int(parsed_year) != int(year)
    ):
        field_diffs["year"] = {"parsed": parsed_year, "reviewed": year}

    add_diff_str("nickname", _parsed_nickname_hint(parsed_vehicle), reviewed_vehicle["nickname"])
    add_diff_str("brand", parsed_vehicle.get("brand"), reviewed_vehicle["brand"])
    add_diff_str("model", parsed_vehicle.get("model"), reviewed_vehicle["model"])
    add_diff_str("engine", _parsed_engine_hint(parsed_vehicle), reviewed_vehicle["engine"])

    pv_raw = re.sub(r"[^A-Za-z0-9]", "", str(parsed_vehicle.get("vin") or "")).upper()
    if pv_raw != normalized_vin:
        field_diffs["vin"] = {"parsed": parsed_vehicle.get("vin"), "reviewed": normalized_vin}

    add_diff_str("plate", parsed_vehicle.get("plate"), reviewed_vehicle["plate"])
    add_diff_str("orv_number", parsed_vehicle.get("orv_number"), reviewed_vehicle["orv_number"])

    audit_payload = {
        "reviewed_vehicle": reviewed_vehicle,
        "field_diffs": field_diffs,
        "vin_validation": vin_validation,
        "ocr_front_sha256": scan.front_image_hash,
        "ocr_back_sha256": scan.back_image_hash,
        "confirmed_at": datetime.utcnow().isoformat() + "Z",
    }
    scan.orv_review_audit_json = json.dumps(audit_payload, ensure_ascii=False)
    scan.updated_at = datetime.utcnow()
    db.add(scan)
    db.commit()
    db.refresh(scan)

    return {
        "scan_id": int(scan.id),
        "field_diffs": field_diffs,
        "vin_validation": vin_validation,
    }


def apply_orv_scan_to_vehicle(
    *,
    db: Session,
    vehicle: VehicleModel,
    current_user: Customer,
    scan_id: int | None,
    orv_number: str | None,
    use_owner_data: bool,
    data_trust_state: str | None,
    create_payload: dict[str, Any],
) -> None:
    if not scan_id:
        if orv_number is not None:
            vehicle.orv_number = str(orv_number or "").strip() or None
        if data_trust_state:
            vehicle.data_trust_state = data_trust_state
        return

    scan = db.query(VehicleORVScan).filter(VehicleORVScan.id == scan_id).first()
    if scan is None:
        raise HTTPException(status_code=404, detail="ORV scan nebyl nalezen.")
    if getattr(scan, "tenant_id", None) != getattr(vehicle, "tenant_id", None):
        raise HTTPException(status_code=403, detail="ORV scan nepatří do stejného tenantu.")
    if getattr(scan, "initiated_by_customer_id", None) not in {None, getattr(current_user, "id", None)}:
        raise HTTPException(status_code=403, detail="ORV scan patří jinému uživateli.")

    parsed_vehicle = json.loads(scan.parsed_vehicle_json or "{}")
    monitored_fields = ["nickname", "brand", "model", "year", "engine", "vin", "plate", "orv_number"]
    manual_overrides = {}
    for field_name in monitored_fields:
        submitted = create_payload.get(field_name)
        parsed = parsed_vehicle.get(field_name)
        if submitted is None and parsed is None:
            continue
        submitted_normalized = str(submitted).strip() if submitted is not None else None
        parsed_normalized = str(parsed).strip() if parsed is not None else None
        if submitted_normalized != parsed_normalized:
            manual_overrides[field_name] = {
                "parsed": parsed,
                "submitted": submitted,
            }

    vehicle.orv_number = str(orv_number or scan.orv_number or "").strip() or None
    vehicle.orv_scan_source = scan.source
    vehicle.orv_front_image_path = scan.front_image_path
    vehicle.orv_back_image_path = scan.back_image_path
    vehicle.orv_scanned_at = scan.processed_at or scan.created_at
    vehicle.orv_confidence_json = scan.confidence_json
    vehicle.data_trust_state = data_trust_state or "verified_by_user"

    scan.vehicle_id = vehicle.id
    scan.use_owner_data = bool(use_owner_data)
    scan.manual_overrides_json = json.dumps(manual_overrides, ensure_ascii=False)
    scan.status = "confirmed"
    scan.trust_state = data_trust_state or "verified_by_user"
    scan.confirmed_at = datetime.utcnow()

