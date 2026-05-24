# Staging-only UI workflow

Datum: 2026-05-19

Tento dokument je ochranné pravidlo pro další UI vývoj projektu Správa vozidel. Vznikl po zjištění, že úpravy určené pro staging se propsaly i do produkčního working tree.

## Závazná pravidla

1. Produkce se nesmí upravovat při vývoji UI.
2. Veškerý UI vývoj běží pouze v `/opt/toozhub2-staging/app`.
3. Deploy pouze přes `toozhub2-staging.service`.
4. Produkční služba `toozhub2.service` se nesmí restartovat.
5. Produkční working tree `/opt/toozhub2/app` se nesmí checkoutovat na experimentální větve.
6. Produkce se aktualizuje až po ručním schválení a merge/release procesu.
7. Každý další prompt pro UI musí obsahovat:
   - `STAGING ONLY`
   - produkci neměnit
   - `service-shell.js` neměnit, pokud se řeší user app
   - backend/DB neměnit
8. Před každým staging deployem ověř:
   - `pwd = /opt/toozhub2-staging/app`
   - `service = toozhub2-staging.service`
   - `port = 8010`
   - `URL = staging.hub.toozservis.cz`

## Povolený staging postup

Před změnou UI:

```bash
cd /opt/toozhub2-staging/app
pwd
git branch --show-current
git status --short
systemctl is-active toozhub2-staging.service
curl -fsS http://127.0.0.1:8010/health
```

Před staging deployem:

```bash
pwd
git status --short
git rev-parse HEAD
systemctl cat toozhub2-staging.service
grep -E "DATABASE_URL|APP_ENV|ENVIRONMENT|PORT" /opt/toozhub2-staging/app/.env || true
```

Deploy je povolen pouze tak, aby cílil na staging:

```bash
sudo systemctl restart toozhub2-staging.service
systemctl is-active toozhub2-staging.service
curl -fsS http://127.0.0.1:8010/health
```

## Zakázané příkazy při UI vývoji

Zakázáno v `/opt/toozhub2/app`:

```bash
git checkout
git pull
git reset
git clean
git merge
sudo systemctl restart toozhub2.service
systemctl restart toozhub2.service
```

Zakázáno bez ručního release schválení:

- jakýkoliv deploy na `hub.toozservis.cz`
- změna branch produkčního working tree
- restart produkční služby
- změna produkční DB `/opt/toozhub2/data/vehicles.db`
- změna produkční nginx konfigurace

## Aktuální oddělení prostředí

Produkce:

- cesta: `/opt/toozhub2/app`
- služba: `toozhub2.service`
- DB: `/opt/toozhub2/data/vehicles.db`
- URL: `https://hub.toozservis.cz`
- port: `127.0.0.1:8000`

Staging:

- cesta: `/opt/toozhub2-staging/app`
- služba: `toozhub2-staging.service`
- DB: `/opt/toozhub2-staging/data/vehicles_staging.db`
- URL: `https://staging.hub.toozservis.cz`
- port: `127.0.0.1:8010`

## Incident note

Produkční a staging cesty nejsou symlinkované, ale produkční working tree byl na feature branchi s public/auth redesignem. Staging navíc obsahuje lokální remote `apprepo` na `/opt/toozhub2/app`, takže předchozí staging deploye tahaly změny z produkčního working tree. Pro další UI práci musí být výchozím pracovním adresářem vždy `/opt/toozhub2-staging/app` a produkční working tree se nesmí používat jako staging zdroj změn.
