# 🔴 DŮLEŽITÉ: Server musí být restartován

## Problém
Server **stále běží se starým kódem** (PID 172776 spuštěn v 10:44).

Kód je správně - router JE zaregistrován:
- ✅ `['GET'] /api/v1/license/status` je v seznamu routes
- ✅ Router má správné prefixy
- ❌ **ALE:** Běžící server tento endpoint nevidí, protože běží ze starého kódu

## Řešení

### Možnost 1: Použít restart skript
```bash
/tmp/restart_server.sh
```

### Možnost 2: Ruční restart
```bash
# 1. Ukončit starý proces
kill -9 172776
# NEBO najít terminál kde běží a stisknout Ctrl+C

# 2. Spustit nový server
cd /opt/toozhub2/app
source .venv/bin/activate
python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
```

### Možnost 3: Systemd service
```bash
sudo systemctl restart toozhub2
```

## Ověření po restartu
```bash
# Mělo by vrátit 401 (ne 404):
curl -i http://127.0.0.1:8000/api/v1/license/status

# Mělo by najít endpoint:
curl -s http://127.0.0.1:8000/openapi.json | grep "license/status"
```

**BEZ RESTARTU TO NEBUDE FUNGOVAT!**
