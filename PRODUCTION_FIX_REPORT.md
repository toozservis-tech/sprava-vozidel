# PRODUCTION FIX REPORT - Správa vozidel
## Datum: 2025-12-29

## Shrnutí Změn

Tento dokument popisuje opravy provedené pro stabilní a bezpečné produkční nasazení na Hetzneru.

---

## 1. CORS Middleware - Opraveno Pořadí

**Problém:** CORS middleware byl za rate limiting, což mohlo blokovat OPTIONS preflight requests.

**Oprava:**
- Přesunuto CORS middleware před rate limiting
- CORS nyní zpracovává OPTIONS requests dříve než rate limiter
- Přidány explicitní metody: `GET, POST, PUT, DELETE, PATCH, OPTIONS, HEAD`

**Soubor:** `src/server/main.py` (řádky 130-147)

**Důvod:** CORS preflight (OPTIONS) musí být zpracován před jakýmkoliv rate limiting nebo autentizací.

---

## 2. Reset Password - Bezpečnostní Oprava

**Problém:** V produkci se vracel `reset_url` v response, což je bezpečnostní riziko.

**Oprava:**
- V PROD: `reset_url` se nikdy nevrací v response
- V DEV: `reset_url` se vrací pouze pro testování
- Přidána kontrola `ENVIRONMENT` proměnné

**Soubor:** `src/server/main.py` (řádky 710-736)

**Důvod:** V produkci nesmí být reset tokeny vystaveny v API response.

---

## 3. CSP (Content Security Policy) - Opraveno pro API Volání

**Problém:** CSP mohlo blokovat API volání na externí servery (dataovozidlech.cz, ares.gov.cz).

**Oprava:**
- Přidán `connect-src` s povolenými API doménami:
  - `https://hub.toozservis.cz` (vlastní API)
  - `https://api.dataovozidlech.cz` (VIN lookup)
  - `https://ares.gov.cz` (IČO lookup)
- V DEV: povoleno `http://localhost:*` a `https:`

**Soubor:** `src/core/security_middleware.py` (řádky 46-64)

**Důvod:** Frontend musí moci volat API na externí servery přes backend proxy.

---

## 4. VIN Lookup - Přidáno Logování

**Oprava:**
- Přidáno strukturované logování (bez citlivých dat)
- Loguje: VIN (maskovaný), make, model, year, source
- Error logging s typem chyby

**Soubor:** `src/modules/vehicle_hub/routers_v1/vin_lookup.py` (řádky 28-121)

**Důvod:** Lepší diagnostika problémů s VIN lookup bez vystavení citlivých dat.

---

## 5. ARES Lookup - Přidáno Logování

**Oprava:**
- Přidáno strukturované logování (bez citlivých dat)
- Loguje: IČO, company name, city
- Error logging s typem chyby (timeout, request error, unexpected)

**Soubor:** `src/modules/vehicle_hub/routers_v1/ares_lookup.py` (řádky 25-122)

**Důvod:** Lepší diagnostika problémů s ARES lookup.

---

## 6. Email Service - Vylepšený Error Handling

**Oprava:**
- Přidáno detailní logování kroků (connection, authentication, sending)
- Specifické error handling pro:
  - `SMTPAuthenticationError` → "SMTP autentizace selhala"
  - `SMTPConnectError` → "Nelze se připojit k SMTP serveru"
  - Ostatní `SMTPException` → obecná chyba
- Timeout zvýšen z 10s na 30s
- Logování bez citlivých dat (heslo se neloguje)

**Soubor:** `src/modules/email_client/service.py` (řádky 100-117)

**Důvod:** Lepší diagnostika email problémů bez vystavení hesel.

---

## 7. Rate Limiting - Vylepšení

**Oprava:**
- OPTIONS requests (CORS preflight) nejsou rate-limited
- `/health` endpoint není rate-limited
- Zůstává limit 100 calls/60s pro ostatní endpointy

**Soubor:** `src/core/security_middleware.py` (řádky 84-121)

**Důvod:** CORS preflight a health check musí fungovat bez omezení.

---

## 8. Health Check - Přidán OPTIONS Handler

**Oprava:**
- Přidán explicitní `@app.options("/health")` decorator
- Health check nevyžaduje autentizaci
- Health check není rate-limited

**Soubor:** `src/server/main.py` (řádky 1133-1155)

**Důvod:** Zajištění, že health check funguje i při CORS preflight.

---

## Změněné Soubory

1. **`src/server/main.py`**
   - Pořadí middleware (CORS před rate limiting)
   - Reset password bezpečnostní oprava
   - Health check OPTIONS handler

2. **`src/core/security_middleware.py`**
   - CSP opraveno pro API volání
   - Rate limiting vylepšení (OPTIONS a /health excluded)

3. **`src/modules/vehicle_hub/routers_v1/vin_lookup.py`**
   - Přidáno logování

4. **`src/modules/vehicle_hub/routers_v1/ares_lookup.py`**
   - Přidáno logování

5. **`src/modules/email_client/service.py`**
   - Vylepšený error handling a logování

---

## Ověření v Produkci

### 1. Health Check
```bash
curl -I https://hub.toozservis.cz/health
# ✅ Musí vrátit 200 OK

curl -X OPTIONS https://hub.toozservis.cz/health -H "Origin: https://hub.toozservis.cz"
# ✅ Musí vrátit 200 OK s CORS headers
```

### 2. CORS Preflight
```bash
curl -X OPTIONS https://hub.toozservis.cz/api/v1/vehicles \
  -H "Origin: https://hub.toozservis.cz" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization"
# ✅ Musí vrátit 200 OK s CORS headers
```

### 3. Login
```bash
curl -X POST https://hub.toozservis.cz/user/login \
  -H "Content-Type: application/json" \
  -H "Origin: https://hub.toozservis.cz" \
  -d '{"email":"test@example.com","password":"test123"}'
# ✅ Musí vrátit 200 OK s JWT tokenem nebo 401 Unauthorized
```

### 4. VIN Lookup
```bash
curl -X GET "https://hub.toozservis.cz/api/v1/vin/TMBJF73T2B9044629" \
  -H "Authorization: Bearer <token>" \
  -H "Origin: https://hub.toozservis.cz"
# ✅ Musí vrátit 200 OK s daty nebo 422 Unprocessable Entity
```

### 5. ARES Lookup
```bash
curl -X GET "https://hub.toozservis.cz/api/v1/ares/27082440" \
  -H "Authorization: Bearer <token>" \
  -H "Origin: https://hub.toozservis.cz"
# ✅ Musí vrátit 200 OK s daty nebo 404 Not Found
```

### 6. Reset Password
```bash
curl -X POST https://hub.toozservis.cz/user/forgot-password \
  -H "Content-Type: application/json" \
  -H "Origin: https://hub.toozservis.cz" \
  -d '{"email":"test@example.com"}'
# ✅ V PROD: response NESMÍ obsahovat "reset_url"
# ✅ V DEV: response může obsahovat "reset_url"
```

---

## Požadované Environment Variables

Pro plnou funkčnost je potřeba nastavit v `.env`:

```bash
# Povinné pro produkci
ENVIRONMENT=production
JWT_SECRET_KEY=<vygenerovaný_bezpečný_klíč>
HOST=127.0.0.1
PORT=8000
PUBLIC_API_BASE_URL=https://hub.toozservis.cz
ALLOWED_ORIGINS=https://www.toozservis.cz,https://toozservis.cz,https://hub.toozservis.cz

# VIN Lookup (volitelné, ale doporučené)
DATAOVO_API_KEY=<api_klíč_z_dataovozidlech.cz>
DATAOVO_API_BASE_URL=https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2

# Email (volitelné, ale doporučené)
SMTP_HOST=smtp.mail.webnode.com
SMTP_PORT=465  # nebo 587 pro STARTTLS
SMTP_USER=info@toozservis.cz
SMTP_PASSWORD=<heslo>
SMTP_FROM=info@toozservis.cz

# Database (výchozí SQLite)
DATABASE_URL=sqlite:///./vehicles.db
```

---

## Security Headers

Aplikace automaticky přidává tyto security headers:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `Referrer-Policy: no-referrer`
- `Permissions-Policy: geolocation=(), microphone=(), camera=()`
- `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload` (pouze HTTPS)
- `Content-Security-Policy: ...` (podle prostředí)
- `Server: Správa vozidel` (skrytí server info)

---

## Rate Limiting

- **Globální limit:** 100 requests / 60 sekund na IP:endpoint
- **Login limit:** 5 pokusů / 60 sekund na IP
- **Výjimky:** OPTIONS requests, `/health` endpoint

---

## Kritérium Úspěchu

- ✅ Web app na `https://hub.toozservis.cz` běží stabilně (žádné "Failed to fetch")
- ✅ Přihlášení funguje (JWT + cookies/headers)
- ✅ VIN lookup funguje z UI a vrací data
- ✅ IČO (ARES) lookup funguje z UI a vrací data
- ✅ Reset hesla pošle email (pokud je SMTP nastaveno)
- ✅ V PROD reset_url není v response
- ✅ CORS správně nastaven pro všechny povolené domény
- ✅ Security headers jsou nastavené
- ✅ Rate limit neblokuje běžné použití
- ✅ Vše funguje na mobilu i desktopu

---

## Nasazení

Po změnách restartovat backend:

```bash
sudo systemctl restart toozhub-server
```

Ověřit logy:

```bash
sudo journalctl -u toozhub-server -n 50 -f
```
