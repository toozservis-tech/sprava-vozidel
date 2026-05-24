# Production Verification Guide - Správa vozidel

## Jak Ověřit, že Aplikace Funguje v Produkci

### 1. V Prohlížeči

1. **Otevřít aplikaci**:
   ```
   https://hub.toozservis.cz/web/index.html
   ```

2. **Otevřít Debug Panel**:
   - Kliknout na 🧪 v navbaru (vpravo nahoře)
   - Zkontrolovat:
     - **API Base URL**: Mělo by být `https://hub.toozservis.cz`
     - **Token present**: Mělo by být "Yes" po přihlášení
     - **Recent Requests**: Měly by být vidět poslední 3 requesty

3. **Přihlásit se** a zkontrolovat:
   - Debug panel → Recent Requests → měl by být `GET /api/v1/vehicles` se statusem 200
   - Pokud je 404, zkontrolovat response body v debug panelu

4. **Zkontrolovat konzoli** (F12 → Console):
   - Měly by být logy: `[API] GET https://hub.toozservis.cz/api/v1/vehicles`
   - Měly by být logy: `[API] Response status: 200` (nebo jiný status)

### 2. Přes curl

```bash
# 1. Health check
curl https://hub.toozservis.cz/health

# 2. Login
curl -X POST https://hub.toozservis.cz/user/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password"}'

# 3. Get vehicles (s tokenem z kroku 2)
curl -X GET https://hub.toozservis.cz/api/v1/vehicles \
  -H "Authorization: Bearer <token>"

# 4. Debug routes (s tokenem)
curl -X GET https://hub.toozservis.cz/api/_debug/routes \
  -H "Authorization: Bearer <token>"
```

### 3. Použití prod_verify.sh

```bash
cd /opt/toozhub2/app
BASE_URL=https://hub.toozservis.cz \
TEST_EMAIL=user@example.com \
TEST_PASSWORD=password \
./scripts/prod_verify.sh
```

### Očekávané Výsledky

- ✅ `GET /health` → `200 OK`
- ✅ `POST /user/login` → `200 OK` + `access_token`
- ✅ `GET /api/v1/vehicles` (s tokenem) → `200 OK` + `[]` nebo seznam vozidel
- ✅ `GET /api/v1/vehicles` (bez tokenu) → `401 Unauthorized` nebo `404 Not Found`
- ✅ `GET /api/_debug/routes` (s tokenem) → `200 OK` + seznam routes včetně `/api/v1/vehicles`

### Pokud Stále Vidíte "Endpoint vozidel nebyl nalezen"

1. **Zkontrolovat Debug Panel**:
   - Jaká je API Base URL?
   - Je token present?
   - Jaký status má request v Recent Requests?

2. **Zkontrolovat Network Tab** (F12 → Network):
   - Jaká je skutečná URL requestu?
   - Jaký je status code?
   - Jaký je response body?

3. **Zkontrolovat Backend**:
   ```bash
   curl -X GET https://hub.toozservis.cz/api/_debug/routes \
     -H "Authorization: Bearer <token>"
   ```
   - Obsahuje response `/api/v1/vehicles`?

4. **Zkontrolovat Cloudflare Tunnel**:
   - Routuje `/api/*` na backend?
   - Neblokuje Cloudflare requesty?
