# INVENTURA PROJEKTU sprava-vozidel

**Datum:** 2025-01-27  
**Root:** /opt/toozhub2/

---

## KROK 0: INVENTURA

### FastAPI App Instance
**FOUND:** `/opt/toozhub2/app/src/server/main.py` -> FastAPI app instance (řádek 106)
- `app = FastAPI(title="Správa vozidel API", version=APP_VERSION)`

### Routery (include_router)
**FOUND:** `/opt/toozhub2/app/src/server/main.py` -> registrace routerů (řádky 168-231)
- `decoder_router` -> `/api/vehicles/decode-vin`, `/api/vehicles/decode-plate`
- `v1_api_router` -> `/api/v1/*` (vehicles, reminders, reservations, atd.)
- `autopilot_router` -> `/api/autopilot/*`
- `customer_commands_router` -> `/api/customer-commands/*`
- `admin_api_router` -> `/api/admin/*`
- `instances.router` -> `/api/instances/*`
- `ai_features_router` -> `/api/ai-features/*`

**FOUND:** `/opt/toozhub2/app/src/modules/vehicle_hub/routers_v1/__init__.py` -> v1 API routery
- `vehicles.router` -> `/api/v1/vehicles`
- `reminders.router` -> `/api/v1/reminders`
- `reservations.router` -> `/api/v1/reservations`
- `vin_lookup.router` -> `/api/v1/vin/{vin}`
- `ares_lookup.router` -> `/api/v1/ares/{ico}`

### Endpointy

#### Vehicles CRUD
- `GET /api/v1/vehicles` -> seznam vozidel
- `POST /api/v1/vehicles` -> vytvoření vozidla
- `GET /api/v1/vehicles/{id}` -> detail vozidla
- `PUT /api/v1/vehicles/{id}` -> aktualizace vozidla
- `DELETE /api/v1/vehicles/{id}` -> smazání vozidla

#### VIN Decode
- `POST /api/vehicles/decode-vin` -> dekódování VIN (decoder router)

#### ARES/IČO
- `GET /api/v1/ares/{ico}` -> ARES lookup podle IČO

#### Reminders
- `GET /api/v1/reminders` -> seznam připomínek
- `POST /api/v1/reminders` -> vytvoření připomínky
- `PUT /api/v1/reminders/{id}` -> aktualizace připomínky
- `DELETE /api/v1/reminders/{id}` -> smazání připomínky

### DB Vrstva

**FOUND:** `/opt/toozhub2/app/src/modules/vehicle_hub/database.py` -> DB konfigurace
- **Typ:** SQLite (default)
- **Config:** `DATABASE_URL` nebo `VEHICLE_DB_URL` z ENV
- **Default:** `sqlite:///./vehicles.db` (relativní cesta!)
- **Engine:** `create_engine(DB_URL, connect_args=connect_args)`
- **Session:** `SessionLocal = sessionmaker(...)`

**FOUND:** `/opt/toozhub2/app/vehicles.db` -> databázový soubor
- **Path:** `/opt/toozhub2/app/vehicles.db`
- **Size:** 446464 bytes (446 KB)
- **Owner:** toozhub2:toozhub2
- **Last modified:** Dec 28 17:59

**PROBLÉM:** DB path je relativní (`sqlite:///./vehicles.db`), což může způsobit problémy při změně working directory!

### ENV Proměnné

**FOUND:** `/opt/toozhub2/app/src/core/config.py` -> načítání ENV
- Používá `python-dotenv` (`load_dotenv`)
- Načítá z `/opt/toozhub2/app/.env`
- Fallback parser pokud dotenv selže

**ENV proměnné:**
- `DATABASE_URL` nebo `VEHICLE_DB_URL` -> DB connection string
- `DATAOVO_API_KEY` -> MDČR API klíč
- `DATAOVO_API_BASE_URL` -> MDČR API base URL
- `JWT_SECRET_KEY` -> JWT secret
- `ALLOWED_ORIGINS` -> CORS origins

### Frontend

**FOUND:** `/opt/toozhub2/app/web/index.html` -> hlavní frontend
- Volá endpointy přes `apiCall()` funkci
- VIN decode: `POST /api/vehicles/decode-vin`
- ARES lookup: `GET /api/v1/ares/{ico}`
- Vehicles: `GET /api/v1/vehicles`

---

## IDENTIFIKOVANÉ PROBLÉMY

### 1. DB Path je relativní
- `sqlite:///./vehicles.db` -> závisí na working directory
- Pokud server běží z jiného adresáře, DB nebude nalezena
- **Řešení:** Použít absolutní path: `/opt/toozhub2/data/vehicles.db`

### 2. DB soubor je v `/opt/toozhub2/app/vehicles.db`
- Mělo by být v `/opt/toozhub2/data/vehicles.db` pro lepší organizaci
- **Řešení:** Migrovat DB do `/opt/toozhub2/data/` nebo upravit path

### 3. Chybí `/opt/toozhub2/data/` složka
- **Řešení:** Vytvořit složku a přesunout DB

---

## DALŠÍ KROKY

1. ✅ Inventura dokončena
2. ⏳ Opravit DB path (KROK 1)
3. ⏳ Opravit /vehicles 500 error
4. ⏳ Otestovat VIN decode
5. ⏳ Otestovat ARES lookup
6. ⏳ Otestovat reminders

