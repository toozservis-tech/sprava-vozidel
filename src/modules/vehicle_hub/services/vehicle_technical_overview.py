"""
Strukturovaný technický přehled vozidla ze zdrojů MDČR + lokální VIN + základní pole Vehicle.

API „Data“ z MDČR je typicky plochý slovník s PascalCase českými klíči — viz dokumentace / odezvy api.dataovozidlech.cz.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from src.modules.vehicle_hub.decoder.vin_decoder import decode_vin_local
from src.modules.vehicle_hub.decoder.mdcr_client import fetch_mdcr_vehicle_raw_data_sync

logger = logging.getLogger(__name__)

OVERVIEW_VERSION = 3


def flatten_key_paths(data: Any, prefix: str = "") -> List[str]:
    """
    Rekurzivně vrátí cesty ke všem listům uzlům ve struktuře (dict/list/scalars jako listy cesty ukončuje scalarů).
    Formát: a.b.c, pole[k].
    """
    paths: List[str] = []

    def _walk(obj: Any, pre: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                seg = f"{pre}.{k}" if pre else str(k)
                if isinstance(v, (dict, list)):
                    _walk(v, seg)
                else:
                    paths.append(seg)
        elif isinstance(obj, list):
            for idx, it in enumerate(obj):
                seg = f"{pre}[{idx}]"
                if isinstance(it, (dict, list)):
                    _walk(it, seg)
                else:
                    paths.append(seg)
        else:
            if pre:
                paths.append(pre)

    _walk(data, prefix)
    return paths


def _ascii_fold(s: str) -> str:
    """Porovnání klíčů bez diakritiky, jen základní znaky."""
    nk = unicodedata.normalize("NFKD", str(s))
    return "".join(c.lower() for c in nk if not unicodedata.combining(c))


def _norm_cmp_token(k: str) -> str:
    """Číslo alfanumerické porovnání klíče bez interpunkce."""
    return "".join(c.lower() for c in str(k) if c.isalnum())


def _is_placeholder_noise(val: Any) -> bool:
    """Prázdné kombinace typu ' /  / ', jen '/', jen pomlčky."""
    if val is None:
        return True
    if isinstance(val, (list, dict)) and not val:
        return True
    s = str(val).strip()
    if not s:
        return True
    # jen oddělovače a mezery, bez číslic ani slabiky/písmen — výjimku drží NE/NANO apod.
    if re.fullmatch(r"[\s/\-.:]+", s):
        return True
    if not any(ch.isalnum() for ch in s):
        return True
    return False


def _present(val: Any) -> bool:
    """Má smysl hodnotu zobrazit (včetně 0, NE, False jako platných)."""
    if val is None:
        return False
    if isinstance(val, bool):
        return True
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return True
    if _is_placeholder_noise(val):
        return False
    return True


def _format_iso_timestamp_or_date_display(val: Any) -> str:
    """Technické řetězce začínající YYYY-MM-DD → DD.MM.RRRR (ne složené hodnoty jako CO2)."""
    if val is None:
        return ""
    s = str(val).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        return s
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return f"{d:02d}.{mo:02d}.{y}"


def _scalar_display(val: Any) -> str:
    if isinstance(val, bool):
        return "ANO" if val else "NE"
    if isinstance(val, float):
        if abs(val - round(val)) < 1e-9:
            base = str(int(round(val)))
        else:
            base = str(val).rstrip("0").rstrip(".")
        return base
    base = str(val).strip()
    return _format_iso_timestamp_or_date_display(base)


def _get_by_dotted(root: Any, dotted: str) -> Any:
    cur: Any = root
    part = dotted.replace("[", ".").replace("]", "")
    for seg in part.split("."):
        if seg.isdigit():
            idx = int(seg)
            if isinstance(cur, list) and 0 <= idx < len(cur):
                cur = cur[idx]
            else:
                return None
        elif isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return None
    return cur


def _deep_scan_first_match(obj: Any, want_tokens: set[str]) -> Any:
    """První hodnota pod klíčem, jehož _norm_cmp_token je ve wants (rekurzivně)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _norm_cmp_token(k) in want_tokens:
                if _present(v):
                    return v
        for v in obj.values():
            got = _deep_scan_first_match(v, want_tokens)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for it in obj:
            got = _deep_scan_first_match(it, want_tokens)
            if got is not None:
                return got
    return None


def _deep_scan_first_raw_under_keys(obj: Any, want_tokens: set[str]) -> Optional[Tuple[Any, Optional[str]]]:
    """První raw hodnota pod klíčem tokenově odpovídajícím candidate_keys (i prázdná)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _norm_cmp_token(k) in want_tokens:
                return v, k
        for v in obj.values():
            got = _deep_scan_first_raw_under_keys(v, want_tokens)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for it in obj:
            got = _deep_scan_first_raw_under_keys(it, want_tokens)
            if got is not None:
                return got
    return None


def pick_value(
    decoded_sources: Dict[str, Any],
    candidate_keys: Sequence[str],
    *,
    fallback: Any = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Zpětná kompatibilita — vrací (hodnota, zdroj)."""
    val, src, _st, _mk = pick_value_detailed(decoded_sources, tuple(candidate_keys), fallback=fallback)
    return val, src


def _peek_first_associated_raw(blob: Any, candidate_keys: Sequence[str]) -> Optional[Tuple[Any, Optional[str]]]:
    """
    První strukturální shoda kandidátu v blobu — vrací (raw_hodnota, název_klíče), i když raw je prázdný řetězec.
    Používá se ke klasifikaci missing vs mapper_miss na straně MDČR.
    """
    want_exact = [c for c in candidate_keys if "." in c or "[" in c]
    for ck in want_exact:
        raw = _get_by_dotted(blob, ck)
        if raw is not None:
            return raw, ck

    if isinstance(blob, dict):
        for ck in candidate_keys:
            if "." in ck or "[" in ck:
                continue
            if ck in blob:
                return blob[ck], ck

        folded_map = {_ascii_fold(k): (k, blob[k]) for k in blob.keys()}
        for ck in candidate_keys:
            if "." in ck or "[" in ck:
                continue
            af = _ascii_fold(ck)
            if af in folded_map:
                ok, raw = folded_map[af]
                return raw, ok

        for ck in candidate_keys:
            wt = _norm_cmp_token(ck)
            if not wt:
                continue
            for bk, raw in blob.items():
                bn = _norm_cmp_token(bk)
                # pouze přesná shoda tokenů — substring „typ“ ⊂ „vozidlodruh“ způsoboval špatné párování Typ ↔ Druh
                if bn == wt:
                    return raw, bk

        want_tokens = {_norm_cmp_token(c) for c in candidate_keys if c and "." not in c and "[" not in c}
        if want_tokens:
            got = _deep_scan_first_raw_under_keys(blob, want_tokens)
            if got is not None:
                return got

    return None


def pick_value_detailed(
    decoded_sources: Dict[str, Any],
    candidate_keys: Sequence[str],
    *,
    fallback: Any = None,
) -> Tuple[Optional[str], Optional[str], str, Optional[str]]:
    """
    Vrací (value_str|None, source_id|None, status, matched_key|None).

    status:
      filled | missing | mapper_miss | source_not_available
    """
    order = ("mdcr", "local_vin", "vehicle")

    for src in order:
        blob = decoded_sources.get(src)
        if blob is None:
            continue
        if isinstance(blob, dict) and len(blob) == 0:
            continue

        val, matched = _lookup_in_blob(blob, candidate_keys)
        if val is not None:
            return val, src, "filled", matched

    if callable(fallback):
        try:
            fb = fallback()
            if _present(fb):
                return _scalar_display(fb), "computed", "filled", None
        except Exception:
            pass
    elif fallback is not None and _present(fallback):
        return _scalar_display(fallback), "fallback", "filled", None

    mdcr = decoded_sources.get("mdcr")
    mdcr_nonempty = isinstance(mdcr, dict) and len(mdcr) > 0
    loc = decoded_sources.get("local_vin")
    loc_nonempty = isinstance(loc, dict) and len(loc) > 0

    if not mdcr_nonempty and not loc_nonempty:
        return None, None, "source_not_available", None

    if mdcr_nonempty:
        assoc = _peek_first_associated_raw(mdcr, candidate_keys)
        if assoc is None:
            return None, None, "mapper_miss", None
        raw, mkey = assoc
        if not _present(raw):
            return None, None, "missing", mkey
        # konsistence vůči _lookup — pokud najdeme platnou hodnotu jen ve peek, doplníme výsledek
        return _scalar_display(raw), "mdcr", "filled", mkey

    if loc_nonempty:
        assoc_loc = _peek_first_associated_raw(loc, candidate_keys)
        if assoc_loc is not None:
            raw_l, mk_loc = assoc_loc
            if not _present(raw_l):
                return None, None, "missing", mk_loc

    return None, None, "missing", None


def _lookup_in_blob(blob: Any, candidate_keys: Sequence[str]) -> Tuple[Optional[str], Optional[str]]:
    """Vrátí (display_value, matched_key_name)."""
    want_exact = [c for c in candidate_keys if "." in c or "[" in c]
    want_tokens = {_norm_cmp_token(c) for c in candidate_keys if c and "." not in c and "[" not in c}

    # 1) přesné / tečkové cesty
    for ck in want_exact:
        raw = _get_by_dotted(blob, ck)
        if _present(raw):
            return _scalar_display(raw), ck

    # 2) plochý dict – přímý klíč (case-sensitive jak vrací MDČR)
    if isinstance(blob, dict):
        for ck in candidate_keys:
            if "." in ck or "[" in ck:
                continue
            if ck in blob:
                raw = blob[ck]
                if _present(raw):
                    return _scalar_display(raw), ck

        # case-insensitive + ascii fold na klíčích
        folded_map = {_ascii_fold(k): (k, blob[k]) for k in blob.keys()}
        for ck in candidate_keys:
            if "." in ck or "[" in ck:
                continue
            af = _ascii_fold(ck)
            if af in folded_map:
                ok, raw = folded_map[af]
                if _present(raw):
                    return _scalar_display(raw), ok

    # 3) fuzzy — jen přesná shoda normalizovaného tokenu klíče (žádné vnořování substringů)
    if isinstance(blob, dict):
        for ck in candidate_keys:
            wt = _norm_cmp_token(ck)
            if not wt:
                continue
            for bk, raw in blob.items():
                if _norm_cmp_token(bk) == wt:
                    if _present(raw):
                        return _scalar_display(raw), bk

    # 4) hluboký průchod podle tokenů
    if want_tokens:
        raw = _deep_scan_first_match(blob, want_tokens)
        if raw is not None:
            return _scalar_display(raw), None

    return None, None


def _vehicle_fallback_dict(vehicle: Any) -> Dict[str, Any]:
    return {
        "vin": getattr(vehicle, "vin", None),
        "brand": getattr(vehicle, "brand", None),
        "make": getattr(vehicle, "brand", None),
        "model": getattr(vehicle, "model", None),
        "year": getattr(vehicle, "year", None),
        "engine": getattr(vehicle, "engine", None),
        "plate": getattr(vehicle, "plate", None),
        "fuel": getattr(vehicle, "fuel", None),
        "body_type": getattr(vehicle, "body_type", None),
        "tyres_info": getattr(vehicle, "tyres_info", None),
    }


def _build_sources(vehicle: Any, mdcr_raw: Optional[Dict[str, Any]], local_decoded: Any) -> Dict[str, Any]:
    local_blob: Dict[str, Any] = {}
    if local_decoded is not None:
        try:
            local_blob = local_decoded.model_dump(mode="python")
        except Exception:
            local_blob = {}

    return {
        "mdcr": mdcr_raw or {},
        "local_vin": local_blob,
        "vehicle": _vehicle_fallback_dict(vehicle),
    }


def _compose_parts(blob: Dict[str, Any], keys: Sequence[str], sep: str = " / ") -> Optional[str]:
    parts: List[str] = []
    for k in keys:
        if k not in blob:
            continue
        raw = blob[k]
        if raw is None:
            continue
        if isinstance(raw, str) and raw.strip() == "":
            continue
        parts.append(_scalar_display(raw))
    if not parts:
        return None
    return sep.join(parts)


def _motor_power_line(blob: Dict[str, Any]) -> Optional[str]:
    v = blob.get("MotorMaxVykon")
    if _present(v):
        return _scalar_display(v)
    kw = blob.get("MaxVykonKw")
    rpm = blob.get("MaxVykonOtacky") or blob.get("MotorOtackyPriMaxVykonu")
    if kw is not None and rpm is not None:
        return f"{_scalar_display(kw)} / {_scalar_display(rpm)}"
    if kw is not None:
        return _scalar_display(kw)
    return None


def _co2_line(blob: Dict[str, Any]) -> Optional[str]:
    v = blob.get("EmiseCO2")
    if _present(v):
        return _scalar_display(v)
    alt = _compose_parts(blob, ("Co2Mesto", "Co2MimoMesto", "Co2Kombinovane"))
    if alt:
        return alt
    return _compose_parts(blob, ("EmiseCo2Mesto", "EmiseCo2MimoMesto", "EmiseCo2Kombinovane"))


def _spotreba_triple(blob: Dict[str, Any]) -> Optional[str]:
    for k in ("SpotrebaNa100Km", "Spotreba"):
        vv = blob.get(k)
        if _present(vv):
            return _scalar_display(vv)
    return _compose_parts(blob, ("SpotrebaMesto", "SpotrebaMimoMesto", "SpotrebaKombinovana"))


def _rozmery_line(blob: Dict[str, Any]) -> Optional[str]:
    vv = blob.get("Rozmery")
    if _present(vv):
        return _scalar_display(vv)
    d, s, v = blob.get("Delka"), blob.get("Sirka"), blob.get("Vyska")
    if _present(d) and _present(s) and _present(v):
        return f"{_scalar_display(d)}/ {_scalar_display(s)}/ {_scalar_display(v)}"
    rd, rs, rv = blob.get("RozmeryDelka"), blob.get("RozmerySirka"), blob.get("RozmeryVyska")
    if _present(rd) and _present(rs) and _present(rv):
        return f"{_scalar_display(rd)}/ {_scalar_display(rs)}/ {_scalar_display(rv)}"
    return None


def _mist_line(blob: Dict[str, Any]) -> Optional[str]:
    for k in ("VozidloKaroserieMist", "Mista"):
        vv = blob.get(k)
        if _present(vv):
            return _scalar_display(vv)
    mk = ("PocetMistCelkem", "PocetMistKSezeni", "PocetMistKStani")
    if any(k in blob for k in mk):
        chunks: List[str] = []
        for k in mk:
            raw = blob.get(k)
            if raw is None or (isinstance(raw, str) and raw.strip() == ""):
                chunks.append("")
            else:
                chunks.append(_scalar_display(raw))
        return " / ".join(chunks)
    return None


def _hluk_stojici_line(blob: Dict[str, Any]) -> Optional[str]:
    vv = blob.get("HlukStojiciOtacky")
    if _present(vv):
        return _scalar_display(vv)
    a = blob.get("HlukStojici") or blob.get("HlukVnejsiStojici")
    b = blob.get("HlukOtacky")
    if a is not None and b is not None:
        return f"{_scalar_display(a)} / {_scalar_display(b)}"
    if a is not None:
        return _scalar_display(a)
    return None


def _paired_weight_line(blob: Dict[str, Any], single_keys: Sequence[str], a_tech: str, b_pov: str) -> Optional[str]:
    for sk in single_keys:
        vv = blob.get(sk)
        if _present(vv):
            return _scalar_display(vv)
    ta = blob.get(a_tech)
    tb = blob.get(b_pov)
    if _present(ta) and _present(tb):
        return f"{_scalar_display(ta)} / {_scalar_display(tb)}"
    return None


def _napravy_pocet_line(blob: Dict[str, Any]) -> Optional[str]:
    vv = blob.get("NapravyPocetDruh")
    if _present(vv):
        return _scalar_display(vv)
    return _compose_parts(blob, ("PocetNaprav", "PohaneneNapravy"))


def _filled_md_row(label: str, value: str, candidate_keys: Sequence[str]) -> Dict[str, Any]:
    return {
        "label": label,
        "value": value,
        "source": "mdcr",
        "status": "filled",
        "matched_key": None,
        "candidate_keys": list(candidate_keys),
    }


def _computed_or_resolve(
    sources: Dict[str, Any],
    blob: Dict[str, Any],
    label: str,
    compute_fn,
    fallback_candidates: Sequence[str],
) -> Dict[str, Any]:
    try:
        txt = compute_fn(blob)
    except Exception:
        txt = None
    if txt is not None and str(txt).strip() != "":
        return _filled_md_row(label, txt, fallback_candidates)
    return _resolve_row(sources, label, tuple(fallback_candidates))


def _resolve_row(
    sources: Dict[str, Any],
    label: str,
    candidates: Sequence[str],
    *,
    fb: Any = None,
) -> Dict[str, Any]:
    fb_call = (lambda: fb) if fb is not None else None
    val, src, status, matched = pick_value_detailed(sources, tuple(candidates), fallback=fb_call)

    return {
        "label": label,
        "value": val,
        "source": src,
        "status": status,
        "matched_key": matched,
        "candidate_keys": list(candidates),
    }


def build_vehicle_technical_overview(
    vehicle: Any,
    *,
    mdcr_raw: Optional[Dict[str, Any]] = None,
    local_decoded: Any = None,
) -> Dict[str, Any]:
    vin_val = str(getattr(vehicle, "vin", "") or "").strip().upper().replace(" ", "").replace("-", "")
    sources = _build_sources(vehicle, mdcr_raw, local_decoded)
    md_flat = sources.get("mdcr") if isinstance(sources.get("mdcr"), dict) else {}
    mdcr_key_count = len(md_flat)

    summary_sources: List[str] = []
    if mdcr_raw:
        summary_sources.append("mdcr")
    if local_decoded is not None:
        summary_sources.append("local_vin")

    generated_at = datetime.now(timezone.utc).isoformat()

    def R(label: str, *keys: str, fb: Any = None) -> Dict[str, Any]:
        return _resolve_row(sources, label, keys, fb=fb)

    def C(label: str, fn, keys: Sequence[str]) -> Dict[str, Any]:
        return _computed_or_resolve(sources, md_flat, label, fn, keys)

    rows_vehicle = [
        R("ZTP", "CisloTypovehoSchvaleni", "Ztp", "ZTPCislo", "ZTP"),
        R("ES/EU", "HomologaceEs", "EsEu", "ESEU", "SchvaleniEsEu"),
        R("Druh vozidla", "VozidloDruh", "DruhVozidla"),
        R("Druh vozidla 2. řádek", "VozidloDruh2", "DruhVozidlaRadek2", "DruhVozidla2Rad"),
        R("Kategorie vozidla", "Kategorie", "KategorieVozidla", "VozidloKategorie"),
        R("Tovární značka", "TovarniZnacka", "Tovarni_Znacka", "Znacka", "make", "brand"),
        R("Typ", "Typ", "VozidloTyp"),
        R("Varianta", "Varianta", "VozidloVarianta"),
        R("Verze", "Verze", "VozidloVerze"),
        R("Obchodní označení", "ObchodniOznaceni", "VozidloObchodniOznaceni", "model"),
        R("VIN", "VIN", "Vin", "vin", fb=vin_val or None),
        R("Výrobce vozidla", "VozidloVyrobce", "VyrobceVozidla"),
    ]

    rows_motor = [
        R("Výrobce motoru", "MotorVyrobce", "VyrobceMotoru"),
        R("Typ motoru", "MotorTyp", "TypMotoru", "engine_code"),
        R("Číslo motoru", "MotorCislo", "CisloMotoru", "KodMotoru"),
        R("Palivo", "Palivo", "MotorPalivo", "fuel_type"),
        C(
            "Max. výkon [kW] / [min⁻¹]",
            _motor_power_line,
            ("MotorMaxVykon", "MaxVykonKw", "MaxVykonOtacky", "MotorOtackyPriMaxVykonu"),
        ),
        R("Zdvihový objem [cm³]", "MotorZdvihObjem", "MotorZdvihovyObjem", "ZdvihovyObjem"),
        R("Nejvyšší rychlost [km.h⁻¹]", "NejvyssiRychlost", "VozidloNejvyssiRychlost"),
        R("Plně elektrické vozidlo", "VozidloElektricke", "PlneElektrickeVozidlo"),
        R("Hybridní vozidlo", "VozidloHybridni", "HybridniVozidlo"),
        R("Třída hybridního vozidla", "VozidloHybridniTrida", "TridaHybridnihoVozidla"),
    ]

    rows_emise = [
        R("Emisní limit [EHKOSN/EHSES]", "EmiseEHKOSNEHSES", "EmisniLimit", "EmiseLimit"),
        R("Korigovaný součinitel absorbce [m⁻¹]", "EmiseKSA", "KorigovanySoucinitelAbsorbce"),
        R("Stupeň plnění emisní úrovně", "EmisniUroven", "StupenPlneniEmisniUrovne", "EmiseStupen"),
        C(
            "CO2 město/mimo město/kombinované [g.km-1]",
            _co2_line,
            ("EmiseCO2", "Co2Mesto", "Co2MimoMesto", "Co2Kombinovane"),
        ),
        R("Specifické CO2", "EmiseCO2Specificke", "SpecifickeCo2"),
        R("Snížení emisí - NEDC", "EmiseSnizeniNedc", "SnizeniEmisiNedc"),
        R("Snížení emisí - WLTP", "EmiseSnizeniWltp", "SnizeniEmisiWltp"),
    ]

    rows_spotreba = [
        R("Spotřeba předpis", "SpotrebaMetodika", "SpotrebaPredpis"),
        C(
            "Spotřeba město/mimo město/kombinovaná [l.100km⁻¹]",
            _spotreba_triple,
            ("SpotrebaNa100Km", "Spotreba", "SpotrebaMesto", "SpotrebaMimoMesto", "SpotrebaKombinovana"),
        ),
        R("Spotřeba při rychlosti [l.100 km⁻¹]", "SpotrebaPriRychlosti"),
        R("Spotřeba el. mobil [Wh/km] – Z", "SpotrebaEl", "SpotrebaElMobilZ"),
        R("Dojezd ZR [km]", "DojezdZR", "DojezdZr"),
    ]

    rows_karoserie = [
        R("Výrobce karoserie", "VyrobceKaroserie", "KaroserieVyrobce"),
        R("Druh (typ)", "KaroserieDruh", "KaroserieTyp"),
        R("Výrobní číslo karoserie", "KaroserieVyrobniCislo", "VyrobniCisloKaroserie"),
        R("Barva", "VozidloKaroserieBarva", "KaroserieBarva", "Barva"),
        R("Barva doplňková", "VozidloKaroserieBarvaDoplnkova", "BarvaDoplnkova"),
        C(
            "Počet míst celkem / k sezení / k stání",
            _mist_line,
            ("VozidloKaroserieMist", "PocetMistCelkem", "Mista"),
        ),
        R("Počet míst k sezení - dodatek", "VozidloKaroserieMistSezeniPozn", "PocetMistKSezeniDodatek"),
        R("Počet míst k stání - dodatek", "VozidloKaroserieMistStaniPozn", "PocetMistKStaniDodatek"),
    ]

    rows_rozmery = [
        C(
            "Celková délka/šířka/výška [mm]",
            _rozmery_line,
            ("Rozmery", "Delka", "Sirka", "Vyska"),
        ),
        R("Délka do", "RozmeryDelkaDo", "DelkaDo"),
        R("Výška do", "RozmeryVyskaDo", "VyskaDo"),
        R("Ložná délka", "RozmeryLoznaDelka", "LoznaDelka"),
        R("Ložná šířka", "RozmeryLoznaSirka", "LoznaSirka"),
        R("Rozvor [mm]", "RozmeryRozvor", "Rozvor", "VozidloRozvor"),
        R("Rozchod [mm]", "Rozchod", "VozidloRozchod"),
    ]

    rows_hmotnosti = [
        R("Provozní hmotnost", "HmotnostiProvozni", "ProvozniHmotnost"),
        R("Provozní hmotnost do", "HmotnostiProvozniDo"),
        C(
            "Největší technicky přípustná/povolená hmotnost [kg]",
            lambda b: _paired_weight_line(
                b,
                ("HmotnostiPripPov",),
                "HmotnostiTechnickyPripustna",
                "HmotnostiPovolena",
            ),
            ("HmotnostiPripPov", "HmotnostiTechnickyPripustna", "HmotnostiPovolena"),
        ),
        C(
            "Největší technicky přípustná/povolená hmotnost přípojného vozidla [kg] brzděného",
            lambda b: _paired_weight_line(
                b,
                ("HmotnostiPripPovBrzdenePV",),
                "HmotnostiPripojneBrzdeneTechnickyPripustna",
                "HmotnostiPripojneBrzdenePovolena",
            ),
            ("HmotnostiPripPovBrzdenePV",),
        ),
        C(
            "Největší technicky přípustná/povolená hmotnost na nápravu [kg]",
            lambda b: _paired_weight_line(
                b,
                ("HmotnostiPripPovN",),
                "HmotnostiNapravaTechnickyPripustna",
                "HmotnostiNapravaPovolena",
            ),
            ("HmotnostiPripPovN",),
        ),
        C(
            "Největší technicky přípustná/povolená hmotnost přípojného vozidla [kg] nebrzděného",
            lambda b: _paired_weight_line(
                b,
                ("HmotnostiPripPovNebrzdenePV",),
                "HmotnostiPripojneNebrzdeneTechnickyPripustna",
                "HmotnostiPripojneNebrzdenePovolena",
            ),
            ("HmotnostiPripPovNebrzdenePV",),
        ),
        C(
            "Největší technicky přípustná/povolená hmotnost jízdní soupravy [kg]",
            lambda b: _paired_weight_line(
                b,
                ("HmotnostiPripPovJS",),
                "HmotnostiSoupravyTechnickyPripustna",
                "HmotnostiSoupravyPovolena",
            ),
            ("HmotnostiPripPovJS",),
        ),
        R("Hmotnosti vozidla při testu WLTP", "HmotnostiTestWltp", "HmotnostiWltp"),
        R(
            "Průměrná hodnota užitečného zatížení",
            "HmotnostUzitecneZatizeniPrumer",
            "PrumernaHodnotaUzitecnehoZatizeni",
        ),
        R("Hmotnosti zatížení SZ", "HmotnostiZatizeniSZ", "HmotnostiZatizeniSz"),
        R("Hmotnosti zatížení SZ typ", "HmotnostiZatizeniSZTyp", "HmotnostiZatizeniSzTyp"),
    ]

    rows_napravy = [
        R(
            "Kola a pneumatiky na nápravě - rozměry/montáž [N.1; N.2; N.3; N.4]",
            "NapravyPneuRafky",
            "KolaPneumatiky",
            "KolaAPneumatiky",
        ),
        C(
            "Počet náprav - z toho poháněných",
            _napravy_pocet_line,
            ("NapravyPocetDruh", "PocetNaprav", "PohaneneNapravy"),
        ),
    ]

    rows_hluk = [
        R("Za jízdy", "HlukJizda", "HlukZaJizdy"),
        C(
            "Vnější hluk vozidla [dB(A)] - stojícího při ot. [min⁻¹]",
            _hluk_stojici_line,
            ("HlukStojiciOtacky", "HlukStojici", "HlukOtacky"),
        ),
    ]

    rows_doklady = [
        R("Číslo TP", "CisloTp", "CisloTP"),
        R("Číslo ORV", "CisloOrv", "CisloORV"),
        R("Zadrženo ORV", "OrvZadrzeno", "ZadrzenoOrv"),
        R("ORV ke skartaci", "OrvKeSkartaci"),
        R("ORV odevzdáno", "OrvOdevzdano"),
        R("Druh RZ", "RzDruh", "DruhRz"),
        R("Varianta RZ", "RzVarianta", "VariantaRz"),
        R("RZ pro nosič j.k. vydána", "RzJkVydana", "RzProNosicJkVydana"),
        R("RZ ke skartaci", "RzKeSkartaci"),
        R("RZ odevzdány", "RzOdevzdano", "RzOdevzdany"),
        R("Zadržená RZ poslední", "RzZadrzena", "ZadrzenaRzPosledni"),
        R("Zařazení vozidla", "ZarazeniVozidla"),
    ]

    rows_stav = [
        R("Status", "StatusNazev", "Status", "Stav", "VozidloStatus"),
        R(
            "Pravidelná technická prohlídka do",
            "PravidelnaTechnickaProhlidkaDo",
            "TechnickaProhlidkaDo",
        ),
        R("Evidenční prohlídka", "EvidencniProhlidkaDne", "EvidencniProhlidka"),
        R(
            "Technická prohlídka před registrací",
            "PredRegistraciProhlidkaDne",
            "TechnickaProhlidkaPredRegistraci",
        ),
        R(
            "Technická prohlídka před schválením",
            "PredSchvalenimProhlidkaDne",
            "TechnickaProhlidkaPredSchvalenim",
        ),
        R(
            "Technická prohlídka historického vozidla",
            "HistorickeVozidloProhlidkaDne",
            "TechnickaProhlidkaHistorickehoVozidla",
        ),
    ]

    rows_hist = [
        R("Datum 1. registrace", "DatumPrvniRegistrace"),
        R("Datum 1. registrace v ČR", "DatumPrvniRegistraceVCr"),
        R("Počet provozovatelů", "PocetProvozovatelu"),
        R("Počet vlastníků", "PocetVlastniku"),
    ]

    rows_ostatni = [
        R("Spojovací zařízení - druh", "VozidloSpojZarizNazev", "SpojovaciZarizeniDruh"),
        R("Poměr Výkon/Hmotnost [kW.kg⁻¹]", "PomerVykonHmotnost"),
        R("Inovativní technologie", "InovativniTechnologie"),
        R("Stupeň dokončení", "StupenDokonceni"),
        R("Faktor odchylky - DE", "FaktorOdchylkyDe"),
        R("Faktor verifikace - Vf", "FaktorVerifikaceVf"),
        R("Účel", "VozidloUcel", "Ucel"),
        R("Alternativní provedení", "AlternativniProvedeni"),
        R(
            "Autonomní Stupeň",
            "VozidloAutonomniStupen",
            "AutonomniStupen",
            "StupenAutonomieVozidla",
        ),
    ]

    rows_dalsi = [
        R(
            "Další záznamy",
            "DalsiZaznamy",
            "DalsiZaznam",
            "TechnickePoznamky",
            "Poznamky",
            "Poznamka",
            "DoplnujiciUdaje",
        ),
        R("Variabilní provedení vozidla", "VariabilniProvedeni", "VariabilniProvedeniVozidla"),
        R("Alternativní provedení vozidla", "AlternativniProvedeni", "AlternativniProvedeniVozidla"),
        R(
            "Poznámky k technické způsobilosti",
            "PoznamkyTechnickaZpusobilost",
            "PoznamkyKtechnickeZpusobilosti",
        ),
        R(
            "Doklad o schválení technické způsobilosti",
            "CisloTypovehoSchvaleni",
            "DokladSchvaleniTechnickeZpusobilosti",
        ),
        R(
            "První registrace vozidla dle zahraničního TP",
            "DatumPrvniRegistrace",
            "PrvniRegistraceDleZahranicnihoTp",
        ),
        R(
            "Automaticky doplněná data",
            "AutomatickyDoplnenaData",
        ),
    ]

    sections_meta = [
        ("vehicle", "Vozidlo", rows_vehicle),
        ("motor", "Motor", rows_motor),
        ("emissions", "Emise", rows_emise),
        ("consumption", "Spotřeba", rows_spotreba),
        ("body", "Karoserie", rows_karoserie),
        ("dimensions", "Rozměry", rows_rozmery),
        ("weights", "Hmotnosti", rows_hmotnosti),
        ("axles", "Nápravy a kola", rows_napravy),
        ("noise", "Hluk", rows_hluk),
        ("documents", "Doklady", rows_doklady),
        ("inspections", "Stav a prohlídky", rows_stav),
        ("history", "Historie", rows_hist),
        ("misc", "Ostatní", rows_ostatni),
        ("extra", "Další záznamy", rows_dalsi),
    ]

    sections_out: List[Dict[str, Any]] = []
    filled = 0
    total = 0
    by_section: Dict[str, Dict[str, int]] = {}

    for key, title, rs in sections_meta:
        sec_rows: List[Dict[str, Any]] = []
        sf = 0
        stotal = len(rs)
        for r in rs:
            total += 1
            v = r.get("value")
            if v is not None and str(v).strip() != "":
                filled += 1
                sf += 1
            sec_rows.append(dict(r))
        by_section[title] = {"filled": sf, "total": stotal}
        sections_out.append({"key": key, "title": title, "rows": sec_rows})

    out: Dict[str, Any] = {
        "version": OVERVIEW_VERSION,
        "source_summary": summary_sources,
        "generated_at": generated_at,
        "vin": vin_val or None,
        "stats": {
            "filled": filled,
            "empty": max(0, total - filled),
            "total": total,
            "by_section": by_section,
            "mdcr_key_count": mdcr_key_count,
        },
        "sections": sections_out,
        "raw": {
            "mdcr": mdcr_raw if mdcr_raw else {},
            "local_vin": sources.get("local_vin") or {},
        },
    }
    return out


def technical_overview_for_api(stored: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not stored:
        return None
    pub = {k: v for k, v in stored.items() if k != "raw"}
    secs = pub.get("sections")
    if isinstance(secs, list):
        pub["sections"] = []
        for sec in secs:
            if not isinstance(sec, dict):
                pub["sections"].append(sec)
                continue
            nrow = dict(sec)
            rows = nrow.get("rows") or []
            cleaned_rows: List[Dict[str, Any]] = []
            for row in rows:
                if isinstance(row, dict):
                    cleaned_rows.append(
                        {k: v for k, v in row.items() if k not in ("matched_key", "candidate_keys")}
                    )
                else:
                    cleaned_rows.append(row)  # type: ignore[arg-type]
            nrow["rows"] = cleaned_rows
            pub["sections"].append(nrow)
    return pub


def build_technical_overview_debug_payload(
    *,
    vin: str,
    overview_stored: Optional[Dict[str, Any]],
    mdcr_raw: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Datová část pro GET …/technical-overview/debug — bez osobních údajů."""
    ov = overview_stored or {}
    stats = ov.get("stats") or {}
    sections = ov.get("sections") or []

    empty_labels: List[str] = []
    candidate_misses: List[Dict[str, Any]] = []

    flat_paths = flatten_key_paths(mdcr_raw or {}) if isinstance(mdcr_raw, dict) else []

    for sec in sections:
        stitle = sec.get("title") or ""
        for row in sec.get("rows") or []:
            lbl = row.get("label") or ""
            if row.get("value") in (None, "") or str(row.get("value")).strip() == "":
                empty_labels.append(f"{stitle}: {lbl}")
            if row.get("status") == "mapper_miss":
                candidate_misses.append(
                    {
                        "section": stitle,
                        "label": lbl,
                        "candidate_keys": row.get("candidate_keys") or [],
                        "found": False,
                    }
                )

    raw_b = ov.get("raw") or {}
    rsa: List[str] = []
    if isinstance(raw_b.get("mdcr"), dict) and len(raw_b["mdcr"]) > 0:
        rsa.append("mdcr")
    if isinstance(raw_b.get("local_vin"), dict) and len(raw_b["local_vin"]) > 0:
        rsa.append("local_vin")

    # řádky se statusy pro debug (ponecháme matched_key/candidate_keys pokud jsou uložené)
    dbg_sections: List[Dict[str, Any]] = []
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        dbg_sections.append(
            {
                "key": sec.get("key"),
                "title": sec.get("title"),
                "rows": sec.get("rows") or [],
            }
        )

    return {
        "vin": vin,
        "has_technical_overview": bool(overview_stored),
        "source_summary": ov.get("source_summary"),
        "raw_sources_available": rsa,
        "mdcr_top_level_keys": sorted(list((mdcr_raw or {}).keys())) if isinstance(mdcr_raw, dict) else [],
        "mdcr_nested_key_paths": flat_paths[:500],
        "filled_rows": stats.get("filled"),
        "empty_rows": stats.get("empty"),
        "empty_labels": empty_labels[:200],
        "candidate_key_misses": candidate_misses[:120],
        "sections_debug": dbg_sections[:14],
        "stats": stats,
    }


def persist_vehicle_technical_overview(db: Session, vehicle: Any) -> Optional[Dict[str, Any]]:
    vin = str(getattr(vehicle, "vin", "") or "").strip()
    if len(vin.replace(" ", "").replace("-", "")) != 17:
        vehicle.vehicle_technical_overview = None
        try:
            from src.modules.vehicle_hub.services.vehicle_large_technical_certificate_storage import (
                try_refresh_vehicle_large_technical_certificate_disk,
            )

            try_refresh_vehicle_large_technical_certificate_disk(vehicle)
        except Exception as exc:
            logger.warning(
                "[TECH_OVERVIEW] large TP refresh after clearing overview failed vehicle_id=%s err=%s",
                getattr(vehicle, "id", None),
                exc,
                exc_info=True,
            )
        return None

    vin_clean = vin.upper().replace(" ", "").replace("-", "")
    mdcr_raw = fetch_mdcr_vehicle_raw_data_sync(vin_clean)
    local_decoded, _errs = decode_vin_local(vin_clean)

    overview = build_vehicle_technical_overview(vehicle, mdcr_raw=mdcr_raw, local_decoded=local_decoded)
    vehicle.vehicle_technical_overview = overview
    db.add(vehicle)
    try:
        from src.modules.vehicle_hub.services.vehicle_large_technical_certificate_storage import (
            try_refresh_vehicle_large_technical_certificate_disk,
        )

        try_refresh_vehicle_large_technical_certificate_disk(vehicle)
    except Exception as exc:
        logger.warning(
            "[TECH_OVERVIEW] large TP refresh after persist failed vehicle_id=%s err=%s",
            getattr(vehicle, "id", None),
            exc,
            exc_info=True,
        )
    return overview
