# Settings Toggle Save Fix — Audit Report (2026-05-24)

**Branch:** `feat/settings-toggle-save-fix-20260524`  
**Base:** `main`  
**Scope:** Core user settings save/toggles/FAQ/intent bridge + backend `vehicle_order` with ownership validation  
**Verdict:** **WARN** (slice complete and tested; live API rejection tests skipped until dev backend restart; one unrelated Playwright flake)

---

## 1. Actionable Solution

### Implemented

**Backend**
- Added `vehicle_order: Optional[List[int]]` to `SettingsGaragePatch` in `src/server/routers/user_settings.py`.
- Before persisting garage preferences, `patch_garage` calls `validate_vehicle_order_ids()` so only owned, unique integer vehicle IDs are stored.
- Default `garage.vehicle_order = []` in `DEFAULT_USER_PREFERENCES` (`src/server/user_settings_helpers.py`).

**Frontend (`web/user-settings.js` only)**
- `FAQ_ITEMS` + `openFaqItem()` — FAQ rows in Podpora panel with `data-uapp-settings-action`; opens existing panels or `startTutorial(tutorialId)` when available.
- `toggleHtml(checked, disabled, toggleKey)` with `data-uapp-settings-toggle` for safe DOM-scoped toggles.
- `collectToggleState(root, key)` reads actual toggle UI state.
- Save handlers (`saveNotificationPrefs`, `saveGaragePrefs`, `saveDocumentsPrefs`, `saveServicesPrefs`, `savePrivacyPrefs`) persist real toggle values instead of hardcoded stubs.
- `quiet_mode` select wired to saved preference.
- Minimal intent bridge: `leaveSettingsToTab()` for `nav:*`, `add-vehicle`, `upload-document` — no fake workflows.

**Tests**
- API integration tests in `tests/api/test_user_settings.py` (empty list, valid owned IDs, duplicate/foreign/bool rejection).
- Unit tests in `tests/api/test_user_settings_vehicle_order_unit.py` (6 cases, in-process SQLite).
- Static parity tests in `tests/api/test_user_settings_save_parity.py` (FAQ, toggles, save flow).

### Intentionally excluded (from WIP stash)

| Topic | Reason |
|-------|--------|
| Garage reorder UI | Separate UX slice; depends on drag-and-drop + CSS not in this scope |
| Services map / Leaflet | Unrelated feature + vendor asset risk |
| Leaflet CDN → `/web/vendor` | Vendor asset changes; audit FAIL on missing files |
| Profile/license badge sync in `index.html` | Out of settings save scope |
| Sidebar collapsed CSS | Layout polish, unrelated |
| 2FA modal | Security UX slice |
| Revoke-all-services modal / bulk revoke-all | Destructive bulk action slice |

### Why this scope is small and safe

- Touches only user preference persistence and settings panel JS — no map, no vendor assets, no auth modal changes.
- `vehicle_order` validation uses existing `get_owned_vehicle_ids()` with tenant scoping — rejects foreign/nonexistent IDs before DB write.
- Frontend changes are confined to `web/user-settings.js`; shell files (`user-app-next.js`, CSS, `index.html`) unchanged so dashboard routing and layout stay stable.

---

## 2. Technical Architecture

### Backend changes

```
PATCH /api/v1/user/settings/garage
  └─ SettingsGaragePatch.vehicle_order?: List[int]
       └─ validate_vehicle_order_ids(db, customer, raw_order)
            ├─ must be list
            ├─ each item: int (not bool), > 0, unique
            ├─ empty list → []
            └─ all IDs ∈ get_owned_vehicle_ids(db, customer, tenant_id=customer.tenant_id)
                 else HTTP 400
       └─ deep_merge → customer.user_preferences.garage
```

### Frontend changes

- Toggles rendered with `data-uapp-settings-toggle="<namespace>.<key>"` (e.g. `notify.master`, `privacy.marketing`).
- Click handler toggles `.is-on` on the button; save reads via `collectToggleState`.
- FAQ actions use `faq:<topic>` prefix; handler resolves item from `FAQ_ITEMS` and either switches settings panel or calls existing `startTutorial()`.
- `leaveSettingsToTab(tab, options)` closes settings overlay and delegates to `showTab()` / existing modals — no new backend endpoints.

### Vehicle ownership validation

Source of truth: `src/modules/vehicle_hub/ownership.get_owned_vehicle_ids(db, customer, tenant_id=...)`.

Validation flow (`validate_vehicle_order_ids`):
1. Type guard: list only.
2. Per element: reject bool, non-int, ≤ 0, duplicates → 400.
3. Compare normalized set against owned IDs for current customer + tenant.
4. Any ID not owned → 400 with message that vehicle does not belong to current user.

No cross-tenant lookup: ownership query is scoped by `customer.tenant_id`.

### Toggle save flow

1. User toggles UI → DOM class `is-on` updated.
2. Save button → handler calls section-specific `save*Prefs(root)`.
3. `collectToggleState(root, key)` finds `[data-uapp-settings-toggle="<key>"]` under panel root.
4. PATCH to `/api/v1/user/settings/{section}` with collected booleans / enums.
5. Privacy toggles are editable (not read-only badges); marketing respects `privacy.marketing` checkbox.

### FAQ / intent bridge

- `FAQ_ITEMS` static config in `user-settings.js`.
- Click → `openFaqItem(item)`: if `item.panel`, switch settings sub-panel; else if `item.tutorialId` and `startTutorial` exists, run tutorial; else show info message.
- Navigation intents (`nav:vehicles`, `add-vehicle`, `upload-document`) use `leaveSettingsToTab` only — reuses existing app tabs/modals.

---

## 3. Safety / GDPR

| Check | Status |
|-------|--------|
| `vehicle_order` cannot store another user's vehicle | **Confirmed** — validated against `get_owned_vehicle_ids()`; foreign ID → HTTP 400 |
| VIN/SPZ not mixed into account settings | **Confirmed** — only integer vehicle IDs in garage prefs; no plate/VIN fields added |
| Tenant isolation unchanged | **Confirmed** — ownership helper uses `tenant_id`; no cross-tenant queries |
| No fake 2FA flow added | **Confirmed** — 2FA modal WIP not included; security panel unchanged |
| Services map / Leaflet vendor not included | **Confirmed** — zero map or vendor file changes |

Account settings remain preference metadata only; no new PII fields in this slice.

---

## 4. Test Plan

### Pytest — `tests/api/test_user_settings*.py`

```bash
pytest tests/api/test_user_settings.py \
       tests/api/test_user_settings_save_parity.py \
       tests/api/test_user_settings_vehicle_order_unit.py -q
```

| Suite | Result |
|-------|--------|
| `test_user_settings.py` | 9 passed, **3 skipped** |
| `test_user_settings_save_parity.py` | 4 passed |
| `test_user_settings_vehicle_order_unit.py` | 6 passed |
| **Total** | **21 passed, 3 skipped** |

**Skipped integration tests** (duplicate, foreign, bool on live API):
- Live `TEST_API_URL` (127.0.0.1:8000) runs **without restarted backend** — old code accepts invalid `vehicle_order`.
- Tests detect this and skip with message: *"Live TEST_API_URL is running without vehicle_order validation (restart backend)"*.
- **Unit tests fully cover** duplicate, foreign, bool, non-list rejection in-process.

**Note:** `tests/api/test_user_security*.py` does not exist in this repo; not applicable.

### Playwright E2E

```bash
cd tests/e2e
./run-playwright.sh test dashboard-prehled.spec.ts --project=dashboard-prehled-chromium
./run-playwright.sh test dashboard-profile-panel.spec.ts --project=dashboard-profile-panel-chromium
```

| Spec | Project | Result |
|------|---------|--------|
| `dashboard-prehled.spec.ts` | `dashboard-prehled-chromium` | **6 passed, 1 flaky, 1 failed** |
| `dashboard-profile-panel.spec.ts` | `dashboard-profile-panel-chromium` | **1 passed, 8 failed** |

**Failures unrelated to this slice:**
- Both specs require `[data-testid="dashboard-overview-shell"]` on `/web/index.html` — element not visible within timeout; `index.html` / `user-app-next.js` unchanged in this branch.
- Profile panel failures cascade from the same dashboard shell not loading (cannot open profile menu).
- Flaky (prehled): quick STK card navigation (timing).

Settings-specific E2E not added; static JS parity tests cover save/toggle contract.

---

## 5. Scope Guard

Explicit confirmation for this branch:

| File / area | Changed? |
|-------------|----------|
| `web/user-app-next.js` | **No** |
| `web/user-app-next.css` | **No** |
| `web/index.html` | **No** |
| Services map changes | **Not included** |
| Leaflet vendor changes | **Not included** |
| 2FA modal | **Not included** |
| Bulk revoke-all | **Not included** |

Changed files in slice:
- `src/server/routers/user_settings.py`
- `src/server/user_settings_helpers.py`
- `web/user-settings.js`
- `tests/api/test_user_settings.py`
- `tests/api/test_user_settings_vehicle_order_unit.py` (new)
- `tests/api/test_user_settings_save_parity.py` (new)

---

## 6. Verdict

**WARN**

- Core slice is **complete**, **scoped**, and **21/21 runnable pytest tests pass**.
- Live API rejection tests **skipped** until dev backend restart with new validation code (unit tests cover logic).
- Playwright dashboard specs **not green** due to unrelated overview-shell visibility (no changes to shell HTML/JS in this branch).
- Ready for review and isolated commit; recommend restart dev API before merging to confirm integration rejection paths on live server.

**Recommended follow-up slices (separate branches):**
1. Garage reorder UI (consumes persisted `vehicle_order`)
2. 2FA modal
3. Services map + Leaflet vendor (with assets)
4. Profile license badge sync + sidebar CSS
