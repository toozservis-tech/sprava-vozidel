#!/usr/bin/env python3
"""
File watcher pro automatickou aktualizaci Webnode při změně web/index.html
"""

import sys
import os
import time
import subprocess
import threading
from pathlib import Path

# Zkontrolovat, zda je watchdog dostupný
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    PROJECT_ROOT = Path(__file__).parent.parent
    print("❌ Modul 'watchdog' není nainstalován!")
    print("\n💡 Instalace:")
    print(f"   cd {PROJECT_ROOT}")
    print("   Windows: .\\venv\\Scripts\\Activate.ps1")
    print("   Linux/Mac: source venv/bin/activate")
    print("   pip install watchdog")
    print("\n💡 Nebo použijte wrapper skript:")
    print("   ./scripts/webnode_auto_watcher.sh")
    sys.exit(1)

# Cesta k projektu
PROJECT_ROOT = Path(__file__).parent.parent
HTML_FILE = PROJECT_ROOT / "web" / "index.html"
UPDATE_SCRIPT = PROJECT_ROOT / "scripts" / "webnode_auto_upload.py"

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from webnode_paths import WEBNODE_LOCK_CANON, WEBNODE_LOCK_LEGACY

class HTMLChangeHandler(FileSystemEventHandler):
    """Handler pro změny v HTML souboru"""
    
    def __init__(self):
        self.last_modified = None
        self.debounce_time = 3  # Počkat 3 sekundy po poslední změně (dostatečně dlouho pro dokončení úprav)
        self.last_update_time = 0
        self.update_timer = None
    
    def on_modified(self, event):
        """Zavoláno při změně souboru"""
        if event.is_directory:
            return
        
        # Zkontrolovat, zda se jedná o náš HTML soubor
        file_path = Path(event.src_path).resolve()
        html_file_path = HTML_FILE.resolve()
        
        if file_path != html_file_path:
            return
        
        current_time = time.time()
        
        # Zrušit předchozí naplánovanou aktualizaci, pokud existuje
        if self.update_timer:
            print("⏸️  Zrušuji předchozí naplánovanou aktualizaci...")
            self.update_timer.cancel()
        else:
            # Naplánovat aktualizaci po debounce čase
            print(f"\n📝 Detekována změna v {HTML_FILE.name}")
            print(f"⏳ Čekám {self.debounce_time} sekund na dokončení úprav...")
        
        self.last_update_time = current_time
        
        # Naplánovat aktualizaci (zruší předchozí, pokud existuje)
        self.update_timer = threading.Timer(self.debounce_time, self.update_webnode)
        self.update_timer.start()
        print(f"✅ Aktualizace naplánována za {self.debounce_time} sekund")
    
    def update_webnode(self):
        """Spustí aktualizaci Webnode"""
        print("\n" + "="*60)
        print("🚀 Spouštím automatickou aktualizaci a publikaci Webnode...")
        print("="*60)
        
        # Zkontrolovat, zda už proces běží (legacy i kanonický lock)
        for lock_file in (WEBNODE_LOCK_LEGACY, WEBNODE_LOCK_CANON):
            if not lock_file.exists():
                continue
            try:
                with open(lock_file, 'r', encoding='utf-8') as f:
                    pid = int(f.read().strip())
                try:
                    os.kill(pid, 0)
                    print("⚠️  Aktualizace už běží (PID: {}) - přeskočeno".format(pid))
                    self.update_timer = None
                    return
                except (OSError, ProcessLookupError):
                    print(f"🧹 Odstraňuji starý lock file ({lock_file.name})...")
                    lock_file.unlink()
            except (OSError, ValueError) as e:
                print(f"⚠️  Chyba při kontrole lock file {lock_file}: {e}")
        
        print(f"📄 Spouštím: {sys.executable} {UPDATE_SCRIPT.name}")
        
        try:
            # Spustit skript pro aktualizaci
            result = subprocess.run(
                [sys.executable, str(UPDATE_SCRIPT)],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                check=False,
                text=True,
                timeout=300  # 5 minut timeout
            )
            
            print("\n" + "="*60)
            if result.returncode == 0:
                print("✅ Webnode úspěšně aktualizován a publikován!")
                print("="*60)
            else:
                print("❌ Chyba při aktualizaci:")
                print(result.stderr)
                print("="*60)
            
            # Zobrazit výstup (pokud není prázdný)
            if result.stdout:
                print("\n📋 Výstup skriptu:")
                print(result.stdout)
                
        except subprocess.TimeoutExpired:
            print("\n" + "="*60)
            print("❌ Timeout při aktualizaci Webnode (trvalo déle než 5 minut)")
            print("="*60)
        except (subprocess.SubprocessError, OSError) as e:
            print("\n" + "="*60)
            print(f"❌ Chyba při spuštění aktualizace: {e}")
            print("="*60)
        
        # Resetovat timer
        self.update_timer = None
        print("\n👀 Pokračuji ve sledování změn...\n")

def main():
    """Hlavní funkce"""
    print("="*60)
    print("👀 Automatické sledování změn v web/index.html")
    print("="*60)
    print(f"📁 Sledovaný soubor: {HTML_FILE}")
    print("💡 Při každé změně se automaticky:")
    print("   1️⃣  Vloží HTML do Webnode editoru")
    print("   2️⃣  Počká na uložení změn")
    print("   3️⃣  Publikuje změny (jako poslední krok)")
    print("🛑 Stiskněte Ctrl+C pro ukončení\n")
    
    if not HTML_FILE.exists():
        print(f"❌ HTML soubor neexistuje: {HTML_FILE}")
        sys.exit(1)
    
    if not UPDATE_SCRIPT.exists():
        print(f"❌ Update skript neexistuje: {UPDATE_SCRIPT}")
        sys.exit(1)
    
    # Vytvořit observer
    event_handler = HTMLChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, str(HTML_FILE.parent), recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Ukončuji sledování...")
        # Zrušit naplánovanou aktualizaci, pokud existuje
        if event_handler.update_timer:
            event_handler.update_timer.cancel()
        observer.stop()
    
    observer.join()
    print("✅ Ukončeno")

if __name__ == "__main__":
    main()

