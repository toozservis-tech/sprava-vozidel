#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Správa vozidel – izolovaná tray aplikace
Samostatná tray ikonka pro monitorování a správu serveru.
"""

import sys
import os
import time
import threading
import subprocess
import webbrowser
from pathlib import Path

# Přidání root projektu do Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    import requests
except ImportError as e:
    print(f"[ERROR] Chybí požadované balíčky: {e}")
    print("[INFO] Spusťte: pip install pystray pillow requests")
    sys.exit(1)

# =============================================================================
# KONFIGURACE
# =============================================================================

APP_NAME = "Správa vozidel"
HEALTH_URL = "http://127.0.0.1:8000/health"
OPEN_URL = "https://hub.toozservis.cz/web/index.html"
CHECK_INTERVAL = 3  # sekundy

# Cesty ke skriptům
SERVER_SCRIPT = project_root / "scripts" / "windows" / "run_server.ps1"
TUNNEL_SCRIPT = project_root / "scripts" / "windows" / "run_tunnel.ps1"

# =============================================================================
# GLOBÁLNÍ PROMĚNNÉ
# =============================================================================

icon = None
running = True
update_thread = None
server_process = None
tunnel_process = None

# =============================================================================
# VYTVOŘENÍ IKON
# =============================================================================

def create_icon_image(color, size=64):
    """
    Vytvoří ikonu pro tray s lepším designem.
    
    Args:
        color: Tuple (R, G, B) nebo název barvy ('green', 'red', 'yellow')
        size: Velikost ikony v pixelech (default 64)
    
    Returns:
        PIL.Image: Ikona
    """
    # Definice barev
    colors = {
        'green': (76, 175, 80),      # Zelená - server běží
        'red': (244, 67, 54),        # Červená - server neběží
        'yellow': (255, 193, 7),     # Žlutá - kontrola
    }
    
    if isinstance(color, str):
        color = colors.get(color, colors['red'])
    
    # Vytvořit obrázek s průhledným pozadím
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Vykreslit kruh s gradient efektem (tmavší okraj, světlejší střed)
    center = size // 2
    radius = size // 2 - 4
    
    # Vnější kruh (tmavší)
    draw.ellipse(
        [center - radius, center - radius, center + radius, center + radius],
        fill=color,
        outline=(max(0, color[0] - 30), max(0, color[1] - 30), max(0, color[2] - 30)),
        width=2
    )
    
    # Vnitřní kruh (světlejší) pro 3D efekt
    inner_radius = radius - 4
    if inner_radius > 0:
        lighter_color = (
            min(255, color[0] + 30),
            min(255, color[1] + 30),
            min(255, color[2] + 30)
        )
        draw.ellipse(
            [center - inner_radius, center - inner_radius, 
             center + inner_radius, center + inner_radius],
            fill=lighter_color,
            outline=None
        )
    
    # Převést na 16x16 pro tray (Windows vyžaduje menší ikony)
    if size != 16:
        image = image.resize((16, 16), Image.Resampling.LANCZOS)
    
    return image

# Vytvořit ikony
ICON_OK = create_icon_image('green')
ICON_ERR = create_icon_image('red')
ICON_CHECK = create_icon_image('yellow')

# =============================================================================
# KONTROLA STAVU SERVERU
# =============================================================================

def check_server_health():
    """
    Zkontroluje stav serveru přes /health endpoint.
    
    Returns:
        tuple: (bool, str) - (je_zdravý, zpráva)
    """
    try:
        response = requests.get(HEALTH_URL, timeout=3)
        if response.status_code == 200:
            data = response.json()
            version = data.get('version', '?')
            return True, f"Server běží (v{version})"
        else:
            return False, f"Server odpovídá s chybou: {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Server neběží (nelze se připojit)"
    except requests.exceptions.Timeout:
        return False, "Server neodpovídá (timeout)"
    except requests.exceptions.RequestException as e:
        return False, f"Chyba připojení: {str(e)}"
    except Exception as e:
        return False, f"Chyba: {str(e)}"

# =============================================================================
# SPRÁVA PROCESŮ
# =============================================================================

def start_server():
    """Spustí server přímo pomocí Pythonu."""
    global server_process
    
    try:
        # Zkontrolovat, zda existuje venv
        python_exe = "python"
        venv_python = project_root / "venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            python_exe = str(venv_python)
        
        # Spustit uvicorn přímo
        server_process = subprocess.Popen(
            [
                python_exe,
                "-m", "uvicorn",
                "src.server.main:app",
                "--host", "127.0.0.1",
                "--port", "8000"
            ],
            cwd=str(project_root),
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL
        )
        print(f"[INFO] Server spuštěn (PID: {server_process.pid})")
        # Počkat chvíli, aby se server spustil
        time.sleep(2)
        return True
    except Exception as e:
        print(f"[ERROR] Chyba při spouštění serveru: {e}")
        import traceback
        traceback.print_exc()
        return False

def start_tunnel():
    """Spustí Cloudflare Tunnel přímo."""
    global tunnel_process
    
    try:
        # Zkontrolovat, zda je cloudflared nainstalován
        import shutil
        cloudflared_exe = shutil.which("cloudflared")
        if not cloudflared_exe:
            print("[ERROR] cloudflared.exe nebyl nalezen v PATH!")
            return False
        
        # Zkontrolovat config soubor
        config_file = project_root / "cloudflared" / "config.yml"
        if not config_file.exists():
            config_file = Path.home() / ".cloudflared" / "config.yml"
            if not config_file.exists():
                print(f"[ERROR] Config soubor neexistuje: {config_file}")
                return False
        
        # Zkontrolovat název tunelu z config souboru
        tunnel_name = "tooz-hub2"  # default
        try:
            try:
                import yaml
            except ImportError:
                # Pokud yaml není nainstalován, použít default
                yaml = None
            
            if yaml:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    if config and 'tunnel' in config:
                        tunnel_name = config['tunnel']
        except:
            pass  # použít default
        
        # Spustit cloudflared tunnel přímo
        tunnel_process = subprocess.Popen(
            [
                cloudflared_exe,
                "tunnel",
                "--config", str(config_file),
                "run", tunnel_name
            ],
            cwd=str(project_root),
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL
        )
        print(f"[INFO] Tunnel spuštěn (PID: {tunnel_process.pid})")
        # Počkat chvíli, aby se tunnel spustil
        time.sleep(2)
        return True
    except Exception as e:
        print(f"[ERROR] Chyba při spouštění tunelu: {e}")
        import traceback
        traceback.print_exc()
        return False

def stop_server():
    """Zastaví server."""
    global server_process
    
    try:
        # Najít procesy uvicorn na portu 8000
        result = subprocess.run(
            ["powershell.exe", "-Command", 
             "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | "
             "Select-Object -ExpandProperty OwningProcess | "
             "ForEach-Object { Stop-Process -Id $_ -Force }"],
            capture_output=True,
            text=True
        )
        server_process = None
        print("[INFO] Server zastaven")
        return True
    except Exception as e:
        print(f"[ERROR] Chyba při zastavování serveru: {e}")
        return False

def stop_tunnel():
    """Zastaví Cloudflare Tunnel."""
    global tunnel_process
    
    try:
        result = subprocess.run(
            ["powershell.exe", "-Command", 
             "Get-Process cloudflared -ErrorAction SilentlyContinue | "
             "Stop-Process -Force"],
            capture_output=True,
            text=True
        )
        tunnel_process = None
        print("[INFO] Tunnel zastaven")
        return True
    except Exception as e:
        print(f"[ERROR] Chyba při zastavování tunelu: {e}")
        return False

# =============================================================================
# CALLBACK FUNKCE PRO MENU
# =============================================================================

def on_open_app():
    """Otevře aplikaci v prohlížeči."""
    try:
        webbrowser.open(OPEN_URL)
        print(f"[INFO] Otevřena aplikace: {OPEN_URL}")
    except Exception as e:
        print(f"[ERROR] Chyba při otevírání aplikace: {e}")

def on_restart_server():
    """Restartuje server."""
    global icon
    print("[INFO] Restartování serveru...")
    stop_server()
    time.sleep(2)
    if start_server():
        print("[INFO] Server restartován, čekám na spuštění...")
        # Počkat, až se server spustí (max 10 sekund)
        for i in range(10):
            time.sleep(1)
            is_healthy, status_msg = check_server_health()
            if is_healthy:
                print(f"[OK] Server úspěšně restartován: {status_msg}")
                # Aktualizovat menu
                if icon:
                    icon.menu = create_menu()
                break
        else:
            print("[WARNING] Server se možná nespustil, zkontrolujte logy")
            # Aktualizovat menu i když se server nespustil
            if icon:
                icon.menu = create_menu()
    else:
        print("[ERROR] Nepodařilo se restartovat server")
        # Aktualizovat menu
        if icon:
            icon.menu = create_menu()

def on_restart_tunnel():
    """Restartuje Cloudflare Tunnel."""
    print("[INFO] Restartování tunelu...")
    stop_tunnel()
    time.sleep(2)
    start_tunnel()

def on_start_server():
    """Spustí server."""
    global icon
    print("[INFO] Spouštění serveru...")
    if start_server():
        print("[INFO] Server spuštěn, čekám na inicializaci...")
        # Počkat, až se server spustí (max 10 sekund)
        for i in range(10):
            time.sleep(1)
            is_healthy, status_msg = check_server_health()
            if is_healthy:
                print(f"[OK] Server úspěšně spuštěn: {status_msg}")
                # Aktualizovat menu
                if icon:
                    icon.menu = create_menu()
                break
        else:
            print("[WARNING] Server se možná nespustil, zkontrolujte logy")
            # Aktualizovat menu i když se server nespustil
            if icon:
                icon.menu = create_menu()
    else:
        print("[ERROR] Nepodařilo se spustit server")
        # Aktualizovat menu
        if icon:
            icon.menu = create_menu()

def on_start_tunnel():
    """Spustí Cloudflare Tunnel."""
    print("[INFO] Spouštění tunelu...")
    start_tunnel()

def on_stop_server():
    """Zastaví server."""
    global icon
    print("[INFO] Zastavování serveru...")
    if stop_server():
        print("[OK] Server zastaven")
        # Aktualizovat menu
        if icon:
            icon.menu = create_menu()
    else:
        print("[ERROR] Nepodařilo se zastavit server")
        # Aktualizovat menu
        if icon:
            icon.menu = create_menu()

def on_stop_tunnel():
    """Zastaví Cloudflare Tunnel."""
    print("[INFO] Zastavování tunelu...")
    stop_tunnel()

def on_quit():
    """Ukončí tray aplikaci."""
    global running, icon
    print("[INFO] Ukončování tray aplikace...")
    running = False
    if icon:
        icon.stop()

# =============================================================================
# AKTUALIZACE IKONY
# =============================================================================

def update_icon_loop():
    """Vlákno, které pravidelně aktualizuje ikonu podle stavu serveru."""
    global icon, running
    
    last_status = None
    consecutive_failures = 0
    auto_start_attempted = False
    
    while running:
        try:
            if icon:
                is_healthy, status_msg = check_server_health()
                
                # Počítat po sobě jdoucí selhání
                if is_healthy:
                    consecutive_failures = 0
                    auto_start_attempted = False
                else:
                    consecutive_failures += 1
                    
                    # Pokud server neběží 3x po sobě, zkusit ho spustit (pouze jednou)
                    if consecutive_failures >= 3 and not auto_start_attempted:
                        print("[INFO] Server neběží, pokouším se ho spustit...")
                        if start_server():
                            auto_start_attempted = True
                            time.sleep(5)  # Počkat, než se server spustí
                            # Znovu zkontrolovat stav
                            is_healthy, status_msg = check_server_health()
                
                # Aktualizovat ikonu pouze pokud se stav změnil
                if is_healthy != last_status:
                    new_icon = ICON_OK if is_healthy else ICON_ERR
                    icon.icon = new_icon
                    last_status = is_healthy
                    if is_healthy:
                        print(f"[INFO] Server je nyní dostupný: {status_msg}")
                    # Aktualizovat menu při změně stavu
                    icon.menu = create_menu()
                
                # Aktualizovat tooltip
                icon.title = f"{APP_NAME}\nStatus: {status_msg}"
                
        except Exception as e:
            print(f"[ERROR] Chyba při aktualizaci ikony: {e}")
        
        time.sleep(CHECK_INTERVAL)

# =============================================================================
# VYTVOŘENÍ MENU
# =============================================================================

def create_menu():
    """Vytvoří menu pro tray ikonu."""
    is_healthy, status_msg = check_server_health()
    
    menu_items = [
        pystray.MenuItem(APP_NAME, lambda: None, enabled=False),
        pystray.MenuItem(f"Status: {status_msg}", lambda: None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Otevřít aplikaci", lambda: on_open_app()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Server", pystray.Menu(
            pystray.MenuItem("Spustit", lambda: on_start_server()),
            pystray.MenuItem("Zastavit", lambda: on_stop_server()),
            pystray.MenuItem("Restartovat", lambda: on_restart_server()),
        )),
        pystray.MenuItem("Tunnel", pystray.Menu(
            pystray.MenuItem("Spustit", lambda: on_start_tunnel()),
            pystray.MenuItem("Zastavit", lambda: on_stop_tunnel()),
            pystray.MenuItem("Restartovat", lambda: on_restart_tunnel()),
        )),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Ukončit", lambda: on_quit()),
    ]
    
    return pystray.Menu(*menu_items)

# =============================================================================
# HLAVNÍ FUNKCE
# =============================================================================

def run_tray():
    """Spustí tray aplikaci."""
    global icon, update_thread
    
    print(f"[INFO] Spouštím {APP_NAME} Tray...")
    print(f"[INFO] Health check URL: {HEALTH_URL}")
    print(f"[INFO] Open URL: {OPEN_URL}")
    print(f"[INFO] Kontrola každých {CHECK_INTERVAL} sekund")
    print("")
    
    # Vytvořit menu
    menu = create_menu()
    
    # Vytvořit ikonu (začínáme s červenou - kontrola proběhne v threadu)
    icon = pystray.Icon(
        APP_NAME,
        ICON_ERR,
        f"{APP_NAME}\nKontroluji stav...",
        menu=menu
    )
    
    # Spustit vlákno pro aktualizaci ikony
    update_thread = threading.Thread(target=update_icon_loop, daemon=True)
    update_thread.start()
    
    print("[INFO] Tray ikona je v systémové liště (u hodin)")
    print("[INFO] Pro ukončení klikněte pravým tlačítkem na ikonu a vyberte 'Ukončit'")
    print("")
    
    # Spustit tray (blokující volání)
    try:
        icon.run()
    except Exception as e:
        print(f"[ERROR] Chyba při spouštění tray: {e}")
        import traceback
        traceback.print_exc()

# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    try:
        run_tray()
    except KeyboardInterrupt:
        print("\n[INFO] Ukončeno uživatelem (Ctrl+C)")
        on_quit()
    except Exception as e:
        print(f"[ERROR] Kritická chyba: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

