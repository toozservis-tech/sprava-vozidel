# GitHub Actions Status — 20260524

## 1. PASS / FAIL

**PASS** — CI Baseline zelený; prod-smoke a definition-of-done opraveny na secret-safe preflight logiku.

---

## 2. Aktuální origin/main HEAD

```
1c5f540f2d67ae533bd68cf2a3c504bc046842ee
Make production smoke workflows manual and secret-safe
```

Report commit (po tomto souboru): viz sekce 9.

Historie oprav:

| Commit | Popis |
|--------|-------|
| `416e20e` | Workflow baseline — manual only pro těžké testy |
| `745a738` | CI Baseline guard — povolen `.env.example` |
| `fbe807a` | Status report |
| `1c5f540` | Preflight logika pro prod-smoke + definition-of-done |

---

## 3. Co padalo a proč

### `prod-smoke.yml`

**Root cause:** Job-level `if: ${{ secrets.PROD_E2E_EMAIL != '' && ... }}` — GitHub Actions **nepovoluje** `secrets` v job `if` kontextu. Workflow selže při parsování/validaci ještě před spuštěním jobů.

**Projev v UI:** Immediate workflow failure bez běžícího Playwright kroku.

### `definition-of-done.yml`

**Root cause:** Stejný problém — `prod-readonly-smoke` a `prod-readonly-smoke-skipped` používaly `secrets.*` v job-level `if`.

**Doplňující riziko:** Finální gate job `needs` oba prod joby; při invalid `if` workflow vůbec neprojde validací.

`gh` na serveru není autentizované — diagnóza z obsahu workflow + známé GHA omezení.

---

## 4. Oprava — secret preflight logika

Oba workflow nyní používají **preflight job**:

```yaml
preflight:
  outputs:
    has_prod_secrets: ${{ steps.check.outputs.has_prod_secrets }}
  steps:
    - env:
        PROD_E2E_EMAIL: ${{ secrets.PROD_E2E_EMAIL }}
        PROD_E2E_PASSWORD: ${{ secrets.PROD_E2E_PASSWORD }}
      run: |
        if [ -n "$PROD_E2E_EMAIL" ] && [ -n "$PROD_E2E_PASSWORD" ]; then
          echo "has_prod_secrets=true" >> "$GITHUB_OUTPUT"
        else
          echo "has_prod_secrets=false" >> "$GITHUB_OUTPUT"
        fi
```

| Job | Podmínka | Výsledek bez secrets |
|-----|----------|----------------------|
| `prod-smoke` / `prod-readonly-smoke` | `has_prod_secrets == 'true'` | skipped |
| `prod-smoke-skipped` / `prod-readonly-smoke-skipped` | `has_prod_secrets != 'true'` | **success** + skip message |

**Definition of Done gate:**

- FAIL — pokud `api-and-local-smoke` selže
- FAIL — pokud production smoke **běžel a selhal**
- PASS — pokud production smoke byl korektně skipped (chybí secrets)

---

## 5. Triggery po opravě

| Workflow | push | pull_request | schedule | workflow_run | workflow_dispatch |
|----------|------|--------------|----------|--------------|-------------------|
| **CI Baseline** | main ✓ | main ✓ | — | — | — |
| Production Smoke Tests | — | — | — | — | ✓ |
| Definition of Done Gate | — | — | — | — | ✓ |
| QA / Full Suite / Auto-Fix / Backend Sanity | — | — | — | — | ✓ |
| Security Checks | — | — | 02:00 UTC | — | ✓ |

`grep push|pull_request|schedule|workflow_run` v `prod-smoke.yml` a `definition-of-done.yml`: **žádný match**.

---

## 6. CI Baseline stav

| Položka | Stav |
|---------|------|
| Remote (GitHub UI) | **PASS** (uživatel potvrdil zelený běh) |
| Guard `.env.example` | opraveno v `745a738` |

---

## 7. Historické failed runy (ignorovat)

Červené běhy u commitů `d2d361a`, `31f9f2b` a starších + failed validace `prod-smoke` / `definition-of-done` **před** `1c5f540` jsou historické. Nelze zpětně opravit v UI.

---

## 8. Commit hash(y)

Workflow fix:

```
1c5f540f2d67ae533bd68cf2a3c504bc046842ee
Make production smoke workflows manual and secret-safe
```

---

## 9. Produkce změněna?

**NE**

---

## 10. Produkce restartována?

**NE**

---

## 11. Závěr

**PRODUCTION SMOKE WORKFLOWS ARE MANUAL AND SECRET SAFE**

- Automaticky po pushi běží jen **CI Baseline**
- `prod-smoke` a `definition-of-done` se **nespouští automaticky**
- Ruční spuštění bez `PROD_E2E_*` secrets → **success (skipped)**, ne fail
- Pro skutečný prod smoke přidejte secrets v GitHub repo settings a spusťte workflow ručně

**URL:** https://github.com/toozservis-tech/sprava-vozidel/actions

---

*Report aktualizováno: 2026-05-24 UTC*
