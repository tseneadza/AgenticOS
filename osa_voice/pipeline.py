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
        # Speech GENERATION counter (2026-07-09, "multiple voices at once" fix).
        # The sentence-chunked _synthesize has windows where _play_proc is None
        # (between chunks, while synthesizing the next one) — in that window a
        # newer speak()'s stop_speaking() kills nothing, so the OLDER thread
        # keeps playing its remaining chunks alongside the new reply. This
        # monotonic counter is the authority instead of _play_proc alone: every
        # speak()/stop_speaking() bumps it, _speak_now captures the value it
        # owns, and the chunk loop aborts before each chunk once the counter
        # has moved on. A stale generation can never reach the speaker.
        self._speak_gen = 0
        # De-dupe guard (2026-07-08): the app can open the chat WebSocket more
        # than once (dev StrictMode, a reconnect, two windows), so the SAME
        # reply can arrive twice near-simultaneously. Speaking the identical
        # text again within this window is suppressed — the fix for "double
        # voices at the same time".
        self._last_spoken: tuple[str, float] = ("", 0.0)
        self._dedupe_window_s = 8.0
        # Voice-IN (2026-07-08): cached faster-whisper models (keyed by size —
        # "small" for commands, "tiny" for fast wake checks) + the sticky
        # thread id all voice turns share (one durable voice conversation).
        self._stt_models: dict[str, object] = {}
        self._voice_thread: str | None = None
        # Wake word (2026-07-08, §9 Q3 RESOLVED as runtime opt-in): the
        # always-listening loop is a daemon thread, started ONLY by set_wake
        # (never by config) — every sidecar start comes up push-to-talk only.
        self._wake_thread: threading.Thread | None = None
        self._wake_stop = threading.Event()
        # Wake turns run on a worker thread (2026-07-08, Tony's latency
        # feedback) so the loop keeps LISTENING while OSA thinks/speaks —
        # otherwise the mic is deaf for the whole LLM round-trip.
        self._turn_thread: threading.Thread | None = None
        # Conversation mode (2026-07-08): when a reply FINISHES playing, a
        # follow-up window opens — the next utterance inside it needs no wake
        # word. Monotonic stamp of the last completed playback.
        self._last_reply_done: float = 0.0
        # Half-duplex echo guard (2026-07-14): monotonic stamp of when the
        # most recent _capture_utterance began recording. Wake turns speak
        # on a worker thread while the main loop keeps listening, so the mic
        # captures OSA's own TTS reply; comparing this start against playback
        # (see _capture_was_echo) lets us drop those self-heard bursts.
        self._last_capture_start: float = 0.0

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
                # Wake word (2026-07-08): whether the always-listening loop is
                # live right now (runtime toggle — never persisted).
                "wake_active": bool(
                    self._wake_thread is not None and self._wake_thread.is_alive()
                ),
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
        """Stop the service: cancel the wake loop and go ``disabled``."""
        self._stop_wake_thread()
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
            if self._state in ("listening", "transcribing"):
                return {
                    "ok": False,
                    "state": self._state,
                    "reason": "a voice turn is already in progress",
                }
            # Wake loop owns the mic while active — a second input stream
            # would fight it (2026-07-08). Just speak instead.
            if self._wake_thread is not None and self._wake_thread.is_alive():
                return {
                    "ok": False,
                    "state": self._state,
                    "reason": "wake listening is on — just say the wake word",
                }
        try:
            self.mark("wake")  # PTT is a synthetic wake
            self.stop_speaking()  # barge-in: pressing PTT cancels playback
            audio = self._capture_utterance()
            text = self._transcribe(audio)
            if not text:
                with self._lock:
                    self._state = self._resting_state()
                return {
                    "ok": False,
                    "state": self._state,
                    "reason": "no speech detected",
                    "transcript": "",
                }
            # Contract (module docstring): the utterance goes through the SAME
            # /api/osa/chat turn as typed input. That route speaks the reply
            # itself via _maybe_speak_reply (dual-path rule — side effects live
            # in the routes); here we only return captions.
            import uuid

            turn_id = uuid.uuid4().hex
            reply = self._voice_turn(text, turn_id=turn_id)
            with self._lock:
                self._state = self._resting_state()
            return {
                "ok": True,
                "state": self._state,
                "reason": None,
                "transcript": text,
                "reply": reply,
                # 14x: the UI folds this spoken turn into the shared transcript
                # live from the bus; the turn_id lets it de-dupe the caption it
                # also renders synchronously from this response.
                "turn_id": turn_id,
            }
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
    # Wake word (2026-07-08) — "Hey Osa", STT-gated. §9 Q3 RESOLVED: Tony
    # opted in as a RUNTIME toggle, default OFF — the YAML default stays
    # push_to_talk_only=true and the safety test keeps guarding it. Design
    # deviation from §3.1: openWakeWord ships no "osa" model, so v1 uses the
    # design doc's own fallback (near-homophone matching): webrtcvad gates
    # speech into utterances, whisper-TINY transcribes the burst (fast), and
    # the leading tokens are fuzzy-matched against ``wake_aliases``. A trained
    # openWakeWord "osa" model can replace _wake_check later without touching
    # the loop. Audio is processed in-memory and discarded — nothing is
    # persisted and nothing leaves the machine.
    # ------------------------------------------------------------------ #
    #: Whisper renderings of "osa" (it's not a dictionary word) — leading-
    #: token match, case/punctuation-insensitive. Config ``wake_aliases``
    #: extends this list.
    _WAKE_ALIASES = (
        "osa", "ossa", "oza", "osah", "o s a", "ohsa",
        # Live-tuning 2026-07-08 (Tony's session): whisper renderings heard
        # in practice — "Osa" is close to a real word and drifts.
        "osaka", "osas", "olsa", "hosa", "oh sa", "oh za",
        # Live-tuning 2026-07-10 (Tony on Bluetooth HEADPHONES): the headset
        # mic's codec shifts whisper's drift — "Osa" arrived as "O.S.",
        # "Usa.", "Elsa.", and "Oh, sir" (all seen in wake discards).
        "os", "usa", "elsa", "oh sir",
    )
    #: Whisper's stock hallucinations on noise/music (YouTube-training
    #: artifacts) — never valid follow-up commands (cleaned, lowercased).
    _FOLLOWUP_STOPLIST = frozenset((
        "thank you", "thanks for watching", "thank you for watching",
        "thanks for listening", "see you next time", "see you later",
        "bye bye", "the end", "so", "you",
    ))


    def set_wake(self, enabled: bool) -> dict:
        """Start/stop the always-listening wake loop (runtime-only toggle).

        Never persisted: every sidecar start comes up push-to-talk only and
        the loop runs ONLY after an explicit opt-in (§9 Q3). Starting
        requires the service to be running (``idle``) with deps present.

        Returns:
            The full ``state()`` snapshot after the flip (``wake_active``
            reports the live thread).
        """
        if not enabled:
            self._stop_wake_thread()
            return self.state()
        with self._lock:
            if self._wake_thread is not None and self._wake_thread.is_alive():
                return self.state()  # already on
            if self._state in ("disabled", "error") or not self._deps_ok:
                self._last_error = (
                    self._last_error or "voice service is not running"
                )
                return self.state()
            self._wake_stop.clear()
            self._wake_thread = threading.Thread(
                target=self._wake_loop, daemon=True, name="osa-wake-loop"
            )
            self._wake_thread.start()
        logger.info("wake loop ON (aliases=%s)", self._wake_aliases())
        return self.state()

    def _stop_wake_thread(self) -> None:
        """Signal the wake loop to exit and reap the thread (best-effort)."""
        with self._lock:
            thread = self._wake_thread
            self._wake_thread = None
        self._wake_stop.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def _wake_aliases(self) -> tuple[str, ...]:
        """Wake-word aliases: built-ins + Constitution ``wake_aliases``."""
        extra = self._config.get("wake_aliases") or []
        return self._WAKE_ALIASES + tuple(
            str(a).strip().lower() for a in extra if str(a).strip()
        )

    def _match_wake(self, text: str) -> str | None:
        """Match a transcript against the wake word; return the command tail.

        "Osa" alone -> ``""`` (ack + listen for the command). "Osa, what time
        is it" -> ``"what time is it"``. The wake word may sit ANYWHERE in
        the first three words (2026-07-08, live fix: Tony's natural "Hello,
        Osa. …" was discarded by strict leading-word matching) — so "Hey
        Osa", "Hello Osa", "Excuse me, Osa …" all wake. Deeper mentions do
        NOT wake ("tell me about osa" stays a discard — false-positive
        guard while background speech is playing). Returns None when the
        utterance is not addressed to OSA (discarded).
        """
        # Match on per-word cleaned tokens but return the ORIGINAL words, so
        # the command tail keeps its punctuation ("what's" stays "what's").
        words = (text or "").split()
        cleaned = ["".join(c for c in w.lower() if c.isalnum()) for w in words]
        pairs = [(w, c) for w, c in zip(words, cleaned) if c]
        if not pairs:
            return None
        aliases = set(self._wake_aliases())
        for start in range(min(3, len(pairs))):
            for n in (3, 2, 1):  # "o s a" spans three words
                if start + n <= len(pairs):
                    gram = " ".join(c for _, c in pairs[start:start + n])
                    if gram in aliases:
                        return " ".join(w for w, _ in pairs[start + n:]).strip()
        return None

    def _wake_loop(self) -> None:
        """Always-listening loop: VAD-gate -> tiny STT -> wake match -> turn.

        Runs on a daemon thread until ``_wake_stop`` is set. Each pass blocks
        in ``_capture_utterance`` (start-timeout returns b"" so the stop flag
        is polled every few seconds). Wake bursts are checked with the
        ``wake_stt_model`` ("tiny"); a matched inline command runs directly;
        a bare wake word gets a spoken ack, then a second capture at command
        quality (``stt_model``). On wake: ``mark("wake")`` + barge-in. Every
        iteration is guarded — an audio error lands in ``error`` and exits
        the loop rather than spinning.
        """
        wake_size = str(self._config.get("wake_stt_model", "tiny") or "tiny")
        while not self._wake_stop.is_set():
            try:
                audio = self._capture_utterance()
                capture_start = self._last_capture_start
                if self._wake_stop.is_set():
                    break
                if not audio:
                    with self._lock:
                        if self._state == "listening":
                            self._state = self._resting_state()
                    continue
                heard = self._transcribe(audio, size=wake_size)
                # Half-duplex echo guard (2026-07-14): drop any burst whose
                # recording overlapped OSA's own playback (or its cooldown
                # tail). Placed BEFORE _match_wake so neither the follow-up
                # path nor the wake-match path can act on echo-tainted audio
                # — otherwise OSA answers its own reply (follow-up) or even
                # re-triggers the wake word from it, cascading indefinitely.
                if self._capture_was_echo(capture_start):
                    if heard.strip():
                        logger.info("echo discard: %r", heard.strip()[:80])
                    with self._lock:
                        self._state = self._resting_state()
                    continue
                command = self._match_wake(heard)
                if command is None:
                    # Conversation mode (2026-07-08): inside the follow-up
                    # window a wake-free utterance IS the command — but only
                    # when nothing is playing (echo guard) and it has some
                    # substance (>=2 words — filters whisper's "Thank you."
                    # hallucinations on noise).
                    followup_s = float(self._config.get("followup_window_s", 8.0))
                    with self._lock:
                        playing = (
                            self._play_proc is not None
                            and self._play_proc.poll() is None
                        )
                        within = (
                            followup_s > 0
                            and (time.monotonic() - self._last_reply_done) < followup_s
                        )
                    cleaned_heard = " ".join(
                        "".join(c for c in w.lower() if c.isalnum())
                        for w in heard.split()
                    ).strip()
                    if (
                        within
                        and not playing
                        and len(heard.split()) >= 2
                        and cleaned_heard not in self._FOLLOWUP_STOPLIST
                    ):
                        # Re-transcribe at command quality (the wake pass used
                        # the tiny model).
                        command = self._transcribe(audio) or heard.strip()
                        logger.info("follow-up: %r", command)
                    else:
                        if heard.strip():
                            # Alias-tuning breadcrumb: what whisper heard when
                            # we DIDN'T wake (in-memory audio discarded).
                            logger.info("wake discard: %r", heard.strip()[:80])
                        with self._lock:
                            self._state = self._resting_state()
                        continue  # not addressed to OSA — burst discarded
                self.mark("wake")
                self.stop_speaking()  # barge-in (§3.3)
                if not command:
                    # Bare "Osa" — acknowledge, then capture the command at
                    # full quality (blocking so we don't capture our own ack).
                    self.speak(
                        str(self._config.get("wake_ack", "Yes?")), blocking=True
                    )
                    audio = self._capture_utterance()
                    command = self._transcribe(audio)
                if command:
                    # Run the turn OFF-loop so we keep listening during the
                    # LLM round-trip + reply playback. One turn at a time —
                    # a new command while busy gets a spoken deferral (the
                    # barge-in above already cut any in-flight playback).
                    with self._lock:
                        busy = (
                            self._turn_thread is not None
                            and self._turn_thread.is_alive()
                        )
                    if busy:
                        self.speak("One moment.")
                    else:
                        t = threading.Thread(
                            target=self._run_wake_turn,
                            args=(command,),
                            daemon=True,
                            name="osa-wake-turn",
                        )
                        with self._lock:
                            self._turn_thread = t
                        t.start()
                with self._lock:
                    self._state = self._resting_state()
            except Exception as exc:  # noqa: BLE001 — never crash the sidecar
                with self._lock:
                    self._state = "error"
                    self._last_error = f"wake loop failed: {exc}"
                logger.warning(self._last_error, exc_info=True)
                break
        with self._lock:
            if self._wake_thread is threading.current_thread():
                self._wake_thread = None

    def _run_wake_turn(self, command: str) -> None:
        """One wake-initiated agent turn (worker thread; never raises).

        The chat route speaks the reply itself; failures are logged and
        recorded in ``last_error`` without touching the loop's state — the
        wake loop stays alive and listening either way.
        """
        try:
            reply = self._voice_turn(command)
            logger.info("wake turn: %r -> %r", command, reply[:80])
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._last_error = f"wake turn failed: {exc}"
            logger.warning(self._last_error, exc_info=True)

    def _capture_was_echo(self, capture_start: float) -> bool:
        """True if OSA's own playback overlapped a capture window.

        Half-duplex echo guard (2026-07-14): wake turns speak on a worker
        thread while the main loop keeps LISTENING, so the mic picks up
        OSA's TTS reply. An utterance whose recording overlapped playback
        finishes just AFTER ``_play_proc`` clears, so the live "is audio
        playing right now" check alone misses it. We therefore also treat a
        capture that STARTED within ``echo_cooldown_s`` of a completed
        playback as echo — that both catches the overlap case (playback
        ended after our start, so ``_last_reply_done >= capture_start``) and
        swallows the reverberant tail just after playback ends. Callers
        discard such bursts so OSA can't answer — or re-wake — itself.
        """
        cooldown = float(self._config.get("echo_cooldown_s", 1.0))
        with self._lock:
            playing = (
                self._play_proc is not None
                and self._play_proc.poll() is None
            )
            recent = self._last_reply_done >= capture_start - cooldown
        return playing or recent

    def _capture_utterance(self) -> bytes:
        """Capture one utterance until end-of-speech (voice-IN, 2026-07-08).

        Design (§3.2): 16 kHz mono int16 PCM from ``sounddevice`` in 30 ms
        frames, gated by ``webrtcvad``. A ~300 ms pre-roll ring buffer is
        prepended when speech starts so the first syllable isn't clipped.
        End-of-speech = ``end_silence_ms`` (default 700) of consecutive
        non-speech frames; hard caps: ``start_timeout_s`` (default 6 — nobody
        spoke) and ``max_utterance_s`` (default 30). The armed/waiting window
        reads ``idle`` (resting state); the state flips to ``listening`` only
        once speech actually starts, so the orb isn't stuck "listening" while
        merely waiting for the wake word (Tony, 2026-07-09).
        ``mark("speech_end")`` on completion. Audio never leaves the machine
        and is not persisted.

        Returns:
            Raw PCM bytes of the captured utterance (b"" when nobody spoke).
        """
        # Half-duplex echo guard (2026-07-14): stamp when recording begins,
        # before the input stream opens, so the caller can tell whether this
        # window overlapped OSA's own playback (self-heard echo).
        self._last_capture_start = time.monotonic()
        import numpy as np
        import sounddevice as sd
        import webrtcvad

        sample_rate = 16000
        frame_ms = 30
        frame_samples = sample_rate * frame_ms // 1000  # 480
        vad = webrtcvad.Vad(int(self._config.get("vad_aggressiveness", 2)))
        start_timeout_s = float(self._config.get("start_timeout_s", 6.0))
        end_silence_ms = int(self._config.get("end_silence_ms", 700))
        max_utterance_s = float(self._config.get("max_utterance_s", 30.0))
        end_silence_frames = max(1, end_silence_ms // frame_ms)
        # Energy gate (2026-07-08, live-calibrated with Tony): webrtcvad calls
        # ANY speech "speech", including a TV across the room — which merges
        # utterances into endless noisy bursts and buries the user. Their
        # voice at arm's length measured ~7x the TV's frame energy, so frames
        # must ALSO clear this RMS floor to count as speech. 0 disables.
        min_rms = float(self._config.get("min_rms", 0.02))
        # Optional named input device (substring match, e.g. "MacBook");
        # default None = system default input.
        device = None
        want = str(self._config.get("input_device", "") or "").strip().lower()
        if want:
            try:
                for i, d in enumerate(sd.query_devices()):
                    if d["max_input_channels"] > 0 and want in d["name"].lower():
                        device = i
                        break
            except Exception:  # noqa: BLE001 — fall back to default input
                device = None

        from collections import deque

        pre: deque[bytes] = deque(maxlen=10)  # ~300 ms pre-roll
        voiced: list[bytes] = []
        in_speech = False
        silence_run = 0
        started = time.monotonic()

        # ponytail: stay at the resting state (idle) while armed; "listening"
        # is set below the instant VAD detects directed speech — not for the
        # whole start-timeout window (that's what pinned the orb "listening").
        with self._lock:
            self._state = self._resting_state()
        try:
            with sd.RawInputStream(
                samplerate=sample_rate,
                blocksize=frame_samples,
                channels=1,
                dtype="int16",
                device=device,
            ) as stream:
                while True:
                    data, _overflowed = stream.read(frame_samples)
                    frame = bytes(data)
                    try:
                        is_speech = vad.is_speech(frame, sample_rate)
                    except Exception:  # noqa: BLE001 — odd frame => not speech
                        is_speech = False
                    if is_speech and min_rms > 0:
                        samples = np.frombuffer(frame, dtype=np.int16)
                        rms = float(
                            np.sqrt(np.mean((samples.astype(np.float32) / 32768.0) ** 2))
                        )
                        is_speech = rms >= min_rms
                    elapsed = time.monotonic() - started
                    if not in_speech:
                        pre.append(frame)
                        if is_speech:
                            in_speech = True
                            voiced.extend(pre)
                            pre.clear()
                            with self._lock:
                                self._state = "listening"
                        elif elapsed > start_timeout_s:
                            return b""  # nobody spoke
                    else:
                        voiced.append(frame)
                        silence_run = 0 if is_speech else silence_run + 1
                        if silence_run >= end_silence_frames:
                            break
                        if elapsed > max_utterance_s:
                            break
        finally:
            self.mark("speech_end")
        return b"".join(voiced)

    def _load_stt(self, size: str | None = None):
        """Load + cache a faster-whisper model by size (lazy). Raises on failure.

        Default size is the Constitution's ``stt_model`` (commands); the wake
        loop passes ``wake_stt_model`` ("tiny") for fast wake checks. First
        call per size downloads the model from Hugging Face into the local
        cache (~/.cache/huggingface) — pre-warm on-device so the first live
        turn isn't a multi-minute download.
        """
        if size is None:
            size = str(self._config.get("stt_model", "small") or "small")
        with self._lock:
            cached = self._stt_models.get(size)
        if cached is not None:
            return cached
        from faster_whisper import WhisperModel

        model = WhisperModel(size, device="cpu", compute_type="int8")
        with self._lock:
            self._stt_models[size] = model
        return model

    def _transcribe(self, audio: bytes, *, size: str | None = None) -> str:
        """Transcribe an utterance with faster-whisper (voice-IN, 2026-07-08).

        Design (§3.2): the ``stt_model``-sized model (default "small",
        int8/CPU) is loaded once and cached on the service. Runs in the
        caller's thread — PTT turns already run in the FastAPI threadpool, so
        the event loop is never blocked. State is ``transcribing``;
        ``mark("text")`` when the transcript is ready. Budget:
        end-of-speech -> text < ~1.5 s on the small model (§3.4).

        Args:
            audio: Raw 16 kHz mono int16 PCM from ``_capture_utterance``.

        Returns:
            The transcript text (empty string for silence/noise).
        """
        if not audio:
            return ""
        with self._lock:
            self._state = "transcribing"
        import numpy as np

        pcm = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        model = self._load_stt(size)
        segments, _info = model.transcribe(
            pcm,
            language=str(self._config.get("stt_language", "en")),
            beam_size=1,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        self.mark("text")
        return text

    def _active_thread_id(self) -> str:
        """Resolve the thread for this voice turn — UNIFIED with the UI.

        Prefers the on-screen chat's active thread (set via
        ``/api/osa/active-thread``) so spoken turns land in the SAME
        transcript the user is viewing. Falls back to the pipeline's sticky
        per-lifetime ``_voice_thread`` when no UI thread is set. Any
        import/lookup failure falls back defensively — never raises.
        """
        import uuid

        with self._lock:
            if not self._voice_thread:
                self._voice_thread = f"osa-voice-{uuid.uuid4().hex[:10]}"
            thread_id = self._voice_thread
        try:
            from gui.sidecar.osa_active_thread import get_active_thread

            active = get_active_thread()
            if active:
                return active
        except Exception:  # noqa: BLE001 — never break voice over a thread lookup
            pass
        return thread_id

    def _voice_turn(self, text: str, *, turn_id: str | None = None) -> str:
        """Run one voice turn AND publish it to the AG-UI bus for the UI.

        Wraps the shared ``_chat_turn`` (which POSTs the SAME /api/osa/chat
        route as typed input, preserving model routing, the 14b confirm flow
        and TTS via ``_maybe_speak_reply``) with two bus events so the spoken
        exchange appears live in the on-screen OSA transcript:

          * ``OSA_VOICE_TURN_STARTED`` the moment the transcript is known.
          * ``OSA_VOICE_TURN_FINISHED`` with the authoritative reply text.

        Every event is tagged ``source="voice"`` so the UI can tell spoken
        turns apart from workflow AG-UI events on the same bus. Publishing is
        best-effort — a bus failure never breaks the turn or the reply.
        """
        import uuid

        turn_id = turn_id or uuid.uuid4().hex
        thread_id = self._active_thread_id()
        self._publish_voice_event(
            "OSA_VOICE_TURN_STARTED",
            turn_id=turn_id, thread_id=thread_id, user=text, source="voice",
        )
        reply = self._chat_turn(text)
        self._publish_voice_event(
            "OSA_VOICE_TURN_FINISHED",
            turn_id=turn_id, thread_id=thread_id, reply=reply, source="voice",
        )
        return reply

    def _publish_voice_event(self, event_type: str, **payload) -> None:
        """Best-effort publish to the AG-UI bus (lazy import, never raises)."""
        try:
            from gui.sidecar.events import bus

            bus.publish(event_type, **payload)
        except Exception:  # noqa: BLE001 — the bus is a garnish, never a dep
            pass

    def _chat_turn(self, text: str) -> str:
        """Run one agent turn for a transcribed utterance (fixed contract).

        POSTs through the SAME ``/api/osa/chat`` route as typed input — shared
        checkpointed graph, model routing, persona, and the 14b confirm flow.
        All voice turns share one sticky ``thread_id`` (minted per service
        lifetime) so the voice conversation is durable and coherent. The
        route itself speaks the reply (``_maybe_speak_reply``); this method
        only returns the caption text.

        Args:
            text: The transcript from ``_transcribe`` (non-empty).

        Returns:
            OSA's reply text ("" if the route returned none).
        """
        import requests

        thread_id = self._active_thread_id()
        try:
            from gui.sidecar.app import SIDECAR_PORT as port
        except Exception:  # noqa: BLE001 — standalone/test use
            port = 5130
        resp = requests.post(
            f"http://127.0.0.1:{port}/api/osa/chat",
            json={"message": text, "thread_id": thread_id},
            timeout=float(self._config.get("chat_timeout_s", 180.0)),
        )
        resp.raise_for_status()
        return str(resp.json().get("reply") or "")

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
        """Cancel any in-flight playback (barge-in / mute-mid-speech).

        Bumps the speech generation so any _synthesize loop currently between
        chunks (with _play_proc momentarily None) sees itself as stale and
        abandons its remaining chunks — the window that let an old reply keep
        playing under a new one. Then terminates the live afplay if there is
        one.
        """
        with self._lock:
            self._speak_gen += 1
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
        self.stop_speaking()  # barge-in: newest utterance wins (bumps the gen)
        # Claim the generation this reply owns, AFTER the barge-in bump above.
        # A later speak()/stop_speaking() bumps past it, and _synthesize aborts
        # the moment it notices — so only the newest reply ever reaches the
        # speaker (the "multiple voices at once" fix).
        with self._lock:
            my_gen = self._speak_gen
            self._state = "speaking"
        try:
            self._synthesize(text, gen=my_gen)
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
                # Conversation mode: the follow-up window opens NOW — only
                # after playback ends, so OSA's own speaker output can never
                # be captured as a wake-free "command" (feedback guard).
                self._last_reply_done = time.monotonic()

    def _synthesize(self, text: str, *, gen: int | None = None) -> None:
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
            gen: The speech generation this reply owns (from ``_speak_now``).
                Before playing each chunk the loop confirms ``_speak_gen``
                still equals ``gen``; if a newer speak()/stop_speaking() has
                moved it on, this reply is stale and abandons its remaining
                chunks — closing the between-chunks window where ``_play_proc``
                is None and an old reply could otherwise play under a new one.
                ``None`` (direct/test callers) skips the check.
        """
        voice = self._load_voice()
        if voice is None:
            raise RuntimeError(self._last_error or "no Piper voice")
        # Cadence (2026-07-08, Tony's live feedback): length_scale < 1.0 speaks
        # faster than the model's deliberate trained pace. Best-effort — an
        # old piper without SynthesisConfig just uses the default cadence.
        syn_config = None
        try:
            from piper import SynthesisConfig

            syn_config = SynthesisConfig(
                length_scale=float(self._config.get("length_scale", 1.0))
            )
        except Exception:  # noqa: BLE001 — keep speaking at default pace
            syn_config = None

        def _synth_chunk(chunk: str) -> str:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            path = tmp.name
            tmp.close()
            with wave.open(path, "wb") as wf:
                voice.synthesize_wav(chunk, wf, syn_config=syn_config)
            return path

        # Sentence-chunked playback (2026-07-08, Tony's latency feedback):
        # synthesize sentence 1 and START PLAYING it, synthesizing sentence
        # i+1 while sentence i plays. Time-to-first-audio = one sentence's
        # synth instead of the whole reply's. Barge-in (stop_speaking)
        # terminates the current afplay and abandons the remaining chunks.
        #
        # Generation guard (2026-07-09): before EACH chunk we confirm this
        # reply still owns the current generation. A newer speak() bumps it,
        # so a reply caught mid-loop (between chunks, _play_proc None) sees
        # itself as stale and stops — it can no longer sneak its remaining
        # chunks onto the speaker under the new reply. Claiming _play_proc is
        # done under the same staleness check so a stale reply never even
        # registers a proc a later stop_speaking() would miss.
        chunks = self._split_sentences(text) or [text]
        next_path: str | None = _synth_chunk(chunks[0])
        first = True
        try:
            for i in range(len(chunks)):
                cur = next_path
                next_path = None
                if cur is None:
                    break
                if self._mute:
                    return  # synthesized but silenced (mute mid-reply)
                player = shutil.which("afplay")
                if not player:
                    logger.info("no afplay on PATH — synthesized but not played")
                    return
                if first:
                    self.mark("first_audio")
                    first = False
                # Start playback only if still current, and register the proc
                # atomically with that check (else a stop_speaking() that fires
                # between the check and the assignment would miss it).
                proc = subprocess.Popen([player, cur])
                with self._lock:
                    if gen is not None and self._speak_gen != gen:
                        superseded = True  # a newer reply already took over
                    else:
                        self._play_proc = proc
                        superseded = False
                if superseded:
                    try:
                        proc.terminate()
                    except Exception:  # noqa: BLE001 — already gone
                        pass
                    try:
                        os.unlink(cur)
                    except OSError:
                        pass
                    break
                if i + 1 < len(chunks):
                    next_path = _synth_chunk(chunks[i + 1])  # overlaps playback
                proc.wait()
                cancelled = False
                with self._lock:
                    if self._play_proc is proc:
                        self._play_proc = None
                    else:
                        cancelled = True  # stop_speaking() intervened
                    if gen is not None and self._speak_gen != gen:
                        cancelled = True  # a newer reply superseded us
                try:
                    os.unlink(cur)
                except OSError:
                    pass
                if cancelled or (getattr(proc, "returncode", 0) or 0) != 0:
                    break  # barge-in / kill / superseded — drop the rest
        finally:
            if next_path is not None:
                try:
                    os.unlink(next_path)
                except OSError:
                    pass

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split a reply into playback chunks (sentences, tiny ones merged).

        Merging avoids choppy inter-chunk gaps on short sentences ("Yes.",
        "Done.") while keeping the first chunk small enough that
        time-to-first-audio stays low.
        """
        import re

        parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", (text or "").strip())]
        parts = [p for p in parts if p]
        chunks: list[str] = []
        for p in parts:
            if chunks and (len(chunks[-1]) < 40 or len(p) < 12):
                chunks[-1] = f"{chunks[-1]} {p}"
            else:
                chunks.append(p)
        return chunks
