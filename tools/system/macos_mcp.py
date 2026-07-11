"""macOS + terminal capabilities — Phase 15a (design §5.1).

Plain Python functions registered (and guarded) through the harness's
``@capability`` decorator. Dual-mode by construction: OSA imports these
directly; ``tools/osa_system_mcp.py`` serves the same functions over stdio.

15a scope: ``get_time``, ``system_info``, ``run_command`` (both surfaces).
The rest of §5.1 (notify, clipboard, open_app, list_running_apps) are
follow-up capabilities — the harness makes each one a small decorated
function.
"""
from __future__ import annotations

import platform
import subprocess
import time
from datetime import datetime, timezone

from tools.system._harness import capability

# Output caps so a chatty command can't flood an LLM context.
_MAX_OUTPUT_CHARS = 8000
_DEFAULT_TIMEOUT_S = 60


@capability(
    "macos.get_time",
    domain="macos",
    effect="read",
    auto=True,
    schema={"type": "object", "properties": {}},
)
def get_time() -> dict:
    """Report the current local time, timezone, and date on this Mac."""
    now = datetime.now().astimezone()
    return {
        "iso": now.isoformat(timespec="seconds"),
        "local": now.strftime("%A, %B %-d %Y, %-I:%M %p"),
        "timezone": str(now.tzinfo),
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "unix": int(now.timestamp()),
    }


@capability(
    "macos.system_info",
    domain="macos",
    effect="read",
    auto=True,
    schema={"type": "object", "properties": {}},
)
def system_info() -> dict:
    """Report machine info: hardware, macOS version, CPU/RAM/disk, uptime."""
    info: dict = {
        "hostname": platform.node(),
        "os": f"macOS {platform.mac_ver()[0]}" if platform.mac_ver()[0] else platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }
    # Reuse the sidecar's health snapshot (same source as the GUI panels).
    try:
        from gui.sidecar import panels

        h = panels.system_health()
        ram = h.get("ram", {}) or {}
        disks = h.get("disks", []) or []
        root = next((d for d in disks if d.get("mount") == "/"), None) or (
            disks[0] if disks else {}
        )
        info.update(
            cpu_percent=h.get("cpu_percent"),
            ram_percent=ram.get("percent"),
            ram_used_gb=ram.get("used_gb"),
            ram_total_gb=ram.get("total_gb"),
            disk_percent=root.get("percent"),
            disk_free_gb=root.get("free_gb"),
        )
    except Exception as exc:  # noqa: BLE001 — partial info beats no info
        info["health_error"] = str(exc)
    try:
        import psutil

        up_s = int(time.time() - psutil.boot_time())
        info["uptime_hours"] = round(up_s / 3600, 1)
    except Exception:  # noqa: BLE001
        pass
    return info


@capability(
    "macos.run_command",
    domain="macos",
    effect="mutate",
    auto=False,  # governed by the terminal allowlist, not the auto flag
    schema={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to run (zsh/bash syntax; pipes and globs work).",
            },
            "surface": {
                "type": "string",
                "enum": ["subprocess", "pane"],
                "default": "subprocess",
                "description": "subprocess = headless with captured output; pane = visible iTerm2 split pane.",
            },
            "cwd": {"type": "string", "description": "Working directory (default: home)."},
            "timeout": {"type": "integer", "default": 60},
        },
        "required": ["command"],
    },
)
def run_command(
    command: str,
    surface: str = "subprocess",
    cwd: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT_S,
) -> dict:
    """Run a terminal command on this Mac (allowlisted auto, else needs approval).

    ``shell=True`` is a locked 15a decision (2026-07-11, Tony): pipes/globs
    work on a personal machine, with the capability guard + allowlist +
    denylist as the mitigation. The guard has ALREADY run by the time this
    body executes (capability layer, design decision #2).
    """
    command = (command or "").strip()
    if not command:
        return {"ok": False, "error": "empty command"}

    if surface == "pane":
        # Visible, abortable: reuse the existing Constitution-gated iTerm2
        # injector. approved=True — OUR guard already cleared this call —
        # but iterm2_tool's blocked-pattern check still applies regardless.
        from tools import iterm2_tool

        session_id = iterm2_tool.run_in_pane([command], approved=True)
        time.sleep(1.0)  # give the command a beat to produce output
        lines = iterm2_tool.last_pane_lines(20)
        return {
            "ok": True,
            "surface": "pane",
            "session_id": session_id,
            "output_tail": lines,
            "note": "command runs in a visible iTerm2 pane; output_tail is a snapshot",
        }

    proc = subprocess.run(  # noqa: S602 — shell=True is the locked decision
        command,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
    )
    return {
        "ok": proc.returncode == 0,
        "surface": "subprocess",
        "returncode": proc.returncode,
        "stdout": proc.stdout[-_MAX_OUTPUT_CHARS:],
        "stderr": proc.stderr[-_MAX_OUTPUT_CHARS:],
    }
