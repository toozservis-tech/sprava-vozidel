"""
Lokální VIN dekodér - dekóduje VIN bez externích API
"""
import json
from pathlib import Path
from typing import Optional, Tuple, List
import logging

from .models import VehicleDecodedData
from .vin_validator import validate_vin, normalize_vin

logger = logging.getLogger(__name__)

# Cachované data (lazy loading)
_wmi_map_cache: Optional[dict] = None
_engine_data_cache: Optional[dict] = None
_vin_patterns_cache: Optional[dict] = None

# Cesta k datovým souborům
DECODER_DATA_DIR = Path(__file__).parent / "data"


def _load_wmi_map() -> dict:
    """Načte WMI mapu z JSON souboru (lazy, cachované)"""
    global _wmi_map_cache
    if _wmi_map_cache is not None:
        return _wmi_map_cache
    
    wmi_file = DECODER_DATA_DIR / "wmi_map.json"
    try:
        with open(wmi_file, "r", encoding="utf-8") as f:
            _wmi_map_cache = json.load(f)
        logger.debug(f"Načteno {len(_wmi_map_cache)} WMI kódů")
    except Exception as e:
        logger.warning(f"Nepodařilo se načíst WMI mapu: {e}")
        _wmi_map_cache = {}
    
    return _wmi_map_cache


def _load_engine_data() -> dict:
    """Načte engine data z JSON souboru (lazy, cachované)"""
    global _engine_data_cache
    if _engine_data_cache is not None:
        return _engine_data_cache
    
    # Zkusit načíst VW/Audi engines
    engine_file = DECODER_DATA_DIR / "vw_audi_engines.json"
    try:
        with open(engine_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            _engine_data_cache = data.get("engine_codes", {})
        logger.debug(f"Načteno {len(_engine_data_cache)} engine kódů")
    except Exception as e:
        logger.warning(f"Nepodařilo se načíst engine data: {e}")
        _engine_data_cache = {}
    
    return _engine_data_cache


def _load_vin_patterns() -> dict:
    """Načte VIN patterns z JSON souboru (lazy, cachované)"""
    global _vin_patterns_cache
    if _vin_patterns_cache is not None:
        return _vin_patterns_cache
    
    patterns_file = DECODER_DATA_DIR / "eu_vin_patterns.json"
    try:
        with open(patterns_file, "r", encoding="utf-8") as f:
            _vin_patterns_cache = json.load(f)
        logger.debug("Načteny VIN patterns")
    except Exception as e:
        logger.warning(f"Nepodařilo se načíst VIN patterns: {e}")
        _vin_patterns_cache = {}
    
    return _vin_patterns_cache


def _decode_model_year(vin: str) -> Optional[int]:
    """
    Dekóduje rok modelu z VIN (10. znak).
    
    Args:
        vin: VIN kód (17 znaků, normalizovaný)
        
    Returns:
        Rok modelu nebo None
    """
    if len(vin) < 10:
        return None
    
    year_char = vin[9]  # 10. znak (0-indexed = pozice 9)
    patterns = _load_vin_patterns()
    year_map = patterns.get("model_year_map", {})
    
    if year_char not in year_map:
        return None
    
    year_data = year_map[year_char]
    
    # VIN může mít rok buď v rozsahu 1980-2009 nebo 2010-2039
    # Pro většinu moderních vozidel (po roce 2000) bereme novější hodnotu (2010+)
    if isinstance(year_data, dict):
        years = list(year_data.values())
        if years:
            # Pro rozlišení mezi staršími a novějšími vozidly:
            # - Pokud je rok > 2000, bereme novější hodnotu (2010+)
            # - Jinak bereme starší hodnotu (1980-2009)
            # Pro jednoduchost bereme maximum (novější rok), což je obvykle správně pro moderní vozidla
            return max(years)
    
    return None


def _decode_wmi(vin: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Dekóduje WMI (World Manufacturer Identifier) z VIN.
    
    Args:
        vin: VIN kód (17 znaků, normalizovaný)
        
    Returns:
        Tuple[wmi, manufacturer, country, plant]
    """
    if len(vin) < 3:
        return None, None, None, None
    
    wmi = vin[0:3]
    wmi_map = _load_wmi_map()
    
    if wmi not in wmi_map:
        return wmi, None, None, None
    
    wmi_info = wmi_map[wmi]
    manufacturer = wmi_info.get("manufacturer")
    country = wmi_info.get("country")
    plant = wmi_info.get("plant")
    
    return wmi, manufacturer, country, plant


def _decode_plant(vin: str) -> Optional[str]:
    """
    Dekóduje závod z VIN (11. znak).
    
    Args:
        vin: VIN kód (17 znaků, normalizovaný)
        
    Returns:
        Kód závodu nebo None
    """
    if len(vin) < 11:
        return None
    
    return vin[10]  # 11. znak (0-indexed = pozice 10)


def _decode_engine_from_vin(vin: str) -> Optional[dict]:
    """
    Pokusí se dekódovat informace o motoru z VIN.
    Zkusí najít engine code v VIN (pozice 4-8 mohou obsahovat engine info).
    
    Args:
        vin: VIN kód (17 znaků, normalizovaný)
        
    Returns:
        Dict s engine info nebo None
    """
    if len(vin) < 9:
        return None
    
    # VDS sekce (4-9) může obsahovat engine code
    # Pro VW/Škoda/Audi je to obvykle pozice 4-7
    vds_section = vin[3:9]  # Pozice 4-9
    
    engine_data = _load_engine_data()
    
    # Zkusit najít engine code v různých délkách
    for length in [4, 3, 2]:
        for start in range(len(vds_section) - length + 1):
            code = vds_section[start:start+length]
            if code in engine_data:
                engine_info = engine_data[code]
                return engine_info
    
    return None


def decode_vin_local(vin: str) -> Tuple[VehicleDecodedData, List[str]]:
    """
    Lokálně dekóduje VIN bez externích API.
    
    Args:
        vin: VIN kód k dekódování
        
    Returns:
        Tuple[VehicleDecodedData, List[str]]: (dekódovaná data, seznam chyb)
    """
    errors: List[str] = []
    
    # Normalizace VIN
    vin = normalize_vin(vin)
    
    # Validace
    is_valid, validation_errors = validate_vin(vin)
    if not is_valid:
        # Vrátit prázdná data s chybami
        return VehicleDecodedData(
            vin=vin,
            source_priority=["local_vin"]
        ), validation_errors
    
    errors.extend(validation_errors)  # Přidat warnings (např. checksum)
    
    # Vytvořit základní VehicleDecodedData
    data = VehicleDecodedData(
        vin=vin,
        source_priority=["local_vin"]
    )
    
    # Dekódovat WMI (1-3 znaky)
    wmi, manufacturer, country, plant_wmi = _decode_wmi(vin)
    if wmi:
        data.wmi = wmi
        logger.debug(f"[VIN] WMI dekódováno: {wmi}")
    if manufacturer:
        data.manufacturer = manufacturer
        data.make = manufacturer  # make je alias pro manufacturer
        logger.info(f"[VIN] WMI {wmi} → {manufacturer}")
    if country:
        data.country_of_registration = country
        logger.debug(f"[VIN] Země: {country}")
    if plant_wmi:
        data.plant = plant_wmi
        logger.debug(f"[VIN] Závod: {plant_wmi}")
    
    # Dekódovat rok modelu (10. znak)
    model_year = _decode_model_year(vin)
    if model_year:
        data.model_year = model_year
        # Pokud nemáme production_year, použijeme model_year
        if not data.production_year:
            data.production_year = model_year
        logger.info(f"[VIN] WMI {wmi} → {manufacturer}, model_year={model_year}")
    else:
        logger.debug(f"[VIN] Nepodařilo se dekódovat rok z VIN (10. znak: {vin[9] if len(vin) >= 10 else 'N/A'})")
    
    # Dekódovat závod (11. znak)
    plant_code = _decode_plant(vin)
    if plant_code and not data.plant:
        data.plant = plant_code
    
    # Pokusit se dekódovat engine info
    engine_info = _decode_engine_from_vin(vin)
    if engine_info:
        if "displacement_cc" in engine_info:
            data.engine_displacement_cc = engine_info["displacement_cc"]
        if "power_kw" in engine_info:
            data.engine_power_kw = engine_info["power_kw"]
        if "fuel_type" in engine_info:
            data.fuel_type = engine_info["fuel_type"]
        if "manufacturer" in engine_info:
            # Engine manufacturer může být jiný než vehicle manufacturer
            pass
    
    return data, errors

