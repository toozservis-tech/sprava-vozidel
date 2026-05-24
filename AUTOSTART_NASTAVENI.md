# 🚀 Nastavení automatického startu - Správa vozidel

## 📋 Co bylo upraveno

### 1. ✅ Tray aplikace - automatický start serveru a tunelu

V `toozhub_tray_final.py` bylo zapnuto automatické spuštění serveru a tunelu při startu tray aplikace.

**Co se stane:**
- ✅ Při spuštění tray aplikace se automaticky spustí server (uvicorn)
- ✅ Po 2 sekundách se automaticky spustí tunnel (cloudflared)
- ✅ Status monitoring kontroluje stav každých 10 sekund

### 2. ✅ Nové funkce pro restart

Přidány funkce pro restart serveru a tunelu zvlášť:

- **🔄 Restartovat Server** - restartuje pouze FastAPI server
- **🔄 Restartovat Tunnel** - restartuje pouze Cloudflare Tunnel
- **🔄 Restartovat Vše** - restartuje server i tunel společně

### 3. ✅ Windows Task Scheduler - automatické spuštění při přihlášení

Vytvořen PowerShell skript pro přidání tray aplikace do Windows Task Scheduleru.

---

## 🎯 Jak nastavit automatický start

### Metoda 1: PowerShell skript (doporučeno)

**Instalace autostartu:**
```powershell
cd C:\Projects\sprava-vozidel
.\install_tray_autostart.ps1
```

**Odebrání autostartu:**
```powershell
.\uninstall_tray_autostart.ps1
```

**Co skript dělá:**
- ✅ Vytvoří úkol v Windows Task Scheduleru
- ✅ Nastaví spuštění při přihlášení do Windows
- ✅ Automaticky najde správný Python executable
- ✅ Spustí tray aplikaci na pozadí (bez oken)

---

### Metoda 2: Ruční přidání do Startup složky

1. Stisknout `Win + R`
2. Zadat: `shell:startup`
3. Vytvořit zástupce na `start_toozhub_tray.bat`
   - Nebo zkopírovat `start_toozhub_tray.bat` přímo do složky Startup

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
3. **Name:** `Správa vozidel Tray`
4. **Trigger:** **When I log on**
5. **Action:** **Start a program**
   - **Program:** `C:\Python312\pythonw.exe` (nebo vaše cesta k pythonw.exe)
   - **Arguments:** `"C:\Projects\sprava-vozidel\toozhub_tray_final.py"`
   - **Start in:** `C:\Projects\sprava-vozidel`
6. Finish

---

## ✅ Co se stane po nastavení autostartu

### Při každém přihlášení do Windows:

1. ✅ Windows Task Scheduler spustí tray aplikaci
2. ✅ Tray ikona se objeví v systémové liště (u hodin)
3. ✅ Automaticky se spustí server (uvicorn) na `http://127.0.0.1:8000`
4. ✅ Automaticky se spustí tunnel (cloudflared tooz-hub2)
5. ✅ Status monitoring začne kontrolovat stav každých 10 sekund
6. ✅ Ikona změní barvu podle stavu:
   - 🟢 **Zelená** - vše běží
   - 🟡 **Žlutá** - server běží, tunnel ne
   - 🔴 **Červená** - vše offline

---

## 🎮 Ovládání přes tray ikonu

### Pravým kliknutím na ikonu:

**Hlavní menu:**
- ▶ **Spustit Správa vozidel** - spustí server i tunel
- 🔄 **Restartovat Správa vozidel** - restartuje vše
- ⏹ **Zastavit Správa vozidel** - zastaví vše

**Nové submenu - Restart:**
- 🔄 **Restartovat Server** - restartuje pouze server
- 🔄 **Restartovat Tunnel** - restartuje pouze tunnel
- 🔄 **Restartovat Vše** - restartuje server i tunel

**Ostatní:**
- 🌐 **Web** - otevře lokální nebo produkční web
- 📚 **Dokumentace** - otevře FastAPI docs
- ❤️ **Health Check** - otevře health endpoint
- 🔄 **Obnovit status** - aktualizuje status ikony
- ❌ **Ukončit ikonu** - ukončí tray aplikaci a zastaví procesy

---

## 🔍 Kontrola, že vše funguje

### 1. Kontrola Task Scheduleru

```powershell
Get-ScheduledTask -TaskName "SpravaVozidel-Tray" | Format-List
```

Měl by zobrazit úkol s názvem `SpravaVozidel-Tray`.

### 2. Kontrola běžících procesů

```powershell
# Tray aplikace
Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*sprava-vozidel*" }

# Server
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*uvicorn*" }

# Tunnel
Get-Process cloudflared -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*tooz-hub2*" }
```

### 3. Test připojení

```powershell
# Lokální server
Invoke-WebRequest -Uri "http://127.0.0.1:8000/health"

# Produkční (přes tunnel)
Invoke-WebRequest -Uri "https://hub.toozservis.cz/health"
```

---

## ❌ Řešení problémů

### Tray ikona se nespustí

1. **Zkontrolovat, že Python je nainstalován:**
   ```powershell
   python --version
   pythonw --version
   ```

2. **Zkontrolovat závislosti:**
   ```powershell
   pip list | Select-String "requests"
   ```
   Pokud chybí:
   ```powershell
   pip install requests
   ```

3. **Zkontrolovat Task Scheduler:**
   - Otevřít Task Scheduler
   - Najít úkol `SpravaVozidel-Tray`
   - Zkontrolovat, že je povolený
   - Zkontrolovat historii spuštění (Last Run Result)

### Server nebo tunnel se nespustí

1. **Zkontrolovat logy:**
   - Server běží na pozadí, logy nejsou vidět
   - Zkontrolovat, jestli port 8000 není obsazený

2. **Zkontrolovat config soubor:**
   ```powershell
   Get-Content "C:\Users\djtoo\.cloudflared\config-hub.yml"
   ```

3. **Zkusit spustit ručně:**
   - Spustit tray aplikaci ručně a zkontrolovat menu

---

## 📋 Shrnutí

✅ **Automatický start serveru a tunelu** - zapnuto v tray aplikaci  
✅ **Funkce pro restart zvlášť** - přidány do menu  
✅ **Automatické spuštění při přihlášení** - přes Task Scheduler  
✅ **Notifikační ikona u hodin** - zobrazuje stav serveru a tunelu  
✅ **Background procesy** - vše běží na pozadí bez oken  

**Vše je připraveno!** 🎉


