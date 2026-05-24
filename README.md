# Správa vozidel

Komplexní webová aplikace pro správu vozidel, servisních záznamů, dokumentů a provozních nástrojů pro autoservisy a majitele vozidel.

## Produkce

| Položka | Hodnota |
|---------|---------|
| URL | [hub.toozservis.cz](https://hub.toozservis.cz) |
| Server path | `/opt/toozhub2/app` |
| systemd | `toozhub2.service` |
| Python venv | `/opt/toozhub2/app/.venv` |
| Backend | `127.0.0.1:8000` |
| Veřejný přístup | Cloudflare Tunnel → `127.0.0.1:8000` |

## Source of truth

**Tento repozitář** (`toozservis-tech/sprava-vozidel`) je nový čistý source of truth pro další vývoj.

Historický repozitář [toozservis-tech/TOOZHUB2](https://github.com/toozservis-tech/TOOZHUB2) slouží pouze jako **archiv historie** — nepoužívejte ho pro nové deploye ani vývoj.

Baseline commit: `clean-production-baseline-20260524` (odvozen z produkčního tagu `prod-support-chat-20260524`).

## Rychlý start (lokální vývoj)

```bash
git clone git@github.com:toozservis-tech/sprava-vozidel.git
cd sprava-vozidel
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Upravte .env pro lokální běh
python -m src.server.main
```

Aplikace běží na `http://127.0.0.1:8000`. Health check: `/health`.

## Co není v Gitu

- `.env` a produkční tajemství
- databáze a runtime data (`data/`, `*.db`)
- uploady, zálohy, snapshots
- virtuální prostředí (`.venv/`)

Produkční DB je runtime data — **záloha DB je povinná před každým deployem nebo migrací**.

## Dokumentace

| Soubor | Obsah |
|--------|-------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Architektura systému |
| [DECISION_RULES.md](DECISION_RULES.md) | Rozhodovací pravidla a zásady |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Nasazení do produkce |
| [RUNBOOK.md](RUNBOOK.md) | Provozní postupy |
| [SAFE_CLEAN_REPO_RUNBOOK.md](SAFE_CLEAN_REPO_RUNBOOK.md) | Bezpečné vytváření clean Git baseline |

## Production data safety (clean-repo / cleanup)

Production runtime data is never part of Git. The production data paths may be symlinked from the app directory to `/mnt/HC_Volume_105053116/toozhub2`. Never run `rm -rf data/` or `rsync --delete` against the production app tree. Always verify symlinks with `readlink -f` before cleanup.

See: `SAFE_CLEAN_REPO_RUNBOOK.md`, `scripts/safety_check_paths.sh`.

## Kontakt (produkce)

- E-mail: podpora@toozservis.cz
- Telefon: +420 731 552 299

## Licence

Vlastnictví TooZ Servis s.r.o. — interní projekt.
