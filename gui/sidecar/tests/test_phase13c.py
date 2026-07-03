"""Phase 13c tests — Data-Driven Launch System: execution layer.

Runs against the real MySQL ``agenticos_test`` schema (see conftest.py) per
the MySQL-everywhere testing rule. Covers:

  * process_manager consuming launch_config.build_launch_command():
      multi-step launches, wait_for_completion semantics, abort-on-failure,
      broken-template surfacing, wait_for_port end-to-end
  * process-group kill (start_new_session + os.killpg) — children die too
  * app_processes persistence (record on start, mark-stopped on stop)
  * legacy registry fallback when no launch config exists
  * GET /api/apps/processes route (live + degraded)
  * /api/apps/{app_id}/status merging DB process rows

Real subprocesses (sleep / bash / true / false) are spawned — they are cheap,
local, and killed by the code under test. launch_config's default sessions
are pointed at the test schema by monkeypatching ``gui.sidecar.db.SessionLocal``.
"""
from __future__ import annotations

import asyncio
import os
import signal
import socket
import subprocess
import sys
import time

import pytest

from gui.sidecar import launch_config
from gui.sidecar.models import AppCommand, AppProcess, Port, Project


# ── fixtures / helpers ─────────────────────────────────────────────────────────

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
    """A fresh (non-singleton) manager per test — no shared _procs state."""
    from core.process_manager import _ProcessManager
    return _ProcessManager()


def _add_project(session, app_id, path, venv_path=None):
    session.add(Project(
        id=app_id, name=app_id, path=path, template="imported",
        venv_path=venv_path, created_by="discovered",
    ))
    session.commit()


def _add_command(session, app_id, step, command, args=None, *,
                 port_type=None, wait_for_completion=False,
                 wait_for_port=False, timeout=10, cwd=None, env=None):
    session.add(AppCommand(
        app_id=app_id, step_order=step, command=command, args=args or [],
        working_directory=cwd, port_type=port_type, environment_json=env,
        wait_for_completion=wait_for_completion, wait_for_port=wait_for_port,
        wait_for_port_timeout_seconds=timeout, health_check_enabled=False,
    ))
    session.commit()


def _rows(session, app_id):
    """Fresh-snapshot read of app_processes rows written by OTHER sessions."""
    session.rollback()   # end the REPEATABLE READ snapshot
    return (
        session.query(AppProcess)
        .filter_by(app_id=app_id)
        .order_by(AppProcess.started_at, AppProcess.id)
        .all()
    )


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_dead(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.1)
    return not _pid_alive(pid)


# ── multi-step launches via launch config ─────────────────────────────────────

class TestLaunchSteps:
    def test_multi_step_launch_and_stop(
            self, db_session, patched_sessionlocal, fresh_manager, tmp_path):
        """Completion step runs to exit; long step stays up; stop kills it."""
        app = "lc-multi"
        _add_project(db_session, app, str(tmp_path))
        _add_command(db_session, app, 1, "true", wait_for_completion=True)
        _add_command(db_session, app, 2, "sleep", ["30"])

        async def scenario():
            status = await fresh_manager.start(app)
            try:
                assert status["running"] is True
                assert status["error"] is None
                assert len(status["processes"]) == 1
                live_pid = status["pid"]
                assert _pid_alive(live_pid)

                rows = _rows(db_session, app)
                assert len(rows) == 2
                done = next(r for r in rows if r.pid != live_pid)
                assert done.status == "stopped" and done.exit_code == 0
                running = next(r for r in rows if r.pid == live_pid)
                assert running.status == "running"
            finally:
                result = await fresh_manager.stop(app)
            return live_pid, result

        live_pid, result = asyncio.run(scenario())
        assert live_pid in result["killed_pids"]
        assert result["running"] is False
        assert _wait_dead(live_pid)
        rows = _rows(db_session, app)
        assert all(r.status != "running" for r in rows)

    def test_failing_completion_step_aborts(
            self, db_session, patched_sessionlocal, fresh_manager, tmp_path):
        app = "lc-fail"
        _add_project(db_session, app, str(tmp_path))
        _add_command(db_session, app, 1, "false", wait_for_completion=True)
        _add_command(db_session, app, 2, "sleep", ["30"])

        status = asyncio.run(fresh_manager.start(app))
        assert status["running"] is False
        assert "exited with code 1" in status["error"]
        rows = _rows(db_session, app)
        assert len(rows) == 1                      # step 2 never spawned
        assert rows[0].status == "stopped" and rows[0].exit_code == 1

    def test_broken_template_surfaces_error(
            self, db_session, patched_sessionlocal, fresh_manager, tmp_path):
        app = "lc-broken"
        _add_project(db_session, app, str(tmp_path))
        _add_command(db_session, app, 1, "echo", ["{bogus_port}"])

        status = asyncio.run(fresh_manager.start(app))
        assert status["running"] is False
        assert "Launch config error" in status["error"]
        assert _rows(db_session, app) == []        # nothing spawned

    def test_process_group_kill_reaches_children(
            self, db_session, patched_sessionlocal, fresh_manager, tmp_path):
        """bash parent + sleep child share a group; stop must kill BOTH."""
        app = "lc-group"
        _add_project(db_session, app, str(tmp_path))
        _add_command(db_session, app, 1, "bash", ["-c", "sleep 60 & wait"])

        async def scenario():
            status = await fresh_manager.start(app)
            parent = status["pid"]
            assert _pid_alive(parent)
            await asyncio.sleep(0.3)  # let bash fork the child
            group = subprocess.run(
                ["pgrep", "-g", str(parent)], capture_output=True, text=True
            ).stdout.split()
            assert len(group) >= 2, f"expected parent+child in group, got {group}"
            await fresh_manager.stop(app)
            return parent, group

        parent, group = asyncio.run(scenario())
        assert _wait_dead(parent)
        for pid in group:
            assert _wait_dead(int(pid)), f"group member {pid} survived killpg"

    def test_wait_for_port_end_to_end(
            self, db_session, patched_sessionlocal, fresh_manager, tmp_path):
        """A step that binds {frontend_port} passes the wait_for_port gate."""
        app = "lc-port"
        port = _free_port()
        _add_project(db_session, app, str(tmp_path))
        db_session.add(Port(port=port, app_id=app, port_type="frontend"))
        db_session.commit()
        _add_command(
            db_session, app, 1, sys.executable,
            ["-c",
             "import socket,time,sys; s=socket.socket(); "
             "s.bind(('127.0.0.1', int(sys.argv[1]))); s.listen(16); "
             "time.sleep(30)",
             "{frontend_port}"],
            port_type="frontend", wait_for_port=True, timeout=10,
        )

        async def scenario():
            status = await fresh_manager.start(app)
            try:
                assert status["running"] is True
                assert status["port"] == port
                assert status["url"] == f"http://localhost:{port}"
                # the gate really waited: port is live
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    pass
            finally:
                await fresh_manager.stop(app)
            return status

        status = asyncio.run(scenario())
        assert _wait_dead(status["pid"])


# ── legacy registry fallback ───────────────────────────────────────────────────

class TestLegacyFallback:
    def test_no_launch_config_uses_registry(
            self, db_session, patched_sessionlocal, fresh_manager,
            tmp_path, monkeypatch):
        """App absent from projects/app_commands → legacy path, still
        persisted to app_processes."""
        from core import app_registry
        app = "legacy-app"
        entry = {"id": app, "app_path": str(tmp_path),
                 "start_command": ["sleep", "30"],
                 "expected_port": None, "venv": None}
        monkeypatch.setattr(app_registry, "get",
                            lambda app_id: entry if app_id == app else None)

        async def scenario():
            status = await fresh_manager.start(app)
            try:
                assert status["running"] is True
                rows = _rows(db_session, app)
                assert len(rows) == 1 and rows[0].status == "running"
                assert rows[0].process_type == "other"
            finally:
                result = await fresh_manager.stop(app)
            return status, result

        status, result = asyncio.run(scenario())
        assert result["killed_pids"] == [status["pid"]]
        rows = _rows(db_session, app)
        assert rows[0].status == "stopped"


# ── stop() orphan sweep ────────────────────────────────────────────────────────

class TestOrphanSweep:
    def test_stop_kills_db_known_orphan(
            self, db_session, patched_sessionlocal, fresh_manager):
        """A running app_processes row with no in-memory entry (sidecar
        restarted) is still killed by stop()."""
        app = "orphan-app"
        proc = subprocess.Popen(["sleep", "60"], start_new_session=True)
        try:
            launch_config.record_process(app, proc.pid, session=db_session)
            result = asyncio.run(fresh_manager.stop(app))
            assert proc.pid in result["killed_pids"]
            # reap our own child — a zombie still passes the signal-0 probe
            assert proc.wait(timeout=5) < 0   # died by signal
            rows = _rows(db_session, app)
            assert rows[0].status != "running"
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


# ── routes ─────────────────────────────────────────────────────────────────────

class TestRoutes:
    def test_get_processes_lists_running(
            self, db_session, patched_sessionlocal):
        from fastapi.testclient import TestClient
        from gui.sidecar.app import app as fastapi_app

        proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
        try:
            launch_config.record_process("route-app", proc.pid, port=4321,
                                         session=db_session)
            client = TestClient(fastapi_app)
            body = client.get("/api/apps/processes").json()
            assert body["available"] is True
            match = [p for p in body["processes"] if p["pid"] == proc.pid]
            assert match and match[0]["app_id"] == "route-app"
            assert match[0]["port"] == 4321
            assert body["total"] == len(body["processes"])
        finally:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()

    def test_get_processes_degrades_without_db(self, monkeypatch):
        from fastapi.testclient import TestClient
        from gui.sidecar.app import app as fastapi_app

        def _boom(session=None):
            raise RuntimeError("MySQL down")
        monkeypatch.setattr(launch_config, "list_all_processes", _boom)
        body = TestClient(fastapi_app).get("/api/apps/processes").json()
        assert body["available"] is False
        assert body["processes"] == [] and body["total"] == 0

    def test_status_route_merges_db_processes(
            self, db_session, patched_sessionlocal, monkeypatch, tmp_path):
        """/api/apps/{id}/status surfaces app_processes rows even when the
        in-memory manager didn't launch the app."""
        from fastapi.testclient import TestClient
        from core import app_registry
        from gui.sidecar.app import app as fastapi_app

        app = "status-app"
        entry = {"id": app, "app_path": str(tmp_path),
                 "start_command": ["sleep", "1"],
                 "expected_port": None, "venv": None}
        monkeypatch.setattr(app_registry, "get",
                            lambda app_id: entry if app_id == app else None)

        proc = subprocess.Popen(["sleep", "30"], start_new_session=True)
        try:
            launch_config.record_process(app, proc.pid, port=4322,
                                         process_type="frontend",
                                         session=db_session)
            body = TestClient(fastapi_app).get(f"/api/apps/{app}/status").json()
            assert body["running"] is True
            assert body["pid"] == proc.pid
            assert body["port"] == 4322
            assert body["processes"][0]["port_type"] == "frontend"
        finally:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


# ── startup reconcile wiring ───────────────────────────────────────────────────

class TestReconcileWiring:
    def test_startup_hook_registered(self):
        """app.py must wire reconcile_stale_processes into startup (13c)."""
        from gui.sidecar import app as app_module
        assert hasattr(app_module, "_reconcile_stale_processes")

    def test_reconcile_sweeps_dead_pid(self, db_session, patched_sessionlocal):
        proc = subprocess.Popen(["sleep", "0.05"])
        proc.wait()
        launch_config.record_process("dead-app", proc.pid, session=db_session)
        # pid may be recycled in theory; on macOS within a test it won't be.
        result = launch_config.reconcile_stale_processes()
        assert {"app_id": "dead-app", "pid": proc.pid} in result["swept"]
        rows = _rows(db_session, "dead-app")
        assert rows[0].status == "stopped"
