"""
Služba pro dynamické URL náhledů vozidel (make / model / year).

Architektura: řetěz poskytovatelů — primárně Unsplash, volitelná šablona URL pro placená API,
fallback na veřejný placeholder. Konfigurace přes .env (viz src.core.config).
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import List, Optional, Protocol, Tuple
from urllib.parse import quote_plus

import requests

from src.core import config as app_config

logger = logging.getLogger(__name__)

UNSPLASH_SEARCH_URL = "https://api.unsplash.com/search/photos"


@dataclass
class VehicleImageResult:
    url: str
    provider: str
    photographer_name: Optional[str] = None
    photographer_url: Optional[str] = None


class VehicleImageProvider(Protocol):
    """Budoucí výměna poskytovatele = nová třída + úprava .env."""

    name: str

    def resolve(
        self, make: str, model: str, year: Optional[int], nickname: str = ""
    ) -> Optional[VehicleImageResult]:
        ...


def _normalize_token(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _simplify_model_for_search(model: str) -> str:
    """Odstraní z modelu objem/motor (1.9 TDI …), které zhoršují shodu ve stock fotobankách."""
    if not model:
        return ""
    t = _normalize_token(model)
    t = re.sub(
        r"\b\d+[.,]\d+\s*(?:TDI|TFSI|TSI|HDI|CDI|MPI|GDI|TD|CR|TCE|BITDI|ECOBLUE|D-?\s*TDI)\b",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(r"\b\d{3,4}\s*(?:TDI|TSI|CDI|HDI)\b", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _vw_t_series_from_year(year: int) -> str:
    """Evropské generace Transporter / Multivan / Caravelle (pro odlišení T1 oproti T5 u stejného názvu)."""
    if year >= 2024:
        return "T7"
    if year >= 2019:
        return "T6.1"
    if year >= 2015:
        return "T6"
    if year >= 2003:
        return "T5"
    if year >= 1990:
        return "T4"
    if year >= 1979:
        return "T3"
    if year >= 1967:
        return "T2"
    return "T1"


def _is_vw_transporter_family(blob: str) -> bool:
    b = blob.lower()
    if not re.search(
        r"\b(transporter|multivan|caravelle|california)\b",
        b,
        flags=re.I,
    ):
        return False
    if re.search(r"\b(vw|volkswagen|v\s*w)\b", b, flags=re.I):
        return True
    # často je značka jen v poli „model“ nebo v přezdívce
    return bool(re.search(r"\b(transporter|multivan|caravelle)\b", b, flags=re.I))


def _search_bias_tokens(
    make: str, model: str, year: Optional[int], nickname: str
) -> List[str]:
    """
    Tokeny pro zpřesnění generace (jinak Unsplash vrací ikonické „retro“ snímky).
    """
    if year is None:
        return []
    y = int(year)
    blob = f"{make} {model} {nickname}".lower()
    out: List[str] = []
    if _is_vw_transporter_family(blob):
        out.append(_vw_t_series_from_year(y))
    elif y >= 2005:
        out.append("modern")
    return out


def build_search_query(
    make: str, model: str, year: Optional[int], nickname: str = ""
) -> str:
    """Dotaz pro Unsplash: značka, zjednodušený model, rok; případně přezdívka, pokud chybí make/model."""
    parts: List[str] = []
    m = _normalize_token(make)
    mo = _simplify_model_for_search(_normalize_token(model))
    nick = _normalize_token(nickname)
    if not m and not mo and nick:
        tokens = nick.split()
        if len(tokens) >= 2:
            m = tokens[0]
            mo = _simplify_model_for_search(" ".join(tokens[1:]))
        else:
            m = nick
    bias = _search_bias_tokens(m, mo, year, nick)
    if m:
        parts.append(m)
    for t in bias:
        if t and t not in parts:
            parts.append(t)
    if mo:
        parts.append(mo)
    if year is not None:
        parts.append(str(int(year)))
    # U dodávek: „studio“ v kombinaci s T5 často 0 výsledků — krátký ocas lépe trefí moderní generace.
    blob_check = f"{m} {mo} {nick}"
    if year is not None and int(year) >= 2000 and _is_vw_transporter_family(blob_check):
        tail = ["van", "white"]
    else:
        tail = ["car", "white", "background", "studio"]
    parts.extend(tail)
    return " ".join(parts) if parts else "car white background studio"


def _unsplash_crop_url(raw_url: str, width: int = 800, height: int = 450) -> str:
    if not raw_url:
        return raw_url
    sep = "&" if "?" in raw_url else "?"
    return f"{raw_url}{sep}w={width}&h={height}&fit=crop&crop=center"


def _unsplash_result_text(item: dict) -> str:
    parts = [item.get("description"), item.get("alt_description")]
    tags = item.get("tags")
    if isinstance(tags, list):
        for t in tags[:12]:
            if isinstance(t, dict) and t.get("title"):
                parts.append(str(t["title"]))
            elif isinstance(t, str):
                parts.append(t)
    return " ".join(str(p) for p in parts if p).lower()


def _score_unsplash_result(
    item: dict,
    *,
    year: Optional[int],
    make_norm: str,
    bias_tokens: List[str],
) -> float:
    """
    Unsplash řadí výsledky slabě — první hit často není správná generace (veterán / jiná značka).
    """
    text = _unsplash_result_text(item)
    score = 0.0
    make_l = (make_norm or "").lower()
    if make_l and ("volkswagen" in make_l or make_l in ("vw", "v w")):
        for wrong in (
            "mercedes",
            "bmw",
            "audi",
            "peugeot",
            "renault",
            "citroën",
            "citroen",
            "ford ",
            "fiat ",
            "toyota",
            "hyundai",
            "iveco",
        ):
            if wrong in text:
                score -= 10.0
    vintage = (
        "1960",
        "1961",
        "1962",
        "1963",
        "1964",
        "1965",
        "1966",
        "1967",
        "1968",
        "1969",
        "1970",
        "1971",
        "1972",
        "1973",
        "1974",
        "1975",
        "westfalia",
        "hippie",
        "kombi",
        "split window",
        "splitty",
        "bulli",
        "bay window",
        "type 2",
        "camper van",
        "vintage vw",
        "classic vw",
        " vw bus",
        " vw camper",
    )
    for v in vintage:
        if v in text:
            score -= 7.0
    if year is not None and int(year) >= 1995:
        y = int(year)
        if str(y) in text:
            score += 8.0
        for y2 in (y - 1, y + 1):
            if str(y2) in text:
                score += 4.0
    for bt in bias_tokens:
        b = (bt or "").lower()
        if b and b in text:
            score += 5.0
    for good in ("t5", "t6.1", "t6", "commercial van", "delivery van", "white van", "transporter"):
        if good in text:
            score += 2.5
    for modern_ctx in ("parking lot", "parking garage", "on the street", "city street", "dealership", "showroom"):
        if modern_ctx in text:
            score += 2.0
    if year is not None and int(year) >= 2003 and bias_tokens:
        for rustic in ("grassy", "dirt road", "in a field", "meadow", "forest road", "camping"):
            if rustic in text:
                score -= 3.0
    if "volkswagen" in text or re.search(r"\bvw\b", text):
        score += 1.5
    return score


class UnsplashVehicleImageProvider:
    name = "unsplash"

    def __init__(
        self,
        access_key: str,
        timeout_sec: float = 8.0,
        dominant_color: Optional[str] = None,
    ) -> None:
        self._access_key = (access_key or "").strip()
        self._timeout_sec = timeout_sec
        self._dominant_color = (dominant_color or "").strip().lower() or None

    def _request_unsplash_results(self, params: dict) -> List[dict]:
        r = requests.get(
            UNSPLASH_SEARCH_URL,
            params=params,
            headers={"Authorization": f"Client-ID {self._access_key}"},
            timeout=self._timeout_sec,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results") if isinstance(data, dict) else None
        if not results:
            return []
        return [x for x in results if isinstance(x, dict)]

    def _fetch_result_batch(self, params: dict) -> List[dict]:
        results = self._request_unsplash_results(params)
        # Úzký filtr color= white často vrátí 0–1 výsledek (špatná fotka) — doplníme širší sadu pro výběr skóre.
        if (
            self._dominant_color
            and "color" in params
            and len(results) < 6
        ):
            p2 = {k: v for k, v in params.items() if k != "color"}
            wider = self._request_unsplash_results(p2)
            if wider:
                results = wider
        elif not results and self._dominant_color and "color" in params:
            p2 = {k: v for k, v in params.items() if k != "color"}
            results = self._request_unsplash_results(p2)
        return results

    def resolve(
        self, make: str, model: str, year: Optional[int], nickname: str = ""
    ) -> Optional[VehicleImageResult]:
        if not self._access_key:
            return None
        query_variants = [
            build_search_query(make, model, year, nickname),
            build_search_query(make, model, None, nickname),
        ]
        # Ještě kratší dotaz (jen značka + první slovo modelu) — např. Transporter dodávka
        m = _normalize_token(make)
        mo = _simplify_model_for_search(_normalize_token(model))
        nick = _normalize_token(nickname)
        if not m and not mo and nick:
            tokens = nick.split()
            if len(tokens) >= 2:
                m = tokens[0]
                mo = _simplify_model_for_search(" ".join(tokens[1:]))
            else:
                m = nick
        mo_words = mo.split()
        bias_short = _search_bias_tokens(m, mo, year, nick)
        if m and mo_words:
            bias_prefix = f"{' '.join(bias_short)} ".strip()
            bias_prefix = f"{bias_prefix} " if bias_prefix else ""
            short = f"{m} {bias_prefix}{mo_words[0]} {year or ''} van white".strip()
            short = re.sub(r"\s+", " ", short)
            if short not in query_variants:
                query_variants.append(short)

        try:
            first = None
            for q in query_variants:
                if not q:
                    continue
                params: dict = {
                    "query": q,
                    "per_page": 15,
                    "orientation": "landscape",
                    "content_filter": "high",
                }
                if self._dominant_color:
                    params["color"] = self._dominant_color
                batch = self._fetch_result_batch(params)
                if not batch:
                    continue
                first = max(
                    batch,
                    key=lambda it: _score_unsplash_result(
                        it,
                        year=year,
                        make_norm=m,
                        bias_tokens=bias_short,
                    ),
                )
                break
            if not first:
                return None
            urls = first.get("urls")
            if not isinstance(urls, dict):
                return None
            raw = urls.get("regular") or urls.get("small")
            if not raw or not isinstance(raw, str):
                return None
            user = first.get("user") if isinstance(first.get("user"), dict) else {}
            pname = user.get("name") if isinstance(user, dict) else None
            plink = user.get("links", {}).get("html") if isinstance(user.get("links"), dict) else None
            return VehicleImageResult(
                url=_unsplash_crop_url(raw),
                provider=self.name,
                photographer_name=str(pname) if pname else None,
                photographer_url=str(plink) if plink else None,
            )
        except requests.RequestException as e:
            logger.warning("Unsplash vehicle image request failed: %s", e)
            return None


class TemplateUrlVehicleImageProvider:
    """
    Obecný poskytovatel pro placená API (IMAGIN.studio, EVOX, …):
    nastavte VEHICLE_IMAGE_URL_TEMPLATE a volitelně VEHICLE_IMAGE_API_KEY.

    Placeholdery v šabloně: {make}, {model}, {year}, {query}, {make_enc}, {model_enc},
    {query_enc}, {api_key}, {api_key_enc}.
    """

    name = "template"

    def __init__(self, url_template: str, api_key: str = "") -> None:
        self._template = (url_template or "").strip()
        self._api_key = (api_key or "").strip()

    def resolve(
        self, make: str, model: str, year: Optional[int], nickname: str = ""
    ) -> Optional[VehicleImageResult]:
        if not self._template:
            return None
        make_raw = _normalize_token(make)
        model_raw = _normalize_token(model)
        year_s = str(int(year)) if year is not None else ""
        q = build_search_query(make, model, year, nickname)
        try:
            url = self._template.format(
                make=make_raw,
                model=model_raw,
                year=year_s,
                query=q,
                make_enc=quote_plus(make_raw),
                model_enc=quote_plus(model_raw),
                query_enc=quote_plus(q),
                api_key=self._api_key,
                api_key_enc=quote_plus(self._api_key) if self._api_key else "",
            )
        except (KeyError, ValueError) as e:
            logger.warning("VEHICLE_IMAGE_URL_TEMPLATE format error: %s", e)
            return None
        return VehicleImageResult(url=url, provider=self.name)


class PlaceholderVehicleImageProvider:
    """Deterministický placeholder (placehold.co) — konzistentní poměr stran."""

    name = "placeholder"

    def __init__(self, width: int = 640, height: int = 360) -> None:
        self._w = width
        self._h = height

    def resolve(
        self, make: str, model: str, year: Optional[int], nickname: str = ""
    ) -> Optional[VehicleImageResult]:
        label_parts = [_normalize_token(make), _normalize_token(model)]
        if year is not None:
            label_parts.append(str(int(year)))
        label = " · ".join(p for p in label_parts if p)
        if not label and _normalize_token(nickname):
            label = _normalize_token(nickname)
        if not label:
            label = "Vozidlo"
        seed = hashlib.sha256(label.encode("utf-8")).hexdigest()[:12]
        text = quote_plus(label[:42])
        bg = "e2e8f0"
        fg = "475569"
        url = (
            f"https://placehold.co/{self._w}x{self._h}/{bg}/{fg}/png?text={text}&font=source-sans-pro"
        )
        return VehicleImageResult(url=f"{url}&s={seed}", provider=self.name)


class VehicleImageService:
    """Orchestruje poskytovatele podle VEHICLE_IMAGE_PROVIDER."""

    def __init__(
        self,
        providers: List[VehicleImageProvider],
        *,
        cache_max: int = 320,
    ) -> None:
        self._providers = providers
        self._cache: "OrderedDict[Tuple[str, str, Optional[int], str], VehicleImageResult]" = OrderedDict()
        self._cache_max = max(8, int(cache_max))

    def _cache_key(
        self, make: str, model: str, year: Optional[int], nickname: str = ""
    ) -> Tuple[str, str, Optional[int], str]:
        y = int(year) if year is not None else None
        return (
            _normalize_token(make).lower(),
            _normalize_token(model).lower(),
            y,
            _normalize_token(nickname).lower(),
        )

    @classmethod
    def from_config(cls) -> VehicleImageService:
        mode = (getattr(app_config, "VEHICLE_IMAGE_PROVIDER", None) or "unsplash").strip().lower()
        unsplash_key = (getattr(app_config, "UNSPLASH_ACCESS_KEY", None) or "").strip()
        tmpl = (getattr(app_config, "VEHICLE_IMAGE_URL_TEMPLATE", None) or "").strip()
        api_key = (getattr(app_config, "VEHICLE_IMAGE_API_KEY", None) or "").strip()
        us_color = (getattr(app_config, "VEHICLE_IMAGE_UNSPLASH_COLOR", None) or "").strip() or None

        chain: List[VehicleImageProvider] = []

        if mode == "placeholder":
            return cls([PlaceholderVehicleImageProvider()])

        if mode == "template":
            if tmpl:
                chain.append(TemplateUrlVehicleImageProvider(tmpl, api_key))
            if unsplash_key:
                chain.append(UnsplashVehicleImageProvider(unsplash_key, dominant_color=us_color))
        else:
            # výchozí unsplash + auto: nejdřív Unsplash, poté volitelná šablona (např. záložní CDN)
            if unsplash_key:
                chain.append(UnsplashVehicleImageProvider(unsplash_key, dominant_color=us_color))
            if tmpl:
                chain.append(TemplateUrlVehicleImageProvider(tmpl, api_key))

        chain.append(PlaceholderVehicleImageProvider())
        return cls(chain)

    def resolve(
        self, make: str, model: str, year: Optional[int], nickname: str = ""
    ) -> VehicleImageResult:
        key = self._cache_key(make, model, year, nickname)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        for p in self._providers:
            try:
                out = p.resolve(make, model, year, nickname)
                if out and out.url:
                    self._cache[key] = out
                    self._cache.move_to_end(key)
                    while len(self._cache) > self._cache_max:
                        self._cache.popitem(last=False)
                    return out
            except Exception as e:
                logger.warning("Vehicle image provider %s error: %s", getattr(p, "name", type(p)), e)
        fallback = PlaceholderVehicleImageProvider().resolve(make, model, year, nickname)
        assert fallback is not None
        self._cache[key] = fallback
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)
        return fallback


_default_service: Optional[VehicleImageService] = None


def get_vehicle_image_service() -> VehicleImageService:
    global _default_service
    if _default_service is None:
        _default_service = VehicleImageService.from_config()
    return _default_service
