"""Shell agent — iTerm2 pane manager and ZSH event handler — FR-10, FR-11.

Two responsibilities:
  1. Socket event handler: receives parsed ZSH events from SocketServer
     and routes them through the appropriate LangGraph nodes.
  2. chpwd handler (FR-11): when the user changes directory, checks whether
     the new path matches a Brain2 project and surfaces relevant context
     (project name, status, recent notes) as a brief log entry.

Wired into the sidecar via:
    from agents.shell_agent import ShellAgent
    agent = ShellAgent()
    socket_server.add_handler(agent.handle_event)
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_settings() -> dict:
    """Load and return the ``settings`` section from ``config/settings.yaml``."""
    return yaml.safe_load((CONFIG_DIR / "settings.yaml").read_text())["settings"]


# ---------------------------------------------------------------------------
# Brain2 project map (FR-11)
# ---------------------------------------------------------------------------

def _build_project_map(vault_path: str) -> dict[str, str]:
    """Return {absolute_dir_path: project_name} by scanning Brain2 projects.

    Looks for Obsidian notes in 01 - Projects/ whose frontmatter contains
    a `codehome_dir` or `dir` key pointing to a filesystem path.
    Falls back to matching by note name against the last component of cwd.
    """
    projects: dict[str, str] = {}
    projects_dir = Path(vault_path) / "01 - Projects"
    if not projects_dir.exists():
        return projects

    for note in projects_dir.glob("*.md"):
        try:
            text = note.read_text(encoding="utf-8")
        except OSError:
            continue
        # Parse YAML frontmatter
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                try:
                    fm = yaml.safe_load(text[3:end]) or {}
                except yaml.YAMLError:
                    fm = {}
                dir_path = fm.get("codehome_dir") or fm.get("dir")
                if dir_path:
                    projects[str(Path(dir_path).expanduser().resolve())] = (
                        fm.get("title") or note.stem
                    )
    return projects


# ---------------------------------------------------------------------------
# Shell agent
# ---------------------------------------------------------------------------

class ShellAgent:
    """iTerm2/ZSH event handler that surfaces Brain2 project context.

    Receives parsed shell events (preexec, precmd, chpwd) from the socket
    server and logs or acts on them. On directory changes, matches the new
    path against known Brain2 projects and emits context events.
    """

    def __init__(self) -> None:
        """Initialize the shell agent with settings and a lazy project map."""
        self._settings = _load_settings()
        self._vault = self._settings.get("vault_path", "")
        self._project_map: dict[str, str] | None = None  # lazy build

    def _get_project_map(self) -> dict[str, str]:
        """Return the project-directory-to-name map, building it lazily on first call."""
        if self._project_map is None:
            self._project_map = _build_project_map(self._vault)
        return self._project_map

    # ------------------------------------------------------------------
    # Main event dispatcher
    # ------------------------------------------------------------------

    async def handle_event(self, event: dict) -> None:
        """Dispatch a ZSH event to the appropriate handler."""
        evt = event.get("event")
        if evt == "preexec":
            await self._on_preexec(event)
        elif evt == "precmd":
            await self._on_precmd(event)
        elif evt == "chpwd":
            await self._on_chpwd(event)
        else:
            logger.debug("Unknown shell event type: %s", evt)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _on_preexec(self, event: dict) -> None:
        """Log command about to execute. Could trigger analysis in future phases."""
        cmd = event.get("command", "")
        cwd = event.get("cwd", "")
        logger.info("[shell] preexec  cwd=%s  cmd=%r", cwd, cmd)

    async def _on_precmd(self, event: dict) -> None:
        """Log command exit code."""
        code = event.get("exit_code", 0)
        cwd = event.get("cwd", "")
        level = logging.INFO if code == 0 else logging.WARNING
        logger.log(level, "[shell] precmd   cwd=%s  exit=%s", cwd, code)

    async def _on_chpwd(self, event: dict) -> None:
        """FR-11: surface Brain2 context when entering a project directory."""
        cwd = event.get("cwd", "")
        if not cwd:
            return

        project_map = self._get_project_map()
        cwd_resolved = str(Path(cwd).resolve())

        # Exact match first, then check if cwd is inside a known project dir
        project_name = project_map.get(cwd_resolved)
        if not project_name:
            for proj_dir, name in project_map.items():
                if cwd_resolved.startswith(proj_dir + os.sep):
                    project_name = name
                    break

        if project_name:
            context = await self._fetch_project_context(project_name)
            logger.info(
                "[shell] chpwd → Brain2 project: %s  status=%s  notes=%d",
                project_name,
                context.get("status", "?"),
                context.get("note_count", 0),
            )
            # Emit a structured context event back into the socket log
            # so the terminal strip can display it (FR-33)
            from core.socket_server import _event_log
            _event_log.append({
                "event": "context",
                "project": project_name,
                "status": context.get("status", ""),
                "notes": context.get("note_count", 0),
                "cwd": cwd,
            })
        else:
            logger.debug("[shell] chpwd  no project match for %s", cwd)

    async def _fetch_project_context(self, project_name: str) -> dict:
        """Read the Brain2 project note and return key metadata."""
        projects_dir = Path(self._vault) / "01 - Projects"
        # Find matching note (case-insensitive stem match)
        for note in projects_dir.glob("*.md"):
            if note.stem.lower() == project_name.lower() or (
                note.stem.lower().endswith(f"- {project_name.lower()}")
            ):
                try:
                    text = note.read_text(encoding="utf-8")
                except OSError:
                    return {}
                fm: dict = {}
                if text.startswith("---"):
                    end = text.find("---", 3)
                    if end != -1:
                        try:
                            fm = yaml.safe_load(text[3:end]) or {}
                        except yaml.YAMLError:
                            pass
                # Count linked notes as a rough context signal
                linked = text.count("[[")
                return {
                    "status": fm.get("status", ""),
                    "note_count": linked,
                    "title": fm.get("title", project_name),
                }
        return {}
