# TooZ Mechanic — ChatGPT MCP plugin v0.1

## Cíl

TooZ Mechanic je pracovní MCP vrstva nad existujícím backendem Správa vozidel. Nezakládá paralelní databázi. Používá stejné modely vozidel, oprávnění servisu, servisní případy, měření práce, servisní historii a audit jako hlavní aplikace.

První verze je určená pro soukromé použití konkrétního servisního účtu. Veřejná katalogová verze musí před zveřejněním nahradit pevnou servisní identitu OAuth/OIDC identitou každého uživatele.

## Dílenský tok

1. `tooz_find_vehicle` — VIN/SPZ lookup. Bez schváleného VehicleServiceLink vrací pouze maskované identifikátory.
2. `tooz_vehicle_context` — technická data, historie, km a servisní případy schváleného vozidla.
3. `tooz_create_service_case` — vytvoří právě jeden otevřený servisní případ. Opakování vrátí existující případ.
4. `tooz_record_diagnosis` — uloží příznaky, DTC, naměřené hodnoty a závěr odděleně ve strukturovaném JSON.
5. `tooz_start_work` — spustí měření práce. Druhé spuštění nevytvoří paralelní session.
6. `tooz_stop_work` — zastaví měření a přepočítá celkový čas. Druhé zastavení je bezpečný no-op.
7. `tooz_finalize_service_record` — vytvoří jeden `service_verified` servisní záznam, přidá km a audit. Druhé volání vrátí původní record ID.

Pomocné nástroje: `tooz_status`, `tooz_my_vehicles`.

## GDPR a oprávnění

Vehicle data a owner data jsou oddělené. MCP vrstva nevrací jméno, telefon, e-mail ani adresu majitele.

Zápis do vozidla je povolen pouze tehdy, když existuje `VehicleServiceLink` ve stavu `approved`. Pro vytvoření servisního záznamu musí být navíc `scope_create_service_record=true`. Servis nemá přes MCP možnost měnit nebo mazat starší servisní historii.

VIN/SPZ lookup se zapisuje do `service_vehicle_lookup_audit`. Zápisy MCP zároveň vytvářejí `audit_log` události s korelačním ID.

## Soukromá identita v0.1

Nastavte v produkčním `.env`:

```env
CHATGPT_MCP_SERVICE_USER_ID=<ID servisního Customer účtu>
CHATGPT_MCP_HOST=127.0.0.1
CHATGPT_MCP_PORT=8011
```

`CHATGPT_MCP_SERVICE_USER_ID` musí ukazovat na aktivní účet s přístupem do servisního workspace.

Server v0.1 záměrně odmítne start na `0.0.0.0` nebo jiném veřejném bindu. Pevná identita nesmí být vystavena na veřejný internet.

## Instalace

Po nasazení větve / release:

```bash
cd /opt/toozhub2/app
source .venv/bin/activate
pip install -r requirements.txt
```

Ruční ověření serveru:

```bash
CHATGPT_MCP_SERVICE_USER_ID=<ID> \
CHATGPT_MCP_HOST=127.0.0.1 \
CHATGPT_MCP_PORT=8011 \
python -m src.plugins.chatgpt_mcp.server
```

MCP endpoint je lokálně:

```text
http://127.0.0.1:8011/mcp
```

Pro trvalý běh použijte `deploy/toozhub-chatgpt-mcp.service.example` jako základ systemd služby.

## Připojení k ChatGPT

Pro v0.1 nepřidávejte obyčejný veřejný Cloudflare hostname přímo na port 8011. Použijte Secure MCP Tunnel, aby lokální MCP endpoint nemusel být veřejně dostupný.

Po připojení v ChatGPT Developer Mode proveďte Scan Tools a ověřte všech 9 nástrojů. Zápisové funkce testujte nejdřív na testovacím vozidle.

## Testovací scénář

Minimální acceptance test:

```text
VIN/SPZ
→ schválené vozidlo
→ vytvořit servisní případ
→ uložit DTC + 2 měření
→ start práce
→ start práce znovu (nesmí vzniknout druhý timer)
→ stop práce
→ stop práce znovu (no-op)
→ dokončit servisní záznam
→ dokončit znovu (stejné record_id)
→ v DB právě 1 ServiceRecord + 1 VehicleMileage
→ audit obsahuje celý tok
```

Automatizovaný test je v `tests/api/test_chatgpt_mcp_service.py` a CI v `.github/workflows/chatgpt-mcp.yml`.

## Veřejná / placená verze

Před veřejným zveřejněním je nutné:

- OAuth/OIDC pro každého uživatele a mapování identity na `Customer`/tenant,
- refresh token / `offline_access`,
- veřejný HTTPS MCP endpoint s ověřením bearer tokenu,
- entitlement kontrola licence pro každý placený tool,
- privacy policy a podmínky použití,
- rate limiting per účet/tenant,
- revokace tokenu a session,
- testy cross-tenant izolace,
- odstranění `CHATGPT_MCP_SERVICE_USER_ID` z veřejného runtime flow.

Stávající `License` / `LicenseSubscription` a Comgate lifecycle lze použít jako zdroj tarifu; plugin nemá ukládat platební kartu.

## Definition of Done v0.1

- žádný nový paralelní vehicle/owner datastore,
- žádné owner PII ve výstupech MCP,
- žádný zápis bez aktivního VehicleServiceLink,
- žádná editace/smazání starší historie,
- idempotentní create case / start / stop / finalize,
- každý významný zápis auditovaný,
- server používá aktuální MCP SDK v2 a Streamable HTTP,
- server se nepustí na veřejný bind bez OAuth varianty,
- automatické testy pro GDPR, audit, revokaci oprávnění a dvojí volání.
