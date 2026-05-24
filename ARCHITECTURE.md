# Architektura — Správa vozidel

## Přehled

Správa vozidel je monolitická Python/FastAPI aplikace s webovým frontendem (vanilla JS + HTML) a volitelnými mobilními klienty (iOS/Android).

```
Internet → Cloudflare Tunnel → 127.0.0.1:8000 (uvicorn)
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
              FastAPI backend   Static web      web_admin
              (src/server)      (web/)          (web_admin/)
                    │
              SQLite / PostgreSQL (runtime, mimo Git)
                    │
              Externí API (MDČR, NHTSA, Comgate, SMTP, …)
```

## Komponenty

### Backend (`src/`)

- **`src/server/`** — FastAPI aplikace, routy, middleware, bootstrap
- **`src/modules/vehicle_hub/`** — jádro: vozidla, VIN, servis, rezervace, faktury
- **`src/modules/auth/`** — autentizace a autorizace
- **`src/modules/email_client/`** — SMTP e-maily
- **`src/modules/licensing/`** — licence a tarify
- **`src/core/`** — konfigurace, bezpečnost, sdílené utility

### Frontend

- **`web/`** — primární webový klient (uživatelé, servisy)
- **`web_admin/`** — administrace a Developer Control Center

### Migrace

- **`alembic/`** — databázové migrace (spouštět jen s migračním plánem a DB zálohou)

### Testy

- **`tests/`** — API a E2E testy (Playwright)

## Runtime (produkce)

| Parametr | Hodnota |
|----------|---------|
| Host | `127.0.0.1:8000` |
| systemd unit | `toozhub2.service` |
| WorkingDirectory | `/opt/toozhub2/app` |
| ExecStart | `.venv/bin/python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000` |
| Veřejný přístup | Cloudflare Tunnel |

## Databáze

- Produkční DB **není v Gitu** — je to runtime data na serveru.
- Výchozí lokální dev: SQLite v `data/` (gitignored).
- Migrace: Alembic; vždy s plánem rollbacku a zálohou.

## Integrace

- **MDČR / Dataovo** — VIN a registrace vozidel (GDPR guard na cizí VIN)
- **Comgate** — platby (faktury nejsou aktivní, dokud není hotový účetní workflow)
- **SMTP** — transakční e-maily
- **Cloudflare Access** — volitelná ochrana admin rozhraní

## Klienti a source of truth

1. **Server/backend** je source of truth pro business logiku a API kontrakty.
2. **Web** je primární klient — nové funkce se nejdřív implementují v backendu + webu.
3. **iOS/Android** se přizpůsobují backendu, ne naopak.
4. **Staging** není produkční source of truth.

## Bezpečnost

- GDPR VIN guard: cizí VIN nesmí vracet SPZ, MDČR data ani data jiného uživatele.
- Tajemství pouze v `.env` na serveru (šablona: `.env.example`).
- Admin přístup: role `admin` / `developer_admin`; doporučeno Cloudflare Access.

## Production data safety (clean-repo / cleanup)

Production runtime data is never part of Git. The production data paths may be symlinked from the app directory to `/mnt/HC_Volume_105053116/toozhub2`. Never run `rm -rf data/` or `rsync --delete` against the production app tree. Always verify symlinks with `readlink -f` before cleanup.
