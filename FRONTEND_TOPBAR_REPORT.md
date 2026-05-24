# Frontend TopBar / Header - Analýza a umístění

## 1. Přesné cesty k souborům

### Hlavní soubor frontendu:
**`/opt/toozhub2/app/web/index.html`**

**Typ:** Vanilla JavaScript (jeden velký HTML soubor s inline CSS a JS)
**Formát:** HTML5 s inline styles a scripts

---

## 2. Komponenty a jejich názvy

**Není to React/TypeScript** - jedná se o vanilla HTML/JS aplikaci.

**Hlavní komponenty:**
- **Navbar komponenta:** `<nav id="mainNavbar">` (řádky 2380-2399)
- **Žádné TSX/JSX soubory** - vše je v jednom HTML souboru

---

## 3. Relevantní část kódu - TopBar/Navbar render

### Umístění: Řádky **2379-2399**

```html
<!-- Navbar (pouze když je uživatel přihlášen) -->
<nav class="navbar hidden" id="mainNavbar">
    <div class="navbar-brand">
        <span class="logo">🚗</span>
        <span class="brand-text">Správa vozidel <span id="navbarVersion">v2.2.0</span></span>
    </div>
    <div class="navbar-stats">
        <span id="userBadge" class="stat-badge hidden">
            <strong>Přihlášen jako:</strong> <span id="userEmail"></span>
        </span>
        <span id="serverStatus" class="stat-badge">
            <div id="statusIndicator"></div>
            <span id="statusText">Kontroluji server...</span>
        </span>
    </div>
    <div class="navbar-actions">
        <button id="configButton" class="config-button hidden" onclick="showApiUrlConfig()" title="Nastavit API URL (pouze pro admina)">⚙️</button>
        <button id="debugButton" class="config-button hidden" onclick="toggleDebugPanel()" title="Debug panel">🧪</button>
        <button id="logout-btn" class="btn-logout hidden" onclick="handleLogout()" data-testid="btn-logout">Odhlásit se</button>
    </div>
</nav>
```

### Struktura:

1. **`.navbar-brand`** - Logo a název aplikace
2. **`.navbar-stats`** - Statistické informace:
   - `#userBadge` - "Přihlášen jako: {email}"
   - `#serverStatus` - "Server online" s indikátorem
3. **`.navbar-actions`** - Tlačítka akcí:
   - `#configButton` - Nastavení API URL
   - `#debugButton` - Debug panel
   - `#logout-btn` - Odhlásit se

---

## 4. CSS styly pro navbar-stats

### Umístění: Řádky **1817-1828** (a **2084-2095** pro mobile)

```css
.navbar-stats {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}

.stat-badge {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    font-size: 13px;
    color: #fff;
    white-space: nowrap;
}

#statusIndicator {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #ff6b6b;
    display: inline-block;
}

.status-online {
    background: #51cf66 !important;
}

.status-offline {
    background: #ff6b6b !important;
}

.status-checking {
    background: #ffd43b !important;
    animation: pulse 1.5s ease-in-out infinite;
}
```

---

## 5. Navrhované umístění pro `<LicenseMenu/>`

### **Doporučené místo: V `.navbar-stats` za `#serverStatus`**

**Řádky 2389-2392** - přidat hned po `#serverStatus`:

```html
<div class="navbar-stats">
    <span id="userBadge" class="stat-badge hidden">
        <strong>Přihlášen jako:</strong> <span id="userEmail"></span>
    </span>
    <span id="serverStatus" class="stat-badge">
        <div id="statusIndicator"></div>
        <span id="statusText">Kontroluji server...</span>
    </span>
    <!-- LICENSE_MENU_START: License menu komponenta -->
    <span id="licenseMenu" class="stat-badge license-menu">
        <!-- Obsah bude dynamicky naplněn JavaScriptem -->
        <span id="licenseMenuText">Licence: Načítání...</span>
    </span>
    <!-- LICENSE_MENU_END -->
</div>
```

### Alternativní umístění (před "Server online"):

```html
<div class="navbar-stats">
    <span id="userBadge" class="stat-badge hidden">
        <strong>Přihlášen jako:</strong> <span id="userEmail"></span>
    </span>
    <!-- LICENSE_MENU_START: License menu komponenta -->
    <span id="licenseMenu" class="stat-badge license-menu">
        <span id="licenseMenuText">Licence: Načítání...</span>
    </span>
    <!-- LICENSE_MENU_END -->
    <span id="serverStatus" class="stat-badge">
        <div id="statusIndicator"></div>
        <span id="statusText">Kontroluji server...</span>
    </span>
</div>
```

**Doporučení:** První varianta (za "Server online") - logičtější pořadí:
1. Přihlášen jako
2. Server online
3. Licence (nové)

---

## 6. Současné umístění license badge

**Aktuálně** je license badge vykreslovaný **uvnitř dashboardu** (ne v navbaru):

- **Řádky 2560-2564:** HTML struktura `#licenseBadge`
- **Řádky 4202-4404:** JavaScript funkce pro načítání a vykreslování licence
- **Funkce:** `loadLicenseStatus()`, `renderLicenseBadge(license)`

**Poznámka:** Pokud chcete mít license menu v navbaru, budete muset:
1. Přesunout HTML do `.navbar-stats`
2. Upravit JavaScript funkce pro renderování do navbaru místo dashboardu

---

## 7. Routing systém

**Neexistuje tradiční routing systém** - jedná se o Single Page Application (SPA) s manuálním přepínáním zobrazení pomocí funkcí:

### Hlavní funkce pro zobrazení:
- **`showDashboard()`** - řádky 4142-4198
  - Zobrazuje `#dashboard`
  - Zobrazuje `#mainNavbar`
  - Volá `loadLicenseStatus()` po načtení

- **`showLogin()`** - řádky ~4200+
  - Skrývá dashboard a navbar
  - Zobrazuje login formulář

### Struktura HTML:
```html
<div class="container">
    <nav id="mainNavbar" class="navbar hidden">...</nav>
    <div class="content">
        <div id="authSection">...</div>
        <div id="dashboard">...</div>
    </div>
</div>
```

**Navbar je zobrazen pouze když:**
- Uživatel je přihlášen (`isAuthenticated() === true`)
- Je volána `showDashboard()`
- `navbar.classList.remove('hidden')`

---

## 8. JavaScript funkce pro Server Status

### Umístění: Řádky **2975-3047**

```javascript
async function checkServerStatus() {
    const indicator = document.getElementById('statusIndicator');
    const statusText = document.getElementById('statusText');
    
    // ... kontrola serveru přes /health endpoint
    // ... aktualizace tříd a textu
}
```

**Volá se:**
- Při startu: `checkServerStatus()`
- Každých 30 sekund: `setInterval(checkServerStatus, 30000)`

---

## 9. CSS styly - detailní definice

### Hlavní CSS soubory:
- **`web/theme.css`** - řádky 278-307 (hlavní definice)
- **`web/index.html`** - řádky 1817-1828 (tablet responsive)
- **`web/index.html`** - řádky 2084-2088 (mobile responsive)

### Definicie z `theme.css` (řádky 278-307):

```css
.navbar-stats {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}

.stat-badge {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    font-size: 13px;
    color: #fff;
    white-space: nowrap;
}

.stat-badge strong {
    font-weight: 600;
    margin-right: 4px;
}
```

### Status indikátor (`inline-styles.css` nebo inline):

```css
#statusIndicator {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #ff6b6b;
    display: inline-block;
}

.status-online {
    background: #51cf66 !important;
}

.status-offline {
    background: #ff6b6b !important;
}

.status-checking {
    background: #ffd43b !important;
    animation: pulse 1.5s ease-in-out infinite;
}
```

---

## 10. Shrnutí

### Pro přidání `<LicenseMenu/>` do navbaru:

#### Krok 1: HTML (řádek ~2392 v `web/index.html`)
Přidat za `#serverStatus` uvnitř `.navbar-stats`:

```html
<span id="licenseMenu" class="stat-badge license-menu">
    <span id="licenseMenuText">Licence: Načítání...</span>
</span>
```

#### Krok 2: CSS
Použít existující `.stat-badge` třídu - automaticky získá správný styling.

Pro custom styling přidat do `theme.css`:

```css
.license-menu {
    /* Volitelně: custom styling pro license menu */
    cursor: pointer; /* Pokud bude klikatelné */
}

.license-menu:hover {
    background: rgba(255, 255, 255, 0.15);
}
```

#### Krok 3: JavaScript
Upravit funkci `renderLicenseBadge()` (řádek 4299) aby:
- Renderovala do `#licenseMenu` místo `#licenseBadge`
- Nebo vytvořit novou funkci `renderLicenseMenu()` specificky pro navbar

Aktualizovat `loadLicenseStatus()` aby volala novou funkci renderování.

#### Krok 4: Volání
`loadLicenseStatus()` se už volá v `showDashboard()` (řádek 4194) - žádná další úprava není potřeba.

### Výhody umístění v navbaru:
- ✅ Vždy viditelné (ne skryté v dashboardu)
- ✅ Konzistentní s ostatními statistikami
- ✅ Logické uspořádání: User → Server → License
- ✅ Responzivní design (už podporován CSS)

### Poznámka o současném umístění:
License badge je momentálně **uvnitř dashboardu** (řádky 2560-2564). Po přesunu do navbaru můžete:
- **Možnost A:** Nechat oba (navbar + dashboard)
- **Možnost B:** Skrýt dashboard badge (`display: none`)

---

## 11. Routing systém - detail

**Neexistuje tradiční routing** - SPA s manuálním zobrazením:

### Hlavní funkce:
- **`showDashboard()`** - řádky 4142-4198
  - Zobrazuje navbar: `navbar.classList.remove('hidden')`
  - Načítá license: `loadLicenseStatus()`
  
- **`showLogin()`** - řádky ~4200+
  - Skrývá navbar: `navbar.classList.add('hidden')`

### Struktura:
```html
<div class="container">
    <nav id="mainNavbar" class="navbar hidden">  <!-- Skrytý při loginu -->
        <div class="navbar-stats">
            <!-- TADY PŘIDAT LICENSE MENU -->
        </div>
    </nav>
    <div class="content">
        <div id="authSection">...</div>
        <div id="dashboard">...</div>
    </div>
</div>
```

**Navbar je zobrazen pouze když:**
- `isAuthenticated() === true`
- Je volána `showDashboard()`
- CSS: `.hidden { display: none !important; }`

---

**Soubor pro editaci:** `/opt/toozhub2/app/web/index.html`

**Klíčové řádky:**
- **HTML navbar:** 2380-2399
- **HTML license badge (současné):** 2560-2564
- **CSS navbar-stats (theme.css):** 278-307
- **CSS responsive (index.html):** 1817-1828 (tablet), 2084-2088 (mobile)
- **JS checkServerStatus:** 2975-3047
- **JS loadLicenseStatus:** 4202-4271
- **JS renderLicenseBadge:** 4299-4360
- **JS showDashboard:** 4142-4198
