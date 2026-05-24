# User app visual reference map

Datum: 2026-05-19

Tento dokument pouze mapuje budoucí redesign přihlášeného uživatelského rozhraní podle dodaných referenčních screenů. Neobsahuje implementaci.

## Globální pravidla pro implementaci

- STAGING ONLY: pracovat pouze v `/opt/toozhub2-staging/app`.
- Produkci neměnit.
- Backend/DB neměnit.
- `web/service-shell.js` neměnit, protože řešený scope je user app, ne servisní shell.
- Neměnit auth/session/token/logout logiku.
- Zachovat existující handlery a datové flow. Redesign smí přeskupit markup/CSS jen tam, kde neporuší funkce.
- Neodstraňovat existující element IDs, které používají JS handlery.
- Nepřidávat externí CDN, hotlinkované obrázky ani iframe.

## 1. `uvod po přihlášení.png`

### Cílový route/tab

- Přihlášený user dashboard.
- Interní tab/sekce: `home`.
- URL mapping zachovat přes `userAppSectionFromTab()`, `userTabFromAppSection()`, `syncUserTabUrlHistory()` a `applyWorkspaceRouteFromUrl()`.

### Existující funkce/handlery, které musí zůstat

- `showDashboard()`
- `switchTab(tab, options = {})`
- `loadHomeDashboard()`
- `loadHomeDashboardLegacy(token)`
- `renderHomeDashboardState(model)`
- `buildUserDashboardCommandCards(license)`
- `openHomeDashboardStatusBubble(kind)`
- `closeHomeDashboardStatusBubble(options = {})`
- `handleDashboardAttentionAction(vehicleId, actionTarget = '')`
- `openVehicleFromShortcut(vehicleId, source = '')`
- `loadLicenseStatus()`
- `applyLicenseToUI(license)`

### Zakázané zásahy

- Neměnit login/session bootstrap.
- Neměnit API endpointy dashboardu.
- Neměnit license gating.
- Neměnit service workspace routing.
- Neměnit `service-shell.js`.

### Hlavní vizuální prvky podle screenshotu

- Světlý prémiový dashboard po přihlášení.
- Levá hlavní plocha s přehledem vozidel, termínů a stavů.
- Karty metrik a stavové prvky s barevnou hierarchií.
- Rychlé akce bez ERP vzhledu.
- Jasný focus na vozidla, STK, servisní historii a dokumenty.
- Žádný horizontální overflow na desktopu ani mobilu.

### BLOCKER položky

- Přesné aktuální API payloady dashboardu je nutné před implementací ověřit v runtime nebo v `loadHomeDashboard()`.

## 2. `sekce moje vozidla.png`

### Cílový route/tab

- Přihlášená sekce Moje vozidla / digitální garáž.
- Interní tab/sekce: `vehicles`.
- Zachovat navigaci přes `switchTab('vehicles')`.

### Existující funkce/handlery, které musí zůstat

- `loadVehicles(force = true)`
- `setVehicleView(mode)`
- `getVehicleViewMode()`
- `applyVehicleViewModeUI()`
- `openAddVehicleModal()`
- `closeAddVehicleModal(options = {})`
- `handleAddVehicle()`
- `previewAddVehiclePhoto(fileInput)`
- `loadVinData(vin)`
- `refreshExistingVehicleFromVin(vehicleId)`
- `toggleVehicleDetail(vehicleId)`
- `showVehicleDetail(vehicleId)`
- `deleteVehicle(vehicleId)`
- `hydrateVehicleCardPhotos(vehicles)`
- `hydrateVehicleCardPhotoPreview(vehicleId)`
- `buildVehiclePhotoUrl(vehicleId)`

### Zakázané zásahy

- Neměnit vehicle CRUD endpointy.
- Neměnit VIN decode flow.
- Neměnit upload/crop/gallery handlery.
- Neměnit existující form IDs používané pro přidání vozidla.
- Neměnit servisní přidávání vozidla v service scope.

### Hlavní vizuální prvky podle screenshotu

- Digitální garáž s kartami vozidel.
- Produktovější karta vozidla s fotkou, SPZ, STK, nájezdem a stavem.
- Přepínače zobrazení bez rušivého tabulkového vzhledu.
- Viditelná akce pro přidání vozidla.
- Barevné stavové badge pro OK / blížící se termín / problém.

### BLOCKER položky

- Je nutné ověřit, jestli část seznamu vozidel renderuje React root přes `ensureReactVehicleListRoot()`; pokud ano, změny musí respektovat React mount a nesmí rozbít fallback rendering.

## 3. `přehied vozidla.png`

### Cílový route/tab

- Detail vozidla otevřený z `vehicles`.
- Interní view/modal/detail: `vehicleDetail`, `vehicleDetailModal`, případně inline detail podle existujícího toku.

### Existující funkce/handlery, které musí zůstat

- `showVehicleDetail(vehicleId)`
- `toggleVehicleDetail(vehicleId)`
- `loadVehicleDetailInline(vehicleId)`
- `openVehicleDetailFloatingSection(sectionKeyOrId, vehicleId)`
- `closeVehicleDetailFloatingSection(options = {})`
- `revealVehicleDetailSection(sectionId)`
- `resolveVehicleDetailSectionConfig(sectionKeyOrId, vehicleId)`
- `renderVehicleDetailQrCard(vehicle, isServiceMode)`
- `copyVehiclePublicHistoryLink(url)`
- `openVehiclePublicHistory(url)`
- `saveVehicleFieldModal(field, vehicleId)`
- `saveVehicleFieldInline(field, vehicleId)`
- `loadVehicleGallery(vehicleId)`
- `handleVehicleGalleryUpload(vehicleId, inputEl)`
- `promoteVehicleGalleryPhoto(vehicleId, photoId)`
- `deleteVehicleGalleryPhoto(vehicleId, photoId)`

### Zakázané zásahy

- Neměnit datový model vozidla.
- Neměnit QR/public history endpointy.
- Neměnit galerii, primary photo a crop algoritmus.
- Neměnit servisní access grant logiku.
- Neměnit API volání tachometru/STK.

### Hlavní vizuální prvky podle screenshotu

- Detail vozidla jako čistá produktová obrazovka.
- Hero karta vozidla s fotkou, stavovými chipy a klíčovými údaji.
- Přehled technických dat, dokumentů, STK a servisních akcí ve vizuálních blocích.
- Přehledná navigace detailu bez přehlcení.
- Akční prvky pro editaci a doplnění dat musí zůstat jasné.

### BLOCKER položky

- Před implementací je nutné rozhodnout, zda cílem je redesign inline detailu, floating modal detailu, nebo obou variant současně.

## 4. `servisni historie.png`

### Cílový route/tab

- Servisní historie v detailu vozidla.
- Pravděpodobně sekce uvnitř `vehicleDetail` / `vehicleDetailModal`.

### Existující funkce/handlery, které musí zůstat

- `loadServiceRecordsModal(vehicleId)`
- `loadServiceRecordsInline(vehicleId)`
- `loadServiceRecords(vehicleId)`
- `openAddServiceRecordModal(vehicleId = null)`
- `handleAddServiceRecordSubmit(event)`
- `openEditServiceRecordModal(recordId, vehicleId)`
- `handleEditServiceRecordSubmit(event, recordId, vehicleId)`
- `showServiceRecordDetail(recordId, vehicleId)`
- `closeServiceRecordDetailModal()`
- `deleteServiceRecordModal(recordId, vehicleId)`
- `deleteServiceRecordInline(recordId, vehicleId)`
- `deleteServiceRecord(recordId)`
- `uploadServiceRecordAttachment(vehicleId, file)`
- `openServiceRecordAttachmentPreview(encodedDownloadUrl, encodedFileName = '')`
- `downloadAuthenticatedRelativeFile(relativeUrl, fallbackFilename = 'soubor')`
- `generateServiceRecordsPDF(vehicleId)`

### Zakázané zásahy

- Neměnit create/edit/delete servisních záznamů.
- Neměnit attachment upload/download.
- Neměnit PDF export.
- Neměnit parsed summary/service report editor.
- Neměnit service workspace servisní modaly.

### Hlavní vizuální prvky podle screenshotu

- Servisní historie jako přehledná časová osa nebo list servisních záznamů.
- Viditelné datum, typ práce, nájezd, cena, servis a přílohy.
- Detail záznamu v modalu nebo rozbalení.
- CTA pro přidání servisního záznamu.
- Barevné ikony podle typu záznamu.

### BLOCKER položky

- Je nutné ověřit, která ze tří variant renderingu je aktivní pro user flow: modal, inline, nebo legacy `loadServiceRecords()`.

## 5. `připomínky.png`

### Cílový route/tab

- Přihlášená sekce Připomínky.
- Interní tab/sekce: `reminders`.
- Zachovat navigaci přes `switchTab('reminders')`.

### Existující funkce/handlery, které musí zůstat

- `loadReminders(force = true)`
- `setReminderView(mode)`
- `getReminderViewMode()`
- `setReminderFilter(mode)`
- `getReminderFilterMode()`
- `setReminderListSort(mode)`
- `handleReminderListSortChange(event)`
- `setReminderVehicleFilter(vehicleId)`
- `renderGroupedReminderCards(reminders, viewMode)`
- `buildReminderInsightsHtml(reminders)`
- `buildReminderVehicleFilterHtml(reminders, selectedVehicleId)`
- `buildReminderCalendarHtml(reminders)`
- `openReminderDetailModalByIndex(index)`
- `closeReminderDetailModal()`
- `showCreateReminderForm()`
- `handleCreateReminder()`
- `editReminder(reminderId)`
- `handleUpdateReminder(reminderId)`
- `deleteReminder(reminderId)`
- `showReminderScheduleForm(reminderId)`
- `handleUpdateReminderSchedule(reminderId)`
- `loadReminderSettings()`
- `handleSaveReminderSettings(event)`

### Zakázané zásahy

- Neměnit reminder CRUD endpointy.
- Neměnit push notification nastavení.
- Neměnit reminder settings persistence.
- Neměnit servisní reminder workspace handlery.
- Neměnit reservation reminders mimo explicitní scope.

### Hlavní vizuální prvky podle screenshotu

- Přehled připomínek se stavovými kartami.
- Filtrování aktivní / hotové / po termínu.
- Přepínač zobrazení seznam / grid / kalendář, pokud má zůstat podle stávající funkce.
- Jasný termín, vozidlo, typ připomínky a upozornění.
- Akce detail, přeplánovat, splnit, upravit, smazat.

### BLOCKER položky

- Před implementací ověřit, zda screenshot cílí na grid/list/kalendář, aby nedošlo ke zrušení existujících view módů.

## Implementační pořadí pro další fázi

1. Přehled po přihlášení (`home`) jako první, protože tvoří shell a vizuální jazyk.
2. Moje vozidla (`vehicles`) jako druhé, protože dashboard na ně odkazuje.
3. Detail vozidla jako třetí, s jasným rozhodnutím modal vs inline.
4. Servisní historie uvnitř detailu vozidla.
5. Připomínky (`reminders`) nakonec, protože mají více režimů a filtrů.

Každá fáze musí mít vlastní staging-only diff, vizuální QA a smoke test bez zásahu do produkce.
