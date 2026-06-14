"""Session-scoped governing-agent runner (Phase 10 / NF-3, FR-55/57).

Sibling of ``runner.py`` (the workflow runner): runs a governing-agent *turn*
on a worker thread and streams tokens + tool events over the AG-UI ``events``
bus, so the same WebSocket feed that shows workflow runs also shows agent
activity.

HITL (FR-55) is unified with the workflow approval queue: when a tool needs
human approval the runner parks a ``PendingApproval`` in the shared
``runner.approvals`` dict and publishes ``APPROVAL_REQUIRED``. The existing
``POST /api/approvals/{id}`` endpoint resolves it (sets the event), so there is
one approval surface for both workflows and the agent.

Budgets (FR-55): per-turn token total is checked against the Constitution's
token budget; cloud cost is added to today's spend and checked against the
daily cap. Local models cost 0, so local turns never trip the cap.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from agents import governor
from core import llm
from core.constitution import Constitution
from gui.sidecar.events import bus
from gui.sidecar.runner import APPROVAL_TIMEOUT_S, PendingApproval, runner

# FR-58 loop guard: cap ReAct tool iterations; recursion_limit ≈ 2×steps + 1.
MAX_TOOL_ITERATIONS = 8


@dataclass
class AgentTurn:
    turn_id: str
    session_id: str
    message: str
    model_id: str
    status: str = "running"  # running | completed | failed
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    error: str | None = None


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(content) if content is not None else ""


class AgentRunner:
    """Runs governing-agent turns and streams them over the event bus."""

    def __init__(self) -> None:
        self.turns: dict[str, AgentTurn] = {}
        # Per-session conversation history as role/content dicts.
        self.sessions: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ API
    def start_turn(self, message: str, *, model: str | None = None,
                   session_id: str = "default") -> str:
        model_id = llm.resolve(model) if model else llm.active_model()
        turn = AgentTurn(
            turn_id="agt-" + uuid.uuid4().hex[:8],
            session_id=session_id,
            message=message,
            model_id=model_id,
        )
        with self._lock:
            self.turns[turn.turn_id] = turn
        threading.Thread(
            target=self._execute, args=(turn,), name=f"agent-{turn.turn_id}", daemon=True
        ).start()
        return turn.turn_id

    # ------------------------------------------------------------- bridges
    def _approval_fn(self, turn: AgentTurn):
        def fn(action_type: str, description: str) -> str:
            approval = PendingApproval(
                approval_id=uuid.uuid4().hex[:10],
                run_id=turn.turn_id,
                workflow=f"agent:{turn.session_id}",
                step=action_type,
                agent="governor",
                action=action_type,
                question=f"Agent wants to '{action_type}': {description}. Approve? [y/N]",
            )
            # Park on the SHARED workflow approval queue so /api/approvals works.
            with runner._lock:  # noqa: SLF001 — deliberate shared-queue reuse
                runner.approvals[approval.approval_id] = approval
            bus.publish(
                "APPROVAL_REQUIRED",
                approval_id=approval.approval_id,
                run_id=turn.turn_id,
                workflow=approval.workflow,
                step=approval.step,
                question=approval.question,
            )
            return approval.wait(APPROVAL_TIMEOUT_S) or "deny"

        return fn

    def _event_fn(self, turn: AgentTurn):
        def fn(phase: str, tool: str, info: dict) -> None:
            if phase == "start":
                bus.publish("TOOL_CALL_START", run_id=turn.turn_id, tool=tool,
                            payload=info.get("payload", ""))
            else:
                bus.publish("TOOL_CALL_END", run_id=turn.turn_id, tool=tool,
                            ok=(phase == "end"), error=info.get("error"))

        return fn

    # ------------------------------------------------------------- execute
    def _execute(self, turn: AgentTurn) -> None:
        bus.publish("RUN_STARTED", run_id=turn.turn_id, agent="governor",
                    model=turn.model_id, message=turn.message)
        try:
            toolbox = governor.GovernorToolbox(
                approval_fn=self._approval_fn(turn),
                event_fn=self._event_fn(turn),
            )
            agent = governor.build_agent(turn.model_id, toolbox=toolbox)

            history = self.sessions.setdefault(turn.session_id, [])
            history.append({"role": "user", "content": turn.message})

            cfg = {"recursion_limit": 2 * MAX_TOOL_ITERATIONS + 1}
            final_text = self._stream(agent, history, turn, cfg)

            history.append({"role": "assistant", "content": final_text})
            turn.text = final_text

            # Budget enforcement (FR-55).
            total_tokens = turn.input_tokens + turn.output_tokens
            turn.cost_usd = llm.cost_usd(turn.model_id, turn.input_tokens, turn.output_tokens)
            constitution = Constitution.load()
            if total_tokens:
                constitution.check_token_budget(total_tokens)
            if turn.cost_usd > 0:
                from core import memory

                constitution.check_cost_budget(memory.cost_today() + turn.cost_usd)

            turn.status = "completed"
            turn.finished_at = time.time()
            bus.publish(
                "RUN_FINISHED", run_id=turn.turn_id, agent="governor",
                tokens_used=total_tokens, cost_usd=turn.cost_usd, text=final_text,
            )
        except Exception as exc:  # noqa: BLE001 — report any failure to the GUI
            turn.status = "failed"
            turn.finished_at = time.time()
            turn.error = str(exc)
            bus.publish("RUN_ERROR", run_id=turn.turn_id, agent="governor",
                        error=str(exc), kind="failed")

    def _stream(self, agent, history: list[dict], turn: AgentTurn, cfg: dict) -> str:
        """Stream assistant tokens to the bus; return the full final text.

        Tries token-level streaming (stream_mode="messages"); falls back to a
        single invoke if the installed LangGraph doesn't support it.
        """
        payload = {"messages": list(history)}
        final_text = ""
        try:
            for chunk, _meta in agent.stream(payload, config=cfg, stream_mode="messages"):
                cls = chunk.__class__.__name__
                if cls.startswith("AIMessage"):
                    delta = _text_of(getattr(chunk, "content", ""))
                    if delta:
                        final_text += delta
                        bus.publish("TEXT_MESSAGE_CONTENT", run_id=turn.turn_id, delta=delta)
                um = getattr(chunk, "usage_metadata", None) or {}
                turn.input_tokens += int(um.get("input_tokens", 0) or 0)
                turn.output_tokens += int(um.get("output_tokens", 0) or 0)
            return final_text
        except TypeError:
            # Older LangGraph: no messages stream mode — do a single invoke.
            result = agent.invoke(payload, config=cfg)
            msgs = result.get("messages", []) if isinstance(result, dict) else []
            if msgs:
                last = msgs[-1]
                final_text = _text_of(getattr(last, "content", "") or "")
                um = getattr(last, "usage_metadata", None) or {}
                turn.input_tokens += int(um.get("input_tokens", 0) or 0)
                turn.output_tokens += int(um.get("output_tokens", 0) or 0)
                bus.publish("TEXT_MESSAGE_CONTENT", run_id=turn.turn_id, delta=final_text)
            return final_text


agent_runner = AgentRunner()
