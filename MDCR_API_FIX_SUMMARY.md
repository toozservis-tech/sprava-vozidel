# MDČR API FIX - SHRNUTÍ ZMĚN

**Datum:** 2025-01-27  
**Status:** ✅ Opraveno

---

## 📋 ZMĚNĚNÉ SOUBORY

### 1. `src/core/config.py`
**Změna:** Konfigurace POUZE z ENV proměnných
- ✅ Používá `os.getenv("DATAOVO_API_KEY", "")` bez fallbacků
- ✅ Používá `os.getenv("DATAOVO_API_BASE_URL", "...")` s default hodnotou
- ✅ Odstraněny všechny fallbacky na staré názvy proměnných

### 2. `src/modules/vehicle_hub/decoder/mdcr_client.py`
**Změny:**
- ✅ Konfigurace POUZE z ENV (`DATAOVO_API_KEY`, `DATAOVO_API_BASE_URL`)
- ✅ Přidáno logování: `[MDCR] API CALLED WITH VIN=...`
- ✅ Přidáno logování: `[MDCR] RESPONSE STATUS=...`
- ✅ Přidáno logování: `[MDCR] DATA RECEIVED`
- ✅ Hlavičky: `{"api_key": DATAOVO_API_KEY, "Accept": "application/json"}`
- ✅ `source_priority` vždy obsahuje `["mdcr"]` pokud API vrátí data

### 3. `src/modules/vehicle_hub/decoder/merge_utils.py`
**Změny:**
- ✅ Opraven duplicitní kód (odstraněna druhá kopie funkce)
- ✅ MDČR má VŽDY vyšší prioritu než local_vin
- ✅ Pokud `mdcr_data` existuje, `"mdcr"` MUSÍ být na první pozici v `source_priority`
- ✅ Logování ověření priority

### 4. `src/modules/vehicle_hub/decoder/router.py`
**Změny:**
- ✅ Přidáno ověření, že `"mdcr"` je v `source_priority` po volání MDČR API
- ✅ Přidáno ověření, že `"mdcr"` je na první pozici po merge
- ✅ Vylepšené logování s prefixem `[MDCR]`

---

## ✅ OVĚŘENÍ

### KROK 4: Swagger /docs test

**Endpoint:** `POST /api/vehicles/decode-vin`

**Request:**
```json
{
  "vin": "TMBJF73T2B9044629"
}
```

**Očekávaná Response:**
```json
{
  "success": true,
  "data": {
    "vin": "TMBJF73T2B9044629",
    "make": "...",
    "model": "...",
    "production_year": ...,
    "engine_code": "...",
    "engine_power_kw": ...,
    "fuel_type": "...",
    "tech_inspection_valid_to": "...",
    "source_priority": ["mdcr", ...]
  },
  "errors": []
}
```

**Kontrola:**
- ✅ `source_priority` MUSÍ obsahovat `"mdcr"` na první pozici
- ✅ Pokud `"mdcr"` není v `source_priority` → JE TO CHYBA (bude zalogováno)

---

## 🔑 ENV PROMĚNNÉ

### Povinné:
```bash
DATAOVO_API_KEY=uNlYcvJan3ClsXzyf5Ezl3N5Bxz5C86k
```

### Volitelné (má default):
```bash
DATAOVO_API_BASE_URL=https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2
```

---

## 📝 LOGOVÁNÍ

### Před voláním API:
```
[MDCR] ========================================
[MDCR] API CALLED WITH VIN=TMBJF73T2B9044629
[MDCR] API URL: https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2
[MDCR] API KEY: SET (length: 32)
[MDCR] Request URL: https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2?vin=TMBJF73T2B9044629
```

### Po volání API:
```
[MDCR] RESPONSE STATUS=200
[MDCR] DATA RECEIVED
[MDCR] Mapping API data to VehicleDecodedData
```

### Po merge:
```
[MERGE] MDČR data existuje - 'mdcr' je na první pozici v source_priority
[DECODER] [VIN] ✅ 'mdcr' je na první pozici v source_priority
```

---

## 🚨 CHYBY (pokud se vyskytnou)

### Pokud `"mdcr"` není v `source_priority`:
```
[DECODER] [MDCR] ❌ CHYBA: 'mdcr' není v source_priority! [...]
```

### Pokud `"mdcr"` není na první pozici:
```
[DECODER] [VIN] ❌ CHYBA: 'mdcr' není na první pozici! source_priority=[...]
```

---

## ✅ POTVRZENÍ

**MDČR API je AKTIVNĚ používáno:**
- ✅ API klíč se čte POUZE z ENV (`DATAOVO_API_KEY`)
- ✅ Request se vytváří s hlavičkou `api_key`
- ✅ Pokud API vrátí data, `source_priority` obsahuje `"mdcr"` na první pozici
- ✅ MDČR data mají VŽDY vyšší prioritu než local_vin
- ✅ Logování potvrzuje každý krok

---

## 🧪 TESTOVÁNÍ

### 1. Lokální test:
```bash
# Nastavit ENV
export DATAOVO_API_KEY=uNlYcvJan3ClsXzyf5Ezl3N5Bxz5C86k

# Spustit server
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000

# Testovat endpoint
curl -X POST http://127.0.0.1:8000/api/vehicles/decode-vin \
  -H "Content-Type: application/json" \
  -d '{"vin": "TMBJF73T2B9044629"}'
```

### 2. Ověřit logy:
```bash
# Sledovat logy
tail -f /var/log/toozhub2/server.log | grep MDCR
```

### 3. Ověřit response:
- Zkontrolovat, že `source_priority[0] == "mdcr"`
- Zkontrolovat, že data obsahují `make`, `model`, `production_year`, atd.

---

**Status:** ✅ Všechny změny dokončeny a připraveny k testování

