# Production Baseline: Vehicle Lifecycle Stable

Baseline date: 2026-04-21

Commit SHA at lock preparation: `39d3e37399f20016b82482df6e6c304ac6095179`

Release tag: `prod-vehicle-lifecycle-stable-2026-04-21`

Release branch: `release/prod-locked-vehicle-lifecycle`

## Key Modules

- Vehicle lifecycle: `src/modules/vehicle_hub/routers_v1/vehicle_lifecycle.py`
- Vehicle canonical API and delete guard: `src/modules/vehicle_hub/routers_v1/vehicles.py`
- Service access enforcement: `src/modules/vehicle_hub/service_access.py`
- Service canonical intake/workflow: `src/modules/vehicle_hub/routers_v1/service_canonical.py`
- Service workspace: `src/modules/vehicle_hub/routers_v1/service_workspace.py`
- Transfer token public API: `src/server/routers/public_vehicle_transfer.py`
- Archive storage: `data/vehicle_archives`
- Digital reports/PDF: `src/modules/vehicle_hub/reports/vehicle_report_pdf.py`
- Report verification: `src/modules/vehicle_hub/reports/vehicle_report_verification.py`
- Session/workspace source of truth: `src/server/routers/session_me.py`
- Audit log: `src/modules/vehicle_hub/audit_log.py`

## Critical Endpoints

- `GET /api/me`
- `GET /api/v1/services/catalog`
- `GET /api/v1/vehicles/{vehicle_id}/service-access`
- `POST /api/v1/vehicles/{vehicle_id}/service-access/request-or-link`
- `POST /api/v1/vehicles/{vehicle_id}/service-access/{access_id}/approve`
- `POST /api/v1/vehicles/{vehicle_id}/service-access/{access_id}/reject`
- `POST /api/v1/vehicles/{vehicle_id}/service-access/{access_id}/revoke`
- `POST /api/v1/vehicles/{vehicle_id}/remove/init`
- `POST /api/v1/vehicles/{vehicle_id}/remove/confirm`
- `POST /api/v1/vehicles/{vehicle_id}/transfer-token`
- `POST /api/v1/vehicles/claim-by-transfer`
- `POST /api/v1/vehicles/lookup-by-spz`
- `POST /api/v1/vehicles/attach-existing`
- `GET /api/v1/vehicles/{vehicle_id}/digital-report`
- `GET /api/public/vehicle-transfer/{token}`
- `POST /api/public/vehicle-transfer/{token}/claim`
- `POST /api/service/vehicle-intake/from-spz-photo`
- `POST /api/service/vehicle-intake/{case_id}/owner-access-request`
- `POST /api/service/vehicle-intake/{case_id}/upload-photos`
- `POST /api/service/vehicle-intake/{case_id}/start-work`
- `POST /api/service/vehicle-intake/{case_id}/stop-work`
- `POST /api/service/vehicle-intake/{case_id}/create-service-record`
- `GET /api/service/vehicles/assigned`
- `GET /api/service/vehicles/search`
- `GET /api/service/vehicle-intake/{case_id}`
- `GET /api/service/vehicle-intake`

## Critical Rules

- Service without approved access must receive `403` for final service-record creation.
- Vehicle removal is lifecycle archival, not hard delete: direct vehicle `DELETE` must not bypass `remove/init` and `remove/confirm`.
- Transfer tokens are stored as hashes only; raw transfer tokens are returned only at issue time.
- `/api/me` is the source of truth for account type, workspace route, slug and default app path.
- Frontend shell must render from backend truth, not legacy role flags.
- `remove/confirm` must generate a digital report and archive bundle.
- Claim through transfer token must preserve VIN-bound service history.
- Critical lifecycle, service access, report generation, route denial and claim actions must write audit logs.
- Required production storage directories must exist at startup:
  - `data/vehicle_archives`
  - `data/vehicle_reports`
  - `data/uploads/vehicles`

## Anti-Regression Tests

Production guard tests live in `tests/production_guard/` and must fail on contract drift in:

- direct vehicle delete bypass
- service record without approved access
- `/api/me` workspace contract
- lifecycle response structure
- transfer token hash-only behavior
- audit event coverage
- production storage and soft lock registration
