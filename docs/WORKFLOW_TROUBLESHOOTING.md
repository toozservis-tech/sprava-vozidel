# Průvodce řešením problémů s GitHub Actions Workflows

## Jak poznat, že je problém?

### 1. **Vizuální indikace v GitHub UI**

Jdi na: **https://github.com/toozservis-tech/TOOZHUB2/actions**

**Zelená ✓ = OK**
- Workflow proběhl úspěšně
- Všechny testy prošly

**Červená ✗ = PROBLÉM**
- Workflow selhal
- Některé testy neprošly
- **Musíš to opravit ručně!**

**Žlutá ⚠ = Částečný problém**
- Workflow proběhl, ale s varováními
- Některé testy selhaly, ale workflow pokračoval (`continue-on-error: true`)

### 2. **Email notifikace (pokud máš zapnuté)**

GitHub ti může posílat emaily, když workflow selže:
- **Settings** → **Notifications** → **Actions**
- Zapni: "Workflow runs" → "Failed workflows only"

### 3. **Badge na README (volitelné)**

Můžeš přidat badge do README.md, který ukazuje stav workflow:

```markdown
![Production Smoke Tests](https://github.com/toozservis-tech/TOOZHUB2/workflows/Production%20Smoke%20Tests/badge.svg)
```

## Co dělat, když workflow selže?

### Krok 1: Zjistit, co selhalo

1. Jdi do **Actions** → klikni na **červený run**
2. Klikni na **failed job** (červený)
3. Klikni na **failed step** (červený)
4. **Přečti si logy** - tam uvidíš přesnou chybu

### Krok 2: Typické problémy a řešení

#### ❌ **Login selhal**
```
Error: Login failed
```

**Příčina:**
- Špatné credentials v GitHub Secrets
- Produkční server je nedostupný
- Změnilo se heslo

**Řešení:**
1. Zkontroluj GitHub Secrets (`PROD_E2E_EMAIL`, `PROD_E2E_PASSWORD`)
2. Ověř, že credentials fungují na https://hub.toozservis.cz
3. Aktualizuj secrets, pokud je potřeba

#### ❌ **Produkční server nedostupný**
```
Error: net::ERR_CONNECTION_REFUSED
Error: 500 Internal Server Error
```

**Příčina:**
- Produkční server je down
- Server restartuje
- Síťové problémy

**Řešení:**
1. Zkontroluj, že https://hub.toozservis.cz běží
2. Zkontroluj logy serveru
3. Restartuj server, pokud je potřeba

#### ❌ **UI změny - selektory nefungují**
```
Error: locator('[data-testid="vehicles-container"]') not found
```

**Příčina:**
- Změnilo se UI
- Chybí `data-testid` atributy
- Změnila se struktura HTML

**Řešení:**
1. Otevři Playwright report v artefaktech
2. Podívej se na screenshot - co se změnilo?
3. Oprav `data-testid` atributy v HTML
4. Nebo uprav testy v `tests/e2e/prod-smoke.spec.ts`

#### ❌ **Timeout**
```
Error: Timeout 30000ms exceeded
```

**Příčina:**
- Server je pomalý
- Síť je pomalá
- UI se načítá dlouho

**Řešení:**
1. Zkontroluj výkon serveru
2. Zvyš timeout v testech (pokud je to oprávněné)
3. Optimalizuj načítání UI

### Krok 3: Opravit problém

**Workflow NEOpravuje automaticky!** Musíš:

1. **Identifikovat problém** (z logů)
2. **Opravit kód/server/konfiguraci** lokálně
3. **Otestovat lokálně:**
   ```powershell
   # Spusť lokální testy
   .\scripts\qa_run.ps1
   ```
4. **Commitnout a pushnout:**
   ```powershell
   git add .
   git commit -m "Fix: [popis opravy]"
   git push origin master
   ```
5. **Workflow se spustí automaticky** a ověří, že oprava funguje

### Krok 4: Ověřit opravu

1. Počkej, až workflow dokončí (2-5 minut)
2. Zkontroluj, že je teď **zelený ✓**
3. Pokud stále selhává, zopakuj kroky 1-3

## Jak zjistit detaily problému?

### 1. **Playwright HTML Report**

V artefaktech najdeš:
- **Screenshoty** z failed testů
- **Videa** z testů
- **Timeline** - co se stalo krok po kroku
- **Console logy** z prohlížeče

**Jak získat:**
1. Actions → failed run → **Artifacts**
2. Stáhni `prod-smoke-artifacts`
3. Rozbal ZIP
4. Otevři `playwright-report/index.html` v prohlížeči

### 2. **GitHub Actions Logy**

V každém kroku workflow:
- **Expand log** - zobrazí celý výstup
- **Search** - hledej "Error", "Failed", "Exception"
- **Download log** - stáhni celý log

### 3. **Lokální testování**

Spusť stejné testy lokálně:

```powershell
# Nastav env proměnné
$env:BASE_URL = "https://hub.toozservis.cz"
$env:E2E_EMAIL = "toozservis@gmail.com"
$env:E2E_PASSWORD = "123456"
$env:E2E_READONLY = "1"

# Spusť testy
cd tests/e2e
npx playwright test prod-smoke.spec.ts --headed
```

## Automatické notifikace (doporučeno)

### Zapni email notifikace:

1. GitHub → **Settings** (tvůj profil)
2. **Notifications** → **Actions**
3. Zapni: **"Workflow runs"** → **"Failed workflows only"**

### Nebo použij GitHub Mobile App:

- Push notifikace při selhání workflow

## Monitoring a prevence

### Pravidelně kontroluj:

1. **Každý den ráno:** Zkontroluj Actions (zda včerejší noční run prošel)
2. **Po každém deploy:** Zkontroluj, že smoke testy prošly
3. **Při změnách UI:** Ověř, že testy stále fungují

### Nastav si připomínku:

- Google Calendar: každý den 08:00 - "Zkontroluj GitHub Actions"
- Nebo použij GitHub Mobile App notifikace

## Shrnutí

✅ **Workflow detekuje problémy** - automaticky  
❌ **Workflow NEOpravuje problémy** - musíš ručně  
📧 **Dostaneš notifikaci** - pokud máš zapnuté  
📊 **Máš reporty** - v artefaktech  
🔧 **Opravíš lokálně** - pak pushneš a workflow ověří

**Workflow je tvůj "hlídač" - když něco selže, řekne ti to, ale opravit to musíš sám!**

