"""Self-Diagnostics Routes — hidden diagnostics dashboard backend.

Powers the (hidden) self-diagnostics dashboard: a single place that answers
"is AgenticOS actually healthy right now?" by combining fast live self-checks
with on-demand execution of the real test suites.

REST endpoints:
    GET  /api/diagnostics/system   — live system self-checks (fast; no test run)
    GET  /api/diagnostics/cached   — last cached full diagnostics result (or empty)

WebSocket:
    WS   /api/diagnostics/ws/run   — run requested suites, stream progress, cache

WS message protocol
-------------------
Inbound (first frame, JSON, all fields optional):
    {"suites": ["system", "pytest", "vitest"]}   # default: all three

Outbound frames (JSON) — every frame has a ``type``:
    {"type": "progress",     "suite": str, "status": str, "message": str}
    {"type": "system",       "checks": [ {id,label,status,detail}, ... ]}
    {"type": "suite_result", "suite": str, "passed": int, "failed": int,
                             "total": int, "returncode": int, "duration_s": float}
    {"type": "complete",     "result": {...}}   # full payload, also written to cache
    {"type": "error",        "error": str}

``status`` for a check/suite is one of: "ok" | "warn" | "fail".

The full result is persisted to ``~/.agentic-os/diagnostics_cache.json`` so the
dashboard can render last-known state instantly on open, before any live run.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

# Repo root: gui/sidecar/routes/api_diagnostics.py -> parents[3]
REPO_ROOT = Path(__file__).resolve().parents[3]
CACHE_PATH = Path.home() / ".agentic-os" / "diagnostics_cache.json"


# ═══════════════════════════════════════════════════════════════════════════════
# Live system self-checks (fast — no subprocess, no test execution)
# ═══════════════════════════════════════════════════════════════════════════════

def _check(cid: str, label: str, status: str, detail: str, **extra) -> dict:
    """Build a single self-check row."""
    return {"id": cid, "label": label, "status": status, "detail": detail, **extra}


def run_system_checks() -> list[dict]:
    """Run the fast live self-checks and return a list of check rows.

    Each check degrades to a ``warn``/``fail`` row on error rather than raising,
    so one dead dependency never breaks the whole report.
    """
    checks: list[dict] = []

    # 1. Sidecar — if this code runs, the sidecar is up and serving.
    try:
        from gui.sidecar.app import SIDECAR_PORT

        checks.append(_check("sidecar", "Sidecar API", "ok",
                             f"Serving on :{SIDECAR_PORT}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("sidecar", "Sidecar API", "ok",
                             f"Serving (port unknown: {exc})"))

    # 2. MySQL — optional dependency; the app degrades gracefully, so "down" = warn.
    try:
        from gui.sidecar import db

        if db.is_available():
            checks.append(_check("mysql", "MySQL (data layer)", "ok", "Reachable"))
        else:
            checks.append(_check("mysql", "MySQL (data layer)", "warn",
                                 "Unreachable — ledger features degrade gracefully"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("mysql", "MySQL (data layer)", "warn", f"Check failed: {exc}"))

    # 3. Model registry — how many models are available right now.
    try:
        from core import llm

        payload = llm.list_models(ensure_ollama=False)
        models = payload.get("models", payload) if isinstance(payload, dict) else payload
        if isinstance(models, list):
            total = len(models)
            available = sum(1 for m in models if m.get("available"))
        else:  # pragma: no cover - defensive
            total, available = 0, 0
        status = "ok" if available > 0 else "warn"
        checks.append(_check("models", "LLM model registry", status,
                             f"{available}/{total} models available",
                             available=available, total=total))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("models", "LLM model registry", "fail", f"Registry error: {exc}"))

    # 4. Port ledger — how many ports are allocated (and whether the DB is holding them).
    try:
        from gui.sidecar.db import SessionLocal
        from gui.sidecar.models import Port

        session = SessionLocal()
        try:
            allocated = session.query(Port).count()
            checks.append(_check("ports", "Port ledger", "ok",
                                 f"{allocated} port(s) allocated", allocated=allocated))
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("ports", "Port ledger", "warn", f"Ledger unavailable: {exc}"))

    # 5. Constitution enforcement — prove guards actually block + allow.
    try:
        from core.constitution import Constitution, ConstitutionViolation

        con = Constitution.load()
        if not con.blocked:
            checks.append(_check("constitution", "Constitution guards", "warn",
                                 "Loaded, but no blocked patterns configured"))
        else:
            pattern = con.blocked[0]
            blocked_raised = False
            try:
                con.guard("shell_command", f"echo {pattern} here")
            except ConstitutionViolation:
                blocked_raised = True
            except Exception:  # noqa: BLE001 - approval etc. is not "blocked"
                blocked_raised = False
            if blocked_raised:
                checks.append(_check("constitution", "Constitution guards", "ok",
                                     f"Enforcing ({len(con.blocked)} blocked patterns, "
                                     f"{len(con.write_allowlist)} allowlisted roots)"))
            else:
                checks.append(_check("constitution", "Constitution guards", "fail",
                                     "Blocked pattern did NOT halt a guarded call"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("constitution", "Constitution guards", "fail",
                             f"Enforcement check errored: {exc}"))

    # 6. Workflow registry — do the YAML-defined workflows load cleanly.
    try:
        from core import orchestrator

        wfs = orchestrator.load_workflows()
        n = len(wfs)
        status = "ok" if n > 0 else "warn"
        checks.append(_check("workflows", "Workflow registry", status,
                             f"{n} workflow(s) loaded", count=n))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("workflows", "Workflow registry", "fail", f"Load failed: {exc}"))

    return checks


def _system_summary(checks: list[dict]) -> dict:
    """Roll a list of checks into ok/warn/fail counts + overall status."""
    ok = sum(1 for c in checks if c["status"] == "ok")
    warn = sum(1 for c in checks if c["status"] == "warn")
    fail = sum(1 for c in checks if c["status"] == "fail")
    overall = "fail" if fail else ("warn" if warn else "ok")
    return {"ok": ok, "warn": warn, "fail": fail, "overall": overall}


# ═══════════════════════════════════════════════════════════════════════════════
# Test-suite execution (streamed subprocesses)
# ═══════════════════════════════════════════════════════════════════════════════

def _venv_python() -> str:
    """Path to the repo venv's python, falling back to the current interpreter."""
    cand = REPO_ROOT / ".venv" / "bin" / "python"
    return str(cand) if cand.exists() else sys.executable


# pytest summary line, e.g. "==== 48 passed in 1.2s ====" / "1 failed, 47 passed"
_PYTEST_PASS = re.compile(r"(\d+) passed")
_PYTEST_FAIL = re.compile(r"(\d+) failed")
_PYTEST_ERR = re.compile(r"(\d+) error")
# vitest, e.g. "Tests  188 failed | 308 passed (496)"
_VITEST_TESTS = re.compile(r"Tests\s+(?:(\d+) failed\s*\|\s*)?(\d+) passed\s*\((\d+)\)")


async def _stream_cmd(cmd: list[str], cwd: Path, suite: str, emit) -> tuple[int, list[str]]:
    """Run *cmd* in *cwd*, streaming each stdout line via ``emit`` progress frames."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError as exc:
        await emit(suite, "fail", f"Cannot launch ({cmd[0]} not found): {exc}")
        return 127, []

    lines: list[str] = []
    assert proc.stdout is not None
    async for raw in proc.stdout:
        line = raw.decode(errors="replace").rstrip("\n")
        if line.strip():
            lines.append(line)
            await emit(suite, "running", line)
    await proc.wait()
    return proc.returncode or 0, lines


def _parse_pytest(lines: list[str]) -> dict:
    """Extract passed/failed/error counts from pytest output."""
    passed = failed = errors = 0
    for line in lines:
        if " passed" in line or " failed" in line or " error" in line:
            p = _PYTEST_PASS.search(line)
            f = _PYTEST_FAIL.search(line)
            e = _PYTEST_ERR.search(line)
            if p:
                passed = int(p.group(1))
            if f:
                failed = int(f.group(1))
            if e:
                errors = int(e.group(1))
    return {"passed": passed, "failed": failed + errors, "total": passed + failed + errors}


def _parse_vitest(lines: list[str]) -> dict:
    """Extract passed/failed/total counts from vitest output."""
    passed = failed = total = 0
    for line in lines:
        m = _VITEST_TESTS.search(line)
        if m:
            failed = int(m.group(1) or 0)
            passed = int(m.group(2))
            total = int(m.group(3))
    return {"passed": passed, "failed": failed, "total": total or (passed + failed)}


async def _run_pytest(emit) -> dict:
    """Run the backend pytest suite and return a structured result."""
    started = time.monotonic()
    await emit("pytest", "start", "Running backend pytest suite…")
    cmd = [_venv_python(), "-m", "pytest", "gui/sidecar/tests",
           "-q", "-p", "no:cacheprovider"]
    rc, lines = await _stream_cmd(cmd, REPO_ROOT, "pytest", emit)
    parsed = _parse_pytest(lines)
    parsed["returncode"] = rc
    parsed["duration_s"] = round(time.monotonic() - started, 2)
    parsed["status"] = "ok" if (rc == 0 and parsed["failed"] == 0) else "fail"
    parsed["tail"] = lines[-12:]
    return parsed


async def _run_vitest(emit) -> dict:
    """Run the frontend vitest suite and return a structured result."""
    started = time.monotonic()
    await emit("vitest", "start", "Running frontend vitest suite…")
    cmd = ["npx", "vitest", "run", "--reporter=dot"]
    rc, lines = await _stream_cmd(cmd, REPO_ROOT / "gui" / "desktop", "vitest", emit)
    parsed = _parse_vitest(lines)
    parsed["returncode"] = rc
    parsed["duration_s"] = round(time.monotonic() - started, 2)
    parsed["status"] = "ok" if (rc == 0 and parsed["failed"] == 0) else "fail"
    parsed["tail"] = lines[-12:]
    return parsed


def _write_cache(result: dict) -> None:
    """Persist the full diagnostics result for instant render on next open."""
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(result, indent=2))
    except Exception as exc:  # noqa: BLE001
        log.warning("diagnostics: cache write failed: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
# REST
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/system")
async def system_checks() -> dict:
    """Return the fast live self-checks (no test execution)."""
    checks = await asyncio.to_thread(run_system_checks)
    return {"ts": time.time(), "checks": checks, "summary": _system_summary(checks)}


@router.get("/cached")
async def cached() -> dict:
    """Return the last cached full diagnostics result, or an empty shell."""
    try:
        if CACHE_PATH.exists():
            return {"available": True, **json.loads(CACHE_PATH.read_text())}
    except Exception as exc:  # noqa: BLE001
        log.warning("diagnostics: cache read failed: %s", exc)
    return {"available": False, "ts": None, "system": None, "suites": {}}


# ═══════════════════════════════════════════════════════════════════════════════
# WebSocket — run suites + stream
# ═══════════════════════════════════════════════════════════════════════════════

@router.websocket("/ws/run")
async def ws_run(ws: WebSocket) -> None:
    """Run the requested diagnostics, streaming progress; cache the final result."""
    await ws.accept()

    async def emit(suite: str, status: str, message: str) -> None:
        await ws.send_json({"type": "progress", "suite": suite,
                            "status": status, "message": message})

    try:
        try:
            req = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            req = {}
        suites = req.get("suites") or ["system", "pytest", "vitest"]

        result: dict = {"ts": time.time(), "system": None, "suites": {}}

        if "system" in suites:
            await emit("system", "start", "Running live system self-checks…")
            checks = await asyncio.to_thread(run_system_checks)
            result["system"] = {"checks": checks, "summary": _system_summary(checks)}
            await ws.send_json({"type": "system", "checks": checks,
                                "summary": result["system"]["summary"]})

        if "pytest" in suites:
            res = await _run_pytest(emit)
            result["suites"]["pytest"] = res
            await ws.send_json({"type": "suite_result", "suite": "pytest", **res})

        if "vitest" in suites:
            res = await _run_vitest(emit)
            result["suites"]["vitest"] = res
            await ws.send_json({"type": "suite_result", "suite": "vitest", **res})

        _write_cache(result)
        await ws.send_json({"type": "complete", "result": result})
    except WebSocketDisconnect:
        log.info("diagnostics ws_run: client disconnected")
    except Exception as exc:  # noqa: BLE001
        log.warning("diagnostics ws_run failed: %s", exc)
        try:
            await ws.send_json({"type": "error", "error": str(exc)})
        except Exception:  # noqa: BLE001
            pass
    finally:
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass
