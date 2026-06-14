"""Agent constitution enforcement.

Every side-effectful operation (file write, file delete, HTTP call, shell
command) must pass through guard() before executing. This is the runtime
boundary described in the PRD (TR-07): violations halt execution, they are
not advisory.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


class ConstitutionViolation(Exception):
    """Raised when a tool call violates a hard constraint. Halts the run."""


class ApprovalRequired(Exception):
    """Raised when an action type needs human approval before executing."""

    def __init__(self, action: str, description: str):
        self.action = action
        self.description = description
        super().__init__(f"Approval required for '{action}': {description}")


@dataclass
class Constitution:
    approval_required: dict[str, str] = field(default_factory=dict)
    limits: dict = field(default_factory=dict)
    blocked: list[str] = field(default_factory=list)
    write_allowlist: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None = None) -> "Constitution":
        path = path or CONFIG_DIR / "constitution.yaml"
        raw = yaml.safe_load(path.read_text())["constitution"]
        return cls(
            approval_required={
                item["action"]: item.get("description", "")
                for item in raw.get("approval_required", [])
            },
            limits=raw.get("limits", {}),
            blocked=raw.get("blocked", []),
            write_allowlist=raw.get("write_allowlist", []),
        )

    # ------------------------------------------------------------------
    # Enforcement
    # ------------------------------------------------------------------
    def guard(self, action_type: str, payload: str = "", *, approved: bool = False) -> None:
        """Evaluate a tool call before execution.

        Raises ConstitutionViolation for blocked operations and
        ApprovalRequired for actions needing human sign-off (unless the
        caller passes approved=True after obtaining it).
        """
        for pattern in self.blocked:
            if pattern in payload:
                raise ConstitutionViolation(
                    f"Blocked operation: payload contains '{pattern}'"
                )

        if action_type in self.approval_required and not approved:
            raise ApprovalRequired(action_type, self.approval_required[action_type])

    def guard_write_path(self, target: str | os.PathLike) -> None:
        """Ensure the agent only writes inside allowlisted roots."""
        resolved = Path(target).resolve()
        for root in self.write_allowlist:
            try:
                resolved.relative_to(Path(root).resolve())
                return
            except ValueError:
                continue
        raise ConstitutionViolation(
            f"Write outside allowlisted roots: {resolved}"
        )

    def check_token_budget(self, tokens_used: int) -> None:
        budget = self.limits.get("max_tokens_per_workflow")
        if budget and tokens_used > budget:
            raise ConstitutionViolation(
                f"Token budget exceeded: {tokens_used} > {budget}"
            )

    def check_cost_budget(self, cost_today_usd: float) -> None:
        cap = self.limits.get("max_cost_per_day_usd")
        if cap and cost_today_usd > cap:
            raise ConstitutionViolation(
                f"Daily cost cap exceeded: ${cost_today_usd:.2f} > ${cap:.2f}"
            )

    def check_files_written(self, count: int) -> None:
        cap = self.limits.get("max_files_written_per_run")
        if cap and count > cap:
            raise ConstitutionViolation(
                f"File-write cap exceeded: {count} > {cap}"
            )
