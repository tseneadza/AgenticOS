"""Persistent agent identity (Soul) + durable memory (Memory).

Two human-editable Markdown files in ``config/`` keep the agent's identity and
accumulated memory intact across sessions AND across models (local/cloud):

* ``config/Soul.md``   — who the agent is: name, voice, relationship, persona.
* ``config/Memory.md`` — what the agent remembers: durable facts, context, prefs.

They're loaded fresh on every turn and injected into each LLM-facing agent's
system prompt (governor chat + briefing composer), so identity and memory are
model-agnostic and survive restarts. ``remember()`` appends new memories — per
the OS's memory policy this is an automatic, append-only write (no approval),
scoped to ``Memory.md`` so its blast radius is bounded.

Markdown is preferred; ``.yaml`` files of the same name are still read as a
fallback so older configs keep working.
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

_CONFIG = Path(__file__).resolve().parent.parent / "config"
_SOUL_NAMES = ("Soul.md", "Soul.yaml")
_MEMORY_NAMES = ("Memory.md", "Memory.yaml")
_lock = threading.Lock()


def _resolve(names: tuple[str, ...]) -> Path:
    """Return the first existing file from candidates, or the preferred (.md) path."""
    for name in names:
        p = _CONFIG / name
        if p.exists():
            return p
    return _CONFIG / names[0]


def _soul_names(soul_name: str | None) -> tuple[str, ...]:
    """Resolve which soul-file candidates to load.

    ``None`` (the default) keeps the historical behaviour — the shared
    ``Soul.md`` (with a ``.yaml`` fallback). A concrete name like
    ``"Soul_OSA.md"`` selects a forked persona file, so the governing/briefing
    agents can keep the plain shared identity while OSA loads its sharper one.
    """
    if not soul_name:
        return _SOUL_NAMES
    stem = Path(soul_name).name  # strip any path components (defensive)
    if stem.endswith(".md"):
        base = stem[: -len(".md")]
        return (stem, f"{base}.yaml")
    return (stem,)


def soul_path(soul_name: str | None = None) -> Path:
    """Return the resolved path to the Soul identity file.

    Pass ``soul_name`` (e.g. ``"Soul_OSA.md"``) to select a forked persona;
    omit it to resolve the shared ``Soul.md``.
    """
    return _resolve(_soul_names(soul_name))


def memory_path() -> Path:
    """Return the resolved path to the Memory file."""
    return _resolve(_MEMORY_NAMES)


def _read(path: Path) -> str:
    """Read and strip a file's text content, returning empty string on error."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def load_soul(soul_name: str | None = None) -> str:
    """Load and return the Soul identity text.

    Defaults to ``config/Soul.md``; pass ``soul_name`` to load a forked persona
    file (e.g. ``"Soul_OSA.md"``).
    """
    return _read(soul_path(soul_name))


def load_memory() -> str:
    """Load and return the Memory text from config/Memory.md."""
    return _read(memory_path())


def identity_preamble(soul_name: str | None = None) -> str:
    """Compose the Soul + Memory block to prepend to an agent's system prompt.

    Returns "" when neither file has content, so callers can inject
    unconditionally without emitting an empty header. ``soul_name`` selects a
    forked persona file (e.g. ``"Soul_OSA.md"``); omit it for the shared
    ``Soul.md`` — so existing callers (governor, briefing) are unaffected.
    Memory (``Memory.md``) is always shared across every agent.
    """
    soul = load_soul(soul_name)
    memory = load_memory()
    if not soul and not memory:
        return ""
    parts = [
        "# Your identity and memory",
        "The following defines who you are and what you remember. It persists "
        "across sessions and across models (local and cloud). Stay in character "
        "and honor it. When you learn a durable fact, preference, or piece of "
        "context worth keeping, call the `remember` tool to save it.",
    ]
    if soul:
        parts.append("## Soul (identity)\n" + soul)
    if memory:
        parts.append("## Memory (what you remember)\n" + memory)
    return "\n\n".join(parts)


_MEMORY_SCAFFOLD = (
    "# Memory\n\n"
    "Durable facts and context the agent remembers across sessions and models.\n\n"
    "## Log\n"
)


def remember(note: str, *, source: str = "agent") -> str:
    """Append a timestamped memory to ``Memory.md``.

    Append-only and bounded to the memory file. Returns a short confirmation
    (or an ``ERROR:`` string the caller/LLM can surface).
    """
    note = (note or "").strip()
    if not note:
        return "ERROR: empty memory, nothing saved."

    path = memory_path()
    if path.suffix != ".md":  # migrate writes to Markdown going forward
        path = _CONFIG / "Memory.md"

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"- {stamp} ({source}): {note}\n"
    with _lock:
        try:
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
            if not existing.strip():
                existing = _MEMORY_SCAFFOLD
            if not existing.endswith("\n"):
                existing += "\n"
            path.write_text(existing + line, encoding="utf-8")
        except Exception as exc:  # pragma: no cover - filesystem dependent
            return f"ERROR saving memory: {exc}"
    return f"Saved to memory: {note}"
