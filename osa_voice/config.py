"""Voice config — the ``voice:`` block of the Constitution (Phase 14d).

Mirrors the 14e ``notifications:`` pattern exactly
(``gui/sidecar/osa_proactive.notifications_config``): the knobs live in
``config/constitution.yaml`` under ``constitution.voice``, are loaded through
``core.constitution.Constitution`` (which merges ``DEFAULT_VOICE`` under any
values present, so pre-14d YAMLs keep loading unchanged), and are cached after
first read. A config-read failure falls back to pure defaults — the voice
service must never crash the sidecar over YAML trouble.

Knobs (see ``core.constitution.DEFAULT_VOICE`` for the authoritative defaults):
    enabled            — HARD default False; opt-in on-device only.
    wake_word          — openWakeWord phrase ("osa").
    stt_model          — faster-whisper model size ("small").
    piper_voice        — Piper voice model; "" = TBD, Tony auditions later.
    push_to_talk_only  — True (design §9 Q3 unresolved — no always-listening
                         until Tony opts in).
    mute               — global output mute.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_config_cache: dict | None = None


def voice_config() -> dict:
    """Return the ``voice:`` policy knobs (cached after first load).

    Loads via ``core.constitution.Constitution`` so the block lives with the
    rest of the governance config; falls back to the loader's defaults if the
    file is unreadable so voice checks never crash the sidecar.
    """
    global _config_cache
    with _lock:
        if _config_cache is not None:
            return _config_cache
    from core.constitution import DEFAULT_VOICE, Constitution

    try:
        cfg = Constitution.load().voice
    except Exception:  # noqa: BLE001 — never let config I/O kill the sidecar
        cfg = dict(DEFAULT_VOICE)
    with _lock:
        _config_cache = cfg
    return cfg


def reset_config_cache() -> None:
    """Clear the cached voice config (tests only)."""
    global _config_cache
    with _lock:
        _config_cache = None
