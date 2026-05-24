"""
Utility funkce pro sloučení dat z více zdrojů
"""
import logging
from typing import Optional

from .models import VehicleDecodedData

logger = logging.getLogger(__name__)


def merge_vehicle_data(
    local_data: Optional[VehicleDecodedData],
    mdcr_data: Optional[VehicleDecodedData],
    eu_data: Optional[VehicleDecodedData],
    template_data: Optional[VehicleDecodedData] = None,
    fallback_plate: Optional[str] = None,
) -> Optional[VehicleDecodedData]:
    """
    Sloučí data z více zdrojů s prioritou:
    1) MDČR (pokud existuje)
    2) EU open data
    3) local_vin
    4) template_data
    
    Args:
        local_data: Data z lokálního VIN dekódování
        mdcr_data: Data z MDČR API
        eu_data: Data z EU Open Data API
        template_data: Data ze šablony z databáze
        fallback_plate: Fallback SPZ, která se použije, pokud žádný zdroj nevrátí SPZ
        
    Returns:
        Sloučená VehicleDecodedData nebo None pokud žádná data neexistují
    """
    logger.info("[MERGE] ========================================")
    logger.info("[MERGE] Začínám slučování dat z více zdrojů")
    
    # Zjistit, který zdroj použít jako base (podle priority: MDČR > EU > Local > Template)
    base_data = None
    base_source = None
    
    if mdcr_data:
        base_data = mdcr_data
        base_source = "mdcr"
        logger.info("[MERGE] Používám MDČR jako base")
    elif eu_data:
        base_data = eu_data
        base_source = "eu_open_data"
        logger.info("[MERGE] Používám EU Open Data jako base")
    elif local_data:
        base_data = local_data
        base_source = "local_vin"
        logger.info("[MERGE] Používám local_vin jako base")
    elif template_data:
        base_data = template_data
        base_source = "template"
        logger.info("[MERGE] Používám template jako base")
    else:
        logger.warning("[MERGE] ❌ Žádná data k sloučení")
        return None
    
    # Vytvořit kopii base dat
    merged = VehicleDecodedData(**base_data.model_dump())
    
    # Doplňovat None hodnoty z dalších zdrojů (podle priority)
    # Priority: MDČR > EU > Local > Template
    
    sources = []
    if mdcr_data:
        sources.append(("mdcr", mdcr_data))
    if eu_data:
        sources.append(("eu_open_data", eu_data))
    if local_data:
        sources.append(("local_vin", local_data))
    if template_data:
        sources.append(("template", template_data))
    
    # Sloučit source_priority - seřadit podle priority
    priority_order = ["mdcr", "eu_open_data", "local_vin", "template"]
    merged.source_priority = []
    seen_sources = set()
    
    # Přidat zdroje v pořadí priority
    for source_name in priority_order:
        for name, data in sources:
            if name == source_name and name not in seen_sources:
                merged.source_priority.append(name)
                seen_sources.add(name)
    
    # KROK 3: Zajistit, že pokud mdcr_data existuje, je "mdcr" na první pozici
    # DŮLEŽITÉ: MDČR má VŽDY vyšší prioritu než local_vin
    if mdcr_data:
        # Pokud mdcr_data existuje, MUSÍ být "mdcr" na první pozici
        if "mdcr" not in merged.source_priority:
            merged.source_priority.insert(0, "mdcr")
        elif merged.source_priority[0] != "mdcr":
            # Přesunout "mdcr" na první pozici
            merged.source_priority.remove("mdcr")
            merged.source_priority.insert(0, "mdcr")
        logger.info(f"[MERGE] MDČR data existuje - 'mdcr' je na první pozici v source_priority")
    
    # Doplňovat None hodnoty z ostatních zdrojů (přeskočit base)
    for source_name, source_data in sources:
        if source_data is base_data:
            continue  # Přeskočit base, už máme jeho data
        
        logger.debug(f"[MERGE] Doplňuji data ze zdroje: {source_name}")
        
        # Doplňovat None hodnoty
        for field_name in VehicleDecodedData.model_fields.keys():
            if field_name == "source_priority":
                continue  # Přeskočit, už máme merged
            
            current_value = getattr(merged, field_name)
            source_value = getattr(source_data, field_name)
            
            # Pokud je aktuální hodnota None a source má hodnotu, použít source
            # DŮLEŽITÉ: Nikdy nepřepisovat non-null hodnotu hodnotou None
            if current_value is None and source_value is not None:
                setattr(merged, field_name, source_value)
                logger.debug(f"[MERGE] Doplněno {field_name} z {source_name}: {source_value}")
    
    # Fallback SPZ: použít pouze pokud žádný zdroj nevrátil SPZ
    if not merged.plate and fallback_plate:
        merged.plate = fallback_plate
        logger.info(f"[MERGE] Použita fallback SPZ: {fallback_plate}")
    
    logger.info(f"[MERGE] ✅ Sloučeno: sources={merged.source_priority}, plate={merged.plate}")
    logger.info(f"[MERGE] Final merged object: make={merged.make}, model={merged.model}, year={merged.production_year}")
    return merged

