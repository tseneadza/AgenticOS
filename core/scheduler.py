"""Workflow scheduler — FR-16.

Two scheduling backends:
  - launchd (primary, macOS): generates and installs .plist files into
    ~/Library/LaunchAgents/.  Each scheduled workflow gets its own plist.
  - APScheduler (fallback): in-process scheduler used when the sidecar is
    already running and you want cron execution without launchd.

Usage:
  # Generate + install launchd plists for all scheduled workflows:
  python -m core.scheduler install

  # Remove all Agentic OS launchd plists:
  python -m core.scheduler uninstall

  # List installed plists:
  python -m core.scheduler list

The sidecar uses start_apscheduler() at startup as a belt-and-suspenders
fallback: if launchd fires a workflow, the sidecar runner handles it via CLI;
if the sidecar is running, APScheduler fires it directly.

Note (open question from PRD): launchd jobs don't inherit shell env.
ANTHROPIC_API_KEY is delivered via the plist EnvironmentVariables key,
read from ~/.agentic-os/env.yaml (chmod 600, created by `scheduler install`
if the key is present in the current environment).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
LAUNCHD_DIR = Path.home() / "Library" / "LaunchAgents"
ENV_FILE = Path.home() / ".agentic-os" / "env.yaml"
PLIST_PREFIX = "com.agentcos.workflow"

_SETTINGS = yaml.safe_load((CONFIG_DIR / "settings.yaml").read_text())["settings"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_workflows() -> dict:
    """Load and return the workflows dict from config/workflows.yaml."""
    return yaml.safe_load((CONFIG_DIR / "workflows.yaml").read_text()).get("workflows", {})


def _plist_label(workflow_name: str) -> str:
    """Return the launchd label for a workflow (e.g. 'com.agentcos.workflow.daily')."""
    return f"{PLIST_PREFIX}.{workflow_name}"


def _plist_path(workflow_name: str) -> Path:
    """Return the filesystem path for a workflow's launchd plist file."""
    return LAUNCHD_DIR / f"{_plist_label(workflow_name)}.plist"


def _cron_to_launchd(cron: str) -> dict:
    """Convert a 5-field cron expression to a launchd StartCalendarInterval dict.

    launchd calendar interval keys: Minute, Hour, Day, Month, Weekday.
    '*' means "every", which is represented by omitting the key in launchd.
    Only simple expressions (no ranges, no lists) are supported.
    """
    fields = cron.strip().split()
    if len(fields) != 5:
        raise ValueError(f"Expected 5-field cron, got: {cron!r}")
    minute, hour, day, month, weekday = fields
    interval: dict[str, int] = {}
    if minute != "*":
        interval["Minute"] = int(minute)
    if hour != "*":
        interval["Hour"] = int(hour)
    if day != "*":
        interval["Day"] = int(day)
    if month != "*":
        interval["Month"] = int(month)
    if weekday != "*":
        # launchd Weekday: 0=Sun … 6=Sat; cron same convention
        # cron "1-5" (weekdays) is not parseable here — omit (fire daily)
        if "-" not in weekday and "," not in weekday:
            interval["Weekday"] = int(weekday)
    return interval


def _build_plist(workflow_name: str, schedule: str) -> str:
    """Return an XML plist string for a launchd agent."""
    label = _plist_label(workflow_name)
    venv_python = str(PROJECT_ROOT / ".venv" / "bin" / "python")
    cli_script = str(PROJECT_ROOT / "main.py")
    interval = _cron_to_launchd(schedule)
    log_dir = PROJECT_ROOT / "data" / "logs"

    # Environment variables (API key delivery)
    env_vars: dict[str, str] = {}
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key and ENV_FILE.exists():
        try:
            env_data = yaml.safe_load(ENV_FILE.read_text()) or {}
            api_key = env_data.get("ANTHROPIC_API_KEY", "")
        except Exception:
            pass
    if api_key:
        env_vars["ANTHROPIC_API_KEY"] = api_key
    env_vars["PATH"] = f"{PROJECT_ROOT / '.venv' / 'bin'}:/usr/local/bin:/usr/bin:/bin"

    env_xml = "\n".join(
        f"      <key>{k}</key>\n      <string>{v}</string>"
        for k, v in env_vars.items()
    )

    interval_xml = "\n".join(
        f"      <key>{k}</key>\n      <integer>{v}</integer>"
        for k, v in interval.items()
    )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>

  <key>ProgramArguments</key>
  <array>
    <string>{venv_python}</string>
    <string>{cli_script}</string>
    <string>run</string>
    <string>{workflow_name}</string>
  </array>

  <key>WorkingDirectory</key>
  <string>{PROJECT_ROOT}</string>

  <key>EnvironmentVariables</key>
  <dict>
{env_xml}
  </dict>

  <key>StartCalendarInterval</key>
  <dict>
{interval_xml}
  </dict>

  <key>StandardOutPath</key>
  <string>{log_dir}/{workflow_name}.log</string>

  <key>StandardErrorPath</key>
  <string>{log_dir}/{workflow_name}.err</string>

  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
"""


# ---------------------------------------------------------------------------
# Install / uninstall
# ---------------------------------------------------------------------------

def install(verbose: bool = True) -> list[str]:
    """Generate and load launchd plists for all scheduled workflows.

    Returns list of installed workflow names.
    """
    LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)
    log_dir = PROJECT_ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Persist API key to env file for future installs
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        ENV_FILE.write_text(yaml.dump({"ANTHROPIC_API_KEY": api_key}))
        ENV_FILE.chmod(0o600)

    workflows = _load_workflows()
    installed = []
    for name, wf in workflows.items():
        schedule = wf.get("trigger", {}).get("schedule")
        if not schedule:
            continue
        plist_content = _build_plist(name, schedule)
        plist_path = _plist_path(name)
        plist_path.write_text(plist_content)
        # launchctl load (unload first in case it was already loaded)
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        result = subprocess.run(
            ["launchctl", "load", str(plist_path)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            installed.append(name)
            if verbose:
                print(f"  ✓ installed {name}  ({schedule})")
        else:
            if verbose:
                print(f"  ✗ {name}: {result.stderr.strip()}")

    return installed


def uninstall(verbose: bool = True) -> list[str]:
    """Unload and remove all Agentic OS launchd plists."""
    removed = []
    for plist in LAUNCHD_DIR.glob(f"{PLIST_PREFIX}.*.plist"):
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        plist.unlink()
        removed.append(plist.stem)
        if verbose:
            print(f"  removed {plist.name}")
    return removed


def list_installed() -> list[dict]:
    """Return info on installed Agentic OS plists."""
    plists = []
    for plist in LAUNCHD_DIR.glob(f"{PLIST_PREFIX}.*.plist"):
        name = plist.stem.replace(f"{PLIST_PREFIX}.", "")
        plists.append({"workflow": name, "plist": str(plist)})
    return plists


# ---------------------------------------------------------------------------
# APScheduler fallback (FR-16) — used by the sidecar
# ---------------------------------------------------------------------------

def start_apscheduler(runner) -> Optional[object]:
    """Start an in-process APScheduler for all workflows with a schedule.

    `runner` is the sidecar WorkflowRunner instance.
    Returns the scheduler object, or None if APScheduler is not installed.
    """
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        return None

    scheduler = AsyncIOScheduler()
    workflows = _load_workflows()
    added = 0
    for name, wf in workflows.items():
        schedule = wf.get("trigger", {}).get("schedule")
        if not schedule:
            continue
        fields = schedule.strip().split()
        if len(fields) != 5:
            continue
        minute, hour, day, month, dow = fields
        trigger = CronTrigger(
            minute=minute, hour=hour, day=day, month=month, day_of_week=dow
        )
        scheduler.add_job(
            lambda n=name: runner.start(n),
            trigger=trigger,
            id=f"workflow_{name}",
            replace_existing=True,
        )
        added += 1

    if added:
        scheduler.start()
    return scheduler


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "install":
        installed = install()
        print(f"\nInstalled {len(installed)} launchd agent(s).")
    elif cmd == "uninstall":
        removed = uninstall()
        print(f"\nRemoved {len(removed)} plist(s).")
    elif cmd == "list":
        plists = list_installed()
        if plists:
            for p in plists:
                print(f"  {p['workflow']}  →  {p['plist']}")
        else:
            print("  No Agentic OS launchd agents installed.")
    else:
        print("Usage: python -m core.scheduler [install|uninstall|list]")
