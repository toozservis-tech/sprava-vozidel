# STAVOVÝ REPORT — Správa vozidel (licence a runtime)

## 1) Instance & Git
- Workdir: /opt/toozhub2/app
- Uživatel: toozhub2 (uid 1000, gid 1000)
- Python: /opt/toozhub2/app/.venv/bin/python (Python 3.10.12)
- Git HEAD: 88d4838 (Initial import from macOS)
- Git status: mnoho změněných/nových souborů (backend + web), není čisté.

## 2) Běžící procesy & porty & service
- Proces: /opt/toozhub2/app/.venv/bin/python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000 (aktuálně PID 1451215)
- Port: 127.0.0.1:8000 (LISTEN, fd=7 proces python PID 1451215)
- PID soubor: logs/uvicorn_8000.pid byl v minulosti nesoulad, nyní ruční start přes nohup; systemd neověřen (sudo bez hesla).

## 3) OpenAPI runtime vs offline
- Runtime openapi.json (curl /openapi.json): licence cesty = ["/api/v1/license/status", "/api/v1/license/upgrade"].
- Offline app.openapi(): licence cesty = ["/api/v1/license/status", "/api/v1/license/upgrade"].
- Porovnání: ONLY_OFFLINE/ONLY_RUNTIME = [] po restartu.
- Závěr: po restartu uvicornu runtime OpenAPI obsahuje i /api/v1/license/upgrade.

## 4) Licencování backend
- Router: src/modules/vehicle_hub/routers_v1/license_status.py
  - prefix /license, tag "license"
  - GET /api/v1/license/status (LicenseStatusResponse)
  - POST /api/v1/license/upgrade (admin-only, plan in {free,basic,premium})
- Service: src/modules/licensing/service.py → upgrade_license_plan nastaví plan, status=active, vehicles_limit (free=1, basic=3, premium=0), feature flags dle PLAN_FEATURES.
- Admin pravidlo (upgrade): tenant_id z JWT == TOOZHUB_ADMIN_TENANT_ID nebo role == "admin".
- app.routes (runtime inspekce): /api/v1/license/status (GET), /api/v1/license/upgrade (POST), include_in_schema=True.
- Runtime /openapi.json chybí /upgrade → nutný restart běžícího uvicornu.

## 5) Licencování frontend (token flow, dropdown, modal)
- Token: globální proměnná accessToken, ukládá se do localStorage pod klíčem "accessToken" při loginu (fetch `${apiUrl}/user/login`).
- Dropdown v topbaru: id="licenseQuickToggle" (web/index.html řádky ~2491), bublina id="licenseQuickDropdown"; modal id="licenseModal" (~2591).
- Načítání licence: loadLicenseStatus() (ř. ~4436) volá GET `${apiUrl}/api/v1/license/status` s Authorization: Bearer accessToken; volá se po loginu, při showDashboard a periodicky (startLicenseRefresh, interval 60s, zastavení při logoutu stopLicenseRefresh).
- Render: renderLicenseMenu() (ř. ~4599) aktualizuje dropdown + označí aktuální plán; updateLicenseModal() (ř. ~4694) pro modal; upgradeLicensePlan() (ř. ~4532) volá POST `${apiUrl}/api/v1/license/upgrade` s Bearer tokenem, po úspěchu zavře modal a volá loadLicenseStatus.

## 6) Endpointy – dostupnost
- Bez tokenu: GET /api/v1/license/status → 401 (Not authenticated) [ověřeno curl].
- Bez tokenu: POST /api/v1/license/upgrade → 401 (Unauthorized) [ověřeno curl po restartu]; endpoint je dostupný (není 404).
- Runtime vs offline po restartu jsou stejné (viz bod 3).

## 7) Rizika / duplicity / co restartovat
- Nesoulad PID souboru vs skutečný proces: po posledním restartu port drží PID 1451215, pid soubor může obsahovat jiné PID (nohup pro různé forky). Při dalším restartu sjednotit PID soubor hned po startu.
- Warning při startu: "Vehicle Decoder Engine není dostupný: cannot import name 'decode_vin' ... circular import" (src/modules/vehicle_hub/decoder/router.py). Nutno rozbít cyklus (lazy import decode_vin_local nebo přesun funkce do service vrstvy). 
- Systemd stav neověřen (sudo bez hesla), proces běží ručně na 127.0.0.1:8000.

## 8) Doporučené další kroky (priority)
1) Udržet jeden uvicorn proces: po startu zapsat správné PID (aktuálně 1451215) do logs/uvicorn_8000.pid a ověřit port 8000.
2) Ověřit upgrade endpoint s admin tokenem (curl login → token → POST /api/v1/license/upgrade) a sledovat změnu plánu/limitů.
3) Řešit VIN decoder warning (circular import v src/modules/vehicle_hub/decoder/router.py) – navrhnout lazy import decode_vin_local nebo přesun do samostatné service.

## 9) Krok 8–9 (restart a ověření)
- Restart proveden ručně (kill SIGTERM původního PID, nový nohup uvicorn). Port 8000 nyní drží PID 1451215.
- Runtime /openapi.json obsahuje /api/v1/license/upgrade.
- POST /api/v1/license/upgrade bez tokenu vrací 401 (už ne 404).
- Admin env TOOZHUB_ADMIN_TENANT_ID není nastaven (nenalezeno v .env); sqlite3 klient není k dispozici, nelze z CLI ověřit admin uživatele bez doplnění nástroje nebo SQL klienta.
- POSLEDNÍ OVĚŘENÍ: Port 8000 poslouchá PID 1451215; openapi.json (uloženo do /tmp/openapi_check.json) obsahuje ['/api/v1/license/status', '/api/v1/license/upgrade']; curl GET /api/v1/license/status bez tokenu → 401 Unauthorized (OK).
