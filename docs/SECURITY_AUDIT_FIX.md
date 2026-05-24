# 🔒 Bezpečnostní audit a opravy

## ⚠️ KRITICKÉ PROBLÉMY (opraveno)

### 1. `.env` soubor v repozitáři
**Status:** ✅ OPRAVENO

**Problém:** Soubor `.env` obsahující citlivé údaje (API klíče, hesla) byl v git repozitáři.

**Oprava:**
- ✅ Přidáno do `.gitignore`
- ✅ Odstraněno z git indexu: `git rm --cached .env`
- ✅ Vytvořen `.env.example` s ukázkovými hodnotami

**⚠️ DŮLEŽITÉ:** Pokud byl `.env` již commitnut do historie, musíte:
1. Rotovat všechny API klíče a hesla, které v něm byly
2. Odstranit z historie pomocí `git filter-repo` nebo BFG

### 2. `tunnel.log` a `vehicles.db` v repozitáři
**Status:** ✅ OPRAVENO

**Problém:** Log soubory a databáze byly v repozitáři.

**Oprava:**
- ✅ Přidáno `*.log`, `*.db`, `*.sqlite` do `.gitignore`
- ✅ Odstraněno z git indexu

### 3. Chybějící LICENSE
**Status:** ✅ OPRAVENO

**Oprava:**
- ✅ Vytvořen `LICENSE` soubor (MIT License)

## 📋 Provedené změny

### Aktualizovaný `.gitignore`
Přidáno:
- `.env` a všechny varianty
- `*.log`, `logs/`
- `*.db`, `*.sqlite`, `*.sqlite3`
- Cache soubory
- Secrets a keys
- Data directories

### Nové soubory
- `.env.example` - šablona pro environment variables
- `LICENSE` - MIT License
- `.github/workflows/security.yml` - bezpečnostní kontroly v CI

### Bezpečnostní CI workflow
Nový workflow `.github/workflows/security.yml` kontroluje:
- ✅ Přítomnost citlivých souborů v repo
- ✅ Hardcoded secrets v kódu
- ✅ Zranitelnosti v závislostech (pip-audit, safety)

## 🚨 OKAMŽITÉ KROKY (musíte provést)

### 1. Odstranit citlivé soubory z git indexu

```bash
# Odstranit z indexu (soubory zůstanou lokálně)
git rm --cached .env
git rm --cached tunnel.log
git rm --cached vehicles.db
git rm --cached .aider.tags.cache.v4/cache.db

# Commit změn
git add .gitignore .env.example LICENSE
git commit -m "Security: Remove sensitive files from repo, add .env.example and LICENSE"
```

### 2. Rotovat všechny vystavené klíče

**⚠️ KRITICKÉ:** Pokud byl `.env` commitnut do historie, musíte rotovat:
- JWT_SECRET_KEY
- SMTP_PASSWORD
- DATAOVO_API_KEY
- AUTOPILOT_SHARED_SECRET
- Všechny další API klíče a hesla

### 3. Odstranit z historie (volitelné, ale doporučené)

Pokud chcete úplně odstranit citlivé soubory z historie:

```bash
# Instalace git-filter-repo
pip install git-filter-repo

# Odstranit z historie
git filter-repo --invert-paths --path .env --path tunnel.log --path vehicles.db

# Force push (POZOR: přepíše historii!)
git push origin --force --all
```

**⚠️ VAROVÁNÍ:** Force push přepíše historii. Všichni spolupracovníci musí znovu klonovat repo.

## ✅ Ověření

Po provedení změn ověřte:

```bash
# Zkontrolovat, že soubory nejsou v git
git ls-files | grep -E "\.env$|\.log$|\.db$"

# Mělo by být prázdné (žádné výsledky)
```

## 📚 Další doporučení

1. **GitHub Secret Scanning** - Zapněte v GitHub Settings → Security → Secret scanning
2. **Dependabot** - Zapněte pro automatické aktualizace závislostí
3. **Pre-commit hooks** - Přidejte kontroly před commitem
4. **Code review** - Vždy review PR před mergem

## 🔐 Best practices

- ✅ Nikdy necommitujte `.env` soubory
- ✅ Používejte `.env.example` pro dokumentaci
- ✅ Rotujte klíče pravidelně
- ✅ Používejte GitHub Secrets pro CI/CD
- ✅ Pravidelně kontrolujte zranitelnosti závislostí

