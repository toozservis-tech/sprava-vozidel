# Postup pro vytvoření a použití testovací verze Správa vozidel

## Úvod

Tento dokument popisuje, jak vytvořit testovací verzi projektu pro vývoj a testování bez ovlivnění produkčního prostředí.

## Možnosti vytvoření testovací verze

### Možnost 1: Git Worktree (Doporučeno)

**Výhody:**
- Sdílí stejný Git repozitář
- Snadné přepínání mezi verzemi
- Není potřeba duplikovat celý projekt
- Snadná synchronizace změn

**Postup:**

1. **Vytvoření worktree pro testovací verzi:**
   ```bash
   # Z hlavní složky projektu (sprava-vozidel)
   git worktree add ../sprava-vozidel-test -b test-version
   ```

2. **Přepnutí do testovací verze:**
   ```bash
   cd ../sprava-vozidel-test
   ```

3. **Nastavení testovacího prostředí:**
   - Vytvořte vlastní `.env` soubor s jiným portem (např. `PORT=8002`)
   - Upravte `VERSION` soubor na testovací verzi (např. `2.2.0-test`)
   - Změňte název aplikace v `web/index.html` (např. "Správa vozidel [TEST]")

4. **Spuštění testovacího serveru:**
   ```bash
   # Aktivace virtuálního prostředí
   venv\Scripts\activate  # Windows
   # nebo
   source venv/bin/activate  # Linux/Mac
   
   # Spuštění serveru na jiném portu
   python -m uvicorn src.server.main:app --port 8002 --reload
   ```

5. **Přepnutí zpět do produkční verze:**
   ```bash
   cd ../sprava-vozidel
   ```

6. **Synchronizace změn mezi verzemi:**
   ```bash
   # V testovací verzi
   cd ../sprava-vozidel-test
   git add .
   git commit -m "Testovací změny"
   git push origin test-version
   
   # V produkční verzi
   cd ../sprava-vozidel
   git merge test-version  # nebo git cherry-pick <commit-hash>
   ```

7. **Odstranění worktree (když už není potřeba):**
   ```bash
   # Z hlavní složky projektu
   git worktree remove ../sprava-vozidel-test
   git branch -d test-version  # Odstranění test branch
   ```

### Možnost 2: Druhá složka s kopií projektu

**Výhody:**
- Úplně nezávislé prostředí
- Jednoduché pochopení
- Žádné riziko záměny s produkční verzí

**Nevýhody:**
- Duplikace databáze a souborů
- Potřebuje více místa na disku
- Synchronizace změn je složitější

**Postup:**

1. **Zkopírování projektu:**
   ```bash
   # Zkopírujte celou složku sprava-vozidel
   xcopy sprava-vozidel sprava-vozidel-test /E /I
   # nebo použijte PowerShell
   Copy-Item -Path sprava-vozidel -Destination sprava-vozidel-test -Recurse
   ```

2. **Nastavení testovací verze:**
   - Vytvořte vlastní `.env` soubor s jiným portem (např. `PORT=8002`)
   - Upravte `VERSION` soubor na testovací verzi (např. `2.2.0-test`)
   - Upravte název aplikace v `web/index.html`
   - Volitelně: Změňte cestu k databázi v `.env` (jiná databáze pro testování)

3. **Aktualizace virtuálního prostředí:**
   ```bash
   cd sprava-vozidel-TEST
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. **Spuštění testovacího serveru:**
   ```bash
   python -m uvicorn src.server.main:app --port 8002 --reload
   ```

### Možnost 3: Git Branch s lokálním přepnutím

**Výhody:**
- Vše v jedné složce
- Snadné přepínání pomocí `git checkout`

**Nevýhody:**
- Nelze spustit obě verze současně
- Riziko záměny verzí

**Postup:**

1. **Vytvoření testovací branch:**
   ```bash
   git checkout -b test-version
   ```

2. **Úprava konfigurace pro testování:**
   - Upravte `.env` soubor (jiný port)
   - Upravte `VERSION` soubor
   - Upravte název aplikace

3. **Commit změn:**
   ```bash
   git add .
   git commit -m "Nastavení testovací verze"
   ```

4. **Přepnutí mezi verzemi:**
   ```bash
   # Na testovací verzi
   git checkout test-version
   
   # Zpět na produkční
   git checkout main  # nebo master
   ```

## Aktualizace běžícího projektu

### Postup aktualizace produkční verze

1. **Zastavení produkčního serveru:**
   ```bash
   # Najděte proces serveru a ukončete ho
   # Windows PowerShell:
   Get-Process | Where-Object {$_.ProcessName -eq "python"} | Stop-Process
   
   # Nebo použijte kill_port_8000.bat
   kill_port_8000.bat
   ```

2. **Zálohování databáze (důležité!):**
   ```bash
   # Zkopírujte vehicles.db
   copy vehicles.db vehicles.db.backup
   ```

3. **Přechod do produkční složky:**
   ```bash
   cd sprava-vozidel
   ```

4. **Aktualizace kódu z Git:**
   ```bash
   git pull origin main
   # nebo pokud máte testovací změny
   git merge test-version
   ```

5. **Aktualizace závislostí:**
   ```bash
   venv\Scripts\activate
   pip install -r requirements.txt --upgrade
   ```

6. **Aktualizace verze:**
   - Otevřete soubor `VERSION`
   - Změňte verzi na novou (např. `2.2.1`)
   - Uložte soubor

7. **Spuštění migrací (pokud jsou potřeba):**
   ```bash
   # Pokud máte databázové migrace
   alembic upgrade head
   ```

8. **Spuštění produkčního serveru:**
   ```bash
   python -m uvicorn src.server.main:app --port 8000 --host 0.0.0.0
   # nebo použijte start_server_production.bat
   start_server_production.bat
   ```

9. **Ověření funkčnosti:**
   - Otevřete aplikaci v prohlížeči
   - Zkontrolujte, že verze v navbar zobrazuje správnou verzi
   - Otestujte základní funkce

## Doporučený workflow pro vývoj

1. **Vývoj nových funkcí:**
   - Vytvořte testovací verzi pomocí Git worktree (Možnost 1)
   - Vyvíjejte a testujte v testovací verzi
   - Commit změn do test branch

2. **Testování:**
   - Spusťte testovací server na portu 8002
   - Spusťte produkční server na portu 8000
   - Testujte obě verze současně

3. **Nasazení do produkce:**
   - Po úspěšném testování merge změn do main branch
   - Aktualizujte produkční verzi podle postupu výše

## Správa verzí

### Formát verzí

Verze jsou ve formátu: `MAJOR.MINOR.PATCH`
- **MAJOR**: Velké změny, breaking changes
- **MINOR**: Nové funkce, zpětně kompatibilní
- **PATCH**: Opravy chyb

### Změna verze

1. Upravte soubor `VERSION`:
   ```
   2.2.1
   ```

2. Verze se automaticky načte do aplikace:
   - Backend: `VERSION.py` načte verzi ze souboru `VERSION`
   - Frontend: API endpoint `/version` vrací aktuální verzi
   - Navbar: Zobrazuje verzi automaticky

### Testovací verze

Pro testovací verzi použijte suffix:
- `2.2.0-test`
- `2.2.0-dev`
- `2.2.0-beta`

## Troubleshooting

### Problém: Nelze spustit obě verze současně

**Řešení:**
- Ujistěte se, že používají jiné porty
- Zkontrolujte `.env` soubory v obou verzích
- Použijte jiné databáze (jiný název souboru `vehicles.db`)

### Problém: Změny se neprojevují v produkci

**Řešení:**
- Zkontrolujte, že jste v správné složce
- Ověřte, že jste commitli změny v testovací verzi
- Ujistěte se, že jste provedli merge do main branch
- Restartujte produkční server

### Problém: Konflikt verzí

**Řešení:**
- Vždy zálohujte databázi před aktualizací
- Použijte Git pro správu verzí
- Ověřte změny v testovací verzi před nasazením

## Doporučení

1. **Vždy používejte Git pro správu verzí**
2. **Zálohujte databázi před každou aktualizací**
3. **Testujte v testovací verzi před nasazením do produkce**
4. **Používejte Git worktree pro snadné přepínání mezi verzemi**
5. **Dokumentujte změny v commit messages**
6. **Zobrazujte verzi v aplikaci pro snadnou identifikaci**

## Kontakty a další informace

- Verze aplikace: Zobrazuje se v navbar-brand
- API endpoint verze: `GET /version`
- Verzní soubor: `VERSION` v kořenovém adresáři
- Verzní modul: `VERSION.py`



