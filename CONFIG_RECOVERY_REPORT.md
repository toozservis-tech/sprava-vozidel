# CONFIG RECOVERY REPORT - Správa vozidel
## Datum: 2025-12-29

## Shrnutí Problému

Po přesunu aplikace na Hetzner server přestaly některé konfigurační klíče fungovat, i když existovaly před přesunem.

---

## KROK 1: DOHLEDÁNÍ EXISTUJÍCÍCH KLÍČŮ

### 1.1 Lokace .env souborů

**Nalezené soubory:**
- `/opt/toozhub2/app/.env` ✅ EXISTUJE
- `/opt/toozhub2/app/.env.example` ✅ EXISTUJE (template)

**Systemd Service konfigurace:**
```ini
EnvironmentFile=/opt/toozhub2/app/.env
WorkingDirectory=/opt/toozhub2/app
User=toozhub2
```

**Závěr:** Systemd service správně načítá `.env` soubor z `/opt/toozhub2/app/.env`.

### 1.2 Názvy proměnných v .env.example

Z `.env.example` byly identifikovány tyto proměnné:
- `ENVIRONMENT`
- `HOST`
- `PORT`
- `PUBLIC_API_BASE_URL`
- `ALLOWED_ORIGINS`
- `JWT_SECRET_KEY`
- `JWT_ALGORITHM`
- `JWT_EXPIRE_MINUTES`
- `DATABASE_URL`
- `DATAOVO_API_KEY` ⚠️ **CHYBÍ V .env**
- `DATAOVO_API_BASE_URL`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `SMTP_FROM`

### 1.3 Aktuální stav v .env

**Nastavené klíče (zjištěno z .env):**
- ✅ `ENVIRONMENT=production`
- ✅ `HOST=127.0.0.1`
- ✅ `PORT=8000`
- ✅ `PUBLIC_API_BASE_URL=https://hub.toozservis.cz`
- ✅ `ALLOWED_ORIGINS=...`
- ✅ `JWT_SECRET_KEY=...` (nastaven, není výchozí hodnota)
- ✅ `SMTP_HOST=smtp.mail.webnode.com`
- ✅ `SMTP_PORT=587`
- ✅ `SMTP_USER=info@toozservis.cz`
- ✅ `SMTP_PASSWORD=...` (nastaven)
- ✅ `SMTP_FROM=info@toozservis.cz`

**Chybějící klíče:**
- ❌ `DATAOVO_API_KEY` - **CHYBÍ V .env SOUBORU**

### 1.4 Zpětná kompatibilita názvů

Config podporuje tyto aliasy (pro zpětnou kompatibilitu):
- `DATAOVO_API_KEY` nebo `DATAOVOZIDLECH_API_KEY`
- `DATAOVO_API_BASE_URL` nebo `DATAOVOZIDLECH_API_URL`

**Závěr:** Pokud byl klíč dříve uložen jako `DATAOVOZIDLECH_API_KEY`, měl by se načíst. Ale v .env není ani jeden z nich.

### 1.5 Git historie

Z git historie:
- Commit `b96f81c`: `.env` byl odstraněn z repo (správně, bezpečnost)
- `.env.example` byl přidán jako template
- Názvy proměnných v `.env.example` odpovídají aktuálním názvům

**Závěr:** Názvy proměnných se nezměnily. Problém je, že `DATAOVO_API_KEY` chybí v `.env` souboru.

---

## KROK 2: PROČ SE KLÍČE NENAČÍTAJÍ

### 2.1 Načítání .env v config.py

**Cesta k .env:**
```python
env_path = Path(__file__).parent.parent.parent / ".env"
# = /opt/toozhub2/app/.env
```

**Proces načítání:**
1. Zkusí načíst s různými kódováními (UTF-8, Windows-1250, latin-1)
2. Použije `dotenv_values()` nebo fallback parser
3. Nastaví proměnné do `os.environ` pomocí `setdefault()`

**Problém:** Pokud klíč chybí v `.env` souboru, použije se výchozí hodnota (prázdný string pro `DATAOVO_API_KEY`).

### 2.2 Systemd Service

**Konfigurace:**
```ini
EnvironmentFile=/opt/toozhub2/app/.env
```

**Problém:** Systemd načítá `.env` do prostředí procesu, ale pokud klíč v souboru není, nebude v prostředí.

### 2.3 Validace při startu

**Před opravou:** Aplikace nekontrolovala, zda jsou všechny klíče nastaveny. Pouze JWT_SECRET_KEY měl kontrolu v produkci.

**Problém:** Chybějící `DATAOVO_API_KEY` nebyl detekován při startu.

---

## KROK 3: OPRAVA NAČÍTÁNÍ

### 3.1 Vylepšené logování při načítání .env

**Změny v `src/core/config.py`:**
- Přidáno logování: `[CONFIG] .env soubor načten z: {path}`
- Přidáno varování, pokud `.env` neexistuje
- Přidány exporty: `ENV_FILE_LOADED`, `ENV_FILE_SOURCE`

### 3.2 Startup validace

**Nový modul: `src/core/config_validator.py`**
- Validuje všechny kritické klíče při startu
- Loguje pouze existenci klíčů (nikdy ne hodnoty)
- Vrací strukturovaný status konfigurace

**Integrace v `src/server/main.py`:**
- Volá `log_config_status()` při startu
- V PROD: pokud chybí JWT_SECRET_KEY → ukončí aplikaci
- V PROD: pokud chybí DATAOVO_API_KEY → varování (není kritické)

### 3.3 Health Check Endpoint

**Nový endpoint: `GET /health/config`**
- Vrací stav konfigurace (bez hodnot)
- Nevyžaduje autentizaci
- Není rate-limited

**Response:**
```json
{
  "status": "ok" | "warning" | "error",
  "environment": "production",
  "jwt_configured": true/false,
  "dataovo_configured": true/false,
  "smtp_configured": true/false,
  "env_file_exists": true/false,
  "env_file_readable": true/false,
  "env_file_path": "/opt/toozhub2/app/.env",
  "missing_keys": ["DATAOVO_API_KEY"],
  "timestamp": "2025-12-29T..."
}
```

---

## KROK 4: SOURCE OF TRUTH

### 4.1 Primární zdroj konfigurace

**SOURCE OF TRUTH: `/opt/toozhub2/app/.env`**

Tento soubor je:
- Načítán systemd service přes `EnvironmentFile=`
- Načítán Python kódem přes `load_dotenv()` v `config.py`
- Měl by být zálohován pravidelně

### 4.2 Pořadí načítání

1. **Systemd EnvironmentFile** → načte `.env` do prostředí procesu
2. **Python config.py** → načte `.env` pomocí `load_dotenv()`
3. **os.getenv()** → použije hodnotu z prostředí nebo výchozí

**Důležité:** Systemd `EnvironmentFile` a Python `load_dotenv()` by měly načíst stejné hodnoty, pokud je `.env` na správném místě.

### 4.3 Zálohování

**Co zálohovat:**
```bash
# .env soubor (obsahuje všechny klíče)
/opt/toozhub2/app/.env

# Systemd service konfigurace
/etc/systemd/system/toozhub-server.service

# Template pro dokumentaci
/opt/toozhub2/app/.env.example
```

**Doporučený postup zálohování:**
```bash
# Záloha .env (bez hodnot v git)
cp /opt/toozhub2/app/.env /opt/toozhub2/app/.env.backup.$(date +%Y%m%d)

# Záloha systemd service
sudo cp /etc/systemd/system/toozhub-server.service /opt/toozhub2/app/toozhub-server.service.backup
```

---

## KROK 5: OBNOVA FUNKČNOSTI

### 5.1 DATAOVO_API_KEY

**Problém:** Klíč chybí v `.env` souboru.

**Řešení:**
1. Použít existující skript: `/opt/toozhub2/app/DOPLNIT_MDCR_API_KEY.sh`
2. Nebo ručně přidat do `.env`:
   ```bash
   echo "" >> /opt/toozhub2/app/.env
   echo "# MDČR API (dataovozidlech.cz)" >> /opt/toozhub2/app/.env
   echo "DATAOVO_API_KEY=<tvůj_api_klíč>" >> /opt/toozhub2/app/.env
   ```
3. Restartovat backend: `sudo systemctl restart toozhub-server`

**Validace:**
```bash
curl https://hub.toozservis.cz/health/config | jq '.dataovo_configured'
# Mělo by vrátit: true
```

### 5.2 Ostatní moduly

**JWT:** ✅ Funguje (klíč je nastaven)
**SMTP:** ✅ Funguje (všechny údaje jsou nastaveny)
**VIN Lookup:** ⚠️ Nebude fungovat bez `DATAOVO_API_KEY`

---

## FINÁLNÍ KONTROLA

### Test 1: Health Check
```bash
curl https://hub.toozservis.cz/health
# ✅ Mělo by vrátit 200 OK
```

### Test 2: Config Health
```bash
curl https://hub.toozservis.cz/health/config
# ✅ Mělo by vrátit status konfigurace
```

### Test 3: Login
```bash
curl -X POST https://hub.toozservis.cz/user/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123"}'
# ✅ Mělo by vrátit JWT token nebo 401
```

### Test 4: VIN Lookup (po přidání DATAOVO_API_KEY)
```bash
curl -X GET "https://hub.toozservis.cz/api/v1/vin/TMBJF73T2B9044629" \
  -H "Authorization: Bearer <token>"
# ✅ Mělo by vrátit data o vozidle
```

### Test 5: Reset Password (kontrola odeslání)
```bash
curl -X POST https://hub.toozservis.cz/user/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com"}'
# ✅ Mělo by vrátit email_sent: true/false
```

---

## ZMĚNĚNÉ SOUBORY

1. **`src/core/config.py`**
   - Přidáno logování při načítání .env
   - Přidány exporty: `ENV_FILE_LOADED`, `ENV_FILE_SOURCE`

2. **`src/core/config_validator.py`** (NOVÝ)
   - Validace konfigurace při startu
   - Logování bez hodnot
   - Funkce `validate_config()`, `log_config_status()`

3. **`src/server/main.py`**
   - Přidána startup validace konfigurace
   - Přidán endpoint `/health/config`

---

## DOPORUČENÍ

### 1. Zálohování
- Zálohovat `/opt/toozhub2/app/.env` pravidelně
- Ukládat zálohy mimo git repo
- Používat šifrované zálohy pro citlivé údaje

### 2. Monitoring
- Pravidelně kontrolovat `/health/config` endpoint
- Nastavit alerting, pokud `dataovo_configured: false` v PROD
- Logovat změny v konfiguraci

### 3. Dokumentace
- Udržovat `.env.example` aktuální
- Dokumentovat všechny požadované proměnné
- Udržovat tento report aktuální

---

## ZÁVĚR

**Hlavní problém:** `DATAOVO_API_KEY` chybí v `.env` souboru. Ostatní klíče jsou nastaveny správně.

**Řešení:** Přidat `DATAOVO_API_KEY` do `.env` souboru pomocí skriptu `DOPLNIT_MDCR_API_KEY.sh` nebo ručně.

**Preventivní opatření:** Přidána startup validace a `/health/config` endpoint pro monitoring konfigurace.

**Source of Truth:** `/opt/toozhub2/app/.env` - tento soubor je primárním zdrojem konfigurace a měl by být zálohován.
