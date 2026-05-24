#!/usr/bin/env python3
"""
Vytvoří nebo povýší účet na roli developer_admin.

Použití:
  python3 scripts/create_developer_admin.py --email admin@example.com --password "tajneheslo"
  python3 scripts/create_developer_admin.py --email existujici@example.com
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import func


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.security import hash_password  # noqa: E402
from src.modules.vehicle_hub.database import DB_URL, SessionLocal  # noqa: E402
from src.modules.vehicle_hub.models import Customer, Tenant  # noqa: E402


def normalize_email(email: str) -> str:
    return email.strip().lower()


def resolve_tenant(db, tenant_id: int | None) -> Tenant:
    if tenant_id is not None:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise ValueError(f"Tenant s ID {tenant_id} neexistuje.")
        return tenant

    tenant = db.query(Tenant).order_by(Tenant.id.asc()).first()
    if tenant:
        return tenant

    tenant = Tenant(name="Default Tenant", license_key="default-license")
    db.add(tenant)
    db.flush()
    return tenant


def main() -> int:
    parser = argparse.ArgumentParser(description="Vytvoření/povýšení developer admin účtu")
    parser.add_argument("--email", required=True, help="Email admin účtu")
    parser.add_argument(
        "--password",
        help="Heslo (povinné při vytvoření nového účtu; volitelné při povýšení existujícího)",
    )
    parser.add_argument("--name", help="Jméno / název účtu")
    parser.add_argument("--tenant-id", type=int, help="Cílový tenant_id (volitelné)")
    args = parser.parse_args()

    email = normalize_email(args.email)
    db = SessionLocal()

    try:
        tenant = resolve_tenant(db, args.tenant_id)
        user = db.query(Customer).filter(func.lower(Customer.email) == email).first()

        if user:
            changed = False
            if user.role != "developer_admin":
                user.role = "developer_admin"
                changed = True
            if user.tenant_id != tenant.id:
                user.tenant_id = tenant.id
                changed = True
            if args.name is not None and args.name != user.name:
                user.name = args.name
                changed = True
            if args.password:
                user.password_hash = hash_password(args.password)
                changed = True

            if changed:
                db.commit()
                print(f"OK: Uživatel {email} byl aktualizován na role=developer_admin (tenant_id={tenant.id}).")
            else:
                print(f"INFO: Uživatel {email} už má role=developer_admin a nebyly potřeba žádné změny.")

            return 0

        if not args.password:
            raise ValueError("Pro vytvoření nového účtu je nutné zadat --password.")

        new_user = Customer(
            tenant_id=tenant.id,
            email=email,
            password_hash=hash_password(args.password),
            name=args.name,
            role="developer_admin",
            created_at=datetime.utcnow(),
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        print(
            f"OK: Vytvořen nový developer_admin účet "
            f"(id={new_user.id}, email={new_user.email}, tenant_id={new_user.tenant_id}, db={DB_URL})"
        )
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
