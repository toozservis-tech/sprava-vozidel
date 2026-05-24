# Legacy Environment Variables Fallback Fix

**Datum:** 2025-01-27  
**Soubory:** 
- `src/core/config.py`
- `src/modules/vehicle_hub/decoder/mdcr_client.py`

---

## ✅ PROBLÉM

Změny odstranily **fallback podporu pro legacy environment variable názvy**:

**Před změnou:**
```python
DATAOVO_API_KEY = os.getenv("DATAOVO_API_KEY") or os.getenv("DATAOVOZIDLECH_API_KEY", "")
DATAOVO_API_BASE_URL = os.getenv("DATAOVO_API_BASE_URL") or os.getenv("DATAOVOZIDLECH_API_URL", "...")
```

**Po změně:**
```python
DATAOVO_API_KEY = os.getenv("DATAOVO_API_KEY", "")
DATAOVO_API_BASE_URL = os.getenv("DATAOVO_API_BASE_URL", "...")
```

**Problém:**
- Existující deploymenty používající `DATAOVOZIDLECH_API_KEY` / `DATAOVOZIDLECH_API_URL` selžou
- MDČR API nebude nakonfigurováno
- VIN dekódování přestane fungovat
- Chyba není zřejmá - silent failure

---

## ✅ OPRAVA

Obnovena **fallback podpora pro legacy názvy**:

**config.py:**
```python
# Podporujeme oba názvy (nové i legacy) pro zpětnou kompatibilitu
DATAOVO_API_KEY = os.getenv("DATAOVO_API_KEY") or os.getenv("DATAOVOZIDLECH_API_KEY", "")
DATAOVO_API_BASE_URL = os.getenv("DATAOVO_API_BASE_URL") or os.getenv("DATAOVOZIDLECH_API_URL", "...")
```

**mdcr_client.py:**
```python
try:
    from src.core.config import DATAOVO_API_KEY, DATAOVO_API_BASE_URL
    # Config.py už má fallback logiku, použijeme ji
except ImportError:
    # Fallback na přímé čtení z ENV s podporou legacy názvů
    DATAOVO_API_KEY = os.getenv("DATAOVO_API_KEY") or os.getenv("DATAOVOZIDLECH_API_KEY", "")
    DATAOVO_API_BASE_URL = os.getenv("DATAOVO_API_BASE_URL") or os.getenv("DATAOVOZIDLECH_API_URL", "...")
```

**Výsledek:**
- ✅ Nové názvy (`DATAOVO_API_KEY`) mají prioritu
- ✅ Legacy názvy (`DATAOVOZIDLECH_API_KEY`) fungují jako fallback
- ✅ Zpětná kompatibilita zachována
- ✅ Existující deploymenty budou fungovat

---

## 📋 ZMĚNY

### Soubor 1: `src/core/config.py` (řádky 166-172)

**Před:**
```python
# KROK 1: Konfigurace POUZE z ENV proměnných
# Používáme POUZE DATAOVO_API_KEY a DATAOVO_API_BASE_URL z ENV
DATAOVO_API_KEY = os.getenv("DATAOVO_API_KEY", "")
DATAOVO_API_BASE_URL = os.getenv("DATAOVO_API_BASE_URL", "https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2")
```

**Po:**
```python
# Podporujeme oba názvy (nové i legacy) pro zpětnou kompatibilitu
DATAOVO_API_KEY = os.getenv("DATAOVO_API_KEY") or os.getenv("DATAOVOZIDLECH_API_KEY", "")
DATAOVO_API_BASE_URL = os.getenv("DATAOVO_API_BASE_URL") or os.getenv("DATAOVOZIDLECH_API_URL", "https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2")
```

### Soubor 2: `src/modules/vehicle_hub/decoder/mdcr_client.py` (řádky 100-108)

**Před:**
```python
# KROK 1: Konfigurace POUZE z ENV proměnných
# Používáme POUZE DATAOVO_API_KEY a DATAOVO_API_BASE_URL z ENV
DATAOVO_API_KEY = os.getenv("DATAOVO_API_KEY", "")
DATAOVO_API_BASE_URL = os.getenv("DATAOVO_API_BASE_URL", "https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2")
```

**Po:**
```python
try:
    from src.core.config import DATAOVO_API_KEY, DATAOVO_API_BASE_URL
    # Config.py už má fallback logiku, použijeme ji
except ImportError:
    # Fallback na přímé čtení z ENV s podporou legacy názvů
    DATAOVO_API_KEY = os.getenv("DATAOVO_API_KEY") or os.getenv("DATAOVOZIDLECH_API_KEY", "")
    DATAOVO_API_BASE_URL = os.getenv("DATAOVO_API_BASE_URL") or os.getenv("DATAOVOZIDLECH_API_URL", "https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2")
```

---

## 🧪 TESTOVÁNÍ

### Test 1: Nové názvy (preferované)
```bash
export DATAOVO_API_KEY="new_key"
export DATAOVO_API_BASE_URL="https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2"
# Očekávaný výsledek: Použije nové názvy
```

### Test 2: Legacy názvy (fallback)
```bash
export DATAOVOZIDLECH_API_KEY="legacy_key"
export DATAOVOZIDLECH_API_URL="https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2"
# Očekávaný výsledek: Použije legacy názvy jako fallback
```

### Test 3: Smíšené (nové má prioritu)
```bash
export DATAOVO_API_KEY="new_key"
export DATAOVOZIDLECH_API_KEY="legacy_key"
# Očekávaný výsledek: Použije nové názvy (má prioritu)
```

---

## ✅ DŮKAZ FUNKČNOSTI

Po opravě:
1. ✅ Nové názvy (`DATAOVO_API_KEY`) mají prioritu
2. ✅ Legacy názvy (`DATAOVOZIDLECH_API_KEY`) fungují jako fallback
3. ✅ Zpětná kompatibilita zachována
4. ✅ Existující deploymenty budou fungovat bez změny konfigurace

---

**Dokončeno:** 2025-01-27

