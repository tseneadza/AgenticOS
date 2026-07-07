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

import contextlib
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"

# Provider adapter registry (populated lower in this module). Declared up here so
# ModelInfo.is_local can reference _LOCAL_PROVIDERS at call time.
_PROVIDERS: dict = {}
_LOCAL_PROVIDERS: set[str] = set()


def _settings() -> dict:
    """Load and return the 'settings' section from settings.yaml."""
    return yaml.safe_load(_SETTINGS_PATH.read_text())["settings"]


# --------------------------------------------------------------------------- #
# Model registry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ModelInfo:
    """Metadata for a registered LLM model.

    Attributes:
        id: Concrete model identifier (e.g. "claude-sonnet-4-6").
        provider: Backend provider name (e.g. "anthropic", "ollama").
        label: Human-readable display label.
        context_window: Maximum context length in tokens (0 if unknown).
        supports_tools: Whether the model supports tool/function calling.
        cost_per_mtok: Per-million-token cost dict with "input" and "output" keys.
        base_url: Optional provider endpoint override.
        api_key_env: Optional env var name holding this model's API key.
        extra: Passthrough kwargs forwarded to the LangChain constructor.
    """

    id: str
    provider: str  # "anthropic" | "ollama" | "openai_compatible" | "google" | custom
    label: str
    context_window: int = 0
    supports_tools: bool = True
    cost_per_mtok: dict = field(default_factory=lambda: {"input": 0.0, "output": 0.0})
    base_url: str | None = None       # provider endpoint (openai_compatible / gateways)
    api_key_env: str | None = None    # env var holding this model's API key
    extra: dict = field(default_factory=dict)  # passthrough kwargs to the LC ctor

    @property
    def is_local(self) -> bool:
        """True if this model runs on a local provider (e.g. Ollama)."""
        return self.provider in _LOCAL_PROVIDERS


def _agent_cfg() -> dict:
    """Return the 'agent' sub-section of settings, defaulting to empty dict."""
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
                base_url=m.get("base_url"),
                api_key_env=m.get("api_key_env"),
                extra=m.get("extra", {}) or {},
            )
        )
    return out


def get_model_info(model_id: str) -> ModelInfo | None:
    """Look up ModelInfo by id from the registry or discovered Ollama models.

    Args:
        model_id: Concrete model identifier to look up.

    Returns:
        The ModelInfo if found, or None.
    """
    for info in registry():
        if info.id == model_id:
            return info
    # Dynamically discovered Ollama models (pulled but not in settings.yaml).
    with _discovery_lock:
        return _discovered.get(model_id)


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


# Anthropic cloud endpoint. Pinned (configurable via settings) so the OS's cloud
# path is self-contained and is NOT hijacked by ambient ``ANTHROPIC_BASE_URL`` /
# ``ANTHROPIC_AUTH_TOKEN`` a user may export to route OTHER tools (e.g. Claude
# Code) through a local Ollama/proxy. Without this, "cloud" requests silently
# hit that local endpoint and 404 / fail to connect (Open issue #2).
_DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"


def anthropic_base_url() -> str:
    """Return the Anthropic API base URL from settings, or the default."""
    return _agent_cfg().get("anthropic_base_url") or _DEFAULT_ANTHROPIC_BASE_URL


@contextlib.contextmanager
def _isolated_anthropic_env():
    """Temporarily drop ambient ANTHROPIC_* routing vars while constructing the
    cloud client, so a gateway/Ollama-routing shell can't redirect it. Restored
    immediately after — other tools and the user's shell are unaffected."""
    saved: dict[str, str] = {}
    for var in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"):
        if var in os.environ:
            saved[var] = os.environ.pop(var)
    try:
        yield
    finally:
        os.environ.update(saved)


# --------------------------------------------------------------------------- #
# Active-model session state (single-process sidecar)
# --------------------------------------------------------------------------- #
_lock = threading.Lock()
_active: str | None = None

# Discovered-Ollama state (models pulled on the machine, not just the ones
# configured in settings.yaml). Populated by discover_ollama(); short TTL cache
# so repeated list/cost calls don't hammer /api/tags.
_discovery_lock = threading.Lock()
_discovered: dict[str, ModelInfo] = {}
_discovered_meta: dict[str, dict] = {}
_discovered_at: float = 0.0
_DISCOVERY_TTL = 5.0  # seconds
_ollama_proc: Any = None  # handle to a sidecar-spawned `ollama serve`


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
    """Set the model used for subsequent turns. Raises KeyError if unknown.

    Unknown ids trigger a forced Ollama re-discovery first, so a model the user
    just pulled (and selected in the dropdown) can be activated even though it
    isn't in settings.yaml.
    """
    info = get_model_info(model_id)
    if info is None:
        discover_ollama(force=True)
        info = get_model_info(model_id)
    if info is None:
        raise KeyError(model_id)
    global _active
    with _lock:
        _active = model_id
    return info


# --------------------------------------------------------------------------- #
# Ollama service: liveness, auto-start, discovery
# --------------------------------------------------------------------------- #
def _ollama_tags(timeout: float = 1.5) -> list[dict] | None:
    """Raw ``/api/tags`` model list, or ``None`` if the service is unreachable.

    ``None`` (down) is distinct from ``[]`` (up but nothing pulled).
    """
    try:
        import requests

        resp = requests.get(f"{ollama_base_url()}/api/tags", timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("models", []) or []
    except Exception:
        return None


def ollama_up(timeout: float = 1.0) -> bool:
    """True if the Ollama service answers at ``ollama_base_url()``."""
    return _ollama_tags(timeout) is not None


def _ollama_binary() -> str | None:
    """Locate the ``ollama`` CLI, including the common macOS/Homebrew paths a
    Finder-launched sidecar may not have on PATH."""
    import shutil

    found = shutil.which("ollama")
    if found:
        return found
    for cand in ("/opt/homebrew/bin/ollama", "/usr/local/bin/ollama",
                 "/Applications/Ollama.app/Contents/Resources/ollama"):
        if Path(cand).exists():
            return cand
    return None


def ensure_ollama_running(wait: float = 8.0) -> dict:
    """Best-effort: if Ollama isn't up, spawn ``ollama serve`` and wait for it.

    The child inherits the environment (incl. ``OLLAMA_HOST``) so it binds the
    same port the sidecar connects to; if ``OLLAMA_HOST`` is unset we derive it
    from ``ollama_base_url()`` so a custom port still works. Detached via a new
    session so it outlives the request but never blocks shutdown.
    """
    global _ollama_proc
    if ollama_up():
        return {"up": True, "started": False}

    binary = _ollama_binary()
    if not binary:
        return {"up": False, "started": False,
                "error": "ollama binary not found on PATH"}

    import subprocess
    from urllib.parse import urlparse

    env = dict(os.environ)
    if "OLLAMA_HOST" not in env:
        parsed = urlparse(ollama_base_url())
        if parsed.hostname and parsed.port:
            env["OLLAMA_HOST"] = f"{parsed.hostname}:{parsed.port}"
    try:
        _ollama_proc = subprocess.Popen(  # noqa: S603 — known binary, no shell
            [binary, "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:  # pragma: no cover — platform/permission dependent
        return {"up": False, "started": False, "error": f"spawn failed: {exc}"}

    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if ollama_up():
            return {"up": True, "started": True}
        time.sleep(0.3)
    return {"up": False, "started": True,
            "error": "ollama did not become ready in time"}


def _label_for(name: str, details: dict) -> str:
    """Build a human-readable label for a discovered (unconfigured) Ollama model."""
    params = (details or {}).get("parameter_size")
    return f"{name} ({params}, local)" if params else f"{name} (local)"


def discover_ollama(force: bool = False) -> dict[str, ModelInfo]:
    """Discover every model the local Ollama has pulled (FR-53, dynamic).

    Curated models (in settings.yaml) keep their nice labels/metadata; any other
    pulled model is added with sensible defaults (local ⇒ cost 0). Cached for
    ``_DISCOVERY_TTL`` seconds. Returns a copy of {id -> ModelInfo}.
    """
    global _discovered_at
    now = time.monotonic()
    with _discovery_lock:
        fresh = _discovered and (now - _discovered_at) < _DISCOVERY_TTL
        if not force and fresh:
            return dict(_discovered)

    tags = _ollama_tags()
    if tags is None:  # service down — keep last known set, don't wipe it
        with _discovery_lock:
            return dict(_discovered)

    curated = {m.id: m for m in registry() if m.provider == "ollama"}
    disc: dict[str, ModelInfo] = {}
    meta: dict[str, dict] = {}
    for tag in tags:
        name = tag.get("name")
        if not name:
            continue
        details = tag.get("details", {}) or {}
        disc[name] = curated.get(name) or ModelInfo(
            id=name,
            provider="ollama",
            label=_label_for(name, details),
            context_window=0,
            supports_tools=True,
            cost_per_mtok={"input": 0.0, "output": 0.0},
        )
        meta[name] = {"size_bytes": int(tag.get("size", 0) or 0), "details": details}

    with _discovery_lock:
        _discovered.clear()
        _discovered.update(disc)
        _discovered_meta.clear()
        _discovered_meta.update(meta)
        _discovered_at = now
        return dict(_discovered)


def _ollama_installed_ids() -> set[str]:
    """Return the set of currently-pulled Ollama model ids (back-compat helper)."""
    return set(discover_ollama().keys())


def looks_like_ollama_id(model_id: str) -> bool:
    """Heuristic: does this id look like an Ollama model ref (name:tag)?

    Used as a last-resort fallback when an id is neither in the curated
    registry nor the discovery cache (e.g. a pinned uncurated model right
    after a cold start, before the first /api/tags probe). Ollama refs carry a
    ':tag' ("mistral:latest", "qwen2.5:7b-instruct"); cloud ids never do.
    """
    return ":" in (model_id or "")


def estimate_pull_size(name: str, timeout: float = 5.0) -> int | None:
    """Estimated download size in bytes for an Ollama model BEFORE pulling.

    Tony's rule (2026-07-07): OSA must know whether a requested model fits
    this machine before asking him to confirm a pull. Two estimators, in
    order:

    1. The Ollama registry manifest (``registry.ollama.ai/v2/<repo>/
       manifests/<tag>``) — sums the layer sizes; exact and free, one small
       GET (e.g. llama3.3 → ~42.5GB).
    2. Name heuristic — a ``<N>b`` parameter count in the name/tag ≈
       ``N × 0.6GB`` (Q4 quantization rule of thumb).

    Returns ``None`` when neither works — callers phrase the confirm as
    "unknown size" rather than guessing.
    """
    try:
        import requests

        base, _, tag = (name or "").partition(":")
        repo = base if "/" in base else f"library/{base}"
        resp = requests.get(
            f"https://registry.ollama.ai/v2/{repo}/manifests/{tag or 'latest'}",
            timeout=timeout,
            headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"},
        )
        if resp.ok:
            total = sum(
                int(l.get("size", 0))
                for l in (resp.json() or {}).get("layers", [])
            )
            if total > 0:
                return total
    except Exception:  # noqa: BLE001 — offline/registry trouble ⇒ heuristic
        pass
    m = re.search(r"(\d+(?:\.\d+)?)b\b", (name or "").lower())
    if m:
        return int(float(m.group(1)) * 0.6e9)
    return None


def pull_ollama_model(name: str, timeout: float = 3600.0) -> dict:
    """Pull a model into the local Ollama — blocking, hours-long for big ones.

    Talks to the same HTTP API the rest of this module uses
    (``POST /api/pull`` with ``stream: false`` — one response when the pull
    finishes). Callers run this off the request path (OSA's ``pull_model``
    tool spawns it on a background thread). A nonexistent model name errors
    cleanly here rather than being pre-validated against a registry.

    Returns:
        ``{"ok": bool, "error": str | None}`` — never raises. On success the
        discovery cache is force-refreshed so the new model is immediately
        pinnable.
    """
    try:
        import requests

        resp = requests.post(
            f"{ollama_base_url()}/api/pull",
            json={"name": name, "stream": False},
            timeout=timeout,
        )
        resp.raise_for_status()
        status = (resp.json() or {}).get("status")
        if status == "success":
            discover_ollama(force=True)
            return {"ok": True, "error": None}
        return {"ok": False, "error": f"unexpected pull status: {status!r}"}
    except Exception as exc:  # noqa: BLE001 — surfaced to OSA's completion message
        return {"ok": False, "error": str(exc)}


# --------------------------------------------------------------------------- #
# Machine RAM (to flag models too large to run comfortably)
# --------------------------------------------------------------------------- #
def total_ram_bytes() -> int:
    """Total physical RAM in bytes, or 0 if it can't be determined."""
    try:
        import psutil

        return int(psutil.virtual_memory().total)
    except Exception:
        pass
    try:
        import subprocess
        import sys

        if sys.platform == "darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"])  # noqa: S603,S607
            return int(out.strip())
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal"):
                    return int(line.split()[1]) * 1024
    except Exception:
        pass
    return 0


def is_available(model_id: str) -> bool:
    """Can we actually run this model right now?

    * anthropic → ANTHROPIC_API_KEY must be set.
    * ollama → the service must be up, the model pulled, AND small enough to run
      comfortably (< half of total RAM) when RAM/size are known.
    """
    info = get_model_info(model_id)
    provider = info.provider if info else "anthropic"
    adapter = get_provider(provider)
    if adapter is None:
        return False
    if info is None:
        info = ModelInfo(id=model_id, provider=provider, label=model_id)
    try:
        return bool(adapter.available(info))
    except Exception:
        return False


def _ram_fit(size_bytes: int) -> tuple[bool, str | None]:
    """(fits, reason). A model fits if it needs < half of total RAM. Unknown
    size or unknown RAM ⇒ fits=True (don't over-block on missing data)."""
    ram = total_ram_bytes()
    half = ram / 2 if ram else 0
    if size_bytes <= 0 or half <= 0:
        return True, None
    return (size_bytes < half), (None if size_bytes < half else "too_large")


def list_models(*, ensure_ollama: bool = True) -> dict:
    """Payload for GET /api/agent/models (FR-53).

    When ``ensure_ollama`` is set (the default for the endpoint), first try to
    bring the Ollama service up. Then list cloud models (``available`` keyed on
    the API key) plus every pulled local model — curated ones keep their labels,
    others are discovered dynamically. Local models are flagged ``fits`` /
    ``available`` based on whether they need less than half the machine's RAM.
    """
    if ensure_ollama:
        ensure_ollama_running()
    discovered = discover_ollama(force=ensure_ollama)
    up = ollama_up()
    ram = total_ram_bytes()

    def _row(info: ModelInfo, *, installed: bool, available: bool,
             size: int, fits: bool, reason: str | None) -> dict:
        """Build a model descriptor dict for the API response."""
        return {
            "id": info.id,
            "provider": info.provider,
            "label": info.label,
            "context_window": info.context_window,
            "supports_tools": info.supports_tools,
            "cost_per_mtok": info.cost_per_mtok,
            "is_local": info.is_local,
            "installed": installed,
            "available": available,
            "size_bytes": size,
            "ram_required_bytes": size,
            "fits": fits,
            "reason": reason,
        }

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    # 1. registry order: cloud models + curated locals (keeps labels + ⌘ order).
    for info in registry():
        seen.add(info.id)
        if info.provider == "ollama":
            if not up:  # service offline ⇒ no local model is runnable right now
                out.append(_row(info, installed=False, available=False,
                                size=0, fits=False, reason="ollama_off"))
                continue
            installed = info.id in discovered
            size = int(_discovered_meta.get(info.id, {}).get("size_bytes", 0))
            if not installed:
                out.append(_row(info, installed=False, available=False,
                                size=0, fits=False, reason="not_installed"))
            else:
                fits, reason = _ram_fit(size)
                out.append(_row(info, installed=True, available=fits,
                                size=size, fits=fits, reason=reason))
        else:
            avail = is_available(info.id)
            out.append(_row(info, installed=True, available=avail,
                            size=0, fits=True,
                            reason=None if avail else "no_api_key"))
    # 2. dynamically discovered locals not in the curated registry (only when the
    #    service is up — a stale cache must not look runnable while Ollama is off).
    if up:
        for mid, info in discovered.items():
            if mid in seen:
                continue
            size = int(_discovered_meta.get(mid, {}).get("size_bytes", 0))
            fits, reason = _ram_fit(size)
            out.append(_row(info, installed=True, available=fits,
                            size=size, fits=fits, reason=reason))

    return {
        "active": active_model(),
        "ollama_up": up,
        "ram_total_bytes": ram,
        "models": out,
    }


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
# Provider adapters (pluggable)
# --------------------------------------------------------------------------- #
# Adding a *provider* = register one ProviderAdapter (here or from a plugin via
# register_provider()). Adding a *model* for an existing provider = one entry in
# settings.yaml > agent.models, no code change. The "openai_compatible" adapter
# alone covers OpenAI, Groq, Together, OpenRouter, DeepSeek, Mistral, xAI,
# Fireworks, Perplexity, and local vLLM / LM Studio servers — they all speak the
# same /v1/chat/completions protocol; only base_url + api_key_env differ.
@dataclass(frozen=True)
class ProviderAdapter:
    """Pluggable backend adapter for a specific LLM provider.

    Attributes:
        name: Provider identifier (e.g. "anthropic", "ollama").
        local: Whether this provider runs models locally.
        build: Callable (ModelInfo, **kwargs) -> LangChain chat model.
        available: Callable (ModelInfo) -> bool indicating availability.
    """

    name: str
    local: bool
    build: Any      # (ModelInfo, **kwargs) -> LangChain chat model
    available: Any  # (ModelInfo) -> bool


def register_provider(adapter: "ProviderAdapter") -> None:
    """Register (or override) a provider adapter. Lets a plugin add a brand-new
    backend without editing this module."""
    _PROVIDERS[adapter.name] = adapter
    (_LOCAL_PROVIDERS.add if adapter.local else _LOCAL_PROVIDERS.discard)(adapter.name)


def get_provider(name: str) -> "ProviderAdapter | None":
    """Return the ProviderAdapter for the given name, or None if unregistered."""
    return _PROVIDERS.get(name)


def provider_names() -> list[str]:
    """Return a sorted list of all registered provider names."""
    return sorted(_PROVIDERS)


def _api_key(info: ModelInfo, default_env: str | None = None) -> str | None:
    """Retrieve the API key for a model from its configured env var.

    Args:
        info: Model metadata containing an optional api_key_env field.
        default_env: Fallback env var name if info.api_key_env is not set.

    Returns:
        The API key string, or None if no env var is set.
    """
    env = info.api_key_env or default_env
    return os.environ.get(env) if env else None


# --- anthropic (cloud) ----------------------------------------------------- #
def _anthropic_build(info: ModelInfo, **kwargs: Any):
    """Build a ChatAnthropic LangChain model with isolated env and pinned endpoint."""
    from langchain_anthropic import ChatAnthropic
    # Pin endpoint + key and strip ambient ANTHROPIC_* routing vars so the cloud
    # client always reaches the real API (Open issue #2).
    kwargs.setdefault("base_url", info.base_url or anthropic_base_url())
    key = _api_key(info, "ANTHROPIC_API_KEY")
    if key:
        kwargs.setdefault("api_key", key)
    kwargs = {**info.extra, **kwargs}
    with _isolated_anthropic_env():
        return ChatAnthropic(model=info.id, **kwargs)


def _anthropic_available(info: ModelInfo) -> bool:
    """True if an Anthropic API key is set for this model."""
    return bool(_api_key(info, "ANTHROPIC_API_KEY"))


# --- ollama (local) -------------------------------------------------------- #
def _ollama_build(info: ModelInfo, **kwargs: Any):
    """Build a ChatOllama LangChain model targeting the local Ollama service."""
    from langchain_ollama import ChatOllama
    kwargs = {**info.extra, **kwargs}
    return ChatOllama(model=info.id, base_url=info.base_url or ollama_base_url(), **kwargs)


def _ollama_available(info: ModelInfo) -> bool:
    """True if the Ollama model is pulled and fits within available RAM."""
    if info.id not in _ollama_installed_ids():
        return False
    size = int(_discovered_meta.get(info.id, {}).get("size_bytes", 0))
    fits, _ = _ram_fit(size)
    return fits


# --- openai-compatible (OpenAI, Groq, Together, OpenRouter, DeepSeek, Mistral,
#     xAI, Fireworks, Perplexity, vLLM, LM Studio, …) ---------------------- #
def _openai_build(info: ModelInfo, **kwargs: Any):
    """Build a ChatOpenAI LangChain model for OpenAI-compatible endpoints."""
    from langchain_openai import ChatOpenAI
    if info.base_url:
        kwargs.setdefault("base_url", info.base_url)
    key = _api_key(info, "OPENAI_API_KEY")
    # Local OpenAI-compatible servers usually need no real key.
    kwargs.setdefault("api_key", key or "not-needed")
    kwargs = {**info.extra, **kwargs}
    return ChatOpenAI(model=info.id, **kwargs)


def _openai_available(info: ModelInfo) -> bool:
    """True if an OpenAI API key is set or a custom base_url is configured."""
    # Reachable if a key is present, or a base_url is configured (self-hosted
    # endpoints that do not require a key).
    return bool(_api_key(info, "OPENAI_API_KEY")) or bool(info.base_url)


# --- google gemini (cloud) ------------------------------------------------- #
def _google_build(info: ModelInfo, **kwargs: Any):
    """Build a ChatGoogleGenerativeAI LangChain model for Google Gemini."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    key = _api_key(info, "GOOGLE_API_KEY")
    if key:
        kwargs.setdefault("google_api_key", key)
    kwargs = {**info.extra, **kwargs}
    return ChatGoogleGenerativeAI(model=info.id, **kwargs)


def _google_available(info: ModelInfo) -> bool:
    """True if a Google API key is set for this model."""
    return bool(_api_key(info, "GOOGLE_API_KEY"))


for _adapter in (
    ProviderAdapter("anthropic", False, _anthropic_build, _anthropic_available),
    ProviderAdapter("ollama", True, _ollama_build, _ollama_available),
    ProviderAdapter("openai_compatible", False, _openai_build, _openai_available),
    ProviderAdapter("google", False, _google_build, _google_available),
):
    register_provider(_adapter)


# --------------------------------------------------------------------------- #
# Model construction + completion
# --------------------------------------------------------------------------- #
def get_chat_model(model_id: str | None = None, **kwargs: Any):
    """Return a LangChain chat model for ``model_id`` (or the active model).

    Dispatches through the provider adapter registry, so any registered backend
    (anthropic, ollama, openai_compatible, google, or a plugin-registered one)
    is constructed uniformly. LangChain imports are lazy inside each adapter, so
    this module loads even when a given provider's package isn't installed.
    """
    model_id = model_id or active_model()
    info = get_model_info(model_id)
    # Sane fallback for ids outside the registry AND the discovery cache (an
    # uncurated Ollama pin on a cold cache): a ':tag' ref builds a ChatOllama
    # instead of being mis-sent to Anthropic.
    provider = info.provider if info else (
        "ollama" if looks_like_ollama_id(model_id) else "anthropic"
    )
    adapter = get_provider(provider)
    if adapter is None:
        raise ValueError(
            f"Unknown provider for model {model_id!r}: {provider!r}. "
            f"Known providers: {', '.join(provider_names())}. "
            f"Add one with core.llm.register_provider()."
        )
    if info is None:
        info = ModelInfo(id=model_id, provider=provider, label=model_id)
    return adapter.build(info, **kwargs)


@dataclass
class LLMResult:
    """Result of a single LLM completion, including text and usage accounting.

    Attributes:
        text: The generated text content.
        model: Model id used for the completion.
        provider: Provider name (e.g. "anthropic", "ollama").
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens generated.
        cost_usd: Estimated USD cost of the completion.
    """

    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def tokens_used(self) -> int:
        """Total tokens consumed (input + output)."""
        return self.input_tokens + self.output_tokens


def _to_lc_messages(system: str | None, messages: list[dict]):
    """Convert a system prompt and list of role/content dicts to LangChain message objects.

    Args:
        system: Optional system prompt prepended as a SystemMessage.
        messages: List of dicts with "role" and "content" keys.

    Returns:
        List of LangChain message objects.
    """
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
    # Wrap invoke() in the same env-isolation guard used during construction.
    # langchain_anthropic reads ANTHROPIC_BASE_URL at call time, not just at
    # client build time, so stripping it only during __init__ is not enough.
    _is_anthropic = provider == "anthropic"
    _ctx = _isolated_anthropic_env() if _is_anthropic else contextlib.nullcontext()
    with _ctx:
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
