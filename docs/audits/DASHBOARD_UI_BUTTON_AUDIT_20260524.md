# Dashboard UI & Button Audit — Přehled (2026-05-24)

## 1. Actionable Solution

### Scope

Audit a implementace uživatelské sekce **Přehled** po přihlášení v repozitáři `toozservis-tech/sprava-vozidel`. Vývoj probíhal výhradně v checkoutu `/opt/sprava-vozidel-dev` na větvi `audit/dashboard-prehled-20260524` (základ `main` @ `998cbb1a1d6aaada5e9cc9d1bffdd930822c115d`).

Screenshot `uvod po přihlášení.png` sloužil jako **vizuální reference** (layout, barvy, spacing). Produktová pravda funkcí zůstává v kódu repozitáře (včetně položky **Objednat servis** v sidebaru).

### Verdict: **PASS**

| Oblast | Před | Po |
|--------|------|-----|
| Vizuál Přehled vs. screenshot | ~80 % | PASS — doladění CSS, help, CTA, primární modrá |
| Funkční kliky | FAIL: Cmd+K, F5 service-history, karta neklikatelná | PASS — opraveno |
| `data-testid` / statické testy | minimální | PASS |
| E2E Playwright | chyběl spec | PASS — 8/8 `dashboard-prehled.spec.ts` |

### Opraveno

1. **Deep link Servisní historie** — `userTabFromAppSection` / `userAppSectionFromTab` v `web/index.html`; detekce URL v `getActiveView()` a boot v `web/user-app-next.js`.
2. **Cmd/Ctrl+K** — `bindSearchShortcut()` fokusuje `#uappNextSearch`; dynamický label ⌘ K / Ctrl K.
3. **Klikací karta vozidla** — tlačítko `.uapp-next-vehicle-open` → `detail:{id}`; akční lišta zůstává oddělená.
4. **Label Sdílet** — text akce na kartě vozidla (funkce `shareVehicle` beze změny).
5. **Nápověda v sidebaru** — sjednocený styl (ikona ?, text „Nápověda“); `help` → `openHowToHubModal` nebo fallback support.
6. **`data-testid`** — prefix `dashboard-*` na navigaci, topbaru, hero, quick kartách, vozidlech, aside, chybovém stavu.
7. **Loading/error** — retry tlačítko při selhání `render()`.
8. **Testy** — `test_service_history_deep_link_contract`, `test_dashboard_overview_testids_present`, nový `tests/e2e/dashboard-prehled.spec.ts`.

### Otevřené / návrhy (neblokující)

- **Spravovat přístupy** vede na `servicesDirectory`, ne na dedikovanou správu grantů — doporučit budoucí route `/access` nebo panel ve vozidle.
- **Faktury** v menu jen při `FEATURE_USER_INVOICES_STAGING_ONLY === true`.
- **E2E** — v dev prostředí chybí `tests/e2e/.deps`; spustit `npm run bootstrap` v `tests/e2e` a pak `./run-playwright.sh dashboard-prehled.spec.ts --project=dashboard-prehled-chromium`.
- Legacy E2E (`critical-smoke.spec.ts`) stále cílí `[data-testid="tab-home"]`; nový spec cílí `user-app-next-dashboard`.

### Potvrzení omezení

- Source of truth: pouze `toozservis-tech/sprava-vozidel`.
- Produkční runtime `/opt/toozhub2/app` **nebyl měněn**.
- `.env` **nebyl upraven** (pro lokální test server na :8001 použit read-only symlink na existující `.env`).
- DB **nebyla měněna** mimo běžné čtení přes API testů.
- **Nebyl vytvořen** nový uživatelský účet.

---

## 2. Technical Architecture

### Repo inventura

| Položka | Hodnota |
|---------|---------|
| Remote | `git@github-sprava-vozidel:toozservis-tech/sprava-vozidel.git` |
| Branch | `audit/dashboard-prehled-20260524` |
| Base commit | `998cbb1a1d6aaada5e9cc9d1bffdd930822c115d` |

### Frontend — Přehled

| Soubor | Účel |
|--------|------|
| `web/user-app-next.js` | Render Přehledu, `runAction`, `loadData`, modaly |
| `web/user-app-next.css` | Layout dashboardu |
| `web/index.html` | SPA shell, routing `userTabFromAppSection`, `switchTab`, legacy `#homeTab` |
| `web/user-dashboard-prototype.*` | Vizuální reference (není production path) |

### Render pipeline

```
showDashboard → applyWorkspaceRouteFromUrl → switchTab('home')
  → loadHomeDashboard (hook) → UserAppNext.render()
  → renderUserAppScreen('home') → renderMainCanvas
```

### Routy

| URL sekce | View | Aktivace |
|-----------|------|----------|
| `/app/u/{slug}/dashboard` | `home` | `userTabFromAppSection('dashboard')` |
| `/app/u/{slug}/service-history` | `serviceHistory` | **nově** mapováno v `index.html` + pathname v `getActiveView()` |
| Ostatní | `vehicles`, `reminders`, … | `switchTab` / `navigateLicensedTab` |

### API (`loadData()`)

| Endpoint | Data |
|----------|------|
| `GET /api/v1/analytics/dashboard` | souhrn, attention, recent_activity |
| `GET /api/v1/vehicles` | karty vozidel |
| `GET /api/v1/reminders` | připomínky, badge |
| `GET /api/v1/services/vehicle-access` | servisní přístupy (owner grants) |
| `GET /api/v1/services/my-contacts` | kontakty servisů |
| `GET /api/v1/vehicles/{id}/records` | STK/servis na kartách |
| `GET /api/me` | workspace routing |

### GDPR / security

- Vozidla filtrovaná přes `VehicleOwnership` / `get_owned_vehicle_ids`.
- `vehicle-access` vrací jen granty aktuálního vlastníka se schváleným stavem.
- `shareVehicle` → `openVehicleAccess` → legacy sekce access (authorization flow v existujícím detailu).
- Dashboard summary neobsahuje owner PII navíc oproti schématu `DashboardSummaryOutV1`.

### Tabulka klikacích prvků (Přehled)

| Prvek | Soubor | testid / selector | Typ | Cíl | Stav | Oprava |
|-------|--------|-------------------|-----|-----|------|--------|
| Přehled | user-app-next.js | `dashboard-nav-home` | button | `switchTab('home')` | PASS | — |
| Moje vozidla | user-app-next.js | `dashboard-nav-vehicles` | button | `switchTab('vehicles')` | PASS | — |
| Servisní historie | user-app-next.js | `dashboard-nav-serviceHistory` | button | `serviceHistory` + URL | PASS | routing F5 |
| Připomínky | user-app-next.js | `dashboard-nav-reminders` | button | `switchTab('reminders')` | PASS | — |
| Objednat servis | user-app-next.js | `dashboard-nav-reservations` | button | `navigateLicensedTab` | PASS | licence lock |
| Dokumenty | user-app-next.js | `dashboard-nav-documents` | button | `navigateLicensedTab` | PASS | licence lock |
| Servisy | user-app-next.js | `dashboard-nav-servicesDirectory` | button | licensed tab | PASS | — |
| Faktury | user-app-next.js | `dashboard-nav-invoices` | button | staging flag | PASS | podmíněné |
| Nastavení | user-app-next.js | `dashboard-nav-settings` | button | settings view | PASS | — |
| Nápověda | user-app-next.js | `dashboard-help` | button | tutorial / support | PASS | label/styl |
| Sbalit menu | user-app-next.js | `dashboard-collapse-sidebar` | button | CSS toggle | PASS | — |
| Vyhledávání | user-app-next.js | `dashboard-search-input` | input | filtr karet | PASS | — |
| Cmd/Ctrl+K | user-app-next.js | `bindSearchShortcut` | keyboard | focus search | PASS | implementováno |
| + Přidat vozidlo | user-app-next.js | `dashboard-add-vehicle` | button | `openAddVehicleModal` | PASS | — |
| Notifikace | user-app-next.js | `dashboard-notifications` | button | `toggleAppNotificationsPanel` | PASS | — |
| Profil | user-app-next.js | `dashboard-profile` | button | `toggleMobileProfileMenu` | PASS | — |
| Celkový stav | user-app-next.js | `dashboard-overall-status` | button | attention modal | PASS | — |
| STK / SME | user-app-next.js | `dashboard-quick-stk` | button | `reminders` | PASS | — |
| Pojištění | user-app-next.js | `dashboard-quick-insurance` | button | `reminders` | PASS | — |
| Servis (quick) | user-app-next.js | `dashboard-quick-service` | button | `serviceHistory` | PASS | — |
| Dokumenty (quick) | user-app-next.js | `dashboard-quick-documents` | button | `documents` | PASS | — |
| Karta vozidla (tělo) | user-app-next.js | `.uapp-next-vehicle-open` | button | `detail:{id}` | PASS | nově |
| Detail | user-app-next.js | `data-uapp-action=detail:*` | button | detail modal | PASS | — |
| Přidat záznam | user-app-next.js | `addRecord:*` | button | `openAddServiceRecordModal` | PASS | — |
| Dokumenty (karta) | user-app-next.js | `documentsVehicle:*` | button | documents tab | PASS | — |
| Sdílet | user-app-next.js | `shareVehicle:*` | button | access tab | PASS | label |
| Zobrazit všechna vozidla | user-app-next.js | `dashboard-view-all-vehicles` | button | vehicles | PASS | — |
| Přidat další vozidlo | user-app-next.js | `dashboard-add-vehicle-card` | button | add modal | PASS | — |
| Termín (aside řádek) | user-app-next.js | aside row | button | detail/reminders | PASS | dynamické |
| Všechny připomínky | user-app-next.js | `dashboard-aside-all-reminders` | button | reminders | PASS | — |
| Aktivita (řádek) | user-app-next.js | aside activity | button | detail/history | PASS | — |
| Spravovat přístupy | user-app-next.js | aside head | button | servicesDirectory | PASS | návrh dedik. UI |

### Testy

| Test | Výsledek |
|------|----------|
| `test_service_history_deep_link_contract` | PASS |
| `test_dashboard_overview_testids_present` | PASS |
| `test_support_navigation_uses_existing_flow_and_safe_error` | PASS |
| `test_dashboard_summary_api.py` (unit) | PASS |
| `tests/e2e/dashboard-prehled.spec.ts` | **PASS** (8/8, `BASE_URL=http://127.0.0.1:8001`, 2026-05-24) |

---

## 3. Business Impact

- **Rychlost práce** — Přehled je jediná obrazovka, kde uživatel vidí STK, servis, dokumenty a přístupy servisů najednou; opravené zkratky (Cmd+K, klik na kartu, F5 na historii) snižují počet „mrtvých“ interakcí.
- **Důvěra** — konzistentní vizuál a funkční odkazy posilují dojem profesionální aplikace; celkový stav + attention modal směřují na konkrétní akce.
- **Servisní transparentnost** — aside „Servisy a přístupy“ napojené na reálné granty; sdílení vede na autorizovaný access flow.
- **Hodnota vozidla při prodeji** — rychlý přístup k historii, dokumentům a stavu STK/pojištění z jedné palubní desky podporuje kompletní digitální složku vozidla.

---

## Změněné soubory (implementace)

- `web/index.html`
- `web/user-app-next.js`
- `web/user-app-next.css`
- `tests/api/test_user_app_p1_parity.py`
- `tests/e2e/dashboard-prehled.spec.ts` (nový)
- `tests/e2e/playwright.config.ts`
- `docs/audits/DASHBOARD_UI_BUTTON_AUDIT_20260524.md` (tento soubor)
