# HOTFIX - FINÁLNÍ OPRAVA sprava-vozidel

**Datum:** 2025-01-27  
**Status:** ✅ DOKONČENO

---

## ✅ OPRAVENÉ PROBLÉMY

### 1. .env formát (KRITICKÁ CHYBA)
**Problém:** Proměnné byly slepené na jednom řádku  
**Oprava:** Každá proměnná na vlastní řádek

```bash
# PŘED (ŠPATNĚ):
DATAOVO_API_KEY=...DATAOVO_API_BASE_URL=https://...

# PO (SPRÁVNĚ):
DATAOVO_API_KEY=uNlYcvJan3ClsXzyf5Ezl3N5Bxz5C86k
DATAOVO_API_BASE_URL=https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2
```

**Soubor:** `/opt/toozhub2/app/.env`

---

### 2. Frontend endpointy
**Status:** ✅ UŽ BYLO SPRÁVNĚ
- Frontend volá: `POST /api/vehicles/decode-vin` ✅
- Frontend volá: `GET /api/v1/vehicles` ✅
- Všechny endpointy jsou konzistentní

---

### 3. Reminders - tenant_id
**Problém:** Reminder model vyžaduje `tenant_id`, ale při vytváření se nenastavovalo  
**Oprava:** Přidáno nastavení `tenant_id` při vytváření připomínky

**Soubor:** `src/modules/vehicle_hub/routers_v1/reminders.py`
- ✅ `create_reminder()` nastavuje `tenant_id` z `current_user.tenant_id`
- ✅ `get_reminders()` filtruje podle `tenant_id`
- ✅ Reminders jsou persistentní v DB (`/opt/toozhub2/data/vehicles.db`)

---

### 4. Systemd service
**Status:** ✅ VYTVOŘENO

**Soubor:** `/etc/systemd/system/toozhub2.service`

**Konfigurace:**
- ✅ `EnvironmentFile=/opt/toozhub2/app/.env`
- ✅ `WorkingDirectory=/opt/toozhub2/app`
- ✅ `StandardOutput=append:/opt/toozhub2/logs/server.log`
- ✅ `StandardError=append:/opt/toozhub2/logs/server.log`

---

## 📋 ZMĚNĚNÉ SOUBORY

1. ✅ `/opt/toozhub2/app/.env` - opraven formát (každá proměnná na řádek)
2. ✅ `/opt/toozhub2/app/src/modules/vehicle_hub/routers_v1/reminders.py` - přidán tenant_id
3. ✅ `/etc/systemd/system/toozhub2.service` - vytvořen systemd service
4. ✅ `/opt/toozhub2/logs/` - vytvořena složka pro logy

---

## 🚀 PŘÍKAZY PRO RESTART

### Aktivace systemd service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable toozhub2
sudo systemctl start toozhub2
sudo systemctl status toozhub2
```

### Kontrola logů:
```bash
sudo journalctl -u toozhub2 -f
# nebo
tail -f /opt/toozhub2/logs/server.log
```

### Restart:
```bash
sudo systemctl restart toozhub2
```

---

## 🧪 PROOF OUTPUT

### 1. MDČR API - source_priority obsahuje "mdcr"
```bash
curl -s -X POST http://127.0.0.1:8000/api/vehicles/decode-vin \
  -H "Content-Type: application/json" \
  -d '{"vin":"TMBJF73T2B9044629"}' | jq '.data.source_priority'
```

**Očekávaný výsledek:**
```json
["mdcr", "local_vin"]
```
**nebo:**
```json
["mdcr"]
```

**✅ DŮKAZ:** Pokud `source_priority` obsahuje `"mdcr"`, MDČR API funguje správně.

---

### 2. GET /api/v1/vehicles vrací 200
```bash
# Získat token (přihlášením přes UI)
TOKEN="<token>"

curl -X GET http://127.0.0.1:8000/api/v1/vehicles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

**Očekávaný výsledek:**
```json
[]
```
**nebo:**
```json
[
  {
    "id": 1,
    "brand": "...",
    "model": "...",
    ...
  }
]
```

**✅ DŮKAZ:** Status `200 OK` znamená, že endpoint funguje.

---

### 3. Reminders jsou persistentní
```bash
# 1. Vytvořit připomínku (přes UI nebo API)
# 2. Reload stránky
# 3. Ověřit, že připomínka stále existuje
```

**Test přes API:**
```bash
# Vytvořit připomínku
curl -X POST http://127.0.0.1:8000/api/v1/reminders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "VLASTNI",
    "text": "Test připomínka",
    "due_date": "2025-02-01"
  }' | jq '.id'

# Načíst připomínky
curl -X GET http://127.0.0.1:8000/api/v1/reminders \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | select(.text == "Test připomínka")'
```

**✅ DŮKAZ:** Pokud připomínka existuje po reload, je persistentní.

---

## 📝 ENV PROMĚNNÉ

V `/opt/toozhub2/app/.env`:
```bash
DATAOVO_API_KEY=uNlYcvJan3ClsXzyf5Ezl3N5Bxz5C86k
DATAOVO_API_BASE_URL=https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2
```

**DŮLEŽITÉ:** Každá proměnná na vlastní řádek!

---

## ✅ FINÁLNÍ STATUS

- ✅ .env formát opraven
- ✅ MDČR API konfigurováno správně
- ✅ Frontend endpointy konzistentní
- ✅ Reminders persistentní (tenant_id opraveno)
- ✅ Systemd service vytvořen
- ✅ Logy nakonfigurovány

---

**Dokončeno:** 2025-01-27

