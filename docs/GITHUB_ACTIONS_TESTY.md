# 🧪 GitHub Actions - Kompletní testování

## 📋 Dostupné workflows

### 1. ✅ QA Tests (`qa.yml`)
**Spouští se:** Při každém pushu, PR, nebo manuálně
**Co testuje:**
- ✅ Python syntax
- ✅ Importy modulů
- ✅ Database inicializace
- ✅ API testy (pytest)
- ✅ E2E testy (Playwright)

### 2. ✅ Security Checks (`security.yml`)
**Spouští se:** Při každém pushu, PR, nebo denně v 02:00 UTC
**Co kontroluje:**
- ✅ Citlivé soubory v repo (.env, *.log, *.db)
- ✅ Hardcoded secrets v kódu
- ✅ Zranitelnosti v závislostech (pip-audit, safety)

### 3. ✅ Production Smoke Tests (`prod-smoke.yml`)
**Spouští se:** Při pushu na main/master, denně v 01:30 UTC, nebo manuálně
**Co testuje:**
- ✅ Produkční server (https://hub.toozservis.cz)
- ✅ E2E smoke testy
- ✅ Read-only testy (neupravují data)

### 4. ✅ Full Test Suite (`full-test-suite.yml`)
**Spouští se:** Při každém pushu, PR, nebo manuálně
**Co testuje:**
- ✅ Python syntax check
- ✅ Import check
- ✅ Database inicializace
- ✅ Python linter (flake8)
- ✅ Health endpoints
- ✅ API testy
- ✅ TypeScript compilation
- ✅ E2E testy
- ✅ Security check (citlivé soubory)
- ✅ .gitignore kontrola

### 5. ✅ Auto-Fix Failed Workflows (`auto-fix.yml`)
**Spouští se:** Automaticky při selhání QA nebo Production Smoke Tests
**Co dělá:**
- ✅ Analyzuje chyby v failed workflows
- ✅ Pokusí se automaticky opravit (pokud je to možné)
- ✅ Vytvoří Pull Request s opravami
- ✅ Nebo vytvoří Issue pro manuální opravu

## 🚀 Jak spustit všechny testy

### Metoda 1: Použít skript (doporučeno)
```powershell
.\scripts\run_all_github_tests.ps1
```

### Metoda 2: Manuálně přes prázdný commit
```powershell
git commit --allow-empty -m "ci: Trigger all workflows"
git push origin master
```

### Metoda 3: Přes GitHub web UI
1. Jděte na: https://github.com/toozservis-tech/TOOZHUB2/actions
2. Klikněte na workflow, který chcete spustit
3. Klikněte na "Run workflow"

## 📊 Sledování výsledků

**GitHub Actions:**
https://github.com/toozservis-tech/TOOZHUB2/actions

**Workflow status:**
- ✅ Zelená = Všechny testy prošly
- ⚠️ Žlutá = Některé testy selhaly (ale continue-on-error)
- ❌ Červená = Kritické testy selhaly

## 🔍 Co se testuje

### Python Backend
- ✅ Syntax všech Python souborů
- ✅ Import všech modulů
- ✅ Database inicializace
- ✅ Server start a health check
- ✅ API endpointy

### Frontend
- ✅ TypeScript compilation
- ✅ E2E testy (Playwright)
- ✅ UI komponenty
- ✅ Navigace

### Bezpečnost
- ✅ Citlivé soubory v repo
- ✅ Hardcoded secrets
- ✅ Zranitelnosti závislostí

## ⚠️ Troubleshooting

### Workflow selhává na import
- Zkontrolujte, zda jsou všechny moduly správně importovány
- Zkontrolujte, zda jsou všechny závislosti v requirements.txt

### Workflow selhává na database
- Zkontrolujte, zda jsou všechny modely importovány před create_all()
- Zkontrolujte, zda jsou foreign keys správně definované

### E2E testy selhávají
- Zkontrolujte, zda server běží
- Zkontrolujte, zda jsou data-testid atributy správně nastavené
- Zkontrolujte logy v artifacts

## 📝 Poznámky

- Všechny workflows mají `continue-on-error: true` u některých kroků
- To znamená, že workflow neukončí při selhání ne-kritických testů
- Zkontrolujte logy pro detailní informace o selháních

