# Ověření endpointu /api/v1/license/status

## Root Cause
**Problém:** Duplicitní registrace licensing routerů způsobovala konflikt.
- `license_status.router` v `vehicle_hub/routers_v1/` je správně zahrnut v `v1_api_router` (prefix `/api/v1`)
- `licensing_router` v `licensing/router.py` měl stejný prefix `/api/v1` a byl registrován samostatně

**Řešení:**
- Odstraněna duplicitní registrace `licensing_router` z `main.py`
- Smazán nepotřebný soubor `src/modules/licensing/router.py`
- Použit pouze `license_status.router`, který je zahrnut v `v1_api_router`

**Výsledná cesta:**
- `v1_api_router` prefix: `/api/v1`
- `license_status.router` prefix: `/license`
- Endpoint: `/status`
- **Finální URL:** `/api/v1/license/status` ✅

## Ověření po restartu

### 1. Bez JWT tokenu (musí vrátit 401, ne 404)
```bash
curl -i http://127.0.0.1:8000/api/v1/license/status
```

**Očekávaný výsledek:**
```
HTTP/1.1 401 Unauthorized
...
{"detail":"Not authenticated"}
```

### 2. V OpenAPI JSON (musí obsahovat license/status)
```bash
curl -s http://127.0.0.1:8000/openapi.json | grep -A 5 "license/status"
```

**Očekávaný výsledek:**
- Najde výskyt "license/status" v JSON

### 3. S JWT tokenem (musí vrátit 200 a JSON)
```bash
TOKEN="<váš_jwt_token>"
curl -i http://127.0.0.1:8000/api/v1/license/status \
  -H "Authorization: Bearer $TOKEN"
```

**Očekávaný výsledek:**
```
HTTP/1.1 200 OK
...
{
  "tenant_id": "1",
  "plan": "free",
  "status": "active",
  "vehicles_limit": 1,
  "vehicles_current": 0,
  "vehicles_remaining": 1,
  "is_unlimited": false
}
```

### 4. Kontrola v server logu při startu
Při startu serveru by měl být vidět:
```
=== LICENSE ROUTES VERIFICATION ===
Found X license route(s):
  GET     /api/v1/license/status
✓ /api/v1/license/status endpoint is registered
```

## Změněné soubory
1. `src/server/main.py`
   - Odstraněna duplicitní registrace `licensing_router`
   - Přidáno logování pro ověření license routes
   - Přidán `/api/v1/license/status` do critical routes

2. `src/modules/licensing/router.py` - **SMAZÁN** (nepoužívaný duplicitní router)

## Funkční router
- `src/modules/vehicle_hub/routers_v1/license_status.py`
- Zahrnut v `src/modules/vehicle_hub/routers_v1/__init__.py` (řádek 24)
- Registrován přes `v1_api_router` v `main.py` (řádek 183)
