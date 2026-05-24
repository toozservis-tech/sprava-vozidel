"""
MDČR API klient pro získání dat o vozidlech
Používá dataovozidlech.cz API (oficiální databáze vozidel MDČR)
"""
import logging
import os
from typing import Any, Dict, List, Optional
from datetime import datetime
import httpx
import urllib.parse
import re

from .models import VehicleDecodedData

logger = logging.getLogger(__name__)


def _should_log_mdcr_shape() -> bool:
    v = os.getenv("MDCR_TECH_OVERVIEW_SHAPE_LOG", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _ascii_fold_key(s: str) -> str:
    import unicodedata

    nk = unicodedata.normalize("NFKD", s)
    return "".join(c.lower() for c in nk if not unicodedata.combining(c))


def _find_mdcr_value(data: Dict[str, Any], *keys: str, default=None):
    """Najde hodnotu i v mělkých vnořených skupinách typu Karoserie -> Barva."""
    normalized_keys = {_ascii_fold_key(str(key)): key for key in keys}
    for key in keys:
        if isinstance(data, dict) and data.get(key) is not None:
            return data[key]

    def walk(value: Any, depth: int = 0):
        if depth > 3:
            return None
        if isinstance(value, dict):
            for raw_key, raw_value in value.items():
                folded = _ascii_fold_key(str(raw_key))
                if folded in normalized_keys and raw_value is not None:
                    return raw_value
                found = walk(raw_value, depth + 1)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = walk(item, depth + 1)
                if found is not None:
                    return found
        return None

    found_value = walk(data)
    return default if found_value is None else found_value


def _nested_key_paths_depth(obj: Any, prefix: str = "", depth: int = 0, max_depth: int = 3) -> List[str]:
    """Klíčové cesty do hloubky max_depth (pro bezpečný profil odpovědi MDČR)."""
    paths: List[str] = []

    def walk(o: Any, pre: str, d: int) -> None:
        if d >= max_depth:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                seg = f"{pre}.{k}" if pre else str(k)
                if isinstance(v, (dict, list)):
                    walk(v, seg, d + 1)
                else:
                    paths.append(seg)
        elif isinstance(o, list):
            for i, it in enumerate(o[:50]):
                seg = f"{pre}[{i}]"
                if isinstance(it, (dict, list)):
                    walk(it, seg, d + 1)
                else:
                    paths.append(seg)

    walk(obj, prefix, depth)
    return paths


def _mdcr_shape_flag_presence(data: Dict[str, Any]) -> Dict[str, bool]:
    """Orientační přítomnost skupin polí (bez logování hodnot)."""
    ks = {_ascii_fold_key(str(k)) for k in data.keys()}

    def has_sub(*parts: str) -> bool:
        return any(all(p in fk for p in parts) for fk in ks)

    return {
        "vykon_kw_like": has_sub("motor", "vykon") or has_sub("maxvykon"),
        "objem_like": has_sub("zdvih") or has_sub("objem"),
        "palivo": has_sub("palivo"),
        "typ_motoru": has_sub("motor") and has_sub("typ"),
        "emise": has_sub("emise") or has_sub("co2"),
        "spotreba": has_sub("spotreb"),
        "hmotnosti": has_sub("hmotnost"),
        "rozmery": has_sub("rozmer") or has_sub("rozvor"),
        "barva": has_sub("barva"),
        "mist": has_sub("mist"),
        "tp_orv": has_sub("cislotp") or has_sub("cisloorv"),
        "stk_like": has_sub("prohlidka") or has_sub("stk"),
        "prvni_registrace": has_sub("prvni") and has_sub("registr"),
    }


def log_mdcr_payload_shape_summary(*, vin_masked: str, http_status: int, data: Optional[Dict[str, Any]]) -> None:
    """
    Bezpečný vývojářský profil odpovědi MDČR — bez API klíče, bez celého těla, bez VIN celého.
    Zapnutí: MDCR_TECH_OVERVIEW_SHAPE_LOG=1
    """
    if not _should_log_mdcr_shape():
        return
    if data is None:
        logger.info("[MDČR][shape] vin=%s http=%s keys_top=[] empty=true", vin_masked, http_status)
        return
    top_keys = sorted(list(data.keys()))
    nested = _nested_key_paths_depth(data, max_depth=3)[:400]
    flags = _mdcr_shape_flag_presence(data)
    logger.info(
        "[MDČR][shape] vin=%s http=%s top_n=%s nested_paths_sample_n=%s flags=%s top_keys=%s",
        vin_masked,
        http_status,
        len(top_keys),
        len(nested),
        flags,
        top_keys[:80],
    )
    logger.info("[MDČR][shape] nested_paths_sample=%s", nested[:120])


def parse_date_like(date_value) -> Optional[str]:
    """
    Parsuje datum z různých formátů (ISO, český formát, timestamp, atd.)
    a vrátí ho jako ISO formát string (YYYY-MM-DD).
    
    Args:
        date_value: Datum v různých formátech (str, int, datetime, atd.)
        
    Returns:
        ISO formát string (YYYY-MM-DD) nebo None
    """
    if date_value is None:
        return None
    
    try:
        # Pokud je to už datetime objekt
        if isinstance(date_value, datetime):
            return date_value.strftime("%Y-%m-%d")
        
        # Převést na string
        date_str = str(date_value).strip()
        
        if not date_str:
            return None
        
        # ISO formát YYYY-MM-DD
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str
        
        # ISO formát s časem YYYY-MM-DDTHH:MM:SS
        iso_match = re.match(r'^(\d{4}-\d{2}-\d{2})', date_str)
        if iso_match:
            return iso_match.group(1)
        
        # Český formát DD.MM.YYYY
        czech_match = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', date_str)
        if czech_match:
            day, month, year = czech_match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        # Formát DD/MM/YYYY
        slash_match = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', date_str)
        if slash_match:
            day, month, year = slash_match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        # Pouze rok (YYYY) - vrátit jako YYYY-01-01
        if re.match(r'^\d{4}$', date_str):
            return f"{date_str}-01-01"
        
        # Zkusit parsovat jako ISO datetime
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            pass
        
        # Zkusit parsovat pomocí strptime s různými formáty
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%d.%m.%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                continue
        
        logger.warning(f"[MDČR] Nepodařilo se parsovat datum: {date_value}")
        # Vrátit jako string, pokud se nepodařilo parsovat
        return date_str
        
    except Exception as e:
        logger.warning(f"[MDČR] Chyba při parsování data {date_value}: {e}")
        return str(date_value) if date_value else None

# Načíst config proměnné - podporujeme více variant názvů pro zpětnou kompatibilitu
# DŮLEŽITÉ: Podporujeme oba názvy (nové i legacy) pro zpětnou kompatibilitu
# Preferujeme nové názvy, ale fallback na staré pokud nové nejsou nastavené
try:
    from src.core.config import DATAOVO_API_KEY, DATAOVO_API_BASE_URL
    # Config.py už má fallback logiku, použijeme ji
except ImportError:
    # Pokud config.py není dostupný, použít přímé čtení z ENV s fallbackem
    DATAOVO_API_KEY = os.getenv("DATAOVO_API_KEY") or os.getenv("DATAOVOZIDLECH_API_KEY", "")
    DATAOVO_API_BASE_URL = os.getenv("DATAOVO_API_BASE_URL") or os.getenv("DATAOVOZIDLECH_API_URL", "https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2")

# Aliasy pro zpětnou kompatibilitu (pouze pro čtení, ne pro zápis)
DATAOVOZIDLECH_API_KEY = DATAOVO_API_KEY
DATAOVOZIDLECH_API_URL = DATAOVO_API_BASE_URL


async def fetch_vehicle_by_vin_from_mdcr(vin: str) -> Optional[VehicleDecodedData]:
    """
    Zavolá MDČR API dle VIN a převede JSON odpověď na VehicleDecodedData.
    
    Args:
        vin: VIN kód vozidla (17 znaků, normalizovaný)
        
    Returns:
        VehicleDecodedData nebo None při chybě/nenalezení
    """
    # Normalizace VIN
    normalized_vin = vin.strip().upper().replace(" ", "").replace("-", "")
    
    # KROK 1: Kontrola konfigurace - POUZE z ENV
    if not DATAOVO_API_KEY or not DATAOVO_API_BASE_URL:
        logger.warning(f"[MDCR] API není nakonfigurováno - DATAOVO_API_KEY nebo DATAOVO_API_BASE_URL chybí v ENV")
        logger.warning(f"[MDCR] DATAOVO_API_KEY: {'SET' if DATAOVO_API_KEY else 'MISSING'}")
        logger.warning(f"[MDCR] DATAOVO_API_BASE_URL: {DATAOVO_API_BASE_URL if DATAOVO_API_BASE_URL else 'MISSING'}")
        return None
    
    # KROK 2: Logování před voláním API
    logger.info(f"[MDCR] ========================================")
    logger.info(f"[MDCR] API CALLED WITH VIN={normalized_vin}")
    logger.info(f"[MDCR] API URL: {DATAOVO_API_BASE_URL}")
    logger.info(f"[MDCR] API KEY: {'SET' if DATAOVO_API_KEY else 'MISSING'} (length: {len(DATAOVO_API_KEY) if DATAOVO_API_KEY else 0})")
    
    try:
        # KROK 2: Vytvoření requestu
        url = f"{DATAOVO_API_BASE_URL}?vin={urllib.parse.quote(normalized_vin)}"
        headers = {
            "api_key": DATAOVO_API_KEY,
            "Accept": "application/json"
        }
        
        logger.info(f"[MDCR] Request URL: {url}")
        logger.debug(f"[MDCR] Request headers: api_key={'***' + DATAOVO_API_KEY[-4:] if len(DATAOVO_API_KEY) > 4 else '***'}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
        
        # KROK 2: Logování response status
        logger.info(f"[MDCR] RESPONSE STATUS={response.status_code}")
        logger.info(f"[MDCR] Response headers: {dict(response.headers)}")
        
        if response.status_code != 200:
            logger.warning(f"[MDČR] ❌ API vrátilo status {response.status_code}")
            logger.warning(f"[MDČR] Response text (prvních 500 znaků): {response.text[:500]}")
            return None
        
        api_response = response.json()
        
        # Detailní logování odpovědi
        response_str = str(api_response)
        logger.info(f"[MDČR] ✅ API odpověď přijata")
        logger.info(f"[MDČR] Response body délka: {len(response_str)} znaků")
        logger.info(f"[MDČR] Response body (prvních 500 znaků): {response_str[:500]}")
        logger.debug(f"[MDČR] Celá response: {response_str}")
        
        # API vrací strukturu: {"Status": 1, "Data": {...}} nebo {"Success": true/false, "Data": {...}}
        # Kontrola obou variant pro kompatibilitu
        status = api_response.get("Status")
        success = api_response.get("Success")
        
        # Pokud Success: false, vrátit None
        if success is False:
            logger.warning(f"[MDČR] ❌ API vrátilo Success: false")
            logger.warning(f"[MDČR] Response (prvních 500 znaků): {response_str[:500]}")
            return None
        
        # Pokud Status není 1 nebo Success není True, a není Data
        if (status != 1 and success is not True) or "Data" not in api_response:
            logger.warning(f"[MDČR] ❌ API vrátilo chybu")
            logger.warning(f"[MDČR] Status: {status}, Success: {success}")
            logger.warning(f"[MDČR] Má 'Data' klíč: {'Data' in api_response}")
            logger.warning(f"[MDČR] Response (prvních 500 znaků): {response_str[:500]}")
            return None
        
        data = api_response["Data"]
        logger.info(f"[MDČR] ✅ Data extrahována z API")
        logger.info(f"[MDČR] Data typ: {type(data)}")
        if isinstance(data, dict):
            logger.info(f"[MDČR] Data klíče ({len(data.keys())}): {list(data.keys())[:30]}")
            log_mdcr_payload_shape_summary(
                vin_masked=f"{normalized_vin[:8]}…",
                http_status=int(response.status_code),
                data=dict(data),
            )
        else:
            logger.warning(f"[MDČR] Data není dict, ale {type(data)}")
            log_mdcr_payload_shape_summary(
                vin_masked=f"{normalized_vin[:8]}…",
                http_status=int(response.status_code),
                data=None,
            )
        
        # Mapování API dat na VehicleDecodedData
        result = VehicleDecodedData(
            vin=normalized_vin,
            source_priority=["mdcr"]
        )
        
        # Helper funkce pro bezpečné získání hodnoty s fallbacky
        def get_value(*keys, default=None):
            """Zkusí najít hodnotu v data pomocí více variant klíčů"""
            return _find_mdcr_value(data, *keys, default=default)
        
        # Tovární značka (make/brand)
        make_val = (
            get_value("TovarniZnacka", "tovarniZnacka", "Tovarni_Znacka", "brand", "Brand", "make", "Make")
            or result.make
        )
        if make_val:
            result.make = str(make_val)
            result.manufacturer = str(make_val)
        
        # Obchodní označení / model
        model_val = (
            get_value("ObchodniOznaceni", "obchodniOznaceni", "Obchodni_Oznaceni", "model", "Model")
            or result.model
        )
        if model_val:
            result.model = str(model_val)
        
        # Typ vozidla (body type)
        body_type_val = (
            get_value("Typ", "typ", "BodyType", "bodyType", "vehicle_type", "VehicleType")
            or result.body_type
        )
        if body_type_val:
            result.body_type = str(body_type_val)

        color_val = (
            get_value(
                "Barva", "barva", "BarvaKaroserie", "barvaKaroserie",
                "KaroserieBarva", "karoserieBarva", "BodyColor", "bodyColor",
                "Color", "color", "Colour", "colour",
            )
            or result.exterior_color
        )
        if color_val:
            result.exterior_color = str(color_val)
        
        # Rok výroby - zkusit více zdrojů
        year_val = None
        # 1) Zkusit přímo RokVyroby
        year_val = get_value("RokVyroby", "rokVyroby", "Rok_Vyroby", "year", "Year", "production_year", "ProductionYear")
        
        # 2) Pokud není, zkusit extrahovat z DatumPrvniRegistrace
        if not year_val and data.get("DatumPrvniRegistrace"):
            try:
                date_str = str(data["DatumPrvniRegistrace"])
                if len(date_str) >= 4:
                    year_val = date_str[:4]
            except (ValueError, TypeError):
                pass
        
        # 3) Převést na int a validovat
        if year_val is not None:
            try:
                year_int = int(str(year_val))
                if 1900 <= year_int <= 2100:
                    result.production_year = year_int
                    if not result.model_year:
                        result.model_year = year_int
                else:
                    logger.warning(f"[MDČR] Nepodařilo se převést rok {year_val} na validní rok (1900-2100)")
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést rok {year_val} na int: {e}")
        
        # Datum první registrace
        reg_date = get_value("DatumPrvniRegistrace", "datumPrvniRegistrace", "Datum_Prvni_Registrace", 
                            "first_registration_date", "FirstRegistrationDate")
        if reg_date:
            result.first_registration_date = str(reg_date)
        
        # SPZ / registrační značka
        plate_val = (
            get_value("RegistracniZnacka", "registracniZnacka", "Registracni_Znacka", 
                     "plate", "Plate", "registration_plate", "RegistrationPlate")
            or result.plate
        )
        if plate_val:
            result.plate = str(plate_val).strip().upper()
        
        # Typ motoru / kód motoru
        engine_code_val = (
            get_value("MotorTyp", "motorTyp", "Motor_Typ", "KodMotoru", "kodMotoru", "Kod_Motoru",
                     "engine_code", "EngineCode", "motorCode", "MotorCode")
            or result.engine_code
        )
        if engine_code_val:
            result.engine_code = str(engine_code_val)
        
        # Max. výkon [kW]
        power_val = get_value("MotorMaxVykon", "motorMaxVykon", "Motor_Max_Vykon", 
                             "MaxVykonKw", "maxVykonKw", "Max_Vykon_Kw",
                             "VykonKw", "vykonKw", "Vykon_Kw",
                             "engine_power_kw", "EnginePowerKw", "powerKw", "PowerKw")
        if power_val is not None:
            try:
                if isinstance(power_val, (int, float)):
                    result.engine_power_kw = int(power_val)
                elif isinstance(power_val, str):
                    import re
                    numbers = re.findall(r'\d+', power_val)
                    if numbers:
                        result.engine_power_kw = int(numbers[0])
                    else:
                        logger.warning(f"[MDČR] Nepodařilo se extrahovat výkon z '{power_val}'")
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést výkon {power_val} na int: {e}")
        
        # Objem motoru [cm³]
        displacement_val = get_value("MotorZdvihObjem", "motorZdvihObjem", "Motor_Zdvih_Objem",
                                    "DisplacementCc", "displacementCc", "Displacement_Cc",
                                    "engine_displacement_cc", "EngineDisplacementCc")
        if displacement_val is not None:
            try:
                if isinstance(displacement_val, (int, float)):
                    result.engine_displacement_cc = int(displacement_val)
                elif isinstance(displacement_val, str):
                    import re
                    numbers = re.findall(r'\d+', displacement_val)
                    if numbers:
                        result.engine_displacement_cc = int(numbers[0])
                    else:
                        logger.warning(f"[MDČR] Nepodařilo se extrahovat objem z '{displacement_val}'")
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést objem {displacement_val} na int: {e}")
        
        # Palivo / druh paliva
        fuel_val = get_value("Palivo", "palivo", "DruhPaliva", "druhPaliva", "Druh_Paliva",
                            "fuel_type", "FuelType", "fuel", "Fuel")
        if fuel_val:
            fuel = str(fuel_val).lower()
            # Normalizace názvu paliva
            fuel_mapping = {
                "benzín": "petrol",
                "benzin": "petrol",
                "petrol": "petrol",
                "nafta": "diesel",
                "diesel": "diesel",
                "lpg": "lpg",
                "cng": "cng",
                "elektřina": "electric",
                "electric": "electric",
                "hybrid": "hybrid",
            }
            result.fuel_type = fuel_mapping.get(fuel, fuel)
        
        # Emisní norma / třída
        emission_val = (
            get_value("EmisniUroven", "emisniUroven", "Emisni_Uroven",
                     "EmisniTrida", "emisniTrida", "Emisni_Trida",
                     "EmissionStandard", "emissionStandard", "emission_standard", "Emission_Standard")
            or result.emission_standard
        )
        if emission_val:
            result.emission_standard = str(emission_val)
        
        # Hmotnosti
        # Provozní hmotnost / pohotovostní
        curb_weight_val = get_value("HmotnostProvozni", "hmotnostProvozni", "Hmotnost_Provozni",
                                   "PohotovostniHmotnost", "pohotovostniHmotnost", "Pohotovostni_Hmotnost",
                                   "curb_weight_kg", "CurbWeightKg", "curbWeight")
        if curb_weight_val is not None:
            try:
                if isinstance(curb_weight_val, (int, float)):
                    result.curb_weight_kg = int(curb_weight_val)
                elif isinstance(curb_weight_val, str):
                    import re
                    numbers = re.findall(r'\d+', curb_weight_val)
                    if numbers:
                        result.curb_weight_kg = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést pohotovostní hmotnost {curb_weight_val} na int: {e}")
        
        # Celková hmotnost / max. přípustná
        gross_weight_val = get_value("HmotnostCelkova", "hmotnostCelkova", "Hmotnost_Celkova",
                                    "MaxPripustnaHmotnost", "maxPripustnaHmotnost", "Max_Pripustna_Hmotnost",
                                    "gross_weight_kg", "GrossWeightKg", "grossWeight")
        if gross_weight_val is not None:
            try:
                if isinstance(gross_weight_val, (int, float)):
                    result.gross_weight_kg = int(gross_weight_val)
                elif isinstance(gross_weight_val, str):
                    import re
                    numbers = re.findall(r'\d+', gross_weight_val)
                    if numbers:
                        result.gross_weight_kg = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést celkovou hmotnost {gross_weight_val} na int: {e}")
        
        # Počet míst k sezení
        seats_val = get_value("PocetMistKSezeni", "pocetMistKSezeni", "Pocet_Mist_K_Sezeni",
                             "seats", "Seats", "numSeats", "NumSeats")
        if seats_val is not None:
            try:
                if isinstance(seats_val, (int, str)):
                    result.seats = int(seats_val)
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést počet míst {seats_val} na int: {e}")
        
        # STK platnost do / technická prohlídka
        stk_date = (
            get_value("PlatnostSTKDo", "platnostSTKDo", "Platnost_STK_Do",
                     "STKPlatnostDo", "stkPlatnostDo", "STK_Platnost_Do",
                     "TechnickaProhlidkaDo", "technickaProhlidkaDo", "Technicka_Prohlidka_Do",
                     "PravidelnaTechnickaProhlidkaDo", "pravidelnaTechnickaProhlidkaDo",
                     "stk_valid_until", "StkValidUntil", "inspection_date", "InspectionDate")
            or result.stk_valid_until
        )
        if stk_date:
            # Parsovat datum do ISO formátu
            parsed_date = parse_date_like(stk_date)
            if parsed_date:
                result.stk_valid_until = parsed_date
                result.tech_inspection_valid_to = parsed_date  # Alias pro nové pole
                logger.info(f"[MDČR] STK platnost do: {result.stk_valid_until}")
            else:
                # Fallback na string pokud se nepodařilo parsovat
                result.stk_valid_until = str(stk_date)
                result.tech_inspection_valid_to = str(stk_date)
                logger.debug(f"[MDČR] STK platnost do (neparsováno): {result.stk_valid_until}")
        
        # Typ vozidla - sestavit type_label z Typ, Varianta, Verze
        type_parts = []
        typ_val = get_value("Typ", "typ", "BodyType", "bodyType", "vehicle_type", "VehicleType")
        varianta_val = get_value("Varianta", "varianta", "Variant", "variant")
        verze_val = get_value("Verze", "verze", "Version", "version")
        
        if typ_val:
            type_parts.append(str(typ_val))
        if varianta_val:
            type_parts.append(str(varianta_val))
        if verze_val:
            type_parts.append(str(verze_val))
        
        if type_parts:
            result.type_label = " / ".join(type_parts)
            # Pokud nemáme body_type, použijeme type_label
            if not result.body_type:
                result.body_type = type_parts[0]
        
        # Typ motoru jako text - sestavit z objem, palivo, výkon
        engine_parts = []
        if result.engine_displacement_cc:
            # Převést na litry (např. 2000 cm³ → 2.0)
            liters = result.engine_displacement_cc / 1000.0
            engine_parts.append(f"{liters:.1f}".rstrip('0').rstrip('.'))
        
        # Přidat palivo
        if result.fuel_type:
            fuel_text = result.fuel_type.lower()
            fuel_mapping = {
                "diesel": "TDI",
                "petrol": "TSI",
                "benzín": "TSI",
                "benzin": "TSI",
                "nafta": "TDI",
            }
            engine_parts.append(fuel_mapping.get(fuel_text, fuel_text.upper()))
        
        # Přidat výkon
        if result.engine_power_kw:
            engine_parts.append(f"{result.engine_power_kw} kW")
        
        if engine_parts:
            result.engine_type_label = " ".join(engine_parts)
        
        # Pneumatiky (NapravyPneuRafky) - extrahovat rozměry
        tyres_raw_val = get_value("NapravyPneuRafky", "napravyPneuRafky", "Napravy_Pneu_Rafky",
                                  "tyres_raw", "TyresRaw", "pneumatiky", "Pneumatiky")
        if tyres_raw_val:
            result.tyres_raw = str(tyres_raw_val)
            logger.debug(f"[MDČR] Pneumatiky (surový text): {result.tyres_raw[:200]}")
            
            # Extrahovat rozměry pneumatik z textu - všechny možné varianty
            import re
            tyres = []
            
            # Rozšířené patterny pro všechny možné formáty kol a pneumatik z MDČR
            tyre_patterns = [
                # Standardní formáty pneumatik
                r'(\d{3}/\d{2}\s*R\s*\d{2,3}\s*\d{2,3}[A-Z]?)',  # 205/55 R 16 90V
                r'(\d{3}/\d{2}\s*R\s*\d{2,3}[A-Z]?)',            # 205/55 R16 90V
                r'(\d{3}/\d{2}\s*R\d{2,3}[A-Z]?)',               # 205/55R16C, 225/70R15C
                r'(\d{3}/\d{2}\s*R\d{2,3})',                     # 205/55R16
                r'(\d{3}x\d{2}x\d{2,3})',                        # 205x55x16
                r'(T\s*\d{3}/\d{2}\s*R\s*\d{2,3})',             # T 125/85 R 16
                
                # Formáty s koly a pneumatikami (6.00-15, 225/70R15C, atd.)
                r'(\d+\.\d{2}-\d{2,3}\s*\([^)]+\)\s*\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?\s*[SM]?)',  # 6.00-15 (E=68) 225/70R15C 112/110 S
                r'(\d+\.\d{2}-\d{2,3}\s*\([^)]+\)[,\s;:]?\s*\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?[RM]?\s*[SM]?)',  # S různými oddělovači
                r'(\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?[RM]?\s*[SM]?)',  # 225/70R15C 112/110 S
                r'(\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?[RM]?\s*M\+S)',  # S M+S
                
                # Formáty v sekci #20, #21 (VARIABILNÍ PROVEDENÍ)
                r'#20\s*\([^)]+\):\s*([^#\n]+?)(?=\n|#|$)',  # #20 (*44): 6.00-15 (E=68) 225/70R15C...
                r'#21\s*\([^)]+\):\s*([^#\n]+?)(?=\n|#|$)',  # #21 (*45): 6.00-15 (E=68); 225/70R15C...
                
                # Samostatné formáty kol
                r'(\d+\.\d{2}-\d{2,3}\s*\([^)]+\))',  # 6.00-15 (E=68)
                r'(\d+\.\d{2}-\d{2,3})',  # 6.00-15
            ]
            
            # Nejprve zkusit najít kompletní sekce s variantami (VARIABILNÍ PROVEDENÍ, #20, #21)
            variable_pattern = r'(?:VARIABILNÍ PROVEDENÍ VOZIDLA|#20|#21)[:\s]*(.*?)(?=\n\n|\nVOZIDLO|\n[A-Z]{2,}|\Z)'
            variable_matches = re.finditer(variable_pattern, result.tyres_raw, re.IGNORECASE | re.DOTALL)
            
            found_variants = []
            for var_match in variable_matches:
                variant_text = var_match.group(1)
                # Najít všechny řádky s pneumatikami v této sekci
                lines = variant_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('*'):
                        continue
                    
                    # Hledat formáty pneumatik v řádku
                    for pattern in tyre_patterns[:10]:  # První 10 patternů pro základní formáty
                        matches = re.finditer(pattern, line, re.IGNORECASE)
                        for match in matches:
                            tyre_text = match.group(1).strip()
                            # Vyčistit a normalizovat
                            tyre_text = re.sub(r'\s+', ' ', tyre_text)
                            if tyre_text and len(tyre_text) >= 5:
                                # Přidat celý řádek, pokud obsahuje kompletní informace
                                if any(x in line for x in ['/', 'R', '-']):
                                    found_variants.append(line)
                                    break
            
            # Pokud jsme našli varianty, použít je
            if found_variants:
                for variant in found_variants:
                    if variant not in tyres:
                        tyres.append(variant)
                        logger.debug(f"[MDČR] Nalezena varianta pneumatik: {variant[:80]}...")
            
            # Pak extrahovat standardní formáty
            for pattern in tyre_patterns:
                matches = re.finditer(pattern, result.tyres_raw, re.IGNORECASE)
                for match in matches:
                    tyre = match.group(1).strip()
                    if not tyre:
                        continue
                    
                    # Vyčistit a normalizovat
                    tyre = re.sub(r'\s+', ' ', tyre)
                    tyre = re.sub(r'(\d{2})\s*([rR])\s*(\d)', r'\1 \2\3', tyre)
                    tyre = re.sub(r'([rR])', 'R', tyre, count=1)
                    
                    # Přidat pouze pokud vypadá jako pneumatika/kolo
                    if len(tyre) >= 5 and (re.search(r'[\d/]', tyre) or re.search(r'R\d', tyre)):
                        if tyre not in tyres:
                            tyres.append(tyre)
                            logger.debug(f"[MDČR] Nalezena pneumatika: {tyre[:80]}...")
            
            if tyres:
                result.tyres = sorted(list(set(tyres)))
                logger.info(f"[MDČR] Extrahováno {len(result.tyres)} rozměrů/variant pneumatik")
        
        # Kola a pneumatiky - použít všechny varianty
        if result.tyres and len(result.tyres) > 0:
            # Pokud máme extrahované varianty, použít je všechny
            result.wheels_and_tyres = "\n".join(result.tyres)
        elif result.tyres_raw:
            # Pokud nemáme extrahované, použít surový text
            result.wheels_and_tyres = result.tyres_raw
        
        # Vytvořit extra_records s dalšími záznamy
        extra_records_parts = []
        if result.emission_standard:
            extra_records_parts.append(f"Emisní norma: {result.emission_standard}")
        if result.curb_weight_kg:
            extra_records_parts.append(f"Pohotovostní hmotnost: {result.curb_weight_kg} kg")
        if result.gross_weight_kg:
            extra_records_parts.append(f"Celková hmotnost: {result.gross_weight_kg} kg")
        if result.seats:
            extra_records_parts.append(f"Počet míst: {result.seats}")
        if result.body_type:
            extra_records_parts.append(f"Druh vozidla: {result.body_type}")
        if result.exterior_color:
            extra_records_parts.append(f"Barva karoserie: {result.exterior_color}")
        if result.first_registration_date:
            extra_records_parts.append(f"Datum první registrace: {result.first_registration_date}")
        
        if extra_records_parts:
            result.extra_records = "\n".join(extra_records_parts)
            logger.debug(f"[MDČR] Vytvořeny extra_records: {len(extra_records_parts)} položek")
        
        # Detailní logování všech extrahovaných hodnot
        extracted_fields = []
        if result.make: extracted_fields.append(f"značka={result.make}")
        if result.model: extracted_fields.append(f"model={result.model}")
        if result.production_year: extracted_fields.append(f"rok={result.production_year}")
        if result.engine_code: extracted_fields.append(f"motor_kód={result.engine_code}")
        if result.engine_displacement_cc: extracted_fields.append(f"objem={result.engine_displacement_cc}cm³")
        if result.engine_power_kw: extracted_fields.append(f"výkon={result.engine_power_kw}kW")
        if result.stk_valid_until: extracted_fields.append(f"STK={result.stk_valid_until}")
        if result.type_label: extracted_fields.append(f"type_label={result.type_label}")
        if result.engine_type_label: extracted_fields.append(f"engine_type_label={result.engine_type_label}")
        if result.tyres: extracted_fields.append(f"pneumatiky={len(result.tyres)}")
        if result.wheels_and_tyres: extracted_fields.append(f"wheels_and_tyres=yes")
        if result.plate: extracted_fields.append(f"SPZ={result.plate}")
        
        logger.info(f"[MDČR] ✅ Úspěšně dekódováno: {result.make} {result.model} ({result.production_year}) | {', '.join(extracted_fields)}")
        logger.info(f"[MDČR] Kompletní data: make={result.make}, model={result.model}, year={result.production_year}, engine_code={result.engine_code}, power={result.engine_power_kw}kW, type_label={result.type_label}, engine_type_label={result.engine_type_label}")
        return result
        
    except httpx.RequestError as e:
        logger.error(f"[MDČR] Chyba při volání API: {e}")
        return None
    except Exception as e:
        logger.error(f"[MDČR] Neočekávaná chyba: {e}", exc_info=True)
        return None


async def fetch_vehicle_by_plate_from_mdcr(plate: str) -> Optional[VehicleDecodedData]:
    """
    Zavolá MDČR API dle SPZ a převede JSON odpověď na VehicleDecodedData.
    
    Args:
        plate: SPZ (normalizovaná - uppercase, bez mezer)
        
    Returns:
        VehicleDecodedData nebo None při chybě/nenalezení
    """
    # Normalizace SPZ
    normalized_plate = plate.strip().upper().replace(" ", "").replace("-", "")
    
    # Kontrola konfigurace
    if not DATAOVOZIDLECH_API_KEY or not DATAOVOZIDLECH_API_URL:
        logger.warning(f"[MDČR] API není nakonfigurováno (BASE_URL nebo TOKEN chybí), vracím None pro SPZ {normalized_plate}")
        return None
    
    logger.info(f"[MDČR] Volám API pro SPZ {normalized_plate} na {DATAOVOZIDLECH_API_URL}, token nastaven: {bool(DATAOVOZIDLECH_API_KEY)}")
    
    try:
        url = f"{DATAOVOZIDLECH_API_URL}?plate={urllib.parse.quote(normalized_plate)}"
        headers = {
            "api_key": DATAOVOZIDLECH_API_KEY
        }
        
        logger.debug(f"[MDČR] Request URL: {url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
        
        logger.info(f"[MDČR] Response status {response.status_code} pro SPZ {normalized_plate}")
        
        if response.status_code != 200:
            logger.warning(f"[MDČR] API vrátilo status {response.status_code}: {response.text[:500]}")
            return None
        
        api_response = response.json()
        logger.debug(f"[MDČR] ✅ API odpověď přijata, response body (první 1000 znaků): {str(api_response)[:1000]}")
        
        # API vrací strukturu: {"Status": 1, "Data": {...}}
        if api_response.get("Status") != 1 or "Data" not in api_response:
            logger.warning(f"[MDČR] API vrátilo chybu: Status={api_response.get('Status', 'Unknown')}, response: {str(api_response)[:500]}")
            return None
        
        data = api_response["Data"]
        logger.debug(f"[MDČR] Data extrahována z API, klíče: {list(data.keys())[:20] if isinstance(data, dict) else 'N/A'}")
        
        # Použít stejné mapování jako u VIN - vytvořit base result s plate
        result = VehicleDecodedData(
            plate=normalized_plate,
            source_priority=["mdcr"]
        )
        
        # Helper funkce pro bezpečné získání hodnoty s fallbacky
        def get_value(*keys, default=None):
            """Zkusí najít hodnotu v data pomocí více variant klíčů"""
            return _find_mdcr_value(data, *keys, default=default)
        
        # VIN z API
        vin_val = get_value("VIN", "vin")
        if vin_val:
            result.vin = str(vin_val).strip().upper()
        
        # Použít stejné mapování jako u VIN (zkopírováno z fetch_vehicle_by_vin_from_mdcr)
        # Tovární značka
        make_val = (
            get_value("TovarniZnacka", "tovarniZnacka", "Tovarni_Znacka", "brand", "Brand", "make", "Make")
            or result.make
        )
        if make_val:
            result.make = str(make_val)
            result.manufacturer = str(make_val)
        
        # Model
        model_val = (
            get_value("ObchodniOznaceni", "obchodniOznaceni", "Obchodni_Oznaceni", "model", "Model")
            or result.model
        )
        if model_val:
            result.model = str(model_val)
        
        # Typ vozidla
        body_type_val = (
            get_value("Typ", "typ", "BodyType", "bodyType", "vehicle_type", "VehicleType")
            or result.body_type
        )
        if body_type_val:
            result.body_type = str(body_type_val)

        color_val = (
            get_value(
                "Barva", "barva", "BarvaKaroserie", "barvaKaroserie",
                "KaroserieBarva", "karoserieBarva", "BodyColor", "bodyColor",
                "Color", "color", "Colour", "colour",
            )
            or result.exterior_color
        )
        if color_val:
            result.exterior_color = str(color_val)
        
        # Rok výroby
        year_val = get_value("RokVyroby", "rokVyroby", "Rok_Vyroby", "year", "Year", "production_year", "ProductionYear")
        if not year_val and data.get("DatumPrvniRegistrace"):
            try:
                date_str = str(data["DatumPrvniRegistrace"])
                if len(date_str) >= 4:
                    year_val = date_str[:4]
            except (ValueError, TypeError):
                pass
        
        if year_val is not None:
            try:
                year_int = int(str(year_val))
                if 1900 <= year_int <= 2100:
                    result.production_year = year_int
                    if not result.model_year:
                        result.model_year = year_int
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést rok {year_val} na int: {e}")
        
        # Datum první registrace
        reg_date = get_value("DatumPrvniRegistrace", "datumPrvniRegistrace", "Datum_Prvni_Registrace", 
                            "first_registration_date", "FirstRegistrationDate")
        if reg_date:
            result.first_registration_date = str(reg_date)
        
        # SPZ
        plate_val = (
            get_value("RegistracniZnacka", "registracniZnacka", "Registracni_Znacka", 
                     "plate", "Plate", "registration_plate", "RegistrationPlate")
            or result.plate
        )
        if plate_val:
            result.plate = str(plate_val).strip().upper()
        
        # Zbytek mapování (stejné jako u VIN)
        # Typ motoru
        engine_code_val = (
            get_value("MotorTyp", "motorTyp", "Motor_Typ", "KodMotoru", "kodMotoru", "Kod_Motoru",
                     "engine_code", "EngineCode", "motorCode", "MotorCode")
            or result.engine_code
        )
        if engine_code_val:
            result.engine_code = str(engine_code_val)
        
        # Max. výkon [kW]
        power_val = get_value("MotorMaxVykon", "motorMaxVykon", "Motor_Max_Vykon", 
                             "MaxVykonKw", "maxVykonKw", "Max_Vykon_Kw",
                             "VykonKw", "vykonKw", "Vykon_Kw",
                             "engine_power_kw", "EnginePowerKw", "powerKw", "PowerKw")
        if power_val is not None:
            try:
                if isinstance(power_val, (int, float)):
                    result.engine_power_kw = int(power_val)
                elif isinstance(power_val, str):
                    import re
                    numbers = re.findall(r'\d+', power_val)
                    if numbers:
                        result.engine_power_kw = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést výkon {power_val} na int: {e}")
        
        # Objem motoru
        displacement_val = get_value("MotorZdvihObjem", "motorZdvihObjem", "Motor_Zdvih_Objem",
                                    "DisplacementCc", "displacementCc", "Displacement_Cc",
                                    "engine_displacement_cc", "EngineDisplacementCc")
        if displacement_val is not None:
            try:
                if isinstance(displacement_val, (int, float)):
                    result.engine_displacement_cc = int(displacement_val)
                elif isinstance(displacement_val, str):
                    import re
                    numbers = re.findall(r'\d+', displacement_val)
                    if numbers:
                        result.engine_displacement_cc = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést objem {displacement_val} na int: {e}")
        
        # Palivo
        fuel_val = get_value("Palivo", "palivo", "DruhPaliva", "druhPaliva", "Druh_Paliva",
                            "fuel_type", "FuelType", "fuel", "Fuel")
        if fuel_val:
            fuel = str(fuel_val).lower()
            fuel_mapping = {
                "benzín": "petrol", "benzin": "petrol", "petrol": "petrol",
                "nafta": "diesel", "diesel": "diesel",
                "lpg": "lpg", "cng": "cng",
                "elektřina": "electric", "electric": "electric",
                "hybrid": "hybrid",
            }
            result.fuel_type = fuel_mapping.get(fuel, fuel)
        
        # Emisní norma
        emission_val = (
            get_value("EmisniUroven", "emisniUroven", "Emisni_Uroven",
                     "EmisniTrida", "emisniTrida", "Emisni_Trida",
                     "EmissionStandard", "emissionStandard", "emission_standard", "Emission_Standard")
            or result.emission_standard
        )
        if emission_val:
            result.emission_standard = str(emission_val)
        
        # Hmotnosti
        curb_weight_val = get_value("HmotnostProvozni", "hmotnostProvozni", "Hmotnost_Provozni",
                                   "PohotovostniHmotnost", "pohotovostniHmotnost", "Pohotovostni_Hmotnost",
                                   "curb_weight_kg", "CurbWeightKg", "curbWeight")
        if curb_weight_val is not None:
            try:
                if isinstance(curb_weight_val, (int, float)):
                    result.curb_weight_kg = int(curb_weight_val)
                elif isinstance(curb_weight_val, str):
                    import re
                    numbers = re.findall(r'\d+', curb_weight_val)
                    if numbers:
                        result.curb_weight_kg = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést pohotovostní hmotnost {curb_weight_val} na int: {e}")
        
        gross_weight_val = get_value("HmotnostCelkova", "hmotnostCelkova", "Hmotnost_Celkova",
                                    "MaxPripustnaHmotnost", "maxPripustnaHmotnost", "Max_Pripustna_Hmotnost",
                                    "gross_weight_kg", "GrossWeightKg", "grossWeight")
        if gross_weight_val is not None:
            try:
                if isinstance(gross_weight_val, (int, float)):
                    result.gross_weight_kg = int(gross_weight_val)
                elif isinstance(gross_weight_val, str):
                    import re
                    numbers = re.findall(r'\d+', gross_weight_val)
                    if numbers:
                        result.gross_weight_kg = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést celkovou hmotnost {gross_weight_val} na int: {e}")
        
        # Počet míst
        seats_val = get_value("PocetMistKSezeni", "pocetMistKSezeni", "Pocet_Mist_K_Sezeni",
                             "seats", "Seats", "numSeats", "NumSeats")
        if seats_val is not None:
            try:
                if isinstance(seats_val, (int, str)):
                    result.seats = int(seats_val)
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést počet míst {seats_val} na int: {e}")
        
        # STK platnost
        stk_date = (
            get_value("PlatnostSTKDo", "platnostSTKDo", "Platnost_STK_Do",
                     "STKPlatnostDo", "stkPlatnostDo", "STK_Platnost_Do",
                     "TechnickaProhlidkaDo", "technickaProhlidkaDo", "Technicka_Prohlidka_Do",
                     "PravidelnaTechnickaProhlidkaDo", "pravidelnaTechnickaProhlidkaDo",
                     "stk_valid_until", "StkValidUntil", "inspection_date", "InspectionDate")
            or result.stk_valid_until
        )
        if stk_date:
            result.stk_valid_until = str(stk_date)
            logger.debug(f"[MDČR] STK platnost do: {result.stk_valid_until}")
        
        # Pneumatiky (NapravyPneuRafky) - extrahovat rozměry (stejná rozšířená logika jako u VIN)
        tyres_raw_val = get_value("NapravyPneuRafky", "napravyPneuRafky", "Napravy_Pneu_Rafky",
                                  "tyres_raw", "TyresRaw", "pneumatiky", "Pneumatiky")
        if tyres_raw_val:
            result.tyres_raw = str(tyres_raw_val)
            logger.debug(f"[MDČR] Pneumatiky (surový text): {result.tyres_raw[:200]}")
            
            # Použít stejnou rozšířenou logiku jako u VIN (kopírováno z výše)
            import re
            tyres = []
            
            # Rozšířené patterny pro všechny možné formáty kol a pneumatik z MDČR
            tyre_patterns = [
                # Standardní formáty pneumatik
                r'(\d{3}/\d{2}\s*R\s*\d{2,3}\s*\d{2,3}[A-Z]?)',  # 205/55 R 16 90V
                r'(\d{3}/\d{2}\s*R\s*\d{2,3}[A-Z]?)',            # 205/55 R16 90V
                r'(\d{3}/\d{2}\s*R\d{2,3}[A-Z]?)',               # 205/55R16C, 225/70R15C
                r'(\d{3}/\d{2}\s*R\d{2,3})',                     # 205/55R16
                r'(\d{3}x\d{2}x\d{2,3})',                        # 205x55x16
                r'(T\s*\d{3}/\d{2}\s*R\s*\d{2,3})',             # T 125/85 R 16
                
                # Formáty s koly a pneumatikami (6.00-15, 225/70R15C, atd.)
                r'(\d+\.\d{2}-\d{2,3}\s*\([^)]+\)\s*\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?\s*[SM]?)',  # 6.00-15 (E=68) 225/70R15C 112/110 S
                r'(\d+\.\d{2}-\d{2,3}\s*\([^)]+\)[,\s;:]?\s*\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?[RM]?\s*[SM]?)',  # S různými oddělovači
                r'(\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?[RM]?\s*[SM]?)',  # 225/70R15C 112/110 S
                r'(\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?[RM]?\s*M\+S)',  # S M+S
                
                # Formáty v sekci #20, #21 (VARIABILNÍ PROVEDENÍ)
                r'#20\s*\([^)]+\):\s*([^#\n]+?)(?=\n|#|$)',  # #20 (*44): 6.00-15 (E=68) 225/70R15C...
                r'#21\s*\([^)]+\):\s*([^#\n]+?)(?=\n|#|$)',  # #21 (*45): 6.00-15 (E=68); 225/70R15C...
                
                # Samostatné formáty kol
                r'(\d+\.\d{2}-\d{2,3}\s*\([^)]+\))',  # 6.00-15 (E=68)
                r'(\d+\.\d{2}-\d{2,3})',  # 6.00-15
            ]
            
            # Nejprve zkusit najít kompletní sekce s variantami (VARIABILNÍ PROVEDENÍ, #20, #21)
            variable_pattern = r'(?:VARIABILNÍ PROVEDENÍ VOZIDLA|#20|#21)[:\s]*(.*?)(?=\n\n|\nVOZIDLO|\n[A-Z]{2,}|\Z)'
            variable_matches = re.finditer(variable_pattern, result.tyres_raw, re.IGNORECASE | re.DOTALL)
            
            found_variants = []
            for var_match in variable_matches:
                variant_text = var_match.group(1)
                # Najít všechny řádky s pneumatikami v této sekci
                lines = variant_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('*'):
                        continue
                    
                    # Hledat formáty pneumatik v řádku
                    for pattern in tyre_patterns[:10]:  # První 10 patternů pro základní formáty
                        matches = re.finditer(pattern, line, re.IGNORECASE)
                        for match in matches:
                            tyre_text = match.group(1).strip()
                            # Vyčistit a normalizovat
                            tyre_text = re.sub(r'\s+', ' ', tyre_text)
                            if tyre_text and len(tyre_text) >= 5:
                                # Přidat celý řádek, pokud obsahuje kompletní informace
                                if any(x in line for x in ['/', 'R', '-']):
                                    found_variants.append(line)
                                    break
            
            # Pokud jsme našli varianty, použít je
            if found_variants:
                for variant in found_variants:
                    if variant not in tyres:
                        tyres.append(variant)
                        logger.debug(f"[MDČR] Nalezena varianta pneumatik: {variant[:80]}...")
            
            # Pak extrahovat standardní formáty
            for pattern in tyre_patterns:
                matches = re.finditer(pattern, result.tyres_raw, re.IGNORECASE)
                for match in matches:
                    tyre = match.group(1).strip()
                    if not tyre:
                        continue
                    
                    # Vyčistit a normalizovat
                    tyre = re.sub(r'\s+', ' ', tyre)
                    tyre = re.sub(r'(\d{2})\s*([rR])\s*(\d)', r'\1 \2\3', tyre)
                    tyre = re.sub(r'([rR])', 'R', tyre, count=1)
                    
                    # Přidat pouze pokud vypadá jako pneumatika/kolo
                    if len(tyre) >= 5 and (re.search(r'[\d/]', tyre) or re.search(r'R\d', tyre)):
                        if tyre not in tyres:
                            tyres.append(tyre)
                            logger.debug(f"[MDČR] Nalezena pneumatika: {tyre[:80]}...")
            
            if tyres:
                result.tyres = sorted(list(set(tyres)))
                logger.info(f"[MDČR] Extrahováno {len(result.tyres)} rozměrů/variant pneumatik")
            
            # Kola a pneumatiky - použít všechny varianty
            if result.tyres and len(result.tyres) > 0:
                result.wheels_and_tyres = "\n".join(result.tyres)
            elif result.tyres_raw:
                result.wheels_and_tyres = result.tyres_raw
        
        # Detailní logování všech extrahovaných hodnot
        extracted_fields = []
        if result.make: extracted_fields.append(f"značka={result.make}")
        if result.model: extracted_fields.append(f"model={result.model}")
        if result.production_year: extracted_fields.append(f"rok={result.production_year}")
        if result.engine_code: extracted_fields.append(f"motor_kód={result.engine_code}")
        if result.engine_displacement_cc: extracted_fields.append(f"objem={result.engine_displacement_cc}cm³")
        if result.engine_power_kw: extracted_fields.append(f"výkon={result.engine_power_kw}kW")
        if result.stk_valid_until: extracted_fields.append(f"STK={result.stk_valid_until}")
        if result.tyres: extracted_fields.append(f"pneumatiky={len(result.tyres)}")
        if result.plate: extracted_fields.append(f"SPZ={result.plate}")
        
        logger.info(f"[MDČR] ✅ Úspěšně dekódováno podle SPZ: {result.make} {result.model} ({result.production_year}) | {', '.join(extracted_fields)}")
        return result
        
    except httpx.RequestError as e:
        logger.error(f"[MDČR] Chyba při volání API podle SPZ: {e}")
        return None
    except Exception as e:
        logger.error(f"[MDČR] Neočekávaná chyba při volání API podle SPZ: {e}", exc_info=True)
        return None
        return None
    
    # Detailní logování konfigurace
    logger.info(f"[MDČR] ========================================")
    logger.info(f"[MDČR] Dekóduji VIN: {normalized_vin}")
    logger.info(f"[MDČR] API URL: {DATAOVOZIDLECH_API_URL}")
    logger.info(f"[MDČR] Token nastaven: {bool(DATAOVOZIDLECH_API_KEY)}")
    logger.info(f"[MDČR] Token délka: {len(DATAOVOZIDLECH_API_KEY) if DATAOVOZIDLECH_API_KEY else 0} znaků")
    
    try:
        url = f"{DATAOVOZIDLECH_API_URL}?vin={urllib.parse.quote(normalized_vin)}"
        headers = {
            "api_key": DATAOVOZIDLECH_API_KEY
        }
        
        logger.info(f"[MDČR] Request URL: {url}")
        logger.debug(f"[MDČR] Request headers: api_key={'***' + DATAOVOZIDLECH_API_KEY[-4:] if DATAOVOZIDLECH_API_KEY else 'N/A'}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
        
        logger.info(f"[MDČR] Response status: {response.status_code}")
        logger.info(f"[MDČR] Response headers: {dict(response.headers)}")
        
        if response.status_code != 200:
            logger.warning(f"[MDČR] ❌ API vrátilo status {response.status_code}")
            logger.warning(f"[MDČR] Response text (prvních 500 znaků): {response.text[:500]}")
            return None
        
        api_response = response.json()
        
        # Detailní logování odpovědi
        response_str = str(api_response)
        logger.info(f"[MDČR] ✅ API odpověď přijata")
        logger.info(f"[MDČR] Response body délka: {len(response_str)} znaků")
        logger.info(f"[MDČR] Response body (prvních 500 znaků): {response_str[:500]}")
        logger.debug(f"[MDČR] Celá response: {response_str}")
        
        # API vrací strukturu: {"Status": 1, "Data": {...}} nebo {"Success": true/false, "Data": {...}}
        # Kontrola obou variant pro kompatibilitu
        status = api_response.get("Status")
        success = api_response.get("Success")
        
        # Pokud Success: false, vrátit None
        if success is False:
            logger.warning(f"[MDČR] ❌ API vrátilo Success: false")
            logger.warning(f"[MDČR] Response (prvních 500 znaků): {response_str[:500]}")
            return None
        
        # Pokud Status není 1 nebo Success není True, a není Data
        if (status != 1 and success is not True) or "Data" not in api_response:
            logger.warning(f"[MDČR] ❌ API vrátilo chybu")
            logger.warning(f"[MDČR] Status: {status}, Success: {success}")
            logger.warning(f"[MDČR] Má 'Data' klíč: {'Data' in api_response}")
            logger.warning(f"[MDČR] Response (prvních 500 znaků): {response_str[:500]}")
            return None
        
        data = api_response["Data"]
        logger.info(f"[MDČR] ✅ Data extrahována z API")
        logger.info(f"[MDČR] Data typ: {type(data)}")
        if isinstance(data, dict):
            logger.info(f"[MDČR] Data klíče ({len(data.keys())}): {list(data.keys())[:30]}")
            log_mdcr_payload_shape_summary(
                vin_masked=f"{normalized_vin[:8]}…",
                http_status=int(response.status_code),
                data=dict(data),
            )
        else:
            logger.warning(f"[MDČR] Data není dict, ale {type(data)}")
            log_mdcr_payload_shape_summary(
                vin_masked=f"{normalized_vin[:8]}…",
                http_status=int(response.status_code),
                data=None,
            )
        
        # Mapování API dat na VehicleDecodedData
        result = VehicleDecodedData(
            vin=normalized_vin,
            source_priority=["mdcr"]
        )
        
        # Helper funkce pro bezpečné získání hodnoty s fallbacky
        def get_value(*keys, default=None):
            """Zkusí najít hodnotu v data pomocí více variant klíčů"""
            return _find_mdcr_value(data, *keys, default=default)
        
        # Tovární značka (make/brand)
        make_val = (
            get_value("TovarniZnacka", "tovarniZnacka", "Tovarni_Znacka", "brand", "Brand", "make", "Make")
            or result.make
        )
        if make_val:
            result.make = str(make_val)
            result.manufacturer = str(make_val)
        
        # Obchodní označení / model
        model_val = (
            get_value("ObchodniOznaceni", "obchodniOznaceni", "Obchodni_Oznaceni", "model", "Model")
            or result.model
        )
        if model_val:
            result.model = str(model_val)
        
        # Typ vozidla (body type)
        body_type_val = (
            get_value("Typ", "typ", "BodyType", "bodyType", "vehicle_type", "VehicleType")
            or result.body_type
        )
        if body_type_val:
            result.body_type = str(body_type_val)

        color_val = (
            get_value(
                "Barva", "barva", "BarvaKaroserie", "barvaKaroserie",
                "KaroserieBarva", "karoserieBarva", "BodyColor", "bodyColor",
                "Color", "color", "Colour", "colour",
            )
            or result.exterior_color
        )
        if color_val:
            result.exterior_color = str(color_val)
        
        # Rok výroby - zkusit více zdrojů
        year_val = None
        # 1) Zkusit přímo RokVyroby
        year_val = get_value("RokVyroby", "rokVyroby", "Rok_Vyroby", "year", "Year", "production_year", "ProductionYear")
        
        # 2) Pokud není, zkusit extrahovat z DatumPrvniRegistrace
        if not year_val and data.get("DatumPrvniRegistrace"):
            try:
                date_str = str(data["DatumPrvniRegistrace"])
                if len(date_str) >= 4:
                    year_val = date_str[:4]
            except (ValueError, TypeError):
                pass
        
        # 3) Převést na int a validovat
        if year_val is not None:
            try:
                year_int = int(str(year_val))
                if 1900 <= year_int <= 2100:
                    result.production_year = year_int
                    if not result.model_year:
                        result.model_year = year_int
                else:
                    logger.warning(f"[MDČR] Nepodařilo se převést rok {year_val} na validní rok (1900-2100)")
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést rok {year_val} na int: {e}")
        
        # Datum první registrace
        reg_date = get_value("DatumPrvniRegistrace", "datumPrvniRegistrace", "Datum_Prvni_Registrace", 
                            "first_registration_date", "FirstRegistrationDate")
        if reg_date:
            result.first_registration_date = str(reg_date)
        
        # SPZ / registrační značka
        plate_val = (
            get_value("RegistracniZnacka", "registracniZnacka", "Registracni_Znacka", 
                     "plate", "Plate", "registration_plate", "RegistrationPlate")
            or result.plate
        )
        if plate_val:
            result.plate = str(plate_val).strip().upper()
        
        # Typ motoru / kód motoru
        engine_code_val = (
            get_value("MotorTyp", "motorTyp", "Motor_Typ", "KodMotoru", "kodMotoru", "Kod_Motoru",
                     "engine_code", "EngineCode", "motorCode", "MotorCode")
            or result.engine_code
        )
        if engine_code_val:
            result.engine_code = str(engine_code_val)
        
        # Max. výkon [kW]
        power_val = get_value("MotorMaxVykon", "motorMaxVykon", "Motor_Max_Vykon", 
                             "MaxVykonKw", "maxVykonKw", "Max_Vykon_Kw",
                             "VykonKw", "vykonKw", "Vykon_Kw",
                             "engine_power_kw", "EnginePowerKw", "powerKw", "PowerKw")
        if power_val is not None:
            try:
                if isinstance(power_val, (int, float)):
                    result.engine_power_kw = int(power_val)
                elif isinstance(power_val, str):
                    import re
                    numbers = re.findall(r'\d+', power_val)
                    if numbers:
                        result.engine_power_kw = int(numbers[0])
                    else:
                        logger.warning(f"[MDČR] Nepodařilo se extrahovat výkon z '{power_val}'")
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést výkon {power_val} na int: {e}")
        
        # Objem motoru [cm³]
        displacement_val = get_value("MotorZdvihObjem", "motorZdvihObjem", "Motor_Zdvih_Objem",
                                    "DisplacementCc", "displacementCc", "Displacement_Cc",
                                    "engine_displacement_cc", "EngineDisplacementCc")
        if displacement_val is not None:
            try:
                if isinstance(displacement_val, (int, float)):
                    result.engine_displacement_cc = int(displacement_val)
                elif isinstance(displacement_val, str):
                    import re
                    numbers = re.findall(r'\d+', displacement_val)
                    if numbers:
                        result.engine_displacement_cc = int(numbers[0])
                    else:
                        logger.warning(f"[MDČR] Nepodařilo se extrahovat objem z '{displacement_val}'")
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést objem {displacement_val} na int: {e}")
        
        # Palivo / druh paliva
        fuel_val = get_value("Palivo", "palivo", "DruhPaliva", "druhPaliva", "Druh_Paliva",
                            "fuel_type", "FuelType", "fuel", "Fuel")
        if fuel_val:
            fuel = str(fuel_val).lower()
            # Normalizace názvu paliva
            fuel_mapping = {
                "benzín": "petrol",
                "benzin": "petrol",
                "petrol": "petrol",
                "nafta": "diesel",
                "diesel": "diesel",
                "lpg": "lpg",
                "cng": "cng",
                "elektřina": "electric",
                "electric": "electric",
                "hybrid": "hybrid",
            }
            result.fuel_type = fuel_mapping.get(fuel, fuel)
        
        # Emisní norma / třída
        emission_val = (
            get_value("EmisniUroven", "emisniUroven", "Emisni_Uroven",
                     "EmisniTrida", "emisniTrida", "Emisni_Trida",
                     "EmissionStandard", "emissionStandard", "emission_standard", "Emission_Standard")
            or result.emission_standard
        )
        if emission_val:
            result.emission_standard = str(emission_val)
        
        # Hmotnosti
        # Provozní hmotnost / pohotovostní
        curb_weight_val = get_value("HmotnostProvozni", "hmotnostProvozni", "Hmotnost_Provozni",
                                   "PohotovostniHmotnost", "pohotovostniHmotnost", "Pohotovostni_Hmotnost",
                                   "curb_weight_kg", "CurbWeightKg", "curbWeight")
        if curb_weight_val is not None:
            try:
                if isinstance(curb_weight_val, (int, float)):
                    result.curb_weight_kg = int(curb_weight_val)
                elif isinstance(curb_weight_val, str):
                    import re
                    numbers = re.findall(r'\d+', curb_weight_val)
                    if numbers:
                        result.curb_weight_kg = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést pohotovostní hmotnost {curb_weight_val} na int: {e}")
        
        # Celková hmotnost / max. přípustná
        gross_weight_val = get_value("HmotnostCelkova", "hmotnostCelkova", "Hmotnost_Celkova",
                                    "MaxPripustnaHmotnost", "maxPripustnaHmotnost", "Max_Pripustna_Hmotnost",
                                    "gross_weight_kg", "GrossWeightKg", "grossWeight")
        if gross_weight_val is not None:
            try:
                if isinstance(gross_weight_val, (int, float)):
                    result.gross_weight_kg = int(gross_weight_val)
                elif isinstance(gross_weight_val, str):
                    import re
                    numbers = re.findall(r'\d+', gross_weight_val)
                    if numbers:
                        result.gross_weight_kg = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést celkovou hmotnost {gross_weight_val} na int: {e}")
        
        # Počet míst k sezení
        seats_val = get_value("PocetMistKSezeni", "pocetMistKSezeni", "Pocet_Mist_K_Sezeni",
                             "seats", "Seats", "numSeats", "NumSeats")
        if seats_val is not None:
            try:
                if isinstance(seats_val, (int, str)):
                    result.seats = int(seats_val)
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést počet míst {seats_val} na int: {e}")
        
        # STK platnost do / technická prohlídka
        stk_date = (
            get_value("PlatnostSTKDo", "platnostSTKDo", "Platnost_STK_Do",
                     "STKPlatnostDo", "stkPlatnostDo", "STK_Platnost_Do",
                     "TechnickaProhlidkaDo", "technickaProhlidkaDo", "Technicka_Prohlidka_Do",
                     "PravidelnaTechnickaProhlidkaDo", "pravidelnaTechnickaProhlidkaDo",
                     "stk_valid_until", "StkValidUntil", "inspection_date", "InspectionDate")
            or result.stk_valid_until
        )
        if stk_date:
            # Parsovat datum do ISO formátu
            parsed_date = parse_date_like(stk_date)
            if parsed_date:
                result.stk_valid_until = parsed_date
                result.tech_inspection_valid_to = parsed_date  # Alias pro nové pole
                logger.info(f"[MDČR] STK platnost do: {result.stk_valid_until}")
            else:
                # Fallback na string pokud se nepodařilo parsovat
                result.stk_valid_until = str(stk_date)
                result.tech_inspection_valid_to = str(stk_date)
                logger.debug(f"[MDČR] STK platnost do (neparsováno): {result.stk_valid_until}")
        
        # Typ vozidla - sestavit type_label z Typ, Varianta, Verze
        type_parts = []
        typ_val = get_value("Typ", "typ", "BodyType", "bodyType", "vehicle_type", "VehicleType")
        varianta_val = get_value("Varianta", "varianta", "Variant", "variant")
        verze_val = get_value("Verze", "verze", "Version", "version")
        
        if typ_val:
            type_parts.append(str(typ_val))
        if varianta_val:
            type_parts.append(str(varianta_val))
        if verze_val:
            type_parts.append(str(verze_val))
        
        if type_parts:
            result.type_label = " / ".join(type_parts)
            # Pokud nemáme body_type, použijeme type_label
            if not result.body_type:
                result.body_type = type_parts[0]
        
        # Typ motoru jako text - sestavit z objem, palivo, výkon
        engine_parts = []
        if result.engine_displacement_cc:
            # Převést na litry (např. 2000 cm³ → 2.0)
            liters = result.engine_displacement_cc / 1000.0
            engine_parts.append(f"{liters:.1f}".rstrip('0').rstrip('.'))
        
        # Přidat palivo
        if result.fuel_type:
            fuel_text = result.fuel_type.lower()
            fuel_mapping = {
                "diesel": "TDI",
                "petrol": "TSI",
                "benzín": "TSI",
                "benzin": "TSI",
                "nafta": "TDI",
            }
            engine_parts.append(fuel_mapping.get(fuel_text, fuel_text.upper()))
        
        # Přidat výkon
        if result.engine_power_kw:
            engine_parts.append(f"{result.engine_power_kw} kW")
        
        if engine_parts:
            result.engine_type_label = " ".join(engine_parts)
        
        # Pneumatiky (NapravyPneuRafky) - extrahovat rozměry
        tyres_raw_val = get_value("NapravyPneuRafky", "napravyPneuRafky", "Napravy_Pneu_Rafky",
                                  "tyres_raw", "TyresRaw", "pneumatiky", "Pneumatiky")
        if tyres_raw_val:
            result.tyres_raw = str(tyres_raw_val)
            logger.debug(f"[MDČR] Pneumatiky (surový text): {result.tyres_raw[:200]}")
            
            # Extrahovat rozměry pneumatik z textu - všechny možné varianty
            import re
            tyres = []
            
            # Rozšířené patterny pro všechny možné formáty kol a pneumatik z MDČR
            tyre_patterns = [
                # Standardní formáty pneumatik
                r'(\d{3}/\d{2}\s*R\s*\d{2,3}\s*\d{2,3}[A-Z]?)',  # 205/55 R 16 90V
                r'(\d{3}/\d{2}\s*R\s*\d{2,3}[A-Z]?)',            # 205/55 R16 90V
                r'(\d{3}/\d{2}\s*R\d{2,3}[A-Z]?)',               # 205/55R16C, 225/70R15C
                r'(\d{3}/\d{2}\s*R\d{2,3})',                     # 205/55R16
                r'(\d{3}x\d{2}x\d{2,3})',                        # 205x55x16
                r'(T\s*\d{3}/\d{2}\s*R\s*\d{2,3})',             # T 125/85 R 16
                
                # Formáty s koly a pneumatikami (6.00-15, 225/70R15C, atd.)
                r'(\d+\.\d{2}-\d{2,3}\s*\([^)]+\)\s*\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?\s*[SM]?)',  # 6.00-15 (E=68) 225/70R15C 112/110 S
                r'(\d+\.\d{2}-\d{2,3}\s*\([^)]+\)[,\s;:]?\s*\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?[RM]?\s*[SM]?)',  # S různými oddělovači
                r'(\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?[RM]?\s*[SM]?)',  # 225/70R15C 112/110 S
                r'(\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?[RM]?\s*M\+S)',  # S M+S
                
                # Formáty v sekci #20, #21 (VARIABILNÍ PROVEDENÍ)
                r'#20\s*\([^)]+\):\s*([^#\n]+?)(?=\n|#|$)',  # #20 (*44): 6.00-15 (E=68) 225/70R15C...
                r'#21\s*\([^)]+\):\s*([^#\n]+?)(?=\n|#|$)',  # #21 (*45): 6.00-15 (E=68); 225/70R15C...
                
                # Samostatné formáty kol
                r'(\d+\.\d{2}-\d{2,3}\s*\([^)]+\))',  # 6.00-15 (E=68)
                r'(\d+\.\d{2}-\d{2,3})',  # 6.00-15
            ]
            
            # Nejprve zkusit najít kompletní sekce s variantami (VARIABILNÍ PROVEDENÍ, #20, #21)
            variable_pattern = r'(?:VARIABILNÍ PROVEDENÍ VOZIDLA|#20|#21)[:\s]*(.*?)(?=\n\n|\nVOZIDLO|\n[A-Z]{2,}|\Z)'
            variable_matches = re.finditer(variable_pattern, result.tyres_raw, re.IGNORECASE | re.DOTALL)
            
            found_variants = []
            for var_match in variable_matches:
                variant_text = var_match.group(1)
                # Najít všechny řádky s pneumatikami v této sekci
                lines = variant_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('*'):
                        continue
                    
                    # Hledat formáty pneumatik v řádku
                    for pattern in tyre_patterns[:10]:  # První 10 patternů pro základní formáty
                        matches = re.finditer(pattern, line, re.IGNORECASE)
                        for match in matches:
                            tyre_text = match.group(1).strip()
                            # Vyčistit a normalizovat
                            tyre_text = re.sub(r'\s+', ' ', tyre_text)
                            if tyre_text and len(tyre_text) >= 5:
                                # Přidat celý řádek, pokud obsahuje kompletní informace
                                if any(x in line for x in ['/', 'R', '-']):
                                    found_variants.append(line)
                                    break
            
            # Pokud jsme našli varianty, použít je
            if found_variants:
                for variant in found_variants:
                    if variant not in tyres:
                        tyres.append(variant)
                        logger.debug(f"[MDČR] Nalezena varianta pneumatik: {variant[:80]}...")
            
            # Pak extrahovat standardní formáty
            for pattern in tyre_patterns:
                matches = re.finditer(pattern, result.tyres_raw, re.IGNORECASE)
                for match in matches:
                    tyre = match.group(1).strip()
                    if not tyre:
                        continue
                    
                    # Vyčistit a normalizovat
                    tyre = re.sub(r'\s+', ' ', tyre)
                    tyre = re.sub(r'(\d{2})\s*([rR])\s*(\d)', r'\1 \2\3', tyre)
                    tyre = re.sub(r'([rR])', 'R', tyre, count=1)
                    
                    # Přidat pouze pokud vypadá jako pneumatika/kolo
                    if len(tyre) >= 5 and (re.search(r'[\d/]', tyre) or re.search(r'R\d', tyre)):
                        if tyre not in tyres:
                            tyres.append(tyre)
                            logger.debug(f"[MDČR] Nalezena pneumatika: {tyre[:80]}...")
            
            if tyres:
                result.tyres = sorted(list(set(tyres)))
                logger.info(f"[MDČR] Extrahováno {len(result.tyres)} rozměrů/variant pneumatik")
        
        # Kola a pneumatiky - použít všechny varianty
        if result.tyres and len(result.tyres) > 0:
            # Pokud máme extrahované varianty, použít je všechny
            result.wheels_and_tyres = "\n".join(result.tyres)
        elif result.tyres_raw:
            # Pokud nemáme extrahované, použít surový text
            result.wheels_and_tyres = result.tyres_raw
        
        # Vytvořit extra_records s dalšími záznamy
        extra_records_parts = []
        if result.emission_standard:
            extra_records_parts.append(f"Emisní norma: {result.emission_standard}")
        if result.curb_weight_kg:
            extra_records_parts.append(f"Pohotovostní hmotnost: {result.curb_weight_kg} kg")
        if result.gross_weight_kg:
            extra_records_parts.append(f"Celková hmotnost: {result.gross_weight_kg} kg")
        if result.seats:
            extra_records_parts.append(f"Počet míst: {result.seats}")
        if result.body_type:
            extra_records_parts.append(f"Druh vozidla: {result.body_type}")
        if result.exterior_color:
            extra_records_parts.append(f"Barva karoserie: {result.exterior_color}")
        if result.first_registration_date:
            extra_records_parts.append(f"Datum první registrace: {result.first_registration_date}")
        
        if extra_records_parts:
            result.extra_records = "\n".join(extra_records_parts)
            logger.debug(f"[MDČR] Vytvořeny extra_records: {len(extra_records_parts)} položek")
        
        # Detailní logování všech extrahovaných hodnot
        extracted_fields = []
        if result.make: extracted_fields.append(f"značka={result.make}")
        if result.model: extracted_fields.append(f"model={result.model}")
        if result.production_year: extracted_fields.append(f"rok={result.production_year}")
        if result.engine_code: extracted_fields.append(f"motor_kód={result.engine_code}")
        if result.engine_displacement_cc: extracted_fields.append(f"objem={result.engine_displacement_cc}cm³")
        if result.engine_power_kw: extracted_fields.append(f"výkon={result.engine_power_kw}kW")
        if result.stk_valid_until: extracted_fields.append(f"STK={result.stk_valid_until}")
        if result.type_label: extracted_fields.append(f"type_label={result.type_label}")
        if result.engine_type_label: extracted_fields.append(f"engine_type_label={result.engine_type_label}")
        if result.tyres: extracted_fields.append(f"pneumatiky={len(result.tyres)}")
        if result.wheels_and_tyres: extracted_fields.append(f"wheels_and_tyres=yes")
        if result.plate: extracted_fields.append(f"SPZ={result.plate}")
        
        logger.info(f"[MDČR] ✅ Úspěšně dekódováno: {result.make} {result.model} ({result.production_year}) | {', '.join(extracted_fields)}")
        logger.info(f"[MDČR] Kompletní data: make={result.make}, model={result.model}, year={result.production_year}, engine_code={result.engine_code}, power={result.engine_power_kw}kW, type_label={result.type_label}, engine_type_label={result.engine_type_label}")
        return result
        
    except httpx.RequestError as e:
        logger.error(f"[MDČR] Chyba při volání API: {e}")
        return None
    except Exception as e:
        logger.error(f"[MDČR] Neočekávaná chyba: {e}", exc_info=True)
        return None


async def fetch_vehicle_by_plate_from_mdcr(plate: str) -> Optional[VehicleDecodedData]:
    """
    Zavolá MDČR API dle SPZ a převede JSON odpověď na VehicleDecodedData.
    
    Args:
        plate: SPZ (normalizovaná - uppercase, bez mezer)
        
    Returns:
        VehicleDecodedData nebo None při chybě/nenalezení
    """
    # Normalizace SPZ
    normalized_plate = plate.strip().upper().replace(" ", "").replace("-", "")
    
    # Kontrola konfigurace
    if not DATAOVOZIDLECH_API_KEY or not DATAOVOZIDLECH_API_URL:
        logger.warning(f"[MDČR] API není nakonfigurováno (BASE_URL nebo TOKEN chybí), vracím None pro SPZ {normalized_plate}")
        return None
    
    logger.info(f"[MDČR] Volám API pro SPZ {normalized_plate} na {DATAOVOZIDLECH_API_URL}, token nastaven: {bool(DATAOVOZIDLECH_API_KEY)}")
    
    try:
        url = f"{DATAOVOZIDLECH_API_URL}?plate={urllib.parse.quote(normalized_plate)}"
        headers = {
            "api_key": DATAOVOZIDLECH_API_KEY
        }
        
        logger.debug(f"[MDČR] Request URL: {url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
        
        logger.info(f"[MDČR] Response status {response.status_code} pro SPZ {normalized_plate}")
        
        if response.status_code != 200:
            logger.warning(f"[MDČR] API vrátilo status {response.status_code}: {response.text[:500]}")
            return None
        
        api_response = response.json()
        logger.debug(f"[MDČR] ✅ API odpověď přijata, response body (první 1000 znaků): {str(api_response)[:1000]}")
        
        # API vrací strukturu: {"Status": 1, "Data": {...}}
        if api_response.get("Status") != 1 or "Data" not in api_response:
            logger.warning(f"[MDČR] API vrátilo chybu: Status={api_response.get('Status', 'Unknown')}, response: {str(api_response)[:500]}")
            return None
        
        data = api_response["Data"]
        logger.debug(f"[MDČR] Data extrahována z API, klíče: {list(data.keys())[:20] if isinstance(data, dict) else 'N/A'}")
        
        # Použít stejné mapování jako u VIN - vytvořit base result s plate
        result = VehicleDecodedData(
            plate=normalized_plate,
            source_priority=["mdcr"]
        )
        
        # Helper funkce pro bezpečné získání hodnoty s fallbacky
        def get_value(*keys, default=None):
            """Zkusí najít hodnotu v data pomocí více variant klíčů"""
            return _find_mdcr_value(data, *keys, default=default)
        
        # VIN z API
        vin_val = get_value("VIN", "vin")
        if vin_val:
            result.vin = str(vin_val).strip().upper()
        
        # Použít stejné mapování jako u VIN (zkopírováno z fetch_vehicle_by_vin_from_mdcr)
        # Tovární značka
        make_val = (
            get_value("TovarniZnacka", "tovarniZnacka", "Tovarni_Znacka", "brand", "Brand", "make", "Make")
            or result.make
        )
        if make_val:
            result.make = str(make_val)
            result.manufacturer = str(make_val)
        
        # Model
        model_val = (
            get_value("ObchodniOznaceni", "obchodniOznaceni", "Obchodni_Oznaceni", "model", "Model")
            or result.model
        )
        if model_val:
            result.model = str(model_val)
        
        # Typ vozidla
        body_type_val = (
            get_value("Typ", "typ", "BodyType", "bodyType", "vehicle_type", "VehicleType")
            or result.body_type
        )
        if body_type_val:
            result.body_type = str(body_type_val)

        color_val = (
            get_value(
                "Barva", "barva", "BarvaKaroserie", "barvaKaroserie",
                "KaroserieBarva", "karoserieBarva", "BodyColor", "bodyColor",
                "Color", "color", "Colour", "colour",
            )
            or result.exterior_color
        )
        if color_val:
            result.exterior_color = str(color_val)
        
        # Rok výroby
        year_val = get_value("RokVyroby", "rokVyroby", "Rok_Vyroby", "year", "Year", "production_year", "ProductionYear")
        if not year_val and data.get("DatumPrvniRegistrace"):
            try:
                date_str = str(data["DatumPrvniRegistrace"])
                if len(date_str) >= 4:
                    year_val = date_str[:4]
            except (ValueError, TypeError):
                pass
        
        if year_val is not None:
            try:
                year_int = int(str(year_val))
                if 1900 <= year_int <= 2100:
                    result.production_year = year_int
                    if not result.model_year:
                        result.model_year = year_int
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést rok {year_val} na int: {e}")
        
        # Datum první registrace
        reg_date = get_value("DatumPrvniRegistrace", "datumPrvniRegistrace", "Datum_Prvni_Registrace", 
                            "first_registration_date", "FirstRegistrationDate")
        if reg_date:
            result.first_registration_date = str(reg_date)
        
        # SPZ
        plate_val = (
            get_value("RegistracniZnacka", "registracniZnacka", "Registracni_Znacka", 
                     "plate", "Plate", "registration_plate", "RegistrationPlate")
            or result.plate
        )
        if plate_val:
            result.plate = str(plate_val).strip().upper()
        
        # Zbytek mapování (stejné jako u VIN)
        # Typ motoru
        engine_code_val = (
            get_value("MotorTyp", "motorTyp", "Motor_Typ", "KodMotoru", "kodMotoru", "Kod_Motoru",
                     "engine_code", "EngineCode", "motorCode", "MotorCode")
            or result.engine_code
        )
        if engine_code_val:
            result.engine_code = str(engine_code_val)
        
        # Max. výkon [kW]
        power_val = get_value("MotorMaxVykon", "motorMaxVykon", "Motor_Max_Vykon", 
                             "MaxVykonKw", "maxVykonKw", "Max_Vykon_Kw",
                             "VykonKw", "vykonKw", "Vykon_Kw",
                             "engine_power_kw", "EnginePowerKw", "powerKw", "PowerKw")
        if power_val is not None:
            try:
                if isinstance(power_val, (int, float)):
                    result.engine_power_kw = int(power_val)
                elif isinstance(power_val, str):
                    import re
                    numbers = re.findall(r'\d+', power_val)
                    if numbers:
                        result.engine_power_kw = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést výkon {power_val} na int: {e}")
        
        # Objem motoru
        displacement_val = get_value("MotorZdvihObjem", "motorZdvihObjem", "Motor_Zdvih_Objem",
                                    "DisplacementCc", "displacementCc", "Displacement_Cc",
                                    "engine_displacement_cc", "EngineDisplacementCc")
        if displacement_val is not None:
            try:
                if isinstance(displacement_val, (int, float)):
                    result.engine_displacement_cc = int(displacement_val)
                elif isinstance(displacement_val, str):
                    import re
                    numbers = re.findall(r'\d+', displacement_val)
                    if numbers:
                        result.engine_displacement_cc = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést objem {displacement_val} na int: {e}")
        
        # Palivo
        fuel_val = get_value("Palivo", "palivo", "DruhPaliva", "druhPaliva", "Druh_Paliva",
                            "fuel_type", "FuelType", "fuel", "Fuel")
        if fuel_val:
            fuel = str(fuel_val).lower()
            fuel_mapping = {
                "benzín": "petrol", "benzin": "petrol", "petrol": "petrol",
                "nafta": "diesel", "diesel": "diesel",
                "lpg": "lpg", "cng": "cng",
                "elektřina": "electric", "electric": "electric",
                "hybrid": "hybrid",
            }
            result.fuel_type = fuel_mapping.get(fuel, fuel)
        
        # Emisní norma
        emission_val = (
            get_value("EmisniUroven", "emisniUroven", "Emisni_Uroven",
                     "EmisniTrida", "emisniTrida", "Emisni_Trida",
                     "EmissionStandard", "emissionStandard", "emission_standard", "Emission_Standard")
            or result.emission_standard
        )
        if emission_val:
            result.emission_standard = str(emission_val)
        
        # Hmotnosti
        curb_weight_val = get_value("HmotnostProvozni", "hmotnostProvozni", "Hmotnost_Provozni",
                                   "PohotovostniHmotnost", "pohotovostniHmotnost", "Pohotovostni_Hmotnost",
                                   "curb_weight_kg", "CurbWeightKg", "curbWeight")
        if curb_weight_val is not None:
            try:
                if isinstance(curb_weight_val, (int, float)):
                    result.curb_weight_kg = int(curb_weight_val)
                elif isinstance(curb_weight_val, str):
                    import re
                    numbers = re.findall(r'\d+', curb_weight_val)
                    if numbers:
                        result.curb_weight_kg = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést pohotovostní hmotnost {curb_weight_val} na int: {e}")
        
        gross_weight_val = get_value("HmotnostCelkova", "hmotnostCelkova", "Hmotnost_Celkova",
                                    "MaxPripustnaHmotnost", "maxPripustnaHmotnost", "Max_Pripustna_Hmotnost",
                                    "gross_weight_kg", "GrossWeightKg", "grossWeight")
        if gross_weight_val is not None:
            try:
                if isinstance(gross_weight_val, (int, float)):
                    result.gross_weight_kg = int(gross_weight_val)
                elif isinstance(gross_weight_val, str):
                    import re
                    numbers = re.findall(r'\d+', gross_weight_val)
                    if numbers:
                        result.gross_weight_kg = int(numbers[0])
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést celkovou hmotnost {gross_weight_val} na int: {e}")
        
        # Počet míst
        seats_val = get_value("PocetMistKSezeni", "pocetMistKSezeni", "Pocet_Mist_K_Sezeni",
                             "seats", "Seats", "numSeats", "NumSeats")
        if seats_val is not None:
            try:
                if isinstance(seats_val, (int, str)):
                    result.seats = int(seats_val)
            except (ValueError, TypeError) as e:
                logger.warning(f"[MDČR] Nepodařilo se převést počet míst {seats_val} na int: {e}")
        
        # STK platnost
        stk_date = (
            get_value("PlatnostSTKDo", "platnostSTKDo", "Platnost_STK_Do",
                     "STKPlatnostDo", "stkPlatnostDo", "STK_Platnost_Do",
                     "TechnickaProhlidkaDo", "technickaProhlidkaDo", "Technicka_Prohlidka_Do",
                     "PravidelnaTechnickaProhlidkaDo", "pravidelnaTechnickaProhlidkaDo",
                     "stk_valid_until", "StkValidUntil", "inspection_date", "InspectionDate")
            or result.stk_valid_until
        )
        if stk_date:
            result.stk_valid_until = str(stk_date)
            logger.debug(f"[MDČR] STK platnost do: {result.stk_valid_until}")
        
        # Pneumatiky (NapravyPneuRafky) - extrahovat rozměry (stejná rozšířená logika jako u VIN)
        tyres_raw_val = get_value("NapravyPneuRafky", "napravyPneuRafky", "Napravy_Pneu_Rafky",
                                  "tyres_raw", "TyresRaw", "pneumatiky", "Pneumatiky")
        if tyres_raw_val:
            result.tyres_raw = str(tyres_raw_val)
            logger.debug(f"[MDČR] Pneumatiky (surový text): {result.tyres_raw[:200]}")
            
            # Použít stejnou rozšířenou logiku jako u VIN (kopírováno z výše)
            import re
            tyres = []
            
            # Rozšířené patterny pro všechny možné formáty kol a pneumatik z MDČR
            tyre_patterns = [
                # Standardní formáty pneumatik
                r'(\d{3}/\d{2}\s*R\s*\d{2,3}\s*\d{2,3}[A-Z]?)',  # 205/55 R 16 90V
                r'(\d{3}/\d{2}\s*R\s*\d{2,3}[A-Z]?)',            # 205/55 R16 90V
                r'(\d{3}/\d{2}\s*R\d{2,3}[A-Z]?)',               # 205/55R16C, 225/70R15C
                r'(\d{3}/\d{2}\s*R\d{2,3})',                     # 205/55R16
                r'(\d{3}x\d{2}x\d{2,3})',                        # 205x55x16
                r'(T\s*\d{3}/\d{2}\s*R\s*\d{2,3})',             # T 125/85 R 16
                
                # Formáty s koly a pneumatikami (6.00-15, 225/70R15C, atd.)
                r'(\d+\.\d{2}-\d{2,3}\s*\([^)]+\)\s*\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?\s*[SM]?)',  # 6.00-15 (E=68) 225/70R15C 112/110 S
                r'(\d+\.\d{2}-\d{2,3}\s*\([^)]+\)[,\s;:]?\s*\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?[RM]?\s*[SM]?)',  # S různými oddělovači
                r'(\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?[RM]?\s*[SM]?)',  # 225/70R15C 112/110 S
                r'(\d{3}/\d{2,3}R\d{2,3}[A-Z]?\s*\d{2,3}/\d{2,3}[A-Z]?[RM]?\s*M\+S)',  # S M+S
                
                # Formáty v sekci #20, #21 (VARIABILNÍ PROVEDENÍ)
                r'#20\s*\([^)]+\):\s*([^#\n]+?)(?=\n|#|$)',  # #20 (*44): 6.00-15 (E=68) 225/70R15C...
                r'#21\s*\([^)]+\):\s*([^#\n]+?)(?=\n|#|$)',  # #21 (*45): 6.00-15 (E=68); 225/70R15C...
                
                # Samostatné formáty kol
                r'(\d+\.\d{2}-\d{2,3}\s*\([^)]+\))',  # 6.00-15 (E=68)
                r'(\d+\.\d{2}-\d{2,3})',  # 6.00-15
            ]
            
            # Nejprve zkusit najít kompletní sekce s variantami (VARIABILNÍ PROVEDENÍ, #20, #21)
            variable_pattern = r'(?:VARIABILNÍ PROVEDENÍ VOZIDLA|#20|#21)[:\s]*(.*?)(?=\n\n|\nVOZIDLO|\n[A-Z]{2,}|\Z)'
            variable_matches = re.finditer(variable_pattern, result.tyres_raw, re.IGNORECASE | re.DOTALL)
            
            found_variants = []
            for var_match in variable_matches:
                variant_text = var_match.group(1)
                # Najít všechny řádky s pneumatikami v této sekci
                lines = variant_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('*'):
                        continue
                    
                    # Hledat formáty pneumatik v řádku
                    for pattern in tyre_patterns[:10]:  # První 10 patternů pro základní formáty
                        matches = re.finditer(pattern, line, re.IGNORECASE)
                        for match in matches:
                            tyre_text = match.group(1).strip()
                            # Vyčistit a normalizovat
                            tyre_text = re.sub(r'\s+', ' ', tyre_text)
                            if tyre_text and len(tyre_text) >= 5:
                                # Přidat celý řádek, pokud obsahuje kompletní informace
                                if any(x in line for x in ['/', 'R', '-']):
                                    found_variants.append(line)
                                    break
            
            # Pokud jsme našli varianty, použít je
            if found_variants:
                for variant in found_variants:
                    if variant not in tyres:
                        tyres.append(variant)
                        logger.debug(f"[MDČR] Nalezena varianta pneumatik: {variant[:80]}...")
            
            # Pak extrahovat standardní formáty
            for pattern in tyre_patterns:
                matches = re.finditer(pattern, result.tyres_raw, re.IGNORECASE)
                for match in matches:
                    tyre = match.group(1).strip()
                    if not tyre:
                        continue
                    
                    # Vyčistit a normalizovat
                    tyre = re.sub(r'\s+', ' ', tyre)
                    tyre = re.sub(r'(\d{2})\s*([rR])\s*(\d)', r'\1 \2\3', tyre)
                    tyre = re.sub(r'([rR])', 'R', tyre, count=1)
                    
                    # Přidat pouze pokud vypadá jako pneumatika/kolo
                    if len(tyre) >= 5 and (re.search(r'[\d/]', tyre) or re.search(r'R\d', tyre)):
                        if tyre not in tyres:
                            tyres.append(tyre)
                            logger.debug(f"[MDČR] Nalezena pneumatika: {tyre[:80]}...")
            
            if tyres:
                result.tyres = sorted(list(set(tyres)))
                logger.info(f"[MDČR] Extrahováno {len(result.tyres)} rozměrů/variant pneumatik")
            
            # Kola a pneumatiky - použít všechny varianty
            if result.tyres and len(result.tyres) > 0:
                result.wheels_and_tyres = "\n".join(result.tyres)
            elif result.tyres_raw:
                result.wheels_and_tyres = result.tyres_raw
        
        # Detailní logování všech extrahovaných hodnot
        extracted_fields = []
        if result.make: extracted_fields.append(f"značka={result.make}")
        if result.model: extracted_fields.append(f"model={result.model}")
        if result.production_year: extracted_fields.append(f"rok={result.production_year}")
        if result.engine_code: extracted_fields.append(f"motor_kód={result.engine_code}")
        if result.engine_displacement_cc: extracted_fields.append(f"objem={result.engine_displacement_cc}cm³")
        if result.engine_power_kw: extracted_fields.append(f"výkon={result.engine_power_kw}kW")
        if result.stk_valid_until: extracted_fields.append(f"STK={result.stk_valid_until}")
        if result.tyres: extracted_fields.append(f"pneumatiky={len(result.tyres)}")
        if result.plate: extracted_fields.append(f"SPZ={result.plate}")
        
        logger.info(f"[MDČR] ✅ Úspěšně dekódováno podle SPZ: {result.make} {result.model} ({result.production_year}) | {', '.join(extracted_fields)}")
        return result
        
    except httpx.RequestError as e:
        logger.error(f"[MDČR] Chyba při volání API podle SPZ: {e}")
        return None
    except Exception as e:
        logger.error(f"[MDČR] Neočekávaná chyba při volání API podle SPZ: {e}", exc_info=True)
        return None


def fetch_mdcr_vehicle_raw_data_sync(vin: str) -> Optional[Dict[str, Any]]:
    """
    Synchronní stažení surového slovníku Data z MDČR API (stejný endpoint jako async VIN fetch).
    Používá se pro strukturovaný technický přehled — bez změny chování async dekodéru.
    """
    normalized_vin = vin.strip().upper().replace(" ", "").replace("-", "")
    if not DATAOVO_API_KEY or not DATAOVO_API_BASE_URL:
        logger.debug("[MDČR][sync] API není nakonfigurováno — přeskakuji raw fetch")
        return None
    url = f"{DATAOVO_API_BASE_URL}?vin={urllib.parse.quote(normalized_vin)}"
    headers = {"api_key": DATAOVO_API_KEY, "Accept": "application/json"}
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers)
        if response.status_code != 200:
            logger.warning("[MDČR][sync] HTTP %s pro VIN %s", response.status_code, normalized_vin[:8])
            return None
        api_response = response.json()
        if api_response.get("Success") is False:
            return None
        status = api_response.get("Status")
        success = api_response.get("Success")
        if (status != 1 and success is not True) or "Data" not in api_response:
            return None
        data = api_response["Data"]
        if isinstance(data, dict):
            dd = dict(data)
            log_mdcr_payload_shape_summary(
                vin_masked=f"{normalized_vin[:8]}…",
                http_status=int(response.status_code),
                data=dd,
            )
            return dd
    except Exception as exc:
        logger.warning("[MDČR][sync] raw fetch selhal: %s", exc, exc_info=False)
        return None
    return None
