"""
Phase 11a / 13f — SQLAlchemy data layer for the AgenticOS FastAPI sidecar.

SQLAlchemy is the sole access layer for the MySQL ``agenticos`` schema. As of
Phase 13f the last of the raw ``mysql.connector`` code is retired: even the
server-level ``CREATE DATABASE`` bootstrap now runs through a SQLAlchemy engine.
Tables self-bootstrap via ``Base.metadata.create_all()`` on startup; there is
no Alembic (idempotent ALTERs live in ``migrations.ensure_phase13_schema``).

Connection config is read from ~/.agentic-os/.env (never committed), using the
same env vars as the stores (news_db / tasks_db):
    MYSQL_HOST  (default: localhost)
    MYSQL_USER  (default: root)
    MYSQL_PASS  (default: "")
    MYSQL_DB    (default: AgenticOS)
    MYSQL_PORT  (default: 3306)

The SQLAlchemy engines are built lazily and resiliently — importing this module
never requires a live MySQL server, so unit tests can import it (and bind the
models to the ``agenticos_test`` schema) without a database present.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# Load .env from ~/.agentic-os/.env — never raises if file is absent
load_dotenv(Path.home() / ".agentic-os" / ".env", override=False)

log = logging.getLogger(__name__)

# ── connection config ─────────────────────────────────────────────────────────
_DB_NAME = os.getenv("MYSQL_DB", "AgenticOS")

_CFG = {
    "host":     os.getenv("MYSQL_HOST", "localhost"),
    "user":     os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASS", ""),
    "database": _DB_NAME,
    "port":     int(os.getenv("MYSQL_PORT", "3306")),
}


def _build_url() -> str:
    """Build the SQLAlchemy connection URL (mysql-connector driver).

    The password is URL-encoded so special characters survive the URL parse.
    """
    user = quote_plus(_CFG["user"])
    password = quote_plus(_CFG["password"])
    host = _CFG["host"]
    port = _CFG["port"]
    db = _CFG["database"]
    return f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db}"


def _server_url() -> str:
    """Build a SQLAlchemy URL to the MySQL *server* — no database selected.

    Used to CREATE DATABASE (before it exists) and to ping availability,
    mirroring ``conftest._server_url``.
    """
    user = quote_plus(_CFG["user"])
    password = quote_plus(_CFG["password"])
    host = _CFG["host"]
    port = _CFG["port"]
    return f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/"


# ── declarative base + engine (lazy) ──────────────────────────────────────────
Base = declarative_base()

engine: Engine = create_engine(
    _build_url(),
    pool_pre_ping=True,   # resilient — drops dead connections before use
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)

_AVAILABLE: bool | None = None   # None = not yet checked
_SCHEMA_READY = False


def is_available() -> bool:
    """True if the MySQL server is reachable. Cached after first check.

    Pings via a short-lived server-level SQLAlchemy engine (no database
    selected), so it succeeds even before the ``agenticos`` schema exists.
    """
    global _AVAILABLE
    if _AVAILABLE is not None:
        return _AVAILABLE
    try:
        server = create_engine(_server_url(), pool_pre_ping=True, future=True)
        try:
            with server.connect():
                pass
        finally:
            server.dispose()
        _AVAILABLE = True
    except Exception as exc:  # noqa: BLE001
        log.warning("MySQL unavailable — SQLAlchemy data layer disabled: %s", exc)
        _AVAILABLE = False
    return _AVAILABLE


def get_session() -> Session:
    """Return a new SQLAlchemy session bound to the shared engine.

    Callers own the session lifecycle (close it when done).
    """
    return SessionLocal()


def init_db() -> None:
    """Ensure the database + tables exist. Idempotent; safe at startup.

    Steps:
      1. ``CREATE DATABASE IF NOT EXISTS`` via a server-level SQLAlchemy engine
         (no database selected).
      2. Import the models module so all tables register on ``Base.metadata``.
      3. ``Base.metadata.create_all(engine)`` to materialise the tables.
      4. Apply the idempotent Phase 13a ALTER migration.

    If MySQL is unreachable this logs a warning and returns without raising,
    so a failed database never blocks sidecar startup.
    """
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    if not is_available():
        log.warning("init_db() skipped — MySQL is not available.")
        return

    try:
        # 1. Create the database if it doesn't exist (no DB selected).
        server = create_engine(_server_url(), pool_pre_ping=True, future=True)
        try:
            with server.begin() as conn:
                conn.execute(text(
                    f"CREATE DATABASE IF NOT EXISTS `{_DB_NAME}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                ))
        finally:
            server.dispose()

        # 2. Import models so their tables register on Base.metadata.
        from gui.sidecar import models  # noqa: F401

        # 3. Materialise the tables.
        Base.metadata.create_all(engine)

        # 4. Phase 13a — apply idempotent ALTERs to pre-existing tables
        #    (create_all never ALTERs). Guarded internally; never raises.
        from gui.sidecar.migrations import ensure_phase13_schema
        migration = ensure_phase13_schema(engine)
        for warning in migration.get("warnings", []):
            log.warning("init_db migration warning: %s", warning)

        _SCHEMA_READY = True
        log.info("SQLAlchemy schema ready in `%s`.", _DB_NAME)
    except Exception as exc:  # noqa: BLE001
        log.warning("init_db() failed — SQLAlchemy schema not created: %s", exc)
