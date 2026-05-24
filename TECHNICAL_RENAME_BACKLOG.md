# Technický backlog přejmenování (legacy identifikátory)

Cíl: postupně odstranit historické názvy **TooZHub2 / TOOZHUB2 / TooZ Hub** z technické vrstvy bez výpadku provozu.

| Oblast | Současný stav | Priorita | Riziko | Doporučený postup |
|--------|----------------|----------|--------|-------------------|
| GitHub repozitář | Remote `toozservis-tech/TOOZHUB2` | Střední | Vysoké (CI, lokální remote, odkazy) | Přejmenovat repo v GitHub UI, aktualizovat `origin`, dokumentaci a výchozí `GITHUB_REPOSITORY`; dočasně redirect GitHub obvykle zachová. |
| Env proměnné | `TOOZHUB_*` + **`SPRAVA_VOZIDEL_*` (preferováno)** | Střední | Střední (prod .env) | **Fáze 2 hotovo:** `env_prefer_new` v `src/core/env_aliases.py`; fáze 3: odebrat fallback po migraci `.env` na všech hostech. |
| iOS target / modul | `TooZHubiOS`, `TooZHub` sources, PRODUCT_NAME | Vysoká | Vysoká (signing, App Store) | Přejmenovat v `project.yml` / Xcode, aktualizovat bundle ID ve vývojářském účtu, nová build konfigurace. |
| Python balíček / moduly | `src.modules.vehicle_hub`, import cesty | Nízká | Velmi vysoká | Neprovádět slepě; případně zavést tenký facade package a postupně přesouvat. |
| systemd / Windows úlohy | Dokumentace už používá `SpravaVozidel-*`; na serverech mohou běžet staré názvy úloh | Střední | Střední | Na každém hostu přejmenovat úlohy a skripty podle runbooku; ověřit po restartu. |
| Databáze / migrace | Žádný povinný sloupec s názvem produktu typicky neblokuje | Nízká | Nízká | Pouze pokud by existovaly řetězce v tabulkách – čistit datově odděleně. |
| Web push zpráva (legacy) | SW posílá `SPRAVA_VOZIDEL_NOTIFICATION_CLICK`; stránka přijímá i `TOOZHUB_NOTIFICATION_CLICK` | Nízká | Nízká | **Fáze 2:** dual příjem; fáze 3: odebrat legacy typ po zanedbatelném podílu starých SW. |
| Lokální cesty v docs | Část návodů používá `sprava-vozidel` místo historického `TOOZHUB2` | Nízká | Nízká | Sjednotit s reálnou cestou na discích vývojářů. |
| Web localStorage klíče | `toozhub_*` + **`sprava_vozidel_*` (preferováno)** | Střední | Střední | **Fáze 2 hotovo:** `web/storage_migration.js` + úpravy `index.html` / `reset-password.html`; fáze 3: odstranit legacy větev. |
| Webnode config / lock | `.toozhub_webnode_*` + **kanonické cesty v `scripts/webnode_paths.py`** | Střední | Střední | **Fáze 2 hotovo:** čtení legacy + zápis kanonický, dual lock; fáze 3: zjednodušit na jednu cestu. |

## Bezpečně už provedeno (nízké riziko)

- HTTP `Server` token, externí `User-Agent` řetězce volající třetí API.
- Veřejné API metadata (`FastAPI.title`, část health JSON).
- Zobrazované názvy v e-mail šablonách (přes `APP_DISPLAY_NAME`).

### Fáze 1 – technické zbytky (bez env / storage kontraktů)

Kompletní tabulka a klasifikace A/B/C: **`TECHNICAL_RENAME_PHASE1.md`**.

- Výchozí dev JWT placeholder (jen pokud není nastaven `JWT_SECRET_KEY` v prostředí).
- Prefix dočasného adresáře a názvy uživatelských exportních ZIPů (`main_helpers.py`).
- Název staženého souboru control center backupu (`admin_api.py`).
- Testovací Web Push tag (`push.py`).
- DOM id vodoznaku (`web/security_protection.js`).
- Název klientského exportu ZIP v `web/index.html`.
- Cesty vývojářských screenshotů (`e2e_browser_agent.py`).
- Obecná systemd nápověda v `test_smtp.py` / `test_smtp_simple.py` (bez konkrétního legacy názvu jednotky).

### Fáze 2 – kompatibilní kontrakty (storage, env, push příjem, Webnode)

Kompletní specifikace: **`TECHNICAL_RENAME_PHASE2.md`**.

- **Storage:** centrální helper `SpravaVozidelStorage` v `web/storage_migration.js`.
- **Env:** `SPRAVA_VOZIDEL_API_URL`, `SPRAVA_VOZIDEL_ADMIN_*` s fallbackem na `TOOZHUB_*`.
- **Push:** kanonický typ v `sw.js`; legacy typ stále v handleru v `index.html`.
- **Webnode:** `load_webnode_config_dict` / dual lock v `scripts/webnode_paths.py`.

## Ověření po změnách

```bash
cd /cesta/k/projektu
python -c "from src.server.main import app; print(app.title)"
```

Očekáváno: titulek obsahuje „Správa vozidel API“ (nebo ekvivalent z `branding`).
