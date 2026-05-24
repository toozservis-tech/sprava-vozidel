# App-wide bridge map - 2026-05-18

Branch: `feature/app-wide-design-system-map-20260518`
Baseline SHA: `f8218f5d1df66b3f575338ddc254b6ca684e3e20`

Rule: every new UI element must reuse or proxy the original production handler/API. If the original is not known, the status is `BLOCKER` and implementation must stop for that element.

| New UI element | App part | Original function / handler | Original DOM / API | Status | Note |
|---|---|---|---|---|---|
| CTA Prihlasit se | Public | `showLogin()` | public buttons in `web/index.html` | READY | Preserve current auth switch. |
| CTA Vyzkouset zdarma | Public | `showRegister()` | public buttons in `web/index.html` | READY | May also set account type if CTA is contextual. |
| CTA Zacit zdarma | Public | `showRegister()` | hero/final CTA buttons | READY | No new registration flow. |
| CTA Zobrazit ukazku | Public | anchor scroll or existing public section navigation | public landing sections | NEEDS_ADAPTER | Safe if it only scrolls; no fake app iframe. |
| Landing nav links | Public | anchor scroll / existing public menu behavior | `#publicSiteMenuToggle`, `#publicSiteDrawer` | READY | Keep mobile drawer accessibility. |
| Public QR vehicle history | Public | public history fetch/render | `web/public-vehicle-history.html`, `/api/public/vehicle-history/{token}` | READY | Keep token privacy. |
| Public document verify | Public | `verifyByToken`, `verifyByCode` | `web/verify.html`, `/api/public/documents/verify*` | READY | Keep code/token states. |
| Public quote | Public | public quote load/action | `web/public-quote.html`, `/api/public/quote/{token}` | READY | Keep approve/reject actions. |
| Login submit | Auth | `handleLogin()` | `#loginForm`, `#loginSubmitBtn` | READY | Preserve error/loading and redirect. |
| Login 2FA submit | Auth | `handleLoginTwoFactor()` | `#loginTwoFactorPanel`, `#loginTwoFactorCode` | READY | Do not bypass 2FA. |
| Register user submit | Auth | `setRegistrationMode('user')`, `handleRegister()` | `#registerForm`, user mode button | READY | Preserve validation. |
| Register service submit | Auth | `setRegistrationMode('service')`, `handleRegister()` | `#serviceRegistrationExtraFields`, pending state | READY | Preserve approval pending flow. |
| Forgot password | Auth | `showForgotPasswordForm()`, `handleForgotPassword()` | `#forgotPasswordForm` | READY | Existing modal can be restyled. |
| Reset password | Auth | `handleResetPassword(event)` | `web/reset-password.html`, `/user/reset-password` | READY | Separate page visual pass. |
| Email verification | Auth | current register/verification flow | registration pending state, verification pages | NEEDS_ADAPTER | Exact email verification route needs implementation check. |
| Phone verification | Auth | none found | no complete SMS screen found | BLOCKER | Do not design as working SMS until backend/frontend flow is confirmed. |
| Account type switch | Auth | `setLoginMode`, `setRegistrationMode` | login/register mode buttons | READY | Must preserve role-specific copy and checks. |
| Auth errors | Auth | existing auth handlers | `#loginErrorContainer`, `#registerErrorContainer` | READY | Keep accessible error slots. |
| Redirect after login | Auth | `navigateToStoredAppAfterAuth()` | `/api/me`, `/user/me`, route state | READY | Must preserve role routing. |
| New notification bell | User | `toggleAppNotificationsPanel(event)` | `#desktopNotificationsButton`, `#mobileNotificationsButton`, `#appNotificationsPanel` | READY | Prefer reusing original buttons or proxy `.click()`. |
| New notification panel | User | `renderAppNotificationsPanelList`, `loadSystemNotifications` | `#appNotificationsPanel`, `#appNotificationsList` | READY | Do not build separate empty panel. |
| New profile button | User | `toggleMobileProfileMenu()` | `#desktopProfileButton`, `#mobileProfileMenu` | READY | Must open menu, not direct settings. |
| New profile menu | User | original profile menu actions | `#mobileProfileMenu` | READY | Preserve all original menu rows. |
| Jak na to | User | `openHowToHubModal()` | profile menu action/support entry | READY | Keep original onboarding/help behavior. |
| Licence | User | `openLicenseModal()`, `initLicenseQuickBadge()` | profile menu/license quick controls, `/api/v1/license/*` | READY | Preserve plan and Comgate behavior. |
| Nastaveni | User | `switchTab('account')` | `#appShellNav`, account tab | READY | Profile click itself must not call this directly. |
| Odhlaseni | User | `handleLogout()` | `#logout-btn`, profile action | READY | Preserve full token/session cleanup. |
| Sidebar Prehled | User | `switchTab('home')` | `[data-tab-key="home"]`, `#homeTab` | READY | Keep data loading. |
| Sidebar Moje vozidla | User | `switchTab('vehicles')` | `[data-tab-key="vehicles"]`, `#vehiclesTab` | READY | Keep vehicle list state. |
| Sidebar Servisni historie | User | vehicle records / service history adapter | vehicle detail record APIs | NEEDS_ADAPTER | Current global dedicated tab not found; bridge must use real records. |
| Sidebar Pripominky | User | `switchTab('reminders')`, `loadReminders()` | `[data-tab-key="reminders"]`, `/api/v1/reminders` | READY | Keep settings/complete/detail actions. |
| Sidebar Dokumenty | User | `switchTab('documents')`, `loadDocumentsHub()` | `[data-tab-key="documents"]`, `/api/v1/vehicles/documents/hub` | READY | Keep central docs hub. |
| Sidebar Servisy | User | `switchTab('servicesDirectory')`, `loadServicesDirectory()` | hidden tab button, services APIs | READY | Must reveal/bridge real service directory. |
| Sidebar Faktury | User | no dedicated user invoice tab found | service invoices exist only in service shell | BLOCKER | Do not fake user invoices until source is confirmed. |
| Sidebar Nastaveni | User | `switchTab('account')`, `loadProfile()` | `[data-tab-key="account"]`, `/user/me` | READY | Preserve account/security flows. |
| Topbar search | User | current list filters/search or adapter | vehicle/service/reminder/document search inputs vary per tab | NEEDS_ADAPTER | Needs per-section routing to real filters. |
| Add vehicle | User | `openAddVehicleModal()` | `#btnOpenAddVehicleModal`, `#addVehicleModal`, `/api/v1/vehicles` | READY | Reuse original modal/submit. |
| Vehicle detail | User | `showVehicleDetail(vehicleId)` | `#vehicleDetailModal`, `/api/v1/vehicles/{id}` | READY | Pass real ID. |
| Add record | User | `openAddServiceRecordModal(vehicleId)` | `#addServiceRecordModal`, `/api/v1/vehicles/{id}/records` | READY | Pass real vehicle ID. |
| Vehicle documents | User | document hub/detail section | `/api/v1/vehicles/documents/hub`, attachment APIs | READY | Keep authenticated downloads. |
| Share with service | User | service access grant/revoke | `/api/v1/services/vehicle-access` | READY | Preserve permission/tenant isolation. |
| Upload photo | User | photo upload/promote/delete functions | `/api/v1/vehicles/{id}/photo`, `/photos`, `/photo/promote` | READY | No demo image fallback except neutral placeholder. |
| Upload document | User | attachment upload/document prefill | `/api/v1/vehicles/{id}/records/attachments/upload`, document prefill | READY | Keep existing upload constraints. |
| Reminder detail | User | reminder detail/edit handlers | `/api/v1/reminders/{id}` | READY | Preserve complete/delay/delete. |
| Invoice detail | User | not found for user app | unknown | BLOCKER | Needs confirmed user invoice surface. |
| Service access detail | User | service access/detail actions | `/api/v1/services/discovery`, `/vehicle-access` | READY | Use existing access state. |
| Service dashboard nav | Service | `window.serviceShell.navigate('dashboard')` | `NAV_RAIL_CONFIG`, `dashboardSection()` | READY | Do not edit service shell in map phase. |
| Service customer detail | Service | `openCustomerDetailModal(id)` | customers section, workspace customer APIs | READY | Preserve customer link/unlink actions. |
| Service vehicle detail | Service | `openVehicleDetailModal(id)` | vehicles section, service vehicle APIs | READY | Preserve access rules. |
| Service access request | Service | lookup/request handlers | `/api/v1/services/workspace/vehicle-lookup`, `/access-requests` | READY | Preserve consent flow. |
| Service create record | Service | `openServiceRecordModal(vehicleId, recordId?)` | service shell modal APIs | READY | Use actual vehicle. |
| Service documents | Service | `openDocumentDetailModal(id)` | `/api/v1/services/workspace/documents` | READY | Preserve downloads/detail. |
| Service invoices | Service | `openCreateInvoiceModal`, `openServiceInvoiceDetailModal`, PDF helpers | `/api/service/invoices` | READY | Preserve invoice status/PDF. |
| Service reservations | Service | `openReservationDetailModal(id)` | `/api/v1/reservations/service` | READY | Preserve reservation status updates. |
| Service logout | Service | `window.serviceShell.logout()` | service account modal/logout action | READY | Preserve service session cleanup. |
| Service payroll | Service | payroll module functions | `/api/service/payroll/*` | NEEDS_ADAPTER | Needs dedicated UI mapping before restyle. |
| Service bank/payments/internal docs | Service | nav entries found, complete screens unclear | `bank-statements`, `payment-orders`, `interni-dokumenty` | BLOCKER | Must audit deeper before visual work. |
| Admin nav | Admin | not found | protected prefixes `/admin-api`, `/api/admin`, `/web_admin`, `/admin-static` | BLOCKER | Locate admin frontend first. |
| Approve service registration | Admin | not found | backend references only | BLOCKER | Do not invent approval screen. |
| Admin user detail | Admin | not found | unknown | BLOCKER | Locate frontend/API contract first. |
| Admin service detail | Admin | not found | unknown | BLOCKER | Locate frontend/API contract first. |
| Admin license change | Admin | not found | licensing backend references only | BLOCKER | User licence modal is not admin UI. |
| Admin support action | Admin | not found | unknown | BLOCKER | Locate admin support module first. |
| Admin audit/logs | Admin | not found | backend audit references only | BLOCKER | Needs confirmed frontend/API. |
| Admin logout | Admin | not found | maybe shared logout if index shell is reused | BLOCKER | Confirm admin shell before redesign. |

## Adapter rules

1. A new visual button must either be the original DOM element restyled or call the original handler.
2. A new route/sidebar item must call the original router/tab function or a documented adapter that loads original API data.
3. A new card action must carry the original entity ID (`vehicle_id`, `record_id`, `document_id`, `service_id`, `invoice_id`, etc.).
4. Dropdowns and modals must keep original close/outside-click/keyboard behavior where it exists.
5. No handler may be replaced by `alert`, toast-only messages, `console.log`, or a dead link.
6. Any item marked `BLOCKER` must be resolved before implementation.

## Current blockers

- Full phone/SMS verification UI is not visible in the audited frontend.
- Dedicated public pricing page is not clearly present.
- User global service-history screen needs a real data adapter if it is promoted from vehicle-level records.
- User invoices/faktury route is not found as a dedicated current user tab.
- Service bank/payments/internal documents sections have nav entries but need deeper confirmation.
- Admin frontend entry, dashboard, users, services, approvals, licences, support, audit/logs, and logout are not located in the audited web files.
