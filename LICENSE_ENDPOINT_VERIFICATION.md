# Ověření endpointu /api/v1/license/status

## Root Cause

**Status:** ✅ **ENDPOINT FUNGUJE SPRÁVNĚ**

Endpoint `/api/v1/license/status` je správně zaregistrován a vrací správnou odpověď:
- **Bez tokenu:** HTTP 401 Unauthorized (správně, ne 404)
- **V OpenAPI JSON:** Endpoint existuje
- **Router registrace:** Správně zahrnut v `v1_api_router`

**Příčina možného problému:**
- Server nebyl restartovaný po předchozích změnách
- Aktuálně běžící server (PID 1081602) má správnou verzi kódu

---

## Diagnostika běžící instance

### Proces
```
PID: 1081602
Uživatel: toozhub2
Command: /opt/toozhub2/app/.venv/bin/python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
Working directory: /opt/toozhub2/app
Entrypoint: src.server.main:app
```

### Struktura routerů

1. **Main app** (`src/server/main.py`):
   - Registruje `v1_api_router` s prefixem `/api/v1`

2. **V1 API Router** (`src/modules/vehicle_hub/routers_v1/__init__.py`):
   - Prefix: `/api/v1`
   - Zahrnuje: `license_status.router`

3. **License Status Router** (`src/modules/vehicle_hub/routers_v1/license_status.py`):
   - Prefix: `/license`
   - Endpoint: `/status`
   - **Výsledná URL:** `/api/v1` + `/license` + `/status` = `/api/v1/license/status` ✅

---

## Ověření

### 1. Test endpointu (bez tokenu)

```bash
curl -i http://127.0.0.1:8000/api/v1/license/status
```

**Výsledek:**
```
HTTP/1.1 401 Unauthorized
date: Sun, 04 Jan 2026 06:10:34 GMT
server: uvicorn
www-authenticate: Bearer
content-type: application/json

{"detail":"Not authenticated"}
```

✅ **Status:** Správně vrací 401 (ne 404!)

### 2. OpenAPI JSON

```bash
curl -s http://127.0.0.1:8000/openapi.json | grep -n "license/status"
```

**Výsledek:**
- Endpoint `/api/v1/license/status` **existuje** v OpenAPI JSON
- Schema `LicenseStatusResponse` je definováno
- Endpoint má správné security requirements (HTTPBearer)

✅ **Status:** Endpoint je v OpenAPI dokumentaci

### 3. Struktura endpointu v OpenAPI

```json
"/api/v1/license/status": {
  "get": {
    "tags": ["api-v1", "license"],
    "summary": "Get License Status Endpoint",
    "description": "Vrací status licence pro aktuálního uživatele.\n\nReturns:\n    LicenseStatusResponse s informacemi o licenci",
    "operationId": "get_license_status_endpoint_api_v1_license_status_get",
    "responses": {
      "200": {
        "description": "Successful Response",
        "content": {
          "application/json": {
            "schema": {
              "$ref": "#/components/schemas/LicenseStatusResponse"
            }
          }
        }
      }
    },
    "security": [{"HTTPBearer": []}]
  }
}
```

### 4. Response Schema

```json
"LicenseStatusResponse": {
  "properties": {
    "tenant_id": {"type": "string"},
    "plan": {"type": "string"},
    "status": {"type": "string"},
    "vehicles_limit": {"type": "integer"},
    "vehicles_current": {"type": "integer"},
    "vehicles_remaining": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
    "is_unlimited": {"type": "boolean"}
  },
  "required": ["tenant_id", "plan", "status", "vehicles_limit", "vehicles_current", "is_unlimited"],
  "title": "LicenseStatusResponse",
  "description": "Response s informacemi o licenci"
}
```

---

## Logování při startu

Při startu serveru by měly být v logu tyto zprávy:

```
[SERVER] API v1 routery zaregistrovány: /api/v1/
[ROUTERS_V1] ✓ License status router zaregistrován (prefix: /license)
[SERVER] Found license routes in v1_api_router: ['GET /api/v1/license/status']
[SERVER] All license routes in app (after registration): ['GET /api/v1/license/status']
[SERVER] ✓ /api/v1/license/status is registered in app
```

---

## Změněné soubory (už jsou v kódu)

1. **`src/modules/vehicle_hub/routers_v1/license_status.py`**
   - Router s prefixem `/license`
   - Endpoint `/status` s `get_license_status_endpoint`

2. **`src/modules/vehicle_hub/routers_v1/__init__.py`**
   - Zahrnuje `license_status.router` v `v1_api_router`
   - Logování při registraci

3. **`src/server/main.py`**
   - Registruje `v1_api_router` (prefix `/api/v1`)
   - Diagnostické logování license routes

---

## Potvrzení

✅ **Endpoint `/api/v1/license/status` funguje správně:**
- Vrací 401 bez tokenu (ne 404)
- Existuje v OpenAPI JSON
- Router je správně zaregistrován
- Schema je správně definováno

**Pokud endpoint vrací 404:**
1. Ověřte, že server je restartovaný
2. Zkontrolujte logy při startu pro chybové zprávy
3. Ověřte, že `license_status.router` je správně importován

---

## Shrnutí

- **Root cause:** Žádný problém - endpoint funguje
- **URL:** `/api/v1/license/status` ✅
- **Bez tokenu:** 401 Unauthorized ✅
- **V OpenAPI:** Existuje ✅
- **V /docs:** Měl by být viditelný ✅

Endpoint je správně implementovaný a registrován.
