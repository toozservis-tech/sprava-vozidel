# Safe Clean Repo Runbook — Správa vozidel

Provozní runbook pro vytváření **nového Git baseline** bez dotčení produkčních runtime dat.

> **Production runtime data is never part of Git.** The production data paths may be symlinked from the app directory to `/mnt/HC_Volume_105053116/toozhub2`. **Never run `rm -rf data/`** or `rsync --delete` against the production app tree. Always verify symlinks with `readlink -f` before cleanup.

---

## A) Absolutní zákaz

- **Nikdy** nespouštět `rm -rf data/`
- **Nikdy** nespouštět `rm -rf` na cestě bez `readlink -f`
- **Nikdy** nemazat symlink bez kontroly cíle
- **Nikdy** nepoužívat `rsync --delete` proti produkčnímu stromu `/opt/toozhub2/app`
- **Nikdy** nečistit produkční adresář destruktivně
- **Nikdy** nemazat z produkce — clean repo se vytváří **kopírováním ven**, ne úklidem na místě

---

## B) Povinná kontrola před jakýmkoliv mazáním/přesunem

```bash
readlink -f <path>
test -L <path> && echo "symlink" || echo "not symlink"
mountpoint -q <path> && echo "mountpoint" || true
findmnt -T <path>
namei -l <path>
lsof +D <path> 2>/dev/null | head
bash scripts/safety_check_paths.sh <path>
```

Pokud `safety_check_paths.sh` vrátí exit code **20** nebo **21** → **STOP**, nic nemazat.

---

## C) Chráněné produkční cesty

| Cesta | Obsah |
|-------|--------|
| `/mnt/HC_Volume_105053116/toozhub2/root_data/` | Produkční DB (`vehicles.db`), DB zálohy |
| `/mnt/HC_Volume_105053116/toozhub2/app_data/` | Runtime soubory aplikace |
| `/opt/toozhub2/app/data` | **Symlink** → `app_data` (viz výše) |
| `.../app_data/vehicle_photos/` | Fotky vozidel |
| `.../app_data/catalog_vehicle_images/` | Katalogové ilustrace |
| `.../app_data/uploads/` | Uploady |
| `.../app_data/*/` | Ostatní media/document/report adresáře |

---

## D) Správný postup — vytvoření clean repo

1. Cílový adresář musí být **nový prázdný strom** (např. `/opt/toozhub2-clean-production`).
2. Kopírovat **z produkce ven** pomocí `rsync` **bez** `--delete`:

```bash
test ! -e /opt/toozhub2-clean-production || { echo "STOP: target exists"; exit 1; }
mkdir -p /opt/toozhub2-clean-production

rsync -a /opt/toozhub2/app/ /opt/toozhub2-clean-production/ \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude 'data/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude 'backups/' \
  --exclude 'snapshots/' \
  # ... další runtime excludes viz CLEAN_PRODUCTION_REPO_REPORT
```

3. **Nikdy** nemazat nic v `/opt/toozhub2/app`.
4. Pokud se v clean stromu objeví `data/`:
   - ověřit: `ls -la data` a `readlink -f data`
   - pokud je to **symlink** na produkční volume → **nesahat** `rm -rf`
   - odstranit pouze odkaz v clean kopii (viz E)

---

## E) Bezpečné odstranění symlinku v clean kopii

Pouze v **clean** stromu, **po** kontrole cíle:

```bash
cd /opt/toozhub2-clean-production
bash scripts/safety_check_paths.sh ./data || true

if [ -L ./data ]; then
  echo "data is symlink to $(readlink -f ./data)"
  unlink ./data
else
  echo "data is not symlink; inspect before delete"
  exit 1
fi
```

`unlink` maže **jen symlink**, ne obsah cíle. **`rm -rf data/` u symlinku maže cíl — zakázáno.**

---

## F) Zakázaný příklad

```bash
# NIKDY — u symlinku smaže produkční app_data na volume
rm -rf data/

# NIKDY — proti produkci
rsync -a --delete /opt/toozhub2-clean-production/ /opt/toozhub2/app/
```

---

## G) Povinný výstup každého clean-repo agenta

Každý běh musí dokumentovat:

1. **Symlink audit** — `readlink -f /opt/toozhub2/app/data`
2. **Protected paths audit** — `bash scripts/safety_check_paths.sh ./data /mnt/HC_Volume_105053116/toozhub2/root_data`
3. **Potvrzení:** nebylo provedeno `rm -rf` na produkci
4. **Potvrzení:** chráněné cesty nebyly změněny (počet souborů v `vehicle_photos/` před/po)

---

## Incident reference

2026-05-24: `rm -rf data/` v clean stromu se symlinkem na produkční volume smazalo `app_data/vehicle_photos/`. Viz `PRODUCTION_PHOTOS_SERVICES_INCIDENT_20260524.md`.

---

## Související dokumenty

- `scripts/safety_check_paths.sh` — read-only kontrola cest
- `DECISION_RULES.md` — rozhodovací pravidla
- `RUNBOOK.md` — provoz produkce
- `PRODUCTION_DATA_CLEANUP_GUARDRAILS_20260524.md` — report guardrails
