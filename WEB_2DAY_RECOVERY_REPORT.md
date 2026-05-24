# Forenzní report: obnova webové vrstvy („poslední 2 dny“)

Datum analýzy: 2026-04-07  
Repozitář: `source-mirror/app` (GitHub `main`)

---

## 1. Kde je poslední správná plná web verze

| Zdroj | Řádků `index.html` | Obsah |
|--------|-------------------|--------|
| **`main` @ `e4aa067` (HEAD)** | **~28 293** | Kanonická plná aplikace: dashboard, přidání vozidla, fotky, servisní záznamy včetně km, service workspace, capabilities uvnitř `<script>`, `storage_migration.js`. |
| `39db028` (WEB + IOS service workspace) | ~28 228 | Stejný „velký“ monolitický web; oproti HEAD jen bez rename fáze 2 + opravy capabilities za `</html>`. |
| `6862206`, `2c5b546` | ~28 229–28 291 | Mezikroky (rename, storage). |
| **`web/index.html.backup_now`** | **~9 437** | Starší snapshot, titulek **„TooZ Hub 2“**; **bez** `vehiclePhoto` / `uploadVehiclePhoto` / `hydrateVehiclePhoto` – **není** cílová verze. |
| `web/index_minimal.html` | ~346 | Úmyslně zkrácená varianta. |
| `web/index_iframe*.html` | malé | Embed / legacy scénáře. |
| `source-mirror/app_backup/web/index.html` (mimo git) | ~27 672 | Obsahuje upload fotek (3× výskyt `uploadVehiclePhoto`), ale je **kratší než HEAD** → spíše starší kopie disku, ne autorita. |

**Závěr:** Jediný zdroj pravdy pro „moderní web v celku“ je **`web/index.html` na větvi `main` nejpozději od `39db028`, aktuálně `e4aa067`**. V lokálním gitu **nebyl nalezen novější commit** s větším obsahem než HEAD.

---

## 2. Co přesně se na produkci „ztratilo“ (interpretace)

Pokud na produkci chybí ORV/add vehicle, nové UI, fotky, km, dashboard apod., jde typicky o jedno z:

1. **Nasazen byl špatný soubor** – např. `index.html.backup_now`, `index_minimal.html`, stará ruční kopie z disku, nebo build, který nekopíruje celý `web/`.
2. **Nasazen starý commit / jiná větev** – bez `39db028` a novějších změn.
3. **Nebyl nasazen `storage_migration.js`** – po fázi 2 rename; API URL a preference pak mohou selhat nebo se chovat divně (nesnižuje řádky HTML, ale runtime).

**V samotném gitu `main` tyto funkce v aktuálním `index.html` přítomny jsou** (ukázky kontroly):

- Dashboard: `#dashboard`, `showDashboard`, `[DASHBOARD]` logy.
- Přidání vozidla: `#addVehicleTab`, `submitAddVehicle` / související flow, STK/VIN UI v šabloně.
- Fotky: `vehiclePhotoInput`, `previewAddVehiclePhoto`, `uploadVehiclePhoto`, `hydrateVehiclePhotoPreview`.
- Km: servisní formuláře `serviceMileage`, `serviceMileage-add`, modální `serviceMileage-modal-*`, zobrazení km u záznamů.

**Poznámka k „ORV“:** V `index.html` se nevyskytuje samostatný řetězec/feature label „ORV“. Pokud jde o konkrétní byznys krok (např. ověření/registrace), může být pojmenovaný jinak (VIN, SPZ, STK, přidat vozidlo). Plný add-vehicle a detailní karty jsou v kanonické verzi.

---

## 3. Proč se to ztratilo (nejpravděpodobnější příčiny)

- **Deploy skript / Webnode / ruční FTP** nahradil produkční `index.html` menším souborem (backup nebo minimal).
- **Oprava na serveru** (např. capabilities) byla provedena jen lokálně na disku a **nebyla ta samá** jako v gitu, nebo byl později přepsán celý soubor starší kopií.
- **Chybějící synchronizace** po `git pull` – běží starý obsah z cache nebo jiné cesty (`/web/` vs kořen).

Git historie **neukazuje** masivní revert webu v posledních commitech – spíše **přidání** (rename, storage helper, přesun capabilities).

---

## 4. Co bylo „obnoveno“ z pohledu repozitáře

- **Žádný velký merge obnovy z backupu nebyl nutný:** aktuální `main` už odpovídá plnému modernímu stavu.
- **Jediná kritická oprava struktury** v tomto období: capability funkce musí být **uvnitř** hlavního `<script>`, ne za `</html>` (**commit `e4aa067`**).

---

## 5. Z jakých zdrojů brát soubory při nasazení

Nasadit **celý adresář `web/`** z `main` včetně minimálně:

- `index.html`
- `storage_migration.js` (povinně po fázi 2, protože `index.html` ho načítá)
- `theme.css`, `app.css`, ostatní skripty (`sw.js`, `security_protection.js`, …) dle stávajícího buildu

**Nikdy jako produkční hlavní app:**

- `index.html.backup_now`
- `index_minimal.html` (kromě záměrného experimentu)

---

## 6. Jak ověřit po nasazení

- [ ] Velikost / kontrola: produkční `index.html` má řádově **28k+ řádků** (ne ~9k).
- [ ] Po přihlášení: dashboard viditelný, záložky fungují.
- [ ] Přidat vozidlo: formulář včetně volitelné fotky; po uložení fotka v seznamu/detailu.
- [ ] Servisní záznam: pole **Nájezd (km)** a uložení bez chyby v konzoli.
- [ ] DevTools konzole: **žádný** `ReferenceError` na `getCapabilityModuleForTab` / `loadSystemCapabilities`.
- [ ] Síť: načtení `storage_migration.js` **200 OK**.

---

## 7. Commity relevantní pro „poslední dny“ (dle `git log`)

| Commit | Datum (autor git) | Shrnutí |
|--------|-------------------|---------|
| `e4aa067` | 2026-04-07 | Fix capabilities uvnitř `<script>`. |
| `2c5b546` | 2026-04-07 | Technický rename fáze 2 (web storage, …). |
| `6862206` | 2026-04-07 | Viditelné pojmenování Správa vozidel. |
| `39db028` | 2026-04-07 | WEB + iOS service workspace alignment (velký web stav). |

Předchozí významná změna `web/index.html` v historii: `776fd79` (2026-03-27).

---

## 8. Shrnutí pro release engineera

**Správná verze je v Gitu na `main` (HEAD `e4aa067`).**  
Problém na produkci je téměř jistě **nesprávný nasazený artefakt nebo stará kopie**, nikoli chybějící historie v tomto repozitáři. Obnova = **znovu nasadit kompletní `web/` z `main`** a ověřit výše uvedený checklist.

---

## 9. Doplnění sloučená do `main` (web, po 2c74412)

Následující úpravy byly znovu zavedeny do `web/index.html` a zapsány do Gitu jako samostatný commit (aby šly bezpečně stáhnout z GitHubu a nasadit na produkci):

- **Záložka „Přehled“** (`data-tab-key="home"`), funkce `loadHomeDashboard()` (statistiky z `GET /api/v1/vehicles`), výchozí zobrazení po přihlášení pro běžného uživatele (`switchTab('home')`); u servisního režimu je Přehled skrytý.
- **ORV** ve formuláři Přidat vozidlo: nahrání přední/zadní strany, `POST /api/v1/vehicles/parse-orv`, předvyplnění polí, při uložení vozidla odeslání `orv_scan_id` / `orv_number` dle API.
- Drobná úprava textu patičky: **Rychlé sekce ToozServis.cz** (jednotné „Tooz“).

Tyto body doplňují dřívější stav `main` (capabilities uvnitř `<script>`, velký monolitický `index.html`), aniž by se vracela orphan-JS regrese.
