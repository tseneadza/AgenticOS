"""Shared pytest fixtures for the sidecar test suite.

Phase 13a establishes the MySQL-everywhere testing rule (decision locked with
Tony 2026-07-02): new tests run against a real MySQL schema —
``agenticos_test`` — instead of in-memory SQLite, so what we test is what
production runs. The live ``agenticos`` schema is never touched.

Fixtures:
    mysql_engine  (session-scoped) — SQLAlchemy engine bound to
        ``agenticos_test``; creates the database + all tables on first use.
        Skips the requesting tests cleanly if MySQL is unreachable.
    db_session    (function-scoped) — a Session on that engine; wipes every
        table after each test for isolation.

Legacy suites (test_phase11a/11c) still carry their own SQLite fixtures —
converting them is scheduled as Phase 13f (SQLAlchemy consolidation).

Connection config comes from the same ~/.agentic-os/.env vars as production
(``gui.sidecar.db._CFG``); only the database name is overridden.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

TEST_DB = "agenticos_test"


def _server_url(cfg: dict) -> str:
    """URL to the MySQL *server* (no database selected)."""
    return (
        f"mysql+mysqlconnector://{quote_plus(cfg['user'])}:"
        f"{quote_plus(cfg['password'])}@{cfg['host']}:{cfg['port']}/"
    )


def _test_db_url(cfg: dict) -> str:
    return _server_url(cfg) + TEST_DB


@pytest.fixture(scope="session")
def mysql_engine():
    """Engine bound to the ``agenticos_test`` schema (created if missing)."""
    from gui.sidecar.db import _CFG, Base
    from gui.sidecar import models  # noqa: F401 — register tables on Base

    # 1. Reach the server; create the test database.
    try:
        server = create_engine(_server_url(_CFG), pool_pre_ping=True, future=True)
        with server.begin() as conn:
            conn.execute(text(
                f"CREATE DATABASE IF NOT EXISTS `{TEST_DB}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            ))
        server.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"MySQL unavailable — skipping DB-backed tests: {exc}")

    # 2. Engine on the test schema; materialise the full current schema.
    engine = create_engine(_test_db_url(_CFG), pool_pre_ping=True, future=True)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(mysql_engine):
    """A Session on ``agenticos_test``; all tables are wiped after the test."""
    from sqlalchemy.orm import sessionmaker
    from gui.sidecar.db import Base

    Session = sessionmaker(bind=mysql_engine, autoflush=False, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        # Wipe in reverse dependency order (no FKs today, but future-safe).
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        session.close()
