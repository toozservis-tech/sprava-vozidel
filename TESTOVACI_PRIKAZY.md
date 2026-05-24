# TESTOVACÍ PŘÍKAZY - sprava-vozidel

**Datum:** 2025-01-27

---

## 🚀 RESTART SERVERU

```bash
# Restart systemd service
sudo systemctl restart toozhub2

# Kontrola statusu
sudo systemctl status toozhub2

# Sledování logů
sudo journalctl -u toozhub2 -f
# nebo
tail -f /opt/toozhub2/logs/server.log
```

---

## 🧪 TEST 1: MDČR API - source_priority obsahuje "mdcr"

```bash
curl -s -X POST http://127.0.0.1:8000/api/vehicles/decode-vin \
  -H "Content-Type: application/json" \
  -d '{"vin":"TMBJF73T2B9044629"}' | jq '.data.source_priority'
```

**✅ Očekávaný výsledek:**
```json
["mdcr", "local_vin"]
```
**nebo:**
```json
["mdcr"]
```

**❌ Pokud NENÍ "mdcr":**
- Zkontrolovat `.env` formát (každá proměnná na řádek)
- Zkontrolovat logy: `sudo journalctl -u toozhub2 | grep MDCR`
- Ověřit, že `DATAOVO_API_KEY` je nastaveno

---

## 🧪 TEST 2: GET /api/v1/vehicles vrací 200

```bash
# Získat token (přihlášením přes UI nebo API)
TOKEN="<token>"

curl -X GET http://127.0.0.1:8000/api/v1/vehicles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -w "\nHTTP Status: %{http_code}\n"
```

**✅ Očekávaný výsledek:**
- HTTP Status: `200`
- JSON response (prázdný list `[]` nebo seznam vozidel)

**❌ Pokud NENÍ 200:**
- Zkontrolovat logy: `sudo journalctl -u toozhub2 | grep VEHICLES`
- Ověřit DB path: `ls -la /opt/toozhub2/data/vehicles.db`

---

## 🧪 TEST 3: Reminders jsou persistentní

### Vytvořit připomínku:
```bash
TOKEN="<token>"

curl -X POST http://127.0.0.1:8000/api/v1/reminders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "VLASTNI",
    "text": "Test připomínka - '$(date +%s)'",
    "due_date": "2025-02-01"
  }' | jq '.id'
```

**Uložit ID:**
```bash
REMINDER_ID=$(curl -s -X POST http://127.0.0.1:8000/api/v1/reminders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "VLASTNI",
    "text": "Test připomínka - '$(date +%s)'",
    "due_date": "2025-02-01"
  }' | jq -r '.id')

echo "Created reminder ID: $REMINDER_ID"
```

### Načíst připomínky:
```bash
curl -X GET http://127.0.0.1:8000/api/v1/reminders \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | select(.id == '$REMINDER_ID')'
```

**✅ Očekávaný výsledek:**
- Připomínka existuje v response
- `id`, `text`, `type` jsou správně

**❌ Pokud připomínka NEEXISTUJE:**
- Zkontrolovat logy: `sudo journalctl -u toozhub2 | grep REMINDERS`
- Ověřit DB: `sqlite3 /opt/toozhub2/data/vehicles.db "SELECT * FROM reminders LIMIT 5;"`

---

## 🧪 TEST 4: ARES Lookup

```bash
curl -X GET http://127.0.0.1:8000/api/v1/ares/27082440 | jq '.company_name'
```

**✅ Očekávaný výsledek:**
- Název firmy (ne null)

---

## 🧪 TEST 5: Frontend VIN

1. Otevřít `https://hub.toozservis.cz/web/index.html`
2. Přihlásit se
3. Jít na "Přidat vozidlo"
4. Zadat VIN: `TMBJF73T2B9044629`
5. Otevřít Developer Console (F12)
6. Sledovat logy `[VIN]`
7. Ověřit, že se vyplní pole: make, model, year, engine, atd.

**✅ Očekávaný výsledek:**
- Console: `[VIN] Filled fields: [make, model, year, ...]`
- UI: Pole jsou vyplněná

---

## 🧪 TEST 6: Frontend IČO

1. Otevřít UI
2. Jít na registraci/přidat vozidlo
3. Zadat IČO: `27082440`
4. Ověřit, že se vyplní: company_name, dic, street, city, zip

**✅ Očekávaný výsledek:**
- Pole jsou vyplněná s daty z ARES

---

## 📋 DEBUG PŘÍKAZY

### Zkontrolovat .env:
```bash
cat /opt/toozhub2/app/.env | grep DATAOVO
```

### Zkontrolovat DB:
```bash
ls -la /opt/toozhub2/data/vehicles.db
sqlite3 /opt/toozhub2/data/vehicles.db ".tables"
```

### Zkontrolovat logy:
```bash
sudo journalctl -u toozhub2 --since "10 minutes ago" | grep -E "MDCR|VEHICLES|REMINDERS"
```

### Zkontrolovat ENV v běžícím procesu:
```bash
sudo systemctl show toozhub2 | grep Environment
```

---

**Dokončeno:** 2025-01-27

