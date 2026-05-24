# Profile Dropdown Panel Audit — 2026-05-24

**Repo:** `toozservis-tech/sprava-vozidel`  
**Branch:** `audit/profile-dropdown-panel-20260524`  
**Base:** `main` @ `e785541` (post PR #3)  
**Worktree:** `/opt/sprava-vozidel-dev`  
**Status:** **PASS**

---

## 1. Actionable Solution

### Co bylo upraveno

- **Vizuální sjednocení** profilového panelu `#mobileProfileMenu` s dashboardem `user-app-next` — bílé pozadí, radius ~23 px, jemný border `#E2E8F0`, soft shadow, pill badge pro licenci, řádky s ikonou v soft čtverci, danger styl pro odhlášení.
- **Desktop popover** — panel se pozicuje pod `[data-testid="dashboard-profile"]` (šířka 320–360 px), bez těžkého overlaye; lehký transparentní backdrop, klik mimo přes document listener.
- **Mobile bottom sheet** — pod 901 px panel jako kompaktní sheet dole s jemným scrimem.
- **Interakce** — Escape, klik mimo, re-klik na profil (topbar z-index 12100 > panel 12090), zavření při `switchTab`, zavření notifikací při otevření profilu.
- **data-testid** — doplněno 9 stabilních identifikátorů pro panel a položky.
- **Testy** — pytest parity + nový Playwright spec `dashboard-profile-panel.spec.ts` (8 testů + auth setup).
- **Oprava wiring** — doplněn `<script src="/web/tutorial-hub.js">` (chyběl v `index.html`; bez něj nefungoval existující onclick `openHowToHubModal()` u „Jak na to“).

### Co bylo opraveno

| Problém | Oprava |
|---------|--------|
| `anchor.getBoundingClientRect is not a function` při otevření z delegovaného click handleru | `resolveMobileProfileMenuAnchor()` — anchor z `event.target.closest(...)`, ne `document` |
| Panel blokoval re-klik na profil | z-index panelu 12090, topbar 12100; backdrop `pointer-events: none` na desktopu |
| Těžký šedý overlay | transparentní backdrop na desktopu, document click pro zavření |
| „Jak na to“ neotevíralo modal | načtení `tutorial-hub.js` |
| Chybějící Escape / outside click | `bindMobileProfileMenuInteractionsOnce()` |
| Licence jako plain text | pill badge + třídy podle stavu (`--trial`, `--premium`, `--free`, `--warn`) |

### Co zůstává otevřené

| Položka | Poznámka |
|---------|----------|
| **Nastavení účtu v user-app-next** | onclick stále volá `switchTab('account')` (legacy). Pod `user-app-next-active` je `#accountTab` skrytý CSS — plná navigace do nastavení funguje přes sidebar `runAction('settings')`. Záměrně neměněno (požadavek: neměnit funkce). |
| **Legacy route-app-view mimo dashboard** | starší styly v `index.html` zůstávají pro non-user-app-next kontext; override jen v `user-app-next.css`. |

### PASS/FAIL

**PASS** — UI sjednoceno, interakce ověřeny, testy 9/9 E2E + pytest OK.

---

## 2. Technical Architecture

### Soubory

| Soubor | Role |
|--------|------|
| `web/index.html` | HTML panelu, JS funkce panelu, script tag tutorial-hub |
| `web/user-app-next.css` | Dashboard-specific override stylů panelu |
| `web/user-app-next.js` | `openProfileMenu(event)` — předává event do toggle |
| `web/tutorial-hub.js` | existující help modal (nyní načten) |
| `tests/e2e/dashboard-profile-panel.spec.ts` | E2E spec |
| `tests/api/test_user_app_p1_parity.py` | statický test testid + akcí |

### Typ komponenty

**Legacy bridge panel** — `#mobileProfileMenu` v `index.html`, sdílený mezi legacy navbar a novým dashboardem. Dashboard ho otevírá přes `UserAppNext.runAction('profile')` → `toggleMobileProfileMenu()`.

### Funkce (JS v `index.html`)

| Funkce | Účel |
|--------|------|
| `toggleMobileProfileMenu(ev)` | otevře/zavře panel |
| `closeMobileProfileMenu()` | zavře panel |
| `setMobileProfileMenuOpen(isOpen)` | stav + aria + třída `is-open` |
| `syncMobileProfileMenu()` | e-mail, ID, licence z session |
| `applyMobileProfileLicenseBadgeClass(el)` | pill barvy podle plánu |
| `getMobileProfileMenuAnchor()` | `.uapp-next-profile` nebo legacy tlačítka |
| `resolveMobileProfileMenuAnchor(ev)` | správný anchor z click eventu |
| `positionMobileProfileMenu(anchorEl)` | popover / bottom sheet pozice |
| `bindMobileProfileMenuInteractionsOnce()` | outside click + Escape + resize |

### CSS třídy

| Třída | Popis |
|-------|-------|
| `.mobile-profile-menu` | kontejner (fixed overlay) |
| `.mobile-profile-sheet` | bílý panel |
| `.mobile-profile-head` | header účtu |
| `.mobile-profile-license-row` | řádek licence |
| `.mobile-profile-license-badge` | pill badge |
| `.mobile-profile-license-badge--trial/premium/free/warn` | stavy licence |
| `.mobile-profile-action` | položka menu |
| `.mobile-profile-action-icon` | ikona v soft čtverci |
| `.mobile-profile-action--danger` | odhlášení |
| `body.user-app-next-active #mobileProfileMenu.is-open` | animace otevření |

### data-testid

| testid | Element |
|--------|---------|
| `dashboard-profile-menu` | `#mobileProfileMenu` |
| `dashboard-profile-menu-close-area` | backdrop tlačítko |
| `dashboard-profile-menu-account` | header účtu |
| `dashboard-profile-menu-license` | řádek licence |
| `dashboard-profile-menu-help` | Jak na to |
| `dashboard-profile-menu-settings` | Nastavení účtu |
| `dashboard-profile-menu-license-plan` | Licence a plán |
| `dashboard-profile-menu-theme` | Světlý/tmavý motiv |
| `dashboard-profile-menu-logout` | Odhlásit se |

Trigger: `dashboard-profile` (v `user-app-next.js` topbar).

### Tabulka kliků

| Položka | Akce | Handler | E2E |
|---------|------|---------|-----|
| Profil (topbar) | toggle panel | `toggleMobileProfileMenu(ev)` | PASS |
| Re-klik profil | zavře | toggle | PASS |
| Klik mimo | zavře | document listener | PASS |
| Escape | zavře | keydown listener | PASS |
| Jak na to | help modal | `openHowToHubModal()` | PASS |
| Nastavení účtu | account tab | `switchTab('account')` | PASS (onclick + close) |
| Licence a plán | license modal | `openLicenseModal()` | PASS |
| Světlý/tmavý motiv | theme toggle | `toggleAppUiTheme()` | PASS |
| Odhlásit se | logout | `handleLogout()` | PASS (existence only) |
| Route change | zavře panel | `switchTab()` start | implicit |

### GDPR — account vs vehicle data

| V panelu | Zdroj | OK |
|----------|-------|-----|
| E-mail | `currentUser.email` / session | ✅ vlastní účet |
| User ID | `account_id` / `id` ze session | ✅ vlastní účet |
| Licence/plán | `#licenseQuickLabel` ze session | ✅ ověřený stav |
| VIN, SPZ, vozidla, servisní historie | — | ✅ **nejsou** v panelu |

---

## 3. Business Impact

- **Rychlejší orientace** — účet, licence a nastavení na jednom místě v jednotném vizuálním jazyku dashboardu.
- **Vyšší důvěra** — panel už nepůsobí jako cizí legacy vrstva.
- **Méně vizuálního bordelu** — bez těžkého modal overlaye na desktopu, konzistentní radius a stíny.
- **Jasný přístup** k licenci, nápovědě, nastavení a odhlášení — ověřeno testy.

---

## Test Results

| Test | Výsledek |
|------|----------|
| `pytest test_profile_dropdown_panel_testids_and_actions` | PASS |
| `pytest test_index_html_loads_tutorial_hub` | PASS |
| Playwright `dashboard-profile-panel.spec.ts` (8 tests) | **9/9 PASS** (incl. setup-auth) |

**Produkce:** nedotčena (`/opt/toozhub2/app` beze změn)  
**DB / .env / runtime data:** beze změn

---

## Navrhovaný commit message

```
Restyle profile dropdown panel for user-app-next dashboard parity

Align #mobileProfileMenu with dashboard visual language (popover on desktop,
bottom sheet on mobile), add positioning/outside-click/Escape handling,
dashboard-profile-menu testids, E2E coverage, and restore tutorial-hub.js load
for Jak na to.
```
