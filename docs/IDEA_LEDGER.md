# Idea Ledger — what came of every idea

> **Purpose.** Every idea/want/feature captured in these docs gets a VERDICT
> here — nothing silently rots. Statuses: **✅ SHIPPED** · **🟧 IN PROGRESS** ·
> **🧪 EXPLORED** (investigated, learning recorded, not built) · **🅿 PARKED**
> (known, deliberately waiting) · **🚫 ABANDONED** (decided no, with reason).
> Rule: when a session ships/kills/parks an idea, update BOTH this ledger and
> the inline tag in the idea's home doc. Created 2026-07-21 (evidence mined
> from roadmap.md, CHANGELOG.md, and the code).

## feature-backlog.md (intake batch, locked 2026-06-14) — ALL SHIPPED, doc CLOSED

| Idea | Status | What came of it |
|---|---|---|
| NF-1 GitHub repo | ✅ SHIPPED | `github.com/tseneadza/AgenticOS`, remote of record |
| NF-2 Nav → dashboard registry | ✅ SHIPPED | Phase 8 ✅ 2026-06-14 (FR-46–51) |
| NF-3 Governing agent | ✅ SHIPPED | Phase 10 ✅ 2026-07-01 (FR-52–59, 22-model registry) |
| NF-4 Absorb the Hub | ✅ SHIPPED | Phase 9 ✅ 2026-06-26 (Hub `:8085` retired) |

## OSAORB_IDEAS.md (orb parking lot, 2026-07-09)

| # | Idea | Status | What came of it |
|---|---|---|---|
| 1 | Announcements flash `alert` | ✅ SHIPPED | 2026-07-09 — `App.jsx` `onAnnounced()` → decaying orb alert (comments cite "OSAORB_IDEAS #1") |
| 2 | Push state (kill 1.5s poll) | 🅿 PARKED | Poll still in `OSAOrb.jsx`; per ponytail note, only act if lag is felt (shorter poll = 1-line first try) |
| 3 | Armed affordance | ✅ SHIPPED | `wake_active` from `/api/osa/voice/state` → static armed indicator on idle orb |
| 4 | Orb as control surface | 🅿 PARKED | Debate still open (presence vs surfaces); no controls in the orb today |
| 5 | Greeting pulse on orb | 🅿 PARKED | Greeting speaks (14e) but no visual orb beat yet |
| 6 | `prefers-reduced-motion` | ✅ SHIPPED | Media-query guard in `OSAOrb.jsx` (and the rail) |
| 7 | Thinking isn't a black box | 🅿 PARKED | No elapsed/tool hint in the caption yet; AGUI data already flows |
| 8 | Time-of-day tint | 🅿 PARKED | Greeting has time buckets; orb hue does not. Cosmetic, do last |

## UI_VISION.md ("shock and awe" north star, 2026-07-09)

| Idea | Status | What came of it |
|---|---|---|
| Whole-shell polish vision | 🅿 PARKED (active north star) | No slices executed as of 2026-07-21 — OSA functionality deliberately prioritized (per the doc's own preamble). The orb + OSARail already embody the target language; pull slices ponytail-sized when UI time comes |

## Plan docs (whole-doc dispositions)

| Doc | Status | What came of it |
|---|---|---|
| PRD-addendum-phases-8-10.md | ✅ ACCOMPLISHED | Phases 8/9/10 all shipped (2026-06-14 → 07-01) |
| hub-decommission-plan.md | ✅ ACCOMPLISHED | Phase 9 complete 2026-06-26; Hub Go server retired |
| ROADMAP-APPEND.md + IMPLEMENTATION-PLAN.md (Aesthetic System + Bling) | ✅ ACCOMPLISHED (renumbered) | Shipped as: theme system (`theme.css`, 14 `data-theme` skins, View ▸ Theme), menu-bar tray status item (FR-61 in `lib.rs`), Minimize-to-HUD (⌘⇧H + `HudOsaPresence`). NOTE: their "Phase 12/13" numbering was overtaken — actual 12/13 became Diagnostics/Launch System |
| PROJECT_CREATION_PLAN.md | ✅ ACCOMPLISHED | Phase 11 complete 2026-07-01 (11a–11d) |
| PHASE13_DATA_DRIVEN_LAUNCH_SYSTEM.md | ✅ ACCOMPLISHED | Phase 13 closed 2026-07-03 (13a–13f) |
| PHASE14_OSA_ASSISTANT.md | ✅ CORE SHIPPED | 14a–14f + presence (07-07 → 07-11); voice deps at equilibrium 2026-07-21, live mic pass pending |
| PHASE15_OSA_SYSTEM_MCP.md | ✅ ACCOMPLISHED | 15a–15e complete 2026-07-14 (29 OSA tools, effect mode live) |
| PHASE16_BRAIN_SCANNER.md | 🟧 IN PROGRESS | 16a–16c built 2026-07-15; Tony's on-device pass → 16d writes → 16e polish |

## Open questions worth a verdict (carried from docs)

| Question | Source | Status |
|---|---|---|
| Allowlist prefix-chaining gap (`ls && rm x`) | roadmap 15e | 🅿 PARKED — flagged, owner's call |
| 2 FDA-dependent mail tests need hermetic fixture | CONTINUATION 07-15 | 🅿 PARKED — chip filed |
| `/login` for the pi-node claude | CONTINUATION 07-15 | 🅿 PARKED — human item |

## Brain Scanner — semantic connections via vector DB

| Idea | Status | What came of it |
|---|---|---|
| Vector-DB semantic drill-down for the orb | 🅿 PARKED (wants own phase) | Intent (Tony, 2026-07-21): drill into a cluster of notes and keep surfacing their semantic connections to other docs — similarity edges layered onto the orb/graph, beyond explicit `[[wikilinks]]` + `#tags`. The auto-continue runner sketched `api_chroma.py` (Chroma) on 2026-07-19 but it was **Flask in a FastAPI app, never wired to the UI, never installed, crash-looped the sidecar**; backed out + deleted 2026-07-21. Build it right as a scoped Phase 16 follow-on: proper FastAPI router, a deliberate `chromadb` (or alt) dependency decision, an embeddings/backfill design, and the orb UI. See roadmap Phase 16 "semantic connections" entry. |
