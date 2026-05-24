# Runtime diagnostika webu „Správa vozidel“

Tento dokument popisuje, co v prohlížeči sledovat po doplnění logů `[WEB_RUNTIME]` a `data-*` markerů v `web/index.html`.

## Co se má v browseru zkontrolovat

1. **Tvrdý refresh** (cache bypass): `Ctrl+Shift+R` (Linux/Windows) nebo `Cmd+Shift+R` (macOS), případně DevTools → Network → zaškrtnout „Disable cache“ a obnovit stránku.
2. **Správná URL** produkčního hubu (např. `https://hub.toozservis.cz/…` dle nasazení).
3. **Console** – filtr `WEB_RUNTIME` (nebo `[WEB_RUNTIME]`).
4. **Elements** – `document.body` a `#dashboard`, `#vehiclesContainer`, kontejner tachometru uvnitř modalu vozidla.
5. **Network** – po přihlášení: `/api/v1/vehicles`, deferred `/api/v1/system/capabilities`, po otevření detailu vozidla: `/api/v1/vehicles/{id}/tachometer/history`, v záložce Profil: `/user/me`.

## Přidané logy a atributy

### Konzole (`console.info`)

Prefix: **`[WEB_RUNTIME]`** (funkce `webRuntimeLog`).

| Fáze | Význam |
|------|--------|
| `boot:domcontentloaded` | DOM připraven, API URL inicializována |
| `boot:route_done` | Po větvi login vs. dashboard (`authenticated: true/false`) |
| `showDashboard:enter` / `showDashboard:aborted` | Vstup do dashboardu nebo návrat na login (neautentizováno) |
| `showDashboard:auth_ok` | Role, email, zda servisní workspace |
| `showDashboard:complete` | Dashboard DOM zobrazen, naplánován primární flow |
| `showLogin:dashboard_hidden` | Login UI, dashboard skrytý |
| `loadVehicles:*` | `fetch_start`, `ok` (count), `error`, `skip`, `cache_hit` |
| `tachometer:*` | `fetch_start`, `ok` (count vč. 0 = prázdná data), `error`, `skip` |
| `profile:*` | `fetch_start`, `ok`, `error`, `cache_hit`, `skip` |
| `capabilities:*` | `skip`, `cache_hit`, `fetch_ok`, `fetch_error`, `applied` |
| `switchTab:blocked_capability` | Tab zablokován hlášením o migraci / capabilities |

### `data-*` atributy

| Uzel | Atributy | Interpretace |
|------|-----------|--------------|
| `document.body` | `data-web-boot` | `domcontentloaded` → `dashboard_mounting` → `dashboard_visible` nebo `routed_login` / `routed_dashboard` po routě |
| `document.body` | `data-auth-present` | `1` / `0` po `boot:route_done` |
| `document.body` | `data-vehicles-state` | Jen při `no_container` na `#vehiclesContainer` |
| `document.body` | `data-capabilities-modules`, `data-capabilities-vehicles` | Po `loadSystemCapabilities`: počet modulů; `vehicles` = `ok` / `blocked` / `unknown` |
| `document.body` | `data-capability-block` | Nastaveno při zablokování tabu (`tab:moduleKey`); při úspěšném přepnutí tabu odstraněno |
| `#dashboard` | `data-dashboard-state`, `data-dashboard-rendered` | `mounting` → `visible` + `rendered=1`; při loginu `hidden` + `0` |
| `#vehiclesContainer` | `data-vehicles-state`, `data-vehicles-count`, příp. `data-vehicles-error` | `loading` → `ok`/`empty`/`error` nebo `cache_fresh` |
| `#profileContainer` | `data-profile-state`, příp. `data-profile-error` | `loading` → `ok` / `error` / `cache_fresh` |
| `#tachometer-history-modal-{id}` | `data-tachometer-state`, `data-tachometer-count`, `data-tachometer-vehicle-id`, příp. `data-tachometer-error` | Stav načtení historie STK/tachometru |

## Interpretace stavů (nejčastější scénáře)

- **`data-dashboard-rendered=1`** a **`showDashboard:complete`**: rozhraní dashboardu by mělo být vidět; pokud ne, hledejte CSS overlay, jiný tab aktivní, nebo chybu až v podsekci.
- **`data-vehicles-state=empty`** + `loadVehicles:ok count:0`**: API funguje, uživatel nemá vozidla – seznam je prázdný (očekávané).
- **`data-vehicles-state=error`**: Network/console u `/api/v1/vehicles` (401, 404, CORS, špatná `API_URL`).
- **`tachometer:ok count:0`** + `data-tachometer-state=empty`**: endpoint OK, žádná historie (ne chyba).
- **`tachometer:error`**: selhání `/tachometer/history` nebo parsování odpovědi.
- **`switchTab:blocked_capability`**: capability gating (modul nedostupný po migraci).
- **`showDashboard:auth_ok` s `serviceWorkspace: true`**: primární tok je `loadServiceWorkspace`, ne `loadVehicles` – prázdná „Vozidla“ může být v pořádku, dokud nepřepnete tab.

## Ověření ze serveru (volitelné)

```bash
# Health (bez tokenu)
curl -sS -o /dev/null -w "%{http_code}\n" https://HUB_HOST/api/v1/health

# Capabilities (vyžaduje platný Bearer)
curl -sS -H "Authorization: Bearer TOKEN" https://HUB_HOST/api/v1/system/capabilities

# Vozidla
curl -sS -H "Authorization: Bearer TOKEN" https://HUB_HOST/api/v1/vehicles

# Tachometr (konkrétní id)
curl -sS -H "Authorization: Bearer TOKEN" "https://HUB_HOST/api/v1/vehicles/VEHICLE_ID/tachometer/history"
```

## Nejpravděpodobnější root cause (v tomto repozitáři)

**Kód funkcí `getCapabilityModuleForTab`, `formatCapabilityHint`, `applySystemCapabilitiesUi` a `loadSystemCapabilities` byl omylem umístěn až za uzavírací tag `</html>`**, tedy mimo `<script>` – prohlížeč ho nevykonával. Důsledek: při volání `switchTab(...)` mohla nastat **`ReferenceError: getCapabilityModuleForTab is not defined`** a deferred úloha `system-capabilities` mohla padat na nedefinované `loadSystemCapabilities`. To vysvětluje „nic se neděje“ po kliknutí na taby a nekonzistentní UI. **Oprava:** přesun těchto funkcí do hlavního `<script>` bloku (před `switchTab`).

Doplňkově kontrolujte: **roli účtu** (servis vs. běžný uživatel), **JWT expiraci** (log `[APP] Token vypršel`), a **prázdný seznam vozidel** vs. chybu API.

## Upravené soubory

- `app/web/index.html` – diagnostické helpery (již dříve `webRuntimeLog` / `webRuntimeSetDiag`), rozšíření toků boot / dashboard / vozidla / tachometr / profil / capabilities / switchTab, **oprava umístění capabilities funkcí**.
- `app/WEB_RUNTIME_DIAGNOSTICS.md` – tento dokument.
