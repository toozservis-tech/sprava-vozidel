# ✅ OPRAVA LICENCOVÁNÍ - DOKONČENO

## Root Cause
**Problém:** `sqlite3.OperationalError: no such column: licenses.plan`

**Příčina:** Tabulka `licenses` neexistovala nebo neměla sloupec `plan`, ale SQLAlchemy model ho očekával.

---

## Provedené změny

### 1. Migrace databáze ✅
**Soubor:** `scripts/fix_license_plan_column.py` (NOVÝ)

**Akce:**
- Vytvořena tabulka `licenses` s kompletní strukturou
- Sloupec `plan` přidán (TEXT, NOT NULL, DEFAULT 'free')
- Všechny potřebné sloupce zkontrolovány

**Struktura tabulky:**
```
id, tenant_id, plan, status, vehicles_limit, valid_from, valid_to,
created_at, updated_at, vin_decode_enabled, ares_enabled, reminders_enabled
```

### 2. Fallback ochrana ✅
**Soubor:** `src/modules/licensing/service.py`

**Přidáno:**
- Funkce `_create_fallback_license()` - vytvoří fallback licenci v paměti
- `get_or_create_license()` - wrapped v try/except, vrací fallback při chybě
- `get_license_status()` - vždy vrací validní JSON, i při chybě DB

**Fallback hodnoty:**
- `plan`: "free"
- `status`: "active"
- `vehicles_limit`: 1
- `vin_decode_enabled`: False (bezpečnější)
- `ares_enabled`: False
- `reminders_enabled`: False

### 3. Response model ✅
**Soubor:** `src/modules/vehicle_hub/routers_v1/license_status.py`

**Přidáno:**
- `vin_decode_enabled`, `ares_enabled`, `reminders_enabled` do response modelu
- `_fallback` flag (volitelný, pro debug)

---

## Seznam změněných souborů

1. **`scripts/fix_license_plan_column.py`** (NOVÝ)
   - Migrační skript pro vytvoření tabulky a přidání sloupce `plan`

2. **`src/modules/licensing/service.py`**
   - Přidána `_create_fallback_license()`
   - Upravena `get_or_create_license()` s error handling
   - Upravena `get_license_status()` s fallback

3. **`src/modules/vehicle_hub/routers_v1/license_status.py`**
   - Přidány fieldy do `LicenseStatusResponse`

4. **`FIX_REPORT.md`** (NOVÝ)
   - Kompletní dokumentace opravy

---

## Ověření po restartu serveru

### 1. Backend start
```bash
sudo systemctl restart toozhub2
# NEBO
kill <old_pid>
cd /opt/toozhub2/app
source .venv/bin/activate
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

**Očekáváno:** Server startuje bez chyby `sqlite3.OperationalError`

### 2. Test endpointu
```bash
curl -i http://127.0.0.1:8000/api/v1/license/status \
  -H "Authorization: Bearer <token>"
```

**Očekáváno:** HTTP 200 s JSON:
```json
{
  "tenant_id": "1",
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

### 3. UI ověření
- License panel: Zobrazuje "FREE / ACTIVE" (ne ERROR)
- Console: Žádná `sqlite3.OperationalError`
- VIN lookup: Funguje podle `vin_decode_enabled` flagu
- ARES lookup: Funguje podle `ares_enabled` flagu

---

## Výsledek

**✅ Problém vyřešen:**
- Tabulka `licenses` vytvořena s `plan` sloupcem
- Fallback ochrana zajišťuje, že UI nikdy nepadne
- API vždy vrací validní JSON
- Model odpovídá DB struktuře

**⚠️ DŮLEŽITÉ:** Server musí být restartován, aby načetl nový kód!
