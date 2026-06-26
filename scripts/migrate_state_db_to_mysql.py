#!/usr/bin/env python3
"""One-time copy of leftover SQLite state into MySQL (migration Phase 6).

Background: the SQLite -> MySQL migration moved `run_history` and `briefed_docs`
into the `AgenticOS` MySQL schema. Rows written to the old SQLite database
*before* that switch are not carried over automatically. This script copies
them, idempotently, so historical run history and the briefing dedupe set
survive the cutover.

Source file: it reads `data/state.db` if present, otherwise the preserved
backup `data/state.db.bak` (the live DB is renamed to `.bak` once retired).

LangGraph checkpoints are deliberately NOT migrated -- they are disposable
run-scratch state, recreated on the next run.

This script is NON-DESTRUCTIVE: it never deletes the SQLite file. With
`--archive` it renames a live `data/state.db` to `data/state.db.bak` after a
successful copy (an existing `.bak` is timestamped, never overwritten).

Usage:
    ./.venv/bin/python scripts/migrate_state_db_to_mysql.py            # copy rows
    ./.venv/bin/python scripts/migrate_state_db_to_mysql.py --dry-run  # report only
    ./.venv/bin/python scripts/migrate_state_db_to_mysql.py --archive  # copy, then rename live state.db -> .bak

Safe to run more than once: inserts use INSERT IGNORE keyed on the primary
keys (`run_id` / `doc_hash`), so existing rows are never duplicated or
overwritten.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sqlite3
import sys
from pathlib import Path

# Make `core` importable when run as a script from anywhere.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import memory  # noqa: E402

DATA_DIR = PROJECT_ROOT / "data"
# Preference order: a live state.db, else the retired backup.
SOURCE_CANDIDATES = (DATA_DIR / "state.db", DATA_DIR / "state.db.bak")

RUN_HISTORY_COLS = (
    "run_id", "workflow", "started_at", "finished_at",
    "status", "tokens_used", "cost_usd", "detail",
)
BRIEFED_DOCS_COLS = ("doc_hash", "title", "path", "first_briefed_at")


def _find_source() -> Path | None:
    """Return the first existing SQLite source file, or None if none found."""
    for p in SOURCE_CANDIDATES:
        if p.exists():
            return p
    return None


def _sqlite_has_table(con: sqlite3.Connection, name: str) -> bool:
    """Check whether a table exists in the SQLite database.

    Args:
        con: Open SQLite connection.
        name: Table name to look for.

    Returns:
        True if the table exists, False otherwise.
    """
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _sqlite_columns(con: sqlite3.Connection, table: str) -> set[str]:
    """Return the set of column names for a SQLite table.

    Args:
        con: Open SQLite connection.
        table: Table name to inspect.

    Returns:
        Set of column name strings.
    """
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _read_rows(con: sqlite3.Connection, table: str, cols: tuple[str, ...]) -> list[tuple]:
    """Read rows for the requested columns, tolerating older schemas that may
    be missing some columns (those come back as NULL)."""
    present = _sqlite_columns(con, table)
    select = ", ".join(c if c in present else "NULL" for c in cols)
    return con.execute(f"SELECT {select} FROM {table}").fetchall()


def _archive(src: Path) -> None:
    """Rename a live state.db to state.db.bak (never delete; never overwrite)."""
    if src.name != "state.db":
        print(f"Source is already a backup ({src.name}) -- nothing to archive.")
        return
    target = src.with_name("state.db.bak")
    if target.exists():
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        target = src.with_name(f"state.db.bak-{stamp}")
    src.rename(target)
    print(f"Archived {src.name} -> {target.name} (not deleted).")


def migrate(dry_run: bool = False, archive: bool = False) -> int:
    """Copy run_history and briefed_docs rows from SQLite into MySQL.

    Uses INSERT IGNORE so re-running is safe and idempotent.

    Args:
        dry_run: If True, report counts without writing any rows.
        archive: If True, rename a live state.db to .bak after copying.

    Returns:
        Exit code (0 for success).
    """
    src = _find_source()
    if src is None:
        print(
            f"No SQLite file found ({' or '.join(p.name for p in SOURCE_CANDIDATES)}) "
            "-- nothing to migrate. ✓"
        )
        return 0

    print(f"Source: {src}")
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        runs = (
            _read_rows(con, "run_history", RUN_HISTORY_COLS)
            if _sqlite_has_table(con, "run_history")
            else []
        )
        docs = (
            _read_rows(con, "briefed_docs", BRIEFED_DOCS_COLS)
            if _sqlite_has_table(con, "briefed_docs")
            else []
        )
    finally:
        con.close()

    print(f"Found: {len(runs)} run_history, {len(docs)} briefed_docs.")
    if dry_run:
        print("--dry-run: no rows written.")
        return 0
    if not runs and not docs:
        print("Nothing to copy. ✓")
        if archive:
            _archive(src)
        return 0

    memory.ensure_schema()
    conn = memory._db()  # noqa: SLF001 -- internal helper reused intentionally
    try:
        cur = conn.cursor()
        inserted_runs = inserted_docs = 0
        if runs:
            cur.executemany(
                "INSERT IGNORE INTO run_history "
                "(run_id, workflow, started_at, finished_at, status, tokens_used, cost_usd, detail) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                runs,
            )
            inserted_runs = cur.rowcount
        if docs:
            cur.executemany(
                "INSERT IGNORE INTO briefed_docs "
                "(doc_hash, title, path, first_briefed_at) VALUES (%s,%s,%s,%s)",
                docs,
            )
            inserted_docs = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    print(
        f"Copied into MySQL (new rows only): {inserted_runs} run_history, "
        f"{inserted_docs} briefed_docs. ✓"
    )

    if archive:
        _archive(src)
    else:
        print(
            "\nSQLite file kept as-is (never deleted). Re-running is safe "
            "(INSERT IGNORE). Pass --archive to rename a live state.db -> .bak."
        )
    return 0


def main() -> int:
    """Parse CLI arguments and run the migration."""
    ap = argparse.ArgumentParser(
        description="Copy leftover SQLite state into MySQL (non-destructive)."
    )
    ap.add_argument("--dry-run", action="store_true", help="report counts, write nothing")
    ap.add_argument(
        "--archive", action="store_true",
        help="after a successful copy, rename a live data/state.db to .bak (never deletes)",
    )
    args = ap.parse_args()
    return migrate(dry_run=args.dry_run, archive=args.archive)


if __name__ == "__main__":
    sys.exit(main())
