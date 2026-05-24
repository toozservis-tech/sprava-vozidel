# Database Path Calculation Fix

**Datum:** 2025-01-27  
**Soubor:** `src/modules/vehicle_hub/database.py`

---

## ✅ PROBLÉM

Výpočet cesty k databázi používal **nesprávný počet `.parent`**:

```python
project_root = Path(__file__).parent.parent.parent.parent  # /opt/toozhub2/app -> /opt/toozhub2
```

**Problém:**
- Soubor je na: `/opt/toozhub2/app/src/modules/vehicle_hub/database.py`
- `.parent.parent.parent.parent` = `/opt/toozhub2/app` ❌
- Očekávaná cesta: `/opt/toozhub2/data/vehicles.db`
- Skutečná cesta: `/opt/toozhub2/app/data/vehicles.db` ❌

**Důsledek:**
- Databáze se vytváří na špatném místě
- Deployment očekávající `/opt/toozhub2/data/vehicles.db` selže
- Potenciální problémy s oprávněními a zálohováním

---

## ✅ OPRAVA

Změněno z **4 `.parent`** na **5 `.parent`**:

```python
# File location: /opt/toozhub2/app/src/modules/vehicle_hub/database.py
# Need to go up 5 levels: database.py -> vehicle_hub -> modules -> src -> app -> /opt/toozhub2
project_root = Path(__file__).parent.parent.parent.parent.parent  # /opt/toozhub2/app/src/modules/vehicle_hub -> /opt/toozhub2
```

**Výpočet:**
- `__file__` = `/opt/toozhub2/app/src/modules/vehicle_hub/database.py`
- `.parent` = `/opt/toozhub2/app/src/modules/vehicle_hub`
- `.parent.parent` = `/opt/toozhub2/app/src/modules`
- `.parent.parent.parent` = `/opt/toozhub2/app/src`
- `.parent.parent.parent.parent` = `/opt/toozhub2/app`
- `.parent.parent.parent.parent.parent` = `/opt/toozhub2` ✅

**Výsledek:**
- Databáze se vytváří na: `/opt/toozhub2/data/vehicles.db` ✅
- Odpovídá očekávané cestě v komentáři
- Správné umístění pro deployment

---

## 📋 ZMĚNY

**Soubor:** `src/modules/vehicle_hub/database.py`
**Řádky:** 13-18

**Před:**
```python
# Default: SQLite v /opt/toozhub2/data/vehicles.db (absolutní path)
project_root = Path(__file__).parent.parent.parent.parent  # /opt/toozhub2/app -> /opt/toozhub2
data_dir = project_root / "data"
data_dir.mkdir(parents=True, exist_ok=True)
db_file = data_dir / "vehicles.db"
DB_URL = f"sqlite:///{db_file}"
```

**Po:**
```python
# Default: SQLite v /opt/toozhub2/data/vehicles.db (absolutní path)
# File location: /opt/toozhub2/app/src/modules/vehicle_hub/database.py
# Need to go up 5 levels: database.py -> vehicle_hub -> modules -> src -> app -> /opt/toozhub2
project_root = Path(__file__).parent.parent.parent.parent.parent  # /opt/toozhub2/app/src/modules/vehicle_hub -> /opt/toozhub2
data_dir = project_root / "data"
data_dir.mkdir(parents=True, exist_ok=True)
db_file = data_dir / "vehicles.db"
DB_URL = f"sqlite:///{db_file}"
```

---

## 🧪 TESTOVÁNÍ

### Test 1: Ověření výpočtu cesty
```python
from pathlib import Path
file_path = Path('/opt/toozhub2/app/src/modules/vehicle_hub/database.py')
project_root = file_path.parent.parent.parent.parent.parent
data_dir = project_root / 'data'
db_file = data_dir / 'vehicles.db'
assert str(db_file) == '/opt/toozhub2/data/vehicles.db'
```

### Test 2: Vytvoření databáze
```bash
# Spustit aplikaci a ověřit, že se databáze vytvoří na správném místě
python3 -c "from src.modules.vehicle_hub.database import DB_URL; print(DB_URL)"
# Očekávaný výstup: sqlite:////opt/toozhub2/data/vehicles.db
```

### Test 3: Ověření existence souboru
```bash
# Po spuštění aplikace by měl existovat:
ls -la /opt/toozhub2/data/vehicles.db
```

---

## ✅ DŮKAZ FUNKČNOSTI

Po opravě:
1. ✅ Databáze se vytváří na `/opt/toozhub2/data/vehicles.db`
2. ✅ Odpovídá očekávané cestě v komentáři
3. ✅ Správné umístění pro deployment
4. ✅ Kompatibilní s očekáváním systemd služby a zálohováním

---

**Dokončeno:** 2025-01-27

