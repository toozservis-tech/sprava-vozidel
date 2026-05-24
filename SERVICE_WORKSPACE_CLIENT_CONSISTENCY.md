# Service workspace – konzistence klientů (web / iOS)

Tento dokument je **kanonický přehled stavů a textů** pro servisní centrum (interně „service workspace“) na webu. **Repozitář `/opt/toozhub2` neobsahuje iOS aplikaci** (žádné Swift zdroje); srovnání s iOS je nutné doplnit v mobilním repozitáři podle tabulek níže.

---

# SERVICE WORKSPACE CLIENT CONSISTENCY – VÝSLEDEK

## 1. Jaké stavy teď mají web a iOS

| Interní `mode` | `backendModel` (web) | Význam |
|----------------|----------------------|--------|
| `new` | `new` | Nové API route pro schválená/čekající vozidla a lookup jsou dostupné; UI zobrazí pokročilou kartu. |
| `legacy` | `legacy` | Nové route vracejí `404`; UI běží v kompatibilním základním režimu bez pokročilých sekcí. |
| `unauthorized` | obvykle `unknown` / dle sondy | `customers` vrací `401` nebo JSON `403` – relace nebo role nestačí. |
| `unavailable` | dle sondy | Síť, timeout, `5xx`, `404` na `customers`, HTML Cloudflare challenge u `403`, apod. |

**iOS:** ve stejném repozitáři není – očekává se **stejný čtyřstavový model** (`new` / `legacy` / `unauthorized` / `unavailable`) a stejné uživatelské názvy režimů jako na webu.

## 2. Kde byly nekonzistence

- Uživatelské texty míchaly **„servisní workspace“** s tabem **„Servisní centrum“** (načítání).
- V banneru a kartě pokročilého režimu byl **anglický** „access model“.
- Stav **neautorizace** používal **červený** `alert-error`, což působilo jako pád aplikace.
- Inline chyba načtení vozidel klienta používala **výraznou jantarovou** barvu (podobně jako varovné bannery).
- **iOS:** nelze v tomto workspace ověřit; riziko odchylek v názvech a copy zůstává do synchronizace s mobilním kódem.

## 3. Co jsem sjednotil

- Jednotné uživatelské označení: **„servisní centrum“** (místo „servisní workspace“) ve všech hláškách resolveru, `getServiceWorkspaceUnavailableMessage`, výchozím titulku stavu a souvisejícím textu.
- **České** formulace místo „service access model“ → **„model servisního přístupu“**.
- `unauthorized` a `unavailable` v celoobrazovkovém stavu: **`alert-info`** místo červené chyby; titulek neautorizace: **„Přihlášení nebo oprávnění“**.
- Doplňující důvod u nedostupnosti pokročilých API: **„Rozšířené funkce servisního centra…“** (srozumitelnější než „pokročilý workspace“).
- Chyba detailu vozidel u karty klienta: **neutrální šedá** (`#64748b`), ne varovná oranžová.

## 4. Jaké soubory jsem upravil

- `app/web/index.html` – copy, typ alertu ve `renderServiceWorkspaceModeState`, barva inline chyby vozidel; resolver a sondy (`apiInspect`, POST na `pending-vehicles` / `vehicle-lookup`); **struktura HTML: blok `loadSystemCapabilities` / `applySystemCapabilitiesUi` zabalen do `<script>` před uzavřením `</body></html>`** (oprava rozbitého startu dashboardu).
- `app/tests/e2e/service-workspace-fallback.spec.ts` – očekávaný titulek neautorizace, mock `detail` u `403`, **405 na GET** u POST-only route, tělo `approved-vehicles` jako `{ items: [...] }`.
- `app/tests/e2e/playwright.config.ts` – projekt `workspace-desktop-chromium` pro tento spec.
- `app/SERVICE_WORKSPACE_WEB_STATUS.md` – odkazy, popis UI, manuální checklist, poznámka k validnímu umístění skriptu capabilities.
- `app/BACKEND_DEPLOY_PRODUCTION_CHECKLIST.md` – upřesnění HTTP metod u nových route (konzistence s OpenAPI).

## 5. Jaké nové soubory jsem vytvořil

- `app/SERVICE_WORKSPACE_CLIENT_CONSISTENCY.md` (tento soubor).

## 6. Jak jsem ověřil reálný browser flow

- **Automaticky:** z `app/tests/e2e` spustit Playwright spec `service-workspace-fallback.spec.ts` (mockované větve; simuluje přihlášený servisní účet přes `localStorage`).
- **Manuálně (produkce / staging):** postup v [SERVICE_WORKSPACE_WEB_STATUS.md](./SERVICE_WORKSPACE_WEB_STATUS.md) – přihlášení servisním účtem, tab Klienti, kontrola `data-workspace-mode` / `data-workspace-backend-model` na `#serviceWorkspaceContainer`, soulad banneru s režimem.

## 7. Jak teď vypadají texty a bannery (web)

### Informační bannery (`data-testid="service-workspace-mode-banner"`)

| Režim | Titulek | Zpráva |
|-------|---------|--------|
| `legacy` | Kompatibilní základní režim | Pokročilá servisní správa zatím není na tomto serveru aktivní. Zobrazuje se stabilní základní režim. |
| `new` | Pokročilý servisní režim | Server podporuje nový model servisního přístupu (schválená vozidla a vyhledávání). |

### Celostránkový stav (`data-testid="service-workspace-mode-state"`)

| Režim | Titulek | Poznámka |
|-------|---------|----------|
| `unauthorized` | Přihlášení nebo oprávnění | Text z resolveru: 401 = znovu ověřit přihlášení; 403 = chybí oprávnění pro servisní centrum. |
| `unavailable` | Server nebo připojení | Důvod z resolveru nebo fallback; tlačítko **Zkusit znovu**. |

### Důvody z resolveru (`capability.reason`, stručně)

- Nedostupnost zákaznické sondy: spojení se serverem / základní centrum na serveru není dostupné.
- Pokročilé route nedostupné (ne legacy): rozšířené funkce + server/síť.
- Legacy větev: pokročilý model na serveru není aktivní / kompatibilní základní režim.

### Pomocné hlášky (`getServiceWorkspaceUnavailableMessage`)

- 401, 403, 5xx, síť/timeout a obecný fallback – vždy s formulací **„servisní centrum“** (viz kód v `index.html`).

### Ne‑servisní účet

- „Servisní centrum je dostupné pouze pro servisní účty.“

## 8. Co zůstává jako další krok

1. **iOS:** vyexportovat stejné stringy z mobilního projektu a srovnat s tabulkami v sekci 7; případně upravit iOS copy na shodu.
2. **E2E s reálnou autentizací:** volitelně rozšířit Playwright o login proti testovacímu backendu (mimo mock), pokud CI poskytuje bezpečné údaje.
3. **Backend JSON `detail`:** pokud API vrací starší text s „workspace“, zvážit sjednocení na API straně pro konzistenci s webem.
