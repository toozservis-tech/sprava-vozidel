"""
Pydantic modely pro Vehicle Decoder Engine
"""
from typing import Optional, List, Union
from datetime import date
from pydantic import BaseModel, Field


class VehicleDecodedData(BaseModel):
    """Kompletní dekódovaná data o vozidle z různých zdrojů"""
    
    vin: Optional[str] = None
    plate: Optional[str] = None  # SPZ
    make: Optional[str] = None  # Tovární značka
    model: Optional[str] = None
    model_year: Optional[int] = None  # Rok modelu z VIN (10. znak)
    production_year: Optional[int] = None  # Rok výroby
    engine_code: Optional[str] = None  # Kód motoru
    engine_displacement_cc: Optional[int] = None  # Objem motoru v cm³
    engine_power_kw: Optional[int] = None  # Výkon v kW
    fuel_type: Optional[str] = None  # Typ paliva
    transmission_type: Optional[str] = None  # Typ převodovky
    body_type: Optional[str] = None  # Typ karoserie
    exterior_color: Optional[str] = None  # Barva karoserie
    doors: Optional[int] = None
    seats: Optional[int] = None
    gross_weight_kg: Optional[int] = None  # Celková hmotnost
    curb_weight_kg: Optional[int] = None  # Hmotnost prázdného vozidla
    emission_standard: Optional[str] = None  # Emisní norma (Euro 4, 5, 6, atd.)
    first_registration_date: Optional[str] = None  # Datum první registrace
    country_of_registration: Optional[str] = None
    manufacturer: Optional[str] = None  # Výrobce (může být jiný než make)
    wmi: Optional[str] = None  # World Manufacturer Identifier (první 3 znaky VIN)
    plant: Optional[str] = None  # Závod/kód závodu (11. znak VIN)
    stk_valid_until: Optional[str] = None  # Datum konce platnosti STK (technická prohlídka)
    
    # Pneumatiky
    tyres: Optional[List[str]] = None  # Seznam rozměrů pneumatik (např. ["205/55 R16", "195/65 R15"])
    tyres_raw: Optional[str] = None  # Surový text s informacemi o pneumatikách z MDČR API
    
    # Nová pole pro kompletní mapování formuláře
    type_label: Optional[str] = None  # Typ / Varianta / Verze (kompletní popis typu vozidla)
    engine_type_label: Optional[str] = None  # Typ motoru jako text (např. "2.0 TDI 125 kW")
    tech_inspection_valid_to: Optional[Union[date, str]] = None  # Datum konce platnosti technické prohlídky (date nebo ISO string YYYY-MM-DD)
    wheels_and_tyres: Optional[str] = None  # Kola a pneumatiky na nápravě - rozměry/montáž (formátovaný text)
    extra_records: Optional[str] = None  # Další záznamy
    
    # Informace o zdrojích dat (pořadí priority)
    source_priority: List[str] = Field(
        default_factory=list,
        description="Ordered list of sources used/attempted (e.g. ['mdcr', 'eu_open_data', 'local_vin'])",
    )
    
    class Config:
        """Pydantic v2 kompatibilita"""
        from_attributes = True
        populate_by_name = True


class VinDecodeRequest(BaseModel):
    """Request pro dekódování VIN"""
    vin: str
    
    class Config:
        from_attributes = True


class PlateDecodeRequest(BaseModel):
    """Request pro dekódování SPZ"""
    plate: str
    
    class Config:
        from_attributes = True


class VehicleDecodeResponse(BaseModel):
    """Response z dekódování vozidla"""
    success: bool
    data: Optional[VehicleDecodedData] = None
    errors: List[str] = Field(default_factory=list)
    
    class Config:
        from_attributes = True

