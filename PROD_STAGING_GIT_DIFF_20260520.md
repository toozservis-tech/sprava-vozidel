# Production vs staging git diff 2026-05-20

Generated from `/opt/toozhub2-staging/app` on 2026-05-21 UTC.

## Heads

- PROD_HEAD: `74d3c0c0bda7fe41dde6841631d20c3d4b97643e`
- STAGING_HEAD: `f6f28e21061e68b6826afe210c0eaefe8aeebeb7`

## Diff command

```bash
git diff --name-status 74d3c0c0bda7fe41dde6841631d20c3d4b97643e..f6f28e21061e68b6826afe210c0eaefe8aeebeb7
```

## Differences

```text
M	.env.example
A	SERVICE_OFFICE_IMPLEMENTATION_REPORT.md
A	SERVICE_OFFICE_TEST_REPORT.md
A	STAGING_SERVICE_OFFICE_AUDIT.md
A	alembic/versions/20260516_0041_staging_revision_compat.py
A	alembic/versions/20260519_0041_service_work_order_items.py
A	alembic/versions/20260520_0042_service_work_order_csv_imports.py
A	alembic/versions/20260520_0043_service_map_locations.py
A	docs/SERVICE_MAP_IMPORT.md
A	docs/STAGING_ONLY_UI_WORKFLOW_20260518.md
A	docs/USER_APP_VISUAL_REFERENCE_MAP_20260518.md
A	scripts/import_service_map_osm_cz.py
A	scripts/seed_service_map_staging.py
M	src/core/config.py
M	src/core/security_middleware.py
M	src/modules/vehicle_hub/models.py
M	src/modules/vehicle_hub/routers_v1/__init__.py
M	src/modules/vehicle_hub/routers_v1/capabilities.py
M	src/modules/vehicle_hub/routers_v1/service_invoices.py
A	src/modules/vehicle_hub/routers_v1/service_map.py
A	src/modules/vehicle_hub/routers_v1/service_workspace_work_orders.py
M	src/modules/vehicle_hub/routers_v1/services.py
A	src/modules/vehicle_hub/routers_v1/user_invoices.py
M	src/modules/vehicle_hub/routers_v1/vehicles.py
M	src/modules/vehicle_hub/schema_management.py
A	src/modules/vehicle_hub/service_map/__init__.py
A	src/modules/vehicle_hub/service_map/claim_service.py
A	src/modules/vehicle_hub/service_map/constants.py
A	src/modules/vehicle_hub/service_map/map_config.py
A	src/modules/vehicle_hub/service_map/mdcr_stk_sme_importer.py
A	src/modules/vehicle_hub/service_map/normalize.py
A	src/modules/vehicle_hub/service_map/osm_importer.py
A	src/modules/vehicle_hub/service_map/regions_cz.py
A	src/modules/vehicle_hub/service_map/search_service.py
A	src/server/admin_service_map.py
M	src/server/bootstrap.py
A	tests/api/test_service_map.py
A	tests/api/test_service_work_order_items.py
M	tests/e2e/service-shell-fallback.helpers.ts
M	tests/e2e/service-shell-work-order-flow.spec.ts
A	web/assets/landing/sprava-vozidel-logo.jpeg
M	web/index.html
M	web/public-auth.css
A	web/service-shell-invoices-dashboard.css
A	web/service-shell-invoices-dashboard.js
M	web/service-shell.css
M	web/service-shell.js
A	web/user-app-next.css
A	web/user-app-next.js
A	web/user-invoice-settings.js
A	web/user-invoices-dashboard.js
A	web/user-invoices-shell-adapter.js
A	web/user-invoices-workflow.js
```

## Classification

- Differences are not limited to `web/`, UI, docs, and assets.
- Backend `src/*` files are present in the diff.
- Alembic migration files are present in the diff.
- `web/service-shell.js` is present in the diff.
- Database files are not present in the git diff.

## Forbidden diff result

Forbidden diff check returned `FAIL forbidden diff`.

Matched files include:

```text
alembic/versions/20260516_0041_staging_revision_compat.py
alembic/versions/20260519_0041_service_work_order_items.py
alembic/versions/20260520_0042_service_work_order_csv_imports.py
alembic/versions/20260520_0043_service_map_locations.py
src/core/config.py
src/core/security_middleware.py
src/modules/vehicle_hub/models.py
src/modules/vehicle_hub/routers_v1/__init__.py
src/modules/vehicle_hub/routers_v1/capabilities.py
src/modules/vehicle_hub/routers_v1/service_invoices.py
src/modules/vehicle_hub/routers_v1/service_map.py
src/modules/vehicle_hub/routers_v1/service_workspace_work_orders.py
src/modules/vehicle_hub/routers_v1/services.py
src/modules/vehicle_hub/routers_v1/user_invoices.py
src/modules/vehicle_hub/routers_v1/vehicles.py
src/modules/vehicle_hub/schema_management.py
src/modules/vehicle_hub/service_map/__init__.py
src/modules/vehicle_hub/service_map/claim_service.py
src/modules/vehicle_hub/service_map/constants.py
src/modules/vehicle_hub/service_map/map_config.py
src/modules/vehicle_hub/service_map/mdcr_stk_sme_importer.py
src/modules/vehicle_hub/service_map/normalize.py
src/modules/vehicle_hub/service_map/osm_importer.py
src/modules/vehicle_hub/service_map/regions_cz.py
src/modules/vehicle_hub/service_map/search_service.py
src/server/admin_service_map.py
src/server/bootstrap.py
web/service-shell.js
```

## Verdict

UNSAFE DIFF

Reason: staging differs from production in backend `src/*`, `alembic/*`, and `web/service-shell.js`, not only in isolated UI/docs/assets files.
