# QA Report - Správa vozidel

**Datum:** 2025-01-27  
**Verze:** 2.2.0  
**Tester:** Automated QA System

## Přehled

Tento dokument popisuje QA infrastrukturu vytvořenou pro Správa vozidel, včetně testovacích scénářů, nalezených bugů a jejich oprav.

## Testovací infrastruktura

### 1. E2E testy (Playwright)

**Lokace:** `tests/e2e/`

**Konfigurace:**

- Base URL: `http://127.0.0.1:8000`
- Start page: `/web/index.html`
- Reporty: `artifacts/qa/playwright-report/`

**Testovací soubory:**

- `auth.spec.ts` - Autentizace (login, registrace, logout)
- `vehicles.spec.ts` - Správa vozidel (CRUD operace)
- `navigation.spec.ts` - Navigace mezi sekcemi
- `reminders.spec.ts` - Připomínky
- `reservations.spec.ts` - Rezervace
- `profile.spec.ts` - Uživatelský profil
- `mobile.spec.ts` - Mobilní zobrazení (iPhone 12)
- `error-handling.spec.ts` - Zpracování chyb

**Pokrytí UI sekcí:**

| Sekce | Testy | Status |
|-------|-------|--------|
| Přihlášení | auth.spec.ts | ✅ |
| Registrace | auth.spec.ts | ✅ |
| Vozidla | vehicles.spec.ts | ✅ |
| Přidat vozidlo | vehicles.spec.ts | ✅ |
| Připomínky | reminders.spec.ts | ✅ |
| Rezervace | reservations.spec.ts | ✅ |
| Profil | profile.spec.ts | ✅ |
| Navigace | navigation.spec.ts | ✅ |
| Mobilní zobrazení | mobile.spec.ts | ✅ |
| Error handling | error-handling.spec.ts | ✅ |

### 2. API testy (pytest)

**Lokace:** `tests/api/`

**Testovací soubory:**

- `test_health.py` - Health check endpointy
- `test_auth.py` - Autentizace API
- `test_vehicles.py` - Vehicles API (CRUD)

**Pokrytí API endpointů:**

| Endpoint | Test | Status |
|----------|------|--------|
| `GET /health` | test_health.py | ✅ |
| `GET /` | test_health.py | ✅ |
| `GET /version` | test_health.py | ✅ |
| `POST /user/register` | test_auth.py | ✅ |
| `POST /user/login` | test_auth.py | ✅ |
| `GET /user/me` | test_auth.py | ✅ |
| `GET /api/v1/vehicles` | test_vehicles.py | ✅ |
| `POST /api/v1/vehicles` | test_vehicles.py | ✅ |
| `GET /api/v1/vehicles/{id}` | test_vehicles.py | ✅ |
| `PUT /api/v1/vehicles/{id}` | test_vehicles.py | ✅ |
| `DELETE /api/v1/vehicles/{id}` | test_vehicles.py | ✅ |

## Data-testid atributy

Pro stabilní E2E testy byly přidány `data-testid` atributy do UI:

**Přihlášení:**

- `data-testid="login-form"`
- `data-testid="input-email"`
- `data-testid="input-password"`
- `data-testid="btn-login"`
- `data-testid="btn-show-register"`

**Registrace:**

- `data-testid="register-form"`
- `data-testid="input-reg-email"`
- `data-testid="input-reg-password"`
- `data-testid="btn-register"`

**Navigace:**

- `data-testid="dashboard"`
- `data-testid="tab-vehicles"`
- `data-testid="tab-add-vehicle"`
- `data-testid="tab-reminders"`
- `data-testid="tab-reservations"`
- `data-testid="tab-profile"`

**Vozidla:**

- `data-testid="vehicles-container"`
- `data-testid="vehicle-card"`
- `data-testid="add-vehicle-form"`
- `data-testid="input-vehicle-name"`
- `data-testid="input-vehicle-plate"`
- `data-testid="btn-add-vehicle"`
- `data-testid="vehicle-detail-modal"`

**Alerty:**

- `data-testid="alert-success"`
- `data-testid="alert-error"`
- `data-testid="alert-info"`

## Instalace závislostí

**Před prvním spuštěním:**

```powershell
# 1. Nainstalovat Python závislosti (včetně pytest)
pip install -r requirements.txt

# 2. Nainstalovat Node.js závislosti pro E2E testy
cd tests/e2e
npm install
npx playwright install chromium
cd ../..
```

## Spuštění QA testů

### Jednoduché spuštění (doporučeno)

```powershell
# V root projektu
.\scripts\qa_run.ps1
```

Tento skript:

1. Spustí backend server na portu 8000
2. Počká na připravenost serveru (`/health`)
3. Zkontroluje a případně nainstaluje pytest
4. Spustí pytest API testy
5. Zkontroluje a případně nainstaluje Playwright závislosti
6. Spustí Playwright E2E testy
7. Uloží výstupy do `artifacts/qa/`
8. Ukončí backend proces

### Manuální spuštění

**API testy:**

```powershell
# V root projektu (NE v tests/api!)
python -m pytest tests/api -v
```

**E2E testy:**

```powershell
cd tests/e2e
npx playwright test
```

**E2E testy (headed mode):**

```powershell
cd tests/e2e
npx playwright test --headed
```

**E2E testy (UI mode):**

```powershell
cd tests/e2e
npx playwright test --ui
```

**Poznámka:** Při manuálním spuštění musí být backend server spuštěn na `http://127.0.0.1:8000`.

## Nalezené bugy a opravy

### ✅ Opraveno: Chybějící data-testid atributy

**Problém:** UI nemělo stabilní selektory pro E2E testy.

**Oprava:** Přidány `data-testid` atributy do všech klíčových UI prvků.

**Soubory:**

- `web/index.html` - Přidány data-testid atributy
- `web/index.html` - Upravena funkce `showAlert()` pro přidání data-testid do alertů

**Regresní testy:**

- Všechny E2E testy používají data-testid selektory

### ✅ Opraveno: Playwright konfigurace

**Problém:** Playwright konfigurace měla špatnou cestu k testům.

**Oprava:** Opravena `testDir` v `playwright.config.ts`.

**Soubory:**

- `tests/e2e/playwright.config.ts`

## TODO / Neřešitelné bez dalších dat

1. **Testování VIN dekodéru** - Vyžaduje externí API (MDČR, NHTSA)
2. **Testování email notifikací** - Vyžaduje SMTP konfiguraci
3. **Testování Command Bot** - Vyžaduje AI integraci
4. **Testování Autopilot API** - Vyžaduje shared secret
5. **Testování multi-tenant funkcionality** - Vyžaduje více tenantů

## Závěr

QA infrastruktura byla úspěšně vytvořena a pokrývá:

- ✅ Autentizaci (login, registrace, logout)
- ✅ Správu vozidel (CRUD)
- ✅ Navigaci mezi sekcemi
- ✅ Základní API endpointy
- ✅ Error handling
- ✅ Mobilní zobrazení

Všechny testy jsou automatizované a lze je spustit jedním příkazem pomocí `scripts/qa_run.ps1`.

## Další kroky

1. Přidat více E2E testů pro edge cases
2. Přidat performance testy
3. Přidat testy pro servisní záznamy
4. Přidat testy pro připomínky a rezervace (CRUD)
5. Přidat testy pro profil (editace)
