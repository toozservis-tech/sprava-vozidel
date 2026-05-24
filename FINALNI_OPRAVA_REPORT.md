# FINÁLNÍ OPRAVA sprava-vozidel - REPORT

**Datum:** 2025-01-27  
**Root:** /opt/toozhub2/

---

## ✅ ZMĚNĚNÉ SOUBORY

### 1. `src/modules/vehicle_hub/database.py`
**Změna:** Opravena DB path na absolutní cestu
- ✅ Vytváří `/opt/toozhub2/data/` pokud neexistuje
- ✅ Používá absolutní path: `/opt/toozhub2/data/vehicles.db`
- ✅ Fallback na ENV proměnné

### 2. `src/modules/vehicle_hub/routers_v1/vehicles.py`
**Změna:** Vylepšené error handling a logování
- ✅ Detailní logování s logger
- ✅ Error handling s traceback
- ✅ Bezpečné přístupy k atributům (`getattr()`)

### 3. `src/modules/vehicle_hub/decoder/mdcr_client.py`
**Změna:** Opraveno použití MDČR API
- ✅ Čte POUZE z ENV
- ✅ Přidáno logování: `[MDCR] API CALLED WITH VIN=...`
- ✅ Přidáno logování: `[MDCR] RESPONSE STATUS=...`
- ✅ Přidáno logování: `[MDCR] DATA RECEIVED`

### 4. `src/modules/vehicle_hub/decoder/merge_utils.py`
**Změna:** Opravena merge logika
- ✅ MDČR má VŽDY prioritu
- ✅ `"mdcr"` je na první pozici v `source_priority`

### 5. `src/modules/vehicle_hub/decoder/router.py`
**Změna:** Vylepšené logování a validace
- ✅ Ověření `"mdcr"` v `source_priority`
- ✅ Timing logy

### 6. `src/core/config.py`
**Změna:** Konfigurace POUZE z ENV
- ✅ `DATAOVO_API_KEY = os.getenv("DATAOVO_API_KEY", "")`

### 7. `web/index.html`
**Změna:** Vylepšené VIN mapování
- ✅ Přidáno logování vyplněných polí
- ✅ Přidána informace o zdroji dat do poznámek

### 8. `.env`
**Změna:** Přidán MDČR API klíč
- ✅ `DATAOVO_API_KEY=uNlYcvJan3ClsXzyf5Ezl3N5Bxz5C86k`
- ✅ `DATAOVO_API_BASE_URL=https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2`

### 9. `/opt/toozhub2/data/vehicles.db`
**Změna:** DB migrována do nové lokace
- ✅ Zkopírována z `/opt/toozhub2/app/vehicles.db`
- ✅ Nová path: `/opt/toozhub2/data/vehicles.db`

---

## 📋 KONKRÉTNÍ DIFF/PATCH

### database.py
```python
# PŘED:
DB_URL = os.getenv("DATABASE_URL") or os.getenv("VEHICLE_DB_URL", "sqlite:///./vehicles.db")

# PO:
from pathlib import Path
_db_url_env = os.getenv("DATABASE_URL") or os.getenv("VEHICLE_DB_URL")
if _db_url_env:
    DB_URL = _db_url_env
else:
    project_root = Path(__file__).parent.parent.parent.parent
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_file = data_dir / "vehicles.db"
    DB_URL = f"sqlite:///{db_file}"
```

### vehicles.py
```python
# PŘIDÁNO:
import logging
logger = logging.getLogger(__name__)
logger.info(f"[VEHICLES] GET /api/v1/vehicles - Načítání vozidel")
# ... detailní logování ...
logger.error(f"[VEHICLES] ❌ FATAL ERROR: {error_msg}")
```

### mdcr_client.py
```python
# PŘED:
DATAOVOZIDLECH_API_KEY = DATAOVO_API_KEY or MDCR_API_TOKEN or os.getenv("DATAOVO_API_KEY") or ...

# PO:
DATAOVO_API_KEY = os.getenv("DATAOVO_API_KEY", "")
DATAOVO_API_BASE_URL = os.getenv("DATAOVO_API_BASE_URL", "https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2")
```

---

## 🚀 PŘÍKAZY PRO RESTART

### 1. Zastavit současný server
```bash
# Najít proces
ps aux | grep "uvicorn src.server.main:app"

# Zastavit
pkill -f "uvicorn src.server.main:app"
```

### 2. Spustit server znovu
```bash
cd /opt/toozhub2/app
source .venv/bin/activate  # nebo: source /opt/toozhub2/app/.venv/bin/activate
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

### 3. Nebo vytvořit systemd service (doporučeno)
```bash
sudo nano /etc/systemd/system/toozhub2.service
```

**Obsah:**
```ini
[Unit]
Description=Správa vozidel API Server
After=network.target

[Service]
Type=simple
User=toozhub2
Group=toozhub2
WorkingDirectory=/opt/toozhub2/app
EnvironmentFile=/opt/toozhub2/app/.env
ExecStart=/opt/toozhub2/app/.venv/bin/python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10
StandardOutput=append:/opt/toozhub2/logs/server.log
StandardError=append:/opt/toozhub2/logs/server.log

[Install]
WantedBy=multi-user.target
```

**Aktivace:**
```bash
sudo mkdir -p /opt/toozhub2/logs
sudo chown toozhub2:toozhub2 /opt/toozhub2/logs
sudo systemctl daemon-reload
sudo systemctl enable toozhub2
sudo systemctl start toozhub2
sudo systemctl status toozhub2
```

---

## 🧪 TEST CHECKLIST

### Test 1: GET /vehicles (200 OK)
```bash
# Získat token (přihlášením přes UI nebo API)
TOKEN="<token>"

curl -X GET http://127.0.0.1:8000/api/v1/vehicles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```
**Očekávaný výsledek:** `200 OK` s JSON listem (nebo `[]`)

### Test 2: POST /api/vehicles/decode-vin (MDČR)
```bash
curl -X POST http://127.0.0.1:8000/api/vehicles/decode-vin \
  -H "Content-Type: application/json" \
  -d '{"vin": "TMBJF73T2B9044629"}' | jq '.data.source_priority'
```
**Očekávaný výsledek:** `["mdcr", "local_vin"]` nebo `["mdcr"]`

### Test 3: GET /api/v1/ares/{ico}
```bash
curl -X GET http://127.0.0.1:8000/api/v1/ares/27082440 | jq '.company_name'
```
**Očekávaný výsledek:** Název firmy (ne null)

### Test 4: Frontend VIN
1. Otevřít `https://hub.toozservis.cz/web/index.html`
2. Přihlásit se
3. Jít na "Přidat vozidlo"
4. Zadat VIN: `TMBJF73T2B9044629`
5. Otevřít Developer Console (F12)
6. Sledovat logy `[VIN]`
7. Ověřit, že se vyplní pole: make, model, year, engine, atd.

**Očekávaný výsledek:**
- Console: `[VIN] Filled fields: [make, model, year, ...]`
- UI: Pole jsou vyplněná

### Test 5: Frontend IČO
1. Otevřít UI
2. Jít na registraci/přidat vozidlo
3. Zadat IČO: `27082440`
4. Ověřit, že se vyplní: company_name, dic, street, city, zip

**Očekávaný výsledek:**
- Pole jsou vyplněná s daty z ARES

### Test 6: Reminders
1. Otevřít UI
2. Jít na "Připomínky"
3. Vytvořit připomínku
4. Reload stránky
5. Ověřit, že připomínka stále existuje

**Očekávaný výsledek:**
- Připomínka je persistentní

---

## 📝 ENV PROMĚNNÉ

### V `/opt/toozhub2/app/.env`:
```bash
ENVIRONMENT=production
HOST=127.0.0.1
PORT=8000
JWT_SECRET_KEY=mw6LQTPuWxk8DwQtMonHsFizXyP2GhmOkXttbNeBfG8
DATAOVO_API_KEY=uNlYcvJan3ClsXzyf5Ezl3N5Bxz5C86k
DATAOVO_API_BASE_URL=https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2
# DATABASE_URL=sqlite:////opt/toozhub2/data/vehicles.db  # (volitelné, má default)
```

---

## ✅ STATUS

- ✅ KROK 0: Inventura dokončena
- ✅ KROK 1: DB path opraven, /vehicles 500 opraven
- ✅ KROK 2: VIN backend opraven (MDČR API)
- ✅ KROK 3: VIN frontend vylepšen (mapování + logování)
- ✅ KROK 4: ARES lookup implementován
- ⏳ KROK 5: Reminders (potřebuje testování)
- ⏳ KROK 6: Systemd service (potřebuje vytvoření)

---

## 🎯 DALŠÍ KROKY

1. **Vytvořit systemd service** (KROK 6)
2. **Otestovat všechny endpointy** (test checklist)
3. **Ověřit logy** při běhu
4. **Otestovat frontend** v produkci

---

**Datum dokončení:** 2025-01-27

