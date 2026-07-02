"""Backfill the ``projects`` ledger from the LIVE app registry.

Source of truth: ``core.app_registry.get_all()`` (filesystem-scanned app.json),
the same source that feeds the ``ports`` ledger (see ``seed_port_ledger.py``).

Why this exists: the ``projects`` table is written to only by the Project
Creation drawer (``create_project_full``, ``created_by='osa'``), so it starts
empty even though ~/Codehome already holds many apps. Those existing apps are
known to AgenticOS *only* through the filesystem registry, which means the
drawer's subfolder discovery (``scan_codehome_structure`` — ledger-based) and
``GET /api/projects`` see nothing until you scaffold. This backfill indexes the
discovered apps into the ledger so both reflect reality.

Backfilled rows are marked ``created_by='discovered'`` and ``template='imported'``
so they stay distinguishable from projects the drawer actually scaffolds. The
filesystem registry remains the source of truth; this table is a synced index.

Idempotent: existing rows (by id) are updated in place if their registry-derived
fields changed; apps without an ``app_path`` are skipped (``path`` is required);
a path already owned by a different id is reported as a conflict, not overwritten.

Run:  .venv/bin/python -m gui.sidecar.seed_projects_ledger
"""
from __future__ import annotations

from pathlib import Path

CODEHOME = Path.home() / "Codehome"


def _subfolder_for(app_path: str) -> str:
    """Derive the ~/Codehome bucket for an app path (parts between Codehome and leaf)."""
    try:
        rel = Path(app_path).resolve().relative_to(CODEHOME.resolve())
    except (ValueError, OSError):
        return ""
    parts = rel.parts
    return "/".join(parts[:-1]) if len(parts) > 1 else ""


def seed(session=None) -> dict:
    """Backfill/refresh the projects ledger from the live registry. Idempotent.

    Returns {inserted, updated, skipped_no_path, path_conflicts, total_in_ledger}.
    """
    from core import app_registry
    from gui.sidecar.db import SessionLocal
    from gui.sidecar.models import Project

    owns = session is None
    session = session or SessionLocal()
    inserted, updated, skipped_no_path, path_conflicts = [], [], [], []
    try:
        rows = {p.id: p for p in session.query(Project).all()}
        path_owner = {p.path: p.id for p in rows.values()}

        for a in app_registry.get_all():
            aid = a.get("id") or a.get("name")
            app_path = a.get("app_path")
            if not aid or not app_path:
                if aid:
                    skipped_no_path.append(aid)
                continue

            # Guard the unique path constraint.
            if path_owner.get(app_path, aid) != aid:
                path_conflicts.append(
                    {"path": app_path, "existing": path_owner[app_path], "incoming": aid})
                continue

            fields = dict(
                name=a.get("name") or aid,
                description=a.get("description"),
                path=app_path,
                subfolder=_subfolder_for(app_path),
                template="imported",
                port=a.get("expected_port"),
                created_by="discovered",
            )

            row = rows.get(aid)
            if row is None:
                session.add(Project(id=aid, **fields))
                inserted.append(aid)
                path_owner[app_path] = aid
            else:
                # Never clobber a real scaffolded project; only refresh discovered ones.
                if row.created_by == "discovered" and (
                    row.port != fields["port"]
                    or row.subfolder != fields["subfolder"]
                    or row.name != fields["name"]
                ):
                    for k, v in fields.items():
                        setattr(row, k, v)
                    updated.append(aid)

        session.commit()
        total = session.query(Project).count()
    finally:
        if owns:
            session.close()

    return {
        "inserted": sorted(inserted),
        "updated": sorted(updated),
        "skipped_no_path": sorted(skipped_no_path),
        "path_conflicts": path_conflicts,
        "total_in_ledger": total,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(seed(), indent=2))
