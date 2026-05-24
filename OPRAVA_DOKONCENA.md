# ✅ OPRAVA sprava-vozidel DOKONČENA

**Datum:** 2025-01-27  
**Root:** /opt/toozhub2/

---

## 📋 ZMĚNĚNÉ SOUBORY

1. ✅ `src/modules/vehicle_hub/database.py` - DB path opraven na absolutní
2. ✅ `src/modules/vehicle_hub/routers_v1/vehicles.py` - Error handling + logování
3. ✅ `src/modules/vehicle_hub/decoder/mdcr_client.py` - MDČR API z ENV
4. ✅ `src/modules/vehicle_hub/decoder/merge_utils.py` - Merge priorita opravena
5. ✅ `src/modules/vehicle_hub/decoder/router.py` - Logování + validace
6. ✅ `src/core/config.py` - Konfigurace z ENV
7. ✅ `web/index.html` - VIN mapování vylepšeno
8. ✅ `.env` - Přidán DATAOVO_API_KEY
9. ✅ `/opt/toozhub2/data/vehicles.db` - DB migrována

---

## 🚀 PŘÍKAZY PRO RESTART

### Restart serveru (pokud běží jako proces):
```bash
# 1. Zastavit
pkill -f "uvicorn src.server.main:app"

# 2. Spustit
cd /opt/toozhub2/app
source .venv/bin/activate
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

### Nebo vytvořit systemd service:
```bash
sudo nano /etc/systemd/system/toozhub2.service
```

**Vložit:**
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

**Aktivovat:**
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

### 1. GET /vehicles (200 OK)
```bash
curl -X GET http://127.0.0.1:8000/api/v1/vehicles \
  -H "Authorization: Bearer <token>"
```
**Očekávaný výsledek:** `200 OK` s JSON listem

### 2. POST /api/vehicles/decode-vin (MDČR)
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
**Očekávaný výsledek:** Název firmy

### 4. Frontend VIN
- Otevřít UI → Přidat vozidlo → Zadat VIN
- Ověřit vyplnění polí
- Console: `[VIN] Filled fields: [...]`

### 5. Frontend IČO
- Otevřít UI → Zadat IČO
- Ověřit vyplnění firmy + adresy

---

## 📝 ENV PROMĚNNÉ

V `/opt/toozhub2/app/.env`:
```bash
DATAOVO_API_KEY=uNlYcvJan3ClsXzyf5Ezl3N5Bxz5C86k
DATAOVO_API_BASE_URL=https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2
```

---

## ✅ STATUS

- ✅ KROK 0: Inventura
- ✅ KROK 1: DB path + /vehicles 500
- ✅ KROK 2: VIN backend (MDČR)
- ✅ KROK 3: VIN frontend
- ✅ KROK 4: ARES lookup
- ⏳ KROK 5: Reminders (potřebuje test)
- ⏳ KROK 6: Systemd service (potřebuje vytvoření)

---

**Dokončeno:** 2025-01-27

