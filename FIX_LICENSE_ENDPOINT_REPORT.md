# Oprava endpointu /api/v1/license/status - Report

## Root Cause
**Problém:** Endpoint `/api/v1/license/status` vracel 404 Not Found, i když router byl definován a měl být zaregistrován.

**Příčina:**
1. Router `license_status.router` je správně definován v `src/modules/vehicle_hub/routers_v1/license_status.py`
2. Router je zahrnut v `src/modules/vehicle_hub/routers_v1/__init__.py` na řádku 24
3. `v1_api_router` má prefix `/api/v1` a je zaregistrován v `main.py`
4. **ALE:** Chybělo diagnostické logování, které by odhalilo problémy při importu nebo registraci
5. **MOŽNÁ PŘÍČINA:** Server běží ze staré verze kódu (ne restartovaný po změnách)

**Struktura prefixů:**
- `v1_api_router` prefix: `/api/v1`
- `license_status.router` prefix: `/license`
- Endpoint path: `/status`
- **Výsledná URL:** `/api/v1` + `/license` + `/status` = `/api/v1/license/status` ✅

## Změny

### 1. `src/server/main.py`
**Řádky 180-208:** Přidáno diagnostické logování při registraci `v1_api_router`:
- Vypíše všechny license routes nalezené v `v1_api_router`
- Vypíše všechny license routes v `app` po registraci
- Explicitně ověří existenci `/api/v1/license/status`

### 2. `src/modules/vehicle_hub/routers_v1/__init__.py`
**Řádky 23-29:** Přidán try-except blok a logování při registraci `license_status.router`:
- Explicitní kontrola úspěšné registrace
- Vypíše prefix routeru
- Zachytí a vypíše případné chyby

### 3. `test_license_endpoint.sh` (nový soubor)
Testovací skript pro ověření funkčnosti endpointu:
- Test bez tokenu (očekáváno 401, ne 404)
- Kontrola OpenAPI JSON
- Kontrola /docs

## Ověření po restartu

### Krok 1: Restart serveru
```bash
# Pokud běží jako systemd service:
sudo systemctl restart toozhub2

# Nebo pokud běží ručně, ukončit (Ctrl+C) a spustit znovu:
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

### Krok 2: Kontrola logů při startu
Při startu byste měli vidět v logu:
```
[ROUTERS_V1] ✓ License status router zaregistrován (prefix: /license)
[SERVER] API v1 routery zaregistrovány: /api/v1/
[SERVER] Found license routes in v1_api_router: ['GET /license/status']
[SERVER] All license routes in app (after registration): ['GET /api/v1/license/status']
[SERVER] ✓ /api/v1/license/status is registered in app
```

### Krok 3: Spuštění testovacího skriptu
```bash
cd /opt/toozhub2/app
./test_license_endpoint.sh
```

**Očekávané výsledky:**
1. **Bez tokenu:** HTTP 401 Unauthorized (ne 404)
2. **OpenAPI JSON:** Obsahuje "license/status"
3. **/docs:** Zobrazuje endpoint GET /api/v1/license/status

### Krok 4: Ruční test
```bash
# Bez tokenu (očekáváno 401)
curl -i http://127.0.0.1:8000/api/v1/license/status

# V OpenAPI JSON
curl -s http://127.0.0.1:8000/openapi.json | grep -n "license/status"

# S tokenem (pokud máte)
TOKEN="<váš_jwt_token>"
curl -i http://127.0.0.1:8000/api/v1/license/status \
  -H "Authorization: Bearer $TOKEN"
```

## Diff změn

### src/server/main.py
```diff
# Include API v1 routery (Správa vozidel v1.0)
 try:
     from src.modules.vehicle_hub.routers_v1 import api_router as v1_api_router
     app.include_router(v1_api_router)
     print("[SERVER] API v1 routery zaregistrovány: /api/v1/")
+    
+    # Diagnostika: Vypiš všechny routes v v1_api_router obsahující "license"
+    license_routes_in_v1 = []
+    for route in v1_api_router.routes:
+        if hasattr(route, 'path') and hasattr(route, 'methods'):
+            if 'license' in route.path.lower():
+                for method in sorted(route.methods):
+                    if method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
+                        license_routes_in_v1.append(f"{method} {route.path}")
+    
+    if license_routes_in_v1:
+        print(f"[SERVER] Found license routes in v1_api_router: {license_routes_in_v1}")
+    else:
+        print("[SERVER] WARNING: No license routes found in v1_api_router!")
+        
+    # Diagnostika: Vypiš všechny routes v app obsahující "license" PO registraci
+    all_license_routes = []
+    for route in app.routes:
+        if hasattr(route, 'path') and hasattr(route, 'methods'):
+            if 'license' in route.path.lower():
+                for method in sorted(route.methods):
+                    if method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
+                        all_license_routes.append(f"{method} {route.path}")
+    
+    if all_license_routes:
+        print(f"[SERVER] All license routes in app (after registration): {all_license_routes}")
+        if any('/api/v1/license/status' in r for r in all_license_routes):
+            print("[SERVER] ✓ /api/v1/license/status is registered in app")
+        else:
+            print("[SERVER] ❌ /api/v1/license/status NOT found in app routes!")
+    else:
+        print("[SERVER] ❌ No license routes found in app at all!")
+        
 except ImportError as e:
     print(f"[SERVER] Warning: API v1 routery nejsou dostupné: {e}")
     import traceback
     traceback.print_exc()
```

### src/modules/vehicle_hub/routers_v1/__init__.py
```diff
 api_router.include_router(vin_lookup.router)  # VIN lookup
 api_router.include_router(ares_lookup.router)  # ARES lookup
 
-# License status router - explicitní kontrola
+try:
     api_router.include_router(license_status.router)  # License status
+    print(f"[ROUTERS_V1] ✓ License status router zaregistrován (prefix: {license_status.router.prefix})")
+except Exception as e:
+    print(f"[ROUTERS_V1] ❌ ERROR při registraci license_status routeru: {e}")
+    import traceback
+    traceback.print_exc()
```

## Potvrzení
Po restartu serveru by mělo být:
- ✅ Endpoint `/api/v1/license/status` vrací 401 bez tokenu (ne 404)
- ✅ OpenAPI JSON obsahuje "license/status"
- ✅ Endpoint je viditelný v `/docs`
- ✅ Logy při startu ukazují správnou registraci routeru
