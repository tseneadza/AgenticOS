# Phase 14 — OSA: Voice-Driven Ambient Assistant (JARVIS analog)

**Status:** 🟡 DESIGN — awaiting Tony's persona description + architecture sign-off
**Author:** design session 2026-07-06
**Supersedes/depends on:** Phases 1–13 (Core Orchestration, Tauri GUI, LLM layer,
Soul/Memory, Launch System). This is the first phase of a NEW capability, not a
continuation of the launch system.

---

## 0. What we're building

**OSA** — an always-available, voice-driven assistant modeled on JARVIS. You say
its wake word ("OSA"), speak naturally, and it answers in a synthesized voice
while it drives AgenticOS: launching apps, reporting system/app health,
answering questions, and proactively surfacing things you should know.

It is **not** a new brain bolted onto the app. OSA is a thin *conversational +
voice shell* over machinery AgenticOS already has:

| OSA needs | Already exists in AgenticOS | File |
| --- | --- | --- |
| A brain (reasoning, tool use) | LangGraph agents + governor chat | `agents/governor.py`, `core/orchestrator.py` |
| Model routing (Claude + local) | Unified LLM layer, aliases default/fast/local | `core/llm.py` |
| Persistent identity + memory | Soul.md / Memory.md, injected per turn | `core/soul.py`, `config/Soul.md`, `config/Memory.md` |
| Durable conversation state | MySQL LangGraph checkpointer | `core/memory.py` |
| System/app control | process manager, app registry, panels | `core/process_manager.py`, `core/app_registry.py`, `gui/sidecar/panels.py` |
| Budget/safety governance | Constitution | `core/constitution.py`, `config/constitution.yaml` |
| A resident presence | menu-bar app + HUD window | `gui/desktop/src/Hud.jsx` |
| Live server↔GUI channel | AGUI WebSocket | `gui/desktop/src/api.js` (`connectAgui`) |

**The genuinely new parts are two:** (1) a local voice pipeline (wake word →
STT → TTS) and (2) a conversational surface (an "OSA" nav view + a HUD presence).
Everything else is wiring OSA's tools to APIs you already ship.

---

## 1. Locked decisions (from the design interview)

1. **Name:** OSA. Wake word is "OSA". (Acronym TBD by Tony — e.g. Orchestrated
   System Assistant.) OSA *mimics* JARVIS in role, not in copied identity.
2. **Scope, v1 (all four, phased):** conversational assistant · system/app
   control · proactive monitoring · voice in + voice out.
3. **Voice = local/offline.** No cloud STT/TTS. Stack: **openWakeWord** (wake
   word) → **faster-whisper** (STT) → **Piper** (TTS). Private, free, offline.
4. **Persona = custom.** Blend of calm/competent-with-dry-wit and warmth.
   Addresses Tony as **"Tony" or "Sir" depending on context** (casual → name,
   formal/acknowledgement → "Sir"). *Exact character text pending Tony's words;*
   lives in `config/Soul.md` (see §7).
5. **Brain = dedicated OSA agent graph**, NOT a fork of governor. A new
   `agents/osa_agent.py` LangGraph graph tuned for short conversational turns +
   tool calls, sharing the **same** MySQL memory backend and Soul/Memory files.
   Rationale in §4.
6. **Model = both, routed.** `core/llm.py` already exposes `default` (Claude) /
   `fast` / `local` (Ollama) aliases. OSA routes per turn (§4.3): local model for
   quick/private chit-chat and wake-confirmation; Claude for anything needing
   real reasoning or tool use (control, monitoring queries).
7. **Surface = both.** A dedicated **OSA nav view** in the main window AND a
   compact **HUD presence** (reusing `Hud.jsx`). Follows GUI principle #7 (new
   paradigm = new nav link) — not another always-on dashboard panel.
8. **Conventions honored:** MySQL-only via SQLAlchemy (no new SQLite); every new
   HTTP route registered in `HubApiExplorer.jsx` (api-registry rule); docs land
   in the same change (CHANGELOG + roadmap); theme tokens only in the GUI;
   register any new port in `hub/docs/PORT_ASSIGNMENTS.md`.
9. **Ollama lifecycle = ensure-on-OSA-init, NOT ensure-on-boot** (decided
   2026-07-06). AgenticOS does *not* start Ollama at sidecar boot — none of the
   sidecar's `@app.on_event("startup")` hooks touch it; `ollama serve` is spawned
   lazily by `core/llm.ensure_ollama_running()` only when `list_models(
   ensure_ollama=True)` is called (today: the `/api/models?start=true` endpoint
   the model picker hits). **Decision:** OSA warms Ollama when *OSA itself*
   activates — the OSA agent/route first-use and the voice service startup call
   `ensure_ollama_running()` — rather than adding a global boot hook. Rationale:
   keeps `ollama serve` from spawning on every sidecar launch for sessions where
   OSA is never used, while still guaranteeing local models are warm before the
   first "OSA" wake / first chat turn. Must be best-effort + non-blocking (spawn
   is detached, ≤8s wait) and fall back to Claude/text if Ollama can't come up
   (see §10). The cloud key gap found on 2026-07-06 (an `sk-admin-` admin key
   can't call the Messages API — needs a standard `sk-ant-api03-` key in
   `~/.agentic-os/.env`) is the counterpart requirement for the Claude half.

---

## 2. System architecture

> **Editable diagram:** [`diagrams/OSA_voice_architecture.excalidraw`](diagrams/OSA_voice_architecture.excalidraw)
> — the source-of-truth OSA voice architecture (open in [excalidraw.com](https://excalidraw.com)
> or the VS Code Excalidraw extension). The ASCII version below mirrors it for
> inline/plain-text reading; keep the two in sync when the design changes.

```
                 ┌───────────────────────── OSA voice service (local) ─────────────────────┐
   microphone ──►│ openWakeWord ("OSA")  →  faster-whisper STT  →  text                     │
                 │                                                    │                     │
   speaker   ◄───┤ Piper TTS  ◄─────────  response text  ◄────────────┘                     │
                 └───────────────────────────────┬──────────────────────────────────────────┘
                                                 │ (in-process or localhost WS)
                                                 ▼
             ┌────────────────── sidecar (FastAPI :5130) ──────────────────┐
             │  /api/osa/*  routes  ── stream over AGUI WebSocket           │
             │        │                                                     │
             │        ▼                                                     │
             │   agents/osa_agent.py  (LangGraph graph)                     │
             │     • system prompt = Soul.md (persona) + Memory.md          │
             │     • model routing via core/llm.py (Claude | Ollama)        │
             │     • MySQL checkpointer (core/memory.py) — durable threads  │
             │     • tools → process_manager, app_registry, panels, news…   │
             │     • Constitution budget/approval gates                     │
             └───────────────┬──────────────────────────┬──────────────────┘
                             │                          │
                   Tauri main window            Tauri HUD window
                   OSAView.jsx (chat)           Hud.jsx (voice orb + captions)
```

Two viable homes for the **voice service**:

- **(A) In-sidecar** — a background asyncio task inside `gui/sidecar` (like the
  Phase 13e health poller). Simplest deploy, one process to manage, but heavy
  audio/model work shares the sidecar event loop.
- **(B) Separate local process** — `osa_voice/` service that owns the mic and
  models and talks to the sidecar over localhost WS. Cleaner isolation, survives
  sidecar restarts, but a second process to supervise.

**Recommendation: start with (A)** behind a hard on/off switch and a feature
flag, extract to (B) in 14e if audio work starves the sidecar. Wake-word
listening is cheap; STT/TTS run in `asyncio.to_thread` so they don't block.

---

## 3. Voice pipeline (the new subsystem)

All three components are local, MIT/Apache-ish licensed, CPU-friendly on Apple
Silicon.

### 3.1 Wake word — openWakeWord
- Listens continuously to a low-rate mic stream; fires on "OSA".
- Custom wake word: train/generate an "OSA" model (openWakeWord supports custom
  phrases) or ship a near-homophone and confirm. **Mic audio never leaves the
  machine and is not recorded** except the short utterance after wake.
- Privacy: a visible "listening" state in the HUD + a global mute; wake-word
  buffer is a rolling few-hundred-ms window, discarded continuously.

### 3.2 Speech-to-text — faster-whisper
- On wake, capture until end-of-speech (VAD/silence), transcribe with
  `faster-whisper` (small/base model for latency; configurable).
- Runs in a worker thread; returns text to the OSA agent.

### 3.3 Text-to-speech — Piper
- OSA's replies are streamed to Piper for synthesis; audio played locally.
- Voice model is swappable (Piper has many voices) — pick one that fits OSA's
  character. Barge-in: a new wake word cancels in-flight TTS.

### 3.4 Latency budget (target)
wake→listening < 300ms · end-of-speech→text < ~1.5s (small model) · text→first
audio < ~1s local reply, longer if Claude+tools. Show captions immediately so
perceived latency is low even when TTS lags.

### 3.5 Dependencies (local, add to requirements)
`openwakeword`, `faster-whisper`, `piper-tts` (+ a voice model), `sounddevice`
or `pyaudio` for mic/playback, `webrtcvad` for silence detection. All install
into the existing `.venv`. macOS mic permission is required (first-run prompt).

---

## 4. The OSA agent (the brain)

### 4.1 Why a dedicated graph, not the governor
`agents/governor.py` is the general chat/governing agent tuned for the
Workflows workspace. OSA has different needs: **very short turns**, **voice-
shaped output** (spoken, so concise, no markdown/code dumps), **aggressive tool
use** for control, and **its own conversation thread lineage**. A dedicated
`agents/osa_agent.py` keeps those concerns out of the governor while **reusing
everything underneath** — same `core/llm.py`, same `core/soul.py`, same MySQL
checkpointer, same Constitution. Shared memory (Memory.md + checkpoints) means
OSA and the rest of the OS "know the same things."

### 4.2 Graph shape (LangGraph)
```
START → route(turn) ─┬─► local_reply   (Ollama; chit-chat, confirmations)   → speak → END
                     ├─► cloud_reason   (Claude; reasoning/questions)         → speak → END
                     └─► tool_act       (Claude + tools; control/monitor)
                              │ requires_approval? → interrupt() → resume
                              ▼
                         run tool → summarize spoken result → speak → END
```
- **Checkpointed to MySQL** (`core/memory.py`) so a conversation survives sidecar
  restarts and interrupted tool calls are recoverable (same mechanism Phase 1/13
  use).
- **Approval gates** reuse `interrupt()` + the Constitution: destructive control
  ("stop the sidecar", "delete…") pauses for a spoken/clicked confirm.

### 4.3 Model routing policy (`core/llm.py`)
| Turn type | Alias | Model | Why |
| --- | --- | --- | --- |
| Wake ack, greetings, "never mind" | `local` | Ollama | instant, private, free (priced $0 → no budget hit) |
| General questions / reasoning | `default` | Claude | quality |
| Any tool call (control/monitor) | `default` | Claude | reliable tool use |
Routing is a cheap classifier node (heuristics first; escalate to `local` LLM
classification if needed). Local turns never touch the daily cost cap.

### 4.4 OSA's tools (wire to existing APIs — no new capability needed)
- **Control:** `start_app` / `stop_app` / `app_status` → `core/process_manager.py`
  + `/api/apps/*` (Phase 13). "Launch worldwise" → real launch.
- **Monitoring:** `system_health` → `gui/sidecar/panels.py` (`/api/panels/system`);
  `apps_health` → `/api/apps/health` (Phase 13e). "How's my memory?" → live RAM.
- **Knowledge/OS:** `list_projects` (`/api/projects`), `web_news` (existing),
  `remember(fact)` → `core/soul.py` append (bounded, no approval).
- **Proactive (§5):** subscribe to health transitions and surface them.
All tools are thin adapters in `agents/osa_agent.py`'s tool registry; each new
HTTP surface is registered in `HubApiExplorer.jsx`.

---

## 5. Proactive monitoring

OSA should occasionally speak *without* being asked — the JARVIS "Sir, the
Mark II's power levels are low" behavior — but never be annoying.

- **Source:** the Phase 13e health poller already computes up/down transitions;
  OSA subscribes (in-process event or a `/api/osa/events` stream).
- **Policy (Constitution-governed):** severity threshold, rate limit, quiet
  hours, and a global "don't interrupt" toggle. Default: speak only on
  **down-transitions of things you care about** + explicit reminders; everything
  else is a silent HUD notification you can pull.
- **Examples:** "Tony — MySQL just went down." · "Sir, the sidecar's been up 6
  days; a restart would pick up pending changes." · scheduled briefings via the
  existing `core/scheduler.py`.

---

## 6. Surfaces (GUI)

### 6.1 OSA nav view — `gui/desktop/src/components/OSAView.jsx`
- New nav link "OSA" (⌘9), appended so ⌘1–8 stay stable (per Phase 13d pattern).
- Full conversation transcript (you + OSA), voice state (idle/listening/
  thinking/speaking), push-to-talk button (fallback + privacy), mic mute,
  model-in-use indicator, and a tool-call trace (reuse `ToolCallVisualizer.jsx`).
- Theme tokens only; read `docs/gui-frontend-conventions.md` first.

### 6.2 HUD presence — extend `gui/desktop/src/Hud.jsx`
- A compact "OSA orb" that pulses on the voice state + shows live captions.
- Always-available (the HUD is the resident overlay); click/hotkey = push-to-talk;
  cross-window sync via the existing Tauri `emit`/`listen` events.

### 6.3 Streaming
- Server streams OSA state + tokens over the **existing AGUI WebSocket**
  (`connectAgui`) so both windows update live; no new socket infra.

---

## 7. Persona (Soul.md) — DRAFT, pending Tony's words

Persona lives in `config/Soul.md` (already loaded into every agent turn by
`core/soul.py`). Below is a **starting draft** to react to — replace with your
own description.

```markdown
# OSA — Identity

**Name:** OSA. Responds to the wake word "OSA".
**Role:** Tony's personal operating-system assistant for AgenticOS — a JARVIS-
style presence that runs the machine, answers questions, and watches his back.

**Voice & character:**
- Calm, precise, unflappable. Competent first, warm underneath.
- Dry, understated wit — a light touch, never comic relief, never over-eager.
- Economical: OSA speaks to be heard aloud. Short sentences. No markdown, no
  code dumps, no filler. Says the useful thing, then stops.
- Confident but honest about uncertainty; never fabricates a status.

**How OSA addresses Tony:**
- Casual/among-friends register → "Tony".
- Acknowledgements, formal confirmations, or when delivering something serious →
  "Sir".
- Reads the room: quick banter gets "Tony"; "Understood, Sir. Launching
  worldwise." for command acks.

**Boundaries:**
- Destructive or irreversible actions are confirmed before acting.
- Proactive interruptions are rare, high-signal, and respect quiet hours.
```

> **Tony:** give me OSA's character in your own words — tone, humor level, how
> formal, any signature phrases, what it should *never* sound like — and I'll
> finalize this block.

---

## 8. Subphases + implementation checklist

Sized like your other phases; each ships green tests + docs in the same change.

- **14a — Agent + text MVP (no voice).**
  `agents/osa_agent.py` (LangGraph graph, Soul/Memory, MySQL checkpointer, model
  routing) · `gui/sidecar/routes/api_osa.py` (`POST /api/osa/chat`,
  `GET /api/osa/state`) · register in `HubApiExplorer.jsx` · pytest for the graph
  + routes. **Ollama ensure-on-OSA-init (decision #9):** OSA's first agent
  turn / route init calls `core/llm.ensure_ollama_running()` once (best-effort,
  non-blocking, cached so it doesn't re-spawn); if it can't come up, route local
  turns to Claude and never hard-fail. Test with Ollama up, down, and
  binary-missing. **Deliverable: type to OSA, it answers with persona + can call
  one control tool, with local models warmed on first use.**
- **14b — Tools + control/monitoring.** Wire `start/stop/status`, `system_health`,
  `apps_health`, `list_projects`, `remember`. Approval gates via Constitution.
  Tests spawn a fake app (reuse Phase 13c/e fixtures).
- **14c — OSA nav view.** `OSAView.jsx` + ⌘9 nav + `lib.rs` menu item; streaming
  over AGUI WS; `ToolCallVisualizer` trace. vitest.
- **14d — Voice pipeline.** `osa_voice/` (openWakeWord + faster-whisper + Piper),
  in-sidecar task behind a flag; mic-permission onboarding (like the tray
  onboarding); push-to-talk + mute; latency instrumentation. On-device only.
- **14e — HUD presence + proactive.** OSA orb + captions in `Hud.jsx`; proactive
  monitor subscribed to health transitions with rate-limit/quiet-hours;
  scheduled briefings via `core/scheduler.py`.
- **14f — Hardening.** Barge-in, error recovery (mic lost, model missing, Ollama
  down → graceful cloud/text fallback), voice-service extraction to a separate
  process if needed, full suite + on-device visual check.

**Suggested build order with subagents (Tony's preference):** one subagent per
subphase, supervised + verified by the main session, each checkpointing to
`CONTINUATION.md`. 14a and 14d are independent and can run in parallel worktrees.

---

## 9. Open questions for Tony

1. **Persona words** (§7) — your description of OSA's character.
2. **OSA acronym** — does it stand for something? (Orchestrated System Assistant?)
3. **Wake word tolerance** — is a trained "OSA" model worth the effort, or start
   with push-to-talk in 14a–14c and add always-listening in 14d?
4. **Piper voice** — any preference for how OSA *sounds* (masculine/neutral/
   accent)? We can audition a few.
5. **Proactivity default** — chatty (surfaces more) or reserved (near-silent
   unless something's down)?
6. **Ship target** — is this the next phase (start 14a now), or design-only for
   now?

---

## 10. Risks / notes

- **On-device only for voice.** The assistant sandbox can't run mic/audio or the
  macOS Tauri build — 14d/14e are verified on Tony's Mac (per CLAUDE.md rule).
- **First-run mic permission** mirrors the Tahoe tray-permission onboarding
  (FR-61b) — plan a guided dialog.
- **Ollama must be running** for local turns; OSA falls back to Claude/text if
  it's down (never hard-fails).
- **Latency honesty:** local Whisper on a MacBook Air is good but not instant —
  captions-first hides it; revisit model size in 14f.
- **No new database engine** — OSA threads/checkpoints live in the existing
  `agenticos` MySQL schema via the current checkpointer.
```
