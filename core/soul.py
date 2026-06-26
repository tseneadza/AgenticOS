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


def soul_path() -> Path:
    """Return the resolved path to the Soul identity file."""
    return _resolve(_SOUL_NAMES)


def memory_path() -> Path:
    """Return the resolved path to the Memory file."""
    return _resolve(_MEMORY_NAMES)


def _read(path: Path) -> str:
    """Read and strip a file's text content, returning empty string on error."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def load_soul() -> str:
    """Load and return the Soul identity text from config/Soul.md."""
    return _read(soul_path())


def load_memory() -> str:
    """Load and return the Memory text from config/Memory.md."""
    return _read(memory_path())


def identity_preamble() -> str:
    """Compose the Soul + Memory block to prepend to an agent's system prompt.

    Returns "" when neither file has content, so callers can inject
    unconditionally without emitting an empty header.
    """
    soul = load_soul()
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
