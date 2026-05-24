# CSS Oprava pro License Dropdown

## Problém
Dropdown se zobrazoval špatně - všechny texty v jednom elementu, špatná struktura.

## Opravy v CSS

### 1. Dropdown default state
```css
.license-dropdown {
  display: none; /* Výchozí stav - skrytý */
}

.license-dropdown:not(.hidden) {
  display: block; /* Zobrazit pouze když NEMÁ class "hidden" */
}
```

### 2. License menu text
```css
.license-menu > #licenseMenuText {
  display: inline-block;
  white-space: nowrap;
  flex-shrink: 0;
}
```

### 3. Vylepšené rozměry
- `min-width: 320px`
- `max-width: calc(100vw - 40px)` (responzivní)
- `box-sizing: border-box`

## Změněné soubory
- `web/theme.css` - řádky ~330-363
