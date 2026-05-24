# Migrace databáze - FÁZE 2: Přidání STK a servisních polí

## ⚠️ DŮLEŽITÉ: Povinná migrace

**Migrace databáze je POVINNÁ** při aktualizaci na FÁZI 2. Nové sloupce musí být přidány pomocí `ALTER TABLE` příkazů.

## 📋 Přehled změn

V této fázi byly přidány nové sloupce do databázových tabulek:

### Vehicle (vozidla)
- **`stk_valid_until`** (Date, nullable) - Datum konce platnosti STK

### ServiceRecord (servisní záznamy)
- **`category`** (String, nullable) - Kategorie servisu (např. "Pravidelná údržba", "Oprava", "Výměna oleje")
- **`next_service_due_date`** (Date, nullable) - Datum dalšího plánovaného servisu

## ⚠️ VAROVÁNÍ: SQLAlchemy create_all() NEPROVÁDÍ migraci

**DŮLEŽITÉ:** `Base.metadata.create_all(bind=engine)` **NEPROVÁDÍ** automatickou migraci existujících tabulek.

- ✅ `create_all()` vytvoří **nové tabulky**, pokud neexistují
- ❌ `create_all()` **NEPŘIDÁ** nové sloupce do existujících tabulek
- ❌ `create_all()` **NEPROVÁDÍ** `ALTER TABLE` příkazy

> **⚠️ VAROVÁNÍ:**
> 
> **Pokud se ALTER TABLE neprovede:**
> - Backend bude očekávat sloupce `stk_valid_until`, `category`, `next_service_due_date`, které v databázi nejsou
> - API endpointy začnou padat s SQL chybami typu `"no such column"` nebo `"unknown column"`
> - Aplikace **nebude funkční** a všechny operace s vozidly/servisními záznamy selžou

## 🔧 Migrace databáze (POVINNÁ)

**Pro přidání nových sloupců do existujících tabulek musíte použít `ALTER TABLE` příkazy:**

### SQLite

```sql
-- Přidání sloupce stk_valid_until do tabulky vehicles
ALTER TABLE vehicles ADD COLUMN stk_valid_until DATE;

-- Přidání sloupce category do tabulky service_records
ALTER TABLE service_records ADD COLUMN category VARCHAR;

-- Přidání sloupce next_service_due_date do tabulky service_records
ALTER TABLE service_records ADD COLUMN next_service_due_date DATE;
```

### PostgreSQL

```sql
-- Přidání sloupce stk_valid_until do tabulky vehicles
ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS stk_valid_until DATE;

-- Přidání sloupce category do tabulky service_records
ALTER TABLE service_records ADD COLUMN IF NOT EXISTS category VARCHAR;

-- Přidání sloupce next_service_due_date do tabulky service_records
ALTER TABLE service_records ADD COLUMN IF NOT EXISTS next_service_due_date DATE;
```

## 📝 Doporučený postup migrace

### Krok 1: Zálohování databáze

**SQLite:**
```bash
cp vehicles.db vehicles.db.backup
```

**PostgreSQL:**
```bash
pg_dump -U username -d database_name > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Krok 2: Vykonání ALTER TABLE příkazů

**SQLite:**
```bash
sqlite3 vehicles.db <<EOF
ALTER TABLE vehicles ADD COLUMN stk_valid_until DATE;
ALTER TABLE service_records ADD COLUMN category VARCHAR;
ALTER TABLE service_records ADD COLUMN next_service_due_date DATE;
EOF
```

Nebo interaktivně:
```bash
sqlite3 vehicles.db
sqlite> ALTER TABLE vehicles ADD COLUMN stk_valid_until DATE;
sqlite> ALTER TABLE service_records ADD COLUMN category VARCHAR;
sqlite> ALTER TABLE service_records ADD COLUMN next_service_due_date DATE;
sqlite> .quit
```

**PostgreSQL:**
```bash
psql -U username -d database_name <<EOF
ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS stk_valid_until DATE;
ALTER TABLE service_records ADD COLUMN IF NOT EXISTS category VARCHAR;
ALTER TABLE service_records ADD COLUMN IF NOT EXISTS next_service_due_date DATE;
EOF
```

### Krok 3: Restart backend serveru

```bash
# Pokud běží jako systemd služba
sudo systemctl restart toozhub-server

# Nebo pokud běží přímo
python src/server/main.py
```

### Krok 4: Ověření migrace

**SQLite:**
```bash
# Ověření struktury tabulek
sqlite3 vehicles.db ".schema vehicles"
sqlite3 vehicles.db ".schema service_records"

# Nebo kontrola sloupců
sqlite3 vehicles.db "PRAGMA table_info(vehicles);"
sqlite3 vehicles.db "PRAGMA table_info(service_records);"
```

**PostgreSQL:**
```sql
-- Ověření struktury tabulek
\d vehicles
\d service_records

-- Nebo kontrola sloupců
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'vehicles' AND column_name IN ('stk_valid_until');

SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'service_records' 
AND column_name IN ('category', 'next_service_due_date');
```

### Krok 5: Otestování API

```bash
# Test health check
curl http://localhost:8000/health

# Test získání vozidel (vyžaduje autentizaci)
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/vehicles

# Test vytvoření vozidla s novým polem
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plate":"ABC1234","name":"Test","stk_valid_until":"2025-12-31"}' \
  http://localhost:8000/vehicles
```

## ✅ Zpětná kompatibilita

Všechny nové sloupce jsou **nullable** (mohou být NULL), takže:
- ✅ Existující záznamy zůstávají funkční po migraci
- ✅ Nové sloupce budou mít hodnotu `NULL` pro existující záznamy
- ✅ Nová pole jsou volitelná při vytváření záznamů

## Aktualizace existujících dat

Po migraci můžete aktualizovat existující data, například:

```sql
-- Aktualizovat STK datum na základě nějaké logiky (ukázka)
-- UPDATE vehicles SET stk_valid_until = date('now', '+2 years') WHERE stk_valid_until IS NULL;

-- Přiřadit kategorii existujícím servisním záznamům (ukázka)
-- UPDATE service_records SET category = 'Pravidelná údržba' WHERE category IS NULL;
```

## 📌 Důležité poznámky

- ✅ Migrace je **neinvazivní** - neodstraní žádná existující data
- ✅ Nové sloupce jsou **volitelné** (nullable) - mohou být NULL
- ❌ **SQLAlchemy `create_all()` NEPROVÁDÍ migraci** - musíte použít ALTER TABLE
- ⚠️ **Migrace je POVINNÁ** - bez ní aplikace nebude funkční
- 🔒 Pro produkční prostředí **VŽDY zálohujte** databázi před migrací

## Související soubory

- `src/modules/vehicle_hub/models.py` - SQLAlchemy modely
- `src/modules/vehicle_hub/database.py` - Databázové připojení
- `src/server/main.py` - API endpointy s novými poli
- `src/modules/vehicle_hub/schemas.py` - Pydantic schémata

## Kontakt

V případě problémů s migrací zkontrolujte logy serveru při startu.

