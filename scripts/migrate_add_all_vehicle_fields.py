"""
Migrační skript pro přidání všech chybějících sloupců do tabulky vehicles
Přidává všechna pole z VehicleDecodedData / MDČR API
"""
import sys
from pathlib import Path

# Přidat kořenový adresář do path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text  # noqa: E402

from src.modules.vehicle_hub.database import SessionLocal, engine  # noqa: E402


def migrate():
    """Přidat všechny chybějící sloupce do tabulky vehicles"""

    print("[MIGRATION] Přidávání všech chybějících sloupců do tabulky vehicles...")

    db = SessionLocal()
    try:
        # Zjistit typ databáze
        db_url = str(engine.url)
        is_sqlite = db_url.startswith("sqlite")
        is_postgres = db_url.startswith("postgresql") or db_url.startswith("postgres")

        print(
            f"[MIGRATION] Typ databáze: {'SQLite' if is_sqlite else 'PostgreSQL' if is_postgres else 'Neznámý'}"
        )

        # Seznam všech sloupců, které mají být přidány
        columns_to_add = [
            ("engine_code", "VARCHAR"),
            ("engine_displacement_cc", "INTEGER"),
            ("engine_power_kw", "INTEGER"),
            ("fuel_type", "VARCHAR"),
            ("transmission_type", "VARCHAR"),
            ("body_type", "VARCHAR"),
            ("doors", "INTEGER"),
            ("seats", "INTEGER"),
            ("curb_weight_kg", "INTEGER"),
            ("gross_weight_kg", "INTEGER"),
            ("emission_standard", "VARCHAR"),
            ("first_registration_date", "VARCHAR"),
            ("type_label", "VARCHAR"),
            ("engine_type_label", "VARCHAR"),
            ("tech_inspection_valid_to", "VARCHAR"),
            ("tyres_raw", "TEXT"),
        ]

        if is_sqlite:
            # Zkontrolovat, zda sloupce už existují
            result = db.execute(text("PRAGMA table_info(vehicles)"))
            columns = [row[1] for row in result.fetchall()]

            for col_name, col_type in columns_to_add:
                if col_name not in columns:
                    print(f"[MIGRATION] Pridavam sloupec {col_name}...")
                    db.execute(
                        text(f"ALTER TABLE vehicles ADD COLUMN {col_name} {col_type}")
                    )
                    db.commit()
                    print(f"[MIGRATION] OK: Sloupec {col_name} pridán")
                else:
                    print(
                        f"[MIGRATION] WARNING: Sloupec {col_name} jiz existuje, preskoceno"
                    )

        elif is_postgres:
            # PostgreSQL podporuje IF NOT EXISTS
            for col_name, col_type in columns_to_add:
                print(f"[MIGRATION] Pridavam sloupec {col_name}...")
                db.execute(
                    text(
                        f"ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                    )
                )
                db.commit()
                print(f"[MIGRATION] OK: Sloupec {col_name} pridán")

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
