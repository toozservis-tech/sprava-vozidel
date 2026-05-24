# Konfigurace funkcí podle licenčních plánů

## Přehled plánů a jejich funkcí

### FREE (Zdarma)
- **Vozidla:** 1 vozidlo
- **VIN dekódování:** ❌ Ne
- **ARES lookup:** ❌ Ne
- **Připomínky:** ❌ Ne

### BASIC
- **Vozidla:** 3 vozidla
- **VIN dekódování:** ❌ Ne
- **ARES lookup:** ✅ Ano
- **Připomínky:** ✅ Ano

### PREMIUM
- **Vozidla:** Neomezeně
- **VIN dekódování:** ✅ Ano
- **ARES lookup:** ✅ Ano
- **Připomínky:** ✅ Ano

---

## Implementace

### 1. Mapování funkcí (`src/modules/licensing/service.py`)

```python
PLAN_FEATURES = {
    "free": {
        "vin_decode_enabled": False,
        "ares_enabled": False,
        "reminders_enabled": False
    },
    "basic": {
        "vin_decode_enabled": False,
        "ares_enabled": True,
        "reminders_enabled": True
    },
    "premium": {
        "vin_decode_enabled": True,
        "ares_enabled": True,
        "reminders_enabled": True
    }
}
```

### 2. Automatická aktualizace existujících licencí

Funkce `get_or_create_license()` automaticky:
- Kontroluje, zda existující licence má správné funkce podle plánu
- Aktualizuje funkce, pokud se liší od očekávaných hodnot
- Aktualizuje limit vozidel podle plánu

### 3. Kontrola funkcí v endpointech

Funkce `assert_feature()` se používá v:
- `/api/vehicles/decode-vin` - kontrola `vin_decode`
- `/api/v1/ares/lookup` - kontrola `ares`
- `/api/v1/reminders` - kontrola `reminders`

### 4. API Response

Endpoint `/api/v1/license/status` vrací:
```json
{
  "tenant_id": "1",
  "plan": "free",
  "status": "active",
  "vehicles_limit": 1,
  "vehicles_current": 2,
  "vehicles_remaining": 0,
  "is_unlimited": false,
  "vin_decode_enabled": false,
  "ares_enabled": false,
  "reminders_enabled": false
}
```

---

## Změna plánu

Při změně plánu (např. z FREE na BASIC):
1. Upravte `plan` v databázi na nový plán
2. Při dalším volání `get_or_create_license()` se automaticky:
   - Aktualizují funkce podle nového plánu
   - Aktualizuje limit vozidel

**Příklad SQL:**
```sql
UPDATE licenses SET plan = 'basic' WHERE tenant_id = 1;
```

---

## Testování

### Test FREE plánu:
```bash
# FREE by měl mít všechny funkce zakázané
curl -H "Authorization: Bearer <token>" \
  http://127.0.0.1:8000/api/v1/license/status

# Očekávaný výsledek:
# "vin_decode_enabled": false
# "ares_enabled": false
# "reminders_enabled": false
```

### Test BASIC plánu:
```bash
# BASIC by měl mít ARES a reminders povolené
# "vin_decode_enabled": false
# "ares_enabled": true
# "reminders_enabled": true
```

### Test PREMIUM plánu:
```bash
# PREMIUM by měl mít všechny funkce povolené
# "vin_decode_enabled": true
# "ares_enabled": true
# "reminders_enabled": true
```

---

## Admin Bypass

Pokud je `TOOZHUB_ADMIN_TENANT_ID` nastaveno v ENV, tenant s tímto ID automaticky:
- Má `plan = "premium"`
- Má všechny funkce povolené (`vin_decode_enabled`, `ares_enabled`, `reminders_enabled = True`)
- Má `vehicles_limit = 0` (unlimited)
