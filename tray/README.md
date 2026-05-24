# Správa vozidel – tray aplikace

Izolovaná tray aplikace pro monitorování a správu backend serveru.

## Funkce

- ✅ **Monitorování stavu serveru** - Ikona se mění podle stavu (zelená = běží, červená = neběží)
- ✅ **Rychlý přístup** - Otevření aplikace v prohlížeči
- ✅ **Správa serveru** - Spuštění, zastavení, restart serveru
- ✅ **Správa tunelu** - Spuštění, zastavení, restart Cloudflare Tunnel
- ✅ **Automatická kontrola** - Kontrola stavu každé 3 sekundy

## Instalace

### 1. Nainstalovat požadované balíčky

```bash
pip install pystray pillow requests
```

### 2. Spustit tray aplikaci

**Windows:**
```bash
tray\start_tray.bat
```

**Nebo přímo:**
```bash
python tray\tray_app.py
```

## Použití

1. Spusťte tray aplikaci pomocí `start_tray.bat`
2. Ikona se objeví v systémové liště (u hodin)
3. Pravým kliknutím na ikonu otevřete menu
4. Ikona se automaticky mění podle stavu serveru:
   - 🟢 **Zelená** - Server běží a odpovídá
   - 🔴 **Červená** - Server neběží nebo neodpovídá

## Menu

- **Otevřít aplikaci** - Otevře aplikaci v prohlížeči
- **Server** → Spustit/Zastavit/Restartovat
- **Tunnel** → Spustit/Zastavit/Restartovat
- **Ukončit** - Ukončí tray aplikaci

## Konfigurace

Konfigurace je v souboru `tray_app.py`:

```python
APP_NAME = "Správa vozidel"
HEALTH_URL = "http://127.0.0.1:8000/health"
OPEN_URL = "https://hub.toozservis.cz/web/index.html"
CHECK_INTERVAL = 3  # sekundy
```

## Autostart (volitelné)

Pro automatické spuštění při startu Windows:

1. Vytvořte zástupce `start_tray.bat`
2. Zkopírujte do složky `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`

Nebo použijte Task Scheduler pro pokročilejší nastavení.

## Řešení problémů

### Ikona se nezobrazuje
- Zkontrolujte, zda jsou nainstalované všechny balíčky: `pip install pystray pillow requests`
- Zkontrolujte, zda Python je v PATH

### Server se nespouští
- Zkontrolujte, zda existuje `scripts\windows\run_server.ps1`
- Zkontrolujte, zda port 8000 není obsazen

### Tunnel se nespouští
- Zkontrolujte, zda je nainstalován `cloudflared`
- Zkontrolujte, zda existuje `cloudflared\config.yml`

