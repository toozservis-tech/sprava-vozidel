# Backend – produkční deploy checklist (Service workspace / nové route)

Cíl: na serveru běží kód, kde existují `GET /api/v1/services/workspace/approved-vehicles`, `POST /api/v1/services/workspace/pending-vehicles` a `POST /api/v1/services/workspace/vehicle-lookup`, migrace DB jsou na `head`, OpenAPI je obsahuje a bez tokenu vracejí **401 nebo 403**, nikoli **404**.

**Důležité:** Endpointy musí být v **nasazeném** kódu. Pokud v checkoutu `grep` níže **nic nenajde**, samotný deploy **neodstraní 404** – je potřeba nejdřív sloučit branch s implementací handlerů.

---

# BACKEND DEPLOY – VÝSLEDEK

## 1. Před deployem checklist

### 1.1 Branch a commit

Na **build stroji** i **na serveru** (nebo v CI), ze stejného kořene aplikace:

```bash
cd /opt/toozhub2/app
git fetch origin
git status
git branch --show-current
git log -1 --oneline
```

Ověřte:

- čistý working tree (`git status` bez neočekávaných změn), nebo vědomé lokální patche;
- že `HEAD` odpovídá commitu, který má projít QA (tag / SHA z CI).

Volitelně shoda s remote:

```bash
git rev-parse HEAD
git rev-parse origin/<váš-produkční-branch>
```

### 1.2 Service workspace router je v buildu

```bash
cd /opt/toozhub2/app
grep -n "service_workspace" src/modules/vehicle_hub/routers_v1/__init__.py
```

Očekávání: řádek s `api_router.include_router(service_workspace.router)`.

Rychlá kontrola importu (spadne při chybě modulu):

```bash
cd /opt/toozhub2/app
source .venv/bin/activate   # nebo: . ../.venv/bin/activate podle vašeho layoutu
python -c "from src.modules.vehicle_hub.routers_v1 import service_workspace; print('ok', service_workspace.router.prefix)"
```

Očekávání: výstup obsahuje `/services/workspace`.

### 1.3 Kde v kódu ověřit nové route (povinné před nasazením)

Soubor: `src/modules/vehicle_hub/routers_v1/service_workspace.py`  
Prefix routeru: `/services/workspace` → plná cesta pod `/api/v1` je `/api/v1/services/workspace/...`.

```bash
cd /opt/toozhub2/app
grep -nE '@router\.(get|post|put|delete)\("/(approved-vehicles|pending-vehicles|vehicle-lookup)' src/modules/vehicle_hub/routers_v1/service_workspace.py
```

Webové klienty volají:

| Cesta | Metoda (dle web klienta) |
|-------|---------------------------|
| `/api/v1/services/workspace/approved-vehicles` | **GET** |
| `/api/v1/services/workspace/pending-vehicles` | **POST** |
| `/api/v1/services/workspace/vehicle-lookup` | **POST** |

`pending-vehicles` a `vehicle-lookup` jsou POST-only cesty. Pro sondu existence route pošlete minimální JSON tělo (`{}` nebo `{"query":"xx"}`) a očekávejte typicky `401`, `403` nebo `422`, ale **ne `404`**.

### 1.4 Migrace a tabulky

Konfigurace očekávaných tabulek modulu service workspace: `src/modules/vehicle_hub/schema_management.py` → klíč `"service_workspace"` (min. `service_customer_links`, `service_customer_invites`, `service_vehicle_access`, `service_document_ingestions`). Novější migrace mohou přidat další tabulky – vždy zkontrolujte nejnovější soubory v `alembic/versions/`.

**Skript `scripts/migrate_database.py`:** v některých checkoutech může chybět; odkazuje na něj např. `src/server/bootstrap.py`. Pokud soubor na serveru **není**, použijte přímo Alembic z adresáře `app/`:

```bash
cd /opt/toozhub2/app
source .venv/bin/activate
alembic current
alembic heads
alembic upgrade head
```

Ověření po upgrade:

```bash
alembic current
```

Mělo by odpovídat `heads` (jedna hlava, nebo vědomý merge).

Volitelně SQL kontrola existence tabulek (příklad pro PostgreSQL – upravte připojení):

```bash
# pouze pokud máte psql a známé jméno DB
psql "$DATABASE_URL" -c "\dt service_*"
```

### 1.5 Deploy artefakt není starý (cache, image, build)

- **Git:** `git log -1` na serveru = očekávaný commit.
- **Python:** po `git pull` znovu aktivovat stejnou `.venv` a při změně `requirements.txt` spustit `pip install -r requirements.txt`.
- **Docker (pokud platí):** `docker images` – zkontrolovat digest/tag buildu; po deployi `docker inspect <image>` – čas vytvoření; nepoužívat starý `:latest` bez rebuildu.
- **Systemd:** po výměně kódu vždy **restart** služby (viz §2), ne spoléhat se na starý běžící proces.
- **CDN / reverse proxy:** neměnit faktor „starý kód“ u API – ale u `openapi.json` může být agresivní cache; ověřte přímo na origin (`127.0.0.1`) nebo s hlavičkami proti cache.

---

## 2. Přesné deploy kroky (Hetzner / Linux, cesta `/opt/toozhub2/app`)

Předpoklad: aplikace žije v `/opt/toozhub2/app`, virtuální prostředí je k dispozici (často `/opt/toozhub2/.venv` nebo `/opt/toozhub2/app/.venv` – **ověřte u sebe**).

```bash
cd /opt/toozhub2/app
git pull origin <váš-produkční-branch>
```

Aktivace venv (zvolte existující cestu):

```bash
# varianta A
source /opt/toozhub2/.venv/bin/activate
# varianta B
source /opt/toozhub2/app/.venv/bin/activate
```

Závislosti (pokud se mění lock/requirements):

```bash
pip install -r requirements.txt
```

Migrace:

```bash
# pokud existuje váš wrapper:
# python scripts/migrate_database.py upgrade head

# jinak (doporučeno v tomto repozitáři):
alembic upgrade head
```

Restart backendu:

### Varianta A – ručně (např. test na serveru)

```bash
cd /opt/toozhub2/app
source <cesta-k-.venv>/bin/activate
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

### Varianta B – systemd

Název unit souboru si ověřte (příklad):

```bash
systemctl list-units --type=service | grep -i tooz
# nebo
systemctl status toozhub-backend.service
```

Restart a stav:

```bash
sudo systemctl restart toozhub-backend.service
sudo systemctl status toozhub-backend.service --no-pager
```

Logy:

```bash
sudo journalctl -u toozhub-backend.service -n 200 --no-pager
sudo journalctl -u toozhub-backend.service -f
```

Hledejte start bez tracebacku, ověřte že naslouchá na očekávaném portu (např. za nginxem stále `127.0.0.1:8000`).

---

## 3. Ověření pomocí curl

**Bez Authorization hlavičky** musí chráněné endpointy vrátit **401 nebo 403**, nikoli **404**. (Přesný kód závisí na `get_current_user` / politice API.)

### Health

```bash
curl -i http://127.0.0.1:8000/health
```

### Service workspace – základ + nové route

```bash
curl -i http://127.0.0.1:8000/api/v1/services/workspace/customers
curl -i http://127.0.0.1:8000/api/v1/services/workspace/approved-vehicles
curl -i -X POST http://127.0.0.1:8000/api/v1/services/workspace/pending-vehicles -H "Content-Type: application/json" -d '{}'
curl -i -X POST http://127.0.0.1:8000/api/v1/services/workspace/vehicle-lookup -H "Content-Type: application/json" -d '{"query":"xx"}'
```

Kontrola:

- HTTP **není** 404 na žádné z cest výše;
- bez tokenu typicky **401** nebo **403** (ne 404).

### OpenAPI

```bash
curl -s http://127.0.0.1:8000/openapi.json | grep -E 'approved-vehicles|pending-vehicles|vehicle-lookup'
```

Nebo přes `jq` (pokud je nainstalován):

```bash
curl -s http://127.0.0.1:8000/openapi.json | jq -r '.paths | keys[]' | grep -E 'approved-vehicles|pending-vehicles|vehicle-lookup'
```

**Musí** se objevit cesty (obvykle s prefixem `/api/v1/services/workspace/...`).

### Veřejná doména (Cloudflare)

```bash
curl -i "https://hub.toozservis.cz/api/v1/services/workspace/approved-vehicles"
```

Poznámka: může se lišit od přímého volání na `127.0.0.1` (WAF, HTML challenge). Pro rozhodnutí „je nový kód nasazený?“ má priorita **origin** na serveru.

---

## 4. Nejčastější chyby

| Problém | Projev | Co zkontrolovat |
|--------|--------|-----------------|
| Starý běžící proces | 404 na nových cestách i po `git pull` | `ps aux \| grep uvicorn`, PID, čas startu; systemd restart; ne dva procesy na stejném portu |
| Špatná / neaktivní `.venv` | ImportError, staré závislosti | `which python`, `pip -V`, znovu `pip install -r requirements.txt` ve správné venv |
| Migrace neproběhly | 500 při dotazu na nové tabulky / assert ve schématu | `alembic current` vs `alembic heads`, logy aplikace |
| Deploy do špatné složky | Změny v kódu se neprojeví | systemd `WorkingDirectory`, `ExecStart`, skutečný `pwd` v unit; ověřit `readlink -f` k běžícímu procesu |
| Cloudflare / proxy | 403 HTML, jiné chování než localhost | Porovnat curl na origin vs veřejnou URL; cookies u browseru |
| Starý systemd unit | Spouští jiný `uvicorn` nebo jiný root | `systemctl cat <service>.service`, cesty k `python` a modulu |
| Nasazený kód bez handlerů | 404 navždy | §1.3 – `grep` na `@router.get("/approved-vehicles"` atd. |

---

## 5. Jak poznám, že je backend opravdu hotový

Splněno **jen pokud současně** platí:

1. `curl` na `approved-vehicles`, `pending-vehicles`, `vehicle-lookup` **nezvrací 404** (bez tokenu: 401 nebo 403, případně 422 u lookup bez query – podle implementace, ale ne 404 „route neexistuje“).
2. V `openapi.json` jsou uvedené všechny tři cesty.
3. `alembic current` je na očekávané revizi po `upgrade head`.
4. Webový service workspace přestane detekovat **legacy** výhradně kvůli **404** na nových route (viz `SERVICE_WORKSPACE_WEB_STATUS.md`).
5. iOS klient přestane hlásit chybějící endpointy pro stejné cesty.

**Konečná pravda** je vždy odpověď **procesu, který skutečně obsluhuje produkční port** (systemd / reverse proxy → uvicorn), ne jen přítomnost souborů na disku.
