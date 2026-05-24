# Nastavení GitHub Secrets pro Production Smoke Tests

## Rychlý postup

1. **Otevři GitHub repozitář v prohlížeči**
   - URL: `https://github.com/[TVAJE-ORGANIZACE]/TOOZHUB2`

2. **Jdi do Settings**
   - Klikni na "Settings" v horním menu repozitáře

3. **Otevři Secrets**
   - V levém menu: "Secrets and variables" → "Actions"

4. **Přidej Secrets**
   - Klikni na "New repository secret"
   - Přidej tyto dva secrets:

   **Secret 1:**
   - Name: `PROD_E2E_EMAIL`
   - Secret: `[tvůj-produkční-email]` (např. `toozservis@gmail.com`)

   **Secret 2:**
   - Name: `PROD_E2E_PASSWORD`
   - Secret: `[tvůj-produkční-heslo]`

5. **Ověř, že secrets jsou nastavené**
   - Měly by se zobrazit v seznamu (ale hodnoty nejsou viditelné)

## Spuštění workflow

### Automatické spuštění
- Workflow se spustí automaticky při push na `main` branch
- Workflow se spustí automaticky každý den v 03:30 (Europe/Prague)

### Ruční spuštění
1. Jdi do "Actions" v GitHub repozitáři
2. V levém menu vyber "Production Smoke Tests"
3. Klikni na "Run workflow"
4. Vyber branch (obvykle `main`)
5. Klikni na zelené tlačítko "Run workflow"

## Ověření, že to funguje

Po spuštění workflow:
1. Jdi do "Actions" → "Production Smoke Tests"
2. Klikni na nejnovější run
3. Zkontroluj, že všechny kroky prošly (zelené ✓)
4. Pokud selhalo, zkontroluj logy a ujisti se, že secrets jsou správně nastavené

## Troubleshooting

**Workflow selhává na login:**
- Zkontroluj, že `PROD_E2E_EMAIL` a `PROD_E2E_PASSWORD` jsou správně nastavené
- Ověř, že credentials fungují na https://hub.toozservis.cz

**Workflow se nespouští:**
- Zkontroluj, že soubor `.github/workflows/prod-smoke.yml` je v repozitáři
- Zkontroluj, že máš oprávnění spouštět workflows

