"""Seed the port ledger (``ports`` table) from the authoritative registry.

Source of truth: ``~/Codehome/hub/docs/PORT_ASSIGNMENTS.md`` — the Codehome port
registry (Hub reserved ports + per-app ``web.port`` / backend ports). This
script mirrors that doc into the ``ports`` ledger so the diagnostics dashboard
reflects real reservations and ``project_manager.allocate_port`` avoids every
already-claimed port when scaffolding new projects.

Idempotent: existing rows are left as-is (their original ``allocated_at`` is
preserved); only missing ports are inserted. Rows are written with
``status="reserved"`` to distinguish registry-seeded ports from ports handed
out dynamically by scaffolding (``status="allocated"``). ``allocate_port``
counts rows regardless of status, so both are honoured for collision-avoidance.

Run:  .venv/bin/python -m gui.sidecar.seed_port_ledger

NOTE on data-quality issues in the current doc (surfaced 2026-07-01):
  * Port 3000 is double-booked (projmanager + igotyou) — merged into one row.
  * Port 5173 is listed for both the RETIRED Hub Vite server and the worldwise
    app — seeded once for the active app (worldwise).
  * The explicitly RETIRED Hub ports (8085 Hub API, 5173 Hub Vite) are NOT
    reserved here — they are decommissioned and free for reuse.
"""
from __future__ import annotations

from datetime import datetime, timezone

# (port, app_id) mirrored from PORT_ASSIGNMENTS.md. Duplicate ports are merged
# into a single owner label; see the module docstring.
SEED: list[tuple[int, str]] = [
    # ── reserved service ports ──
    (5130, "agenticos-sidecar"),      # AgenticOS FastAPI sidecar (TR-10)
    # ── app web ports ──
    (3000, "projmanager,igotyou"),    # DOUBLE-BOOKED in the doc — merged
    (3002, "taste-dees"),
    (4000, "physics"),
    (5100, "keno"),
    (5101, "songtrans"),
    (5102, "solar-system"),
    (5103, "ufc"),
    (5104, "agentic"),
    (5105, "weather"),
    (5106, "ai-voice"),
    (5107, "mazegame"),
    (5108, "shuffle"),
    (5110, "chem"),
    (5111, "dreamcatcher-backend"),   # dreamcatcher separate API server
    (5112, "astro-physics-hub"),
    (5120, "dreamcatcher"),
    (5173, "worldwise"),              # retired Hub Vite also used 5173 (now free)
    (5200, "blackjack"),
    (8090, "battester"),
]


def seed(session=None) -> dict:
    """Insert any missing registry ports into the ledger. Idempotent.

    Returns a summary dict: {inserted, skipped, total, ports:[...]}.
    """
    from gui.sidecar.db import SessionLocal
    from gui.sidecar.models import Port

    owns = session is None
    session = session or SessionLocal()
    inserted, skipped = [], []
    try:
        existing = {row.port for row in session.query(Port).all()}
        now = datetime.now(timezone.utc)
        for port, app_id in SEED:
            if port in existing:
                skipped.append(port)
                continue
            session.add(Port(port=port, app_id=app_id, status="reserved",
                             allocated_at=now))
            inserted.append(port)
        session.commit()
        total = session.query(Port).count()
    finally:
        if owns:
            session.close()
    return {"inserted": sorted(inserted), "skipped": sorted(skipped),
            "total_in_ledger": total}


if __name__ == "__main__":
    import json
    print(json.dumps(seed(), indent=2))
