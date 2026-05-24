# App-wide functional map - 2026-05-18

Branch: `feature/app-wide-design-system-map-20260518`
Baseline SHA: `f8218f5d1df66b3f575338ddc254b6ca684e3e20`

This document is an inventory of the current production functionality that must survive the next visual redesign. The redesign may change layout and styling, but it must not replace these handlers, APIs, auth/session rules, role routing, or data flows with mock behavior.

Status values:
- `READY`: existing DOM/handler/API is clear enough to restyle or bridge directly.
- `NEEDS_ADAPTER`: existing behavior is clear, but a new visual component will need a thin adapter/proxy.
- `BLOCKER`: no reliable current frontend entry point was found in the audited files; do not fake it.

Audited files:
- `web/index.html`
- `web/service-shell.js` read-only
- related `web/*.html`, `web/*.js`, `web/*.css` read-only search
- backend paths were only searched to confirm admin/public route existence; no backend changes were made.

## Public

| Item | Current DOM / entry point | Handler / API | State / data | Must not lose | Status |
|---|---|---|---|---|---|
| Public landing before login | `#authSection.auth-shell.auth-shell-root`, public markup around `#publicHeroTitle`, `#publicValueTitle`, `#publicAudienceTitle`, `#publicContactTitle`, `#publicFinalCtaTitle` in `web/index.html` | public buttons call `showLogin()`, `showRegister()`, sometimes `setRegistrationMode(...)` | unauthenticated visibility is controlled by app/auth shell state | landing must stay hidden after authenticated app routing | READY |
| Public marketing sections | Public sections in `web/index.html`: hero, value/benefits, owner/service sections, landing vehicles/records/access | anchor/navigation and existing public drawer/menu handlers | static marketing content | no new auth flow, no iframe mock app | READY |
| CTA to login | Buttons near public header/drawer/hero call `showLogin()` | `showLogin(options={})` | switches auth view to login | must keep existing login form and redirect logic | READY |
| CTA to register | Buttons call `showRegister()` and sometimes `setRegistrationMode('user'/'service')` | `showRegister()`, `setRegistrationMode(mode)` | switches auth view to register user/service | must keep account type semantics | READY |
| Pricing / licence public references | Public page has marketing CTA; licence logic is in user app `openLicenseModal()` and `/api/v1/license/*` | public pricing route not found as separate page | public pricing can link/scroll, but production billing is inside auth/user flow | exact public pricing screen requires product decision | NEEDS_ADAPTER |
| Public help/support | Public support/contact section exists in landing; authenticated support tab is `switchTab('support')` | no separate public support app found | public contact text only | do not route unauthenticated user into app shell | NEEDS_ADAPTER |
| Public document verification | `web/verify.html` | `verifyByToken(token)`, `verifyByCode(code)`, APIs `/api/public/documents/verify/{token}`, `/api/public/documents/verify-by-code` | token/code from URL or form | verification result and error states | READY |
| Public vehicle history via QR | `web/public-vehicle-history.html` | `publicVehicleHistoryFetchUrl(token)`, API `/api/public/vehicle-history/{token}` | token route param/query | public report privacy and token handling | READY |
| Public quote | `web/public-quote.html` | API `/api/public/quote/{token}`, action `/api/public/quote/{token}/{action}` | quote token and quote status | approve/reject actions and status messages | READY |
| Vehicle transfer claim | `web/vehicle-transfer.html` | APIs `/api/public/vehicle-transfer/{token}`, `/claim` | token and authenticated claim flow | transfer security semantics | READY |

## Auth

| Item | Current DOM / entry point | Handler / API | State / data | Must not lose | Status |
|---|---|---|---|---|---|
| Auth shell visibility | `#authSection` | `showLogin()`, `showRegister()`, `showDashboard()`, `navigateToStoredAppAfterAuth()` | token/session, route, role | correct public/auth/app visibility | READY |
| Login form | `#loginForm`, `#loginEmail`, `#loginPassword`, `#loginSubmitBtn`, `#loginErrorContainer` | `handleLogin()` | email/password, expected role | original auth error handling and redirect | READY |
| Login user/service switch | `#loginModeUserBtn`, `#loginModeServiceBtn`, `#loginModeHint` | `setLoginMode('user'/'service')` | selected login mode | service role checks after login | READY |
| 2FA login | `#loginTwoFactorPanel`, `#loginTwoFactorCode`, `#loginTwoFactorVerifyBtn` | `handleLoginTwoFactor()` | pending auth session/code | do not bypass 2FA | READY |
| Register user | `#registerForm`, `#registerModeUserBtn`, common register fields | `setRegistrationMode('user')`, `handleRegister()` | account type, personal fields | existing validation and post-register state | READY |
| Register service | `#registerModeServiceBtn`, `#serviceRegistrationExtraFields`, `#registerPendingState` | `setRegistrationMode('service')`, `handleRegister()` | service company/contact fields | pending approval messaging and service workflow | READY |
| Forgot password | `#forgotPasswordForm`, `#forgotPasswordEmail` | `showForgotPasswordForm()`, `handleForgotPassword()` | email | original modal/error/loading states | READY |
| Reset password | `web/reset-password.html`, `#resetForm`, `#resetButton` | `handleResetPassword(event)`, API `/user/reset-password` | reset token/password | token validation and success/fail messaging | READY |
| Email verification | registration pending text plus verification routes | email verification flow is implied in auth/register and public verify pages | token/email state | exact new UI must preserve backend contract | NEEDS_ADAPTER |
| Phone/SMS verification | registration pending hint mentions phone stored in E.164 but full SMS verification is not visibly active | no complete SMS auth screen found | phone field only | do not design fake SMS screen as functional | BLOCKER |
| Pending service approval | `#registerPendingState`, `#registerPendingSubtitle`, `#registerPendingHint` | post-register state in `handleRegister()` | service account state | "wait for admin approval" flow | READY |
| Auth errors/loading | `#loginErrorContainer`, `#registerErrorContainer`, button busy states in handlers | `handleLogin()`, `handleRegister()`, `handleForgotPassword()` | API errors | visible, accessible error states | READY |
| Redirect after login | app path storage and `navigateToStoredAppAfterAuth()` | `/api/me`, `/user/me`, app role routing | token, user role, workspace route | user/service/admin role separation | READY |
| Logout | user `handleLogout()`, service `window.serviceShell.logout()` | clears auth/session state | token/session/timers | must never be replaced by a link-only fake logout | READY |

## User App

| Item | Current DOM / entry point | Handler / API | State / data | Must not lose | Status |
|---|---|---|---|---|---|
| App shell | `#mainNavbar`, `#app-shell`, `#dashboard` | `showDashboard()`, `switchTab(tab, options)` | active tab, profile/session, role | hidden public/auth sections after login | READY |
| User topbar | `#mainNavbar.app-shell-header`, desktop/mobile sections | existing buttons and profile menu | notification state, profile state | original buttons/listeners/ARIA | READY |
| Notifications bell | `#desktopNotificationsButton`, `#mobileNotificationsButton` | `toggleAppNotificationsPanel(event)` | unread counts and notification list | original dropdown, outside-click close, badge | READY |
| Notifications panel | `#appNotificationsPanel`, `#appNotificationsList`, `#appNotificationsArchiveList` | `loadSystemNotifications()`, `renderAppNotificationsPanelList()`, `renderAppNotificationsArchivePanel()` | system notification payload | archive, unread state, links/actions | READY |
| Profile button/menu | `#desktopProfileButton`, `#mobileProfileMenu` | `toggleMobileProfileMenu()` | current user/license/theme state | original menu must open, not route straight to settings | READY |
| Profile menu - Jak na to | row in `#mobileProfileMenu` | `openHowToHubModal()` fallback | help/onboarding modal state | original onboarding/help flow | READY |
| Profile menu - Licence | row in `#mobileProfileMenu`, `#licenseQuickToggle`, `#licenseQuickDropdown` | `openLicenseModal()`, `initLicenseQuickBadge()` | `/api/v1/license/status`, subscription state | plan limits, Comgate/sandbox behavior | READY |
| Profile menu - Nastaveni | row in `#mobileProfileMenu` | `switchTab('account')` | account/profile tab | original account settings section | READY |
| Profile menu - Odhlaseni | `#logout-btn`, profile action | `handleLogout()` | token/session | full logout cleanup | READY |
| Sidebar/tabs/navigation | `#appShellNav`, buttons with `data-tab-key` | `switchTab('home'|'vehicles'|'reminders'|'reservations'|'servicesDirectory'|'serviceWorkspace'|'documents'|'support'|'account')` | active tab, data caches | no toast-only fake navigation | READY |
| Overview dashboard | `#homeTab`, `#homeDashboardGreeting`, `#homeDashboardStats`, `#homeDashboardWorkspace`, `#homeDashboardRecentFeed` | `loadHomeDashboard()` | vehicles, reminders, licence, service records | real counts and real vehicle/service data | READY |
| My vehicles | `#vehiclesTab`, `#vehiclesList`, `#vehiclesContainer` | `loadVehicles(force)`, `setVehicleView(...)` | `/api/v1/vehicles`, current view | real vehicle IDs and card actions | READY |
| Add vehicle | `#btnOpenAddVehicleModal`, `#addVehicleModal`, vehicle form fields, ORV wizard | `openAddVehicleModal()`, vehicle create/update functions | `/api/v1/vehicles`, VIN preview, ORV scan, photos | existing validations and upload flow | READY |
| Vehicle detail | `#vehicleDetailModal`, `#vehicleModalBody`, `#vehicleModalTitle` | `showVehicleDetail(vehicleId)`, `openVehicleDetailFloatingSection(section, vehicleId)` | `/api/v1/vehicles/{id}`, records, docs, access | real `vehicle_id` and modal state | READY |
| Photos/gallery | photo inputs and gallery functions in `web/index.html` | `/api/v1/vehicles/{id}/photos`, `/photo`, `/photo/promote`, `/catalog-images/.../file` | vehicle photo IDs/storage | no demo/cross-car images | READY |
| Service history | vehicle record sections and modals | `/api/v1/vehicles/{id}/records`, record detail/update/delete/export APIs | records/attachments | real records, attachments, PDF export | READY |
| Add service record | `#addServiceRecordModal`, `#addServiceRecordModalBody` | `openAddServiceRecordModal(vehicleId)`, submit to `/api/v1/vehicles/{id}/records` | selected vehicle/record data | existing record form and upload attachments | READY |
| Documents hub | `#documentsTab` and central hub rendering | `loadDocumentsHub(force)`, `/api/v1/vehicles/documents/hub` | vehicle documents | central docs and vehicle-specific docs | READY |
| Upload document | record/document modal uploads and prefill | `/api/v1/vehicles/{id}/records/attachments/upload`, document prefill endpoints | selected vehicle/record | upload progress and authenticated downloads | READY |
| Reminders | reminders tab and modal controls | `loadReminders(force)`, `/api/v1/reminders`, `/settings`, check notifications | reminders, settings, vehicles | complete/delay/detail flows | READY |
| Invoices | User invoice surface appears tied to documents/service records/licence; no standalone user invoice tab found | service invoices exist in service shell | invoice data if linked to docs/records | do not invent a standalone invoice app without confirmed handler | NEEDS_ADAPTER |
| Services and access | `servicesDirectoryTabButton`, vehicle detail access sections | `loadServicesDirectory(force)`, `/api/v1/services/discovery`, `/api/v1/services/vehicle-access` | service grants, contacts, selected vehicle | grant/revoke and access state | READY |
| Share with service | vehicle detail/service access actions | POST/DELETE `/api/v1/services/vehicle-access` | service ID + vehicle ID | consent/tenant isolation | READY |
| Account settings | `account` tab | `loadProfile(force)`, `/user/me`, `/user/security/*` | profile/security data | export/delete/update semantics | READY |
| Support/Jak na to | support tab and `openHowToHubModal()` | help/onboarding handlers | support content | original support/onboarding entry points | READY |

## Service App

`web/service-shell.js` is a separate production shell and was audited read-only. It must not be edited in this map phase.

| Item | Current DOM / entry point | Handler / API | State / data | Must not lose | Status |
|---|---|---|---|---|---|
| Service shell | mounted through `window.serviceShell` | `init`, `mount`, `unmount`, `load`, `render` | service workspace state | separation from user app shell | READY |
| Service nav | `NAV_RAIL_CONFIG` groups/sections | `window.serviceShell.navigate(section)` | active section and nav group | submenu mapping | READY |
| Service dashboard | `dashboardSection()` | `/api/service/dashboard/summary`, `/api/service/dashboard/queue`, `/api/service/work-orders`, `/api/service/technicians/performance` | summary, queue, performance, active vehicle | real service KPIs/actions | READY |
| Customers | `clientsSection()` | `/api/v1/services/workspace/customers`, search/link/create/invite APIs | customer list/search/link state | customer linking and invitations | READY |
| Assigned vehicles | `vehiclesSection()` | `/api/v1/services/workspace/approved-vehicles`, vehicle detail modal APIs | approved vehicles | access rules and detail modal | READY |
| Access requests | service vehicle lookup/request flows | `/api/v1/services/workspace/vehicle-lookup`, `/access-requests` | lookup and pending request state | customer consent/access state | READY |
| Work orders | dashboard and nav `work-orders` | `/api/service/work-orders`, `openCreateWorkOrderModal()` | work-order list/modal state | create/update/detail workflow | READY |
| Service records | modal actions | `openServiceRecordModal(vehicleId, recordId?)` | selected vehicle/record | record creation tied to actual vehicle | READY |
| Documents | `documentsSection()` | `/api/v1/services/workspace/documents?limit=50`, `openDocumentDetailModal()` | service documents | authenticated docs | READY |
| Invoices | `invoicesSection()` | `/api/service/invoices`, `openCreateInvoiceModal()`, `openServiceInvoiceDetailModal()`, PDF actions | invoice filters/search/status | invoice creation/PDF/detail | READY |
| Quotes | nav item `quotes`, quote modal/list helpers | `/api/service/quotes/*`, public quote links | quote detail/status/public URL | approve/reject/PDF/public links | READY |
| Reservations | `reservationsSection()` | `/api/v1/reservations/service`, `openReservationDetailModal()` | reservation list/status | reservation status and archive toggles | READY |
| Reminders | `remindersSection()` | `/api/v1/services/workspace/reminders`, create/detail/update/delete | service reminders | overdue prompts and complete/reschedule | READY |
| Payroll/employees/attendance | nav entries and payroll refresh APIs | `/api/service/payroll/*` | payroll module state | payroll operations and downloads | NEEDS_ADAPTER |
| Bank/payment/internal docs | nav entries exist (`bank-statements`, `payment-orders`, `interni-dokumenty`) | no complete audited screen in first pass | unknown | must confirm before redesign | BLOCKER |
| Service settings/team | `teamSection()` | `/api/v1/services/workspace/partner-public-profile`, `/user/me` | public profile/team settings | save profile/settings | READY |
| Service notifications | service header button calls `window.toggleAppNotificationsPanel(event)` and badge `#serviceShellNotificationsBadge` | shared app notification handler | unread counts | must keep shared notification behavior | READY |
| Service logout | account modal/logout action | `window.serviceShell.logout()` | auth/session | full logout cleanup | READY |

## Admin

No complete admin frontend screen was found in the permitted audited web files. Backend/security references exist for admin roles and protected paths (`/admin-api`, `/api/admin`, `/web_admin`, `/admin-static`), and `web/ai-features.js` has admin-only actions, but this is not enough to define a reliable app-wide admin redesign.

| Item | Current DOM / entry point | Handler / API | State / data | Must not lose | Status |
|---|---|---|---|---|---|
| Admin entry | Backend protected prefixes and role checks found; no concrete web admin app found | security middleware protects `/admin-api`, `/api/admin`, `/web_admin`, `/admin-static` | admin/developer_admin role | admin access protections | BLOCKER |
| Admin dashboard | Not found in audited web frontend | unknown | unknown | must not invent dashboard | BLOCKER |
| Users | Not found in audited web frontend | unknown | unknown | user admin actions must be confirmed | BLOCKER |
| Services | Not found in audited web frontend | unknown | unknown | service management must be confirmed | BLOCKER |
| Service registration approvals | Backend/service registration references exist, no admin UI found | unknown | pending service accounts | approval workflow must be located | BLOCKER |
| Licences | Licensing backend/admin tenant references exist; user licence modal exists | unknown admin UI | licence state | do not alter licence contracts | BLOCKER |
| Support | Not found in admin frontend | unknown | unknown | support actions must be confirmed | BLOCKER |
| Audit/logs | Backend audit references exist, no frontend found | unknown | audit events | audit integrity | BLOCKER |
| Admin logout | no admin shell found | likely shared `handleLogout()` if in index shell, but not confirmed | token/session | logout semantics | BLOCKER |

## Non-negotiable redesign constraints

- Preserve `showLogin`, `showRegister`, `handleLogin`, `handleRegister`, `handleLoginTwoFactor`, `handleLogout`, `switchTab`, `toggleAppNotificationsPanel`, `toggleMobileProfileMenu`, `openLicenseModal`, `openHowToHubModal`, `openAddVehicleModal`, `showVehicleDetail`, `openAddServiceRecordModal`.
- Preserve `window.serviceShell.*` as the authoritative service workflow surface.
- Preserve all existing API endpoints and payload semantics.
- New UI elements must either reuse existing DOM/handlers or proxy to them through documented adapters.
- Anything marked `BLOCKER` cannot be implemented as a working feature until its production handler/API is confirmed.
