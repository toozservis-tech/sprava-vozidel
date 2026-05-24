# App-wide design map - 2026-05-18

Branch: `feature/app-wide-design-system-map-20260518`
Baseline SHA: `f8218f5d1df66b3f575338ddc254b6ca684e3e20`

This is the target visual system for the next redesign of Sprava vozidel. It is a design map only; it does not activate any UI.

## Global principles

- Light premium SaaS interface: background `#F5F7FA` / `#F7F9FC`, white surfaces, calm spacing.
- One visual language across public, auth, user, service, and admin areas.
- Blue is the primary product accent; green means verified/healthy; orange means attention; red means danger/overdue.
- Cards are clean, elevated, and functional. They must not become decorative wrappers around broken workflows.
- App sections use a left sidebar plus topbar on desktop, compact navigation on mobile.
- No old horizontal tab layout as the primary visual pattern in redesigned app screens.
- No ERP-heavy appearance, no generic automotive template, no hybrid of old and new UI.
- No demo vehicles or mock app data on real authenticated routes.
- Every redesigned component must map to an existing handler/API or be explicitly marked `BLOCKER`.

## Design tokens

### Colors

| Token | Value | Use |
|---|---:|---|
| `--sv-bg` | `#F5F7FA` | page background |
| `--sv-bg-soft` | `#F7F9FC` | bands and empty states |
| `--sv-surface` | `#FFFFFF` | cards, dropdowns, forms |
| `--sv-border` | `#E2E8F0` | card and control borders |
| `--sv-border-strong` | `#CBD5E1` | active/hover borders |
| `--sv-text` | `#0F172A` | main text |
| `--sv-muted` | `#64748B` | secondary text |
| `--sv-muted-strong` | `#334155` | important secondary text |
| `--sv-blue` | `#2563EB` | primary actions and active state |
| `--sv-blue-dark` | `#0B3BAE` | pressed/gradient end |
| `--sv-green` | `#22C55E` | verified/ok |
| `--sv-orange` | `#F59E0B` | attention |
| `--sv-red` | `#EF4444` | danger/overdue |
| `--sv-indigo-soft` | `#EEF4FF` | active nav background |
| `--sv-green-soft` | `#EAFBF1` | ok badge background |
| `--sv-orange-soft` | `#FFF4E5` | warning badge background |
| `--sv-red-soft` | `#FEECEC` | danger badge background |

### Typography

- Font stack: Inter if already available, otherwise system UI (`-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, `Arial`, sans-serif).
- Display heading: 48-64 px public hero, 700/800, line-height 1.04.
- App page heading: 28-34 px, 700/800, line-height 1.15.
- Card heading: 16-20 px, 700.
- Body: 14-16 px, 400/500.
- Meta text: 12-13 px, 500.
- No viewport-based font scaling.

### Spacing

| Token | Value |
|---|---:|
| `--sv-space-1` | 4 px |
| `--sv-space-2` | 8 px |
| `--sv-space-3` | 12 px |
| `--sv-space-4` | 16 px |
| `--sv-space-5` | 20 px |
| `--sv-space-6` | 24 px |
| `--sv-space-8` | 32 px |
| `--sv-space-10` | 40 px |
| `--sv-space-12` | 48 px |

### Radius

| Token | Value | Use |
|---|---:|---|
| `--sv-radius-sm` | 10 px | compact controls |
| `--sv-radius-md` | 14 px | inputs, buttons |
| `--sv-radius-lg` | 20 px | cards |
| `--sv-radius-xl` | 24 px | hero/auth/public cards |
| `--sv-radius-2xl` | 32 px | public CTA/large panels |

### Shadows

| Token | Value |
|---|---|
| `--sv-shadow-sm` | `0 8px 24px rgba(15, 23, 42, 0.06)` |
| `--sv-shadow-md` | `0 18px 45px rgba(15, 23, 42, 0.08)` |
| `--sv-shadow-lg` | `0 28px 70px rgba(15, 23, 42, 0.12)` |

### Grid and breakpoints

- App desktop: sidebar 248 px, content max width around 1500 px, 12-column logical grid.
- Dashboard desktop: main content + right rail, using CSS grid with `min-width: 0`.
- Vehicle grids: 3 columns desktop, 2 tablet, 1 mobile.
- Breakpoints:
  - mobile: `< 768px`
  - tablet: `768-1199px`
  - desktop: `>= 1200px`
  - wide: `>= 1536px`
- No `width: 100vw` inside offset containers. Use `%`, grid, and `min-width: 0`.

### Z-index layers

| Layer | Value |
|---|---:|
| content | 1 |
| sticky topbar/sidebar | 50 |
| dropdown/popover | 200 |
| notification/profile menu | 300 |
| modal backdrop | 900 |
| modal/dialog | 1000 |
| toast | 1100 |

### Form, error, and success states

- Inputs: 48-52 px high, 14 px radius, subtle border, blue focus ring.
- Buttons: 44 px minimum touch target.
- Errors: red text and red-soft background; do not rely only on color.
- Loading: disabled button + spinner/label, no duplicate submit.
- Success: green check affordance with clear text.

## Components

| Component | Visual target | Functional source |
|---|---|---|
| Public floating navbar | centered glass/white header, rounded 24-28 px, logo left, nav center, login/register right | existing public CTAs `showLogin()`, `showRegister()` |
| Public hero | two columns, strong headline, dashboard mockup, floating status cards | public landing only; mockup is decorative and non-interactive |
| Public CTA | blue gradient card with two auth CTAs | existing auth functions |
| Auth card | centered white card, account type segmented control, compact explanation | existing auth forms/handlers |
| Auth form input | rounded, accessible labels, error slot below | existing form IDs and submit handlers |
| Auth account type selector | user/service segmented control | `setLoginMode`, `setRegistrationMode` |
| App shell | left light sidebar, topbar, content grid | existing `#app-shell`, `switchTab` |
| Sidebar | logo, nav items with icons, active blue pill, help box | existing tabs/router mapped through bridge |
| Topbar | search, primary action, notification, profile | existing search/action/notification/profile handlers |
| Search | 48 px rounded input with icon and keyboard hint | current search or adapter to existing filters |
| Button | blue primary, subtle secondary, icon+text where useful | existing handlers only |
| Badge | status pill with semantic color | real status from vehicle/reminder/license data |
| Card | white surface, border, subtle shadow | data-bound app content |
| Dropdown | white floating menu, high z-index, outside click | original dropdown/menu handlers or adapters |
| Notification panel | original notification data in new styled popover | `#appNotificationsPanel` / service shared notifications |
| User profile menu | original menu content in new visual style | `#mobileProfileMenu`, `toggleMobileProfileMenu()` |
| Vehicle card | large photo, status badge, SPZ/VIN/mileage/STK/service/doc actions | `/api/v1/vehicles` and vehicle actions |
| Vehicle detail card | hero photo, metadata, action row, tabs/sections, right rail | `showVehicleDetail`, vehicle detail APIs |
| Timeline item | date line, icon, title, vehicle/service, attachments/actions | service records/reminders |
| Document card | type icon, status, vehicle, download/open actions | documents hub and attachment APIs |
| Reminder card | kanban/status card with complete/delay/detail | reminder APIs |
| Invoice card | invoice status, total, linked vehicle/service, PDF/detail | service invoice APIs; user invoice needs confirmation |
| Service access card | service logo/name, status, permissions, revoke/manage | service access APIs |
| Empty state | icon, clear action, no fake data | same handler as primary create action |
| Loading skeleton | card/list placeholders | loading states before API data |
| Modal bridge | new modal frame can host old form/body or proxy old modal | existing modal functions |
| Admin table/card hybrid | modern table with cards on mobile | BLOCKER until admin UI is located |
| Service workspace card | service KPIs/customer/vehicle card | `window.serviceShell` data/actions |

## Public screens

### Public landing page

Target:
- floating navbar, hero, benefit cards, owner/service panels, how-it-works, trust/security, bottom CTA, footer.
- premium SaaS tone, light background, blue accent.

Original functions:
- login/register CTAs use `showLogin()`, `showRegister()`.
- account-specific CTAs may call `setRegistrationMode('user'/'service')`.

Blockers:
- none for landing shell; pricing/support routes need product confirmation if they become dedicated pages.

### Features / owner / service / pricing / how it works

Target:
- anchor sections within landing until dedicated routes are confirmed.
- cards and two-column panels matching GPT visual language.

Original functions:
- public nav/anchor scrolling, auth CTAs.

Blockers:
- dedicated public pricing page not found.

### Public QR / vehicle verification

Target:
- clean public report page with vehicle identity, verified history timeline, documents, quote/transfer actions where applicable.

Original functions:
- `web/public-vehicle-history.html`, `web/verify.html`, `web/public-quote.html`, `web/vehicle-transfer.html`.

Blockers:
- none for known public pages; exact QR landing route must be confirmed during implementation.

## Auth screens

### Login

Target:
- auth card with logo, account type switch, email/password, forgot password, optional 2FA step, error slot.

Original functions:
- `handleLogin()`, `handleLoginTwoFactor()`, `setLoginMode()`, `showForgotPasswordForm()`.

Blockers:
- none.

### User registration

Target:
- account type selector, user fields, privacy/consent text, success/pending screen.

Original functions:
- `setRegistrationMode('user')`, `handleRegister()`.

Blockers:
- none.

### Service registration

Target:
- service-specific form fields, clear approval expectation, pending approval state.

Original functions:
- `setRegistrationMode('service')`, `handleRegister()`, `#serviceRegistrationExtraFields`, `#registerPendingState`.

Blockers:
- admin approval UI not found, but auth-side pending state is ready.

### Reset/verification states

Target:
- consistent auth card styling for forgot/reset/verify/error/success.

Original functions:
- `web/reset-password.html`, `web/verify.html`, existing auth error containers.

Blockers:
- full SMS verification screen not found.

## User screens

### Prehled

Target:
- left sidebar, topbar, hero summary, status card, quick cards, vehicle preview, right rail with upcoming terms/activity/service access.

Original functions:
- `loadHomeDashboard()`, `switchTab('home')`, notification/profile handlers.

Blockers:
- none.

### Moje vozidla

Target:
- garage/catalog layout with filters, sort/view controls, vehicle cards, add vehicle card, summary strip.

Original functions:
- `loadVehicles()`, `setVehicleView()`, `openAddVehicleModal()`, `showVehicleDetail(vehicleId)`.

Blockers:
- none.

### Detail vozidla

Target:
- hero detail panel, metric cards, section tabs, right rail timeline/terms/actions/access.

Original functions:
- `showVehicleDetail(vehicleId)`, `openVehicleDetailFloatingSection(section, vehicleId)`, vehicle APIs, record/document/photo/access handlers.

Blockers:
- none.

### Servisni historie

Target:
- timeline/list view with filters, cost summary, common operations, service summary.

Original functions:
- vehicle record APIs and service record modals; cross-vehicle service history may need adapter over current vehicle records.

Blockers:
- global user "service history" tab is not a dedicated current tab; implement as adapter only after exact source data is mapped.

### Pripominky

Target:
- status columns/cards, calendar side rail, automatic reminder settings.

Original functions:
- `loadReminders()`, `/api/v1/reminders`, `/api/v1/reminders/settings`.

Blockers:
- none.

### Dokumenty

Target:
- document hub with vehicle/type/status filters, upload actions, document cards.

Original functions:
- `loadDocumentsHub()`, upload/download document/attachment APIs.

Blockers:
- none.

### Servisy

Target:
- service directory/access dashboard, partner cards, permission management.

Original functions:
- `loadServicesDirectory()`, `/api/v1/services/discovery`, `/api/v1/services/vehicle-access`.

Blockers:
- none.

### Faktury

Target:
- invoices list/cards, linked vehicle/service status, PDF/detail.

Original functions:
- service invoice APIs exist; user invoice surface not found as dedicated tab.

Blockers:
- user invoice section requires confirmed production route/API before implementation.

### Nastaveni / Licence / Jak na to

Target:
- account settings page, license modal/section, onboarding/help hub.

Original functions:
- `loadProfile()`, `/user/me`, `/user/security/*`, `openLicenseModal()`, `openHowToHubModal()`.

Blockers:
- none for settings/license/help entry points.

## Service screens

### Service dashboard

Target:
- service workspace with KPI cards, queue, latest customers/vehicles/work orders, quick actions.

Original functions:
- `window.serviceShell.load()`, `dashboardSection()`, service dashboard APIs.

Blockers:
- none.

### Customers / vehicles

Target:
- customer cards/table hybrid, assigned vehicles, access request status.

Original functions:
- `clientsSection()`, `vehiclesSection()`, customer/vehicle/access request APIs.

Blockers:
- none.

### Work orders / service records

Target:
- kanban/list with status, technician, vehicle/customer, record creation.

Original functions:
- service work order APIs and `openServiceRecordModal()`.

Blockers:
- none.

### Documents / invoices / quotes / reservations / reminders

Target:
- card/table hybrid with filters, detail modals, PDF/public links where existing.

Original functions:
- `documentsSection()`, `invoicesSection()`, quote helpers, `reservationsSection()`, `remindersSection()`.

Blockers:
- none for listed active sections.

### Payroll, bank/payment, internal documents

Target:
- same service shell visual language, but only after feature surface is confirmed.

Original functions:
- payroll APIs exist; bank/payment/internal docs nav exists but screen completeness unclear.

Blockers:
- bank/payment/internal docs require a deeper dedicated audit before visual implementation.

### Service settings

Target:
- partner profile, team/settings cards, integrations/access settings.

Original functions:
- `teamSection()`, partner profile APIs.

Blockers:
- integrations/access settings need detailed implementation audit.

## Admin screens

Admin redesign is a documentation placeholder only until the real admin frontend is found.

Target visual language:
- same light SaaS system, denser information surfaces.
- tables for users/services/licences/audit with card summaries.
- explicit approval queues and audit-safe action confirmations.

Known source:
- backend role/security/admin prefixes exist.

Blockers:
- admin dashboard, users, services, approvals, licences, support, audit/logs, and admin logout frontend entry points were not found in the audited web files.

## Architecture recommendation

Recommended approach: **Variant C - hybrid safe rollout**.

Reasoning:
- Public/auth can be restyled first with low risk because their forms and CTAs are clearly located in `web/index.html`.
- User app needs a bridge-driven shell so notification/profile/menu/vehicle flows remain production-backed.
- Service shell is already separate and complex; it should receive its own later design pass using `window.serviceShell` as the contract.
- Admin cannot be implemented until the real admin frontend is located.

Implementation order after approval:
1. Generate final public landing, login, and registration screens from the design map.
2. Implement public/auth visual layer only, preserving existing form IDs and handlers.
3. Create user shell/topbar/sidebar bridge with original notification/profile/menu handlers.
4. Restyle user screens one by one, each behind functional bridge checks.
5. Restyle service shell after a dedicated service bridge pass.
6. Locate/admin-map admin UI before any admin redesign.
