# Průvodce automatickou opravou workflow chyb

## Přehled

Systém automatické opravy workflow chyb monitoruje GitHub Actions a pokusí se automaticky opravit běžné problémy, které způsobují selhání testů.

## Jak to funguje

### 1. **GitHub Action Workflow** (`.github/workflows/auto-fix.yml`)

Automaticky se spustí:
- Po každém failed workflow runu (QA Tests nebo Production Smoke Tests)
- Každých 30 minut (scheduled check)
- Ručně přes workflow_dispatch

**Co dělá:**
1. Analyzuje failed workflow runy
2. Identifikuje typ chyby
3. Pokusí se automaticky opravit (pokud je to možné)
4. Vytvoří Pull Request s opravami
5. Nebo vytvoří Issue, pokud oprava vyžaduje manuální zásah

### 2. **Lokální skript** (`scripts/auto_fix_workflows.ps1`)

Můžeš spustit lokálně pro monitoring a opravu:

```powershell
# Jednorázová kontrola
.\scripts\auto_fix_workflows.ps1 -RunOnce

# Kontinuální monitoring (kontrola každých 5 minut)
.\scripts\auto_fix_workflows.ps1 -CheckInterval 300
```

## Nastavení

### GitHub Token

Pro lokální skript potřebuješ GitHub Personal Access Token:

1. **Vytvoř token:**
   - GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
   - Generate new token (classic)
   - Oprávnění: `repo`, `workflow`, `actions:read`
   - Zkopíruj token

2. **Nastav environment variable:**
   ```powershell
   $env:GITHUB_TOKEN = "tvuj-token-zde"
   ```

   Nebo přidej do PowerShell profilu (`$PROFILE`):
   ```powershell
   $env:GITHUB_TOKEN = "tvuj-token-zde"
   ```

### GitHub Action Permissions

GitHub Action workflow automaticky používá `GITHUB_TOKEN`, který má potřebná oprávnění:
- `contents: write` - pro commitování oprav
- `issues: write` - pro vytváření issues
- `pull-requests: write` - pro vytváření PR
- `actions: read` - pro čtení workflow runů

## Typy chyb, které lze automaticky opravit

### ✅ **Selector/UI Errors** (`selector_not_found`)
- **Příčina:** Chybí `data-testid` atributy nebo změnily se selektory
- **Oprava:** Přidání chybějících `data-testid` do HTML nebo aktualizace testů
- **Status:** Částečně podporováno (vyžaduje vylepšení)

### ✅ **Import Errors** (`import_error`)
- **Příčina:** Chybí importy nebo moduly
- **Oprava:** Přidání chybějících importů
- **Status:** Částečně podporováno (vyžaduje vylepšení)

### ✅ **Syntax Errors** (`syntax_error`)
- **Příčina:** Syntaktické chyby v kódu
- **Oprava:** Oprava chybějících závorek, středníků, atd.
- **Status:** Částečně podporováno (základní opravy)

### ✅ **Test Failures** (`test_failure`)
- **Příčina:** Testy selhávají kvůli změnám v aplikaci
- **Oprava:** Aktualizace testů nebo oprava aplikace
- **Status:** Vyžaduje manuální review

## Typy chyb, které NELZE automaticky opravit

### ❌ **Login Failed** (`login_failed`)
- **Příčina:** Špatné credentials v GitHub Secrets
- **Oprava:** Manuální kontrola a aktualizace secrets
- **Akce:** Vytvoří Issue s instrukcemi

### ❌ **Connection Refused** (`connection_refused`)
- **Příčina:** Server je nedostupný
- **Oprava:** Manuální restart serveru
- **Akce:** Vytvoří Issue s varováním

## Workflow proces

```
Failed Workflow Run
       ↓
Analyze Error (analyze_failed_workflow.py)
       ↓
   Can Auto-Fix?
    ↙        ↘
  YES        NO
   ↓          ↓
Apply Fix   Create Issue
(apply_fixes.py)
   ↓
Create Branch
   ↓
Commit Changes
   ↓
Push to GitHub
   ↓
Create Pull Request
   ↓
Review & Merge
```

## Použití

### Automatické (GitHub Actions)

Workflow se spustí automaticky - nic nemusíš dělat. Když najde problém:

1. **Pokud lze opravit automaticky:**
   - Vytvoří se Pull Request s opravami
   - Zkontroluj PR a merge, pokud vypadá dobře

2. **Pokud nelze opravit automaticky:**
   - Vytvoří se Issue s detaily problému
   - Oprav problém ručně podle instrukcí v Issue

### Lokální monitoring

```powershell
# Spusť monitoring
.\scripts\auto_fix_workflows.ps1

# Nebo jednorázová kontrola
.\scripts\auto_fix_workflows.ps1 -RunOnce

# S vlastním intervalem (2 minuty)
.\scripts\auto_fix_workflows.ps1 -CheckInterval 120
```

## Omezení a poznámky

### ⚠️ **Aktuální stav**

Systém je v **beta verzi** a automatické opravy jsou **omezené**:

- ✅ **Detekce chyb** - plně funkční
- ✅ **Analýza chyb** - plně funkční
- ⚠️ **Automatické opravy** - částečně funkční (vyžaduje vylepšení)
- ✅ **Vytváření PR/Issues** - plně funkční

### 🔧 **Vylepšení pro budoucnost**

1. **Lepší analýza chyb:**
   - Použití AI/LLM pro lepší porozumění chybám
   - Kontextové opravy na základě celého kódu

2. **Rozšířené automatické opravy:**
   - Oprava selector errors s přidáním data-testid
   - Oprava import errors s automatickým přidáním importů
   - Oprava test failures s aktualizací testů

3. **Lepší integrace:**
   - Přímá oprava v main branch (s approval)
   - Automatické testování oprav před PR

## Troubleshooting

### Workflow se nespouští

- Zkontroluj, že soubor `.github/workflows/auto-fix.yml` existuje
- Zkontroluj, že máš oprávnění spouštět workflows

### Lokální skript nefunguje

- Zkontroluj, že máš nastavený `GITHUB_TOKEN`
- Zkontroluj, že máš oprávnění k repozitáři
- Zkontroluj, že máš nainstalovaný PowerShell 5.1+

### Opravy se neaplikují

- Zkontroluj logy v GitHub Actions
- Některé chyby nelze opravit automaticky
- Vytvoří se Issue s instrukcemi pro manuální opravu

## Shrnutí

✅ **Automatická detekce** - funguje  
✅ **Analýza chyb** - funguje  
⚠️ **Automatické opravy** - částečně (vyžaduje vylepšení)  
✅ **Notifikace (PR/Issues)** - funguje  

**Systém ti pomůže identifikovat problémy a v některých případech je i opravit automaticky. Vždy zkontroluj PR před mergem!**

