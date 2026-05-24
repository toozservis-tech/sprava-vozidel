# LICENSE UI - FINÁLNÍ IMPLEMENTACE

**Datum:** 2025-01-27  
**Soubor:** `web/index.html`

---

## ✅ ZMĚNĚNÉ BLOKY

### 1. HTML - License Badge (řádky ~2560-2573)
**LICENSE_UI_START / LICENSE_UI_END**

```html
<div id="licenseBadge" style="...">
    <div id="licenseInfo">
        <span id="licensePlan">Načítám...</span>
        <span id="licenseVehicles"></span>
        <span id="licenseRemaining"></span>
    </div>
    <button id="licenseUpgradeBtn" onclick="showUpgradeModal()">Upgradovat</button>
</div>
```

**Umístění:** Před `<div class="tabs">` v dashboardu

### 2. JavaScript - Načtení licence (řádky ~4190-4191)
**V `showDashboard()`:**
```javascript
// LICENSE_UI_START: Načíst licenční informace
loadLicenseStatus();
```

### 3. JavaScript - loadLicenseStatus() (řádky ~4196-4219)
**LICENSE_UI_START / LICENSE_UI_END**

- Volá `GET /api/v1/license/status`
- Ukládá do `window.appState.license`
- Volá `renderLicenseBadge()`

### 4. JavaScript - renderLicenseBadge() (řádky ~4221-4282)
**LICENSE_UI_START / LICENSE_UI_END**

- Barvy podle plánu (free=šedá, basic=modrá, premium=zlatá)
- Zobrazení: "Licence: FREE (active) • Vozidla: 1/1 • Zbývá: 0"
- Premium: "Vozidla: 5/∞"
- Upgrade button (zobrazit pokud není premium)

### 5. JavaScript - showLicenseQuotaBanner() (řádky ~4284-4317)
**LICENSE_UI_START / LICENSE_UI_END**

- Zobrazí banner/toast při překročení limitu
- Fallback banner pokud showAlert není dostupný
- Auto-remove po 10 sekundách

### 6. JavaScript - showUpgradeModal() (řádky ~4319-4327)
**LICENSE_UI_START / LICENSE_UI_END**

- Placeholder modal s textem "Kontaktujte TooZServis pro změnu licence."

### 7. JavaScript - Error handling v apiCall() (řádky ~3273-3284)
**LICENSE_UI_START**

- Detekce `error.error.code === "LICENSE_QUOTA_EXCEEDED"`
- Zobrazení banneru: `showLicenseQuotaBanner(error.error)`
- Refresh license status: `loadLicenseStatus()`

---

## 📋 PŘÍKLADY ZOBRAZENÍ

### Free licence (1/1):
```
Licence: FREE (active) • Vozidla: 1/1 • Limit dosažen
```
Barva: šedá (#f1f5f9)

### Basic licence (2/3):
```
Licence: BASIC (active) • Vozidla: 2/3 • Zbývá: 1
```
Barva: modrá (#eff6ff)

### Premium licence (5/∞):
```
Licence: PREMIUM (active) • Vozidla: 5/∞
```
Barva: zlatá (#fef3c7)

---

## 🧪 TESTOVÁNÍ

### Test 1: Zobrazení po loginu
1. Přihlásit se
2. Otevřít Developer Console (F12)
3. Sledovat logy: `[LICENSE] Loading license status...`
4. Ověřit badge

**Očekávaný výsledek:**
- Badge zobrazený
- Console: `[LICENSE] License data: {...}`
- `window.appState.license` obsahuje data

### Test 2: Quota exceeded banner
1. Free tenant s 1 vozidlem
2. Pokusit přidat 2. vozidlo
3. Ověřit banner

**Očekávaný výsledek:**
- Banner: "Limit vozidel překročen (1/1). Zvažte upgrade licence."
- License status se refreshne

### Test 3: Upgrade button
1. Free nebo basic tenant
2. Kliknout na "Upgradovat"
3. Ověřit alert

**Očekávaný výsledek:**
- Alert: "Kontaktujte TooZServis pro změnu licence."

---

## ✅ DŮKAZ FUNKČNOSTI

Po přihlášení:
1. ✅ Badge se zobrazí s informacemi o licenci
2. ✅ Barvy se mění podle plánu
3. ✅ Zobrazí se "Vozidla: current/limit" nebo "current/∞"
4. ✅ Zobrazí se "Zbývá: X" (pokud není unlimited)
5. ✅ Při překročení limitu se zobrazí banner
6. ✅ Upgrade button je zobrazený (pokud není premium)

---

**Dokončeno:** 2025-01-27

