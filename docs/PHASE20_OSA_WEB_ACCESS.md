# Phase 20 — OSA Web Access ("give the local brains the open web")

**Status:** 🟨 DESIGN KICKOFF — decisions locked with Tony 2026-08-06.
**Goal:** bring the **local** OSA brains (Ollama pins: qwen2.5:7b, etc.) to
web-capability parity with cloud/Claude agents — search the web, fetch and
read pages, and (this phase) drive a headless browser — through the Phase 15
System-MCP capability framework, gated by the same Constitution safety ladder.

> Why this exists: today only Claude (via `claude-in-chrome` / `web_search` /
> `web_fetch`) can reach the open web. AgenticOS itself only *consumes RSS*
> (`gui/sidecar/routes/news_db.py`, feedparser). The local OSA agent has **no**
> general search / fetch / browse capability. Phase 20 closes that gap so a
> $0 local pin can research, read, and act on the web the way a Claude agent
> does — while staying inside the Constitution.

---

## ▶ Kickoff prompt (paste this to start Phase 20a in a fresh session)

> **Phase 20a — Web foundation + safety spine.** Read `CLAUDE.md`,
> `docs/CONTINUATION.md`, `docs/GLOSSARY.md`, and this doc
> (`docs/PHASE20_OSA_WEB_ACCESS.md`) first. Build the web-access **safety
> foundation** that every later sub-phase depends on — no capabilities exposed
> yet, just the guarded HTTP layer + policy wiring + config surface:
>
> 1. Add a `web` block to `config/constitution.yaml` (schema in §7 of this
>    doc): `searxng_url`, `denylist_domains`, optional `allowlist_domains`,
>    `respect_robots`, `max_bytes`, `timeout_s`, `max_redirects`,
>    `allowed_content_types`, `per_domain_rate_limit`, `cache_ttl_s`,
>    `browse_enabled`. Merge defaults in `core/constitution.py` so pre-20
>    configs still load unchanged (same pattern as the 15a `system_mcp` merge).
> 2. Create `tools/system/_web_safety.py`: an SSRF-hardened fetch primitive
>    (`safe_get(url)`) that (a) allows only `http`/`https`, (b) resolves the
>    host and **denies** loopback / RFC-1918 / link-local / `0.0.0.0` /
>    `169.254.169.254` (cloud metadata) / `metadata.google.internal`,
>    (c) re-checks on **every redirect hop** (re-resolve, cap hops), (d) caps
>    bytes + total time, (e) enforces the domain denylist FIRST (always-deny,
>    like the `run_command` denylist), (f) sets an honest User-Agent. This is
>    the security spine of the whole phase — `security-verifier` is MANDATORY.
> 3. Wire the `web.*` effect classes into `tools/system/_policy.py` (see §6):
>    reads → `allow` in effect mode / `approve` in strict mode; browse actions
>    → always `approve`; password-field entry → always `deny`.
> 4. `test-author` subagent writes `gui/sidecar/tests/test_phase20a.py`
>    (adversarial SSRF proofs: DNS-rebind-shaped inputs, redirect-to-localhost,
>    IPv6 loopback, decimal/hex IP encodings, oversized body, denylist bypass
>    attempts). Supervising session independently re-runs the FULL suite.
> 5. Add the Phase 20 row to `docs/roadmap.md`, a 🟧 row to `docs/IDEA_LEDGER.md`,
>    and update `CHANGELOG.md` + `GLOSSARY.md` (SearXNG, SSRF, trafilatura,
>    web domain) in the SAME commit. Commit AND push at session end.
>
> Do NOT expose any `@capability` yet — 20a ends with a green, guarded
> foundation and zero new tools in `list_tools`. `web_search` lands in 20b.

*(Per-sub-phase kickoff prompts for 20b–20f are in §9.)*

---

## 1. Locked decisions (2026-08-06)

| # | Decision | Choice |
|---|----------|--------|
| 1 | **Search + read mechanism** | **Credential-free / self-hosted.** SearXNG (local, Dockerized, registered port) for search; `httpx` + `trafilatura` for page fetch + extraction. No API keys. Search sits behind a provider **adapter registry** (mirrors `core/llm.py`) so Tavily/Brave/Serper become config-only swaps later. |
| 2 | **Surface** | **Both.** A single `tools/system/web_mcp.py` capability domain that self-registers into `_harness.REGISTRY` (→ auto-exposed over the `osa-system-mcp` stdio server to Claude Desktop/Code) **and** is bound into OSA's `TOOL_SPECS` (Phase 17a) so local pins get the tools in their generated prompt. |
| 3 | **v1 depth** | **Full browsing.** Read tier (`web_search`, `web_fetch`) **plus** a headless-Playwright browse tier. Reads auto/gate-by-mode; DOM **actions** (click/type/submit) always gate to approval; credential entry is hard-denied. |

**Defaults I'm baking in (not separately asked — flag if any is wrong):**
- **Read-only is the default lane.** `web_search` + `web_fetch` are the common
  path; Playwright is only spun up when a page needs JS or an action. Cheap,
  safe, fast path first (same instinct as local-first LLM routing).
- **Small-context safety.** Local pins are 8–32k ctx. `web_fetch` returns
  **extracted, truncated** markdown, and a sibling `web_read` capability offers
  an **optional LLM-summarize-on-fetch** (composed on the ACTIVE brain, $0 on a
  local pin) so a 7B model doesn't drown. (This is the "summarize" half of the
  option you passed over — reintroduced as an *optional layer* because it's
  orthogonal to depth and clearly needed for 7B models. Kill it if you'd rather
  keep fetch raw.)
- **Fetch audit log in MySQL.** A `web_fetch_log` table (via `models.py` +
  idempotent `migrations.py` ALTER — the sole-DB rule) records what the agent
  read (url, ts, brain, bytes, blocked?). Fits the trust-first / "announce
  every change" ethos of the Attention Model.
- **No credentials, ever.** Password/secret fields are never filled by the
  agent (mirrors the global "never enter passwords" rule). CAPTCHAs are never
  solved — hitting one is reported to Tony, not worked around.

---

## 2. Where it slots in the architecture

```
tools/system/
  _harness.py        # REGISTRY + @capability (unchanged)
  _policy.py         # +web.* effect wiring (20a)
  _web_safety.py     # NEW (20a) — SSRF-hardened safe_get + caps + denylist
  _web_providers.py  # NEW (20b) — search adapter registry (searxng default)
  web_mcp.py         # NEW (20b–20d) — @capability defs: web_search / web_fetch
                     #                 / web_read / browse_*
tools/osa_system_mcp.py   # +`from tools.system import web_mcp`  (auto-exposes)
agents/osa_agent.py       # +TOOL_SPECS rows (20e) → render_tool_map picks them up
config/constitution.yaml  # +`web:` block (20a)
core/constitution.py      # +web defaults merge (20a)
gui/sidecar/models.py     # +WebFetchLog (20b)
gui/sidecar/migrations.py # +ensure_phase20_schema() idempotent ALTER (20b)
```

**Reuses, does not fork:** the `@capability`/`REGISTRY`/`dispatch` machinery,
the strict/effect policy ladder, the `ApprovalRequired`/`ConstitutionViolation`
semantics, the `TOOL_SPECS` single-source-of-truth from 17a, and the
adapter-registry shape from `core/llm.py`. New tools appear in the stdio
server's `list_tools` automatically and in a local pin's prompt automatically.

**Coordinates with two pending items:**
- **Phase 15e (effect-mode flip)** — 20's capabilities ship with correct
  `effect=` tags so they behave right under both strict mode (all gate) and
  effect mode (reads run). Land 20 tags 15e-ready.
- **Phase 17a `render_tool_map`** — web tools carry battle-tuned `usage_note`s
  (when to search vs fetch vs browse; that browse actions will ask permission)
  so a local pin routes correctly and doesn't hallucinate the capability.

---

## 3. Capability catalog

Effect column drives the policy ladder (§6). "read" = auto in effect mode /
gate in strict; "mutate" = always gate; "denied" = never.

| Capability | Tier | Effect | What it does |
|------------|------|--------|--------------|
| `web_search` | read | read | SearXNG query → ranked results (title, url, snippet). Provider-abstracted. |
| `web_fetch` | read | read | `safe_get` a URL → trafilatura-extracted markdown, truncated to a token budget. Playwright fallback only if flagged/needed. |
| `web_read` | read | read | `web_fetch` + optional LLM summarize-on-active-brain (config/arg toggle). For small local pins. |
| `browse_open` | browse | read | Launch/reuse a headless Chromium context, navigate to a `safe_get`-vetted URL. |
| `browse_read` | browse | read | Extract rendered text / accessibility snapshot from the live page (JS-rendered content). |
| `browse_screenshot` | browse | read | PNG of the current page (for the GUI viewer / Claude vision). |
| `browse_click` | browse | **mutate** | Click an element. **Gates to approval.** |
| `browse_fill` | browse | **mutate** | Type into a non-secret field. **Gates to approval.** Password/secret field → **deny**. |
| `browse_submit` | browse | **mutate** | Submit a form / press Enter. **Gates to approval.** |
| `browse_close` | browse | read | Tear down the browsing session/context. |

**Session model:** one isolated, ephemeral Chromium context per browsing
session — **no persisted cookies/logins by default**, downloads disabled,
capped duration. Teardown on `browse_close` or timeout. (Optional persistent
profile is a later, explicitly-opt-in slice — not v1.)

---

## 4. Human prerequisites (like the FDA grant / MySQL-up tasks)

1. **Run SearXNG locally.** `docker run -d -p <PORT>:8080 searxng/searxng`
   (JSON output format enabled). Register `<PORT>` in
   `hub/docs/PORT_ASSIGNMENTS.md` (TR-10) before use. `searxng_url` in the
   `web:` config points at it. Fallback: a configurable remote instance URL if
   Docker isn't running.
2. **Install Playwright browser** (20d): `.venv/bin/python -m playwright
   install chromium` (~150 MB, one-time). Gate 20d build on this being present.
3. Confirm `httpx`, `trafilatura`, `selectolax`/`lxml`, `playwright` land in
   the venv (`requirements`/`pyproject`) — pin versions, run an import smoke.

---

## 5. Dependencies

`searxng` (Docker, external) · `httpx` (async client) · `trafilatura` (main-content
extraction → markdown) · `selectolax` or `lxml` (parse) · `playwright` (headless
Chromium, 20d only). All MIT/permissive. No cloud API keys. SearXNG is the only
out-of-process dependency.

---

## 6. Safety / policy design (the part that earns `security-verifier`)

**Two risk tiers, one denylist checked first.**

1. **Denylist (always-deny, both modes, checked before anything).**
   `web.denylist_domains` — matched host-suffix — can never be fetched or
   browsed, even with `approved=True` (the harness re-checks, same as the
   `run_command` denylist). Ships with a starter set (internal/admin panels,
   known-malware hosts) that Tony edits.

2. **SSRF spine (`_web_safety.safe_get`).** Every fetch — read tier AND every
   Playwright navigation — routes through it:
   - scheme ∈ {http, https} else deny;
   - resolve host → deny if any resolved IP is loopback / private (10/8,
     172.16/12, 192.168/16, fc00::/7) / link-local (169.254/16 incl.
     `169.254.169.254`) / `0.0.0.0` / IPv6 `::1`;
   - **re-run the check on every redirect hop** (re-resolve; cap `max_redirects`)
     — mirrors the mail-domain "re-check the recipient on every step" pattern
     that caught the reply-target bug;
   - enforce `max_bytes`, `timeout_s`, `allowed_content_types`;
   - honor `respect_robots` for search-driven bulk fetch (single explicit
     user-intent fetch may bypass per config).

3. **Effect ladder (into `_policy.py`).**
   - **strict mode (start):** all `web.*` gate to approval.
   - **effect mode (15e target):** `web_search` / `web_fetch` / `web_read` /
     `browse_open` / `browse_read` / `browse_screenshot` / `browse_close` →
     `allow`; `browse_click` / `browse_fill` / `browse_submit` → `approve`.
   - **always:** a `browse_fill` targeting a password/secret input →
     `ConstitutionViolation` (deny). CAPTCHA / bot-check → refuse + report.

4. **Approval routing.** Over MCP, gated web actions return the structured
   `needs_approval` error (external clients can't self-approve — 15a rule).
   In-process (OSA / sidecar HITL) they raise `ApprovalRequired` → the existing
   inline Allow/Deny interrupt (Phase 14). Re-raise `GraphInterrupt` /
   `GraphBubbleUp` before any broad `except` (the lesson paid twice in 15c/d).

---

## 7. Config surface — `config/constitution.yaml` `web:` block

```yaml
web:
  searxng_url: "http://127.0.0.1:8888"     # local SearXNG (register the port)
  search_provider: "searxng"                # adapter key; tavily/brave later
  denylist_domains: []                      # always-deny, host-suffix match
  allowlist_domains: []                     # if non-empty in strict mode, ONLY these
  respect_robots: true
  max_bytes: 5_000_000
  timeout_s: 10
  max_redirects: 5
  allowed_content_types: ["text/html", "text/plain", "application/json", "application/pdf"]
  per_domain_rate_limit: 10                 # requests / minute / host
  cache_ttl_s: 900                          # fetch cache (TTL, like app_registry)
  browse_enabled: false                     # master switch for the Playwright tier
  browse_session_ttl_s: 300
  browse_persist_profile: false             # no saved logins by default
```

Search-provider keys (if a future adapter needs one) live in
`~/.agentic-os/.env`, never in the yaml.

---

## 8. GUI (design principle #7: new paradigm = new nav link)

A **Web** view (VIEWS registry entry — not another always-on dashboard panel):
- live browsing session viewer (latest `browse_screenshot` + extracted text),
- a fetch/search audit feed from `web_fetch_log` (what OSA read, when, on which
  brain, blocked-or-not) — the trust surface,
- pending web-action approvals surfaced inline (reuse the 14 HITL affordance).

GUI can land as **20f** or be parked behind the backend — Tony's call.

---

## 9. Sub-phase breakdown + per-phase kickoff prompts

Each sub-phase: `test-author` writes the tests, supervising session re-runs the
FULL suite, `security-verifier` is MANDATORY on anything touching
`_web_safety.py` / `_policy.py` / the `web:` config block / `web_mcp` dispatch.
Same-commit doc policy (CHANGELOG/roadmap/GLOSSARY/CONTINUATION). Commit + push
at session end.

### 20a — Web foundation + safety spine
Config block + defaults merge, `_web_safety.safe_get` (SSRF + caps + denylist),
`_policy.py` web wiring, `test_phase20a.py` (adversarial SSRF). **No capabilities
exposed.** *(Full prompt at top of doc.)*

### 20b — Search + fetch (read tier)
> Build `tools/system/_web_providers.py` (search adapter registry; `searxng`
> adapter calling `web.searxng_url` JSON API) and `tools/system/web_mcp.py`
> exposing `@capability web_search` and `@capability web_fetch` (fetch via
> `_web_safety.safe_get` → trafilatura → truncated markdown). Add `web_mcp` to
> the `osa_system_mcp.py` import list. Add `WebFetchLog` to `models.py` +
> `ensure_phase20_schema()` to `migrations.py` (idempotent ALTER; `agenticos_test`
> fixture). `test_phase20b.py`: provider adapter, extraction, truncation, denylist
> + SSRF still enforced through the capability, MySQL audit row written.
> Verify live against the local SearXNG. `security-verifier` REQUIRED.

### 20c — `web_read` (summarize layer) + OSA read-tier binding
> Add `@capability web_read` (`web_fetch` + optional summarize on the active
> brain via `core.llm`; local pin = $0, skip the cost gate like the attention
> brief). Add `web_search` / `web_fetch` / `web_read` rows to `TOOL_SPECS` in
> `agents/osa_agent.py` with `usage_note`s (when to search vs fetch vs read;
> local-first). Confirm `render_tool_map` emits them only when bound.
> `test_phase20c.py`: summarize path mocked, TOOL_SPECS parity/phrase snapshots
> (17a pattern). Live-verify a local pin actually searching + reading.

### 20d — Browse tier (Playwright)
> **Prereq:** `playwright install chromium`. Add the browse capabilities from §3.
> Reads (`browse_open`/`browse_read`/`browse_screenshot`/`browse_close`) via
> `safe_get`-vetted navigation; **actions** (`browse_click`/`browse_fill`/
> `browse_submit`) `effect="mutate"` → gate; password-field fill → deny;
> ephemeral isolated context, downloads off, session TTL. Bind into `TOOL_SPECS`
> with a `usage_note` that browse actions ask permission. `test_phase20d.py`:
> a local static fixture server (NOT the live web) for determinism — read a
> rendered page, screenshot, and PROVE click/fill/submit raise `ApprovalRequired`
> and password-fill raises `ConstitutionViolation`. `security-verifier` REQUIRED.

### 20e — Effect-mode wiring + TCC/runbook + hardening
> Confirm the full `web.*` ladder under both modes (coordinate with 15e).
> Rate-limit + cache live-verified. Write `docs/WEB_ACCESS_RUNBOOK.md` (SearXNG
> up, Playwright install, denylist editing, how approvals surface). Full-suite
> green; restart the sidecar so OSA gets the tools live (gotcha #1: kill any
> stray :5130 first).

### 20f — Web GUI view (optional / parkable)
> VIEWS-registry "Web" nav link: session viewer + audit feed + inline web-action
> approvals. vitest + a live click-through. Or park behind the backend.

---

## 10. Open questions for Tony

1. **SearXNG hosting:** local Docker on a registered port (my rec), or point at
   an existing/remote instance? (Affects the 20a prereq + `searxng_url` default.)
2. **Summarize layer (`web_read`):** keep the optional LLM-summarize-on-fetch
   for small pins (my rec), or ship fetch raw and let the model summarize
   itself?
3. **Browse persistence:** confirm v1 is stateless (no saved logins). A
   persistent, explicitly-opt-in profile (so OSA can act inside a logged-in site
   Tony pre-authorized) would be its own later slice — in or out?
4. **robots.txt:** honor by default for agent fetches (my rec: yes for
   search-driven bulk, allow single explicit fetch), or ignore?
5. **GUI (20f):** build the Web view this phase, or backend-only first?

---

## 11. Doc / process reminders (standing rules)

- Same-commit doc policy: CHANGELOG, roadmap, GLOSSARY (both copies),
  CONTINUATION, this design doc all move WITH the code.
- MySQL is the sole DB; SQLAlchemy the sole access layer (WebFetchLog via
  models.py + migrations.py, tested on `agenticos_test`).
- Register the SearXNG port (TR-10) before use.
- `security-verifier` MANDATORY on the safety spine; a dead subagent = an
  untrusted tree (review or discard).
- Commit AND push completed work at session end — no dirty trees left for "next
  time."
