"""Briefing agent — composes the morning brief.

Routes every model call through the unified LLM provider layer
(``core/llm.py``, FR-52) so cloud (Anthropic) and local (Ollama) models share
one entry point, one model registry, and one cost accountant. When the chosen
model isn't usable (e.g. a cloud model with no ANTHROPIC_API_KEY, or a local
model with Ollama down), it falls back to a deterministic template so the
pipeline can be tested end-to-end without spending tokens (controlled by
settings.allow_template_fallback). Token usage is reported back so the
orchestrator can enforce the constitution's token budget.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import yaml

CONFIG = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "config" / "settings.yaml").read_text()
)["settings"]

_SYSTEM = (
    "You are the briefing agent of a personal Agentic OS. Compose a concise, "
    "well-structured morning briefing in Markdown from the JSON context "
    "provided. Sections: Today's Focus (from active projects + open tasks), "
    "New Since Last Brief (from vault.recent_docs — documents created since the "
    "last briefing; group or list them by folder, and if the list is empty say "
    "there's nothing new), Inbox (raw note queue), Codehome Status. Keep it "
    "under 300 words, actionable, no filler. Start with a single H1 title line."
)


def _template_brief(vault: dict, hub: dict) -> str:
    """Build a deterministic morning briefing from vault and hub data.

    Args:
        vault: Vault state dict with projects, raw notes, open tasks, and recent docs.
        hub: Codehome Hub state dict with app statuses.

    Returns:
        Markdown-formatted briefing string.
    """
    today = dt.date.today().strftime("%A, %B %d, %Y")
    lines = [f"# Morning Briefing — {today}", ""]

    lines.append("## Today's Focus")
    active = [p for p in vault.get("projects", []) if str(p.get("status", "")).lower() in ("active", "in-progress")]
    for p in active or vault.get("projects", [])[:3]:
        prio = f" ({p.get('priority')})" if p.get("priority") else ""
        lines.append(f"- **{p.get('name', 'untitled')}**{prio} — status: {p.get('status', 'unknown')}")
    if vault.get("open_tasks"):
        lines.append("")
        lines.append("Open tasks:")
        lines.extend(f"- [ ] {t}" for t in vault.get("open_tasks", [])[:5])

    lines.append("")
    lines.append("## New Since Last Brief")
    recent = vault.get("recent_docs", [])
    if recent:
        since = vault.get("recent_since", "")
        window = " (first run — last 24h)" if vault.get("recent_cold_start") else ""
        lines.append(f"*{len(recent)} doc(s) created since {since}{window}:*")
        for d in recent[:15]:
            folder = f" — `{d['folder']}`" if d.get("folder") else ""
            lines.append(f"- {d['title']}{folder}")
        if len(recent) > 15:
            lines.append(f"- …and {len(recent) - 15} more")
    else:
        lines.append("- Nothing new since the last briefing.")

    lines.append("")
    lines.append("## Inbox")
    lines.append(f"- {vault.get('raw_note_count', 0)} unprocessed note(s) in `00 - Raw/`")

    lines.append("")
    lines.append("## Codehome Status")
    if hub.get("hub_up"):
        lines.append(f"- Hub is up — {hub.get('running_count', 0)} app(s) running")
        for app in hub.get("apps", []):
            # _normalise_app() returns a boolean `running` key (not `status`).
            if app.get("running"):
                lines.append(f"  - {app.get('name', 'unknown')} (port {app.get('port', '?')})")
    else:
        lines.append("- Hub unreachable")

    lines.append("")
    lines.append("*(template brief — set ANTHROPIC_API_KEY for an AI-composed brief)*")
    return "\n".join(lines)


def compose_brief(state: dict) -> dict:
    """Compose the morning briefing using an LLM or a template fallback.

    Args:
        state: Pipeline state dict containing vault and hub outputs, plus an
            optional ``model`` key selecting the LLM.

    Returns:
        Dict with ``brief`` (Markdown text), ``tokens_used``, ``mode``, and
        optionally ``cost_usd`` and ``model``.

    Raises:
        RuntimeError: If the selected model is unavailable and template
            fallback is disabled.
    """
    vault = state["outputs"]["read_vault"]
    hub = state["outputs"]["check_hub"]

    from core import llm

    model_id = llm.resolve(state.get("model", "default"))

    # If the selected model can't run right now (no API key for a cloud model,
    # or Ollama down for a local one), fall back to the deterministic template.
    if not llm.is_available(model_id):
        if not CONFIG.get("allow_template_fallback", True):
            raise RuntimeError(
                f"Model '{model_id}' unavailable and template fallback disabled"
            )
        return {"brief": _template_brief(vault, hub), "tokens_used": 0, "mode": "template"}

    # Daily cost cap gate — checked BEFORE spending (constitution limit).
    # Local models are priced 0, so this is a no-op for them.
    from core import memory
    from core.constitution import Constitution

    Constitution.load().check_cost_budget(memory.cost_today())

    # Carry the persistent agent identity + memory into the brief (FR: Soul/Memory).
    from core import soul

    preamble = soul.identity_preamble()
    system = f"{preamble}\n\n{_SYSTEM}" if preamble else _SYSTEM

    context = json.dumps({"vault": vault, "hub": hub}, indent=2)
    result = llm.complete(
        [{"role": "user", "content": f"Context:\n{context}"}],
        system=system,
        model=model_id,
        max_tokens=1024,
    )
    return {
        "brief": result.text,
        "tokens_used": result.tokens_used,
        "cost_usd": result.cost_usd,
        "mode": result.provider,  # "anthropic" | "ollama"
        "model": result.model,
    }


ACTIONS = {"compose_brief": compose_brief}
