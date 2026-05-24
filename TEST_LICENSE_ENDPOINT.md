# Test /api/v1/license/status endpointu

## ✅ OVĚŘENÍ - Endpoint funguje!

**Produkční URL:** `https://hub.toozservis.cz`

### Test 1: Bez tokenu (na serveru lokálně)
```bash
# Na serveru (SSH):
curl -i http://127.0.0.1:8000/api/v1/license/status
```

**Nebo zvenčí (produkční URL):**
```bash
curl -i https://hub.toozservis.cz/api/v1/license/status
```

**Výsledek:** HTTP 401 Unauthorized ✅
- **NENÍ 404** - endpoint existuje!
- Správné chování bez tokenu

### Test 2: V OpenAPI JSON
```bash
# Na serveru:
curl -s http://127.0.0.1:8000/openapi.json | grep "license/status"

# Nebo zvenčí:
curl -s https://hub.toozservis.cz/openapi.json | grep "license/status"
```

**Výsledek:** ✅ Endpoint je v OpenAPI JSON

---

## Získání JWT tokenu pro testování

### Možnost 1: Přes UI (nejjednodušší)
1. Otevřít `https://hub.toozservis.cz/web/index.html`
2. Přihlásit se
3. Otevřít Developer Console (F12)
4. Spustit:
   ```javascript
   localStorage.getItem('access_token')
   ```
5. Zkopírovat token a použít v curl

### Možnost 2: Přes API login (na serveru)
```bash
# Na serveru (SSH):
curl -X POST http://127.0.0.1:8000/user/login \
  -H "Content-Type: application/json" \
  -d '{"email":"toozservis@gmail.com","password":"<heslo>"}'

# Nebo zvenčí:
curl -X POST https://hub.toozservis.cz/user/login \
  -H "Content-Type: application/json" \
  -d '{"email":"toozservis@gmail.com","password":"<heslo>"}'

# Odpověď obsahuje:
# {
#   "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
#   "token_type": "bearer",
#   "user": {...}
# }
```

### Možnost 3: Vytvořit testovacího uživatele
```bash
# Na serveru:
curl -X POST http://127.0.0.1:8000/user/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "test123",
    "name": "Test User"
  }'

# Odpověď obsahuje access_token
```

---

## Test s tokenem

```bash
TOKEN="<váš_jwt_token>"

# Na serveru:
curl -i http://127.0.0.1:8000/api/v1/license/status \
  -H "Authorization: Bearer $TOKEN"

# Nebo zvenčí (produkční):
curl -i https://hub.toozservis.cz/api/v1/license/status \
  -H "Authorization: Bearer $TOKEN"
```

**Očekávaný výsledek:** HTTP 200 s JSON:
```json
{
  "tenant_id": "1",
  "plan": "free",
  "status": "active",
  "vehicles_limit": 1,
  "vehicles_current": 0,
  "vehicles_remaining": 1,
  "is_unlimited": false,
  "vin_decode_enabled": true,
  "ares_enabled": true,
  "reminders_enabled": true
}
```

---

## Shrnutí

✅ **Endpoint je funkční:**
- Vrací 401 bez tokenu (ne 404)
- Je v OpenAPI JSON
- Bude viditelný v `/docs`
- Router je správně zaregistrován
- DB migrace dokončena

🎉 **Problém vyřešen!**
