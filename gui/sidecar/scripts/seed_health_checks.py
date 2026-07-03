"""Phase 13e — Seed ``app_health_checks`` from live, verified endpoints.

Locked decision (with Tony, 2026-07-03): health checks are seeded ONLY for
endpoints that answer correctly RIGHT NOW — no guessed rows. For every typed
``ports`` ledger row whose port is live (TCP), candidate endpoints are probed
in order and the first HTTP 200 wins:

    /api/health  →  /health  →  /docs  →  /

Apps whose port isn't live are reported as ``not_running`` — re-run the
script while they're up to add them. Apps whose live port answers nothing
with a 200 are reported as ``no_endpoint`` (nothing inserted — the pid/port
badge remains their only signal, doc §app_health_checks "optional table").

Idempotent: an existing (app_id, port) row is never touched (``existing``).
``--dry-run`` is the DEFAULT (probes + prints the plan, writes nothing);
``--apply`` commits.

Run:  .venv/bin/python -m gui.sidecar.scripts.seed_health_checks           # dry run
      .venv/bin/python -m gui.sidecar.scripts.seed_health_checks --apply   # commit
"""
from __future__ import annotations

import argparse
import socket
import sys

CANDIDATE_ENDPOINTS: tuple[str, ...] = ("/api/health", "/health", "/docs", "/")


def _tcp_live(port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def plan_seed(session) -> dict:
    """Probe every typed ledger port and build the seeding plan.

    Returns ``{"insert": [...], "existing": [...], "not_running": [...],
    "no_endpoint": [...]}`` where each entry is a dict with at least
    ``app_id`` and ``port``.
    """
    from gui.sidecar.launch_config import _probe_health
    from gui.sidecar.models import AppHealthCheck, Port

    existing = {
        (hc.app_id, hc.port)
        for hc in session.query(AppHealthCheck).all()
    }
    plan = {"insert": [], "existing": [], "not_running": [], "no_endpoint": []}

    for row in session.query(Port).order_by(Port.app_id, Port.port).all():
        entry = {"app_id": row.app_id, "port": row.port,
                 "port_type": row.port_type}
        if (row.app_id, row.port) in existing:
            plan["existing"].append(entry)
            continue
        if not _tcp_live(row.port):
            plan["not_running"].append(entry)
            continue
        for endpoint in CANDIDATE_ENDPOINTS:
            if _probe_health(f"http://localhost:{row.port}{endpoint}",
                             expected_status=200, timeout=3):
                plan["insert"].append({**entry, "endpoint": endpoint})
                break
        else:
            plan["no_endpoint"].append(entry)

    return plan


def apply_seed(session, plan: dict) -> int:
    """Insert the planned rows. Returns the number inserted."""
    from gui.sidecar.models import AppHealthCheck

    for entry in plan["insert"]:
        session.add(AppHealthCheck(
            app_id=entry["app_id"], port=entry["port"],
            endpoint=entry["endpoint"], method="GET",
            expected_status_code=200, timeout_seconds=5,
            interval_seconds=10, enabled=True,
        ))
    session.commit()
    return len(plan["insert"])


def _report(plan: dict, apply_mode: bool) -> str:
    lines = ["Health-check seeding — "
             + ("APPLIED" if apply_mode else "DRY RUN (use --apply to write)")]
    lines.append(f"\nVerified endpoints ({len(plan['insert'])}):")
    for e in plan["insert"]:
        lines.append(f"  + {e['app_id']}:{e['port']}{e['endpoint']}  "
                     f"({e['port_type']})")
    lines.append(f"\nAlready configured, untouched ({len(plan['existing'])}):")
    for e in plan["existing"]:
        lines.append(f"  = {e['app_id']}:{e['port']}")
    lines.append(f"\nNot running — re-run while up ({len(plan['not_running'])}):")
    for e in plan["not_running"]:
        lines.append(f"  · {e['app_id']}:{e['port']}")
    lines.append(f"\nLive but no 200 endpoint ({len(plan['no_endpoint'])}):")
    for e in plan["no_endpoint"]:
        lines.append(f"  ? {e['app_id']}:{e['port']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed app_health_checks from live, verified endpoints "
                    "(dry-run by default).")
    parser.add_argument("--apply", action="store_true",
                        help="write the verified rows (default: dry run)")
    args = parser.parse_args(argv)

    from gui.sidecar.db import SessionLocal
    session = SessionLocal()
    try:
        plan = plan_seed(session)
        if args.apply:
            apply_seed(session, plan)
        print(_report(plan, args.apply))
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
