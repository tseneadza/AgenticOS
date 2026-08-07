"""Phase 13b tests — launch-config backfill script.

Runs against the real MySQL ``agenticos_test`` schema (see conftest.py) per
the MySQL-everywhere testing rule. Covers:

  * start.sh parser — worldwise-style 2-step script (cwd tracking, env
    capture, background detection, shell-variable substitution), housekeeping
    filtering, inline env, unrecognized-command notes. ``parse_start_sh`` is
    exercised directly here; note that under **Option D** ``build_plan`` no
    longer feeds start.sh through it (see below).
  * port_type inference — expected_port -> 'frontend', headless services stay
    'api', uk_app_port_type conflicts skipped, idempotent second pass
  * Option D — an app that ships a ``start.sh`` is planned as a single
    ``bash start.sh`` step (source ``"start.sh"``), NOT parsed into granular
    steps. The script self-manages venv/deps/child procs; process_manager
    injects ``PORT`` and group-kills on stop. So the backfill does no
    interpreter/venv templating, no per-literal port allocation, and no
    script-internal port cross-check for these apps.
  * no-start.sh fallback to the registry start_command (still a single step,
    templated through {app_path}/{venv_path}/{<type>_port})
  * apply end-to-end — a start.sh app inserts ONE command, allocates no extra
    port, re-types its expected_port ledger row, and ``build_launch_command``
    resolves it to ``bash start.sh``; second run inserts 0 (idempotent).

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

    def test_venv_activation_captured_bare_python(self):
        # Calculator-style: `source .venv/bin/activate` is consumed (no step of
        # its own) but its venv dir rides along on the following bare `python`.
        steps, _ = parse_start_sh(
            "source .venv/bin/activate\npython src/server.py\n")
        assert len(steps) == 1
        assert steps[0].command == "python"
        assert steps[0].args == ["src/server.py"]
        assert steps[0].venv == ".venv"

    def test_venv_activation_dot_form_and_alt_dir_name(self):
        # `.` (dot) is equivalent to `source`; venv dir name is not fixed.
        steps, _ = parse_start_sh(". venv/bin/activate\npython3 app.py\n")
        assert len(steps) == 1
        assert steps[0].command == "python3"
        assert steps[0].venv == "venv"

    def test_venv_activation_quoted_path(self):
        steps, _ = parse_start_sh(
            'source ".venv/bin/activate"\npython app.py\n')
        assert steps[0].venv == ".venv"

    def test_no_activation_leaves_venv_none(self):
        # Regression: without an activation line, venv stays None (unchanged
        # behavior for the vast majority of start.sh scripts).
        steps, _ = parse_start_sh("python app.py\n")
        assert steps[0].venv is None

    def test_venv_activation_does_not_special_case_non_python(self):
        # The parser only records the venv dir — it does NOT decide what to
        # rewrite. A non-python command after activation keeps its own name;
        # the plan builder (not the parser) is what compiles a bare `python`.
        steps, _ = parse_start_sh(
            "source .venv/bin/activate\nuvicorn main:app --port 5100\n")
        assert steps[0].command == "uvicorn"
        assert steps[0].venv == ".venv"


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

class TestOptionD:
    """A start.sh app is planned as a single ``bash start.sh`` step — the
    script self-manages venv/deps/child procs (Option D)."""

    def test_worldwise_start_sh_plans_bash_start_sh(self, db_session):
        apps = _worldwise_setup(db_session)
        plan = build_plan(apps, db_session,
                          read_start_sh=lambda app: WORLDWISE_SH)

        (cp,) = plan.command_plans
        assert cp.status == "planned" and cp.source == "start.sh"
        assert any("Option D" in n for n in cp.notes)

        # The whole (multi-process) script collapses to ONE bash step; the
        # backfill does not parse it, so no per-step uvicorn/npm rows appear.
        (step,) = cp.steps
        assert step["command"] == "bash"
        assert step["args"] == ["start.sh"]
        assert step["working_directory"] == "."
        assert step["environment_json"] is None
        assert step["wait_for_completion"] is False
        assert step["wait_for_port"] is True
        # expected_port (5173) is re-typed to frontend, so the one step waits
        # on the frontend port.
        assert step["port_type"] == "frontend"
        assert step["port_variable_name"] == "frontend_port"

        # No script parsing => no extra-port allocation, no collision check.
        assert plan.allocations == []
        assert plan.collisions == []
        # Ledger row 5173 (currently 'api') is still re-typed to frontend
        # (port_type inference is independent of the launch-command plan).
        assert plan.port_type_updates == [{"app_id": "worldwise", "port": 5173,
                                           "from": "api", "to": "frontend"}]

    def test_start_sh_app_ignores_script_internals(self, db_session):
        # Option D contract: venv/deps are the SCRIPT's concern. Even when the
        # project has an explicit venv_path and the script invokes a venv
        # interpreter directly, the plan is just `bash start.sh` — the backfill
        # does no interpreter/venv templating for start.sh apps.
        _add_project(db_session, "withvenv", "/tmp/codehome/withvenv",
                     venv_path="/tmp/codehome/withvenv/.venv")
        db_session.add(Port(port=5601, app_id="withvenv", port_type="api"))
        db_session.commit()

        script = ("#!/bin/bash\n"
                  "source .venv/bin/activate\n"
                  "/tmp/codehome/withvenv/.venv/bin/python api.py\n")
        apps = [_mk_app("withvenv", "/tmp/codehome/withvenv", 5601)]
        plan = build_plan(apps, db_session, read_start_sh=lambda a: script)

        (cp,) = plan.command_plans
        assert cp.source == "start.sh"
        (step,) = cp.steps
        assert step["command"] == "bash"
        assert step["args"] == ["start.sh"]


# ── collision path ─────────────────────────────────────────────────────────────

class TestCollisions:
    def test_start_sh_internal_port_not_cross_checked(
            self, db_session, monkeypatch):
        # Under Option D the backfill no longer parses start.sh, so a port the
        # SCRIPT happens to bind — even one owned by another app in the ledger —
        # is NOT cross-checked and NOT logged as a collision. The script owns
        # its own ports; the backfill only records the expected_port ledger row.
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

        assert plan.collisions == []
        assert plan.allocations == []
        # The plan is the opaque bash step — the script's 5112 never surfaces.
        (step,) = plan.command_plans[0].steps
        assert step["command"] == "bash" and step["args"] == ["start.sh"]

        result = apply_plan(plan, db_session)
        assert result["collisions_logged"] == 0
        assert db_session.query(PortCollisionLog).count() == 0
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
    def test_apply_inserts_single_bash_start_sh_command(self, db_session,
                                                        monkeypatch):
        _no_live_ports(monkeypatch)
        apps = _worldwise_setup(db_session)
        plan = build_plan(apps, db_session,
                          read_start_sh=lambda a: WORLDWISE_SH)
        result = apply_plan(plan, db_session)

        # 5173 re-typed frontend; Option D allocates NO extra port and inserts
        # exactly ONE command (the whole script is one opaque step).
        assert result["port_type_updated"] == [
            {"app_id": "worldwise", "port": 5173, "from": "api",
             "to": "frontend"}]
        assert result["allocated"] == []
        assert result["collisions_logged"] == 0
        assert result["commands_inserted"] == 1

        # The 13a contract still holds: build_launch_command resolves cleanly.
        steps = launch_config.build_launch_command(
            "worldwise", session=db_session)
        assert len(steps) == 1
        assert steps[0]["command"] == "bash"
        assert steps[0]["args"] == ["start.sh"]
        assert steps[0]["cwd"] == WORLDWISE_PATH        # working_directory "."
        assert steps[0]["port_type"] == "frontend"
        assert steps[0]["port"] == 5173

    def test_second_run_inserts_zero(self, db_session, monkeypatch):
        _no_live_ports(monkeypatch)
        apps = _worldwise_setup(db_session)
        first = apply_plan(build_plan(
            apps, db_session, read_start_sh=lambda a: WORLDWISE_SH), db_session)
        assert first["commands_inserted"] == 1

        plan2 = build_plan(apps, db_session,
                           read_start_sh=lambda a: WORLDWISE_SH)
        (cp2,) = plan2.command_plans
        assert cp2.status == "existing"
        assert plan2.port_type_updates == []      # 5173 already frontend
        assert plan2.allocations == []
        second = apply_plan(plan2, db_session)
        assert second["commands_inserted"] == 0
        assert second["apps_inserted"] == []
        assert db_session.query(AppCommand).filter_by(
            app_id="worldwise").count() == 1
