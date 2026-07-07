"""OSA proactive monitor (Phase 14e) — health transitions -> spoken messages.

The Phase 13e health poller computes ``"app:port up|down"`` transitions every
pass; this module turns them into OSA-voiced proactive messages, decides which
ones OSA should *announce* (speak/animate) versus record silently, and keeps a
small in-memory ring buffer the GUI polls via ``GET /api/osa/events``.

Policy (Tony's locked decisions, knobs in ``config/constitution.yaml`` under
``notifications:``, loaded by ``core.constitution.Constitution``):

* **Balanced level** — DOWN and UP (recovery) transitions are announced;
  anything else is recorded silently.
* **Quiet hours** (default 22:00-08:00 local), **activity-aware** — during
  quiet hours a message is downgraded to silent UNLESS Tony is active. Tony's
  a night owl: activity is probed best-effort via macOS HID idle time
  (``ioreg -c IOHIDSystem``; active if idle < ``activity_idle_minutes``); if
  that fails, fall back to "last /api/osa/chat turn within
  ``chat_activity_minutes``"; if both are unavailable, treat as ACTIVE
  (fail-open — better to announce than to swallow).
* **Rate limit** — at most one announced message per app per
  ``rate_limit_seconds`` (default 300); a flip-flapping app can't spam.
  Silenced duplicates are still recorded.

Scheduled briefing: ``compose_briefing()`` + ``post_briefing()`` produce a
short spoken-style daily status summary (``launch_config.list_all_health()`` +
the project-ledger count). It is scheduled INSIDE the sidecar as an asyncio
task (see ``app.py`` ``_start_osa_briefing``) at ``briefing_time`` (default
08:30) — deliberately an in-process timer matching the 13e health-poller
precedent, NOT a launchd plist via ``core/scheduler.py``: no install step, it
lives and dies with the sidecar, and quiet-hours policy still applies to it.

State is in-memory and process-local (same precedent as ``_PENDING_CONFIRM``
in ``routes/api_osa.py``) — no new DB tables. All clock-dependent functions
take an injectable ``now`` for tests.
"""
from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, time as dtime, timedelta, timezone

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Module state (in-memory, thread-safe — the health poller runs in a worker
# thread while routes read from the event loop).
# --------------------------------------------------------------------------- #
_MAX_MESSAGES = 50

_lock = threading.RLock()
_messages: deque[dict] = deque(maxlen=_MAX_MESSAGES)
_latest_id = 0                      # monotonic, survives ring-buffer eviction
_last_announced: dict[str, float] = {}  # app_id -> epoch seconds of last announce
_last_chat_ts: float | None = None      # epoch seconds of the last /api/osa/chat turn
_config_cache: dict | None = None


def reset_state() -> None:
    """Clear all in-memory proactive state (tests only)."""
    global _latest_id, _last_chat_ts, _config_cache
    with _lock:
        _messages.clear()
        _last_announced.clear()
        _latest_id = 0
        _last_chat_ts = None
        _config_cache = None


# --------------------------------------------------------------------------- #
# Config — the notifications block of the Constitution (defaults if absent).
# --------------------------------------------------------------------------- #
def notifications_config() -> dict:
    """Return the ``notifications:`` policy knobs (cached after first load).

    Loads via ``core.constitution.Constitution`` so the block lives with the
    rest of the governance config; falls back to the loader's defaults if the
    file is unreadable so policy checks never crash the poller.
    """
    global _config_cache
    with _lock:
        if _config_cache is not None:
            return _config_cache
    from core.constitution import DEFAULT_NOTIFICATIONS, Constitution

    try:
        cfg = Constitution.load().notifications
    except Exception:  # noqa: BLE001 — never let config I/O kill the poller
        cfg = dict(DEFAULT_NOTIFICATIONS)
    with _lock:
        _config_cache = cfg
    return cfg


# --------------------------------------------------------------------------- #
# Activity probe — is Tony at the machine?
# --------------------------------------------------------------------------- #
_HID_IDLE_RE = re.compile(r'"HIDIdleTime"\s*=\s*(\d+)')


def hid_idle_seconds() -> float | None:
    """Best-effort macOS HID idle time in seconds via ``ioreg -c IOHIDSystem``.

    Returns None when the probe is unavailable (non-macOS, sandbox, parse
    failure) so callers can fall back to the chat-recency signal.
    """
    try:
        out = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        m = _HID_IDLE_RE.search(out or "")
        if m:
            return int(m.group(1)) / 1e9  # HIDIdleTime is in nanoseconds
    except Exception:  # noqa: BLE001 — probe is strictly best-effort
        pass
    return None


def note_chat_turn(*, now: datetime | None = None) -> None:
    """Record that a /api/osa/chat turn just happened (activity fallback)."""
    global _last_chat_ts
    with _lock:
        _last_chat_ts = (now.timestamp() if now is not None else time.time())


def is_tony_active(*, now: datetime | None = None, cfg: dict | None = None) -> bool:
    """Whether Tony appears to be at the machine (quiet-hours override).

    Order: HID idle probe (active if idle < ``activity_idle_minutes``) ->
    last-chat recency (active if within ``chat_activity_minutes``) ->
    fail-open True when neither signal is available.
    """
    cfg = cfg or notifications_config()
    idle = hid_idle_seconds()
    if idle is not None:
        return idle < float(cfg.get("activity_idle_minutes", 10)) * 60
    with _lock:
        last_chat = _last_chat_ts
    if last_chat is not None:
        ref = now.timestamp() if now is not None else time.time()
        return (ref - last_chat) < float(cfg.get("chat_activity_minutes", 30)) * 60
    return True  # fail-open: better to announce than to swallow


# --------------------------------------------------------------------------- #
# Policy engine — pure functions with an injectable clock.
# --------------------------------------------------------------------------- #
def _parse_hhmm(value: str) -> dtime:
    """Parse an 'HH:MM' knob into a time (invalid values -> midnight)."""
    try:
        h, m = str(value).split(":", 1)
        return dtime(int(h), int(m))
    except Exception:  # noqa: BLE001
        return dtime(0, 0)


def in_quiet_hours(now: datetime | None = None, cfg: dict | None = None) -> bool:
    """Whether local time ``now`` falls inside the configured quiet hours.

    Handles the overnight wrap (start > end, e.g. 22:00-08:00): quiet when
    t >= start OR t < end. The end boundary itself is outside quiet hours.
    """
    cfg = cfg or notifications_config()
    now = now or datetime.now()
    start = _parse_hhmm(cfg.get("quiet_hours_start", "22:00"))
    end = _parse_hhmm(cfg.get("quiet_hours_end", "08:00"))
    t = now.time()
    if start <= end:
        return start <= t < end
    return t >= start or t < end


def should_announce(
    app_id: str,
    kind: str,
    *,
    now: datetime | None = None,
    cfg: dict | None = None,
    active: bool | None = None,
) -> bool:
    """Decide whether a message is announced (spoken) or recorded silently.

    Balanced level: only "down", "up" and "briefing" are announce candidates.
    Quiet hours downgrade to silent unless Tony is active (``active`` overrides
    the live probe — used by tests). The per-app rate limit is checked last and
    is only consumed by ``mark_announced`` when the caller actually announces.
    """
    cfg = cfg or notifications_config()
    now = now or datetime.now()
    if kind not in ("down", "up", "briefing"):
        return False  # balanced level: anything else is silent
    if in_quiet_hours(now, cfg):
        if not (active if active is not None else is_tony_active(now=now, cfg=cfg)):
            return False
    limit = float(cfg.get("rate_limit_seconds", 300))
    with _lock:
        last = _last_announced.get(app_id)
    if last is not None and (now.timestamp() - last) < limit:
        return False
    return True


def mark_announced(app_id: str, *, now: datetime | None = None) -> None:
    """Consume the per-app rate limit for an announced message."""
    now = now or datetime.now()
    with _lock:
        _last_announced[app_id] = now.timestamp()


def seconds_until(hhmm: str, now: datetime | None = None) -> float:
    """Seconds from ``now`` until the next local occurrence of 'HH:MM'."""
    now = now or datetime.now()
    t = _parse_hhmm(hhmm)
    target = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


# --------------------------------------------------------------------------- #
# Transitions -> messages
# --------------------------------------------------------------------------- #
_TRANSITION_RE = re.compile(r"^(?P<app>.+):(?P<port>\d+)\s+(?P<dir>up|down)$")


def parse_transition(entry: str) -> tuple[str, int, str] | None:
    """Parse a 13e ``"app:port up|down"`` entry -> (app_id, port, kind).

    Returns None for anything that doesn't match, so a malformed entry is
    skipped rather than crashing the poller loop.
    """
    m = _TRANSITION_RE.match((entry or "").strip())
    if not m:
        return None
    return m.group("app"), int(m.group("port")), m.group("dir")


def phrase_transition(app_id: str, port: int, kind: str) -> str:
    """Phrase a transition in OSA's spoken voice (short, no markdown)."""
    if kind == "down":
        return f"Tony — {app_id} just went down (port {port})."
    return f"{app_id} is back up."


def _append(app_id: str, kind: str, text: str, announced: bool,
            *, now: datetime | None = None) -> dict:
    """Append one message to the ring buffer and return it."""
    global _latest_id
    if now is not None:
        ts = (now if now.tzinfo else now.astimezone()).astimezone(timezone.utc)
    else:
        ts = datetime.now(timezone.utc)
    with _lock:
        _latest_id += 1
        msg = {
            "id": _latest_id,
            "ts": ts.isoformat(),
            "app_id": app_id,
            "kind": kind,
            "text": text,
            "announced": announced,
        }
        _messages.append(msg)
    return msg


def record_transitions(transitions: list[str], *, now: datetime | None = None) -> list[dict]:
    """Turn health-poller transitions into buffered OSA messages (poller hook).

    Called from the 13e health-poller loop in ``app.py``. Each parseable entry
    becomes a ring-buffer message; the policy engine decides ``announced``.
    Malformed entries are skipped. Never raises.
    """
    results: list[dict] = []
    for entry in transitions or []:
        try:
            parsed = parse_transition(entry)
            if parsed is None:
                continue
            app_id, port, kind = parsed
            text = phrase_transition(app_id, port, kind)
            announced = should_announce(app_id, kind, now=now)
            if announced:
                mark_announced(app_id, now=now)
            results.append(_append(app_id, kind, text, announced, now=now))
        except Exception:  # noqa: BLE001 — one bad entry never kills the loop
            logger.debug("proactive: skipped transition %r", entry, exc_info=True)
    return results


# --------------------------------------------------------------------------- #
# Ring-buffer reads (back GET /api/osa/events)
# --------------------------------------------------------------------------- #
def latest_id() -> int:
    """The id of the newest message ever recorded (0 when none)."""
    with _lock:
        return _latest_id


def get_messages(after: int | None = None) -> dict:
    """Messages newer than the ``after`` cursor (all buffered when omitted)."""
    with _lock:
        msgs = [m for m in _messages if after is None or m["id"] > after]
        return {"messages": msgs, "latest_id": _latest_id}


# --------------------------------------------------------------------------- #
# Scheduled briefing
# --------------------------------------------------------------------------- #
def _project_count() -> int | None:
    """Project-ledger row count (same source as list_projects); None if down."""
    try:
        from gui.sidecar.db import SessionLocal
        from gui.sidecar.models import Project
        session = SessionLocal()
    except Exception:  # noqa: BLE001 — degrade like the list_projects tool
        return None
    try:
        return session.query(Project).count()
    except Exception:  # noqa: BLE001
        return None
    finally:
        session.close()


def compose_briefing() -> str:
    """Short spoken-style status summary (1-3 sentences, no markdown).

    Built from ``launch_config.list_all_health()`` + the project-ledger count.
    Both sources degrade gracefully — a briefing is always composable.
    """
    try:
        from gui.sidecar import launch_config
        health = launch_config.list_all_health()
    except Exception:  # noqa: BLE001
        health = {"apps": {}, "total": 0}
    apps = health.get("apps", {}) or {}
    total = health.get("total", len(apps))
    unhealthy = sorted(a for a, v in apps.items() if not v.get("healthy"))

    if total == 0:
        first = "Morning, Tony. Nothing's under health watch right now."
    elif not unhealthy:
        noun = "app is" if total == 1 else f"{total} tracked apps are"
        first = f"Morning, Tony. {'The one tracked ' + noun if total == 1 else 'All ' + noun} healthy."
    else:
        names = ", ".join(unhealthy)
        verb = "is" if len(unhealthy) == 1 else "are"
        first = f"Morning, Tony. {names} {verb} down; the other {total - len(unhealthy)} of {total} look fine."

    count = _project_count()
    if count is None:
        return first
    plural = "project" if count == 1 else "projects"
    return f"{first} The ledger holds {count} {plural}."


def post_briefing(*, force_announce: bool = False, now: datetime | None = None) -> dict:
    """Compose + record the daily briefing (kind="briefing").

    Announced by default; the quiet-hours/activity check still applies, so an
    early briefing while Tony's asleep lands silently in the buffer instead.

    ``force_announce=True`` bypasses that check — used by the on-demand
    ``POST /api/osa/briefing`` route: an explicit ask is its own proof of
    activity, so quiet hours never silence it. Forced announcements still
    stamp the rate-limit window (an on-demand brief defers the next
    scheduled one's announce window like any other).
    """
    text = compose_briefing()
    announced = force_announce or should_announce("osa-briefing", "briefing", now=now)
    if announced:
        mark_announced("osa-briefing", now=now)
    return _append("osa", "briefing", text, announced, now=now)
