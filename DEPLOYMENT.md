# Deployment — Správa vozidel

## Produkční prostředí

| Položka | Hodnota |
|---------|---------|
| URL | https://hub.toozservis.cz |
| Server path | `/opt/toozhub2/app` |
| systemd | `toozhub2.service` |
| Backend bind | `127.0.0.1:8000` |
| Veřejný přístup | Cloudflare Tunnel → `127.0.0.1:8000` |
| Python venv | `/opt/toozhub2/app/.venv` |

## Před deployem (povinné)

1. **Záloha DB** — Developer Control Center → Backup & Restore, nebo ruční snapshot.
2. **Git tag** na deploy commit (např. `prod-YYYYMMDD-popis`).
3. **Migrační plán** — pokud obsahuje Alembic migrace, otestovat na kopii DB.
4. **Rollback plán** — předchozí tag + obnova DB ze zálohy.

## Deploy postup (typický)

```bash
# Na serveru jako uživatel s oprávněním
cd /opt/toozhub2/app

# 1. Záloha (viz RUNBOOK.md)

# 2. Stáhnout nový kód
git fetch origin
git checkout <tag-nebo-commit>

# 3. Závislosti (pokud se změnily)
source .venv/bin/activate
pip install -r requirements.txt

# 4. Migrace (pokud jsou)
alembic upgrade head

# 5. Restart
sudo systemctl restart toozhub2.service

# 6. Ověření
curl -fsS http://127.0.0.1:8000/health
```

> **Poznámka:** Po změně `.env` je restart backendu povinný — proměnné se načítají jen při startu.

## Co se nedeployuje z Gitu

- `.env` — zůstává na serveru, ruční správa
- `data/` — runtime data, uploady, DB
- `.venv/` — vytváří se na serveru

## Production data safety (clean-repo / cleanup)

Production runtime data is never part of Git. The production data paths may be symlinked from the app directory to `/mnt/HC_Volume_105053116/toozhub2`. Never run `rm -rf data/` or `rsync --delete` against the production app tree. Always verify symlinks with `readlink -f` before cleanup.

## Cloudflare

- Tunnel směruje veřejný provoz na `127.0.0.1:8000`.
- Cloudflare Access (volitelné) chrání `/web_admin/`, `/admin-api/`, `/admin-static/`.
- Konfigurace Cloudflare se nemění bez plánu — viz `.env.example` pro Access proměnné.

## Nový GitHub repo

Pro nový vývojový workflow:

```bash
git remote add origin git@github.com:toozservis-tech/sprava-vozidel.git
git push -u origin main
git push origin clean-production-baseline-20260524
```

Doporučení: **private** repo (obsahuje interní obchodní logiku).

## Historický repo

[toozservis-tech/TOOZHUB2](https://github.com/toozservis-tech/TOOZHUB2) — archiv, nemazat, nepoužívat pro nové deploye.
