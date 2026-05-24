#!/usr/bin/env python3
"""
Skript pro automatické vložení HTML kódu do Webnode editoru
Používá clipboard a může automaticky otevřít Webnode v prohlížeči
"""

import pyperclip
import sys
from pathlib import Path

def read_html_file(file_path):
    """Načte HTML soubor"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except (IOError, OSError, UnicodeDecodeError) as e:
        print(f"Chyba při čtení souboru: {e}")
        return None

def copy_to_clipboard(text):
    """Zkopíruje text do clipboardu"""
    try:
        pyperclip.copy(text)
        print("✓ HTML kód byl zkopírován do clipboardu!")
        return True
    except (AttributeError, RuntimeError, Exception) as e:
        # pyperclip může vyhodit různé výjimky v závislosti na platformě
        print(f"Chyba při kopírování do clipboardu: {e}")
        print("Zkuste nainstalovat: pip install pyperclip")
        return False

def main():
    # Cesta k HTML souboru
    project_root = Path(__file__).parent.parent
    html_file = project_root / "web" / "index.html"
    
    if not html_file.exists():
        print(f"Chyba: Soubor {html_file} neexistuje!")
        sys.exit(1)
    
    print(f"Načítám HTML z: {html_file}")
    html_content = read_html_file(html_file)
    
    if html_content:
        if copy_to_clipboard(html_content):
            print("\n" + "="*60)
            print("HTML kód je nyní ve vašem clipboardu!")
            print("="*60)
            print("\nNyní můžete:")
            print("1. Otevřít Webnode editor (Remix správce)")
            print("2. Vložit kód (Ctrl+V nebo Cmd+V)")
            print("\nPoznámka: V Webnode editoru:")
            print("- Najděte HTML blok nebo 'Vlastní HTML'")
            print("- Vložte celý obsah z clipboardu")
            print("- Uložte změny")
        else:
            print("\nHTML obsah:")
            print("="*60)
            print(html_content)
            print("="*60)
            print("\nZkopírujte výše uvedený kód ručně do Webnode editoru.")

if __name__ == "__main__":
    main()

