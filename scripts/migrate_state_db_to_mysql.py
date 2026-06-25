#!/usr/bin/env python3
"""One-time copy of leftover SQLite state into MySQL (migration Phase 6).

Background: the SQLite -> MySQL migration moved `run_history` and `briefed_docs`
into the `AgenticOS` MySQL schema. Rows written to the old `data/state.db`
*before* that switch are not carried over automatically. This script copies
them, idempotently, so historical run history and the briefing dedupe set
survive the cutover.

LangGraph checkpoints are deliberately NOT migrated — they are disposable
run-scratch state, recreated on the next run.

Usage:
    ./.venv/bin/python scripts/migrate_state_db_to_mysql.py            # copy rows
    ./.venv/bin/python scripts/migrate_state_db_to_mysql.py --dry-run  # report only
    ./.venv/bin/python scripts/migrate_state_db_to_mysql.py --delete-after

Safe to run more than once: inserts use INSERT IGNORE keyed on the primary
keys (`run_id` / `doc_hash`), so existing rows are never duplicated or
overwritten.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Make `core` importable when run as a script from anywhere.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import memory  # noqa: E402

STATE_DB = PROJECT_ROOT / "data" / "state.db"

# (sqlite table, columns, MySQL INSERT) — column order is shared between read+write.
RUN_HISTORY_COLS = (
    "run_id", "workflow", "started_at", "finished_at",
    "status", "tokens_used", "cost_usd", "detail",
)
BRIEFED_DOCS_COLS = ("doc_hash", "title", "path", "first_briefed_at")


def _sqlite_has_table(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _sqlite_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _read_rows(con: sqlite3.Connection, table: str, cols: tuple[str, ...]) -> list[tuple]:
    """Read rows for the requested columns, tolerating older schemas that may
    be missing some columns (those come back as NULL)."""
    present = _sqlite_columns(con, table)
    select = ", ".join(c if c in present else "NULL" for c in cols)
    return con.execute(f"SELECT {select} FROM {table}").fetchall()


def migrate(dry_run: bool = False, delete_after: bool = False) -> int:
    if not STATE_DB.exists():
        print(f"No SQLite file at {STATE_DB} — nothing to migrate. ✓")
        return 0

    con = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
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

    print(f"Found in {STATE_DB.name}: {len(runs)} run_history, {len(docs)} briefed_docs.")
    if dry_run:
        print("--dry-run: no rows written.")
        return 0
    if not runs and not docs:
        print("Nothing to copy. ✓")
        return 0

    memory.ensure_schema()
    conn = memory._db()  # noqa: SLF001 — internal helper reused intentionally
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

    if delete_after:
        for suffix in ("", "-wal", "-shm"):
            p = STATE_DB.with_name(STATE_DB.name + suffix)
            if p.exists():
                p.unlink()
                print(f"Removed {p.name}")
    else:
        print(
            "\nLeftover data/state.db kept. Re-running is safe (INSERT IGNORE). "
            "Pass --delete-after once you've confirmed the rows landed in MySQL."
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Copy leftover SQLite state into MySQL.")
    ap.add_argument("--dry-run", action="store_true", help="report counts, write nothing")
    ap.add_argument(
        "--delete-after", action="store_true",
        help="delete data/state.db (and -wal/-shm) after a successful copy",
    )
    args = ap.parse_args()
    return migrate(dry_run=args.dry_run, delete_after=args.delete_after)


if __name__ == "__main__":
    sys.exit(main())
