"""
Migrační skript pro přidání licenčních polí do tabulky customers
"""
import sys
from pathlib import Path

# Přidání kořenového adresáře projektu do Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.modules.vehicle_hub.database import SessionLocal

def migrate():
    """Přidá nové sloupce do tabulky customers pro licenční systém"""
    db = SessionLocal()
    try:
        # SQLite ALTER TABLE příkazy
        migrations = [
            # Přidat subscription_status (String, default "active")
            "ALTER TABLE customers ADD COLUMN subscription_status TEXT DEFAULT 'active'",
            
            # Přidat expires_at (DateTime, nullable)
            "ALTER TABLE customers ADD COLUMN expires_at DATETIME",
            
            # Přidat grace_until (DateTime, nullable)
            "ALTER TABLE customers ADD COLUMN grace_until DATETIME",
            
            # Přidat last_license_sync_at (DateTime, nullable)
            "ALTER TABLE customers ADD COLUMN last_license_sync_at DATETIME",
            
            # Přidat license_source (String, default "local")
            "ALTER TABLE customers ADD COLUMN license_source TEXT DEFAULT 'local'",
            
            # Přidat subscription_id (String, nullable, index)
            "ALTER TABLE customers ADD COLUMN subscription_id TEXT",
        ]
        
        print("Spoustim migraci tabulky customers (licencni pole)...")
        for sql in migrations:
            try:
                db.execute(text(sql))
                print(f"[OK] {sql[:60]}...")
            except Exception as e:
                # Pokud sloupec už existuje, ignorovat chybu
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"[SKIP] Sloupec uz existuje: {sql[:60]}...")
                else:
                    raise
        
        # Vytvořit index na subscription_id (SQLite nepodporuje CREATE INDEX IF NOT EXISTS přímo)
        try:
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_customers_subscription_id ON customers(subscription_id)"))
            print("[OK] Index na subscription_id vytvoren")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("[SKIP] Index uz existuje")
            else:
                print(f"[WARN] Chyba pri vytvareni indexu: {e}")
        
        db.commit()
        print("\n[OK] Migrace dokoncena")
        
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Chyba pri migraci: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    migrate()



















