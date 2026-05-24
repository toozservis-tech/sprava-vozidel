# LICENSE UI - NEPRŮSTŘELNÝ DEBUG

**Datum:** 2025-01-27  
**Soubor:** `web/index.html`

---

## ✅ ZMĚNĚNÉ BLOKY

### 1. HTML - License Badge (řádky ~2560-2563)
**LICENSE_UI_START / LICENSE_UI_END**

```html
<div id="licenseBadge" style="... display: block;">
    Licence: LOADING…
</div>
```

**Důležité:**
- ✅ `display: block` - VŽDY VIDITELNÝ
- ✅ Default text: "Licence: LOADING…"
- ✅ Umístění: Před tabs v dashboardu

### 2. HTML - Debug Panel (řádky ~2566-2569)
**LICENSE_UI_START / LICENSE_UI_END**

```html
<div id="licenseDebugPanel" style="... display: block;">
    <strong>License Debug:</strong> Initializing...
</div>
```

**Důležité:**
- ✅ `display: block` - VŽDY VIDITELNÝ pro debug
- ✅ Zobrazuje: last call, status, error, response

### 3. JavaScript - loadLicenseStatus() (řádky ~4197-4249)
**LICENSE_UI_START / LICENSE_UI_END**

**Klíčové změny:**
- ✅ Robustní error handling
- ✅ Handle wrapped response (`res.data ? res.data : res`)
- ✅ Detailní console logy
- ✅ Debug state: `window.__licenseDebug`
- ✅ Vždy zobrazí badge (i při chybě)

**Console logy:**
```
[LICENSE] ========================================
[LICENSE] fetching /api/v1/license/status
[LICENSE] API URL: https://hub.toozservis.cz
[LICENSE] Full URL will be: https://hub.toozservis.cz/api/v1/license/status
[LICENSE] Access token: present
[LICENSE] Token preview: eyJhbGciOiJIUzI1NiI...
[LICENSE] response: {...}
[LICENSE] response type: object
[LICENSE] response keys: ["tenant_id", "plan", ...]
```

### 4. JavaScript - updateLicenseDebugPanel() (řádky ~4320-4340)
**LICENSE_UI_START / LICENSE_UI_END**

- Aktualizuje debug panel s:
  - Last call timestamp
  - Status (success/error/unknown)
  - Error message (pokud je)
  - Response preview

### 5. Volání loadLicenseStatus() - 2 MÍSTA

**A) Po loginu (řádky ~3515-3518):**
```javascript
// LICENSE_UI_START: Načíst licenci po loginu (1. místo)
if (typeof loadLicenseStatus === 'function') {
    await loadLicenseStatus();
}
```

**B) V showDashboard() (řádky ~4190-4194):**
```javascript
// LICENSE_UI_START: Načíst licenční informace (2. místo - po vykreslení dashboard HTML)
setTimeout(() => {
    if (typeof loadLicenseStatus === 'function') {
        loadLicenseStatus();
    }
}, 200);
```

---

## 🧪 TESTOVÁNÍ

### Test 1: Badge je vždy viditelný
1. Otevřít dashboard (i bez přihlášení)
2. Ověřit, že badge je zobrazený s textem "Licence: LOADING…"

**Očekávaný výsledek:**
- ✅ Badge je viditelný (display: block)
- ✅ Text: "Licence: LOADING…"

### Test 2: Po loginu se načte licence
1. Přihlásit se
2. Otevřít Developer Console (F12)
3. Sledovat logy

**Očekávané logy:**
```
[LICENSE] ========================================
[LICENSE] fetching /api/v1/license/status
[LICENSE] API URL: https://hub.toozservis.cz
[LICENSE] Full URL will be: https://hub.toozservis.cz/api/v1/license/status
[LICENSE] Access token: present
[LICENSE] Token preview: eyJhbGciOiJIUzI1NiI...
[LICENSE] response: {tenant_id: "1", plan: "free", ...}
[LICENSE] response type: object
[LICENSE] response keys: ["tenant_id", "plan", "status", ...]
```

**Očekávaný badge:**
- Text: "Licence: FREE (active) • Vozidla: 1/1 • Zbývá: 0"

### Test 3: Chyba se zobrazí
1. Odstranit JWT token (nebo použít neplatný)
2. Přihlásit se
3. Ověřit badge a console

**Očekávaný výsledek:**
- Badge: "Licence: ERROR (viz Console)" (červeně)
- Console: `[LICENSE] failed: ...`
- Debug panel: Status: error, Error: ...

### Test 4: Debug panel
1. Přihlásit se
2. Ověřit debug panel

**Očekávaný výsledek:**
- Debug panel zobrazený
- Obsahuje: Last call, Status, Response preview

---

## 📋 PŘESNÉ ZMĚNY

### Blok 1: HTML badge (řádky ~2560-2563)
- ✅ `display: block` (ne `none`)
- ✅ Default text: "Licence: LOADING…"

### Blok 2: HTML debug panel (řádky ~2566-2569)
- ✅ `display: block` (pro debug)
- ✅ Zobrazuje debug info

### Blok 3: loadLicenseStatus() (řádky ~4197-4249)
- ✅ Robustní error handling
- ✅ Handle wrapped response
- ✅ Detailní console logy
- ✅ Debug state tracking

### Blok 4: Volání po loginu (řádky ~3515-3518)
- ✅ `await loadLicenseStatus()` po úspěšném loginu

### Blok 5: Volání v showDashboard() (řádky ~4190-4194)
- ✅ `setTimeout(loadLicenseStatus, 200)` po vykreslení HTML

### Blok 6: updateLicenseDebugPanel() (řádky ~4320-4340)
- ✅ Aktualizuje debug panel s informacemi

---

## ✅ DŮKAZ FUNKČNOSTI

Po implementaci:
1. ✅ Badge je VŽDY viditelný (i při chybě)
2. ✅ Po loginu se zavolá loadLicenseStatus()
3. ✅ V showDashboard() se zavolá loadLicenseStatus() (setTimeout)
4. ✅ Console obsahuje detailní logy
5. ✅ Debug panel zobrazuje debug info
6. ✅ Chyby se zobrazí v badge i console

---

**Dokončeno:** 2025-01-27

