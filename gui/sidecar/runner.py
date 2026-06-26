"""Threaded workflow runner with programmatic HITL approvals.

The CLI's run_workflow() blocks on input() at interrupts; the GUI needs
the run parked while the Approval Queue panel (FR-32) collects a decision
over HTTP. Each run gets a worker thread; interrupts park on a
threading.Event that the /api/approvals endpoint sets.

Streams LangGraph node updates as AG-UI events (FR-21).
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from langgraph.types import Command

from core import memory, orchestrator
from core.exceptions import SkippedRun
from gui.sidecar.events import bus

APPROVAL_TIMEOUT_S = 3600  # parked run gives up after an hour


@dataclass
class PendingApproval:
    """A HITL approval request that parks a workflow run until resolved."""

    approval_id: str
    run_id: str
    workflow: str
    step: str
    agent: str
    action: str
    question: str
    created_at: float = field(default_factory=time.time)
    decision: str | None = None
    _event: threading.Event = field(default_factory=threading.Event)

    def resolve(self, decision: str) -> None:
        """Set the decision and wake the waiting thread.

        Args:
            decision: The approve/deny decision string.
        """
        self.decision = decision
        self._event.set()

    def wait(self, timeout: float) -> str | None:
        """Block until the approval is resolved or timeout expires.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            The decision string, or None if the timeout expired.
        """
        self._event.wait(timeout)
        return self.decision


@dataclass
class RunHandle:
    """Tracks the state of a single workflow run."""

    run_id: str
    workflow: str
    status: str = "running"  # running | waiting_approval | completed | failed | denied | skipped
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    error: str | None = None


class WorkflowRunner:
    """Threaded workflow runner with HITL approval support for the GUI."""

    def __init__(self) -> None:
        """Initialize the runner with empty run and approval registries."""
        self.runs: dict[str, RunHandle] = {}
        self.approvals: dict[str, PendingApproval] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def start(self, workflow: str) -> str:
        """Start a workflow run on a background thread.

        Args:
            workflow: Name of the workflow to execute.

        Returns:
            The unique run ID.
        """
        run_id = memory.start_run(workflow)
        handle = RunHandle(run_id=run_id, workflow=workflow)
        with self._lock:
            self.runs[run_id] = handle
        thread = threading.Thread(
            target=self._execute, args=(handle,), name=f"run-{run_id}", daemon=True
        )
        thread.start()
        return run_id

    def pending_approvals(self) -> list[dict]:
        """Return a list of all unresolved approval requests as dicts."""
        with self._lock:
            return [
                {
                    "approval_id": a.approval_id,
                    "run_id": a.run_id,
                    "workflow": a.workflow,
                    "step": a.step,
                    "agent": a.agent,
                    "action": a.action,
                    "question": a.question,
                    "created_at": a.created_at,
                }
                for a in self.approvals.values()
                if a.decision is None
            ]

    def resolve_approval(self, approval_id: str, decision: str) -> bool:
        """Resolve a pending approval and publish the decision to the event bus.

        Args:
            approval_id: ID of the approval to resolve.
            decision: The approve/deny decision string.

        Returns:
            True if the approval was found and resolved, False otherwise.
        """
        with self._lock:
            approval = self.approvals.get(approval_id)
        if approval is None or approval.decision is not None:
            return False
        approval.resolve(decision)
        bus.publish(
            "APPROVAL_RESOLVED",
            approval_id=approval_id,
            run_id=approval.run_id,
            decision=decision,
        )
        return True

    # ------------------------------------------------------------------
    def _execute(self, handle: RunHandle) -> None:
        """Run a workflow on the current thread, streaming events to the bus.

        Handles interrupts for HITL approvals, tracks tokens and cost,
        and publishes RUN_FINISHED or RUN_ERROR events on completion.

        Args:
            handle: The RunHandle tracking this execution.
        """
        bus.publish("RUN_STARTED", run_id=handle.run_id, workflow=handle.workflow)
        config = {"configurable": {"thread_id": handle.run_id}}
        conn = memory.checkpointer_conn()
        saver = memory.get_checkpointer(conn)
        tokens_total = 0
        cost_total = 0.0
        steps_done: list[str] = []
        try:
            app = orchestrator.build_graph(handle.workflow, saver)
            payload: object = {"outputs": {}, "tokens_used": 0, "cost_usd": 0.0}

            while True:
                interrupted = None
                for update in app.stream(payload, config, stream_mode="updates"):
                    if "__interrupt__" in update:
                        interrupted = update["__interrupt__"][0].value
                        break
                    for node_name, node_update in update.items():
                        node_update = node_update or {}
                        tokens = int(node_update.get("tokens_used", 0) or 0)
                        cost = float(node_update.get("cost_usd", 0.0) or 0.0)
                        tokens_total += tokens
                        cost_total += cost
                        steps_done.append(node_name)
                        bus.publish(
                            "STEP_FINISHED",
                            run_id=handle.run_id,
                            workflow=handle.workflow,
                            step=node_name,
                            tokens_used=tokens,
                            cost_usd=cost,
                        )

                if interrupted is None:
                    break  # run completed

                approval = PendingApproval(
                    approval_id=uuid.uuid4().hex[:10],
                    run_id=handle.run_id,
                    workflow=handle.workflow,
                    step=interrupted.get("step", "?"),
                    agent=interrupted.get("agent", "?"),
                    action=interrupted.get("action", "?"),
                    question=interrupted.get("question", "Approve?"),
                )
                with self._lock:
                    self.approvals[approval.approval_id] = approval
                handle.status = "waiting_approval"
                bus.publish(
                    "APPROVAL_REQUIRED",
                    approval_id=approval.approval_id,
                    run_id=handle.run_id,
                    workflow=handle.workflow,
                    step=approval.step,
                    question=approval.question,
                )
                decision = approval.wait(APPROVAL_TIMEOUT_S)
                handle.status = "running"
                if decision is None:
                    raise PermissionError(
                        f"Approval for step '{approval.step}' timed out"
                    )
                payload = Command(resume=decision)

            handle.status = "completed"
            handle.finished_at = time.time()
            memory.finish_run(
                handle.run_id,
                "completed",
                tokens_used=tokens_total,
                cost_usd=cost_total,
                detail={"steps": steps_done, "via": "sidecar"},
            )
            bus.publish(
                "RUN_FINISHED",
                run_id=handle.run_id,
                workflow=handle.workflow,
                tokens_used=tokens_total,
                cost_usd=cost_total,
                steps=steps_done,
            )
        except PermissionError as exc:
            handle.status = "denied"
            handle.finished_at = time.time()
            handle.error = str(exc)
            memory.finish_run(handle.run_id, "interrupted", detail={"reason": str(exc)})
            bus.publish(
                "RUN_ERROR", run_id=handle.run_id, workflow=handle.workflow,
                error=str(exc), kind="denied",
            )
        except SkippedRun as exc:
            handle.status = "skipped"
            handle.finished_at = time.time()
            memory.finish_run(handle.run_id, "skipped", detail={"reason": str(exc)})
            bus.publish(
                "RUN_SKIPPED", run_id=handle.run_id, workflow=handle.workflow,
                reason=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 — report any failure to the GUI
            handle.status = "failed"
            handle.finished_at = time.time()
            handle.error = str(exc)
            memory.finish_run(handle.run_id, "failed", detail={"error": str(exc)})
            bus.publish(
                "RUN_ERROR", run_id=handle.run_id, workflow=handle.workflow,
                error=str(exc), kind="failed",
            )
        finally:
            conn.close()


runner = WorkflowRunner()
