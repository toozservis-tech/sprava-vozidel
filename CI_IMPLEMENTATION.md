# CI Implementation Summary

## Přidané soubory

1. **`.github/workflows/qa.yml`** - GitHub Actions workflow pro automatické spouštění testů

## Upravené soubory

1. **`tests/e2e/helpers.ts`** - Nový helper soubor pro E2E testy s podporou env proměnných
2. **`tests/e2e/auth.spec.ts`** - Používá helper funkce místo hardcoded credentials
3. **`tests/e2e/vehicles.spec.ts`** - Používá helper funkce
4. **`tests/e2e/navigation.spec.ts`** - Používá helper funkce
5. **`tests/e2e/mobile.spec.ts`** - Používá helper funkce
6. **`tests/e2e/reminders.spec.ts`** - Používá helper funkce
7. **`tests/e2e/reservations.spec.ts`** - Používá helper funkce
8. **`tests/e2e/profile.spec.ts`** - Používá helper funkce
9. **`tests/e2e/error-handling.spec.ts`** - Používá helper funkce
10. **`README.md`** - Přidána sekce "CI / QA" s dokumentací

## Workflow příkazy

Workflow `.github/workflows/qa.yml` provádí následující kroky:

1. **Checkout repository** - `actions/checkout@v4`
2. **Setup Python 3.12** - `actions/setup-python@v5` s pip cache
3. **Install Python dependencies** - `pip install -r requirements.txt`
4. **Setup Node.js 20** - `actions/setup-node@v4` s npm cache
5. **Install E2E dependencies** - `npm ci` v `tests/e2e/` + `npx playwright install --with-deps chromium`
6. **Create artifacts directory** - `mkdir -p artifacts/qa`
7. **Initialize database via Alembic** - `rm -f test_vehicles.db && python scripts/migrate_database.py upgrade head`
8. **Start backend server** - `python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000 &`
9. **Wait for backend** - Polling `GET /health` endpoint (timeout 60s)
10. **Run API tests** - `python -m pytest tests/api -v --tb=short --junit-xml=artifacts/qa/pytest-report.xml`
11. **Run E2E tests** - `cd tests/e2e && npx playwright test --reporter=list,html --project=chromium`
12. **Upload artifacts** - Upload `artifacts/qa/**`, `tests/e2e/playwright-report/**`, `tests/e2e/test-results/**`
13. **Stop backend** - Kill backend process pomocí PID a cleanup uvicorn procesů

## Environment proměnné

Workflow nastavuje následující env proměnné:

- `BASE_URL=http://127.0.0.1:8000`
- `TEST_API_URL=http://127.0.0.1:8000`
- `APP_ENV=test`
- `ENVIRONMENT=test`
- `DATABASE_URL=sqlite:///./test_vehicles.db`
- `VEHICLE_DB_URL=sqlite:///./test_vehicles.db` (pro kompatibilitu s `src/server/config.py`)
- `TEST_DATABASE_URL=sqlite:///./test_vehicles.db`
- `E2E_EMAIL=toozservis@gmail.com`
- `E2E_PASSWORD=123456`
- `JWT_SECRET_KEY=test-secret-key-for-ci-only`
- `HOST=127.0.0.1`
- `PORT=8000`

## Test DB izolace

✅ **Test DB je izolovaná a vědomě oddělená od runtime DB:**
- Používá `test_vehicles.db` (nastaveno přes `DATABASE_URL` a `VEHICLE_DB_URL` env proměnné)
- Produkční DB (`vehicles.db`) není použita v testech
- Test DB je v `.gitignore`
- Backend automaticky použije test DB díky env proměnným
- Schema se připravuje přes Alembic migrace, ne přes `Base.metadata.create_all`

## E2E credentials

✅ **E2E testy podporují env proměnné:**
- Vytvořen `tests/e2e/helpers.ts` s funkcemi `getTestCredentials()` a `loginUser()`
- Všechny E2E testy upraveny, aby používaly helper funkce
- Credentials lze přepsat přes `E2E_EMAIL` a `E2E_PASSWORD` env proměnné
- Default hodnoty: `toozservis@gmail.com` / `123456` (pro lokální vývoj)

## Health endpoint

✅ **`/health` endpoint už existuje:**
- Endpoint je v `src/server/main.py` na řádku 1082
- Vrací `{"status": "ok", ...}` s informacemi o verzi
- Workflow používá tento endpoint pro readiness check

## Poznámky

- Workflow spouští pouze Chromium pro E2E testy (rychlejší v CI)
- Testy mají `continue-on-error: true`, aby se všechny testy spustily i při selhání
- Artefakty se ukládají na 7 dní
- Backend se ukončuje vždy (i při failu) pomocí `if: always()`

## Spuštění

Workflow se spouští:
- Automaticky při každém push a pull requestu
- Ručně přes GitHub Actions UI (workflow_dispatch)

---

# Production Smoke Tests

## Přidané soubory

1. **`.github/workflows/prod-smoke.yml`** - GitHub Actions workflow pro production smoke testy
2. **`tests/e2e/prod-smoke.spec.ts`** - Read-only smoke testy pro produkci

## Upravené soubory

1. **`tests/e2e/helpers.ts`** - Přidány funkce: `isReadOnly()`, `assertNoGlobalErrorBanner()`, `gotoTab()`, `getBaseUrl()`
2. **`tests/e2e/playwright.config.ts`** - BaseURL nyní podporuje env proměnnou `BASE_URL`
3. **`CI_IMPLEMENTATION.md`** - Přidána dokumentace pro production smoke testy

## Production Smoke Tests Workflow

**Workflow:** `.github/workflows/prod-smoke.yml`

**Spuštění:**
- Automaticky 1× denně v 03:30 Europe/Prague (01:30 UTC)
- Automaticky při push na `main` branch
- Ručně přes GitHub Actions UI (workflow_dispatch)

**Kroky workflow:**
1. Checkout repository
2. Setup Node.js 20 s npm cache
3. Install E2E dependencies (`npm ci` + Playwright)
4. Create artifacts directory
5. Run production smoke tests (`npx playwright test prod-smoke.spec.ts --reporter=list,html --project=chromium`)
6. Upload artifacts (retention 30 dní)

## Environment proměnné

Workflow nastavuje:
- `BASE_URL=https://hub.toozservis.cz`
- `E2E_READONLY=1`
- `E2E_EMAIL=${{ secrets.PROD_E2E_EMAIL }}`
- `E2E_PASSWORD=${{ secrets.PROD_E2E_PASSWORD }}`

## GitHub Secrets

**Povinné secrets (nastav v GitHub Settings → Secrets and variables → Actions):**

1. `PROD_E2E_EMAIL` - Email pro přihlášení do produkce
2. `PROD_E2E_PASSWORD` - Heslo pro přihlášení do produkce

**Jak nastavit:**
1. Jdi do GitHub repozitáře
2. Settings → Secrets and variables → Actions
3. New repository secret
4. Přidej `PROD_E2E_EMAIL` a `PROD_E2E_PASSWORD`

## Read-Only Testy

Production smoke testy jsou **read-only** - **nesmí vytvářet, upravovat ani mazat data**.

**Co testují:**
- ✅ Načtení login stránky
- ✅ Přihlášení do aplikace
- ✅ Navigace mezi sekcemi (vozidla, připomínky, rezervace, profil)
- ✅ Zobrazení seznamů (bez vytváření/editace/mazání)
- ✅ Ověření, že UI nezobrazuje chybové hlášky
- ✅ Odhlášení

**Co NEdělají:**
- ❌ Vytváření vozidel
- ❌ Editace dat
- ❌ Mazání záznamů
- ❌ Vytváření servisních záznamů
- ❌ Jakékoliv změny v databázi

## Cron Schedule

- **Čas v ČR:** 03:30 (Europe/Prague)
- **Čas v UTC:** 01:30
- **Cron:** `30 1 * * *` (každý den v 01:30 UTC)

**Poznámka:** Prague je UTC+2 v létě (CEST) a UTC+1 v zimě (CET). Cron je nastaven na 01:30 UTC, což odpovídá přibližně 03:30 Prague času v obou režimech.

## Artefakty

Artefakty z production smoke testů:
- Najdete v GitHub Actions UI → "Production Smoke Tests" workflow → konkrétní run → "Artifacts"
- Název artefaktu: `prod-smoke-artifacts`
- Retention: 30 dní
- Obsahuje:
  - `playwright-report/` - HTML report z E2E testů
  - `test-results/` - Screenshoty a videa z failed testů
