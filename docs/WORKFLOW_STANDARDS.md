# Workflow standardy — end-to-end procesy

**STATUS: ZÁVAZNÉ** — podřízeno [PRODUKTOVA-USTAVA.md](./PRODUKTOVA-USTAVA.md)

---

## Zásada

Každá funkce je **článek řetězce**, ne izolovaný endpoint nebo obrazovka.

Data flow vždy směřuje k **jednomu vozidlu** (`vehicle_id`). Uživatel a servis jsou aktéři, ne primární klíč historie.

---

## Referenční flow: Příjem vozidla (servis)

| Krok | Název | Výstup / stav | Navazuje na |
|------|-------|---------------|-------------|
| 1 | Vyhledání vozidla | lookup, masked VIN/SPZ | 2 |
| 2 | Volba režimu | owner link **nebo** one-time work | 3 |
| 2a | Žádost o propojení | `ServiceAccessRequest` pending | user approve → approved access |
| 2b | Jednorázový zásah | `work_access` bez owner PII | 3 |
| 3 | Fotodokumentace příjmu | fotky k case/WO | 4 |
| 4 | Příjmový protokol | protokol PDF / data | 5 |
| 5 | Návrh zakázky | WO draft / `intake_pending` | 6 |
| 6 | Přijetí technikem | WO accepted | 7 |
| 7 | Práce | položky, čas, díly | 8 |
| 8 | Dokončení | inline completion panel, stav WO | 9 |
| 9 | Doklady | faktura, PDF | 10 |
| 10 | Servisní historie | `ServiceRecord` na vozidle | — |

**FAIL**, pokud krok existuje bez navazujícího kroku nebo bez API persistence.

---

## Referenční flow: Propojení servis ↔ majitel

| Krok | Aktér | Akce |
|------|-------|------|
| 1 | Servis | Vytvoří access request |
| 2 | Majitel | Vidí žádost (dashboard, detail vozidla, nastavení) |
| 3 | Majitel | Schválí nebo zamítne |
| 4 | Systém | `VehicleServiceLink` nebo rejected |
| 5 | Servis | Vidí approved / rejected stav |
| 6 | Servis (rejected) | Nesmí vidět owner PII; může one-time work |

UI povinná místa pro krok 2: viz implementace `ddcf68d` + ústava §11.

---

## Referenční flow: Majitel — životní cyklus vozidla

| Oblast | Minimální workflow |
|--------|-------------------|
| Registrace | účet → přidání vozidla → dashboard |
| STK / připomínky | termín → upozornění → detail vozidla |
| Dokumenty | upload → kategorizace → náhled |
| Servisní historie | záznamy z approved servisů + vlastní |
| Přístupy servisů | schvalování / odebrání |

**Očekávaný dluh:** uživatelské workflow po registraci — audit Fáze B.

---

## API tok — obecná pravidla

1. **Create** musí mít **list** a **detail** pro oprávněné role  
2. **Approve / reject** musí měnit stav čitelný oběma stranami  
3. **Delete / revoke** musí mít audit stopu  
4. Side effect (email, notifikace) nesmí nahradit persistenci stavu  

---

## E2E povinnost (každá nová funkce)

Pro každý nový workflow scénář:

1. Vytvoření  
2. Editace  
3. Smazání (nebo revoke)  
4. Detail  
5. Reload stránky  
6. Odhlášení + přihlášení  
7. Mobil (390×844 min.)  

Bez projítí cyklu: **PASS zakázán** (ústava §13).

---

## Stav propojení oblastí (orientační, 2026-05)

| Oblast | Poznámka |
|--------|----------|
| Intake → zakázka → práce → dokončení | Relativně dobře propojeno |
| Dokončení → faktura → servisní záznam | Částečně |
| User ↔ servis schvalování | Opraveno `ddcf68d` |
| PDF / náhledy | Slabé — priorita auditu |
| Detail vozidla jako hub | Částečné — priorita auditu |

Přesná procenta doplní **Fáze B — Audit proti ústavě**.

---

*Poslední aktualizace: 2026-05-30 — Fáze A Governance Layer*
