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
import os
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

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
        # Voice-OUT (2026-07-08): cached Piper voice + current playback handle
        # (for barge-in / mute-mid-speech). TTS runs independently of the mic
        # stack, so these are managed outside start()/stop().
        self._voice = None            # cached PiperVoice (lazy)
        self._voice_key: str | None = None  # path the cache was loaded for
        self._play_proc: subprocess.Popen | None = None
        # De-dupe guard (2026-07-08): the app can open the chat WebSocket more
        # than once (dev StrictMode, a reconnect, two windows), so the SAME
        # reply can arrive twice near-simultaneously. Speaking the identical
        # text again within this window is suppressed — the fix for "double
        # voices at the same time".
        self._last_spoken: tuple[str, float] = ("", 0.0)
        self._dedupe_window_s = 8.0

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
                # Voice-OUT (2026-07-08): whether replies/alerts are spoken,
                # and whether Piper (TTS-only) is importable regardless of the
                # full mic stack in ``deps_ok``.
                "speak_replies": bool(self._config.get("speak_replies", False)),
                "tts_ok": self._tts_ok(),
            }

    def _tts_ok(self) -> bool:
        """Whether Piper (voice-OUT) is importable (never raises)."""
        try:
            from osa_voice import tts_available

            return tts_available()[0]
        except Exception:  # noqa: BLE001
            return False

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
        Muting mid-sentence also cancels the current playback (barge-in).

        Returns:
            The full ``state()`` snapshot after the flip.
        """
        with self._lock:
            self._mute = bool(mute)
        if mute:
            self.stop_speaking()
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

    # ------------------------------------------------------------------ #
    # Voice-OUT (2026-07-08) — Piper TTS + macOS playback. Implemented ahead
    # of the mic stack: speaking needs no mic permission, so OSA can talk
    # before it can listen. Everything here is best-effort — a TTS failure
    # degrades to silent (the caller already has captions) and never raises.
    # ------------------------------------------------------------------ #
    def _voice_path(self) -> Path | None:
        """Resolve the configured Piper voice to an absolute .onnx path.

        ``piper_voice`` is either an absolute/relative path to an ``.onnx``
        file, or a bare voice NAME (``en_GB-alan-medium``) resolved under
        ``voice_dir``. ``~`` is expanded. Returns None when nothing resolves.
        """
        name = str(self._config.get("piper_voice", "")).strip()
        if not name:
            return None
        p = Path(os.path.expanduser(name))
        if p.suffix == ".onnx" and p.exists():
            return p
        vdir = Path(os.path.expanduser(str(self._config.get("voice_dir", ""))))
        cand = vdir / (name if name.endswith(".onnx") else f"{name}.onnx")
        return cand if cand.exists() else None

    def _load_voice(self):
        """Load + cache the Piper voice (lazy). None on any failure."""
        path = self._voice_path()
        if path is None:
            self._last_error = "no Piper voice model found (check voice.piper_voice / voice_dir)"
            return None
        key = str(path)
        with self._lock:
            if self._voice is not None and self._voice_key == key:
                return self._voice
        try:
            from piper import PiperVoice

            voice = PiperVoice.load(key)
        except Exception as exc:  # noqa: BLE001 — missing piper / bad model
            self._last_error = f"Piper load failed: {exc}"
            logger.warning(self._last_error)
            return None
        with self._lock:
            self._voice = voice
            self._voice_key = key
        return voice

    def stop_speaking(self) -> None:
        """Cancel any in-flight playback (barge-in / mute-mid-speech)."""
        with self._lock:
            proc = self._play_proc
            self._play_proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001 — already gone
                pass

    def speak(self, text: str, *, blocking: bool = False) -> dict:
        """Speak ``text`` aloud (voice-OUT entrypoint for replies + alerts).

        Independent of the mic stack and of ``start()``: gated only on Piper
        being importable, ``mute`` being off, and non-empty text. Synthesizes
        with the cached Piper voice and plays via macOS ``afplay``. Sets the
        service ``speaking`` for the duration, then restores the resting
        state. Non-blocking by default (returns immediately, plays on a
        worker thread); ``blocking=True`` for tests/PTT.

        Returns:
            ``{ok, reason}`` — ``ok`` False (with a reason) when muted, empty,
            Piper missing, or synth/playback failed.
        """
        text = (text or "").strip()
        if not text:
            return {"ok": False, "reason": "empty text"}
        if self._mute:
            return {"ok": False, "reason": "muted"}
        # De-dupe identical text within the window (double-open protection).
        with self._lock:
            last_text, last_ts = self._last_spoken
            if text == last_text and (time.monotonic() - last_ts) < self._dedupe_window_s:
                return {"ok": False, "reason": "duplicate"}
            self._last_spoken = (text, time.monotonic())
        from osa_voice import tts_available

        ok, missing = tts_available()
        if not ok:
            return {"ok": False, "reason": "missing: " + ", ".join(missing)}

        if blocking:
            return self._speak_now(text)
        threading.Thread(
            target=self._speak_now, args=(text,), daemon=True
        ).start()
        return {"ok": True, "reason": None}

    def _resting_state(self) -> str:
        """State to return to after speaking: idle if the full stack is up."""
        if self._config.get("enabled", False) and self._deps_ok:
            return "idle"
        return "disabled"

    def _speak_now(self, text: str) -> dict:
        """Synthesize + play synchronously. Best-effort; never raises."""
        self.stop_speaking()  # barge-in: newest utterance wins
        with self._lock:
            self._state = "speaking"
        try:
            self._synthesize(text)
            return {"ok": True, "reason": None}
        except Exception as exc:  # noqa: BLE001 — TTS failure => silent
            with self._lock:
                self._last_error = f"speak failed: {exc}"
            logger.warning(self._last_error, exc_info=True)
            return {"ok": False, "reason": self._last_error}
        finally:
            with self._lock:
                if self._state == "speaking":
                    self._state = self._resting_state()

    def _synthesize(self, text: str) -> None:
        """Speak OSA's reply with Piper (voice-OUT implemented 2026-07-08).

        Loads/caches the configured Piper voice, synthesizes ``text`` to a
        temp WAV, and plays it via macOS ``afplay`` (no PortAudio needed for
        output). Honors ``mute`` (skip playback). ``mark("first_audio")`` when
        playback starts (budget: text -> first audio < ~1 s, §3.4). Barge-in
        is handled by ``stop_speaking``/``_speak_now``. Raises on hard
        failure so ``_speak_now`` can record it; callers there never re-raise.

        Args:
            text: OSA's reply text (the ``reply`` field from
                ``POST /api/osa/chat`` — see the module-level contract).
        """
        voice = self._load_voice()
        if voice is None:
            raise RuntimeError(self._last_error or "no Piper voice")
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            with wave.open(tmp_path, "wb") as wf:
                voice.synthesize_wav(text, wf)
            if self._mute:
                return  # synthesized but silenced
            player = shutil.which("afplay")
            if not player:
                logger.info("no afplay on PATH — synthesized but not played")
                return
            self.mark("first_audio")
            proc = subprocess.Popen([player, tmp_path])
            with self._lock:
                self._play_proc = proc
            proc.wait()
            with self._lock:
                if self._play_proc is proc:
                    self._play_proc = None
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
