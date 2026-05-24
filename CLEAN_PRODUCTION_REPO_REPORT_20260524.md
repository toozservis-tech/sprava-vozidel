# Clean Production Repository Report — 20260524

## 1. Původní produkční path

`/opt/toozhub2/app`

## 2. Původní commit

`9ed987b7eb6144191d1df33508f9878041e45712`

## 3. Původní tag

`prod-support-chat-20260524`

## 4. Starý GitHub repo

[toozservis-tech/TOOZHUB2](https://github.com/toozservis-tech/TOOZHUB2) — archiv historie, nemazat.

## 5. Nový doporučený GitHub repo

`toozservis-tech/sprava-vozidel`

Alternativa: `toozservis-tech/sprava-vozidel-production`

## 6. Nový clean repo path

`/opt/toozhub2-clean-production`

## 7. Nový clean commit

`2d19fc906435bc17af27daa7ee63023d5e224299`

## 8. Nový clean tag

`clean-production-baseline-20260524`

## 9. Co nebylo přeneseno

| Kategorie | Položky |
|-----------|---------|
| Git historie | `.git/` (archivováno zvlášť) |
| Runtime env | `.env`, `.env.*` (kromě `.env.example`) |
| Virtuální prostředí | `.venv/` |
| Databáze | `data/`, `*.db`, `*.sqlite*`, `vehicles.db` |
| Tajemství | `private_key.pem` |
| Uploady/zálohy | `backups/`, `snapshots/`, `releases/`, `worktrees/`, `incoming/` |
| Cache | `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `node_modules/` |
| Dev/audit | `.cursor/`, `cursor_chat_tools/`, `scripts/cursor_chat_tools/` |
| Runtime junk | `.local-libs/`, `.cloudflare_url`, `.tmp-simple-icons/`, `=*` prázdné soubory, `.aider.input.history` |
| Logy | `*.log`, `*.pid`, `logs/` |
| Test reporty | `playwright-report/`, `.pw-*-report/` |
| Audit markdown | `PRODUCTION_RUNTIME_REPAIR_20260524.md`, `SERVER_PRODUCTION_CLEANUP_AUDIT_20260524.md` |
| HTML backupy | `web/index.html.backup_*`, `web_admin/admin.js.bak` |

**Poznámka:** Clean baseline používá **committed HEAD** verze souborů `analytics.py` a `web/index.html`, ne necommitnuté lokální úpravy na produkci.

## 10. Secret/data kontrola

| Kontrola | Výsledek |
|----------|----------|
| `find` zakázané soubory | **PASS** — po cleanupu 0 nálezů |
| `private_key.pem` | **Odstraněn** z clean stromu (zůstal na produkci) |
| `data/` runtime | **Odstraněn** z clean stromu |
| PEM klíče v clean stromu | **PASS** — žádné |
| Grep secret patterns | **PASS s poznámkou** — shody jsou v kódu (env var názvy), `.env.example` šablonách, migračních skriptech a testech; žádné produkční tajemství v clean stromu |

## 11. Build/syntax testy

| Test | Výsledek |
|------|----------|
| `python3 -m compileall src` | **PASS** (exit 0) |
| `node --check web/user-app-next.js` | **PASS** |
| `node --check web/user-settings.js` | **PASS** |
| `node --check web/service-shell.js` | **PASS** |
| `node --check web/sw.js` | **PASS** |
| `node --check web/tutorial-hub.js` | **PASS** |
| `node --check web/security_protection.js` | **PASS** |
| `node --check web/storage_migration.js` | **PASS** |
| `node --check web/ai-features.js` | **PASS** |
| `node --check web/user-dashboard-prototype.js` | **PASS** |

## 12. Diff kontrola proti produkci

Soubor: `/opt/archive/git-history-20260524/clean_repo_diff.txt` (126 řádků)

Rozdíly jsou **očekávané**:
- Runtime soubory pouze na produkci (`private_key.pem`, `vehicles.db`, logy, `.cloudflare_url`, `.local-libs/`, `=*` junk)
- Nové governance docs v clean repu (`ARCHITECTURE.md`, `DECISION_RULES.md`, `DEPLOYMENT.md`, `RUNBOOK.md`, aktualizovaný `README.md`, `.gitignore`)
- `analytics.py` a `web/index.html` — clean = HEAD commit, produkce = necommitnuté lokální změny
- Playwright reporty a audit soubory pouze na produkci

**Produkční kód není chybějící.**

## 13. Navržený GitHub remote

```bash
git remote add origin git@github.com:toozservis-tech/sprava-vozidel.git
```

## 14. Push příkazy (NEPROVEDENY — čeká na potvrzení)

```bash
cd /opt/toozhub2-clean-production

# 1. Vytvořte prázdný repo na GitHubu: toozservis-tech/sprava-vozidel

git remote add origin git@github.com:toozservis-tech/sprava-vozidel.git
git push -u origin main
git push origin clean-production-baseline-20260524
```

**Doporučení visibility:** **private** — repo obsahuje interní obchodní logiku autoservisní platformy.

## 15. Doporučený další krok

1. Vytvořit prázdný GitHub repo `toozservis-tech/sprava-vozidel` (private).
2. Po potvrzení spustit push příkazy výše.
3. Nastavit branch protection na `main`.
4. Aktualizovat lokální dev workflow — klonovat nový repo místo TOOZHUB2.
5. Produkční deploy path (`/opt/toozhub2/app`) zatím neměnit — až po schválení migračního plánu.

---

## Archiv starého Gitu

| Soubor | Path |
|--------|------|
| Git tarball | `/opt/archive/git-history-20260524/toozhub2_git_history_20260524.tar.gz` (87 MB) |
| Branches | `/opt/archive/git-history-20260524/branches.txt` |
| Tags | `/opt/archive/git-history-20260524/tags.txt` |
| Graph | `/opt/archive/git-history-20260524/git_graph.txt` |
| Status před clean | `/opt/archive/git-history-20260524/status_before_clean_repo.txt` |
| Diff report | `/opt/archive/git-history-20260524/clean_repo_diff.txt` |

Starý `.git` v `/opt/toozhub2/app` **nebyl smazán**.

---

## Produkční git status před clean (zaznamenáno)

**Tracked modified:**
- `src/modules/vehicle_hub/routers_v1/analytics.py`
- `web/index.html`

**Untracked:**
- `.cursor/`
- `PRODUCTION_RUNTIME_REPAIR_20260524.md`
- `SERVER_PRODUCTION_CLEANUP_AUDIT_20260524.md`
- `scripts/cursor_chat_tools/`

## Step 1 poznámka — systemd

V době kontroly `toozhub2.service` vykazoval restart loop (exit code 1), ale `/health` na `127.0.0.1:8000` odpovídal OK. Produkce nebyla restartována ani měněna tímto procesem.

---

*Report vygenerován: 2026-05-24*
