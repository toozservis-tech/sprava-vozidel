#!/usr/bin/env python3
"""
Vyčištění testovacích zákaznických účtů před ostrým provozem (soft-delete, stejně jako admin API).

Důležité:
  - Primární klíče (customers.id) se nemění — přemapování by rozbilo desítky cizích klíčů.
  - Soft-delete zachová vazby; přehled „živých“ uživatelů pak odpovídá realitě.
  - U SQLite zůstane sqlite_sequence podle největšího kdy použitého ID; to je v pořádku.

Použití:
  python3 scripts/purge_test_accounts.py --dry-run
  python3 scripts/purge_test_accounts.py --execute --i-understand

Volitelně vlastní vzory (SQL LIKE, case-insensitive), např.:
  python3 scripts/purge_test_accounts.py --dry-run --pattern '%@mytest.local' --pattern 'e2e%@%'

Chráněné e-maily a ID:
  --keep-email admin@firma.cz --protect-id 1 --protect-id 2
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import or_, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.modules.vehicle_hub.database import DB_URL, SessionLocal  # noqa: E402
from src.modules.vehicle_hub.models import Customer  # noqa: E402
from src.server.customer_soft_delete import soft_delete_customer  # noqa: E402


DEFAULT_PATTERNS = [
    "%@example.com",
    "%@example.org",
    "%@test.local",
    "%@deleted.toozhub.local",
    "%e2e%@%",
    "test+%@%",
    "devadmin@%",
]


def _patterns_from_env() -> list[str]:
    raw = (os.environ.get("PURGE_TEST_EMAIL_PATTERNS") or "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _collect_targets(
    db,
    *,
    patterns: list[str],
    keep_lower: set[str],
    protect_ids: set[int],
    skip_developer_admin: bool,
):
    conds = [Customer.email.ilike(p) for p in patterns]
    q = (
        db.query(Customer)
        .filter(Customer.is_deleted.is_(False))
        .filter(or_(*conds))
        .order_by(Customer.id.asc())
    )
    rows = q.all()
    out = []
    for c in rows:
        em = (c.email or "").strip().lower()
        if em in keep_lower:
            continue
        if c.id in protect_ids:
            continue
        if skip_developer_admin and (c.role or "") == "developer_admin":
            continue
        out.append(c)
    return out


def _sqlite_sequence_report(db) -> None:
    if not str(DB_URL or "").startswith("sqlite"):
        print("\n(sqlite_sequence: pouze pro SQLite)\n")
        return
    print("\n--- SQLite: ID zákazníků ---")
    try:
        mx = db.execute(text("SELECT IFNULL(MAX(id), 0) FROM customers")).scalar()
        print(f"  customers MAX(id): {mx}")
    except Exception as ex:
        print(f"  (MAX(id) customers: {ex})")
    try:
        r = db.execute(
            text(
                "SELECT name, seq FROM sqlite_sequence WHERE name IN "
                "('customers','tenants','vehicles') ORDER BY name"
            )
        ).fetchall()
        if r:
            print("  sqlite_sequence:")
            for name, seq in r:
                print(f"    {name}: seq={seq}")
        else:
            print("  sqlite_sequence: (tabulka neexistuje nebo žádné AUTOINCREMENT řádky)")
    except Exception:
        print("  sqlite_sequence: tabulka neexistuje (běžné u INTEGER PK bez AUTOINCREMENT)")
    print(
        "  Pozn.: ID zákazníků se nepřečíslovávají — zachovávají se všechny FK vazby. "
        "Další nový řádek dostane dosud nepoužité ID.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Soft-delete testovacích účtů (zachová vazby).")
    parser.add_argument("--dry-run", action="store_true", help="Jen vypsat, nic neměnit.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Provede soft-delete (vyžaduje --i-understand).",
    )
    parser.add_argument(
        "--i-understand",
        action="store_true",
        help="Potvrzení, že rozumíte dopadu na vybrané účty.",
    )
    parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        default=[],
        help="Dodatečný vzor LIKE pro email (lze opakovat). Bez --pattern se použijí výchozí + PURGE_TEST_EMAIL_PATTERNS.",
    )
    parser.add_argument(
        "--include-developer-admins",
        action="store_true",
        help="Neomezovat roli developer_admin (výchozí: tyto účty přeskočit).",
    )
    parser.add_argument("--keep-email", action="append", default=[], help="E-mail nikdy nesmazat (lze opakovat).")
    parser.add_argument("--protect-id", type=int, action="append", default=[], help="Customer ID nikdy nesmazat.")

    args = parser.parse_args()
    if args.execute and not args.i_understand:
        print("Chyba: --execute vyžaduje --i-understand.", file=sys.stderr)
        return 2
    if not args.dry_run and not args.execute:
        print("Zadejte --dry-run nebo --execute.", file=sys.stderr)
        return 2

    patterns = list(args.patterns) if args.patterns else (_patterns_from_env() or DEFAULT_PATTERNS)
    keep_lower = {e.strip().lower() for e in args.keep_email if e.strip()}
    protect_ids = set(args.protect_id or [])

    db = SessionLocal()
    try:
        targets = _collect_targets(
            db,
            patterns=patterns,
            keep_lower=keep_lower,
            protect_ids=protect_ids,
            skip_developer_admin=not args.include_developer_admins,
        )
        print("Vzory:", patterns)
        print(f"Nalezeno k úpravě: {len(targets)}")
        for c in targets:
            print(f"  id={c.id} role={c.role!r} email={c.email!r} tenant_id={c.tenant_id}")

        _sqlite_sequence_report(db)

        if args.dry_run:
            print("\n(--dry-run: žádné změny)\n")
            return 0

        ok = 0
        for c in targets:
            soft_delete_customer(db, c)
            db.commit()
            ok += 1
            print(f"  soft-delete OK id={c.id}")
        print(f"\nHotovo: {ok} účtů.\n")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
