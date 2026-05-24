from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.core import config as app_config
from src.modules.vehicle_hub.audit_log import write_global_audit_log
from src.modules.vehicle_hub.decoder.models import VehicleDecodedData
from src.modules.vehicle_hub.models import Customer, VehicleCatalogImage
from src.modules.vehicle_hub.services.image_providers.base import (
    VehicleImageProviderAdapter,
    VehicleImageProviderCandidate,
)

try:
    from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
    PILLOW_AVAILABLE = True
except Exception:
    Image = None
    ImageDraw = None
    ImageOps = None
    UnidentifiedImageError = Exception
    PILLOW_AVAILABLE = False

logger = logging.getLogger(__name__)

PLACEHOLDER_URL = "/web/assets/vehicle-placeholder.svg"
LICENSE_NOTE = "Ilustrační katalogová fotka – nejde o skutečnou fotku vozidla."
SAFE_LICENSE_NOTE = "Ilustrační katalogová fotka – nejde o skutečnou fotku konkrétního vozidla."
FAST_ACCEPT_SCORE = 80
FAST_ACCEPT_ALTERNATIVES = 3
CATALOG_STYLE_TOKENS = (
    "official exterior",
    "exterior photo",
    "front",
)
PREFERRED_VIEW_QUERY = "front view exterior"
PREFERRED_VIEW_TOKENS_STRICT = (
    "front three quarter",
    "front 3 4",
    "front 3/4",
    "front view",
    "side front",
    "three quarter front",
    "front side",
    "вид спереди",
    "спереди",
)
REJECTED_VIEW_TOKENS = (
    "rear",
    "back",
    "tailgate",
    "trunk",
    "interior",
    "dashboard",
    "cockpit",
    "зад",
    "сзади",
    "вид сзади",
)
NON_CATALOG_COLOR_TOKENS = (
    "red",
    "blue",
    "green",
    "yellow",
    "orange",
    "brown",
    "beige",
)
COLOR_MAP = {
    "bila": "white",
    "bily": "white",
    "white": "white",
    "cerna": "black",
    "cerny": "black",
    "black": "black",
    "seda": "grey",
    "sedy": "grey",
    "grey": "grey",
    "gray": "grey",
    "stribrna": "silver",
    "stribrny": "silver",
    "silver": "silver",
    "modra": "blue",
    "modry": "blue",
    "blue": "blue",
    "cervena": "red",
    "cerveny": "red",
    "red": "red",
    "zelena": "green",
    "zeleny": "green",
    "green": "green",
    "hneda": "brown",
    "hnedy": "brown",
    "brown": "brown",
    "bezova": "beige",
    "bezovy": "beige",
    "beige": "beige",
    "zluta": "yellow",
    "zluty": "yellow",
    "yellow": "yellow",
    "oranzova": "orange",
    "oranzovy": "orange",
    "orange": "orange",
}

BODY_TYPE_MAP = {
    "combi": "estate",
    "estate": "estate",
    "wagon": "estate",
    "van": "van",
    "dodavka": "van",
    "dodávka": "van",
    "minibus": "minibus",
    "sedan": "sedan",
    "saloon": "sedan",
    "hatchback": "hatchback",
    "suv": "SUV",
}
CANONICAL_MAKE_MAP = {
    "skoda": "skoda",
    "skoda auto": "skoda",
    "škoda": "skoda",
    "vw": "volkswagen",
    "vw group": "volkswagen",
    "volkswagen": "volkswagen",
    "mercedes benz": "mercedes",
    "mercedes-benz": "mercedes",
    "mercedes": "mercedes",
}
CATALOG_IMAGE_STORAGE_DIR = app_config.DATA_DIR / "catalog_vehicle_images"
CATALOG_IMAGE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
CATALOG_IMAGE_TARGET_SIZE = (1280, 720)
CATALOG_IMAGE_OUTPUT_QUALITY = 84
CATALOG_IMAGE_TIMEOUT_SECONDS = 12
LOCAL_CATALOG_ROUTE = "/api/v1/vehicles/catalog-images/{image_id}/file"


@dataclass
class CatalogImageResult:
    ok: bool
    vin: str
    decoded: dict[str, Any] | None
    catalog_image: dict[str, Any]
    alternatives: list[dict[str, Any]]
    warnings: list[str]
    reason: str | None = None


def normalize_vehicle_text(value: str) -> str:
    raw = str(value or "").strip().lower()
    raw = "".join(
        ch for ch in unicodedata.normalize("NFKD", raw)
        if not unicodedata.combining(ch)
    )
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return CANONICAL_MAKE_MAP.get(raw, raw)


def _canonical_make_label(value: str | None) -> str:
    norm = normalize_vehicle_text(value or "")
    mapping = {
        "skoda": "Skoda",
        "volkswagen": "Volkswagen",
        "mercedes": "Mercedes",
    }
    return mapping.get(norm, str(value or "").strip() or "Unknown")


def _body_type_en(value: str | None) -> str | None:
    norm = normalize_vehicle_text(value or "")
    return BODY_TYPE_MAP.get(norm, norm or None)


def _color_en(value: str | None) -> str | None:
    norm = normalize_vehicle_text(value or "")
    if not norm:
        return None
    if norm in COLOR_MAP:
        return COLOR_MAP[norm]
    for token in norm.split():
        if token in COLOR_MAP:
            return COLOR_MAP[token]
    return norm


def build_vehicle_image_queries(decoded_vehicle: VehicleDecodedData | dict[str, Any]) -> list[str]:
    if isinstance(decoded_vehicle, dict):
        make = decoded_vehicle.get("make")
        model = decoded_vehicle.get("model")
        year = decoded_vehicle.get("year")
        body_type = decoded_vehicle.get("body_type")
        preferred_color = decoded_vehicle.get("preferred_color") or decoded_vehicle.get("exterior_color")
    else:
        make = decoded_vehicle.make
        model = decoded_vehicle.model
        year = decoded_vehicle.production_year or decoded_vehicle.model_year
        body_type = decoded_vehicle.body_type
        preferred_color = getattr(decoded_vehicle, "exterior_color", None)

    make_label = _canonical_make_label(make)
    model_label = str(model or "").strip()
    year_label = str(int(year)) if year else ""
    body_en = _body_type_en(body_type)
    colors = app_config.VEHICLE_IMAGE_ALLOWED_COLORS or ["white", "grey"]
    requested_color = _color_en(preferred_color)
    primary_color = requested_color or colors[0]
    secondary_color = colors[1] if len(colors) > 1 else colors[0]

    base_tokens = [token for token in [make_label, model_label, year_label] if token]
    variant_model = model_label
    if body_en == "estate" and "combi" in normalize_vehicle_text(model_label):
        variant_model = model_label
    preferred_view = PREFERRED_VIEW_QUERY
    queries = [
        " ".join(base_tokens + [body_en or "", primary_color, preferred_view, "photo"]).strip(),
        " ".join(base_tokens + [body_en or "", primary_color, "front three quarter exterior photo"]).strip(),
        " ".join(base_tokens + [body_en or "", primary_color, "front 3/4 exterior photo"]).strip(),
    ]
    if secondary_color and secondary_color != primary_color:
        queries.append(" ".join(base_tokens + [body_en or "", secondary_color, preferred_view, "photo"]).strip())
    if body_en == "estate":
        queries.append(" ".join([make_label, variant_model, year_label, "variant", primary_color, preferred_view, "official exterior"]).strip())
    if body_en == "van":
        queries.append(" ".join([make_label, model_label, year_label, "minibus", primary_color, preferred_view, "photo"]).strip())
    return [q for q in dict.fromkeys(q.strip() for q in queries if q.strip())]


def score_image_candidate(candidate: VehicleImageProviderCandidate | dict[str, Any], decoded_vehicle: VehicleDecodedData | dict[str, Any]) -> int:
    if isinstance(candidate, dict):
        cand = VehicleImageProviderCandidate(**candidate)
    else:
        cand = candidate
    if isinstance(decoded_vehicle, dict):
        make = normalize_vehicle_text(decoded_vehicle.get("make") or "")
        model = normalize_vehicle_text(decoded_vehicle.get("model") or "")
        year = decoded_vehicle.get("year")
        body_type = _body_type_en(decoded_vehicle.get("body_type"))
        preferred_color = normalize_vehicle_text(_color_en(decoded_vehicle.get("preferred_color") or decoded_vehicle.get("exterior_color")) or "")
    else:
        make = normalize_vehicle_text(decoded_vehicle.make or "")
        model = normalize_vehicle_text(decoded_vehicle.model or "")
        year = decoded_vehicle.production_year or decoded_vehicle.model_year
        body_type = _body_type_en(decoded_vehicle.body_type)
        preferred_color = normalize_vehicle_text(_color_en(getattr(decoded_vehicle, "exterior_color", None)) or "")

    if not cand.image_url:
        return -100

    text = " ".join(
        [
            str(cand.title or ""),
            str(cand.snippet or ""),
            str(cand.source_url or ""),
            str(cand.source_domain or ""),
        ]
    )
    text_norm = normalize_vehicle_text(text)
    score = 0

    if make and make in text_norm and model and model in text_norm:
        score += 40
    elif make and make in text_norm:
        score += 20

    if year and str(year) in text:
        score += 25
    elif year:
        for candidate_year in (year - 1, year + 1):
            if str(candidate_year) in text:
                score += 12
                break

    if body_type and body_type.lower() in str(cand.title or "").lower() + " " + str(cand.snippet or "").lower():
        score += 20

    if any(_text_has_token(text_norm, token) for token in PREFERRED_VIEW_TOKENS_STRICT):
        score += 28
    if _text_has_any_token(text_norm, REJECTED_VIEW_TOKENS):
        score -= 70

    if any(token in text_norm for token in CATALOG_STYLE_TOKENS):
        score += 10

    catalog_colors = tuple(dict.fromkeys([preferred_color, *(app_config.VEHICLE_IMAGE_ALLOWED_COLORS or []), *COLOR_MAP.values()]))
    color_hit = ""
    for color in catalog_colors:
        if color in text_norm:
            color_hit = color
            break
    if color_hit:
        score += 24 if preferred_color and color_hit == preferred_color else 10
    elif preferred_color:
        score -= 10
    elif any(token in text_norm for token in NON_CATALOG_COLOR_TOKENS):
        score -= 8

    if cand.width and cand.height:
        if cand.width < app_config.VEHICLE_IMAGE_MIN_WIDTH or cand.height < app_config.VEHICLE_IMAGE_MIN_HEIGHT:
            score -= 100
        else:
            score += 10
            ratio = cand.width / max(cand.height, 1)
            if (4 / 3) <= ratio <= (16 / 9):
                score += 10

    penalties = {
        -30: ("interior", "dashboard", "cockpit"),
        -40: ("tuning", "modified", "stance"),
        -50: ("accident", "damaged", "crashed", "spare parts", "parts", "toy", "diecast", "drawing", "render", "cartoon"),
        -70: ("watermark",),
    }
    for delta, tokens in penalties.items():
        if _text_has_any_token(text_norm, tokens):
            score += delta
    return score


def _image_hash(url: str) -> str | None:
    clean = str(url or "").strip()
    if not clean:
        return None
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()


def _text_has_token(text_norm: str, token: str) -> bool:
    token_norm = normalize_vehicle_text(token)
    if not token_norm:
        return False
    return re.search(rf"(^|\s){re.escape(token_norm)}($|\s)", text_norm) is not None


def _text_has_any_token(text_norm: str, tokens: tuple[str, ...]) -> bool:
    return any(_text_has_token(text_norm, token) for token in tokens)


def _placeholder_image(make: str | None = None, model: str | None = None, *, provider: str = "disabled", warning: str | None = None) -> tuple[dict[str, Any], list[str]]:
    warnings = [warning] if warning else []
    provider_label = "disabled" if provider == "disabled" else "placeholder"
    return {
        "id": None,
        "url": PLACEHOLDER_URL,
        "thumbnail_url": PLACEHOLDER_URL,
        "source_domain": None,
        "provider": provider_label,
        "score": 0,
        "representative": True,
        "verified_real_vehicle": False,
        "license_note": LICENSE_NOTE,
    }, warnings


def _build_mock_candidate(decoded: dict[str, Any], *, body_type: str | None = None) -> VehicleImageProviderCandidate:
    make = str(decoded.get("make") or "").strip()
    model = str(decoded.get("model") or "").strip()
    year = decoded.get("year")
    year_label = str(int(year)) if year else ""
    body_label = str(body_type or decoded.get("body_type") or "").strip() or "vehicle"
    title = " ".join(part for part in [make, model, year_label, body_label, "official exterior"] if part).strip()
    snippet = " ".join(part for part in [body_label, "official exterior white", "front three quarter"] if part).strip()
    slug = normalize_vehicle_text(f"{make}-{model}-{year_label or 'vehicle'}") or "vehicle"
    return VehicleImageProviderCandidate(
        title=title,
        image_url=f"https://mock.vehicle-images.local/{slug}.jpg",
        thumbnail_url=f"https://mock.vehicle-images.local/{slug}-thumb.jpg",
        source_url=None,
        source_domain="mock.vehicle-images.local",
        width=1280,
        height=720,
        snippet=snippet,
        provider="mock",
        raw_payload={
            "fixture": "generated-fallback",
            "make": make,
            "model": model,
            "year": year,
            "body_type": body_label,
        },
    )


def _catalog_image_route(image_id: str) -> str:
    return LOCAL_CATALOG_ROUTE.format(image_id=image_id)


def _safe_json_loads(raw: str | None) -> dict[str, Any]:
    try:
        payload = json.loads(str(raw or "").strip() or "{}")
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_catalog_image_storage_file(row: VehicleCatalogImage) -> Path | None:
    payload = _safe_json_loads(getattr(row, "provider_payload_json", None))
    storage_key = str(payload.get("storage_key") or "").strip()
    if not storage_key:
        return None
    candidate = (CATALOG_IMAGE_STORAGE_DIR / storage_key).resolve()
    base = CATALOG_IMAGE_STORAGE_DIR.resolve()
    if not str(candidate).startswith(str(base)):
        return None
    return candidate


def _catalog_image_available(row: VehicleCatalogImage) -> bool:
    path = resolve_catalog_image_storage_file(row)
    return bool(path and path.exists() and path.is_file())


def ensure_catalog_image_storage(row: VehicleCatalogImage, *, db: Session | None = None) -> bool:
    if _catalog_image_available(row):
        return True
    remote_url = str(getattr(row, "image_url", "") or "").strip()
    if not remote_url or remote_url.startswith("/api/v1/vehicles/catalog-images/") or remote_url == PLACEHOLDER_URL:
        return False
    candidate = VehicleImageProviderCandidate(
        title=f"{getattr(row, 'make', '')} {getattr(row, 'model', '')}".strip(),
        image_url=remote_url,
        thumbnail_url=getattr(row, "thumbnail_url", None),
        source_url=getattr(row, "source_url", None),
        source_domain=getattr(row, "source_domain", None),
        provider=getattr(row, "provider", "legacy"),
        raw_payload={},
    )
    safe_content, safe_mime_type, safe_meta = _build_safe_catalog_asset(candidate)
    storage_key = f"{row.id}.jpg"
    storage_file = (CATALOG_IMAGE_STORAGE_DIR / storage_key).resolve()
    storage_file.parent.mkdir(parents=True, exist_ok=True)
    storage_file.write_bytes(safe_content)
    payload = _safe_json_loads(getattr(row, "provider_payload_json", None))
    payload.update(
        {
            "storage_key": storage_key,
            "storage_media_type": safe_mime_type,
            "sanitized": bool(safe_meta.get("sanitized")),
            "redaction": safe_meta.get("redaction"),
            "applied_zones": safe_meta.get("applied_zones") or [],
        }
    )
    row.provider_payload_json = json.dumps(payload, ensure_ascii=False)
    row.thumbnail_url = _catalog_image_route(str(row.id))
    row.image_url = _catalog_image_route(str(row.id))
    row.license_note = SAFE_LICENSE_NOTE
    row.updated_at = datetime.utcnow()
    if db is not None:
        db.flush()
    return True


def _download_remote_catalog_image(url: str) -> tuple[bytes, str]:
    clean_url = str(url or "").strip()
    if not clean_url or not re.match(r"^https?://", clean_url, re.IGNORECASE):
        raise RuntimeError("Katalogová fotka nemá validní vzdálenou HTTP(S) URL.")
    response = requests.get(
        clean_url,
        timeout=CATALOG_IMAGE_TIMEOUT_SECONDS,
        headers={"User-Agent": "SpravaVozidel/1.0 catalog-image-fetch"},
    )
    response.raise_for_status()
    content = response.content or b""
    if not content:
        raise RuntimeError("Stažená katalogová fotka je prázdná.")
    return content, str(response.headers.get("content-type") or "image/jpeg")


def _build_mock_catalog_asset(candidate: VehicleImageProviderCandidate) -> tuple[bytes, str, dict[str, Any]]:
    if not PILLOW_AVAILABLE:
        raise RuntimeError("Mock katalogovou fotku nelze vytvořit bez Pillow.")
    image = Image.new("RGB", CATALOG_IMAGE_TARGET_SIZE, (236, 238, 240))
    draw = ImageDraw.Draw(image)
    width, height = image.size
    draw.rectangle((0, int(height * 0.58), width, height), fill=(203, 208, 214))
    draw.rounded_rectangle(
        (int(width * 0.10), int(height * 0.24), int(width * 0.82), int(height * 0.78)),
        radius=44,
        fill=(248, 249, 250),
        outline=(85, 91, 99),
        width=6,
    )
    draw.polygon(
        [
            (int(width * 0.44), int(height * 0.20)),
            (int(width * 0.68), int(height * 0.20)),
            (int(width * 0.76), int(height * 0.32)),
            (int(width * 0.50), int(height * 0.32)),
        ],
        fill=(220, 225, 230),
        outline=(85, 91, 99),
    )
    draw.rectangle((int(width * 0.16), int(height * 0.60), int(width * 0.28), int(height * 0.74)), fill=(48, 52, 58))
    draw.rectangle((int(width * 0.56), int(height * 0.57), int(width * 0.77), int(height * 0.74)), fill=(42, 45, 51))
    for cx in (0.26, 0.70):
        x = int(width * cx)
        y = int(height * 0.76)
        r = int(height * 0.10)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(44, 47, 52))
        draw.ellipse((x - r // 2, y - r // 2, x + r // 2, y + r // 2), fill=(196, 201, 208))
    draw.rectangle((int(width * 0.58), int(height * 0.69), int(width * 0.72), int(height * 0.75)), fill=(255, 255, 255))
    image, redaction_meta = _apply_catalog_plate_redaction(image)
    output = BytesIO()
    image.save(output, format="JPEG", quality=CATALOG_IMAGE_OUTPUT_QUALITY, optimize=True)
    return output.getvalue(), "image/jpeg", redaction_meta


def _fill_from_sample(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    x1, y1, x2, y2 = box
    sample_box = (
        max(0, x1 - 12),
        max(0, y1 - 12),
        min(image.width, x2 + 12),
        min(image.height, y2 + 12),
    )
    sample = image.crop(sample_box).resize((1, 1))
    rgb = sample.getpixel((0, 0))
    if not isinstance(rgb, tuple):
        return (210, 210, 210)
    return tuple(int(channel) for channel in rgb[:3])


def _apply_catalog_plate_redaction(image: Image.Image) -> tuple[Image.Image, dict[str, Any]]:
    return image, {
        "sanitized": False,
        "redaction": "none_no_overlay_v1",
        "applied_zones": [],
    }


def _build_safe_catalog_asset(candidate: VehicleImageProviderCandidate) -> tuple[bytes, str, dict[str, Any]]:
    if not PILLOW_AVAILABLE:
        raise RuntimeError("Server není připraven bezpečně anonymizovat katalogovou fotku.")
    if candidate.provider == "mock":
        return _build_mock_catalog_asset(candidate)
    content, mime_type = _download_remote_catalog_image(candidate.image_url)
    if mime_type and not mime_type.lower().startswith("image/"):
        raise RuntimeError("Katalogová fotka není obrázek.")
    try:
        with Image.open(BytesIO(content)) as source_image:
            resampling = getattr(Image, "Resampling", Image)
            image = ImageOps.exif_transpose(source_image)
            if image.mode not in {"RGB", "L"}:
                rgba_image = image.convert("RGBA")
                flattened = Image.new("RGB", rgba_image.size, (255, 255, 255))
                flattened.paste(rgba_image, mask=rgba_image.getchannel("A"))
                image = flattened
            elif image.mode == "L":
                image = image.convert("RGB")
            else:
                image = image.copy()
            image = ImageOps.fit(
                image,
                CATALOG_IMAGE_TARGET_SIZE,
                method=resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            image, redaction_meta = _apply_catalog_plate_redaction(image)
            output = BytesIO()
            image.save(
                output,
                format="JPEG",
                quality=CATALOG_IMAGE_OUTPUT_QUALITY,
                optimize=True,
            )
    except UnidentifiedImageError as exc:
        raise RuntimeError("Katalogová fotka je poškozená nebo nepodporovaná.") from exc
    except OSError as exc:
        raise RuntimeError("Katalogovou fotku se nepodařilo bezpečně zpracovat.") from exc
    return output.getvalue(), "image/jpeg", redaction_meta


@lru_cache(maxsize=1)
def _provider_adapter() -> VehicleImageProviderAdapter:
    mode = app_config.VEHICLE_IMAGE_PROVIDER
    if mode == "mock":
        from .image_providers.mock import build_provider
        return build_provider()
    if mode == "searchapi":
        from .image_providers.searchapi import build_provider
        return build_provider()
    if mode == "serpapi":
        from .image_providers.serpapi import build_provider
        return build_provider()
    from .image_providers.disabled import build_provider
    return build_provider()


class VehicleCatalogImageService:
    def __init__(self) -> None:
        self.provider_name = app_config.VEHICLE_IMAGE_PROVIDER

    def preview_from_decoded_vehicle(
        self,
        *,
        db: Session,
        vin: str,
        decoded_vehicle: VehicleDecodedData,
        preferred_color: str | None,
        force_refresh: bool,
        current_user: Customer | None = None,
    ) -> CatalogImageResult:
        warnings: list[str] = []
        normalized_make = normalize_vehicle_text(decoded_vehicle.make or "")
        normalized_model = normalize_vehicle_text(decoded_vehicle.model or "")
        year = decoded_vehicle.production_year or decoded_vehicle.model_year
        body_type = _body_type_en(decoded_vehicle.body_type)
        color_bucket = normalize_vehicle_text(_color_en(preferred_color or getattr(decoded_vehicle, "exterior_color", None)) or "")

        decoded_payload = {
            "make": decoded_vehicle.make,
            "model": decoded_vehicle.model,
            "year": year,
            "body_type": body_type,
            "exterior_color": _color_en(preferred_color or getattr(decoded_vehicle, "exterior_color", None)),
            "source": decoded_vehicle.source_priority[0] if decoded_vehicle.source_priority else "manual-fallback",
        }

        if not normalized_make or not normalized_model:
            fallback, fallback_warnings = _placeholder_image(decoded_vehicle.make, decoded_vehicle.model, provider="disabled", warning="VIN decode returned incomplete make/model; fallback used.")
            warnings.extend(fallback_warnings)
            return CatalogImageResult(ok=True, vin=vin, decoded=decoded_payload, catalog_image=fallback, alternatives=[], warnings=warnings)

        if not force_refresh:
            cached = self._find_cache(
                db=db,
                tenant_id=getattr(current_user, "tenant_id", None),
                normalized_make=normalized_make,
                normalized_model=normalized_model,
                year=year,
                body_type=body_type,
                color_bucket=color_bucket or None,
            )
            if cached is not None and str(getattr(cached, "provider", "") or "").lower() == "mock" and self.provider_name != "mock":
                logger.warning("[CATALOG_IMAGE] cache ignored provider=mock in non-mock mode id=%s", cached.id)
                cached = None
            if cached is not None and (ensure_catalog_image_storage(cached, db=db) or _catalog_image_available(cached)):
                logger.info("[CATALOG_IMAGE] cache hit provider=%s make=%s model=%s", cached.provider, normalized_make, normalized_model)
                self._write_audit(db=db, vin=vin, decoded=decoded_payload, row=cached, current_user=current_user, provider="cache")
                return CatalogImageResult(
                    ok=True,
                    vin=vin,
                    decoded=decoded_payload,
                    catalog_image=self._row_to_payload(cached, provider_override="cache"),
                    alternatives=[],
                    warnings=[],
                )
            if cached is not None:
                logger.warning("[CATALOG_IMAGE] cache stale_missing_file provider=%s id=%s", cached.provider, cached.id)

        logger.info("[CATALOG_IMAGE] cache miss provider=%s make=%s model=%s", self.provider_name, normalized_make, normalized_model)
        if self.provider_name in {"searchapi", "serpapi"} and not app_config.VEHICLE_IMAGE_API_KEY:
            fallback, fallback_warnings = _placeholder_image(
                decoded_vehicle.make,
                decoded_vehicle.model,
                provider=self.provider_name,
                warning="Vehicle image provider API key missing; fallback used.",
            )
            warnings.extend(fallback_warnings)
            return CatalogImageResult(ok=True, vin=vin, decoded=decoded_payload, catalog_image=fallback, alternatives=[], warnings=warnings)

        if self.provider_name == "disabled":
            fallback, _ = _placeholder_image(decoded_vehicle.make, decoded_vehicle.model, provider="disabled")
            return CatalogImageResult(ok=True, vin=vin, decoded=decoded_payload, catalog_image=fallback, alternatives=[], warnings=warnings)

        queries = build_vehicle_image_queries(
            {
                "make": decoded_vehicle.make,
                "model": decoded_vehicle.model,
                "year": year,
                "body_type": body_type,
                "preferred_color": preferred_color or getattr(decoded_vehicle, "exterior_color", None),
                "exterior_color": preferred_color or getattr(decoded_vehicle, "exterior_color", None),
            }
        )
        logger.info("[CATALOG_IMAGE] provider selected=%s query_count=%s", self.provider_name, len(queries))

        candidates: list[tuple[int, VehicleImageProviderCandidate]] = []
        seen_image_urls: set[str] = set()
        try:
            adapter = _provider_adapter()
            for index, query in enumerate(queries):
                logger.info("[CATALOG_IMAGE] query=%s", query)
                provider_candidates = adapter.search(query, limit=app_config.VEHICLE_IMAGE_MAX_RESULTS)
                logger.info("[CATALOG_IMAGE] candidates=%s provider=%s", len(provider_candidates), adapter.name)
                for item in provider_candidates:
                    image_url = str(item.image_url or "").strip()
                    if not image_url or image_url in seen_image_urls:
                        continue
                    seen_image_urls.add(image_url)
                    score = score_image_candidate(
                        item,
                        {
                            "make": decoded_vehicle.make,
                            "model": decoded_vehicle.model,
                            "year": year,
                            "body_type": body_type,
                            "preferred_color": preferred_color,
                        },
                    )
                    candidates.append((score, item))
                if self._should_stop_after_query(index=index, candidates=candidates):
                    logger.info("[CATALOG_IMAGE] early stop provider=%s query_index=%s best_score=%s", adapter.name, index, max(score for score, _ in candidates))
                    break
        except Exception as exc:
            logger.warning("[CATALOG_IMAGE] provider lookup failed provider=%s error=%s", self.provider_name, exc)
            fallback, fallback_warnings = _placeholder_image(
                decoded_vehicle.make,
                decoded_vehicle.model,
                provider=self.provider_name,
                warning=f"Image provider failed; fallback used: {type(exc).__name__}",
            )
            warnings.extend(fallback_warnings)
            return CatalogImageResult(ok=True, vin=vin, decoded=decoded_payload, catalog_image=fallback, alternatives=[], warnings=warnings)

        candidates.sort(key=lambda item: item[0], reverse=True)
        if not candidates or candidates[0][0] < 40:
            logger.info("[CATALOG_IMAGE] fallback reason=low_score best_score=%s", candidates[0][0] if candidates else None)
            fallback, fallback_warnings = _placeholder_image(
                decoded_vehicle.make,
                decoded_vehicle.model,
                provider=self.provider_name,
                warning="No representative candidate reached score threshold; fallback used.",
            )
            warnings.extend(fallback_warnings)
            return CatalogImageResult(ok=True, vin=vin, decoded=decoded_payload, catalog_image=fallback, alternatives=[], warnings=warnings)

        row = None
        best_score = 0
        processing_errors: list[str] = []
        for candidate_score, candidate in candidates:
            if candidate_score < 40:
                break
            try:
                row = self._store_cache_row(
                    db=db,
                    candidate=candidate,
                    score=candidate_score,
                    decoded=decoded_payload,
                    normalized_make=normalized_make,
                    normalized_model=normalized_model,
                    body_type=body_type,
                    color_bucket=color_bucket or None,
                    tenant_id=getattr(current_user, "tenant_id", None),
                )
                best_score = candidate_score
                break
            except Exception as exc:
                source_hint = candidate.source_domain or urlparse(str(candidate.source_url or candidate.image_url or "")).netloc or "unknown"
                logger.warning(
                    "[CATALOG_IMAGE] candidate processing failed provider=%s score=%s source=%s error=%s",
                    self.provider_name,
                    candidate_score,
                    source_hint,
                    exc,
                )
                processing_errors.append(f"{source_hint}: {type(exc).__name__}")
                continue
        if row is None:
            fallback, fallback_warnings = _placeholder_image(
                decoded_vehicle.make,
                decoded_vehicle.model,
                provider=self.provider_name,
                warning="Katalogovou fotku se nepodařilo bezpečně anonymizovat ani z alternativ; použit placeholder.",
            )
            warnings.extend(fallback_warnings)
            if processing_errors:
                logger.warning("[CATALOG_IMAGE] all candidates failed provider=%s errors=%s", self.provider_name, processing_errors[:5])
            return CatalogImageResult(ok=True, vin=vin, decoded=decoded_payload, catalog_image=fallback, alternatives=[], warnings=warnings)
        alternatives: list[dict[str, Any]] = []
        self._write_audit(db=db, vin=vin, decoded=decoded_payload, row=row, current_user=current_user, provider=row.provider)
        logger.info("[CATALOG_IMAGE] winner_score=%s provider=%s", best_score, row.provider)
        return CatalogImageResult(
            ok=True,
            vin=vin,
            decoded=decoded_payload,
            catalog_image=self._row_to_payload(row),
            alternatives=alternatives,
            warnings=warnings,
        )

    def _mock_catalog_result(
        self,
        *,
        db: Session,
        vin: str,
        decoded_payload: dict[str, Any],
        normalized_make: str,
        normalized_model: str,
        body_type: str | None,
        color_bucket: str | None,
        current_user: Customer | None,
        warnings: list[str],
    ) -> CatalogImageResult:
        try:
            mock_candidate = _build_mock_candidate(decoded_payload, body_type=body_type)
            row = self._store_cache_row(
                db=db,
                candidate=mock_candidate,
                score=62,
                decoded=decoded_payload,
                normalized_make=normalized_make,
                normalized_model=normalized_model,
                body_type=body_type,
                color_bucket=color_bucket,
                tenant_id=getattr(current_user, "tenant_id", None),
            )
            self._write_audit(db=db, vin=vin, decoded=decoded_payload, row=row, current_user=current_user, provider="mock")
            return CatalogImageResult(
                ok=True,
                vin=vin,
                decoded=decoded_payload,
                catalog_image=self._row_to_payload(row),
                alternatives=[],
                warnings=warnings,
            )
        except Exception as exc:
            logger.warning("[CATALOG_IMAGE] mock fallback failed error=%s", exc)
            fallback, fallback_warnings = _placeholder_image(
                decoded_payload.get("make"),
                decoded_payload.get("model"),
                provider="placeholder",
                warning="Generování katalogové fotky selhalo i v lokálním fallbacku; použit placeholder.",
            )
            return CatalogImageResult(
                ok=True,
                vin=vin,
                decoded=decoded_payload,
                catalog_image=fallback,
                alternatives=[],
                warnings=warnings + fallback_warnings,
            )

    @staticmethod
    def _should_stop_after_query(*, index: int, candidates: list[tuple[int, VehicleImageProviderCandidate]]) -> bool:
        if not candidates:
            return False
        best_score = max(score for score, _ in candidates)
        strong_candidates = sum(1 for score, _ in candidates if score >= 60)
        if best_score >= 90:
            return True
        if index == 0 and best_score >= FAST_ACCEPT_SCORE and strong_candidates >= FAST_ACCEPT_ALTERNATIVES:
            return True
        return False

    def preview_from_vehicle_snapshot(
        self,
        *,
        db: Session,
        vin: str | None,
        make: str | None,
        model: str | None,
        year: int | None,
        body_type: str | None,
        preferred_color: str | None,
        force_refresh: bool,
        current_user: Customer | None = None,
    ) -> CatalogImageResult:
        decoded_vehicle = VehicleDecodedData(
            vin=vin,
            make=make,
            model=model,
            production_year=year,
            body_type=body_type,
            source_priority=["vehicle_record"],
        )
        return self.preview_from_decoded_vehicle(
            db=db,
            vin=str(vin or ""),
            decoded_vehicle=decoded_vehicle,
            preferred_color=preferred_color,
            force_refresh=force_refresh,
            current_user=current_user,
        )

    def _find_cache(
        self,
        *,
        db: Session,
        tenant_id: int | None,
        normalized_make: str,
        normalized_model: str,
        year: int | None,
        body_type: str | None,
        color_bucket: str | None,
    ) -> VehicleCatalogImage | None:
        now = datetime.utcnow()
        query = db.query(VehicleCatalogImage).filter(
            VehicleCatalogImage.normalized_make == normalized_make,
            VehicleCatalogImage.normalized_model == normalized_model,
            VehicleCatalogImage.year == year,
            VehicleCatalogImage.body_type == body_type,
            VehicleCatalogImage.color_bucket == color_bucket,
            VehicleCatalogImage.score >= 40,
            or_(VehicleCatalogImage.expires_at.is_(None), VehicleCatalogImage.expires_at > now),
            or_(VehicleCatalogImage.tenant_id.is_(None), VehicleCatalogImage.tenant_id == tenant_id),
        )
        if self.provider_name != "mock":
            query = query.filter(VehicleCatalogImage.provider != "mock")
        return query.order_by(VehicleCatalogImage.score.desc(), VehicleCatalogImage.created_at.desc()).first()

    def _store_cache_row(
        self,
        *,
        db: Session,
        candidate: VehicleImageProviderCandidate,
        score: int,
        decoded: dict[str, Any],
        normalized_make: str,
        normalized_model: str,
        body_type: str | None,
        color_bucket: str | None,
        tenant_id: int | None,
    ) -> VehicleCatalogImage:
        now = datetime.utcnow()
        row_id = hashlib.sha256(f"{candidate.provider}:{candidate.image_url}".encode("utf-8")).hexdigest()[:32]
        image_hash = _image_hash(candidate.image_url)
        with db.no_autoflush:
            row = db.query(VehicleCatalogImage).filter(VehicleCatalogImage.id == row_id).first()
            if image_hash:
                row = row or (
                    db.query(VehicleCatalogImage)
                    .filter(
                        VehicleCatalogImage.provider == candidate.provider,
                        VehicleCatalogImage.image_hash == image_hash,
                    )
                    .first()
                )
        is_new_row = row is None
        if row is None:
            row = VehicleCatalogImage(
                id=row_id,
                created_at=now,
            )
        # NOT NULL sloupce (image_url, provider, …) musí být vyplněné před dlouhým stahováním a zpracováním
        # obrázku — SQLAlchemy může před dotazem v relaci spustit autoflush a INSERT by pak měl NULL u image_url.
        stable_route = _catalog_image_route(row.id)
        safe_content, safe_mime_type, safe_meta = _build_safe_catalog_asset(candidate)
        storage_key = f"{row.id}.jpg"
        storage_file = (CATALOG_IMAGE_STORAGE_DIR / storage_key).resolve()
        storage_file.parent.mkdir(parents=True, exist_ok=True)
        storage_file.write_bytes(safe_content)
        row.tenant_id = tenant_id
        row.make = str(decoded.get("make") or "")
        row.model = str(decoded.get("model") or "")
        row.normalized_make = normalized_make
        row.normalized_model = normalized_model
        row.year = decoded.get("year")
        row.year_from = decoded.get("year")
        row.year_to = decoded.get("year")
        row.body_type = body_type
        row.color_bucket = color_bucket
        row.image_url = stable_route
        row.thumbnail_url = stable_route
        row.source_url = candidate.source_url
        row.source_domain = candidate.source_domain or (urlparse(str(candidate.source_url or "")).netloc or None)
        row.provider = str(candidate.provider or "legacy")[:32]
        row.provider_payload_json = json.dumps(
            {
                "storage_key": storage_key,
                "storage_media_type": safe_mime_type,
                "sanitized": bool(safe_meta.get("sanitized")),
                "redaction": safe_meta.get("redaction"),
                "applied_zones": safe_meta.get("applied_zones") or [],
                "provider_payload": candidate.raw_payload or {},
            },
            ensure_ascii=False,
        )
        row.image_hash = image_hash
        row.score = int(score)
        row.is_representative = True
        row.is_verified_real_vehicle = False
        row.license_note = SAFE_LICENSE_NOTE if candidate.provider not in {"disabled"} else LICENSE_NOTE
        row.updated_at = now
        row.expires_at = now + timedelta(days=app_config.VEHICLE_IMAGE_CACHE_TTL_DAYS)
        if is_new_row:
            db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            with db.no_autoflush:
                row = db.query(VehicleCatalogImage).filter(VehicleCatalogImage.id == row_id).first()
                if row is None and image_hash:
                    row = (
                        db.query(VehicleCatalogImage)
                        .filter(
                            VehicleCatalogImage.provider == candidate.provider,
                            VehicleCatalogImage.image_hash == image_hash,
                        )
                        .first()
                    )
            if row is None:
                raise
            row.tenant_id = tenant_id
            row.make = str(decoded.get("make") or "")
            row.model = str(decoded.get("model") or "")
            row.normalized_make = normalized_make
            row.normalized_model = normalized_model
            row.year = decoded.get("year")
            row.year_from = decoded.get("year")
            row.year_to = decoded.get("year")
            row.body_type = body_type
            row.color_bucket = color_bucket
            row.image_url = stable_route
            row.thumbnail_url = stable_route
            row.source_url = candidate.source_url
            row.source_domain = candidate.source_domain or (urlparse(str(candidate.source_url or "")).netloc or None)
            row.provider = str(candidate.provider or "legacy")[:32]
            row.provider_payload_json = json.dumps(
                {
                    "storage_key": storage_key,
                    "storage_media_type": safe_mime_type,
                    "sanitized": bool(safe_meta.get("sanitized")),
                    "redaction": safe_meta.get("redaction"),
                    "applied_zones": safe_meta.get("applied_zones") or [],
                    "provider_payload": candidate.raw_payload or {},
                },
                ensure_ascii=False,
            )
            row.image_hash = image_hash
            row.score = int(score)
            row.is_representative = True
            row.is_verified_real_vehicle = False
            row.license_note = SAFE_LICENSE_NOTE if candidate.provider not in {"disabled"} else LICENSE_NOTE
            row.updated_at = now
            row.expires_at = now + timedelta(days=app_config.VEHICLE_IMAGE_CACHE_TTL_DAYS)
            db.flush()
        return row

    def _row_to_payload(self, row: VehicleCatalogImage, *, provider_override: str | None = None) -> dict[str, Any]:
        return {
            "id": row.id,
            "url": row.image_url,
            "thumbnail_url": row.thumbnail_url,
            "source_domain": row.source_domain,
            "provider": provider_override or row.provider,
            "score": int(row.score or 0),
            "representative": bool(row.is_representative),
            "verified_real_vehicle": bool(row.is_verified_real_vehicle),
            "license_note": row.license_note or LICENSE_NOTE,
        }

    def _write_audit(
        self,
        *,
        db: Session,
        vin: str,
        decoded: dict[str, Any],
        row: VehicleCatalogImage,
        current_user: Customer | None,
        provider: str,
    ) -> None:
        try:
            write_global_audit_log(
                db,
                entity_type="vehicle_catalog_image",
                entity_id=None,
                action="vehicle_catalog_image_preview_generated",
                actor_user_id=getattr(current_user, "id", None),
                actor_role=getattr(current_user, "role", None),
                tenant_id=getattr(current_user, "tenant_id", None),
                metadata={
                    "vin_hash": hashlib.sha256(str(vin or "").upper().encode("utf-8")).hexdigest(),
                    "make": decoded.get("make"),
                    "model": decoded.get("model"),
                    "year": decoded.get("year"),
                    "provider": provider,
                    "image_hash": row.image_hash,
                    "source_domain": row.source_domain,
                    "score": int(row.score or 0),
                    "sanitized": _safe_json_loads(row.provider_payload_json).get("sanitized"),
                    "redaction": _safe_json_loads(row.provider_payload_json).get("redaction"),
                    "user_id": getattr(current_user, "id", None),
                    "tenant_id": getattr(current_user, "tenant_id", None),
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
        except Exception as exc:
            logger.warning("[CATALOG_IMAGE] audit write failed: %s", exc)


@lru_cache(maxsize=1)
def get_vehicle_catalog_image_service() -> VehicleCatalogImageService:
    return VehicleCatalogImageService()
