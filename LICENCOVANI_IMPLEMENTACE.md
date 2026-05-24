# LICENCOVÁNÍ - IMPLEMENTACE

**Datum:** 2025-01-27

---

## ✅ ZMĚNĚNÉ SOUBORY

### 1. `src/modules/vehicle_hub/models.py`
**Přidáno:** `License` model
- `tenant_id` (unique, indexed)
- `plan_name` (free/pro/admin)
- `status` (active/inactive/trial)
- `vehicles_limit` (0 = unlimited)
- `vin_decode_enabled`, `ares_enabled`, `reminders_enabled`
- `valid_to`, `created_at`, `updated_at`

### 2. `src/modules/licensing/license_service.py` (NOVÝ)
**Funkce:**
- `get_or_create_license()` - získá nebo vytvoří licenci
- `is_unlimited()` - zkontroluje unlimited
- `count_vehicles()` - spočítá vozidla
- `assert_vehicle_quota()` - zkontroluje quota
- `assert_feature()` - zkontroluje feature flag
- `get_license_status()` - získá status

**Admin bypass:**
- Pokud `tenant_id == TOOZHUB_ADMIN_TENANT_ID` → unlimited, všechny features

### 3. `src/modules/vehicle_hub/routers_v1/vehicles.py`
**Opraveno:** `create_vehicle()` endpoint
- ✅ Error handling s JSON response
- ✅ Quota check před vytvořením
- ✅ Duplicate VIN/SPZ detection (409)
- ✅ License quota exceeded (403)
- ✅ Tenant missing (403)
- ✅ Logging: `[VEHICLE_CREATE] tenant_id=... vin=... plate=...`

### 4. `src/modules/vehicle_hub/decoder/router.py`
**Opraveno:** `decode_vin()` endpoint
- ✅ Přidán `current_user` dependency
- ✅ Feature flag check: `assert_feature(db, tenant_id, "vin_decode")`

### 5. `src/modules/vehicle_hub/routers_v1/ares_lookup.py`
**Opraveno:** `lookup_ares()` endpoint
- ✅ Přidán `current_user` dependency
- ✅ Feature flag check: `assert_feature(db, tenant_id, "ares")`

### 6. `src/modules/vehicle_hub/routers_v1/reminders.py`
**Opraveno:** `get_reminders()` a `create_reminder()` endpointy
- ✅ Feature flag check: `assert_feature(db, tenant_id, "reminders")`

### 7. `src/modules/vehicle_hub/routers_v1/license_status.py` (NOVÝ)
**Endpoint:** `GET /api/v1/license/status`
- Vrací informace o licenci pro aktuálního uživatele

### 8. `src/modules/vehicle_hub/routers_v1/__init__.py`
**Přidáno:** `license_status.router`

### 9. `scripts/migrate_add_license_table.py` (NOVÝ)
**Migrace:** Vytvoření License tabulky

---

## 📋 DB ZMĚNY

### Vytvoření License tabulky:
```sql
CREATE TABLE licenses (
    id INTEGER PRIMARY KEY,
    tenant_id INTEGER UNIQUE NOT NULL,
    plan_name VARCHAR NOT NULL DEFAULT 'free',
    status VARCHAR NOT NULL DEFAULT 'active',
    vehicles_limit INTEGER NOT NULL DEFAULT 1,
    vin_decode_enabled BOOLEAN NOT NULL DEFAULT 1,
    ares_enabled BOOLEAN NOT NULL DEFAULT 1,
    reminders_enabled BOOLEAN NOT NULL DEFAULT 1,
    valid_to DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX uq_license_tenant_id ON licenses(tenant_id);
```

**Spuštění migrace:**
```bash
cd /opt/toozhub2/app
python scripts/migrate_add_license_table.py
```

---

## 🔧 ENV PROMĚNNÉ

### Admin bypass:
```bash
TOOZHUB_ADMIN_TENANT_ID=1
```

**Přidat do `/opt/toozhub2/app/.env`:**
```bash
# Admin tenant ID (unlimited quota, všechny features)
TOOZHUB_ADMIN_TENANT_ID=1
```

---

## 🧪 TESTOVÁNÍ

### Test 1: Free tenant - quota limit
```bash
# 1. Vytvořit vozidlo (OK)
curl -X POST http://127.0.0.1:8000/api/v1/vehicles \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "nickname": "Test 1",
    "plate": "ABC 1234",
    "brand": "Test"
  }'

# 2. Pokusit vytvořit 2. vozidlo (403 LICENSE_QUOTA_EXCEEDED)
curl -X POST http://127.0.0.1:8000/api/v1/vehicles \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "nickname": "Test 2",
    "plate": "XYZ 5678",
    "brand": "Test"
  }'
```

**Očekávaný výsledek:**
```json
{
  "error": {
    "code": "LICENSE_QUOTA_EXCEEDED",
    "message": "Byl dosažen limit vozidel pro váš plán. Plán: free, Limit: 1, Aktuálně: 1",
    "details": {
      "plan_name": "free",
      "limit": 1,
      "current": 1,
      "tenant_id": 1
    }
  }
}
```

### Test 2: Duplicate VIN
```bash
curl -X POST http://127.0.0.1:8000/api/v1/vehicles \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "nickname": "Test",
    "plate": "ABC 1234",
    "vin": "TMBJF73T2B9044629",
    "brand": "Test"
  }'

# 2. Pokusit vytvořit stejné VIN (409 VEHICLE_DUPLICATE)
curl -X POST http://127.0.0.1:8000/api/v1/vehicles \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "nickname": "Test 2",
    "plate": "XYZ 5678",
    "vin": "TMBJF73T2B9044629",
    "brand": "Test"
  }'
```

**Očekávaný výsledek:**
```json
{
  "error": {
    "code": "VEHICLE_DUPLICATE",
    "message": "Vozidlo s tímto VIN již existuje",
    "details": {
      "which_field": "vin",
      "value": "TMBJF73T2B9044629"
    }
  }
}
```

### Test 3: Duplicate plate
```bash
# Stejné jako Test 2, ale s plate místo VIN
```

**Očekávaný výsledek:**
```json
{
  "error": {
    "code": "VEHICLE_DUPLICATE",
    "message": "Vozidlo s tímto PLATE již existuje",
    "details": {
      "which_field": "plate",
      "value": "ABC 1234"
    }
  }
}
```

### Test 4: Admin tenant - unlimited
```bash
# Pokud tenant_id == TOOZHUB_ADMIN_TENANT_ID
# Může přidat neomezeně vozidel
```

### Test 5: License status
```bash
curl -X GET http://127.0.0.1:8000/api/v1/license/status \
  -H "Authorization: Bearer <token>"
```

**Očekávaný výsledek:**
```json
{
  "tenant_id": 1,
  "plan_name": "free",
  "status": "active",
  "vehicles_limit": 1,
  "vehicles_current": 1,
  "is_unlimited": false,
  "features": {
    "vin_decode_enabled": true,
    "ares_enabled": true,
    "reminders_enabled": true
  },
  "valid_to": null
}
```

### Test 6: Feature flags
```bash
# Pokud vin_decode_enabled=false:
curl -X POST http://127.0.0.1:8000/api/vehicles/decode-vin \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"vin": "TMBJF73T2B9044629"}'
```

**Očekávaný výsledek:**
```json
{
  "success": false,
  "errors": ["Feature 'vin_decode' není povoleno pro váš plán"]
}
```

---

## 📝 ERROR CODES

| Code | HTTP | Popis |
|------|------|-------|
| `LICENSE_QUOTA_EXCEEDED` | 403 | Byl dosažen limit vozidel |
| `LICENSE_INACTIVE` | 403 | Licence není aktivní |
| `LICENSE_EXPIRED` | 403 | Licence vypršela |
| `VEHICLE_DUPLICATE` | 409 | Duplicitní VIN nebo SPZ |
| `TENANT_MISSING` | 403 | Uživatel nemá tenant_id |
| `FEATURE_DISABLED` | 403 | Feature není povoleno |
| `INTEGRITY_ERROR` | 400 | Obecná DB chyba |

---

## ✅ CHECKLIST

- ✅ License model vytvořen
- ✅ License service implementován
- ✅ Admin bypass (ENV)
- ✅ Quota enforcement v create_vehicle
- ✅ Feature flags v decode-vin, ares, reminders
- ✅ Error handling s JSON response
- ✅ Duplicate detection (VIN/SPZ)
- ✅ Status endpoint
- ✅ Migrace script

---

**Dokončeno:** 2025-01-27

