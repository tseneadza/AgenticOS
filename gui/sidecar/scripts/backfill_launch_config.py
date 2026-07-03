"""Phase 13b — Launch-config backfill: ledger port_types + app_commands rows.

Populates the Phase 13a launch tables from what already exists on disk:

  * ``ports.port_type`` for the pre-existing ledger rows (all defaulted to
    ``'api'`` by the 13a migration) is inferred from the live app registry.
  * ``app_commands`` rows are created per app — parsed from the app's
    ``start.sh`` when one exists, otherwise from the registry's
    ``start_command`` (the app.json ``web.command`` list).
  * Ports discovered in start.sh are cross-checked against the ledger;
    mismatches go to ``port_collision_log`` and are never force-inserted.

Locked decisions (with Tony, 2026-07-03):

  1. **port_type semantics** — ``frontend`` = the port a user opens in a
     browser, even when FastAPI/Flask serves the UI from it (single-port apps
     like keno/weather are ``frontend``); ``backend`` = an API-only port
     behind a separate frontend (worldwise's uvicorn on :8000); ``api`` =
     headless services with no browser UI (agenticos-sidecar :5130,
     dreamcatcher-backend :5111 — no registry row, left untouched).
     Inference rule: a ledger row whose port equals the owning app's registry
     ``expected_port`` is the browser-facing port → ``frontend``.
  2. **No-start.sh apps** use the registry ``start_command`` (app.json
     ``web.command``) as a single launch step, working_directory = app root,
     port_type = the app's browser-facing port type.
  3. **start.sh-only ports** (in the script but in no ledger row, e.g.
     worldwise's backend :8000) are allocated on ``--apply`` through the ONE
     allocator — ``project_manager.allocate_port(app_id, preferred_port=...)``
     — then stamped with their port_type. If the preferred port is
     unavailable the allocator picks another; that is logged to
     ``port_collision_log`` (phase='backfill') and the command is templated
     with the port-type variable, so it resolves to the ALLOCATED port.

Contracts honoured:

  * Templating uses the exact variables ``launch_config.build_launch_command``
    resolves — ``{app_path}``, ``{venv_path}`` (only when
    ``projects.venv_path`` is set) and ``{<port_type>_port}``. No plan ever
    stores a token that would be unresolvable at launch time; ports that
    collide with another app stay as literals.
  * Idempotent — apps that already have ``app_commands`` rows are reported as
    'existing' and skipped; port_type updates are no-ops on a second run.
  * ``--dry-run`` is the DEFAULT (prints the full plan, writes nothing);
    ``--apply`` commits. Exit code is 0 even when collisions are found —
    they are logged by design; nonzero only on real errors.

Run:  .venv/bin/python -m gui.sidecar.scripts.backfill_launch_config          # dry run
      .venv/bin/python -m gui.sidecar.scripts.backfill_launch_config --apply  # commit

The core logic is pure planning over ``(apps, session)`` — see
``build_plan`` / ``apply_plan`` — so tests can drive it with injected
registry entries and an injected ``read_start_sh`` callable (no real
~/Codehome apps or filesystem needed).
"""
from __future__ import annotations

import argparse
import logging
import posixpath
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# ── start.sh parsing ──────────────────────────────────────────────────────────

#: Sentinel for "the app root" while parsing (SCRIPT_DIR-style variables).
_ROOT_SENTINEL = "__AGENTIC_APP_ROOT__"

#: Command basenames that count as real launch steps.
_LAUNCH_COMMANDS: frozenset[str] = frozenset({
    "uvicorn", "gunicorn", "uv", "flask", "python", "python3", "streamlit",
    "npm", "npx", "yarn", "pnpm", "node", "next", "vite", "deno", "bun",
})

#: Launch commands that usually serve the browser-facing port.
_FRONTENDISH_COMMANDS: frozenset[str] = frozenset({
    "npm", "npx", "yarn", "pnpm", "node", "next", "vite", "deno", "bun",
})

#: Housekeeping commands — never launch steps.
_HOUSEKEEPING_COMMANDS: frozenset[str] = frozenset({
    "echo", "printf", "sleep", "lsof", "kill", "pkill", "killall", "xargs",
    "trap", "wait", "set", "exit", "true", "false", "source", ".", "mkdir",
    "rm", "cp", "mv", "touch", "cat", "test", "[", "open", "curl", "which",
    "command", "read", "shift", "clear", "date", "chmod", "ln",
})

#: Shell control-flow keywords — structural, never commands.
_CONTROL_KEYWORDS: frozenset[str] = frozenset({
    "if", "then", "else", "elif", "fi", "for", "while", "until", "do",
    "done", "case", "esac", "function", "return", "break", "continue",
    "{", "}",
})

_ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_VAR_RE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
_FUNC_DEF_RE = re.compile(r"^(?:function\s+[\w-]+|[\w-]+\s*\(\s*\))\s*\{?\s*$")
_PORT_EQ_RE = re.compile(r"^(?:--port|--listen-port|--server-port|-p)=?(\d{4,5})$")
_HOST_PORT_RE = re.compile(r":(\d{4,5})$")
_PORT_FLAGS: frozenset[str] = frozenset({
    "--port", "-p", "-P", "--listen-port", "--server-port", "-b", "--bind",
})


@dataclass
class ParsedStep:
    """One launch step extracted from start.sh (pre-templating)."""

    command: str
    args: list[str] = field(default_factory=list)
    cwd: str = "."                                # relative to the app root
    env: dict[str, str] = field(default_factory=dict)
    background: bool = False                      # ran with a trailing ``&``
    ports: list[int] = field(default_factory=list)  # literal ports found


def _valid_port(value: str) -> int | None:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None
    return port if 1024 <= port <= 65535 else None


def _extract_ports(args: list[str], env: dict[str, str]) -> list[int]:
    """Literal ports referenced by a step's args / PORT-ish env values."""
    found: list[int] = []

    def add(value: str) -> None:
        port = _valid_port(value)
        if port is not None and port not in found:
            found.append(port)

    prev: str | None = None
    for tok in args:
        m = _PORT_EQ_RE.match(tok)
        if m:
            add(m.group(1))
        elif prev in _PORT_FLAGS and re.fullmatch(r"\d{4,5}", tok):
            add(tok)
        elif not tok.startswith("-"):
            m2 = _HOST_PORT_RE.search(tok)
            if m2:
                add(m2.group(1))
        prev = tok

    for key, value in env.items():
        if "PORT" in key.upper() and re.fullmatch(r"\d{4,5}", str(value)):
            add(value)
    return found


class _StartShParser:
    """Line-oriented start.sh parser — commands, cwd, env, background flags.

    Deliberately conservative: only allow-listed launch commands become
    steps; everything unrecognized is either housekeeping (silently skipped)
    or reported in ``notes`` for manual review. Shell variables assigned at
    the top of the script (``BACKEND_PORT=8000``) are substituted into later
    lines; ``$(dirname "$0")`` / ``$SCRIPT_DIR`` style values are treated as
    the app root.
    """

    def __init__(self, app_path: str | None = None):
        self.root = (app_path or ".").rstrip("/") or "/"
        self.variables: dict[str, str] = {}
        self.exported: dict[str, str] = {}
        self.cwd = "."
        self.steps: list[ParsedStep] = []
        self.notes: list[str] = []
        self._in_function = False
        self._brace_depth = 0

    # -- helpers ---------------------------------------------------------

    def _sub(self, token: str, *, keep_sentinel: bool = False) -> str:
        """Substitute known ``$VAR``/``${VAR}`` occurrences in *token*."""
        out = _VAR_RE.sub(
            lambda m: self.variables.get(m.group(1), m.group(0)), token)
        if not keep_sentinel:
            out = out.replace(_ROOT_SENTINEL, self.root)
        return out

    def _assign(self, name: str, value: str, *, export: bool) -> None:
        resolved = self._sub(value, keep_sentinel=True)
        self.variables[name] = resolved
        if export:
            self.exported[name] = resolved.replace(_ROOT_SENTINEL, self.root)

    def _cd(self, target: str) -> None:
        t = self._sub(target, keep_sentinel=True)
        if t.startswith(_ROOT_SENTINEL):          # root-relative
            rel = t[len(_ROOT_SENTINEL):].lstrip("/")
            self.cwd = posixpath.normpath(rel) if rel else "."
            return
        if "$" in t:
            self.notes.append(f"cd with unresolved variable ignored: {target!r}")
            return
        if self.root != "." and t.rstrip("/") == self.root:
            self.cwd = "."
            return
        if self.root != "." and t.startswith(self.root + "/"):
            self.cwd = posixpath.normpath(t[len(self.root) + 1:]) or "."
            return
        if t.startswith("/"):
            self.notes.append(f"cd to path outside app root kept absolute: {t}")
            self.cwd = t
            return
        self.cwd = posixpath.normpath(posixpath.join(self.cwd, t)) or "."

    # -- line/segment processing ------------------------------------------

    def parse(self, text: str) -> tuple[list[ParsedStep], list[str]]:
        # Join backslash line-continuations first.
        lines: list[str] = []
        buf = ""
        for raw in text.split("\n"):
            if raw.rstrip().endswith("\\"):
                buf += raw.rstrip()[:-1] + " "
                continue
            lines.append(buf + raw)
            buf = ""
        if buf:
            lines.append(buf)

        for raw in lines:
            self._line(raw.strip())
        return self.steps, self.notes

    def _line(self, line: str) -> None:
        if not line or line.startswith("#"):
            return

        # Function bodies (cleanup() { ... }) are housekeeping — skip whole.
        if self._in_function:
            self._brace_depth += line.count("{") - line.count("}")
            if self._brace_depth <= 0:
                self._in_function = False
            return
        if _FUNC_DEF_RE.match(line):
            self._brace_depth = line.count("{") - line.count("}")
            self._in_function = self._brace_depth > 0 or "{" not in line
            return

        first = line.split(None, 1)[0]
        if first in _CONTROL_KEYWORDS or first == "trap":
            return

        # Command substitutions can't be tokenized safely — special-case the
        # common shapes (SCRIPT_DIR=$(dirname "$0"), cd "$(dirname "$0")").
        if "$(" in line or "`" in line:
            export = line.startswith("export ")
            work = line[len("export "):].strip() if export else line
            m = _ASSIGN_RE.match(work)
            if m and not re.search(r"\s", work.split("=", 1)[0]):
                name, value = m.group(1), m.group(2)
                if "dirname" in value or "pwd" in value:
                    self._assign(name, _ROOT_SENTINEL, export=export)
                else:
                    self.notes.append(
                        f"variable {name} uses command substitution — skipped")
                return
            if first == "cd" and ("dirname" in line or "pwd" in line):
                self.cwd = "."
                return
            self.notes.append(f"line with command substitution skipped: {line!r}")
            return

        background = False
        stripped = line.rstrip()
        if stripped.endswith("&") and not stripped.endswith("&&"):
            background = True
            stripped = stripped[:-1].rstrip()

        segments = re.split(r"\s*(?:&&|;)\s*", stripped)
        for idx, seg in enumerate(segments):
            if seg:
                self._segment(seg, background and idx == len(segments) - 1)

    def _segment(self, seg: str, background: bool) -> None:
        try:
            tokens = shlex.split(seg, posix=True)
        except ValueError:
            self.notes.append(f"unparseable line skipped: {seg!r}")
            return
        if not tokens:
            return

        # Cut at pipes / redirections — everything after is plumbing.
        cut: list[str] = []
        for tok in tokens:
            if tok in ("|", "||") or tok.startswith((">", "<", "2>", "&>")):
                break
            cut.append(tok)
        tokens = cut
        if not tokens:
            return

        if tokens[0] == "export":
            for tok in tokens[1:]:
                m = _ASSIGN_RE.match(self._sub(tok, keep_sentinel=True))
                if m:
                    self._assign(m.group(1), m.group(2), export=True)
            return
        if all(_ASSIGN_RE.match(t) for t in tokens):   # variable-only line
            for tok in tokens:
                m = _ASSIGN_RE.match(tok)
                self._assign(m.group(1), m.group(2), export=False)
            return
        if tokens[0] == "cd":
            if len(tokens) > 1:
                self._cd(tokens[1])
            return

        tokens = [self._sub(t) for t in tokens]
        while tokens and tokens[0] in ("nohup", "exec"):
            tokens = tokens[1:]
        if not tokens:
            return

        # Inline env prefix: KEY=val [KEY=val ...] command args.
        inline_env: dict[str, str] = {}
        while tokens and (m := _ASSIGN_RE.match(tokens[0])):
            inline_env[m.group(1)] = m.group(2)
            tokens = tokens[1:]
        if not tokens:
            return

        command = tokens[0]
        base = posixpath.basename(command)
        if base in _HOUSEKEEPING_COMMANDS or command in _HOUSEKEEPING_COMMANDS:
            return
        if base not in _LAUNCH_COMMANDS:
            self.notes.append(f"skipped unrecognized command: {seg.strip()!r}")
            return

        env = {**self.exported, **inline_env}
        args = tokens[1:]
        # Port scan: args + INLINE env only. Script-level `export`ed PORT-ish
        # vars are references to OTHER apps (e.g. agentic's HUB_PORT=8085
        # pointing at the hub), not ports this step binds — feeding them to
        # the cross-check produced false collisions. A port this app truly
        # binds shows up in args after variable substitution anyway.
        self.steps.append(ParsedStep(
            command=command, args=args, cwd=self.cwd, env=env,
            background=background, ports=_extract_ports(args, inline_env),
        ))


def parse_start_sh(
    text: str, app_path: str | None = None,
) -> tuple[list[ParsedStep], list[str]]:
    """Parse *text* (a start.sh) into launch steps + reviewer notes."""
    return _StartShParser(app_path).parse(text)


# ── templating ────────────────────────────────────────────────────────────────

def _template(value: str, app_path: str | None, venv_path: str | None,
              port_vars: dict[int, str]) -> str:
    """Rewrite *value* with the launch_config template variables.

    venv before app_path (the venv usually lives under the app root); ports
    with digit-boundary guards so 8000 never matches inside 18000.
    """
    out = str(value)
    if venv_path:
        out = out.replace(venv_path.rstrip("/"), "{venv_path}")
    if app_path and app_path != ".":
        out = out.replace(app_path.rstrip("/"), "{app_path}")
    for port, port_type in port_vars.items():
        out = re.sub(
            rf"(?<!\d){port}(?!\d)", "{" + f"{port_type}_port" + "}", out)
    return out


# ── planning ─────────────────────────────────────────────────────────────────

@dataclass
class CommandPlan:
    """Planned app_commands rows for one app."""

    app_id: str
    steps: list[dict] = field(default_factory=list)   # AppCommand kwargs
    status: str = "planned"                           # planned | existing
    source: str = ""                                  # start.sh | registry
    notes: list[str] = field(default_factory=list)


@dataclass
class BackfillPlan:
    """Everything the backfill would do — computed without writing."""

    port_type_updates: list[dict] = field(default_factory=list)
    port_type_skips: list[dict] = field(default_factory=list)
    command_plans: list[CommandPlan] = field(default_factory=list)
    allocations: list[dict] = field(default_factory=list)
    collisions: list[dict] = field(default_factory=list)
    manual: list[dict] = field(default_factory=list)


def plan_port_type_updates(apps: list[dict], session) -> tuple[list, list, dict]:
    """Infer real port_types for the existing ledger rows.

    Rule (locked): a row whose port equals the owning app's registry
    ``expected_port`` is the browser-facing port → 'frontend'. Rows owned by
    ids not in the registry (headless services) keep 'api'. Updates that
    would violate uk_app_port_type are skipped and reported.

    Returns ``(updates, skips, intended)`` where *intended* is the post-plan
    ``{app_id: {port: port_type}}`` map used by command planning.
    """
    from gui.sidecar.models import Port

    by_id = {a.get("id"): a for a in apps if a.get("id")}
    rows = session.query(Port).order_by(Port.port).all()

    intended: dict[str, dict[int, str]] = {}
    for row in rows:
        intended.setdefault(row.app_id, {})[row.port] = row.port_type

    updates: list[dict] = []
    skips: list[dict] = []
    for row in rows:
        app = by_id.get(row.app_id)
        if app is None:
            continue  # headless service (sidecar :5130 etc.) — keep 'api'
        if app.get("expected_port") != row.port:
            continue  # not the browser-facing port — leave as-is
        if row.port_type == "frontend":
            continue  # already correct (idempotent re-run)
        change = {"app_id": row.app_id, "port": row.port,
                  "from": row.port_type, "to": "frontend"}
        other_types = {t for p, t in intended[row.app_id].items()
                       if p != row.port}
        if "frontend" in other_types:
            skips.append({**change, "reason":
                          "uk_app_port_type: app already has a frontend port"})
            continue
        updates.append(change)
        intended[row.app_id][row.port] = "frontend"
    return updates, skips, intended


def _pick_port_type(command: str, used: set[str]) -> str | None:
    """Choose a port_type for a start.sh-only port, respecting the UK."""
    base = posixpath.basename(command)
    if base in _FRONTENDISH_COMMANDS:
        preference = ("frontend", "backend", "api", "admin", "other")
    else:
        preference = ("backend", "api", "admin", "other")
    return next((t for t in preference if t not in used), None)


def _wait_flags(step: ParsedStep, has_port_type: bool, is_last: bool) -> tuple[bool, bool]:
    """(wait_for_completion, wait_for_port) for a parsed step.

    Servers (steps with a port) never block; a foreground non-final step
    without a port is a setup step (migrations, npm install) and blocks.
    """
    if has_port_type:
        return False, True
    return (not step.background and not is_last), False


def _plan_from_steps(app: dict, project, steps: list[ParsedStep],
                     notes: list[str], intended: dict, port_owner: dict,
                     allocations: list[dict], collisions: list[dict]) -> CommandPlan:
    app_id = app["id"]
    own: dict[int, str] = dict(intended.get(app_id, {}))
    used_types: set[str] = set(own.values())
    step_types: list[str | None] = []

    # Pass 1 — resolve every literal port: own ledger row, foreign ledger row
    # (collision) or brand new (planned allocation via the ONE allocator).
    for i, ps in enumerate(steps, start=1):
        step_type: str | None = None
        for port in ps.ports:
            if port in own:
                step_type = step_type or own[port]
            elif port in port_owner:
                owner = port_owner[port]
                collisions.append({
                    "port": port, "app_id": app_id, "owner": owner,
                    "notes": (f"start.sh for {app_id!r} step {i} uses port "
                              f"{port}, owned by {owner!r} in the ledger — "
                              "left literal, not allocated"),
                })
                notes.append(f"step {i}: port {port} collides with "
                             f"{owner!r} — left literal")
            else:
                port_type = _pick_port_type(ps.command, used_types)
                if port_type is None:
                    notes.append(f"step {i}: port {port} has no free "
                                 "port_type slot — left literal")
                    continue
                used_types.add(port_type)
                own[port] = port_type
                allocations.append({"app_id": app_id, "preferred_port": port,
                                    "port_type": port_type, "step": i})
                step_type = step_type or port_type
        step_types.append(step_type)

    # If no step claimed a type but the app has a browser-facing port, pin it
    # to the final step (the foreground server) so launches wait on it.
    if not any(step_types) and own:
        expected = app.get("expected_port")
        fallback = own.get(expected) if expected in own else (
            next(iter(own.values())) if len(own) == 1 else None)
        if fallback:
            step_types[-1] = fallback
            notes.append("no step declared a port literal — final step "
                         f"pinned to the app's {fallback!r} port")

    # Pass 2 — template every step with the full own-port map (a backend step
    # may reference the frontend port in CORS args and vice versa).
    port_vars = dict(own)
    app_path = project.path
    venv_path = project.venv_path
    rows: list[dict] = []
    for i, (ps, step_type) in enumerate(zip(steps, step_types), start=1):
        wait_done, wait_port = _wait_flags(ps, step_type is not None,
                                           is_last=(i == len(steps)))
        rows.append(dict(
            app_id=app_id,
            step_order=i,
            command=_template(ps.command, app_path, venv_path, {}),
            args=[_template(a, app_path, venv_path, port_vars)
                  for a in ps.args],
            working_directory=ps.cwd,
            port_type=step_type,
            port_variable_name=f"{step_type}_port" if step_type else None,
            environment_json={
                k: _template(v, app_path, venv_path, port_vars)
                for k, v in ps.env.items()
            } or None,
            wait_for_completion=wait_done,
            wait_for_port=wait_port,
        ))
    return CommandPlan(app_id=app_id, steps=rows, status="planned",
                       source="start.sh", notes=notes)


def _plan_from_registry(app: dict, project, start_command: list,
                        intended: dict) -> CommandPlan:
    """Single-step plan from the registry's start_command (no start.sh)."""
    app_id = app["id"]
    own = intended.get(app_id, {})
    expected = app.get("expected_port")

    step_type: str | None = None
    port_vars: dict[int, str] = {}
    if expected in own:
        step_type = own[expected]
        port_vars[expected] = step_type
    elif len(own) == 1:
        (port, port_type), = own.items()
        step_type = port_type
        port_vars[port] = port_type

    command, *args = [str(t) for t in start_command]
    row = dict(
        app_id=app_id,
        step_order=1,
        command=_template(command, project.path, project.venv_path, {}),
        args=[_template(a, project.path, project.venv_path, port_vars)
              for a in args],
        working_directory=".",
        port_type=step_type,
        port_variable_name=f"{step_type}_port" if step_type else None,
        environment_json=None,
        wait_for_completion=False,
        wait_for_port=bool(step_type),
    )
    return CommandPlan(app_id=app_id, steps=[row], status="planned",
                       source="registry", notes=[])


def _default_read_start_sh(app: dict) -> str | None:
    """Read <app_path>/start.sh from disk; None when absent/unreadable."""
    app_path = app.get("app_path")
    if not app_path:
        return None
    path = Path(app_path) / "start.sh"
    try:
        return path.read_text() if path.is_file() else None
    except OSError as exc:  # noqa: BLE001
        log.warning("could not read %s: %s", path, exc)
        return None


def build_plan(apps: list[dict] | None = None, session=None,
               read_start_sh=None) -> BackfillPlan:
    """Compute the full backfill plan — pure, writes nothing.

    Args:
        apps: registry entries (default: ``core.app_registry.get_all()``).
        session: SQLAlchemy session (required for ledger/projects queries).
        read_start_sh: ``callable(app) -> str | None`` — injectable for tests.
    """
    from gui.sidecar.models import AppCommand, Port, Project

    if apps is None:
        from core import app_registry
        apps = app_registry.get_all()
    if read_start_sh is None:
        read_start_sh = _default_read_start_sh

    plan = BackfillPlan()
    updates, skips, intended = plan_port_type_updates(apps, session)
    plan.port_type_updates = updates
    plan.port_type_skips = skips

    existing_cmd_apps = {
        r[0] for r in session.query(AppCommand.app_id).distinct().all()}
    port_owner = {row.port: row.app_id for row in session.query(Port).all()}
    projects = {p.id: p for p in session.query(Project).all()}

    for app in apps:
        app_id = app.get("id")
        if not app_id:
            continue
        if app_id in existing_cmd_apps:
            plan.command_plans.append(CommandPlan(
                app_id=app_id, status="existing",
                notes=["app_commands rows already present"]))
            continue
        project = projects.get(app_id)
        if project is None:
            plan.manual.append({
                "app_id": app_id,
                "reason": "no projects ledger row — run seed_projects_ledger first"})
            continue

        text = read_start_sh(app)
        notes: list[str] = []
        if text is not None:
            steps, notes = parse_start_sh(text, app_path=project.path)
            if steps:
                plan.command_plans.append(_plan_from_steps(
                    app, project, steps, notes, intended, port_owner,
                    plan.allocations, plan.collisions))
                continue
            notes.append("start.sh present but no launch commands recognized")

        start_command = app.get("start_command") or []
        if start_command:
            cp = _plan_from_registry(app, project, start_command, intended)
            cp.notes = notes + cp.notes
            plan.command_plans.append(cp)
        else:
            plan.manual.append({
                "app_id": app_id,
                "reason": ("no usable start.sh launch commands and empty "
                           "registry start_command — manual app_commands "
                           "entry needed"),
                "notes": notes,
            })
    return plan


# ── applying ─────────────────────────────────────────────────────────────────

def apply_plan(plan: BackfillPlan, session) -> dict:
    """Write the plan: port_type updates, collision log, allocations, inserts.

    Collisions are LOGGED, never force-resolved (that is the design — exit
    code stays 0). uk_app_port_type violations are reported and skipped,
    never raised.
    """
    from sqlalchemy.exc import IntegrityError

    from gui.sidecar.launch_config import log_collision
    from gui.sidecar.models import AppCommand, Port
    from gui.sidecar.project_manager import allocate_port

    result = {
        "port_type_updated": [],
        "port_type_skipped": list(plan.port_type_skips),
        "allocated": [],
        "collisions_logged": 0,
        "apps_inserted": [],
        "commands_inserted": 0,
        "errors": [],
    }

    # 1. port_type updates on existing ledger rows.
    for upd in plan.port_type_updates:
        row = session.get(Port, upd["port"])
        if row is None or row.app_id != upd["app_id"]:
            result["port_type_skipped"].append(
                {**upd, "reason": "ledger row changed since planning"})
            continue
        row.port_type = upd["to"]
        try:
            session.commit()
            result["port_type_updated"].append(upd)
        except IntegrityError as exc:
            session.rollback()
            result["port_type_skipped"].append(
                {**upd, "reason": f"uk_app_port_type violation: {exc.orig}"})
            log.warning("port_type update skipped (%s:%s): %s",
                        upd["app_id"], upd["port"], exc)

    # 2. Cross-check collisions → port_collision_log (never inserted).
    for c in plan.collisions:
        log_collision(c["port"], c["app_id"], c["owner"], phase="backfill",
                      notes=c["notes"], session=session)
        result["collisions_logged"] += 1

    # 3. start.sh-only ports → the ONE allocator, then stamp the port_type.
    for alloc in plan.allocations:
        try:
            got = allocate_port(alloc["app_id"],
                                preferred_port=alloc["preferred_port"],
                                session=session)
        except RuntimeError as exc:
            result["errors"].append(
                f"port allocation failed for {alloc['app_id']}: {exc}")
            continue
        row = session.query(Port).filter_by(port=got).one()
        row.port_type = alloc["port_type"]
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            result["errors"].append(
                f"could not stamp port_type on {got} for "
                f"{alloc['app_id']}: {exc.orig}")
            continue
        if got != alloc["preferred_port"]:
            log_collision(
                alloc["preferred_port"], alloc["app_id"], None,
                phase="backfill",
                notes=(f"start.sh literal port {alloc['preferred_port']} was "
                       f"unavailable; allocator assigned {got} "
                       f"({alloc['port_type']}) — command is templated with "
                       f"{{{alloc['port_type']}_port}} so it resolves to {got}"),
                session=session)
            result["collisions_logged"] += 1
        result["allocated"].append({**alloc, "allocated_port": got})

    # 4. app_commands inserts (idempotent — re-checked at write time).
    for cp in plan.command_plans:
        if cp.status != "planned" or not cp.steps:
            continue
        if session.query(AppCommand).filter_by(app_id=cp.app_id).count():
            cp.status = "existing"
            continue
        for row in cp.steps:
            session.add(AppCommand(**row))
        try:
            session.commit()
            result["apps_inserted"].append(cp.app_id)
            result["commands_inserted"] += len(cp.steps)
        except IntegrityError as exc:
            session.rollback()
            result["errors"].append(
                f"app_commands insert failed for {cp.app_id}: {exc.orig}")
    return result


# ── summary output ────────────────────────────────────────────────────────────

def render_summary(plan: BackfillPlan, result: dict | None = None) -> str:
    """Human summary in the doc's §Backfill Process step-6 style."""
    apply_mode = result is not None
    lines: list[str] = []
    lines.append("=" * 68)
    lines.append("Launch-config backfill — "
                 + ("APPLIED" if apply_mode else "DRY RUN (use --apply to write)"))
    lines.append("=" * 68)

    # port_type updates
    updates = result["port_type_updated"] if apply_mode else plan.port_type_updates
    verb = "updated" if apply_mode else "planned"
    lines.append(f"\nPort-type updates ({verb}): {len(updates)}")
    for u in updates:
        lines.append(f"  {u['app_id']:<24} {u['port']:>5}  "
                     f"{u['from']} -> {u['to']}")
    skips = result["port_type_skipped"] if apply_mode else plan.port_type_skips
    for s in skips:
        lines.append(f"  SKIPPED {s['app_id']}:{s['port']} — {s['reason']}")

    # app_commands
    planned = [cp for cp in plan.command_plans if cp.status == "planned"]
    existing = [cp for cp in plan.command_plans if cp.status == "existing"]
    total_steps = sum(len(cp.steps) for cp in planned)
    verb = "inserted" if apply_mode else "planned"
    if apply_mode:
        lines.append(f"\napp_commands: {result['commands_inserted']} rows "
                     f"inserted across {len(result['apps_inserted'])} apps"
                     f" ({len(existing)} apps already had rows)")
    else:
        lines.append(f"\napp_commands ({verb}): {total_steps} rows across "
                     f"{len(planned)} apps ({len(existing)} existing, skipped)")
    for cp in planned:
        step_word = "step" if len(cp.steps) == 1 else "steps"
        lines.append(f"  {cp.app_id:<24} {len(cp.steps)} {step_word:<6} "
                     f"[{cp.source}]")
        for note in cp.notes:
            lines.append(f"      note: {note}")
    for cp in existing:
        lines.append(f"  {cp.app_id:<24} existing — skipped")

    # allocations
    allocs = result["allocated"] if apply_mode else plan.allocations
    label = ("Ports allocated (via project_manager.allocate_port)"
             if apply_mode else "Planned port allocations (on --apply, via "
             "project_manager.allocate_port)")
    lines.append(f"\n{label}: {len(allocs)}")
    for a in allocs:
        got = a.get("allocated_port")
        suffix = (f" -> allocated {got}" if got is not None
                  and got != a["preferred_port"] else "")
        lines.append(f"  {a['app_id']:<24} preferred {a['preferred_port']} "
                     f"({a['port_type']}){suffix}")

    # collisions
    logged = result["collisions_logged"] if apply_mode else len(plan.collisions)
    lines.append(f"\nCollisions ({'logged to port_collision_log' if apply_mode else 'would be logged on --apply'}): {logged}")
    for c in plan.collisions:
        lines.append(f"  port {c['port']}: {c['app_id']} vs {c['owner']}")

    # edge cases
    lines.append(f"\nEdge cases — manual entry needed: {len(plan.manual)}")
    for m in plan.manual:
        lines.append(f"  {m['app_id']:<24} {m['reason']}")

    if apply_mode and result["errors"]:
        lines.append(f"\nERRORS: {len(result['errors'])}")
        for err in result["errors"]:
            lines.append(f"  {err}")
    lines.append("")
    return "\n".join(lines)


# ── CLI entry point ───────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backfill_launch_config",
        description=("Backfill ports.port_type + app_commands from the live "
                     "registry and start.sh scripts. Dry run by default."))
    parser.add_argument("--apply", action="store_true",
                        help="write the plan to the database")
    parser.add_argument("--dry-run", action="store_true",
                        help="report only (this is already the default)")
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive")

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    from gui.sidecar.db import SessionLocal

    session = SessionLocal()
    try:
        plan = build_plan(session=session)
        result = apply_plan(plan, session) if args.apply else None
    finally:
        session.close()

    print(render_summary(plan, result))
    # Collisions are logged by design — only real errors are nonzero.
    if result and result["errors"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
