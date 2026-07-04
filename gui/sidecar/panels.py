"""Data providers for the six dashboard panels (FR-28..FR-33).

Each function returns a JSON-serializable dict. Failures degrade to
{"available": False, "error": ...} so one dead dependency (e.g. MySQL
down) never breaks the whole dashboard.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import psutil
import yaml

from core import memory

_SETTINGS = yaml.safe_load(
    (Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml").read_text()
)["settings"]

# Keno DB — mirrors live_keno_fetcher.py defaults (host/user/db + DP_PASSWORD env)
KENO_DB = {
    "host": os.environ.get("KENO_DB_HOST", "localhost"),
    "user": os.environ.get("KENO_DB_USER", "root"),
    "password": os.environ.get("DP_PASSWORD", "Natasha1785"),
    "database": os.environ.get("DB_NAME", "keno_georgia"),
}

SHELL_LOG = Path.home() / ".agentic-os" / "shell.log"  # Phase 3 source


# ----------------------------------------------------------------- FR-28
def system_health() -> dict:
    """Collect system health metrics: CPU, RAM, disk, network, load, and top processes."""
    vm = psutil.virtual_memory()
    disks = []
    seen = set()
    for part in psutil.disk_partitions(all=False):
        if part.mountpoint in seen:
            continue
        seen.add(part.mountpoint)
        try:
            du = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        disks.append(
            {
                "mount": part.mountpoint,
                "used_gb": round(du.used / 1e9, 1),
                "free_gb": round(du.free / 1e9, 1),
                "percent": du.percent,
            }
        )
    net = psutil.net_io_counters()
    load1, load5, load15 = os.getloadavg()

    def top(attr: str) -> list[dict]:
        """Return the top 10 processes sorted by the given attribute descending."""
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: x.get(attr) or 0, reverse=True)
        return [
            {"pid": p["pid"], "name": p["name"], attr: round(p.get(attr) or 0, 1)}
            for p in procs[:10]
        ]

    cpu_per_core = [round(x, 1) for x in psutil.cpu_percent(interval=None, percpu=True)]
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "cpu_per_core": cpu_per_core,
        "ram": {
            # "used" = total - available, so it agrees with vm.percent, which
            # psutil defines as (total - available) / total, NOT used / total.
            # On macOS vm.used (active+wired+compressed) is far below
            # total-available (cache/inactive pages psutil won't call "free"),
            # so vm.used / total and vm.percent disagree badly. Reporting
            # total-available keeps the number and the percentage consistent.
            "used_gb": round((vm.total - vm.available) / 1e9, 1),
            "total_gb": round(vm.total / 1e9, 1),
            "percent": vm.percent,
        },
        "disks": disks,
        "network": {"bytes_in": net.bytes_recv, "bytes_out": net.bytes_sent},
        "uptime_s": int(time.time() - psutil.boot_time()),
        "load_avg": [round(load1, 2), round(load5, 2), round(load15, 2)],
        "top_cpu": top("cpu_percent"),
        "top_memory": top("memory_percent"),
    }


# ----------------------------------------------------------------- FR-29
def agent_activity() -> dict:
    """Return agent activity panel data: costs, run counts, success rate, and recent runs."""
    # Run telemetry now comes from MySQL via memory.activity_stats()
    # (Category A of docs/mysql-migration-plan.md). MySQL aggregates can come
    # back as Decimal, so coerce to plain int/float for clean JSON.
    row = memory.activity_stats()

    def _f(key: str) -> float:
        """Coerce a row value to float, defaulting to 0.0 if None."""
        v = row.get(key)
        return float(v) if v is not None else 0.0

    def _i(key: str) -> int:
        """Coerce a row value to int, defaulting to 0 if None."""
        v = row.get(key)
        return int(v) if v is not None else 0

    finished = _i("finished")
    avg = row.get("avg_duration_s")
    return {
        "cost_today_usd": round(_f("cost_today"), 4),
        "cost_month_usd": round(_f("cost_month"), 4),
        "runs_today": _i("runs_today"),
        "tokens_total": _i("tokens_total"),
        "success_rate": round(100 * _i("completed") / finished, 1) if finished else None,
        "avg_duration_s": round(float(avg), 1) if avg is not None else None,
        "recent_runs": memory.recent_runs(limit=15),
    }


# ----------------------------------------------------------------- FR-30
def keno_telemetry() -> dict:
    """Return Keno data pipeline telemetry from MySQL, degrading gracefully on failure."""
    try:
        import mysql.connector

        conn = mysql.connector.connect(connection_timeout=4, **KENO_DB)
        cur = conn.cursor()
        cur.execute(
            """SELECT COUNT(*), MAX(CAST(draw_number AS UNSIGNED)),
                      MIN(CAST(draw_number AS UNSIGNED)), MAX(created_at)
               FROM draws"""
        )
        total, latest, earliest, last_sync = cur.fetchone()
        cur.execute(
            "SELECT COUNT(*) FROM draws WHERE created_at >= NOW() - INTERVAL 3 HOUR"
        )
        recent_imported = cur.fetchone()[0]
        conn.close()

        span = (latest - earliest + 1) if latest and earliest else 0
        gaps = max(span - total, 0)
        last_sync_ts = last_sync.timestamp() if last_sync else None
        age_s = int(time.time() - last_sync_ts) if last_sync_ts else None
        # scheduled task runs every 2 hours
        next_eta_s = max(7200 - age_s, 0) if age_s is not None else None
        return {
            "available": True,
            "total_draws": total,
            "latest_draw": latest,
            "last_sync_ts": last_sync_ts,
            "last_sync_age_s": age_s,
            "next_sync_eta_s": next_eta_s,
            "imported_last_run": recent_imported,
            "gaps_remaining": gaps,
            "coverage_percent": round(100 * total / span, 2) if span else None,
        }
    except Exception as exc:  # noqa: BLE001 — degrade, never break the dashboard
        return {"available": False, "error": str(exc)}


# ----------------------------------------------------------------- FR-31 (Phase 6: routed through hub_mcp — TR-11)
def hub_status() -> dict:
    """Hub panel data — delegates to hub_mcp so all Hub I/O goes via one place."""
    from tools import hub_mcp  # noqa: PLC0415
    return hub_mcp.hub_status()


def hub_app_action(app_id: str, action: str) -> dict:
    """Start/stop/restart a Hub app — delegates to hub_mcp (TR-11)."""
    from tools import hub_mcp  # noqa: PLC0415
    return hub_mcp.hub_app_action(app_id, action)


def hub_manifests() -> dict:
    """Agent capability manifests for all Hub apps (FR-18).

    Returns {app_id: agent_block_or_None} so the Hub panel can show
    which apps have declared agent APIs without a per-app round-trip.
    """
    from tools import hub_mcp  # noqa: PLC0415
    return hub_mcp.hub_manifests()


def hub_scripts() -> dict:
    """FR-19: all Hub-registered scripts, for display and tool registry use."""
    from tools import hub_mcp  # noqa: PLC0415
    return hub_mcp.list_hub_scripts()


# ----------------------------------------------------------------- FR-33
def iterm_strip(lines: int = 15) -> dict:
    """Last N lines of agent terminal output.

    Primary source: the Unix socket ring buffer populated by the ZSH plugin
    via the socket server (FR-10).  Falls back to reading ~/.agentic-os/shell.log
    for compatibility with manual log writers.
    """
    try:
        from core.socket_server import get_recent_lines
        ring = get_recent_lines(lines)
        if ring:
            return {"available": True, "lines": ring, "source": "socket"}
    except Exception:
        pass

    # Fallback: plain log file
    if SHELL_LOG.exists():
        tail = SHELL_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
        return {"available": True, "lines": tail, "source": "logfile"}

    # Ring buffer empty — server is running but no events yet
    return {
        "available": True,
        "lines": ["Waiting for shell events — run a command or cd in your terminal."],
        "source": "empty",
    }
