#!/usr/bin/env python3
"""Agentic OS CLI.

    agentic-os run <workflow>     Execute a workflow end-to-end
    agentic-os list               List available workflows
    agentic-os history            Show recent run history
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys


def cmd_list() -> int:
    """List all available workflows with their descriptions and schedules."""
    from core.orchestrator import load_workflows

    print("Available workflows:\n")
    for name, wf in load_workflows().items():
        trigger = wf.get("trigger", {})
        sched = trigger.get("schedule")
        sched_note = f"  [schedule: {sched}]" if sched else ""
        print(f"  {name:<24} {wf.get('description', '')}{sched_note}")
    return 0


def cmd_history() -> int:
    """Display recent workflow run history with timing, token, and cost details."""
    from core import memory

    runs = memory.recent_runs(15)
    if not runs:
        print("No runs yet.")
        return 0
    print(f"{'when':<20} {'workflow':<22} {'status':<12} {'tokens':>7} {'cost':>8}")
    print("-" * 74)
    for r in runs:
        when = dt.datetime.fromtimestamp(r["started_at"]).strftime("%Y-%m-%d %H:%M:%S")
        cost = r.get("cost_usd") or 0.0
        print(
            f"{when:<20} {r['workflow']:<22} {r['status']:<12} "
            f"{r['tokens_used'] or 0:>7} {cost:>8.4f}"
        )
    from core import memory as _mem

    print(f"\n  spend today: ${_mem.cost_today():.4f}")
    return 0


def cmd_run(workflow: str) -> int:
    """Execute a named workflow end-to-end and print results.

    Args:
        workflow: Name of the workflow to run.

    Returns:
        Exit code: 0 on success, 2 for constitution violations, 3 for permission errors.
    """
    from core.constitution import ConstitutionViolation
    from core.orchestrator import run_workflow
    from tools.filesystem_tool import reset_write_counter

    reset_write_counter()
    print(f"▶ Running workflow: {workflow}")
    try:
        result = run_workflow(workflow)
    except ConstitutionViolation as exc:
        print(f"\n⛔ HALTED by constitution: {exc}")
        return 2
    except PermissionError as exc:
        print(f"\n🚫 {exc}")
        return 3

    print("\n✅ Workflow completed.")
    for step_id, output in result.get("outputs", {}).items():
        summary = output if not isinstance(output, dict) else {
            k: (v if not isinstance(v, str) or len(v) < 80 else v[:77] + "...")
            for k, v in output.items()
            if k != "brief"
        }
        print(f"  • {step_id}: {summary}")
        if isinstance(output, dict) and "written_to" in output:
            print(f"    → {output['written_to']}")
    tokens = result.get("tokens_used", 0)
    if tokens:
        print(f"\n  tokens used: {tokens}  (${result.get('cost_usd', 0.0):.4f})")
    return 0


def main() -> int:
    """Parse CLI arguments and dispatch to the appropriate subcommand."""
    parser = argparse.ArgumentParser(prog="agentic-os", description="Personal Agentic OS")
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="Run a workflow")
    run_p.add_argument("workflow")
    sub.add_parser("list", help="List workflows")
    sub.add_parser("history", help="Recent run history")

    args = parser.parse_args()
    if args.command == "list":
        return cmd_list()
    if args.command == "history":
        return cmd_history()
    if args.command == "run":
        return cmd_run(args.workflow)
    return 1


if __name__ == "__main__":
    sys.exit(main())
