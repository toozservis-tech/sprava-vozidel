from __future__ import annotations

import logging
import re

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from src.core.config import DATABASE_URL


# Jediná runtime databázová pravda je centrální resolver v src.core.config.
# Legacy VEHICLE_DB_URL zůstává podporovaný pouze jako compat vstup do configu.
DB_URL = DATABASE_URL

# Connect args pro SQLite. Admin přehledy čtou hodně dat a nesmí spadnout při krátkém zápisu.
connect_args = {"check_same_thread": False, "timeout": 30} if DB_URL.startswith("sqlite") else {}

# Engine s poolováním (pro PostgreSQL), nebo bez (pro SQLite)
if DB_URL.startswith("postgresql") or DB_URL.startswith("postgres"):
    engine = create_engine(
        DB_URL,
        pool_size=20,
        max_overflow=30,
        future=True,
        connect_args={}
    )
else:
    # SQLite - bez poolování
    engine = create_engine(DB_URL, connect_args=connect_args)


if DB_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _configure_sqlite_connection(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
        except Exception as exc:
            logger.warning("[DB] SQLite PRAGMA setup failed: %s", exc)
        finally:
            cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

logger = logging.getLogger(__name__)
_DML_TABLE_RE = re.compile(
    r"^\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([\"`\[]?)([a-zA-Z_][a-zA-Z0-9_]*)\1",
    re.IGNORECASE,
)


def _writable_table_names() -> set[str]:
    table_names = set(Base.metadata.tables.keys())
    table_names.add("alembic_version")
    return table_names


SERVICE_HUB_WRITABLE_TABLES: set[str] = set()


def _extract_dml_target_table(statement: str) -> str | None:
    match = _DML_TABLE_RE.match(statement or "")
    if not match:
        return None
    return str(match.group(2) or "").strip().lower() or None


@event.listens_for(Session, "before_flush")
def _guard_session_writes_to_known_tables(session: Session, flush_context, instances) -> None:
    allowed_tables = _writable_table_names()
    SERVICE_HUB_WRITABLE_TABLES.clear()
    SERVICE_HUB_WRITABLE_TABLES.update(allowed_tables)
    for collection in (session.new, session.dirty, session.deleted):
        for obj in collection:
            table = getattr(getattr(obj, "__table__", None), "name", None)
            if not table:
                continue
            if str(table) not in allowed_tables:
                logger.error("[DB_GUARD] Blocked ORM write to non-whitelisted table: %s", table)
                raise RuntimeError(f"Write blocked for non-whitelisted table: {table}")


@event.listens_for(engine, "before_cursor_execute")
def _guard_raw_dml_writes(conn, cursor, statement, parameters, context, executemany) -> None:
    target_table = _extract_dml_target_table(statement)
    if not target_table:
        return
    allowed_tables = _writable_table_names()
    SERVICE_HUB_WRITABLE_TABLES.clear()
    SERVICE_HUB_WRITABLE_TABLES.update(allowed_tables)
    allowed = {name.lower() for name in allowed_tables}
    if target_table not in allowed:
        logger.error("[DB_GUARD] Blocked SQL write to non-whitelisted table: %s", target_table)
        raise RuntimeError(f"Write blocked for non-whitelisted table: {target_table}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
