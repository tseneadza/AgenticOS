"""Native App Registry — Phase 9a (FR-60).

Scans ~/Codehome/**/app.json to build a canonical list of Codehome apps
without requiring the external Hub server on :8085.

Designed for parallel-run: nothing here conflicts with hub_mcp.py.
Both can be queried simultaneously during the transition period.

Schema contract (stable across all sub-phases):
    AppEntry = {
        "id":              str,          # from app.json "id"
        "name":            str,          # from app.json "name"
        "description":     str,
        "icon":            str,
        "category":        str,
        "type":            str,          # "web" | "desktop" | "cli" | ...
        "app_path":        str,          # absolute path to project root
        "start_command":   list[str],    # e.g. ["python3", "api.py"]
        "expected_port":   int | None,   # from web.port
        "venv":            str | None,   # relative venv path if any
        "agent":           dict | None,  # agent capability block
        "scripts":         list[dict],   # scripts[] array from app.json
        "tags":            list[str],
    }

Public API (import-safe, no side effects on import):
    scan()                 -> list[AppEntry]
    get(app_id)            -> AppEntry | None
    get_all()              -> list[AppEntry]   (cached, refreshed every 60s)
    invalidate_cache()     -> None
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── scan roots ───────────────────────────────────────────────────────────────
# Directories under ~/Codehome to search. Excludes hidden dirs and node_modules
# automatically (see _should_skip). Add extra roots via settings.yaml later.
_CODEHOME = Path.home() / "Codehome"

# Directories to never descend into when globbing for app.json.
_SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".cursor", ".claude", ".autoclaude", ".obsidian", ".DS_Store",
    "dist", "build", ".build", "target",
}

# ── simple TTL cache ─────────────────────────────────────────────────────────
_CACHE: list[dict] = []
_CACHE_TS: float = 0.0
_CACHE_TTL: float = 60.0   # seconds


def invalidate_cache() -> None:
    """Force the next get_all() call to re-scan from disk."""
    global _CACHE_TS
    _CACHE_TS = 0.0


# ── internal helpers ──────────────────────────────────────────────────────────

def _find_app_jsons() -> list[Path]:
    """Walk ~/Codehome and return all app.json paths, skipping noise dirs."""
    results: list[Path] = []
    if not _CODEHOME.exists():
        log.warning("Codehome root not found: %s", _CODEHOME)
        return results

    # Use rglob but prune skipped directories manually via os.walk-style logic.
    # Path.rglob doesn't support pruning, so we walk manually.
    def _walk(root: Path) -> None:
        try:
            entries = list(root.iterdir())
        except PermissionError:
            return
        for entry in entries:
            if entry.name in _SKIP_DIRS or entry.name.startswith("."):
                continue
            if entry.is_dir():
                _walk(entry)
            elif entry.name == "app.json":
                results.append(entry)

    _walk(_CODEHOME)
    return results


def _parse_app_json(path: Path) -> dict | None:
    """Parse a single app.json into a normalised AppEntry dict.

    Returns None if the file is malformed or missing required fields.
    """
    try:
        raw: dict[str, Any] = json.loads(path.read_text())
    except Exception as exc:
        log.debug("Skipping %s — parse error: %s", path, exc)
        return None

    app_id = raw.get("id", "").strip()
    if not app_id:
        log.debug("Skipping %s — no 'id' field", path)
        return None

    app_path = str(path.parent)

    # Web block (optional — desktop/cli apps may not have one)
    web: dict = raw.get("web") or {}
    command: list[str] = web.get("command") or []
    expected_port: int | None = web.get("port") or web.get("expected_port")
    venv: str | None = web.get("venv")

    # Resolve venv to an absolute path for the process manager
    venv_abs: str | None = None
    if venv:
        venv_path = path.parent / venv
        if venv_path.exists():
            venv_abs = str(venv_path)

    return {
        "id": app_id,
        "name": raw.get("name", app_id),
        "description": raw.get("description", ""),
        "icon": raw.get("icon", "📦"),
        "category": raw.get("category", "general"),
        "type": raw.get("type", "web"),
        "app_path": app_path,
        "start_command": command,
        "expected_port": expected_port,
        "venv": venv_abs,
        "agent": raw.get("agent"),
        "scripts": raw.get("scripts") or [],
        "tags": raw.get("tags") or [],
    }


# ── public API ────────────────────────────────────────────────────────────────

def scan() -> list[dict]:
    """Scan ~/Codehome for app.json files and return normalised AppEntry list.

    Always reads from disk — no caching. Use get_all() for the cached version.
    """
    entries: list[dict] = []
    seen_ids: set[str] = set()

    for path in _find_app_jsons():
        entry = _parse_app_json(path)
        if entry is None:
            continue
        app_id = entry["id"]
        if app_id in seen_ids:
            log.warning("Duplicate app id %r — keeping first occurrence", app_id)
            continue
        seen_ids.add(app_id)
        entries.append(entry)

    entries.sort(key=lambda e: e["name"].lower())
    log.info("app_registry: scanned %d apps from %s", len(entries), _CODEHOME)
    return entries


def get_all() -> list[dict]:
    """Return the cached app list, refreshing from disk if the TTL has expired."""
    global _CACHE, _CACHE_TS
    now = time.monotonic()
    if now - _CACHE_TS > _CACHE_TTL:
        _CACHE = scan()
        _CACHE_TS = now
    return _CACHE


def get(app_id: str) -> dict | None:
    """Look up a single app by id. Returns None if not found."""
    return next((a for a in get_all() if a["id"] == app_id), None)


def get_manifests() -> dict[str, dict | None]:
    """Return {app_id: agent_block_or_None} for every discovered app.

    Drop-in replacement for hub_mcp._fetch_all_manifests() — same contract,
    no Hub round-trip.
    """
    return {a["id"]: a.get("agent") for a in get_all()}


def get_scripts() -> list[dict]:
    """Return a flat list of all scripts across all apps, each tagged with app_id."""
    results: list[dict] = []
    for app in get_all():
        for script in app.get("scripts") or []:
            results.append({
                **script,
                "app_id": app["id"],
                "app_name": app["name"],
                "app_path": app["app_path"],
            })
    return results
