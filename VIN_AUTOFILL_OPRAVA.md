# OPRAVA VIN AUTOFILL - SHRNUTÍ

**Datum:** 2025-01-27  
**Soubor:** `web/index.html`

---

## ✅ OPRAVENÉ PROBLÉMY

### 1. Robustní setter funkce
**Přidáno:**
```javascript
function setValueIfExists(id, value, options = {}) {
    const el = document.getElementById(id);
    if (!el) return false;
    if (value === null || value === undefined || value === "") return false;
    el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
}
```

**Výhody:**
- ✅ Automaticky dispatchuje `input` a `change` eventy
- ✅ Kontroluje existenci elementu
- ✅ Kontroluje prázdné hodnoty
- ✅ Vrací boolean pro tracking

---

### 2. Normalizace fuel_type
**Přidáno:**
```javascript
function normalizeFuelType(fuelType) {
    const fuelMap = {
        'nm': 'Nafta',
        'bm': 'Benzín',
        'el': 'Elektro',
        'hy': 'Hybrid',
        'lpg': 'LPG',
        'cng': 'CNG'
    };
    return fuelMap[fuelType.toLowerCase()] || fuelType;
}
```

**Použití:** Při sestavování engineValue se fuel_type normalizuje na lidsky čitelný formát.

---

### 3. Očištění type_label
**Přidáno:**
```javascript
function cleanTypeLabel(s) {
    if (!s) return s;
    return s.replace(/^\s*\/\s*/, "").trim();
}
```

**Použití:** Odstraní leading " / " z type_label před uložením do `vehicleType`.

---

### 4. SPZ - Nepřepisovat pokud uživatel vyplnil
**Opraveno:**
```javascript
const currentPlate = plateInput ? plateInput.value.trim() : '';
const userPlate = currentPlate && currentPlate.length > 0 && currentPlate !== '1A2 3456';
if (!userPlate && setValueIfExists('vehiclePlate', data.plate)) {
    // Vyplnit SPZ
}
```

**Logika:** SPZ se vyplní pouze pokud:
- Pole je prázdné NEBO
- Obsahuje placeholder "1A2 3456"

---

### 5. Motor - engine_code jako primární
**Opraveno:**
```javascript
// Primární: engine_code
if (data.engine_code) {
    engineValue = data.engine_code;
}
// Sekundární: sestavit z displacement, power, fuel
if (!engineValue && (data.engine_displacement_cc || data.engine_power_kw || data.fuel_type)) {
    // Sestavit z částí
}
```

**Priorita:**
1. `engine_code` (pokud existuje)
2. Sestavení z `engine_displacement_cc`, `engine_power_kw`, `fuel_type` (normalizovaný)

---

### 6. Vylepšené debug logy
**Přidáno:**
```javascript
console.log('[VIN] ✅ Filled fields:', filledFields);
console.log('[VIN] ✅ Filled IDs:', filledIds);
console.log('[VIN] Total fields filled:', filledFields.length);
console.log('[VIN] Data object:', data);
```

**Výhody:**
- ✅ Tracking vyplněných polí
- ✅ Tracking ID elementů
- ✅ Full data object pro debugging

---

## 📋 MAPOVÁNÍ POLÍ

| Backend Field | Frontend ID | Typ | Poznámka |
|---------------|-------------|-----|----------|
| `make` | `vehicleBrand` | hidden | Značka |
| `model` | `vehicleModel` | input | Model |
| `type_label` | `vehicleType` | hidden | Typ (očištěný) |
| `production_year` | `vehicleYear` | number | Rok |
| `engine_code` | `vehicleEngine` | input | Motor (primární) |
| `engine_code` | `vehicleEngineCode` | hidden | Kód motoru |
| `engine_power_kw` | `vehicleMaxPower` | hidden | Max. výkon |
| `fuel_type` | - | - | Normalizován v engine |
| `tech_inspection_valid_to` | `vehicleInspectionDate` | input | STK do |
| `plate` | `vehiclePlate` | input | SPZ (nepřepisovat) |
| `make + model` | `vehicleName` | input | Název vozidla |
| `source_priority` | `vehicleNotes` | textarea | Přidáno do poznámek |

---

## 🔧 ZMĚNĚNÉ ŘÁDKY

### Blok 1: Přidání helper funkcí (řádky ~4547-4575)
- ✅ `setValueIfExists()` - robustní setter
- ✅ `normalizeFuelType()` - normalizace paliva
- ✅ `cleanTypeLabel()` - očištění type_label

### Blok 2: Oprava mapování polí (řádky ~4576-4680)
- ✅ SPZ - kontrola uživatelského vstupu
- ✅ Značka - použití setValueIfExists
- ✅ Model - použití setValueIfExists
- ✅ Název - sestavení z make + model
- ✅ Rok - production_year jako primární
- ✅ Motor - engine_code jako primární
- ✅ Typ - očištění type_label
- ✅ Kód motoru - engine_code
- ✅ Max. výkon - engine_power_kw

### Blok 3: STK a poznámky (řádky ~4681-4725)
- ✅ STK - tech_inspection_valid_to
- ✅ Poznámky - sestavení z dalších údajů
- ✅ Source info - přidání do poznámek (POVINNÉ)

### Blok 4: Debug logy (řádky ~4726-4730)
- ✅ Filled fields tracking
- ✅ Filled IDs tracking
- ✅ Data object log

---

## 🧪 TESTOVÁNÍ

### Test 1: Základní VIN decode
1. Otevřít UI: `https://hub.toozservis.cz/web/index.html`
2. Přihlásit se
3. Jít na "Přidat vozidlo"
4. Zadat VIN: `TMBJF73T2B9044629`
5. Otevřít Developer Console (F12)

**Očekávaný výsledek:**
```
[VIN] ✅ Filled fields: ["SPZ: 5J1 7444", "značka: ŠKODA", "model: SUPERB", ...]
[VIN] ✅ Filled IDs: ["vehiclePlate", "vehicleBrand", "vehicleModel", ...]
[VIN] Total fields filled: 8+
```

**Ověřit vyplnění:**
- ✅ `vehicleName` = "ŠKODA SUPERB"
- ✅ `vehicleModel` = "SUPERB"
- ✅ `vehicleYear` = 2011
- ✅ `vehicleEngine` = "CFGB"
- ✅ `vehicleInspectionDate` = "2026-04-22"
- ✅ `vehiclePlate` = "5J1 7444"
- ✅ `vehicleNotes` obsahuje "Dekódováno z: mdcr, local_vin"

### Test 2: SPZ nepřepisování
1. Vyplnit SPZ ručně: "ABC 1234"
2. Zadat VIN: `TMBJF73T2B9044629`
3. Ověřit, že SPZ zůstala "ABC 1234"

**Očekávaný výsledek:**
```
[VIN] Plate NOT overwritten (user has value): ABC 1234
```

### Test 3: Fuel type normalizace
1. Zadat VIN s fuel_type="nm"
2. Ověřit, že v engineValue je "Nafta" místo "nm"

**Očekávaný výsledek:**
- `vehicleEngine` obsahuje "Nafta" (ne "nm")

### Test 4: Type label očištění
1. Zadat VIN s type_label=" / 3T / ACCFGBX01 / NFM6P0"
2. Ověřit, že vehicleType obsahuje "3T / ACCFGBX01 / NFM6P0" (bez leading " / ")

**Očekávaný výsledek:**
- `vehicleType` = "3T / ACCFGBX01 / NFM6P0"

---

## ✅ DŮKAZ FUNKČNOSTI

Po zadání VIN `TMBJF73T2B9044629` se musí vyplnit minimálně:
- ✅ `make` → `vehicleBrand` (hidden)
- ✅ `model` → `vehicleModel`
- ✅ `production_year` → `vehicleYear`
- ✅ `engine_code` → `vehicleEngine` + `vehicleEngineCode`
- ✅ `engine_power_kw` → `vehicleMaxPower` (hidden)
- ✅ `tech_inspection_valid_to` → `vehicleInspectionDate`
- ✅ `plate` → `vehiclePlate` (pokud není vyplněno)
- ✅ `source_priority` → přidáno do `vehicleNotes`

---

**Dokončeno:** 2025-01-27

