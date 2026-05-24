# License Menu v TopBar - Shrnutí implementace

## ✅ Provedené změny

### 1. HTML struktura (web/index.html)

**Přidáno do TopBar (řádky ~2393):**
- Nový element `#licenseMenu` v `.navbar-stats` za `#serverStatus`
- Dropdown struktura s aktuální licencí a dostupnými plány
- Responzivní layout s flexbox

**Skryto původní badge:**
- `#licenseBadge` v dashboardu je nyní skrytý (`display: none !important`)

### 2. CSS styly (web/theme.css)

**Přidáno:**
- `.license-menu` - základní styling s cursor pointer a pozicí relative
- `.license-dropdown` - absolutně pozicovaný dropdown s shadow a border
- `.license-current` - styling pro aktuální licenci
- `.license-plans` - styling pro sekci s plány
- `.plan-item` - styling pro jednotlivé plány
- `.plan-action` - styling pro tlačítka "Aktivní" / "Upgradovat"

**Vlastnosti:**
- Dropdown se zobrazuje pod badge (top: calc(100% + 8px))
- Z-index: 1000 pro správné zobrazení nad ostatními elementy
- Hover efekty a transitions
- Responzivní design (320px šířka)

### 3. JavaScript logika (web/index.html)

**Upravena funkce `loadLicenseStatus()`:**
- Místo renderování do `#licenseBadge` nyní volá `renderLicenseMenu(data)`
- Zobrazuje `#licenseMenu` po úspěšném načtení
- Zobrazuje chybu v TopBar pokud selže načtení

**Nová funkce `renderLicenseMenu(license)`:**
- Nastavuje text v `#licenseMenuText` (např. "Licence: FREE")
- Aktualizuje `#licenseCurrentText` s detaily (počet vozidel, limit)
- Označuje aktivní plán jako "Aktivní" (disabled tlačítko)
- Ostatní plány mají tlačítko "Upgradovat"

**Nová funkce `toggleLicenseDropdown()`:**
- Přepíná viditelnost dropdown menu (toggle class 'hidden')

**Nová funkce `initLicenseDropdownHandlers()`:**
- Event listener na kliknutí do `#licenseMenu` - otevře/zavře dropdown
- Event listener na kliknutí mimo menu - zavře dropdown
- Event listener na tlačítka "Upgradovat" - placeholder alert (bez backend logiky)

### 4. Lifecycle management

**V `showDashboard()`:**
- Volá se `initLicenseDropdownHandlers()` pro inicializaci event handlerů
- Volá se `loadLicenseStatus()` pro načtení licence

**V `handleLogout()`:**
- Skryje `#licenseMenu` při odhlášení

**V `loadLicenseStatus()`:**
- Zobrazuje `#licenseMenu` po úspěšném načtení
- Skrývá při chybě (text "Licence: ERROR")

## 📋 Akceptační kritéria

✅ **Licence NENÍ vidět jako samostatný box v obsahu stránky**
- `#licenseBadge` je skrytý (`display: none !important`)

✅ **V TopBar je malý badge "Licence: …"**
- `#licenseMenu` zobrazuje text "Licence: FREE/BASIC/PREMIUM"

✅ **Klik otevře dropdown/bublinu**
- Click handler otevírá/zavírá dropdown
- Dropdown obsahuje aktuální licenci a dostupné plány

✅ **Data odpovídají /api/v1/license/status**
- `loadLicenseStatus()` volá `/api/v1/license/status`
- Data jsou správně parsována a zobrazena

✅ **UI je čisté, responzivní, nerozbije navbar**
- Používá existující `.stat-badge` třídu
- Responzivní design s flex-wrap
- Dropdown má správný z-index

## 🎨 UX detaily

- **Badge text:** "Licence: FREE" / "Licence: BASIC" / "Licence: PREMIUM"
- **Dropdown obsahuje:**
  - Aktuální licenci s detaily (počet vozidel, limit)
  - Seznam všech plánů (Free, Basic, Premium)
  - Aktivní plán označen "Aktivní" (nebo "Aktivní / Základ" pro Free)
  - Ostatní plány mají tlačítko "Upgradovat"
- **Interakce:**
  - Klik na badge otevře/zavře dropdown
  - Klik mimo dropdown ho zavře
  - Klik na "Upgradovat" zobrazí placeholder alert

## 🔄 Další kroky (neprováděno)

- ❌ Backend API pro upgrade licence
- ❌ Platby/integrace platební brány
- ❌ Real-time aktualizace po změně licence
- ❌ Animace při otevírání/zavírání dropdownu

## 📁 Změněné soubory

1. **web/index.html**
   - Přidána HTML struktura license menu (řádek ~2393)
   - Skryt původní license badge (řádek ~2596)
   - Upravena funkce `loadLicenseStatus()` (řádek ~4202)
   - Přidána funkce `renderLicenseMenu()` (nová)
   - Přidána funkce `toggleLicenseDropdown()` (nová)
   - Přidána funkce `initLicenseDropdownHandlers()` (nová)
   - Upravena funkce `handleLogout()` (řádek ~4048)
   - Upravena funkce `showDashboard()` (řádek ~4228)

2. **web/theme.css**
   - Přidány CSS styly pro license menu (~100 řádků)

## 🧪 Testování

**Očekávané chování:**
1. Po přihlášení se v TopBar zobrazí badge "Licence: načítání…"
2. Po načtení se zobrazí "Licence: FREE/BASIC/PREMIUM"
3. Kliknutí na badge otevře dropdown s detaily
4. Aktivní plán má tlačítko "Aktivní" (disabled)
5. Ostatní plány mají tlačítko "Upgradovat" (aktivní)
6. Kliknutí mimo dropdown ho zavře
7. Při odhlášení se menu skryje
