import urllib.request
import urllib.parse
import json
import requests
from typing import Optional

# FastAPI je volitelný - potřebný jen pro HTTP endpoint
try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel

    router = APIRouter(prefix="/vin", tags=["vin"])

    class TyreResponse(BaseModel):
        tyres: list[str]

    @router.get("/tyres", response_model=TyreResponse)
    def get_tyres_from_vin(vin: str):
        try:
            vin = _validate_vin(vin)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        # TODO: sem přijde reálné API – zatím placeholder
        raw_tyres = [
            "205/55 R16 91V",
            "225/45 R17 94W",
            "225/40 R18 92Y (alternativní)"
        ]

        # Odebrání duplicit a seřazení
        unique = sorted(set([t.strip() for t in raw_tyres if t.strip()]))

        if not unique:
            raise HTTPException(status_code=404, detail="Pro toto VIN nebyly nalezeny rozměry pneu")

        return TyreResponse(tyres=unique)
except ImportError:
    # FastAPI není nainstalovaný - router nebude dostupný, ale decode_vin_api funguje
    router = None


def _validate_vin(vin: str) -> str:
    """
    Validuje a normalizuje VIN kód.
    
    Args:
        vin: VIN kód vozidla
        
    Returns:
        Normalizovaný VIN (uppercase, bez mezer)
        
    Raises:
        ValueError: Pokud je VIN neplatný
    """
    vin = vin.strip().upper()
    
    # Základní validace délky
    if len(vin) != 17:
        raise ValueError("Neplatné VIN - musí mít přesně 17 znaků")
    
    # Validace povolených znaků (VIN může obsahovat pouze alfanumerické znaky, kromě I, O, Q)
    # Povolené znaky: 0-9, A-H, J-N, P, R-Z
    allowed_chars = set('0123456789ABCDEFGHJKLMNPRSTUVWXYZ')
    invalid_chars = set(vin) - allowed_chars
    
    if invalid_chars:
        raise ValueError(f"Neplatné VIN - obsahuje nepovolené znaky: {', '.join(sorted(invalid_chars))}")
    
    return vin


def _fetch_mdcr_data(vin: str) -> Optional[dict]:
    """
    Pokusí se získat data z MDČR systému pomocí API.
    Používá dataovozidlech.cz API (oficiální databáze vozidel MDČR).
    Extrahuje všechna dostupná data o vozidle včetně kódu motoru a pneumatik.
    """
    try:
        import requests
        from src.core.config import DATAOVOZIDLECH_API_KEY, DATAOVOZIDLECH_API_URL
        
        # Zkontrolovat, zda máme API klíč
        if not DATAOVOZIDLECH_API_KEY:
            print("[MDCR] WARNING: API klic neni nastaven. Nastavte DATAOVOZIDLECH_API_KEY v .env souboru.")
            return None
        
        # Volání API
        url = f"{DATAOVOZIDLECH_API_URL}?vin={urllib.parse.quote(vin)}"
        headers = {
            "api_key": DATAOVOZIDLECH_API_KEY
        }
        
        print(f"[MDCR] Volám API: {url}")
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"[MDCR] ERROR: API vratilo status {response.status_code}: {response.text[:200]}")
            return None
        
        api_response = response.json()
        print(f"[MDCR] OK: API odpoved prijata, zpracovavam data...")
        
        # API vrací strukturu: {"Status": 1, "Data": {...}}
        if api_response.get("Status") != 1 or "Data" not in api_response:
            print(f"[MDCR] ERROR: API vratilo chybu: Status={api_response.get('Status', 'Unknown')}")
            return None
        
        data = api_response["Data"]
        
        # Zpracování JSON odpovědi
        result = {}
        
        # Tovární značka
        if data.get("TovarniZnacka"):
            result['brand'] = data["TovarniZnacka"]
            print(f"[MDCR] OK: Značka: {result['brand']}")
        
        # Typ vozidla
        if data.get("Typ"):
            result['vehicle_type'] = data["Typ"]
            print(f"[MDCR] OK: Typ: {result['vehicle_type']}")
        
        # Obchodní označení (model)
        if data.get("ObchodniOznaceni"):
            result['model'] = data["ObchodniOznaceni"]
            print(f"[MDCR] OK: Model: {result['model']}")
        
        # Rok výroby
        if data.get("DatumPrvniRegistrace"):
            try:
                # Zkusit extrahovat rok z data (formát: "2011-03-01T00:00:00")
                date_str = str(data["DatumPrvniRegistrace"])
                if len(date_str) >= 4:
                    year = int(date_str[:4])
                    if 1900 <= year <= 2100:
                        result['year'] = year
                        print(f"[MDCR] OK: Rok: {result['year']}")
            except (ValueError, TypeError):
                pass
        
        # Typ motoru (MotorTyp)
        if data.get("MotorTyp"):
            result['engine_code'] = data["MotorTyp"]
            print(f"[MDCR] OK: Typ motoru: {result['engine_code']}")
        
        # Max. výkon [kW] (MotorMaxVykon)
        if data.get("MotorMaxVykon"):
            result['max_power'] = str(data["MotorMaxVykon"])
            print(f"[MDCR] OK: Max. výkon: {result['max_power']}")
        
        # Motor (sestavený z více údajů)
        engine_parts = []
        if data.get("MotorZdvihObjem"):
            engine_parts.append(f"{data['MotorZdvihObjem']} cm³")
        if data.get("MotorMaxVykon"):
            engine_parts.append(f"{data['MotorMaxVykon']}")
        if data.get("Palivo"):
            engine_parts.append(data["Palivo"])
        if engine_parts:
            result['engine'] = ' / '.join(engine_parts)
            print(f"[MDCR] OK: Motor: {result['engine']}")
        
        # Kola a pneumatiky (NapravyPneuRafky)
        tyres = []
        tyres_raw = ""
        
        # Zkusit najít pneumatiky v různých polích
        if data.get("NapravyPneuRafky"):
            tyres_raw = str(data["NapravyPneuRafky"])
            result['tyres_raw'] = tyres_raw
            print(f"[MDCR] OK: Pneumatiky (surový text): {tyres_raw[:100]}")
        
        # Extrahovat rozměry pneumatik z textu
        import re
        tyre_patterns = [
            r'(\d{3}/\d{2}\s*R\s*\d{2,3}\s*\d{2,3}[A-Z]?)',  # 205/55 R 16 90V
            r'(\d{3}/\d{2}\s*R\s*\d{2,3}[A-Z]?)',            # 205/55 R16 90V
            r'(\d{3}/\d{2}\s*R\d{2,3})',                     # 205/55R16
            r'(\d{3}x\d{2}x\d{2,3})',                        # 205x55x16
            r'(T\s*\d{3}/\d{2}\s*R\s*\d{2,3})',             # T 125/85 R 16
        ]
        
        if tyres_raw:
            for pattern in tyre_patterns:
                matches = re.finditer(pattern, tyres_raw, re.IGNORECASE)
                for match in matches:
                    tyre = match.group(1).strip()
                    tyre = re.sub(r'\s+', ' ', tyre)
                    tyre = re.sub(r'(\d{2})\s*([rR])\s*(\d)', r'\1 \2\3', tyre)
                    tyre = re.sub(r'([rR])', 'R', tyre, count=1)
                    if tyre and len(tyre) >= 7 and re.search(r'\d{3}/\d{2}', tyre):
                        if tyre not in tyres:
                            tyres.append(tyre)
                            print(f"[MDCR] OK: Nalezena pneumatika: {tyre}")
        
        if tyres:
            result['tyres'] = sorted(list(set(tyres)))
        
        # Další záznamy (pokud existuje pole)
        # V API může být v různých polích, zkusit najít
        additional_info = []
        if data.get("VozidloDruh"):
            additional_info.append(f"Druh: {data['VozidloDruh']}")
        if data.get("Kategorie"):
            additional_info.append(f"Kategorie: {data['Kategorie']}")
        if data.get("EmisniUroven"):
            additional_info.append(f"Emisní norma: {data['EmisniUroven']}")
        if additional_info:
            result['additional_notes'] = "\n".join(additional_info)
            print(f"[MDCR] OK: Další záznamy: {result['additional_notes'][:100]}")
        
        # Technická prohlídka do (pokud je v API)
        # Toto pole nemusí být v API, ale zkusit najít
        if data.get("PravidelnaTechnickaProhlidkaDo"):
            result['inspection_date'] = str(data["PravidelnaTechnickaProhlidkaDo"])
            print(f"[MDCR] OK: Technická prohlídka do: {result['inspection_date']}")
        
        # SPZ (pokud je dostupná)
        if data.get("RegistracniZnacka"):
            result['plate'] = data["RegistracniZnacka"]
            print(f"[MDCR] OK: SPZ: {result['plate']}")
        
        # Název vozidla (značka + model)
        if result.get('brand') and result.get('model'):
            result['name'] = f"{result['brand']} {result['model']}"
        
        print(f"[MDCR] OK: Uspesne nacteno {len(result)} poli z API")
        return result if result else None
        
    except requests.exceptions.RequestException as e:
        print(f"[MDCR] ERROR: Chyba při volání API: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"[MDCR] ERROR: Chyba při parsování JSON: {e}")
        return None
    except Exception as e:
        print(f"[MDCR] ERROR: Neočekávaná chyba: {e}")
        import traceback
        traceback.print_exc()
        return None
        
    return None


def _fetch_vin_decoder_api(vin: str) -> Optional[dict]:
    """
    Použije veřejné VIN dekódovací API (např. vpic.nhtsa.dot.gov nebo alternativní).
    Extrahuje všechna dostupná data.
    """
    import re
    # NHTSA VIN Decoder API (zdarma, mezinárodní)

def decode_vin_api(vin: str) -> dict:
    """
    Dekóduje VIN a vrací informace o vozidle jako dict.
    Používá MDČR API a NHTSA VIN Decoder jako fallback.
    
    Args:
        vin: VIN kód vozidla (17 znaků)
        
    Returns:
        dict s klíči: brand, model, year, engine, tyres (seznam)
        
    Raises:
        ValueError: Pokud je VIN neplatný
        Exception: Pokud API selže
    """
    vin = _validate_vin(vin)
    
    result = {
        "brand": None,
        "model": None,
        "year": None,
        "engine": None,
        "engine_code": None,  # Kód motoru
        "plate": None,  # SPZ
        "name": None,   # Název vozidla (značka + model)
        "tyres": []
    }
    
    # 1. PRIMÁRNÍ ZDROJ: MDČR (dataovozidlech.cz) - obsahuje všechna data vozidel přihlášených v ČR
    mdcr_data = None
    try:
        print(f"[API] Načítám data z MDČR (dataovozidlech.cz) pro VIN: {vin}")
        mdcr_data = _fetch_mdcr_data(vin)
    except Exception as e:
        print(f"[API] Chyba při načítání MDČR: {e}")
        import traceback
        traceback.print_exc()
        mdcr_data = None
    
    if mdcr_data:
        print(f"[API] OK: MDCR data uspesne ziskana: brand={mdcr_data.get('brand')}, model={mdcr_data.get('model')}, year={mdcr_data.get('year')}, engine_code={mdcr_data.get('engine_code')}, tyres={len(mdcr_data.get('tyres', []))}")
        # Mapování dat z MDČR (data jsou už ve správném formátu z _fetch_mdcr_data)
        # Zkopírovat všechna pole z mdcr_data do result
        for key in ['brand', 'model', 'year', 'engine', 'engine_code', 'plate', 'name', 'tyres', 
                    'vehicle_type', 'max_power', 'tyres_raw', 'additional_notes', 'inspection_date']:
            if key in mdcr_data and mdcr_data[key]:
                result[key] = mdcr_data[key]
        print(f"[API] Po MDČR: brand={result.get('brand')}, model={result.get('model')}, year={result.get('year')}, engine={result.get('engine')}, engine_code={result.get('engine_code')}, vehicle_type={result.get('vehicle_type')}, max_power={result.get('max_power')}, tyres={len(result.get('tyres', []))}")
    
    # 2. NHTSA použijeme JEN jako poslední fallback, pokud MDČR úplně selhalo
    # Pro česká vozidla je MDČR primární a nejpřesnější zdroj
    if not mdcr_data or not any([result['brand'], result['model'], result['year']]):
        print(f"[API] MDČR nevrátilo dostatečná data, zkouším NHTSA jako fallback...")
        nhtsa_data = _fetch_vin_decoder_api(vin)
        if nhtsa_data:
            print(f"[API] NHTSA data získána jako fallback")
            if not result['brand'] and 'brand' in nhtsa_data:
                result['brand'] = nhtsa_data['brand']
            if not result['model'] and 'model' in nhtsa_data:
                result['model'] = nhtsa_data['model']
            if not result['year'] and 'year' in nhtsa_data:
                result['year'] = nhtsa_data['year']
            if not result['engine'] and 'engine' in nhtsa_data:
                result['engine'] = nhtsa_data['engine']
            # Kód motoru - použijeme NHTSA jen pokud MDČR nevrátilo
            if not result['engine_code'] and 'engine_code' in nhtsa_data:
                result['engine_code'] = nhtsa_data['engine_code']
            if not result['name'] and 'name' in nhtsa_data:
                result['name'] = nhtsa_data['name']
            # Pneumatiky - použijeme NHTSA jen pokud MDČR nevrátilo
            if not result['tyres'] and 'tyres' in nhtsa_data and nhtsa_data['tyres']:
                result['tyres'] = nhtsa_data['tyres']
    
    # 3. Pokud nemáme název, vytvoříme ho z značky a modelu (bez roku)
    if not result['name']:
        name_parts = []
        if result['brand']:
            name_parts.append(result['brand'])
        if result['model']:
            name_parts.append(result['model'])
        if name_parts:
            result['name'] = ' '.join(name_parts)
    
    # 3. Pokud se nepodařilo získat žádná data, vyhodíme výjimku
    # Ale pouze pokud nemáme vůbec žádná data (ani pneumatiky, ani kód motoru)
    has_any_data = any([
        result['brand'], 
        result['model'], 
        result['year'], 
        result['engine'],
        result['engine_code'],
        result['plate'],
        result['tyres']
    ])
    
    if not has_any_data:
        raise Exception("Nepodařilo se získat informace o vozidle z MDČR ani z veřejného VIN dekodéru. Zkontrolujte prosím VIN kód.")
    
    # Vrátit i částečná data
    print(f"[API] Vracím result: brand={result.get('brand')}, model={result.get('model')}, year={result.get('year')}, engine={result.get('engine')}, engine_code={result.get('engine_code')}, plate={result.get('plate')}, tyres={len(result.get('tyres', []))}")
    return result
