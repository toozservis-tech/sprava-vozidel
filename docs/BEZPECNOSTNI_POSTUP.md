# 🔒 Bezpečnostní postup po úniku citlivých dat

## ⚠️ KRITICKÁ SITUACE

Pokud byl `.env` soubor commitnut do git historie, musíte **OKAMŽITĚ** provést následující kroky:

## 🚨 OKAMŽITÉ KROKY (prvních 15 minut)

### 1. Rotovat všechny vystavené klíče

**Zkontrolujte, co bylo v `.env` a rotujte:**

#### JWT Secret Key
```bash
# Vygenerujte nový klíč
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Aktualizujte v .env
JWT_SECRET_KEY=<nový-klíč>
```

#### SMTP Password
- Změňte heslo v emailovém účtu
- Vygenerujte nové App Password (pokud používáte Gmail)
- Aktualizujte v `.env`

#### API Klíče
- **DATAOVO_API_KEY** - Získejte nový klíč na https://dataovozidlech.cz
- **AUTOPILOT_SHARED_SECRET** - Vygenerujte nový secret
- Všechny další API klíče

### 2. Zkontrolovat GitHub Secrets

Pokud používáte GitHub Actions:
1. Jděte do Settings → Secrets and variables → Actions
2. Zkontrolujte, zda tam nejsou stejné klíče
3. Pokud ano, rotujte je také

## 🔧 Odstranění z historie (doporučené)

### Metoda 1: git filter-repo (doporučeno)

```bash
# Instalace
pip install git-filter-repo

# Vytvoření zálohy
git clone --mirror https://github.com/toozservis-tech/TOOZHUB2.git TOOZHUB2-backup.git

# Odstranění souborů z historie
git filter-repo --invert-paths \
  --path .env \
  --path tunnel.log \
  --path vehicles.db \
  --path .aider.tags.cache.v4/cache.db

# Force push (POZOR: přepíše historii!)
git push origin --force --all
git push origin --force --tags
```

### Metoda 2: BFG Repo-Cleaner

```bash
# Stáhnout BFG
# https://rtyley.github.io/bfg-repo-cleaner/

# Vytvoření zálohy
git clone --mirror https://github.com/toozservis-tech/TOOZHUB2.git TOOZHUB2-backup.git

# Odstranění souborů
java -jar bfg.jar --delete-files .env,tunnel.log,vehicles.db TOOZHUB2.git

# Vyčištění
cd sprava-vozidel.git
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# Force push
git push --force
```

### ⚠️ VAROVÁNÍ

**Force push přepíše historii!**
- Všichni spolupracovníci musí znovu klonovat repo
- Všechny otevřené PR budou muset být znovu vytvořeny
- Forky budou mít starou historii

## ✅ Ověření

Po provedení změn:

```bash
# Zkontrolovat, že soubory nejsou v git
git ls-files | grep -E "\.env$|\.log$|\.db$"

# Mělo by být prázdné (žádné výsledky)

# Zkontrolovat historii
git log --all --full-history -- .env

# Mělo by být prázdné (pokud bylo odstraněno z historie)
```

## 📋 Checklist

- [ ] Rotován JWT_SECRET_KEY
- [ ] Rotován SMTP_PASSWORD
- [ ] Rotován DATAOVO_API_KEY
- [ ] Rotován AUTOPILOT_SHARED_SECRET
- [ ] Rotovány všechny další API klíče
- [ ] Zkontrolovány GitHub Secrets
- [ ] Odstraněno z git indexu (`git rm --cached`)
- [ ] Odstraněno z historie (git filter-repo/BFG)
- [ ] Vytvořen `.env.example`
- [ ] Aktualizován `.gitignore`
- [ ] Všichni spolupracovníci informováni
- [ ] Vytvořen nový commit s opravami

## 🔐 Prevence do budoucna

1. **Pre-commit hooks** - Automatická kontrola před commitem
2. **GitHub Secret Scanning** - Automatická detekce secrets
3. **Code review** - Vždy review PR před mergem
4. **Pravidelné audity** - Kontrola repo na citlivé soubory

## 📞 Kontakt

Pokud máte pochybnosti nebo potřebujete pomoc, kontaktujte správce repozitáře.

