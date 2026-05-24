# GitHub Secret Scanning - Alternativní řešení

## Problém: Secret Scanning není dostupný v Settings

Pokud nevidíte sekci "Security" → "Advanced Security" → "Secret scanning" v GitHub Settings, může to být z těchto důvodů:

1. **Nemáte admin oprávnění** k repozitáři
2. **Privátní repozitář** - Secret Scanning vyžaduje GitHub Advanced Security (placené)
3. **Organizační repozitář** - potřebujete organizační admin oprávnění

## ✅ Řešení: Lokální kontrola pomocí pre-commit hooku

Místo GitHub Secret Scanning můžeme použít lokální kontrolu, která zabrání commitnutí secrets:

### Instalace detect-secrets

```bash
pip install detect-secrets
```

### Vytvoření .secrets.baseline

```bash
detect-secrets scan > .secrets.baseline
```

### Vytvoření pre-commit hooku

Vytvořte soubor `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
        exclude: package.lock.json
```

### Instalace pre-commit

```bash
pip install pre-commit
pre-commit install
```

## ✅ Řešení: GitHub Actions workflow (již máme!)

Už máme vytvořený workflow `.github/workflows/security.yml`, který kontroluje:
- ✅ Přítomnost citlivých souborů (.env, *.log, *.db)
- ✅ Hardcoded secrets v kódu
- ✅ Zranitelnosti v závislostích

Tento workflow běží automaticky při každém pushu!

## ✅ Řešení: Manuální kontrola pomocí gitleaks

### Instalace gitleaks

**Windows:**
```powershell
# Pomocí Chocolatey
choco install gitleaks

# Nebo stáhnout z: https://github.com/gitleaks/gitleaks/releases
```

**Linux/Mac:**
```bash
brew install gitleaks
```

### Spuštění kontroly

```bash
# Kontrola aktuálního stavu
gitleaks detect --source . --verbose

# Kontrola s reportem
gitleaks detect --source . --report-path gitleaks-report.json
```

### Přidání do CI/CD

Můžeme přidat gitleaks do GitHub Actions workflow.

## ✅ Řešení: Použití GitHub CLI

Pokud máte GitHub CLI nainstalovaný:

```bash
# Kontrola, zda máte admin oprávnění
gh repo view toozservis-tech/sprava-vozidel --json permissions

# Zkontrolovat security features
gh api repos/toozservis-tech/sprava-vozidel/vulnerability-alerts
```

## ✅ Nejjednodušší řešení: Použít náš Security workflow

**Už máme vytvořený workflow, který:**
1. ✅ Kontroluje přítomnost .env, *.log, *.db souborů
2. ✅ Hledá hardcoded secrets v kódu
3. ✅ Kontroluje zranitelnosti závislostí
4. ✅ Běží automaticky při každém pushu

**Workflow je v:** `.github/workflows/security.yml`

**Kontrola:**
1. Jděte do GitHub → "Actions" tab
2. Najděte workflow "Security Checks"
3. Zkontrolujte, zda běží a prochází

## Doporučení

**Pro teď:**
1. ✅ Použijte náš Security workflow (už běží)
2. ✅ Nainstalujte pre-commit hook pro lokální kontrolu
3. ✅ Pravidelně spouštějte gitleaks pro kontrolu

**Do budoucna:**
- Pokud je repozitář privátní, zvažte upgrade na GitHub Advanced Security
- Nebo změňte repozitář na veřejný (Secret Scanning je zdarma pro veřejné repo)

## Kontrola oprávnění

Zkontrolujte, zda máte admin oprávnění:

1. Jděte na: `https://github.com/toozservis-tech/TOOZHUB2/settings/access`
2. Podívejte se na sekci "Collaborators"
3. Zkontrolujte, zda máte roli "Admin"

Pokud nemáte admin oprávnění, požádejte vlastníka repozitáře o přidání.

