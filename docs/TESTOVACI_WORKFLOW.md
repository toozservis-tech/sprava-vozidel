# 🧪 Testovací Workflow - Kompletní testování

## Nový workflow: Full Test Suite

Vytvořen nový workflow `.github/workflows/full-test-suite.yml`, který spouští **všechny možné testy** a kontroly.

## Co workflow testuje

### 1. ✅ Python Syntax Check
- Kontroluje syntax všech Python souborů
- Používá `py_compile` pro validaci

### 2. ✅ Import Check
- Testuje import všech hlavních modulů:
  - Server (`src.server.main`)
  - AI Features modely
  - Analytics
  - Routers

### 3. ✅ Database Initialization
- Vytváří všechny databázové tabulky
- Ověřuje, že modely jsou správně definované

### 4. ✅ Python Linter (flake8)
- Kontroluje code quality
- Hledá syntax errors a potenciální problémy

### 5. ✅ Backend Server Start
- Spouští server na portu 8000
- Čeká na připravenost (health check)

### 6. ✅ Health Endpoints Test
- Testuje `/health`
- Testuje `/` (root)
- Testuje `/version`

### 7. ✅ API Tests (pytest)
- Spouští všechny API testy
- Generuje JUnit XML report

### 8. ✅ TypeScript Compilation Check
- Kontroluje TypeScript soubory
- Ověřuje, že E2E testy jsou kompilovatelné

### 9. ✅ E2E Tests (Playwright)
- Spouští end-to-end testy
- Generuje HTML report

### 10. ✅ Security Checks
- Kontroluje, zda nejsou citlivé soubory v git
- Ověřuje, že `.gitignore` obsahuje správné vzory

## Jak spustit

### Automaticky
Workflow se spustí automaticky při:
- Push na jakoukoliv branch
- Pull request
- Ručním spuštění (workflow_dispatch)

### Ručně
1. Jděte na GitHub → "Actions" tab
2. Vyberte "Full Test Suite"
3. Klikněte na "Run workflow"
4. Vyberte branch (obvykle `master`)
5. Klikněte na "Run workflow"

## Výstupy

### Artifacts
Všechny testy generují artifacts:
- `pytest-report.xml` - API testy report
- `playwright-report/` - E2E testy HTML report
- `test-results/` - E2E testy výsledky

### Test Summary
Workflow vytváří summary v GitHub Actions UI s přehledem všech testů.

## Ostatní workflows

### QA Tests (`.github/workflows/qa.yml`)
- Spouští API a E2E testy
- Používá se pro každý push/PR

### Production Smoke Tests (`.github/workflows/prod-smoke.yml`)
- Testuje produkční prostředí
- Spouští se denně v 03:30

### Security Checks (`.github/workflows/security.yml`)
- Kontroluje bezpečnost
- Skenuje závislosti

### Auto-Fix (`.github/workflows/auto-fix.yml`)
- Automaticky opravuje chyby
- Vytváří PR s opravami

## Doporučení

Pro kompletní testování použijte **Full Test Suite** workflow, který:
- ✅ Testuje vše najednou
- ✅ Poskytuje kompletní přehled
- ✅ Generuje všechny artifacts
- ✅ Kontroluje bezpečnost

---

**Vytvořeno:** 12. prosince 2025  
**Status:** ✅ Aktivní a připraven k použití

