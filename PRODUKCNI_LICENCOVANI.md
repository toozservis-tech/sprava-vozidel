# PRODUKČNÍ LICENCOVÁNÍ - IMPLEMENTACE

**Datum:** 2025-01-27

---

## ✅ ZMĚNĚNÉ SOUBORY

### 1. `src/modules/vehicle_hub/models.py`
**License model:**
- `plan` (string) - "free", "basic", "premium"
- `status` (string) - "active", "inactive"
- `vehicles_limit` (int) - free=1, basic=3, premium=0 (0 = unlimited)
- `valid_from` (datetime)
- `valid_to` (datetime, nullable)
- `created_at`, `updated_at`

### 2. `src/modules/licensing/service.py` (NOVÝ)
**Funkce:**
- `get_or_create_license(db, tenant_id)` - získá nebo vytvoří free licenci
- `get_vehicle_count(db, tenant_id)` - spočítá vozidla
- `is_unlimited(license)` - zkontroluje unlimited (limit == 0)
- `assert_vehicle_quota(db, tenant_id)` - zkontroluje quota, vyhodí LicenseError
- `get_license_status(db, tenant_id)` - získá status

**LicenseError:**
```python
class LicenseError(HTTPException):
    def __init__(self, code: str, message: str, details: dict = None, status_code: int = 403):
        self.code = code
        self.details = details or {}
        super().__init__(status_code=status_code, detail=message)
```

### 3. `src/modules/vehicle_hub/routers_v1/vehicles.py`
**Enforcement:**
- Před vložením do DB: `assert_vehicle_quota(db, tenant_id)`
- Error handling s JSON response

### 4. `src/modules/vehicle_hub/routers_v1/license_status.py`
**Endpoint:** `GET /api/v1/license/status`
- Vrací status licence pro aktuálního uživatele

### 5. `scripts/migrate_add_license_table.py`
**Migrace:** Vytvoření License tabulky

---

## 📋 DB ZMĚNY

### Tabulka `licenses`:
```sql
CREATE TABLE licenses (
    id INTEGER PRIMARY KEY,
    tenant_id INTEGER UNIQUE NOT NULL,
    plan VARCHAR NOT NULL DEFAULT 'free',
    status VARCHAR NOT NULL DEFAULT 'active',
    vehicles_limit INTEGER NOT NULL DEFAULT 1,
    valid_from DATETIME NOT NULL,
    valid_to DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    vin_decode_enabled BOOLEAN NOT NULL DEFAULT 1,
    ares_enabled BOOLEAN NOT NULL DEFAULT 1,
    reminders_enabled BOOLEAN NOT NULL DEFAULT 1
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
# Admin tenant ID (premium plan, unlimited quota)
TOOZHUB_ADMIN_TENANT_ID=1
```

---

## 🧪 TESTOVÁNÍ

### Test 1: Free tenant - 1 vozidlo OK, 2. vozidlo => 403

```bash
# 1. Vytvořit 1. vozidlo (OK)
TOKEN="<token>"
curl -X POST http://127.0.0.1:8000/api/v1/vehicles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "nickname": "Test 1",
    "plate": "ABC 1234",
    "brand": "Test"
  }'

# 2. Pokusit vytvořit 2. vozidlo (403 LICENSE_QUOTA_EXCEEDED)
curl -X POST http://127.0.0.1:8000/api/v1/vehicles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "nickname": "Test 2",
    "plate": "XYZ 5678",
    "brand": "Test"
  }'
```

**Očekávaný výsledek (2. vozidlo):**
```json
HTTP 403
{
  "error": {
    "code": "LICENSE_QUOTA_EXCEEDED",
    "message": "Limit vozidel překročen (1/1)",
    "details": {
      "plan": "free",
      "limit": 1,
      "current": 1
    }
  }
}
```

### Test 2: Basic tenant - 3 vozidla OK, 4. vozidlo => 403

**Předpoklad:** Nastavit tenant_id na basic plán v DB:
```sql
UPDATE licenses SET plan='basic', vehicles_limit=3 WHERE tenant_id=<tenant_id>;
```

```bash
# 1-3. Vytvořit 3 vozidla (OK)
# 4. Pokusit vytvořit 4. vozidlo (403)
```

**Očekávaný výsledek (4. vozidlo):**
```json
HTTP 403
{
  "error": {
    "code": "LICENSE_QUOTA_EXCEEDED",
    "message": "Limit vozidel překročen (3/3)",
    "details": {
      "plan": "basic",
      "limit": 3,
      "current": 3
    }
  }
}
```

### Test 3: Premium tenant - unlimited

**Předpoklad:** Nastavit tenant_id na premium plán v DB:
```sql
UPDATE licenses SET plan='premium', vehicles_limit=0 WHERE tenant_id=<tenant_id>;
```

```bash
# Může přidat libovolný počet vozidel (vše OK)
```

### Test 4: License status endpoint

```bash
curl -X GET http://127.0.0.1:8000/api/v1/license/status \
  -H "Authorization: Bearer $TOKEN"
```

**Očekávaný výsledek:**
```json
{
  "tenant_id": "1",
  "plan": "free",
  "status": "active",
  "vehicles_limit": 1,
  "vehicles_current": 1,
  "vehicles_remaining": 0,
  "is_unlimited": false
}
```

**Pro premium:**
```json
{
  "tenant_id": "1",
  "plan": "premium",
  "status": "active",
  "vehicles_limit": 0,
  "vehicles_current": 5,
  "vehicles_remaining": null,
  "is_unlimited": true
}
```

### Test 5: Admin bypass

**Předpoklad:** `TOOZHUB_ADMIN_TENANT_ID=1` v ENV

```bash
# Admin tenant může přidat neomezeně vozidel
# Automaticky má plan=premium, vehicles_limit=0
```

---

## 📝 ERROR RESPONSE FORMAT

Všechny licenční chyby vrací standardizovaný JSON:

```json
HTTP 403
{
  "error": {
    "code": "LICENSE_QUOTA_EXCEEDED",
    "message": "Limit vozidel překročen (3/3)",
    "details": {
      "plan": "basic",
      "limit": 3,
      "current": 3
    }
  }
}
```

**Error codes:**
- `LICENSE_QUOTA_EXCEEDED` (403) - limit vozidel překročen
- `LICENSE_INACTIVE` (403) - licence není aktivní
- `LICENSE_EXPIRED` (403) - licence vypršela

---

## ✅ CHECKLIST

- ✅ License model s `plan`, `status`, `vehicles_limit`, `valid_from`, `valid_to`
- ✅ `get_or_create_license()` - vytvoří free licenci pokud neexistuje
- ✅ `get_vehicle_count()` - spočítá vozidla
- ✅ `is_unlimited()` - zkontroluje unlimited
- ✅ `assert_vehicle_quota()` - zkontroluje quota, vyhodí LicenseError
- ✅ Enforcement v `POST /api/v1/vehicles`
- ✅ Standardizovaná error response
- ✅ Status endpoint `GET /api/v1/license/status`
- ✅ Admin bypass (ENV)
- ✅ Migrace script

---

## 🎯 PLÁNY A LIMITY

| Plán | vehicles_limit | Popis |
|------|----------------|-------|
| `free` | 1 | Max 1 vozidlo |
| `basic` | 3 | Max 3 vozidla |
| `premium` | 0 | Unlimited (0 = neomezeně) |

**Výchozí chování:**
- Pokud licence pro tenant_id neexistuje → vytvoří se automaticky `free` licenci
- `plan="free"`, `status="active"`, `vehicles_limit=1`

---

**Dokončeno:** 2025-01-27

