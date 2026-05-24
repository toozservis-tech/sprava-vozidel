# Technický rename – fáze 2 (kompatibilní migrace kontraktů)

**Cíl:** zavést nové technické identifikátory jako **preferované**, při čtení **fallback na legacy**, při zápisu **kanonické nové názvy**, bez rozbití session, push, uložených preferencí a provozních skriptů.

**Pravidla:** žádné natvrdo odstranění starých klíčů v této fázi; legacy je označené `@deprecated` v kódu / komentářích a zůstane do **fáze 3**.

---

## 1. Web storage (`localStorage`)

### Nový modul

- Soubor: `web/storage_migration.js`
- Globální API: `SpravaVozidelStorage.getLocal(name)`, `setLocal`, `removeLocal`
- Mapování logických jmen → `{ primary, legacy }` v `SpravaVozidelStorageKeys`

### Chování

| Operace | Chování |
|---------|---------|
| **Čtení** | Nejdřív `sprava_vozidel_*`; pokud prázdné/chybí → `toozhub_*`; při úspěšném čtení z legacy se hodnota **zkopíruje** do primárního klíče (migrace při čtení). |
| **Zápis** | Pouze primární klíč; legacy klíč se **odstraní** (`removeItem`). |
| **Odstranění** | Odstraní oba klíče. |

### Tabulka klíčů

| Logické jméno | Nový klíč (primární) | Legacy klíč |
|---------------|----------------------|---------------|
| `apiUrl` | `sprava_vozidel_api_url` | `toozhub_api_url` |
| `vehicleViewMode` | `sprava_vozidel_vehicle_view_mode` | `toozhub_vehicle_view_mode` |
| `reminderViewMode` | `sprava_vozidel_reminder_view_mode` | `toozhub_reminder_view_mode` |
| `reminderFilterMode` | `sprava_vozidel_reminder_filter_mode` | `toozhub_reminder_filter_mode` |
| `reminderCalendarMonth` | `sprava_vozidel_reminder_calendar_month` | `toozhub_reminder_calendar_month` |
| `reminderNotificationCheckAt` | `sprava_vozidel_reminder_notification_check_at` | `toozhub_reminder_notification_check_at` |

### Integrace ve webu

- `web/index.html` – načtení `storage_migration.js` před hlavním skriptem; čtení/zápis výše uvedených hodnot přes helper (s lokálním fallbackem, pokud by skript chyběl).
- `web/reset-password.html` – API URL přes stejný helper.
- `web/cookies.html` – tabulka klíčů aktualizována + poznámka k legacy.

### Fáze 3 (odstranění)

- Odstranit legacy klíče z mapování a přímé fallbacky v HTML; případně jednorázově vyčistit staré položky u klientů (volitelné).

---

## 2. Proměnné prostředí (env aliasy)

### Helper

- `src/core/env_aliases.py` – `env_prefer_new(*names)`, `env_flag_prefer_new(...)`.
- První **neprázdná** hodnota v uvedeném pořadí vyhrává (nový název má přednost).

### Mapování (nový → legacy, deprecated)

| Účel | Preferovaný klíč | Fallback (deprecated) |
|------|------------------|------------------------|
| Veřejná / klientská API URL | `SPRAVA_VOZIDEL_API_URL` | `TOOZHUB_API_URL` |
| Admin tenant (licence) | `SPRAVA_VOZIDEL_ADMIN_TENANT_ID` | `TOOZHUB_ADMIN_TENANT_ID` |
| Admin force premium | `SPRAVA_VOZIDEL_ADMIN_FORCE_PREMIUM` | `TOOZHUB_ADMIN_FORCE_PREMIUM` |

### Použití v kódu

- `src/core/config.py` – `BASE_API_URL` z nového + fallback.
- `src/modules/licensing/service.py` – admin proměnné.
- `src/modules/licensing/license_service.py` – admin tenant.
- `src/modules/vehicle_hub/routers_v1/license_status.py` – URL helpery.

### Dokumentace pro provoz

- `.env.example` – sekce `SPRAVA_VOZIDEL_*` + komentář, že `TOOZHUB_*` jsou deprecated, ale stále podporované.

### Fáze 3

- Po migraci všech hostů na nové názvy: odstranit fallback v kódu a zmínky o starých klíčích (ne dříve).

---

## 3. Push / service worker (`postMessage` typ)

| Role | Typ | Poznámka |
|------|-----|----------|
| **Kanonický (nový SW)** | `SPRAVA_VOZIDEL_NOTIFICATION_CLICK` | Odesílá `web/sw.js`. |
| **Legacy (starý SW v cache)** | `TOOZHUB_NOTIFICATION_CLICK` | Stále **přijímán** v `web/index.html` – stejný handler jako u kanonického typu. |

Záměrně **ne** posíláme oba typy z jednoho SW (aby se handler nespustil dvakrát). Kompatibilita je na straně **příjemce**.

### Fáze 3

- Po doložení zanedbatelného podílu starých SW odebrat větev pro `TOOZHUB_NOTIFICATION_CLICK`.

---

## 4. Webnode (config + lock)

Modul: `scripts/webnode_paths.py`.

| Artefakt | Kanonická cesta | Legacy (fallback) |
|----------|-----------------|-------------------|
| Config JSON | `~/.sprava_vozidel_webnode_config.json` | `~/.toozhub_webnode_config.json` |
| Lock (upload) | `/tmp/sprava_vozidel_webnode_upload.lock` | `/tmp/toozhub_webnode_upload.lock` |

- **Čtení configu:** existuje-li kanonický soubor → ten; jinak legacy. Po načtení z legacy se obsah **zrcadlí** do kanonického souboru (stejný raw JSON), chmod `600` kde lze.
- **Zápis:** vždy kanonická cesta.
- **Lock:** `acquire_webnode_lock_dual` – exkluzivní zámek **nejprve legacy, pak kanonický**, aby se vyloučily staré i nové verze skriptů navzájem.

Skripty používající modul: `webnode_auto_upload.py`, `webnode_learn_steps.py`, `setup_webnode_interactive.py`; watcher kontroluje oba lock soubory.

### Fáze 3

- Po přechodné době lze přestat číst/zakládat legacy config a legacy lock (nejdřív metriky / absence hlášení).

---

## 5. Co záměrně nebylo měněno (stejně jako ve fázi 1)

- systemd názvy jednotek, bundle ID, Git remote URL, Python import cesty (`src.modules.vehicle_hub`), názvy DB objektů.

---

## 6. Ověření po fázi 2

```bash
cd /cesta/k/source-mirror/app
PYTHONPATH=. python3 -c "from src.server.main import app; print(app.title)"
python3 -m compileall -q src
```

**Manuální / prohlížeč (doporučeno):**

- Po deployi: v DevTools ověřit, že při existujícím `toozhub_api_url` aplikace funguje a po interakci se objeví / přepíše `sprava_vozidel_api_url`.
- Push: klik z notifikace funguje s novým SW; starý SW stále doručí legacy typ → stránka zpracuje.

**Webnode:** spustit `setup_webnode_interactive` nebo upload s existujícím `~/.toozhub_webnode_config.json` – očekává se načtení a zrcadlení do `~/.sprava_vozidel_webnode_config.json`.

---

## 7. Související dokumenty

- `PROJECT_RENAME_STATUS.md` – stav brandu a fází
- `TECHNICAL_RENAME_BACKLOG.md` – backlog + co zbývá
- `TECHNICAL_RENAME_PHASE1.md` – audit fáze 1 a kontext skupin A/B/C

---

## 8. Manuální QA checklist (finální kontrola před nasazením)

Krátký seznam pro release engineer po deployi nového frontendu + backendu z větve obsahující fázi 2.

### Web storage migrace

- [ ] V DevTools → Application → Local Storage nastavit pouze legacy `toozhub_api_url` (a případně `toozhub_vehicle_view_mode`), kanonické `sprava_vozidel_*` smazat nebo nepoužívat.
- [ ] Obnovit `/web/`, přihlásit se: aplikace se připojí ke správnému API.
- [ ] Po uložení URL nebo přepnutí zobrazení vozidel zkontrolovat, že vznikl / doplnil se `sprava_vozidel_*` a při zápisu mizí odpovídající `toozhub_*`.

### Env aliasy

- [ ] Na stagingu nastavit jen `SPRAVA_VOZIDEL_API_URL` (bez `TOOZHUB_API_URL`) a ověřit start aplikace a licence/redirect URL dle potřeby.
- [ ] Stejný host s pouze `TOOZHUB_API_URL` (bez nového klíče): aplikace stále naběhne a čte URL správně.
- [ ] Admin bypass: ověřit kombinaci `SPRAVA_VOZIDEL_ADMIN_*` resp. fallback `TOOZHUB_ADMIN_*` podle interního postupu (ne na produkci bez schválení).

### Push compatibility

- [ ] Registrovat SW, povolit notifikace, vyvolat notifikaci (test nebo reálná připomínka).
- [ ] Klik z notifikace otevře očekávanou stránku (handler akceptuje `SPRAVA_VOZIDEL_NOTIFICATION_CLICK` i legacy `TOOZHUB_NOTIFICATION_CLICK`).

### Webnode legacy config fallback

- [ ] Ponechat jen `~/.toozhub_webnode_config.json`, dočasně odstranit `~/.sprava_vozidel_webnode_config.json` (záloha!).
- [ ] Spustit `scripts/webnode_auto_upload.py` (nebo interaktivní setup načítající config): skript načte legacy soubor a vytvoří / doplní kanonický `~/.sprava_vozidel_webnode_config.json`.
- [ ] Ověřit, že druhá souběžná instance uploadu je odmítnuta (dual lock na obou cestách v `/tmp`).
