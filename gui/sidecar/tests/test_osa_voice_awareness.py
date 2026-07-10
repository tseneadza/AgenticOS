"""OSA voice-awareness (2026-07-09) — the persona knows it has ears + a voice.

Found live 2026-07-08: OSA told Tony "I'm text-only, no microphone" mid
voice-chat. Fix: when the Constitution's voice block is enabled, both chat
routes build the agent with ``voice_aware=True``, which inserts
``VOICE_AWARENESS_LINE`` into the system prompt — BEFORE the brain-status
suffix so the never-repeat brain line stays the prompt tail (small local
models echo trailing text).

Headless: the prompt is inspected by patching create_react_agent so no
LLM/graph is constructed for real.
"""

from __future__ import annotations

import inspect

from agents import osa_agent


def _capture_prompt(monkeypatch, **build_kwargs) -> str:
    """Build the agent with a stubbed graph constructor; return the prompt."""
    captured = {}

    def _fake_create_react_agent(model, tools, **kwargs):
        captured["prompt"] = kwargs.get("prompt", "")
        return object()

    import langgraph.prebuilt as prebuilt

    monkeypatch.setattr(prebuilt, "create_react_agent", _fake_create_react_agent)
    # No real model either — get_chat_model may hit provider adapters.
    from core import llm

    monkeypatch.setattr(llm, "get_chat_model", lambda mid=None: object())
    osa_agent.build_agent("claude-sonnet-4-6", **build_kwargs)
    return captured["prompt"]


class TestVoiceAwarenessLine:
    def test_line_present_when_voice_aware(self, monkeypatch):
        prompt = _capture_prompt(monkeypatch, voice_aware=True)
        assert osa_agent.VOICE_AWARENESS_LINE in prompt

    def test_line_absent_by_default(self, monkeypatch):
        prompt = _capture_prompt(monkeypatch)
        assert osa_agent.VOICE_AWARENESS_LINE not in prompt
        assert "text-only" not in prompt  # and nothing claims the opposite

    def test_brain_line_stays_the_tail(self, monkeypatch):
        # The brain suffix must remain LAST (its never-repeat marker guards the
        # echo-prone tail); the voice line sits before it.
        brain = osa_agent.brain_prompt_line(
            pin=None, effective="claude-sonnet-4-6", escalated=False
        )
        prompt = _capture_prompt(
            monkeypatch, voice_aware=True, system_suffix=brain
        )
        assert prompt.index(osa_agent.VOICE_AWARENESS_LINE) < prompt.index(brain)
        assert prompt.rstrip().endswith(brain)

    def test_line_says_not_text_only(self):
        # The line's whole job: forbid the "text-only / no microphone" claim.
        line = osa_agent.VOICE_AWARENESS_LINE
        assert "NOT text-only" in line
        assert "microphone" in line
        assert "spoken aloud" in line


class TestVoiceIsOn:
    def test_true_when_enabled(self, monkeypatch):
        from gui.sidecar.routes import api_osa
        from osa_voice import config as vcfg

        monkeypatch.setattr(vcfg, "voice_config", lambda: {"enabled": True})
        assert api_osa._voice_is_on() is True

    def test_false_when_disabled(self, monkeypatch):
        from gui.sidecar.routes import api_osa
        from osa_voice import config as vcfg

        monkeypatch.setattr(vcfg, "voice_config", lambda: {"enabled": False})
        assert api_osa._voice_is_on() is False

    def test_false_when_config_unreadable(self, monkeypatch):
        from gui.sidecar.routes import api_osa
        from osa_voice import config as vcfg

        def _boom():
            raise RuntimeError("config down")

        monkeypatch.setattr(vcfg, "voice_config", _boom)
        assert api_osa._voice_is_on() is False  # never raises, never claims ears


class TestDualPathWiring:
    def test_both_chat_routes_pass_voice_aware(self):
        # Dual-path rule (skills/osa-chat-dual-path): the WS route is the
        # app's PRIMARY chat path, the POST route the fallback + voice's own
        # path — BOTH must build the agent voice-aware. Source-level guard,
        # same pattern as TestWsPathHasVoiceHook in test_osa_voice_out.py.
        from gui.sidecar.routes import api_osa

        post_src = inspect.getsource(api_osa.osa_chat)
        ws_src = inspect.getsource(api_osa.osa_chat_ws)
        assert "voice_aware=_voice_is_on()" in post_src
        assert "voice_aware=_voice_is_on()" in ws_src
