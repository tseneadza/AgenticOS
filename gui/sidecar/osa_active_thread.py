"""Shared active OSA conversation thread_id (thread-safe).

Bridges the on-screen OSA chat UI and the voice pipeline so SPOKEN turns
write into the SAME thread the user is viewing on screen — one unified
conversation instead of a separate ``osa-voice-…`` thread.

The chat UI POSTs its current thread_id to ``/api/osa/active-thread``; the
voice pipeline reads it (lazily, best-effort) in ``_chat_turn`` and prefers
it over its own sticky ``_voice_thread`` when set.

Deliberately tiny + dependency-free so both the FastAPI routes and the voice
worker threads can touch it without import-layering or event-loop concerns.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_active_thread_id: str | None = None


def set_active_thread(tid: str | None) -> None:
    """Record the UI's current OSA thread_id (empty/None clears it)."""
    global _active_thread_id
    cleaned = (tid or "").strip() or None
    with _lock:
        _active_thread_id = cleaned


def get_active_thread() -> str | None:
    """Return the current active OSA thread_id, or None when unset."""
    with _lock:
        return _active_thread_id
