"""Phase 13a tests — Data-Driven App Launch System (schema + config layer).

Runs against the real MySQL ``agenticos_test`` schema (see conftest.py) per
the MySQL-everywhere testing rule. Covers:

  * schema — all Phase 13a tables + new columns exist after create_all
  * migrations.ensure_phase13_schema — ALTERs an old-shape database in place
  * launch_config.allocate_ports — contract, typing, idempotency
  * launch_config.build_launch_command — templating, cwd, env, health checks,
    unresolved-variable failure
  * launch_config get_app_status / record / mark-stopped / reconcile / list

Network/pid probes are monkeypatched — no real ports or processes involved.
"""
from __future__ import annotations

import pytest
from sqlalchemy import inspect, text

from gui.sidecar import launch_config
from gui.sidecar.models import (
    AppCommand,
    AppHealthCheck,
    AppProcess,
    Port,
    PortCollisionLog,
    Project,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _add_project(session, app_id="worldwise", path="/tmp/codehome/worldwise",
                 venv_path="/tmp/codehome/worldwise/.venv"):
    session.add(Project(
        id=app_id, name=app_id, path=path, template="imported",
        venv_path=venv_path, created_by="discovered",
    ))
    session.commit()


def _no_live_ports(monkeypatch):
    """Neutralise live TCP probes + registry lookups in the allocator."""
    from gui.sidecar import project_manager
    monkeypatch.setattr(project_manager, "_port_in_use", lambda p: False)
    monkeypatch.setattr(project_manager, "_registry_ports", lambda: set())


# ── schema ─────────────────────────────────────────────────────────────────────

class TestSchema:
    def test_all_phase13_tables_exist(self, mysql_engine):
        tables = set(inspect(mysql_engine).get_table_names())
        assert {"projects", "ports", "app_commands", "app_processes",
                "app_health_checks", "port_collision_log"} <= tables

    def test_new_columns_exist(self, mysql_engine):
        insp = inspect(mysql_engine)
        assert "venv_path" in {c["name"] for c in insp.get_columns("projects")}
        assert "port_type" in {c["name"] for c in insp.get_columns("ports")}

    def test_uk_app_port_type_enforced(self, db_session):
        db_session.add(Port(port=5300, app_id="x", port_type="backend"))
        db_session.commit()
        db_session.add(Port(port=5301, app_id="x", port_type="backend"))
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()


class TestMigration:
    def test_alters_old_shape_database(self, mysql_engine):
        """Simulate the pre-13a shape in a scratch schema and migrate it."""
        from gui.sidecar.migrations import ensure_phase13_schema
        from gui.sidecar.tests.conftest import _server_url, _test_db_url  # noqa
        from gui.sidecar.db import _CFG
        from sqlalchemy import create_engine

        scratch = "agenticos_migration_test"
        server = create_engine(_server_url(_CFG), future=True)
        with server.begin() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS `{scratch}`"))
            conn.execute(text(f"CREATE DATABASE `{scratch}`"))
        server.dispose()

        engine = create_engine(_server_url(_CFG) + scratch, future=True)
        try:
            with engine.begin() as conn:
                # Old (Phase 11a) shapes — no venv_path, no port_type.
                conn.execute(text(
                    "CREATE TABLE projects (id VARCHAR(128) PRIMARY KEY, "
                    "name VARCHAR(255) NOT NULL, description TEXT, "
                    "path VARCHAR(512) NOT NULL UNIQUE, subfolder VARCHAR(128), "
                    "template VARCHAR(128) NOT NULL, port INT, "
                    "github_repo_url VARCHAR(512), created_at DATETIME, "
                    "created_by VARCHAR(255))"
                ))
                conn.execute(text(
                    "CREATE TABLE ports (port INT PRIMARY KEY, "
                    "app_id VARCHAR(128) NOT NULL, status VARCHAR(32), "
                    "allocated_at DATETIME)"
                ))
                conn.execute(text(
                    "INSERT INTO ports (port, app_id, status) "
                    "VALUES (5130, 'agenticos-sidecar', 'reserved')"
                ))

            result = ensure_phase13_schema(engine)

            assert "projects.venv_path" in result["added_columns"]
            assert "ports.port_type" in result["added_columns"]
            assert "ports.uk_app_port_type" in result["added_indexes"]
            assert {"app_commands", "app_processes", "app_health_checks",
                    "port_collision_log"} <= set(result["created_tables"])
            # Existing row got the default port_type and survived.
            with engine.connect() as conn:
                row = conn.execute(text(
                    "SELECT app_id, port_type FROM ports WHERE port=5130"
                )).one()
            assert row == ("agenticos-sidecar", "api")

            # Idempotent: second run changes nothing.
            again = ensure_phase13_schema(engine)
            assert again["added_columns"] == []
            assert again["added_indexes"] == []
            assert again["warnings"] == []
        finally:
            engine.dispose()
            server = create_engine(_server_url(_CFG), future=True)
            with server.begin() as conn:
                conn.execute(text(f"DROP DATABASE IF EXISTS `{scratch}`"))
            server.dispose()


# ── allocate_ports ─────────────────────────────────────────────────────────────

class TestAllocatePorts:
    def test_allocates_typed_ports(self, db_session, monkeypatch):
        _no_live_ports(monkeypatch)
        result = launch_config.allocate_ports(
            "newapp", ["backend", "frontend"], session=db_session)
        assert result["success"] is True
        assert set(result["ports"]) == {"backend", "frontend"}
        ports = db_session.query(Port).filter_by(app_id="newapp").all()
        assert {p.port_type for p in ports} == {"backend", "frontend"}
        assert all(p.status == "allocated" for p in ports)

    def test_idempotent_returns_existing(self, db_session, monkeypatch):
        _no_live_ports(monkeypatch)
        first = launch_config.allocate_ports("app2", ["api"], session=db_session)
        second = launch_config.allocate_ports("app2", ["api"], session=db_session)
        assert first["ports"] == second["ports"]
        assert db_session.query(Port).filter_by(app_id="app2").count() == 1

    def test_rejects_invalid_type(self, db_session):
        result = launch_config.allocate_ports(
            "app3", ["warp-core"], session=db_session)
        assert result["success"] is False
        assert "invalid port_type" in result["error"]

    def test_rejects_duplicate_types(self, db_session):
        result = launch_config.allocate_ports(
            "app4", ["api", "api"], session=db_session)
        assert result["success"] is False


# ── build_launch_command ───────────────────────────────────────────────────────

class TestBuildLaunchCommand:
    def _seed_worldwise(self, session):
        _add_project(session)
        session.add_all([
            Port(port=8000, app_id="worldwise", port_type="backend"),
            Port(port=5173, app_id="worldwise", port_type="frontend"),
        ])
        session.add_all([
            AppCommand(
                app_id="worldwise", step_order=1, command="uvicorn",
                args=["backend.app.main:app", "--reload",
                      "--port", "{backend_port}"],
                working_directory=".", port_type="backend",
                environment_json={"PYTHONPATH": "{app_path}/backend"},
                wait_for_port=True,
            ),
            AppCommand(
                app_id="worldwise", step_order=2, command="npm",
                args=["run", "dev", "--", "--port", "{frontend_port}"],
                working_directory="web", port_type="frontend",
                wait_for_port=True,
            ),
        ])
        session.add(AppHealthCheck(
            app_id="worldwise", port=8000, endpoint="/docs",
        ))
        session.commit()

    def test_resolves_templates_and_paths(self, db_session):
        self._seed_worldwise(db_session)
        steps = launch_config.build_launch_command("worldwise", session=db_session)
        assert [s["step"] for s in steps] == [1, 2]

        backend = steps[0]
        assert backend["args"] == [
            "backend.app.main:app", "--reload", "--port", "8000"]
        assert backend["cwd"] == "/tmp/codehome/worldwise"
        assert backend["env"] == {"PYTHONPATH": "/tmp/codehome/worldwise/backend"}
        assert backend["venv"] == "/tmp/codehome/worldwise/.venv"
        assert backend["port"] == 8000
        assert backend["wait_for_port"] is True
        assert backend["health_check"]["url"] == "http://localhost:8000/docs"

        frontend = steps[1]
        assert frontend["args"][-1] == "5173"
        assert frontend["cwd"] == "/tmp/codehome/worldwise/web"
        assert "health_check" not in frontend

    def test_unresolved_variable_raises(self, db_session):
        _add_project(db_session, app_id="broken", path="/tmp/broken")
        db_session.add(AppCommand(
            app_id="broken", step_order=1, command="uvicorn",
            args=["--port", "{backend_port}"],   # no backend port allocated
        ))
        db_session.commit()
        with pytest.raises(ValueError, match="backend_port"):
            launch_config.build_launch_command("broken", session=db_session)

    def test_unknown_app_raises(self, db_session):
        with pytest.raises(LookupError):
            launch_config.build_launch_command("ghost", session=db_session)

    def test_no_commands_raises(self, db_session):
        _add_project(db_session, app_id="bare", path="/tmp/bare")
        with pytest.raises(LookupError, match="no app_commands"):
            launch_config.build_launch_command("bare", session=db_session)


# ── process bookkeeping + status ───────────────────────────────────────────────

class TestProcessLifecycle:
    def test_record_and_status(self, db_session, monkeypatch):
        monkeypatch.setattr(launch_config, "_pid_alive", lambda pid: True)
        launch_config.record_process(
            "worldwise", 12345, process_type="backend", port=8000,
            session=db_session)
        launch_config.record_process(
            "worldwise", 12346, process_type="frontend", port=5173,
            session=db_session)

        status = launch_config.get_app_status("worldwise", session=db_session)
        assert status["running"] is True
        assert status["ports"] == [5173, 8000]
        assert {p["pid"] for p in status["processes"]} == {12345, 12346}

    def test_dead_pid_marked_stopped(self, db_session, monkeypatch):
        launch_config.record_process(
            "worldwise", 11111, process_type="backend", port=8000,
            session=db_session)
        monkeypatch.setattr(launch_config, "_pid_alive", lambda pid: False)

        status = launch_config.get_app_status("worldwise", session=db_session)
        assert status["running"] is False
        row = db_session.query(AppProcess).filter_by(pid=11111).one()
        assert row.status == "stopped"
        assert row.stopped_at is not None

    def test_mark_process_stopped(self, db_session):
        launch_config.record_process("app", 222, session=db_session)
        assert launch_config.mark_process_stopped(
            222, exit_code=0, session=db_session) is True
        row = db_session.query(AppProcess).filter_by(pid=222).one()
        assert row.status == "stopped" and row.exit_code == 0
        # No running row left → False.
        assert launch_config.mark_process_stopped(222, session=db_session) is False

    def test_mark_error(self, db_session):
        launch_config.record_process("app", 333, session=db_session)
        launch_config.mark_process_stopped(
            333, exit_code=1, error_message="boom", session=db_session)
        row = db_session.query(AppProcess).filter_by(pid=333).one()
        assert row.status == "error" and row.error_message == "boom"

    def test_reconcile_stale(self, db_session, monkeypatch):
        launch_config.record_process("a", 444, session=db_session)
        launch_config.record_process("b", 555, session=db_session)
        monkeypatch.setattr(
            launch_config, "_pid_alive", lambda pid: pid == 555)

        result = launch_config.reconcile_stale_processes(session=db_session)
        assert result["checked"] == 2
        assert result["swept"] == [{"app_id": "a", "pid": 444}]
        assert db_session.query(AppProcess).filter_by(
            pid=555, status="running").count() == 1

    def test_list_all_processes(self, db_session, monkeypatch):
        monkeypatch.setattr(launch_config, "_pid_alive", lambda pid: True)
        launch_config.record_process("a", 666, port=5200, session=db_session)
        launch_config.record_process("b", 777, port=5201, session=db_session)
        result = launch_config.list_all_processes(session=db_session)
        assert result["total"] == 2
        assert {p["app_id"] for p in result["processes"]} == {"a", "b"}

    def test_invalid_process_type_rejected(self, db_session):
        with pytest.raises(ValueError):
            launch_config.record_process(
                "a", 888, process_type="daemon", session=db_session)


class TestCollisionLog:
    def test_log_collision(self, db_session):
        launch_config.log_collision(
            5173, "worldwise", "other-app", phase="backfill",
            notes="both claim 5173", session=db_session)
        row = db_session.query(PortCollisionLog).one()
        assert (row.port, row.phase, row.resolved) == (5173, "backfill", False)
