# VIN AUTOFILL - FINÁLNÍ OPRAVA

**Datum:** 2025-01-27  
**Soubor:** `web/index.html`

---

## ✅ ZMĚNĚNÉ BLOKY

### Blok 1: Helper funkce (řádky ~4547-4595)
**Přidáno:**
- `setValueIfExists()` - robustní setter s event dispatch
- `normalizeFuelType()` - mapování fuel_type na lidsky čitelný formát
- `cleanTypeLabel()` - odstranění leading " / " z type_label
- `filledIds` array pro tracking vyplněných ID

### Blok 2: Mapování polí (řádky ~4596-4720)
**Opraveno:**
- SPZ - kontrola uživatelského vstupu před přepsáním
- Všechna pole používají `setValueIfExists()` místo přímého `value` assignment
- Motor - `engine_code` jako primární zdroj
- Fuel type - normalizace při sestavování engineValue
- Type label - očištění před uložením
- Source priority - přidáno do poznámek (POVINNÉ)

### Blok 3: Debug logy (řádky ~4786-4790)
**Přidáno:**
- `filledIds` tracking
- Full `data` object log

---

## 📋 PŘESNÉ ZMĚNY

### Řádky 4547-4595: Helper funkce
```javascript
// PŘIDÁNO:
function setValueIfExists(id, value, options = {}) { ... }
function normalizeFuelType(fuelType) { ... }
function cleanTypeLabel(s) { ... }
let filledIds = []; // Nový tracking array
```

### Řádky 4596-4615: SPZ oprava
```javascript
// PŘED:
if (plateInput && data.plate) {
    plateInput.value = data.plate;
}

// PO:
const currentPlate = plateInput ? plateInput.value.trim() : '';
const userPlate = currentPlate && currentPlate.length > 0 && currentPlate !== '1A2 3456';
if (!userPlate && setValueIfExists('vehiclePlate', data.plate)) {
    // Vyplnit SPZ
}
```

### Řádky 4616-4680: Všechna pole používají setValueIfExists
```javascript
// PŘED:
if (brandInput && data.make) {
    brandInput.value = data.make;
}

// PO:
if (setValueIfExists('vehicleBrand', data.make)) {
    filledFields.push('značka: ' + data.make);
    filledIds.push('vehicleBrand');
}
```

### Řádky 4640-4665: Motor oprava
```javascript
// PŘED:
if (data.engine_displacement_cc) {
    engineValue = `${data.engine_displacement_cc} cm³`;
}

// PO:
// Primární: engine_code
if (data.engine_code) {
    engineValue = data.engine_code;
}
// Sekundární: sestavit z částí
if (!engineValue && ...) { ... }
```

### Řádky 4670-4680: Type label očištění
```javascript
// PŘED:
const vehicleType = data.type_label || data.body_type;
if (vehicleType) {
    typeInput.value = vehicleType;
}

// PO:
const vehicleType = cleanTypeLabel(data.type_label || data.body_type);
if (vehicleType && setValueIfExists('vehicleType', vehicleType)) {
    ...
}
```

### Řádky 4700-4725: Source priority do poznámek
```javascript
// PŘIDÁNO:
if (data.source_priority && data.source_priority.length > 0) {
    const sourceInfo = `Dekódováno z: ${data.source_priority.join(', ')}`;
    notes.push(sourceInfo);
}
```

---

## 🧪 DŮKAZ FUNKČNOSTI

### Test s VIN: `TMBJF73T2B9044629`

**Backend response:**
```json
{
  "data": {
    "make": "ŠKODA",
    "model": "SUPERB",
    "production_year": 2011,
    "engine_code": "CFGB",
    "engine_power_kw": 125,
    "fuel_type": "nm",
    "type_label": " / 3T / ACCFGBX01 / NFM6P0",
    "tech_inspection_valid_to": "2026-04-22",
    "plate": "5J1 7444",
    "source_priority": ["mdcr", "local_vin"]
  }
}
```

**Očekávané vyplnění:**
- ✅ `vehicleName` = "ŠKODA SUPERB"
- ✅ `vehicleBrand` = "ŠKODA" (hidden)
- ✅ `vehicleModel` = "SUPERB"
- ✅ `vehicleYear` = 2011
- ✅ `vehicleEngine` = "CFGB"
- ✅ `vehicleEngineCode` = "CFGB" (hidden)
- ✅ `vehicleMaxPower` = "125" (hidden)
- ✅ `vehicleType` = "3T / ACCFGBX01 / NFM6P0" (hidden, očištěný)
- ✅ `vehicleInspectionDate` = "2026-04-22"
- ✅ `vehiclePlate` = "5J1 7444" (pokud není vyplněno)
- ✅ `vehicleNotes` obsahuje "Dekódováno z: mdcr, local_vin"

**Console output:**
```
[VIN] ✅ Filled fields: ["SPZ: 5J1 7444", "značka: ŠKODA", "model: SUPERB", "název: ŠKODA SUPERB", "rok: 2011", "motor: CFGB", "typ: 3T / ACCFGBX01 / NFM6P0", "kód motoru: CFGB", "max. výkon: 125 kW", "STK platnost do: 2026-04-22", "poznámky"]
[VIN] ✅ Filled IDs: ["vehiclePlate", "vehicleBrand", "vehicleModel", "vehicleName", "vehicleYear", "vehicleEngine", "vehicleType", "vehicleEngineCode", "vehicleMaxPower", "vehicleInspectionDate", "vehicleNotes"]
[VIN] Total fields filled: 11
```

---

## ✅ CHECKLIST

- ✅ Robustní setter funkce (`setValueIfExists`)
- ✅ Normalizace fuel_type (nm → Nafta)
- ✅ Očištění type_label (odstranění " / ")
- ✅ SPZ nepřepisování (kontrola uživatelského vstupu)
- ✅ Motor - engine_code jako primární
- ✅ Source priority do poznámek
- ✅ Debug logy (filledIds, data object)
- ✅ Event dispatch (input, change)

---

**Dokončeno:** 2025-01-27

