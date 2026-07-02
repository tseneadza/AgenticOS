"""Phase 12 — Self-Diagnostics backend tests.

Covers the pure parsers, the system-check summary roll-up, the live
``run_system_checks`` shape (degrades gracefully with no MySQL), and the two
REST endpoints via FastAPI's TestClient. No live MySQL and no test-suite
execution are required — the WS ``/ws/run`` subprocess flow is intentionally
not exercised here (it shells out to pytest/vitest).
"""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gui.sidecar.routes import api_diagnostics as d


# ── parsers ────────────────────────────────────────────────────────────────────

def test_parse_pytest_all_passed():
    assert d._parse_pytest(["=== 48 passed in 1.20s ==="]) == {
        "passed": 48, "failed": 0, "total": 48
    }


def test_parse_pytest_with_failures_and_errors():
    out = d._parse_pytest(["1 failed, 2 error, 47 passed in 2s"])
    assert out["passed"] == 47
    assert out["failed"] == 3  # failed + error folded together
    assert out["total"] == 50


def test_parse_vitest_mixed():
    assert d._parse_vitest(["Tests  188 failed | 308 passed (496)"]) == {
        "passed": 308, "failed": 188, "total": 496
    }


def test_parse_vitest_all_passed():
    assert d._parse_vitest(["Tests  569 passed (569)"]) == {
        "passed": 569, "failed": 0, "total": 569
    }


def test_parse_handles_no_summary_line():
    assert d._parse_pytest(["random noise"]) == {"passed": 0, "failed": 0, "total": 0}
    assert d._parse_vitest(["random noise"])["total"] == 0


# ── summary roll-up ────────────────────────────────────────────────────────────

def test_summary_overall_fail_dominates():
    checks = [
        {"status": "ok"}, {"status": "warn"}, {"status": "fail"},
    ]
    s = d._system_summary(checks)
    assert s == {"ok": 1, "warn": 1, "fail": 1, "overall": "fail"}


def test_summary_overall_warn_when_no_fail():
    s = d._system_summary([{"status": "ok"}, {"status": "warn"}])
    assert s["overall"] == "warn"


def test_summary_overall_ok_when_all_ok():
    s = d._system_summary([{"status": "ok"}, {"status": "ok"}])
    assert s["overall"] == "ok"


# ── live system checks (must never raise, even with no MySQL) ───────────────────

def test_run_system_checks_shape():
    checks = d.run_system_checks()
    ids = {c["id"] for c in checks}
    # The core self-checks are always present.
    assert {"sidecar", "mysql", "models", "constitution", "workflows"} <= ids
    for c in checks:
        assert c["status"] in {"ok", "warn", "fail"}
        assert c["label"] and c["detail"]


def test_constitution_check_enforces():
    # The Constitution ships with blocked patterns, so the guard check must pass.
    checks = {c["id"]: c for c in d.run_system_checks()}
    assert checks["constitution"]["status"] in {"ok", "warn"}  # never "fail" on a healthy repo


# ── REST endpoints ─────────────────────────────────────────────────────────────

def _client() -> TestClient:
    app = FastAPI()
    app.include_router(d.router)
    return TestClient(app)


def test_system_endpoint():
    resp = _client().get("/api/diagnostics/system")
    assert resp.status_code == 200
    body = resp.json()
    assert "checks" in body and "summary" in body
    assert body["summary"]["overall"] in {"ok", "warn", "fail"}


def test_cached_endpoint_shape(tmp_path, monkeypatch):
    # Point the cache at a temp file and round-trip a payload through it.
    cache = tmp_path / "diagnostics_cache.json"
    monkeypatch.setattr(d, "CACHE_PATH", cache)

    # No cache yet → available False.
    resp = _client().get("/api/diagnostics/cached")
    assert resp.json()["available"] is False

    # Write one, then it should surface.
    payload = {"ts": 123.0, "system": {"summary": {"overall": "ok"}}, "suites": {}}
    d._write_cache(payload)
    resp = _client().get("/api/diagnostics/cached")
    body = resp.json()
    assert body["available"] is True
    assert body["ts"] == 123.0
