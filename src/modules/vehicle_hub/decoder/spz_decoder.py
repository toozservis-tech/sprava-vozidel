"""
Dekodér SPZ – orchestrace volání MDČR a EU Open Data.
"""

import logging
from typing import Optional

from .models import VehicleDecodedData
from .mdcr_client import fetch_vehicle_by_plate_from_mdcr
from .eu_open_data_client import fetch_vehicle_by_plate_from_eu_open_data

logger = logging.getLogger(__name__)


async def decode_by_plate(plate: str) -> Optional[VehicleDecodedData]:
    """
    1) Normalizuje SPZ
    2) Zkusí MDČR
    3) Pokud MDČR nevrátí nic, zkusí EU Open Data
    4) Pokud stále nic, vrátí None
    """
    normalized = plate.strip().upper().replace(" ", "").replace("-", "")
    logger.info(f"[SPZ] Dekóduji SPZ: {normalized}")

    # 1) MDČR
    mdcr_data = await fetch_vehicle_by_plate_from_mdcr(normalized)
    if mdcr_data:
        logger.debug("[SPZ] Data nalezena v MDČR")
        return mdcr_data

    # 2) EU Open Data
    eu_data = await fetch_vehicle_by_plate_from_eu_open_data(normalized)
    if eu_data:
        logger.debug("[SPZ] Data nalezena v EU Open Data")
        return eu_data

    logger.warning(f"[SPZ] Pro SPZ {normalized} nebyla nalezena žádná data")
    return None

import logging
from typing import Optional

from .models import VehicleDecodedData
from .mdcr_client import fetch_vehicle_by_plate_from_mdcr
from .eu_open_data_client import fetch_vehicle_by_plate_from_eu_open_data

logger = logging.getLogger(__name__)


async def decode_by_plate(plate: str) -> Optional[VehicleDecodedData]:
    """
    1) Normalizuje SPZ
    2) Zkusí MDČR
    3) Pokud MDČR nevrátí nic, zkusí EU Open Data
    4) Pokud stále nic, vrátí None
    """
    normalized = plate.strip().upper().replace(" ", "").replace("-", "")
    logger.info(f"[SPZ] Dekóduji SPZ: {normalized}")

    # 1) MDČR
    mdcr_data = await fetch_vehicle_by_plate_from_mdcr(normalized)
    if mdcr_data:
        logger.debug("[SPZ] Data nalezena v MDČR")
        return mdcr_data

    # 2) EU Open Data
    eu_data = await fetch_vehicle_by_plate_from_eu_open_data(normalized)
    if eu_data:
        logger.debug("[SPZ] Data nalezena v EU Open Data")
        return eu_data

    logger.warning(f"[SPZ] Pro SPZ {normalized} nebyla nalezena žádná data")
    return None
