# Restart Serveru - Pokyny

## Aktuální stav

**✓ Router je správně zaregistrován:**
- Logy ukazují: `[ROUTERS_V1] ✓ License status router zaregistrován (prefix: /license)`
- `[SERVER] ✓ /api/v1/license/status is registered in app`

**❌ Problém:** Starý server proces (PID 172776) stále běží a blokuje port 8000.

## Řešení - Restart serveru

### Možnost 1: Ruční restart (doporučeno)

1. **Najděte terminál/session, kde běží starý server:**
   ```bash
   ps aux | grep 172776
   ```
   Proces běží v session `pts/0` (možná v jiném SSH terminálu)

2. **Ukončete starý proces:**
   - Najděte terminál, kde běží server
   - Stiskněte `Ctrl+C` k ukončení
   - Nebo: `kill 172776` (pokud máte oprávnění)

3. **Spusťte nový server:**
   ```bash
   cd /opt/toozhub2/app
   /opt/toozhub2/app/.venv/bin/python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000
   ```

### Možnost 2: Použití systemd service

```bash
# Pokud je service nakonfigurován:
sudo systemctl restart toozhub2
sudo systemctl status toozhub2
```

### Možnost 3: Použití fuser (pokud máte sudo)

```bash
sudo fuser -k 8000/tcp
sleep 2
cd /opt/toozhub2/app
/opt/toozhub2/app/.venv/bin/python -m uvicorn src.server.main:app --host 127.0.0.1 --port 8000 &
```

## Ověření po restartu

Po restartu serveru byste měli vidět v logu:
```
[ROUTERS_V1] ✓ License status router zaregistrován (prefix: /license)
[SERVER] Found license routes in v1_api_router: ['GET /api/v1/license/status']
[SERVER] ✓ /api/v1/license/status is registered in app
```

Poté otestujte:
```bash
# 1. Bez tokenu (očekáváno 401, ne 404)
curl -i http://127.0.0.1:8000/api/v1/license/status

# 2. Kontrola OpenAPI
curl -s http://127.0.0.1:8000/openapi.json | grep "license/status"
```

## Očekávané výsledky

- ✓ HTTP 401 (ne 404) při volání bez tokenu
- ✓ OpenAPI JSON obsahuje "license/status"
- ✓ Endpoint je viditelný v `/docs`
