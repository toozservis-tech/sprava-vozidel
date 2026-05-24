# KOMPLETNÍ OPRAVA sprava-vozidel - SHRNUTÍ

**Datum:** 2025-01-27  
**Root:** /opt/toozhub2/

---

## ✅ ZMĚNĚNÉ SOUBORY

### 1. `/opt/toozhub2/app/src/modules/vehicle_hub/database.py`
**Změna:** Opravena DB path - používá absolutní cestu `/opt/toozhub2/data/vehicles.db`
- ✅ Vytváří `/opt/toozhub2/data/` složku pokud neexistuje
- ✅ Používá absolutní path místo relativní (`./vehicles.db`)
- ✅ Fallback na ENV proměnné `DATABASE_URL` nebo `VEHICLE_DB_URL`

### 2. `/opt/toozhub2/app/src/modules/vehicle_hub/routers_v1/vehicles.py`
**Změna:** Vylepšené error handling a logování pro GET /vehicles
- ✅ Přidáno detailní logování s logger
- ✅ Lepší error handling s traceback
- ✅ Použití `getattr()` pro bezpečné přístup k atributům
- ✅ Pokračuje i při chybách jednotlivých vozidel

### 3. `/opt/toozhub2/app/src/modules/vehicle_hub/decoder/mdcr_client.py`
**Změna:** Opraveno použití MDČR API klíče
- ✅ Čte POUZE z ENV (`DATAOVO_API_KEY`, `DATAOVO_API_BASE_URL`)
- ✅ Přidáno logování: `[MDCR] API CALLED WITH VIN=...`
- ✅ Přidáno logování: `[MDCR] RESPONSE STATUS=...`
- ✅ Přidáno logování: `[MDCR] DATA RECEIVED`
- ✅ `source_priority` vždy obsahuje `["mdcr"]` pokud API vrátí data

### 4. `/opt/toozhub2/app/src/modules/vehicle_hub/decoder/merge_utils.py`
**Změna:** Opravena merge logika
- ✅ MDČR má VŽDY vyšší prioritu než local_vin
- ✅ Pokud `mdcr_data` existuje, `"mdcr"` je na první pozici v `source_priority`
- ✅ Opraven duplicitní kód

### 5. `/opt/toozhub2/app/src/modules/vehicle_hub/decoder/router.py`
**Změna:** Vylepšené logování a validace
- ✅ Přidáno ověření, že `"mdcr"` je v `source_priority`
- ✅ Přidáno ověření, že `"mdcr"` je na první pozici po merge
- ✅ Vylepšené logování s timing

### 6. `/opt/toozhub2/app/src/core/config.py`
**Změna:** Konfigurace POUZE z ENV
- ✅ `DATAOVO_API_KEY = os.getenv("DATAOVO_API_KEY", "")`
- ✅ `DATAOVO_API_BASE_URL = os.getenv("DATAOVO_API_BASE_URL", "...")`

### 7. `/opt/toozhub2/app/.env`
**Změna:** Přidán MDČR API klíč
- ✅ `DATAOVO_API_KEY=uNlYcvJan3ClsXzyf5Ezl3N5Bxz5C86k`
- ✅ `DATAOVO_API_BASE_URL=https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2`

### 8. `/opt/toozhub2/data/vehicles.db`
**Změna:** DB migrována do `/opt/toozhub2/data/`
- ✅ DB zkopírována z `/opt/toozhub2/app/vehicles.db`
- ✅ Nová DB path: `/opt/toozhub2/data/vehicles.db`

---

## 🔧 KROK 1: OPRAVA /vehicles 500

### Problém:
- DB path byl relativní (`sqlite:///./vehicles.db`)
- Chybějící error handling
- Chybějící logování

### Oprava:
1. ✅ DB path změněn na absolutní: `/opt/toozhub2/data/vehicles.db`
2. ✅ Přidáno detailní logování do `get_vehicles()`
3. ✅ Vylepšené error handling s traceback
4. ✅ DB migrována do nové lokace

### Test:
```bash
# Test GET /vehicles (vyžaduje autentizaci)
curl -X GET http://127.0.0.1:8000/api/v1/vehicles \
  -H "Authorization: Bearer <token>"
```

**Očekávaný výsledek:** `200 OK` s JSON listem vozidel (nebo prázdný list `[]`)

---

## 🔧 KROK 2: VIN BACKEND (MDČR + merge)

### Oprava:
1. ✅ MDČR client čte ENV proměnné
2. ✅ MDČR API volá s hlavičkou `api_key`
3. ✅ Merge logika má správnou prioritu (mdcr > eu > local_vin)
4. ✅ `source_priority` obsahuje `"mdcr"` na první pozici

### Test:
```bash
curl -X POST http://127.0.0.1:8000/api/vehicles/decode-vin \
  -H "Content-Type: application/json" \
  -d '{"vin": "TMBJF73T2B9044629"}'
```

**Očekávaný výsledek:**
```json
{
  "success": true,
  "data": {
    "vin": "TMBJF73T2B9044629",
    "make": "...",
    "model": "...",
    "source_priority": ["mdcr", "local_vin"]
  }
}
```

---

## 🔧 KROK 3: VIN FRONTEND

### Status: ⏳ ČÁSTEČNĚ IMPLEMENTOVÁNO
- ✅ Frontend volá `POST /api/vehicles/decode-vin`
- ✅ Mapování polí existuje
- ⚠️ Potřebuje otestovat, zda se všechna pole vyplní

### Test:
1. Otevřít `https://hub.toozservis.cz/web/index.html`
2. Přihlásit se
3. Jít na "Přidat vozidlo"
4. Zadat VIN: `TMBJF73T2B9044629`
5. Ověřit, že se vyplní pole: make, model, year, engine, atd.

---

## 🔧 KROK 4: IČO (ARES)

### Status: ✅ IMPLEMENTOVÁNO
- ✅ Endpoint: `GET /api/v1/ares/{ico}`
- ✅ Validace IČO (8 číslic)
- ✅ Mapování: company_name, dic, street, city, zip

### Test:
```bash
curl -X GET http://127.0.0.1:8000/api/v1/ares/27082440
```

**Očekávaný výsledek:**
```json
{
  "ico": "27082440",
  "company_name": "...",
  "dic": "...",
  "street": "...",
  "city": "...",
  "zip": "...",
  "source": "ares"
}
```

---

## 🔧 KROK 5: REMINDERS

### Status: ⏳ POTŘEBUJE TESTOVÁNÍ
- ✅ Endpointy existují: `/api/v1/reminders`
- ✅ CRUD operace implementovány
- ⚠️ Potřebuje otestovat persistence a timezone

---

## 🔧 KROK 6: START / ENV / DEPLOY

### Systemd Service
**Status:** ⚠️ Service `toozhub2.service` neexistuje

**Potřebné:**
1. Vytvořit systemd service soubor
2. Nastavit `EnvironmentFile=/opt/toozhub2/app/.env`
3. Nastavit `WorkingDirectory=/opt/toozhub2/app`
4. Nastavit logy do `/opt/toozhub2/logs/`

---

## 📋 PŘÍKAZY PRO RESTART

### Pokud běží jako systemd service:
```bash
sudo systemctl restart toozhub2
sudo systemctl status toozhub2
```

### Pokud běží jako uvicorn proces:
```bash
# Najít proces
ps aux | grep uvicorn

# Zastavit
pkill -f "uvicorn src.server.main:app"

# Spustit znovu
cd /opt/toozhub2/app
source .venv/bin/activate
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

---

## 🧪 TEST CHECKLIST

### 1. GET /vehicles
```bash
# Získat token (přihlášením)
TOKEN="<token>"

# Test GET /vehicles
curl -X GET http://127.0.0.1:8000/api/v1/vehicles \
  -H "Authorization: Bearer $TOKEN"
```
**Očekávaný výsledek:** `200 OK` s JSON listem

### 2. POST /api/vehicles/decode-vin
```bash
curl -X POST http://127.0.0.1:8000/api/vehicles/decode-vin \
  -H "Content-Type: application/json" \
  -d '{"vin": "TMBJF73T2B9044629"}' | jq '.data.source_priority'
```
**Očekávaný výsledek:** `["mdcr", "local_vin"]` nebo `["mdcr"]`

### 3. GET /api/v1/ares/{ico}
```bash
curl -X GET http://127.0.0.1:8000/api/v1/ares/27082440 | jq '.company_name'
```
**Očekávaný výsledek:** Název firmy (ne null)

### 4. Frontend VIN
- Otevřít UI
- Zadat VIN
- Ověřit, že se vyplní pole

### 5. Frontend IČO
- Otevřít UI
- Zadat IČO
- Ověřit, že se vyplní firma + adresa

---

## 📝 ENV PROMĚNNÉ

### Povinné:
```bash
JWT_SECRET_KEY=mw6LQTPuWxk8DwQtMonHsFizXyP2GhmOkXttbNeBfG8
```

### Volitelné (ale doporučené):
```bash
DATAOVO_API_KEY=uNlYcvJan3ClsXzyf5Ezl3N5Bxz5C86k
DATAOVO_API_BASE_URL=https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2
DATABASE_URL=sqlite:////opt/toozhub2/data/vehicles.db
```

---

## ✅ STATUS

- ✅ KROK 0: Inventura dokončena
- ✅ KROK 1: DB path opraven, error handling vylepšen
- ✅ KROK 2: VIN backend opraven (MDČR API)
- ⏳ KROK 3: VIN frontend (potřebuje testování)
- ✅ KROK 4: ARES lookup implementován
- ⏳ KROK 5: Reminders (potřebuje testování)
- ⏳ KROK 6: Systemd service (potřebuje vytvoření)

---

**Datum dokončení:** 2025-01-27

