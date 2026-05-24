# SANITATION SUMMARY

## Co bylo špatně

- Backend spoléhal na runtime `create_all` a ad-hoc `ALTER TABLE` hacky.
- Servisní historie šla fyzicky mazat.
- Ownership vozidla byl odvozovaný hlavně přes `vehicles.user_email`.
- Licencování mělo dvě paralelní implementace.
- Frontend/admin neuměl jasně rozlišit připravený vs nepřipravený modul.

## Co bylo opraveno

- Zavedena Alembic baseline migrace a migrační runner `scripts/migrate_database.py`.
- Přidána deterministická schema/capability vrstva místo runtime patchování.
- Servisní záznamy převedeny na soft-delete + audit snapshot + hash.
- Přidána explicitní tabulka `vehicle_ownerships` a backfill z legacy `user_email`.
- Stará licenční vrstva je jen kompatibilní wrapper nad novou tenantovou službou.
- Legacy `/user/ares` je wrapper na `/api/v1/ares/{ico}`.

## Co bylo jen stabilizováno

- `vehicles.user_email` zůstává kvůli kompatibilitě web/iOS/admin, ale není nově zdrojem pravdy.
- `main.py` už není endpoint monolit; zůstal jako tenký entrypoint a app wiring je přesunutý do `src/server/bootstrap.py` a `src/server/routers/*`.

## Co bylo dočasně disabled

- UI moduly navázané na nepřipravené DB schema se teď označují jako dočasně nedostupné po migraci.
- Push/system notifications/subscriptions/service workspace vrací explicitní `503`, pokud schema není po migraci připravené.

## Co zůstává jako další krok

- Převést admin API na ownership source-of-truth místo přímé závislosti na `vehicles.user_email`.
- Dopsat další contract/e2e testy na capability gating ve web/admin UI.
