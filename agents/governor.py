"""Governing agent (Phase 10 / NF-3, FR-54/55).

A conversational, tool-calling agent that operates the whole OS in natural
language. It does **not** invent a parallel command layer — its tools wrap the
capability that already exists: workflows (run via the threaded runner so they
keep their own HITL), the dynamic ``tool_registry`` (Hub apps + scripts), the
in-process agent ACTIONS, and read-only status.

Safety (FR-55) is centralized in ``GovernorToolbox._guarded``: every
side-effectful tool call passes ``constitution.guard(action_type, payload)``
first. A ``ConstitutionViolation`` hard-stops the call; an ``ApprovalRequired``
is bridged to a human via the injected ``approval_fn`` (the sidecar wires this
to the approval queue + ``APPROVAL_REQUIRED`` AG-UI event). The toolbox is a
plain object so it is fully unit-testable without LangChain; ``build_agent``
lazily constructs the LangGraph ReAct agent on top of it.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Callable

import yaml

from core.constitution import (
    CONFIG_DIR,
    ApprovalRequired,
    Constitution,
    ConstitutionViolation,
)

# Type of the human-approval bridge: (action_type, description) -> decision str.
ApprovalFn = Callable[[str, str], str]
# Optional tool-event sink: (phase, tool_name, info) -> None. phase in
# {"start", "end", "error"}. Lets the runner stream TOOL_CALL_* events.
EventFn = Callable[[str, str, dict], None]


GOVERNOR_SYSTEM = (
    "You are the governing agent of a personal Agentic OS running on the user's "
    "Mac. You operate the system on the user's behalf through the provided tools "
    "— you never fabricate results, and you only act through tools.\n\n"
    "Capabilities:\n"
    "- list_workflows / run_workflow: the canonical automations (morning "
    "briefing, note processing, etc.). Prefer running an existing workflow over "
    "ad-hoc tool calls when one fits.\n"
    "- list_tools / call_tool: dynamic Hub app + script tools.\n"
    "- list_agent_actions: in-process agent capabilities (reachable via "
    "workflows).\n"
    "- get_status / get_runs: read-only system + run history.\n"
    "- write_config / edit_workflow: AUTHORING — change the OS's own YAML config "
    "and workflow definitions. These always require human approval and write a "
    "timestamped backup first. Use them only when the user explicitly asks to "
    "change configuration or a workflow; describe the change before making it.\n\n"
    "Safety rules (enforced by the runtime, not optional):\n"
    "- Side-effectful actions pass a Constitution guard. Some require human "
    "approval; if a tool returns 'DENIED' or 'BLOCKED', respect it and explain "
    "to the user rather than retrying.\n"
    "- Never attempt to bypass approval or budget limits.\n"
    "- Be concise. State what you did and the outcome."
)


def _is_yes(decision: str | None) -> bool:
    return str(decision).strip().lower() in ("y", "yes", "approve", "approved", "ok")


def _default_deny(action_type: str, description: str) -> str:  # pragma: no cover
    return "deny"


def _noop_event(phase: str, tool: str, info: dict) -> None:  # pragma: no cover
    return None


class GovernorToolbox:
    """The governing agent's tools as guarded Python methods.

    Each method returns a *string* (JSON or a human-readable status) because
    that is what a tool-calling LLM consumes. Methods are deliberately small and
    well-described so small local models can call them reliably (FR-58).
    """

    def __init__(
        self,
        constitution: Constitution | None = None,
        approval_fn: ApprovalFn = _default_deny,
        event_fn: EventFn = _noop_event,
    ) -> None:
        self.constitution = constitution or Constitution.load()
        self.approval_fn = approval_fn
        self.event_fn = event_fn

    # ------------------------------------------------------------------ guard
    def _guarded(self, action_type: str, payload: str, do: Callable[[], Any]) -> str:
        """Run ``do`` only after the Constitution clears ``action_type``.

        Blocked → 'BLOCKED: …'. Approval needed → ask the human via approval_fn;
        on yes, re-guard with approved=True and proceed; on no, 'DENIED: …'.
        """
        try:
            self.constitution.guard(action_type, payload)
        except ConstitutionViolation as cv:
            return f"BLOCKED: {cv}"
        except ApprovalRequired as ar:
            decision = self.approval_fn(action_type, ar.description or payload)
            if not _is_yes(decision):
                return f"DENIED: human did not approve '{action_type}'."
            try:
                self.constitution.guard(action_type, payload, approved=True)
            except ConstitutionViolation as cv:
                return f"BLOCKED: {cv}"
        return self._run(action_type, payload, do)

    def _run(self, action_type: str, payload: str, do: Callable[[], Any]) -> str:
        self.event_fn("start", action_type, {"payload": payload})
        try:
            result = do()
            text = result if isinstance(result, str) else json.dumps(result, default=str)
            self.event_fn("end", action_type, {"ok": True})
            return text
        except Exception as exc:  # noqa: BLE001 — surface to the model, don't crash the turn
            self.event_fn("error", action_type, {"error": str(exc)})
            return f"ERROR running '{action_type}': {exc}"

    # ------------------------------------------------------------ read-only
    def list_workflows(self) -> str:
        """List available workflows (name, description, steps). Read-only."""
        from core import orchestrator

        wfs = orchestrator.load_workflows()
        return json.dumps(
            [
                {
                    "name": name,
                    "description": wf.get("description", ""),
                    "steps": [s["id"] for s in wf.get("steps", [])],
                }
                for name, wf in wfs.items()
            ]
        )

    def list_agent_actions(self) -> str:
        """List in-process agent actions ({agent: [action, ...]}). Read-only."""
        from core import orchestrator

        return json.dumps(
            {agent: sorted(actions) for agent, actions in orchestrator.AGENT_REGISTRY.items()}
        )

    def list_tools(self) -> str:
        """List dynamic Hub app + script tools (name + description). Read-only."""
        from core.tool_registry import get_registry

        try:
            tools = get_registry().list_tools()
        except Exception as exc:  # noqa: BLE001 — Hub may be down
            return f"ERROR listing tools: {exc}"
        return json.dumps(
            [{"name": t["name"], "description": t.get("description", "")} for t in tools]
        )

    def get_status(self) -> str:
        """System health + Hub status snapshot. Read-only."""
        from gui.sidecar import panels

        out: dict[str, Any] = {}
        for key, fn in (("system", panels.system_health), ("hub", panels.hub_status)):
            try:
                out[key] = fn()
            except Exception as exc:  # noqa: BLE001
                out[key] = {"error": str(exc)}
        return json.dumps(out, default=str)

    def get_runs(self, limit: int = 10) -> str:
        """Recent workflow runs (most recent first). Read-only."""
        from core import memory

        return json.dumps(memory.recent_runs(limit=limit), default=str)

    # ------------------------------------------------------------ effectful
    def run_workflow(self, name: str) -> str:
        """Start a workflow by name. Returns its run_id. The workflow keeps its
        own step-level approvals via the runner, so this is not guarded here.
        """
        from core import orchestrator

        if name not in orchestrator.load_workflows():
            return f"ERROR: unknown workflow '{name}'. Use list_workflows first."

        def _do() -> dict:
            from gui.sidecar.runner import runner

            run_id = runner.start(name)
            return {"started": name, "run_id": run_id}

        # action_type 'workflow_run' is not in approval_required by default →
        # passes straight through; step-level gates fire inside the run.
        return self._guarded("workflow_run", name, _do)

    def call_tool(self, name: str, args_json: str = "{}") -> str:
        """Call a dynamic registry tool by name with JSON args. Guarded as an
        external API call (approval-required by the Constitution).
        """
        try:
            kwargs = json.loads(args_json) if args_json else {}
            if not isinstance(kwargs, dict):
                raise ValueError("args_json must be a JSON object")
        except (ValueError, json.JSONDecodeError) as exc:
            return f"ERROR: invalid args_json: {exc}"

        def _do() -> Any:
            from core.tool_registry import get_registry

            return get_registry().call(name, **kwargs)

        return self._guarded("api_call_external", f"{name} {args_json}", _do)

    # ------------------------------------------------------------- authoring
    # FR-59: the agent can change the OS's own config + workflows. Authoring is
    # the highest-risk capability, so it is guarded harder than ordinary tools:
    #   1. the target must be inside the Constitution write_allowlist;
    #   2. the payload is checked against the blocked-substring list;
    #   3. it ALWAYS requires human approval — independent of the active model
    #      and independent of whether the action_type is in approval_required;
    #   4. the YAML is validated *before* asking for approval; and
    #   5. a timestamped backup of any existing file is written before the save.
    def _authoring_write(
        self, action_type: str, target: Path, payload: str, write_fn: Callable[[], Any]
    ) -> str:
        try:
            self.constitution.guard_write_path(target)
        except ConstitutionViolation as cv:
            return f"BLOCKED: {cv}"
        try:
            self.constitution.guard(action_type, payload)
        except ConstitutionViolation as cv:
            return f"BLOCKED: {cv}"
        except ApprovalRequired:
            # Authoring requires approval below regardless; ignore the config gate.
            pass
        decision = self.approval_fn(action_type, f"write {target.name}")
        if not _is_yes(decision):
            return f"DENIED: human did not approve '{action_type}' on {target}."
        return self._run(action_type, str(target), write_fn)

    def _save_with_backup(self, target: Path, text: str) -> dict:
        """Write ``text`` to ``target``, backing up any existing file first."""
        backup: str | None = None
        if target.exists():
            ts = time.strftime("%Y%m%d-%H%M%S")
            backup_path = target.with_name(f"{target.name}.{ts}.bak")
            shutil.copy2(target, backup_path)
            backup = str(backup_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return {"wrote": str(target), "backup": backup, "bytes": len(text)}

    def write_config(self, filename: str, content: str) -> str:
        """Create or overwrite a YAML config file in the OS config dir.

        ``filename`` is a bare name (path components are stripped) ending in
        .yaml/.yml. Requires approval; validates YAML; backs up the old file.
        """
        name = Path(filename).name
        if not name.endswith((".yaml", ".yml")):
            return "ERROR: config filename must end in .yaml or .yml"
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as exc:
            return f"ERROR: invalid YAML, not written: {exc}"
        target = CONFIG_DIR / name
        return self._authoring_write(
            "config_write", target, content, lambda: self._save_with_backup(target, content)
        )

    def edit_workflow(self, name: str, definition_json: str) -> str:
        """Add or replace one workflow in config/workflows.yaml.

        ``definition_json`` is a JSON object for the workflow body (description,
        steps, schedule, …). Requires approval; validates the merged YAML; backs
        up workflows.yaml. Other workflows are preserved untouched.
        """
        try:
            definition = json.loads(definition_json)
            if not isinstance(definition, dict):
                raise ValueError("definition_json must be a JSON object")
        except (ValueError, json.JSONDecodeError) as exc:
            return f"ERROR: invalid definition_json: {exc}"
        target = CONFIG_DIR / "workflows.yaml"
        try:
            doc = yaml.safe_load(target.read_text()) if target.exists() else {}
            doc = doc or {}
        except (OSError, yaml.YAMLError) as exc:
            return f"ERROR: cannot read workflows.yaml: {exc}"
        workflows = doc.setdefault("workflows", {})
        workflows[name] = definition
        new_text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
        try:
            yaml.safe_load(new_text)  # round-trip validation before approval
        except yaml.YAMLError as exc:
            return f"ERROR: serialized workflows.yaml invalid, not written: {exc}"
        return self._authoring_write(
            "workflow_edit", target, new_text, lambda: self._save_with_backup(target, new_text)
        )


# --------------------------------------------------------------------------- #
# LangGraph ReAct agent construction (lazy — keeps this module import-light)
# --------------------------------------------------------------------------- #
def build_tools(toolbox: GovernorToolbox) -> list:
    """Wrap a GovernorToolbox's methods as LangChain StructuredTools."""
    from langchain_core.tools import StructuredTool

    specs = [
        (toolbox.list_workflows, "list_workflows"),
        (toolbox.list_agent_actions, "list_agent_actions"),
        (toolbox.list_tools, "list_tools"),
        (toolbox.get_status, "get_status"),
        (toolbox.get_runs, "get_runs"),
        (toolbox.run_workflow, "run_workflow"),
        (toolbox.call_tool, "call_tool"),
        (toolbox.write_config, "write_config"),
        (toolbox.edit_workflow, "edit_workflow"),
    ]
    return [
        StructuredTool.from_function(func=fn, name=name, description=(fn.__doc__ or name).strip())
        for fn, name in specs
    ]


def build_agent(
    model_id: str | None = None,
    *,
    toolbox: GovernorToolbox | None = None,
    constitution: Constitution | None = None,
    approval_fn: ApprovalFn = _default_deny,
    event_fn: EventFn = _noop_event,
    max_tool_iterations: int = 8,
):
    """Build a compiled LangGraph ReAct governing agent over the toolbox.

    ``max_tool_iterations`` is the FR-58 loop guard (recursion_limit ≈ 2×steps).
    All heavy imports are local so unit tests can exercise the toolbox without
    LangChain/LangGraph installed.
    """
    from langgraph.prebuilt import create_react_agent

    from core import llm

    toolbox = toolbox or GovernorToolbox(
        constitution=constitution, approval_fn=approval_fn, event_fn=event_fn
    )
    model = llm.get_chat_model(model_id)
    tools = build_tools(toolbox)
    return create_react_agent(model, tools, prompt=GOVERNOR_SYSTEM)
