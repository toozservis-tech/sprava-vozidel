# Service Workspace Web Status

Související: [SERVICE_WORKSPACE_CLIENT_CONSISTENCY.md](./SERVICE_WORKSPACE_CLIENT_CONSISTENCY.md) – kanonické názvy režimů, přesné texty a poznámka k iOS.

## Co web detekuje

Web rozlišuje dva oddělené pojmy:

- `backendModel`
  - `new`: server vrací existující nové route `approved-vehicles`, `pending-vehicles`, `vehicle-lookup`
  - `legacy`: některá z nových route vrací `404`, takže nový service access model ještě není na serveru nasazený
  - `unknown`: server nebo síť nevrátily spolehlivý výsledek
- `mode`
  - `new`: nový model je dostupný a UI používá pokročilý režim
  - `legacy`: nový model na serveru není a UI přechází do kompatibilního základního režimu
  - `unauthorized`: route existují, ale aktuální relace nebo účet nemají přístup
  - `unavailable`: server, síť nebo WAF/Cloudflare blokují požadavek

Detekce běží centrálně ve webu a používá HTTP statusy, ne heuristiku podle textu chyb.

**Klasifikace „route existuje“ (nové endpointy):** jakýkoli HTTP kód **kromě `404`** (např. `401`, `403`, `405`, `422`, `409`, `200` …) znamená, že cesta je zaregistrovaná. Pouze **`404`** znamená „route na serveru chybí“ → `legacy`. **`405`** u špatné metody tedy **není** považován za chybějící backend.

## Klíčové route

- `GET /api/v1/services/workspace/customers`
  - základní legacy route
  - `401/403` znamená, že route existuje, ale chybí relace nebo oprávnění
- `GET /api/v1/services/workspace/approved-vehicles`
- `POST /api/v1/services/workspace/pending-vehicles` (předregistrace vozidla; pro **sondu existence** web pošle prázdné `{}` → typicky `401`/`422`, nikoli `404`)
- `POST /api/v1/services/workspace/vehicle-lookup` (tělo `{ "query": "xx" }` – minimální platná délka; pro sondu stačí odpověď ≠ `404`)
  - nové route pro service access model
  - `404` na těchto cestách znamená, že nový model ještě není nasazený

**Sondy v prohlížeči (`apiInspect`):** `customers` + `GET` approved + `POST` pending `{}` + `POST` lookup `{ "query": "xx" }` – stejné hlavičky jako běžné `apiCall` (Bearer / geo), **bez** automatického odhlášení při `401` (odlišně od `apiCall`).

Vedlejší legacy route, které web dál používá i ve fallback režimu:

- `GET /api/v1/services/workspace/invitations`
- `GET /api/v1/services/workspace/documents?limit=20`
- `GET /api/v1/services/workspace/reminders?include_completed=true&limit=500`
- `GET /api/v1/services/workspace/customers/{id}/vehicles`
- `GET /api/v1/reservations/service`

## Mapování statusů

### 404

- `approved-vehicles`, `pending-vehicles`, `vehicle-lookup`
  - web nastaví `backendModel=legacy`
  - UI nastaví `mode=legacy`
  - zobrazí neblokující informační banner o kompatibilním základním režimu

### 401 nebo 403 JSON

- `customers`
  - route existuje, ale aktuální relace nebo účet nemají přístup
  - UI nastaví `mode=unauthorized`
- nové route
  - pokud vrací `401/403` a nejsou `404`, web považuje nový model za nasazený

### 403 HTML challenge

- pokud server vrátí HTML typu `Cloudflare`, `challenge`, `Just a moment`
  - web to nebere jako auth chybu
  - UI nastaví `mode=unavailable`

### 5xx nebo network/timeout

- web nastaví `mode=unavailable`
- zobrazí server/network stav a retry tlačítko

## Chování UI

### `mode=new`

- nahoře se zobrazí informační banner, že je aktivní pokročilý servisní režim
- karta **Pokročilý servisní přístup**:
  - seznam schválených vozidel z `GET /approved-vehicles`
  - vyhledávání přes `POST /vehicle-lookup` (uživatel zadá SPZ/VIN)
  - krátká poznámka k `POST /pending-vehicles` (předregistrace s povinným tělem – není zde celý formulář)
- základní klientská agenda (klienti, pozvánky, doklady) zůstává zachovaná

### `mode=legacy`

- web nespadne na `404`
- zobrazí se stručný banner:
  - „Pokročilá servisní správa zatím není na tomto serveru aktivní. Zobrazuje se stabilní základní režim.“
- nové pokročilé sekce nejsou renderované
- zůstává funkční stávající legacy flow přes:
  - klienty
  - pozvánky
  - dokumenty
  - připomínky

### `mode=unauthorized`

- zobrazí se stav přihlášení nebo oprávnění (vizuálně `alert-info`, bez červeného „alarmu“)
- UI se netváří jako rozbitý backend

### `mode=unavailable`

- zobrazí se stav serveru nebo připojení (`alert-info`)
- obsahuje retry tlačítko **Zkusit znovu**

## Interní debug markery

Service workspace root nastavuje datové atributy:

- `data-workspace-mode`
- `data-workspace-backend-model`
- `data-workspace-mode-reason` (stručný textový důvod režimu z resolveru)
- `data-workspace-mode-source-endpoint` (která route rozhodla / zdroj diagnostiky)

Konzole zapisuje omezené debug logy:

- `[SERVICE_WORKSPACE_MODE]`
- `[SERVICE_WORKSPACE_UI]`

## Klíčové web soubory

- `app/web/index.html`
  - capability resolver
  - service workspace mode/fallback branch
  - UI texty a bannery
  - debug markery
  - **`loadSystemCapabilities` a mapování tabů musí být v platném `<script>` před `</body></html>`** – předčasný konec dokumentu (kód za `</html>`) dříve způsobil `ReferenceError` v `showDashboard()` a servisní centrum se nenačetlo (zůstalo „Načítám…“ bez `data-workspace-*`).
- `app/tests/e2e/service-workspace-fallback.spec.ts`
  - cílený Playwright smoke pro `new / legacy / unauthorized / unavailable / blocked`
- `app/tests/e2e/playwright.config.ts`
  - projekt `workspace-desktop-chromium` pro cílené spuštění testu

## Jak testovat lokálně

### 1. Cílený automatický smoke

```bash
cd /opt/toozhub2/app/tests/e2e
./node_modules/.bin/playwright test service-workspace-fallback.spec.ts --config playwright.config.ts --project workspace-desktop-chromium
```

Očekávání:

- `new` branch projde
- `legacy` branch projde při mockovaném `404`
- `unauthorized` branch projde při mockovaném `401/403`
- `unavailable` branch projde při mockovaném `5xx`
- `blocked` branch projde při mockovaném `403` HTML challenge

### 2. Lokální běh aplikace

```bash
cd /opt/toozhub2
. .venv/bin/activate
HOST=127.0.0.1 PORT=8010 python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8010
```

Pak otevřít:

- `http://127.0.0.1:8010/web/index.html`

### 3. Lokální HTTP kontrola route

Bez přihlášení typicky ověříte aspoň existenci/absenci route:

```bash
curl -i http://127.0.0.1:8010/api/v1/services/workspace/customers
curl -i http://127.0.0.1:8010/api/v1/services/workspace/approved-vehicles
curl -i -X POST http://127.0.0.1:8010/api/v1/services/workspace/pending-vehicles -H "Content-Type: application/json" -d '{}'
curl -i -X POST http://127.0.0.1:8010/api/v1/services/workspace/vehicle-lookup -H "Content-Type: application/json" -d '{"query":"xx"}'
```

Vyhodnocení:

- `customers=401/403` a některá z nových cest `404` => starý backend, web má přejít do `legacy`
- nové cesty vracejí `401`/`403`/`422`/`405` (u špatné metody), ale **ne** `404` => route existují; po přihlášení web → `new`
- `5xx` => `unavailable`

## Jak testovat v browseru

1. Přihlaste se servisním účtem.
2. Otevřete tab `Klienti`.
3. Zkontrolujte atributy na `#serviceWorkspaceContainer`.
4. Ověřte banner / stavový blok:
   - `new`: banner „Pokročilý servisní režim“
   - `legacy`: banner „Kompatibilní základní režim“
   - `unauthorized`: nadpis „Přihlášení nebo oprávnění“ (`data-testid="service-workspace-mode-state"`)
   - `unavailable`: nadpis „Server nebo připojení“ + tlačítko Zkusit znovu
5. V konzoli ověřte log `[SERVICE_WORKSPACE_MODE]` (stav sond, `mode`, `backendModel`).
6. Ověřte, že:
   - v `legacy` **není** karta „Pokročilý servisní přístup“ a je banner kompatibilního režimu
   - v `new` je banner „Pokročilý servisní režim“, karta s schválenými vozidly a vyhledáváním
   - UI nespadne na chybějící endpoint (žádný tvrdý 404 z vlastního kódu)

## Jak testovat proti veřejnému serveru

### Browser

- otevřete produkční web v běžném browseru
- přihlaste se
- přejděte do `Klienti`
- zkontrolujte banner a `data-workspace-*` atributy

### Curl

```bash
curl -i https://hub.toozservis.cz/api/v1/services/workspace/customers
curl -i https://hub.toozservis.cz/api/v1/services/workspace/approved-vehicles
curl -i -X POST https://hub.toozservis.cz/api/v1/services/workspace/pending-vehicles -H "Content-Type: application/json" -d '{}'
curl -i -X POST https://hub.toozservis.cz/api/v1/services/workspace/vehicle-lookup -H "Content-Type: application/json" -d '{"query":"xx"}'
```

Poznámka:

- veřejný server může při `curl` vracet `403` HTML challenge od Cloudflare místo čistého API statusu
- web to má nově klasifikovat jako `unavailable`, ne jako běžnou auth chybu
- browser se skutečnou relací a cookies je pro finální ověření reprezentativnější než samotný `curl`

## Co má web zobrazit v jednotlivých režimech

- `new`
  - pokročilý servisní banner
  - karta `Pokročilý servisní přístup` (schválená vozidla + POST lookup; poznámka k POST předregistraci)
- `legacy`
  - informační banner o základním režimu
  - funkční legacy klienti/pozvánky/dokumenty/připomínky
  - bez mrtvých prvků pro nový model
- `unauthorized`
  - nadpis „Přihlášení nebo oprávnění“ a stručný důvod (401 vs 403)
  - bez textu o rozbité aplikaci
- `unavailable`
  - nadpis „Server nebo připojení“ a stručný důvod
  - retry tlačítko
