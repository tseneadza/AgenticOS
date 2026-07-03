"""Phase 13b tests — launch-config backfill script.

Runs against the real MySQL ``agenticos_test`` schema (see conftest.py) per
the MySQL-everywhere testing rule. Covers:

  * start.sh parser — worldwise-style 2-step script (cwd tracking, env
    capture, background detection, shell-variable substitution), housekeeping
    filtering, inline env, unrecognized-command notes
  * port_type inference — expected_port -> 'frontend', headless services stay
    'api', uk_app_port_type conflicts skipped, idempotent second pass
  * templating — literal port -> {backend_port}/{frontend_port}, app path ->
    {app_path}, venv -> {venv_path} only when projects.venv_path is set
  * collision path — start.sh port owned by another app -> PortCollisionLog
    row, no ports insert, literal kept in args
  * no-start.sh fallback to the registry start_command
  * apply end-to-end — extra start.sh port allocated via the ONE allocator
    (incl. preferred-port-unavailable), build_launch_command resolves the
    inserted rows with zero leftover tokens, second run inserts 0

No real ~/Codehome apps are touched: registry entries are injected as plain
dicts and start.sh content is injected via ``read_start_sh``; the allocator's
live TCP/registry probes are monkeypatched.
"""
from __future__ import annotations

from gui.sidecar import launch_config
from gui.sidecar.models import AppCommand, Port, PortCollisionLog, Project
from gui.sidecar.scripts.backfill_launch_config import (
    apply_plan,
    build_plan,
    parse_start_sh,
    plan_port_type_updates,
)

WORLDWISE_PATH = "/tmp/codehome/worldwise"

#: Canonical 2-step script: backend uvicorn :8000 (background) + web npm
#: run dev :5173 (foreground), with the housekeeping noise a real start.sh
#: carries — shebang, comments, echo, sleep, lsof/kill port-freeing, a
#: cleanup function, trap, wait.
WORLDWISE_SH = """\
#!/bin/bash
# Start worldwise: FastAPI backend + Vite frontend
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT=8000
FRONTEND_PORT=5173
export PYTHONPATH="$SCRIPT_DIR/backend"

cleanup() {
    kill $BACKEND_PID 2>/dev/null
    exit 0
}
trap cleanup EXIT

cd "$SCRIPT_DIR"
lsof -ti:$BACKEND_PORT | xargs kill -9 2>/dev/null || true
lsof -ti:$FRONTEND_PORT | xargs kill -9 2>/dev/null || true

echo "Starting backend on port $BACKEND_PORT"
uvicorn backend.app.main:app --reload --port $BACKEND_PORT &
BACKEND_PID=$!
sleep 2

echo "Starting frontend on port $FRONTEND_PORT"
cd "$SCRIPT_DIR/web"
npm run dev -- --port $FRONTEND_PORT

wait
"""


# ── helpers ────────────────────────────────────────────────────────────────────

def _mk_app(app_id, path, expected_port=None, start_command=None):
    """Registry entry shaped like ``core.app_registry.get_all()`` output."""
    return {
        "id": app_id, "name": app_id, "app_path": path,
        "start_command": start_command or [],
        "expected_port": expected_port, "venv": None,
    }


def _add_project(session, app_id, path, venv_path=None):
    session.add(Project(
        id=app_id, name=app_id, path=path, template="imported",
        venv_path=venv_path, created_by="discovered",
    ))
    session.commit()


def _no_live_ports(monkeypatch, in_use=None):
    """Neutralise live TCP probes + registry lookups in the allocator."""
    from gui.sidecar import project_manager
    monkeypatch.setattr(project_manager, "_port_in_use",
                        in_use or (lambda p: False))
    monkeypatch.setattr(project_manager, "_registry_ports", lambda: set())


def _worldwise_setup(session, venv_path=None):
    """Project + ledger row (post-13a shape: port_type defaulted 'api')."""
    _add_project(session, "worldwise", WORLDWISE_PATH, venv_path=venv_path)
    session.add(Port(port=5173, app_id="worldwise", port_type="api"))
    session.commit()
    return [_mk_app("worldwise", WORLDWISE_PATH, expected_port=5173,
                    start_command=["./start.sh"])]


# ── start.sh parser ────────────────────────────────────────────────────────────

class TestStartShParser:
    def test_worldwise_two_steps(self):
        steps, _notes = parse_start_sh(WORLDWISE_SH, app_path=WORLDWISE_PATH)
        assert len(steps) == 2

        backend, frontend = steps
        assert backend.command == "uvicorn"
        assert backend.args == [
            "backend.app.main:app", "--reload", "--port", "8000"]
        assert backend.cwd == "."
        assert backend.background is True
        assert backend.ports == [8000]
        assert backend.env == {"PYTHONPATH": f"{WORLDWISE_PATH}/backend"}

        assert frontend.command == "npm"
        assert frontend.args == ["run", "dev", "--", "--port", "5173"]
        assert frontend.cwd == "web"
        assert frontend.background is False
        assert frontend.ports == [5173]

    def test_housekeeping_and_functions_filtered(self):
        text = """\
#!/bin/bash
set -e
echo "starting"
sleep 1
lsof -ti:5100 | xargs kill -9 2>/dev/null
kill -9 12345 2>/dev/null
cleanup() {
    echo bye
    kill $PID
}
trap cleanup EXIT
mkdir -p logs
python3 api.py
wait
"""
        steps, _ = parse_start_sh(text)
        assert len(steps) == 1
        assert steps[0].command == "python3"
        assert steps[0].args == ["api.py"]

    def test_variable_substitution_in_args(self):
        text = "PORT=5100\nflask run --port $PORT\n"
        steps, _ = parse_start_sh(text)
        assert steps[0].args == ["run", "--port", "5100"]
        assert steps[0].ports == [5100]

    def test_inline_env_captured_and_port_detected(self):
        steps, _ = parse_start_sh("PORT=5100 python api.py &\n")
        assert steps[0].env == {"PORT": "5100"}
        assert steps[0].ports == [5100]
        assert steps[0].background is True

    def test_exported_port_env_is_reference_not_binding(self):
        # Regression (found on live data): agentic's start.sh exports
        # HUB_PORT=8085 — the HUB's port, not a port agentic binds. Exported
        # PORT-ish vars must reach the step env (the app needs them) but must
        # NOT enter the collision cross-check via ParsedStep.ports.
        text = "export HUB_PORT=8085\npython app.py --port 5104\n"
        steps, _ = parse_start_sh(text)
        assert steps[0].env == {"HUB_PORT": "8085"}
        assert steps[0].ports == [5104]

    def test_cd_tracking_relative_and_root(self):
        text = """\
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/backend"
python3 manage.py
cd "$SCRIPT_DIR"
npm start
"""
        steps, _ = parse_start_sh(text, app_path="/tmp/codehome/x")
        assert [s.cwd for s in steps] == ["backend", "."]

    def test_unrecognized_commands_noted_not_captured(self):
        steps, notes = parse_start_sh("make build\npython3 api.py\n")
        assert len(steps) == 1
        assert any("make build" in n for n in notes)


# ── port_type inference ────────────────────────────────────────────────────────

class TestPortTypeInference:
    def test_expected_port_becomes_frontend_services_stay_api(self, db_session):
        db_session.add_all([
            Port(port=5100, app_id="keno", port_type="api"),
            Port(port=5130, app_id="agenticos-sidecar", port_type="api"),
            Port(port=5111, app_id="dreamcatcher-backend", port_type="api"),
        ])
        db_session.commit()
        apps = [_mk_app("keno", "/tmp/codehome/keno", expected_port=5100)]

        updates, skips, intended = plan_port_type_updates(apps, db_session)
        assert updates == [{"app_id": "keno", "port": 5100,
                            "from": "api", "to": "frontend"}]
        assert skips == []
        assert intended["agenticos-sidecar"][5130] == "api"
        assert intended["dreamcatcher-backend"][5111] == "api"

    def test_uk_conflict_reported_and_skipped(self, db_session):
        db_session.add_all([
            Port(port=3000, app_id="x", port_type="frontend"),
            Port(port=3001, app_id="x", port_type="api"),
        ])
        db_session.commit()
        apps = [_mk_app("x", "/tmp/codehome/x", expected_port=3001)]

        updates, skips, _ = plan_port_type_updates(apps, db_session)
        assert updates == []
        assert len(skips) == 1
        assert "uk_app_port_type" in skips[0]["reason"]

    def test_second_pass_is_noop(self, db_session):
        db_session.add(Port(port=5100, app_id="keno", port_type="frontend"))
        db_session.commit()
        apps = [_mk_app("keno", "/tmp/codehome/keno", expected_port=5100)]

        updates, skips, _ = plan_port_type_updates(apps, db_session)
        assert updates == [] and skips == []


# ── templating ─────────────────────────────────────────────────────────────────

class TestTemplating:
    def test_worldwise_plan_paths_and_ports_templated(self, db_session):
        apps = _worldwise_setup(db_session)
        plan = build_plan(apps, db_session,
                          read_start_sh=lambda app: WORLDWISE_SH)

        (cp,) = plan.command_plans
        assert cp.status == "planned" and cp.source == "start.sh"
        step1, step2 = cp.steps

        assert step1["command"] == "uvicorn"
        assert step1["args"] == [
            "backend.app.main:app", "--reload", "--port", "{backend_port}"]
        assert step1["environment_json"] == {"PYTHONPATH": "{app_path}/backend"}
        assert step1["port_type"] == "backend"
        assert step1["port_variable_name"] == "backend_port"
        assert step1["wait_for_completion"] is False
        assert step1["wait_for_port"] is True

        assert step2["args"] == ["run", "dev", "--", "--port", "{frontend_port}"]
        assert step2["working_directory"] == "web"
        assert step2["port_type"] == "frontend"

        # 8000 is in no ledger row -> planned allocation, not a collision.
        assert plan.allocations == [{"app_id": "worldwise",
                                     "preferred_port": 8000,
                                     "port_type": "backend", "step": 1}]
        assert plan.collisions == []
        # Ledger row 5173 (currently 'api') is re-typed to frontend.
        assert plan.port_type_updates == [{"app_id": "worldwise", "port": 5173,
                                           "from": "api", "to": "frontend"}]

    def test_venv_templated_only_when_project_has_venv(self, db_session):
        _add_project(db_session, "withvenv", "/tmp/codehome/withvenv",
                     venv_path="/tmp/codehome/withvenv/.venv")
        _add_project(db_session, "novenv", "/tmp/codehome/novenv")
        db_session.add_all([
            Port(port=5601, app_id="withvenv", port_type="api"),
            Port(port=5602, app_id="novenv", port_type="api"),
        ])
        db_session.commit()

        script = ("#!/bin/bash\n"
                  "/tmp/codehome/withvenv/.venv/bin/python api.py\n")
        apps = [_mk_app("withvenv", "/tmp/codehome/withvenv", 5601)]
        plan = build_plan(apps, db_session, read_start_sh=lambda a: script)
        assert plan.command_plans[0].steps[0]["command"] == \
            "{venv_path}/bin/python"

        script = ("#!/bin/bash\n"
                  "/tmp/codehome/novenv/.venv/bin/python api.py\n")
        apps = [_mk_app("novenv", "/tmp/codehome/novenv", 5602)]
        plan = build_plan(apps, db_session, read_start_sh=lambda a: script)
        # No projects.venv_path -> never emit {venv_path}; app_path still used.
        assert plan.command_plans[0].steps[0]["command"] == \
            "{app_path}/.venv/bin/python"


# ── collision path ─────────────────────────────────────────────────────────────

class TestCollisions:
    def test_foreign_port_logged_not_inserted_literal_kept(
            self, db_session, monkeypatch):
        _no_live_ports(monkeypatch)
        _add_project(db_session, "appa", "/tmp/codehome/appa")
        db_session.add_all([
            Port(port=5109, app_id="appa", port_type="api"),
            Port(port=5112, app_id="astro-physics-hub", port_type="api"),
        ])
        db_session.commit()

        script = "#!/bin/bash\nuvicorn main:app --port 5112\n"
        apps = [_mk_app("appa", "/tmp/codehome/appa", expected_port=5109)]
        plan = build_plan(apps, db_session, read_start_sh=lambda a: script)

        assert len(plan.collisions) == 1
        assert plan.collisions[0]["port"] == 5112
        assert plan.collisions[0]["owner"] == "astro-physics-hub"
        assert plan.allocations == []
        # Literal survives — a colliding port must never become a template.
        step = plan.command_plans[0].steps[0]
        assert step["args"] == ["main:app", "--port", "5112"]

        apply_plan(plan, db_session)
        row = db_session.query(PortCollisionLog).one()
        assert (row.port, row.app_id_1, row.app_id_2, row.phase) == \
            (5112, "appa", "astro-physics-hub", "backfill")
        assert row.resolved is False
        # 5112 still has exactly one owner in the ledger.
        owners = [p.app_id for p in
                  db_session.query(Port).filter_by(port=5112).all()]
        assert owners == ["astro-physics-hub"]


# ── no-start.sh fallback ───────────────────────────────────────────────────────

class TestRegistryFallback:
    def test_start_command_becomes_single_step(self, db_session):
        _add_project(db_session, "keno", "/tmp/codehome/keno")
        db_session.add(Port(port=5100, app_id="keno", port_type="api"))
        db_session.commit()
        apps = [_mk_app("keno", "/tmp/codehome/keno", expected_port=5100,
                        start_command=["python3", "api.py"])]

        plan = build_plan(apps, db_session, read_start_sh=lambda a: None)
        (cp,) = plan.command_plans
        assert cp.source == "registry"
        (step,) = cp.steps
        assert step["command"] == "python3"
        assert step["args"] == ["api.py"]
        assert step["working_directory"] == "."
        # Browser-facing port type (frontend after inference), waited on.
        assert step["port_type"] == "frontend"
        assert step["wait_for_port"] is True
        assert step["wait_for_completion"] is False

    def test_neither_start_sh_nor_command_is_manual(self, db_session):
        _add_project(db_session, "bare", "/tmp/codehome/bare")
        apps = [_mk_app("bare", "/tmp/codehome/bare")]
        plan = build_plan(apps, db_session, read_start_sh=lambda a: None)
        assert plan.command_plans == []
        assert len(plan.manual) == 1
        assert plan.manual[0]["app_id"] == "bare"

    def test_missing_project_row_is_manual(self, db_session):
        apps = [_mk_app("ghost", "/tmp/codehome/ghost",
                        start_command=["python3", "api.py"])]
        plan = build_plan(apps, db_session, read_start_sh=lambda a: None)
        assert plan.command_plans == []
        assert "seed_projects_ledger" in plan.manual[0]["reason"]

    def test_default_registry_and_filesystem_paths(self, db_session, monkeypatch):
        """build_plan defaults: app_registry.get_all + on-disk start.sh."""
        from core import app_registry
        _add_project(db_session, "keno", "/nonexistent/keno")
        db_session.add(Port(port=5100, app_id="keno", port_type="api"))
        db_session.commit()
        monkeypatch.setattr(app_registry, "get_all", lambda: [
            _mk_app("keno", "/nonexistent/keno", expected_port=5100,
                    start_command=["python3", "api.py"])])

        plan = build_plan(session=db_session)   # no apps/read_start_sh given
        (cp,) = plan.command_plans
        assert cp.source == "registry"          # /nonexistent has no start.sh


# ── apply: allocation, contract, idempotency ───────────────────────────────────

class TestApplyEndToEnd:
    def test_apply_allocates_extra_port_and_resolves(self, db_session,
                                                     monkeypatch):
        _no_live_ports(monkeypatch)
        apps = _worldwise_setup(db_session)
        plan = build_plan(apps, db_session,
                          read_start_sh=lambda a: WORLDWISE_SH)
        result = apply_plan(plan, db_session)

        # Ledger: 5173 re-typed frontend; 8000 allocated as backend via the
        # ONE allocator (preferred port honoured).
        assert result["port_type_updated"] == [
            {"app_id": "worldwise", "port": 5173, "from": "api",
             "to": "frontend"}]
        assert result["allocated"][0]["allocated_port"] == 8000
        row = db_session.query(Port).filter_by(port=8000).one()
        assert (row.app_id, row.port_type) == ("worldwise", "backend")
        assert result["collisions_logged"] == 0
        assert result["commands_inserted"] == 2

        # The 13a contract: build_launch_command resolves with no leftovers.
        steps = launch_config.build_launch_command(
            "worldwise", session=db_session)
        assert steps[0]["args"] == [
            "backend.app.main:app", "--reload", "--port", "8000"]
        assert steps[0]["env"] == {"PYTHONPATH": f"{WORLDWISE_PATH}/backend"}
        assert steps[1]["args"][-1] == "5173"
        assert steps[1]["cwd"] == f"{WORLDWISE_PATH}/web"

    def test_preferred_port_unavailable_logs_and_retemplates(
            self, db_session, monkeypatch):
        # 8000 is busy on the machine -> allocator scans 5200..5999 instead.
        _no_live_ports(monkeypatch, in_use=lambda p: p == 8000)
        apps = _worldwise_setup(db_session)
        plan = build_plan(apps, db_session,
                          read_start_sh=lambda a: WORLDWISE_SH)
        result = apply_plan(plan, db_session)

        allocated = result["allocated"][0]["allocated_port"]
        assert allocated != 8000
        row = db_session.query(Port).filter_by(port=allocated).one()
        assert (row.app_id, row.port_type) == ("worldwise", "backend")

        # The mismatch is logged (backfill phase) …
        logged = db_session.query(PortCollisionLog).one()
        assert (logged.port, logged.app_id_1, logged.phase) == \
            (8000, "worldwise", "backfill")
        # … and the templated command resolves to the ALLOCATED port.
        steps = launch_config.build_launch_command(
            "worldwise", session=db_session)
        assert steps[0]["args"][-1] == str(allocated)

    def test_second_run_inserts_zero(self, db_session, monkeypatch):
        _no_live_ports(monkeypatch)
        apps = _worldwise_setup(db_session)
        first = apply_plan(build_plan(
            apps, db_session, read_start_sh=lambda a: WORLDWISE_SH), db_session)
        assert first["commands_inserted"] == 2

        plan2 = build_plan(apps, db_session,
                           read_start_sh=lambda a: WORLDWISE_SH)
        (cp2,) = plan2.command_plans
        assert cp2.status == "existing"
        assert plan2.port_type_updates == []      # 5173 already frontend
        assert plan2.allocations == []            # 8000 already in the ledger
        second = apply_plan(plan2, db_session)
        assert second["commands_inserted"] == 0
        assert second["apps_inserted"] == []
        assert db_session.query(AppCommand).filter_by(
            app_id="worldwise").count() == 2
