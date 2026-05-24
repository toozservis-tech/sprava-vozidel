# GDPR VIN Duplicate Guard Audit 2026-05-21

## Status

**Resolved by commit `16acf50cb3be1ff3d8dc00e03cce4c0d9ce36b81`.**

## Scope

Reviewed VIN-related add/decode/preview/create paths:

- `src/modules/vehicle_hub/vin_ownership_guard.py`
- `src/modules/vehicle_hub/decoder/router.py`
- `src/modules/vehicle_hub/routers_v1/vin_lookup.py`
- `src/modules/vehicle_hub/routers_v1/vehicles.py`
- `tests/api/test_vin_duplicate_guard.py`

## Risk

Before the guard, VIN enrichment could run before a tenant-aware ownership check. That created a GDPR risk because external vehicle data enrichment could return identifying vehicle information before the application knew whether the current user was allowed to see that vehicle.

## Corrected Behavior

All relevant authenticated VIN flows now run a server-side ownership guard before MDCR/external decode, catalog preview, technical preload, or vehicle creation.

If the VIN is already held by another tenant, the response is HTTP 409 with a safe payload:

```json
{
  "code": "VIN_ALREADY_REGISTERED_OTHER_USER",
  "message": "Vozidlo s tímto VIN je již evidováno v aplikaci pod jiným uživatelem.",
  "can_continue": false
}
```

The response intentionally contains no:

- `vehicle_id`
- `tenant_id`
- owner/customer data
- service account data
- SPZ/RZ
- brand/model
- technical data
- MDCR payload
- service history

## Privacy Review

This audit document does not contain concrete customer VIN values, SPZ/RZ values, owner data, service data, tokens, passwords, API keys, or session identifiers.

## Test Coverage

Covered by `tests/api/test_vin_duplicate_guard.py`:

- Other-tenant VIN returns 409.
- MDCR/decode is not called after guard block.
- Response avoids ownership and vehicle details.
- Own-tenant VIN remains allowed.
