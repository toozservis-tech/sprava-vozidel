# VIN DECODE FLOW - AUDIT REPORT

**Datum:** 2025-01-27  
**Cíl:** Najít všechny komponenty VIN decode flow a identifikovat problémy

---

## 📍 KROK 1: SOUČASNÝ VIN FLOW - MAPOVÁNÍ

### Frontend komponenty

#### 1. VIN Input Handler
**Soubor:** `web/index.html`  
**Funkce:** `loadVinData(vin)` (řádek ~4484)  
**Event listener:** řádek ~6779-6805  
- Naslouchá na `input` event na `#vehicleVin`
- Automaticky volá `loadVinData()` když je VIN 17 znaků a validní
- Debounce: 500ms

**Alternativní implementace:**
- `lookupVin(vin)` (řádek ~8497) - volá `/api/v1/vin/{vin}` GET
- `attachVin()` (řádek ~8545) - alternativní listener

#### 2. API Client
**Soubor:** `web/index.html`  
**Funkce:** `apiCall(endpoint, method, data, signal)` (řádek ~3068)  
**Base URL funkce:** `getApiBaseUrl()` (řádek ~2906)

**Base URL logika:**
- **Produkce:** `https://hub.toozservis.cz` (pokud `hostname === "hub.toozservis.cz"`)
- **Dev:** localStorage `toozhub_api_url` nebo fallback `http://127.0.0.1:8000`
- **Iframe:** detekuje iframe a používá produkční URL

**VIN API volání:**
- `POST /api/vehicles/decode-vin` s `{ vin: "..." }` (hlavní implementace)
- `GET /api/v1/vin/{vin}` (alternativní implementace)

---

### Backend komponenty

#### 1. Decoder Router (hlavní endpoint)
**Soubor:** `src/modules/vehicle_hub/decoder/router.py`  
**Endpoint:** `POST /api/vehicles/decode-vin`  
**Funkce:** `decode_vin(req: VinDecodeRequest, db: Session)` (řádek ~23)

**Registrace:**
- Zaregistrován v `src/server/main.py` řádek ~169
- Prefix: `/api/vehicles`
- Tag: `["vehicles", "decoder"]`

**Flow:**
1. Lokální VIN dekódování (`decode_vin_local`)
2. MDČR API (`fetch_vehicle_by_vin_from_mdcr`) - pokud je API key
3. EU Open Data API (`fetch_vehicle_by_vin_from_eu_open_data`)
4. Šablona z DB (`get_template_from_db`)
5. Merge dat (`merge_vehicle_data`)

**Response:** `VehicleDecodeResponse` s `success`, `data`, `errors`

#### 2. VIN Lookup Router (alternativní endpoint)
**Soubor:** `src/modules/vehicle_hub/routers_v1/vin_lookup.py`  
**Endpoint:** `GET /api/v1/vin/{vin}`  
**Funkce:** `lookup_vin(vin: str, db: Session)` (řádek ~28)

**Registrace:**
- Zaregistrován v `src/modules/vehicle_hub/routers_v1/__init__.py` řádek ~22
- Prefix: `/api/v1` → `/api/v1/vin`
- Tag: `["vin-lookup-v1"]`

**Flow:**
1. Validace VIN (17 znaků, alfanumerické)
2. Volá `decode_vin()` z decoder routeru
3. Mapuje na zjednodušenou `VinLookupResponse`

**Response:** `VinLookupResponse` s `vin`, `make`, `model`, `year`, `engine`, `source`, `detail`

---

### Service/Client moduly

#### 1. MDČR Client
**Soubor:** `src/modules/vehicle_hub/decoder/mdcr_client.py`  
**Funkce:** `fetch_vehicle_by_vin_from_mdcr(vin: str)` (řádek ~110)

**Konfigurace:**
- ENV: `DATAOVO_API_KEY` nebo `DATAOVOZIDLECH_API_KEY`
- ENV: `DATAOVO_API_BASE_URL` (default: `https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2`)
- Timeout: 30s (httpx.AsyncClient)

**Logování:**
- INFO: VIN, API URL, token status
- WARNING: pokud API není nakonfigurováno
- ERROR: při chybách

#### 2. EU Open Data Client
**Soubor:** `src/modules/vehicle_hub/decoder/eu_open_data_client.py`  
**Funkce:** `fetch_vehicle_by_vin_from_eu_open_data(vin: str)`

#### 3. Lokální VIN Decoder
**Soubor:** `src/modules/vehicle_hub/decoder/vin_decoder.py`  
**Funkce:** `decode_vin_local(vin: str)`

---

### DB modely

**Soubor:** `src/modules/vehicle_hub/models.py`  
**Model:** `Vehicle` (řádek ~93)
- `vin` - String, nullable

**Template model:** `VehicleTemplate` (řádek ~238)
- `default_notes` - Text, nullable

---

## 🔍 IDENTIFIKOVANÉ PROBLÉMY

### 1. Frontend volá špatný endpoint nebo base URL
**Problém:**
- Frontend má dvě implementace (`loadVinData` a `lookupVin`)
- `getApiBaseUrl()` může vracet špatnou URL na VPS
- Na VPS může být problém s detekcí produkčního režimu

**Řešení:**
- Zajistit, že `getApiBaseUrl()` správně detekuje produkci
- Přidat explicitní logování do console
- Ověřit, že endpoint je dostupný

### 2. Backend endpoint může být nedostupný
**Problém:**
- CORS může blokovat requesty
- Routery mohou být špatně zaregistrované
- Endpoint může vyžadovat autentizaci, ale frontend ji neposílá

**Řešení:**
- Ověřit CORS konfiguraci
- Zkontrolovat registraci routerů
- Ověřit, zda endpoint vyžaduje auth (neměl by)

### 3. ENV proměnné nejsou nastavené
**Problém:**
- `DATAOVO_API_KEY` může chybět
- Backend vrací prázdnou odpověď místo chyby

**Řešení:**
- Přidat validaci ENV při startu
- Vracet jasnou chybu pokud API key chybí
- Logovat warning pokud API key chybí

### 4. MDČR API selhává bez viditelné chyby
**Problém:**
- Pokud MDČR API selže, backend pokračuje s lokálním dekódováním
- Frontend může dostat prázdnou odpověď a neví proč

**Řešení:**
- Přidat detailní logování
- Vracet status "partial" pokud některé zdroje selhaly
- Logovat do production logů

---

## 📋 ENV PROMĚNNÉ

### Povinné:
- `JWT_SECRET_KEY` - pro autentizaci (ale VIN endpoint by neměl vyžadovat auth)

### Volitelné (ale doporučené):
- `DATAOVO_API_KEY` nebo `DATAOVOZIDLECH_API_KEY` - pro MDČR API
- `DATAOVO_API_BASE_URL` - default: `https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2`

### Defaulty:
- `DATAOVO_API_BASE_URL` = `https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2`
- Pokud `DATAOVO_API_KEY` chybí, MDČR API se přeskočí (pouze lokální dekódování)

---

## 🎯 DALŠÍ KROKY

1. ✅ Audit dokončen
2. ⏳ Opravit frontend BASE_URL detekci
3. ⏳ Přidat detailní logování
4. ⏳ Ověřit CORS konfiguraci
5. ⏳ Přidat validaci ENV
6. ⏳ Vytvořit test

