# Průvodce nastavením GitHub repozitáře

## Rychlý postup

### 1. Vytvoř nový repozitář na GitHubu

1. Jdi na: **https://github.com/new**
2. **Repository name:** `sprava-vozidel` (nebo jiný název)
3. **Description:** (volitelné) "Správa vozidel - Vehicle Management System"
4. **Visibility:** Vyber Private nebo Public
5. **DŮLEŽITÉ:** 
   - ❌ **NEVYTVÁŘEJ** README
   - ❌ **NEVYTVÁŘEJ** .gitignore
   - ❌ **NEVYTVÁŘEJ** licenci
   
   (Projekt už tyto soubory má!)
6. Klikni na **"Create repository"**

### 2. Spusť setup skript

```powershell
.\scripts\setup_github_repo.ps1
```

Skript tě provede:
- Nastavením git remote
- Commitnutím změn (pokud chceš)
- Pushnutím na GitHub

### 3. Nebo ručně přes příkazovou řádku

```powershell
# 1. Přidej remote (nahraď URL svým repozitářem)
git remote add origin https://github.com/TVAJE-USERNAME/TOOZHUB2.git

# 2. Přidej všechny soubory
git add .

# 3. Commitni změny
git commit -m "Initial commit: Add sprava-vozidel project with CI/CD workflows"

# 4. Pushni na GitHub
git push -u origin master
```

## Po pushnutí na GitHub

### Nastavení GitHub Secrets

1. Jdi do repozitáře na GitHubu
2. **Settings** → **Secrets and variables** → **Actions**
3. Klikni na **"New repository secret"**
4. Přidej tyto dva secrets:

   **Secret 1:**
   - Name: `PROD_E2E_EMAIL`
   - Secret: `toozservis@gmail.com` (nebo tvůj produkční email)

   **Secret 2:**
   - Name: `PROD_E2E_PASSWORD`
   - Secret: `123456` (nebo tvůj produkční heslo)

### Ověření, že to funguje

1. Jdi do **Actions** v GitHub repozitáři
2. Měl bys vidět workflow "QA Tests" a "Production Smoke Tests"
3. Workflow se spustí automaticky při push na `main` branch
4. Nebo spusť ručně: **Actions** → **Production Smoke Tests** → **Run workflow**

## Troubleshooting

### "remote origin already exists"
```powershell
# Odstraň starý remote
git remote remove origin

# Přidej nový
git remote add origin https://github.com/TVAJE-USERNAME/TOOZHUB2.git
```

### "Permission denied"
- Zkontroluj, že máš oprávnění k repozitáři
- Pokud používáš HTTPS, možná budeš muset použít Personal Access Token místo hesla
- Nebo použij SSH: `git@github.com:USERNAME/TOOZHUB2.git`

### "Repository already has commits"
```powershell
# Stáhni existující commity
git pull origin master --allow-unrelated-histories

# Nebo force push (POZOR: přepíše historii na GitHubu!)
git push -u origin master --force
```

### "Not logged in to git"
```powershell
# Nastav git user
git config --global user.name "Tvoje Jméno"
git config --global user.email "tvoje@email.com"
```

## Co se stane po pushnutí

1. ✅ GitHub Actions workflow se automaticky spustí při push na `main`
2. ✅ Production Smoke Tests se spustí každý den v 03:30 (Europe/Prague)
3. ✅ Artefakty (test reporty) se uloží v GitHub Actions UI
4. ✅ Workflow můžeš spustit ručně kdykoliv

## Odkazy

- **GitHub Actions:** `https://github.com/TVAJE-USERNAME/TOOZHUB2/actions`
- **Secrets:** `https://github.com/TVAJE-USERNAME/TOOZHUB2/settings/secrets/actions`
- **Workflow soubory:** `.github/workflows/`

