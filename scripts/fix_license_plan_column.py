#!/usr/bin/env python3
"""
Migrace: Přidání sloupce 'plan' do tabulky licenses

Opravuje chybu: sqlite3.OperationalError: no such column: licenses.plan
"""
import sys
from pathlib import Path

# Přidat root projektu do path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def get_db_path():
    """Získá cestu k databázi"""
    from src.core.config import DATABASE_URL

    db_url = DATABASE_URL
    
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "")
        return db_path
    return None

def check_column_exists(db_path):
    """Zkontroluje, zda sloupec 'plan' existuje"""
    engine = create_engine(f"sqlite:///{db_path}")
    from sqlalchemy import inspect
    
    inspector = inspect(engine)
    
    # Zkontrolovat, zda tabulka existuje
    if 'licenses' not in inspector.get_table_names():
        print("⚠️  Tabulka 'licenses' neexistuje - bude vytvořena při prvním použití")
        return False
    
    columns = inspector.get_columns('licenses')
    column_names = [col['name'] for col in columns]
    
    print("=== Aktuální struktura tabulky licenses ===")
    for col in columns:
        print(f"  {col['name']} ({col['type']})")
    
    return "plan" in column_names

def migrate():
    """Přidá sloupec 'plan' do tabulky licenses"""
    db_path = get_db_path()
    
    if not db_path:
        print("❌ ERROR: Nepodařilo se zjistit cestu k databázi")
        print("   Zkontrolujte DATABASE_URL nebo VEHICLE_DB_URL v .env")
        return False
    
    if not Path(db_path).exists():
        print(f"❌ ERROR: Databáze neexistuje: {db_path}")
        return False
    
    print(f"📁 Databáze: {db_path}")
    
    # Zkontrolovat, zda tabulka licenses existuje (pokud ne, vytvoří se při prvním použití)
    engine = create_engine(f"sqlite:///{db_path}")
    from sqlalchemy import inspect
    
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    if 'licenses' not in table_names:
        print("⚠️  Tabulka 'licenses' neexistuje - vytvářím...")
        # Vytvořit tabulku pomocí Base.metadata
        from src.modules.vehicle_hub.database import Base
        from src.modules.vehicle_hub.models import License
        Base.metadata.create_all(bind=engine, tables=[License.__table__])
        print("✅ Tabulka 'licenses' vytvořena")
    
    # Zkontrolovat, zda sloupec už existuje
    if check_column_exists(db_path):
        print("\n✅ Sloupec 'plan' již existuje v tabulce licenses")
        return True
    
    # Přidat sloupec
    print("\n=== Přidávání sloupce 'plan' ===")
    
    try:
        with engine.connect() as conn:
            # SQLite ADD COLUMN s DEFAULT hodnotou
            conn.execute(text("""
                ALTER TABLE licenses 
                ADD COLUMN plan TEXT NOT NULL DEFAULT 'free';
            """))
            conn.commit()
        
        print("✅ Sloupec 'plan' úspěšně přidán")
        
        # Ověřit přidání
        if check_column_exists(db_path):
            print("\n✅ Ověření: Sloupec 'plan' je v tabulce")
            
            # Aktualizovat existující záznamy (pokud nějaké jsou)
            with engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM licenses WHERE plan IS NULL OR plan = '';"))
                count = result.fetchone()[0]
                
                if count > 0:
                    print(f"\n📝 Aktualizuji {count} existujících záznamů na plan='free'...")
                    conn.execute(text("UPDATE licenses SET plan = 'free' WHERE plan IS NULL OR plan = '';"))
                    conn.commit()
                    print("✅ Záznamy aktualizovány")
            
            return True
        else:
            print("❌ ERROR: Sloupec nebyl přidán")
            return False
            
    except Exception as e:
        print(f"❌ ERROR při migraci: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("MIGRACE: Přidání sloupce 'plan' do tabulky licenses")
    print("=" * 60)
    print()
    
    success = migrate()
    
    print()
    if success:
        print("=" * 60)
        print("✅ MIGRACE DOKONČENA")
        print("=" * 60)
        sys.exit(0)
    else:
        print("=" * 60)
        print("❌ MIGRACE SELHALA")
        print("=" * 60)
        sys.exit(1)
