"""
Migrační skript pro přidání licenčních cache polí do tabulky customers
"""
import sys
from pathlib import Path

# Přidání kořenového adresáře projektu do Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.modules.vehicle_hub.database import SessionLocal, engine

def migrate():
    """Přidá nové sloupce do tabulky customers pro licenční cache systém"""
    db = SessionLocal()
    try:
        # Zjistit typ databáze
        db_url = str(engine.url)
        is_sqlite = db_url.startswith("sqlite")
        is_postgres = db_url.startswith("postgresql") or db_url.startswith("postgres")
        
        print(f"[MIGRATION] Typ databáze: {'SQLite' if is_sqlite else 'PostgreSQL' if is_postgres else 'Neznámý'}")
        
        migrations = []
        
        if is_sqlite:
            # SQLite - zkontrolovat existující sloupce
            result = db.execute(text("PRAGMA table_info(customers)"))
            columns = {row[1]: row for row in result.fetchall()}
            
            # Přidat license_plan_cached
            if "license_plan_cached" not in columns:
                migrations.append(("license_plan_cached", "TEXT DEFAULT 'FREE' NOT NULL"))
            
            # Přidat license_status_cached
            if "license_status_cached" not in columns:
                migrations.append(("license_status_cached", "TEXT DEFAULT 'ACTIVE' NOT NULL"))
            
            # Přidat license_period_end_cached
            if "license_period_end_cached" not in columns:
                migrations.append(("license_period_end_cached", "DATETIME"))
            
            # Přidat license_last_sync_at (nový sloupec, nezávislý na last_license_sync_at)
            if "license_last_sync_at" not in columns:
                migrations.append(("license_last_sync_at", "DATETIME"))
                if "last_license_sync_at" in columns:
                    print("[MIGRATION] INFO: last_license_sync_at existuje, přidávám nový sloupec license_last_sync_at.")
            
            # Aktualizovat default pro license_source na "service_hub" (pokud existuje)
            if "license_source" in columns:
                # SQLite nepodporuje ALTER COLUMN DEFAULT přímo, musíme použít UPDATE
                print("[MIGRATION] Aktualizuji default hodnoty pro license_source...")
                db.execute(text("UPDATE customers SET license_source = 'service_hub' WHERE license_source IS NULL OR license_source = 'local'"))
                db.commit()
            
            # Spustit migrace
            for col_name, col_type in migrations:
                print(f"[MIGRATION] Přidávám sloupec {col_name}...")
                try:
                    db.execute(text(f"ALTER TABLE customers ADD COLUMN {col_name} {col_type}"))
                    db.commit()
                    print(f"[MIGRATION] OK: Sloupec {col_name} přidán")
                except Exception as e:
                    if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                        print(f"[MIGRATION] SKIP: Sloupec {col_name} již existuje")
                    else:
                        raise
        
        elif is_postgres:
            # PostgreSQL podporuje IF NOT EXISTS
            migrations = [
                ("license_plan_cached", "VARCHAR DEFAULT 'FREE' NOT NULL"),
                ("license_status_cached", "VARCHAR DEFAULT 'ACTIVE' NOT NULL"),
                ("license_period_end_cached", "TIMESTAMP"),
                ("license_last_sync_at", "TIMESTAMP"),
            ]
            
            for col_name, col_type in migrations:
                print(f"[MIGRATION] Přidávám sloupec {col_name}...")
                try:
                    db.execute(text(f"ALTER TABLE customers ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                    db.commit()
                    print(f"[MIGRATION] OK: Sloupec {col_name} přidán")
                except Exception as e:
                    print(f"[MIGRATION] WARN: Chyba při přidávání {col_name}: {e}")
            
            # Aktualizovat default pro license_source
            print("[MIGRATION] Aktualizuji default hodnoty pro license_source...")
            db.execute(text("UPDATE customers SET license_source = 'service_hub' WHERE license_source IS NULL OR license_source = 'local'"))
            db.commit()
        
        else:
            print(f"[MIGRATION] CHYBA: Nepodporovaný typ databáze: {db_url}")
            sys.exit(1)
        
        print("[MIGRATION] OK: Migrace dokončena úspěšně!")
        
    except Exception as e:
        db.rollback()
        print(f"[MIGRATION] CHYBA: Chyba při migraci: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    migrate()


