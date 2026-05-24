#!/usr/bin/env python3
"""
Migrace: Vytvoření License tabulky
"""
import os
import sys
from pathlib import Path

# Přidat root projektu do path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.modules.vehicle_hub.database import engine, Base
from src.modules.vehicle_hub.models import License

def migrate():
    """Vytvoří License tabulku pokud neexistuje"""
    print("[MIGRATION] Vytváření License tabulky...")
    
    # Zkontrolovat, zda tabulka už existuje
    with engine.connect() as conn:
        inspector = __import__('sqlalchemy').inspect(engine)
        table_names = inspector.get_table_names()
        
        if 'licenses' in table_names:
            print("[MIGRATION] ✅ Tabulka 'licenses' již existuje")
            return
        
        # Vytvořit tabulku
        Base.metadata.create_all(bind=engine, tables=[License.__table__])
        print("[MIGRATION] ✅ Tabulka 'licenses' vytvořena")
        
        # Vytvořit unique constraint na tenant_id
        try:
            # SQLite nepodporuje IF NOT EXISTS pro UNIQUE constraint, zkusit přímo
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_license_tenant_id ON licenses(tenant_id)"))
            conn.commit()
            print("[MIGRATION] ✅ Unique index na tenant_id vytvořen")
        except Exception as e:
            # Pokud už existuje, ignorovat
            if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
                print(f"[MIGRATION] WARNING: Nepodařilo se vytvořit unique index: {e}")
            else:
                print("[MIGRATION] ✅ Unique index na tenant_id již existuje")

if __name__ == "__main__":
    migrate()

