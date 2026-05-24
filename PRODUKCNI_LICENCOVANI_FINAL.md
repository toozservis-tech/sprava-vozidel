# PRODUKČNÍ LICENCOVÁNÍ - FINÁLNÍ IMPLEMENTACE

**Datum:** 2025-01-27

---

## ✅ ZMĚNĚNÉ SOUBORY

1. ✅ `src/modules/vehicle_hub/models.py` - License model (plan, status, vehicles_limit, valid_from, valid_to)
2. ✅ `src/modules/licensing/service.py` - License service (get_or_create_license, assert_vehicle_quota, LicenseError)
3. ✅ `src/modules/vehicle_hub/routers_v1/vehicles.py` - Enforcement v create_vehicle
4. ✅ `src/modules/vehicle_hub/routers_v1/license_status.py` - Status endpoint
5. ✅ `scripts/migrate_add_license_table.py` - Migrace script

---

## 📋 DB MODEL: LICENSES

```python
class License(Base):
    __tablename__ = "licenses"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), unique=True, nullable=False, index=True)
    
    plan = Column(String, nullable=False, default="free")  # "free", "basic", "premium"
    status = Column(String, nullable=False, default="active")  # "active", "inactive"
    vehicles_limit = Column(Integer, nullable=False, default=1)  # free=1, basic=3, premium=0
    
    valid_from = Column(DateTime, nullable=False, default=datetime.utcnow)
    valid_to = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

**Výchozí chování:**
- Pokud licence pro tenant_id neexistuje → vytvoří se automaticky:
  - `plan="free"`
  - `status="active"`
  - `vehicles_limit=1`

---

## 🔧 LICENSE SERVICE

### LicenseError
```python
class LicenseError(HTTPException):
    def __init__(self, code: str, message: str, details: dict = None, status_code: int = 403):
        self.code = code
        self.details = details or {}
        super().__init__(status_code=status_code, detail=message)
```

### Funkce
- `get_or_create_license(db, tenant_id)` - získá nebo vytvoří free licenci
- `get_vehicle_count(db, tenant_id)` - spočítá vozidla pro tenant_id
- `is_unlimited(license)` - zkontroluje unlimited (vehicles_limit == 0)
- `assert_vehicle_quota(db, tenant_id)` - zkontroluje quota, vyhodí LicenseError

---

## 🚀 ENFORCEMENT

### POST /api/v1/vehicles
```python
# PŘED vložením do DB:
from ...licensing.service import assert_vehicle_quota, LicenseError

try:
    assert_vehicle_quota(db, tenant_id)
except LicenseError as e:
    return JSONResponse(
        status_code=e.status_code,
        content={
            "error": {
                "code": e.code,
                "message": e.detail,
                "details": e.details
            }
        }
    )
```

**Chování:**
- free + 1 vozidlo → OK
- free + 2. vozidlo → 403 LICENSE_QUOTA_EXCEEDED
- basic + 3 vozidla → OK
- basic + 4. vozidlo → 403
- premium → vždy OK (unlimited)

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

**ŽÁDNÉ:**
- ❌ silent fail
- ❌ prázdná response
- ❌ generic 500

---

## 🧪 TESTOVÁNÍ

### Test 1: Free tenant
```bash
# 1. Vytvořit 1. vozidlo (OK)
curl -X POST http://127.0.0.1:8000/api/v1/vehicles \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"nickname": "Test 1", "plate": "ABC 1234", "brand": "Test"}'

# 2. Pokusit vytvořit 2. vozidlo (403)
curl -X POST http://127.0.0.1:8000/api/v1/vehicles \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"nickname": "Test 2", "plate": "XYZ 5678", "brand": "Test"}'
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

### Test 2: Basic tenant
**Nastavit v DB:**
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

### Test 3: Premium tenant
**Nastavit v DB:**
```sql
UPDATE licenses SET plan='premium', vehicles_limit=0 WHERE tenant_id=<tenant_id>;
```

```bash
# Může přidat libovolný počet vozidel (vše OK)
```

### Test 4: License status
```bash
curl -X GET http://127.0.0.1:8000/api/v1/license/status \
  -H "Authorization: Bearer <token>"
```

**Očekávaný výsledek (free):**
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

**Očekávaný výsledek (premium):**
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

---

## 🔧 ADMIN BYPASS

**ENV proměnná:**
```bash
TOOZHUB_ADMIN_TENANT_ID=1
```

**Chování:**
- Pokud `tenant_id == TOOZHUB_ADMIN_TENANT_ID`:
  - `plan = "premium"`
  - `vehicles_limit = 0` (unlimited)
  - Bypass `valid_to`

---

## 📋 MIGRACE

**Spuštění:**
```bash
cd /opt/toozhub2/app
python scripts/migrate_add_license_table.py
```

**Vytvoří:**
- Tabulku `licenses`
- Unique index na `tenant_id`

**Backward compatibility:**
- Stávající vozidla zůstávají
- Licence se vytvoří při prvním requestu
- Nic se nemaže

---

## ✅ DŮKAZ FUNKČNOSTI

Po implementaci:
1. ✅ Free tenant může přidat 1 vozidlo
2. ✅ Free tenant NEMŮŽE přidat 2. vozidlo (403)
3. ✅ Basic tenant může přidat 3 vozidla
4. ✅ Basic tenant NEMŮŽE přidat 4. vozidlo (403)
5. ✅ Premium tenant může přidat neomezeně vozidel
6. ✅ Status endpoint vrací správné informace
7. ✅ Error response má standardizovaný formát

---

**Dokončeno:** 2025-01-27

