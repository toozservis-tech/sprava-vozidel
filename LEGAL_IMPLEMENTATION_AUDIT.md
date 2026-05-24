# LEGAL_IMPLEMENTATION_AUDIT

Datum auditu: 8. 3. 2026  
Projekt: Správa vozidel  
Rozsah: UI + backend + DB schéma + platební flow + cookies/storage + logování + anti-abuse  
Porovnávané dokumenty: `obchodni-podminky.html`, `reklamacni-rad.html`, `ochrana-osobnich-udaju.html`, `cookies.html`, `platebni-podminky.html`

---

## 1. Audit registrace

### Stav implementace
- Checkbox potvrzení obchodních podmínek při registraci: **NENÍ implementován**.
- Uložení verze dokumentu při registraci: **NENÍ implementováno**.
- Uložení timestamp souhlasu při registraci: **NENÍ implementováno**.
- Uložení vazby souhlasu na `user_id`: **NENÍ implementováno**.

### Důkazy v kódu
- Registrační UI neobsahuje legal checkboxy: `app/web/index.html:7226-7297`.
- Frontend posílá na `/user/register` pouze identifikační údaje bez legal consent polí: `app/web/index.html:10373-10494`.
- Backend model registrace neobsahuje consent/version/timestamp pole: `app/src/server/main.py:566-577`.
- Endpoint `/user/register` consent data neukládá: `app/src/server/main.py:1140-1184`.
- DB tabulka `customers` nemá sloupce pro evidenci akceptace dokumentů (ověřeno přímo ve schématu DB).

### Hodnocení
- **Nesoulad s požadovanou důkazní úrovní clickwrapu.**

---

## 2. Audit plateb

### Stav implementace
- Checkboxy před platbou existují v UI:
  - `licenseAgreeTerms`
  - `licenseAgreeDigitalStart`
  (`app/web/index.html:7111-7125`)
- Chybí explicitní text samostatného potvrzení „beru na vědomí ztrátu práva na odstoupení“.
- Souhlas se kontroluje pouze klientsky (`hasAcceptedPaidPlanLegalConsent`), ale **neodesílá se do backendu**.
- Backend checkout request obsahuje jen `plan` + `billing_period`.
- Neukládá se `user_id`, `timestamp`, `verze dokumentu`, `payment_id/trans_id` jako důkaz souhlasu.

### Platební stavy
- `PAID` aktivuje službu: `app/src/modules/vehicle_hub/routers_v1/license_status.py:548-593`.
- Ne-`PAID` (`PENDING`, `FAILED`, `CANCELLED`, `EXPIRED` atd.) službu neaktivují (`IGNORED`): `.../license_status.py:549-550`.
- Frontend po návratu řeší jen `paid`, `pending`, `cancelled`; jiné stavy jsou jen „Neznámý stav“: `app/web/index.html:11317-11333`.

### Další zjištění
- Není implementováno ukládání payment transakcí do DB tabulky (chybí payment ledger).
- Není implementován interní workflow refund/chargeback (v kódu chybí refund endpointy/logika).
- Není implementován důkazní záznam souhlasu navázaný na `trans_id`.
- Není implementováno systémové e-mailové potvrzení uzavření smlouvy po objednávce (platební flow).

### Důkazy v kódu
- UI checkboxy: `app/web/index.html:7109-7127`.
- Klientská validace souhlasu: `app/web/index.html:11342-11356`.
- Checkout payload bez legal dat: `app/web/index.html:11414-11417`.
- Backend model checkout: `app/src/modules/vehicle_hub/routers_v1/license_status.py:70-73`.
- Platební callback a aktivace: `.../license_status.py:506-598`.
- Dokumentové tvrzení o evidenci souhlasu: `app/web/platebni-podminky.html:124-127`, `app/web/obchodni-podminky.html:152-154`.

---

## 3. Audit logování

### Stav implementace
- Existuje tabulka `security_access_logs` s poli:
  - `customer_id` (uživatel),
  - `created_at` (timestamp),
  - `event_type` (typ akce),
  - `ip_address`,
  - `endpoint`,
  - `user_agent`,
  - `details`.
- Login flow loguje explicitní bezpečnostní eventy (`login_success`, `login_failed`, `login_rate_limited`, 2FA eventy).
- Autorizované API volání logují `api_activity` přes dependency `get_current_user`.

### Omezení
- `api_activity` je throttled (default 90 s na uživatele), takže **ne každý jednotlivý krok je logován**.
- Chybí specializované DB logy pro platby (`trans_id`, payment state transitions, refund decisions).
- Comgate callback používá primárně runtime logger, ne perzistentní auditní záznam v DB.
- Chybí explicitní event log při mazání účtu (`DELETE /user/me`).
- Session ID není v DB jako samostatné pole (IP je přítomná).

### Důkazy v kódu
- Model logu: `app/src/modules/vehicle_hub/models.py:413-439`.
- Logger implementace: `app/src/server/security_tracking.py:332-475`.
- Throttling logů: `app/src/server/security_tracking.py:32`, `414-442`.
- Login eventy: `app/src/server/main.py:1466-1591`, `1690-1698`.
- Export explicitně logován: `app/src/server/main.py:2006-2013`.
- Změna profilu/hesla logována: `app/src/server/main.py:1744-1751`, `2284-2291`.
- Mazání účtu bez explicitního `log_user_activity`: `app/src/server/main.py:2023-2267`.

---

## 4. Audit GDPR

### Stav implementace
- Export dat uživatele implementován (`/user/me/export`) včetně ZIP/JSON/PDF.
- Smazání účtu implementováno (`/user/me` DELETE) jako hard delete navázaných dat.

### Mezery
- Anonymizace (alternativa k výmazu) není implementována.
- Retenční pravidla nejsou implementována jako automatizované purge/job procesy (kromě 2FA challenge cleanup).
- `export_downloaded` při mazání účtu je klientské tvrzení; frontend posílá `true` natvrdo.
- Není samostatný DSAR workflow engine (řízení lhůt, identity challenge flow, evidence vyřízení žádostí).

### Důkazy v kódu
- Export endpoint: `app/src/server/main.py:1764-2020`.
- Delete endpoint: `app/src/server/main.py:2023-2267`.
- Frontend mazání účtu posílá `export_downloaded: true`: `app/web/index.html:19236-19240`.
- Chybí anonymizační logika (v kódu nenalezena).
- Retenční clean-up joby pro logy/doklady nenalezeny.

### Dokument vs implementace
- GDPR dokument uvádí retenční kritéria a zpracování auditních logů (`app/web/ochrana-osobnich-udaju.html:160-166`, `180-183`), ale automatizované retenční vynucování v implementaci není patrné.

---

## 5. Audit cookies

### Stav implementace
- V aplikaci nejsou nalezeny aktivní analytické/marketingové skripty třetích stran.
- Hlavní UI používá technické `localStorage/sessionStorage` klíče pro auth a provoz.
- Consent banner pro analytics/marketing není implementován (aktuálně není nutný, pokud skutečně neběží volitelné cookies).

### Zjištěné mezery proti dokumentaci
- `cookies.html` pokrývá hlavní app klíče, ale neobsahuje některé reálně používané klíče v dalších částech:
  - legacy `token` read fallback (`app/web/index.html:13492`, `14940`),
  - admin klíče `adminAccessToken`, `admin:view:*` (`app/web_admin/admin.js:7`, `225`, `250`),
  - minimal UI klíč `API_URL` (`app/web/index_minimal.html:108`, `286`).

### Důkazy v kódu
- Cookies policy tabulka: `app/web/cookies.html:97-199`.
- Tvrzení „bez analytics/marketing“: `app/web/cookies.html:86`, `209-210`.
- Reálné storage použití: `app/web/index.html:7756-7763`, `7787`, `9106`, `9159`, `10751`, `11939-11940`, `16107`, `13492`, `14940`; `app/web_admin/admin.js:7-8`, `31`, `44`, `225`, `250`; `app/web/index_minimal.html:108`, `286`.

---

## 6. Audit anti-abuse

### Stav implementace
- Globální rate limiting middleware (100 req / 60 s / IP:endpoint).
- Login brute-force limit (5 pokusů / 60 s / email+IP).
- 2FA challenge TTL a limit pokusů.
- Security headers middleware.

### Mezery
- AntiTampering middleware podivné hlavičky pouze loguje, aktivně neblokuje.
- Chybí detekce scraping vzorců (beyond basic rate limit), anomaly scoring, device fingerprint policy.
- Chybí účetní stav pro blokaci/suspendaci uživatele (pro rychlou reakci na abuse).
- V platebním flow není implementována interní risk/fraud/chargeback engine logika navzdory dokumentovým tvrzením.

### Důkazy v kódu
- Middleware registrace: `app/src/server/main.py:380-404`.
- RateLimit middleware: `app/src/core/security_middleware.py:79-133`.
- AntiTampering behavior: `app/src/core/security_middleware.py:136-155`.
- Login limiter: `app/src/server/main.py:1461-1476`.
- Customer model bez `is_blocked/suspended` pole: `app/src/modules/vehicle_hub/models.py:33-75`.

---

## 7. Kritické právní mezery

- ⚠️ **PRÁVNÍ RIZIKO**: Dokumenty tvrdí evidenci souhlasových kroků před platbou (`timestamp`, `user ID`, text, verze dokumentu, IP/relace), ale backend nic takového neukládá.
- ⚠️ **PRÁVNÍ RIZIKO**: Chybí explicitní capture souhlasu „vědomí ztráty práva na odstoupení“ jako samostatně prokazatelný údaj.
- ⚠️ **PRÁVNÍ RIZIKO**: Dokumenty opírají platební/reklamační rozhodování o payment logy a state transitions, ale v DB není payment ledger ani refund/chargeback evidence.
- ⚠️ **PRÁVNÍ RIZIKO**: Rizikové transakce/chargeback abuse jsou deklarovány v platebních podmínkách, ale v implementaci není dohledatelný odpovídající enforcement workflow.
- ⚠️ **PRÁVNÍ RIZIKO**: Důkazní síla auditních logů je oslabena throttlingem `api_activity` (nekompletní chronologie kroků).
- ⚠️ **PRÁVNÍ RIZIKO**: GDPR retenční kritéria nejsou vynucována automatizovaným retenčním mechanismem.
- ⚠️ **PRÁVNÍ RIZIKO**: Cookies policy nemusí být úplná pro všechny části systému (`web_admin`, legacy/minimal klíče).
- ⚠️ **PRÁVNÍ RIZIKO**: Registrace neobsahuje právní clickwrap a důkazní stopu akceptace dokumentů.

---

## 8. Doporučené opravy

### GAP A: Důkazní evidence souhlasu před platbou
- UI: Přidat 3 samostatné checkboxy: (1) seznámení s dokumenty, (2) zahájení plnění před 14 dny, (3) vědomí ztráty práva na odstoupení v rozsahu plnění.
- Backend: Rozšířit `/api/v1/license/comgate/checkout` o povinné `legal_consents` payload + server-side validaci.
- Databáze: Nová tabulka např. `legal_consents` (`id`, `user_id`, `tenant_id`, `context=payment_checkout`, `payment_provider`, `payment_ref/trans_id`, `doc_versions_json`, `consent_text_hash`, `ip`, `user_agent`, `created_at`).
- Dokumenty: Upřesnit, že souhlas je evidován server-side a vazba na transakci je v interním auditním záznamu.

### GAP B: Payment ledger + refund/chargeback audit
- UI: Přidat v profilu sekci „Historie plateb“ a „Žádost o prověření/refund“.
- Backend: Implementovat perzistentní `payment_transactions` + `payment_events` + `refund_requests` endpointy.
- Databáze: Tabulky `payment_transactions`, `payment_state_transitions`, `refund_cases` s vazbou na `user_id`, `tenant_id`, `comgate_trans_id`.
- Dokumenty: Zachovat provider-friendly formulace, ale uvést, že rozhodování probíhá nad interním payment ledgerem + Comgate záznamy.

### GAP C: Registrace a clickwrap
- UI: Přidat checkbox „Souhlasím s OP + GDPR + Cookies“ před registrací s odkazy na verze.
- Backend: Povinně přijímat a ukládat `registration_consent` + verze dokumentů + timestamp.
- Databáze: Sloupce v `customers` nebo samostatná `registration_consents` tabulka.
- Dokumenty: Dopsat do OP proces registrace a důkazní ukládání akceptace i pro free režim.

### GAP D: Logování pro právní obhajobu
- UI: Bez změny nebo volitelně přidat „security activity“ výpis pro uživatele.
- Backend: Pro kritické operace (platba, změna tarifu, upload, export, smazání účtu) zapisovat explicitní eventy (`event_type`) bez throttle skipu.
- Databáze: Rozšířit `security_access_logs` o `session_id` (nebo ekvivalent request correlation id) + `operation_id`.
- Dokumenty: Upravit formulaci tak, aby odpovídala skutečné granularitě logů (nepřehánět kompletnost, dokud nebude implementována).

### GAP E: GDPR retenční vynucení
- UI: Volitelně informační panel o retenčních dobách.
- Backend: Přidat plánované retenční joby (purge/anonymizace dle typu dat a lhůt).
- Databáze: Pomocné retention metadata (`retention_until`, `legal_hold`) tam, kde dává smysl.
- Dokumenty: Jakmile budou lhůty technicky vynuceny, zpřesnit přesné doby místo obecných kritérií.

### GAP F: Cookies policy úplnost
- UI: Zatím bez banneru (pokud opravdu nejsou volitelné cookies); připravit banner pro budoucí analytics.
- Backend/Frontend: Sjednotit a inventarizovat všechny storage klíče napříč `web`, `web_admin`, `index_minimal`.
- Databáze: N/A.
- Dokumenty: Rozšířit cookies tabulku o skutečně používané klíče nebo jasně vymezit, že dokument pokrývá jen konkrétní frontend část.

### GAP G: Anti-abuse enforcement
- UI: N/A.
- Backend: Přidat abuse decision layer (temporary lock/suspend, velocity rules, risk flags pro payments).
- Databáze: Pole `account_status`, `suspended_until`, `risk_level`, `risk_reason` (nebo samostatná `security_flags` tabulka).
- Dokumenty: Potvrdit, že uváděná oprávnění (pozastavení, challenge, omezení) jsou reálně provozována a auditovatelná.

---

## Shrnutí

Implementace má solidní základ v autentizaci, základním logování, exportu a tvrdém výmazu. Největší právní slabina je aktuálně **neexistující server-side důkazní evidence souhlasů v platebním procesu** a **absence perzistentního payment/refund/chargeback audit trailu**, přestože to právní dokumenty výslovně deklarují.
