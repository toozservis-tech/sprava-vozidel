#!/usr/bin/env python3
"""
Testovací skript pro ověření SMTP konfigurace (bez PySide6)
"""
import sys
import os
from pathlib import Path

# Přidat kořenový adresář projektu do Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Načíst .env soubor
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass

# Načíst konfiguraci přímo
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.mail.webnode.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "info@toozservis.cz")

def test_smtp_config():
    """Test SMTP konfigurace"""
    print("=" * 60)
    print("TEST SMTP KONFIGURACE")
    print("=" * 60)
    print()
    
    print("Aktuální konfigurace:")
    print(f"  SMTP_HOST: {SMTP_HOST}")
    print(f"  SMTP_PORT: {SMTP_PORT}")
    print(f"  SMTP_USER: {SMTP_USER if SMTP_USER else '(není nastaveno)'}")
    print(f"  SMTP_PASSWORD: {'***' if SMTP_PASSWORD else '(není nastaveno)'}")
    print(f"  SMTP_FROM: {SMTP_FROM}")
    print()
    
    # Kontrola konfigurace
    is_configured = bool(SMTP_USER and SMTP_PASSWORD and SMTP_HOST)
    
    print(f"is_configured(): {is_configured}")
    print()
    
    if not is_configured:
        print("❌ SMTP není nakonfigurován!")
        print()
        print("Pro nastavení SMTP přidejte do .env souboru:")
        print("  SMTP_HOST=smtp.mail.webnode.com")
        print("  SMTP_PORT=465")
        print("  SMTP_USER=vas-email@example.com")
        print("  SMTP_PASSWORD=vase-heslo")
        print("  SMTP_FROM=info@toozservis.cz")
        print()
        print("Po přidání proměnných restartujte backend:")
        print("  sudo systemctl restart <název-backend-systemd-jednotky>")
        return False
    
    print("✓ SMTP je nakonfigurován")
    print()
    
    # Test připojení
    print("Test připojení k SMTP serveru...")
    try:
        import smtplib
        import ssl

        tls_ctx = ssl.create_default_context()
        if SMTP_PORT == 465:
            print(f"Připojuji se k {SMTP_HOST}:{SMTP_PORT} (SSL)...")
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10, context=tls_ctx)
        else:
            print(f"Připojuji se k {SMTP_HOST}:{SMTP_PORT} (STARTTLS)...")
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
            server.ehlo()
            server.starttls(context=tls_ctx)
            server.ehlo()
        
        print("Připojení úspěšné!")
        print()
        
        print("Test autentizace...")
        server.login(SMTP_USER, SMTP_PASSWORD)
        print("✓ Autentizace úspěšná!")
        print()
        
        server.quit()
        
        print("=" * 60)
        print("✓ VŠECHNY TESTY PROŠLY")
        print("=" * 60)
        print()
        print("SMTP je správně nakonfigurován a připraven k odesílání emailů.")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ Chyba autentizace: {e}")
        print()
        print("Zkontrolujte:")
        print("  - SMTP_USER (email adresa)")
        print("  - SMTP_PASSWORD (heslo nebo app password)")
        print()
        print("Pro Webnode může být potřeba použít 'App Password' místo běžného hesla.")
        return False
        
    except smtplib.SMTPConnectError as e:
        print(f"❌ Chyba připojení: {e}")
        print()
        print("Zkontrolujte:")
        print("  - SMTP_HOST (správná adresa serveru)")
        print("  - SMTP_PORT (správný port)")
        print("  - Firewall / síťové připojení")
        return False
        
    except Exception as e:
        print(f"❌ Neočekávaná chyba: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_smtp_config()
    sys.exit(0 if success else 1)
