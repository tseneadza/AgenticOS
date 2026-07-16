"""
Phase 16a — Brain Scanner vault API (read-only slice).

Serves the Brain2 Obsidian vault to the Brain Scanner view:
- GET /api/vault/tree   — folder/file tree (dirs + .md notes only)
- GET /api/vault/note   — raw markdown of one note (+ mtime, size)
- GET /api/vault/graph  — nodes (notes + tags) and edges (wikilinks, note→tag)

Design: docs/PHASE16_BRAIN_SCANNER.md §5. Write endpoints (PUT/POST) are
Phase 16d — deliberately absent here.

Security posture:
- Every caller-supplied path is symlink-resolved and must stay under the
  vault root (Phase 15b resolve_path/under_any_root pattern). ``..`` and
  symlink escapes resolve outside the root and are rejected.
- The vault root is CONFIG, not caller input: default is the ~/Brain2 entry
  of ``system_mcp.fs.allowed_roots`` (constitution.yaml), overridable only
  via the test seam ``set_vault_root()``.
"""

import re
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from tools.system._policy import resolve_path, under_any_root

logger = logging.getLogger(__name__)

router = APIRouter()

DEFAULT_VAULT_ROOT = "~/Brain2"

# Test seam: None → resolve the default lazily on first use. Tests inject a
# tmp_path vault via set_vault_root() so pytest never touches the real Brain2.
_vault_root_override: Path | None = None


def set_vault_root(path: str | Path | None) -> None:
    """Inject the vault root (tests) or reset to the config default (None)."""
    global _vault_root_override
    _vault_root_override = resolve_path(str(path)) if path is not None else None
    _invalidate_graph_cache()


def _config_vault_root() -> Path:
    """The ~/Brain2 entry of system_mcp.fs.allowed_roots, else ~/Brain2."""
    try:
        from core.constitution import Constitution

        roots = Constitution.load().system_mcp.get("fs", {}).get("allowed_roots", [])
        for root in roots:
            if "Brain2" in str(root):
                return resolve_path(str(root))
    except Exception:  # config unreadable → fall through to the default
        pass
    return resolve_path(DEFAULT_VAULT_ROOT)


def vault_root() -> Path:
    return _vault_root_override if _vault_root_override is not None else _config_vault_root()


def _require_vault() -> Path:
    """The vault root, or 503 when it's missing/empty (design §5: 16a, not polish).
    Emptiness uses the same visibility rules as tree/graph (_iter_notes) — a
    vault whose only notes hide in .obsidian/.trash is empty, not half-alive."""
    root = vault_root()
    if not root.is_dir() or not _iter_notes(root):
        raise HTTPException(status_code=503, detail=f"Vault missing or empty: {root}")
    return root


def _is_hidden(part: str) -> bool:
    return part.startswith(".")


def _iter_notes(root: Path) -> list[Path]:
    """All .md notes under root, excluding .obsidian/ and any dot-directories.
    Symlinks that resolve outside the vault are skipped — tree and graph obey
    the same scope as /note, so outside content is never listed OR parsed."""
    notes = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root)
        if any(_is_hidden(part) for part in rel.parts):
            continue
        if not under_any_root(str(p), [str(root)]):
            continue
        notes.append(p)
    return notes


def _scope_note_path(raw: str, root: Path) -> Path:
    """Resolve a caller path against the vault root and enforce the scope."""
    if not raw or not raw.strip():
        raise HTTPException(status_code=400, detail="Missing note path")
    candidate = Path(raw)
    p = resolve_path(str(candidate if candidate.is_absolute() else root / candidate))
    if not under_any_root(str(p), [str(root)]):
        raise HTTPException(status_code=400, detail="Path escapes the vault root")
    if p.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="Only .md notes are served")
    return p


# ── tree ────────────────────────────────────────────────────────────────────

def _build_tree(dir_path: Path, root: Path) -> list[dict]:
    entries = []
    for child in sorted(dir_path.iterdir(), key=lambda c: (c.is_file(), c.name.lower())):
        if _is_hidden(child.name):
            continue
        # same scope as /note: a symlink resolving outside the vault is invisible
        if not under_any_root(str(child), [str(root)]):
            continue
        rel = str(child.relative_to(root))
        if child.is_dir():
            entries.append({
                "name": child.name,
                "path": rel,
                "type": "dir",
                "children": _build_tree(child, root),
            })
        elif child.suffix.lower() == ".md":
            entries.append({"name": child.name, "path": rel, "type": "file"})
    return entries


@router.get("/api/vault/tree")
async def get_tree():
    """Folder/file tree of the vault (dirs + .md notes; dotfiles excluded)."""
    root = _require_vault()
    return {"root": str(root), "tree": _build_tree(root, root)}


# ── note ────────────────────────────────────────────────────────────────────

@router.get("/api/vault/note")
async def get_note(path: str = Query(...)):
    """Raw markdown of one note + metadata (mtime drives the 16d 409 check)."""
    root = _require_vault()
    p = _scope_note_path(path, root)
    if not p.is_file():
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")
    stat = p.stat()
    return {
        "path": str(p.relative_to(root)),
        "content": p.read_text(errors="replace"),
        "mtime": stat.st_mtime,
        "size": stat.st_size,
    }


# ── graph ───────────────────────────────────────────────────────────────────

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
# Leading letter required — rejects numeric issue refs (#42). Hex colors that
# happen to start with a letter (#fff, #d97b4f) pass the regex, so a post-
# filter drops pure-hex candidates at CSS-color lengths (3/4/6/8).
TAG_RE = re.compile(r"(?:^|\s)#([A-Za-z][\w/-]*)")
HEX_COLOR_RE = re.compile(r"^[0-9a-fA-F]{3}$|^[0-9a-fA-F]{4}$|^[0-9a-fA-F]{6}$|^[0-9a-fA-F]{8}$")
FENCE_RE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)

# In-memory graph cache, keyed on a fast vault scan (no DB — design §5).
_graph_cache: dict | None = None
_graph_cache_key: tuple | None = None


def _invalidate_graph_cache() -> None:
    global _graph_cache, _graph_cache_key
    _graph_cache = None
    _graph_cache_key = None


def _vault_scan_key(notes: list[Path]) -> tuple:
    """Cheap change detector: file count + max mtime. Catches writes from ANY
    writer (real Obsidian, process-raw-notes, fs_mcp) — not just our own."""
    max_mtime = 0.0
    for p in notes:
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if m > max_mtime:
            max_mtime = m
    return (len(notes), max_mtime)


def _frontmatter_tags(fm_text: str) -> list[str]:
    """Parse ``tags:`` out of YAML frontmatter (list or comma/space string)."""
    try:
        import yaml

        data = yaml.safe_load(fm_text) or {}
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    raw = data.get("tags")
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = re.split(r"[,\s]+", raw)
    if not isinstance(raw, list):
        return []
    tags = []
    for t in raw:
        t = str(t).strip().lstrip("#")
        if t and re.match(r"[A-Za-z]", t):
            tags.append(t)
    return tags


def _parse_note(p: Path) -> tuple[list[str], list[str]]:
    """(wikilink targets, tags) — code fences/inline code stripped first,
    frontmatter stripped from the body and parsed separately for tags."""
    try:
        text = p.read_text(errors="replace")
    except OSError:
        return [], []
    tags: list[str] = []
    fm = FRONTMATTER_RE.match(text)
    if fm:
        tags.extend(_frontmatter_tags(fm.group(1)))
        text = text[fm.end():]
    text = FENCE_RE.sub("", text)
    text = INLINE_CODE_RE.sub("", text)
    links = [m.strip() for m in WIKILINK_RE.findall(text) if m.strip()]
    for tag in TAG_RE.findall(text):
        # body-only filter: frontmatter tags are explicit metadata, but a body
        # "#d97b4f" is far more likely a color than a tag
        if HEX_COLOR_RE.match(tag):
            continue
        if tag not in tags:
            tags.append(tag)
    return links, tags


def _resolve_link(target: str, by_relpath: dict, by_stem: dict) -> str | None:
    """Resolve a wikilink target to a note id (relative path). Obsidian rule:
    basename match, shortest path wins. Unresolved → None (dropped, v1)."""
    t = target.strip().removesuffix(".md")
    if "/" in t:
        hit = by_relpath.get(t.lower())
        if hit:
            return hit
        t = t.rsplit("/", 1)[-1]  # fall back to basename
    candidates = by_stem.get(t.lower())
    if not candidates:
        return None
    return min(candidates, key=lambda rel: (len(rel), rel))


def _build_graph(root: Path, notes: list[Path]) -> dict:
    nodes = []
    edges = []
    by_stem: dict[str, list[str]] = {}
    by_relpath: dict[str, str] = {}

    rels = [str(p.relative_to(root)) for p in notes]
    for rel in rels:
        stem = Path(rel).stem
        folder = rel.split("/", 1)[0] if "/" in rel else ""
        nodes.append({"id": rel, "label": stem, "folder": folder, "type": "note"})
        by_stem.setdefault(stem.lower(), []).append(rel)
        by_relpath[rel.removesuffix(".md").lower()] = rel

    tag_nodes: set[str] = set()
    seen_edges: set[tuple[str, str]] = set()
    for p, rel in zip(notes, rels):
        links, tags = _parse_note(p)
        for target in links:
            resolved = _resolve_link(target, by_relpath, by_stem)
            if resolved is None or resolved == rel:
                continue
            key = (rel, resolved)
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append({"source": rel, "target": resolved, "kind": "link"})
        # Tags are their own nodes with note→tag edges — NEVER pairwise
        # note-to-note cliques (design §5: one 200-note tag ≈ 20k edges).
        for tag in tags:
            tag_id = f"#{tag}"
            if tag_id not in tag_nodes:
                tag_nodes.add(tag_id)
                nodes.append({"id": tag_id, "label": tag_id, "folder": "#tags", "type": "tag"})
            key = (rel, tag_id)
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append({"source": rel, "target": tag_id, "kind": "tag"})

    return {"nodes": nodes, "edges": edges}


@router.get("/api/vault/graph")
async def get_graph(refresh: int = Query(0)):
    """Vault graph: note + tag nodes, wikilink + tag edges. Cached on a fast
    (count, max-mtime) scan; ``?refresh=1`` forces a rebuild."""
    global _graph_cache, _graph_cache_key
    root = _require_vault()
    notes = _iter_notes(root)
    key = _vault_scan_key(notes)
    if not refresh and _graph_cache is not None and _graph_cache_key == key:
        return _graph_cache
    graph = _build_graph(root, notes)
    _graph_cache = graph
    _graph_cache_key = key
    return graph
