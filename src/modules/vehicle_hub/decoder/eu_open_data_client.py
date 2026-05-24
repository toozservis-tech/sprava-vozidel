"""
EU Open Data klient – zatím bezpečný stub.
Pokud není nakonfigurován API endpoint/token, vrací None a nic nepokazí.
"""

import logging
from typing import Optional
import os
import urllib.parse

import httpx

from .models import VehicleDecodedData

logger = logging.getLogger(__name__)

# Zkusit načíst z core configu, jinak z env
try:
    from src.core.config import EU_VEHICLE_API_BASE_URL, EU_VEHICLE_API_TOKEN
    EU_API_BASE_URL = EU_VEHICLE_API_BASE_URL
    EU_API_TOKEN = EU_VEHICLE_API_TOKEN
except ImportError:
    EU_API_BASE_URL = os.getenv("EU_VEHICLE_API_BASE_URL", "")
    EU_API_TOKEN = os.getenv("EU_VEHICLE_API_TOKEN", "")


async def fetch_vehicle_by_plate_from_eu_open_data(plate: str) -> Optional[VehicleDecodedData]:
    """
    Zkusí načíst data o vozidle podle SPZ z EU open data API.
    Pokud API není nakonfigurováno nebo požadavek selže, vrací None.
    """
    if not EU_API_BASE_URL or not EU_API_TOKEN:
        logger.debug("[EU] API není nakonfigurováno (BASE_URL/TOKEN chybí), vracím None")
        return None

    try:
        normalized_plate = plate.strip().upper().replace(" ", "").replace("-", "")
        url = f"{EU_API_BASE_URL}?plate={urllib.parse.quote(normalized_plate)}"

        headers = {
            "Authorization": f"Bearer {EU_API_TOKEN}"
        }

        logger.debug(f"[EU] Volám API podle SPZ: {url}")

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            logger.warning(f"[EU] API vrátilo {resp.status_code} pro SPZ {normalized_plate}")
            return None

        data = resp.json()

        # Minimální mapování – zatím jen základ, ať se to nerozbije
        result = VehicleDecodedData(
            plate=normalized_plate,
            source_priority=["eu_open_data"],
        )

        # Pokud API někdy vrátí tyhle klíče, lehce je namapujeme
        result.make = data.get("make") or data.get("brand")
        result.model = data.get("model")
        result.production_year = data.get("year") or data.get("production_year")

        return result

    except Exception as e:
        logger.error(f"[EU] Chyba při volání EU API podle SPZ: {e}", exc_info=True)
        return None


async def fetch_vehicle_by_vin_from_eu_open_data(vin: str) -> Optional[VehicleDecodedData]:
    """
    Zkusí načíst data o vozidle podle VIN z EU open data API.
    Pokud API není nakonfigurováno nebo požadavek selže, vrací None.
    """
    if not EU_API_BASE_URL or not EU_API_TOKEN:
        logger.debug("[EU] API není nakonfigurováno (BASE_URL/TOKEN chybí), vracím None")
        return None

    try:
        normalized_vin = vin.strip().upper().replace(" ", "").replace("-", "")
        url = f"{EU_API_BASE_URL}?vin={urllib.parse.quote(normalized_vin)}"

        headers = {
            "Authorization": f"Bearer {EU_API_TOKEN}"
        }

        logger.debug(f"[EU] Volám API podle VIN: {url}")

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            logger.warning(f"[EU] API vrátilo {resp.status_code} pro VIN {normalized_vin}")
            return None

        data = resp.json()

        result = VehicleDecodedData(
            vin=normalized_vin,
            source_priority=["eu_open_data"],
        )

        result.make = data.get("make") or data.get("brand")
        result.model = data.get("model")
        result.production_year = data.get("year") or data.get("production_year")

        return result

    except Exception as e:
        logger.error(f"[EU] Chyba při volání EU API podle VIN: {e}", exc_info=True)
        return None
