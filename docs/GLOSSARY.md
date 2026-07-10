# AgenticOS — Glossary

> **Purpose.** Canonical definitions for acronyms, project-specific terms,
> and technical concepts used across AgenticOS docs, code, and Brain2 notes.
> New to the project? Read this alongside `docs/README.md` and
> `docs/architecture.md`.
>
> **Maintenance policy.** This glossary is **living**. Any change that
> introduces a new acronym, project term, or non-obvious technical concept
> to the docs or codebase must also add an entry here — in the *same
> change*, same rule as `CHANGELOG.md` / `roadmap.md`. If you find a term
> in-repo that isn't here, add it. Outdated or missing entries are a bug.
>
> **Mirror.** A copy of this file lives at
> `~/Brain2/08 - Systems/Agentic OS/GLOSSARY.md`. Keep them in sync (this
> file is authoritative; Brain2 mirrors it).
>
> **Last full pass:** 2026-07-07 (Phase 14e shipped, Phase 13f pending).

---

## Contents

1. [Core project vocabulary](#1-core-project-vocabulary)
2. [Phases, planning, and process](#2-phases-planning-and-process)
3. [Architecture and runtime](#3-architecture-and-runtime)
4. [Persistence and data](#4-persistence-and-data)
5. [Frontend, desktop, and GUI](#5-frontend-desktop-and-gui)
6. [Voice, LLM, and OSA](#6-voice-llm-and-osa)
7. [Unix, macOS, and system ops](#7-unix-macos-and-system-ops)
8. [Web, protocols, and general tech](#8-web-protocols-and-general-tech)

---

## 1. Core project vocabulary

Terms coined by or specific to AgenticOS / Tony's stack.

**AgenticOS** — This project. A personal agentic desktop OS built on a
FastAPI sidecar (port 5130), a Tauri/React desktop GUI, LangGraph
workflows, and a MySQL backend (schema `agenticos`). Repo:
`~/Codehome/AgenticOS/`.

**AGUI** — "Agent UI." The WebSocket event stream (`/ws/agui`) the sidecar
uses to push live workflow state — step starts/ends, token deltas, tool
calls, interrupts — to the desktop GUI. See `gui/desktop/src/api.js`
(`connectAgui`).

**Approval Queue** — GUI-side counterpart to the CLI's `input()` prompt.
When a workflow hits `requires_approval: true` and LangGraph raises
`interrupt()`, the sidecar's `runner.py` parks the paused run on this
queue; the desktop GUI resolves it over HTTP so the human can approve or
deny. See [constitution.md](constitution.md).

**Brain2** — Tony's Obsidian-based personal knowledge management vault at
`~/Brain2/`. AgenticOS reads it freely (spec, research, notes) and writes
to it only through the guarded filesystem tool into allowlisted roots.
Not to be confused with an AI's "brain" — it's a note vault.

**Codehome** — Tony's monorepo-style parent workspace at `~/Codehome/`,
holding 20+ personal projects. AgenticOS discovers and manages sibling
apps in Codehome via `app.json` manifests.

**Constitution** — The runtime-enforced safety model. Defined as YAML in
`config/constitution.yaml`, enforced in `core/constitution.py` at every
tool-call boundary. **Enforcement, not advisory** — a violation raises an
exception that halts the run (CLI exit code 2). See
[constitution.md](constitution.md).

**Continuation (CONTINUATION.md)** — The single-file session handoff
document at `docs/CONTINUATION.md`. Every session must checkpoint here
before ending: what shipped, what's in flight (file + line specifics),
exact next steps, verification commands. The next Claude session reads
this file first. See `CLAUDE.md` §"Session-budget rule".

**Governor / Governing Agent** — The top-level agent that supervises other
agents and enforces the Constitution during tool use. Lives in
`agents/governor.py`. Distinct from the OSA agent.

**Hub** — Historically an external Go server on port 8085 that discovered
and controlled Codehome apps. **RETIRED as of Phase 9d (late June 2026).**
Its functionality was absorbed into the sidecar natively via
`core/app_registry.py` and `core/process_manager.py`. Port 8085 is marked
RETIRED in `hub/docs/PORT_ASSIGNMENTS.md`. The name "Hub" persists in
`HubApiExplorer.jsx`, `tools/hub_mcp.py`, and older docs — treat those as
"Hub-era APIs, now sidecar-served."

**HUD** — "Heads-Up Display." A compact secondary Tauri window
(`gui/desktop/src/Hud.jsx`) that surfaces OSA presence, alerts, and status
without opening the full app. Shares origin with the `main` window; state
sync uses Tauri events. Distinct from "the HUD panel" in the dashboard.

**OSA** — The voice-driven ambient assistant introduced in Phase 14. Wake
word is "OSA". Working expansion: *Orchestrated System Assistant*
(pending Tony's final wording). Modeled on JARVIS in role, not identity.
Fully local voice pipeline: openWakeWord → faster-whisper → Piper. See
[PHASE14_OSA_ASSISTANT.md](PHASE14_OSA_ASSISTANT.md).

**Sidecar** — The FastAPI Python service that is the OS's beating heart.
Listens on port **5130**. Serves the workflow runner, panel data APIs,
AGUI WebSocket, PTY WebSocket, `/api/apps`, `/api/osa/*`, and everything
else the GUI consumes. Started via `./.venv/bin/python -m gui.sidecar`.
Source: `gui/sidecar/`.

**Soul.md / Memory.md** — Persistent identity + memory files
(`config/Soul.md`, `config/Memory.md`) injected into every LLM turn by
`core/soul.py`. Soul is the persona (voice, values); Memory is
accumulated context.

**`promote-to-system`** — A reusable Claude skill that graduates a shipped
project from `01 - Projects/` to `08 - Systems/` in Brain2 and creates the
Operations note. Part of Tony's Codehome → Brain2 flow.

---

## 2. Phases, planning, and process

**FR** — "Feature Requirement." A numbered requirement from the PRD,
e.g. FR-28 (a dashboard panel). Grep for `FR-\d+` to find them in docs.

**HITL** — "Human In The Loop." A design pattern where an automated
process pauses and awaits explicit human approval before continuing.
Implemented in AgenticOS via LangGraph `interrupt()` + `Command(resume=)`
on the CLI, and via the Approval Queue in the GUI.

**MVP** — "Minimum Viable Product." The smallest thing that proves the
core loop end-to-end. Phase 1 was AgenticOS's MVP.

**Phase (Phase 1, Phase 13a, etc.)** — A numbered work unit in the
renumbered PRD. Phases 1–7 are complete; recent history includes Phase 9
(Hub Absorption), Phase 10 (Governor smoke tests), Phase 13 (Data-Driven
Launch System — 13a shipped, 13f pending), Phase 14 (OSA, in progress).
Canonical list: `docs/roadmap.md`. Phase numbering must match the PRD.

**PoC** — "Proof of Concept." A throwaway spike proving an idea is
feasible before real implementation.

**PRD** — "Product Requirements Document." The master spec.
`Brain2/01 - Projects/PRDs/Agentic OS - Full PRD.md` is authoritative.
Phase numbering in `docs/roadmap.md` must match the PRD.

**Sub-phase (Phase 9a, 9b, 9c, 9d)** — A phase split into serial slices,
each independently committable. Used when a phase is too big to land as
one change.

**TR** — "Technical Requirement." Numbered like FRs (e.g. TR-03, TR-07,
TR-10) but describing an implementation constraint rather than a user
feature. TR-10 is "sidecar on port 5130." Grep for `TR-\d+`.

---

## 3. Architecture and runtime

**Agent** — A plain Python module in `agents/` exposing an `ACTIONS` dict
of `action(state: dict) -> dict` functions. No classes, no framework
coupling. Current agents: `brain2`, `hub`, `briefing`, `governor`, and
`osa_agent` (Phase 14).

**AGENT_REGISTRY** — The dict in `core/orchestrator.py` mapping agent
names in `workflows.yaml` to their `ACTIONS` dicts. Adding an action means
adding a function to that dict — no other wiring.

**Checkpoint / Checkpointer** — LangGraph's mechanism for persisting the
full graph state after every node. AgenticOS uses
`langgraph-checkpoint-mysql`'s `PyMySQLSaver` against the `AgenticOS`
schema; tables are `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`,
`checkpoint_migrations`. Makes HITL interrupts durable across process
restarts.

**FastAPI** — The Python web framework that hosts the sidecar. Async,
Pydantic-based, generates OpenAPI automatically at `/openapi.json`.

**HTTP status codes used deliberately** — `403 approval_required`
(constitution gate), `409` (state conflict, e.g. model not installed),
`422` (unknown-but-valid-shape input), `503` (dependency down —
`news_db.py`/`tasks_db.py` when MySQL is unreachable).

**LangGraph** — The framework AgenticOS uses to model workflows as
directed graphs of Python nodes. Provides native interrupt/resume (HITL)
and pluggable checkpointing.

**MCP** — "Model Context Protocol." Anthropic's open protocol for
LLM ↔ tool servers. AgenticOS uses MCP three ways: (1) the
filesystem tool talks to `@modelcontextprotocol/server-filesystem` over
stdio; (2) `tools/hub_mcp.py` exposes Hub-era operations as MCP tools;
(3) Tony's Claude Desktop connects to third-party MCP servers.

**Orchestrator** — `core/orchestrator.py`. Loads `workflows.yaml`, builds
a linear LangGraph `StateGraph` (one node per step), compiles with the
MySQL checkpointer, and runs it. Owns cost/token accounting and the
interrupt/resume dance.

**ProcessManager** — `core/process_manager.py`. Asyncio-based lifecycle
manager for child processes (managed Codehome apps): venv-Python rewriting,
per-app log files at `~/.agentic-os/logs/<app_id>.log`, graceful stop
(SIGTERM → SIGKILL fallback), port-probe fallback for externally-managed
apps.

**Runner** — `gui/sidecar/runner.py`. Executes workflows in worker threads
on behalf of the GUI, parking `requires_approval` interrupts on the
Approval Queue (the GUI equivalent of the CLI's `input()` loop).

**StateGraph** — LangGraph's typed graph primitive. State is a
`TypedDict`; nodes are pure functions; edges connect them.

**TypedDict** — Python typing construct (`typing.TypedDict`) for a dict
whose keys and value types are known statically. LangGraph state is a
`TypedDict` with reducer channels (e.g. `outputs`, `tokens_used`).

**Workflow** — A named sequence of steps declared in
`config/workflows.yaml`. Each step names an agent, an action, and its
inputs. Runs are one execution of a workflow.

---

## 4. Persistence and data

**Autocommit** — A MySQL connection mode where each statement commits
immediately (no explicit `BEGIN`/`COMMIT`). `PyMySQLSaver` requires an
autocommit connection so `saver.setup()` can create checkpoint tables.

**CRUD** — "Create, Read, Update, Delete." The four basic persistence
operations most `*_db.py` modules expose.

**Migration** — An idempotent schema change. AgenticOS runs migrations
via `gui/sidecar/migrations.py` (raw `ALTER`s), separate from
`models.py` (SQLAlchemy `create_all` for new tables). `create_all` never
alters existing tables — that's the migrations file's job.

**MySQL** — The one and only database. Schema `agenticos`. Locked in
Phase 13a (2026-07-02). Config in `~/.agentic-os/.env` (`MYSQL_HOST/
USER/PASS/DB/PORT`). Requires ≥ 8.0.19 (or MariaDB ≥ 10.7.1) for the
LangGraph MySQL checkpointer.

**ORM** — "Object-Relational Mapper." A library that maps Python classes
to SQL tables. **SQLAlchemy is the sole ORM** for AgenticOS (locked Phase
13a). No new raw `mysql.connector` code.

**PyMySQLSaver** — The LangGraph checkpointer implementation from
`langgraph-checkpoint-mysql`. Persists graph state to MySQL for durable
interrupt/resume.

**PK** — "Primary Key." A column (or set) uniquely identifying a row.

**Schema (as in `agenticos` schema)** — In MySQL, "schema" ≡ "database."
The `agenticos` schema holds all AgenticOS tables. A separate
`agenticos_test` schema is used by pytest fixtures (never in-memory
SQLite for new tests).

**SQLAlchemy** — The Python ORM/DB-toolkit AgenticOS uses. Models live in
`gui/sidecar/models.py`; sessions/engines in `gui/sidecar/db.py`.

**SQLite** — File-based DB. **Retired** for AgenticOS state as of Phase
13a. `data/state.db` is gone. Only lingering references are in legacy
modules (`news_db.py`, `tasks_db.py`, some test files) queued for
migration in Phase 13f.

**TTL** — "Time To Live." How long a cached value stays fresh before
refresh. `app_registry.py` uses a 60-second TTL cache for Codehome app
discovery.

---

## 5. Frontend, desktop, and GUI

**ARIA** — "Accessible Rich Internet Applications." A W3C spec for
attributes (e.g. `aria-label`) making rich UI accessible to assistive
tech.

**CSS variable / design token** — Custom property like `--accent`,
`--text`. AgenticOS's theme tokens live in `gui/desktop/src/theme.css`
(`:root` for the terracotta default, `[data-theme=…]` for cyber, future,
term). **Never** invent tokens — undefined vars fail silently and break
hierarchy. See `docs/gui-frontend-conventions.md`.

**DOM** — "Document Object Model." The in-memory tree the browser builds
from HTML. React manipulates it via a virtual DOM diff.

**HTMX** — A JS library that lets HTML attributes trigger AJAX requests
and swap fragments. Being considered for the browser-dashboard fallback
(FR-34).

**HubApiExplorer** — `gui/desktop/src/components/HubApiExplorer.jsx`. The
in-app API browser. **Every** HTTP endpoint the app ships must appear in
its `ENDPOINTS` array in the same change that adds/renames the route (see
`docs/api-registry.md`).

**JSX** — JavaScript syntax extension for embedding HTML-like markup in
React components. AgenticOS uses `.jsx` (not TSX) for React source.

**Orb (OSAOrb) / orb states** — The JARVIS-style reactor orb
(`gui/desktop/src/components/OSAOrb.jsx`) that renders OSA's presence in the
right rail. Driven by a `data-state` of `idle | listening | thinking |
speaking | alert`; precedence is alert > live voice state > chat/context
state. Voice states come from a 1.5s poll of `/api/osa/voice/state`.

**PTY** — "Pseudo-Terminal." A pair of virtual character devices that
lets a program pretend to be a terminal. AgenticOS's interactive terminal
panel is `xterm.js` in the browser talking to a PTY on the sidecar via
`/ws/terminal`.

**React** — The frontend UI library. AgenticOS uses **React 19** (with
Vite as the bundler).

**Tauri** — Rust-based framework for building native desktop apps with a
web frontend. AgenticOS uses **Tauri 2**. Native window/menu/tray code
lives in `gui/desktop/src-tauri/src/lib.rs`; frontend in
`gui/desktop/src/`. Menu-bar tray icon is an `NSStatusItem`.

**Vite** — Fast frontend dev server / bundler. Serves the React dev build
under `tauri dev` and produces the production bundle for release.

**WCAG** — "Web Content Accessibility Guidelines." The standards
accessibility audits target — AgenticOS aims at WCAG 2.1 AA.

**xterm.js** — A JavaScript terminal emulator running in the browser.
Renders the PTY output stream in the terminal panel.

---

## 6. Voice, LLM, and OSA

**Barge-in** — Interrupting OSA mid-speech. A new wake word, a push-to-talk
press, or mute cancels in-flight Piper playback: `stop_speaking()` terminates
the `afplay` process and abandons the remaining sentence chunks. Design §3.3.

**Claude** — Anthropic's LLM family. AgenticOS routes to Claude (via
`~/.agentic-os/.env` `ANTHROPIC_API_KEY`) for tool-use and heavy
reasoning. Requires a standard `sk-ant-api03-` key; `sk-admin-` keys
cannot call the Messages API.

**Conversation mode / follow-up window** — After a spoken reply finishes, an
~8s window (`followup_window_s`) in which the next utterance needs no wake
word. Guarded by an echo check (opens only post-playback), a hallucination
stoplist, and a ≥2-word minimum. See `osa_voice/pipeline.py`.

**Energy gate (`min_rms`)** — An RMS-amplitude floor (default 0.02) a frame
must clear, on TOP of VAD, to count as speech. Rejects a TV or background
media across the room that VAD alone calls "speech." Live-calibrated with Tony
(his voice measured ~7× the TV's frame energy). 0 disables the gate.

**faster-whisper** — A fast, CTranslate2-based reimplementation of
OpenAI's Whisper. Used as OSA's local speech-to-text engine.

**Headless voice test** — A unit test that exercises the voice state machine
without a real microphone or the optional audio deps, by injecting fake
`sounddevice` + `webrtcvad` modules and controlling the per-frame VAD verdict.
Lets CI assert pipeline transitions (e.g. idle-vs-listening) deterministically.
See `gui/sidecar/tests/test_osa_idle_state.py`.

**JARVIS** — Iron Man's fictional AI assistant. OSA mimics JARVIS's
*role* (calm, competent, always-on) — not copied identity.

**LLM** — "Large Language Model." The pluggable adapter registry in
`core/llm.py` supports four provider types: `anthropic`, `ollama`,
`openai_compatible`, `google`.

**Model aliases (default / fast / local)** — Roles resolved by
`core/llm.py` to actual models. `default` is Claude for reasoning; `fast`
is a cheap Claude tier for quick turns; `local` is an Ollama model for
private/offline use. OSA routes per turn based on need.

**Ollama** — Local LLM runtime. AgenticOS's `core/llm.py` speaks to it
via the `ollama` provider adapter. `ensure_ollama_running()` spawns
`ollama serve` lazily on first use (not at sidecar boot).

**openWakeWord** — A local wake-word detection library. Listens
continuously for "OSA" and gates the STT pipeline.

**Persona** — OSA's voice/values, defined in `config/Soul.md`.
Calm-competent-with-dry-wit + warmth. Addresses Tony as "Tony" or "Sir"
depending on context.

**Piper** — A local neural TTS engine. Produces OSA's spoken responses.

**Presence greeting** — OSA's time-of-day "welcome back" line, shown and
spoken when the app launches or regains focus after being away past a
threshold (~3 min). Templated per bucket (morning / afternoon / evening /
late night, cheek dialed to 3–4) with a pending-items clause. Backend:
`gui/sidecar/osa_greeting.py` + `POST /api/osa/greeting`; wired in `App.jsx`.

**Resting state** — The state the voice pipeline returns to when not in an
active turn: `idle` when voice is enabled with deps present, else `disabled`
(`_resting_state()`). The armed wake loop waits in the resting state (idle)
and flips to `listening` only when VAD detects directed speech (2026-07-09
fix — the orb no longer reads "listening" while merely armed and waiting).

**STT** — "Speech To Text." Voice input → text. OSA uses faster-whisper.

**Tool guardrail (7B tool-calling)** — Local 7B-class models aren't
reliable for tool calls. When a user pins a small local model but the
turn needs a tool, OSA escalates to Claude and marks the reply
`escalated` ("Took Claude for that one"). See Phase 14 brain-switching
work.

**TTS** — "Text To Speech." Text output → voice. OSA uses Piper.

**VAD** — "Voice Activity Detection." Frame-level speech/non-speech
classification (via `webrtcvad`) that gates utterance capture: pre-roll until
speech starts, end-of-speech after `end_silence_ms` of non-speech. Paired with
the energy gate (`min_rms`) so background noise doesn't count as speech.

**Wake word** — The trigger phrase ("OSA") that flips the assistant from
passive-listening to active. Detected locally by openWakeWord.

---

## 7. Unix, macOS, and system ops

**launchd** — macOS's system-wide daemon manager (analog of systemd). Runs
Tony's Brain2 vault-index job and other scheduled tasks. Configured via
`.plist` files.

**NSStatusItem** — macOS API for a menu-bar item. AgenticOS's tray icon.
Requires "Allow in Menu Bar" permission on macOS 26 (Tahoe)+ — new apps
default to OFF, so the icon creates successfully but stays invisible
until the user toggles it. See `CLAUDE.md` §"macOS Tahoe" note.

**PID** — "Process ID." Numeric identifier for a running process. Tracked
in `app_processes` table for managed Codehome apps.

**SIGKILL** — Unix signal (9) that force-terminates a process
immediately; cannot be caught or ignored. AgenticOS falls back to SIGKILL
after a SIGTERM grace period.

**SIGTERM** — Unix signal (15) requesting graceful shutdown. Process can
catch it and clean up. AgenticOS sends this first when stopping managed
apps.

**Venv** — Python virtual environment. AgenticOS uses `./.venv/`; managed
Codehome apps get their venv Python rewritten in-place when launched via
`ProcessManager`.

**zsh** — Tony's default shell. Configured with Powerlevel10k / Starship
prompt switching.

---

## 8. Web, protocols, and general tech

**API** — "Application Programming Interface." Almost always means the
HTTP + JSON surface the sidecar (or historically the Hub) exposes.

**ASCII** — Text encoding covering plain English characters. Comes up in
"ASCII art" and encoding-sensitive edits.

**CLI** — "Command-Line Interface." The `agentic-os` command in
`main.py`. Three subcommands: `run`, `list`, `history`.

**CSS** — "Cascading Style Sheets." Styling for the GUI. AgenticOS's
tokens live in `gui/desktop/src/theme.css`.

**GET / POST / PUT / PATCH / DELETE** — HTTP verbs. AgenticOS routes
follow REST conventions (`GET` read, `POST` create, `PATCH` partial
update, `PUT` replace, `DELETE` remove).

**GUI** — "Graphical User Interface." The Tauri desktop app.

**HTML** — "HyperText Markup Language." The web's document format.

**HTTP / HTTPS** — "HyperText Transfer Protocol" (secure). The wire
protocol for the sidecar's REST API and Hub-era endpoints.

**JSON** — "JavaScript Object Notation." Payload format for every
sidecar API and most config files (`app.json`).

**KV** — "Key-Value." A simple lookup store — a table with a `key`
column and a `value` column. `osa_settings` (Phase 14) is a KV table.

**OpenAPI** — Spec for describing HTTP APIs. FastAPI auto-generates
`/openapi.json`; the recommended API-Explorer auto-discovery reads this.

**PR** — "Pull Request." A proposed set of changes on GitHub.

**REST** — "Representational State Transfer." The API style AgenticOS
uses — resource nouns, HTTP verbs, JSON payloads.

**RSS** — "Really Simple Syndication." The XML feed format Web News
ingests. Feed catalogue lives in MySQL (`news_feeds` / `news_categories`).

**URL** — "Uniform Resource Locator." A web address.

**UX** — "User Experience." Umbrella for how the app feels to use.

**WebSocket (WS)** — Bidirectional persistent connection over HTTP.
AgenticOS uses two: `/ws/agui` (workflow event stream) and
`/ws/terminal` (PTY stream).

**YAML** — "YAML Ain't Markup Language." Human-friendly config format.
Used for `workflows.yaml`, `constitution.yaml`, `settings.yaml`.

---

## How to add an entry

1. Pick the right section (create a new one only if truly needed).
2. Write the entry in the same style: **term** — one-line definition,
   then optional context (where it lives, why it matters, links).
3. If the term crosses sections, put it in the most specific one and
   cross-reference from the others.
4. Update `docs/CHANGELOG.md` with a one-line note (`glossary: added X`).
5. Sync the Brain2 copy at `~/Brain2/08 - Systems/Agentic OS/GLOSSARY.md`.

Missing terms are a bug. File one against yourself and fix it.
