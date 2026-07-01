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

The full async orchestration (``create_project_full``) and GitHub integration
are intentionally out of scope here — they arrive in Phase 11b / 11c. This
module is deliberately lenient about failures for best-effort steps (venv
creation), matching the resilient design of ``db.py`` / ``app_registry.py``:
a missing ``uv``/``python`` or a failed install logs a warning and returns
``None`` rather than raising.
"""
from __future__ import annotations

import logging
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from gui.sidecar.template_registry import PYTHON_TEMPLATES

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

def scan_codehome_structure() -> dict:
    """Scan ``~/Codehome`` for immediate subdirectories.

    Returns a dict of the shape::

        {
            "suggested": ["agents", "apps", "tools"],   # subset that exists
            "all":       [... every non-noise subdir ...],
            "custom_available": True,
        }

    Hidden dirs and known noise dirs (``.git``, ``node_modules``,
    ``__pycache__``, ``.venv`` …) are skipped. A missing ``~/Codehome`` is
    handled gracefully (empty ``all``, ``suggested`` falls back to ``["apps"]``).
    """
    all_dirs: list[str] = []
    if _CODEHOME.exists():
        try:
            for entry in sorted(_CODEHOME.iterdir(), key=lambda p: p.name.lower()):
                if not entry.is_dir():
                    continue
                if entry.name.startswith(".") or entry.name in _NOISE_DIRS:
                    continue
                all_dirs.append(entry.name)
        except OSError as exc:  # noqa: BLE001
            log.warning("scan_codehome_structure: cannot read %s: %s", _CODEHOME, exc)

    suggested = [d for d in ("agents", "apps", "tools") if d in set(all_dirs)]
    if not suggested:
        suggested = ["apps"]

    return {
        "suggested": suggested,
        "all": all_dirs,
        "custom_available": True,
    }


# ── folder creation ───────────────────────────────────────────────────────────

def create_project_folder(subfolder: str, project_name: str) -> Path:
    """Create ``~/Codehome/<subfolder>/<project_name>/`` and return its Path.

    Uses ``parents=True, exist_ok=True`` so intermediate dirs are created. If
    the target project folder already exists AND is non-empty, a
    ``FileExistsError`` is raised (we never clobber existing work).
    """
    target = _CODEHOME / subfolder / project_name

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
