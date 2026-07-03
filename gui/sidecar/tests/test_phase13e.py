"""Phase 13e tests — integration (fake app e2e) + active health polling.

The centerpiece is a REAL fake app: a Python HTTP server whose /health flips
to 500 when a flag file appears. The e2e chain exercises the whole launch
system end to end:

    seed config → manager.start (build_launch_command + wait_for_port)
    → run_health_checks marks healthy → flip the flag → unhealthy transition
    → manager.stop (process-group kill) → rows stopped, port free

Also covered: the hard-kill path (SIGTERM-ignoring process), allocator
collision avoidance against a LIVE port, health-poll edge cases
(no_config / not_due / dead-pid sweep), list_all_health aggregation,
GET /api/apps/health (live + degraded), and the seed_health_checks script
(probe-verified plan, apply, idempotency).

MySQL-backed per the testing rule; one event loop per scenario (13c gotcha).
"""
from __future__ import annotations

import asyncio
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import timedelta

import pytest

from gui.sidecar import launch_config
from gui.sidecar.models import AppCommand, AppHealthCheck, AppProcess, Port, Project


# ── fixtures / helpers (13c conventions) ──────────────────────────────────────

@pytest.fixture()
def patched_sessionlocal(mysql_engine, monkeypatch):
    """Point launch_config's default sessions at the agenticos_test schema."""
    from sqlalchemy.orm import sessionmaker
    import gui.sidecar.db as db
    monkeypatch.setattr(
        db, "SessionLocal",
        sessionmaker(bind=mysql_engine, autoflush=False, future=True),
    )


@pytest.fixture()
def fresh_manager():
    from core.process_manager import _ProcessManager
    return _ProcessManager()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _add_project(session, app_id, path):
    session.add(Project(id=app_id, name=app_id, path=path,
                        template="imported", created_by="discovered"))
    session.commit()


def _registry_stub(monkeypatch, app_id, app_path):
    from core import app_registry
    entry = {"id": app_id, "app_path": app_path,
             "start_command": ["sleep", "1"],
             "expected_port": None, "venv": None}
    monkeypatch.setattr(app_registry, "get",
                        lambda aid: entry if aid == app_id else None)


FAKE_APP = """\
import http.server, os, sys
port, flag = int(sys.argv[1]), sys.argv[2]
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        code = 500 if os.path.exists(flag) else 200
        self.send_response(code)
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *a):
        pass
srv = http.server.HTTPServer(("127.0.0.1", port), H)
srv.serve_forever()
"""


def _seed_fake_app(session, tmp_path, *, interval=0):
    """Seed project + typed port + launch step + health check; return (id, port, flag)."""
    app_id = "e2e-app"
    port = _free_port()
    script = tmp_path / "fake_app.py"
    script.write_text(FAKE_APP)
    flag = tmp_path / "unhealthy.flag"

    _add_project(session, app_id, str(tmp_path))
    session.add(Port(port=port, app_id=app_id, port_type="frontend"))
    session.add(AppCommand(
        app_id=app_id, step_order=1, command=sys.executable,
        args=[str(script), "{frontend_port}", str(flag)],
        working_directory=None, port_type="frontend",
        wait_for_completion=False, wait_for_port=True,
        wait_for_port_timeout_seconds=15, health_check_enabled=False,
    ))
    session.add(AppHealthCheck(
        app_id=app_id, port=port, endpoint="/health", method="GET",
        expected_status_code=200, timeout_seconds=3,
        interval_seconds=interval, enabled=True,
    ))
    session.commit()
    return app_id, port, flag


# ═══════════════════════════════════════════════════════════════════════════════
# The e2e chain
# ═══════════════════════════════════════════════════════════════════════════════

class TestEndToEnd:
    def test_launch_health_unhealthy_stop(
            self, db_session, patched_sessionlocal, monkeypatch,
            tmp_path, fresh_manager):
        app_id, port, flag = _seed_fake_app(db_session, tmp_path, interval=0)
        _registry_stub(monkeypatch, app_id, str(tmp_path))

        async def scenario():
            started = await fresh_manager.start(app_id)
            assert started["running"] is True and started["error"] is None
            assert started["port"] == port          # wait_for_port proved it

            # healthy pass
            s1 = launch_config.run_health_checks()
            assert s1["checked"] == 1 and s1["healthy"] == 1

            status = launch_config.get_app_status(app_id)
            assert status["running"] is True
            assert status["processes"][0]["is_healthy"] is True
            assert status["processes"][0]["last_health_check"] is not None

            # flip to unhealthy — transition recorded
            flag.write_text("down")
            s2 = launch_config.run_health_checks()
            assert s2["unhealthy"] == 1
            assert s2["transitions"] == [f"{app_id}:{port} down"]
            agg = launch_config.list_all_health()
            assert agg["apps"][app_id]["healthy"] is False

            stopped = await fresh_manager.stop(app_id)
            assert stopped["running"] is False and stopped["killed_pids"]
            return stopped["killed_pids"]

        killed = asyncio.run(scenario())
        # process really gone + port free again
        time.sleep(0.2)
        for pid in killed:
            with pytest.raises(OSError):
                os.kill(pid, 0)
        with socket.socket() as s:
            assert s.connect_ex(("127.0.0.1", port)) != 0
        # DB rows closed out
        db_session.rollback()
        rows = db_session.query(AppProcess).filter_by(app_id=app_id).all()
        assert rows and all(r.status == "stopped" for r in rows)

    def test_hard_kill_path_sigterm_ignorer(
            self, db_session, patched_sessionlocal, monkeypatch,
            tmp_path, fresh_manager):
        """A SIGTERM-trapping process must die via the SIGKILL fallback."""
        app_id = "stubborn-app"
        _add_project(db_session, app_id, str(tmp_path))
        db_session.add(AppCommand(
            app_id=app_id, step_order=1, command="bash",
            args=["-c", 'trap "" TERM; sleep 60'],
            wait_for_completion=False, wait_for_port=False,
            wait_for_port_timeout_seconds=5, health_check_enabled=False,
        ))
        db_session.commit()
        _registry_stub(monkeypatch, app_id, str(tmp_path))

        async def scenario():
            started = await fresh_manager.start(app_id)
            assert started["running"] is True
            pid = started["pid"]
            t0 = time.monotonic()
            stopped = await fresh_manager.stop(app_id)
            elapsed = time.monotonic() - t0
            assert stopped["running"] is False and pid in stopped["killed_pids"]
            assert elapsed >= 4.5        # grace expired → SIGKILL path taken
            return pid

        pid = asyncio.run(scenario())
        time.sleep(0.2)
        with pytest.raises(OSError):
            os.kill(pid, 0)

    def test_allocator_avoids_live_port(self, db_session, tmp_path):
        """Collision detection: a preferred port that is LIVE is refused."""
        from gui.sidecar import project_manager
        app_id = "collide-app"
        _add_project(db_session, app_id, str(tmp_path))

        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen(1)
            live_port = blocker.getsockname()[1]
            allocated = project_manager.allocate_port(
                app_id, preferred_port=live_port, session=db_session)
            assert allocated != live_port


# ═══════════════════════════════════════════════════════════════════════════════
# run_health_checks edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthPolling:
    def test_no_config_rows_left_alone(self, db_session, patched_sessionlocal):
        proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
        try:
            launch_config.record_process("plain-app", proc.pid, port=None,
                                         session=db_session)
            s = launch_config.run_health_checks(session=db_session)
            assert s["no_config"] == 1 and s["checked"] == 0
            db_session.rollback()
            row = db_session.query(AppProcess).filter_by(pid=proc.pid).one()
            assert row.last_health_check is None
        finally:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()

    def test_interval_not_due_skips(self, db_session, patched_sessionlocal,
                                    tmp_path):
        """interval_seconds is respected — second immediate pass skips."""
        app_id, port, _flag = _seed_fake_app(db_session, tmp_path,
                                             interval=3600)
        proc = subprocess.Popen(
            [sys.executable, str(tmp_path / "fake_app.py"), str(port),
             str(tmp_path / "unhealthy.flag")],
            start_new_session=True)
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                with socket.socket() as s:
                    if s.connect_ex(("127.0.0.1", port)) == 0:
                        break
                time.sleep(0.1)
            launch_config.record_process(app_id, proc.pid, port=port,
                                         session=db_session)
            s1 = launch_config.run_health_checks(session=db_session)
            assert s1["checked"] == 1 and s1["healthy"] == 1
            s2 = launch_config.run_health_checks(session=db_session)
            assert s2["not_due"] == 1 and s2["checked"] == 0
        finally:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()

    def test_health_check_url_fallback(self, db_session, patched_sessionlocal,
                                       tmp_path):
        """No app_health_checks row → the launch-time URL is used."""
        port = _free_port()
        script = tmp_path / "fake_app.py"
        script.write_text(FAKE_APP)
        proc = subprocess.Popen(
            [sys.executable, str(script), str(port),
             str(tmp_path / "nope.flag")],
            start_new_session=True)
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                with socket.socket() as s:
                    if s.connect_ex(("127.0.0.1", port)) == 0:
                        break
                time.sleep(0.1)
            launch_config.record_process(
                "url-app", proc.pid, port=port,
                health_check_url=f"http://localhost:{port}/health",
                session=db_session)
            s1 = launch_config.run_health_checks(session=db_session)
            assert s1["checked"] == 1 and s1["healthy"] == 1
        finally:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()

    def test_dead_pid_swept_not_probed(self, db_session, patched_sessionlocal):
        proc = subprocess.Popen(["sleep", "0.1"], start_new_session=True)
        proc.wait()
        launch_config.record_process("ghost-app", proc.pid, port=1,
                                     health_check_url="http://localhost:1/",
                                     session=db_session)
        s = launch_config.run_health_checks(session=db_session)
        assert s["checked"] == 0
        db_session.rollback()
        row = db_session.query(AppProcess).filter_by(app_id="ghost-app").one()
        assert row.status == "stopped"


# ═══════════════════════════════════════════════════════════════════════════════
# Aggregation + route
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthSurface:
    def test_list_all_health_excludes_unchecked(self, db_session,
                                                patched_sessionlocal):
        proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
        try:
            launch_config.record_process("silent-app", proc.pid, port=None,
                                         session=db_session)
            agg = launch_config.list_all_health(session=db_session)
            assert "silent-app" not in agg["apps"]
        finally:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()

    def test_health_route_live_and_degraded(self, db_session,
                                            patched_sessionlocal, monkeypatch):
        from fastapi.testclient import TestClient
        from gui.sidecar.app import app as fastapi_app

        body = TestClient(fastapi_app).get("/api/apps/health").json()
        assert body["available"] is True and isinstance(body["apps"], dict)

        def _boom(session=None):
            raise RuntimeError("MySQL down")
        monkeypatch.setattr(launch_config, "list_all_health", _boom)
        body = TestClient(fastapi_app).get("/api/apps/health").json()
        assert body["available"] is False and body["apps"] == {}


# ═══════════════════════════════════════════════════════════════════════════════
# seed_health_checks script
# ═══════════════════════════════════════════════════════════════════════════════

class TestSeedScript:
    def test_plan_verifies_live_probe_and_apply_is_idempotent(
            self, db_session, tmp_path):
        from gui.sidecar.scripts import seed_health_checks as seeder

        app_id = "seed-app"
        _add_project(db_session, app_id, str(tmp_path))
        port = _free_port()
        dead_port = _free_port()
        db_session.add(Port(port=port, app_id=app_id, port_type="frontend"))
        db_session.add(Port(port=dead_port, app_id="dead-app",
                            port_type="frontend"))
        db_session.commit()

        script = tmp_path / "fake_app.py"
        script.write_text(FAKE_APP)
        proc = subprocess.Popen(
            [sys.executable, str(script), str(port),
             str(tmp_path / "nope.flag")],
            start_new_session=True)
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                with socket.socket() as s:
                    if s.connect_ex(("127.0.0.1", port)) == 0:
                        break
                time.sleep(0.1)

            plan = seeder.plan_seed(db_session)
            inserts = {(e["app_id"], e["port"]) for e in plan["insert"]}
            assert (app_id, port) in inserts
            # fake app answers 200 on every path → first candidate wins
            entry = next(e for e in plan["insert"] if e["app_id"] == app_id)
            assert entry["endpoint"] == "/api/health"
            assert any(e["app_id"] == "dead-app" for e in plan["not_running"])

            seeder.apply_seed(db_session, plan)
            row = (db_session.query(AppHealthCheck)
                   .filter_by(app_id=app_id, port=port).one())
            assert row.endpoint == "/api/health" and row.enabled is True

            # idempotent: second plan reports it as existing, inserts nothing
            plan2 = seeder.plan_seed(db_session)
            assert not any(e["app_id"] == app_id for e in plan2["insert"])
            assert any(e["app_id"] == app_id for e in plan2["existing"])
        finally:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
