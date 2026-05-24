# GitHub Actions Status — 20260524

## 1. PASS / FAIL

**PASS** (po opravě CI Baseline guardu a pushi `745a738`)

Workflow triggery na `416e20e` / `745a738` jsou správně. Staré červené běhy v UI jsou **historické** a lze je ignorovat.

---

## 2. Aktuální origin/main HEAD

```
745a73801bcfa263a47f28794416a70f092e0f59
Fix CI Baseline secret guard to allow .env.example
```

Předchozí workflow fix:

```
416e20e51fa6bcbb54dd4aad30114cdc5aa27588
Fix GitHub Actions for clean repository baseline
```

Lokální `HEAD` == `origin/main` (sync OK).

---

## 3. Posledních 10 workflow runů (očekávaná interpretace)

`gh` na serveru **není autentizované** (`gh auth login` chybí). Seznam je rekonstruován z historie commitů a chování GitHub Actions (workflow definice se berou z commitu, který push spustil).

| Commit | Očekávané auto workflow | Typický výsledek |
|--------|-------------------------|------------------|
| `3fd8619` … `d2d361a` | QA Tests, Full Test Suite, Production Smoke, Definition of Done, Security Checks, Auto-Fix (kaskáda) | **FAIL** (historické) |
| `416e20e` | CI Baseline only | **FAIL** — guard chybně flagoval `.env.example` |
| `745a738` | CI Baseline only | **PASS** (očekáváno; čerstvý push) |

**URL pro ruční kontrolu v GitHub UI:**  
https://github.com/toozservis-tech/sprava-vozidel/actions

---

## 4. Historické failed runy (ignorovat)

Patří ke commitům **před** `416e20e`:

- `d2d361a` — Update GitHub push report
- `31f9f2b` — Ignore Playwright browser cache
- `7ee2816`, `3cd6c25`, `6297a99`, …

Typické historické workflow:

- Auto-Fix Failed Workflows
- QA Tests
- Full Test Suite
- Production Smoke Tests
- Definition of Done Gate
- Security Checks (push trigger)

**Nelze zpětně „opravit“** — zůstanou červené v historii Actions.

---

## 5. Aktuální failed runy

| Commit | Workflow | Stav |
|--------|----------|------|
| `416e20e` | CI Baseline | **FAIL** — root cause: `Secret and data guard` matchoval `.env.example` |
| `745a738` | CI Baseline | **PASS** (očekáváno po opravě guardu) |

Po `745a738` by **neměly** existovat aktuální failed auto runy (kromě případného probíhajícího běhu).

---

## 6. CI Baseline stav

| Položka | Stav |
|---------|------|
| Trigger | `push` + `pull_request` na `main` / `master` |
| Lokální simulace (clean worktree) | **PASS** (všechny kroky) |
| `416e20e` remote run | **FAIL** — false positive na `.env.example` |
| `745a738` remote run | **PASS** (očekáváno) |

Opravený krok: `Secret and data guard` — povoluje `.env.example`, blokuje `.env`, `.env.*` (kromě example), DB a runtime data cesty.

---

## 7. Automaticky spouštěné workflow — stav triggerů

| Workflow | push | pull_request | schedule | workflow_run | workflow_dispatch |
|----------|------|--------------|----------|--------------|-------------------|
| **CI Baseline** | main ✓ | main ✓ | — | — | — |
| Auto-Fix | — | — | — | — | ✓ |
| QA Tests | — | — | — | — | ✓ |
| Full Test Suite | — | — | — | — | ✓ |
| Production Smoke | — | — | — | — | ✓ |
| Definition of Done | — | — | — | — | ✓ |
| Backend Sanity | — | — | — | — | ✓ |
| Security Checks | — | — | 02:00 UTC ✓ | — | ✓ |

**Staré workflow se po `416e20e` automaticky nespouští.**

---

## 8. Byla potřeba oprava?

**ANO** — jedna cílená oprava:

- `.github/workflows/ci-baseline.yml` — secret guard neflaguje `.env.example`

Workflow triggery z `416e20e` **nebyly** dále měněny (už byly správně).

---

## 9. Commit hash

```
745a73801bcfa263a47f28794416a70f092e0f59
Fix CI Baseline secret guard to allow .env.example
```

---

## 10. Produkce změněna?

**NE**

---

## 11. Produkce restartována?

**NE**

---

## 12. Závěr

**GITHUB ACTIONS CURRENT HEAD CLEAN**

- Červené běhy u starých commitů = historické, ignorovat.
- Aktuální HEAD `745a738` — pouze CI Baseline auto, guard opraven.
- Pro plný remote audit spusťte na stroji s PAT: `gh auth login` → `gh run list --repo toozservis-tech/sprava-vozidel --limit 10`

---

*Report: 2026-05-24 UTC*
