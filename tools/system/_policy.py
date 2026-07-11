"""System-MCP safety policy — Phase 15a (design §4).

Pure decision logic: given a capability + its payload, answer one of
``"allow" | "approve" | "deny"``. The harness (`_harness.py`) turns those
answers into execution / ``ApprovalRequired`` / ``ConstitutionViolation``.

The safety ladder (design §4.1):

  strict mode (start): auto-marked capabilities run; ``macos.run_command``
      runs only if the command matches the terminal allowlist, else halts to
      approval; everything else halts to approval.
  effect mode (target, flipped in 15e): reads run; mutate/irreversible halt
      to approval; run_command still honors the allowlist.

Denylist patterns are ALWAYS deny, in both modes — they are checked before
anything else, and even an ``approved=True`` call can never pass one (the
harness re-checks).

Config comes from ``config/constitution.yaml``'s ``system_mcp`` block via
``core.constitution.Constitution`` (defaults-merged, so pre-15a configs load
unchanged). Pass a ``Constitution`` explicitly for tests.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.constitution import Constitution

Decision = str  # "allow" | "approve" | "deny"


@dataclass
class PolicyResult:
    """A policy decision plus the human-readable reason behind it."""

    decision: Decision
    reason: str


def _match_denylist(payload: str, patterns: list[str]) -> str | None:
    """Return the first denylist pattern found in ``payload``, or None."""
    for pattern in patterns:
        if pattern and pattern in payload:
            return pattern
    return None


def _match_allowlist(command: str, allowlist: list[str]) -> bool:
    """Whether ``command`` is allowlisted (exact match or first-word prefix).

    Prefix rules match on word boundaries so ``ls`` allows ``ls -la ~/Codehome``
    but does NOT allow ``lsof`` (a substring-prefix would). Multi-word entries
    like ``git status`` must match the leading words exactly.
    """
    cmd = command.strip()
    for entry in allowlist:
        entry = (entry or "").strip()
        if not entry:
            continue
        if cmd == entry or cmd.startswith(entry + " "):
            return True
    return False


def evaluate(
    *,
    name: str,
    effect: str,
    auto: bool,
    payload: str = "",
    constitution: Constitution | None = None,
) -> PolicyResult:
    """Decide what to do with one capability call.

    Args:
        name: Capability name (e.g. ``"macos.run_command"``).
        effect: ``"read" | "mutate" | "irreversible"``.
        auto: Capability-level auto flag (benign reads/mutates the design
            marks "auto" — get_time, system_info, notify, …).
        payload: The side-effect payload (the command string for
            run_command; empty for pure reads).
        constitution: Injected for tests; loaded from YAML if omitted.

    Returns:
        A :class:`PolicyResult` — allow / approve / deny + reason.
    """
    constitution = constitution or Constitution.load()
    cfg = constitution.system_mcp
    mode = cfg.get("mode", "strict")
    terminal = cfg.get("terminal", {})

    # 1. Denylist — always deny, both modes, approval can't override.
    hit = _match_denylist(payload, terminal.get("denylist_patterns", []))
    if hit:
        return PolicyResult("deny", f"payload contains denylisted pattern '{hit}'")

    # 2. Terminal commands — the allowlist governs in BOTH modes (effect-mode
    #    relaxation of run_command is a 15e decision, not automatic).
    if name == "macos.run_command":
        if not payload.strip():
            # Nothing can execute — let the capability body return its own
            # clean "empty command" error instead of asking approval for ''.
            return PolicyResult("allow", "empty command (no-op)")
        if _match_allowlist(payload, terminal.get("allowlist", [])):
            return PolicyResult("allow", "command is allowlisted")
        return PolicyResult("approve", "non-allowlisted terminal command")

    # 3. Everything else by mode.
    if mode == "effect":
        if effect == "read":
            return PolicyResult("allow", "read capability (effect mode)")
        return PolicyResult("approve", f"{effect} capability (effect mode)")

    # strict mode (default): only auto-marked capabilities run.
    if auto:
        return PolicyResult("allow", "auto capability (strict mode)")
    return PolicyResult("approve", "non-auto capability (strict mode)")
