# LOKÁLNÍ CURSOR – SPRÁVA VOZIDEL – KOMPLETNÍ RENAME VÝSLEDEK

Tento dokument je **požadovaný výstup** k řízenému přejmenování projektu na oficiální název **Správa vozidel**. Doplňuje `PROJECT_RENAME_STATUS.md` a `TECHNICAL_RENAME_BACKLOG.md` lidsky čitelným shrnutím.

---

## 1. Kde všude byl starý název

- **Web** – dříve v titulcích, notifikacích, service worker zprávách, některých textech a interních typech zpráv (push click).
- **iOS** – technické cesty a target (`TooZHubiOS`, `Sources/TooZHub/`); uživatelské řetězce byly již dříve bez starého brandu nebo byly sjednoceny.
- **Admin** – texty a metadata v souladu s backendem / web_admin (brand přes centrální konstanty na backendu a dokumentaci).
- **E-maily** – šablony a patičky dříve mohly obsahovat „TooZ Hub 2“; nyní jednotně přes `src/core/branding.py` a `email_client/templates.py`.
- **Notifikace** – push titulky (např. připomínky), výchozí titulky ve `sw.js`.
- **Exporty** – PDF/metadata kde se používá `APP_EXPORT_DISPLAY_NAME` / branding.
- **Dokumentace** – desítky `.md` souborů (runbooky, QA, GitHub, nasazení, právní diffy), skripty s výpisy do konzole.
- **Server / provoz** – OpenAPI `title`, `/health` pole `project`, HTTP hlavička `Server`, User-Agent u volání třetích služeb, file-share miniapp, tray/desktop popisky.
- **Technické identifikátory** – GitHub slug `TOOZHUB2`, env `TOOZHUB_*`, iOS bundle/target/složky, Python modulové cesty (`vehicle_hub` atd.), legacy typ web push zprávy pro kompatibilitu SW.

---

## 2. Co jsem přejmenoval hned na „Správa vozidel“

- **Centrální brand:** `src/core/branding.py` – `APP_DISPLAY_NAME`, odvozené názvy API/podpora/export, `APP_SERVER_PRODUCT_TOKEN`, `WEB_PUSH_CLIENT_MESSAGE_TYPE`, `APP_FILESHARE_DISPLAY_NAME`, `APP_OPS_PROJECT_LABEL`.
- **Backend runtime:** FastAPI titulek (bootstrap), `/health` → `project`, middleware `Server`, geolokační User-Agent, připomínkové push titulky, autopilot/AI docstringy a poznámky u záznamů, `fileshare.py` titulky a HTML, modulové docstringy (`config`, `auth`, `security`, `rbac`, licensing, push, email_notifications, bot, routers `__init__`).
- **Verze:** `VERSION.py` → `__version_name__` ve tvaru `Správa vozidel <verze>`; fallback v `main_helpers.py`.
- **Web:** `web/sw.js` – nový typ `SPRAVA_VOZIDEL_NOTIFICATION_CLICK`, tag notifikace; `web/index.html` – příjem nového typu + dočasný fallback `TOOZHUB_NOTIFICATION_CLICK`.
- **Desktop / tray:** `src/app/main.py`, `tray/tray_app.py`, `tray/tray_manager.py`, `tray/README.md`, `tray/start_tray.bat`, `tray/start_tray_hidden.vbs`.
- **Skripty:** mimo jiné `webnode_auto_upload.py`, `webnode_learn_steps.py`, `license_clickthrough.py`, `e2e_browser_agent.py`, `kontrolatachometru_cli.py`, `scripts/webnode_helper.html`.
- **Testy / CI metadata:** `tests/e2e/package.json`; komentář u `.github/scripts/analyze_failed_workflow.py`.
- **Dokumentace:** hromadná úprava **47+** souborů `.md` (product názvy, lokální cesty `TOOZHUB2` → `sprava-vozidel` kde to dávalo smysl); úpravy `README.md`, `PROJECT_NAMING_STATUS.md`, `NASAZENI_HUB_TOOZSERVIS.md`, `FACEBOOK_PRISPEVEK_SPUSTENI.md`, `docs/qa/CONTINUOUS_VALIDATION.md` atd.
- **Oprava kódu:** `src/server/version.py` – správné umístění importu `APP_DISPLAY_NAME`.

---

## 3. Co jsem ponechal technicky beze změny (nebo jen s komentářem)

- **GitHub:** URL a slug `toozservis-tech/TOOZHUB2` v dokumentaci a výchozí hodnota `GITHUB_REPOSITORY` ve skriptu (skutečný remote).
- **Prostředí:** `TOOZHUB_API_URL`, `TOOZHUB_ADMIN_TENANT_ID`, `TOOZHUB_ADMIN_FORCE_PREMIUM` v `.env.example` a v licenčním kódu.
- **iOS projekt:** název targetu `TooZHubiOS`, cesta `Sources/TooZHub/` v `project.yml` (bundle / struktura Xcode).
- **Web push:** ve `web/index.html` stále akceptován typ `TOOZHUB_NOTIFICATION_CLICK` pro staré nainstalované service workery.
- **Historické dokumenty:** odkazy na soubor `REKONSTRUKCE_TOOZHUB2.md` v archivních poznámkách; příkazy s `TOOZHUB2.git` v bezpečnostním postupu (mirror záloh).
- **Python balíčková struktura:** `src.modules.vehicle_hub` a import cesty beze změny.

---

## 4. Proč to zatím zůstává

- **Repo a env** – přejmenování bez koordinace by rozbilo CI, lokální `git remote`, produkční `.env` a existující runbooky.
- **iOS** – změna targetu/bundle ID vyžaduje Apple Developer a release plán.
- **Web push fallback** – krátké překrytí snižuje riziko nefunkčních kliků po nasazení, dokud se uživatelům neaktualizuje SW.
- **ENV názvy** – migrace na `SPRAVA_VOZIDEL_*` je samostatný krok s nasazením na všechny prostředí.

---

## 5. Jaké soubory jsem upravil (shrnutí podle oblastí)

| Oblast | Příklady cest |
|--------|----------------|
| Branding / verze | `src/core/branding.py`, `VERSION.py`, `src/server/main_helpers.py`, `src/server/version.py`, `src/server/routers/system.py` |
| Bezpečnost / HTTP | `src/core/security_middleware.py`, `src/server/security_tracking.py` |
| API routery / doména | `src/modules/vehicle_hub/routers_v1/reminders.py`, `services.py`, `bot.py`, `autopilot.py`, `ai.py`, `__init__.py` |
| Notifikace / e-mail | `src/modules/vehicle_hub/email_notifications.py`, `push_notifications.py` |
| Licensing / config | `src/modules/licensing/service.py`, `src/core/config.py`, `src/core/auth.py`, `src/core/security.py`, `src/core/rbac.py` |
| File share | `src/server/fileshare.py` |
| Desktop / tray | `src/app/main.py`, `tray/*` |
| Web | `web/sw.js`, `web/index.html` (řádek service worker zpráv) |
| Skripty | `scripts/webnode_*.py`, `scripts/*.html`, `scripts/kontrolatachometru_cli.py`, … |
| Testy | `tests/e2e/package.json` |
| CI | `.github/scripts/analyze_failed_workflow.py` |
| Dokumentace | `README.md`, `PROJECT_*.md`, `NASAZENI_*.md`, `docs/**/*.md` (včetně GitHub návodů s ponechanými URL), desítky dalších `.md` v kořeni repozitáře aplikace |

*(Úplný seznam řádkových změn je v git historii; výše jsou hlavní oblasti.)*

---

## 6. Jaké nové soubory jsem vytvořil

- `PROJECT_RENAME_STATUS.md` – co je hotové vs. legacy, proč, odkaz na backlog.
- `TECHNICAL_RENAME_BACKLOG.md` – tabulka technických identifikátorů, priority, rizika, doporučení.
- `RENAME_KOMPLETNI_VYSLEDEK.md` – **tento soubor** (požadovaný výstup sekcí 1–8).

Aktualizováno (obsahově přepsáno): `PROJECT_NAMING_STATUS.md` jako krátký rozcestník na výše uvedené.

---

## 7. Jak jsem ověřil, že se nic nerozbilo

- **Import aplikace:**  
  `PYTHONPATH=. python3 -c "from src.server.main import app; print(app.title)"`  
  → očekávaný titulek: **„Správa vozidel API“** (z branding + bootstrap).
- **Žádný slepý rename importů:** modulová cesta `src.server.main:app` beze změny; `vehicle_hub` a router registrace beze změny názvů balíčků.
- **Kontrola zbytků:** grep na uživatelské řetězce „TooZ Hub“ / `TooZHub2` v `src/**/*.py` → bez nálezu; zbývající `TOOZHUB2` / `TooZHub` jsou v dokumentaci (GitHub URL), status souborech, iOS `project.yml`, env proměnných a kompatibilním web push fallbacku.

*(Plný test suite nebyl v této session spuštěn; doporučení: `pytest` / CI podle vašeho profilu.)*

---

## 8. Jaký je další krok pro úplné vyčištění starého názvu z technické vrstvy

1. **GitHub:** přejmenovat repozitář (nebo založit nový), aktualizovat všechny `remote` URL a výchozí `GITHUB_REPOSITORY`.
2. **Env:** zavést aliasy `SPRAVA_VOZIDEL_*`, nasadit, poté odstranit `TOOZHUB_*`.
3. **iOS:** přejmenovat target, složku zdrojů a bundle ID v koordinaci s App Store Connect.
4. **Web push:** po dostatečné době / metrice odebrat `TOOZHUB_NOTIFICATION_CLICK` z `web/index.html`.
5. **Python architektura:** jen pokud bude produktový důvod – přejmenovat moduly (`vehicle_hub` → …) jako samostatný projekt s migrací importů.

Detailní plán: **`TECHNICAL_RENAME_BACKLOG.md`**.
