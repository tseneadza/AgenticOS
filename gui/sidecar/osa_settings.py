"""OSA settings store + brain pin (OSA brain switching, 2026-07-07).

The single source of truth for OSA's *model pin* — Tony saying "switch to
Sonnet" / "use your local brain" pins ALL conversational turns to one model,
overriding the automatic per-turn router in ``agents.osa_agent`` until he says
"back to auto". Three surfaces share this module: the ``switch_model`` chat
tool, ``GET/POST /api/osa/model``, and the rail's Brain picker.

Design:

* **Durable, cached.** The pin lives in the MySQL ``osa_settings`` key-value
  table (``gui.sidecar.models.OsaSetting``, key ``model_pin``) so it survives
  sidecar restarts. Reads go through an in-process cache — the DB row is read
  at most once, updated on write — so the per-turn ``get_model_pin()`` in the
  chat route never hits MySQL.
* **Degrades gracefully.** MySQL down ⇒ reads fall back to auto (``None``) and
  writes keep working in-memory for this process (logged, never raised) —
  matching the house rule that a dead database never breaks a route.
* **Validated at the door.** ``set_model_pin`` accepts only ``auto``/``None``
  or an id present in the curated registry (``core.llm.registry``); unknown ⇒
  ``UnknownBrainError`` listing the valid brains, known-but-unrunnable (no API
  key, Ollama off, model not pulled, too big for RAM) ⇒
  ``UnavailableBrainError`` carrying the reason from ``core.llm.list_models``
  — a dead brain is never pinned.
* **Fuzzy front door.** ``resolve_brain`` maps spoken names ("sonnet",
  "haiku", "local", "qwen", "auto") to registry ids for the ``switch_model``
  tool; ambiguous asks ("claude") come back as a question, not a guess.

Functions take an optional ``session`` (house pattern, mirrors
``launch_config``) so tests inject the ``agenticos_test`` session.
"""
from __future__ import annotations

import logging
import re
import threading

log = logging.getLogger(__name__)

#: The osa_settings row key holding the pin.
PIN_KEY = "model_pin"

#: Tokens (whole words in the user's ask) that mean "clear the pin".
_AUTO_TOKENS = frozenset({"auto", "automatic", "automatically"})

# In-process cache over the DB row: read once, updated on every write.
_lock = threading.Lock()
_pin_cache: dict = {"loaded": False, "value": None}


class UnknownBrainError(ValueError):
    """The pin target is neither 'auto' nor a registry model id."""


class UnavailableBrainError(RuntimeError):
    """The pin target exists but can't run right now (reason in the message)."""


def _session_scope(session):
    """Return (session, owns) — creating one from SessionLocal if needed."""
    from gui.sidecar.db import SessionLocal

    if session is not None:
        return session, False
    return SessionLocal(), True


def reset_pin_cache() -> None:
    """Drop the in-process pin cache so the next read hits the DB. Test helper."""
    with _lock:
        _pin_cache["loaded"] = False
        _pin_cache["value"] = None


def get_model_pin(session=None) -> str | None:
    """Return the pinned model id, or ``None`` when routing is automatic.

    The DB row is read once per process; afterwards the cached value is
    served (writes keep it fresh). If MySQL is unreachable the pin degrades
    to auto (``None``) — logged, never raised — so a dead database can't
    break a chat turn.
    """
    with _lock:
        if _pin_cache["loaded"]:
            return _pin_cache["value"]

    value: str | None = None
    try:
        s, owns = _session_scope(session)
        try:
            from gui.sidecar.models import OsaSetting

            row = s.get(OsaSetting, PIN_KEY)
            value = row.value if row is not None and row.value else None
        finally:
            if owns:
                s.close()
    except Exception as exc:  # noqa: BLE001 — DB down ⇒ auto, never raise
        log.warning("osa_settings: pin read failed — auto until MySQL is back: %s", exc)
        value = None

    with _lock:
        _pin_cache["loaded"] = True
        _pin_cache["value"] = value
    return value


def _persist_pin(value: str | None, session=None) -> None:
    """Write-through: update the cache, then best-effort upsert the DB row."""
    with _lock:
        _pin_cache["loaded"] = True
        _pin_cache["value"] = value
    try:
        s, owns = _session_scope(session)
        try:
            from gui.sidecar.models import OsaSetting

            row = s.get(OsaSetting, PIN_KEY)
            if row is None:
                s.add(OsaSetting(key=PIN_KEY, value=value))
            else:
                row.value = value
            s.commit()
        finally:
            if owns:
                s.close()
    except Exception as exc:  # noqa: BLE001 — in-memory pin still holds
        log.warning("osa_settings: pin write failed — in-memory only: %s", exc)


def _registry_ids() -> list[str]:
    """Ids of the curated registry models (settings.yaml > agent.models)."""
    from core import llm

    return [m.id for m in llm.registry()]


def _availability(model_id: str) -> tuple[bool, str | None]:
    """(available, reason) for one model, per ``core.llm.list_models``.

    Pinning a *local* brain gets the ensure-Ollama treatment (try to bring the
    service up first, mirroring the endpoint's behavior); cloud targets skip
    the spawn/wait so a cloud pin stays snappy.
    """
    from core import llm

    info = llm.get_model_info(model_id)
    ensure = bool(info is not None and info.is_local)
    rows = llm.list_models(ensure_ollama=ensure).get("models", [])
    row = next((r for r in rows if r.get("id") == model_id), None)
    if row is None:
        return False, "unknown_model"
    return bool(row.get("available")), row.get("reason")


def set_model_pin(value: str | None, session=None) -> str | None:
    """Pin OSA's brain to a registry model id, or clear it with None/'auto'.

    Returns the stored pin (``None`` for auto). The pin is validated before
    anything is written:

    Raises:
        UnknownBrainError: target isn't 'auto' or a registry model id
            (message lists the valid brains).
        UnavailableBrainError: target exists but can't run right now —
            message carries the ``list_models`` reason (no_api_key,
            ollama_off, not_installed, too_large).
    """
    target = (value or "").strip()
    if not target or target.lower() in _AUTO_TOKENS:
        _persist_pin(None, session)
        return None

    ids = _registry_ids()
    if target not in ids:
        raise UnknownBrainError(
            f"unknown model {target!r} — valid brains: auto, {', '.join(ids)}"
        )
    available, reason = _availability(target)
    if not available:
        raise UnavailableBrainError(
            f"{target} is not available right now ({reason or 'unavailable'})"
        )
    _persist_pin(target, session)
    return target


def resolve_brain(text: str) -> dict:
    """Fuzzily resolve a spoken brain name to a registry id (or 'auto').

    Accepts the way Tony actually talks — "sonnet", "haiku", "local", "qwen",
    "use your fast brain", "back to auto", or a full model id. Resolution
    order: auto tokens → exact id → workflow aliases from settings.yaml
    (``local``/``fast``; ``default`` is deliberately skipped — "my default
    brain" should not silently pin Sonnet) → substring match over id + label.

    Returns one of:
        {"status": "auto"}
        {"status": "ok", "model": "<id>"}
        {"status": "ambiguous", "matches": ["<id>", ...]}
        {"status": "unknown", "valid": ["<id>", ...]}
    """
    from core import llm

    reg = llm.registry()
    ids = [m.id for m in reg]
    term = (text or "").strip().lower()
    if not term:
        return {"status": "unknown", "valid": ids}

    tokens = [t for t in re.split(r"[^a-z0-9.:_-]+", term) if t]
    if any(t in _AUTO_TOKENS for t in tokens):
        return {"status": "auto"}

    # Exact id (the API/registry form — always unambiguous).
    for m in reg:
        if term == m.id.lower():
            return {"status": "ok", "model": m.id}

    # Workflow aliases (settings.yaml > models): "local" → qwen, "fast" →
    # haiku. "default" is skipped — it aliases Sonnet for workflow steps, but
    # spoken "default" means auto-routing, and that path is handled above.
    for t in tokens:
        if t == "default":
            continue
        resolved = llm.resolve(t)
        if resolved != t and resolved in ids:
            return {"status": "ok", "model": resolved}

    # Substring over id + label ("sonnet", "haiku", "qwen", "llama").
    # Tokens under 3 chars are noise ("to", "7b") — skip them.
    matches: list[str] = []
    for m in reg:
        hay = f"{m.id} {m.label}".lower()
        if any(t in hay for t in tokens if len(t) >= 3):
            matches.append(m.id)

    if len(matches) == 1:
        return {"status": "ok", "model": matches[0]}
    if len(matches) > 1:
        return {"status": "ambiguous", "matches": matches}
    return {"status": "unknown", "valid": ids}
