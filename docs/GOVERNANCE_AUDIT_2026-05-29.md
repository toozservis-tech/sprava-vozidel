# Governance Audit — soulad s produktovou ústavou

**Fáze B — Audit proti ústavě**  
**Auditovaný commit:** `80171eaba77e35dd26dea536bbed6154ff25b215` (Governance Layer)  
**Referenční implementace (kontext):** `ddcf68d` (user service requests), `c7b8993` (WO completion panel)  
**Datum auditu:** 2026-05-30  
**Metoda:** statická revize kódu, E2E inventář, PDF šablon, UI vzorů — **bez změn kódu, UI, backendu ani testů**

Závazné dokumenty: `PRODUKTOVA-USTAVA.md`, `DECISION_RULES.md`, `UI_GOVERNANCE.md`, `WORKFLOW_STANDARDS.md`, `PDF_STANDARDS.md`, `ARCHITECTURE.md`, `.cursor/rules/*.mdc`

---

## Executive summary

| Metrika | Hodnota |
|---------|---------|
| **Celkové skóre systému** | **73 %** (průměr 15 oblastí) |
| **Verdikt systému vůči ústavě** | **NEPASS** — produkt funguje, ale PDF, dokumenty, detail vozidla a jednota user UI nesplňují ústavu |
| **Verdikt Fáze B (audit)** | **PASS** — audit kompletní, prioritizovaný, bez kódových změn |

### Nejslabší oblasti (< 60 %)

1. PDF výstupy — **35 %**
2. Dokumenty / náhledy — **41 %**
3. Modaly a panely — **58 %**
4. Navigace a prokliky — **65 %**

### Nejsilnější oblasti (> 85 %)

1. Service dashboard — **92 %**
2. Příjem vozidla — **88 %**
3. Zakázky — **87 %**
4. Sklad dílů — **85 %**

### Doporučená další fáze

**Fáze C1 — PDF & dokumenty** (P0): sjednotit fakturu, nabídku, zakázkový list; náhledové karty v UI.  
**Fáze C2 — Detail vozidla jako hub** (P0): jeden shell, všechny sekce jako karty, bez legacy redirectů.  
**Fáze C3 — User onboarding & design parity** (P1): registrace → první vozidlo → dashboard; user ↔ service vizuální sjednocení.  
**Fáze C4 — Modal cleanup & E2E user** (P1): odstranit nested modaly; doplnit user E2E cyklus.

---

## Výstupní tabulka

| Oblast | Soulad % | Verdikt | P0/P1/P2 | Hlavní problém | Doporučená fáze |
|--------|----------|---------|----------|----------------|-----------------|
| 1. User dashboard | 74 | Částečný | P1 | Dual stack `user-app-next` + legacy `index.html`; chart placeholder | C3 |
| 2. Service dashboard | 92 | Silný | P3 | Drobné limited-placeholdery | — |
| 3. Detail vozidla | 68 | Slabý | **P0** | Většina tabů = placeholder → legacy floating; není centrální hub | C2 |
| 4. Dokumenty | 41 | FAIL | **P0** | Seznam + ikony, chybí preview karty dle §10 | C1 |
| 5. PDF výstupy | 35 | FAIL | **P0** | Faktura/nabídka = Helvetica text; chybí QR, logo, WO PDF | C1 |
| 6. Zakázky | 87 | Silný | P2 | Dokončení inline (OK); chybí PDF zakázkového listu | C1 |
| 7. Faktury | 55 | Slabý | **P0** | Backend + UI flow OK, PDF neodpovídá §7 ústavy | C1 |
| 8. Servisní historie | 70 | Částečný | P1 | User history OK; graf placeholder; servis timeline odděleně | C2 |
| 9. Příjem vozidla | 88 | Silný | P2 | Kroky 1–6 hotové; protokol PDF slabší | C1 |
| 10. Servis ↔ user propojení | 78 | Částečný | P1 | `ddcf68d` opravil viditelnost; stále split UI | C3 |
| 11. Sklad dílů | 85 | Silný | P2 | `service-pro-*`, E2E; vazba na WO badge | — |
| 12. Mobil / tablet | 72 | Částečný | P1 | Servis testuje 390/412/768; user legacy overlay riziko | C4 |
| 13. Navigace / prokliky | 65 | Slabý | P1 | `detailTab` → legacy; BLOCKER handlery; „brzy“ modaly | C2/C3 |
| 14. Modaly a panely | 58 | FAIL | **P0** | `index.html` nested modals; multiple floating roots | C4 |
| 15. E2E pokrytí | 68 | Částečný | P1 | Servis silný; user dashboard/documents bez full cyklu | C4 |

---

## Detailní audit po oblastech

### 1. User dashboard — 74 %

| Pole | Hodnocení |
|------|-----------|
| **Hlavní porušení** | Dual UI stack; `uapp-next-service-requests-dashboard` mimo `service-pro-*` (user výjimka OK, ale vizuálně oddělené); legacy `loadHomeDashboard` hook |
| **Riziko user** | Střední — funkce viditelné po `ddcf68d`, ale konzistence matoucí |
| **Riziko servis** | Nízké |
| **Riziko GDPR** | Nízké — service requests maskují SPZ/VIN |
| **Doporučená oprava** | Sjednotit dashboard do jednoho shellu; odstranit legacy parallel load |
| **Priorita** | P1 |
| **Backend** | Ne |
| **UI** | Ano |
| **PDF/docs** | Ne |
| **E2E** | Ano — rozšířit mimo service-request flow |

**Důkazy:** `web/user-app-next.js` (`renderMainCanvas`, `renderServiceRequestsDashboardCard`), `web/index.html` (legacy home tab).

---

### 2. Service dashboard — 92 %

| Pole | Hodnocení |
|------|-----------|
| **Hlavní porušení** | Občas `service-pro-card--limited` placeholder; KPI ne vždy na všech sekcích |
| **Riziko user** | Nízké |
| **Riziko servis** | Nízké — dobrá orientace |
| **Riziko GDPR** | Nízké |
| **Doporučená oprava** | Doplnit KPI na méně používané sekce |
| **Priorita** | P3 |
| **Backend** | Minimálně |
| **UI** | Ano (kosmetika) |
| **PDF/docs** | Ne |
| **E2E** | Dostatečné (`service-shell-navigation`, dashboard specs) |

**Důkazy:** `web/service-shell.js` (`service-dashboard-pro`, `service-pro-card`), `src/.../service_dashboard.py`.

---

### 3. Detail vozidla — 68 %

| Pole | Hodnocení |
|------|-----------|
| **Hlavní porušení** | Ústava §11 vyžaduje sekce jako karty (Přehled, Dokumenty, Historie, Fotky, Přístupy, STK, Připomínky, Rezervace, Audit). `user-app-next` modal: jen `tech` tab plný, ostatní `uapp-next-detail-tab-placeholder` → `openDetailLegacyTab` do `index.html` |
| **Riziko user** | Vysoké — „centrální hub“ rozbitý mezi dvěma UI |
| **Riziko servis** | Střední — servis timeline v service shell OK |
| **Riziko GDPR** | Střední — split může vést k nekonzistentnímu maskování |
| **Doporučená oprava** | Fáze C2: jeden detail shell, všechny sekce nativně v `uapp-next` |
| **Priorita** | **P0** |
| **Backend** | Minimálně (agregace API) |
| **UI** | Ano (velká) |
| **PDF/docs** | Ne |
| **E2E** | Ano |

**Důkazy:** `user-app-next.js:5441` (placeholder), `openDetailLegacyTab`, `index.html` vehicle-detail panels.

---

### 4. Dokumenty — 41 %

| Pole | Hodnocení |
|------|-----------|
| **Hlavní porušení** | §10 ústavy: chybí karty s náhledem první stránky, stavem, typem, datem, vozidlem. UI = tabulka/řádky + `docPreview` ikonové tlačítko |
| **Riziko user** | Střední — dokumenty existují, ale „sklad dokumentů“ nepůsobí profesionálně |
| **Riziko servis** | Střední |
| **Riziko GDPR** | Nízké |
| **Doporučená oprava** | Document preview cards v `uapp-next` + servis |
| **Priorita** | **P0** |
| **Backend** | Ano (thumbnail/metadata) |
| **UI** | Ano |
| **PDF/docs** | Ano |
| **E2E** | Ano — chybí user documents flow |

**Důkazy:** `user-app-next.js` (`renderDocumentsPage`, `docPreview`), `index.html` doc preview modal.

---

### 5. PDF výstupy — 35 %

| Pole | Hodnocení |
|------|-----------|
| **Hlavní porušení** | `service_invoice_pdf.py`, `service_quote_pdf.py` = ReportLab `drawString` Helvetica — **textový export**. Chybí: QR platba, logo, tabulka položek, patička. `vehicle_report_pdf.py` = profesionální (barvy, logo, QR) — **výjimka**. **Chybí** dedicované WO / intake protokol PDF |
| **Riziko user** | Střední — faktury/reporty nevypadají důvěryhodně |
| **Riziko servis** | Vysoké — servis posílá zákazníkovi „interní výpis“ |
| **Riziko GDPR** | Nízké |
| **Doporučená oprava** | Sjednotit PDF engine na úroveň `vehicle_report_pdf.py`; šablony faktura, nabídka, WO |
| **Priorita** | **P0** |
| **Backend** | Ano |
| **UI** | Ne (preview ano v C1) |
| **PDF/docs** | Ano |
| **E2E** | Ano — PDF snapshot/visual |

**Důkazy:** `src/modules/vehicle_hub/reports/service_invoice_pdf.py`, `service_quote_pdf.py`, `vehicle_report_pdf.py`.

---

### 6. Zakázky — 87 %

| Pole | Hodnocení |
|------|-----------|
| **Hlavní porušení** | Chybí tisknutelný zakázkový list PDF (§8); jinak silný flow |
| **Riziko user** | Nízké |
| **Riziko servis** | Nízké — completion inline panel (`c7b8993`) splňuje §5 |
| **Riziko GDPR** | Nízké |
| **Doporučená oprava** | WO PDF šablona + propojení z completion panelu |
| **Priorita** | P2 |
| **Backend** | Ano (PDF) |
| **UI** | Minimálně |
| **PDF/docs** | Ano |
| **E2E** | Silné (`service-shell-work-orders.spec.ts`, completion tests) |

---

### 7. Faktury — 55 %

| Pole | Hodnocení |
|------|-----------|
| **Hlavní porušení** | API + UI flow (`service-shell-invoice-flow.spec.ts`) vs PDF §7 — propast |
| **Riziko user** | Střední |
| **Riziko servis** | Vysoké — faktura jako hlavní výstup k zákazníkovi |
| **Riziko GDPR** | Střední — faktura obsahuje PII, musí být správně generovaná |
| **Doporučená oprava** | Nová faktura PDF dle `PDF_STANDARDS.md` |
| **Priorita** | **P0** |
| **Backend** | Ano |
| **UI** | Ano (náhled) |
| **PDF/docs** | Ano |
| **E2E** | Rozšířit visual PDF assert |

---

### 8. Servisní historie — 70 %

| Pole | Hodnocení |
|------|-----------|
| **Hlavní porušení** | User `serviceHistory` v uapp-next; chart placeholder; servis timeline odděleně; historický report PDF dobrý, ale UI náhled slabý |
| **Riziko user** | Střední |
| **Riziko servis** | Nízké |
| **Riziko GDPR** | Nízké — owner-safe patterns v API |
| **Doporučená oprava** | Integrovat historii do vehicle detail hub; odstranit placeholder graf |
| **Priorita** | P1 |
| **Backend** | Minimálně |
| **UI** | Ano |
| **PDF/docs** | Ano (náhled reportu) |
| **E2E** | Částečné |

---

### 9. Příjem vozidla — 88 %

| Pole | Hodnocení |
|------|-----------|
| **Hlavní porušení** | Kroky 1–6 wizard OK; kroky 7–10 (dokončení→doklady→historie) navázané přes WO, ne přímo z intake; příjmový protokol PDF chybí |
| **Riziko user** | Nízké |
| **Riziko servis** | Nízké — hlavní flow funguje |
| **Riziko GDPR** | Nízké — work_access / owner link správně |
| **Doporučená oprava** | Intake protokol PDF; explicitní navázání krok 9–10 v UI |
| **Priorita** | P2 |
| **Backend** | Ano (PDF) |
| **UI** | Minimálně |
| **PDF/docs** | Ano |
| **E2E** | Silné (`service-shell-intake-flow.spec.ts`, mobile intake) |

---

### 10. Servis ↔ uživatel propojení — 78 %

| Pole | Hodnocení |
|------|-----------|
| **Hlavní porušení** | `ddcf68d` opravil viditelnost (dashboard, detail, settings); stále dual UI pro access tab (legacy panel v `index.html`) |
| **Riziko user** | Střední — dříve kritické, nyní funkční |
| **Riziko servis** | Nízké — approved/rejected stav OK |
| **Riziko GDPR** | Střední — rejected servis bez owner PII (testováno) |
| **Doporučená oprava** | Sjednotit access sekci do uapp-next; odstranit duplicitní legacy modal |
| **Priorita** | P1 |
| **Backend** | Ne (hotovo) |
| **UI** | Ano |
| **PDF/docs** | Ne |
| **E2E** | Ano (`service-shell-user-service-request-flow.spec.ts`) |

---

### 11. Sklad dílů — 85 %

| Pole | Hodnocení |
|------|-----------|
| **Hlavní porušení** | Route load E2E často mockuje API; plný CRUD cyklus v E2E omezený |
| **Riziko user** | Nízké (servisní modul) |
| **Riziko servis** | Nízké |
| **Riziko GDPR** | Nízké |
| **Doporučená oprava** | Real API E2E pro create/adjust/low-stock |
| **Priorita** | P2 |
| **Backend** | Minimálně |
| **UI** | Minimálně |
| **PDF/docs** | Ne |
| **E2E** | Ano |

**Důkazy:** `service-shell.js` (parts section), `service-shell-inventory.spec.ts`, `service-shell.css`.

---

### 12. Mobil / tablet — 72 %

| Pole | Hodnocení |
|------|-----------|
| **Hlavní porušení** | Servis: viewport testy 390/412/768 v intake/mobile specs. User: `responsive-smoke`, `mobile.spec` — ale legacy `index.html` fixed overlays, nested floating modals |
| **Riziko user** | Střední — přeplácané vrstvy na úzké šířce |
| **Riziko servis** | Nízké |
| **Riziko GDPR** | Nízké |
| **Doporučená oprava** | User mobile pass na 390/412/768; audit overlay stack |
| **Priorita** | P1 |
| **Backend** | Ne |
| **UI** | Ano |
| **PDF/docs** | Ne |
| **E2E** | Ano — user-specific mobile |

**Důkazy:** `service-shell-mobile-intake.spec.ts`, `responsive-smoke.spec.ts`, `.cursor/rules/mobile-tablet-ux.mdc`.

---

### 13. Navigace a prokliky — 65 %

| Pole | Hodnocení |
|------|-----------|
| **Hlavní porušení** | `detailTab:*` → legacy redirect; `console.warn BLOCKER: handler not found`; settings modal „SMS ověření brzy“; share-service modal redirect-only |
| **Riziko user** | Střední — mrtvé nebo nepřímé cesty |
| **Riziko servis** | Nízké |
| **Riziko GDPR** | Nízké |
| **Doporučená oprava** | Audit všech `data-uapp-action` / `BLOCKER`; implementovat nebo odstranit |
| **Priorita** | P1 |
| **Backend** | Částečně (SMS verify) |
| **UI** | Ano |
| **PDF/docs** | Ne |
| **E2E** | Ano — dead link scan |

---

### 14. Modaly a panely — 58 %

| Pole | Hodnocení |
|------|-----------|
| **Hlavní porušení** | Ústava §5 FAIL: `#vehicleDetailModal[data-nested-modal-open]`, `appFloatingModalRoot`, reminder overlay + vehicle floating + uapp detail modal současně. Pozitivum: WO completion **inline** (`service-work-order-completion-panel`) |
| **Riziko user** | Vysoké — ztráta orientace, tap conflicts |
| **Riziko servis** | Střední |
| **Riziko GDPR** | Nízké |
| **Doporučená oprava** | Jeden modal root; floating → inline panels |
| **Priorita** | **P0** |
| **Backend** | Ne |
| **UI** | Ano (velká) |
| **PDF/docs** | Ne |
| **E2E** | Ano |

**Důkazy:** `index.html` (`data-nested-modal-open`, `vehicle-detail-floating-modal`), `user-app-next.js` (`uapp-next-detail-modal`).

---

### 15. E2E pokrytí — 68 %

| Pole | Hodnocení |
|------|-----------|
| **Hlavní porušení** | §13 ústavy: create→edit→delete→detail→reload→login→mobil — **servis** intake/WO/inventory silný; **user** documents/dashboard/history bez full cyklu |
| **Riziko user** | Střední — regrese user flow |
| **Riziko servis** | Nízké |
| **Riziko GDPR** | Střední — owner PII testy existují, ale ne všechny user cesty |
| **Doporučená oprava** | User E2E suite: dashboard, documents, vehicle detail, registration |
| **Priorita** | P1 |
| **Backend** | Ne |
| **UI** | Ne |
| **PDF/docs** | Ne |
| **E2E** | Ano |

**Existující spec soubory (výběr):**  
Servis: `service-shell-intake-flow`, `work-orders`, `invoice-flow`, `inventory`, `user-service-request-flow`, `owner-requests`.  
User: `vehicles`, `reminders`, `responsive-smoke`, `mobile`, `vehicle-lifecycle.auth-smoke`.  
Chybí: user documents E2E, user registration onboarding E2E, PDF visual regression.

---

## Top 10 produktových dluhů

1. **Detail vozidla není centrální hub** — split uapp-next / legacy (§11) — P0  
2. **Faktura PDF neprofesionální** — porušení §7 — P0  
3. **Chybí zakázkový list / intake protokol PDF** — §8 — P0  
4. **Document preview = ikony, ne karty** — §10 — P0  
5. **Nested modaly v legacy vehicle detail** — §5 — P0  
6. **User onboarding po registraci** — chybí vedený flow k prvnímu vozidlu a servisním žádostem — P1  
7. **Dual UI stack user app** — index.html + user-app-next — P1  
8. **Nabídka PDF textový export** — servisní důvěryhodnost — P1  
9. **Navigační BLOCKER handlery** — mrtvé nebo legacy redirect akce — P1  
10. **Design parity user ↔ service** — různé design language — P1  

---

## Top 10 grafických dluhů

1. Faktura PDF — Helvetica řádky místo účetního dokladu 2026  
2. Cenová nabídka PDF — stejný problém  
3. `uapp-next-detail-tab-placeholder` — poloviční detail modal  
4. Service request karta — mimo sjednocený token systém (amber box vs `--sv-*`)  
5. Chart placeholder v service history (`uapp-sh-chart-placeholder`)  
6. Legacy vehicle detail CSS paralelně s uapp-next  
7. Settings modaly vs uapp-next styl (oddělená rodina)  
8. Dokumenty — tabulka místo preview karet  
9. `index.html` horizontal tab remnants vs sidebar model  
10. Inkonsistentní badge/pill styly mezi service-shell a uapp-next  

---

## Top 10 workflow dluhů

1. Detail tab → legacy místo nativní sekce (přerušení flow)  
2. Intake krok 9–10 (doklady→historie) implicitní přes WO, ne explicitní v UI  
3. User registrace → dashboard bez guided checklist  
4. Documents upload → preview → verify — ne jeden lineární flow  
5. Faktura vystavení → PDF → odeslání zákazníkovi — PDF slabé  
6. WO dokončení → faktura → servisní záznam — API OK, UX trhliny  
7. Settings „Sdílet vozidlo“ modal → redirect na directory místo inline  
8. SMS verify placeholder — dead-end modal  
9. Servis rejected access — one-time work OK, UI feedback u servisu variabilní  
10. Rezervace — user flow méně propojený s vehicle hub  

---

## Top 10 PDF / dokumentových dluhů

1. `service_invoice_pdf.py` — bez QR, logo, tabulky, patičky  
2. `service_quote_pdf.py` — textový layout  
3. Chybí **work order PDF** / zakázkový list  
4. Chybí **intake / příjmový protokol PDF**  
5. Faktura — chybí podpis / razítko blok  
6. Faktura — VIN/SPZ v layoutu minimální  
7. UI náhled faktury — není thumbnail karta  
8. UI náhled nabídky — PDF URL, ne preview card  
9. Verified report PDF dobrý, ale UI náhled nekonzistentní s ostatními docs  
10. Technický průkaz — partial preview, ne unified document hub  

---

## Top 10 E2E / test dluhů

1. Chybí user **documents** full cycle E2E  
2. Chybí user **registration → first vehicle** E2E  
3. Chybí user **vehicle detail all tabs** E2E (native, ne legacy)  
4. Chybí **PDF visual regression** (faktura, nabídka, report)  
5. User dashboard E2E jen přes service-request flow  
6. Inventory E2E často mock API — ne real CRUD  
7. Chybí **dead link crawler** E2E user app  
8. Modal stack — ne testováno nested open/close  
9. User mobile 390/412/768 — méně pokrytí než servis  
10. Chybí E2E **invoice → PDF download → obsah** assert  

---

## Doporučené implementační fáze (po auditu)

| Fáze | Název | Priority | Odhad dopadu na skóre |
|------|-------|----------|------------------------|
| **C1** | PDF & document platform | P0 | PDF 35→75, Dokumenty 41→70, Faktury 55→80 |
| **C2** | Vehicle detail hub | P0 | Detail 68→85, Navigace 65→78, Historie 70→82 |
| **C3** | User onboarding & design parity | P1 | User dashboard 74→85, Propojení 78→88 |
| **C4** | Modal cleanup & user E2E | P1 | Modaly 58→80, E2E 68→82, Mobil 72→85 |

**Nepouštět nové feature** mimo tyto fáze, dokud C1 nebo C2 nezvednou P0 oblasti nad 70 %.

---

## Potvrzení Fáze B

| Kontrola | Stav |
|----------|------|
| Kódová změna | **Ne** — pouze tento dokument |
| UI / backend / testy změněny | **Ne** |
| Audit obsahuje procenta | **Ano** — 15 oblastí |
| Audit obsahuje priority P0–P3 | **Ano** |
| Audit obsahuje konkrétní další fáze C1–C4 | **Ano** |
| Top 10 seznamy (5×) | **Ano** |

---

*Auditor: governance audit agent (statická revize). Další audit doporučen po dokončení C1+C2.*
