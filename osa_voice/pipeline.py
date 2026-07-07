"""VoiceService — the OSA voice-pipeline state machine (Phase 14d SCAFFOLD).

Architecture (design doc §2, option A — in-sidecar): the service runs as a
background task inside the FastAPI sidecar, started by the ``_start_osa_voice``
startup hook in ``gui/sidecar/app.py`` only when the Constitution's
``voice.enabled`` is true AND the optional deps are installed. Wake-word
listening is cheap; STT/TTS run in worker threads so the event loop is never
blocked. Extraction to a separate process is the 14f escape hatch if audio
work starves the sidecar.

Pipeline (design doc §3)::

    mic ──► openWakeWord ("osa") ──► capture until end-of-speech (webrtcvad)
                 │                              │
                 ▼                              ▼
           rolling few-hundred-ms         faster-whisper STT (worker thread)
           buffer, discarded                    │
           continuously                         ▼ text
                                     POST /api/osa/chat  (same turn as typed
                                                          input — see contract)
                                                │ reply text
                                                ▼
                              Piper TTS ──► speaker (barge-in: a new wake word
                                            cancels in-flight playback)

UTTERANCE -> AGENT CONTRACT (for the implementation pass): when a captured
utterance transcribes to text, the pipeline POSTs it through the SAME
``/api/osa/chat`` route used by typed input (localhost sidecar, body
``{"message": <text>, "thread_id": <sticky voice thread>}``) so voice turns
share the checkpointed OSA graph, model routing, persona, and the 14b
destructive-action confirm flow. The JSON ``reply`` is then synthesized via
``_synthesize`` and played. Captions should be emitted BEFORE synthesis
completes (captions-first hides TTS latency, §3.4).

States: ``disabled | idle | listening | transcribing | speaking | error``.
The service NEVER crashes the sidecar: missing deps or a NotImplementedError
from a stubbed stage land it in ``error``/``disabled`` with a reason in
``last_error``; every transition is observable via ``state()``.
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("agenticos.osa.voice")

#: Legal service states.
STATES = ("disabled", "idle", "listening", "transcribing", "speaking", "error")


class VoiceService:
    """State machine for the OSA voice pipeline (skeleton — no live audio).

    Args:
        config: Voice knobs; defaults to ``osa_voice.config.voice_config()``
            (the Constitution's ``voice:`` block). Injectable for tests.
        availability: Callable returning ``(ok, missing)``; defaults to
            ``osa_voice.voice_available``. Injectable for tests.
    """

    def __init__(self, config: dict | None = None, availability=None) -> None:
        if config is None:
            from osa_voice.config import voice_config

            config = voice_config()
        if availability is None:
            from osa_voice import voice_available

            availability = voice_available

        self._lock = threading.RLock()
        self._config = dict(config)
        self._availability = availability
        self._state = "disabled"
        self._mute = bool(self._config.get("mute", False))
        self._last_error: str | None = None
        self._latency: dict[str, float] = {}
        self._deps_ok, self._missing = self._probe_deps()

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    def _probe_deps(self) -> tuple[bool, list[str]]:
        """Run the availability probe defensively (never raises)."""
        try:
            return self._availability()
        except Exception:  # noqa: BLE001 — probe failure == unavailable
            return (False, ["<availability probe failed>"])

    def state(self) -> dict:
        """Snapshot of the service for ``GET /api/osa/voice/state``.

        Returns:
            ``{state, mute, deps_ok, missing, last_error, latency,
            push_to_talk_only, wake_word, stt_model, piper_voice}`` —
            ``latency`` is the ``mark()`` stamp dict (stage -> monotonic
            seconds), empty until the pipeline runs for real.
        """
        with self._lock:
            return {
                "state": self._state,
                "mute": self._mute,
                "deps_ok": self._deps_ok,
                "missing": list(self._missing),
                "last_error": self._last_error,
                "latency": dict(self._latency),
                "push_to_talk_only": bool(
                    self._config.get("push_to_talk_only", True)
                ),
                "wake_word": self._config.get("wake_word", "osa"),
                "stt_model": self._config.get("stt_model", "small"),
                "piper_voice": self._config.get("piper_voice", ""),
            }

    def mark(self, stage: str) -> float:
        """Record a monotonic latency stamp for a pipeline stage.

        Latency budget (§3.4 targets, checked in 14f):
            wake -> listening          < 300 ms
            end-of-speech -> text      < ~1.5 s   (small model)
            text -> first audio        < ~1 s     (local reply; longer w/ tools)

        Stages stamp themselves (``wake``, ``speech_end``, ``text``,
        ``first_audio``) so deltas between stamps give the per-hop numbers.

        Returns:
            The recorded ``time.monotonic()`` value.
        """
        stamp = time.monotonic()
        with self._lock:
            self._latency[stage] = stamp
        return stamp

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> bool:
        """Bring the service up (state transitions only in the skeleton).

        * ``voice.enabled`` false  -> stays ``disabled`` (reason recorded).
        * deps missing             -> ``error`` with the missing list.
        * enabled + deps ok        -> ``idle``; the implementation pass will
          additionally spawn ``_wake_loop`` here when ``push_to_talk_only``
          is false. Also warms Ollama (decision #9: ensure-on-OSA-init) —
          best-effort, in the impl pass.

        Returns:
            True when the service reached ``idle``; False otherwise. Never
            raises — failures are recorded in ``state()``.
        """
        with self._lock:
            if not self._config.get("enabled", False):
                self._state = "disabled"
                self._last_error = "voice.enabled is false in the Constitution"
                logger.debug("voice service not started: %s", self._last_error)
                return False
            self._deps_ok, self._missing = self._probe_deps()
            if not self._deps_ok:
                self._state = "error"
                self._last_error = (
                    "missing voice deps: " + ", ".join(self._missing)
                    + " (install with: .venv/bin/pip install -r requirements-voice.txt)"
                )
                logger.warning("voice service unavailable: %s", self._last_error)
                return False
            self._state = "idle"
            self._last_error = None
            logger.info(
                "voice service idle (push_to_talk_only=%s, wake_word=%r)",
                self._config.get("push_to_talk_only", True),
                self._config.get("wake_word", "osa"),
            )
            return True

    def stop(self) -> None:
        """Stop the service: cancel loops (impl pass) and go ``disabled``."""
        with self._lock:
            self._state = "disabled"
            self._last_error = "stopped"

    def push_to_talk(self) -> dict:
        """One push-to-talk turn: capture -> transcribe -> chat -> speak.

        Skeleton behaviour: refuses cleanly unless the service is ``idle``
        with deps present; with deps present the stubbed capture stage raises
        ``NotImplementedError``, which is caught and recorded — the sidecar
        never sees an exception.

        Returns:
            ``{ok, state, reason}`` — ``ok`` True only when a full turn ran
            (never, in the skeleton).
        """
        with self._lock:
            if self._state in ("disabled", "error") or not self._deps_ok:
                reason = self._last_error or "voice service is not running"
                return {"ok": False, "state": self._state, "reason": reason}
        try:
            self.mark("wake")  # PTT is a synthetic wake
            audio = self._capture_utterance()
            text = self._transcribe(audio)
            # Impl pass: POST text -> /api/osa/chat, then _synthesize(reply).
            self._synthesize(text)
            return {"ok": True, "state": self._state, "reason": None}
        except NotImplementedError:
            with self._lock:
                self._state = "error"
                self._last_error = "not_implemented: 14d skeleton — audio stages land in the implementation pass"
                return {"ok": False, "state": self._state, "reason": self._last_error}
        except Exception as exc:  # noqa: BLE001 — never crash the sidecar
            with self._lock:
                self._state = "error"
                self._last_error = f"push_to_talk failed: {exc}"
                logger.warning(self._last_error, exc_info=True)
                return {"ok": False, "state": self._state, "reason": self._last_error}

    def set_mute(self, mute: bool) -> dict:
        """Flip the global output mute (works even in the skeleton).

        Mute silences TTS playback only — the state machine keeps running so
        captions still flow. Runtime-only: does not write the YAML back.

        Returns:
            The full ``state()`` snapshot after the flip.
        """
        with self._lock:
            self._mute = bool(mute)
        logger.info("voice mute set to %s", mute)
        return self.state()

    # ------------------------------------------------------------------ #
    # Pipeline stages — STUBS (implementation pass fills these in).
    # Every stage is guarded by callers: NotImplementedError -> error state.
    # ------------------------------------------------------------------ #
    def _wake_loop(self) -> None:
        """Always-listening wake-word loop (openWakeWord) — NOT IMPLEMENTED.

        Design (§3.1): open a low-rate ``sounddevice`` input stream and feed a
        rolling few-hundred-ms buffer to an openWakeWord model for the
        configured ``wake_word`` ("osa" — custom model TBD, or a
        near-homophone + confirmation). The buffer is discarded continuously;
        mic audio never leaves the machine and is not recorded except the
        short utterance after a wake. On detection: ``mark("wake")``, cancel
        any in-flight TTS (barge-in, §3.3), transition ``idle -> listening``,
        then run capture -> transcribe -> chat -> speak and return to
        ``idle``. Runs in a worker thread; only spawned when
        ``push_to_talk_only`` is false (§9 Q3 — default stays PTT).
        """
        raise NotImplementedError("14d skeleton — wake loop lands in the implementation pass")

    def _capture_utterance(self) -> bytes:
        """Capture one utterance until end-of-speech — NOT IMPLEMENTED.

        Design (§3.2): record 16 kHz mono PCM from ``sounddevice`` while
        ``webrtcvad`` reports speech; end-of-speech = a run of ~600-800 ms of
        non-speech frames (with a hard max-utterance cap). State is
        ``listening`` for the duration; ``mark("speech_end")`` on completion.

        Returns:
            Raw PCM bytes of the captured utterance.
        """
        raise NotImplementedError("14d skeleton — capture lands in the implementation pass")

    def _transcribe(self, audio: bytes) -> str:
        """Transcribe an utterance with faster-whisper — NOT IMPLEMENTED.

        Design (§3.2): run the ``stt_model``-sized faster-whisper model in a
        worker thread (model loaded once, cached on the service). State is
        ``transcribing``; ``mark("text")`` when the transcript is ready.
        Budget: end-of-speech -> text < ~1.5 s on the small model (§3.4).

        Args:
            audio: Raw PCM bytes from ``_capture_utterance``.

        Returns:
            The transcript text (empty string for silence/noise).
        """
        raise NotImplementedError("14d skeleton — STT lands in the implementation pass")

    def _synthesize(self, text: str) -> None:
        """Speak OSA's reply with Piper — NOT IMPLEMENTED.

        Design (§3.3): stream ``text`` through the configured ``piper_voice``
        model (TBD — Tony auditions later) and play via ``sounddevice``.
        State is ``speaking``; ``mark("first_audio")`` when playback starts
        (budget: text -> first audio < ~1 s local, §3.4). Honors ``mute``
        (skip playback, captions only). Barge-in: a new wake word cancels
        in-flight playback. Captions are emitted before/while synthesizing so
        perceived latency stays low.

        Args:
            text: OSA's reply text (the ``reply`` field from
                ``POST /api/osa/chat`` — see the module-level contract).
        """
        raise NotImplementedError("14d skeleton — TTS lands in the implementation pass")
