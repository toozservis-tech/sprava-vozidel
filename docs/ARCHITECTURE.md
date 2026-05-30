# Architektura — Správa vozidel

**STATUS: ŽIVÝ DOKUMENT** — technická mapa; produktová pravidla viz governance vrstva.

---

## Governance vrstva (priorita)

| Dokument | Účel |
|----------|------|
| [PRODUKTOVA-USTAVA.md](./PRODUKTOVA-USTAVA.md) | Produktová vize, zákony, PASS/FAIL |
| [DECISION_RULES.md](./DECISION_RULES.md) | Pořadí priorit, konflikty |
| [UI_GOVERNANCE.md](./UI_GOVERNANCE.md) | Design systém |
| [WORKFLOW_STANDARDS.md](./WORKFLOW_STANDARDS.md) | End-to-end procesy |
| [PDF_STANDARDS.md](./PDF_STANDARDS.md) | Dokumenty a PDF |

**Agenti a revieweři:** nejdřív governance, pak tento dokument, pak feature spec.

---

## Produktová doména

```
                    ┌─────────────┐
                    │   Vehicle   │  ← jediná identita vozidla
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │   Owners   │  │  Services  │  │  Records   │
    │ (customers)│  │ (workshops)│  │ docs, WO,  │
    └────────────┘  └────────────┘  │ STK, …     │
                                    └────────────┘
```

Historie vozidla je **append-only k vozidlu**; majitelé a servisy mají **oprávnění**, ne vlastní kopii vozidla.

---

## Repozitář — hlavní vrstvy

| Vrstva | Cesta | Popis |
|--------|-------|-------|
| Backend API | `app/src/` | FastAPI, moduly `vehicle_hub`, routery v1 |
| Web SPA | `app/web/` | User + service shell, legacy `index.html` |
| Admin | `web_admin/` | Admin rozhraní |
| Testy API | `app/tests/api/` | Pytest |
| Testy E2E | `app/tests/e2e/` | Playwright |
| Migrace | `app/alembic/` | DB schema |
| Docs | `app/docs/` | Governance + provozní dokumentace |

---

## Frontend — dvě aplikace

| Aplikace | Entry | CSS / vzory |
|----------|-------|-------------|
| **User** | `user-app-next.js`, `user-settings.js` | `uapp-next-*`, `user-app-next.css` |
| **Service** | `service-shell.js`, intake, WO | `service-dashboard-pro`, `service-pro-*`, `service-shell.css` |

Design reference (cílový stav): [APP_WIDE_DESIGN_MAP_20260518.md](./APP_WIDE_DESIGN_MAP_20260518.md)

---

## Backend — routery (orientační)

| Prefix | Modul | Doména |
|--------|-------|--------|
| `/api/v1/vehicles` | vehicle routers | CRUD vozidel, dokumenty, záznamy |
| `/api/v1/services` | `services.py`, `service_workspace.py` | Lookup, access requests, approved vehicles |
| `/api/v1/user/service-requests` | `user_service_requests.py` | Majitel — pending žádosti |
| `/api/v1/user/settings` | `user_settings.py` | Nastavení, sdílení |
| `/api/v1/analytics/dashboard` | `analytics.py` | Dashboard souhrny |
| `/api/service/work-orders` | service dashboard | Zakázky servisu |

Podrobná mapa funkcí: [APP_WIDE_FUNCTION_MAP_20260518.md](./APP_WIDE_FUNCTION_MAP_20260518.md)

---

## Autentizace a workspace

- Login: `/user/login`
- User routes: `/web/app/u/{slug}/…`
- Service routes: `/web/app/s/{slug}/…`
- Role: `user` vs `service` — oddělené shelly

---

## Cursor / agent pravidla

| Soubor | Scope |
|--------|-------|
| `/.cursor/rules/produktova-ustava.mdc` | Vždy |
| `/.cursor/rules/ui-governance.mdc` | UI soubory |
| `/.cursor/rules/workflow-governance.mdc` | Flow, API, E2E |
| `/.cursor/rules/pdf-governance.mdc` | PDF, dokumenty |
| `/.cursor/rules/env-restart-backend.mdc` | `.env` změny |
| `/.cursor/rules/mobile-tablet-ux.mdc` | Mobil/tablet |

---

## Provozní dokumenty (doplňkové)

| Dokument | Účel |
|----------|------|
| [MVP_SCOPE_FREEZE.md](./MVP_SCOPE_FREEZE.md) | Feature flags, scope freeze |
| [CELKOVY_STAV_PROJEKTU.md](./CELKOVY_STAV_PROJEKTU.md) | Stav projektu |
| [qa/CONTINUOUS_VALIDATION.md](./qa/CONTINUOUS_VALIDATION.md) | CI / QA |

---

## Plánované fáze

| Fáze | Obsah | Stav |
|------|-------|------|
| **A — Governance** | Tento balík dokumentů + `.mdc` | probíhá |
| **B — Audit** | Soulad % po oblastech | plánováno |
| **C — Vývoj** | Až po auditu nebo výjimce | pozastaveno |

---

*Poslední aktualizace: 2026-05-30 — Fáze A Governance Layer*
