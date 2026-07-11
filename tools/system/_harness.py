"""System-MCP harness — Phase 15a (design §3.3).

The heart of the OSA System MCP: a decorator-driven capability registry that
applies the Constitution-backed safety guard AT REGISTRATION TIME, so it is
impossible to register a capability that isn't governed. One guard, both
doors — OSA importing a capability in-process and Claude Desktop/Code calling
it over stdio MCP land on the identical guarded function.

Replaces `hub_mcp.py`'s hand-maintained if/elif `call_tool` dispatch: the
aggregator's `call_tool` becomes a registry lookup, and `list_tools` is
generated from the registered schemas.

Guard semantics (mirrors ``core.constitution.Constitution.guard``):
  * policy says **deny**    → raise ``ConstitutionViolation`` (never runs;
                              ``approved=True`` cannot override).
  * policy says **approve** → raise ``ApprovalRequired`` unless the caller
                              passes ``approved=True`` (obtained via the HITL
                              approval flow — OSA's two-turn confirm or the
                              approval queue).
  * policy says **allow**   → run.
"""
from __future__ import annotations

import functools
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Literal

from core.constitution import ApprovalRequired, Constitution, ConstitutionViolation

from tools.system import _policy

Effect = Literal["read", "mutate", "irreversible"]


@dataclass
class Capability:
    """One registered, guarded system capability.

    Attributes:
        name: MCP tool name, e.g. ``"macos.run_command"``.
        domain: ``"macos" | "fs" | "messages" | "mail"``.
        effect: Effect class driving the safety ladder.
        auto: Runs without approval in strict mode (benign reads/mutates).
        func: The GUARDED callable (what both OSA and the MCP server call).
        schema: JSON schema for MCP ``list_tools``.
        description: One-line human description for ``list_tools``.
    """

    name: str
    domain: str
    effect: Effect
    auto: bool
    func: Callable
    schema: dict
    description: str


REGISTRY: dict[str, Capability] = {}

# Test seam: inject a Constitution for every guard evaluation. None = load
# the real YAML per call (cheap — yaml parse — and always current).
_constitution_override: Constitution | None = None


def set_constitution(constitution: Constitution | None) -> None:
    """Inject (or clear) a Constitution for guard checks. Test seam."""
    global _constitution_override
    _constitution_override = constitution


def _payload_of(
    cap_name: str, args: tuple, kwargs: dict, first_param: str | None = None
) -> str:
    """Extract the side-effect payload string for policy/audit purposes.

    The payload is the capability's FIRST parameter — ``command`` for
    run_command, ``path``/``root``/``src`` for the fs domain — whether it
    arrives positionally or as a keyword. ``first_param`` (captured from the
    function signature at registration) makes the keyword form visible:
    without it, ``dispatch(**arguments)`` calls produced an empty payload and
    the root-scoping/denylist checks silently saw nothing (15b bug, fixed).
    """
    if first_param is not None and isinstance(kwargs.get(first_param), str):
        return kwargs[first_param]
    if "command" in kwargs:  # legacy fallback, harmless
        return str(kwargs["command"])
    if args and isinstance(args[0], str):
        return args[0]
    return ""


def _guard(cap_name: str, effect: Effect, auto: bool, func: Callable) -> Callable:
    """Wrap ``func`` in the capability-layer guard (design decision #2).

    The wrapper accepts an extra ``approved: bool = False`` keyword —
    mirroring ``Constitution.guard`` — so a caller that has ALREADY obtained
    human approval (OSA's two-turn confirm, the approval queue) can proceed.
    Denies can never be overridden.
    """
    # Captured ONCE at registration: the name of the function's first
    # parameter, so keyword-style calls (the MCP dispatch path calls
    # ``func(**arguments)``) yield the same payload as positional calls.
    try:
        first_param = next(iter(inspect.signature(func).parameters), None)
    except (TypeError, ValueError):  # exotic callables — fall back gracefully
        first_param = None

    @functools.wraps(func)
    def wrapper(*args: Any, approved: bool = False, **kwargs: Any) -> Any:
        payload = _payload_of(cap_name, args, kwargs, first_param)
        result = _policy.evaluate(
            name=cap_name,
            effect=effect,
            auto=auto,
            payload=payload,
            constitution=_constitution_override,
        )
        if result.decision == "deny":
            raise ConstitutionViolation(
                f"Blocked capability call '{cap_name}': {result.reason}"
            )
        if result.decision == "approve" and not approved:
            raise ApprovalRequired(cap_name, f"{result.reason}: {payload or cap_name}")
        return func(*args, **kwargs)

    return wrapper


def capability(
    name: str,
    *,
    domain: str,
    effect: Effect,
    schema: dict,
    auto: bool = False,
    description: str | None = None,
) -> Callable:
    """Register a capability AND wrap it in the guard — one decorator.

    The guard is applied HERE, at the capability layer, so every caller —
    OSA in-process, Claude Desktop/Code over stdio — is equally gated.

    Args:
        name: MCP tool name (``domain.verb`` convention).
        domain: Capability domain for grouping.
        effect: ``read`` / ``mutate`` / ``irreversible``.
        schema: JSON input schema for MCP ``list_tools``.
        auto: True for benign capabilities that run without approval in
            strict mode (design §5's "auto" markers).
        description: One-liner for ``list_tools``; defaults to the wrapped
            function's first docstring line.
    """

    def deco(func: Callable) -> Callable:
        guarded = _guard(name, effect, auto, func)
        desc = description or (func.__doc__ or name).strip().splitlines()[0]
        REGISTRY[name] = Capability(
            name=name,
            domain=domain,
            effect=effect,
            auto=auto,
            func=guarded,
            schema=schema,
            description=desc,
        )
        return guarded  # OSA imports the guarded version too

    return deco
