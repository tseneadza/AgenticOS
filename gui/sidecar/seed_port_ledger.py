"""Reconcile the port ledger (``ports`` table) from the LIVE app registry.

Source of truth: ``core.app_registry.get_all()`` — the filesystem-scanned
app.json registry. (Previously this script mirrored the hand-maintained
``hub/docs/PORT_ASSIGNMENTS.md``, which drifted from reality: 19 of 27 apps,
two double-booked ports. Since 2026-07-02 the flow is inverted — the registry
feeds the ledger AND regenerates the doc.)

Behaviour (idempotent):
  * Missing ports are inserted with ``status="reserved"``.
  * Existing ``reserved`` rows whose owner changed in the registry are
    UPDATED (e.g. the old merged ``projmanager,igotyou`` row on 3000).
  * ``allocated`` rows (handed out by project scaffolding) are never touched;
    a conflict with the registry is reported, not overwritten.
  * ``reserved`` rows for ports no longer claimed by any app or service are
    pruned.
  * Duplicate ports in the registry itself are reported as conflicts and NOT
    seeded — fix the offending app.json files first.

Also regenerates ``~/Codehome/hub/docs/PORT_ASSIGNMENTS.md`` as a
generated artifact (see ``generate_doc``).

Run:  .venv/bin/python -m gui.sidecar.seed_port_ledger          # reconcile + doc
      .venv/bin/python -m gui.sidecar.seed_port_ledger --no-doc # ledger only
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Service ports that are not app.json-discovered apps but must never be
# handed out by allocate_port.
SERVICE_PORTS: list[tuple[int, str, str]] = [
    (5130, "agenticos-sidecar", "AgenticOS FastAPI sidecar (AG-UI + orchestrator API, TR-10)"),
    (5111, "dreamcatcher-backend", "dreamcatcher separate API server"),
    (12434, "ollama-local", "OSA local brain — Ollama server (curated instance, tool-capable models); settings.yaml agent.ollama_base_url"),
]

DOC_PATH = Path.home() / "Codehome" / "hub" / "docs" / "PORT_ASSIGNMENTS.md"


def _registry_ports() -> tuple[dict[int, str], dict[int, list[str]]]:
    """Return ({port: app_id}, {port: [app_ids]} for conflicts) from the live registry."""
    from core import app_registry

    claims: dict[int, list[str]] = defaultdict(list)
    for a in app_registry.get_all():
        get = (lambda k, a=a: a.get(k) if isinstance(a, dict) else getattr(a, k, None))
        app_id = get("id") or get("app_id") or get("name")
        port = get("expected_port") or get("port")
        if app_id and port:
            claims[int(port)].append(str(app_id))

    clean = {p: ids[0] for p, ids in claims.items() if len(ids) == 1}
    conflicts = {p: ids for p, ids in claims.items() if len(ids) > 1}
    return clean, conflicts


def seed(session=None) -> dict:
    """Reconcile the ledger against the registry + service ports. Idempotent.

    Returns {inserted, updated, pruned, skipped_allocated, registry_conflicts,
    total_in_ledger}.
    """
    from gui.sidecar.db import SessionLocal
    from gui.sidecar.models import Port

    registry, conflicts = _registry_ports()
    desired: dict[int, str] = dict(registry)
    for port, app_id, _note in SERVICE_PORTS:
        desired.setdefault(port, app_id)

    owns = session is None
    session = session or SessionLocal()
    inserted, updated, pruned, skipped_allocated = [], [], [], []
    try:
        rows = {row.port: row for row in session.query(Port).all()}
        now = datetime.now(timezone.utc)

        for port, app_id in sorted(desired.items()):
            row = rows.get(port)
            if row is None:
                session.add(Port(port=port, app_id=app_id, status="reserved",
                                 allocated_at=now))
                inserted.append(port)
            elif row.app_id != app_id:
                if row.status == "allocated":
                    skipped_allocated.append(
                        {"port": port, "ledger": row.app_id, "registry": app_id})
                else:
                    row.app_id = app_id
                    updated.append(port)

        for port, row in rows.items():
            if port not in desired and row.status == "reserved":
                session.delete(row)
                pruned.append(port)

        session.commit()
        total = session.query(Port).count()
    finally:
        if owns:
            session.close()

    return {
        "inserted": sorted(inserted),
        "updated": sorted(updated),
        "pruned": sorted(pruned),
        "skipped_allocated": skipped_allocated,
        "registry_conflicts": {p: ids for p, ids in sorted(conflicts.items())},
        "total_in_ledger": total,
    }


def generate_doc(path: Path = DOC_PATH) -> str:
    """Regenerate PORT_ASSIGNMENTS.md from the live registry. Returns the text."""
    registry, conflicts = _registry_ports()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Codehome Port Assignments",
        "",
        "> **GENERATED FILE — DO NOT EDIT BY HAND.**",
        "> Regenerate with `.venv/bin/python -m gui.sidecar.seed_port_ledger`",
        f"> (AgenticOS repo). Source of truth: the live `app.json` registry. Last generated: {now}.",
        "",
        "To change an app's port, edit its `app.json` (`web.port`) — and its dev",
        "command/config if the port is duplicated there — then re-run the",
        "generator so this doc and the `ports` ledger stay in sync.",
        "",
        "## Reserved service ports",
        "",
        "| Port | Service | Notes |",
        "|------|---------|-------|",
    ]
    for port, app_id, note in sorted(SERVICE_PORTS):
        lines.append(f"| {port} | {app_id} | {note} |")

    lines += [
        "",
        "## App ports (from the live registry)",
        "",
        "| Port | App |",
        "|------|-----|",
    ]
    for port, app_id in sorted(registry.items()):
        lines.append(f"| {port} | {app_id} |")

    if conflicts:
        lines += ["", "## ⚠ CONFLICTS — fix these app.json files", ""]
        for port, ids in sorted(conflicts.items()):
            lines.append(f"- Port **{port}** claimed by: {', '.join(ids)}")

    lines += [
        "",
        "## Historical notes",
        "",
        "- 8085 (Hub API) — Hub decommissioned 2026-06-26 (Phase 9d); the `hub`",
        "  binary still registers 8085 while it remains runnable.",
        "- 2026-07-02: resolved double-bookings — `igotyou` 3000→3001,",
        "  `worldwise` 5112→5173 (astro-physics-hub keeps 5112,",
        "  projmanager keeps 3000).",
        "",
    ]
    text = "\n".join(lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return text


if __name__ == "__main__":
    import json
    import sys

    result = seed()
    print(json.dumps(result, indent=2))
    if "--no-doc" not in sys.argv:
        generate_doc()
        print(f"doc regenerated: {DOC_PATH}")
    if result["registry_conflicts"]:
        print("WARNING: registry conflicts present — not seeded.", file=sys.stderr)
        sys.exit(1)
