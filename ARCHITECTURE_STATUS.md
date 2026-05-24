# ARCHITECTURE STATUS

## Aktivní moduly

- Backend entrypoint a bootstrap: `src/server/main.py`, `src/server/bootstrap.py`
- Auth a registrace: `src/server/routers/user_auth.py`
- Účet / profil / export / account actions: `src/server/routers/user_account.py`
- Security + support: `src/server/routers/user_security.py`
- System / health / public / debug: `src/server/routers/system.py`
- Vozidla a servisní historie: `src/modules/vehicle_hub/routers_v1/vehicles.py`, `src/modules/vehicle_hub/routers_v1/service_records.py`
- Připomínky a rezervace: `src/modules/vehicle_hub/routers_v1/reminders.py`, `src/modules/vehicle_hub/routers_v1/reservations.py`
- Service workspace: `src/modules/vehicle_hub/routers_v1/service_workspace.py`
- Licence a billing: `src/modules/licensing/service.py`, `src/modules/vehicle_hub/routers_v1/license_status.py`
- Admin/developer: `src/server/admin_api.py`

## Entry point vs routery

- `src.server.main:app` zůstává oficiální import path pro server i testy.
- `src/server/main.py` je teď tenký entrypoint bez endpoint implementací.
- `src/server/bootstrap.py` skládá aplikaci: middleware, startup/shutdown hooky, router registration, static mounts.
- Sdílené request/response modely a helpery z původního monolitu jsou v `src/server/main_helpers.py` a `src/server/security_helpers.py`.

## Source-of-truth pro ownership

- Primární ownership je `vehicle_ownerships`.
- `vehicles.user_email` je kompatibilní legacy alias pro starší klienty a exporty.

## Source-of-truth pro licence

- Jediná rozhodovací vrstva je `src/modules/licensing/service.py`.
- `src/modules/licensing/licensing_service.py` je deprecated compatibility wrapper.

## Append-only princip servisní historie

- `service_records` se fyzicky nemažou.
- Delete přepíná `is_deleted=1` a zapisuje audit log do `service_record_audit_logs`.
- Update vždy zapisuje `previous_snapshot_json`, `new_snapshot_json` a `snapshot_hash`.

## RBAC přehled

- `user`: vlastní vozidla a jejich historii
- `service`: pouze explicitně sdílená vozidla / linky
- `admin`: admin přístup napříč tenantem
- `developer_admin`: admin + developer control center, ale není implicitně servis

## Deprecated části

- `vehicles.user_email` jako ownership source-of-truth
- `src/modules/licensing/licensing_service.py` jako samostatná licenční implementace
- `/user/ares` jako primární ARES endpoint
- Runtime `create_all` / `ALTER TABLE` patching v request flow
