from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_trial_alembic_head_adds_license_columns():
    migration = ROOT / "alembic" / "versions" / "20260522_0042_initial_user_trial_fields.py"
    content = migration.read_text(encoding="utf-8")
    assert 'revision = "20260522_0042"' in content
    assert 'down_revision = "20260516_0041"' in content
    for column in ("trial_started_at", "trial_ends_at", "trial_used_at", "trial_source", "trial_plan"):
        assert column in content
    assert '"vehicles"' not in content


def test_runtime_sqlite_licenses_has_trial_columns():
    db_path = Path("/opt/toozhub2/data/vehicles.db")
    if not db_path.exists():
        return
    with sqlite3.connect(str(db_path)) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(licenses)").fetchall()}
    assert {
        "trial_started_at",
        "trial_ends_at",
        "trial_used_at",
        "trial_source",
        "trial_plan",
    }.issubset(columns)


def test_global_500_handler_does_not_expose_sql_details():
    content = (ROOT / "src" / "server" / "bootstrap.py").read_text(encoding="utf-8")
    assert "Funkci se nepodařilo načíst. Zkuste to prosím znovu nebo kontaktujte podporu." in content
    assert '"type": type(exc).__name__' not in content
    assert 'f"Interní chyba serveru: {str(exc)}"' not in content
