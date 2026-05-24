# Runbook — Správa vozidel

Provozní postupy pro produkci hub.toozservis.cz.

## Rychlá diagnostika

```bash
# Stav služby
systemctl status toozhub2.service --no-pager -l

# Health check
curl -fsS http://127.0.0.1:8000/health

# Poslední logy
journalctl -u toozhub2.service -n 100 --no-pager

# Aktuální commit
cd /opt/toozhub2/app && git rev-parse HEAD && git describe --tags
```

## Restart backendu

Pouze když je potřeba (deploy, změna `.env`):

```bash
sudo systemctl restart toozhub2.service
curl -fsS http://127.0.0.1:8000/health
```

## Záloha databáze

### Přes Developer Control Center (doporučeno)

1. Přihlásit se na https://hub.toozservis.cz/web_admin/ jako `developer_admin`
2. Sekce **Backup & Restore** → **Vytvořit backup**
3. Ověřit, že záloha obsahuje DB a je mladší než 72 h

### Před migrací nebo deployem

Záloha je **povinná**. Bez zálohy deploy neprovádět.

## Rollback

1. Zastavit deploy / identifikovat problémový commit
2. Obnovit DB ze zálohy (Control Center nebo ručně)
3. `git checkout <previous-tag>` v `/opt/toozhub2/app`
4. `sudo systemctl restart toozhub2.service`
5. Ověřit `/health` a kritické user flows

## Admin přístup

- URL: https://hub.toozservis.cz/web_admin/
- Role: `admin` nebo `developer_admin`
- Developer Control Center: pouze `developer_admin`
- Návod: `deploy/PRODUCTION_ACCESS.txt`

## Logy a monitoring

```bash
# Průběžné sledování
journalctl -u toozhub2.service -f

# System health v adminu
# Developer Control Center → System Health
```

## GDPR VIN incident

Pokud cizí VIN vrátí SPZ/MDČR/cizí data:

1. **STOP** — neprovádět další deploy
2. Zaznamenat VIN, uživatele, timestamp, endpoint
3. Eskalovat na `developer_admin`
4. Oprava + regression test na VIN guard

## Kontakty

- podpora@toozservis.cz
- +420 731 552 299

## Archiv Git historie

Starý Git repozitář archivován:

```
/opt/archive/git-history-20260524/
├── toozhub2_git_history_20260524.tar.gz
├── branches.txt
├── tags.txt
├── git_graph.txt
└── status_before_clean_repo.txt
```

Nový clean baseline: `/opt/toozhub2-clean-production/`

## Production data safety (clean-repo / cleanup)

Production runtime data is never part of Git. The production data paths may be symlinked from the app directory to `/mnt/HC_Volume_105053116/toozhub2`. Never run `rm -rf data/` or `rsync --delete` against the production app tree. Always verify symlinks with `readlink -f` before cleanup.

Před clean-repo operací: `bash scripts/safety_check_paths.sh ./data`
