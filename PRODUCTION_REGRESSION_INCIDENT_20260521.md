# Production Regression Incident 2026-05-21

## Status

**Historical incident log. Current release state: stabilized after P0/P1/P2.**

This document is retained as an audit record of the May 21 regression response. It must not be read as the current licensing or trial rule.

## Historical Context

On 2026-05-21 the application had a production/staging regression around VIN/MDCR availability, placeholder assets, and Alembic revision compatibility. A short-lived mitigation attempted to grant Premium trial capability broadly to existing FREE tenants.

That broad backfill approach is now explicitly superseded and is **not** the current business rule.

## Historical Backfill Note

The phrase "backfill 92 tenants" referred to an incident-era mitigation idea/state from the old hotfix timeline. It is recorded here only as historical context.

Current approved rule:

- No broad backfill of existing FREE accounts.
- No automatic Premium grant to all existing FREE tenants.
- Initial Premium trial applies only to a regular user account after email verification.
- Trial starts on the first successful login.
- Trial lasts 30 days from activation.
- Paid Basic/Premium/lifetime licenses take precedence.
- After trial expiry, data is not deleted.
- Without an active paid license, the effective plan returns to Free.

## Final Fix References

- Runtime trial/licensing fix: `639face1b7397114eafd57d0bdd6460f0955145a`
- GDPR/VIN duplicate guard: `16acf50cb3be1ff3d8dc00e03cce4c0d9ce36b81`
- P0 email verification: `bbc7771b6dfdbb76a7973e08881b194b3dbd40bf`
- Fixed E2E test accounts policy: `a8263f4489fef3ee433b8832dc15e43ede0c83cb`
- P2 UX/GDPR polish: `1fd77096559950366996a2144d758f1ce44b6b17`

## Current Corrected State

- Email verification page and verification flow are restored.
- Trial schema/runtime mismatch is fixed.
- Trial activation is limited to first verified login for eligible user accounts.
- License status uses `effective_plan`, including `premium_trial`.
- VIN/MDCR locked states show a user-safe Premium message.
- Raw SQL/backend errors are sanitized before display in the UI.
- Cookie/GDPR consent banner is present without external tracking.
- Fixed E2E account policy prevents random test-account growth.

## Data And Privacy Notes

This document intentionally does not include:

- Passwords, tokens, API keys, bearer/session values, or secrets.
- Customer personal data.
- Real customer VIN/SPZ values.
- Internal credentials or privileged access details.

## Release Checkpoint

After P2, staging is suitable for wider manual testing if browser smoke confirms:

- Fixed user login works.
- Fixed service login works.
- License status endpoints return without 500.
- VIN lock/duplicate handling does not expose SQL or ownership data.
- Support, service history deep links, and cookie consent behave correctly.
