# Oprava License Dropdown - Modernizace designu

## Problém
Dropdown měl špatnou strukturu - všechny texty se zobrazovaly v jednom elementu místo správné strukturované bubliny.

## Opravy

### 1. HTML struktura
- ✅ Změněno `<span id="licenseMenu">` na `<div id="licenseMenu">` - správné vnoření blokových elementů
- ✅ Dropdown je správně vnořený jako `<div id="licenseDropdown">` uvnitř menu

### 2. CSS vylepšení

**Moderní efekty:**
- Glassmorphism (backdrop-filter: blur)
- Gradient pozadí
- Moderní stíny (vícenásobné box-shadow)
- Animace při otevírání (fadeIn + scale)
- Hover efekty s transformací

**Vizuální prvky:**
- Ikony u názvů plánů (🔹 Free, 💎 Basic, ⭐ Premium)
- Barevné levé okraje při hoveru
- Gradient tlačítka
- Lepší spacing a padding

### 3. JavaScript opravy
- ✅ Event handling pro toggle dropdown
- ✅ Zavření při kliknutí mimo
- ✅ Stop propagation pro správné chování

## Změněné soubory

1. **web/index.html**
   - Změněn `<span>` na `<div>` pro licenseMenu (řádek 2394)

2. **web/theme.css**
   - Vylepšené CSS styly pro moderní dropdown
   - Glassmorphism efekt
   - Animace a transitions
   - Lepší vizuální hierarchie

## Výsledek

Dropdown by nyní měl:
- ✅ Být správně skrytý když má class "hidden"
- ✅ Zobrazovat se jako moderní bublina při kliknutí
- ✅ Mít plynulé animace
- ✅ Být responzivní
- ✅ Mít moderní vzhled s glassmorphism efektem
