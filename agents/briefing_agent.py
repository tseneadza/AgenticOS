"""Briefing agent — composes the morning brief.

Uses the Claude API when ANTHROPIC_API_KEY is set; otherwise falls back to a
deterministic template so the pipeline can be tested end-to-end without
spending tokens (controlled by settings.allow_template_fallback).
Token usage is reported back so the orchestrator can enforce the
constitution's token budget.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import yaml

CONFIG = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "config" / "settings.yaml").read_text()
)["settings"]

_SYSTEM = (
    "You are the briefing agent of a personal Agentic OS. Compose a concise, "
    "well-structured morning briefing in Markdown from the JSON context "
    "provided. Sections: Today's Focus (from active projects + open tasks), "
    "Inbox (raw note queue), Codehome Status. Keep it under 300 words, "
    "actionable, no filler. Start with a single H1 title line."
)


def _template_brief(vault: dict, hub: dict) -> str:
    today = dt.date.today().strftime("%A, %B %d, %Y")
    lines = [f"# Morning Briefing — {today}", ""]

    lines.append("## Today's Focus")
    active = [p for p in vault["projects"] if p["status"].lower() in ("active", "in-progress")]
    for p in active or vault["projects"][:3]:
        prio = f" ({p['priority']})" if p["priority"] else ""
        lines.append(f"- **{p['name']}**{prio} — status: {p['status']}")
    if vault["open_tasks"]:
        lines.append("")
        lines.append("Open tasks:")
        lines.extend(f"- [ ] {t}" for t in vault["open_tasks"][:5])

    lines.append("")
    lines.append("## Inbox")
    lines.append(f"- {vault['raw_note_count']} unprocessed note(s) in `00 - Raw/`")

    lines.append("")
    lines.append("## Codehome Status")
    if hub.get("hub_up"):
        lines.append(f"- Hub is up — {hub['running_count']} app(s) running")
        for app in hub["apps"]:
            if str(app["status"]).lower() == "running":
                lines.append(f"  - {app['name']} (port {app['port']})")
    else:
        lines.append("- Hub unreachable")

    lines.append("")
    lines.append("*(template brief — set ANTHROPIC_API_KEY for an AI-composed brief)*")
    return "\n".join(lines)


def compose_brief(state: dict) -> dict:
    vault = state["outputs"]["read_vault"]
    hub = state["outputs"]["check_hub"]

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        if not CONFIG.get("allow_template_fallback", True):
            raise RuntimeError("ANTHROPIC_API_KEY not set and template fallback disabled")
        return {"brief": _template_brief(vault, hub), "tokens_used": 0, "mode": "template"}

    # Daily cost cap gate — checked BEFORE spending (constitution limit)
    from core import memory
    from core.constitution import Constitution

    Constitution.load().check_cost_budget(memory.cost_today())

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    model_alias = state.get("model", "default")
    model = CONFIG["models"].get(model_alias, CONFIG["models"]["default"])

    context = json.dumps({"vault": vault, "hub": hub}, indent=2)
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": f"Context:\n{context}"}],
    )
    brief = "".join(block.text for block in resp.content if block.type == "text")
    tokens = resp.usage.input_tokens + resp.usage.output_tokens
    cost = _cost_usd(model, resp.usage.input_tokens, resp.usage.output_tokens)
    return {
        "brief": brief,
        "tokens_used": tokens,
        "cost_usd": cost,
        "mode": "claude",
        "model": model,
    }


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost from the settings pricing table (USD per MTok).

    Unknown models fall back to the most expensive listed rates so the cap
    errs conservative rather than undercounting.
    """
    pricing = CONFIG.get("pricing", {})
    if not pricing:
        return 0.0
    rates = pricing.get(model) or max(
        pricing.values(), key=lambda r: r["input"] + r["output"]
    )
    return round(
        input_tokens * rates["input"] / 1e6 + output_tokens * rates["output"] / 1e6, 6
    )


ACTIONS = {"compose_brief": compose_brief}
