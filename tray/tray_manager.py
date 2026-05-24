#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Správa vozidel – System Tray Manager
Zobrazuje stav serveru v systémové liště a umožňuje rychlý restart serveru nebo tunelu.
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
    from PIL import Image, ImageDraw
    import requests
except ImportError as e:
    print(f"[ERROR] Chybí požadované balíčky: {e}")
    print("[INFO] Spusťte: pip install pystray pillow requests")
    sys.exit(1)

# =============================================================================
# KONFIGURACE PROJEKTU
# =============================================================================

PROJECT_NAME = "sprava-vozidel"
TRAY_APP_NAME = "Správa vozidel – tray"
TRAY_SHORTCUT_NAME = "SpravaVozidel_tray.lnk"

# URL konfigurace
HEALTH_URL = "http://127.0.0.1:8000/health"
OPEN_URL = "https://hub.toozservis.cz/"

# Cesty ke skriptům (relativní k root projektu)
RUN_SERVER_SCRIPT = r"scripts\windows\run_server.ps1"
RUN_TUNNEL_SCRIPT = r"scripts\windows\run_tunnel.ps1"

# =============================================================================
# GLOBÁLNÍ PROMĚNNÉ
# =============================================================================

icon = None
server_process = None
tunnel_process = None
update_thread = None
running = True

# =============================================================================
# FUNKCE PRO VYTVOŘENÍ IKON
# =============================================================================

def create_icon(color):
    """
    Vytvoří ikonu pro tray (kruh v dané barvě).
    
    Args:
        color: Tuple (R, G, B) nebo název barvy
        
    Returns:
        PIL.Image: Ikona 16x16 pixelů
    """
    # Definice barev
    colors = {
        'green': (76, 175, 80),
        'red': (244, 67, 54),
        'yellow': (255, 193, 7),
    }
    
    if isinstance(color, str):
        color = colors.get(color, colors['red'])
    
    # Vytvořit obrázek 16x16
    image = Image.new('RGB', (16, 16), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    # Nakreslit kruh
    draw.ellipse([2, 2, 14, 14], fill=color, outline=(0, 0, 0), width=1)
    
    return image

ICON_OK = create_icon('green')
ICON_ERR = create_icon('red')

# =============================================================================
# FUNKCE PRO KONTROLU STAVU
# =============================================================================

def check_health():
    """
    Zkontroluje stav serveru přes /health endpoint.
    
    Returns:
        bool: True pokud server běží a odpovídá, False jinak
    """
    try:
        response = requests.get(HEALTH_URL, timeout=1.5)
        return response.status_code == 200
    except (requests.RequestException, Exception):
        return False

# =============================================================================
# FUNKCE PRO SPOUŠTĚNÍ PROCESŮ
# =============================================================================

def run_server():
    """Spustí server pomocí PowerShell skriptu."""
    global server_process
    
    try:
        script_path = project_root / RUN_SERVER_SCRIPT
        if not script_path.exists():
            print(f"[ERROR] Server skript neexistuje: {script_path}")
            return
        
        server_process = subprocess.Popen(
            [
                "powershell.exe",
                "-ExecutionPolicy", "Bypass",
                "-File", str(script_path)
            ],
            cwd=str(project_root),
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        print(f"[INFO] Server spuštěn (PID: {server_process.pid})")
    except Exception as e:
        print(f"[ERROR] Chyba při spouštění serveru: {e}")

def run_tunnel():
    """Spustí Cloudflare Tunnel pomocí PowerShell skriptu."""
    global tunnel_process
    
    try:
        script_path = project_root / RUN_TUNNEL_SCRIPT
        if not script_path.exists():
            print(f"[ERROR] Tunnel skript neexistuje: {script_path}")
            return
        
        tunnel_process = subprocess.Popen(
            [
                "powershell.exe",
                "-ExecutionPolicy", "Bypass",
                "-File", str(script_path)
            ],
            cwd=str(project_root),
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        print(f"[INFO] Tunnel spuštěn (PID: {tunnel_process.pid})")
    except Exception as e:
        print(f"[ERROR] Chyba při spouštění tunelu: {e}")

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
    print("[INFO] Restartování serveru...")
    run_server()

def on_restart_tunnel():
    """Restartuje Cloudflare Tunnel."""
    print("[INFO] Restartování tunelu...")
    run_tunnel()

def on_quit():
    """Ukončí tray aplikaci."""
    global running, icon
    print("[INFO] Ukončování tray aplikace...")
    running = False
    if icon:
        icon.stop()

# =============================================================================
# FUNKCE PRO AKTUALIZACI IKONY
# =============================================================================

def update_icon_loop():
    """Vlákno, které pravidelně aktualizuje ikonu podle stavu serveru."""
    global icon, running
    
    while running:
        try:
            if icon:
                is_healthy = check_health()
                new_icon = ICON_OK if is_healthy else ICON_ERR
                icon.icon = new_icon
                status_text = "Běží" if is_healthy else "Nedostupný"
                icon.title = f"{TRAY_APP_NAME}\nStatus: {status_text}"
        except Exception as e:
            print(f"[ERROR] Chyba při aktualizaci ikony: {e}")
        
        time.sleep(3)

# =============================================================================
# HLAVNÍ FUNKCE
# =============================================================================

def create_menu():
    """Vytvoří menu pro tray ikonu."""
    menu_items = [
        pystray.MenuItem(f"{PROJECT_NAME}", lambda: None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Otevřít aplikaci", lambda: on_open_app()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Restart serveru", lambda: on_restart_server()),
        pystray.MenuItem("Restart tunelu", lambda: on_restart_tunnel()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Ukončit", lambda: on_quit()),
    ]
    return pystray.Menu(*menu_items)

def run_tray():
    """Spustí tray aplikaci."""
    global icon, update_thread
    
    print(f"[INFO] Spouštím {TRAY_APP_NAME}...")
    print(f"[INFO] Health check URL: {HEALTH_URL}")
    print(f"[INFO] Open URL: {OPEN_URL}")
    
    # Vytvořit ikonu
    menu = create_menu()
    icon = pystray.Icon(
        TRAY_APP_NAME,
        ICON_ERR,
        TRAY_APP_NAME,
        menu=menu
    )
    
    # Spustit vlákno pro aktualizaci ikony
    update_thread = threading.Thread(target=update_icon_loop, daemon=True)
    update_thread.start()
    
    print("[INFO] Tray ikona je v systémové liště (u hodin)")
    print("[INFO] Pro ukončení klikněte pravým tlačítkem na ikonu a vyberte 'Ukončit'")
    
    # Spustit tray (blokující volání)
    icon.run()

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


