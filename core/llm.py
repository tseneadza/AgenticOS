"""Unified LLM provider layer (Phase 10 / NF-3, FR-52/53).

One seam over cloud (Anthropic) and local (Ollama) chat models so the rest of
the OS has a *single* place that constructs a model, lists what's available,
tracks the active model, and accounts for tokens + cost. The governing agent
(FR-54) and the briefing agent both build on this — there must be exactly one
LLM entry point.

Design notes
------------
* LangChain packages are imported lazily inside the functions that need them,
  so this module imports cleanly (and the registry/cost helpers stay testable)
  even in an environment where ``langchain_*`` or Ollama is not installed.
* Model identity flows as a concrete *id* (e.g. ``"claude-sonnet-4-6"`` or
  ``"qwen2.5:7b-instruct"``). Workflow steps still use short *aliases*
  (``default`` / ``fast`` / ``local``); ``resolve()`` maps an alias→id.
* Local (Ollama) models are priced 0, so local turns never consume the daily
  cost cap enforced by the Constitution.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"


def _settings() -> dict:
    return yaml.safe_load(_SETTINGS_PATH.read_text())["settings"]


# --------------------------------------------------------------------------- #
# Model registry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ModelInfo:
    id: str
    provider: str  # "anthropic" | "ollama"
    label: str
    context_window: int = 0
    supports_tools: bool = True
    cost_per_mtok: dict = field(default_factory=lambda: {"input": 0.0, "output": 0.0})

    @property
    def is_local(self) -> bool:
        return self.provider == "ollama"


def _agent_cfg() -> dict:
    return _settings().get("agent", {}) or {}


def registry() -> list[ModelInfo]:
    """Configured models from settings.yaml > agent.models (FR-53)."""
    out: list[ModelInfo] = []
    for m in _agent_cfg().get("models", []) or []:
        out.append(
            ModelInfo(
                id=m["id"],
                provider=m.get("provider", "anthropic"),
                label=m.get("label", m["id"]),
                context_window=int(m.get("context_window", 0)),
                supports_tools=bool(m.get("supports_tools", True)),
                cost_per_mtok=m.get("cost_per_mtok", {"input": 0.0, "output": 0.0}),
            )
        )
    return out


def get_model_info(model_id: str) -> ModelInfo | None:
    for info in registry():
        if info.id == model_id:
            return info
    return None


def resolve(alias_or_id: str | None) -> str:
    """Map a workflow alias (default/fast/local) to a concrete model id.

    Passing a concrete id (or an unknown string) returns it unchanged, so the
    function is safe to call on either form.
    """
    if not alias_or_id:
        return active_model()
    aliases = _settings().get("models", {}) or {}
    return aliases.get(alias_or_id, alias_or_id)


def _normalize_ollama_host(value: str) -> str:
    """Normalize an OLLAMA_HOST-style value into a base URL.

    Accepts a full URL ("http://host:port"), a bare port ("12434"), a host, or
    "host:port" — the same flexible forms the official ollama client accepts.
    A 0.0.0.0 bind address is mapped to 127.0.0.1 for connecting.
    """
    value = value.strip()
    if "://" not in value:
        if value.isdigit():
            host, port = "127.0.0.1", value
        elif ":" in value:
            host, port = value.rsplit(":", 1)
        else:
            host, port = value, "11434"
        host = host or "127.0.0.1"
        if host == "0.0.0.0":  # noqa: S104 — bind-all → loopback for connecting
            host = "127.0.0.1"
        value = f"http://{host}:{port}"
    return value.rstrip("/")


def ollama_base_url() -> str:
    """Base URL of the local Ollama service.

    Honors the standard ``OLLAMA_HOST`` env var first (so the sidecar aligns
    with whatever the user's ollama CLI/other tools use), then falls back to
    settings.yaml > agent.ollama_base_url, then the Ollama default :11434.
    """
    env = os.environ.get("OLLAMA_HOST")
    if env:
        return _normalize_ollama_host(env)
    return _agent_cfg().get("ollama_base_url", "http://localhost:11434")


# --------------------------------------------------------------------------- #
# Active-model session state (single-process sidecar)
# --------------------------------------------------------------------------- #
_lock = threading.Lock()
_active: str | None = None


def active_model() -> str:
    """Currently selected model id. Defaults to settings.agent.default_model."""
    global _active
    with _lock:
        if _active is None:
            _active = _agent_cfg().get("default_model") or (
                registry()[0].id if registry() else "claude-sonnet-4-6"
            )
        return _active


def set_active_model(model_id: str) -> ModelInfo:
    """Set the model used for subsequent turns. Raises KeyError if unknown."""
    info = get_model_info(model_id)
    if info is None:
        raise KeyError(model_id)
    global _active
    with _lock:
        _active = model_id
    return info


# --------------------------------------------------------------------------- #
# Availability
# --------------------------------------------------------------------------- #
def _ollama_installed_ids(timeout: float = 1.5) -> set[str]:
    """Model ids reported by a running Ollama service, or empty if it's down.

    Ollama is treated as optional everywhere: any failure → no local models.
    """
    try:
        import requests

        resp = requests.get(f"{ollama_base_url()}/api/tags", timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return set()
    return {m.get("name", "") for m in data.get("models", []) if m.get("name")}


def is_available(model_id: str) -> bool:
    """Can we actually run this model right now?

    * anthropic → ANTHROPIC_API_KEY must be set.
    * ollama → the service must be up and the model pulled.
    """
    info = get_model_info(model_id)
    provider = info.provider if info else "anthropic"
    if provider == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    if provider == "ollama":
        return model_id in _ollama_installed_ids()
    return False


def list_models() -> dict:
    """Payload for GET /api/agent/models (FR-53).

    Cloud models are always listed (with ``available`` keyed on the API key);
    local models are listed from the registry with an ``installed`` flag from
    Ollama's tag list. If Ollama is down, locals show installed=False.
    """
    installed = _ollama_installed_ids()
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    models: list[dict[str, Any]] = []
    for info in registry():
        if info.provider == "ollama":
            inst = info.id in installed
            available = inst
        else:
            inst = True
            available = has_key
        models.append(
            {
                "id": info.id,
                "provider": info.provider,
                "label": info.label,
                "context_window": info.context_window,
                "supports_tools": info.supports_tools,
                "cost_per_mtok": info.cost_per_mtok,
                "is_local": info.is_local,
                "installed": inst,
                "available": available,
            }
        )
    return {"active": active_model(), "ollama_up": bool(installed), "models": models}


# --------------------------------------------------------------------------- #
# Cost accounting
# --------------------------------------------------------------------------- #
def cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """USD cost of a call. Prefers the registry's cost_per_mtok, falls back to
    settings.pricing, then (for unknown cloud ids) the most expensive rate so
    the cap errs conservative. Local models are 0.
    """
    info = get_model_info(model_id)
    if info is not None:
        rates = info.cost_per_mtok
    else:
        pricing = _settings().get("pricing", {}) or {}
        rates = pricing.get(model_id)
        if rates is None:
            if not pricing:
                return 0.0
            rates = max(pricing.values(), key=lambda r: r["input"] + r["output"])
    return round(
        input_tokens * rates.get("input", 0.0) / 1e6
        + output_tokens * rates.get("output", 0.0) / 1e6,
        6,
    )


# --------------------------------------------------------------------------- #
# Model construction + completion
# --------------------------------------------------------------------------- #
def get_chat_model(model_id: str | None = None, **kwargs: Any):
    """Return a LangChain chat model for ``model_id`` (or the active model).

    ChatAnthropic for cloud, ChatOllama for local. LangChain imports are lazy
    so this module loads even when those packages aren't installed.
    """
    model_id = model_id or active_model()
    info = get_model_info(model_id)
    provider = info.provider if info else "anthropic"

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model_id, **kwargs)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model_id, base_url=ollama_base_url(), **kwargs)
    raise ValueError(f"Unknown provider for model '{model_id}': {provider}")


@dataclass
class LLMResult:
    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def tokens_used(self) -> int:
        return self.input_tokens + self.output_tokens


def _to_lc_messages(system: str | None, messages: list[dict]):
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    lc: list[Any] = []
    if system:
        lc.append(SystemMessage(content=system))
    role_map = {"user": HumanMessage, "human": HumanMessage, "assistant": AIMessage, "ai": AIMessage}
    for m in messages:
        role = m.get("role", "user")
        if role == "system":
            lc.append(SystemMessage(content=m["content"]))
        else:
            lc.append(role_map.get(role, HumanMessage)(content=m["content"]))
    return lc


def complete(
    messages: list[dict],
    *,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 1024,
    **kwargs: Any,
) -> LLMResult:
    """Single non-streaming completion through the unified layer.

    Returns text plus token + cost accounting so callers can enforce the
    Constitution's budgets uniformly across cloud and local models.
    """
    model_id = model or active_model()
    info = get_model_info(model_id)
    provider = info.provider if info else "anthropic"

    chat = get_chat_model(model_id, max_tokens=max_tokens, **kwargs)
    resp = chat.invoke(_to_lc_messages(system, messages))

    text = resp.content if isinstance(resp.content, str) else "".join(
        part.get("text", "") if isinstance(part, dict) else str(part)
        for part in resp.content
    )
    usage = getattr(resp, "usage_metadata", None) or {}
    in_tok = int(usage.get("input_tokens", 0))
    out_tok = int(usage.get("output_tokens", 0))
    return LLMResult(
        text=text,
        model=model_id,
        provider=provider,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=cost_usd(model_id, in_tok, out_tok),
    )
