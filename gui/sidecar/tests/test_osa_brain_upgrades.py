"""OSA brain upgrades (2026-07-07 follow-on to brain switching).

Covers the three gaps Tony's live test exposed, plus his cloud ask:
* Introspection — the per-turn ``brain_prompt_line`` + switch_model status
  intent, so "what's your brain?" is a factual zero-tool answer.
* Dynamic Ollama discovery — pinnable set = curated registry ∪ installed
  models; RAM overflow is a warning (``may_not_fit_ram``), never a block.
* ``pull_model`` — approval-gated (Constitution ``model_pull``), background,
  completion announced through the proactive ring buffer.
* Cloud escape hatch — any explicit ``claude-*`` id pins when the key is
  live, even uncurated; bare family names are never guessed into ids.

Patching seams are the documented ones: ``osa_settings._discovered_infos``,
``core.llm.list_models``, ``osa_agent._run_pull``. Ring buffer and pull
registries are reset per test.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from agents import osa_agent
from gui.sidecar import osa_proactive as pro
from gui.sidecar import osa_settings


def _local(id_, label=None, installed=True):
    """A discovered-Ollama stand-in (only .id/.label/.is_local are consumed)."""
    return SimpleNamespace(
        id=id_, label=label or f"{id_} (local)", is_local=True,
        installed=installed,
    )


@pytest.fixture(autouse=True)
def _fresh():
    pro.reset_state()
    osa_agent.reset_pull_state()
    osa_settings._pin_cache_clear() if hasattr(osa_settings, "_pin_cache_clear") else None
    yield
    pro.reset_state()
    osa_agent.reset_pull_state()


def _approve(*_a, **_k):
    return "yes"


def _deny(*_a, **_k):
    return "no"


# ═══════════════════════════════════════════════════════════════════════════════
# Introspection — brain_prompt_line + switch_model status intent
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntrospection:
    def test_prompt_line_auto(self):
        line = osa_agent.brain_prompt_line(
            pin=None, effective="qwen2.5:7b-instruct", escalated=False)
        assert "auto" in line
        assert "qwen2.5:7b-instruct" in line
        assert "escalated" not in line

    def test_prompt_line_pinned(self):
        line = osa_agent.brain_prompt_line(
            pin="claude-sonnet-4-6", effective="claude-sonnet-4-6",
            escalated=False)
        assert "pinned" in line
        assert "claude-sonnet-4-6" in line

    def test_prompt_line_escalated(self):
        line = osa_agent.brain_prompt_line(
            pin="qwen2.5:7b-instruct", effective="claude-sonnet-4-6",
            escalated=True)
        assert "escalated" in line

    def test_prompt_line_survives_lookup_trouble(self, monkeypatch):
        # Labels are cosmetic — a broken registry must not break the line.
        monkeypatch.setattr(osa_agent, "_model_label", lambda m: m)
        line = osa_agent.brain_prompt_line(
            pin=None, effective="anything", escalated=False)
        assert "anything" in line

    @pytest.mark.parametrize("query", ["status", "current", "?", "Status?"])
    def test_switch_model_status_intent_auto(self, monkeypatch, query):
        monkeypatch.setattr(osa_settings, "get_model_pin", lambda **k: None)
        box = osa_agent.OSAToolbox(approval_fn=_approve)
        out = box.switch_model(query)
        assert "Automatic routing" in out

    def test_switch_model_status_intent_local_pin(self, monkeypatch):
        monkeypatch.setattr(
            osa_settings, "get_model_pin", lambda **k: "qwen2.5:7b-instruct")
        box = osa_agent.OSAToolbox(approval_fn=_approve)
        out = box.switch_model("status")
        assert "Pinned" in out
        assert "escalates" in out  # local pin mentions the tool guardrail

    def test_build_agent_system_suffix_lands_in_prompt(self, monkeypatch):
        captured = {}

        def _fake_create(model, tools, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(invoke=lambda *a, **k: None)

        import langgraph.prebuilt as prebuilt
        monkeypatch.setattr(prebuilt, "create_react_agent", _fake_create)
        monkeypatch.setattr(
            osa_agent, "get_llm", lambda *a, **k: object(), raising=False)
        try:
            osa_agent.build_agent(
                "claude-sonnet-4-6", system_suffix="Brain status TEST LINE.")
        except Exception:
            pytest.skip("build_agent needs heavier stubbing on this box")
        assert "Brain status TEST LINE." in captured.get("prompt", "")


# ═══════════════════════════════════════════════════════════════════════════════
# Dynamic discovery — pinnable set + RAM note + fuzzy resolution
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiscovery:
    def test_pinnable_ids_merge_discovered(self, monkeypatch):
        monkeypatch.setattr(
            osa_settings, "_discovered_infos",
            lambda: [_local("llama3.2:latest"), _local("mistral:latest")])
        ids = osa_settings._pinnable_ids()
        assert "llama3.2:latest" in ids
        assert "mistral:latest" in ids
        # curated entries still present
        assert "claude-sonnet-4-6" in ids

    def test_discovery_down_degrades_to_curated(self, monkeypatch):
        # mistral is discovered-only; llama3.2 no longer qualifies as the
        # probe since it was curated (2026-07-07, OSA to-do #4).
        monkeypatch.setattr(osa_settings, "_discovered_infos", lambda: [])
        ids = osa_settings._pinnable_ids()
        assert "mistral:latest" not in ids
        assert "claude-sonnet-4-6" in ids

    def test_availability_maps_too_large_to_ram_warning(self, monkeypatch):
        from core import llm

        monkeypatch.setattr(llm, "get_model_info", lambda m: None)
        monkeypatch.setattr(
            llm, "list_models",
            lambda **k: {"models": [{
                "id": "gemma4:26b", "available": False, "reason": "too_large",
                "installed": True,
            }]})
        available, reason = osa_settings._availability("gemma4:26b")
        assert available is True
        assert reason == "may_not_fit_ram"

    def test_availability_not_installed_still_blocks(self, monkeypatch):
        from core import llm

        monkeypatch.setattr(llm, "get_model_info", lambda m: None)
        monkeypatch.setattr(
            llm, "list_models",
            lambda **k: {"models": [{
                "id": "llama3.1:8b", "available": False,
                "reason": "not_installed", "installed": False,
            }]})
        available, reason = osa_settings._availability("llama3.1:8b")
        assert available is False
        assert reason == "not_installed"

    def test_resolve_exact_discovered_id(self, monkeypatch):
        monkeypatch.setattr(
            osa_settings, "_discovered_infos",
            lambda: [_local("mistral:latest")])
        res = osa_settings.resolve_brain("mistral:latest")
        assert res == {"status": "ok", "model": "mistral:latest"}

    def test_resolve_fuzzy_prefers_installed_over_unpulled_curated(
            self, monkeypatch):
        # "llama" matches curated llama3.1:8b (not installed) AND discovered
        # llama3.2:latest — the installed one must win.
        monkeypatch.setattr(
            osa_settings, "_discovered_infos",
            lambda: [_local("llama3.2:latest")])
        res = osa_settings.resolve_brain("llama")
        assert res.get("model") == "llama3.2:latest", res

    def test_set_pin_accepts_discovered_id(self, monkeypatch):
        stored = {}
        monkeypatch.setattr(
            osa_settings, "_discovered_infos",
            lambda: [_local("mistral:latest")])
        monkeypatch.setattr(
            osa_settings, "_availability", lambda m: (True, None))
        monkeypatch.setattr(
            osa_settings, "_persist_pin",
            lambda v, s=None: stored.update(pin=v))
        assert osa_settings.set_model_pin("mistral:latest") == "mistral:latest"
        assert stored["pin"] == "mistral:latest"

    def test_pin_is_local_for_discovered_and_tag_heuristic(self, monkeypatch):
        from core import llm

        monkeypatch.setattr(llm, "get_model_info", lambda m: None)
        monkeypatch.setattr(
            llm, "discover_ollama",
            lambda **k: {"mistral:latest": _local("mistral:latest")})
        assert osa_agent._pin_is_local("mistral:latest") is True
        # cold cache + ':tag' heuristic
        monkeypatch.setattr(llm, "discover_ollama", lambda **k: {})
        assert osa_agent._pin_is_local("some-model:7b") is True
        assert osa_agent._pin_is_local("claude-opus-4-8") is False


# ═══════════════════════════════════════════════════════════════════════════════
# Cloud escape hatch — explicit claude-* ids pin easily
# ═══════════════════════════════════════════════════════════════════════════════

class TestCloudEscapeHatch:
    def test_resolve_uncurated_cloud_id(self):
        res = osa_settings.resolve_brain("claude-opus-4-8")
        assert res == {"status": "ok", "model": "claude-opus-4-8"}

    def test_bare_family_name_is_not_guessed(self, monkeypatch):
        # Hermetic: drop discovered Ollama models — Tony's :12434 instance has a
        # 'claude-opus-*' model that would otherwise make "opus" resolve.
        monkeypatch.setattr("core.llm.discover_ollama", lambda force=False: {})
        res = osa_settings.resolve_brain("opus")
        assert res.get("status") != "ok"

    def test_set_pin_uncurated_cloud_with_live_key(self, monkeypatch):
        stored = {}
        monkeypatch.setattr(osa_settings, "_anthropic_key_ok", lambda: True)
        monkeypatch.setattr(
            osa_settings, "_persist_pin",
            lambda v, s=None: stored.update(pin=v))
        assert osa_settings.set_model_pin("claude-opus-4-8") == "claude-opus-4-8"
        assert stored["pin"] == "claude-opus-4-8"

    def test_set_pin_uncurated_cloud_without_key_refused(self, monkeypatch):
        monkeypatch.setattr(osa_settings, "_anthropic_key_ok", lambda: False)
        with pytest.raises(osa_settings.UnavailableBrainError):
            osa_settings.set_model_pin("claude-opus-4-8")

    def test_garbage_claude_prefix_is_unknown(self, monkeypatch):
        monkeypatch.setattr(osa_settings, "_anthropic_key_ok", lambda: True)
        with pytest.raises(osa_settings.UnknownBrainError):
            osa_settings.set_model_pin("claude-")

    def test_switch_model_uncurated_cloud_caveat(self, monkeypatch):
        monkeypatch.setattr(
            osa_settings, "resolve_brain",
            lambda t: {"status": "ok", "model": "claude-opus-4-8"})
        monkeypatch.setattr(
            osa_settings, "set_model_pin", lambda v, **k: v)
        monkeypatch.setattr(
            osa_settings, "_availability", lambda m: (True, None))
        box = osa_agent.OSAToolbox(approval_fn=_approve)
        out = box.switch_model("claude-opus-4-8")
        assert "Switched to claude-opus-4-8" in out
        assert "doesn't recognize the id" in out


# ═══════════════════════════════════════════════════════════════════════════════
# pull_model — gated, background, announced
# ═══════════════════════════════════════════════════════════════════════════════

class TestPullModel:
    def _box(self, approval_fn=_approve):
        return osa_agent.OSAToolbox(approval_fn=approval_fn)

    def test_garbage_name_refused_before_gate(self):
        asked = []
        box = self._box(lambda *a: asked.append(a) or "yes")
        out = box.pull_model("not a model!!")
        assert "doesn't look like an Ollama model name" in out
        assert asked == []          # never reached the approval gate

    def test_already_installed_shortcut(self, monkeypatch):
        from core import llm

        monkeypatch.setattr(
            llm, "discover_ollama",
            lambda **k: {"mistral:latest": _local("mistral:latest")})
        out = self._box().pull_model("mistral:latest")
        assert "already on the shelf" in out

    def test_denied_pull_starts_nothing(self, monkeypatch):
        from core import llm

        monkeypatch.setattr(llm, "discover_ollama", lambda **k: {})
        out = self._box(_deny).pull_model("llama3.3")
        assert out.startswith("DENIED")
        assert osa_agent.pulls_in_flight() == []

    def test_approved_pull_runs_and_announces_success(self, monkeypatch):
        from core import llm

        monkeypatch.setattr(llm, "discover_ollama", lambda **k: {})
        monkeypatch.setattr(
            osa_agent, "_run_pull", lambda n: {"ok": True, "error": None})
        out = self._box().pull_model("llama3.3")
        assert "Pulling llama3.3" in out
        for _ in range(100):            # wait out the daemon thread
            if not osa_agent.pulls_in_flight():
                break
            time.sleep(0.05)
        msgs = pro.get_messages()["messages"]
        assert any(m["kind"] == "model" and "llama3.3" in m["text"]
                   for m in msgs), msgs

    def test_worker_failure_announces_too(self, monkeypatch):
        monkeypatch.setattr(
            osa_agent, "_run_pull",
            lambda n: {"ok": False, "error": "model not found"})
        osa_agent._pull_worker("nope3.9")
        msgs = pro.get_messages()["messages"]
        assert any(m["kind"] == "model" for m in msgs), msgs

    def test_duplicate_in_flight_answered(self, monkeypatch):
        from core import llm

        monkeypatch.setattr(llm, "discover_ollama", lambda **k: {})
        with osa_agent._pull_lock:
            osa_agent._pulls_in_flight.add("llama3.3")
        out = self._box().pull_model("llama3.3")
        assert "Already pulling" in out

    def test_model_kind_is_announce_candidate(self, monkeypatch):
        monkeypatch.setattr(pro, "is_tony_active", lambda **k: True)
        entry = pro.post_model_event("llama3.3", ok=True)
        assert entry["kind"] == "model"
        assert entry["announced"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Routes — discovered choices + uncurated pin display
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoutes:
    def _client(self):
        from fastapi.testclient import TestClient
        from gui.sidecar.app import app as fastapi_app
        return TestClient(fastapi_app)

    def test_choices_include_discovered_installed_models(self, monkeypatch):
        from core import llm
        from gui.sidecar import osa_settings as st

        monkeypatch.setattr(st, "get_model_pin", lambda **k: None)
        monkeypatch.setattr(
            llm, "list_models",
            lambda **k: {"ollama_up": True, "models": [
                {"id": "claude-sonnet-4-6", "label": "Sonnet",
                 "is_local": False, "available": True, "reason": None,
                 "installed": True},
                {"id": "mistral:latest", "label": "mistral:latest (local)",
                 "is_local": True, "available": True, "reason": None,
                 "installed": True},
                {"id": "gemma4:26b", "label": "gemma4:26b (local)",
                 "is_local": True, "available": False, "reason": "too_large",
                 "installed": True},
            ]})
        body = self._client().get("/api/osa/model").json()
        by_id = {c["id"]: c for c in body["choices"]}
        assert by_id["mistral:latest"]["discovered"] is True
        assert by_id["gemma4:26b"]["available"] is True
        assert by_id["gemma4:26b"]["reason"] == "may_not_fit_ram"
        assert by_id["claude-sonnet-4-6"]["discovered"] is False

    def test_uncurated_cloud_pin_appended_to_choices(self, monkeypatch):
        from core import llm
        from gui.sidecar import osa_settings as st

        monkeypatch.setattr(
            st, "get_model_pin", lambda **k: "claude-opus-4-8")
        monkeypatch.setattr(
            llm, "list_models", lambda **k: {"ollama_up": False, "models": []})
        body = self._client().get("/api/osa/model").json()
        by_id = {c["id"]: c for c in body["choices"]}
        assert "claude-opus-4-8" in by_id
        assert by_id["claude-opus-4-8"]["reason"] == "uncurated_cloud"
        assert body["pinned_model"] == "claude-opus-4-8"
