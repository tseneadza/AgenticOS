"""Project Manager — Phase 11a (Project Creation Scaffolding).

Foundation helpers that turn a template + a name into a real project on disk
and a claimed local port. This module owns the *side-effectful* half of the
scaffolding feature (filesystem, venv creation, DB-backed port allocation);
the pure content-generation lives in ``template_registry.py``.

Public API (Phase 11a):
    validate_project_name(name)                     -> bool
    scan_codehome_structure()                       -> dict
    create_project_folder(subfolder, project_name)  -> Path
    create_venv(project_path, template_name)        -> str | None
    allocate_port(app_id, preferred_port, session)  -> int

Phase 11b adds the best-effort git flow (``init_git_repo``); Phase 11c adds the
full async orchestration (``create_project_full``) that ties folder + port +
files + venv + github + git + DB registration into one resilient state machine.
This module is deliberately lenient about failures for best-effort steps (venv
creation, git, github), matching the resilient design of ``db.py`` /
``app_registry.py``: a missing ``uv``/``python`` or a failed install logs a
warning and returns ``None`` rather than raising.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from gui.sidecar.template_registry import (
    PYTHON_TEMPLATES,
    TEMPLATES,
    generate_files,
)

log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

#: Root under which all Codehome projects live.
_CODEHOME = Path.home() / "Codehome"

#: Directories that are structural noise — never surfaced as target subfolders.
_NOISE_DIRS: set[str] = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".cursor", ".claude", ".autoclaude", ".obsidian", ".DS_Store",
    "dist", "build", ".build", "target", ".idea", ".vscode",
}

#: The canonical top-level buckets we suggest first when they exist.
_SUGGESTED_SUBFOLDERS: set[str] = {"agents", "apps", "tools"}

#: Port scan window for dynamic allocation.
_PORT_RANGE_START = 5200
_PORT_RANGE_END = 5999   # inclusive


# ── name validation ───────────────────────────────────────────────────────────

#: slug: starts with a lowercase letter, then lowercase letters/digits/hyphens,
#: no double hyphens, no leading/trailing hyphen. 1–64 chars total.
_NAME_RE = re.compile(r"^[a-z](?:[a-z0-9]|-(?=[a-z0-9])){0,63}$")


def validate_project_name(name: str) -> bool:
    """Return True if *name* is a valid slug-friendly project name.

    Rules:
        * lowercase letters, digits and single hyphens only
        * must start with a letter
        * 1–64 characters
        * no leading/trailing hyphen and no double hyphens
    """
    if not isinstance(name, str):
        return False
    if not (1 <= len(name) <= 64):
        return False
    return _NAME_RE.match(name) is not None


# ── Codehome structure discovery ──────────────────────────────────────────────

def scan_codehome_structure(session=None) -> dict:
    """Return the subfolders that already hold OSA-created projects.

    We deliberately do NOT guess categories from the filesystem — that surfaced
    unrelated folders (Docker, Golang, Artifacts, …) as clutter and could not
    reliably tell a real category from an incidental one. Instead the picker is
    self-curating: a subfolder appears here once you've created a project in it
    (distinct ``Project.subfolder`` values from the ledger). The Codehome root
    and brand-new folders are always available via the returned flags, so you
    can target any location the first time and it's remembered afterwards.

    Returns::

        {
            "suggested": [...],        # folders with existing OSA projects
            "all":       [...],        # same list
            "custom_available": True,  # caller may type a brand-new folder
            "root_available":   True,  # caller may create directly in ~/Codehome
        }

    Args:
        session: optional SQLAlchemy session (tests inject sqlite); ``None`` ->
            ``SessionLocal()``. A DB failure degrades gracefully to an empty
            list (root + custom stay available).
    """
    from gui.sidecar.db import SessionLocal
    from gui.sidecar.models import Project

    owns_session = session is None
    subfolders: list[str] = []
    try:
        if owns_session:
            session = SessionLocal()
        rows = session.query(Project.subfolder).distinct().all()
        subfolders = sorted(
            {(r[0] or "").strip() for r in rows if r[0] and r[0].strip()},
            key=str.lower,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("scan_codehome_structure: ledger query failed: %s", exc)
    finally:
        if owns_session and session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass

    return {
        "suggested": subfolders,
        "all": subfolders,
        "custom_available": True,
        "root_available": True,
    }


# ── folder creation ───────────────────────────────────────────────────────────

def create_project_folder(subfolder: str, project_name: str) -> Path:
    """Create the project folder and return its Path.

    An empty/blank *subfolder* targets the Codehome root (``~/Codehome/<name>``).

    Uses ``parents=True, exist_ok=True`` so intermediate dirs are created. If
    the target project folder already exists AND is non-empty, a
    ``FileExistsError`` is raised (we never clobber existing work).
    """
    sub = (subfolder or "").strip().strip("/")
    target = (_CODEHOME / sub / project_name) if sub else (_CODEHOME / project_name)

    if target.exists() and any(target.iterdir()):
        raise FileExistsError(
            f"Project folder already exists and is not empty: {target}"
        )

    target.mkdir(parents=True, exist_ok=True)
    log.info("create_project_folder: %s", target)
    return target


# ── venv creation (best-effort) ───────────────────────────────────────────────

def create_venv(project_path: Path, template_name: str) -> str | None:
    """Create a ``.venv`` for python templates and editable-install the project.

    Best-effort and lenient: for non-python templates this returns ``None``
    immediately. For python templates it prefers ``uv`` (``uv venv`` +
    ``uv pip install -e .``) and falls back to the stdlib ``venv`` module
    (``python -m venv`` + ``.venv/bin/pip install -e .``). Any failure logs a
    warning and returns ``None`` — a broken venv never aborts scaffolding.

    Returns the path to the venv ``activate`` script on success, else ``None``.
    """
    if template_name not in PYTHON_TEMPLATES:
        return None

    project_path = Path(project_path)
    venv_dir = project_path / ".venv"
    activate = venv_dir / "bin" / "activate"

    uv = shutil.which("uv")
    try:
        if uv:
            _run([uv, "venv", ".venv"], cwd=project_path)
            _run([uv, "pip", "install", "-e", "."], cwd=project_path)
        else:
            _run([sys.executable, "-m", "venv", ".venv"], cwd=project_path)
            pip = venv_dir / "bin" / "pip"
            _run([str(pip), "install", "-e", "."], cwd=project_path)
    except (subprocess.CalledProcessError, OSError) as exc:  # noqa: BLE001
        log.warning(
            "create_venv: venv creation failed for %s (template=%s): %s",
            project_path, template_name, exc,
        )
        return None

    if not activate.exists():
        log.warning("create_venv: activate script missing at %s", activate)
        return None

    log.info("create_venv: created %s", venv_dir)
    return str(activate)


def _run(cmd: list[str], cwd: Path) -> None:
    """Run *cmd* in *cwd*, raising CalledProcessError on non-zero exit."""
    log.debug("create_venv: running %s (cwd=%s)", cmd, cwd)
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True, text=True)


# ── port allocation (DB-backed) ───────────────────────────────────────────────

def _port_in_use(port: int) -> bool:
    """Quick TCP probe on 127.0.0.1 — True if something is already listening."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def _registry_ports() -> set[int]:
    """Expected ports declared by every discovered app.json (best-effort).

    A registry failure must not block allocation, so this is fully guarded.
    """
    ports: set[int] = set()
    try:
        from core import app_registry

        for app in app_registry.get_all():
            port = app.get("expected_port")
            if isinstance(port, int):
                ports.add(port)
    except Exception as exc:  # noqa: BLE001
        log.warning("allocate_port: app_registry lookup failed: %s", exc)
    return ports


def allocate_port(
    app_id: str,
    preferred_port: int | None = None,
    session=None,
) -> int:
    """Claim a free local port for *app_id*, recording it in the ``ports`` table.

    Unavailable ports are the union of:
        * every ``Port.port`` already recorded in the ledger,
        * every ``expected_port`` declared in the app registry,
        * any port a quick TCP probe finds already in use.

    If *preferred_port* is given and free, it is claimed and returned. Otherwise
    the range ``5200..5999`` is scanned and the first free port is claimed.

    Args:
        app_id: owner recorded on the ledger row.
        preferred_port: try this first if free.
        session: an existing SQLAlchemy Session. If ``None`` a session is
            created from ``SessionLocal`` and managed locally (commit + close).

    Raises:
        RuntimeError: if no free port is available in the range.
    """
    from sqlalchemy.exc import IntegrityError

    from gui.sidecar.db import SessionLocal
    from gui.sidecar.models import Port

    owns_session = session is None
    if owns_session:
        session = SessionLocal()

    try:
        taken: set[int] = {row.port for row in session.query(Port).all()}
        taken |= _registry_ports()

        def _try_claim(port: int) -> bool:
            """Insert a ledger row for *port*; return True on success."""
            session.add(Port(port=port, app_id=app_id, status="allocated"))
            try:
                session.commit()
                return True
            except IntegrityError:
                # Lost a race — another writer claimed it. Roll back and skip.
                session.rollback()
                taken.add(port)
                return False

        # 1. Honour a free preferred port.
        if preferred_port is not None:
            if (
                preferred_port not in taken
                and not _port_in_use(preferred_port)
                and _try_claim(preferred_port)
            ):
                log.info("allocate_port(%s): claimed preferred %d", app_id, preferred_port)
                return preferred_port

        # 2. Scan the range for the first free port.
        for candidate in range(_PORT_RANGE_START, _PORT_RANGE_END + 1):
            if candidate in taken:
                continue
            if _port_in_use(candidate):
                taken.add(candidate)
                continue
            if _try_claim(candidate):
                log.info("allocate_port(%s): claimed %d", app_id, candidate)
                return candidate

        raise RuntimeError("No free ports available")
    finally:
        if owns_session:
            session.close()


# ── git init / commit / push (best-effort) — Phase 11b ────────────────────────

def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run ``git <args>`` in *cwd* without raising.

    Unlike ``_run`` (which raises on non-zero exit), this uses ``check=False``
    so callers can inspect ``returncode`` / ``stderr`` and append precise
    warnings — the git flow is fully best-effort.
    """
    log.debug("init_git_repo: running git %s (cwd=%s)", args, cwd)
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )


def init_git_repo(
    project_path: Path,
    remote_url: str | None = None,
    *,
    push: bool = False,
    default_branch: str = "main",
) -> dict:
    """Initialise a git repo in *project_path*, commit, and optionally push.

    Every step is best-effort and guarded: a failing step appends a warning and
    the function continues where sensible. This function NEVER raises (matching
    the lenient design used elsewhere in this module) — inspect the returned
    status dict instead.

    Steps:
        * ``git init`` (preferring ``git init -b <default_branch>``; falls back
          to plain ``git init`` for old git).
        * local ``user.name`` / ``user.email`` config (repo-local, not global).
        * ``git add -A`` + ``git commit -m "Initial project scaffold"``.
        * if *remote_url*: ``git remote add origin <remote_url>``.
        * if *push* and *remote_url*: ``git push -u origin <default_branch>``.

    Returns:
        {"initialized": bool, "committed": bool, "remote_added": bool,
         "pushed": bool, "warnings": [str, ...]}
    """
    project_path = Path(project_path)
    status = {
        "initialized": False,
        "committed": False,
        "remote_added": False,
        "pushed": False,
        "warnings": [],
    }
    warnings: list[str] = status["warnings"]

    def _warn(msg: str) -> None:
        log.warning("init_git_repo: %s", msg)
        warnings.append(msg)

    # 1. git init (prefer -b <branch>; fall back for old git).
    res = _git(["init", "-b", default_branch], cwd=project_path)
    if res.returncode == 0:
        status["initialized"] = True
    else:
        res = _git(["init"], cwd=project_path)
        if res.returncode == 0:
            status["initialized"] = True
            # Point HEAD at the desired branch for the first commit.
            ref = _git(
                ["symbolic-ref", "HEAD", f"refs/heads/{default_branch}"],
                cwd=project_path,
            )
            if ref.returncode != 0:
                _warn(f"could not set initial branch to {default_branch}: {ref.stderr.strip()}")
        else:
            _warn(f"git init failed: {res.stderr.strip()}")
            return status  # nothing else can succeed without a repo

    # 2. Repo-local identity (so the commit doesn't depend on global config).
    name_res = _git(["config", "user.name", "AgenticOS"], cwd=project_path)
    if name_res.returncode != 0:
        _warn(f"git config user.name failed: {name_res.stderr.strip()}")
    email_res = _git(
        ["config", "user.email", "agentic@codehome.local"], cwd=project_path
    )
    if email_res.returncode != 0:
        _warn(f"git config user.email failed: {email_res.stderr.strip()}")

    # 3. Stage + commit.
    add_res = _git(["add", "-A"], cwd=project_path)
    if add_res.returncode != 0:
        _warn(f"git add failed: {add_res.stderr.strip()}")
    commit_res = _git(
        ["commit", "-m", "Initial project scaffold"], cwd=project_path
    )
    if commit_res.returncode == 0:
        status["committed"] = True
        # Ensure the branch is named as requested even on the old-git path.
        _git(["branch", "-M", default_branch], cwd=project_path)
    else:
        _warn(
            "git commit failed (nothing to commit or git error): "
            f"{commit_res.stderr.strip() or commit_res.stdout.strip()}"
        )

    # 4. Add remote.
    if remote_url:
        remote_res = _git(
            ["remote", "add", "origin", remote_url], cwd=project_path
        )
        if remote_res.returncode == 0:
            status["remote_added"] = True
        else:
            _warn(f"git remote add origin failed: {remote_res.stderr.strip()}")

    # 5. Push (best-effort).
    if push and remote_url:
        if not status["remote_added"]:
            _warn("skipping push: remote was not added")
        elif not status["committed"]:
            _warn("skipping push: nothing was committed")
        else:
            push_res = _git(
                ["push", "-u", "origin", default_branch], cwd=project_path
            )
            if push_res.returncode == 0:
                status["pushed"] = True
            else:
                _warn(f"git push failed: {push_res.stderr.strip()}")

    return status


# ── full async orchestration — Phase 11c ──────────────────────────────────────

async def create_project_full(
    *,
    name: str,
    template: str,
    subfolder: str,
    description: str | None = None,
    custom_port: int | None = None,
    private: bool = True,
    emit=None,          # optional async callable: emit(step, status, message=None)
    session=None,       # optional SQLAlchemy session (tests inject sqlite); None -> SessionLocal()
) -> dict:
    """Scaffold a project end-to-end: folder + port + files + venv + git + DB.

    A resilient state machine that ties together the Phase 11a/11b helpers.
    CRITICAL steps (validate, folder, port, files, register) raise on failure
    and abort the flow after emitting an ``error`` event. OPTIONAL steps (venv,
    github, git) are best-effort: a failure appends a warning and emits a
    ``warning`` event but never raises.

    Emit protocol
    -------------
    If *emit* is provided it is awaited as ``emit(step, status, message=None)``
    for each transition. The stable ``step`` names emitted (in order) are::

        validate, folder, port, files, venv, github, git, register

    Each step emits ``status="start"`` then either ``status="complete"`` (on
    success), ``status="warning"`` (optional-step failure), or ``status="error"``
    (critical-step failure). ``venv`` is only emitted for python templates.
    An emit failure never breaks the flow.

    Args:
        name: slug-friendly project name (validated).
        template: a key of ``TEMPLATES``.
        subfolder: target bucket under ``~/Codehome`` (e.g. ``apps``).
        description: optional human description.
        custom_port: preferred port; falls back to auto-allocation if taken.
        private: create the GitHub repo private (default True).
        emit: optional async callable for progress events.
        session: optional SQLAlchemy session; ``None`` -> ``SessionLocal()``.

    Returns:
        {"project_id", "path", "port", "template", "subfolder", "github_url",
         "pushed", "warnings", "success"}

    Raises:
        ValueError: invalid name or unknown template.
        Exception: any critical-step failure (folder / port / files / register).
    """
    # Lazy imports (mirrors allocate_port) to keep module import cheap and dodge
    # import cycles.
    from gui.sidecar.github_integration import setup_repo
    from gui.sidecar.db import SessionLocal
    from gui.sidecar.models import Project

    warnings: list[str] = []

    async def _emit(step: str, status: str, message: str | None = None) -> None:
        """Best-effort progress emit — never lets an emit failure break the flow."""
        if emit is None:
            return
        try:
            await emit(step, status, message)
        except Exception as exc:  # noqa: BLE001
            log.debug("create_project_full: emit(%s, %s) failed: %s", step, status, exc)

    github_url: str | None = None
    clone_url: str | None = None
    pushed = False

    # ── 1. validate (CRITICAL) ───────────────────────────────────────────────
    await _emit("validate", "start")
    if not validate_project_name(name):
        await _emit("validate", "error", f"Invalid project name: {name!r}")
        raise ValueError(f"Invalid project name: {name!r}")
    if template not in TEMPLATES:
        await _emit("validate", "error", f"Unknown template: {template!r}")
        raise ValueError(f"Unknown template: {template!r}")
    await _emit("validate", "complete")

    # ── 2. folder (CRITICAL) ─────────────────────────────────────────────────
    await _emit("folder", "start")
    try:
        project_path: Path = await asyncio.to_thread(
            create_project_folder, subfolder, name
        )
    except Exception as exc:  # noqa: BLE001
        await _emit("folder", "error", str(exc))
        raise
    await _emit("folder", "complete", str(project_path))

    # ── 3. port (CRITICAL) — allocate BEFORE files (app.json embeds the port) ─
    # NB: DB work runs inline on the event-loop thread (queries are fast), NOT
    # via asyncio.to_thread — a SQLAlchemy Session is not thread-safe and must
    # not be shared across the worker thread here and the main thread used by
    # the register step below. Only subprocess/filesystem work is offloaded.
    await _emit("port", "start")
    try:
        port: int = allocate_port(name, custom_port, session)
    except Exception as exc:  # noqa: BLE001
        await _emit("port", "error", str(exc))
        raise
    await _emit("port", "complete", str(port))

    # ── 4. files (CRITICAL) — render + write every file (app.json included) ───
    await _emit("files", "start")
    try:
        files = generate_files(template, name, description or "", port)

        def _write_files() -> None:
            for rel_path, content in files.items():
                dest = project_path / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content)

        await asyncio.to_thread(_write_files)
    except Exception as exc:  # noqa: BLE001
        await _emit("files", "error", str(exc))
        raise
    await _emit("files", "complete", f"{len(files)} files")

    # ── 5. venv (OPTIONAL) — python templates only ───────────────────────────
    if template in PYTHON_TEMPLATES:
        await _emit("venv", "start")
        try:
            activate = await asyncio.to_thread(create_venv, project_path, template)
            if activate is None:
                msg = "venv creation skipped or failed (missing uv/python?)"
                warnings.append(msg)
                await _emit("venv", "warning", msg)
            else:
                await _emit("venv", "complete", activate)
        except Exception as exc:  # noqa: BLE001
            msg = f"venv creation error: {exc}"
            warnings.append(msg)
            await _emit("venv", "warning", msg)

    # ── 6. github (OPTIONAL) — best-effort remote creation ───────────────────
    await _emit("github", "start")
    try:
        repo = await asyncio.to_thread(setup_repo, name, description, private)
    except Exception as exc:  # noqa: BLE001
        repo = None
        log.warning("create_project_full: setup_repo raised: %s", exc)
    if repo is None:
        msg = "GitHub repo creation skipped (no token / creation failed)"
        warnings.append(msg)
        await _emit("github", "warning", msg)
    else:
        github_url = repo.get("html_url")
        clone_url = repo.get("clone_url")
        await _emit("github", "complete", github_url)

    # ── 7. git (OPTIONAL) — init/commit + optional push ──────────────────────
    await _emit("git", "start")
    try:
        git_status = await asyncio.to_thread(
            lambda: init_git_repo(
                project_path, remote_url=clone_url, push=bool(clone_url)
            )
        )
        for w in git_status.get("warnings", []):
            warnings.append(w)
        pushed = bool(git_status.get("pushed"))
        await _emit("git", "complete", f"pushed={pushed}")
    except Exception as exc:  # noqa: BLE001
        msg = f"git init/commit error: {exc}"
        warnings.append(msg)
        await _emit("git", "warning", msg)

    # ── 8. register (CRITICAL) — insert the Project ledger row ────────────────
    await _emit("register", "start")
    owns_session = session is None
    reg_session = SessionLocal() if owns_session else session
    try:
        reg_session.add(
            Project(
                id=name,
                name=name,
                description=description,
                path=str(project_path),
                subfolder=subfolder,
                template=template,
                port=port,
                github_repo_url=github_url,
            )
        )
        reg_session.commit()
    except Exception as exc:  # noqa: BLE001
        try:
            reg_session.rollback()
        except Exception:  # noqa: BLE001
            pass
        await _emit("register", "error", str(exc))
        raise
    finally:
        if owns_session:
            reg_session.close()
    await _emit("register", "complete")

    # ── best-effort registry invalidation so the app shows up immediately ────
    try:
        from core import app_registry
        app_registry.invalidate_cache()
    except Exception as exc:  # noqa: BLE001
        log.debug("create_project_full: invalidate_cache failed: %s", exc)

    return {
        "project_id": name,
        "path": str(project_path),
        "port": port,
        "template": template,
        "subfolder": subfolder,
        "github_url": github_url,
        "pushed": pushed,
        "warnings": warnings,
        "success": True,
    }
