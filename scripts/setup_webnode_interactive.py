#!/usr/bin/env python3
"""
Interaktivní Python skript pro nastavení Webnode přihlašovacích údajů
Lepší než bash skript, protože funguje i v různých terminálech
"""

import json
import getpass
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from webnode_paths import (
    WEBNODE_CONFIG_CANON,
    WEBNODE_CONFIG_LEGACY,
    save_webnode_config_dict,
)

def main():
    print("🔐 Nastavení Webnode přihlašovacích údajů")
    print("=" * 50)
    print()
    print("Tyto údaje budou uloženy lokálně a použity pro automatické aktualizace.")
    print()
    
    # Zkontrolovat, zda soubor už existuje (kanonický nebo legacy)
    if WEBNODE_CONFIG_CANON.exists() or WEBNODE_CONFIG_LEGACY.exists():
        existing = WEBNODE_CONFIG_CANON if WEBNODE_CONFIG_CANON.exists() else WEBNODE_CONFIG_LEGACY
        print(f"⚠️  Konfigurační soubor už existuje: {existing}")
        response = input("Chcete ho přepsat? (y/n): ").strip().lower()
        if response != 'y':
            print("Zrušeno.")
            return
        print()
    
    # Načíst údaje
    print("Zadejte přihlašovací údaje pro Webnode:")
    print()
    
    email = input("📧 Email: ").strip()
    if not email:
        print("❌ Email je povinný!")
        return
    
    password = getpass.getpass("🔑 Heslo: ")
    if not password:
        print("❌ Heslo je povinné!")
        return
    
    print()
    page_url = input("🌐 URL stránky (např. https://www.toozservis.cz/sprava-vozidel/): ").strip()
    if not page_url:
        print("❌ URL stránky je povinná!")
        return
    
    print()
    api_key = input("🔑 API klíč (pokud máte, jinak nechte prázdné): ").strip()
    
    # Vytvořit konfiguraci
    config = {
        "email": email,
        "password": password,
        "page_url": page_url,
        "api_key": api_key if api_key else None
    }
    
    # Uložit (vždy kanonická cesta; legacy lze smazat ručně po migraci)
    try:
        target = save_webnode_config_dict(config)
        
        print()
        print("✅ Konfigurace uložena do:", target)
        print("ℹ️  Zastaralý soubor ~/.toozhub_webnode_config.json (pokud existuje) můžete po ověření smazat.")
        print("🔒 Soubor má oprávnění pouze pro vás (600)")
        print()
        print("📝 Co dál:")
        print("1. Spusťte: python3 scripts/webnode_auto_upload.py")
        print("   Tento helper má pro běžný upload používat canonical větev web/index.html")
        print("2. Nebo použijte API endpoint: curl -X POST http://localhost:8000/webnode/update")
        print()
        print("⚠️  DŮLEŽITÉ: Tento soubor obsahuje citlivé údaje a NENÍ v Gitu!")
        
    except (IOError, OSError, ValueError) as e:
        print(f"❌ Chyba při ukládání konfigurace: {e}")

if __name__ == "__main__":
    main()
