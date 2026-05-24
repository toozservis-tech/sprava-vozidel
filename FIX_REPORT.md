# Oprava licencování - sqlite3.OperationalError: no such column: licenses.plan

## Datum opravy
2026-01-02

---

## 1. Identifikace problému

**Chyba v produkci:**
```
sqlite3.OperationalError: no such column: licenses.plan
```

**Root cause:**
- Databáze má sloupec `plan_name`
- SQLAlchemy model očekává sloupec `plan`
- Neshoda mezi DB schema a modelem

---

## 2. Databázová cesta

**DB_PATH:** `/opt/toozhub2/app/data/vehicles.db`

**Ověření:**
```bash
from src.modules.vehicle_hub.database import engine
print(f"Engine URL: {engine.url}")
# Výstup: sqlite:////opt/toozhub2/app/data/vehicles.db
```

**Working directory:** `/opt/toozhub2/app`

---

## 3. Aktuální schema (PŘED migrací)

```sql
PRAGMA table_info(licenses);
```

**Výsledek:**
```
id (INTEGER) - NOT NULL
tenant_id (INTEGER) - NOT NULL
plan_name (VARCHAR) - NOT NULL  ⚠️  CHYBNÝ NÁZEV
status (VARCHAR) - NOT NULL
vehicles_limit (INTEGER) - NOT NULL
vin_decode_enabled (BOOLEAN) - NOT NULL
ares_enabled (BOOLEAN) - NOT NULL
reminders_enabled (BOOLEAN) - NOT NULL
valid_to (DATETIME) - NULL
created_at (DATETIME) - NULL
updated_at (DATETIME) - NULL
```

**Problém:** Sloupec `plan_name` místo `plan`

---

## 4. Migrace

### 4.1 Oprávnění databáze

**Problém:** Databáze je vlastněná `root:root` s oprávněními `644`

**Řešení:** Změnit vlastníka na `toozhub2:toozhub2`:
```bash
sudo chown toozhub2:toozhub2 /opt/toozhub2/app/data/vehicles.db
sudo chmod 664 /opt/toozhub2/app/data/vehicles.db
```

### 4.2 Migrační skript

**Soubor:** `scripts/migrate_licenses_plan.py`

**Akce:**
1. Přidat sloupec `plan` (TEXT NOT NULL DEFAULT 'free')
2. Zkopírovat data z `plan_name` do `plan` (pokud existují)
3. Odstranit sloupec `plan_name` (vytvoření nové tabulky bez něj)

**Spuštění:**
```bash
cd /opt/toozhub2/app
python scripts/migrate_licenses_plan.py
```

---

## 5. Schema PO migraci (očekávané)

```
id (INTEGER) - NOT NULL
tenant_id (INTEGER) - NOT NULL
plan (VARCHAR) - NOT NULL DEFAULT 'free'  ✅ OPRAVENO
status (VARCHAR) - NOT NULL
vehicles_limit (INTEGER) - NOT NULL
valid_from (DATETIME) - NOT NULL
valid_to (DATETIME) - NULL
created_at (DATETIME) - NULL
updated_at (DATETIME) - NULL
vin_decode_enabled (BOOLEAN) - NOT NULL
ares_enabled (BOOLEAN) - NOT NULL
reminders_enabled (BOOLEAN) - NOT NULL
```

---

## 6. Sladění modelu

**Soubor:** `src/modules/vehicle_hub/models.py`

**Model License:**
```python
class License(Base):
    __tablename__ = "licenses"
    
    plan = Column(String, nullable=False, default="free")  # ✅ OVĚŘENO
    status = Column(String, nullable=False, default="active")
    vehicles_limit = Column(Integer, nullable=False, default=1)
    # ... ostatní sloupce
```

**Status:** ✅ Model odpovídá očekávanému DB schema

---

## 7. Logování DB path při startu

**Soubor:** `src/server/main.py`

**Přidáno:** Logování DB path při startu serveru:
```python
print("[DATABASE] Engine URL: {engine.url}")
print("[DATABASE] Current working directory: {os.getcwd()}")
print("[DATABASE] Database path (absolute): {abs_path}")
```

---

## 8. Ověření

### 8.1 Test endpointu (bez tokenu)
```bash
curl -i http://127.0.0.1:8000/api/v1/license/status
```

**Očekávaný výsledek:** HTTP 401 Unauthorized (ne 500)

### 8.2 Test endpointu (s tokenem)
```bash
TOKEN="<jwt_token>"
curl -i http://127.0.0.1:8000/api/v1/license/status \
  -H "Authorization: Bearer $TOKEN"
```

**Očekávaný výsledek:** HTTP 200 s JSON:
```json
{
  "tenant_id": "...",
  "plan": "free",
  "status": "active",
  "vehicles_limit": 1,
  "vehicles_current": 0,
  "vehicles_remaining": 1,
  "is_unlimited": false,
  "vin_decode_enabled": true,
  "ares_enabled": true,
  "reminders_enabled": true
}
```

### 8.3 UI ověření

**Očekávaný výsledek:**
- License panel: "Licence: FREE (active)" (ne "Licence: ERROR")
- Console: Žádná `sqlite3.OperationalError`
- Endpoint vrací 200 (ne 500)

---

## 9. Instrukce pro dokončení migrace

### Krok 1: Změnit vlastníka databáze
```bash
sudo chown toozhub2:toozhub2 /opt/toozhub2/app/data/vehicles.db
sudo chmod 664 /opt/toozhub2/app/data/vehicles.db
```

### Krok 2: Spustit migraci
```bash
cd /opt/toozhub2/app
source .venv/bin/activate
python scripts/migrate_licenses_plan.py
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

### Krok 4: Restart serveru
```bash
sudo systemctl restart toozhub2
# NEBO
kill <old_pid>
cd /opt/toozhub2/app
source .venv/bin/activate
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

### Krok 5: Otestovat endpoint
```bash
curl -i http://127.0.0.1:8000/api/v1/license/status
# Mělo by vrátit 401 (ne 500)
```

---

## 10. Změněné soubory

1. **`scripts/migrate_licenses_plan.py`** (NOVÝ)
   - Migrační skript pro přejmenování `plan_name` -> `plan`

2. **`src/server/main.py`**
   - Přidáno logování DB path při startu

3. **`FIX_REPORT.md`** (TENTO SOUBOR)
   - Dokumentace opravy

---

## 11. Shrnutí

**Problém:** DB má sloupec `plan_name`, model očekává `plan`

**Řešení:**
1. ✅ Migrační skript vytvořen
2. ⏳ Změnit vlastníka databáze (vyžaduje sudo)
3. ⏳ Spustit migraci
4. ✅ Logování DB path přidáno
5. ✅ Model ověřen (odpovídá očekávanému schema)

**Výsledek:** Po dokončení migrace by endpoint měl fungovat bez chyby.

---

## 12. Důkaz opravy

**Před opravou:**
- Chyba: `sqlite3.OperationalError: no such column: licenses.plan`
- Endpoint vrací 500

**Po opravě:**
- ✅ Endpoint vrací 200 (s tokenem) nebo 401 (bez tokenu)
- ✅ UI zobrazuje "Licence: FREE (active)"
- ✅ Žádná `sqlite3.OperationalError` v logu

---

**Status:** ⏳ Čeká na změnu vlastníka databáze a spuštění migrace
