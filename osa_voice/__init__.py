"""OSA voice pipeline (Phase 14d) — wake word -> STT -> agent -> TTS.

SCAFFOLD: package structure, config, state machine, and API surface are real;
the audio stages raise ``NotImplementedError`` until the on-device
implementation pass. The heavy deps (openWakeWord, faster-whisper, Piper,
sounddevice, webrtcvad) are OPTIONAL — declared in ``requirements-voice.txt``,
never imported at module import time, so the sidecar runs fully with zero
voice deps installed.

Public surface:
    voice_available() -> (ok, missing)   # never raises
    get_service()     -> VoiceService    # process-wide singleton
    reset_service()                      # tests only
"""
from __future__ import annotations

import importlib.util
import threading

# pip-install name -> importable module name. Checked with find_spec so the
# probe is cheap and has no import side effects (openwakeword in particular
# loads models on import).
OPTIONAL_DEPS: dict[str, str] = {
    "openwakeword": "openwakeword",
    "faster-whisper": "faster_whisper",
    "piper-tts": "piper",
    "sounddevice": "sounddevice",
    "webrtcvad": "webrtcvad",
}

_lock = threading.Lock()
_service = None  # populated lazily by get_service()


def voice_available() -> tuple[bool, list[str]]:
    """Report whether the optional voice deps are importable.

    Returns:
        ``(ok, missing)`` — ``ok`` is True only when every dep in
        ``OPTIONAL_DEPS`` resolves; ``missing`` lists the pip-install names
        of the absent ones (matching ``requirements-voice.txt`` lines).
        Never raises: any probe failure counts the dep as missing.
    """
    missing: list[str] = []
    for pip_name, module_name in OPTIONAL_DEPS.items():
        try:
            if importlib.util.find_spec(module_name) is None:
                missing.append(pip_name)
        except Exception:  # noqa: BLE001 — a broken install is still "missing"
            missing.append(pip_name)
    return (not missing, missing)


def get_service():
    """Return the process-wide ``VoiceService`` singleton (lazy-created)."""
    global _service
    with _lock:
        if _service is None:
            from osa_voice.pipeline import VoiceService

            _service = VoiceService()
        return _service


def reset_service() -> None:
    """Drop the singleton so the next get_service() builds fresh (tests only)."""
    global _service
    with _lock:
        _service = None
