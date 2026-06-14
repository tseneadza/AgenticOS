"""iTerm2 Python API wrapper — FR-08, TR-08, FR-12.

Provides two public coroutines for the shell agent:
  - open_pane(commands)  — open a new split pane and inject commands
  - read_pane()          — return last N lines from the most recent pane

TR-08: the iTerm2 cookie is acquired once via AppleScript on first use
and cached for the process lifetime.  All subsequent operations use the
Python API exclusively.

FR-12: every call to inject() is evaluated against the agent constitution
BEFORE the command reaches the terminal.  Irreversible operations raise
ApprovalRequired (halts the run and surfaces the approval queue).
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Optional

from core.constitution import Constitution, ApprovalRequired, ConstitutionViolation

# ---------------------------------------------------------------------------
# Cookie cache (TR-08)
# ---------------------------------------------------------------------------
_COOKIE: Optional[str] = None
_KEY: Optional[str] = None


def _acquire_cookie() -> tuple[str, str]:
    """Acquire the iTerm2 cookie+key via AppleScript (once per process)."""
    global _COOKIE, _KEY
    if _COOKIE and _KEY:
        return _COOKIE, _KEY
    script = (
        'tell application "iTerm2"\n'
        '  request cookie and key\n'
        'end tell'
    )
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Could not acquire iTerm2 cookie: {result.stderr.strip()}"
        )
    # osascript returns "cookie,key"
    parts = result.stdout.strip().split(",", 1)
    if len(parts) != 2:
        raise RuntimeError(f"Unexpected iTerm2 cookie format: {result.stdout!r}")
    _COOKIE, _KEY = parts[0].strip(), parts[1].strip()
    return _COOKIE, _KEY


# ---------------------------------------------------------------------------
# Pane state (most recent pane session_id for read_pane)
# ---------------------------------------------------------------------------
_last_session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def open_pane(commands: list[str], *, approved: bool = False) -> str:
    """Open a new vertical split pane in iTerm2 and inject commands.

    FR-12: each command is checked against the constitution before inject.
    Returns the session_id of the new pane.
    """
    import iterm2  # lazy import — only available when running on macOS with iTerm2

    constitution = Constitution.load()

    # FR-12: policy intercept before any injection
    for cmd in commands:
        constitution.guard("shell_command", cmd, approved=approved)

    cookie, key = _acquire_cookie()

    async with iterm2.Connection.connect(cookie=cookie, key=key) as connection:
        app = await iterm2.async_get_app(connection)
        window = app.current_window
        if window is None:
            window = await iterm2.Window.async_create(connection)

        tab = window.current_tab
        current_session = tab.current_session

        # Vertical split (FR-08: async_split_pane)
        new_session = await current_session.async_split_pane(vertical=True)
        global _last_session_id
        _last_session_id = new_session.session_id

        # Inject each command (FR-08: async_inject)
        for cmd in commands:
            await new_session.async_inject((cmd + "\n").encode())
            await asyncio.sleep(0.05)  # small delay between commands

        return new_session.session_id


async def read_pane(n_lines: int = 15, session_id: Optional[str] = None) -> list[str]:
    """Return the last n_lines of output from a pane.

    Uses the most recently opened pane unless session_id is given.
    Returns an empty list if no pane is available.
    """
    import iterm2  # lazy import

    target_id = session_id or _last_session_id
    if target_id is None:
        return []

    cookie, key = _acquire_cookie()

    async with iterm2.Connection.connect(cookie=cookie, key=key) as connection:
        app = await iterm2.async_get_app(connection)
        # Find the session by id across all windows/tabs
        for window in app.windows:
            for tab in window.tabs:
                for session in tab.sessions:
                    if session.session_id == target_id:
                        contents = await session.async_get_screen_contents()
                        lines = []
                        for i in range(contents.number_of_lines):
                            line = contents.line(i)
                            if line and line.string:
                                lines.append(line.string.rstrip())
                        return lines[-n_lines:]
    return []


# ---------------------------------------------------------------------------
# Sync wrappers for use from non-async workflow nodes
# ---------------------------------------------------------------------------

def run_in_pane(commands: list[str], *, approved: bool = False) -> str:
    """Sync wrapper around open_pane. Returns session_id."""
    return asyncio.run(open_pane(commands, approved=approved))


def last_pane_lines(n_lines: int = 15) -> list[str]:
    """Sync wrapper around read_pane."""
    return asyncio.run(read_pane(n_lines=n_lines))
