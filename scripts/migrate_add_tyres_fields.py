"""
Migrační skript pro přidání sloupců wheels_and_tyres a extra_records do tabulky vehicles
"""
import sys
from pathlib import Path

# Přidat kořenový adresář do path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text  # noqa: E402

from src.modules.vehicle_hub.database import SessionLocal, engine  # noqa: E402


def migrate():
    """Přidat sloupce wheels_and_tyres a extra_records do tabulky vehicles"""

    print(
        "[MIGRATION] Přidávání sloupců wheels_and_tyres a extra_records do tabulky vehicles..."
    )

    db = SessionLocal()
    try:
        # Zjistit typ databáze
        db_url = str(engine.url)
        is_sqlite = db_url.startswith("sqlite")
        is_postgres = db_url.startswith("postgresql") or db_url.startswith("postgres")

        print(
            f"[MIGRATION] Typ databáze: {'SQLite' if is_sqlite else 'PostgreSQL' if is_postgres else 'Neznámý'}"
        )

        # SQLite nepodporuje IF NOT EXISTS v ALTER TABLE ADD COLUMN
        # Musíme zkontrolovat, zda sloupec už existuje
        if is_sqlite:
            # Zkontrolovat, zda sloupce už existují
            result = db.execute(text("PRAGMA table_info(vehicles)"))
            columns = [row[1] for row in result.fetchall()]

            if "wheels_and_tyres" not in columns:
                print("[MIGRATION] Přidávám sloupec wheels_and_tyres...")
                db.execute(
                    text("ALTER TABLE vehicles ADD COLUMN wheels_and_tyres TEXT")
                )
                db.commit()
                print("[MIGRATION] OK: Sloupec wheels_and_tyres pridán")
            else:
                print(
                    "[MIGRATION] WARNING: Sloupec wheels_and_tyres jiz existuje, preskoceno"
                )

            if "extra_records" not in columns:
                print("[MIGRATION] Pridavam sloupec extra_records...")
                db.execute(text("ALTER TABLE vehicles ADD COLUMN extra_records TEXT"))
                db.commit()
                print("[MIGRATION] OK: Sloupec extra_records pridán")
            else:
                print(
                    "[MIGRATION] WARNING: Sloupec extra_records jiz existuje, preskoceno"
                )

        elif is_postgres:
            # PostgreSQL podporuje IF NOT EXISTS
            print("[MIGRATION] Pridavam sloupec wheels_and_tyres...")
            db.execute(
                text(
                    "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS wheels_and_tyres TEXT"
                )
            )
            db.commit()
            print("[MIGRATION] OK: Sloupec wheels_and_tyres pridán")

            print("[MIGRATION] Pridavam sloupec extra_records...")
            db.execute(
                text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS extra_records TEXT")
            )
            db.commit()
            print("[MIGRATION] OK: Sloupec extra_records pridán")

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
