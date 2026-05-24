# Technický rename – fáze 1 (bezpečný audit + skupina A)

**Cíl:** odstranit zbytečné interní zbytky starého názvu tam, kde změna **nerozbije** env, storage, push, systemd, iOS ani importy.

**Skupiny**

- **A** – bezpečně změněno v této fázi  
- **B** – vyžaduje kompatibilní migraci (čtení starého + nového, nasazení, teprve pak odstranění)  
- **C** – zatím neměnit (data v DB, kontrakty, produkční cesty)

---

## 1. Tabulka technických zbytků (výběr kritických)

| Identifikátor | Soubor(y) | Typ | Riziko | Fáze 1? | Proč |
|---------------|-----------|-----|--------|---------|------|
| `TOOZHUB_API_URL`, `TOOZHUB_ADMIN_*` | `src/core/config.py`, licensing, `license_status.py`, `.env.example` | env klíče | vysoké | **Ne** | produkční `.env` a skripty |
| `toozhub_api_url`, `toozhub_*_view_mode`, … | `web/index.html`, `reset-password.html`, `cookies.html` | localStorage / sessionStorage | vysoké | **Ne** | existující prohlížeče drží staré klíče |
| `TOOZHUB_NOTIFICATION_CLICK` | `web/index.html` | postMessage typ (SW ↔ stránka) | střední | **Ne** | starý service worker |
| `SPRAVA_VOZIDEL_NOTIFICATION_CLICK` | `web/sw.js`, `web/index.html` | postMessage typ | nízké | už hotovo | nový kanonický typ |
| `TooZHubiOS`, `Sources/TooZHub/`, `TooZHubApp.swift` | `ios/**`, `project.yml`, `project.pbxproj` | Xcode / bundle / cesty | vysoké | **Ne** | signing, App Store, build |
| `toozservis-tech/TOOZHUB2` | `docs/**`, `.github/scripts/...` | Git remote URL | vysoké | **Ne** | skutečný repozitář |
| `toozhub-server`, `toozhub2.service`, `/opt/toozhub2/` | `NASAZENI_*.md`, historické reporty | systemd / deploy cesty | střední | **Ne** | musí odpovídat reálnému serveru |
| `.toozhub_webnode_config.json` | `webnode_auto_upload.py`, `webnode_learn_steps.py`, `setup_webnode_interactive.py` | uživatelská konfigurace | střední | **Ne** | ztráta uložených údajů operátora |
| `/tmp/toozhub_webnode_upload.lock` | `webnode_auto_upload.py`, `webnode_auto_watcher.py` | lock soubor | střední | **Ne** | paralelní běh starých verzí skriptů |
| `deleted+...@deleted.toozhub.local` | `src/server/admin_api.py` | syntetický e-mail | střední | **Ne** | může být v DB u smazaných účtů |
| Výchozí JWT (jen bez `JWT_SECRET_KEY` v .env) | `config.py`, `bootstrap.py`, `config_validator.py` | dev placeholder | nízké | **Ano** | neprodukční default; produkce má vlastní klíč |
| Prefix temp dir / název ZIP exportu uživatele | `main_helpers.py` | souborový systém | nízké | **Ano** | `/tmp` prefix; nové názvy stažených souborů |
| Název ZIP control center backup | `admin_api.py` | HTTP download | nízké | **Ano** | pouze název souboru v odpovědi |
| `tag` test push | `push.py` | Web Push tag | nízké | **Ano** | jen testovací endpoint |
| `toozhub-watermark` | `web/security_protection.js` | DOM `id` | nízké | **Ano** | interní, bez externího kontraktu |
| `toozhub_export_*.zip` (klient) | `web/index.html` | název staženého souboru | nízké | **Ano** | uživatelsky viditelné, ne storage klíč |
| Screenshot cesty E2E | `scripts/e2e_browser_agent.py` | /tmp soubory | nízké | **Ano** | pouze vývoj |
| Text v `test_smtp*.py` | `test_smtp.py`, `test_smtp_simple.py` | nápověda v printu | nízké | **Ano** | obecná formulace místo názvu jednotky |

---

## 2. Co bylo ve fázi 1 bezpečně přejmenováno (skupina A)

- Výchozí řetězec JWT (pouze pokud není nastaven `JWT_SECRET_KEY`): `sprava-vozidel-dev-secret-change-in-production` v `src/core/config.py`, `src/server/bootstrap.py`, `src/core/config_validator.py`.
- Export uživatele: prefix dočasného adresáře a název ZIP v `src/server/main_helpers.py` → `sprava_vozidel_export_*`.
- Control center backup ZIP: `src/server/admin_api.py` → `sprava-vozidel-backup-{id}.zip`.
- Test push tag: `src/modules/vehicle_hub/routers_v1/push.py` → `sprava-vozidel-test`.
- Vodoznak: `web/security_protection.js` → id `sprava-vozidel-watermark`.
- Klient-side název exportu ZIP: `web/index.html`.
- E2E screenshoty: `scripts/e2e_browser_agent.py` → `/tmp/sprava_vozidel_ui_flow_*.png`.
- Nápověda systemd v `test_smtp.py` / `test_smtp_simple.py` → generický placeholder (bez konkrétního legacy názvu jednotky).

---

## 3. Co zůstávalo kvůli kompatibilitě po fázi 1 (B + C)

Po **fázi 2** jsou níže uvedené položky **storage / env / push / Webnode** řešeny dualním čtením a kanonickým zápisem – viz **`TECHNICAL_RENAME_PHASE2.md`**. Zde zůstává kontext původního auditu:

- ~~Všechny **env** klíče pouze `TOOZHUB_*`~~ → nyní aliasy `SPRAVA_VOZIDEL_*` + fallback.
- ~~Pouze **localStorage** `toozhub_*`~~ → nyní `sprava_vozidel_*` + fallback a migrace při čtení.
- **Typ** `TOOZHUB_NOTIFICATION_CLICK` – stále přijímán ve frontendu; SW preferuje nový typ.
- **iOS** struktura `TooZHub*` (target, složky, schémata, skripty).
- **GitHub** URL s `TOOZHUB2`.
- ~~Webnode jen stará cesta~~ → kanonická cesta + načtení/zrcadlení legacy.
- **admin_api** doména `deleted.toozhub.local` pro anonymizované e-maily.
- **Dokumentace** popisující reálné produkční cesty `/opt/toozhub2/` a jednotky `toozhub-server` – dokud se server fyzicky nepřejmenuje.

---

## 4. Plán fáze 2 → realizace

Původní tabulka zůstává jako historický návrh; **implementace** je popsána v **`TECHNICAL_RENAME_PHASE2.md`**.

| Oblast | Stav |
|--------|------|
| localStorage | Hotovo (`storage_migration.js` + web stránky). |
| env | Hotovo (`env_prefer_new`, config + licensing + license_status). |
| push | Hotovo (kanonický typ ve `sw.js`, dual příjem v `index.html`). |
| webnode | Hotovo (`webnode_paths.py`, skripty). |
| systemd | **Ne** ve fázi 2 (záměr – vyžaduje okno na serverech). |

---

## 5. Ověření po fázi 1

```bash
cd /cesta/k/source-mirror/app
PYTHONPATH=. python3 -c "from src.server.main import app; print(app.title)"
python3 -m compileall -q src
```

Volitelně: `bash scripts/qa/run_post_change_validation.sh --profile fast` (vyžaduje dostupný backend dle profilu).

---

## 6. Související dokumenty

- `PROJECT_RENAME_STATUS.md` – celkový stav brandu a odkaz na fáze  
- `TECHNICAL_RENAME_BACKLOG.md` – backlog + doplnění po fázích  
- `TECHNICAL_RENAME_PHASE2.md` – kompatibilní migrace kontraktů (fáze 2)  
