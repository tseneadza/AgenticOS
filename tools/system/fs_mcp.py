"""Filesystem capabilities — Phase 15b (design §5.2).

Reads (``read_file`` / ``list_dir`` / ``search``) auto-run, scoped to the
Constitution's ``system_mcp.fs.allowed_roots``. Writes are gated by the
policy ladder — except inside ``scratch_root``, where they auto-run. Move
and delete are irreversible: always gated, never auto.

Root scoping is enforced by ``_policy`` on the FIRST path argument (the
guard runs before these bodies); ``move``'s destination is re-checked here
with the same symlink-resolving helper, raising ``ConstitutionViolation``
so an approved move still cannot land outside the roots.

DELIBERATE DEVIATION from the design's "builds on tools/filesystem_tool.py"
line: that module is the VAULT write path — it spawns an npx MCP client,
guards against the constitution's ``write_allowlist`` (a different list),
and counts workflow writes. Wrapping it here would double-guard with
mismatched allowlists and add a node dependency for a stat call. These
capabilities use pathlib directly; ``filesystem_tool.py`` remains the
workflow agents' vault path.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from core.constitution import ConstitutionViolation

from tools.system import _policy
from tools.system._harness import capability

_MAX_READ_CHARS = 20000
_MAX_ENTRIES = 500
_MAX_SEARCH_RESULTS = 50

_PATH_PROP = {"type": "string", "description": "Absolute path (~ ok); must be inside the allowed roots."}


def _fs_cfg() -> dict:
    """The live ``system_mcp.fs`` block (honors the harness test seam)."""
    from tools.system import _harness

    c = _harness._constitution_override
    if c is None:
        from core.constitution import Constitution

        c = Constitution.load()
    return c.system_mcp.get("fs", {})


def _require_in_roots(path: str, what: str) -> Path:
    """Resolve ``path`` and hard-fail if it's outside allowed_roots."""
    cfg = _fs_cfg()
    if not _policy.under_any_root(path, cfg.get("allowed_roots", [])):
        raise ConstitutionViolation(
            f"{what} outside allowed filesystem roots: {path}"
        )
    return _policy.resolve_path(path)


@capability(
    "fs.read_file",
    domain="fs",
    effect="read",
    auto=True,
    schema={
        "type": "object",
        "properties": {
            "path": _PATH_PROP,
            "max_chars": {"type": "integer", "default": _MAX_READ_CHARS},
        },
        "required": ["path"],
    },
)
def read_file(path: str, max_chars: int = _MAX_READ_CHARS) -> dict:
    """Read a UTF-8 text file inside the allowed roots (content capped)."""
    if not (path or "").strip():
        return {"ok": False, "error": "path required"}
    p = _policy.resolve_path(path)
    if not p.is_file():
        return {"ok": False, "error": f"not a file: {path}"}
    text = p.read_text(encoding="utf-8", errors="replace")
    return {
        "ok": True,
        "path": str(p),
        "size_bytes": p.stat().st_size,
        "truncated": len(text) > max_chars,
        "content": text[:max_chars],
    }


@capability(
    "fs.list_dir",
    domain="fs",
    effect="read",
    auto=True,
    schema={
        "type": "object",
        "properties": {"path": _PATH_PROP},
        "required": ["path"],
    },
)
def list_dir(path: str) -> dict:
    """List a directory inside the allowed roots (name/type/size per entry)."""
    if not (path or "").strip():
        return {"ok": False, "error": "path required"}
    p = _policy.resolve_path(path)
    if not p.is_dir():
        return {"ok": False, "error": f"not a directory: {path}"}
    entries = []
    for child in sorted(p.iterdir(), key=lambda c: c.name.lower()):
        try:
            entries.append(
                {
                    "name": child.name,
                    "type": "dir" if child.is_dir() else "file",
                    "size_bytes": None if child.is_dir() else child.stat().st_size,
                }
            )
        except OSError:
            continue  # racing deletes / permission holes: skip, don't fail
        if len(entries) >= _MAX_ENTRIES:
            break
    return {
        "ok": True,
        "path": str(p),
        "entries": entries,
        "truncated": len(entries) >= _MAX_ENTRIES,
    }


@capability(
    "fs.search",
    domain="fs",
    effect="read",
    auto=True,
    schema={
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Directory to search under (inside allowed roots)."},
            "pattern": {"type": "string", "description": "Filename glob, e.g. '*.md' or 'osa_*.py'."},
            "max_results": {"type": "integer", "default": _MAX_SEARCH_RESULTS},
        },
        "required": ["root", "pattern"],
    },
)
def search(root: str, pattern: str, max_results: int = _MAX_SEARCH_RESULTS) -> dict:
    """Find files by name glob under a directory inside the allowed roots."""
    if not (root or "").strip():
        return {"ok": False, "error": "root required"}
    if not (pattern or "").strip():
        return {"ok": False, "error": "pattern required"}
    p = _policy.resolve_path(root)
    if not p.is_dir():
        return {"ok": False, "error": f"not a directory: {root}"}
    results: list[str] = []
    truncated = False
    for hit in p.rglob(pattern):
        results.append(str(hit))
        if len(results) >= max_results:
            truncated = True
            break
    return {"ok": True, "root": str(p), "matches": results, "truncated": truncated}


@capability(
    "fs.write_file",
    domain="fs",
    effect="mutate",
    auto=False,  # gated — except inside scratch_root (policy auto-allows)
    schema={
        "type": "object",
        "properties": {
            "path": _PATH_PROP,
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
)
def write_file(path: str, content: str) -> dict:
    """Write a UTF-8 text file (auto inside scratch_root, else needs approval)."""
    if not (path or "").strip():
        return {"ok": False, "error": "path required"}
    p = _policy.resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(p), "bytes": len(content.encode("utf-8"))}


@capability(
    "fs.append",
    domain="fs",
    effect="mutate",
    auto=False,
    schema={
        "type": "object",
        "properties": {
            "path": _PATH_PROP,
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
)
def append(path: str, content: str) -> dict:
    """Append UTF-8 text to a file (auto inside scratch_root, else approval)."""
    if not (path or "").strip():
        return {"ok": False, "error": "path required"}
    p = _policy.resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(content)
    return {"ok": True, "path": str(p), "appended_bytes": len(content.encode("utf-8"))}


@capability(
    "fs.move",
    domain="fs",
    effect="irreversible",
    auto=False,
    schema={
        "type": "object",
        "properties": {
            "src": _PATH_PROP,
            "dst": {"type": "string", "description": "Destination path (must also be inside the allowed roots)."},
        },
        "required": ["src", "dst"],
    },
)
def move(src: str, dst: str) -> dict:
    """Move/rename a file or directory (both ends inside the allowed roots)."""
    if not (src or "").strip():
        return {"ok": False, "error": "src required"}
    if not (dst or "").strip():
        return {"ok": False, "error": "dst required"}
    s = _policy.resolve_path(src)
    # The guard checked src (first arg = payload); the destination is
    # enforced here with the same resolver so approval can't move data
    # outside the roots.
    d = _require_in_roots(dst, "fs.move destination")
    if not s.exists():
        return {"ok": False, "error": f"source does not exist: {src}"}
    if d.exists():
        return {"ok": False, "error": f"destination already exists: {dst}"}
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(s), str(d))
    return {"ok": True, "src": str(s), "dst": str(d)}


@capability(
    "fs.delete",
    domain="fs",
    effect="irreversible",
    auto=False,
    schema={
        "type": "object",
        "properties": {"path": _PATH_PROP},
        "required": ["path"],
    },
)
def delete(path: str) -> dict:
    """Delete a file or EMPTY directory (non-empty dirs are refused)."""
    if not (path or "").strip():
        return {"ok": False, "error": "path required"}
    p = _policy.resolve_path(path)
    if not p.exists():
        return {"ok": False, "error": f"does not exist: {path}"}
    if p.is_dir():
        if any(p.iterdir()):
            return {
                "ok": False,
                "error": f"refusing to delete non-empty directory: {path} "
                "(delete contents individually — recursive delete is rm -rf territory)",
            }
        p.rmdir()
        return {"ok": True, "deleted": str(p), "kind": "empty_dir"}
    p.unlink()
    return {"ok": True, "deleted": str(p), "kind": "file"}
