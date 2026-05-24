# 🔴 KRITICKÉ: Restart serveru je nutný

## Situace

**✓ Kód je opravený:**
- Router `/api/v1/license/status` je správně zaregistrován
- Logy potvrzují: `[SERVER] ✓ /api/v1/license/status is registered in app`

**❌ Problém:**
- Starý server proces (PID 172776) běží jako **root** od 30.12.2025
- Uživatel `toozhub2` nemá oprávnění ukončit root proces
- Port 8000 je obsazený starým serverem
- Endpoint vrací **404**, protože server běží se starým kódem

## Řešení - vyberte jednu z možností:

### Možnost 1: Systemd restart (nejjednodušší)
```bash
sudo systemctl restart toozhub2
sudo systemctl status toozhub2
```

### Možnost 2: Ukončit jako root
```bash
# Jako root nebo s sudo:
sudo kill -9 172776

# Pak spustit nový server:
cd /opt/toozhub2/app
source .venv/bin/activate
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

### Možnost 3: Najít terminál/session root procesu
```bash
# Najít session:
ps -p 172776 -o tty=

# Pokud je to pts/0, najděte terminál a ukončete (Ctrl+C)
# Nebo použijte:
sudo pkill -9 -t pts/0
```

### Možnost 4: Ukončit vše na portu 8000 (sudo)
```bash
sudo fuser -k 8000/tcp
sleep 2
cd /opt/toozhub2/app
source .venv/bin/activate
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

## Ověření po restartu

```bash
# 1. Test endpointu (mělo by vrátit 401, ne 404):
curl -i http://127.0.0.1:8000/api/v1/license/status

# 2. Kontrola OpenAPI:
curl -s http://127.0.0.1:8000/openapi.json | grep "license/status"

# 3. Kontrola /docs:
# Otevřít http://127.0.0.1:8000/docs v prohlížeči
# Mělo by být vidět: GET /api/v1/license/status
```

## Očekávaný výsledek

Po restartu by mělo být:
- ✅ HTTP 401 (ne 404) při volání bez tokenu
- ✅ OpenAPI JSON obsahuje "license/status"
- ✅ Endpoint viditelný v `/docs`

**BEZ RESTARTU TO NEBUDE FUNGOVAT!**
