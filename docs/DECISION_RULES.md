# Rozhodovací pravidla — pořadí priorit

**STATUS: ZÁVAZNÉ**

Tento dokument definuje, **kterým pravidlům agent a reviewer dávají přednost**, když si dokumenty nebo požadavky odporují.

---

## Pořadí priorit (sestupně)

| # | Dokument / pravidlo | Co řídí |
|---|---------------------|---------|
| 1 | [PRODUKTOVA-USTAVA.md](./PRODUKTOVA-USTAVA.md) | Produktová vize, PASS/FAIL, zákazy |
| 2 | [DECISION_RULES.md](./DECISION_RULES.md) | Tento dokument — řešení konfliktů |
| 3 | [UI_GOVERNANCE.md](./UI_GOVERNANCE.md) | Vzhled, komponenty, design systém |
| 4 | [WORKFLOW_STANDARDS.md](./WORKFLOW_STANDARDS.md) | End-to-end procesy |
| 5 | [PDF_STANDARDS.md](./PDF_STANDARDS.md) | Dokumenty, faktury, zakázkové listy |
| 6 | [ARCHITECTURE.md](./ARCHITECTURE.md) | Technická struktura, API, moduly |
| 7 | Feature prompt / task spec | Konkrétní fáze implementace |
| 8 | Ad hoc uživatelský komentář | Pouze pokud neporušuje 1–6 |

**Feature prompt nikdy nepřebíjí ústavu.** Pokud prompt žádá nový styl karty nebo fake UI, ústava vyhrává → FAIL nebo nejdřív návrh.

---

## Verdikt PASS / FAIL

### Automatický FAIL

- Funkce funguje, ale **rozbíjí jednotný vzhled** (§2 ústavy)
- **Modal v modalu** nebo fake approve/reject
- **PDF** vypadá jako textový export
- **Mrtvé tlačítko** nebo placeholder success
- **Data navázaná na user** místo na vozidlo (kde jde o historii vozidla)
- **E2E** neprojde povinným cyklem (§13 ústavy)
- **Mobil** — horizontální scroll, tap < 44px, skryté akce

### Podmíněný PASS

- API testy zelené, ale chybí grafický / workflow / dokumentový audit → **PASS zakázán** do doplnění §15 ústavy

### PASS

- Splněn feature cíl **a** soulad s ústavou **a** kompletní gate report (15 bodů)

---

## Konflikty mezi user a service UI

| Oblast | Pravidlo |
|--------|----------|
| Servisní obrazovky | `service-dashboard-pro`, `service-pro-*` |
| Uživatelské obrazovky | `uapp-next-*`, tokeny z [APP_WIDE_DESIGN_MAP_20260518.md](./APP_WIDE_DESIGN_MAP_20260518.md) |
| Společné | Stejná sémantika barev, stejná logika workflow, **ne** kopírování CSS 1:1 bez mapování |

Jednotný **produkt** ≠ jeden CSS soubor. Jednotný **dojem** a **interakční vzory** jsou povinné.

---

## Governance vs. vývoj

| Fáze | Povolená práce |
|------|----------------|
| **A — Governance** | Dokumentace, `.cursor/rules`, audity — **bez nových feature** |
| **B — Audit** | Hodnocení souladu proti ústavě — **bez nových feature** |
| **C — Vývoj** | Implementace až po schváleném auditu nebo explicitní výjimce |

---

## Odkazy na Cursor pravidla

Agent musí respektovat:

- `/.cursor/rules/produktova-ustava.mdc` — vždy
- `/.cursor/rules/ui-governance.mdc` — při úpravách UI
- `/.cursor/rules/workflow-governance.mdc` — při flow a API
- `/.cursor/rules/pdf-governance.mdc` — při PDF a dokumentech
- `/.cursor/rules/env-restart-backend.mdc` — po změně `.env`
- `/.cursor/rules/mobile-tablet-ux.mdc` — mobil/tablet

---

*Poslední aktualizace: 2026-05-30 — Fáze A Governance Layer*
