# ANALÝZA: Odkud aplikace ví o SPZ "5J1 7444" pro VIN TMBJF73T2B9044629

**Datum:** 2025-01-27  
**Problém:** Response obsahuje `"plate":"5J1 7444"` a `"source_priority":["local_vin"]`

---

## 🔍 ZJIŠTĚNÍ

### 1. SPZ "5J1 7444" je HARDCODED v kódu

**Soubor:** `src/modules/vehicle_hub/decoder/router.py`  
**Řádek:** 163-164

```python
# Fallback SPZ pro VIN TMBJF73T2B9044629: 5J1 7444
fallback_plate = "5J1 7444" if vin == "TMBJF73T2B9044629" else None
```

**Co to znamená:**
- Tato SPZ je **natvrdo zakódovaná** v kódu jako fallback pro tento konkrétní VIN
- Použije se pouze pokud **žádný zdroj** (MDČR, EU, local_vin) nevrátí SPZ
- V merge_utils.py se přidá na konec, pokud `merged.plate` je `None`

---

### 2. MDČR API se NEVOLÁ

**Důkaz:** `"source_priority":["local_vin"]` obsahuje pouze `local_vin`, ne `mdcr`

**Možné příčiny:**
1. ❌ **ENV proměnná `DATAOVO_API_KEY` není nastavena**
   - Backend loguje: `[MDCR] API není nakonfigurováno - DATAOVO_API_KEY chybí v ENV`
   - MDČR API se přeskočí, použije se pouze local_vin

2. ❌ **MDČR API selhalo** (timeout, 4xx, 5xx)
   - Backend loguje: `[MDCR] ❌ Error calling MDČR API`
   - Použije se fallback na local_vin

---

## 📋 KDE SE SPZ NASTAVUJE

### Flow v kódu:

1. **MDČR API** (pokud je dostupné):
   - Volá se `fetch_vehicle_by_vin_from_mdcr(vin)`
   - Pokud API vrátí data s `plate`, použije se

2. **EU Open Data API** (pokud je dostupné):
   - Volá se `fetch_vehicle_by_vin_from_eu_open_data(vin)`
   - Pokud API vrátí data s `plate`, použije se

3. **Local VIN decoder**:
   - Volá se `decode_vin_local(vin)`
   - **Nevrací SPZ** (lokální dekodér nezná SPZ)

4. **Hardcoded fallback** (řádek 164):
   - Pokud `vin == "TMBJF73T2B9044629"`, nastaví se `fallback_plate = "5J1 7444"`
   - Použije se pouze pokud žádný zdroj nevrátil SPZ

5. **Merge** (merge_utils.py):
   - Pokud `merged.plate` je `None` a `fallback_plate` existuje, použije se fallback

---

## ✅ ŘEŠENÍ

### Problém 1: MDČR API se nevolá

**Kontrola:**
```bash
# Zkontrolovat, zda je ENV proměnná nastavena
echo $DATAOVO_API_KEY

# Nebo v systemd service
sudo systemctl show toozhub2 | grep Environment
```

**Oprava:**
```bash
# Nastavit ENV proměnnou v .env souboru
echo "DATAOVO_API_KEY=uNlYcvJan3ClsXzyf5Ezl3N5Bxz5C86k" >> /opt/toozhub2/app/.env

# Nebo v systemd service souboru
sudo systemctl edit toozhub2
# Přidat:
# [Service]
# Environment="DATAOVO_API_KEY=uNlYcvJan3ClsXzyf5Ezl3N5Bxz5C86k"

# Restartovat service
sudo systemctl restart toozhub2
```

### Problém 2: Hardcoded fallback SPZ

**Otázka:** Chcete tento hardcoded fallback odstranit?

**Možnosti:**
1. **Odstranit** - SPZ se bude získávat pouze z MDČR API
2. **Ponechat** - Jako fallback pro tento konkrétní VIN (testovací účely)
3. **Přesunout do databáze** - Vytvořit tabulku `vin_plate_fallback` s VIN → SPZ mapováním

---

## 🧪 TESTOVÁNÍ

### Test 1: Zkontrolovat logy
```bash
# Sledovat logy při volání VIN decode
sudo journalctl -u toozhub2 -f | grep -E "MDCR|DECODER|MERGE"
```

**Očekávané logy (pokud MDČR API funguje):**
```
[MDCR] API CALLED WITH VIN=TMBJF73T2B9044629
[MDCR] RESPONSE STATUS=200
[MDCR] DATA RECEIVED
[MERGE] Používám MDČR jako base
[DECODER] [VIN] ✅ 'mdcr' je na první pozici v source_priority
```

**Očekávané logy (pokud MDČR API nefunguje):**
```
[MDCR] API není nakonfigurováno - DATAOVO_API_KEY chybí v ENV
[MERGE] Používám local_vin jako base
```

### Test 2: Ověřit response
```bash
curl -X POST http://127.0.0.1:8000/api/vehicles/decode-vin \
  -H "Content-Type: application/json" \
  -d '{"vin": "TMBJF73T2B9044629"}' | jq '.data.source_priority'
```

**Očekávaný výsledk (pokud MDČR funguje):**
```json
["mdcr", "local_vin"]
```

**Současný výsledek:**
```json
["local_vin"]
```

---

## 📝 ZÁVĚR

1. ✅ **SPZ "5J1 7444" je hardcoded fallback** v `router.py` řádek 164
2. ❌ **MDČR API se nevolá** - chybí `DATAOVO_API_KEY` v ENV
3. ✅ **Lokální VIN dekodér funguje** - vrací základní data (make, country, plant)
4. ⚠️ **Fallback SPZ se použije** pouze pokud žádný zdroj nevrátí SPZ

**Doporučení:**
- Nastavit `DATAOVO_API_KEY` v ENV
- Restartovat backend service
- Ověřit, že `source_priority` obsahuje `"mdcr"` na první pozici
- Zvážit odstranění hardcoded fallback SPZ (nebo přesunout do DB)

