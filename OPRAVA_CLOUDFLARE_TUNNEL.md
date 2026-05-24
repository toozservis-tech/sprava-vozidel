# Oprava Cloudflare Tunnel

## Problém
Port 8000 běžel (server běžel lokálně), ale aplikace nebyla dostupná přes web (Cloudflare error 1033). Důvod: **Cloudflare tunnel neběžel**.

## Řešení

### 1. Oprava Cloudflare Config

**Soubor:** `cloudflared/config.yml`
- ✅ Změněno `http://localhost:8000` na `http://127.0.0.1:8000` (konzistentní)

## Jak to funguje

1. **Spuštění aplikace:**
   - Server se spustí na `127.0.0.1:8000`
   - Cloudflare tunnel se spustí pomocí `start_cloudflare_tunnel.bat` nebo `scripts/windows/run_tunnel.ps1`

2. **Zastavení aplikace:**
   - Při zastavení serveru se zastaví i Cloudflare tunnel
   - Všechny procesy jsou správně ukončeny

## Testování

Pro otestování:

1. **Spustit server a tunnel:**
   ```powershell
   cd C:\Projects\sprava-vozidel
   .\scripts\windows\start_all.ps1
   ```

2. **Zkontrolovat, zda tunnel běží:**
   ```powershell
   tasklist | findstr cloudflared
   ```

3. **Otestovat web:**
   - Otevřít `https://hub.toozservis.cz/health` v prohlížeči
   - Mělo by vrátit JSON s `"status": "ok"`

4. **Zkontrolovat logy:**
   - `logs/tunnel_stdout.log` - stdout tunelu
   - `logs/tunnel_stderr.log` - stderr tunelu
   - `tunnel.log` - logy tunelu

## Důležité poznámky

- Tunnel se spustí pomocí startovacích skriptů
- Pokud cloudflared není nainstalován, tunnel se nespustí (ale server bude fungovat lokálně)
- Pokud config soubor neexistuje, tunnel se nespustí (ale server bude fungovat lokálně)

## Možné problémy a řešení

### Problém: Tunnel se nespustí
**Řešení:** Zkontrolujte:
1. Zda je cloudflared nainstalován: `where cloudflared.exe`
2. Zda existuje config soubor: `%USERPROFILE%\.cloudflared\config.yml` nebo `cloudflared\config.yml`
3. Logy: `logs/tunnel_stderr.log`

### Problém: Tunnel běží, ale web stále nefunguje
**Řešení:** Zkontrolujte:
1. DNS záznam v Cloudflare Dashboard (CNAME na tunnel hostname)
2. Config soubor - správný hostname a service URL
3. Zda server skutečně běží na `127.0.0.1:8000`

## Závěr

Cloudflare tunnel se spouští pomocí startovacích skriptů, takže aplikace bude dostupná přes web (`https://hub.toozservis.cz`).


