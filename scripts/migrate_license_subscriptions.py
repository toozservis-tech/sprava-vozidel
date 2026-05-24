#!/usr/bin/env python3
"""
Migrace: vytvoření tabulek pro lifecycle předplatného licencí.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect, text

from src.modules.vehicle_hub.database import engine, Base
from src.modules.vehicle_hub.models import LicensePaymentTransaction, LicenseSubscription


def migrate() -> None:
    print("[MIGRATION] Kontrola tabulek předplatného licencí...")
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "license_subscriptions" not in table_names:
        Base.metadata.create_all(bind=engine, tables=[LicenseSubscription.__table__])
        print("[MIGRATION] ✅ Vytvořena tabulka license_subscriptions")
    else:
        print("[MIGRATION] ✅ Tabulka license_subscriptions již existuje")

    if "license_payment_transactions" not in table_names:
        Base.metadata.create_all(bind=engine, tables=[LicensePaymentTransaction.__table__])
        print("[MIGRATION] ✅ Vytvořena tabulka license_payment_transactions")
    else:
        print("[MIGRATION] ✅ Tabulka license_payment_transactions již existuje")

    # Non-destructive ALTER pro nové sloupce.
    inspector = inspect(engine)
    if "license_subscriptions" in set(inspector.get_table_names()):
        sub_cols = {col["name"] for col in inspector.get_columns("license_subscriptions")}
        with engine.begin() as conn:
            if "credit_balance_halers" not in sub_cols:
                conn.execute(
                    text(
                        "ALTER TABLE license_subscriptions "
                        "ADD COLUMN credit_balance_halers INTEGER NOT NULL DEFAULT 0"
                    )
                )
                print("[MIGRATION] ✅ Přidán sloupec license_subscriptions.credit_balance_halers")
            else:
                print("[MIGRATION] ✅ Sloupec license_subscriptions.credit_balance_halers již existuje")


if __name__ == "__main__":
    migrate()
