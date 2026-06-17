#!/usr/bin/env python3
"""Diagnose "the agent has no tools available" on local models.

The wiring already binds tools: ``governor.build_agent`` →
``create_react_agent(model, tools, prompt=GOVERNOR_SYSTEM)`` and create_react_agent
calls ``model.bind_tools(tools)``. So "no tools" is almost always one of:

  (a) the model never EMITS a tool call (small local models often answer in prose
      and even claim they have no tools), or
  (b) ``bind_tools`` isn't attaching (version/signature), or
  (c) the Ollama model doesn't advertise tool support at all.

This probe tells them apart for a given model. Run on the Mac, from the repo root,
with the project venv:

    cd ~/Codehome/AgenticOS
    ./.venv/bin/python scripts/diagnose_tools.py                 # active model
    ./.venv/bin/python scripts/diagnose_tools.py llama3.1:8b     # a specific model
    ./.venv/bin/python scripts/diagnose_tools.py claude-sonnet-4-6   # cloud control

Paste the full output back. If cloud emits tool_calls but local doesn't, it's a
local-capability issue (b/c ruled out); if NOTHING emits tool_calls, suspect the
binding/version.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROMPTS = ["list my workflows", "what is the system status?"]


def hr(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def pkg_version(name: str) -> str:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception as exc:  # noqa: BLE001
        return f"? ({exc})"


def ollama_show(model_id: str) -> None:
    """Ask Ollama whether this model advertises tool support."""
    from core import llm

    try:
        import requests

        base = llm.ollama_base_url()
        # newer Ollama uses "model", older "name" — send both.
        resp = requests.post(f"{base}/api/show",
                             json={"model": model_id, "name": model_id}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        print(f"  /api/show failed: {exc}")
        return
    caps = data.get("capabilities") or []
    print(f"  capabilities: {caps}")
    tmpl = (data.get("template") or "")
    print(f"  template mentions tools: {'tools' in tmpl.lower() or '.Tools' in tmpl}")
    if "tools" in [c.lower() for c in caps]:
        print("  → Ollama reports this model SUPPORTS tools.")
    else:
        print("  → Ollama does NOT list 'tools' capability — native tool-calling "
              "may be unavailable for this model.")


def main() -> None:
    from core import llm

    model_id = sys.argv[1] if len(sys.argv) > 1 else llm.active_model()
    info = llm.get_model_info(model_id)
    provider = info.provider if info else "anthropic"

    hr("0. Versions / target")
    for p in ("langgraph", "langgraph-prebuilt", "langchain-core",
              "langchain-ollama", "langchain-anthropic", "anthropic"):
        print(f"  {p:22} {pkg_version(p)}")
    print(f"  target model           {model_id}  (provider={provider})")
    print(f"  available              {llm.is_available(model_id)}")

    if provider == "ollama":
        hr("1. Does Ollama advertise tool support for this model?")
        ollama_show(model_id)

    hr("2. Build tools + bind to the model")
    from langchain_core.messages import HumanMessage, SystemMessage

    from agents import governor

    tools = governor.build_tools(governor.GovernorToolbox())
    print(f"  tools built: {len(tools)} -> {[t.name for t in tools]}")

    model = llm.get_chat_model(model_id)
    if not hasattr(model, "bind_tools"):
        print("  ✗ model has NO bind_tools() — tool-calling unsupported by this class.")
        return
    try:
        bound = model.bind_tools(tools)
        print("  ✓ model.bind_tools(tools) OK")
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ bind_tools raised: {type(exc).__name__}: {exc}")
        return

    hr("3. Does the BOUND model emit tool_calls? (the decisive test)")
    for prompt in PROMPTS:
        try:
            resp = bound.invoke(
                [SystemMessage(content=governor.GOVERNOR_SYSTEM),
                 HumanMessage(content=prompt)]
            )
            tcs = getattr(resp, "tool_calls", None) or []
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            print(f"\n  prompt: {prompt!r}")
            print(f"    tool_calls: {[tc.get('name') for tc in tcs] if tcs else '[] (NONE — answered in prose)'}")
            if not tcs:
                print(f"    prose[:200]: {text[:200]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  prompt {prompt!r} raised: {type(exc).__name__}: {exc}")

    hr("4. Full create_react_agent turn (what the sidecar runs)")
    try:
        agent = governor.build_agent(model_id, toolbox=governor.GovernorToolbox())
        out = agent.invoke({"messages": [HumanMessage(content="list my workflows")]})
        msgs = out.get("messages", []) if isinstance(out, dict) else []
        called = []
        final = ""
        for m in msgs:
            for tc in (getattr(m, "tool_calls", None) or []):
                called.append(tc.get("name"))
            if m.__class__.__name__ == "AIMessage":
                c = m.content
                final = c if isinstance(c, str) else str(c)
        print(f"  tools invoked during the run: {called or '[] (none)'}")
        print(f"  final reply[:240]: {final[:240]!r}")
    except TypeError as exc:
        print(f"  ✗ create_react_agent TypeError (signature mismatch?): {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ run raised: {type(exc).__name__}: {exc}")

    hr("Interpretation")
    print(
        "  §3 tool_calls NON-empty  ⇒ binding works; the GUI 'no tools' was a one-off\n"
        "                             prose answer — hardening the prompt should fix it.\n"
        "  §3 empty on local but a CLOUD run (re-run with claude-sonnet-4-6) shows\n"
        "     tool_calls ⇒ local-model capability gap (see §1 capabilities).\n"
        "  §3 empty EVERYWHERE / §4 TypeError ⇒ binding or langgraph-version issue."
    )


if __name__ == "__main__":
    main()
