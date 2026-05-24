# Release freeze rules 2026-05-20

## Baseline

- Production is the current stable reference state.
- Staging is the test branch and validation area.
- New UI changes must happen only on staging or staging-derived branches.
- Production may be changed only after explicit manual approval.

## Before every production deploy

1. `git status` must be clean.
2. A database backup must be created and verified.
3. Staging smoke test must pass.
4. The exact change list must be written down.
5. A rollback plan must be written down.

## Hard rules

- No commits directly in the production working tree without approval.
- No automatic pulling, merging, or copying of staging changes into production.
- No production restart as part of audit-only or freeze-only work.
- No production database overwrite without a verified backup and explicit approval.
- Any production release must identify source branch, target commit, DB backup path, smoke result, and rollback command/path before deployment.
