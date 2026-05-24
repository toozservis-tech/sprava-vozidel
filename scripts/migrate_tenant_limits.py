"""
Migrační skript pro přidání limitů a funkcí do tabulky tenants
"""
import sys
from pathlib import Path

# Přidání kořenového adresáře projektu do Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.modules.vehicle_hub.database import SessionLocal, engine

def migrate():
    """Přidá nové sloupce do tabulky tenants"""
    db = SessionLocal()
    try:
        # SQLite ALTER TABLE příkazy
        migrations = [
            # Přidat max_vehicles (Integer, nullable)
            "ALTER TABLE tenants ADD COLUMN max_vehicles INTEGER",
            
            # Přidat feature sloupce (Boolean, default False/True)
            "ALTER TABLE tenants ADD COLUMN feature_advanced_reports INTEGER DEFAULT 0",
            "ALTER TABLE tenants ADD COLUMN feature_api_access INTEGER DEFAULT 0",
            "ALTER TABLE tenants ADD COLUMN feature_export_data INTEGER DEFAULT 1",
            "ALTER TABLE tenants ADD COLUMN feature_service_history INTEGER DEFAULT 1",
            "ALTER TABLE tenants ADD COLUMN feature_reminders INTEGER DEFAULT 1",
            "ALTER TABLE tenants ADD COLUMN feature_multiple_users INTEGER DEFAULT 0",
        ]
        
        print("Spoustim migraci tabulky tenants...")
        for sql in migrations:
            try:
                db.execute(text(sql))
                print(f"[OK] {sql[:50]}...")
            except Exception as e:
                # Pokud sloupec už existuje, ignorovat chybu
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"[SKIP] Sloupec uz existuje: {sql[:50]}...")
                else:
                    raise
        
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



















