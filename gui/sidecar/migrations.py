"""Phase 13a — lightweight, idempotent schema migrations (no Alembic).

``Base.metadata.create_all()`` only CREATEs missing tables — it never ALTERs
existing ones. The live ``projects`` (27 rows) and ``ports`` (28 rows) tables
predate Phase 13, so their new columns/constraints must be added explicitly.

``ensure_phase13_schema(engine)``:
  1. ``create_all`` — materialises any brand-new tables (app_commands,
     app_processes, app_health_checks, port_collision_log) and, on a fresh
     database, the full current-shape schema.
  2. Adds missing columns to pre-existing tables via ``ALTER TABLE``:
        projects.venv_path   VARCHAR(512) NULL
        ports.port_type      VARCHAR(32) NOT NULL DEFAULT 'api'
  3. Adds the ``uk_app_port_type`` unique index on ports(app_id, port_type)
     if absent. If existing data violates it (two ports of the same type for
     one app), the failure is logged as a warning — never raised — so sidecar
     startup is never blocked.

Later brand-new tables (e.g. ``osa_settings`` — OSA brain pin, 2026-07-07)
ride step 1: ``create_all`` materialises them with no ALTERs needed, so they
need no entry in the lists below.

Everything is inspected first (``sqlalchemy.inspect``), so re-running is a
no-op. Dialect-neutral SQL only (works on MySQL and SQLite, which both
support ``ALTER TABLE ... ADD COLUMN`` and ``CREATE UNIQUE INDEX``).
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

#: (table, column, dialect-neutral column DDL)
_MISSING_COLUMNS: list[tuple[str, str, str]] = [
    ("projects", "venv_path", "VARCHAR(512) NULL"),
    ("ports", "port_type", "VARCHAR(32) NOT NULL DEFAULT 'api'"),
]

_UNIQUE_INDEXES: list[tuple[str, str, tuple[str, ...]]] = [
    ("ports", "uk_app_port_type", ("app_id", "port_type")),
]


def _existing_columns(engine: Engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def _existing_indexes(engine: Engine, table: str) -> set[str]:
    insp = inspect(engine)
    names = {i.get("name") for i in insp.get_indexes(table)}
    try:  # unique constraints may be reported separately (dialect-dependent)
        names |= {c.get("name") for c in insp.get_unique_constraints(table)}
    except NotImplementedError:  # pragma: no cover
        pass
    return {n for n in names if n}


def ensure_phase13_schema(engine: Engine) -> dict:
    """Bring an existing database up to the Phase 13a schema. Idempotent.

    Returns {"created_tables": [...], "added_columns": [...],
    "added_indexes": [...], "warnings": [...]} — and NEVER raises.
    """
    result: dict = {
        "created_tables": [], "added_columns": [],
        "added_indexes": [], "warnings": [],
    }

    try:
        from gui.sidecar import models  # noqa: F401 — register tables on Base
        from gui.sidecar.db import Base

        before = set(inspect(engine).get_table_names())
        Base.metadata.create_all(engine)
        after = set(inspect(engine).get_table_names())
        result["created_tables"] = sorted(after - before)
    except Exception as exc:  # noqa: BLE001
        msg = f"create_all failed: {exc}"
        log.warning("ensure_phase13_schema: %s", msg)
        result["warnings"].append(msg)
        return result  # nothing else is safe without table metadata

    # ── add missing columns ───────────────────────────────────────────────────
    for table, column, ddl in _MISSING_COLUMNS:
        try:
            if column in _existing_columns(engine, table):
                continue
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            result["added_columns"].append(f"{table}.{column}")
            log.info("ensure_phase13_schema: added column %s.%s", table, column)
        except Exception as exc:  # noqa: BLE001
            msg = f"ALTER {table} ADD {column} failed: {exc}"
            log.warning("ensure_phase13_schema: %s", msg)
            result["warnings"].append(msg)

    # ── add missing unique indexes ───────────────────────────────────────────
    for table, index_name, columns in _UNIQUE_INDEXES:
        try:
            if index_name in _existing_indexes(engine, table):
                continue
            cols = ", ".join(columns)
            with engine.begin() as conn:
                conn.execute(
                    text(f"CREATE UNIQUE INDEX {index_name} ON {table} ({cols})")
                )
            result["added_indexes"].append(f"{table}.{index_name}")
            log.info("ensure_phase13_schema: added unique index %s on %s(%s)",
                     index_name, table, cols)
        except Exception as exc:  # noqa: BLE001
            # Most likely cause: existing rows violate uniqueness. Surface it
            # loudly in the log but never block startup.
            msg = (
                f"CREATE UNIQUE INDEX {index_name} ON {table} failed "
                f"(existing rows may violate uniqueness — review the ledger): {exc}"
            )
            log.warning("ensure_phase13_schema: %s", msg)
            result["warnings"].append(msg)

    return result
