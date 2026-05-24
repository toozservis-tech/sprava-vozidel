# GitHub Push Report — 20260524

## 1. PASS / FAIL

**FAIL** — push na GitHub neproběhl (autentizace / přístup k novému repu).

Pre-push kontroly clean repa: **PASS**  
Produkce: **beze změny**

---

## 2. remote URL

```
origin  git@github.com:toozservis-tech/sprava-vozidel.git (fetch)
origin  git@github.com:toozservis-tech/sprava-vozidel.git (push)
```

Remote **není** `toozservis-tech/TOOZHUB2`.

---

## 3. pushed branch

**NE** — `git push -u origin main` selhalo.

---

## 4. pushed tags

**NE** — `git push origin --tags` nebylo spuštěno (main push selhal).

---

## 5. clean repo HEAD (před reportem)

`95ddd9f15c7783e8c336bcec0f6959398d9642d5`

---

## 6. forbidden files check

**PASS** — 0 souborů

---

## 7. symlink check

**PASS** — žádný symlink na `/mnt/HC_Volume_105053116/toozhub2` ani `/opt/toozhub2/app/data`

---

## 8. secrets check

**PASS** — žádné PEM klíče; grep bez produkčních tajemství

---

## 9. produkce změněna?

**NE**

---

## 10. produkce restartována?

**NE**

---

## 11. runtime produkce

```
ActiveState=active
SubState=running
NRestarts=0
ExecMainPID=2724976
```

---

## 12. health

**OK** — `{"status":"ok","environment":"production",...}`

---

## Chyba push

```
ERROR: Repository not found.
fatal: Could not read from remote repository.
```

**Diagnóza:** SSH klíč `~/.ssh/toozhub2_github_deploy` funguje pro `toozservis-tech/TOOZHUB2` (`git ls-remote` OK), ale **nemá přístup** k `toozservis-tech/sprava-vozidel`. GitHub u deploy key vrací „Repository not found“, pokud klíč není registrovaný u cílového repa.

SSH test: `ssh -T git@github.com` → `Hi toozservis-tech/TOOZHUB2!`

---

## Oprava (vyžaduje akci na GitHubu)

### Varianta A — deploy key (doporučeno pro server)

1. GitHub → `toozservis-tech/sprava-vozidel` → **Settings** → **Deploy keys** → **Add deploy key**
2. Title: `toozhub2-production-deploy`
3. Key (veřejný):

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILYatj9lXmALom+erb/iAMO2AcKrYOw1mTjdUPLHPs+R toozhub2-production-deploy@toozservis.cz
```

4. Zaškrtnout **Allow write access**
5. Na serveru znovu:

```bash
cd /opt/toozhub2-clean-production
git push -u origin main
git push origin --tags
```

### Varianta B — gh CLI s PAT

```bash
gh auth login
cd /opt/toozhub2-clean-production
git push -u origin main
git push origin --tags
```

---

## 13. Verdikt

**PUSH BLOCKED — CLEAN REPO READY, GITHUB ACCESS MISSING**

Clean repo je připraven; po přidání deploy key nebo `gh auth login` spusťte push znovu.

---

*Report: 2026-05-24 UTC*
