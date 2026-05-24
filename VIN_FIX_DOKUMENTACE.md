# VIN DECODE FIX - DOKUMENTACE

**Datum:** 2025-01-27  
**Status:** ✅ Opraveno a připraveno k testování

---

## 📋 SHRNUTÍ ZMĚN

### Frontend (`web/index.html`)

#### 1. Vylepšené logování v `loadVinData()`
- ✅ Přidáno detailní logování každého kroku
- ✅ Logování API URL před voláním
- ✅ Logování request payload
- ✅ Logování response status a dat
- ✅ Lepší error handling s detailními zprávami
- ✅ Detekce CORS chyb
- ✅ Detekce network chyb

**Logy:**
```javascript
[VIN] ========================================
[VIN] loadVinData called with VIN: ...
[VIN] Cleaned VIN: ...
[VIN] Request URL: ...
[VIN] Request method: POST
[VIN] Request payload: { vin: "..." }
[VIN] API response status: OK
[VIN] API response: {...}
```

### Backend (`src/modules/vehicle_hub/decoder/router.py`)

#### 1. Vylepšená validace VIN
- ✅ Validace délky (musí být 17 znaků)
- ✅ Validace znaků (nesmí obsahovat I, O, Q)
- ✅ Automatické čištění (trim, uppercase, odstranění mezer a pomlček)
- ✅ Jasné chybové zprávy při neplatném VIN

#### 2. Vylepšené logování
- ✅ Timing pro každý krok (MDČR API, celkový request)
- ✅ Detailní logování zdrojů dat
- ✅ Logování chyb s traceback
- ✅ Logování výsledků merge

**Logy:**
```
[DECODER] ========================================
[DECODER] VIN decode request received
[DECODER] VIN: ...
[DECODER] VIN length: 17
[DECODER] VIN validation passed
[DECODER] Starting decode process...
[DECODER] [MDČR] Attempting to fetch data...
[DECODER] [MDČR] ✅ Data received (took 1.23s): ...
[DECODER] ✅ Decode completed (took 2.45s)
```

#### 3. Lepší error handling
- ✅ Pokud MDČR API selže, pokračuje s lokálním dekódováním
- ✅ Chyby se přidávají do `errors` pole, ale neblokují response
- ✅ Response vždy obsahuje `success` a `errors` pole

---

## 🔧 ENDPOINTY

### POST `/api/vehicles/decode-vin`

**Request:**
```json
{
  "vin": "WVWZZZ1KZ6W000000"
}
```

**Response (success):**
```json
{
  "success": true,
  "data": {
    "vin": "WVWZZZ1KZ6W000000",
    "make": "Volkswagen",
    "model": "Golf",
    "production_year": 2020,
    "engine_code": "EA211",
    ...
  },
  "errors": []
}
```

**Response (error):**
```json
{
  "success": false,
  "errors": ["VIN musí mít přesně 17 znaků (zadáno: 10)"]
}
```

### GET `/api/v1/vin/{vin}` (alternativní)

**Request:**
```
GET /api/v1/vin/WVWZZZ1KZ6W000000
```

**Response:**
```json
{
  "vin": "WVWZZZ1KZ6W000000",
  "make": "Volkswagen",
  "model": "Golf",
  "year": 2020,
  "engine": "2.0 TDI / 125 kW",
  "source": "mdcr",
  "detail": null
}
```

---

## 🔑 ENV PROMĚNNÉ

### Povinné:
- `JWT_SECRET_KEY` - pro autentizaci (ale VIN endpoint nevyžaduje auth)

### Volitelné (ale doporučené):
- `DATAOVO_API_KEY` nebo `DATAOVOZIDLECH_API_KEY` - pro MDČR API
  - Pokud chybí, MDČR API se přeskočí (pouze lokální dekódování)
- `DATAOVO_API_BASE_URL` - default: `https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2`

### Defaulty:
- Pokud `DATAOVO_API_KEY` chybí:
  - Backend loguje warning
  - MDČR API se přeskočí
  - Použije se pouze lokální VIN dekódování
  - Response může být prázdná nebo částečná

---

## 🧪 TESTOVÁNÍ

### Lokální testování

#### 1. Test endpointu přes curl:
```bash
curl -X POST http://127.0.0.1:8000/api/vehicles/decode-vin \
  -H "Content-Type: application/json" \
  -d '{"vin": "WVWZZZ1KZ6W000000"}'
```

#### 2. Test přes Python:
```bash
cd /opt/toozhub2/app
python -m pytest tests/api/test_vin_decode.py -v
```

#### 3. Test v prohlížeči:
1. Otevřít `http://127.0.0.1:8000/web/index.html`
2. Přihlásit se
3. Jít na "Přidat vozidlo"
4. Zadat VIN do pole "VIN (17 znaků)"
5. Otevřít Developer Console (F12)
6. Sledovat logy `[VIN]` a `[DECODER]`

### Production testování (VPS)

#### 1. Test endpointu přes curl:
```bash
# Na VPS (lokálně)
curl -X POST http://127.0.0.1:8000/api/vehicles/decode-vin \
  -H "Content-Type: application/json" \
  -d '{"vin": "WVWZZZ1KZ6W000000"}'

# Zvenčí (přes Cloudflare)
curl -X POST https://hub.toozservis.cz/api/vehicles/decode-vin \
  -H "Content-Type: application/json" \
  -d '{"vin": "WVWZZZ1KZ6W000000"}'
```

#### 2. Sledování logů:
```bash
# Systemd service logy
sudo journalctl -u toozhub2 -f

# Nebo pokud běží jako Python proces
tail -f /opt/toozhub2/app/server.log
```

#### 3. Test v UI:
1. Otevřít `https://hub.toozservis.cz/web/index.html`
2. Přihlásit se
3. Jít na "Přidat vozidlo"
4. Zadat VIN
5. Otevřít Developer Console (F12)
6. Sledovat logy

---

## 🐛 DIAGNOSTIKA PROBLÉMŮ

### Problém: Frontend nenačítá data

**Kroky:**
1. Otevřít Developer Console (F12)
2. Zkontrolovat logy `[VIN]` - měly by ukazovat:
   - Request URL
   - Request payload
   - Response status
   - Response data

3. Pokud je chyba:
   - **404 Not Found** → Endpoint není zaregistrovaný nebo špatná URL
   - **CORS error** → CORS není správně nakonfigurovaný
   - **Network error** → Server neběží nebo není dostupný
   - **Timeout** → Server trvá příliš dlouho

### Problém: Backend vrací prázdnou odpověď

**Kroky:**
1. Zkontrolovat backend logy:
   ```bash
   sudo journalctl -u toozhub2 -f | grep DECODER
   ```

2. Zkontrolovat ENV proměnné:
   ```bash
   # Na VPS
   sudo systemctl show toozhub2 | grep Environment
   ```

3. Pokud `DATAOVO_API_KEY` chybí:
   - Backend použije pouze lokální dekódování
   - Response může být prázdná nebo částečná
   - To je **normální chování** - není to chyba

### Problém: MDČR API selhává

**Kroky:**
1. Zkontrolovat logy:
   ```
   [DECODER] [MDČR] ❌ Error calling MDČR API: ...
   ```

2. Zkontrolovat ENV:
   - `DATAOVO_API_KEY` musí být nastaven
   - `DATAOVO_API_BASE_URL` musí být správný

3. Testovat MDČR API přímo:
   ```bash
   curl "https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2?vin=WVWZZZ1KZ6W000000" \
     -H "api_key: YOUR_API_KEY"
   ```

---

## 📝 COMMIT MESSAGE

```
fix(vin): enable VIN decode flow on VPS + add logs + stable API contract

- Frontend: Add detailed logging to loadVinData() with request/response tracking
- Frontend: Improve error handling with specific messages for CORS, network, timeout
- Backend: Add VIN validation (length, characters) with clear error messages
- Backend: Add timing logs for MDČR API calls and overall request duration
- Backend: Improve error handling - continue with local decode if MDČR fails
- Tests: Add test_vin_decode.py with validation and format tests
- Docs: Add VIN_FIX_DOKUMENTACE.md with testing and troubleshooting guide

Fixes VIN decode not working on production VPS by:
- Ensuring proper API URL detection in production
- Adding comprehensive logging for debugging
- Making MDČR API optional (fallback to local decode)
- Validating VIN format before processing
```

---

## ✅ CHECKLIST PRO DEPLOYMENT

- [x] Frontend logging přidáno
- [x] Backend logging přidáno
- [x] VIN validace přidána
- [x] Error handling vylepšen
- [x] Testy vytvořeny
- [ ] Testováno lokálně
- [ ] Testováno na VPS
- [ ] Dokumentace aktualizována

---

## 🚀 DALŠÍ KROKY (volitelné)

1. **Cache implementace:**
   - Přidat in-memory cache pro VIN dekódování
   - TTL: 30 dní
   - LRU eviction

2. **DB cache:**
   - Vytvořit tabulku `vin_cache`
   - Ukládat dekódovaná data
   - Použít při opakovaných requestech

3. **Retry logika:**
   - Přidat retry pro MDČR API (max 2 pokusy)
   - Exponential backoff

4. **Monitoring:**
   - Přidat metriky (success rate, latency)
   - Alerting při vysoké chybovosti

