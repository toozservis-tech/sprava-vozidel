# Production Data Cleanup Guardrails — 20260524

## 1. PASS / FAIL

**PASS**

---

## 2. Incident summary

2026-05-24: Při vytváření clean repo v `/opt/toozhub2-clean-production` bylo spuštěno `rm -rf data/`. Adresář `data` byl **symlink** na `/mnt/HC_Volume_105053116/toozhub2/app_data`. Důsledek: smazání produkčních fotek a runtime souborů na volume (obnoveno ze zálohy, 2 fotky stále chybí).

Viz: `PRODUCTION_PHOTOS_SERVICES_INCIDENT_20260524.md`

---

## 3. Protected paths

| Cesta | Typ |
|-------|-----|
| `/mnt/HC_Volume_105053116/toozhub2/root_data/` | Produkční DB |
| `/mnt/HC_Volume_105053116/toozhub2/app_data/` | Runtime data (fotky, uploady, …) |
| `/opt/toozhub2/app/data` | Symlink → `app_data` |
| `app_data/vehicle_photos/` | Fotky vozidel |
| `app_data/catalog_vehicle_images/` | Katalogové ilustrace |
| `app_data/uploads/` | Uploady |

**Poznámka:** `/opt/toozhub2-clean-production/data` stále ukazuje symlink na produkční volume — `safety_check_paths.sh` vrací exit **21**. V budoucnu odstranit **`unlink ./data`**, ne `rm -rf`.

---

## 4. New runbook

`SAFE_CLEAN_REPO_RUNBOOK.md` — absolutní zákazy, kontrolní příkazy, správný rsync postup, bezpečné `unlink` symlinku.

---

## 5. New safety script

`scripts/safety_check_paths.sh` — read-only audit, exit 20/21 pro protected paths.

---

## 6. Test outputs

**Produkce (`/opt/toozhub2/app`):**

```
bash -n scripts/safety_check_paths.sh  → OK
bash scripts/safety_check_paths.sh ./data  → exit 21 (SYMLINK TO PROTECTED PRODUCTION DATA)
bash scripts/safety_check_paths.sh /mnt/.../root_data  → exit 20 (PROTECTED PRODUCTION DATA PATH)
```

**Clean repo (`/opt/toozhub2-clean-production`):**

```
bash -n scripts/safety_check_paths.sh  → OK
bash scripts/safety_check_paths.sh ./data  → exit 21
```

Skript **nic nemazal**.

---

## 7. Changed files

| Soubor | Akce |
|--------|------|
| `SAFE_CLEAN_REPO_RUNBOOK.md` | Nový |
| `scripts/safety_check_paths.sh` | Nový |
| `README.md` | Varování |
| `ARCHITECTURE.md` | Nový v prod + varování |
| `DECISION_RULES.md` | Nový v prod + pravidlo |
| `DEPLOYMENT.md` | Nový v prod + varování |
| `RUNBOOK.md` | Nový v prod + varování |
| `CLEAN_PRODUCTION_REPO_REPORT_20260524.md` | Doplněn incident + guardrails |

---

## 8. Production commit / tag

(viz git po commitu)

---

## 9. Clean commit / tag

(viz git po commitu)

---

## 10. Production restarted?

**NE**

---

## 11. DB changed?

**NE**

---

## 12. .env changed?

**NE**

---

## 13. GitHub push?

**NE**

---

## 14. Verdict

**PRODUCTION DATA CLEANUP GUARDRAILS ADDED**

---

## Rizikové výskyty v kódu (audit)

| Soubor | Riziko | Poznámka |
|--------|--------|----------|
| `scripts/ensure_api_running.sh` | `fuser -k 8000/tcp` | Watchdog mimo systemd — není v cronu |
| `scripts/backup_volume_data.sh` | `shutil.rmtree` | Pouze staré zálohy v backup adresáři |
| `CRITICAL_RESTART.md`, `RESTART_INSTRUCTIONS.md` | `fuser -k 8000` | Dokumentace — agenti nemají spouštět |
| Cursor historie | `fuser`, `nohup` | Archiv — viz runtime repair reporty |

*Report: 2026-05-24 UTC*
