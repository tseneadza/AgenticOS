"""Wake word — "Hey Osa" (2026-07-08). STT-gated loop, runtime toggle.

§9 Q3 RESOLVED: always-listening is a RUNTIME opt-in (set_wake / POST
/api/osa/voice/wake), never persisted — the YAML `push_to_talk_only: true`
default stays and its safety test keeps guarding it. These tests mock every
audio stage: no mic, no whisper, no Piper — headless-safe.
"""
from __future__ import annotations

import threading
import time

import pytest

from core.constitution import DEFAULT_VOICE
from osa_voice.pipeline import VoiceService


def _svc(**over):
    cfg = {**DEFAULT_VOICE, "enabled": True, **over}
    return VoiceService(config=cfg, availability=lambda: (True, []))


# ═══════════════════════════════════════════════════════════════════════════════
# Wake-word matching — cleaned-token match, original-word command tail
# ═══════════════════════════════════════════════════════════════════════════════

class TestMatchWake:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Osa", ""),
            ("osa.", ""),
            ("OSA!", ""),
            ("Ossa", ""),
            ("Hey Osa", ""),
            ("Hey, Osa.", ""),
            ("Okay Osa", ""),
            ("Osa, what time is it?", "what time is it?"),
            ("Hey Osa what's my memory like?", "what's my memory like?"),
            ("O S A status report", "status report"),
            # 2026-07-08 live fix: wake word anywhere in the first 3 words.
            ("Hello, Osa. Would you happen to have the time?",
             "Would you happen to have the time?"),
            ("Excuse me, Osa, lights on", "lights on"),
            ("Osaka, what's the weather?", "what's the weather?"),
        ],
    )
    def test_matches(self, text, expected):
        assert _svc()._match_wake(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "what time is it?",              # no wake word
            "the mimosa is blooming",        # substring, not a word match
            "hey there, how are you",        # no wake word at all
            "tell me more about the osa project",  # too deep — not addressed
        ],
    )
    def test_non_wake_is_discarded(self, text):
        assert _svc()._match_wake(text) is None

    def test_config_aliases_extend_the_builtins(self):
        svc = _svc(wake_aliases=["oser"])
        assert svc._match_wake("Oser, lights on") == "lights on"


# ═══════════════════════════════════════════════════════════════════════════════
# set_wake — runtime toggle semantics
# ═══════════════════════════════════════════════════════════════════════════════

class TestSetWake:
    def _idle_svc(self, monkeypatch):
        svc = _svc()
        svc.start()
        # A tame "loop": parks on the stop event instead of touching audio.
        monkeypatch.setattr(svc, "_wake_loop", lambda: svc._wake_stop.wait(5))
        return svc

    def test_on_off_lifecycle(self, monkeypatch):
        svc = self._idle_svc(monkeypatch)
        assert svc.state()["wake_active"] is False        # default OFF (§9 Q3)
        snap = svc.set_wake(True)
        assert snap["wake_active"] is True
        snap = svc.set_wake(False)
        assert snap["wake_active"] is False

    def test_enable_is_idempotent(self, monkeypatch):
        svc = self._idle_svc(monkeypatch)
        svc.set_wake(True)
        first = svc._wake_thread
        svc.set_wake(True)
        assert svc._wake_thread is first                  # same thread kept
        svc.set_wake(False)

    def test_refused_while_disabled(self):
        svc = _svc(enabled=False)                          # never start()ed
        snap = svc.set_wake(True)
        assert snap["wake_active"] is False
        assert snap["last_error"]

    def test_ptt_refused_while_wake_is_on(self, monkeypatch):
        svc = self._idle_svc(monkeypatch)
        svc.set_wake(True)
        out = svc.push_to_talk()
        assert out["ok"] is False
        assert "wake" in out["reason"]
        svc.set_wake(False)

    def test_stop_service_stops_the_loop(self, monkeypatch):
        svc = self._idle_svc(monkeypatch)
        svc.set_wake(True)
        svc.stop()
        assert svc.state()["wake_active"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# The loop itself — one pass with mocked stages
# ═══════════════════════════════════════════════════════════════════════════════

class TestWakeLoop:
    def _run_one_pass(self, svc, monkeypatch, heard: str):
        """Run the real _wake_loop for exactly one captured burst."""
        calls = {"chat": [], "spoke": []}

        def _capture():
            if calls.get("captured"):
                svc._wake_stop.set()  # second pass: exit the loop
                return b""
            calls["captured"] = True
            return b"\x00\x00" * 480

        monkeypatch.setattr(svc, "_capture_utterance", _capture)
        monkeypatch.setattr(
            svc, "_transcribe", lambda audio, size=None: heard if audio else ""
        )
        monkeypatch.setattr(
            svc, "_chat_turn", lambda text: calls["chat"].append(text) or "done"
        )
        monkeypatch.setattr(
            svc, "speak", lambda text, blocking=False: calls["spoke"].append(text) or {"ok": True}
        )
        svc._wake_stop.clear()
        svc._wake_loop()
        # Wake turns run on a worker thread (2026-07-08) — reap it so
        # assertions on calls["chat"] never race.
        t = svc._turn_thread
        if t is not None:
            t.join(timeout=2)
        return calls

    def test_inline_command_runs_a_turn(self, monkeypatch):
        svc = _svc()
        svc.start()
        calls = self._run_one_pass(svc, monkeypatch, "Osa, what time is it?")
        assert calls["chat"] == ["what time is it?"]
        assert calls["spoke"] == []                        # no ack needed
        assert svc.state()["state"] == "idle"

    def test_unaddressed_speech_is_discarded(self, monkeypatch):
        svc = _svc()
        svc.start()
        calls = self._run_one_pass(svc, monkeypatch, "just talking to myself")
        assert calls["chat"] == []
        assert calls["spoke"] == []
        assert svc.state()["state"] == "idle"

    def test_bare_wake_word_acks_then_listens(self, monkeypatch):
        svc = _svc()
        svc.start()
        calls = {"chat": [], "spoke": []}
        captures = iter([b"\x01", b"\x02"])                # wake burst, command

        def _capture():
            try:
                return next(captures)
            except StopIteration:
                svc._wake_stop.set()
                return b""

        transcripts = {b"\x01": "Osa", b"\x02": "status report"}
        monkeypatch.setattr(svc, "_capture_utterance", _capture)
        monkeypatch.setattr(
            svc, "_transcribe",
            lambda audio, size=None: transcripts.get(audio, ""),
        )
        monkeypatch.setattr(
            svc, "_chat_turn", lambda text: calls["chat"].append(text) or "done"
        )
        monkeypatch.setattr(
            svc, "speak",
            lambda text, blocking=False: calls["spoke"].append(text) or {"ok": True},
        )
        svc._wake_stop.clear()
        svc._wake_loop()
        t = svc._turn_thread
        if t is not None:
            t.join(timeout=2)
        assert calls["spoke"] == ["Yes?"]                  # the ack
        assert calls["chat"] == ["status report"]

    def test_audio_failure_lands_in_error_and_exits(self, monkeypatch):
        svc = _svc()
        svc.start()

        def _boom():
            raise RuntimeError("mic unplugged")

        monkeypatch.setattr(svc, "_capture_utterance", _boom)
        svc._wake_stop.clear()
        svc._wake_loop()                                   # returns, no raise
        snap = svc.state()
        assert snap["state"] == "error"
        assert "mic unplugged" in snap["last_error"]


# ═══════════════════════════════════════════════════════════════════════════════
# Route — POST /api/osa/voice/wake
# ═══════════════════════════════════════════════════════════════════════════════

class TestWakeRoute:
    """Routes resolve the service via ``osa_voice.get_service`` at call time —
    inject a fresh, KNOWN service per test. The real singleton must never be
    used here: in a full-suite run other tests (startup hooks) may have
    started it against the real Constitution, and set_wake(True) on it would
    open the actual microphone from inside pytest."""

    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient

        from gui.sidecar.app import app as fastapi_app

        return TestClient(fastapi_app)

    @pytest.fixture()
    def disabled_svc(self, monkeypatch):
        import osa_voice

        svc = _svc(enabled=False)
        monkeypatch.setattr(osa_voice, "get_service", lambda: svc)
        return svc

    def test_state_reports_wake_active(self, client, disabled_svc):
        body = client.get("/api/osa/voice/state").json()
        assert body["wake_active"] is False                # default OFF

    def test_enable_while_disabled_is_409(self, client, disabled_svc):
        r = client.post("/api/osa/voice/wake", json={"enabled": True})
        assert r.status_code == 409
        assert r.json()["detail"]

    def test_disable_is_always_ok(self, client, disabled_svc):
        r = client.post("/api/osa/voice/wake", json={"enabled": False})
        assert r.status_code == 200
        assert r.json()["wake_active"] is False

    def test_requires_bool_body(self, client, disabled_svc):
        assert client.post("/api/osa/voice/wake", json={}).status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# Conversation mode (2026-07-08) — follow-up window after a finished reply
# ═══════════════════════════════════════════════════════════════════════════════

class TestFollowupWindow:
    def _run_pass(self, svc, monkeypatch, heard: str):
        calls = {"chat": []}

        def _capture():
            if calls.get("captured"):
                svc._wake_stop.set()
                return b""
            calls["captured"] = True
            return b"\x00\x00" * 480

        monkeypatch.setattr(svc, "_capture_utterance", _capture)
        monkeypatch.setattr(
            svc, "_transcribe", lambda audio, size=None: heard if audio else ""
        )
        monkeypatch.setattr(
            svc, "_chat_turn", lambda text: calls["chat"].append(text) or "ok"
        )
        svc._wake_stop.clear()
        svc._wake_loop()
        t = svc._turn_thread
        if t is not None:
            t.join(timeout=2)
        return calls

    def test_wake_free_followup_inside_window(self, monkeypatch):
        svc = _svc()
        svc.start()
        svc._last_reply_done = time.monotonic()            # reply just ended
        calls = self._run_pass(svc, monkeypatch, "and what about tomorrow?")
        assert calls["chat"] == ["and what about tomorrow?"]

    def test_no_followup_after_window_expires(self, monkeypatch):
        svc = _svc(followup_window_s=1.0)
        svc.start()
        svc._last_reply_done = time.monotonic() - 5        # long expired
        calls = self._run_pass(svc, monkeypatch, "and what about tomorrow?")
        assert calls["chat"] == []                         # discarded

    def test_single_word_bursts_never_follow_up(self, monkeypatch):
        """Whisper hallucinates short phrases on noise — they must not
        become commands even inside the window."""
        svc = _svc()
        svc.start()
        svc._last_reply_done = time.monotonic()
        calls = self._run_pass(svc, monkeypatch, "Thank you.")
        assert calls["chat"] == []

    def test_no_followup_while_reply_is_playing(self, monkeypatch):
        """Echo guard: OSA's own speaker output must not become a command."""
        svc = _svc()
        svc.start()
        svc._last_reply_done = time.monotonic()

        class _FakeProc:
            def poll(self):
                return None                                # still playing

        svc._play_proc = _FakeProc()
        calls = self._run_pass(svc, monkeypatch, "and what about tomorrow?")
        assert calls["chat"] == []

    def test_disabled_window_requires_wake_word(self, monkeypatch):
        svc = _svc(followup_window_s=0)
        svc.start()
        svc._last_reply_done = time.monotonic()
        calls = self._run_pass(svc, monkeypatch, "and what about tomorrow?")
        assert calls["chat"] == []
