# Instrukce pro dokončení migrace licenses.plan

## Problém
Databáze má sloupec `plan_name`, ale model očekává `plan`.

## Řešení

### Krok 1: Změnit vlastníka databáze (vyžaduje sudo)

```bash
sudo chown toozhub2:toozhub2 /opt/toozhub2/app/data/vehicles.db
sudo chmod 664 /opt/toozhub2/app/data/vehicles.db
```

**Nebo použít připravený skript:**
```bash
sudo bash /tmp/fix_db_permissions.sh
```

### Krok 2: Spustit migraci

```bash
cd /opt/toozhub2/app
source .venv/bin/activate
python scripts/migrate_licenses_plan.py
```

**Očekávaný výstup:**
```
✅ Migrace dokončena
```

### Krok 3: Ověřit schema

```bash
python -c "
from sqlalchemy import create_engine, text
engine = create_engine('sqlite:////opt/toozhub2/app/data/vehicles.db')
with engine.connect() as conn:
    result = conn.execute(text('PRAGMA table_info(licenses);'))
    for row in result.fetchall():
        print(f'{row[1]} ({row[2]})')
"
```

**Očekávaný výstup:**
```
id (INTEGER)
tenant_id (INTEGER)
plan (VARCHAR)  ✅
status (VARCHAR)
...
```

### Krok 4: Restart serveru

```bash
sudo systemctl restart toozhub2
```

**Nebo ručně:**
```bash
# Najít PID
ps aux | grep uvicorn

# Zastavit
kill <PID>

# Spustit znovu
cd /opt/toozhub2/app
source .venv/bin/activate
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

### Krok 5: Otestovat endpoint

```bash
# Bez tokenu (očekáváno 401):
curl -i http://127.0.0.1:8000/api/v1/license/status

# S tokenem (očekáváno 200):
TOKEN="<jwt_token>"
curl -i http://127.0.0.1:8000/api/v1/license/status \
  -H "Authorization: Bearer $TOKEN"
```

**Očekávaný výsledek:**
- HTTP 200 s JSON (s tokenem)
- HTTP 401 (bez tokenu)
- **NE** HTTP 500 s `sqlite3.OperationalError`

---

## Ověření v UI

1. Otevřít `https://hub.toozservis.cz/web/index.html`
2. Přihlásit se
3. Ověřit license panel:
   - ✅ "Licence: FREE (active)" (ne "Licence: ERROR")
   - ✅ Console: žádná `sqlite3.OperationalError`

---

## Shrnutí

✅ Migrační skript vytvořen  
✅ Logování DB path přidáno  
⏳ **Čeká na:** Změnu vlastníka DB a spuštění migrace
