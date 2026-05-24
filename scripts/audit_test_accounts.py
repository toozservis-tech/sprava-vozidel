#!/usr/bin/env python3
"""Dry-run audit of likely test accounts. Does not modify data."""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.config import DATABASE_URL


@dataclass
class Candidate:
    email: str
    tenant_id: int | None
    created_at: str | None
    role: str | None
    has_vehicles: bool
    has_payments: bool
    has_service_history: bool


def _mask_email(email: str) -> str:
    local, _, domain = str(email or "").partition("@")
    if not local:
        return "***"
    prefix = local[:2]
    suffix = local[-1:] if len(local) > 2 else ""
    return f"{prefix}***{suffix}@{domain or '***'}"


def _table_exists(engine, table_name: str) -> bool:
    return table_name in inspect(engine).get_table_names()


def _count(conn, sql: str, params: dict) -> int:
    try:
        return int(conn.execute(text(sql), params).scalar() or 0)
    except Exception:
        return 0


def collect_candidates(limit: int | None = None) -> list[Candidate]:
    engine = create_engine(DATABASE_URL)
    has_payments_table = _table_exists(engine, "license_payment_transactions")
    rows_sql = """
        SELECT id, email, tenant_id, created_at, role
        FROM customers
        WHERE lower(email) LIKE '%e2e%'
           OR lower(email) LIKE '%test%'
           OR lower(email) LIKE '%pw-%'
           OR lower(email) LIKE '%ci.%'
           OR lower(email) LIKE '%@example.com'
           OR lower(email) LIKE '%@example.test'
           OR lower(email) LIKE '%@toozservis.test'
        ORDER BY created_at DESC, id DESC
    """
    if limit:
        rows_sql += " LIMIT :limit"
    candidates: list[Candidate] = []
    with engine.connect() as conn:
        rows = conn.execute(text(rows_sql), {"limit": int(limit or 0)}).mappings().all()
        for row in rows:
            tenant_id = row.get("tenant_id")
            customer_id = row.get("id")
            vehicle_count = _count(
                conn,
                "SELECT count(*) FROM vehicles WHERE tenant_id = :tenant_id",
                {"tenant_id": tenant_id},
            )
            history_count = _count(
                conn,
                """
                SELECT count(*)
                FROM service_records
                WHERE tenant_id = :tenant_id OR user_id = :customer_id OR customer_id = :customer_id
                """,
                {"tenant_id": tenant_id, "customer_id": customer_id},
            )
            payment_count = 0
            if has_payments_table:
                payment_count = _count(
                    conn,
                    "SELECT count(*) FROM license_payment_transactions WHERE tenant_id = :tenant_id",
                    {"tenant_id": tenant_id},
                )
            candidates.append(
                Candidate(
                    email=str(row.get("email") or ""),
                    tenant_id=int(tenant_id) if tenant_id is not None else None,
                    created_at=str(row.get("created_at") or ""),
                    role=str(row.get("role") or ""),
                    has_vehicles=vehicle_count > 0,
                    has_payments=payment_count > 0,
                    has_service_history=history_count > 0,
                )
            )
    return candidates


def recommendation(candidate: Candidate) -> str:
    if candidate.has_payments or candidate.has_vehicles or candidate.has_service_history:
        return "archive/disable candidate"
    return "delete candidate"


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run audit of likely generated test accounts.")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    candidates = collect_candidates(limit=args.limit)
    print(f"total candidates: {len(candidates)}")
    print("email_masked\ttenant_id\tcreated_at\trole\thas_vehicles\thas_payments\thas_service_history\trecommendation")
    for item in candidates:
        print(
            "\t".join(
                [
                    _mask_email(item.email),
                    str(item.tenant_id or ""),
                    item.created_at or "",
                    item.role or "",
                    "yes" if item.has_vehicles else "no",
                    "yes" if item.has_payments else "no",
                    "yes" if item.has_service_history else "no",
                    recommendation(item),
                ]
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
