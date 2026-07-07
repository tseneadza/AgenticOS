"""Phase 14e tests — OSA proactive monitor: policy, buffer, routes, briefing.

Everything runs without a live poller, LLM, or MySQL: the policy engine is
pure (injectable ``now`` clock), the activity probe is monkeypatched, the ring
buffer is in-memory, and the FastAPI routes are driven with TestClient the
same way ``test_phase14a_osa.py`` does. Briefing composition patches
``launch_config.list_all_health`` + the ledger-count helper.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from core.constitution import DEFAULT_NOTIFICATIONS, Constitution
from gui.sidecar import osa_proactive as pro


DAY = datetime(2026, 7, 7, 12, 0)     # local noon — outside quiet hours
NIGHT = datetime(2026, 7, 7, 23, 30)  # local 23:30 — inside quiet hours


@pytest.fixture(autouse=True)
def _fresh_state():
    """Each test gets a cold buffer/rate-limit state and pure default policy.

    The config cache is pinned to the loader defaults so a future edit to
    Tony's live constitution.yaml can't silently change policy tests.
    """
    pro.reset_state()
    pro._config_cache = dict(DEFAULT_NOTIFICATIONS)
    yield
    pro.reset_state()


def _active(monkeypatch, value: bool):
    """Pin the live activity probe used inside should_announce."""
    monkeypatch.setattr(pro, "is_tony_active", lambda **k: value)


# ═══════════════════════════════════════════════════════════════════════════════
# Transition parsing + OSA phrasing
# ═══════════════════════════════════════════════════════════════════════════════

class TestParsingPhrasing:
    def test_parse_down(self):
        assert pro.parse_transition("worldwise:5150 down") == ("worldwise", 5150, "down")

    def test_parse_up(self):
        assert pro.parse_transition("keno:5000 up") == ("keno", 5000, "up")

    def test_parse_app_id_with_colon(self):
        # Greedy app match — only the LAST :port splits.
        assert pro.parse_transition("my:app:8080 down") == ("my:app", 8080, "down")

    @pytest.mark.parametrize("bad", [
        "", "garbage", "worldwise down", "worldwise:port down",
        "worldwise:5150 sideways", None,
    ])
    def test_parse_malformed_returns_none(self, bad):
        assert pro.parse_transition(bad) is None

    def test_phrase_down_spoken_voice(self):
        text = pro.phrase_transition("worldwise", 5150, "down")
        assert text == "Tony — worldwise just went down (port 5150)."

    def test_phrase_up_spoken_voice(self):
        assert pro.phrase_transition("worldwise", 5150, "up") == "worldwise is back up."

    def test_record_skips_malformed_entries(self):
        out = pro.record_transitions(["nonsense", "worldwise:5150 down"], now=DAY)
        assert len(out) == 1
        assert out[0]["app_id"] == "worldwise"


# ═══════════════════════════════════════════════════════════════════════════════
# Balanced policy — down + up announce; everything else silent
# ═══════════════════════════════════════════════════════════════════════════════

class TestBalancedPolicy:
    def test_down_announces(self):
        (msg,) = pro.record_transitions(["worldwise:5150 down"], now=DAY)
        assert msg["kind"] == "down"
        assert msg["announced"] is True

    def test_up_recovery_announces(self):
        (msg,) = pro.record_transitions(["worldwise:5150 up"], now=DAY)
        assert msg["kind"] == "up"
        assert msg["announced"] is True

    def test_other_kinds_are_silent(self):
        assert pro.should_announce("worldwise", "degraded", now=DAY) is False
        assert pro.should_announce("worldwise", "note", now=DAY) is False

    def test_message_shape(self):
        (msg,) = pro.record_transitions(["worldwise:5150 down"], now=DAY)
        assert set(msg) == {"id", "ts", "app_id", "kind", "text", "announced"}
        assert isinstance(msg["id"], int)
        assert "T" in msg["ts"]  # iso timestamp


# ═══════════════════════════════════════════════════════════════════════════════
# Rate limit — max 1 announced per app per window; duplicates still recorded
# ═══════════════════════════════════════════════════════════════════════════════

class TestRateLimit:
    def test_flap_is_silenced_but_recorded(self):
        first = pro.record_transitions(["worldwise:5150 down"], now=DAY)[0]
        second = pro.record_transitions(
            ["worldwise:5150 up"], now=DAY + timedelta(seconds=60))[0]
        assert first["announced"] is True
        assert second["announced"] is False           # silenced by the rate limit
        assert pro.latest_id() == 2                    # ...but still recorded

    def test_window_expiry_reannounces(self):
        pro.record_transitions(["worldwise:5150 down"], now=DAY)
        later = DAY + timedelta(seconds=DEFAULT_NOTIFICATIONS["rate_limit_seconds"] + 1)
        msg = pro.record_transitions(["worldwise:5150 up"], now=later)[0]
        assert msg["announced"] is True

    def test_per_app_isolation(self):
        pro.record_transitions(["worldwise:5150 down"], now=DAY)
        other = pro.record_transitions(
            ["keno:5000 down"], now=DAY + timedelta(seconds=5))[0]
        assert other["announced"] is True              # different app, own budget

    def test_silenced_message_does_not_consume_window(self, monkeypatch):
        # Quiet-hours-silenced first message must not eat the app's budget.
        _active(monkeypatch, False)
        silenced = pro.record_transitions(["worldwise:5150 down"], now=NIGHT)[0]
        assert silenced["announced"] is False
        _active(monkeypatch, True)
        spoken = pro.record_transitions(
            ["worldwise:5150 up"], now=NIGHT + timedelta(seconds=30))[0]
        assert spoken["announced"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Quiet hours (22:00–08:00 local) + the activity override
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuietHours:
    @pytest.mark.parametrize("hour,minute,quiet", [
        (21, 59, False), (22, 0, True), (23, 30, True),
        (3, 0, True), (7, 59, True), (8, 0, False), (12, 0, False),
    ])
    def test_overnight_window(self, hour, minute, quiet):
        now = datetime(2026, 7, 7, hour, minute)
        assert pro.in_quiet_hours(now) is quiet

    def test_non_wrapping_window(self):
        cfg = {**DEFAULT_NOTIFICATIONS,
               "quiet_hours_start": "13:00", "quiet_hours_end": "14:00"}
        assert pro.in_quiet_hours(datetime(2026, 7, 7, 13, 30), cfg) is True
        assert pro.in_quiet_hours(datetime(2026, 7, 7, 12, 30), cfg) is False

    def test_quiet_inactive_downgrades_to_silent(self, monkeypatch):
        _active(monkeypatch, False)
        (msg,) = pro.record_transitions(["worldwise:5150 down"], now=NIGHT)
        assert msg["announced"] is False               # recorded, not spoken

    def test_quiet_but_active_night_owl_announces(self, monkeypatch):
        _active(monkeypatch, True)                     # Tony's up — locked decision
        (msg,) = pro.record_transitions(["worldwise:5150 down"], now=NIGHT)
        assert msg["announced"] is True

    def test_daytime_ignores_activity(self, monkeypatch):
        def _boom(**k):
            raise AssertionError("activity probe must not run outside quiet hours")
        monkeypatch.setattr(pro, "is_tony_active", _boom)
        assert pro.should_announce("worldwise", "down", now=DAY) is True


class TestActivityProbe:
    def test_hid_idle_active(self, monkeypatch):
        monkeypatch.setattr(pro, "hid_idle_seconds", lambda: 120.0)  # 2 min idle
        assert pro.is_tony_active(now=NIGHT) is True

    def test_hid_idle_inactive(self, monkeypatch):
        monkeypatch.setattr(pro, "hid_idle_seconds", lambda: 3600.0)
        assert pro.is_tony_active(now=NIGHT) is False

    def test_hid_fails_falls_back_to_recent_chat(self, monkeypatch):
        monkeypatch.setattr(pro, "hid_idle_seconds", lambda: None)
        pro.note_chat_turn(now=NIGHT - timedelta(minutes=5))
        assert pro.is_tony_active(now=NIGHT) is True

    def test_hid_fails_stale_chat_is_inactive(self, monkeypatch):
        monkeypatch.setattr(pro, "hid_idle_seconds", lambda: None)
        pro.note_chat_turn(now=NIGHT - timedelta(hours=2))
        assert pro.is_tony_active(now=NIGHT) is False

    def test_both_unavailable_fails_open(self, monkeypatch):
        monkeypatch.setattr(pro, "hid_idle_seconds", lambda: None)
        # reset_state cleared the last-chat timestamp — no signal at all.
        assert pro.is_tony_active(now=NIGHT) is True

    def test_ioreg_output_parse(self, monkeypatch):
        class _Result:
            stdout = '| "HIDIdleTime" = 123456789000\n'
        monkeypatch.setattr(pro.subprocess, "run", lambda *a, **k: _Result())
        assert pro.hid_idle_seconds() == pytest.approx(123.456789)

    def test_ioreg_failure_returns_none(self, monkeypatch):
        def _boom(*a, **k):
            raise FileNotFoundError("no ioreg here")
        monkeypatch.setattr(pro.subprocess, "run", _boom)
        assert pro.hid_idle_seconds() is None


# ═══════════════════════════════════════════════════════════════════════════════
# Ring buffer + `after` cursor
# ═══════════════════════════════════════════════════════════════════════════════

class TestRingBuffer:
    def test_capped_at_50_with_monotonic_ids(self):
        for i in range(60):
            pro.record_transitions([f"app{i}:5000 down"], now=DAY)
        out = pro.get_messages()
        assert len(out["messages"]) == 50
        assert out["latest_id"] == 60
        ids = [m["id"] for m in out["messages"]]
        assert ids == sorted(ids)
        assert ids[0] == 11                            # oldest 10 evicted

    def test_after_cursor(self):
        for app in ("a", "b", "c"):
            pro.record_transitions([f"{app}:5000 down"], now=DAY)
        out = pro.get_messages(after=1)
        assert [m["app_id"] for m in out["messages"]] == ["b", "c"]
        assert out["latest_id"] == 3

    def test_after_latest_returns_empty(self):
        pro.record_transitions(["a:5000 down"], now=DAY)
        out = pro.get_messages(after=pro.latest_id())
        assert out["messages"] == []
        assert out["latest_id"] == 1

    def test_empty_buffer(self):
        assert pro.get_messages() == {"messages": [], "latest_id": 0}


# ═══════════════════════════════════════════════════════════════════════════════
# Routes — TestClient (14a conventions; the buffer is module state we seed)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoutes:
    def _client(self):
        from fastapi.testclient import TestClient
        from gui.sidecar.app import app as fastapi_app
        return TestClient(fastapi_app)

    def test_events_all_and_after(self):
        pro.record_transitions(
            ["worldwise:5150 down", "keno:5000 down"], now=DAY)
        c = self._client()

        body = c.get("/api/osa/events").json()
        assert body["latest_id"] == 2
        assert [m["app_id"] for m in body["messages"]] == ["worldwise", "keno"]
        assert body["messages"][0]["text"] == "Tony — worldwise just went down (port 5150)."

        newer = c.get("/api/osa/events", params={"after": 1}).json()
        assert [m["app_id"] for m in newer["messages"]] == ["keno"]

    def test_events_empty(self):
        body = self._client().get("/api/osa/events").json()
        assert body == {"messages": [], "latest_id": 0}

    def test_state_carries_latest_event_id(self, monkeypatch):
        from core import llm
        monkeypatch.setattr(llm, "ollama_up", lambda *a, **k: True)
        pro.record_transitions(["worldwise:5150 down"], now=DAY)
        body = self._client().get("/api/osa/state").json()
        assert body["ready"] is True
        assert body["latest_event_id"] == 1

    def test_chat_notes_activity(self, monkeypatch):
        """A /api/osa/chat turn must feed the activity fallback."""
        from agents import osa_agent as oa
        from core import llm, memory

        monkeypatch.setattr(oa, "warm_ollama", lambda: True)
        monkeypatch.setattr(oa, "pick_model", lambda msg, **k: "local")
        monkeypatch.setattr(llm, "resolve", lambda alias: "qwen2.5:7b-instruct")
        monkeypatch.setattr(memory, "checkpointer_conn", lambda: None)
        monkeypatch.setattr(memory, "get_checkpointer", lambda conn=None: object())

        class _FakeMsg:
            content = "Standing by."
            tool_calls = []

        class _FakeAgent:
            def invoke(self, payload, config=None):
                return {"messages": [_FakeMsg()]}

        monkeypatch.setattr(oa, "build_agent", lambda model_id, **k: _FakeAgent())

        assert pro._last_chat_ts is None
        r = self._client().post("/api/osa/chat", json={"message": "you up?"})
        assert r.status_code == 200
        assert pro._last_chat_ts is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Briefing — composition + quiet-hours interaction + scheduling helper
# ═══════════════════════════════════════════════════════════════════════════════

class TestBriefing:
    def _patch_sources(self, monkeypatch, apps: dict, projects: int | None):
        from gui.sidecar import launch_config
        monkeypatch.setattr(launch_config, "list_all_health",
                            lambda session=None: {"apps": apps, "total": len(apps)})
        monkeypatch.setattr(pro, "_project_count", lambda: projects)

    def test_all_healthy_with_projects(self, monkeypatch):
        self._patch_sources(monkeypatch, {
            "worldwise": {"healthy": True, "ports": []},
            "keno": {"healthy": True, "ports": []},
        }, projects=12)
        text = pro.compose_briefing()
        assert text == ("Morning, Tony. All 2 tracked apps are healthy. "
                        "The ledger holds 12 projects.")
        assert "\n" not in text and "*" not in text   # spoken, no markdown

    def test_unhealthy_named(self, monkeypatch):
        self._patch_sources(monkeypatch, {
            "worldwise": {"healthy": False, "ports": []},
            "keno": {"healthy": True, "ports": []},
        }, projects=3)
        text = pro.compose_briefing()
        assert "worldwise is down" in text
        assert "3 projects" in text

    def test_nothing_tracked(self, monkeypatch):
        self._patch_sources(monkeypatch, {}, projects=None)
        assert pro.compose_briefing() == \
            "Morning, Tony. Nothing's under health watch right now."

    def test_sources_degrade_gracefully(self, monkeypatch):
        from gui.sidecar import launch_config

        def _boom(session=None):
            raise RuntimeError("MySQL is napping")
        monkeypatch.setattr(launch_config, "list_all_health", _boom)
        monkeypatch.setattr(pro, "_project_count", lambda: None)
        assert pro.compose_briefing().startswith("Morning, Tony.")

    def test_post_briefing_announces_in_daytime(self, monkeypatch):
        self._patch_sources(monkeypatch, {}, projects=None)
        msg = pro.post_briefing(now=DAY)
        assert msg["kind"] == "briefing"
        assert msg["announced"] is True
        assert msg["app_id"] == "osa"
        assert pro.get_messages()["messages"] == [msg]

    def test_post_briefing_quiet_and_asleep_is_silent(self, monkeypatch):
        self._patch_sources(monkeypatch, {}, projects=None)
        _active(monkeypatch, False)
        msg = pro.post_briefing(now=NIGHT)
        assert msg["announced"] is False               # recorded silently

    def test_post_briefing_quiet_but_active_announces(self, monkeypatch):
        self._patch_sources(monkeypatch, {}, projects=None)
        _active(monkeypatch, True)
        assert pro.post_briefing(now=NIGHT)["announced"] is True

    def test_seconds_until(self):
        now = datetime(2026, 7, 7, 8, 0)
        assert pro.seconds_until("08:30", now) == 30 * 60
        # Already past today → tomorrow.
        assert pro.seconds_until("08:30", datetime(2026, 7, 7, 9, 0)) == 23.5 * 3600


# ═══════════════════════════════════════════════════════════════════════════════
# Config — the notifications block loads with defaults (old configs never break)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotificationsConfig:
    def test_absent_block_yields_defaults(self, tmp_path):
        p = tmp_path / "constitution.yaml"
        p.write_text("constitution:\n  version: '1.0'\n")
        c = Constitution.load(p)
        assert c.notifications == DEFAULT_NOTIFICATIONS

    def test_partial_block_merges_over_defaults(self, tmp_path):
        p = tmp_path / "constitution.yaml"
        p.write_text(
            "constitution:\n"
            "  version: '1.0'\n"
            "  notifications:\n"
            "    quiet_hours_start: '23:00'\n"
            "    rate_limit_seconds: 60\n"
        )
        c = Constitution.load(p)
        assert c.notifications["quiet_hours_start"] == "23:00"
        assert c.notifications["rate_limit_seconds"] == 60
        assert c.notifications["briefing_time"] == "08:30"      # default kept
        assert c.notifications["briefing_enabled"] is True

    def test_live_config_has_block(self):
        # Tony's real constitution.yaml carries the 14e block.
        c = Constitution.load()
        assert c.notifications["quiet_hours_start"] == "22:00"
        assert c.notifications["briefing_enabled"] is True

    def test_module_falls_back_when_load_explodes(self, monkeypatch):
        pro.reset_state()  # drop the pinned cache so the real loader path runs

        def _boom(cls, path=None):
            raise RuntimeError("yaml on fire")

        monkeypatch.setattr(Constitution, "load", classmethod(_boom))
        assert pro.notifications_config() == DEFAULT_NOTIFICATIONS


# ═══════════════════════════════════════════════════════════════════════════════
# Brief-me-now (14e follow-on) — force_announce + POST /api/osa/briefing
# ═══════════════════════════════════════════════════════════════════════════════

class TestBriefMeNow:
    def _client(self):
        from fastapi.testclient import TestClient
        from gui.sidecar.app import app as fastapi_app
        return TestClient(fastapi_app)

    def test_force_announce_beats_quiet_and_asleep(self, monkeypatch):
        monkeypatch.setattr(pro, "compose_briefing", lambda: "All systems nominal.")
        _active(monkeypatch, False)                    # 23:30 and idle …
        msg = pro.post_briefing(force_announce=True, now=NIGHT)
        assert msg["announced"] is True                # … but he ASKED
        assert msg["kind"] == "briefing"

    def test_force_announce_stamps_rate_limit_window(self, monkeypatch):
        monkeypatch.setattr(pro, "compose_briefing", lambda: "Nominal.")
        pro.post_briefing(force_announce=True, now=DAY)
        # A scheduled briefing straight after is rate-limited → silent.
        assert pro.post_briefing(now=DAY)["announced"] is False

    def test_route_always_announces_and_records(self, monkeypatch):
        monkeypatch.setattr(pro, "compose_briefing", lambda: "All quiet, Tony.")
        _active(monkeypatch, False)   # policy would silence — the route must not
        body = self._client().post("/api/osa/briefing").json()
        assert body["announced"] is True
        assert body["kind"] == "briefing"
        assert body["text"] == "All quiet, Tony."
        got = self._client().get("/api/osa/events").json()
        assert got["messages"][-1]["id"] == body["id"]
        assert got["latest_id"] == body["id"]

    def test_route_notes_activity(self, monkeypatch):
        monkeypatch.setattr(pro, "compose_briefing", lambda: "Nominal.")
        called = []
        monkeypatch.setattr(pro, "note_chat_turn", lambda: called.append(True))
        self._client().post("/api/osa/briefing")
        assert called == [True]
