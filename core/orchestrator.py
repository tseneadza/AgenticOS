"""Orchestrator — turns workflows.yaml definitions into LangGraph graphs.

Each workflow step becomes a graph node. Nodes with requires_approval: true
call langgraph's interrupt(), pausing the run until the CLI resumes it with
the user's decision. State is checkpointed to MySQL (FR-05) via
langgraph-checkpoint-mysql, so interrupted runs are recoverable.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, TypedDict

import yaml
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agents import brain2_agent, briefing_agent, hub_agent
from core import memory
from core.constitution import Constitution

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

AGENT_REGISTRY = {
    "brain2_agent": brain2_agent.ACTIONS,
    "hub_agent": hub_agent.ACTIONS,
    "briefing_agent": briefing_agent.ACTIONS,
}


def _merge(left: dict, right: dict) -> dict:
    return {**left, **right}


class WorkflowState(TypedDict, total=False):
    outputs: Annotated[dict, _merge]
    tokens_used: Annotated[int, lambda a, b: a + b]
    cost_usd: Annotated[float, lambda a, b: a + b]
    model: str


def load_workflows() -> dict[str, dict]:
    return yaml.safe_load((CONFIG_DIR / "workflows.yaml").read_text())["workflows"]


def _make_node(step: dict, constitution: Constitution):
    agent_name = step["agent"]
    action_name = step["action"]
    step_id = step["id"]

    try:
        action = AGENT_REGISTRY[agent_name][action_name]
    except KeyError as exc:
        raise ValueError(
            f"Workflow step '{step_id}' references unknown {agent_name}.{action_name}"
        ) from exc

    def node(state: WorkflowState) -> dict[str, Any]:
        if step.get("requires_approval"):
            decision = interrupt(
                {
                    "step": step_id,
                    "agent": agent_name,
                    "action": action_name,
                    "question": f"Approve step '{step_id}' ({agent_name}.{action_name})? [y/N]",
                }
            )
            if str(decision).strip().lower() not in ("y", "yes", "approve", "approved"):
                raise PermissionError(f"Step '{step_id}' denied by user")

        call_state = {
            "outputs": state.get("outputs", {}),
            "model": step.get("model", "default"),
        }
        result = action(call_state)

        tokens = int(result.get("tokens_used", 0)) if isinstance(result, dict) else 0
        cost = float(result.get("cost_usd", 0.0)) if isinstance(result, dict) else 0.0
        constitution.check_token_budget(state.get("tokens_used", 0) + tokens)
        if cost > 0:
            constitution.check_cost_budget(
                memory.cost_today() + state.get("cost_usd", 0.0) + cost
            )

        return {"outputs": {step_id: result}, "tokens_used": tokens, "cost_usd": cost}

    return node


def build_graph(workflow_name: str, checkpointer: BaseCheckpointSaver):
    workflows = load_workflows()
    if workflow_name not in workflows:
        raise ValueError(
            f"Unknown workflow '{workflow_name}'. Available: {', '.join(workflows)}"
        )

    constitution = Constitution.load()
    steps = workflows[workflow_name]["steps"]

    graph = StateGraph(WorkflowState)
    prev = START
    for step in steps:
        graph.add_node(step["id"], _make_node(step, constitution))
        graph.add_edge(prev, step["id"])
        prev = step["id"]
    graph.add_edge(prev, END)

    return graph.compile(checkpointer=checkpointer)


def run_workflow(workflow_name: str, *, thread_id: str | None = None) -> dict:
    """Execute a workflow with HITL support. Returns the final state dict."""
    from langgraph.types import Command

    run_id = memory.start_run(workflow_name)
    thread_id = thread_id or run_id
    config = {"configurable": {"thread_id": thread_id}}

    conn = memory.checkpointer_conn()
    saver = memory.get_checkpointer(conn)
    app = build_graph(workflow_name, saver)
    try:
        result = app.invoke({"outputs": {}, "tokens_used": 0, "cost_usd": 0.0}, config)

        # Handle human-in-the-loop interrupts (possibly several)
        while "__interrupt__" in result:
            payload = result["__interrupt__"][0].value
            print(f"\n⏸  PAUSED — {payload['question']}")
            decision = input("> ").strip()
            result = app.invoke(Command(resume=decision), config)

        memory.finish_run(
            run_id,
            "completed",
            tokens_used=result.get("tokens_used", 0),
            cost_usd=result.get("cost_usd", 0.0),
            detail={"steps": list(result.get("outputs", {}).keys())},
        )
        return result
    except PermissionError as exc:
        memory.finish_run(run_id, "interrupted", detail={"reason": str(exc)})
        raise
    except Exception as exc:
        memory.finish_run(run_id, "failed", detail={"error": str(exc)})
        raise
    finally:
        conn.close()
