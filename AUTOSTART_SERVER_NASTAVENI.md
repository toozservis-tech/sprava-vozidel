# 🚀 Nastavení automatického startu serveru Správa vozidel

## 📋 Přehled

Tento dokument popisuje, jak nastavit automatické spuštění serveru Správa vozidel a Cloudflare Tunnel při každém startu PC.

## ✅ Co se stane po nastavení

Při každém přihlášení do Windows:
1. ✅ Automaticky se spustí FastAPI server na `http://0.0.0.0:8000`
2. ✅ Automaticky se spustí Cloudflare Tunnel (pokud je k dispozici)
3. ✅ Vše běží na pozadí bez oken
4. ✅ Logy se ukládají do `%TEMP%\toozhub2_*.log`

---

## 🎯 Instalace autostartu

### Metoda 1: PowerShell script - Task Scheduler (vyžaduje admin práva)

**Instalace:**
```powershell
# Spustit PowerShell jako správce (pravý klik -> Spustit jako správce)
cd C:\Projects\sprava-vozidel
.\install_server_autostart.ps1
```

**Odebrání:**
```powershell
.\uninstall_server_autostart.ps1
```

**Co script dělá:**
- ✅ Vytvoří úkol v Windows Task Scheduleru
- ✅ Nastaví spuštění při přihlášení do Windows
- ✅ Spustí server a tunnel na pozadí
- ✅ Logy se ukládají do `%TEMP%\toozhub2_*.log`

**Poznámka:** Pokud nemáte admin práva, použijte Metodu 2 (Startup složka).

---

### Metoda 2: PowerShell script - Startup složka (NENÍ potřeba admin práva) ⭐ DOPORUČENO

**Instalace:**
```powershell
cd C:\Projects\sprava-vozidel
.\install_server_autostart_startup.ps1
```

**Odebrání:**
```powershell
.\uninstall_server_autostart_startup.ps1
```

**Co script dělá:**
- ✅ Vytvoří zástupce v Startup složce
- ✅ Spustí se při každém přihlášení do Windows
- ✅ Nevyžaduje admin práva
- ✅ Jednodušší a spolehlivější

---

### Metoda 3: Ruční přidání do Startup složky

1. Stisknout `Win + R`
2. Zadat: `shell:startup`
3. Vytvořit zástupce na `start_server_background.bat`
   - Nebo zkopírovat `start_server_background.bat` přímo do složky Startup

**Výhody:**
- ✅ Jednoduché nastavení
- ✅ Snadné odebrání (smazat zástupce)

**Nevýhody:**
- ❌ Spouští se až po úplném načtení Windows
- ❌ Může být pomalejší

---

### Metoda 3: Ruční přidání do Task Scheduleru

1. Otevřít **Task Scheduler** (taskschd.msc)
2. Kliknout na **Create Basic Task**
3. **Name:** `SpravaVozidel-Server-Autostart`
4. **Trigger:** **When I log on**
5. **Action:** **Start a program**
   - **Program:** `C:\Projects\sprava-vozidel\start_server_background.bat`
   - **Start in:** `C:\Projects\sprava-vozidel`
6. **Settings:**
   - ✅ Allow task to be run on demand
   - ✅ Run task as soon as possible after a scheduled start is missed
   - ✅ If the task fails, restart every: 1 minute (max 3 times)
7. Finish

---

## 🔍 Kontrola, že vše funguje

### 1. Kontrola Task Scheduleru

```powershell
Get-ScheduledTask -TaskName "SpravaVozidel-Server-Autostart" | Format-List
```

Měl by zobrazit úkol s názvem `SpravaVozidel-Server-Autostart`.

### 2. Kontrola běžících procesů

```powershell
# Server
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*uvicorn*" }

# Tunnel
Get-Process cloudflared -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*tooz-hub2*" }
```

### 3. Kontrola portu 8000

```powershell
netstat -ano | findstr :8000
```

Měl by zobrazit, že port 8000 je v LISTENING stavu.

### 4. Test připojení

```powershell
# Lokální server
Invoke-WebRequest -Uri "http://localhost:8000/health"

# Produkční (přes tunnel)
Invoke-WebRequest -Uri "https://hub.toozservis.cz/health"
```

### 5. Kontrola logů

```powershell
# Autostart log
Get-Content "$env:TEMP\toozhub2_autostart.log" -Tail 20

# Server log
Get-Content "$env:TEMP\toozhub2_server.log" -Tail 20

# Tunnel log
Get-Content "$env:TEMP\toozhub2_tunnel.log" -Tail 20
```

---

## ❌ Řešení problémů

### Server se nespustí automaticky

1. **Zkontrolovat Task Scheduler:**
   - Otevřít Task Scheduler
   - Najít úkol `SpravaVozidel-Server-Autostart`
   - Zkontrolovat, že je povolený
   - Zkontrolovat historii spuštění (Last Run Result)
   - Zkontrolovat, zda není chyba v "Last Run Result"

2. **Zkontrolovat logy:**
   ```powershell
   Get-Content "$env:TEMP\toozhub2_autostart.log" -Tail 50
   ```

3. **Zkontrolovat, zda Python je v PATH:**
   ```powershell
   python --version
   where python.exe
   ```

4. **Zkusit spustit ručně:**
   ```powershell
   cd C:\Projects\sprava-vozidel
   .\start_server_background.bat
   ```

### Port 8000 je obsazen

1. **Najít proces na portu 8000:**
   ```powershell
   Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Get-Process -Id $_ }
   ```

2. **Zastavit proces:**
   ```powershell
   Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }
   ```

### Tunnel se nespustí

1. **Zkontrolovat, zda cloudflared je v PATH:**
   ```powershell
   where cloudflared.exe
   ```

2. **Zkontrolovat config soubor:**
   ```powershell
   Test-Path "$env:USERPROFILE\.cloudflared\config.yml"
   Get-Content "$env:USERPROFILE\.cloudflared\config.yml"
   ```

3. **Zkontrolovat credentials file:**
   ```powershell
   $config = Get-Content "$env:USERPROFILE\.cloudflared\config.yml"
   $credPath = ($config | Select-String "credentials-file:").ToString().Split(":")[1].Trim()
   Test-Path $credPath
   ```

### Server běží, ale není přístupný přes tunnel

1. **Zkontrolovat, zda tunnel běží:**
   ```powershell
   Get-Process cloudflared -ErrorAction SilentlyContinue
   ```

2. **Zkontrolovat DNS záznamy v Cloudflare:**
   - Otevřít Cloudflare Dashboard
   - Zkontrolovat DNS záznamy pro `hub.toozservis.cz`
   - Měl by být CNAME na `[tunnel-id].cfargotunnel.com`

3. **Zkontrolovat tunnel logy:**
   ```powershell
   Get-Content "$env:TEMP\toozhub2_tunnel.log" -Tail 50
   ```

---

## 📋 Související soubory

- `install_server_autostart.ps1` - Instalační script
- `uninstall_server_autostart.ps1` - Odinstalační script
- `start_server_background.bat` - Script pro spuštění na pozadí
- `start_server_with_tunnel.bat` - Alternativní script (s okny)
- `start_server_only.bat` - Script pouze pro server

---

## 🎮 Ovládání serveru

### Zastavení serveru

```powershell
# Najít a zastavit procesy
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*uvicorn*" } | Stop-Process -Force
Get-Process cloudflared -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*tooz-hub2*" } | Stop-Process -Force
```

### Restart serveru

1. Zastavit procesy (viz výše)
2. Spustit znovu: `.\start_server_background.bat`
3. Nebo počkat na automatický restart při příštím přihlášení

---

## 📋 Shrnutí

✅ **Automatické spuštění serveru** - při každém přihlášení do Windows  
✅ **Automatické spuštění tunelu** - pokud je k dispozici  
✅ **Background procesy** - vše běží na pozadí bez oken  
✅ **Logování** - logy v `%TEMP%\toozhub2_*.log`  
✅ **Automatický restart** - při selhání (max 3x)  

**Vše je připraveno!** 🎉








