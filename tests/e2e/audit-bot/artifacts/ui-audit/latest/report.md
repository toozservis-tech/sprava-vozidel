# UI Audit Report — Správa vozidel

- **Run ID:** audit-2026-05-24T13-51-40-852Z
- **Scope:** dashboard-profile
- **Overall verdict:** FAIL
- **Started:** 2026-05-24T13:51:40.852Z
- **Finished:** 2026-05-24T13:51:49.002Z

## Actionable Solution

- **FAIL** `dashboard-search-input`: Formulářové pole — neklikáme → Upravit navigaci/prvek "" aby vedl na /web/index.html#home
- **FAIL** `Dobrý den, E2E 👋 Máte 0 vozidel, 0 blížící se STK, 0 aktivních připomínek a 0 nových upozornění od servisu. Celkový sta`: Neznámý prvek bez pravidla → Upravit navigaci/prvek "Dobrý den, E2E 👋 Máte 0 vozidel, 0 blížící se STK, 0 aktivních připomínek a 0 nových upozornění od servisu. Celkový sta" aby vedl na /web/index.html#home
- **FAIL** `Dobrý den, E2E 👋 Máte 0 vozidel, 0 blížící se STK, 0 aktivních připomínek a 0 nových upozornění od servisu. Celkový sta`: Neznámý prvek bez pravidla → Upravit navigaci/prvek "Dobrý den, E2E 👋 Máte 0 vozidel, 0 blížící se STK, 0 aktivních připomínek a 0 nových upozornění od servisu. Celkový sta" aby vedl na /web/index.html#home
- **FAIL** `Dobrý den, E2E 👋 Máte 0 vozidel, 0 blížící se STK, 0 aktivních připomínek a 0 nových upozornění od servisu.`: Neznámý prvek bez pravidla → Upravit navigaci/prvek "Dobrý den, E2E 👋 Máte 0 vozidel, 0 blížící se STK, 0 aktivních připomínek a 0 nových upozornění od servisu." aby vedl na /web/index.html#home
- **FAIL** `Dobrý den, E2E 👋`: Neznámý prvek bez pravidla → Upravit navigaci/prvek "Dobrý den, E2E 👋" aby vedl na /web/index.html#home
- **FAIL** `Celkový stav Vozidla pod kontrolou Poslední aktualizace: dnes v 13:51 Zobrazit detaily ›`: Neznámý prvek bez pravidla → Upravit navigaci/prvek "Celkový stav Vozidla pod kontrolou Poslední aktualizace: dnes v 13:51 Zobrazit detaily ›" aby vedl na /web/index.html#home
- **FAIL** `STK / SME STK / SME v pořádku Žádná blížící se lhůta › Pojištění Všechna vozidla v pořádku Platné smlouvy › Servis Bez s`: Neznámý prvek bez pravidla → Upravit navigaci/prvek "STK / SME STK / SME v pořádku Žádná blížící se lhůta › Pojištění Všechna vozidla v pořádku Platné smlouvy › Servis Bez s" aby vedl na /web/index.html#home
- **FAIL** `Moje vozidla Zobrazit všechna vozidla → Zatím nemáte žádné vozidlo. Přidejte první vozidlo a přehled se naplní reálnými `: Neznámý prvek bez pravidla → Upravit navigaci/prvek "Moje vozidla Zobrazit všechna vozidla → Zatím nemáte žádné vozidlo. Přidejte první vozidlo a přehled se naplní reálnými " aby vedl na /web/index.html#home
- **FAIL** `Moje vozidla Zobrazit všechna vozidla → Zatím nemáte žádné vozidlo. Přidejte první vozidlo a přehled se naplní reálnými `: Neznámý prvek bez pravidla → Upravit navigaci/prvek "Moje vozidla Zobrazit všechna vozidla → Zatím nemáte žádné vozidlo. Přidejte první vozidlo a přehled se naplní reálnými " aby vedl na /web/index.html#home
- **FAIL** `Zatím nemáte žádné vozidlo. Přidejte první vozidlo a přehled se naplní reálnými daty.`: Neznámý prvek bez pravidla → Upravit navigaci/prvek "Zatím nemáte žádné vozidlo. Přidejte první vozidlo a přehled se naplní reálnými daty." aby vedl na /web/index.html#home
- **WARN** `? Nápověda ›`: Neznámý prvek bez pravidla

## Technical Architecture

- Deterministic crawler (`audit-crawler.spec.ts`) + safety-policy + route-oracle
- READ/SAFE CLICK režim — bez submitů, plateb, mazání
- Volitelný AI reviewer přes `UI_AUDIT_AI=1`
- Artefakty: JSON + Markdown + screenshots + trace

## Business Impact

- Celkem prvků: **23** (SAFE 2 / WARN 19 / BLOCKED 2)
- FAIL redirectů: **0**
- PASS: 5, FAIL: 15, WARN: 1, BLOCKED: 2

## Detailní tabulka kliků

| Sekce | Text | testid | role | URL před | URL po | Očekávaný cíl | Skutečný cíl | Verdict | Chyby | Screenshot | Oprava |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Přehled | Licence: LOADING… License Debug: Initial | dashboard | generic | http://127.0.0.1:80****/web/app/u/e2e-fi | http://127.0.0.1:80****/web/app/u/e2e-fi | /web/index.html#home | beze změny | PASS | [API] Error [/api/v1/services/my-contacts]: TypeError: Failed to fetch
    at apiCall (http://127.0.0.1:80****/web/index.html:381****:38)
    at http://127.0.0.1:80****/web/index.html:576****:43
    at loadManagedServiceContacts (http://127.0.0.1:80****/web/index.html:576****:15)
    at http://127.0.0.1:80****/web/index.html:447****:70 | screenshots/000-before.png | — |
| Přehled | ☰ Správa vozidel ES Správa vozidel Přehl | user-app-next-screen | generic | http://127.0.0.1:80****/web/app/u/e2e-fi | http://127.0.0.1:80****/web/app/u/e2e-fi | /web/index.html#home | beze změny | PASS | [API] Error [/api/v1/services/my-contacts]: TypeError: Failed to fetch
    at apiCall (http://127.0.0.1:80****/web/index.html:381****:38)
    at http://127.0.0.1:80****/web/index.html:576****:43
    at loadManagedServiceContacts (http://127.0.0.1:80****/web/index.html:576****:15)
    at http://127.0.0.1:80****/web/index.html:447****:70 | screenshots/001-before.png | — |
| Přehled | ☰ Správa vozidel ES Správa vozidel Přehl | user-app-next-dashboard | generic | http://127.0.0.1:80****/web/app/u/e2e-fi | http://127.0.0.1:80****/web/app/u/e2e-fi | /web/index.html#home | beze změny | PASS | [API] Error [/api/v1/services/my-contacts]: TypeError: Failed to fetch
    at apiCall (http://127.0.0.1:80****/web/index.html:381****:38)
    at http://127.0.0.1:80****/web/index.html:576****:43
    at loadManagedServiceContacts (http://127.0.0.1:80****/web/index.html:576****:15)
    at http://127.0.0.1:80****/web/index.html:447****:70 | screenshots/002-before.png | — |
| Navigace | Přehled | dashboard-nav-home | button | http://127.0.0.1:80****/web/app/u/e2e-fi | http://127.0.0.1:80****/web/app/u/e2e-fi | view:home | beze změny | PASS | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/003-after.png | — |
| Navigace | Moje vozidla | dashboard-nav-vehicles | button | http://127.0.0.1:80****/web/app/u/e2e-fi | http://127.0.0.1:80****/web/app/u/e2e-fi | view:vehicles | url+view | PASS | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/004-after.png | — |
| Navigace | ? Nápověda › | dashboard-help | button | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | — | beze změny | WARN | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/011-before.png | Definovat expected_target pro "? Nápověda ›" |
| Přehled | Ctrl K + Přidat vozidlo ES E2E Settings  | dashboard-topbar | generic | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | — | beze změny | BLOCKED | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/013-before.png | — |
| Přehled |  | dashboard-search-input | generic | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | /web/index.html#home | beze změny | FAIL | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/014-before.png | Upravit navigaci/prvek "" aby vedl na /web/index.html#home |
| Přehled | + Přidat vozidlo | dashboard-add-vehicle | button | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | — | beze změny | BLOCKED | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/015-before.png | — |
| Přehled | Dobrý den, E2E 👋 Máte 0 vozidel, 0 blíž | dashboard-overview-shell | generic | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | /web/index.html#home | beze změny | FAIL | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/018-before.png | Upravit navigaci/prvek "Dobrý den, E2E 👋 Máte 0 vozidel, 0 blížící se STK, 0 aktivních připomínek a 0 nových upozornění od servisu. Celkový sta" aby vedl na /web/index.html#home |
| Přehled | Dobrý den, E2E 👋 Máte 0 vozidel, 0 blíž | dashboard-hero-row | generic | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | /web/index.html#home | beze změny | FAIL | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/019-before.png | Upravit navigaci/prvek "Dobrý den, E2E 👋 Máte 0 vozidel, 0 blížící se STK, 0 aktivních připomínek a 0 nových upozornění od servisu. Celkový sta" aby vedl na /web/index.html#home |
| Přehled | Dobrý den, E2E 👋 Máte 0 vozidel, 0 blíž | dashboard-hero | generic | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | /web/index.html#home | beze změny | FAIL | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/020-before.png | Upravit navigaci/prvek "Dobrý den, E2E 👋 Máte 0 vozidel, 0 blížící se STK, 0 aktivních připomínek a 0 nových upozornění od servisu." aby vedl na /web/index.html#home |
| Přehled | Dobrý den, E2E 👋 | dashboard-hero-greeting | generic | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | /web/index.html#home | beze změny | FAIL | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/021-before.png | Upravit navigaci/prvek "Dobrý den, E2E 👋" aby vedl na /web/index.html#home |
| Přehled | Celkový stav Vozidla pod kontrolou Posle | dashboard-overall-status | button | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | /web/index.html#home | beze změny | FAIL | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/022-before.png | Upravit navigaci/prvek "Celkový stav Vozidla pod kontrolou Poslední aktualizace: dnes v 13:51 Zobrazit detaily ›" aby vedl na /web/index.html#home |
| Přehled | STK / SME STK / SME v pořádku Žádná blíž | dashboard-quick-grid | generic | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | /web/index.html#home | beze změny | FAIL | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/023-before.png | Upravit navigaci/prvek "STK / SME STK / SME v pořádku Žádná blížící se lhůta › Pojištění Všechna vozidla v pořádku Platné smlouvy › Servis Bez s" aby vedl na /web/index.html#home |
| Přehled | Moje vozidla Zobrazit všechna vozidla →  | dashboard-overview-body | generic | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | /web/index.html#home | beze změny | FAIL | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/028-before.png | Upravit navigaci/prvek "Moje vozidla Zobrazit všechna vozidla → Zatím nemáte žádné vozidlo. Přidejte první vozidlo a přehled se naplní reálnými " aby vedl na /web/index.html#home |
| Přehled | Moje vozidla Zobrazit všechna vozidla →  | dashboard-vehicles-section | generic | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | /web/index.html#home | beze změny | FAIL | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/029-before.png | Upravit navigaci/prvek "Moje vozidla Zobrazit všechna vozidla → Zatím nemáte žádné vozidlo. Přidejte první vozidlo a přehled se naplní reálnými " aby vedl na /web/index.html#home |
| Přehled | Zatím nemáte žádné vozidlo. Přidejte prv | dashboard-vehicle-grid | generic | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | /web/index.html#home | beze změny | FAIL | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/031-before.png | Upravit navigaci/prvek "Zatím nemáte žádné vozidlo. Přidejte první vozidlo a přehled se naplní reálnými daty." aby vedl na /web/index.html#home |
| Přehled | + Přidat další vozidlo Rychle přidejte n | dashboard-add-vehicle-card | button | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | /web/index.html#home | beze změny | FAIL | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/032-before.png | Upravit navigaci/prvek "+ Přidat další vozidlo Rychle přidejte nové vozidlo do své správy" aby vedl na /web/index.html#home |
| Přehled | Blížící se termíny Zobrazit všechny → Be | dashboard-overview-aside | generic | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | view:reminders | beze změny | FAIL | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/033-before.png | Upravit navigaci/prvek "Blížící se termíny Zobrazit všechny → Bez blížících se termínů. Zobrazit všechny připomínky → Poslední aktivita Zobrazit" aby vedl na view:reminders |
| Přehled | Blížící se termíny Zobrazit všechny → Be | dashboard-aside-deadlines | generic | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | view:reminders | beze změny | FAIL | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/034-before.png | Upravit navigaci/prvek "Blížící se termíny Zobrazit všechny → Bez blížících se termínů. Zobrazit všechny připomínky →" aby vedl na view:reminders |
| Přehled | Poslední aktivita Zobrazit vše → Zatím b | dashboard-aside-activity | generic | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | /web/index.html#home | beze změny | FAIL | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/037-before.png | Upravit navigaci/prvek "Poslední aktivita Zobrazit vše → Zatím bez poslední aktivity." aby vedl na /web/index.html#home |
| Přehled | Servisy a přístupy Spravovat přístupy →  | dashboard-aside-access | generic | chrome-error://chromewebdata/ | chrome-error://chromewebdata/ | view:servicesDirectory | beze změny | FAIL | Failed to load resource: net::ERR_CONNECTION_REFUSED | screenshots/039-before.png | Upravit navigaci/prvek "Servisy a přístupy Spravovat přístupy → Zatím nejsou aktivní sdílené přístupy ani servisní kontakty." aby vedl na view:servicesDirectory |
