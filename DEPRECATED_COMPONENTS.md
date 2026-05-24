# DEPRECATED COMPONENTS

- `source-mirror/app_backup`
  - mimo aktivní vývoj

- `src/modules/licensing/licensing_service.py`
  - deprecated compatibility wrapper
  - nová source-of-truth je `src/modules/licensing/service.py`

- `/user/ares`
  - deprecated wrapper
  - oficiální endpoint je `/api/v1/ares/{ico}`

- `vehicles.user_email` jako ownership source-of-truth
  - zachováno jen kvůli kompatibilitě
  - primární vazba je `vehicle_ownerships`

- Runtime schema patching (`create_all`, `ALTER TABLE` v routerech)
  - nahrazeno migracemi a capability checks
