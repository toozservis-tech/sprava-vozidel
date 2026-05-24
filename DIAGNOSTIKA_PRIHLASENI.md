# Diagnostika přihlášení – Správa vozidel

## Co bylo přidáno

1. **Backend** (`src/server/main.py`): Při každém požadavku na `POST /user/login` se do logu vypíše  
   `[LOGIN] Request received for xy***z (path=/user/login)`  
   → Pokud tento řádek v logu **není**, request na server **nedorazil** (síť, proxy, CORS, server neběží).

2. **Frontend** (`web/index.html`): V konzoli prohlížeče (F12 → Console) se u přihlášení zobrazí:
   - `[LOGIN] Odesílám požadavek na: <URL>`
   - `[LOGIN] Odpověď serveru: <status> <statusText>`  
   → Podle toho poznáte, zda se volá správná URL a co vrací server.

---

## Postup diagnostiky

### 1. Ověřit, že backend běží a login endpoint odpovídá

Na stroji, kde běží server (nebo na localhost):

```bash
# Health
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health
# Očekáváte: 200

# Login (špatné údaje – očekáváte 401)
curl -s -w "\nHTTP %{http_code}\n" -X POST http://127.0.0.1:8000/user/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.cz","password":"wrong"}'
# Očekáváte: JSON s "detail": "Neplatný email nebo heslo" a HTTP 401
```

- Pokud **health** není 200: server neběží nebo neposlouchá na 8000.
- Pokud **login** neodpovídá (timeout, connection refused): server neběží nebo je za firewall/proxy.
- Pokud login vrací 401 s JSON: backend funguje; problém je mezi prohlížečem a serverem (URL, CORS, Cloudflare).

### 2. V prohlížeči (F12 → Console a Network)

1. Otevřete přihlašovací stránku (např. https://hub.toozservis.cz/web/ nebo localhost).
2. Otevřete **Console** (F12 → Console).
3. Zadejte email a heslo a klikněte na **Přihlásit se**.

**V Console hledejte:**

- `[LOGIN] Odesílám požadavek na: ...`  
  - Pokud **není**: volá se jiná funkce nebo se před tím zastaví skript (chyba v konzoli).
- `[LOGIN] Odpověď serveru: 200 OK`  
  - 200 = server vrátil úspěch; pak může jít o chybu v parsování nebo v ukládání tokenu.
- `[LOGIN] Odpověď serveru: 401`  
  - Neplatný email nebo heslo (účet neexistuje nebo špatné heslo).
- `[LOGIN] Odpověď serveru: 429`  
  - Příliš mnoho pokusů (rate limit); počkejte cca 1 minutu.
- Žádná hláška „Odpověď serveru“ a místo toho chyba typu **Failed to fetch** / **NetworkError**  
  - Request se k serveru nedostal: server neběží, špatná URL, CORS, nebo blokace (např. Cloudflare).

**V záložce Network (Síť):**

1. Filtrujte např. podle „login“ nebo „user“.
2. Klikněte na request na `/user/login`.
3. Zkontrolujte:
   - **Status**: 200, 401, 403, 429, 500, (failed)…
   - **Request URL**: musí být ta samá, kterou používáte v prohlížeči (např. `https://hub.toozservis.cz/user/login` nebo `http://127.0.0.1:8000/user/login`).
   - **Response**: tělo odpovědi (JSON s `detail` nebo `access_token`).

### 3. Logy serveru

Při pokusu o přihlášení na serveru (nebo v terminálu, kde běží uvicorn) hledejte:

- `[LOGIN] Request received for ...`  
  - Pokud je tam: request dorazil na backend; chyba je v logice (heslo, účet, odpověď).
  - Pokud **není**: request na backend nedorazil (viz síť, CORS, proxy, URL).

---

## Časté příčiny „nereaguje přihlášení“

| Příznak | Možná příčina | Co zkontrolovat |
|--------|----------------|------------------|
| Žádná reakce po kliknutí | Chyba v JS před `fetch` | Console – červené chyby; existují `loginEmail`, `loginPassword`? |
| „API URL není nastavena“ | `getApiBaseUrl()` vrací prázdno | Na hub.toozservis.cz by měla vracet `https://hub.toozservis.cz`. Console: první řádek u přihlášení. |
| Failed to fetch / Network error | Síť, CORS, server nedostupný | Backend běží? Voláte správnou URL? CORS pro váš origin (ALLOWED_ORIGINS)? |
| 401 Unauthorized | Špatný email nebo heslo | Účet v DB existuje? Heslo odpovídá (bcrypt)? |
| 403 | Cloudflare / bezpečnostní blokace | Zkusit z jiné sítě; v Response zkontrolovat, zda je HTML (challenge) místo JSON. |
| 429 | Rate limit | Počkat cca 1 minutu; omezit počet pokusů. |
| 500 | Chyba na serveru | Server log – traceback; typicky chyba v DB nebo v kódu přihlášení. |

---

## Rychlý test přihlášení (curl s platným účtem)

Nahraďte email a heslo existujícím účtem:

```bash
curl -s -X POST http://127.0.0.1:8000/user/login \
  -H "Content-Type: application/json" \
  -d '{"email":"VAS_EMAIL","password":"VASE_HESLO"}'
```

Očekávaná úspěšná odpověď: JSON s `access_token`, `token_type` a `user`.
