# Stav projektu Správa vozidel – kde jsme skončili a kde pokračovat

**Datum:** 2026-01-25

---

## Kde jsme skončili (co je hotové)

### 1. Produkce a bezpečnost (PRODUCTION_FIX_REPORT.md)
- **CORS** – middleware před rate limitingem, OPTIONS fungují
- **Reset password** – v PROD se `reset_url` nevrací
- **CSP** – povolené `connect-src` pro hub, dataovozidlech.cz, ares.gov.cz
- **VIN/ARES logování** – strukturované logy bez citlivých dat
- **Email service** – lepší error handling (SMTP timeout 30s)
- **Rate limiting** – OPTIONS a `/health` vyjmuty
- **Health** – explicitní OPTIONS handler

### 2. Konfigurace (CONFIG_RECOVERY_REPORT.md)
- **.env** – načítání přes `dotenv`, logování stavu
- **JWT, SMTP, DATAOVO** – klíče v `.env` (včetně DATAOVO_API_KEY)
- **TOOZHUB_ADMIN_TENANT_ID=1** – nastaveno pro upgrade licencí
- **Startup validátor** – `config_validator.py`, log při startu
- **Endpoint** – `GET /health/config` (stav konfigurace bez hodnot)

### 3. Licence (FIX_REPORT.md + implementace)
- **DB tabulka `licenses`** – sloupec `plan` existuje (migrace už proběhla nebo byla DB v pořádku)
- **License status** – `GET /api/v1/license/status` (JWT povinný → 401 bez tokenu)
- **License upgrade** – `POST /api/v1/license/upgrade` (pouze admin tenant nebo role admin)
- **Admin tenant** – tenant_id=1 může měnit plán (free/basic/premium)

### 4. VIN a ARES autofill (hotfix v index.html)
- **VIN** – podle sekce „Přidat nové vozidlo“ + pořadí inputů (bez ID)
- **ARES** – podle sekce „Registrace“ + pořadí inputů
- **MutationObserver** – listenery se připojí i při dynamickém načtení formulářů
- **Debug panel** – sledování requestů (pokud je zapnutý)

### 5. Diagnostika
- **GET /api/_debug/db_stats** – statistiky DB, tenant, vozidla (vyžaduje JWT)
- **GET /api/_debug/routes** – seznam route (pro ověření v produkci)
- **Frontend** – debug logy v `loadVehicles()`, `getApiBaseUrl()` s pravidlem pro hub.toozservis.cz

### 6. UI (tvé poslední úpravy)
- **Container/content** – max-width 1200px, transparentní pozadí
- **Připomínky** – panelový layout, collapsible „Nastavení upozornění“ a „Šablony“
- **Reminder formulář** – payload jen `notification` blok při ukládání nastavení
- **Event listenery** – opravené po cloneNode (save/refresh, toggle šablon)

### 7. Server
- **Restart** – server byl restartován (uvicorn na 127.0.0.1:8000)
- **Health** – vrací 200 OK
- **License bez tokenu** – vrací 401

---

## Kde je potřeba pokračovat (doporučené kroky)

### A. Ověření v produkci (doporučeno)
- [ ] **Health** – `curl -I https://hub.toozservis.cz/health` → 200
- [ ] **Login** – přihlášení z prohlížeče, token se ukládá
- [ ] **Vozidla** – po přihlášení se zobrazují (nebo „žádná vozidla“)
- [ ] **VIN autofill** – na formuláři „Přidat nové vozidlo“ zadat 17 znaků VIN → načtou se make/model/rok/motor (pokud je DATAOVO_API_KEY nastaven)
- [ ] **ARES autofill** – na registraci zadat 8místné IČO → načtou se údaje firmy
- [ ] **License** – v UI licence (FREE/BASIC/PREMIUM), admin může upgrade

### B. Systemd (na serveru)
- Služba `toozhub-server` je **disabled**; server byl spuštěn ručně (`python3 -m uvicorn ...`).
- **Pokud chceš automatický start po rebootu:**
  - `sudo systemctl enable toozhub-server`
  - `sudo systemctl start toozhub-server`
  - Po změnách v kódu nebo `.env`: `sudo systemctl restart toozhub-server`

### C. Volitelné / nízká priorita
- **Command Bot** – v analýze označen jako vypnutý; rozhodnout, zda obnovit nebo odstranit kód
- **Feature flags** – v licensing je TODO (501); doplnit, až bude potřeba dle plánů
- **Dokumentace** – `OPRAVY_SHRNUTI.md` a `ANALYZA_A_NAVRH_RESENI.md` uvádějí ARES/VIN jako „vypnuté“; ve skutečnosti je autofill (hotfix) aktivní – lze v dokumentech upravit

---

## Shrnutí v bodech

| Oblast              | Stav   | Poznámka |
|---------------------|--------|----------|
| Produkce / CORS/CSP | Hotovo | |
| Konfigurace / .env  | Hotovo | včetně admin tenantu |
| Licence (DB + API)   | Hotovo | `plan` v DB, upgrade pro admin |
| VIN/ARES autofill   | Hotovo | podle sekce + pořadí, bez ID |
| Diagnostika         | Hotovo | debug endpointy + frontend logy |
| UI připomínky       | Hotovo | tvoje úpravy |
| Server běží         | Ano    | ruční start uvicorn |
| Systemd             | Nepoužito | enable/start pokud chceš autostart |
| Produkční testy     | Zbývá  | health, login, vozidla, VIN, ARES, licence v prohlížeči |

**Pokračovat:** nejdřív ověření v produkci (A), pak podle potřeby systemd (B) a volitelné úkoly (C).
