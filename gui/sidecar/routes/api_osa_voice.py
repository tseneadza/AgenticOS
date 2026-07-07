"""OSA voice-pipeline API endpoints (Phase 14d — scaffold).

GET  /api/osa/voice/state — voice service snapshot: state machine position,
                            mute, dep availability + missing list, last error,
                            latency stamps, and the active config knobs.
POST /api/osa/voice/ptt   — push-to-talk trigger (one capture->chat->speak
                            turn). 409 while the service is disabled, deps are
                            missing, or (this phase) the audio stages are
                            still the 14d skeleton stubs.
POST /api/osa/voice/mute  — flip the global output mute. Body ``{mute: bool}``.
                            Works even in the skeleton / while disabled.

Kept in its own routes module (rather than growing ``api_osa.py``, which is
the chat + confirm-flow surface) — voice is a distinct subsystem with its own
service object. The service itself lives in ``osa_voice/`` at the repo root
(design doc §2) and is imported lazily so the sidecar never needs the optional
audio deps. Every route here is registered in ``HubApiExplorer.jsx``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class VoiceMute(BaseModel):
    """Request body for the mute toggle."""

    mute: bool


@router.get("/api/osa/voice/state")
def osa_voice_state() -> dict:
    """Return the voice service snapshot (cheap, read-only, never 5xx).

    Shape: ``{state, mute, deps_ok, missing, last_error, latency,
    push_to_talk_only, wake_word, stt_model, piper_voice, enabled}`` —
    ``enabled`` is the Constitution flag so the GUI can distinguish
    "off by config" from "on but broken".
    """
    from osa_voice import get_service
    from osa_voice.config import voice_config

    snapshot = get_service().state()
    snapshot["enabled"] = bool(voice_config().get("enabled", False))
    return snapshot


@router.post("/api/osa/voice/ptt")
def osa_voice_ptt() -> dict:
    """Trigger one push-to-talk turn (capture -> transcribe -> chat -> speak).

    Raises:
        HTTPException: 409 when the service can't run a turn — voice disabled
            in the Constitution, optional deps missing, or (14d skeleton) the
            audio stages are not implemented yet. The detail carries the
            machine-readable reason.
    """
    from osa_voice import get_service

    result = get_service().push_to_talk()
    if not result.get("ok"):
        raise HTTPException(
            409, result.get("reason") or "voice service is not running"
        )
    return result


@router.post("/api/osa/voice/mute")
def osa_voice_mute(body: VoiceMute) -> dict:
    """Set the global output mute; returns the post-flip state snapshot.

    Runtime-only (in-memory on the service) — the Constitution YAML is not
    rewritten. Works regardless of service state so Tony can pre-mute before
    ever enabling voice.
    """
    from osa_voice import get_service

    return get_service().set_mute(body.mute)
