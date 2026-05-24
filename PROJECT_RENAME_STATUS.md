# Stav přejmenování na „Správa vozidel“

Oficiální název produktu je **Správa vozidel**. Tento dokument shrnuje, co už bylo sjednoceno a co zůstává záměrně legacy z kompatibility.

## Přejmenováno okamžitě (uživatelsky / provozně viditelné)

- **Centrální branding:** `src/core/branding.py` – `APP_DISPLAY_NAME`, `APP_API_DISPLAY_NAME`, tokeny pro HTTP `Server` a User-Agent (`APP_SERVER_PRODUCT_TOKEN`), web push typ zprávy, název file-share miniaplikace.
- **Backend:** OpenAPI titulek (přes bootstrap), `/health` pole `project`, middleware hlavička `Server`, push titulky připomínek, poznámky u autopilot záznamů, docstringy modulů, file-share HTML/API titulky, geolokační User-Agent řetězce.
- **Web:** `sw.js` – nový typ `postMessage` `SPRAVA_VOZIDEL_NOTIFICATION_CLICK` (stránka akceptuje i starý typ pro přechodnou kompatibilitu se starým service workerem).
- **Desktop (legacy Qt):** `src/app/main.py` – titulek okna a záhlaví.
- **Tray:** `tray/tray_app.py`, `tray/tray_manager.py`, `tray/README.md`, `start_tray.bat`, `start_tray_hidden.vbs` – zobrazené názvy a názvy zástupců (`SpravaVozidel_tray.lnk`).
- **Skripty / E2E metadata:** výpisy v `webnode_auto_upload.py`, `webnode_learn_steps.py`, `license_clickthrough.py`, `e2e_browser_agent.py`, `kontrolatachometru_cli.py`, `tests/e2e/package.json`.
- **Dokumentace:** hromadná úprava `.md` souborů (kromě řádků s živými URL na `github.com/.../TOOZHUB2`, které odpovídají skutečnému repozitáři).
- **Verze:** `VERSION.py` – `__version_name__` ve tvaru `Správa vozidel <semver>`.

## Zůstává technicky beze změny (záměr)

- **GitHub URL a slug repozitáře** `toozservis-tech/TOOZHUB2` v dokumentaci a výchozí hodnotě `GITHUB_REPOSITORY` – dokud se repozitář na GitHubu fyzicky nepřejmenuje.
- **iOS / Xcode:** cílový název `TooZHubiOS`, složka `Sources/TooZHub/`, bundle identifier – vyžaduje změnu v Apple Developer / projektu.
- **Interní Python cesty** `src.modules.vehicle_hub` atd. – nejsou uživatelsky viditelné; refaktor až v samostatné větvi.

### Env a storage po fázi 2 (dual support)

- **Proměnné prostředí:** kód preferuje `SPRAVA_VOZIDEL_*`, s fallbackem na `TOOZHUB_*` (deprecated). Staré klíče v `.env` dál fungují – viz `TECHNICAL_RENAME_PHASE2.md`.
- **localStorage:** preferuje se prefix `sprava_vozidel_*`, čtení fallbackuje `toozhub_*` a při čtení z legacy se hodnota kopíruje do nového klíče – viz `web/storage_migration.js`.
- **Push:** nový SW posílá `SPRAVA_VOZIDEL_NOTIFICATION_CLICK`; stránka stále přijímá i `TOOZHUB_NOTIFICATION_CLICK` pro starý service worker v cache.

## Proč část identifikátorů zůstává (GitHub, iOS, importy)

- Zabránit rozbití CI a existujících odkazů na skutečný GitHub slug.
- Přejmenování iOS bundle ID a složek vyžaduje koordinaci s App Store a vývojářským účtem.

## Technický rename – fáze 1 (dokončeno v repo)

Bezpečná úprava interních identifikátorů **bez** změny env klíčů, localStorage, push typů, iOS projektu ani GitHub URL.

- Detailní audit tabulka, skupiny A/B/C a plán fáze 2: **`TECHNICAL_RENAME_PHASE1.md`**.
- Provedeno mimo jiné: nový text výchozího dev JWT (pouze když chybí `JWT_SECRET_KEY`), prefixy a názvy exportních ZIPů, název admin backup ZIPu, testovací Web Push tag, DOM id vodoznaku v `security_protection.js`, klient-side název exportu v `index.html`, cesty E2E screenshotů, obecná nápověda v `test_smtp*.py`.

## Technický rename – fáze 2 (dokončeno v repo)

Kompatibilní migrace: web storage, env aliasy, push typ (příjem), Webnode config/lock. Detail mapování a fallbacků: **`TECHNICAL_RENAME_PHASE2.md`**.

## Další krok (fáze 3)

Podrobný backlog a zbývající položky: **`TECHNICAL_RENAME_BACKLOG.md`**.  
Tvrdé odstranění legacy env/storage/push fallbacků až po přechodné době a migraci hostů.
