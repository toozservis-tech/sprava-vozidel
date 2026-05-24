#!/usr/bin/env python3
"""
Migrace: Oprava sloupce 'plan' v tabulce licenses

Problém: DB má sloupec 'plan_name', ale model očekává 'plan'
Řešení: Přidat sloupec 'plan', zkopírovat data z 'plan_name', smazat 'plan_name'
"""
import sys
from pathlib import Path
import os

# Přidat root projektu do path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text, inspect

def get_db_path():
    """Získá cestu k databázi z ENV nebo default"""
    from src.core.config import DATABASE_URL

    db_url = DATABASE_URL
    
    if db_url and db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "")
        return db_path

    return None

def check_schema(db_path):
    """Zkontroluje aktuální schema tabulky licenses"""
    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    
    if 'licenses' not in inspector.get_table_names():
        return None, None, False
    
    columns = inspector.get_columns('licenses')
    column_names = [col['name'] for col in columns]
    
    has_plan_name = 'plan_name' in column_names
    has_plan = 'plan' in column_names
    
    return has_plan_name, has_plan, True

def migrate():
    """Provede migraci: přidá 'plan', zkopíruje data, smaže 'plan_name'"""
    db_path = get_db_path()
    
    if not db_path:
        print("❌ ERROR: Nepodařilo se zjistit cestu k databázi")
        return False
    
    if not os.path.exists(db_path):
        print(f"❌ ERROR: Databáze neexistuje: {db_path}")
        return False
    
    print(f"📁 Databáze: {db_path}")
    print(f"📂 Working directory: {os.getcwd()}")
    
    # Zkontrolovat schema
    has_plan_name, has_plan, table_exists = check_schema(db_path)
    
    if not table_exists:
        print("⚠️  Tabulka 'licenses' neexistuje - bude vytvořena při prvním použití")
        return True
    
    print(f"\n=== Aktuální schema ===")
    print(f"  plan_name existuje: {has_plan_name}")
    print(f"  plan existuje: {has_plan}")
    
    # Pokud už máme 'plan', není co dělat
    if has_plan:
        print("\n✅ Sloupec 'plan' již existuje - migrace není potřeba")
        return True
    
    # Pokud nemáme ani 'plan_name' ani 'plan', přidat 'plan'
    if not has_plan_name:
        print("\n=== Přidávání sloupce 'plan' ===")
        try:
            engine = create_engine(f"sqlite:///{db_path}")
            with engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE licenses 
                    ADD COLUMN plan TEXT NOT NULL DEFAULT 'free';
                """))
                conn.commit()
            print("✅ Sloupec 'plan' přidán")
            return True
        except Exception as e:
            print(f"❌ ERROR při přidávání sloupce: {e}")
            return False
    
    # Máme 'plan_name', ale ne 'plan' - přidat 'plan' a zkopírovat data
    print("\n=== Migrace: plan_name -> plan ===")
    
    try:
        engine = create_engine(f"sqlite:///{db_path}")
        
        with engine.connect() as conn:
            # 1. Přidat sloupec 'plan'
            print("1. Přidávám sloupec 'plan'...")
            conn.execute(text("""
                ALTER TABLE licenses 
                ADD COLUMN plan TEXT NOT NULL DEFAULT 'free';
            """))
            conn.commit()
            
            # 2. Zkopírovat data z 'plan_name' do 'plan'
            print("2. Kopíruji data z 'plan_name' do 'plan'...")
            result = conn.execute(text("SELECT COUNT(*) FROM licenses WHERE plan_name IS NOT NULL;"))
            count = result.fetchone()[0]
            
            if count > 0:
                conn.execute(text("""
                    UPDATE licenses 
                    SET plan = plan_name 
                    WHERE plan_name IS NOT NULL;
                """))
                conn.commit()
                print(f"   ✅ Zkopírováno {count} záznamů")
            else:
                print("   ℹ️  Žádné záznamy k zkopírování")
            
            # 3. Smazat sloupec 'plan_name' (SQLite neumí DROP COLUMN přímo)
            # Musíme vytvořit novou tabulku bez 'plan_name'
            print("3. Odstraňuji sloupec 'plan_name'...")
            
            # Získat strukturu tabulky
            result = conn.execute(text("PRAGMA table_info(licenses);"))
            columns = result.fetchall()
            
            # Vytvořit novou tabulku bez 'plan_name', ale s 'plan'
            # Použít správné sloupce podle modelu
            col_defs = [
                "id INTEGER PRIMARY KEY",
                "tenant_id INTEGER NOT NULL",
                "plan TEXT NOT NULL DEFAULT 'free'",
                "status TEXT NOT NULL",
                "vehicles_limit INTEGER NOT NULL",
                "valid_from DATETIME",
                "valid_to DATETIME",
                "created_at DATETIME",
                "updated_at DATETIME",
                "vin_decode_enabled BOOLEAN NOT NULL",
                "ares_enabled BOOLEAN NOT NULL",
                "reminders_enabled BOOLEAN NOT NULL"
            ]
            
            # Vytvořit novou tabulku
            conn.execute(text(f"""
                CREATE TABLE licenses_new (
                    {', '.join(col_defs)}
                );
            """))
            
            # Zkopírovat data (mapování: plan_name -> plan)
            # Zkontrolovat, zda existuje valid_from
            result = conn.execute(text("PRAGMA table_info(licenses);"))
            has_valid_from = any(row[1] == 'valid_from' for row in result.fetchall())
            
            if has_valid_from:
                conn.execute(text("""
                    INSERT INTO licenses_new (
                        id, tenant_id, plan, status, vehicles_limit, 
                        valid_from, valid_to, created_at, updated_at,
                        vin_decode_enabled, ares_enabled, reminders_enabled
                    )
                    SELECT 
                        id, tenant_id, 
                        COALESCE(plan_name, 'free') as plan,
                        status, vehicles_limit,
                        valid_from, valid_to, created_at, updated_at,
                        vin_decode_enabled, ares_enabled, reminders_enabled
                    FROM licenses;
                """))
            else:
                conn.execute(text("""
                    INSERT INTO licenses_new (
                        id, tenant_id, plan, status, vehicles_limit, 
                        valid_to, created_at, updated_at,
                        vin_decode_enabled, ares_enabled, reminders_enabled
                    )
                    SELECT 
                        id, tenant_id, 
                        COALESCE(plan_name, 'free') as plan,
                        status, vehicles_limit,
                        valid_to, created_at, updated_at,
                        vin_decode_enabled, ares_enabled, reminders_enabled
                    FROM licenses;
                """))
            
            # Smazat starou tabulku a přejmenovat novou
            conn.execute(text("DROP TABLE licenses;"))
            conn.execute(text("ALTER TABLE licenses_new RENAME TO licenses;"))
            
            # Obnovit indexy a constraints
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_license_tenant_id ON licenses(tenant_id);
            """))
            
            conn.commit()
            print("   ✅ Sloupec 'plan_name' odstraněn, 'plan' přidán")
        
        print("\n✅ Migrace dokončena")
        return True
        
    except Exception as e:
        print(f"❌ ERROR při migraci: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("MIGRACE: Oprava sloupce 'plan' v tabulce licenses")
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
