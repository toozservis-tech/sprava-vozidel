#!/usr/bin/env python3
"""
Migrace: každému uživateli (role=user) vytvoří vlastní tenant
a přesune jeho data pod nový tenant_id.

Použití:
  python scripts/migrate_users_to_dedicated_tenants.py           # dry-run
  python scripts/migrate_users_to_dedicated_tenants.py --apply   # provede změny
"""
import argparse
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Tuple

from sqlalchemy import inspect, text

# Zajistí import `src.*` i při spuštění skriptu z /scripts.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.modules.vehicle_hub.database import SessionLocal
from src.modules.vehicle_hub.models import Customer
from src.modules.vehicle_hub.tenant_provisioning import (
    create_dedicated_tenant,
    ensure_default_license_for_tenant,
)


@dataclass
class TableUpdate:
    table_name: str
    where_sql: str
    params_builder: callable


def _count(db, table_name: str, where_sql: str, params: Dict) -> int:
    query = text(f"SELECT COUNT(*) FROM {table_name} WHERE {where_sql}")
    return db.execute(query, params).scalar() or 0


def _update_tenant(db, table_name: str, where_sql: str, params: Dict, new_tenant_id: int) -> int:
    query = text(f"UPDATE {table_name} SET tenant_id = :new_tenant_id WHERE {where_sql}")
    payload = dict(params)
    payload["new_tenant_id"] = new_tenant_id
    result = db.execute(query, payload)
    return int(result.rowcount or 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Provede změny (jinak jen dry-run).")
    parser.add_argument("--include-services", action="store_true", help="Migrovat i role=service.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        inspector = inspect(db.bind)
        existing_tables = set(inspector.get_table_names())

        roles = ["user"]
        if args.include_services:
            roles.append("service")

        users: List[Customer] = (
            db.query(Customer)
            .filter(Customer.role.in_(roles))
            .order_by(Customer.id.asc())
            .all()
        )

        if not users:
            print("Nenalezeni žádní uživatelé pro migraci.")
            return 0

        updates: List[TableUpdate] = [
            TableUpdate(
                table_name="vehicles",
                where_sql="lower(user_email) = :email",
                params_builder=lambda user: {"email": (user.email or "").strip().lower()},
            ),
            TableUpdate(
                table_name="service_records",
                where_sql=(
                    "user_id = :customer_id "
                    "OR vehicle_id IN (SELECT id FROM vehicles WHERE lower(user_email) = :email)"
                ),
                params_builder=lambda user: {
                    "customer_id": user.id,
                    "email": (user.email or "").strip().lower(),
                },
            ),
            TableUpdate(
                table_name="reminders",
                where_sql="customer_id = :customer_id",
                params_builder=lambda user: {"customer_id": user.id},
            ),
            TableUpdate(
                table_name="reservations",
                where_sql="customer_id = :customer_id",
                params_builder=lambda user: {"customer_id": user.id},
            ),
            TableUpdate(
                table_name="service_intakes",
                where_sql="customer_id = :customer_id",
                params_builder=lambda user: {"customer_id": user.id},
            ),
            TableUpdate(
                table_name="email_notification_logs",
                where_sql="customer_id = :customer_id OR lower(email) = :email",
                params_builder=lambda user: {
                    "customer_id": user.id,
                    "email": (user.email or "").strip().lower(),
                },
            ),
            TableUpdate(
                table_name="usage_analytics",
                where_sql="lower(user_email) = :email",
                params_builder=lambda user: {"email": (user.email or "").strip().lower()},
            ),
            TableUpdate(
                table_name="security_access_logs",
                where_sql="customer_id = :customer_id OR lower(user_email) = :email",
                params_builder=lambda user: {
                    "customer_id": user.id,
                    "email": (user.email or "").strip().lower(),
                },
            ),
            TableUpdate(
                table_name="bot_commands",
                where_sql="user_id = :customer_id OR lower(user_email) = :email",
                params_builder=lambda user: {
                    "customer_id": user.id,
                    "email": (user.email or "").strip().lower(),
                },
            ),
            TableUpdate(
                table_name="customer_commands",
                where_sql="lower(customer_email) = :email",
                params_builder=lambda user: {"email": (user.email or "").strip().lower()},
            ),
        ]

        # Volitelné tabulky (nemusí existovat ve všech snapshot verzích)
        optional_updates: List[Tuple[str, str, callable]] = [
            ("invoices", "user_id = :customer_id", lambda user: {"customer_id": user.id}),
        ]
        for table_name, where_sql, params_builder in optional_updates:
            if table_name in existing_tables:
                updates.append(
                    TableUpdate(
                        table_name=table_name,
                        where_sql=where_sql,
                        params_builder=params_builder,
                    )
                )

        print(f"Režim: {'APPLY' if args.apply else 'DRY-RUN'}")
        print(f"Uživatelé k migraci: {len(users)}")

        migrated = 0
        for user in users:
            email = (user.email or "").strip().lower()
            if not email:
                continue

            # Když je účet už izolovaný (jediný customer v tenantu), přeskočit.
            tenant_user_count = (
                db.query(Customer)
                .filter(Customer.tenant_id == user.tenant_id)
                .count()
            )
            if tenant_user_count <= 1:
                print(f"[SKIP] user_id={user.id} email={email} tenant_id={user.tenant_id} (už dedikovaný)")
                continue

            print(f"[PLAN] user_id={user.id} email={email} old_tenant={user.tenant_id}")

            transfer_counts: Dict[str, int] = {}
            for item in updates:
                if item.table_name not in existing_tables:
                    continue
                params = item.params_builder(user)
                transfer_counts[item.table_name] = _count(db, item.table_name, item.where_sql, params)

            print(f"       data={transfer_counts}")

            if not args.apply:
                continue

            try:
                new_tenant = create_dedicated_tenant(
                    db,
                    owner_email=email,
                    owner_name=user.name,
                )

                user.tenant_id = new_tenant.id
                db.flush()

                for item in updates:
                    if item.table_name not in existing_tables:
                        continue
                    params = item.params_builder(user)
                    _update_tenant(db, item.table_name, item.where_sql, params, new_tenant.id)

                db.commit()
                ensure_default_license_for_tenant(db, new_tenant.id)
                migrated += 1
                print(f"[OK]   user_id={user.id} new_tenant={new_tenant.id}")
            except Exception as exc:
                db.rollback()
                print(f"[ERR]  user_id={user.id} email={email} error={exc}")

        print(f"Dokončeno. Migrovaných uživatelů: {migrated}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
