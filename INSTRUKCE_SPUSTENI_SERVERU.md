# Instrukce pro spuštění serveru sprava-vozidel

## Rychlý start

### 1. Spuštění pouze serveru (pro lokální vývoj)
```batch
.\start_server_only.bat
```

### 2. Spuštění serveru + Cloudflare Tunnel (pro produkci)
```batch
.\start_server_with_tunnel.bat
```

### 3. Manuální spuštění
```batch
python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8000
```

## Před spuštěním

### Kontrola portu 8000
```powershell
netstat -ano | findstr :8000
```
Pokud je port obsazen, zastavte proces:
```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }
```

### Kontrola závislostí
```powershell
pip install -r requirements.txt
```

### Kontrola .env souboru
```powershell
Test-Path .env
```
Pokud neexistuje, vytvořte ho podle `INSTRUKCE_PRO_ENV_SMTP.md`

## Cloudflare Tunnel

### Konfigurace
- Config soubor: `%USERPROFILE%\.cloudflared\config.yml`
- Credentials: `C:\Users\djtoo\.cloudflared\a8451dbb-2ca2-4006-862b-09959b274eb4.json`

### Spuštění tunelu samostatně
```batch
.\start_cloudflare_tunnel.bat
```

## Ověření funkčnosti

### 1. Health check
```powershell
curl http://localhost:8000/health
```

### 2. Root endpoint
```powershell
curl http://localhost:8000/
```

### 3. Webové rozhraní
Otevřete v prohlížeči: `http://localhost:8000/web/index.html`

## Řešení problémů

### Server se nespustí
1. Zkontrolujte, zda je port 8000 volný
2. Zkontrolujte, zda jsou nainstalované všechny závislosti
3. Zkontrolujte, zda existuje `.env` soubor
4. Spusťte diagnostiku: `python test_server_start.py`

### Tunnel se nespustí
1. Zkontrolujte, zda existuje config v `%USERPROFILE%\.cloudflared\config.yml`
2. Zkontrolujte, zda existuje credentials file
3. Zkontrolujte, zda je `cloudflared.exe` v PATH

### Server běží, ale není přístupný přes tunnel
1. Zkontrolujte, zda tunnel běží
2. Zkontrolujte DNS záznamy v Cloudflare
3. Zkontrolujte, zda je hostname správně nastaven v config

## Logy a diagnostika

### Zobrazení logů serveru
Server vypisuje logy přímo do konzole. Pro detailnější logy:
```batch
python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8000 --log-level debug
```

### Diagnostický script
```batch
python test_server_start.py
```

## Produkční nasazení

1. Nastavte `ENVIRONMENT=production` v `.env`
2. Nastavte `JWT_SECRET_KEY` na bezpečnou hodnotu
3. Nastavte `PUBLIC_API_BASE_URL=https://hub.toozservis.cz`
4. Spusťte `start_server_with_tunnel.bat`
5. Ověřte funkčnost na `https://hub.toozservis.cz/health`








