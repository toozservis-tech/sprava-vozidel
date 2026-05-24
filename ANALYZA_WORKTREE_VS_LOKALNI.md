# Analýza: Worktree vs. Lokální složka

## Shrnutí

Po analýze projektu sprava-vozidel bylo zjištěno, že **server by měl fungovat v obou prostředích** (worktree i hlavní složka), protože:

1. **Struktura souborů je identická** - obě složky obsahují stejné soubory
2. **Kód je stejný** - žádné rozdíly v klíčových souborech
3. **Konfigurace je sdílená** - `.env` a `VERSION.py` jsou stejné

## Zjištěné skutečnosti

### 1. Worktree umístění
- **Hlavní repository**: `C:\Projects\sprava-vozidel`
- **Worktree**: `C:\Users\djtoo\.cursor\worktrees\sprava-vozidel\vda`
- **Commit**: Oba na stejném commitu `41674d0`

### 2. Struktura souborů
- ✅ `src/server/main.py` - existuje v obou
- ✅ `src/core/config.py` - existuje v obou
- ✅ `VERSION.py` - existuje v obou
- ✅ `requirements.txt` - existuje v obou
- ✅ `.env` - existuje v obou (pokud je nastaven)

### 3. Python prostředí
- Oba používají stejný Python interpreter (systémový)
- Stejné balíčky by měly být nainstalované

## Možné příčiny problémů

### 1. **Port 8000 může být obsazen**
- Pokud server běží ve worktree, port 8000 je obsazen
- Řešení: Zastavit server ve worktree před spuštěním v hlavní složce

### 2. **Chybějící závislosti**
- V hlavní složce mohou chybět některé Python balíčky
- Řešení: Spustit `pip install -r requirements.txt`

### 3. **Chybějící .env soubor**
- Konfigurace může být jiná nebo chybět
- Řešení: Zkontrolovat a synchronizovat `.env` soubor

### 4. **Cloudflare Tunnel konfigurace**
- Config musí být v `%USERPROFILE%\.cloudflared\config.yml`
- Credentials file musí existovat

## Řešení

### Krok 1: Zkontrolovat, zda server běží
```powershell
netstat -ano | findstr :8000
```

### Krok 2: Zastavit všechny instance serveru
```powershell
# Najít a zastavit procesy na portu 8000
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }
```

### Krok 3: Nainstalovat závislosti (pokud chybí)
```powershell
cd C:\Projects\sprava-vozidel
pip install -r requirements.txt
```

### Krok 4: Zkontrolovat .env soubor
```powershell
# Zkontrolovat, zda existuje
Test-Path .env

# Pokud neexistuje, vytvořit z template nebo zkopírovat z worktree
```

### Krok 5: Spustit server
```powershell
# Varianta 1: Pouze server
.\start_server_only.bat

# Varianta 2: Server + Cloudflare Tunnel
.\start_server_with_tunnel.bat

# Varianta 3: Manuálně
python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8000
```

## Vytvořené scripty

### 1. `start_server_only.bat`
- Spouští pouze FastAPI server
- Kontroluje port 8000
- Vhodné pro lokální vývoj

### 2. `start_server_with_tunnel.bat`
- Spouští server na pozadí
- Spouští Cloudflare Tunnel
- Vhodné pro produkci

### 3. `test_server_start.py`
- Diagnostický script pro testování
- Kontroluje všechny závislosti a konfiguraci

## Cloudflare Tunnel konfigurace

### Umístění config souboru
- **Lokální (projekt)**: `cloudflared\config.yml`
- **Systémový (používaný)**: `%USERPROFILE%\.cloudflared\config.yml`

### Obsah config souboru
```yaml
tunnel: tooz-hub2
credentials-file: C:\Users\djtoo\.cloudflared\a8451dbb-2ca2-4006-862b-09959b274eb4.json

ingress:
  - hostname: hub.toozservis.cz
    service: http://localhost:8000
  - service: http_status:404
```

### Důležité poznámky
- ✅ Config soubor byl zkopírován do `%USERPROFILE%\.cloudflared\config.yml`
- ⚠️ Credentials file musí existovat na cestě uvedené v config
- ⚠️ Pokud credentials file neexistuje, tunnel nebude fungovat

## Doporučení

1. **Používat hlavní složku** (`C:\Projects\sprava-vozidel`) jako primární workspace
2. **Worktree používat pouze pro dočasné experimenty**
3. **Před spuštěním serveru vždy zkontrolovat port 8000**
4. **Synchronizovat .env soubor** mezi prostředími (bez commitu tajných klíčů)
5. **Používat vytvořené .bat scripty** pro snadné spuštění

## Závěr

**Server by měl fungovat v hlavní složce stejně jako ve worktree.** Pokud nefunguje, pravděpodobně jde o:
- Obsazený port 8000
- Chybějící závislosti
- Chybějící nebo nesprávná konfigurace

Všechny tyto problémy lze vyřešit pomocí kroků uvedených výše.








