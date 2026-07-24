"""OSA brain switching tests (2026-07-07) — pin store, routing, tool, routes.

Tony can pin OSA's brain ("switch to Sonnet", "use your local brain") over the
automatic per-turn router; "back to auto" clears it. Covered here:

  * pin store — MySQL ``osa_settings`` CRUD + persistence (``agenticos_test``
    via the shared conftest fixtures), the read-once in-process cache, and the
    DB-down degrade (auto + in-memory writes, never raises)
  * validation — unknown ids rejected listing valid brains; unavailable models
    refused with the ``list_models`` reason (never pin a dead brain)
  * resolve_brain — fuzzy spoken names → registry ids ("sonnet", "local",
    "fast", full ids), auto phrases, ambiguous ("claude") and unknown
  * pick_model matrix — auto / local-pin / cloud-pin × chit-chat / tool-turn /
    Ollama-down (the tool guardrail: a local pin never gets tool turns)
  * switch_model tool — fuzzy resolution, persona confirmations, unknown /
    ambiguous / unavailable replies, guarded-plumbing events
  * routes — GET/POST /api/osa/model (valid, auto, 422 unknown, 409
    unavailable), the pin surfacing in /api/osa/state, and the chat route
    honoring the pin + appending the escalation clause

Nothing here touches the live ``agenticos`` schema: DB tests inject the
``agenticos_test`` session (house pattern, mirrors test_phase13a); everything
else runs with SessionLocal patched to fail so pins stay in-memory.
"""
from __future__ import annotations

import pytest

from agents import osa_agent
from core.constitution import Constitution
from gui.sidecar import osa_settings

SONNET = "claude-sonnet-4-6"
HAIKU = "claude-haiku-4-5-20251001"
QWEN = "qwen2.5:7b-instruct"
LLAMA = "llama3.1:8b"


@pytest.fixture(autouse=True)
def _fresh_pin_cache():
    """Every test starts and ends with a cold pin cache — no cross-test leaks."""
    osa_settings.reset_pin_cache()
    yield
    osa_settings.reset_pin_cache()


@pytest.fixture()
def db_offline(monkeypatch):
    """Make the default session factory fail — pins go in-memory only.

    Keeps route/tool tests off the live ``agenticos`` schema AND exercises the
    degrade path in one move.
    """
    def _boom(*a, **k):
        raise RuntimeError("MySQL offline (test)")

    monkeypatch.setattr("gui.sidecar.db.SessionLocal", _boom)


@pytest.fixture()
def all_available(monkeypatch):
    """Every registry model reports available — validation always passes."""
    monkeypatch.setattr(osa_settings, "_availability", lambda mid: (True, None))


def _permissive_constitution() -> Constitution:
    """A constitution that blocks nothing and requires no approval."""
    return Constitution(approval_required={}, limits={}, blocked=[], write_allowlist=[])


def _fake_listing(available_ids=(), reasons=None, ollama_up=True) -> dict:
    """A deterministic ``llm.list_models`` payload over the real registry."""
    from core import llm

    reasons = reasons or {}
    rows = [
        {
            "id": m.id,
            "provider": m.provider,
            "label": m.label,
            "context_window": m.context_window,
            "supports_tools": m.supports_tools,
            "cost_per_mtok": m.cost_per_mtok,
            "is_local": m.is_local,
            "installed": True,
            "available": m.id in available_ids,
            "size_bytes": 0,
            "ram_required_bytes": 0,
            "fits": True,
            "reason": reasons.get(m.id),
        }
        for m in llm.registry()
    ]
    return {"active": SONNET, "ollama_up": ollama_up,
            "ram_total_bytes": 0, "models": rows}


# ═══════════════════════════════════════════════════════════════════════════════
# Pin store — MySQL osa_settings CRUD, cache, DB-down degrade
# ═══════════════════════════════════════════════════════════════════════════════

class TestPinStore:
    def test_osa_settings_table_exists(self, mysql_engine):
        from sqlalchemy import inspect

        assert "osa_settings" in inspect(mysql_engine).get_table_names()

    def test_set_get_roundtrip_persists(self, db_session, all_available):
        assert osa_settings.set_model_pin(SONNET, session=db_session) == SONNET
        # A fresh process (cold cache) reads the pin back from the DB row.
        osa_settings.reset_pin_cache()
        assert osa_settings.get_model_pin(session=db_session) == SONNET

    def test_update_overwrites_single_row(self, db_session, all_available):
        from gui.sidecar.models import OsaSetting

        osa_settings.set_model_pin(SONNET, session=db_session)
        osa_settings.set_model_pin(HAIKU, session=db_session)
        rows = db_session.query(OsaSetting).filter_by(key=osa_settings.PIN_KEY).all()
        assert len(rows) == 1
        assert rows[0].value == HAIKU

    def test_clear_with_auto_and_none(self, db_session, all_available):
        osa_settings.set_model_pin(SONNET, session=db_session)
        assert osa_settings.set_model_pin("auto", session=db_session) is None
        osa_settings.reset_pin_cache()
        assert osa_settings.get_model_pin(session=db_session) is None
        # None clears too (row stays, value NULL).
        osa_settings.set_model_pin(SONNET, session=db_session)
        assert osa_settings.set_model_pin(None, session=db_session) is None

    def test_reads_are_cached_after_first_hit(self, db_session, all_available, monkeypatch):
        osa_settings.set_model_pin(QWEN, session=db_session)
        osa_settings.reset_pin_cache()
        assert osa_settings.get_model_pin(session=db_session) == QWEN

        # Kill the session factory: a cached read must not touch the DB.
        def _boom(*a, **k):
            raise AssertionError("per-turn pin read hit the DB")

        monkeypatch.setattr(osa_settings, "_session_scope", _boom)
        assert osa_settings.get_model_pin() == QWEN

    def test_db_down_set_and_get_work_in_memory(self, db_offline, all_available):
        assert osa_settings.set_model_pin(SONNET) == SONNET
        assert osa_settings.get_model_pin() == SONNET  # in-memory write-through

    def test_db_down_fresh_read_degrades_to_auto(self, db_offline):
        # Cold cache + unreachable DB ⇒ auto, never an exception.
        assert osa_settings.get_model_pin() is None


# ═══════════════════════════════════════════════════════════════════════════════
# Validation — unknown listed, unavailable refused with reason
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidation:
    def test_unknown_id_rejected_listing_valid_brains(self, db_offline):
        with pytest.raises(osa_settings.UnknownBrainError) as exc:
            osa_settings.set_model_pin("gpt-9-mega")
        msg = str(exc.value)
        assert "auto" in msg and SONNET in msg and QWEN in msg
        assert osa_settings.get_model_pin() is None  # nothing was pinned

    def test_unavailable_model_refused_with_reason(self, db_offline, monkeypatch):
        monkeypatch.setattr(
            osa_settings, "_availability", lambda mid: (False, "no_api_key")
        )
        with pytest.raises(osa_settings.UnavailableBrainError) as exc:
            osa_settings.set_model_pin(SONNET)
        assert "no_api_key" in str(exc.value)
        assert osa_settings.get_model_pin() is None

    def test_availability_reads_list_models(self, monkeypatch):
        from core import llm

        monkeypatch.setattr(
            llm, "list_models",
            lambda **k: _fake_listing(available_ids=(SONNET,),
                                      reasons={QWEN: "ollama_off"}),
        )
        assert osa_settings._availability(SONNET) == (True, None)
        assert osa_settings._availability(QWEN) == (False, "ollama_off")


# ═══════════════════════════════════════════════════════════════════════════════
# resolve_brain — fuzzy spoken names → registry ids
# ═══════════════════════════════════════════════════════════════════════════════

class TestResolveBrain:
    @pytest.fixture(autouse=True)
    def _no_discovery(self, monkeypatch):
        """Pin discovery to empty — these tests define CURATED-only semantics.

        Discovery (2026-07-07) widened resolve_brain's candidates to whatever
        Ollama has pulled on the host, which made these assertions depend on
        Tony's live machine ("qwen" became ambiguous next to qwen2.5-coder).
        Discovery-aware resolution is covered in test_osa_brain_upgrades.py.
        """
        monkeypatch.setattr(osa_settings, "_discovered_infos", lambda: [])
    @pytest.mark.parametrize("text,expected", [
        ("sonnet", SONNET),
        ("switch to Sonnet", SONNET),
        ("haiku", HAIKU),
        ("qwen", QWEN),
        ("local", QWEN),                   # workflow alias
        ("use your local brain", QWEN),
        ("fast", HAIKU),                   # workflow alias
        # "llama" alone went ambiguous when llama3.2:latest was curated
        # (2026-07-07, OSA to-do #4) — the version-qualified ask is exact.
        ("llama3.1", LLAMA),
        (SONNET, SONNET),                  # exact registry id
    ])
    def test_resolves_to_id(self, text, expected):
        assert osa_settings.resolve_brain(text) == {"status": "ok", "model": expected}

    @pytest.mark.parametrize("text", ["auto", "automatic", "back to auto", "AUTO"])
    def test_auto_phrases(self, text):
        assert osa_settings.resolve_brain(text) == {"status": "auto"}

    @pytest.mark.parametrize("text", ["claude", "cloud"])
    def test_ambiguous_asks_back(self, text):
        res = osa_settings.resolve_brain(text)
        assert res["status"] == "ambiguous"
        assert set(res["matches"]) >= {SONNET, HAIKU}

    @pytest.mark.parametrize("text", ["banana", "gpt-5", ""])
    def test_unknown_lists_valid(self, text):
        res = osa_settings.resolve_brain(text)
        assert res["status"] == "unknown"
        assert SONNET in res["valid"] and QWEN in res["valid"]

    def test_spoken_default_is_not_a_silent_sonnet_pin(self):
        # "default" aliases Sonnet for workflows, but spoken it must NOT pin.
        assert osa_settings.resolve_brain("default")["status"] == "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# pick_model matrix — auto / local-pin / cloud-pin × chit-chat / tool / down
# ═══════════════════════════════════════════════════════════════════════════════

class TestPickModelMatrix:
    # auto (no pin): menial system tasks → local; web/heavy → cloud (2026-07-23).
    def test_auto_routes_menial_local_web_cloud(self):
        assert osa_agent.pick_model("hey", ollama_ready=True, pin=None) == "local"
        assert osa_agent.pick_model("hey", ollama_ready=False, pin=None) == "default"
        # menial system task → LOCAL now (curated toolset, works offline)
        assert osa_agent.pick_model("launch worldwise", ollama_ready=True, pin=None) == "local"
        # web/heavy → cloud
        assert osa_agent.pick_model("search the web for X", ollama_ready=True, pin=None) == "default"
        # menial but Ollama down → cloud fallback (never hard-fail)
        assert osa_agent.pick_model("launch worldwise", ollama_ready=False, pin=None) == "default"

    # cloud pin: EVERY turn goes to the pinned model.
    @pytest.mark.parametrize("msg,ready", [
        ("hey", True), ("hey", False), ("launch worldwise", True),
        ("launch worldwise", False),
    ])
    def test_cloud_pin_takes_every_turn(self, msg, ready):
        assert osa_agent.pick_model(msg, ollama_ready=ready, pin=SONNET) == SONNET

    # local pin: conversational AND menial system turns local; web/heavy escalate.
    def test_local_pin_takes_chitchat(self):
        assert osa_agent.pick_model("hey", ollama_ready=True, pin=QWEN) == QWEN

    def test_local_pin_menial_stays_local(self):
        assert osa_agent.pick_model("launch worldwise", ollama_ready=True, pin=QWEN) == QWEN
        assert osa_agent.pick_model("how's my memory?", ollama_ready=True, pin=QWEN) == QWEN

    def test_local_pin_web_heavy_escalates(self):
        assert osa_agent.pick_model("search the web for news", ollama_ready=True, pin=QWEN) == "default"
        assert osa_agent.pick_model("explain why this keeps happening", ollama_ready=True, pin=QWEN) == "default"

    def test_local_pin_ollama_down_falls_back(self):
        assert osa_agent.pick_model("hey", ollama_ready=False, pin=QWEN) == "default"

    def test_pin_is_local_metadata(self):
        assert osa_agent._pin_is_local(QWEN) is True
        assert osa_agent._pin_is_local(SONNET) is False


# ═══════════════════════════════════════════════════════════════════════════════
# switch_model tool — fuzzy, persona confirmations, guarded plumbing
# ═══════════════════════════════════════════════════════════════════════════════

class TestSwitchModelTool:
    def _toolbox(self, event_fn=None):
        kwargs = {"constitution": _permissive_constitution()}
        if event_fn is not None:
            kwargs["event_fn"] = event_fn
        return osa_agent.OSAToolbox(**kwargs)

    def test_switch_to_sonnet_pins_and_confirms(self, db_offline, all_available):
        reply = self._toolbox().switch_model("sonnet")
        assert "Claude Sonnet 4.6" in reply
        assert osa_settings.get_model_pin() == SONNET

    def test_switch_to_local_mentions_tool_guardrail(self, db_offline, all_available):
        reply = self._toolbox().switch_model("use your local brain")
        assert osa_settings.get_model_pin() == QWEN
        assert "Claude" in reply  # says tool work still escalates

    def test_back_to_auto_clears(self, db_offline, all_available):
        box = self._toolbox()
        box.switch_model("haiku")
        assert osa_settings.get_model_pin() == HAIKU
        reply = box.switch_model("back to auto")
        assert osa_settings.get_model_pin() is None
        assert "automatic" in reply.lower()

    def test_ambiguous_asks_back_without_pinning(self, db_offline, all_available):
        reply = self._toolbox().switch_model("claude")
        assert SONNET in reply and HAIKU in reply
        assert osa_settings.get_model_pin() is None

    def test_unknown_lists_the_shelf(self, db_offline):
        reply = self._toolbox().switch_model("banana")
        assert "auto" in reply and SONNET in reply
        assert osa_settings.get_model_pin() is None

    def test_unavailable_refused_with_reason(self, db_offline, monkeypatch):
        monkeypatch.setattr(
            osa_settings, "_availability", lambda mid: (False, "not_installed")
        )
        # Unambiguous id (registry-backed) so resolution reaches the availability
        # check — a bare "llama" is now ambiguous across the :12434 model set.
        reply = self._toolbox().switch_model("llama3.1:8b")
        assert "not_installed" in reply
        assert osa_settings.get_model_pin() is None

    def test_goes_through_guarded_plumbing(self, db_offline, all_available):
        events = []
        box = self._toolbox(event_fn=lambda phase, tool, info: events.append((phase, tool)))
        box.switch_model("sonnet")
        assert ("start", "switch_model") in events
        assert ("end", "switch_model") in events

    def test_registered_as_agent_tool(self):
        names = {t.name for t in osa_agent.build_tools(self._toolbox())}
        assert "switch_model" in names
        # And the system prompt maps the spoken ask to it.
        assert "switch_model" in osa_agent.OSA_SYSTEM


# ═══════════════════════════════════════════════════════════════════════════════
# Routes — GET/POST /api/osa/model, state field, pin-aware chat
# ═══════════════════════════════════════════════════════════════════════════════

def _client():
    from fastapi.testclient import TestClient
    from gui.sidecar.app import app as fastapi_app

    return TestClient(fastapi_app)


class TestModelRoutes:
    def test_get_shape(self, db_offline, monkeypatch):
        from core import llm

        monkeypatch.setattr(
            llm, "list_models",
            lambda **k: _fake_listing(available_ids=(SONNET, HAIKU),
                                      reasons={QWEN: "ollama_off", LLAMA: "ollama_off"}),
        )
        body = _client().get("/api/osa/model").json()
        assert body["pinned_model"] is None
        assert body["mode"] == "auto"
        ids = {c["id"] for c in body["choices"]}
        assert {SONNET, HAIKU, QWEN, LLAMA} <= ids
        qwen = next(c for c in body["choices"] if c["id"] == QWEN)
        assert qwen["available"] is False and qwen["reason"] == "ollama_off"

    def test_post_valid_pins(self, db_offline, all_available, monkeypatch):
        from core import llm

        monkeypatch.setattr(
            llm, "list_models", lambda **k: _fake_listing(available_ids=(SONNET,))
        )
        r = _client().post("/api/osa/model", json={"model": SONNET})
        assert r.status_code == 200
        assert r.json()["pinned_model"] == SONNET
        assert r.json()["mode"] == "pinned"
        # GET reflects the change.
        assert _client().get("/api/osa/model").json()["pinned_model"] == SONNET

    def test_post_auto_clears(self, db_offline, all_available, monkeypatch):
        from core import llm

        monkeypatch.setattr(llm, "list_models", lambda **k: _fake_listing())
        osa_settings.set_model_pin(SONNET)
        r = _client().post("/api/osa/model", json={"model": "auto"})
        assert r.status_code == 200
        assert r.json()["pinned_model"] is None
        assert r.json()["mode"] == "auto"

    def test_post_unknown_is_422(self, db_offline):
        r = _client().post("/api/osa/model", json={"model": "gpt-9-mega"})
        assert r.status_code == 422
        assert SONNET in r.json()["detail"]

    def test_post_unavailable_is_409_with_reason(self, db_offline, monkeypatch):
        monkeypatch.setattr(
            osa_settings, "_availability", lambda mid: (False, "no_api_key")
        )
        r = _client().post("/api/osa/model", json={"model": SONNET})
        assert r.status_code == 409
        assert "no_api_key" in r.json()["detail"]

    def test_state_carries_pinned_model(self, db_offline, all_available, monkeypatch):
        from core import llm

        monkeypatch.setattr(llm, "ollama_up", lambda *a, **k: True)
        assert _client().get("/api/osa/state").json()["pinned_model"] is None
        osa_settings.set_model_pin(QWEN)
        assert _client().get("/api/osa/state").json()["pinned_model"] == QWEN


class _FakeMsg:
    def __init__(self, content):
        self.content = content
        self.tool_calls = []


class _FakeAgent:
    def __init__(self, reply):
        self.reply = reply

    def invoke(self, payload, config=None):
        return {"messages": [_FakeMsg(self.reply)]}


class TestChatHonorsPin:
    """POST /api/osa/chat with the real pick_model/resolve, fake agent + DB."""

    def _patch_graph(self, monkeypatch, reply="Understood, Sir.", warm=True):
        from agents import osa_agent as oa
        from core import memory

        built = {}
        monkeypatch.setattr(oa, "warm_ollama", lambda: warm)
        monkeypatch.setattr(memory, "checkpointer_conn", lambda: None)
        monkeypatch.setattr(memory, "get_checkpointer", lambda conn=None: object())

        def _fake_build(model_id, **k):
            built["model"] = model_id
            return _FakeAgent(reply)

        monkeypatch.setattr(oa, "build_agent", _fake_build)
        return built

    def test_cloud_pin_takes_chitchat(self, db_offline, all_available, monkeypatch):
        built = self._patch_graph(monkeypatch)
        osa_settings.set_model_pin(SONNET)
        d = _client().post("/api/osa/chat", json={"message": "hey"}).json()
        assert built["model"] == SONNET
        assert d["model"] == SONNET
        assert d["route"] == "default"      # cloud badge
        assert d["pinned_model"] == SONNET
        assert d["escalated"] is False
        assert "Took Claude" not in d["reply"]

    def test_local_pin_takes_chitchat(self, db_offline, all_available, monkeypatch):
        built = self._patch_graph(monkeypatch, warm=True)
        osa_settings.set_model_pin(QWEN)
        d = _client().post("/api/osa/chat", json={"message": "hey"}).json()
        assert built["model"] == QWEN
        assert d["route"] == "local"        # local badge keeps working
        assert d["escalated"] is False

    def test_local_pin_tool_turn_escalates_with_mention(
        self, db_offline, all_available, monkeypatch
    ):
        built = self._patch_graph(monkeypatch, reply="Worldwise is up.")
        osa_settings.set_model_pin(QWEN)
        # A web/heavy turn escalates a local pin to Claude (menial turns now stay
        # local — see TestPickModelMatrix).
        d = _client().post(
            "/api/osa/chat", json={"message": "explain why worldwise keeps crashing"}
        ).json()
        assert built["model"] == SONNET     # resolve("default") → Sonnet
        assert d["route"] == "default"
        assert d["escalated"] is True
        assert d["reply"].endswith("Took Claude for that one.")

    def test_local_pin_ollama_down_escalates(self, db_offline, all_available, monkeypatch):
        built = self._patch_graph(monkeypatch, warm=False)
        osa_settings.set_model_pin(QWEN)
        d = _client().post("/api/osa/chat", json={"message": "hey"}).json()
        assert built["model"] == SONNET
        assert d["escalated"] is True

    def test_no_double_claude_mention(self, db_offline, all_available, monkeypatch):
        self._patch_graph(monkeypatch, reply="Took Claude for the heavy lifting.")
        osa_settings.set_model_pin(QWEN)
        d = _client().post(
            "/api/osa/chat", json={"message": "explain why worldwise keeps crashing"}
        ).json()
        assert d["escalated"] is True
        assert d["reply"].count("Claude") == 1

    def test_no_pin_keeps_auto_router(self, db_offline, monkeypatch):
        built = self._patch_graph(monkeypatch, warm=True)
        d = _client().post("/api/osa/chat", json={"message": "hey"}).json()
        assert built["model"] == QWEN       # resolve("local") → Qwen
        assert d["pinned_model"] is None
        assert d["escalated"] is False
