# Phase 17 — OSA Self-Model ("The Sentiency of OSA")

> **Status:** 🟨 DESIGN LOCKED with Tony 2026-07-23 · build not started
> **Owner docs:** this file (authoritative) · `docs/roadmap.md` Phase 17 table
> **Prereqs:** Phase 14 (OSA agent), Phase 15 (system MCP), local-first routing
> (2026-07-23 session, `LOCAL_TOOL_NAMES` + `route_turn`).

## 1. Goal

OSA should **know what it has access to** — its tools, its rules and limits,
its brains, the system it runs on, and its memory — from a self-model that is
**generated from the real system**, never hand-authored prose. Two payoffs,
both locked as goals with Tony:

1. **Truthful self-answers.** "What can you do?", "what do you have access
   to?", "what are you running on?", "what would you need my OK for?" get
   complete, current, honest answers — even fully offline on the local brain.
2. **Smarter behavior.** OSA stops attempting things it can't do, volunteers
   the right capability at the right moment, and can say "that will need your
   OK" *before* the DENIED round-trip (without breaking the arming pattern —
   see §6.1).

## 2. The problem today (why this phase exists)

- OSA's entire self-knowledge is the hand-written `OSA_SYSTEM` string in
  `agents/osa_agent.py`: a manually maintained request→tool mapping paragraph
  plus two bolted-on special cases (the Brain-status line and
  `VOICE_AWARENESS_LINE`). Every new tool requires remembering to edit prose —
  the classic drift source.
- **The local brain is told about tools it doesn't have.** The mapping
  paragraph describes all ~29 tools, but local pins bind only the 19
  `LOCAL_TOOL_NAMES`. A 3B model reading mappings for `run_command`,
  `move_file`, `delete_file`, `search_files` it cannot call is both wasted
  context (latency — the 2026-07-23 session measured how much schema bloat
  costs a 7B) and a hallucinated-capability risk.
- OSA knows nothing of the Constitution (its own rules), the services it sits
  on (sidecar :5130, MySQL, ports ledger, Ollama :12434), or what its memory
  actually is (`config/Memory.md`, durable MySQL threads).

## 3. Decisions locked with Tony (2026-07-23)

| # | Decision |
|---|----------|
| 1 | **Scope: everything.** Tools + brains, rules & limits, live system, memory & history — "all that it has access to." |
| 2 | **Delivery: hybrid.** A compact auto-generated "Self" block in the system prompt (tiered by brain, §5.2) **plus** a read-only `introspect` tool for live detail on demand (§5.3). |
| 3 | **The hand-written tool-mapping paragraph is replaced by generated text.** Each tool carries its own trigger-phrases + usage-note metadata; the prompt prose is assembled from that. The battle-tuned phrasing rules (iMessage handle-confirm, mail address-confirm, full-claude-id switching, etc.) move into per-tool `usage_note` fields so nothing is lost (§5.1, §7 tests). |
| 4 | **Purpose: both** self-answering and behavior (routing, preemption). |

## 4. Architecture overview

One new module, one new tool, one refactor:

```
core/self_model.py          NEW — manifest builders + prompt renderers
agents/osa_agent.py         REFACTOR — TOOL_SPECS registry; build_tools and
                            the prompt both derive from it; OSA_SYSTEM loses
                            the hand-written mapping paragraph
tools (OSAToolbox)          NEW method — introspect(section) (guard-free,
                            read-only, added to LOCAL_TOOL_NAMES)
```

**Single source of truth:** the `TOOL_SPECS` registry. `build_tools()` binds
from it; the generated mapping prose renders from it; `introspect("tools")`
reports from it. A tool that exists but isn't in the registry (or vice versa)
is a test failure, not a doc bug.

## 5. Design

### 5.1 `TOOL_SPECS` — per-tool metadata registry (17a)

Promote the anonymous `specs` list inside `build_tools()` to a module-level
registry. Per tool:

```python
ToolSpec(
    name="send_message",
    method="send_message",              # OSAToolbox attr
    triggers=["text <person>", "message <person>"],
    usage_note=("if given a NAME, resolve_contact first, then send_message "
                "with the RAW handle; sends always need Tony's OK and the "
                "confirm must show the actual handle, never just the name"),
    local=True,                          # member of LOCAL_TOOL_NAMES
    guard="approval",                    # "free" | "approval" | "blocked-able"
    group="messages",                    # for grouped prose rendering
)
```

- `local` is asserted against `LOCAL_TOOL_NAMES` in tests (no silent split).
- `guard` is **derived where possible** from `config/constitution.yaml`
  (approval_required / blocked action types) — a spec that contradicts the
  Constitution fails a test. The Constitution stays the enforcement authority;
  `guard` is descriptive only.
- `render_tool_map(specs, only=)` produces the mapping paragraph **per brain**:
  cloud renders all groups; a local pin renders only its bound subset. This
  fixes the "local told about cloud-only tools" bug as a side effect.
- Every learned phrasing rule currently in `OSA_SYSTEM` is carried by a
  `usage_note`; §7's snapshot test enforces their survival.

### 5.2 Capability manifest + tiered "Self" block (17b)

`core/self_model.py` builds a manifest at `build_agent()` time:

| Section | Source (all live, no hand-authoring) |
|---------|--------------------------------------|
| `tools` | `TOOL_SPECS` filtered to the bound subset |
| `rules` | `config/constitution.yaml`: file-scope roots (~/Codehome, ~/Brain2), approval-required action types, hard blocks |
| `brains` | current pin/mode from settings; local shelf via Ollama `/api/tags` on :12434 (best-effort, cached, non-fatal — same posture as `warm_ollama`); routing policy one-liner (menial→local, web/heavy/sharp→cloud); "local has no web access" |
| `system` | sidecar :5130, MySQL `agenticos`, ports ledger, voice on/off (absorbs `VOICE_AWARENESS_LINE` and the Brain-status line as ordinary fields) |
| `memory` | `config/Memory.md` headline facts (count + top lines); "conversations persist across restarts (MySQL checkpointer)" |

`render_self_block(manifest, tier)`:

- **cloud tier:** ~12 lines, all sections summarized.
- **local tier:** 3–4 lines, hard token budget (≤ ~60 tokens): tool count +
  groups, file scope, "cloud brain handles web/heavy," memory-persists fact.
  The 3B pin's latency is already inherent to its size; the Self block must
  not measurably worsen it (§7 has a latency check in the DoD).

Failure posture: every manifest source is best-effort. Ollama down, missing
Memory.md, unreadable constitution → the section renders a short honest
degraded line ("local shelf unavailable"), never blocks agent construction.

### 5.3 `introspect(section)` tool (17c)

- Read-only, **no guard** (it changes nothing), added to `LOCAL_TOOL_NAMES` so
  offline OSA can self-describe with live data.
- `section ∈ {"tools", "rules", "brains", "system", "memory", "all"}`;
  `"all"` returns the summary, specific sections return detail (per-tool
  triggers, full approval list, full shelf, thread count, Memory.md contents).
- Output is voice-shaped plain text (OSA speaks it), size-capped like other
  tool outputs (local-latency lesson from 2026-07-23).
- **No secrets, ever:** the manifest and introspect must never include env
  vars, API keys, DB passwords, or raw settings dumps. (Standing security
  item: a process env already leaks the real ANTHROPIC_API_KEY — this feature
  must not add a second leak path via chat transcript.)

## 6. Behavioral guardrails

### 6.1 The arming pattern is preserved (regression trap)

Rules-awareness lets OSA *say* "moving that file will need your OK" — but the
prompt's generated rules text MUST retain the existing instruction: **always
call the tool first; the guard's DENIED is the only thing that arms a
confirmation.** Awareness that causes a bare ask (which arms nothing, so
Tony's "yes" approves nothing) is a regression, and §7 tests the generated
prompt still contains the call-first instruction.

### 6.2 Honesty rules

- The Self block states capabilities of the **currently bound** brain/toolset
  only. Local OSA says "my cloud brain can search the web; I can't right
  now," not "I can't search the web" nor "sure, searching…".
- "Never fabricate" extends to self-description: detail questions beyond the
  Self block go through `introspect`, not recall.

## 7. Sub-phases, tests, DoD

| Sub-phase | Scope | Verification |
|-----------|-------|--------------|
| 17a | `TOOL_SPECS` registry; `build_tools` + `render_tool_map` derive from it; `OSA_SYSTEM` mapping paragraph replaced; per-brain prompt rendering | pytest: registry↔toolbox parity (every bound tool has a spec and vice versa); `local` flags ≡ `LOCAL_TOOL_NAMES`; **phrase-preservation snapshot** (handle-confirm, address-confirm, full-claude-id, guard call-first text all present in rendered cloud prompt); local prompt contains NO cloud-only tool names |
| 17b | `core/self_model.py` manifest builders + tiered `render_self_block` wired into `build_agent` (absorbing Brain-status + voice lines) | pytest per section incl. degraded modes (Ollama down, Memory.md missing); guard-class-vs-constitution consistency test; local block token-budget test |
| 17c | `introspect` toolbox method + `LOCAL_TOOL_NAMES` entry; live verification | pytest (sections, size caps, **no-secrets scan** of output); live: "what do you have access to" on cloud AND on local with cloud dead |

- **Subagents:** test authorship via `test-author` per the standing rule
  (inline fallback documented if the surface lacks it).
  **`security-verifier` REQUIRED** for 17b/17c: the diff reads
  `config/constitution.yaml` and exposes rule descriptions in prompts/replies —
  fresh eyes on info-disclosure and on any accidental touch of the security
  spine.
- **DoD:** full suite green (894 baseline); live proof on both brains; local
  warm-turn latency within ~10% of the pre-17 baseline (get_time benchmark);
  `CHANGELOG.md`, `roadmap.md`, `GLOSSARY.md` (+ Brain2 mirror) updated in the
  landing change.

## 8. Risks

| Risk | Mitigation |
|------|------------|
| Regressing the battle-tuned prompt prose | Phrase-preservation snapshot tests (§7 17a); live phrasing spot-checks before commit |
| Local-pin latency from added prompt text | Hard token budget + latency check in DoD |
| Registry/toolbox drift returning in a new form | Impossible by construction: `build_tools` consumes `TOOL_SPECS`; parity is tested |
| Secret leakage via introspect | No-secrets scan test; manifest builders whitelist fields, never dump settings |
| Bare-ask arming regression | §6.1 test on generated prompt |

## 9. Out of scope (parked, noted for later)

- Proactive capability suggestions ("want me to watch that inbox?") beyond
  what naturally falls out of prompt awareness — separate behavior phase.
- Self-model of Hub/API endpoints as callable surface (OSA driving the API
  Explorer) — revisit after Phase 16 lands.
- Cloud-down local fallback for web turns (the parked Part C from
  2026-07-23) — unrelated mechanism, still awaiting Tony's call.
