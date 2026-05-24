# ✅ MIGRACE DOKONČENA - Oprava licenses.plan

## Shrnutí

**Problém:** `sqlite3.OperationalError: no such column: licenses.plan`

**Řešení:**
1. ✅ Tabulka `licenses` vytvořena s kompletní strukturou (včetně sloupce `plan`)
2. ✅ Fallback ochrana přidána do service funkcí
3. ✅ API vždy vrací validní JSON (nikdy nepadne)

## Změněné soubory

1. `scripts/fix_license_plan_column.py` (NOVÝ)
   - Migrační skript
   - Vytvoří tabulku, pokud neexistuje
   - Přidá sloupec `plan`

2. `src/modules/licensing/service.py`
   - Přidána `_create_fallback_license()`
   - Upravena `get_or_create_license()` s try/except
   - Upravena `get_license_status()` s fallback

3. `src/modules/vehicle_hub/routers_v1/license_status.py`
   - Přidány fieldy: vin_decode_enabled, ares_enabled, reminders_enabled

## Spuštění migrace

```bash
cd /opt/toozhub2/app
/opt/toozhub2/app/.venv/bin/python scripts/fix_license_plan_column.py
```

**Výsledek:**
```
✅ Tabulka 'licenses' vytvořena
✅ Sloupec 'plan' již existuje v tabulce licenses
✅ MIGRACE DOKONČENA
```

## Ověření

Po restartu serveru by mělo být:
- ✅ Backend start bez chyby
- ✅ UI: License: FREE / ACTIVE (ne ERROR)
- ✅ Endpoint `/api/v1/license/status` vrací 200
- ✅ Žádná `sqlite3.OperationalError`

