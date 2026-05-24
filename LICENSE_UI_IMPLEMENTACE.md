# LICENSE UI - IMPLEMENTACE

**Datum:** 2025-01-27  
**Soubor:** `web/index.html`

---

## ✅ ZMĚNĚNÉ BLOKY

### 1. HTML - License Badge (řádky ~2559-2575)
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

### 2. JavaScript - Načtení licence (řádky ~4157-4158)
**V `showDashboard()`:**
```javascript
// LICENSE_UI_START: Načíst licenční informace
loadLicenseStatus();
```

### 3. JavaScript - loadLicenseStatus() (řádky ~4160-4180)
**LICENSE_UI_START / LICENSE_UI_END**

```javascript
async function loadLicenseStatus() {
    const licenseData = await apiCall('/api/v1/license/status', 'GET');
    window.appState.license = licenseData;
    renderLicenseBadge(licenseData);
}
```

### 4. JavaScript - renderLicenseBadge() (řádky ~4182-4240)
**LICENSE_UI_START / LICENSE_UI_END**

- Barvy podle plánu (free=šedá, basic=modrá, premium=zlatá)
- Zobrazení: "Licence: FREE (active) • Vozidla: 1/1 • Zbývá: 0"
- Upgrade button (zobrazit pokud není premium)

### 5. JavaScript - showLicenseQuotaBanner() (řádky ~4242-4275)
**LICENSE_UI_START / LICENSE_UI_END**

- Zobrazí banner/toast při překročení limitu
- Fallback banner pokud showAlert není dostupný

### 6. JavaScript - showUpgradeModal() (řádky ~4277-4285)
**LICENSE_UI_START / LICENSE_UI_END**

- Placeholder modal s textem "Kontaktujte TooZServis pro změnu licence."

### 7. JavaScript - Error handling v apiCall() (řádky ~3273-3284)
**LICENSE_UI_START**

- Detekce `error.error.code === "LICENSE_QUOTA_EXCEEDED"`
- Zobrazení banneru
- Refresh license status

---

## 📋 MAPOVÁNÍ

### Backend response → UI:
```json
{
  "tenant_id": "1",
  "plan": "free",
  "status": "active",
  "vehicles_limit": 1,
  "vehicles_current": 1,
  "vehicles_remaining": 0,
  "is_unlimited": false
}
```

### UI zobrazení:
- **Plan:** `Licence: FREE (active)`
- **Vehicles:** `Vozidla: 1/1` nebo `Vozidla: 5/∞` (premium)
- **Remaining:** `• Zbývá: 0` nebo `• Limit dosažen` (červeně)

---

## 🎨 BARVY

| Plán | Background | Border | Text |
|------|-----------|--------|------|
| `free` | `#f1f5f9` (šedá) | `#e2e8f0` | `#64748b` |
| `basic` | `#eff6ff` (modrá) | `#bfdbfe` | `#1e40af` |
| `premium` | `#fef3c7` (zlatá) | `#fde68a` | `#92400e` |

---

## 🧪 TESTOVÁNÍ

### Test 1: Zobrazení licence po loginu
1. Přihlásit se
2. Otevřít Developer Console (F12)
3. Sledovat logy: `[LICENSE] Loading license status...`
4. Ověřit, že badge je zobrazený

**Očekávaný výsledek:**
- Badge zobrazený s textem: "Licence: FREE (active) • Vozidla: 1/1 • Zbývá: 0"
- Barva: šedá (free)

### Test 2: Premium licence
**Nastavit v DB:**
```sql
UPDATE licenses SET plan='premium', vehicles_limit=0 WHERE tenant_id=1;
```

**Očekávaný výsledek:**
- Badge: "Licence: PREMIUM (active) • Vozidla: 5/∞"
- Barva: zlatá
- Upgrade button: skrytý

### Test 3: Quota exceeded banner
1. Free tenant s 1 vozidlem
2. Pokusit přidat 2. vozidlo
3. Ověřit, že se zobrazí banner

**Očekávaný výsledek:**
- Banner: "Limit vozidel překročen (1/1). Zvažte upgrade licence."
- License status se refreshne

### Test 4: Upgrade button
1. Free nebo basic tenant
2. Ověřit, že upgrade button je zobrazený
3. Kliknout na "Upgradovat"
4. Ověřit, že se zobrazí alert/modal

**Očekávaný výsledek:**
- Alert: "Kontaktujte TooZServis pro změnu licence."

---

## ✅ CHECKLIST

- ✅ License badge HTML přidán
- ✅ `loadLicenseStatus()` volá se po loginu
- ✅ `renderLicenseBadge()` vykresluje badge
- ✅ Barvy podle plánu
- ✅ Quota exceeded banner handling
- ✅ Upgrade button (placeholder)
- ✅ Error handling v apiCall()
- ✅ Globální stav: `window.appState.license`

---

## 📝 PŘESNÉ ZMĚNY

### Blok 1: HTML badge (řádky ~2559-2575)
- Přidán `<div id="licenseBadge">` před tabs

### Blok 2: showDashboard() (řádky ~4157-4158)
- Přidáno: `loadLicenseStatus();`

### Blok 3: loadLicenseStatus() (řádky ~4160-4180)
- Nová funkce pro načtení licence

### Blok 4: renderLicenseBadge() (řádky ~4182-4240)
- Nová funkce pro vykreslení badge

### Blok 5: showLicenseQuotaBanner() (řádky ~4242-4275)
- Nová funkce pro zobrazení banneru

### Blok 6: showUpgradeModal() (řádky ~4277-4285)
- Nová funkce pro upgrade modal

### Blok 7: apiCall() error handling (řádky ~3273-3284)
- Přidána detekce LICENSE_QUOTA_EXCEEDED

---

**Dokončeno:** 2025-01-27

