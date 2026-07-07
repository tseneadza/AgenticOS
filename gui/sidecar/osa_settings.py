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
  or a *pinnable* id — the curated registry (``core.llm.registry``) UNION the
  installed Ollama models (``core.llm.discover_ollama``, 2026-07-07); unknown
  ⇒ ``UnknownBrainError`` listing the valid brains, known-but-unrunnable (no
  API key, Ollama off, model not pulled) ⇒ ``UnavailableBrainError`` carrying
  the reason from ``core.llm.list_models`` — a dead brain is never pinned.
  Exception (Tony's call): an installed model that may exceed free RAM is a
  WARNING, not a block — ``_availability`` maps ``too_large`` to pinnable with
  reason ``may_not_fit_ram`` so ``switch_model`` can warn in persona.
* **Fuzzy front door.** ``resolve_brain`` maps spoken names ("sonnet",
  "haiku", "local", "qwen", "llama", "mistral", "auto") to pinnable ids —
  curated AND discovered — for the ``switch_model`` tool; when several match,
  installed models win over not-installed curated entries; still-ambiguous
  asks ("claude") come back as a question, not a guess.

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


def _discovered_infos() -> list:
    """Installed-Ollama ``ModelInfo``s (discovery seam — tests patch this).

    Best-effort over ``core.llm.discover_ollama`` (TTL-cached /api/tags; keeps
    the last known set while Ollama is down, empty on a cold cache). Any
    failure degrades to ``[]`` — curated-only, exactly the pre-discovery
    behavior.
    """
    try:
        from core import llm

        return list(llm.discover_ollama().values())
    except Exception:  # noqa: BLE001 — Ollama trouble never breaks pinning
        return []


def is_discovered(model_id: str) -> bool:
    """Whether ``model_id`` is an installed Ollama model outside the registry."""
    reg = set(_registry_ids())
    return any(i.id == model_id for i in _discovered_infos() if i.id not in reg)


def _pinnable_ids() -> list[str]:
    """Every id Tony may pin: curated registry ∪ installed Ollama models."""
    ids = _registry_ids()
    seen = set(ids)
    for info in _discovered_infos():
        if info.id not in seen:
            ids.append(info.id)
            seen.add(info.id)
    return ids


def _availability(model_id: str) -> tuple[bool, str | None]:
    """(available, reason) for one model, per ``core.llm.list_models``.

    Pinning a *local* brain gets the ensure-Ollama treatment (try to bring the
    service up first, mirroring the endpoint's behavior); cloud targets skip
    the spawn/wait so a cloud pin stays snappy.
    """
    from core import llm

    info = llm.get_model_info(model_id)
    ensure = (
        bool(info.is_local) if info is not None
        else llm.looks_like_ollama_id(model_id)  # discovered id, cold cache
    )
    rows = llm.list_models(ensure_ollama=ensure).get("models", [])
    row = next((r for r in rows if r.get("id") == model_id), None)
    if row is None:
        return False, "unknown_model"
    available, reason = bool(row.get("available")), row.get("reason")
    # RAM note, not a block (2026-07-07): an INSTALLED local model that may
    # not fit free RAM stays pinnable — the caller warns instead of refusing.
    if not available and reason == "too_large" and row.get("installed"):
        return True, "may_not_fit_ram"
    return available, reason


# Cloud escape hatch (Tony, 2026-07-07): any explicit Anthropic model id is
# pinnable when the API key works, even if it isn't in the curated registry —
# "switch to claude-opus-4-8" must Just Work. Validation is the id shape +
# a live key; a nonexistent id then errors at call time on the next turn
# (switch_model warns about that in persona).
_CLOUD_ID_RE = re.compile(r"^claude-[a-z0-9][a-z0-9.-]*$")


def is_uncurated_cloud(model_id: str) -> bool:
    """Whether ``model_id`` is a claude-* id outside the curated registry."""
    return bool(_CLOUD_ID_RE.match(model_id or "")) and model_id not in _registry_ids()


def _anthropic_key_ok() -> bool:
    """Best-effort: is the Anthropic key usable? (any curated cloud row avail).

    Reuses ``list_models`` availability on the curated anthropic rows rather
    than sniffing env vars directly — one source of truth for key health.
    """
    try:
        from core import llm

        rows = llm.list_models(ensure_ollama=False).get("models", [])
        return any(
            r.get("available") for r in rows
            if not r.get("is_local")
        )
    except Exception:  # noqa: BLE001 — can't verify ⇒ don't pin a dead brain
        return False


def set_model_pin(value: str | None, session=None) -> str | None:
    """Pin OSA's brain to a pinnable model id, or clear it with None/'auto'.

    Returns the stored pin (``None`` for auto). The pin is validated before
    anything is written:

    Raises:
        UnknownBrainError: target isn't 'auto', a pinnable id, or a claude-*
            cloud id (message lists the valid brains).
        UnavailableBrainError: target exists but can't run right now —
            message carries the ``list_models`` reason (no_api_key,
            ollama_off, not_installed, too_large).
    """
    target = (value or "").strip()
    if not target or target.lower() in _AUTO_TOKENS:
        _persist_pin(None, session)
        return None

    ids = _pinnable_ids()
    if target not in ids:
        # Cloud escape hatch: explicit claude-* ids pin when the key is live.
        if is_uncurated_cloud(target):
            if not _anthropic_key_ok():
                raise UnavailableBrainError(
                    f"{target} is not available right now (no_api_key)"
                )
            _persist_pin(target, session)
            return target
        raise UnknownBrainError(
            f"unknown model {target!r} — valid brains: auto, {', '.join(ids)}, "
            "or any full claude-* model id"
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
    "llama", "mistral", "use your fast brain", "back to auto", or a full model
    id. Candidates are the PINNABLE set: curated registry ∪ installed Ollama
    models (2026-07-07). Resolution order: auto tokens → exact id → workflow
    aliases from settings.yaml (``local``/``fast``; ``default`` is
    deliberately skipped — "my default brain" should not silently pin Sonnet)
    → substring match over id + label. A multi-way substring tie narrows to
    models that can actually run (cloud, or installed locally) — so "llama"
    lands on the installed llama3.2 rather than an unpulled curated llama.

    Returns one of:
        {"status": "auto"}
        {"status": "ok", "model": "<id>"}
        {"status": "ambiguous", "matches": ["<id>", ...]}
        {"status": "unknown", "valid": ["<id>", ...]}
    """
    from core import llm

    reg = llm.registry()
    discovered = {i.id: i for i in _discovered_infos()}
    candidates = list(reg) + [
        i for i in discovered.values() if i.id not in {m.id for m in reg}
    ]
    ids = [m.id for m in candidates]
    term = (text or "").strip().lower()
    if not term:
        return {"status": "unknown", "valid": ids}

    tokens = [t for t in re.split(r"[^a-z0-9.:_-]+", term) if t]
    if any(t in _AUTO_TOKENS for t in tokens):
        return {"status": "auto"}

    # Exact id (the API/registry/Ollama form — always unambiguous).
    for m in candidates:
        if term == m.id.lower():
            return {"status": "ok", "model": m.id}

    # Cloud escape hatch (2026-07-07): an explicit claude-* id resolves even
    # when uncurated — "switch to claude-opus-4-8" Just Works; set_model_pin
    # verifies the key. Family names alone ("opus") stay unresolved — we
    # never guess a full id Anthropic might not have.
    if _CLOUD_ID_RE.match(term):
        return {"status": "ok", "model": term}

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
    for m in candidates:
        hay = f"{m.id} {m.label}".lower()
        if any(t in hay for t in tokens if len(t) >= 3):
            matches.append(m.id)

    if len(matches) > 1:
        # Narrow a tie to runnable models: cloud entries, or locals that are
        # actually installed. "llama" → the installed llama3.2:latest, not the
        # curated-but-unpulled llama3.1:8b. If nothing survives, keep the
        # original tie — better an honest question than an empty shrug.
        by_id = {m.id: m for m in candidates}
        narrowed = [
            mid for mid in matches
            if not by_id[mid].is_local or mid in discovered
        ]
        if narrowed:
            matches = narrowed

    if len(matches) == 1:
        return {"status": "ok", "model": matches[0]}
    if len(matches) > 1:
        return {"status": "ambiguous", "matches": matches}
    return {"status": "unknown", "valid": ids}
